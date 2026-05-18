"""Slack notification when a patient is missing a phone number.

Posts to the configured webhook so the scheduling team can fix the record.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Set

import httpx

logger = logging.getLogger(__name__)

MISSING_PHONE_WEBHOOK = os.getenv("SLACK_MISSING_PHONE_WEBHOOK", "")

# Track which patients we've already notified about in this process lifetime
# to avoid spamming Slack on every poll cycle.
_notified_patient_ids: Set[str] = set()


async def notify_missing_phone(
    patient_id: str,
    patient_name: str,
    order_id: str = "",
) -> None:
    """Post a Slack message about a patient missing a phone number.

    Only sends once per patient per process lifetime.
    """
    if patient_id in _notified_patient_ids:
        return
    _notified_patient_ids.add(patient_id)

    if not MISSING_PHONE_WEBHOOK:
        logger.warning("SLACK_MISSING_PHONE_WEBHOOK not configured, skipping notification")
        return

    message = (
        f"*Missing Phone Number*\n"
        f"Patient *{patient_name}* (`{patient_id}`) has no phone number on file.\n"
        f"This patient was skipped by the AI outbound caller. "
        f"Please update their phone number in RadFlow."
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(MISSING_PHONE_WEBHOOK, json={"text": message})
            resp.raise_for_status()
        logger.info("Missing phone Slack notification sent for %s (%s)", patient_id, patient_name)
    except Exception as e:
        logger.warning("Failed to send missing phone Slack notification for %s: %s", patient_id, e)
