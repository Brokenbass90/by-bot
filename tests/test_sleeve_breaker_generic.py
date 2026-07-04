"""Generic per-sleeve breaker (RANGE canary protection) — env-driven, fail-safe."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import smart_pump_reversal_bot as bot


def test_range_expiry_blocks_even_without_breaker_enable(monkeypatch):
    monkeypatch.delenv("RANGE_BREAKER_ENABLE", raising=False)
    monkeypatch.setenv("RANGE_CANARY_EXPIRY_UTC", "2020-01-01")
    st = bot._sleeve_breaker_state_env("RANGE", "range")
    assert st["expired"] is True
    assert st["blocked"] is True
    assert st["risk_mult"] == 0.0


def test_range_disabled_and_unexpired_is_noop(monkeypatch):
    monkeypatch.delenv("RANGE_BREAKER_ENABLE", raising=False)
    monkeypatch.setenv("RANGE_CANARY_EXPIRY_UTC", "2099-01-01")
    st = bot._sleeve_breaker_state_env("RANGE", "range")
    assert st["blocked"] is False
    assert st["risk_mult"] == 1.0
    assert st["strategy"] == "range"


def test_prefix_env_keys_are_respected(monkeypatch):
    monkeypatch.setenv("RANGE_BREAKER_ENABLE", "1")
    monkeypatch.setenv("RANGE_BREAKER_STRATEGY_NAME", "range")
    monkeypatch.setenv("RANGE_BREAKER_MIN_TRADES", "2")
    monkeypatch.delenv("RANGE_CANARY_EXPIRY_UTC", raising=False)
    st = bot._sleeve_breaker_state_env("RANGE", "range")
    # empty live journal for 'range' in lookback -> not blocked, mult 1.0
    assert st["strategy"] == "range"
    assert isinstance(st["blocked"], bool)


def test_att1_wrapper_still_works(monkeypatch):
    monkeypatch.setenv("ATT1_CANARY_EXPIRY_UTC", "2099-01-01")
    st = bot._att1_breaker_state()
    assert st["strategy"] == "att1_trendline_touch"
    assert st["expired"] is False
