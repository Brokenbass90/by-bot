from types import SimpleNamespace

import pytest

from strategies.inplay_breakout import InPlayBreakoutWrapper
from strategies.signals import TradeSignal


def test_breakout_limit_entry_rebases_runner_targets(monkeypatch):
    monkeypatch.setenv("BREAKOUT_USE_LIMIT_ENTRY", "1")
    monkeypatch.setenv("BREAKOUT_LIMIT_ENTRY_OFFSET_ATR", "0.05")
    monkeypatch.setenv("BREAKOUT_LIMIT_ENTRY_VALIDITY_BARS", "5")

    wrapper = InPlayBreakoutWrapper()
    wrapper.impl = SimpleNamespace(_level=100.0, _atr=2.0)
    sig = TradeSignal(
        strategy="inplay_breakout",
        symbol="TESTUSDT",
        side="long",
        entry=102.0,
        sl=98.0,
        tp=110.0,
        tps=[105.0, 110.0],
        tp_fracs=[0.5, 0.5],
    )

    out = wrapper._apply_limit_entry(sig, partial_rs=[1.5, 3.0])

    assert out is not None
    assert out.entry == pytest.approx(100.1)
    assert out.tps == pytest.approx([103.25, 106.4])
    assert out.tp == pytest.approx(106.4)
    assert out.entry_order_type == "limit"
    assert out.limit_validity_bars == 5
    assert "limit_entry" in out.reason


def test_breakout_limit_entry_short(monkeypatch):
    monkeypatch.setenv("BREAKOUT_USE_LIMIT_ENTRY", "1")
    monkeypatch.setenv("BREAKOUT_LIMIT_ENTRY_OFFSET_ATR", "0.10")

    wrapper = InPlayBreakoutWrapper()
    wrapper.impl = SimpleNamespace(_level=100.0, _atr=2.0)
    sig = TradeSignal(
        strategy="inplay_breakout",
        symbol="TESTUSDT",
        side="short",
        entry=98.0,
        sl=102.0,
        tp=92.0,
    )

    out = wrapper._apply_limit_entry(sig, fixed_rr=2.0)

    assert out is not None
    assert out.entry == pytest.approx(99.8)
    assert out.tp == pytest.approx(95.4)
    assert out.entry_order_type == "limit"
    assert out.limit_validity_bars == 3
