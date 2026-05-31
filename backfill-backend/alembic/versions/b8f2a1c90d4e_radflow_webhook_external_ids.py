"""radflow webhook external ids and inbound events

Revision ID: b8f2a1c90d4e
Revises: 4c37bc640970
Create Date: 2026-05-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b8f2a1c90d4e"
down_revision: Union[str, None] = "4c37bc640970"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("facilities", sa.Column("external_id", sa.String(length=64), nullable=True))
    op.add_column("patients", sa.Column("external_id", sa.String(length=64), nullable=True))
    op.add_column("appointments", sa.Column("external_id", sa.String(length=64), nullable=True))
    op.add_column(
        "appointments",
        sa.Column("procedure_description", sa.String(length=512), nullable=True),
    )

    op.create_index("ix_facilities_external_id", "facilities", ["external_id"], unique=True)
    op.create_index("ix_patients_external_id", "patients", ["external_id"], unique=True)
    op.create_index("ix_appointments_external_id", "appointments", ["external_id"], unique=True)

    op.create_table(
        "backfill_inbound_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("radflow_event_id", sa.String(length=128), nullable=False),
        sa.Column("appointment_external_id", sa.String(length=64), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=True),
        sa.Column("result_status", sa.String(length=64), nullable=False),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["backfill_campaigns.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("radflow_event_id", name="uq_inbound_radflow_event_id"),
    )
    op.create_index(
        "ix_backfill_inbound_events_appointment_external",
        "backfill_inbound_events",
        ["appointment_external_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_backfill_inbound_events_appointment_external", "backfill_inbound_events")
    op.drop_table("backfill_inbound_events")
    op.drop_index("ix_appointments_external_id", "appointments")
    op.drop_index("ix_patients_external_id", "patients")
    op.drop_index("ix_facilities_external_id", "facilities")
    op.drop_column("appointments", "procedure_description")
    op.drop_column("appointments", "external_id")
    op.drop_column("patients", "external_id")
    op.drop_column("facilities", "external_id")
