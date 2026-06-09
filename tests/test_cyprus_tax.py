"""Tests for scripts.cyprus_tax.estimate_set_aside (Opus 2026-06-08)."""
import importlib.util
spec = importlib.util.spec_from_file_location("ct", "scripts/cyprus_tax.py")
ct = importlib.util.module_from_spec(spec); spec.loader.exec_module(ct)


def test_trading_default_12_5():
    r = ct.estimate_set_aside(1000.0, "trading")
    assert r["applied_rate_pct"] == 12.5 and r["suggested_set_aside"] == 125.0
    assert r["keep_after_set_aside"] == 875.0


def test_investment_default_zero():
    r = ct.estimate_set_aside(1000.0, "investment")
    assert r["applied_rate_pct"] == 0.0 and r["suggested_set_aside"] == 0.0


def test_losses_no_tax():
    r = ct.estimate_set_aside(-500.0, "trading")
    assert r["taxable_base"] == 0.0 and r["suggested_set_aside"] == 0.0


def test_custom_rate_and_disclaimer():
    r = ct.estimate_set_aside(200.0, "trading", trading_rate=0.20)
    assert r["suggested_set_aside"] == 40.0
    assert "консультант" in r["disclaimer"]
