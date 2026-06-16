"""Tests for liquidation-sweep research engine."""

from backtest.liquidation_sweep_research import (
    detect_clusters, measure_bounce, hypothesis_test,
)


def test_cluster_detection_and_dominance():
    ev = [
        {"ts_ms": 0, "side": "long", "usd": 800_000},
        {"ts_ms": 60_000, "side": "long", "usd": 400_000},
        {"ts_ms": 120_000, "side": "short", "usd": 50_000},
    ]
    cl = detect_clusters(ev, window_ms=5 * 60_000, min_usd=1_000_000, dominance=0.7)
    assert len(cl) == 1
    assert cl[0]["side"] == "long"            # longs liquidated
    assert cl[0]["reversal_side"] == "long"   # expect UP reversal -> enter long
    assert cl[0]["usd"] == 1_250_000


def test_below_min_usd_no_cluster():
    ev = [{"ts_ms": 0, "side": "long", "usd": 100_000}]
    assert detect_clusters(ev, min_usd=1_000_000) == []


def test_mixed_side_fails_dominance():
    ev = [{"ts_ms": 0, "side": "long", "usd": 600_000},
          {"ts_ms": 1000, "side": "short", "usd": 600_000}]
    assert detect_clusters(ev, min_usd=1_000_000, dominance=0.7) == []


def test_bounce_win_for_long_reversal():
    # long-liq cluster at t=0, price=100; then bounces up to target 0.4%
    cluster = {"ts_ms": 0, "side": "long", "reversal_side": "long", "usd": 2e6}
    bars = [(0, 100.0, 100.0, 100.0), (60_000, 100.5, 99.9, 100.4)]
    r = measure_bounce(cluster, bars, target_pct=0.4, stop_pct=0.4, fee_bps=0)
    assert r == 1.0   # target hit, 1:1 RR, no fees


def test_bounce_loss_when_continues_down():
    cluster = {"ts_ms": 0, "side": "long", "reversal_side": "long", "usd": 2e6}
    bars = [(0, 100.0, 100.0, 100.0), (60_000, 100.1, 99.5, 99.6)]  # hits stop
    r = measure_bounce(cluster, bars, target_pct=0.4, stop_pct=0.4, fee_bps=0)
    assert r == -1.0


def test_hypothesis_test_verdict_shape():
    ev = [{"ts_ms": 0, "side": "long", "usd": 2e6}]
    bars = [(0, 100, 100, 100), (60_000, 100.5, 99.9, 100.4)]
    res = hypothesis_test(ev, bars, target_pct=0.4, stop_pct=0.4, fee_bps=0)
    assert res["trades"] == 1
    assert "verdict" in res
