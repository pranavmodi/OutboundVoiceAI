"""Patient providers — Simulation (DB-backed) and Live (RadFlow CallListData API)."""
import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.db.models import PatientRow, PatientCallStateRow
from app.models import (
    Patient,
    Language,
    IntakeStatus,
    RadflowStatus,
    STATUS_RANK,
    normalize_radflow_status,
)
from app.models.system_settings import DispatcherSettings

logger = logging.getLogger(__name__)

CALLLIST_API_URL = os.getenv(
    "CALLLIST_API_URL",
    "https://app.radflow360.com/chatbotapi/Patient/CallListData",
)
# Separate endpoint for writing call outcomes back to RadFlow.
CALLLIST_LOG_URL = os.getenv(
    "CALLLIST_LOG_URL",
    "https://app.radflow360.com/chatbotapi/Patient/SaveCallListLog",
)
# HL7 status update endpoint — used when a patient hits max attempts and
# transitions to "Couldnt Schedule" (status code 69).
HL7_STATUS_URL = os.getenv(
    "HL7_STATUS_URL",
    "https://app.radflow360.com/chatbotapi/Patient/UpdateHL7Status",
)
# Canonical HL7 status code strings per Neeraj's 2026-04-14 spec.
HL7_STATUS_CODE_COULDNT_SCHEDULE = "69"
CALLLIST_API_USER = os.getenv("CALLLIST_API_USER", "")
CALLLIST_API_PASSWORD = os.getenv("CALLLIST_API_PASSWORD", "")


def _row_to_patient(row: PatientRow) -> Patient:
    try:
        lang = Language(row.language)
    except ValueError:
        lang = Language.ENGLISH
    try:
        intake = IntakeStatus(row.intake_status)
    except ValueError:
        intake = IntakeStatus.COMPLETE

    p = Patient.__new__(Patient)
    p.patient_id = row.patient_id
    p.name = row.name
    p.phone = row.phone
    p.language = lang
    p.order_id = row.order_id
    p.order_created = row.order_created
    p.intake_status = intake
    p.has_called_in_before = row.has_called_in_before
    p.has_abandoned_before = row.has_abandoned_before
    p.ai_called_before = row.ai_called_before
    p.ai_attempt_count = row.ai_attempt_count or 0
    p.human_attempt_count = row.human_attempt_count or 0
    p.attempt_count = p.ai_attempt_count + p.human_attempt_count
    p.last_attempt_at = row.last_attempt_at
    p.last_outcome = row.last_outcome
    p.due_by = row.due_by
    p.radflow_status = row.radflow_status
    p.hl7_sent_at = row.hl7_sent_at
    p.priority_bucket = STATUS_RANK.get(row.radflow_status or "", 99)
    return p


def _sort_key(p: Patient):
    """Priority: fewest combined attempts first (interleaves across statuses),
    then status rank as tiebreaker (Ordered > No Show > Needs to Reschedule),
    then earliest due date, then oldest order."""
    far_future = datetime.max.replace(tzinfo=timezone.utc)
    return (
        p.total_attempts,
        STATUS_RANK.get(p.radflow_status or "", 99),
        p.due_by or far_future,
        p.order_created or far_future,
    )


def _eligible_for_queue(p: Patient, settings: DispatcherSettings, cutoff: datetime) -> bool:
    """Queue filter: in-scope status, under the per-status cap, past cooldown,
    not flagged invalid, has phone number."""
    if not (p.phone or "").strip():
        return False  # No phone number — skip entirely
    if STATUS_RANK.get(p.radflow_status or "", 99) >= 99:
        return False  # Unknown status or already "Couldnt Schedule"
    if p.last_outcome == "invalid_number":
        return False
    if p.last_attempt_at is not None and p.last_attempt_at > cutoff:
        return False
    if p.total_attempts >= settings.max_attempts_for_status(p.radflow_status):
        return False
    return True


def _map_language(lang_str: str) -> Language:
    """Map RadFlow LANGUAGE string to Language enum."""
    mapping = {
        "english": Language.ENGLISH,
        "spanish": Language.SPANISH,
        "chinese": Language.CHINESE,
    }
    return mapping.get(lang_str.lower().strip(), Language.ENGLISH) if lang_str else Language.ENGLISH


