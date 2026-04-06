"""REST API endpoints for dashboard."""
import html
import os
import logging
from fastapi import APIRouter, HTTPException, Form, Request
from fastapi.responses import Response
from typing import Optional

from app.providers import get_queue_provider, get_mock_queue_provider, get_patient_provider, get_simulation_patient_provider, get_call_log_provider, get_settings_provider
from app.services.call_orchestrator import get_orchestrator
from app.services import safe_create_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/status")
async def get_system_status():
    """Get overall system status."""
    queue_provider = get_queue_provider()
    patient_provider = get_patient_provider()
    call_log_provider = get_call_log_provider()

    queue_state = queue_provider.get_state()
    outbound_queue = await patient_provider.get_outbound_queue()
    active_call = await call_log_provider.get_active_call()
    stats = await call_log_provider.get_statistics()

    return {
        "queue_state": queue_state.to_dict(),
        "outbound_queue_count": len(outbound_queue),
        "has_active_call": active_call is not None,
        "active_call": active_call.to_dict() if active_call else None,
        "statistics": stats,
    }


@router.get("/queue")
async def get_queue_state():
    """Get current queue state (FreePBX simulation)."""
    queue_provider = get_queue_provider()
    return queue_provider.get_state().to_dict()


@router.post("/queue/simulate/busy")
async def simulate_busy_queue():
    """Simulate a busy queue scenario."""
    queue_provider = get_mock_queue_provider()
    queue_provider.simulate_busy_queue()
    return {"status": "ok", "queue_state": queue_provider.get_state().to_dict()}


@router.post("/queue/simulate/quiet")
async def simulate_quiet_queue():
    """Simulate a quiet queue scenario."""
    queue_provider = get_mock_queue_provider()
    queue_provider.simulate_quiet_queue()
    return {"status": "ok", "queue_state": queue_provider.get_state().to_dict()}


@router.post("/queue/simulate/ami-failure")
async def simulate_ami_failure():
    """Simulate AMI connection failure."""
    queue_provider = get_mock_queue_provider()
    queue_provider.simulate_ami_failure()
    return {"status": "ok", "queue_state": queue_provider.get_state().to_dict()}


@router.post("/queue/simulate/ami-recovery")
async def simulate_ami_recovery():
    """Simulate AMI connection recovery."""
    queue_provider = get_mock_queue_provider()
    queue_provider.simulate_ami_recovery()
    return {"status": "ok", "queue_state": queue_provider.get_state().to_dict()}


@router.post("/queue/{queue_name}")
async def update_queue(
    queue_name: str,
    Calls: Optional[int] = None,
    Holdtime: Optional[int] = None,
    AvailableAgents: Optional[int] = None,
):
    """Update a specific queue's state (simulation only)."""
    queue_provider = get_mock_queue_provider()
    queue_provider.set_queue_state(
        queue_name=queue_name,
        Calls=Calls,
        Holdtime=Holdtime,
        AvailableAgents=AvailableAgents,
    )
    return {"status": "ok", "queue_state": queue_provider.get_state().to_dict()}


@router.get("/patients")
async def get_patients():
    """Get all patients in the system."""
    patient_provider = get_patient_provider()
    patients = await patient_provider.get_all_patients()
    return {"patients": [p.to_dict() for p in patients]}


