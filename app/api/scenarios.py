"""Scenarios API endpoints - full CRUD for simulation scenarios."""
import uuid
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete

from app.db import AsyncSessionLocal
from app.db.models import SimulationScenarioRow


router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


class QueueConfigItem(BaseModel):
    Queue: str
    Calls: int = 0
    Holdtime: int = 0
    AvailableAgents: int = 0


class PatientConfigItem(BaseModel):
    name: str
    phone: str
    language: str = "en"
    has_abandoned_before: bool = False
    has_called_in_before: bool = False
    ai_called_before: bool = False
    attempt_count: int = 0


class ScenarioResponse(BaseModel):
    id: str
    label: str
    description: str
    is_builtin: bool
    ami_connected: bool
    queues: List[dict]
    patients: List[dict]
    created_at: str
    updated_at: str


class ScenarioCreateRequest(BaseModel):
    label: str
    description: str = ""
    ami_connected: bool = True
    queues: List[QueueConfigItem] = []
    patients: List[PatientConfigItem] = []


class ScenarioUpdateRequest(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    ami_connected: Optional[bool] = None
    queues: Optional[List[QueueConfigItem]] = None
    patients: Optional[List[PatientConfigItem]] = None


def _row_to_response(row: SimulationScenarioRow) -> ScenarioResponse:
    return ScenarioResponse(
        id=row.id,
        label=row.label,
        description=row.description,
        is_builtin=row.is_builtin,
        ami_connected=row.ami_connected,
        queues=row.queues or [],
        patients=row.patients or [],
        created_at=row.created_at.isoformat() if row.created_at else "",
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )


@router.get("", response_model=List[ScenarioResponse])
async def list_scenarios():
    """List all simulation scenarios."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SimulationScenarioRow).order_by(SimulationScenarioRow.label)
        )
        rows = result.scalars().all()
        return [_row_to_response(row) for row in rows]


@router.get("/{scenario_id}", response_model=ScenarioResponse)
async def get_scenario(scenario_id: str):
    """Get a single scenario by ID."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SimulationScenarioRow).where(SimulationScenarioRow.id == scenario_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Scenario not found")
        return _row_to_response(row)


@router.post("", response_model=ScenarioResponse, status_code=201)
async def create_scenario(request: ScenarioCreateRequest):
    """Create a new custom scenario."""
    async with AsyncSessionLocal() as session:
        scenario_id = str(uuid.uuid4())[:8]
        row = SimulationScenarioRow(
            id=scenario_id,
            label=request.label,
            description=request.description,
            is_builtin=False,
            ami_connected=request.ami_connected,
            queues=[q.model_dump() for q in request.queues],
            patients=[p.model_dump() for p in request.patients],
            dispatcher={},
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return _row_to_response(row)


@router.put("/{scenario_id}", response_model=ScenarioResponse)
async def update_scenario(scenario_id: str, request: ScenarioUpdateRequest):
    """Update an existing scenario. Cannot update builtin scenarios."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SimulationScenarioRow).where(SimulationScenarioRow.id == scenario_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Scenario not found")
        if row.is_builtin:
            raise HTTPException(status_code=400, detail="Cannot modify builtin scenarios")

        if request.label is not None:
            row.label = request.label
        if request.description is not None:
            row.description = request.description
        if request.ami_connected is not None:
            row.ami_connected = request.ami_connected
        if request.queues is not None:
            row.queues = [q.model_dump() for q in request.queues]
        if request.patients is not None:
            row.patients = [p.model_dump() for p in request.patients]

        await session.commit()
        await session.refresh(row)
        return _row_to_response(row)


@router.delete("/{scenario_id}")
async def delete_scenario(scenario_id: str):
    """Delete a scenario. Cannot delete builtin scenarios."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SimulationScenarioRow).where(SimulationScenarioRow.id == scenario_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Scenario not found")
        if row.is_builtin:
            raise HTTPException(status_code=400, detail="Cannot delete builtin scenarios")

        await session.execute(
            delete(SimulationScenarioRow).where(SimulationScenarioRow.id == scenario_id)
        )
        await session.commit()
        return {"status": "ok", "deleted_id": scenario_id}


@router.delete("")
async def delete_all_custom_scenarios():
    """Delete all custom (non-builtin) simulation scenarios."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            delete(SimulationScenarioRow).where(
                SimulationScenarioRow.is_builtin == False  # noqa: E712
            )
        )
        await session.commit()
        return {"status": "ok", "deleted": result.rowcount}
