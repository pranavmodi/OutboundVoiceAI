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
from app.models import Patient, Language, IntakeStatus

logger = logging.getLogger(__name__)

CALLLIST_API_URL = os.getenv(
    "CALLLIST_API_URL",
    "https://app.radflow360.com/chatbotapi/Patient/CallListData",
)
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
    p.attempt_count = row.attempt_count
    p.last_attempt_at = row.last_attempt_at
    p.last_outcome = row.last_outcome
    p.due_by = row.due_by
    p.priority_bucket = row.priority_bucket
    return p


def _compute_priority(has_abandoned_before: bool, ai_called_before: bool,
                       has_called_in_before: bool) -> int:
    if has_abandoned_before and not ai_called_before:
        return 1
    elif has_abandoned_before and ai_called_before:
        return 2
    elif not ai_called_before and has_called_in_before:
        return 3
    else:
        return 4


def _map_language(lang_str: str) -> Language:
    """Map RadFlow LANGUAGE string to Language enum."""
    mapping = {
        "english": Language.ENGLISH,
        "spanish": Language.SPANISH,
        "chinese": Language.CHINESE,
    }
    return mapping.get(lang_str.lower().strip(), Language.ENGLISH) if lang_str else Language.ENGLISH


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
    p.order_created = None
    p.intake_status = intake
    p.has_called_in_before = (rec.get("CB", 0) or 0) > 0
    p.has_abandoned_before = (rec.get("status", "") or "").upper() == "NO SHOW"
    p.ai_called_before = False
    p.attempt_count = (rec.get("VM", 0) or 0) + (rec.get("CB", 0) or 0)
    p.last_attempt_at = None
    p.last_outcome = rec.get("status")
    p.due_by = None
    # Parse Studydatetime as due_by if present
    study_dt = rec.get("Studydatetime", "")
    if study_dt:
        try:
            p.due_by = datetime.strptime(study_dt, "%m-%d-%Y %I:%M %p").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
    p.priority_bucket = _compute_priority(p.has_abandoned_before, p.ai_called_before, p.has_called_in_before)
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
    async def get_outbound_queue(self, max_attempts: int = 3, min_hours_between: int = 6) -> list[Patient]:
        ...

    @abstractmethod
    async def get_next_candidate(self, max_attempts: int = 3, min_hours_between: int = 6) -> Optional[Patient]:
        ...

    @abstractmethod
    async def update_patient_after_call(self, patient_id: str, outcome: str, increment_attempt: bool = True):
        ...

    @abstractmethod
    async def mark_patient_invalid_number(self, patient_id: str, reason: str):
        ...


