from os2_bridge_fixture import END, HOUR, bundle, repin, signal, terminal
from research_lab.os2_shadow_bridge import assess_bundle, empty_state
import pytest


def test_old_intent_cannot_be_annotated_with_a_later_regime():
    b = bundle(); b["events"][0]["signal_ms"] = END - 1
    r = assess_bundle(b, empty_state())
    assert r["decisions"][0]["decision"] == "skip"
    assert r["decisions"][0]["reason"] == "invalid_candidate"


def test_terminal_before_durable_admission_cannot_free_or_count():
    state = assess_bundle(bundle(), empty_state())["state_after"]
    b = bundle([terminal(terminal_ms=END, available_ms=END + 1)])
    r = assess_bundle(b, state)
    assert r["state_after"]["reservations"]
    assert not r["state_after"]["terminals"]


def test_rejected_identity_body_is_frozen_too():
    b = bundle(); b["policy"]["allowed_regimes"] = {"fixture": ["BULL_TREND"], "other": ["NEUTRAL"]}
    state = assess_bundle(b, empty_state())["state_after"]
    b["events"][0]["strategy"] = "other"
    r = assess_bundle(b, state)
    assert r["reason"] == "event_identity_conflict"
    assert not r["state_after"]["reservations"]


def test_shorter_prefix_cannot_erase_revision_memory():
    b = bundle([])
    rows = b["source"]["rows"]
    first = rows[0][0]
    older = [[first - (560 - i) * HOUR, 100., 101., 99., 100., 10., first - (559 - i) * HOUR + 1000] for i in range(560)]
    b["source"]["rows"] = older + rows; repin(b)
    state = assess_bundle(b, empty_state())["state_after"]
    small = bundle([])
    state = assess_bundle(small, state)["state_after"]
    b["source"]["rows"][0][4] = 100.5; repin(b)
    r = assess_bundle(b, state)
    assert r["reason"] == "regime_source_revision"


def test_long_and_short_health_cannot_cancel_and_terminal_cannot_spoof_side():
    b = bundle([signal("long", "ETHUSDT"), signal("short", "SOLUSDT", "short", "sol")])
    b["correlations"]["rows"] = [["ETHUSDT", "SOLUSDT", 0.1]]; repin(b)
    state = assess_bundle(b, empty_state())["state_after"]
    ends = [terminal("long", "tl", net_r=-2), terminal("short", "ts", net_r=2)]
    b = bundle(ends); b["decision_ms"] = END + 4000
    r = assess_bundle(b, state)
    assert set(r["diagnostics"]["health"]) == {"fixture:long", "fixture:short"}
    assert r["diagnostics"]["health"]["fixture:long"]["drawdown_R"] == 2
    assert r["diagnostics"]["registry"]["fixture:short"]["risk_mult"] == 0
    forged = bundle([terminal("long", "spoof", side="short")]); forged["decision_ms"] = END + 4000
    r = assess_bundle(forged, state)
    assert "long" in r["state_after"]["reservations"]
    assert not r["state_after"]["terminals"]


def test_regime_hash_and_unknown_fields_cannot_change_candidate_contract():
    b = bundle(); b["events"][0]["regime_source_pin"] = "c" * 64
    assert assess_bundle(b, empty_state())["decisions"][0]["decision"] == "skip"
    b = bundle(); b["events"][0]["unexpected_secret"] = "do-not-persist"
    r = assess_bundle(b, empty_state())
    assert not r["state_after"]["reservations"]


def test_strategy_dependency_identity_is_frozen_across_intents():
    state = assess_bundle(bundle(), empty_state())["state_after"]
    b = bundle([signal("changed", "SOLUSDT", "short", "sol")])
    b["correlations"]["rows"] = [["ETHUSDT", "SOLUSDT", 0.1]]; repin(b)
    b["events"][0]["dependencies"]["strategy"] = "c" * 64
    r = assess_bundle(b, state)
    assert r["decisions"][0]["reason"] == "strategy_identity_conflict"
    assert len(r["state_after"]["reservations"]) == 1


def test_denominators_are_durable_unique_observations():
    b = bundle([signal(), {"id": "none", "type": "NO_SIGNAL"}])
    r = assess_bundle(b, empty_state())
    assert r["diagnostics"]["denominators"]["signals"] == 1
    assert r["diagnostics"]["denominators"]["selected"] == 1
    assert r["diagnostics"]["denominators"]["no_signal"] == 1
    again = assess_bundle(b, r["state_after"])
    assert again["diagnostics"]["denominators"] == r["diagnostics"]["denominators"]


@pytest.mark.parametrize("bad_id", [[], {}, None, 123])
def test_malformed_identity_is_a_blocked_receipt_not_an_exception(bad_id):
    b = bundle(); b["events"][0]["id"] = bad_id
    r = assess_bundle(b, empty_state())
    assert r["status"] == "BLOCKED_DATA"
    assert r["reason"] == "missing_event_identity"
    assert not r["state_after"]["reservations"]


@pytest.mark.parametrize("field,value", [("symbol", "ETHUSDT"), ("timeframe", "4h")])
def test_regime_source_must_explicitly_identify_btc_h1(field, value):
    b = bundle(); b["source"][field] = value
    r = assess_bundle(b, empty_state())
    assert r["status"] == "BLOCKED_DATA"
    assert r["regime_envelope"]["validity"] == "UNKNOWN"


def test_four_hour_aggregation_cannot_overflow_finite_inputs():
    b = bundle()
    for row in b["source"]["rows"]: row[5] = 1e308
    repin(b)
    assert assess_bundle(b, empty_state())["status"] == "BLOCKED_DATA"


def test_conflicting_bundle_does_not_credit_uncommitted_observation_id():
    state = assess_bundle(bundle(), empty_state())["state_after"]
    b = bundle([signal("new", "SOLUSDT", "short", "sol"), signal()])
    b["events"][1]["risk_pct"] = 1
    r = assess_bundle(b, state)
    assert r["reason"] == "event_identity_conflict"
    assert r["state_after"]["counts"] == state["counts"]
