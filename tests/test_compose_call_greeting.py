"""Tests for the v2 consent / recording-disclosure greeting composer.

The composer is the seam between the v2 gate decision and what the AI
voice agent actually speaks at call start. With the gate ruling the call
ineligible (the prod default while flags are OFF) it must return the
greeting byte-identically; with the gate eligible it must prepend the
configured disclosure.
"""
from app.models import IntakeV2Settings
from app.models.system_settings import (
    DEFAULT_CALL_GREETING,
    DEFAULT_V2_CONSENT_DISCLOSURE,
    compose_call_greeting,
)


def test_returns_base_greeting_when_gate_not_eligible():
    """Shadow mode / master OFF / outside canary all funnel through here."""
    settings = IntakeV2Settings(consent_disclosure=DEFAULT_V2_CONSENT_DISCLOSURE)
    out = compose_call_greeting("Hi from Ashley.", settings, gate_eligible=False)
    assert out == "Hi from Ashley."


def test_prepends_disclosure_when_gate_eligible():
    settings = IntakeV2Settings(consent_disclosure="This call is recorded.")
    out = compose_call_greeting("Hi from Ashley.", settings, gate_eligible=True)
    assert out == "This call is recorded. Hi from Ashley."


def test_eligible_with_empty_disclosure_falls_back_to_base():
    """An operator who clears the disclosure shouldn't accidentally inject
    a stray leading space — the greeting should be unchanged."""
    settings = IntakeV2Settings(consent_disclosure="")
    out = compose_call_greeting("Hi from Ashley.", settings, gate_eligible=True)
    assert out == "Hi from Ashley."


def test_eligible_with_whitespace_disclosure_falls_back_to_base():
    settings = IntakeV2Settings(consent_disclosure="   ")
    out = compose_call_greeting("Hi from Ashley.", settings, gate_eligible=True)
    assert out == "Hi from Ashley."


def test_empty_base_greeting_uses_default():
    """If the operator wiped the call_greeting, the v1 default still plays."""
    settings = IntakeV2Settings(consent_disclosure="Recorded.")
    out = compose_call_greeting("", settings, gate_eligible=False)
    assert out == DEFAULT_CALL_GREETING


def test_eligible_with_default_disclosure_uses_legal_text():
    settings = IntakeV2Settings()  # disclosure defaults to DEFAULT_V2_CONSENT_DISCLOSURE
    out = compose_call_greeting("Hi from Ashley.", settings, gate_eligible=True)
    assert out.startswith(DEFAULT_V2_CONSENT_DISCLOSURE)
    assert out.endswith("Hi from Ashley.")
