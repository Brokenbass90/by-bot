"""Tests for bot.edge_monitor — live edge-decay governor (anti-degradation)."""
from bot.edge_monitor import assess_sleeve, assess_all, _max_drawdown_R, _worst_streak, HealthReport


def test_drawdown_and_streak_helpers():
    assert abs(_max_drawdown_R([1, 1, -1, -1, -1]) - 3.0) < 1e-9
    assert _worst_streak([1, -1, -1, 1, -1, -1, -1]) == 3


def test_healthy_in_line_with_baseline():
    r = [2.5, -1, -1, 2.5, -1, -1, 2.5, -1, 2.5, -1, -1, 2.5, -1, 2.5, -1, -1, 2.5, -1, 2.5, -1]
    rep = assess_sleeve(r, baseline_expectancy_R=0.4, min_trades=20, max_dd_R=8)
    assert rep.status == "healthy"
    assert abs(rep.live_expectancy_R - 0.4) < 0.05


def test_degraded_when_live_far_below_baseline():
    r = [0.3, -0.2] * 10           # exp ~0.05, tiny DD
    rep = assess_sleeve(r, baseline_expectancy_R=0.4, min_trades=20, max_dd_R=6)
    assert rep.status == "degraded"
    assert rep.reason.startswith("edge_decay_ratio")


def test_halt_on_drawdown_breach():
    r = [-1] * 8 + [2.5] * 12
    rep = assess_sleeve(r, baseline_expectancy_R=0.4, max_dd_R=6)
    assert rep.status == "halt" and rep.reason.startswith("drawdown_breach")


def test_halt_on_losing_streak():
    r = [1] * 5 + [-1] * 8 + [1] * 7
    rep = assess_sleeve(r, baseline_expectancy_R=0.4, max_dd_R=20, max_losing_streak=8)
    assert rep.status == "halt" and rep.reason.startswith("losing_streak")


def test_watch_when_insufficient_trades():
    rep = assess_sleeve([2.5, -1, 2.5], baseline_expectancy_R=0.4, min_trades=20)
    assert rep.status == "watch" and rep.reason.startswith("insufficient_trades")


def test_assess_all_from_bus_records():
    from bot.decision_bus import build_decision, attach_outcome
    recs = []
    seq = [2.5, -1, -1, 2.5, -1, -1, 2.5, -1, 2.5, -1, -1, 2.5, -1, 2.5, -1, -1, 2.5, -1, 2.5, -1]
    for i, rm in enumerate(seq):
        r = build_decision(ts=i, symbol="LINK", strategy="spike_fade_v3", side="short", decision="enter")
        attach_outcome(r, filled=True, r_multiple=rm)
        recs.append(r.to_dict())
    recs.append(build_decision(ts=99, symbol="LINK", strategy="spike_fade_v3", side="short", decision="skip").to_dict())
    h = assess_all(recs, baselines={"spike_fade_v3": 0.4}, min_trades=20, max_dd_R=8)
    assert "spike_fade_v3" in h
    assert isinstance(h["spike_fade_v3"], HealthReport)
    assert h["spike_fade_v3"].status == "healthy"
