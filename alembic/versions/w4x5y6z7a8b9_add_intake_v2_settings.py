"""Add intake_v2 column to system_settings

Stores the v2 intake-agent feature flags (master_enabled, tenant_allowlist,
order_canary_pct, mode_voice_capture, mode_portal_copilot, multi_call_resume)
as a JSONB blob on the singleton settings row. All flags default OFF — v1
behavior is preserved until master_enabled is flipped.

Revision ID: w4x5y6z7a8b9
Revises: v3w4x5y6z7a8
Create Date: 2026-05-07 20:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "w4x5y6z7a8b9"
down_revision = "v3w4x5y6z7a8"
branch_labels = None
depends_on = None


_DEFAULT_INTAKE_V2 = (
    "'{"
    '"master_enabled": false, '
    '"tenant_allowlist": [], '
    '"order_canary_pct": 0, '
    '"mode_voice_capture": false, '
    '"mode_portal_copilot": false, '
    '"multi_call_resume": false'
    "}'::jsonb"
)


def upgrade():
    op.add_column(
        "system_settings",
        sa.Column(
            "intake_v2",
            JSONB,
            nullable=False,
            server_default=sa.text(_DEFAULT_INTAKE_V2),
        ),
    )


def downgrade():
    op.drop_column("system_settings", "intake_v2")
