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
    """Declarative base — import app.models so metadata is populated for Alembic."""
    pass


# Register ORM tables on metadata (import after Base is defined).
from app import models as _models  # noqa: F401, E402
