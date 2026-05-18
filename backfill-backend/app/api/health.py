from fastapi import APIRouter
from sqlalchemy import text

from app.db import async_engine

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "backfill-backend"}


@router.get("/db-health")
async def db_health() -> dict[str, object]:
    """Confirm the backend can reach its database. Returns connection details
    on success or a structured error on failure — never raises."""
    try:
        async with async_engine.connect() as conn:
            row = (await conn.execute(text("SELECT current_database(), current_user"))).first()
        return {"status": "ok", "database": row[0], "user": row[1]}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
