"""Cancellation Backfill backend — FastAPI entry point.

This service is independent of the outbound caller. See ../docs/cancellation-backfill/architecture.md.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent, campaigns, facilities_read, health
from app.api.integrations import radflow as radflow_integration
from app.api import settings as settings_api
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
app.include_router(agent.router, prefix="/api")
app.include_router(facilities_read.router, prefix="/api")
app.include_router(campaigns.router, prefix="/api")
app.include_router(settings_api.router, prefix="/api")
app.include_router(
    radflow_integration.router,
    prefix="/api/integrations/radflow",
)

if settings.backfill_simulator_enabled:
    from simulator import router as simulator_router

    app.include_router(simulator_router, prefix="/api/simulator")