@router.post("/patients")
async def add_patient(
    name: str,
    phone: str,
    language: str = "en",
    has_abandoned_before: bool = False,
    has_called_in_before: bool = False,
    ai_called_before: bool = False,
    attempt_count: int = 0,
):
    """Add a patient to the simulation queue and save to active scenario."""
    from datetime import datetime, timedelta, timezone
    from app.models import Patient, Language, IntakeStatus
    from app.db.models import SimulationScenarioRow
    from app.db import AsyncSessionLocal
    from sqlalchemy import select
    import uuid

    # Validate language
    try:
        lang = Language(language)
    except ValueError:
        lang = Language.ENGLISH

    # Generate a unique patient ID
    patient_id = f"SIM-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now(timezone.utc)

    patient = Patient(
        patient_id=patient_id,
        name=name,
        phone=phone,
        language=lang,
        order_id=f"ORD-{patient_id}",
        order_created=now - timedelta(days=1),
        intake_status=IntakeStatus.COMPLETE,
        has_called_in_before=has_called_in_before,
        has_abandoned_before=has_abandoned_before,
        ai_called_before=ai_called_before,
        attempt_count=attempt_count,
        due_by=now + timedelta(days=2),
    )

    # Add to simulation queue
    sim_provider = get_simulation_patient_provider()
    await sim_provider.add_patient(patient)
    print(f"[ADD_PATIENT] Added patient to queue: id={patient_id}, name={name}, phone={phone}")

    # Also save to active scenario if it exists
    saved_to_scenario = False
    settings_provider = get_settings_provider()
    settings = await settings_provider.get_settings()
    print(f"[ADD_PATIENT] Active scenario ID: {settings.active_scenario_id}")

    if settings.active_scenario_id:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SimulationScenarioRow).where(
                    SimulationScenarioRow.id == settings.active_scenario_id
                )
            )
            scenario_row = result.scalar_one_or_none()
            if scenario_row:
                # Add patient to scenario's patient list
                patient_data = {
                    "name": name,
                    "phone": phone,
                    "language": language,
                    "has_abandoned_before": has_abandoned_before,
                    "has_called_in_before": has_called_in_before,
                    "ai_called_before": ai_called_before,
                    "attempt_count": attempt_count,
                }
                current_patients = scenario_row.patients or []
                print(f"[ADD_PATIENT] Scenario '{scenario_row.label}' has {len(current_patients)} patients, adding new one")
                scenario_row.patients = current_patients + [patient_data]
                await session.commit()
                saved_to_scenario = True
                print(f"[ADD_PATIENT] Saved patient to scenario '{scenario_row.label}', now has {len(scenario_row.patients)} patients")
            else:
                print(f"[ADD_PATIENT] Scenario not found: {settings.active_scenario_id}")
    else:
        logger.debug("[ADD_PATIENT] No active scenario, patient only added to queue")

    return {
        "status": "ok",
        "patient": patient.to_dict(),
        "saved_to_scenario": saved_to_scenario,
    }


@router.delete("/patients/{patient_id}")
async def delete_patient(patient_id: str):
    """Delete a patient from the simulation queue and active scenario."""
    from app.db.models import SimulationScenarioRow
    from app.db import AsyncSessionLocal
    from sqlalchemy import select

    # Get patient first before deleting
    sim_provider = get_simulation_patient_provider()
    patient = await sim_provider.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    patient_phone = patient.phone

    # Also remove from active scenario if it exists and is not builtin
    removed_from_scenario = False
    settings_provider = get_settings_provider()
    settings = await settings_provider.get_settings()
    if settings.active_scenario_id:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SimulationScenarioRow).where(
                    SimulationScenarioRow.id == settings.active_scenario_id
                )
            )
            scenario_row = result.scalar_one_or_none()
            if scenario_row:
                current_patients = scenario_row.patients or []
                # Filter out the patient with matching phone
                new_patients = [p for p in current_patients if p.get("phone") != patient_phone]
                if len(new_patients) < len(current_patients):
                    scenario_row.patients = new_patients
                    await session.commit()
                    removed_from_scenario = True

    # Delete from simulation queue
    await sim_provider.remove_patient(patient_id)

    return {"status": "ok", "removed_from_scenario": removed_from_scenario}


