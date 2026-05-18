"""Add voice_provider to system_settings.

Revision ID: r9s0t1u2v3w4
Revises: q8r9s0t1u2v3
Create Date: 2026-04-11
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "r9s0t1u2v3w4"
down_revision = "q8r9s0t1u2v3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column("voice_provider", sa.String(20), server_default="openai", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "voice_provider")
