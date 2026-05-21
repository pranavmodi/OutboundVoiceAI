"""Add timings column to call_logs

Stores per-call time-to-first-speech milestones as a JSONB blob keyed by
stable snake_case identifiers (voice_connected, twilio_dial_accepted,
media_stream_connected, first_audio_out, etc.). Values are cumulative
milliseconds since start_call entry. Empty dict on legacy rows.

Used by the CallHistoryCard TTFS badge and by anyone doing latency
analysis on production calls.

Revision ID: y6z7a8b9c0d1
Revises: x5y6z7a8b9c0
Create Date: 2026-05-21 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "y6z7a8b9c0d1"
down_revision = "x5y6z7a8b9c0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "call_logs",
        sa.Column(
            "timings",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade():
    op.drop_column("call_logs", "timings")
