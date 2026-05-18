"""Add dialing lock columns to patients and patient_call_state.

Revision ID: v3w4x5y6z7a8
Revises: u2v3w4x5y6z7
Create Date: 2026-04-24

Phase 3 of the parallel-calls rollout. Lets the dispatcher claim a patient
via SELECT ... FOR UPDATE SKIP LOCKED before placing the call, so two
dispatcher instances (or a dispatcher + manual-call) can never pick the
same patient. At MAX_PARALLEL_CALLS == 1 this is belt-and-braces; at
higher caps it is load-bearing.
"""
from alembic import op
import sqlalchemy as sa

revision = "v3w4x5y6z7a8"
down_revision = "u2v3w4x5y6z7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "patients",
        sa.Column("dialing_call_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "patients",
        sa.Column("dialing_started_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_patients_dialing_call_id",
        "patients",
        ["dialing_call_id"],
        postgresql_where=sa.text("dialing_call_id IS NOT NULL"),
    )

    op.add_column(
        "patient_call_state",
        sa.Column("dialing_call_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "patient_call_state",
        sa.Column("dialing_started_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_patient_call_state_dialing_call_id",
        "patient_call_state",
        ["dialing_call_id"],
        postgresql_where=sa.text("dialing_call_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_patient_call_state_dialing_call_id", table_name="patient_call_state")
    op.drop_column("patient_call_state", "dialing_started_at")
    op.drop_column("patient_call_state", "dialing_call_id")

    op.drop_index("ix_patients_dialing_call_id", table_name="patients")
    op.drop_column("patients", "dialing_started_at")
    op.drop_column("patients", "dialing_call_id")
