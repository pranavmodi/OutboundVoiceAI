"""Cancellation Backfill backend — FastAPI entry point.

This service is independent of the outbound caller. See ../docs/cancellation-backfill/architecture.md.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.config import settings

app = FastAPI(title="Cancellation Backfill Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.backfill_cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