# ---------------------------------------------------------------------------
# Simulation (DB-backed) provider
# ---------------------------------------------------------------------------
class SimulationPatientProvider(BasePatientProvider):
    """Manages patient records with PostgreSQL storage (simulation mode)."""

    async def get_all_patients(self) -> list[Patient]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(PatientRow).order_by(PatientRow.priority_bucket, PatientRow.due_by)
            )
            return [_row_to_patient(r) for r in result.scalars().all()]

    async def get_patient(self, patient_id: str) -> Optional[Patient]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(PatientRow).where(PatientRow.patient_id == patient_id)
            )
            row = result.scalar_one_or_none()
            return _row_to_patient(row) if row else None

    async def get_outbound_queue(self, max_attempts: int = 3, min_hours_between: int = 6) -> list[Patient]:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=min_hours_between)

        async with AsyncSessionLocal() as session:
            stmt = (
                select(PatientRow)
                .where(PatientRow.attempt_count < max_attempts)
                .where(
                    (PatientRow.last_outcome == None) |  # noqa: E711
                    (PatientRow.last_outcome != "invalid_number")
                )
                .where(
                    (PatientRow.last_attempt_at == None) |  # noqa: E711
                    (PatientRow.last_attempt_at <= cutoff)
                )
                .order_by(
                    PatientRow.priority_bucket,
                    PatientRow.due_by.asc().nulls_last(),
                    PatientRow.order_created.asc().nulls_last(),
                    PatientRow.attempt_count,
                )
            )
            result = await session.execute(stmt)
            return [_row_to_patient(r) for r in result.scalars().all()]

    async def get_next_candidate(self, max_attempts: int = 3, min_hours_between: int = 6) -> Optional[Patient]:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=min_hours_between)

        async with AsyncSessionLocal() as session:
            stmt = (
                select(PatientRow)
                .where(PatientRow.attempt_count < max_attempts)
                .where(
                    (PatientRow.last_outcome == None) |  # noqa: E711
                    (PatientRow.last_outcome != "invalid_number")
                )
                .where(
                    (PatientRow.last_attempt_at == None) |  # noqa: E711
                    (PatientRow.last_attempt_at <= cutoff)
                )
                .order_by(
                    PatientRow.priority_bucket,
                    PatientRow.due_by.asc().nulls_last(),
                    PatientRow.order_created.asc().nulls_last(),
                    PatientRow.attempt_count,
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return _row_to_patient(row) if row else None

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
                    row.attempt_count += 1
                row.last_attempt_at = datetime.now(timezone.utc)
                row.last_outcome = outcome
                row.ai_called_before = True
                row.priority_bucket = _compute_priority(
                    row.has_abandoned_before, row.ai_called_before, row.has_called_in_before
                )
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
                attempt_count=patient.attempt_count,
                last_attempt_at=patient.last_attempt_at,
                last_outcome=patient.last_outcome,
                due_by=patient.due_by,
                priority_bucket=patient.priority_bucket,
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
                    attempt_count=pd.get("attempt_count", 0),
                    due_by=now + timedelta(days=2),
                    priority_bucket=_compute_priority(has_abandoned, ai_called, has_called_in),
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


# ---------------------------------------------------------------------------
# Live (RadFlow CallListData API) provider
# ---------------------------------------------------------------------------
class LivePatientProvider(BasePatientProvider):
    """Fetches patient call list from RadFlow CallListData API."""

    def __init__(
        self,
        url: str = CALLLIST_API_URL,
        user: str = CALLLIST_API_USER,
        password: str = CALLLIST_API_PASSWORD,
    ):
        self._url = url
        self._auth = (user, password) if user else None
        self._client = httpx.AsyncClient(verify=False, timeout=30.0)
        self._cache: list[Patient] = []
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(seconds=60)

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
            # Deduplicate by PatientId (API may return multiple rows per study)
            seen: dict[str, Patient] = {}
            for p in patients:
                if p.patient_id not in seen:
                    seen[p.patient_id] = p
            deduped = list(seen.values())
            if patient_id is None:
                self._cache = deduped
                self._cache_time = now
            return deduped
        except Exception as e:
            logger.warning("CallListData fetch failed: %s", e)
            return self._cache  # return stale cache on error

    # -- Outcome-to-RadFlow type mapping ----------------------------------

    _OUTCOME_TO_RADFLOW_TYPE = {
        "transferred": "PATIENT SCHEDULED",
        "voicemail": "VM",
        "callback_requested": "CB",
        # Everything else maps to a generic failure type
        "wrong_number": "COULD NOT SCHEDULE PATIENT",
        "disconnected": "COULD NOT SCHEDULE PATIENT",
        "failed": "COULD NOT SCHEDULE PATIENT",
        "completed": "CB",  # Completed without transfer ≈ callback
    }

    async def _post_outcome_to_radflow(self, patient_id: str, order_id: Optional[str], outcome: str):
        """POST call outcome back to RadFlow CallListData API."""
        radflow_type = self._OUTCOME_TO_RADFLOW_TYPE.get(outcome, "CB")
        payload = {
            "patientId": patient_id,
            "internalStudyId": order_id or "",
            "type": radflow_type,
        }
        try:
            resp = await self._client.post(
                self._url,
                json=payload,
                headers={"Accept": "application/json"},
                auth=self._auth,
            )
            resp.raise_for_status()
            logger.info("RadFlow write-back OK: patient=%s type=%s", patient_id, radflow_type)
        except Exception as e:
            logger.warning("RadFlow write-back failed for patient %s: %s", patient_id, e)

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
        patient.attempt_count = max(patient.attempt_count, state.attempt_count)
        patient.last_attempt_at = state.last_attempt_at
        patient.last_outcome = state.last_outcome or patient.last_outcome
        patient.ai_called_before = state.ai_called_before
        # Recompute priority bucket with updated flags
        patient.priority_bucket = _compute_priority(
            patient.has_abandoned_before, patient.ai_called_before, patient.has_called_in_before
        )
        return patient

    async def _merge_all(self, patients: list[Patient]) -> list[Patient]:
        """Merge local state into all patients."""
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
        async with AsyncSessionLocal() as session:
            state = await self._get_local_state(session, patient_id)
        if state:
            if state.invalid_number:
                return None
            patient = self._merge_local_state(patient, state)
        return patient

    async def get_outbound_queue(self, max_attempts: int = 3, min_hours_between: int = 6) -> list[Patient]:
        patients = await self._fetch()
        patients = await self._merge_all(patients)

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=min_hours_between)

        filtered = [
            p for p in patients
            if p.attempt_count < max_attempts
            and (p.last_attempt_at is None or p.last_attempt_at <= cutoff)
        ]

        return sorted(filtered, key=lambda p: (
            p.priority_bucket,
            p.due_by or datetime.max.replace(tzinfo=timezone.utc),
            p.order_created or datetime.max.replace(tzinfo=timezone.utc),
            p.attempt_count,
        ))

    async def get_next_candidate(self, max_attempts: int = 3, min_hours_between: int = 6) -> Optional[Patient]:
        queue = await self.get_outbound_queue(max_attempts, min_hours_between)
        return queue[0] if queue else None

    async def update_patient_after_call(
        self,
        patient_id: str,
        outcome: str,
        increment_attempt: bool = True,
    ):
        # 1. Update local state table
        async with AsyncSessionLocal() as session:
            state = await self._get_local_state(session, patient_id)
            if state is None:
                state = PatientCallStateRow(patient_id=patient_id)
                session.add(state)
            if increment_attempt:
                state.attempt_count += 1
            state.last_attempt_at = datetime.now(timezone.utc)
            state.last_outcome = outcome
            state.ai_called_before = True
            await session.commit()
        logger.info("Local state updated: patient=%s outcome=%s attempts=%s",
                     patient_id, outcome, state.attempt_count)

        # 2. Write back to RadFlow (best-effort, non-blocking)
        # Look up order_id from cache
        order_id = None
        for p in self._cache:
            if p.patient_id == patient_id:
                order_id = p.order_id
                break
        await self._post_outcome_to_radflow(patient_id, order_id, outcome)

    async def mark_patient_invalid_number(self, patient_id: str, reason: str):
        async with AsyncSessionLocal() as session:
            state = await self._get_local_state(session, patient_id)
            if state is None:
                state = PatientCallStateRow(patient_id=patient_id)
                session.add(state)
            state.invalid_number = True
            state.last_outcome = "invalid_number"
            state.last_attempt_at = datetime.now(timezone.utc)
            await session.commit()
        logger.info("Local state: patient %s flagged invalid_number: %s", patient_id, reason)

        # Write back to RadFlow
        order_id = None
        for p in self._cache:
            if p.patient_id == patient_id:
                order_id = p.order_id
                break
        await self._post_outcome_to_radflow(patient_id, order_id, "disconnected")


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
