"""Unit tests for the parallel-calls plumbing landed in Phases 1–6.

These don't exercise the full call flow (which needs a DB) — they pin down
the invariants that, if broken, would let us silently double-dial or leak
slots at DEFAULT_MAX_PARALLEL_CALLS > 1.
"""
import pytest

from app.services.dispatcher import (
    ActiveCall,
    AutoCallDispatcher,
    DispatcherState,
    DEFAULT_MAX_PARALLEL_CALLS,
)
from app.services.orchestrator_registry import OrchestratorRegistry


# -- Dispatcher slot accounting -------------------------------------------

def _fake_entry(pid: str, phase: str = "active", call_id: str = "c1") -> ActiveCall:
    return ActiveCall(
        patient_id=pid, patient_name=pid, dispatched_at=0.0,
        phase=phase, call_id=call_id,
    )


def test_default_max_parallel_calls_is_one():
    # The default is 1 so existing deployments keep single-call behavior
    # until an operator opts in via DispatcherSettings.max_parallel_calls.
    assert DEFAULT_MAX_PARALLEL_CALLS == 1


def test_empty_dispatcher_reports_zero_slots():
    d = AutoCallDispatcher()
    assert d._occupied_slots() == 0


def test_active_call_consumes_slot():
    d = AutoCallDispatcher()
    d._active_calls["p1"] = _fake_entry("p1", phase="active")
    assert d._occupied_slots() == 1


def test_dispatched_phase_still_counts_against_cap():
    # A pre-dispatched candidate must hold the slot — otherwise a second
    # tick could start a parallel dispatch while the first waits for a
    # voice client.
    d = AutoCallDispatcher()
    d._active_calls["p1"] = _fake_entry("p1", phase="dispatched")
    assert d._occupied_slots() == 1


def test_voicemail_phase_frees_slot():
    # Phase 5: once AMD detects an answering machine, the slot is released
    # so the next call can start while the AI reads the VM script.
    d = AutoCallDispatcher()
    d._active_calls["p1"] = _fake_entry("p1", phase="active")
    d.notify_voicemail_started("p1")
    assert d._active_calls["p1"].phase == "voicemail"
    assert d._occupied_slots() == 0


def test_notify_voicemail_started_noop_on_unknown_patient():
    d = AutoCallDispatcher()
    d.notify_voicemail_started("ghost")  # must not raise


def test_notify_voicemail_started_idempotent():
    d = AutoCallDispatcher()
    d._active_calls["p1"] = _fake_entry("p1", phase="voicemail")
    d.notify_voicemail_started("p1")
    assert d._active_calls["p1"].phase == "voicemail"


# -- notify_call_started / notify_call_ended ------------------------------

def test_notify_call_started_creates_manual_entry():
    d = AutoCallDispatcher()
    d.notify_call_started("p1", call_id="c1")
    assert "p1" in d._active_calls
    assert d._active_calls["p1"].phase == "active"
    assert d._active_calls["p1"].call_id == "c1"


def test_notify_call_started_promotes_dispatched_entry():
    d = AutoCallDispatcher()
    d._active_calls["p1"] = _fake_entry("p1", phase="dispatched", call_id=None)
    d.notify_call_started("p1", call_id="c-real")
    assert d._active_calls["p1"].phase == "active"
    assert d._active_calls["p1"].call_id == "c-real"


def test_notify_call_ended_by_patient_id():
    d = AutoCallDispatcher()
    d._active_calls["p1"] = _fake_entry("p1")
    d._active_calls["p2"] = _fake_entry("p2")
    d.notify_call_ended("p2")
    assert set(d._active_calls) == {"p1"}


def test_notify_call_ended_legacy_no_arg_drops_oldest():
    # websocket.py calls notify_call_ended() with no arg. At max==1 this
    # must clear the single entry. At max>1 we rely on insertion-ordered
    # dict iteration — p1 was inserted first, so it's the one removed.
    d = AutoCallDispatcher()
    d._active_calls["p1"] = _fake_entry("p1")
    d._active_calls["p2"] = _fake_entry("p2")
    d.notify_call_ended()
    assert set(d._active_calls) == {"p2"}


def test_notify_call_ended_empty_is_noop():
    d = AutoCallDispatcher()
    d.notify_call_ended()
    d.notify_call_ended("ghost")


# -- get_status ------------------------------------------------------------

def test_get_status_reports_active_calls_and_cap():
    d = AutoCallDispatcher()
    d._active_calls["p1"] = _fake_entry("p1", phase="voicemail", call_id="c1")
    status = d.get_status()
    assert status["max_parallel_calls"] == DEFAULT_MAX_PARALLEL_CALLS
    assert status["dispatched_patient_id"] == "p1"  # back-compat shim
    assert status["active_calls"] == [
        {
            "patient_id": "p1",
            "patient_name": "p1",
            "phase": "voicemail",
            "call_id": "c1",
            "dispatched_at": 0.0,
        }
    ]


def test_initial_state_is_stopped():
    d = AutoCallDispatcher()
    assert d.state == DispatcherState.STOPPED


# -- Phase 7 settings plumbing --------------------------------------------

def test_update_config_clamps_max_parallel_calls():
    # Settings provider also clamps, but the dispatcher must defend itself
    # in case it's called directly (e.g. from main.py boot).
    d = AutoCallDispatcher()
    d.update_config(10, 30, 4, 4, 6, max_parallel_calls=999, dispatch_pacing_seconds=2)
    assert d.max_parallel_calls == 10  # MAX_PARALLEL_CALLS_HARD_CEILING
    assert d.dispatch_pacing_seconds == 2

    d.update_config(10, 30, 4, 4, 6, max_parallel_calls=0, dispatch_pacing_seconds=-1)
    assert d.max_parallel_calls == 1
    assert d.dispatch_pacing_seconds == 0


