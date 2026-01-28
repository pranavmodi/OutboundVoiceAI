"""REST API endpoints for dashboard."""
import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional

from app.providers import get_queue_provider, get_patient_provider, get_call_log_provider
from app.models import CallOutcome
from app.services.dispatcher import get_dispatcher

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/status")
async def get_system_status():
    """Get overall system status."""
    queue_provider = get_queue_provider()
    patient_provider = get_patient_provider()
    call_log_provider = get_call_log_provider()

    queue_state = queue_provider.get_state()
    outbound_queue = patient_provider.get_outbound_queue()
    active_call = call_log_provider.get_active_call()
    stats = call_log_provider.get_statistics()

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
    queue_provider = get_queue_provider()
    queue_provider.simulate_busy_queue()
    return {"status": "ok", "queue_state": queue_provider.get_state().to_dict()}


@router.post("/queue/simulate/quiet")
async def simulate_quiet_queue():
    """Simulate a quiet queue scenario."""
    queue_provider = get_queue_provider()
    queue_provider.simulate_quiet_queue()
    return {"status": "ok", "queue_state": queue_provider.get_state().to_dict()}


@router.post("/queue/simulate/ami-failure")
async def simulate_ami_failure():
    """Simulate AMI connection failure."""
    queue_provider = get_queue_provider()
    queue_provider.simulate_ami_failure()
    return {"status": "ok", "queue_state": queue_provider.get_state().to_dict()}


@router.post("/queue/simulate/ami-recovery")
async def simulate_ami_recovery():
    """Simulate AMI connection recovery."""
    queue_provider = get_queue_provider()
    queue_provider.simulate_ami_recovery()
    return {"status": "ok", "queue_state": queue_provider.get_state().to_dict()}


@router.post("/queue/{queue_name}")
async def update_queue(
    queue_name: str,
    calls_waiting: Optional[int] = None,
    oldest_wait_seconds: Optional[int] = None,
    agents_available: Optional[int] = None,
    agents_logged_in: Optional[int] = None,
):
    """Update a specific queue's state."""
    queue_provider = get_queue_provider()
    queue_provider.set_queue_state(
        queue_name=queue_name,
        calls_waiting=calls_waiting,
        oldest_wait_seconds=oldest_wait_seconds,
        agents_available=agents_available,
        agents_logged_in=agents_logged_in,
    )
    return {"status": "ok", "queue_state": queue_provider.get_state().to_dict()}


@router.get("/patients")
async def get_patients():
    """Get all patients in the system."""
    patient_provider = get_patient_provider()
    patients = patient_provider.get_all_patients()
    return {"patients": [p.to_dict() for p in patients]}


@router.get("/patients/queue")
async def get_outbound_queue():
    """Get patients eligible for outbound calling, sorted by priority."""
    patient_provider = get_patient_provider()
    queue = patient_provider.get_outbound_queue()
    return {"queue": [p.to_dict() for p in queue]}


@router.get("/patients/{patient_id}")
async def get_patient(patient_id: str):
    """Get a specific patient."""
    patient_provider = get_patient_provider()
    patient = patient_provider.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient.to_dict()


@router.post("/patients/reset")
async def reset_patients():
    """Reset patients to sample data."""
    patient_provider = get_patient_provider()
    patient_provider.reset_to_sample_data()
    return {"status": "ok", "count": len(patient_provider.get_all_patients())}


@router.get("/calls")
async def get_calls(limit: int = 50):
    """Get call history."""
    call_log_provider = get_call_log_provider()
    calls = call_log_provider.get_all_calls(limit=limit)
    return {"calls": [c.to_dict() for c in calls]}


@router.get("/calls/active")
async def get_active_call():
    """Get the currently active call."""
    call_log_provider = get_call_log_provider()
    active = call_log_provider.get_active_call()
    if not active:
        return {"active": False, "call": None}
    return {"active": True, "call": active.to_dict()}


@router.get("/calls/{call_id}")
async def get_call(call_id: str):
    """Get a specific call by ID."""
    call_log_provider = get_call_log_provider()
    call = call_log_provider.get_call(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    return call.to_dict()


@router.get("/calls/patient/{patient_id}")
async def get_patient_calls(patient_id: str):
    """Get all calls for a specific patient."""
    call_log_provider = get_call_log_provider()
    calls = call_log_provider.get_calls_by_patient(patient_id)
    return {"calls": [c.to_dict() for c in calls]}


@router.get("/statistics")
async def get_statistics():
    """Get call statistics."""
    call_log_provider = get_call_log_provider()
    return call_log_provider.get_statistics()


class QueueConfigItem(BaseModel):
    queue_name: str
    calls_waiting: int = 0
    oldest_wait_seconds: int = 0
    agents_available: int = 1
    agents_logged_in: int = 1


class QueueConfig(BaseModel):
    ami_connected: bool = True
    queues: list[QueueConfigItem] = []


class PatientConfigItem(BaseModel):
    name: str
    phone: str
    language: str = "en"
    has_abandoned_before: bool = False
    has_called_in_before: bool = False
    ai_called_before: bool = False
    attempt_count: int = 0


class DispatcherConfig(BaseModel):
    poll_interval: int = 10
    dispatch_timeout: int = 30
    max_attempts: int = 3
    min_hours_between: int = 6


class SimulationApplyRequest(BaseModel):
    queue: QueueConfig = QueueConfig()
    patients: list[PatientConfigItem] = []
    dispatcher: DispatcherConfig = DispatcherConfig()


@router.post("/simulation/apply")
async def apply_simulation(request: SimulationApplyRequest):
    """Apply simulation configuration and restart dispatcher."""
    queue_provider = get_queue_provider()
    patient_provider = get_patient_provider()
    call_log_provider = get_call_log_provider()
    dispatcher = get_dispatcher()

    # 1. Reset queue provider
    queue_provider.reset_with_config(
        queues_config=[q.model_dump() for q in request.queue.queues],
        ami_connected=request.queue.ami_connected,
    )

    # 2. Reset patient provider
    patient_provider.reset_with_patients(
        patient_dicts=[p.model_dump() for p in request.patients]
    )

    # 3. Clear call log history
    call_log_provider.reset()

    # 4. Update dispatcher config and restart
    dispatcher.update_config(
        poll_interval=request.dispatcher.poll_interval,
        dispatch_timeout=request.dispatcher.dispatch_timeout,
        max_attempts=request.dispatcher.max_attempts,
        min_hours_between=request.dispatcher.min_hours_between,
    )
    dispatcher.restart()

    # 5. Return new state
    return {
        "status": "ok",
        "queue_state": queue_provider.get_state().to_dict(),
        "patient_count": len(patient_provider.get_all_patients()),
        "dispatcher_status": dispatcher.get_status(),
    }


@router.post("/twilio/twiml/{stream_id}")
@router.get("/twilio/twiml/{stream_id}")
async def twilio_twiml(stream_id: str):
    """Return TwiML that connects Twilio to our media stream WebSocket."""
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


@router.get("/config/check")
async def check_configuration():
    """Check system configuration status (for diagnostics)."""
    api_key = os.getenv("OPENAI_API_KEY", "")

    return {
        "openai_api_key_configured": bool(api_key),
        "openai_api_key_format_valid": api_key.startswith("sk-") if api_key else False,
        "openai_api_key_preview": f"{api_key[:7]}...{api_key[-4:]}" if len(api_key) > 15 else "(too short or not set)",
    }
