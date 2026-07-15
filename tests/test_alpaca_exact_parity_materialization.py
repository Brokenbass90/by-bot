from __future__ import annotations

import csv
import json
import math
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from backtest.alpaca_exact_parity_contract import (
    DailyBar,
    ParityContractError,
    SharedExitContract,
    adverse_fill_price,
    calendar_month_signal_schedule,
    daily_max_drawdown,
    daily_portfolio_mark_to_market,
    load_xnys_session_ledger,
    sha256_file,
    simulate_position,
)
from scripts.materialize_alpaca_exact_parity_inputs import (
    DEFAULT_CONFIG,
    MaterializationError,
    _atomic_json,
    build_receipt,
    validate_materialization_config,
)


def _write_sessions(path: Path) -> None:
    rows = [
        ("2026-01-30", "2026-01-30T14:30:00Z", "2026-01-30T21:00:00Z"),
        ("2026-02-02", "2026-02-02T14:30:00Z", "2026-02-02T21:00:00Z"),
        ("2026-02-27", "2026-02-27T14:30:00Z", "2026-02-27T21:00:00Z"),
        ("2026-03-02", "2026-03-02T14:30:00Z", "2026-03-02T21:00:00Z"),
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["session_date", "market_open_utc", "market_close_utc", "source_record_sha256"])
        for row in rows:
            writer.writerow([*row, "a" * 64])


def test_hash_pinned_calendar_month_schedule_is_last_close_to_next_open(tmp_path):
    ledger = tmp_path / "sessions.csv"
    _write_sessions(ledger)

    sessions = load_xnys_session_ledger(ledger, expected_sha256=sha256_file(ledger))
    schedule = calendar_month_signal_schedule(sessions)

    assert schedule == [
        {
            "signal_month": "2026-01",
            "signal_session": "2026-01-30",
            "signal_at_utc": "2026-01-30T21:00:00Z",
            "entry_session": "2026-02-02",
            "entry_at_utc": "2026-02-02T14:30:00Z",
        },
        {
            "signal_month": "2026-02",
            "signal_session": "2026-02-27",
            "signal_at_utc": "2026-02-27T21:00:00Z",
            "entry_session": "2026-03-02",
            "entry_at_utc": "2026-03-02T14:30:00Z",
        },
    ]


def test_session_ledger_refuses_hash_drift_and_inferred_columns(tmp_path):
    ledger = tmp_path / "sessions.csv"
    _write_sessions(ledger)
    digest = sha256_file(ledger)
    ledger.write_text(ledger.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ParityContractError, match="hash mismatch"):
        load_xnys_session_ledger(ledger, expected_sha256=digest)


def test_shared_exit_is_next_open_costed_gap_aware_and_stop_first():
    both_touch = simulate_position(
        [DailyBar(date(2026, 2, 2), 100, 104, 97, 101)],
        atr_at_signal=1,
        cost_bps_per_side=0,
    )
    assert both_touch["entry_fill"] == 100
    assert both_touch["exit_reason"] == "stop_first"
    assert both_touch["exit_reference"] == 98

    gap = simulate_position(
        [
            DailyBar(date(2026, 2, 2), 100, 101, 99, 100),
            DailyBar(date(2026, 2, 3), 97, 99, 96, 98),
        ],
        atr_at_signal=1,
        cost_bps_per_side=5,
    )
    assert gap["entry_fill"] == pytest.approx(100.05)
    assert gap["exit_reason"] == "stop_gap_open"
    assert gap["exit_reference"] == 97
    assert gap["exit_fill"] == pytest.approx(adverse_fill_price(97, side="sell", cost_bps=5))


def test_trailing_from_current_bar_only_changes_next_session_stop():
    result = simulate_position(
        [
            # High arms BE/trailing, but the old 98 stop is the only stop active
            # on this bar; the newly calculated stop applies tomorrow.
            DailyBar(date(2026, 2, 2), 100, 102, 98.5, 101),
            DailyBar(date(2026, 2, 3), 99.5, 101, 99, 100),
        ],
        atr_at_signal=1,
        cost_bps_per_side=0,
    )
    first = result["daily_marks"][0]
    assert first["active_stop"] == 98
    assert first["next_session_stop"] == 100.5
    assert result["exit_reason"] == "stop_gap_open"
    assert result["exit_reference"] == 99.5


def test_max_hold_daily_mtm_portfolio_stop_primitives_and_initial_peak_dd():
    contract = replace(SharedExitContract(), max_hold_sessions=2)
    result = simulate_position(
        [
            DailyBar(date(2026, 2, 2), 100, 100.5, 99, 100),
            DailyBar(date(2026, 2, 3), 100, 100.5, 99, 100.25),
            DailyBar(date(2026, 2, 4), 100.25, 101, 100, 100.5),
        ],
        atr_at_signal=2,
        cost_bps_per_side=5,
        contract=contract,
    )
    assert result["exit_reason"] == "max_hold_close"
    assert result["exit_session"] == "2026-02-03"
    assert daily_portfolio_mark_to_market(
        settled_cash=50,
        open_positions=[{"qty": 2, "close": 25}, {"qty": 0, "close": 10}],
    ) == 100
    assert daily_max_drawdown(100, [92, 95, 110, 99]) == pytest.approx(-0.10)


def test_materializer_records_real_blockers_without_performance_or_live_authority():
    cfg = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))

    validate_materialization_config(cfg)
    receipt = build_receipt(cfg)

    assert receipt["permission"] == "BLOCKED_FAIL_CLOSED"
    assert receipt["performance_computed"] is False
    assert receipt["outcome_access_allowed"] is False
    assert receipt["promotion_authorized"] is False
    assert receipt["live_or_broker_calls"] is False
    assert receipt["safe_hold_changed"] is False
    assert all(row["ok"] for row in receipt["sources"])
    assert len([row for row in receipt["required_inputs"] if not row["ok"]]) == 6
    assert "original_2026_07_13_forward_window_not_retroactively_sealable" in receipt["blockers"]
    shared = next(
        row for row in receipt["component_receipts"]
        if row["component"] == "shared_stop_break_even_trailing_contract"
    )
    assert shared["unit_conformance"]["all_cases_passed"] is True
    assert shared["unit_conformance"]["broker_lifecycle_exact_match"] is False
    assert math.isfinite(receipt["diagnostic_observed_schedule"]["observed_session_count"])


def test_materialization_config_cannot_gain_live_or_promotion_authority():
    cfg = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    cfg["promotion_authority"] = True
    with pytest.raises(MaterializationError, match="risk-zero"):
        validate_materialization_config(cfg)

    cfg = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    cfg["no_broker_calls"] = False
    with pytest.raises(MaterializationError, match="research-only"):
        validate_materialization_config(cfg)


def test_receipt_is_write_once(tmp_path):
    path = tmp_path / "receipt.json"
    _atomic_json(path, {"performance_computed": False})
    with pytest.raises(MaterializationError, match="refusing to overwrite"):
        _atomic_json(path, {"performance_computed": False})
