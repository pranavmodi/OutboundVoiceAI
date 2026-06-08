"""Cancellation Backfill backend — FastAPI entry point.

This service is independent of the outbound caller. See ../docs/cancellation-backfill/architecture.md.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent, campaigns, facilities_read, health, webhooks_sms
from app.api.integrations import radflow as radflow_integration
from app.api import settings as settings_api
from app.config import settings
from app.services.wave_worker import WaveWorker

wave_worker = WaveWorker()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.backfill_wave_worker_enabled:
        wave_worker.start()
    try:
        yield
    finally:
        await wave_worker.stop()


app = FastAPI(title="Cancellation Backfill Backend", lifespan=lifespan)

_cors_origins = [o.strip() for o in settings.backfill_cors_origins.split(",") if o.strip()]
# Local dev: browser may use LAN IP (Next "Network" URL) — not only localhost.
_cors_kwargs: dict = {
    "allow_origins": _cors_origins,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if settings.backfill_simulator_enabled:
    _cors_kwargs["allow_origin_regex"] = (
        r"https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d+)?"
    )
app.add_middleware(CORSMiddleware, **_cors_kwargs)

app.include_router(health.router, prefix="/api")
app.include_router(agent.router, prefix="/api")
app.include_router(facilities_read.router, prefix="/api")
app.include_router(campaigns.router, prefix="/api")
app.include_router(settings_api.router, prefix="/api")
app.include_router(webhooks_sms.router, prefix="/api")
app.include_router(
    radflow_integration.router,
    prefix="/api/integrations/radflow",
)

if settings.backfill_simulator_enabled:
    from simulator import router as simulator_router

    app.include_router(simulator_router, prefix="/api/simulator")

if settings.backfill_simulator_enabled:
    from mock_sms.router import router as mock_sms_router

    app.include_router(mock_sms_router, prefix="/api/mock-sms")