def _parse_radflow_datetime(value: str) -> Optional[datetime]:
    """Parse a RadFlow datetime string into an aware UTC datetime.

    RadFlow timestamps look like: '11-20-2025 1:56: 00' (with an odd space
    before seconds) or '12-28-2025 11:30 AM'.  Be lenient about both.
    """
    if not value:
        return None
    v = value.strip().replace(": ", ":")
    for fmt in ("%m-%d-%Y %H:%M:%S", "%m-%d-%Y %I:%M %p", "%m-%d-%Y %H:%M"):
        try:
            return datetime.strptime(v, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _add_business_days(start: datetime, days: int) -> datetime:
    """Add N business days (skipping Sat/Sun) to a datetime."""
    result = start
    added = 0
    while added < days:
        result = result + timedelta(days=1)
        if result.weekday() < 5:  # Mon=0..Fri=4
            added += 1
    return result


def _api_record_to_patient(rec: dict) -> Patient:
    """Convert a CallListData record to a Patient object."""
    lang = _map_language(rec.get("LANGUAGE", "english"))
    intake = IntakeStatus.COMPLETE if rec.get("IntakeCompleted", True) else IntakeStatus.INCOMPLETE

    p = Patient.__new__(Patient)
    p.patient_id = rec.get("PatientId", "")
    p.name = f"{rec.get('GivenName', '')} {rec.get('FamilyName', '')}".strip()
    p.phone = rec.get("CELLPHONE", "") or ""
    p.language = lang
    p.order_id = rec.get("InternalStudyId")
    # order_created = when the order was placed in RadFlow (INSERTIONDATETIME)
    p.order_created = _parse_radflow_datetime(rec.get("INSERTIONDATETIME", ""))
    p.intake_status = intake
    p.has_called_in_before = (rec.get("CB", 0) or 0) > 0
    p.has_abandoned_before = (rec.get("status", "") or "").upper() == "NO SHOW"
    p.ai_called_before = False
    # Split counts: human side comes from RadFlow (VM + CB), AI side is zero
    # at ingest — the merge step overlays our local AI attempt count.
    p.human_attempt_count = (rec.get("VM", 0) or 0) + (rec.get("CB", 0) or 0)
    p.ai_attempt_count = 0
    p.attempt_count = p.human_attempt_count
    p.last_attempt_at = None
    p.last_outcome = rec.get("status")
    p.radflow_status = normalize_radflow_status(rec.get("status")) or RadflowStatus.ORDERED.value
    p.hl7_sent_at = None
    # Per spec: DueBy = OrderCreated + 2 business days (unless HasCalledInBefore,
    # in which case there's no 2-day SLA — fall back to order_created so they
    # sort naturally by when the order was placed).
    if p.order_created:
        if p.has_called_in_before:
            p.due_by = p.order_created
        else:
            p.due_by = _add_business_days(p.order_created, 2)
    else:
        p.due_by = None
    p.priority_bucket = STATUS_RANK.get(p.radflow_status or "", 99)
    return p


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------
class BasePatientProvider(ABC):
    """Interface for patient data access."""

    @abstractmethod
    async def get_all_patients(self) -> list[Patient]:
        ...

    @abstractmethod
    async def get_patient(self, patient_id: str) -> Optional[Patient]:
        ...

    @abstractmethod
    async def get_outbound_queue(
        self,
        max_attempts_ordered: int = 4,
        max_attempts_other: int = 4,
        min_hours_between: int = 6,
    ) -> list[Patient]:
        ...

    @abstractmethod
    async def get_next_candidate(
        self,
        max_attempts_ordered: int = 4,
        max_attempts_other: int = 4,
        min_hours_between: int = 6,
    ) -> Optional[Patient]:
        ...

    @abstractmethod
    async def update_patient_after_call(self, patient_id: str, outcome: str, increment_attempt: bool = True):
        ...

    @abstractmethod
    async def mark_patient_invalid_number(self, patient_id: str, reason: str):
        ...

    @abstractmethod
    async def reserve_for_dialing(self, patient_id: str, call_id: str) -> bool:
        """Atomically claim a patient for dialing. Returns True on success,
        False if the patient is already claimed by another caller. Used to
        prevent double-dial races when dispatcher ticks overlap."""
        ...

    @abstractmethod
    async def rekey_dialing(self, patient_id: str, old_call_id: str, new_call_id: str) -> bool:
        """Atomically swap the dialing lock from old_call_id to new_call_id.
        Returns False if the lock no longer matches old_call_id (someone
        else released or re-keyed it). Used by the dispatcher to swap a
        provisional dispatch-* lock for the real call_id once start_call
        succeeds, without ever leaving the patient unlocked."""
        ...

    @abstractmethod
    async def release_dialing(self, patient_id: str) -> None:
        """Release a dialing claim. Safe to call on an already-released patient."""
        ...

    @abstractmethod
    async def reap_stale_dialing(self, older_than_seconds: int) -> int:
        """Clear dialing claims older than the cutoff (stuck-dial reaper).
        Returns the number of claims cleared."""
        ...

    @abstractmethod
    async def clear_all_dialing(self) -> int:
        """Clear every dialing claim — called once on dispatcher startup.
        Returns the number of claims cleared."""
        ...


# ---------------------------------------------------------------------------
# Simulation (DB-backed) provider
# ---------------------------------------------------------------------------
class SimulationPatientProvider(BasePatientProvider):
    """Manages patient records with PostgreSQL storage (simulation mode)."""

    async def get_all_patients(self) -> list[Patient]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(PatientRow))
            patients = [_row_to_patient(r) for r in result.scalars().all()]
        return sorted(patients, key=_sort_key)

    async def get_patient(self, patient_id: str) -> Optional[Patient]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(PatientRow).where(PatientRow.patient_id == patient_id)
            )
            row = result.scalar_one_or_none()
            return _row_to_patient(row) if row else None

    async def get_outbound_queue(
        self,
        max_attempts_ordered: int = 4,
        max_attempts_other: int = 4,
        min_hours_between: int = 6,
    ) -> list[Patient]:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=min_hours_between)
        settings = DispatcherSettings(
            max_attempts_ordered=max_attempts_ordered,
            max_attempts_other=max_attempts_other,
        )

        async with AsyncSessionLocal() as session:
            # Exclude patients currently being dialed — prevents a second
            # dispatcher tick from picking a patient we've already claimed.
            result = await session.execute(
                select(PatientRow).where(PatientRow.dialing_call_id.is_(None))
            )
            patients = [_row_to_patient(r) for r in result.scalars().all()]

        filtered = [p for p in patients if _eligible_for_queue(p, settings, cutoff)]
        return sorted(filtered, key=_sort_key)

    async def get_next_candidate(
        self,
        max_attempts_ordered: int = 4,
        max_attempts_other: int = 4,
        min_hours_between: int = 6,
    ) -> Optional[Patient]:
        queue = await self.get_outbound_queue(
            max_attempts_ordered=max_attempts_ordered,
            max_attempts_other=max_attempts_other,
            min_hours_between=min_hours_between,
        )
        return queue[0] if queue else None

    async def update_patient_after_call(
        self,
        patient_id: str,
        outcome: str,
        increment_attempt: bool = True,
    ):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(PatientRow).where(PatientRow.patient_id == patient_id)
            )
            row = result.scalar_one_or_none()
            if row:
                if increment_attempt:
                    row.ai_attempt_count = (row.ai_attempt_count or 0) + 1
                    row.attempt_count = (row.ai_attempt_count or 0) + (row.human_attempt_count or 0)
                row.last_attempt_at = datetime.now(timezone.utc)
                row.last_outcome = outcome
                row.ai_called_before = True

                # Mirror the live flow: flip to "Couldnt Schedule" when the
                # patient hits their per-status cap.  Sim doesn't POST HL7.
                from app.providers.settings_provider import get_settings_provider
                settings = await get_settings_provider().get_settings()
                cap = settings.dispatcher_settings.max_attempts_for_status(row.radflow_status)
                if (
                    row.hl7_sent_at is None
                    and STATUS_RANK.get(row.radflow_status or "", 99) < 99
                    and row.attempt_count >= cap
                ):
                    row.radflow_status = RadflowStatus.COULDNT_SCHEDULE.value
                    row.hl7_sent_at = datetime.now(timezone.utc)
                    logger.info("Sim patient %s hit max attempts (%s/%s) → Couldnt Schedule",
                                patient_id, row.attempt_count, cap)

                row.priority_bucket = STATUS_RANK.get(row.radflow_status or "", 99)
                await session.commit()

    async def mark_patient_invalid_number(self, patient_id: str, reason: str):
        """Flag patient as invalid number to prevent retries."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(PatientRow).where(PatientRow.patient_id == patient_id)
            )
            row = result.scalar_one_or_none()
            if row:
                row.last_outcome = "invalid_number"
                row.ai_called_before = True
                row.last_attempt_at = datetime.now(timezone.utc)
                await session.commit()
                logger.info("Patient %s flagged invalid_number: %s", patient_id, reason)

    # -- Simulation-only methods --

    async def add_patient(self, patient: Patient):
        async with AsyncSessionLocal() as session:
            row = PatientRow(
                patient_id=patient.patient_id,
                name=patient.name,
                phone=patient.phone,
                language=patient.language.value,
                order_id=patient.order_id,
                order_created=patient.order_created,
                intake_status=patient.intake_status.value,
                has_called_in_before=patient.has_called_in_before,
                has_abandoned_before=patient.has_abandoned_before,
                ai_called_before=patient.ai_called_before,
                ai_attempt_count=patient.ai_attempt_count,
                human_attempt_count=patient.human_attempt_count,
                attempt_count=patient.total_attempts,
                last_attempt_at=patient.last_attempt_at,
                last_outcome=patient.last_outcome,
                due_by=patient.due_by,
                radflow_status=patient.radflow_status or RadflowStatus.ORDERED.value,
                hl7_sent_at=patient.hl7_sent_at,
                priority_bucket=STATUS_RANK.get(patient.radflow_status or RadflowStatus.ORDERED.value, 99),
            )
            session.add(row)
            await session.commit()

    async def remove_patient(self, patient_id: str):
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(PatientRow).where(PatientRow.patient_id == patient_id)
            )
            await session.commit()

    async def reset_with_patients(self, patient_dicts: list[dict]):
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            await session.execute(delete(PatientRow))
            for i, pd in enumerate(patient_dicts, start=1):
                lang_str = pd.get("language", "en")
                try:
                    lang = Language(lang_str)
                except ValueError:
                    lang = Language.ENGLISH

                has_abandoned = pd.get("has_abandoned_before", False)
                ai_called = pd.get("ai_called_before", False)
                has_called_in = pd.get("has_called_in_before", False)
                # Scenarios can opt into a specific RadFlow status; otherwise
                # infer from the legacy flags (abandoned → No Show).
                raw_status = pd.get("radflow_status")
                if raw_status:
                    status = normalize_radflow_status(raw_status) or RadflowStatus.ORDERED.value
                elif has_abandoned:
                    status = RadflowStatus.NO_SHOW.value
                else:
                    status = RadflowStatus.ORDERED.value

                ai_attempts = pd.get("ai_attempt_count", pd.get("attempt_count", 0) if ai_called else 0)
                human_attempts = pd.get("human_attempt_count", 0)

                row = PatientRow(
                    patient_id=f"SIM{i:03d}",
                    name=pd["name"],
                    phone=pd["phone"],
                    language=lang.value,
                    order_id=f"ORD-SIM{i:03d}",
                    order_created=now - timedelta(days=1),
                    has_abandoned_before=has_abandoned,
                    has_called_in_before=has_called_in,
                    ai_called_before=ai_called,
                    ai_attempt_count=ai_attempts,
                    human_attempt_count=human_attempts,
                    attempt_count=ai_attempts + human_attempts,
                    due_by=now + timedelta(days=2),
                    radflow_status=status,
                    priority_bucket=STATUS_RANK.get(status, 99),
                )
                session.add(row)
            await session.commit()

    async def reset_to_sample_data(self):
        """Reset to initial sample data by re-running seed."""
        from app.db.seed import seed_sample_patients
        async with AsyncSessionLocal() as session:
            await session.execute(delete(PatientRow))
            await session.commit()
        async with AsyncSessionLocal() as session:
            await seed_sample_patients(session)
            await session.commit()

    # -- Dialing lock (simulation) -----------------------------------------

    async def reserve_for_dialing(self, patient_id: str, call_id: str) -> bool:
        from sqlalchemy import update
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                update(PatientRow)
                .where(
                    PatientRow.patient_id == patient_id,
                    PatientRow.dialing_call_id.is_(None),
                )
                .values(dialing_call_id=call_id, dialing_started_at=now)
            )
            await session.commit()
            return (result.rowcount or 0) > 0

    async def rekey_dialing(self, patient_id: str, old_call_id: str, new_call_id: str) -> bool:
        from sqlalchemy import update
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                update(PatientRow)
                .where(
                    PatientRow.patient_id == patient_id,
                    PatientRow.dialing_call_id == old_call_id,
                )
                .values(dialing_call_id=new_call_id)
            )
            await session.commit()
            return (result.rowcount or 0) > 0

    async def release_dialing(self, patient_id: str) -> None:
        from sqlalchemy import update
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(PatientRow)
                .where(PatientRow.patient_id == patient_id)
                .values(dialing_call_id=None, dialing_started_at=None)
            )
            await session.commit()

    async def reap_stale_dialing(self, older_than_seconds: int) -> int:
        from sqlalchemy import update
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                update(PatientRow)
                .where(
                    PatientRow.dialing_call_id.is_not(None),
                    PatientRow.dialing_started_at < cutoff,
                )
                .values(dialing_call_id=None, dialing_started_at=None)
            )
            await session.commit()
            return result.rowcount or 0

    async def clear_all_dialing(self) -> int:
        from sqlalchemy import update
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                update(PatientRow)
                .where(PatientRow.dialing_call_id.is_not(None))
                .values(dialing_call_id=None, dialing_started_at=None)
            )
            await session.commit()
            return result.rowcount or 0


# ---------------------------------------------------------------------------
# Live (RadFlow CallListData API) provider
# ---------------------------------------------------------------------------
class LivePatientProvider(BasePatientProvider):
    """Fetches patient call list from RadFlow CallListData API."""

    def __init__(
        self,
        url: str = CALLLIST_API_URL,
        log_url: str = CALLLIST_LOG_URL,
        user: str = CALLLIST_API_USER,
        password: str = CALLLIST_API_PASSWORD,
    ):
        self._url = url
        self._log_url = log_url
        self._auth = (user, password) if user else None
        self._client = httpx.AsyncClient(verify=False, timeout=30.0)
        self._cache: list[Patient] = []
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(seconds=60)
        # Mock-mode attempts tracked in memory only — cleared on restart or
        # when switching to non-mock mode, so real production state is untouched.
        self._mock_state: dict[str, dict] = {}  # patient_id → {attempt_count, last_attempt_at, last_outcome, invalid_number}

    async def _fetch(self, patient_id: Optional[str] = None) -> list[Patient]:
        """Fetch from API, with a 60-second cache."""
        now = datetime.now(timezone.utc)
        if (
            patient_id is None
            and self._cache
            and self._cache_time
            and (now - self._cache_time) < self._cache_ttl
        ):
            return self._cache

        url = self._url
        if patient_id:
            url = f"{self._url}?patientId={patient_id}"

        try:
            resp = await self._client.get(
                url,
                headers={"Accept": "application/json"},
                auth=self._auth,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("result", "")
            if not raw:
                return []
            records = json.loads(raw) if isinstance(raw, str) else raw
            patients = [_api_record_to_patient(r) for r in records]
            # Deduplicate by PatientId (API may return multiple rows per
            # study).  Collect all InternalStudyIds so the HL7 POST can
            # send them as a comma-separated value.
            seen: dict[str, Patient] = {}
            study_ids: dict[str, list[str]] = {}
            for p in patients:
                if p.patient_id not in seen:
                    seen[p.patient_id] = p
                    study_ids[p.patient_id] = []
                if p.order_id:
                    study_ids[p.patient_id].append(p.order_id)
            for pid, p in seen.items():
                ids = study_ids.get(pid, [])
                if ids:
                    p.order_id = ", ".join(ids)
            deduped = list(seen.values())
            if patient_id is None:
                self._cache = deduped
                self._cache_time = now
            return deduped
        except Exception as e:
            logger.warning("CallListData fetch failed: %s", e)
            return self._cache  # return stale cache on error

    # -- Outcome-to-RadFlow type mapping ----------------------------------

    # Maps our internal outcome to the RadFlow status code and a human-readable detail
    _OUTCOME_TO_RADFLOW = {
        "transferred":        {"status": "CB", "details": "AI transferred to human scheduler — pending confirmation"},
        "voicemail":          {"status": "VM",                "details": "AI left voicemail"},
        "callback_requested": {"status": "CB",                "details": "Patient requested callback"},
        "completed":          {"status": "CB",                "details": "AI call completed"},
        "wrong_number":       {"status": "COULD NOT SCHEDULE PATIENT", "details": "Wrong number reported"},
        "disconnected":       {"status": "COULD NOT SCHEDULE PATIENT", "details": "Number disconnected or invalid"},
        "failed":             {"status": "COULD NOT SCHEDULE PATIENT", "details": "Call could not be completed"},
        "no_answer":          {"status": "CB",                "details": "No answer"},
        "hung_up":            {"status": "CB",                "details": "Patient hung up"},
    }

    async def _post_outcome_to_radflow(self, patient_id: str, order_id: Optional[str], outcome: str, patient_name: str = ""):
        """POST call outcome back to RadFlow SaveCallListLog API.

        Skipped entirely when mock_mode is enabled (test calls should
        not write to production RadFlow).

        Payload fields per Danny/Neeraj agreement:
        - patientId, internalStudyId: identifiers
        - type: "Phone Call" (activity kind)
        - status: VM / CB / COULD NOT SCHEDULE PATIENT (never "PATIENT SCHEDULED" — this system only transfers, not schedules)
        - details: human-readable description (e.g. "AI transferred to human scheduler")
        - user: "AI"
        - logMethod: "Ordered Scheduler"
        """
        from app.providers.settings_provider import get_settings_provider
        from app.services.audit_service import log_audit_event
        settings = await get_settings_provider().get_settings()
        if settings.mock_mode:
            logger.info("RadFlow write-back SKIPPED (mock mode): patient=%s outcome=%s", patient_id, outcome)
            await log_audit_event(
                event_type="radflow", action="post_outcome", status="skipped",
                patient_id=patient_id, patient_name=patient_name, order_id=order_id,
                request_summary=f"Skipped (mock mode) — outcome={outcome}",
            )
            return

        mapping = self._OUTCOME_TO_RADFLOW.get(outcome, {"status": "CB", "details": f"AI call outcome: {outcome}"})
        payload = {
            "patientId": patient_id,
            "internalStudyId": order_id or "",
            "type": "Phone Call",
            "status": mapping["status"],
            "details": mapping["details"],
            "user": "AI",
            "logMethod": "Ordered Scheduler",
        }
        try:
            resp = await self._client.post(
                self._log_url,
                json=payload,
                headers={"Accept": "application/json"},
                auth=self._auth,
            )
            resp.raise_for_status()
            logger.info("RadFlow write-back OK: patient=%s status=%s details=%s", patient_id, mapping["status"], mapping["details"])
            await log_audit_event(
                event_type="radflow", action="post_outcome", status="success",
                patient_id=patient_id, patient_name=patient_name, order_id=order_id,
                request_summary=f"{mapping['status']} — {mapping['details']}",
                request_payload=payload, response_status=resp.status_code,
            )
        except Exception as e:
            logger.warning("RadFlow write-back failed for patient %s: %s", patient_id, e)
            await log_audit_event(
                event_type="radflow", action="post_outcome", status="failed",
                patient_id=patient_id, patient_name=patient_name, order_id=order_id,
                request_summary=f"{mapping['status']} — {mapping['details']}",
                request_payload=payload, error_message=str(e),
            )

    async def _post_hl7_status(self, order_id: str, status_code: str, patient_name: str = "") -> bool:
        """POST the HL7 status update for a patient (max-attempts-reached).

        Returns True on 2xx.  Skipped in mock mode.
        """
        from app.providers.settings_provider import get_settings_provider
        from app.services.audit_service import log_audit_event
        settings = await get_settings_provider().get_settings()
        if settings.mock_mode:
            logger.info("HL7 status SKIPPED (mock mode): studyId=%s status=%s", order_id, status_code)
            await log_audit_event(
                event_type="hl7", action="post_hl7_status", status="skipped",
                patient_name=patient_name, order_id=order_id,
                request_summary=f"Skipped (mock mode) — status_code={status_code}",
            )
            return False
        if not order_id:
            logger.warning("HL7 status SKIPPED: no order_id/studyId available")
            await log_audit_event(
                event_type="hl7", action="post_hl7_status", status="skipped",
                patient_name=patient_name,
                request_summary="Skipped — no order_id available",
            )
            return False

        payload = [{"studyId": order_id, "status": status_code}]
        try:
            resp = await self._client.post(
                HL7_STATUS_URL,
                json=payload,
                headers={"Accept": "application/json"},
                auth=self._auth,
            )
            resp.raise_for_status()
            logger.info("HL7 status sent OK: studyId=%s status=%s", order_id, status_code)
            await log_audit_event(
                event_type="hl7", action="post_hl7_status", status="success",
                patient_name=patient_name, order_id=order_id,
                request_summary=f"Status code {status_code} sent for studyId={order_id}",
                request_payload={"studyId": order_id, "status": status_code},
                response_status=resp.status_code,
            )
            return True
        except Exception as e:
            logger.warning("HL7 status POST failed for studyId=%s: %s", order_id, e)
            await log_audit_event(
                event_type="hl7", action="post_hl7_status", status="failed",
                patient_name=patient_name, order_id=order_id,
                request_summary=f"Status code {status_code} for studyId={order_id}",
                request_payload={"studyId": order_id, "status": status_code},
                error_message=str(e),
            )
            return False

    # -- Local state helpers -----------------------------------------------

    async def _get_local_state(self, session: AsyncSession, patient_id: str) -> Optional[PatientCallStateRow]:
        result = await session.execute(
            select(PatientCallStateRow).where(PatientCallStateRow.patient_id == patient_id)
        )
        return result.scalar_one_or_none()

    async def _get_all_local_state(self, session: AsyncSession) -> dict[str, PatientCallStateRow]:
        result = await session.execute(select(PatientCallStateRow))
        return {row.patient_id: row for row in result.scalars().all()}

    def _merge_local_state(self, patient: Patient, state: PatientCallStateRow) -> Patient:
        """Apply local call state on top of API-fetched patient data."""
        patient.ai_attempt_count = state.ai_attempt_count or 0
        patient.attempt_count = patient.ai_attempt_count + patient.human_attempt_count
        patient.last_attempt_at = state.last_attempt_at
        patient.last_outcome = state.last_outcome or patient.last_outcome
        patient.ai_called_before = state.ai_called_before
        patient.hl7_sent_at = state.hl7_sent_at
        if state.hl7_sent_at is not None:
            patient.radflow_status = RadflowStatus.COULDNT_SCHEDULE.value
        patient.priority_bucket = STATUS_RANK.get(patient.radflow_status or "", 99)
        return patient

    async def _is_mock_mode(self) -> bool:
        from app.providers.settings_provider import get_settings_provider
        settings = await get_settings_provider().get_settings()
        return bool(settings.mock_mode)

    def _merge_mock_state(self, patient: Patient, st: dict) -> Patient:
        """Apply in-memory mock call state on top of API-fetched patient data."""
        patient.ai_attempt_count = st.get("ai_attempt_count", st.get("attempt_count", 0))
        patient.attempt_count = patient.ai_attempt_count + patient.human_attempt_count
        patient.last_attempt_at = st.get("last_attempt_at")
        patient.last_outcome = st.get("last_outcome") or patient.last_outcome
        patient.ai_called_before = True
        patient.priority_bucket = STATUS_RANK.get(patient.radflow_status or "", 99)
        return patient

    async def _merge_all(self, patients: list[Patient], *, exclude_dialing: bool = False) -> list[Patient]:
        """Merge local state into all patients.

        In mock mode, only the in-memory mock_state is applied — the real
        patient_call_state DB table is left untouched so production state
        remains pristine.  In live mode, the DB state is applied as usual.

        When exclude_dialing is True, patients with an outstanding dialing
        lock (local state row) are dropped. Used by get_outbound_queue so
        a second dispatcher tick can't pick a patient mid-call.
        """
        mock_mode = await self._is_mock_mode()
        if mock_mode:
            merged = []
            for p in patients:
                st = self._mock_state.get(p.patient_id)
                if st:
                    if st.get("invalid_number"):
                        continue  # Skip invalid numbers entirely
                    if exclude_dialing and st.get("dialing_call_id"):
                        continue
                    p = self._merge_mock_state(p, st)
                merged.append(p)
            return merged

        async with AsyncSessionLocal() as session:
            state_map = await self._get_all_local_state(session)
        if not state_map:
            return patients
        merged = []
        for p in patients:
            st = state_map.get(p.patient_id)
            if st:
                if st.invalid_number:
                    continue  # Skip invalid numbers entirely
                if exclude_dialing and st.dialing_call_id is not None:
                    continue
                p = self._merge_local_state(p, st)
            merged.append(p)
        return merged

    # -- BasePatientProvider interface -------------------------------------

    async def get_all_patients(self) -> list[Patient]:
        patients = await self._fetch()
        return await self._merge_all(patients)

    async def get_patient(self, patient_id: str) -> Optional[Patient]:
        patients = await self._fetch(patient_id=patient_id)
        if not patients:
            return None
        patient = patients[0]
        mock_mode = await self._is_mock_mode()
        if mock_mode:
            st = self._mock_state.get(patient_id)
            if st:
                if st.get("invalid_number"):
                    return None
                patient = self._merge_mock_state(patient, st)
            return patient
        async with AsyncSessionLocal() as session:
            state = await self._get_local_state(session, patient_id)
        if state:
            if state.invalid_number:
                return None
            patient = self._merge_local_state(patient, state)
        return patient

    async def get_outbound_queue(
        self,
        max_attempts_ordered: int = 4,
        max_attempts_other: int = 4,
        min_hours_between: int = 6,
    ) -> list[Patient]:
        patients = await self._fetch()
        patients = await self._merge_all(patients, exclude_dialing=True)

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=min_hours_between)
        settings = DispatcherSettings(
            max_attempts_ordered=max_attempts_ordered,
            max_attempts_other=max_attempts_other,
        )

        filtered = []
        for p in patients:
            if not (p.phone or "").strip():
                from app.services.missing_phone_notifier import notify_missing_phone
                await notify_missing_phone(p.patient_id, p.name, p.order_id or "")
                continue
            if _eligible_for_queue(p, settings, cutoff):
                filtered.append(p)
        return sorted(filtered, key=_sort_key)

    async def get_next_candidate(
        self,
        max_attempts_ordered: int = 4,
        max_attempts_other: int = 4,
        min_hours_between: int = 6,
    ) -> Optional[Patient]:
        queue = await self.get_outbound_queue(
            max_attempts_ordered=max_attempts_ordered,
            max_attempts_other=max_attempts_other,
            min_hours_between=min_hours_between,
        )
        return queue[0] if queue else None

    async def update_patient_after_call(
        self,
        patient_id: str,
        outcome: str,
        increment_attempt: bool = True,
    ):
        mock_mode = await self._is_mock_mode()
        if mock_mode:
            # Track in memory only — real patient state is untouched
            st = self._mock_state.setdefault(patient_id, {
                "ai_attempt_count": 0,
                "attempt_count": 0,
                "last_attempt_at": None,
                "last_outcome": None,
                "invalid_number": False,
            })
            if increment_attempt:
                st["ai_attempt_count"] = st.get("ai_attempt_count", 0) + 1
                st["attempt_count"] = st["ai_attempt_count"]
            st["last_attempt_at"] = datetime.now(timezone.utc)
            st["last_outcome"] = outcome
            logger.info("Mock state updated: patient=%s outcome=%s ai_attempts=%s (in-memory only)",
                         patient_id, outcome, st["ai_attempt_count"])
            # RadFlow write-back already skipped in mock mode
            mock_name = ""
            for p in self._cache:
                if p.patient_id == patient_id:
                    mock_name = p.name
                    break
            await self._post_outcome_to_radflow(patient_id, None, outcome, patient_name=mock_name)
            return

        # 1. Update local state table (live mode)
        async with AsyncSessionLocal() as session:
            state = await self._get_local_state(session, patient_id)
            if state is None:
                state = PatientCallStateRow(patient_id=patient_id, attempt_count=0, ai_attempt_count=0)
                session.add(state)
            if increment_attempt:
                state.ai_attempt_count = (state.ai_attempt_count or 0) + 1
                state.attempt_count = state.ai_attempt_count
            state.last_attempt_at = datetime.now(timezone.utc)
            state.last_outcome = outcome
            state.ai_called_before = True
            await session.commit()
            ai_attempts = state.ai_attempt_count or 0
            hl7_already_sent = state.hl7_sent_at is not None
        logger.info("Local state updated: patient=%s outcome=%s ai_attempts=%s",
                     patient_id, outcome, ai_attempts)

        # 2. Write back to RadFlow (best-effort, non-blocking)
        # Look up cached patient record for order_id, status, and human count.
        cached: Optional[Patient] = None
        for p in self._cache:
            if p.patient_id == patient_id:
                cached = p
                break
        order_id = cached.order_id if cached else None
        await self._post_outcome_to_radflow(patient_id, order_id, outcome, patient_name=cached.name if cached else "")

        # 3. If this attempt pushed the patient past their status-specific cap,
        # fire the HL7 "Couldnt Schedule" write-back exactly once.
        if cached and not hl7_already_sent and increment_attempt:
            from app.providers.settings_provider import get_settings_provider
            settings = await get_settings_provider().get_settings()
            ds = settings.dispatcher_settings
            cap = ds.max_attempts_for_status(cached.radflow_status)
            total = ai_attempts + (cached.human_attempt_count or 0)
            if total >= cap:
                ok = await self._post_hl7_status(order_id or "", HL7_STATUS_CODE_COULDNT_SCHEDULE, patient_name=cached.name if cached else "")
                if ok:
                    async with AsyncSessionLocal() as session:
                        state = await self._get_local_state(session, patient_id)
                        if state is not None:
                            state.hl7_sent_at = datetime.now(timezone.utc)
                            await session.commit()
                    logger.info(
                        "Patient %s hit max attempts (%s/%s) for status=%s — HL7 Couldnt Schedule sent",
                        patient_id, total, cap, cached.radflow_status,
                    )

    async def mark_patient_invalid_number(self, patient_id: str, reason: str):
        mock_mode = await self._is_mock_mode()
        if mock_mode:
            st = self._mock_state.setdefault(patient_id, {
                "ai_attempt_count": 0,
                "attempt_count": 0,
                "last_attempt_at": None,
                "last_outcome": None,
                "invalid_number": False,
            })
            st["invalid_number"] = True
            st["last_outcome"] = "invalid_number"
            st["last_attempt_at"] = datetime.now(timezone.utc)
            logger.info("Mock state: patient %s flagged invalid_number (in-memory only): %s", patient_id, reason)
            mock_name = ""
            for p in self._cache:
                if p.patient_id == patient_id:
                    mock_name = p.name
                    break
            await self._post_outcome_to_radflow(patient_id, None, "disconnected", patient_name=mock_name)
            return

        async with AsyncSessionLocal() as session:
            state = await self._get_local_state(session, patient_id)
            if state is None:
                state = PatientCallStateRow(patient_id=patient_id, attempt_count=0, ai_attempt_count=0)
                session.add(state)
            state.invalid_number = True
            state.last_outcome = "invalid_number"
            state.last_attempt_at = datetime.now(timezone.utc)
            await session.commit()
        logger.info("Local state: patient %s flagged invalid_number: %s", patient_id, reason)

        # Write back to RadFlow
        order_id = None
        cached_name = ""
        for p in self._cache:
            if p.patient_id == patient_id:
                order_id = p.order_id
                cached_name = p.name
                break
        await self._post_outcome_to_radflow(patient_id, order_id, "disconnected", patient_name=cached_name)

    # -- Dialing lock (live) -----------------------------------------------

    async def reserve_for_dialing(self, patient_id: str, call_id: str) -> bool:
        """Claim the local-state row (or mock entry) so no other tick re-picks."""
        from sqlalchemy import update
        from sqlalchemy.exc import IntegrityError
        if await self._is_mock_mode():
            st = self._mock_state.setdefault(patient_id, {
                "ai_attempt_count": 0,
                "attempt_count": 0,
                "last_attempt_at": None,
                "last_outcome": None,
                "invalid_number": False,
                "dialing_call_id": None,
                "dialing_started_at": None,
            })
            if st.get("dialing_call_id"):
                return False
            st["dialing_call_id"] = call_id
            st["dialing_started_at"] = datetime.now(timezone.utc)
            return True

        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            state = await self._get_local_state(session, patient_id)
            if state is None:
                state = PatientCallStateRow(
                    patient_id=patient_id, attempt_count=0, ai_attempt_count=0,
                    dialing_call_id=call_id, dialing_started_at=now,
                )
                session.add(state)
                try:
                    await session.commit()
                    return True
                except IntegrityError:
                    # Another process inserted the row first. Roll back, then
                    # fall through to the UPDATE path below to claim the lock
                    # only if it's still free.
                    await session.rollback()
            else:
                if state.dialing_call_id is not None:
                    return False
            result = await session.execute(
                update(PatientCallStateRow)
                .where(
                    PatientCallStateRow.patient_id == patient_id,
                    PatientCallStateRow.dialing_call_id.is_(None),
                )
                .values(dialing_call_id=call_id, dialing_started_at=now)
            )
            await session.commit()
            return (result.rowcount or 0) > 0

    async def rekey_dialing(self, patient_id: str, old_call_id: str, new_call_id: str) -> bool:
        from sqlalchemy import update
        if await self._is_mock_mode():
            st = self._mock_state.get(patient_id)
            if st and st.get("dialing_call_id") == old_call_id:
                st["dialing_call_id"] = new_call_id
                return True
            return False
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                update(PatientCallStateRow)
                .where(
                    PatientCallStateRow.patient_id == patient_id,
                    PatientCallStateRow.dialing_call_id == old_call_id,
                )
                .values(dialing_call_id=new_call_id)
            )
            await session.commit()
            return (result.rowcount or 0) > 0

    async def release_dialing(self, patient_id: str) -> None:
        from sqlalchemy import update
        if await self._is_mock_mode():
            st = self._mock_state.get(patient_id)
            if st:
                st["dialing_call_id"] = None
                st["dialing_started_at"] = None
            return
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(PatientCallStateRow)
                .where(PatientCallStateRow.patient_id == patient_id)
                .values(dialing_call_id=None, dialing_started_at=None)
            )
            await session.commit()

    async def reap_stale_dialing(self, older_than_seconds: int) -> int:
        from sqlalchemy import update
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)
        if await self._is_mock_mode():
            cleared = 0
            for st in self._mock_state.values():
                started = st.get("dialing_started_at")
                if started is not None and started < cutoff:
                    st["dialing_call_id"] = None
                    st["dialing_started_at"] = None
                    cleared += 1
            return cleared
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                update(PatientCallStateRow)
                .where(
                    PatientCallStateRow.dialing_call_id.is_not(None),
                    PatientCallStateRow.dialing_started_at < cutoff,
                )
                .values(dialing_call_id=None, dialing_started_at=None)
            )
            await session.commit()
            return result.rowcount or 0

    async def clear_all_dialing(self) -> int:
        from sqlalchemy import update
        if await self._is_mock_mode():
            cleared = 0
            for st in self._mock_state.values():
                if st.get("dialing_call_id"):
                    st["dialing_call_id"] = None
                    st["dialing_started_at"] = None
                    cleared += 1
            return cleared
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                update(PatientCallStateRow)
                .where(PatientCallStateRow.dialing_call_id.is_not(None))
                .values(dialing_call_id=None, dialing_started_at=None)
            )
            await session.commit()
            return result.rowcount or 0


# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------
_sim_provider: Optional[SimulationPatientProvider] = None
_live_provider: Optional[LivePatientProvider] = None
_active_source: str = "simulation"


def _get_sim_provider() -> SimulationPatientProvider:
    global _sim_provider
    if _sim_provider is None:
        _sim_provider = SimulationPatientProvider()
    return _sim_provider


def _get_live_provider() -> LivePatientProvider:
    global _live_provider
    if _live_provider is None:
        _live_provider = LivePatientProvider()
    return _live_provider


def get_patient_provider() -> BasePatientProvider:
    """Get the active patient provider based on patient_source setting."""
    if _active_source == "live":
        return _get_live_provider()
    return _get_sim_provider()


def get_simulation_patient_provider() -> SimulationPatientProvider:
    """Always returns the simulation provider (for sim endpoints)."""
    return _get_sim_provider()


def set_patient_source(source: str):
    """Switch the active patient source ('simulation' or 'live')."""
    global _active_source
    if source not in ("simulation", "live"):
        raise ValueError(f"Invalid patient source: {source!r}")
    _active_source = source
    logger.info("Patient source set to: %s", source)


# Backwards-compatible alias
PatientProvider = SimulationPatientProvider