@router.put("/patients/{patient_id}")
async def update_patient(
    patient_id: str,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    language: Optional[str] = None,
    has_abandoned_before: Optional[bool] = None,
    has_called_in_before: Optional[bool] = None,
    ai_called_before: Optional[bool] = None,
    attempt_count: Optional[int] = None,
):
    """Update a patient in the simulation queue and active scenario."""
    from app.db.models import SimulationScenarioRow, PatientRow
    from app.db import AsyncSessionLocal
    from sqlalchemy import select
    from app.models import Language

    # Get current patient first
    sim_provider = get_simulation_patient_provider()
    patient = await sim_provider.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    old_phone = patient.phone

    # Update in database
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PatientRow).where(PatientRow.patient_id == patient_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Patient not found")

        if name is not None:
            row.name = name
        if phone is not None:
            row.phone = phone
        if language is not None:
            try:
                row.language = Language(language).value
            except ValueError:
                row.language = "en"
        if has_abandoned_before is not None:
            row.has_abandoned_before = has_abandoned_before
        if has_called_in_before is not None:
            row.has_called_in_before = has_called_in_before
        if ai_called_before is not None:
            row.ai_called_before = ai_called_before
        if attempt_count is not None:
            row.attempt_count = attempt_count

        # Recompute priority
        from app.providers.patient_provider import _compute_priority
        row.priority_bucket = _compute_priority(
            row.has_abandoned_before, row.ai_called_before, row.has_called_in_before
        )

        await session.commit()
        await session.refresh(row)

    # Also update in active scenario if it exists and is not builtin
    updated_in_scenario = False
    settings_provider = get_settings_provider()
    settings = await settings_provider.get_settings()
    if settings.active_scenario_id:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SimulationScenarioRow).where(
                    SimulationScenarioRow.id == settings.active_scenario_id
                )
            )
            scenario_row = result.scalar_one_or_none()
            if scenario_row:
                current_patients = scenario_row.patients or []
                # Find patient by old phone and update
                for p in current_patients:
                    if p.get("phone") == old_phone:
                        if name is not None:
                            p["name"] = name
                        if phone is not None:
                            p["phone"] = phone
                        if language is not None:
                            p["language"] = language
                        if has_abandoned_before is not None:
                            p["has_abandoned_before"] = has_abandoned_before
                        if has_called_in_before is not None:
                            p["has_called_in_before"] = has_called_in_before
                        if ai_called_before is not None:
                            p["ai_called_before"] = ai_called_before
                        if attempt_count is not None:
                            p["attempt_count"] = attempt_count
                        updated_in_scenario = True
                        break
                if updated_in_scenario:
                    scenario_row.patients = current_patients
                    await session.commit()

    # Get updated patient
    updated_patient = await sim_provider.get_patient(patient_id)
    return {
        "status": "ok",
        "patient": updated_patient.to_dict() if updated_patient else None,
        "updated_in_scenario": updated_in_scenario,
    }


@router.get("/patients/queue")
async def get_outbound_queue():
    """Get patients eligible for outbound calling, sorted by priority."""
    patient_provider = get_patient_provider()
    queue = await patient_provider.get_outbound_queue()
    return {"queue": [p.to_dict() for p in queue]}


@router.get("/patients/{patient_id}")
async def get_patient(patient_id: str):
    """Get a specific patient."""
    patient_provider = get_patient_provider()
    patient = await patient_provider.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient.to_dict()


@router.post("/patients/reset")
async def reset_patients():
    """Reset patients to sample data (simulation only)."""
    patient_provider = get_simulation_patient_provider()
    await patient_provider.reset_to_sample_data()
    patients = await patient_provider.get_all_patients()
    return {"status": "ok", "count": len(patients)}


@router.get("/calls")
async def get_calls(limit: int = 25, offset: int = 0):
    """Get call history with pagination."""
    call_log_provider = get_call_log_provider()
    calls = await call_log_provider.get_all_calls(limit=limit, offset=offset)
    total = await call_log_provider.get_total_call_count()
    return {"calls": [c.to_dict() for c in calls], "total": total}


@router.get("/calls/active")
async def get_active_call():
    """Get the currently active call."""
    call_log_provider = get_call_log_provider()
    active = await call_log_provider.get_active_call()
    if not active:
        return {"active": False, "call": None}
    return {"active": True, "call": active.to_dict()}


