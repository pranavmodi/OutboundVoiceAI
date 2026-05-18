"""Add api_keys column to system_settings

Stores per-provider API keys (openai, gemini) as a plaintext JSONB blob on
the singleton settings row. Lets the keys be updated from the UI and applied
without a server restart. Empty string means "not configured" — call sites
fall back to the env var.

Revision ID: x5y6z7a8b9c0
Revises: w4x5y6z7a8b9
Create Date: 2026-05-11 13:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "x5y6z7a8b9c0"
down_revision = "w4x5y6z7a8b9"
branch_labels = None
depends_on = None


_DEFAULT_API_KEYS = "'{\"openai\": \"\", \"gemini\": \"\"}'::jsonb"


def upgrade():
    op.add_column(
        "system_settings",
        sa.Column(
            "api_keys",
            JSONB,
            nullable=False,
            server_default=sa.text(_DEFAULT_API_KEYS),
        ),
    )


def downgrade():
    op.drop_column("system_settings", "api_keys")
