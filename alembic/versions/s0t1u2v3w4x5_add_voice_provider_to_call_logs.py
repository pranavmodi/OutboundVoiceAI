"""Add voice_provider to call_logs and backfill existing rows as openai.

Revision ID: s0t1u2v3w4x5
Revises: r9s0t1u2v3w4
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa

revision = "s0t1u2v3w4x5"
down_revision = "r9s0t1u2v3w4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "call_logs",
        sa.Column("voice_provider", sa.String(20), server_default="openai", nullable=False),
    )
    # Backfill all existing rows as openai
    op.execute("UPDATE call_logs SET voice_provider = 'openai' WHERE voice_provider IS NULL OR voice_provider = ''")


def downgrade() -> None:
    op.drop_column("call_logs", "voice_provider")
