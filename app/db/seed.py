"""Seed default data into the database on startup."""
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import SystemSettingsRow, PatientRow, SimulationScenarioRow

logger = logging.getLogger(__name__)


async def seed_default_settings(session: AsyncSession):
    """Insert the singleton settings row if it doesn't exist."""
    result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
    if result.scalar_one_or_none() is not None:
        return
    row = SystemSettingsRow(
        id=1,
        system_enabled=True,
        business_hours={
            "start_time": "08:00",
            "end_time": "17:00",
            "enabled": False,
            "timezone": "America/New_York",
        },
        queue_thresholds={
            "calls_waiting_threshold": 1,
            "holdtime_threshold_seconds": 30,
            "stable_polls_required": 3,
        },
        allow_live_calls=False,
        allowed_phones=[],
        queue_source="simulation",
    )
    session.add(row)
    logger.info("Seeded default system settings")


async def seed_sample_patients(session: AsyncSession):
    """Insert sample patients if the table is empty."""
    result = await session.execute(select(PatientRow.patient_id).limit(1))
    if result.scalar_one_or_none() is not None:
        return

    now = datetime.now(timezone.utc)
    samples = [
        PatientRow(
            patient_id="PRE001", name="John Smith", phone="555-0101",
            language="en", order_id="ORD001",
            order_created=now - timedelta(days=1),
            has_abandoned_before=True, ai_called_before=False,
            due_by=now + timedelta(days=1), priority_bucket=1,
        ),
        PatientRow(
            patient_id="PRE002", name="Maria Garcia", phone="555-0102",
            language="es", order_id="ORD002",
            order_created=now - timedelta(days=2),
            has_abandoned_before=True, ai_called_before=False,
            due_by=now, priority_bucket=1,
        ),
        PatientRow(
            patient_id="PRE003", name="Robert Johnson", phone="555-0103",
            language="en", order_id="ORD003",
            order_created=now - timedelta(days=1),
            has_abandoned_before=True, ai_called_before=True,
            attempt_count=1, last_attempt_at=now - timedelta(hours=8),
            last_outcome="no_answer",
            due_by=now + timedelta(days=1), priority_bucket=2,
        ),
        PatientRow(
            patient_id="PRE004", name="Emily Davis", phone="555-0104",
            language="en", order_id="ORD004",
            order_created=now - timedelta(hours=12),
            has_called_in_before=True, ai_called_before=False,
            due_by=now + timedelta(days=2), priority_bucket=3,
        ),
        PatientRow(
            patient_id="PRE005", name="Michael Wilson", phone="555-0105",
            language="en", order_id="ORD005",
            order_created=now - timedelta(hours=6),
            ai_called_before=False,
            due_by=now + timedelta(days=2), priority_bucket=4,
        ),
        PatientRow(
            patient_id="PRE006", name="Sarah Brown", phone="555-0106",
            language="en", order_id="ORD006",
            order_created=now - timedelta(hours=3),
            intake_status="incomplete", ai_called_before=False,
            due_by=now + timedelta(days=2), priority_bucket=4,
        ),
        PatientRow(
            patient_id="PRE007", name="Wei Zhang", phone="555-0107",
            language="zh", order_id="ORD007",
            order_created=now - timedelta(hours=18),
            has_called_in_before=True, ai_called_before=False,
            due_by=now + timedelta(days=1), priority_bucket=3,
        ),
    ]
    session.add_all(samples)
    logger.info("Seeded %d sample patients", len(samples))


async def seed_builtin_scenarios(session: AsyncSession):
    """Insert built-in simulation scenarios if they don't exist."""
    result = await session.execute(
        select(SimulationScenarioRow.id).where(SimulationScenarioRow.is_builtin == True)  # noqa: E712
    )
    if result.scalars().first() is not None:
        return

    scenarios = [
        SimulationScenarioRow(
            id="quiet_queue",
            label="Quiet Queue",
            description="Agents available, no calls waiting — outbound allowed immediately",
            is_builtin=True,
            ami_connected=True,
            queues=[
                {"Queue": "scheduling_en", "Calls": 0, "Holdtime": 0,
                 "AvailableAgents": 2},
                {"Queue": "scheduling_es", "Calls": 0, "Holdtime": 0,
                 "AvailableAgents": 1},
            ],
            patients=[
                {"name": "Jane Doe", "phone": "555-1001", "language": "en",
                 "has_abandoned_before": True},
                {"name": "Carlos Ruiz", "phone": "555-1002", "language": "es"},
            ],
            dispatcher={"poll_interval": 5, "dispatch_timeout": 30,
                        "max_attempts": 3, "min_hours_between": 6},
        ),
        SimulationScenarioRow(
            id="busy_queue",
            label="Busy Queue",
            description="High call volume — outbound blocked",
            is_builtin=True,
            ami_connected=True,
            queues=[
                {"Queue": "scheduling_en", "Calls": 5, "Holdtime": 120,
                 "AvailableAgents": 0},
                {"Queue": "intake", "Calls": 3, "Holdtime": 60,
                 "AvailableAgents": 0},
            ],
            patients=[
                {"name": "Test Patient", "phone": "555-2001", "language": "en"},
            ],
            dispatcher={"poll_interval": 10, "dispatch_timeout": 30,
                        "max_attempts": 3, "min_hours_between": 6},
        ),
        SimulationScenarioRow(
            id="ami_failure",
            label="AMI Disconnected",
            description="AMI connection lost — outbound blocked",
            is_builtin=True,
            ami_connected=False,
            queues=[
                {"Queue": "scheduling_en", "Calls": 0, "Holdtime": 0,
                 "AvailableAgents": 0},
            ],
            patients=[
                {"name": "Test Patient", "phone": "555-3001", "language": "en"},
            ],
            dispatcher={"poll_interval": 10, "dispatch_timeout": 30,
                        "max_attempts": 3, "min_hours_between": 6},
        ),
    ]
    session.add_all(scenarios)
    logger.info("Seeded %d built-in simulation scenarios", len(scenarios))
