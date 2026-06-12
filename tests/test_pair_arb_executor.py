"""Tests for strategies.pair_arb_executor_v1 (Opus 2026-06-09)."""
from strategies.pair_arb_executor_v1 import (
    plan_entry, plan_exit, pair_pnl, PairExecConfig, PairPosition,
)
from strategies.pair_stat_arb_v1 import PairSignal


def _sig(long_s="BTCUSDT", short_s="ETHUSDT", z=2.5):
    return PairSignal(long_symbol=long_s, short_symbol=short_s, z=z, beta=1.0,
                      half_life=5.0, corr=0.9, reason="entry")


def test_entry_two_equal_notional_legs_opposite_sides():
    cfg = PairExecConfig(leg_frac_of_equity=0.5, max_notional_per_leg=100.0)
    pos, intents = plan_entry(_sig(), equity=200.0, px_long=30000.0, px_short=2000.0, cfg=cfg)
    assert pos is not None and len(intents) == 2
    sides = {i.symbol: i.side for i in intents}
    assert sides["BTCUSDT"] == "Buy" and sides["ETHUSDT"] == "Sell"
    # equal notional per leg (capped at 100)
    assert abs(intents[0].notional - intents[1].notional) < 1e-6
    assert intents[0].notional == 100.0


def test_entry_too_small_rejected():
    cfg = PairExecConfig(leg_frac_of_equity=0.5, min_notional_per_leg=10.0)
    pos, intents = plan_entry(_sig(), equity=5.0, px_long=30000.0, px_short=2000.0, cfg=cfg)
    assert pos is None and intents == []


def test_pnl_positive_on_convergence():
    # long BTC entry 30000, short ETH entry 2000; BTC up, ETH down -> both legs win
    pos, _ = plan_entry(_sig(), 200.0, 30000.0, 2000.0, PairExecConfig(max_notional_per_leg=100.0))
    pnl = pair_pnl(pos, px_long=30300.0, px_short=1980.0)  # +1% long, -1% short
    assert pnl > 0


def test_exit_on_revert():
    pos, _ = plan_entry(_sig(z=2.5), 200.0, 30000.0, 2000.0, PairExecConfig(max_notional_per_leg=100.0))
    out = plan_exit(pos, 30150.0, 1990.0, cur_z=0.3, cur_bar=10, cfg=PairExecConfig(exit_z=0.5))
    assert out is not None
    reason, pnl, closes = out
    assert "reverted" in reason and len(closes) == 2
    assert all(c.reduce_only for c in closes)


def test_exit_on_stop():
    pos, _ = plan_entry(_sig(z=2.5), 200.0, 30000.0, 2000.0)
    out = plan_exit(pos, 29000.0, 2100.0, cur_z=4.0, cur_bar=5, cfg=PairExecConfig(stop_z=3.5))
    assert out is not None and "stop" in out[0]


def test_exit_on_max_hold():
    pos, _ = plan_entry(_sig(), 200.0, 30000.0, 2000.0)
    pos.opened_bar = 0
    out = plan_exit(pos, 30010.0, 1999.0, cur_z=1.5, cur_bar=100, cfg=PairExecConfig(max_hold_bars=96))
    assert out is not None and out[0] == "max_hold"


def test_no_exit_when_in_band():
    pos, _ = plan_entry(_sig(), 200.0, 30000.0, 2000.0)
    out = plan_exit(pos, 30010.0, 1999.0, cur_z=1.8, cur_bar=10,
                    cfg=PairExecConfig(exit_z=0.5, stop_z=3.5, max_hold_bars=96))
    assert out is None
