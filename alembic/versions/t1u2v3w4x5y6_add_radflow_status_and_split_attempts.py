"""Add radflow_status, split attempt counts (ai/human), and HL7 tracking.

Priority is now driven by RadFlow lifecycle status + combined (AI+human)
attempt count, per Danny's 2026-04-15 spec.  See project_hl7_max_attempts
memory for full context.

Revision ID: t1u2v3w4x5y6
Revises: s0t1u2v3w4x5
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa

revision = "t1u2v3w4x5y6"
down_revision = "s0t1u2v3w4x5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- patients table ---
    op.add_column(
        "patients",
        sa.Column("radflow_status", sa.String(32), nullable=True),
    )
    op.add_column(
        "patients",
        sa.Column("ai_attempt_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column(
        "patients",
        sa.Column("human_attempt_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column(
        "patients",
        sa.Column("hl7_sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # Backfill: treat the legacy combined attempt_count as AI attempts
    # (best we can do — most past calls were driven by our AI).  RadFlow
    # refreshes will populate human_attempt_count on next fetch.
    op.execute(
        "UPDATE patients SET ai_attempt_count = COALESCE(attempt_count, 0)"
    )

    # Default radflow_status = 'Ordered' for any patient already in the
    # queue — assume they're in the initial state until RadFlow refresh
    # tells us otherwise.
    op.execute("UPDATE patients SET radflow_status = 'Ordered' WHERE radflow_status IS NULL")

    # Replace the old index that referenced priority_bucket.
    op.drop_index("ix_patients_priority_due", table_name="patients")
    op.create_index(
        "ix_patients_status_attempts",
        "patients",
        ["radflow_status", "ai_attempt_count", "human_attempt_count", "due_by"],
    )

    # --- patient_call_state table ---
    op.add_column(
        "patient_call_state",
        sa.Column("ai_attempt_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column(
        "patient_call_state",
        sa.Column("hl7_sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE patient_call_state SET ai_attempt_count = COALESCE(attempt_count, 0)"
    )


def downgrade() -> None:
    op.drop_index("ix_patients_status_attempts", table_name="patients")
    op.create_index(
        "ix_patients_priority_due",
        "patients",
        ["priority_bucket", "due_by"],
    )

    op.drop_column("patients", "hl7_sent_at")
    op.drop_column("patients", "human_attempt_count")
    op.drop_column("patients", "ai_attempt_count")
    op.drop_column("patients", "radflow_status")

    op.drop_column("patient_call_state", "hl7_sent_at")
    op.drop_column("patient_call_state", "ai_attempt_count")