def test_get_status_reflects_runtime_max_parallel_calls():
    # The status payload must report the live (potentially raised) cap, not
    # the constant default — UI uses this to render N tiles.
    d = AutoCallDispatcher()
    d.update_config(10, 30, 4, 4, 6, max_parallel_calls=4, dispatch_pacing_seconds=1)
    status = d.get_status()
    assert status["max_parallel_calls"] == 4


def test_dispatcher_settings_default_max_parallel_calls():
    from app.models.system_settings import DispatcherSettings
    assert DispatcherSettings().max_parallel_calls == 1
    assert DispatcherSettings().dispatch_pacing_seconds == 1


def test_notify_call_started_warns_when_manual_call_overshoots_cap(caplog):
    # Backend defense-in-depth: the UI disables the manual-call button when
    # at cap, but if anything bypasses the UI we want a loud warning.
    import logging
    d = AutoCallDispatcher()
    d.max_parallel_calls = 2
    d._active_calls["p1"] = _fake_entry("p1", phase="active")
    d._active_calls["p2"] = _fake_entry("p2", phase="active")
    with caplog.at_level(logging.WARNING, logger="app.services.dispatcher"):
        d.notify_call_started("p3", call_id="c3")
    assert any("pushes occupied=3 past cap=2" in r.message for r in caplog.records)
    # The entry is still added — by the time this fires, the call exists.
    assert "p3" in d._active_calls


def test_notify_call_started_no_warn_at_cap_when_promoting_dispatched():
    # Promoting a 'dispatched' entry to 'active' shouldn't warn — the slot
    # was already counted when the entry was created.
    import logging
    d = AutoCallDispatcher()
    d.max_parallel_calls = 1
    d._active_calls["p1"] = _fake_entry("p1", phase="dispatched")
    # Promote — still 1/1, no warning.
    d.notify_call_started("p1", call_id="c1")
    assert d._active_calls["p1"].phase == "active"


def test_stop_clears_pick_lock():
    # The lock must be dropped on stop so the next start() rebinds it to
    # whichever event loop hosts the new run loop.
    d = AutoCallDispatcher()
    d._pick_lock = "sentinel"  # type: ignore
    d.stop()
    assert d._pick_lock is None


# -- OrchestratorRegistry --------------------------------------------------

def test_registry_roundtrip_by_all_indexes():
    r = OrchestratorRegistry()
    session = object()
    r.register("call-1", "pat-1", session)
    r.bind_twilio_sid("call-1", "SID123")
    assert r.by_call_id("call-1") is session
    assert r.by_patient_id("pat-1") is session
    assert r.by_twilio_sid("SID123") is session
    assert r.active_count() == 1


def test_registry_unregister_clears_all_indexes():
    r = OrchestratorRegistry()
    r.register("call-1", "pat-1", object())
    r.bind_twilio_sid("call-1", "SID123")
    r.unregister("call-1")
    assert r.by_call_id("call-1") is None
    assert r.by_patient_id("pat-1") is None
    assert r.by_twilio_sid("SID123") is None
    assert r.active_count() == 0


def test_registry_handles_missing_lookups():
    r = OrchestratorRegistry()
    assert r.by_call_id("missing") is None
    assert r.by_twilio_sid("missing") is None
    assert r.by_patient_id("missing") is None
    r.unregister("missing")  # must not raise


def test_registry_bind_without_register_is_ignored_on_lookup():
    # bind_twilio_sid creates an index entry, but by_twilio_sid also looks
    # through _by_call_id, so an orphan binding surfaces None cleanly.
    r = OrchestratorRegistry()
    r.bind_twilio_sid("orphan-call", "SIDX")
    assert r.by_twilio_sid("SIDX") is None


def test_registry_clear_wipes_everything():
    r = OrchestratorRegistry()
    r.register("c1", "p1", object())
    r.bind_twilio_sid("c1", "S1")
    r.register("c2", "p2", object())
    r.clear()
    assert r.active_count() == 0
    assert r.by_twilio_sid("S1") is None


# -- CallLogProvider multi-slot -------------------------------------------

def test_call_log_provider_has_active_call_multi_slot():
    from app.providers.call_log_provider import CallLogProvider
    p = CallLogProvider()
    assert not p.has_active_call()
    p._active_call_ids["c1"] = None
    p._active_call_ids["c2"] = None
    assert p.has_active_call()
    assert p.has_active_call("c1")
    assert p.has_active_call("c2")
    assert not p.has_active_call("c3")
    assert p.active_call_count() == 2


def test_call_log_provider_clear_active_call_clears_dict():
    from app.providers.call_log_provider import CallLogProvider
    p = CallLogProvider()
    p._active_call_ids.update({"c1": None, "c2": None})
    p.clear_active_call()
    assert p.active_call_count() == 0


def test_call_log_provider_active_calls_are_insertion_ordered():
    # get_active_call() must return the earliest live call deterministically
    # — we rely on this in dispatcher self-heal and in the legacy single-slot
    # callers that expect "the" current call.
    from app.providers.call_log_provider import CallLogProvider
    p = CallLogProvider()
    p._active_call_ids["b"] = None
    p._active_call_ids["a"] = None
    p._active_call_ids["c"] = None
    assert next(iter(p._active_call_ids)) == "b"
