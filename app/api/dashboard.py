"""REST API endpoints for dashboard."""
from fastapi import APIRouter, HTTPException
from typing import Optional

from app.providers import get_queue_provider, get_patient_provider, get_call_log_provider
from app.models import CallOutcome

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
