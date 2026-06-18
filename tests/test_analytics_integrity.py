from __future__ import annotations

import json

import pytest

from scripts import claude_monthly_analyst as monthly
from scripts import equities_alpaca_intraday_bridge as intraday
from scripts import equities_alpaca_paper_bridge as monthly_bridge
from scripts import live_vs_backtest_monitor as monitor
from scripts import post_trade_ai_review as post_trade
from scripts import pnl_by_sleeve
from scripts import run_pair_arb_matrix


def test_trade_learning_summary_uses_live_schema() -> None:
    result = monthly._trade_learning_summary(
        [
            {"pnl_closed": 0.5, "tags": ["clean_tp"]},
            {"pnl_closed": -0.25, "tags": ["fast_stop", "fee_drag"]},
        ]
    )

    assert result["win_rate"] == 0.5
    assert result["avg_win"] == 0.5
    assert result["avg_loss"] == -0.25
    assert result["patterns"] == {"clean_tp": 1, "fast_stop": 1, "fee_drag": 1}


def test_intraday_state_summary_reads_position_map() -> None:
    result = monthly._intraday_state_summary(
        {
            "COST": {"symbol": "COST", "realized_pnl": 1.25},
            "MSFT": {"symbol": "MSFT", "realized_pnl": -0.25},
        }
    )

    assert result["open_positions"] == 2
    assert result["realized_pnl"] == 1.0


def test_post_trade_context_is_labeled_review_time(monkeypatch) -> None:
    monkeypatch.setattr(post_trade, "_scanner_setup_for", lambda symbol: {"side": "Buy"})
    monkeypatch.setattr(post_trade, "_ohlc_for", lambda symbol: {"close": 10})

    compact = post_trade._compact_trade_for_ai(
        {"close": {"symbol": "BTCUSDT", "strategy": "range", "ts": 20}}
    )

    assert compact["context_timing"] == "review_time_not_entry_time"
    assert compact["scanner_setup_at_review_time"] == {"side": "Buy"}
    assert "scanner_setup_at_run_time" not in compact


def test_range_has_monitor_reference_and_pause_key() -> None:
    assert monitor._DEFAULT_BACKTEST_PF["range"] == 1.25
    assert monitor._STRATEGY_RISK_KEY["range"] == "RANGE_RISK_MULT"


def test_monthly_cleanup_fails_closed_on_malformed_intraday_state(tmp_path, monkeypatch) -> None:
    state_path = tmp_path / "intraday_state.json"
    state_path.write_text("{partial", encoding="utf-8")
    monkeypatch.setenv("ALPACA_INTRADAY_STATE_PATH", str(state_path))
    monkeypatch.setenv("ALPACA_INTRADAY_ADVISORY_PATH", str(tmp_path / "missing.json"))

    with pytest.raises(RuntimeError, match="refusing monthly cleanup"):
        monthly_bridge._load_intraday_managed_symbols(strict=True)


def test_intraday_state_save_is_atomic(tmp_path, monkeypatch) -> None:
    state_path = tmp_path / "intraday_state.json"
    monkeypatch.setattr(intraday, "STATE_FILE", state_path)
    position = intraday.PositionState(
        symbol="MSFT",
        side="long",
        entry_price=100.0,
        sl_price=98.0,
        tp_price=104.0,
        qty=1.0,
        entry_ts=1,
    )

    intraday._save_state({"MSFT": position})

    assert json.loads(state_path.read_text(encoding="utf-8"))["MSFT"]["symbol"] == "MSFT"
    assert not state_path.with_suffix(".json.tmp").exists()


def test_fractional_alpaca_long_closes_at_software_take_profit(monkeypatch) -> None:
    monkeypatch.setenv("INTRADAY_TRAIL_ENABLE", "0")
    position = intraday.PositionState(
        symbol="PLTR",
        side="long",
        entry_price=132.10,
        sl_price=131.28,
        tp_price=132.91,
        qty=1.136,
        entry_ts=1,
    )

    decision = intraday._position_management_decision(
        position,
        {"side": "long", "current_price": "133.00"},
        now_ts=60,
    )

    assert decision["action"] == "close"
    assert decision["reason"] == "software_take_profit"


def test_fractional_alpaca_short_closes_at_software_stop(monkeypatch) -> None:
    monkeypatch.setenv("INTRADAY_TRAIL_ENABLE", "0")
    position = intraday.PositionState(
        symbol="XYZ",
        side="short",
        entry_price=100.0,
        sl_price=102.0,
        tp_price=96.0,
        qty=0.5,
        entry_ts=1,
    )

    decision = intraday._position_management_decision(
        position,
        {"side": "short", "current_price": "102.10"},
        now_ts=60,
    )

    assert decision["action"] == "close"
    assert decision["reason"] == "software_stop_loss"


def test_pnl_breakdown_can_isolate_current_canary(tmp_path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        "\n".join(
            [
                json.dumps({"event": "close", "strategy": "range", "pnl": -1.0, "fees": 0.1, "ts_utc": "2026-04-28 08:00:00 UTC"}),
                json.dumps({"event": "close", "strategy": "range", "pnl": 0.5, "fees": 0.02, "ts_utc": "2026-06-17 10:00:00 UTC"}),
            ]
        ),
        encoding="utf-8",
    )

    result = pnl_by_sleeve.build_breakdown(events, since_day="2026-06-17")

    assert result["total"]["pnl"] == 0.5
    assert result["total"]["trades"] == 1


def test_pair_arb_matrix_reads_nested_walkforward_metrics() -> None:
    result = {
        "oos_aggregate": {
            "profit_factor": {"mean": 1.23, "median": 1.10},
            "return_pct": {"mean": 2.5},
        },
        "win_rate_all": 0.54,
    }

    assert run_pair_arb_matrix._metric(result, "profit_factor") == 1.23
    assert run_pair_arb_matrix._metric(result, "return_pct") == 2.5
    assert run_pair_arb_matrix._win_rate(result) == 0.54


def test_pair_arb_matrix_marks_positive_but_unstable_candidate_as_research() -> None:
    result = {
        "oos_aggregate": {
            "return_pct": {"mean": 1.06, "median": 0.0, "min": -5.06},
            "verdict": "fragile",
        },
        "folds_detail": [
            {"return_pct": value}
            for value in (1.2, 0.0, -5.06, -1.7, 10.8, 4.7, -2.7, 2.3, 9.8, 0.3, -3.0, -1.1, -1.5, 2.0, -0.2)
        ],
        "fee_sensitivity": {"verdict": "fee_robust"},
    }

    verdict, evidence = run_pair_arb_matrix._classify(result, trades=49)

    assert verdict == "RESEARCH"
    assert evidence["positive_folds"] == 7
    assert evidence["folds"] == 15


def test_pair_arb_matrix_pass_requires_robust_majority_of_folds() -> None:
    result = {
        "oos_aggregate": {
            "return_pct": {"mean": 1.5, "median": 1.1, "min": -2.0},
            "verdict": "robust",
        },
        "folds_detail": [{"return_pct": value} for value in (2.0, 1.0, 1.5, -2.0, 1.2, 0.8, -0.5)],
        "fee_sensitivity": {"verdict": "fee_robust"},
    }

    verdict, evidence = run_pair_arb_matrix._classify(result, trades=45)

    assert verdict == "PASS"
    assert evidence["positive_folds"] == 5
