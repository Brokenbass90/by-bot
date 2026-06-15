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
