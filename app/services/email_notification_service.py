"""Email notifications for call outcome issues."""
import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Optional

from app.models import CallLog


DEFAULT_RECIPIENT = "nehapipada39@gmail.com"


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _build_wrong_number_subject(patient_id: str) -> str:
    return f"Scheduling Call Issue - Wrong Number (Patient ID: {patient_id})"


def _build_disconnected_subject(patient_id: str) -> str:
    return f"Scheduling Call Issue - Invalid/Disconnected Number (Patient ID: {patient_id})"


def _format_body(call: CallLog, status: Optional[str] = None) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    lines = [
        f"Patient ID: {call.patient_id}",
        f"Order ID: {call.order_id or 'N/A'}",
        f"Phone: {call.phone or 'N/A'}",
        f"Timestamp: {timestamp}",
        f"Call ID: {call.call_id}",
    ]
    if status:
        lines.append(f"Error/Status: {status}")
    return "\n".join(lines)


def send_wrong_number_email(call: CallLog) -> str:
    """Send wrong-number notification email. Returns message-id."""
    subject = _build_wrong_number_subject(call.patient_id)
    body = _format_body(call)
    return _send_email(subject, body)


def send_disconnected_number_email(call: CallLog, status: str) -> str:
    """Send disconnected/invalid-number notification email. Returns message-id."""
    subject = _build_disconnected_subject(call.patient_id)
    body = _format_body(call, status=status)
    return _send_email(subject, body)


def _send_email(subject: str, body: str) -> str:
    recipient = os.getenv("EMAIL_NOTIFICATION_RECIPIENT", DEFAULT_RECIPIENT).strip()
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587").strip() or "587")
    smtp_user = os.getenv("SMTP_USERNAME", "").strip()
    smtp_pass = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM_EMAIL", "").strip() or smtp_user
    smtp_use_tls = _is_truthy(os.getenv("SMTP_USE_TLS", "true"))

    if not smtp_host or not smtp_from:
        raise RuntimeError("Email is not configured. Set SMTP_HOST and SMTP_FROM_EMAIL (or SMTP_USERNAME).")

    msg = EmailMessage()
    msg["From"] = smtp_from
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        if smtp_use_tls:
            server.starttls()
        if smtp_user and smtp_pass:
            server.login(smtp_user, smtp_pass)
        server.send_message(msg)

    return msg.get("Message-ID", "")
