from __future__ import annotations

import copy

from research_lab.adapter_parity import SCHEMA_ID, compare_ledgers


def _row(**updates):
    row = {
        "schema_id": SCHEMA_ID,
        "symbol": "BTCUSDT",
        "bar_ts": 1_700_000_000_000,
        "side": "short",
        "signal_id": "att1:btc:1",
        "entry": 100.0,
        "sl": 102.0,
        "tp1": 97.6,
        "tp2": 95.0,
        "tp_fracs": [0.55, 0.45],
        "runner_fraction": 0.45,
        "time_stop": 4032,
        "cooldown_state": {"bars": 8},
        "regime_value": "flat_down",
        "regime_bar_ts": 1_699_999_200_000,
        "validator_drop_reason": "",
        "config_hash": "config",
        "source_hash": "source",
        "data_hash": "data",
        "tick_size": 0.1,
        "outcome": "tp1_then_stop",
        "net_r": 0.21,
        "exception": None,
    }
    row.update(updates)
    return row


def _ledger(row):
    return {(row["symbol"], row["bar_ts"], row["side"]): row}


def test_identical_ledgers_pass():
    row = _row()
    report = compare_ledgers(_ledger(row), _ledger(copy.deepcopy(row)))
    assert report["decision"] == "PASS"
    assert report["failures"] == []


def test_price_within_one_tick_passes():
    research = _row()
    live = copy.deepcopy(research)
    live["sl"] += 0.1
    assert compare_ledgers(_ledger(research), _ledger(live))["decision"] == "PASS"


def test_geometry_mismatch_fails_closed():
    research = _row()
    live = copy.deepcopy(research)
    live["sl"] += 0.11
    report = compare_ledgers(_ledger(research), _ledger(live))
    assert report["decision"] == "FAIL_CLOSED"
    assert "contract_field_mismatch" in report["failures"]


def test_regime_or_outcome_mismatch_fails_closed():
    research = _row()
    live = copy.deepcopy(research)
    live["regime_value"] = "flat_up"
    live["net_r"] = 0.19
    report = compare_ledgers(_ledger(research), _ledger(live))
    assert report["decision"] == "FAIL_CLOSED"
    fields = {item["field"] for item in report["mismatches"]}
    assert {"regime_value", "net_r"}.issubset(fields)


def test_unmatched_row_fails_closed():
    research = _row()
    live = copy.deepcopy(research)
    live["bar_ts"] += 3_600_000
    report = compare_ledgers(_ledger(research), _ledger(live))
    assert report["decision"] == "FAIL_CLOSED"
    assert "unmatched_evaluation_rows" in report["failures"]
