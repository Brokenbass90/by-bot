from __future__ import annotations

import csv

from scripts.evaluate_crypto_promotion import _annual_gate, _load_monthly_metrics, _monthly_gate


def _candidate(**overrides):
    candidate = {
        "net_pnl": 10.0,
        "profit_factor": 1.4,
        "max_drawdown": 5.0,
        "trades": 120,
        "entry_execution": "next_open",
        "fee_bps_per_side": 6.0,
        "slippage_bps_per_side": 2.0,
    }
    candidate.update(overrides)
    return candidate


def test_annual_gate_rejects_optimistic_execution_or_costs() -> None:
    cfg = {
        "min_profit_factor": 1.2,
        "required_entry_execution": "next_open",
        "min_fee_bps_per_side": 6.0,
        "min_slippage_bps_per_side": 2.0,
    }

    result = _annual_gate(
        _candidate(entry_execution="signal_price", fee_bps_per_side=3.0, slippage_bps_per_side=0.0),
        cfg,
    )

    assert result["passed"] is False
    assert result["reasons"] == [
        "entry_execution_not_approved",
        "fee_assumption_below_min",
        "slippage_assumption_below_min",
    ]


def test_monthly_gate_reads_trade_stream_and_rejects_instability(tmp_path) -> None:
    trades = tmp_path / "trades.csv"
    with trades.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["exit_ts", "pnl"])
        writer.writeheader()
        # Four represented months; three consecutive losses.
        writer.writerows(
            [
                {"exit_ts": 1736899200000, "pnl": 2.0},   # 2025-01
                {"exit_ts": 1739577600000, "pnl": -1.0},  # 2025-02
                {"exit_ts": 1741996800000, "pnl": -1.0},  # 2025-03
                {"exit_ts": 1744675200000, "pnl": -1.0},  # 2025-04
            ]
        )

    monthly = _load_monthly_metrics(trades)
    result = _monthly_gate(
        monthly,
        {"required": True, "min_months": 4, "max_negative_months": 2, "max_negative_streak": 2},
    )

    assert monthly["negative_months"] == 3
    assert monthly["max_negative_streak"] == 3
    assert result["passed"] is False
    assert result["reasons"] == ["negative_months_above_max", "negative_streak_above_max"]


def test_monthly_gate_fails_closed_without_trades_file(tmp_path) -> None:
    monthly = _load_monthly_metrics(tmp_path / "missing.csv")
    result = _monthly_gate(monthly, {"required": True, "min_months": 10})

    assert result["passed"] is False
    assert result["reasons"] == ["monthly_trade_stream_missing", "months_below_min"]
