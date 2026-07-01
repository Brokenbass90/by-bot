"""Tests for bot.exposure_gate — portfolio correlation / exposure guard."""
import random

from bot.exposure_gate import check_exposure, correlation_from_prices, _corr_key, ExposureDecision

CORR = {
    _corr_key("ETHUSDT", "BTCUSDT"): 0.85,
    _corr_key("SOLUSDT", "BTCUSDT"): 0.80,
    _corr_key("SOLUSDT", "ETHUSDT"): 0.82,
}
LONGS = [{"symbol": "BTCUSDT", "side": "long", "risk_pct": 0.5},
         {"symbol": "ETHUSDT", "side": "long", "risk_pct": 0.5}]


def test_bad_candidate():
    d = check_exposure({"symbol": "", "side": "long", "risk_pct": 0.5}, [], CORR)
    assert d.ok is False and d.allow is False


def test_empty_book_allows_full():
    d = check_exposure({"symbol": "BTCUSDT", "side": "long", "risk_pct": 0.5}, [], CORR)
    assert d.allow is True and d.scaled_risk_pct == 0.5


def test_correlated_stack_counts_cluster():
    d = check_exposure({"symbol": "SOLUSDT", "side": "long", "risk_pct": 0.5}, LONGS, CORR,
                       max_cluster_risk_pct=1.5)
    assert set(d.correlated) == {"BTCUSDT", "ETHUSDT"}
    assert d.cluster_risk_pct > 0.5           # includes correlated open risk
    assert d.allow is True                    # 1.31 <= 1.5


def test_over_budget_scales_down():
    d = check_exposure({"symbol": "SOLUSDT", "side": "long", "risk_pct": 0.5}, LONGS, CORR,
                       max_cluster_risk_pct=1.0, allow_scale=True)
    assert d.allow is True
    assert d.scaled_risk_pct < 0.5            # trimmed to fit the cluster budget
    assert d.reason == "scaled_to_cluster_budget"


def test_over_budget_hard_deny_when_no_scale():
    d = check_exposure({"symbol": "SOLUSDT", "side": "long", "risk_pct": 0.5}, LONGS, CORR,
                       max_cluster_risk_pct=1.0, allow_scale=False)
    assert d.allow is False and d.reason == "cluster_budget_exceeded"


def test_opposite_side_hedges_cluster():
    d = check_exposure({"symbol": "SOLUSDT", "side": "short", "risk_pct": 0.5}, LONGS, CORR)
    assert "BTCUSDT" in d.hedges and "ETHUSDT" in d.hedges
    assert d.cluster_risk_pct < 0.5           # hedge reduces net cluster
    assert d.allow is True


def test_same_symbol_is_fully_correlated():
    d = check_exposure({"symbol": "BTCUSDT", "side": "long", "risk_pct": 0.5},
                       [{"symbol": "BTCUSDT", "side": "long", "risk_pct": 1.2}], {},
                       max_cluster_risk_pct=1.5, allow_scale=False)
    assert d.allow is False                   # 0.5 + 1.2 > 1.5, same symbol

def test_correlation_from_prices_signs():
    random.seed(3)
    A, C, D = [100.0], [100.0], [100.0]
    for _ in range(40):
        r = random.uniform(-0.02, 0.02)
        A.append(A[-1] * (1 + r)); C.append(C[-1] * (1 - r))
        D.append(D[-1] * (1 + random.uniform(-0.02, 0.02)))
    c = correlation_from_prices({"A": A, "C": C, "D": D})
    assert c[_corr_key("A", "C")] < -0.9      # anti-correlated
    assert abs(c[_corr_key("A", "D")]) < 0.6  # roughly independent
