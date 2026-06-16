"""Tests for the funding-carry readiness gate."""

from backtest.funding_carry_gate import evaluate, CarryThresholds
from backtest.funding_carry_gate import evaluate_run_dir


def test_single_window_research_fails_consistency():
    # positive net but only 1 window -> not proven consistent
    r = evaluate(gross_funding_usd=40, fees_usd=12.72, hedge_cost_usd=0,
                 basis_pnl_usd=0, notional_usd=800, days=180,
                 windows=1, positive_windows=1, worst_window_usd=0)
    assert r.net_usd > 0
    assert r.go is False
    assert any("consistency" in f for f in r.failed)


def test_guarded_consistent_bounded_tail_passes():
    r = evaluate(gross_funding_usd=48, fees_usd=13, hedge_cost_usd=6,
                 basis_pnl_usd=-2, notional_usd=800, days=180,
                 windows=6, positive_windows=5, worst_window_usd=-18)
    assert r.go is True
    assert r.failed == []


def test_hedge_cost_can_flip_net_negative():
    r = evaluate(gross_funding_usd=30, fees_usd=13, hedge_cost_usd=25,
                 basis_pnl_usd=0, notional_usd=800, days=180,
                 windows=6, positive_windows=6, worst_window_usd=-5)
    assert r.net_usd < 0
    assert r.go is False


def test_big_tail_blocks_promotion():
    # good net & consistency but a catastrophic worst window -> blocked
    r = evaluate(gross_funding_usd=60, fees_usd=13, hedge_cost_usd=5,
                 basis_pnl_usd=0, notional_usd=800, days=180,
                 windows=6, positive_windows=6, worst_window_usd=-120)  # -15%
    assert r.go is False
    assert any("tail" in f for f in r.failed)


def test_annualized_floor():
    thr = CarryThresholds(min_annual_pct=10.0)
    r = evaluate(gross_funding_usd=20, fees_usd=5, hedge_cost_usd=3,
                 basis_pnl_usd=0, notional_usd=800, days=180,
                 windows=6, positive_windows=6, worst_window_usd=-5, thr=thr)
    # net ~12 over 180d on 800 = ~3% annualized < 10% floor
    assert r.go is False
    assert any("annualized" in f for f in r.failed)


def test_evaluate_run_dir_reads_funding_capture_outputs(tmp_path):
    run_dir = tmp_path / "funding_run"
    run_dir.mkdir()
    (run_dir / "summary.csv").write_text(
        "tag,days,symbols,notional_per_symbol,gross_funding_total_usd,fees_total_usd\n"
        "t,30,A;B,100,4.0,0.6\n",
        encoding="utf-8",
    )
    (run_dir / "monthly_pnl.csv").write_text(
        "month,gross_funding_usd\n"
        "2026-05,1.5\n"
        "2026-06,2.5\n",
        encoding="utf-8",
    )
    (run_dir / "funding_per_symbol.csv").write_text(
        "symbol,net_usd\nA,1\nB,1\n",
        encoding="utf-8",
    )
    r = evaluate_run_dir(run_dir, extra_spread_bps=10, basis_pnl_usd=-0.2)
    assert r.details["notional_usd"] == 200
    assert r.details["windows"] == 2
    assert r.details["positive_windows"] == 2
    assert r.net_usd == 3.0
