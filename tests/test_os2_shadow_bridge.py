import copy
import pytest

from os2_bridge_fixture import END, HOUR, bundle, repin, signal, terminal
from research_lab.os2_shadow_bridge import assess_bundle, empty_state


def test_neutral_is_valid_closed_data_with_one_canonical_envelope():
    result = assess_bundle(bundle(), empty_state())
    assert result["status"] == "SHADOW_WIRING_PASS"
    assert result["regime_envelope"]["validity"] == "VALID"
    assert result["regime_envelope"]["label"] == "NEUTRAL"
    assert result["regime_envelope"]["closed_cutoff_ms"] == END
    assert result["decisions"][0]["decision"] == "enter"
    assert result["decisions"][0]["context"]["money_authorized"] is False
    assert len(result["state_after"]["reservations"]) == 1


@pytest.mark.parametrize("fault", ["missing", "duplicate", "unordered", "future", "late", "warmup", "bad_ohlc", "nan", "stale", "clock"])
def test_invalid_source_is_unknown_and_records_rejection(fault):
    b = bundle()
    rows = b["source"]["rows"]
    if fault == "missing": rows.pop(-2)
    elif fault == "duplicate": rows[-2] = rows[-1][:]
    elif fault == "unordered": rows.reverse()
    elif fault == "future": rows[-1][0] += HOUR
    elif fault == "late": rows[-1][6] = b["decision_ms"] + 1
    elif fault == "warmup": b["source"]["rows"] = rows[4:]
    elif fault == "bad_ohlc": rows[-1][2] = 90
    elif fault == "nan": rows[-1][4] = float("nan")
    elif fault == "stale": b["source"]["observed_ms"] -= 300001
    elif fault == "clock": b["clock_uncertainty_ms"] = 251
    if fault != "nan": repin(b)
    r = assess_bundle(b, empty_state())
    assert r["status"] == "BLOCKED_DATA"
    assert r["regime_envelope"]["validity"] == "UNKNOWN"
    assert r["decisions"][0]["decision"] == "skip"
    assert not r["state_after"]["reservations"]


def test_uncertainty_uses_conservative_cutoff():
    b = bundle(); b["decision_ms"] = END + 100; b["clock_uncertainty_ms"] = 200
    assert assess_bundle(b, empty_state())["status"] == "BLOCKED_DATA"


def test_external_sources_never_activate_policy_or_fixture_statistics():
    b = bundle(); b["mode"] = "EXTERNAL_PUBLIC"
    r = assess_bundle(b, empty_state())
    assert r["status"] == "BLOCKED_DATA"
    assert r["reason"] == "POLICY_UNAPPROVED"
    assert not r["state_after"]["reservations"]
    assert not r["diagnostics"]["health"]


@pytest.mark.parametrize("field", ["positions", "correlations"])
def test_missing_exposure_provenance_is_not_zero(field):
    b = bundle(); del b[field]
    assert assess_bundle(b, empty_state())["status"] == "BLOCKED_DATA"


def test_missing_correlation_rejects_and_exposure_reject_does_not_consume_slot():
    b = bundle([signal("a", "ETHUSDT", rank=1), signal("b", "SOLUSDT", cluster="sol")])
    b["positions"]["rows"] = [{"symbol": "BTCUSDT", "side": "long", "risk_pct": 1.2, "beta_cluster": "btc"}]
    b["correlations"]["rows"] = [["BTCUSDT", "ETHUSDT", 0.9], ["BTCUSDT", "SOLUSDT", 0.1]]
    r = assess_bundle(repin(b), empty_state())
    d = {v["context"]["event_id"]: v for v in r["decisions"]}
    assert d["a"]["reason"] == "cluster_budget_exceeded"
    assert d["b"]["decision"] == "enter"
    b["correlations"]["rows"] = []
    assert all(d["decision"] == "skip" for d in assess_bundle(repin(b), empty_state())["decisions"])


def test_persisted_slots_survive_empty_caller_positions_and_reordered_overlap():
    r = assess_bundle(bundle(), empty_state())
    b = bundle([signal("s2")]); b["request_id"] = "r2"
    r2 = assess_bundle(b, r["state_after"])
    assert r2["decisions"][0]["reason"] == "symbol_overlap"
    assert len(r2["state_after"]["reservations"]) == 1


def test_exact_duplicate_and_changed_identity_cannot_reserve_again():
    b = bundle(); r = assess_bundle(b, empty_state())
    r2 = assess_bundle(b, r["state_after"])
    assert r2["decisions"][0]["reason"] == "duplicate_event"
    b["events"][0]["risk_pct"] = 1.0
    assert assess_bundle(b, r["state_after"])["reason"] == "event_identity_conflict"


@pytest.mark.parametrize("change", [{"source_pin": "c" * 64}, {"source_id": "other"}, {"continuity": "GAP"},
                                   {"costs_complete": False}, {"finality": False}, {"filled": False},
                                   {"terminal_ms": END + 5000}, {"net_r": float("nan")}])
def test_unproven_terminal_never_frees_or_counts(change):
    state = assess_bundle(bundle(), empty_state())["state_after"]
    r = assess_bundle(bundle([terminal(**change)]), state)
    assert len(r["state_after"]["reservations"]) == 1
    assert not r["state_after"]["terminals"]


def test_clean_terminal_is_once_only_and_diagnostics_are_fixture_proposals():
    state = assess_bundle(bundle(), empty_state())["state_after"]
    b = bundle([terminal()]); b["request_id"] = "r2"
    r = assess_bundle(b, state)
    assert not r["state_after"]["reservations"]
    assert len(r["state_after"]["terminals"]) == 1
    assert r["diagnostics"]["health"]["fixture"]["drawdown_R"] == 2.0
    assert r["diagnostics"]["evidence_kind"] == "FIXTURE"
    assert r["diagnostics"]["money_authorized"] is False
    assert "insufficient" in r["diagnostics"]["health"]["fixture"]["reason"]
    again = assess_bundle(b, r["state_after"])
    assert len(again["state_after"]["terminals"]) == 1
    replacement = assess_bundle(bundle([signal("s2")]), r["state_after"])
    assert replacement["decisions"][0]["reason"] == "cooldown"


def test_fixture_policy_and_source_domain_cannot_change_after_start():
    state = assess_bundle(bundle(), empty_state())["state_after"]
    b = bundle(); b["policy"]["allowed_regimes"]["fixture"] = ["BULL_TREND"]
    assert assess_bundle(b, state)["reason"] == "source_or_policy_conflict"


def test_historical_constituent_revision_is_not_accepted_as_new_source():
    state = assess_bundle(bundle(), empty_state())["state_after"]
    b = bundle(); b["source"]["rows"][0][4] = 100.5; repin(b)
    assert assess_bundle(b, state)["reason"] == "regime_source_revision"


def test_no_signal_and_bad_candidate_each_have_a_decision():
    b = bundle([{"id": "none", "type": "NO_SIGNAL"}, signal("bad")])
    b["events"][1]["money_authorized"] = True
    r = assess_bundle(b, empty_state())
    assert len(r["decisions"]) == 2
    assert {d["reason"] for d in r["decisions"]} == {"no_signal", "invalid_candidate"}


def test_assessor_does_not_mutate_input_or_state():
    b = bundle(); s = empty_state(); old = copy.deepcopy((b, s))
    assess_bundle(b, s)
    assert (b, s) == old
