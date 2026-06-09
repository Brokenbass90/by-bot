"""Tests for backtest.lab (Opus 2026-06-08)."""
import math
from backtest.lab import (
    Scenario, RunResult, report_from_result, run_scenarios, compare, ablation,
)


def _res(pnls, name="s", rets=None, fees=0.0):
    trades = []
    for i, p in enumerate(pnls):
        t = {"pnl": p, "fees": fees}
        if rets is not None:
            t["return_pct"] = rets[i]
        trades.append(t)
    return RunResult(trades=trades, meta={"name": name})


def test_report_basic_metrics():
    r = report_from_result(_res([10, -5, 8, -3], rets=[0.1, -0.05, 0.08, -0.03]))
    assert r["trades"] == 4
    assert r["net_pnl"] == 10.0
    assert r["win_rate"] == 50.0
    assert r["profit_factor"] == round(18 / 8, 4)
    assert r["expectancy"] == 2.5
    assert r["sortino"] is not None
    assert r["geo_mean_return"] is not None


def test_report_all_wins_pf_inf():
    r = report_from_result(_res([5, 7, 3]))
    assert r["profit_factor"] == "inf"
    assert r["max_drawdown_pct"] == 0.0


def test_report_drawdown():
    # equity: 100 ->110 ->90 -> peak 110, trough 90 => 18.18% dd
    r = report_from_result(_res([10, -20, 5]))
    assert abs(r["max_drawdown_pct"] - 18.18) < 0.1


def test_compare_ranks_by_pf():
    reports = {
        "A": report_from_result(_res([10, -5], name="A")),       # pf 2.0
        "B": report_from_result(_res([10, -1], name="B")),       # pf 10.0
        "C": report_from_result(_res([1, -10], name="C")),       # pf 0.1
    }
    ranked = compare(reports, key="profit_factor")
    assert ranked[0]["scenario"] == "B"
    assert ranked[-1]["scenario"] == "C"


def test_ablation_marginal_contribution():
    reports = {
        "FULL": report_from_result(_res([30], name="FULL")),        # net 30
        "minus_breakdown": report_from_result(_res([20], name="m")), # net 20 -> breakdown adds 10
        "minus_att1": report_from_result(_res([35], name="m")),      # net 35 -> att1 COSTS 5 (hurts)
    }
    a = ablation(reports, metric="net_pnl")
    assert a["full"] == 30.0
    assert a["marginal_contribution"]["breakdown"] == 10.0   # helps
    assert a["marginal_contribution"]["att1"] == -5.0        # hurts (removing it improved)


def test_run_scenarios_with_stub_runner():
    def stub(sc: Scenario) -> RunResult:
        # deterministic fake: more strategies -> more (fake) pnl
        return RunResult(trades=[{"pnl": 5.0 * len(sc.strategies)}], meta={"name": sc.name})
    scs = [Scenario(name="one", strategies=["a"]), Scenario(name="two", strategies=["a", "b"])]
    reps = run_scenarios(scs, stub)
    assert reps["one"]["net_pnl"] == 5.0 and reps["two"]["net_pnl"] == 10.0
