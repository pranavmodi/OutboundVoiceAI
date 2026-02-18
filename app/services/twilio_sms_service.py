"""Twilio SMS helper for outbound callback notifications."""
import os
from twilio.rest import Client


DEFAULT_CALLBACK_NUMBER = "1-800-555-7226"


def get_callback_number() -> str:
    """Return callback number shown in SMS messages."""
    return os.getenv("PRECISE_CALLBACK_NUMBER", DEFAULT_CALLBACK_NUMBER)


def get_main_number() -> str:
    """Return main office number shown in SMS messages."""
    return os.getenv("PRECISE_MAIN_NUMBER", get_callback_number())


def build_sms_message(message_type: str) -> str:
    """Build a non-PHI SMS message body."""
    callback_number = get_callback_number()
    main_number = get_main_number()

    if message_type == "appointment_reminder":
        return (
            "Precise Imaging reminder: please contact us to review scheduling details. "
            f"Callback: {callback_number}."
        )

    # Default and callback_info: concise, no PHI.
    return (
        "This is Precise Imaging. We were unable to complete your scheduling call. "
        f"Please call us back at {callback_number}. Main office: {main_number}."
    )


def send_sms(to_number: str, message_body: str) -> str:
    """Send an SMS via Twilio and return the message SID.

    Raises:
        RuntimeError: If Twilio credentials/config are missing.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_SMS_FROM_NUMBER", "") or os.getenv("TWILIO_FROM_NUMBER", "")

    if not account_sid or not auth_token or not from_number:
        raise RuntimeError(
            "Twilio SMS is not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
            "and TWILIO_SMS_FROM_NUMBER (or TWILIO_FROM_NUMBER)."
        )

    client = Client(account_sid, auth_token)
    message = client.messages.create(
        to=to_number,
        from_=from_number,
        body=message_body,
    )
    return message.sid