@router.get("/calls/{call_id}")
async def get_call(call_id: str):
    """Get a specific call by ID."""
    call_log_provider = get_call_log_provider()
    call = await call_log_provider.get_call(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    return call.to_dict()


@router.get("/calls/patient/{patient_id}")
async def get_patient_calls(patient_id: str):
    """Get all calls for a specific patient."""
    call_log_provider = get_call_log_provider()
    calls = await call_log_provider.get_calls_by_patient(patient_id)
    return {"calls": [c.to_dict() for c in calls]}


@router.get("/statistics")
async def get_statistics():
    """Get call statistics."""
    call_log_provider = get_call_log_provider()
    return await call_log_provider.get_statistics()


@router.post("/twilio/twiml/{stream_id}")
@router.get("/twilio/twiml/{stream_id}")
async def twilio_twiml(stream_id: str):
    """Return TwiML that connects Twilio to our media stream WebSocket."""
    print(f"[TwiML] Twilio fetched TwiML for stream_id={stream_id}")
    # Build the WebSocket URL for Twilio to connect to
    public_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if not public_url:
        public_url = os.getenv("NEXT_PUBLIC_API_URL", "http://localhost:8000").rstrip("/")

    # Convert http(s) to ws(s)
    ws_url = public_url.replace("https://", "wss://").replace("http://", "ws://")
    stream_url = f"{ws_url}/ws/twilio-media/{stream_id}"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{stream_url}" />
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


@router.post("/twilio/status")
async def twilio_status_callback(
    CallSid: str = Form(""),
    CallStatus: str = Form(""),
    AnsweredBy: str = Form(""),
    ErrorCode: str = Form(""),
    SipResponseCode: str = Form(""),
):
    """Handle Twilio call status callbacks, including AMD AnsweredBy values."""
    parts = [f"[TwilioStatus] SID={CallSid} status={CallStatus}"]
    if AnsweredBy:
        parts.append(f"answered_by={AnsweredBy}")
    if ErrorCode:
        parts.append(f"error_code={ErrorCode}")
    if SipResponseCode:
        parts.append(f"sip_code={SipResponseCode}")
    print(" | ".join(parts))

    try:
        orchestrator = get_orchestrator()
        if AnsweredBy:
            safe_create_task(
                orchestrator.handle_twilio_amd_status(CallSid, AnsweredBy),
                logger,
                f"twilio_amd_status CallSid={CallSid}",
            )
        if CallStatus:
            safe_create_task(
                orchestrator.handle_twilio_call_status(
                    call_sid=CallSid,
                    call_status=CallStatus,
                    error_code_raw=ErrorCode,
                    sip_response_code_raw=SipResponseCode,
                ),
                logger,
                f"twilio_call_status CallSid={CallSid}",
            )
    except Exception as e:
        print(f"[TwilioStatus] Callback handling failed: {e}")
    return {"status": "ok"}


@router.post("/twilio/dial-status")
async def twilio_dial_status(request: Request):
    """Callback from <Dial action=...> — tells us what happened with the SIP transfer.

    If the transfer succeeded, return empty TwiML (call is bridged).
    If it failed, play a spoken apology so the patient isn't left in silence.
    """
    form = await request.form()
    dial_status = form.get("DialCallStatus", "")
    sip_code = form.get("DialSipResponseCode", "")
    bridged = form.get("DialBridged", "")
    call_sid = form.get("CallSid", "")

    parts = []
    for key in ("DialCallStatus", "DialCallSid", "DialCallDuration",
                "DialSipResponseCode", "CallSid", "DialBridged"):
        val = form.get(key, "")
        if val:
            parts.append(f"{key}={val}")
    print(f"[DialStatus] {' | '.join(parts) or 'no fields'}")

    if dial_status in ("completed", "answered") or bridged == "true":
        # Transfer succeeded — patient is connected to agent, nothing more to do
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml",
        )

    # Transfer failed — tell the patient and provide the callback number
    from app.services.twilio_sms_service import get_callback_number
    callback = get_callback_number()
    if callback:
        message = (
            "I'm sorry, we're having trouble connecting you to our scheduling team right now. "
            f"Please call us back at {callback} and we'll get you scheduled. "
            "We apologize for the inconvenience. Goodbye."
        )
    else:
        message = (
            "I'm sorry, we're having trouble connecting you to our scheduling team right now. "
            "Please call our office back and we'll get you scheduled. "
            "We apologize for the inconvenience. Goodbye."
        )

    print(f"[DialStatus] Transfer failed (status={dial_status}, sip={sip_code}) — playing fallback message for {call_sid}")

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response>'
        f'<Say voice="alice">{html.escape(message)}</Say>'
        '<Hangup/>'
        '</Response>'
    )
    return Response(content=twiml, media_type="application/xml")


@router.delete("/calls")
async def delete_all_calls():
    """Delete all call logs and transcripts."""
    call_log_provider = get_call_log_provider()
    await call_log_provider.reset()
    return {"status": "ok"}


@router.get("/config/check")
async def check_configuration():
    """Check system configuration status (for diagnostics)."""
    api_key = os.getenv("OPENAI_API_KEY", "")

    return {
        "openai_api_key_configured": bool(api_key),
        "openai_api_key_format_valid": api_key.startswith("sk-") if api_key else False,
        "openai_api_key_preview": f"{api_key[:7]}...{api_key[-4:]}" if len(api_key) > 15 else "(too short or not set)",
    }
