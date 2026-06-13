"""Aggregate dev simulator routes under /api/simulator."""
from fastapi import APIRouter

from simulator.api import appointments, bootstrap, facilities, patients

router = APIRouter(tags=["simulator"])
router.include_router(facilities.router)
router.include_router(patients.router)
router.include_router(appointments.router)
router.include_router(bootstrap.router)
