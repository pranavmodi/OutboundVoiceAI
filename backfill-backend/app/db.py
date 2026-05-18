"""Async SQLAlchemy engine and session factory for the backfill backend.

Independent of the outbound caller's app/db/base.py — different database, different metadata. See ../docs/cancellation-backfill/architecture.md.
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

async_engine = create_async_engine(
    settings.backfill_database_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base for BackfillCampaign, BackfillCandidate, BackfillActionLog."""
    pass
