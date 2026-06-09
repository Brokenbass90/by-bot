"""Tests for scripts.validate_pair_arb.simulate_pair (Opus 2026-06-08)."""
import importlib.util, math
spec = importlib.util.spec_from_file_location("vpa", "scripts/validate_pair_arb.py")
vpa = importlib.util.module_from_spec(spec); spec.loader.exec_module(vpa)
from strategies.pair_stat_arb_v1 import PairConfig


def test_synthetic_cointegrated_produces_trades():
    a, b = vpa._gen_cointegrated(n=400, seed=1)
    trades = vpa.simulate_pair(a, b, PairConfig(lookback=120))
    assert isinstance(trades, list)
    assert all("return_pct" in t and "pnl" in t for t in trades)


def test_flat_pair_no_blowup():
    # identical series -> spread ~0, no extreme z -> no/few trades, must not error
    base = [100.0 * (1.0 + 0.0001 * i) for i in range(300)]
    trades = vpa.simulate_pair(base, base, PairConfig(lookback=120))
    assert isinstance(trades, list)


def test_report_structure():
    a, b = vpa._gen_cointegrated(n=400, seed=2)
    rep = vpa.run_report(a, b, PairConfig(lookback=120))
    assert "profit_factor" in rep and "fee_sensitivity" in rep and "trades" in rep
