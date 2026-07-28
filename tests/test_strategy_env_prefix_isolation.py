from strategies.alt_slope_break_v1 import AltSlopeBreakV1Strategy
from strategies.alt_support_bounce_v1 import AltSupportBounceV1Strategy


def test_canonical_prefixes_isolate_slope_break_from_support_bounce(monkeypatch):
    monkeypatch.setenv("ASB1_SL_ATR_MULT", "9.0")
    monkeypatch.setenv("ASB1_ALLOW_LONGS", "0")
    monkeypatch.setenv("ASLB1_SL_ATR_MULT", "1.25")
    monkeypatch.setenv("ASLB1_ALLOW_LONGS", "0")
    monkeypatch.setenv("BOUNCE1_SL_ATR_MULT", "1.60")
    monkeypatch.setenv("BOUNCE1_ALLOW_LONGS", "1")

    slope = AltSlopeBreakV1Strategy()
    bounce = AltSupportBounceV1Strategy()

    assert slope.cfg.sl_atr_mult == 1.25
    assert slope.cfg.allow_longs is False
    assert bounce.cfg.sl_atr_mult == 1.60
    assert bounce.cfg.allow_longs is True


def test_legacy_asb1_prefix_remains_a_fallback(monkeypatch):
    monkeypatch.setenv("ASB1_SL_ATR_MULT", "1.35")
    monkeypatch.setenv("ASB1_ALLOW_SHORTS", "1")

    slope = AltSlopeBreakV1Strategy()
    bounce = AltSupportBounceV1Strategy()

    assert slope.cfg.sl_atr_mult == 1.35
    assert slope.cfg.allow_shorts is True
    assert bounce.cfg.sl_atr_mult == 1.35
    assert bounce.cfg.allow_shorts is True


def test_canonical_symbol_allowlists_are_independent(monkeypatch):
    monkeypatch.setenv("ASB1_SYMBOL_ALLOWLIST", "BTCUSDT")
    monkeypatch.setenv("ASLB1_SYMBOL_ALLOWLIST", "ETHUSDT")
    monkeypatch.setenv("BOUNCE1_SYMBOL_ALLOWLIST", "SOLUSDT")

    slope = AltSlopeBreakV1Strategy()
    bounce = AltSupportBounceV1Strategy()

    assert slope._allow == {"ETHUSDT"}
    assert bounce._allow == {"SOLUSDT"}
