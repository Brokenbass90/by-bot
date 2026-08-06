from __future__ import annotations

from strategies.alt_squeeze_breakout_v1 import AltSqueezeBreakoutV1


def test_squeeze_research_controls_keep_legacy_defaults(monkeypatch):
    monkeypatch.delenv("SQB1_SQUEEZE_CHECK_OFFSET", raising=False)
    monkeypatch.delenv("SQB1_SYMBOL_ALLOWLIST", raising=False)

    strategy = AltSqueezeBreakoutV1()

    assert strategy.squeeze_check_offset == 0
    assert "BTCUSDT" in strategy.params["SYMBOL_ALLOWLIST"]


def test_squeeze_research_controls_are_read_from_environment(monkeypatch):
    monkeypatch.setenv("SQB1_SQUEEZE_CHECK_OFFSET", "1")
    monkeypatch.setenv("SQB1_SYMBOL_ALLOWLIST", "WIFUSDT,SOLUSDT")
    monkeypatch.setenv("SQB1_BB_PERIOD", "34")

    strategy = AltSqueezeBreakoutV1()

    assert strategy.squeeze_check_offset == 1
    assert strategy.params["SYMBOL_ALLOWLIST"] == "WIFUSDT,SOLUSDT"
    assert int(strategy.params["BB_PERIOD"]) == 34
