"""Tests for alpaca_adaptive_v1 — the regime-gated best-of-breed Alpaca selector."""

from strategies.alpaca_adaptive_v1 import AdaptiveConfig, market_regime_ok, select


def _uptrend(n=260, start=100.0, step=0.4):
    return [start + i * step for i in range(n)]


def _downtrend(n=260, start=200.0, step=0.4):
    return [max(1.0, start - i * step) for i in range(n)]


def test_regime_gate_blocks_longs_in_bear_market():
    # The core value: when SPY is below its 200-SMA, no long picks -> cash.
    bull_index = _uptrend()
    bear_index = _downtrend()
    assert market_regime_ok(bull_index, 200) is True
    assert market_regime_ok(bear_index, 200) is False

    # Even with strong-momentum names available, a bear index => cash.
    universe = {"AAA": _uptrend(), "BBB": _uptrend(start=120, step=0.5)}
    out_bull = select(universe, bull_index)
    out_bear = select(universe, bear_index)
    assert out_bull["regime_ok"] is True and len(out_bull["picks"]) > 0
    assert out_bear["regime_ok"] is False and out_bear["picks"] == []
    assert "cash" in out_bear["reason"]


def test_min_momentum_and_trend_filter_exclude_falling_names():
    idx = _uptrend()
    universe = {"UP": _uptrend(), "DOWN": _downtrend()}  # DOWN below its SMA + neg mom
    out = select(universe, idx)
    syms = [p["symbol"] for p in out["picks"]]
    assert "UP" in syms
    assert "DOWN" not in syms


def test_sector_cap_limits_concentration():
    idx = _uptrend()
    # four tech names, cap = 2 per sector
    universe = {s: _uptrend(start=100 + i, step=0.4 + i * 0.05) for i, s in
                enumerate(["T1", "T2", "T3", "T4"])}
    sectors = {s: "tech" for s in universe}
    cfg = AdaptiveConfig(max_per_sector=2, max_positions=4)
    out = select(universe, idx, sectors=sectors, cfg=cfg)
    assert len(out["picks"]) == 2  # capped by sector


def test_weights_normalized_and_capped():
    idx = _uptrend()
    universe = {s: _uptrend(start=100 + i * 5, step=0.4) for i, s in
                enumerate(["A", "B", "C"])}
    out = select(universe, idx)
    weights = [float(p["weight"]) for p in out["picks"]]
    cap = AdaptiveConfig().max_position_frac
    # Hard cap is a risk limit: each weight <= cap, total invested <= 1 (rest cash).
    assert all(w <= cap + 1e-9 for w in weights)
    assert 0.0 < sum(weights) <= 1.0 + 1e-9
    assert abs(out["cash_frac"] - (1.0 - sum(weights))) < 1e-9


def test_ai_approver_can_veto_a_candidate():
    idx = _uptrend()
    universe = {"GOOD": _uptrend(), "BLOCK": _uptrend(start=130, step=0.6)}

    def approver(symbol, metrics):
        return (symbol != "BLOCK", "ai_news_veto" if symbol == "BLOCK" else "ok")

    out = select(universe, idx, ai_approver=approver)
    syms = [p["symbol"] for p in out["picks"]]
    assert "GOOD" in syms and "BLOCK" not in syms


def test_portfolio_dd_guard_pauses_new_buys():
    idx = _uptrend()
    universe = {"A": _uptrend()}
    out = select(universe, idx, current_dd_pct=20.0)  # > default 15% limit
    assert out["picks"] == []
    assert "dd_guard" in out["reason"]


# ---- "bodrее" extensions: graduated regime + trailing (opt-in, baseline-safe) ----
from strategies.alpaca_adaptive_v1 import (
    regime_exposure, trailing_exit, update_peak, lively_config,
)


def test_regime_exposure_matches_binary_gate_by_default():
    cfg = AdaptiveConfig(regime_index_sma=5)  # soft_regime False (default)
    assert regime_exposure([100, 100, 100, 100, 100], cfg) == 1.0       # px>=sma
    assert regime_exposure([100, 100, 100, 100, 98], cfg) == 0.0        # below -> cash
    assert regime_exposure([100, 100, 100, 100, 90], cfg) == 0.0


def test_soft_regime_gives_partial_exposure_in_borderline_band():
    cfg = AdaptiveConfig(regime_index_sma=5, soft_regime=True, soft_band_pct=3.0, soft_exposure=0.45)
    # px=98, sma=99.6, floor=96.6 -> borderline band -> reduced exposure
    assert regime_exposure([100, 100, 100, 100, 98], cfg) == 0.45
    # px=90 well below floor -> still full cash (deep-bear protection kept)
    assert regime_exposure([100, 100, 100, 100, 90], cfg) == 0.0
    # px>=sma -> full
    assert regime_exposure([100, 100, 100, 100, 101], cfg) == 1.0


def test_select_scales_total_exposure_in_borderline_regime():
    cfg = AdaptiveConfig(regime_index_sma=5, soft_regime=True, soft_band_pct=3.0, soft_exposure=0.4,
                         mom_slow=5, mom_fast=2, vol_period=5, trend_sma=3, max_positions=3)
    idx = [100, 100, 100, 100, 100, 100, 100, 100, 100, 98]  # borderline
    universe = {s: [100 + i * 0.5 for i in range(20)] for s in ("A", "B")}
    out = select(universe, idx, cfg=cfg)
    assert out["regime_ok"] is True and len(out["picks"]) > 0
    assert out["exposure"] == 0.4
    assert "soft_regime_partial" in out["reason"]
    # total invested cannot exceed the soft exposure cap
    assert sum(float(p["weight"]) for p in out["picks"]) <= 0.4 + 1e-9


def test_trailing_exit_arms_after_gain_then_triggers_on_retrace():
    cfg = AdaptiveConfig(use_trailing=True, trail_atr_mult=3.0, trail_activate_pct=4.0)
    # not armed yet: only +2% from entry
    peak = update_peak(100.0, 102.0)
    armed, _ = trailing_exit(100.0, peak, 102.0, atr=1.0, cfg=cfg)
    assert armed is False
    # armed: +10% peak, ATR=1, stop = 110 - 3 = 107; price 106 -> exit
    peak = update_peak(peak, 110.0)
    hit, stop = trailing_exit(100.0, peak, 106.0, atr=1.0, cfg=cfg)
    assert hit is True and abs(stop - 107.0) < 1e-9
    # price still above stop -> hold
    hold, _ = trailing_exit(100.0, peak, 108.0, atr=1.0, cfg=cfg)
    assert hold is False


def test_trailing_disabled_by_default():
    cfg = AdaptiveConfig()  # use_trailing False
    assert trailing_exit(100.0, 120.0, 100.0, atr=1.0, cfg=cfg) == (False, float("nan")) or \
           trailing_exit(100.0, 120.0, 100.0, atr=1.0, cfg=cfg)[0] is False


def test_lively_preset_enables_extensions():
    cfg = lively_config()
    assert cfg.soft_regime is True and cfg.use_trailing is True
    assert cfg.max_positions >= 4
