"""Widen external patient and order identifiers

RadFlow patient/order identifiers can exceed 64 characters. Widen the
columns that store those external identifiers so call logging, live call
state updates, and audit logging do not fail before a call can start.

Revision ID: z7a8b9c0d1e2
Revises: y6z7a8b9c0d1
Create Date: 2026-05-27 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "z7a8b9c0d1e2"
down_revision = "y6z7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("patients", "patient_id", existing_type=sa.String(length=64), type_=sa.String(length=255), existing_nullable=False)
    op.alter_column("patients", "order_id", existing_type=sa.String(length=64), type_=sa.String(length=255), existing_nullable=True)
    op.alter_column("call_logs", "patient_id", existing_type=sa.String(length=64), type_=sa.String(length=255), existing_nullable=False)
    op.alter_column("call_logs", "order_id", existing_type=sa.String(length=64), type_=sa.String(length=255), existing_nullable=True)
    op.alter_column("patient_call_state", "patient_id", existing_type=sa.String(length=64), type_=sa.String(length=255), existing_nullable=False)
    op.alter_column("audit_events", "patient_id", existing_type=sa.String(length=64), type_=sa.String(length=255), existing_nullable=True)
    op.alter_column("audit_events", "order_id", existing_type=sa.String(length=64), type_=sa.String(length=255), existing_nullable=True)


def downgrade():
    op.alter_column("audit_events", "order_id", existing_type=sa.String(length=255), type_=sa.String(length=64), existing_nullable=True)
    op.alter_column("audit_events", "patient_id", existing_type=sa.String(length=255), type_=sa.String(length=64), existing_nullable=True)
    op.alter_column("patient_call_state", "patient_id", existing_type=sa.String(length=255), type_=sa.String(length=64), existing_nullable=False)
    op.alter_column("call_logs", "order_id", existing_type=sa.String(length=255), type_=sa.String(length=64), existing_nullable=True)
    op.alter_column("call_logs", "patient_id", existing_type=sa.String(length=255), type_=sa.String(length=64), existing_nullable=False)
    op.alter_column("patients", "order_id", existing_type=sa.String(length=255), type_=sa.String(length=64), existing_nullable=True)
    op.alter_column("patients", "patient_id", existing_type=sa.String(length=255), type_=sa.String(length=64), existing_nullable=False)
