"""Suppression/opt-out checks for backfill outreach (M2 Phase 1.2).

Current source of truth is patient projection flags in backfill DB.
This service centralizes decision logic so later phases can swap in
replicated suppression tables or an external API without touching
campaign selection logic.
"""
from app.models.appointment_data import Patient


def get_sms_suppression_reason(patient: Patient) -> str | None:
    """Return exclusion reason when a patient cannot receive SMS outreach."""
    if patient.sms_opt_out:
        return "SMS opt-out"
    if patient.suppressed:
        return "Suppressed by backfill suppression rules"
    return None
