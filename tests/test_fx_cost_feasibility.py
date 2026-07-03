import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.fx_harness import cost_feasibility


def _bars(n, price, rng):
    """n bars around `price` with true range ~rng."""
    rows = []
    for i in range(n):
        rows.append([i * 3_600_000, price, price + rng / 2, price - rng / 2, price, 0.0])
    return rows


def test_eurusd_m5_scale_is_infeasible():
    # ATR ~ 0.00024 at price 1.14 -> fee_r ~ 1.78R with 0.8*ATR stop
    rows = _bars(300, 1.14, 0.00024)
    out = cost_feasibility(rows, sl_atr=0.8, fee_bps=1.0, slippage_bps=0.5)
    assert out["feasible"] is False
    assert out["fee_r"] > 1.0
    assert "fee_r" in out["reason"]


def test_eurusd_h1_scale_is_feasible_at_wider_stop():
    # ATR ~ 0.00114 at 1.14 -> fee_r ~ 0.3R at 0.8*ATR; pass with sl_atr=1.3
    rows = _bars(300, 1.14, 0.00114)
    out = cost_feasibility(rows, sl_atr=1.3, fee_bps=1.0, slippage_bps=0.5)
    assert out["feasible"] is True
    assert out["fee_r"] < 0.25


def test_xau_h1_is_comfortably_feasible():
    rows = _bars(300, 2400.0, 20.0)
    out = cost_feasibility(rows, sl_atr=0.8)
    assert out["feasible"] is True
    assert out["fee_r"] < 0.1


def test_empty_rows_infeasible():
    out = cost_feasibility([])
    assert out["feasible"] is False
    assert out["reason"] == "no_atr_or_price"
