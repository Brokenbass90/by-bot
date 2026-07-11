import hashlib
import json

from bot.att1_runtime_contract import build_att1_runtime_contract


def test_runtime_contract_reads_strategy_effective_environment(monkeypatch):
    monkeypatch.setenv("ATT1_ALLOW_LONGS", "0")
    monkeypatch.setenv("ATT1_ALLOW_SHORTS", "1")
    monkeypatch.setenv("ATT1_PIVOT_LEFT", "2")
    monkeypatch.setenv("ATT1_PIVOT_RIGHT", "3")
    monkeypatch.setenv("ATT1_MIN_PIVOTS", "2")
    monkeypatch.setenv("ATT1_MAX_PIVOT_AGE", "16")
    monkeypatch.setenv("ATT1_MIN_R2", "0.55")
    monkeypatch.setenv("ATT1_TOUCH_ATR", "0.50")
    monkeypatch.setenv("ATT1_RSI_SHORT_MIN", "45")
    monkeypatch.setenv("ATT1_CANARY_EXPIRY_UTC", "2026-07-20")

    contract = build_att1_runtime_contract(risk_mult=0.10)
    params = contract["params"]

    assert params["risk_mult"] == 0.10
    assert params["allow_longs"] is False
    assert params["allow_shorts"] is True
    assert params["pivot_left"] == 2
    assert params["pivot_right"] == 3
    assert params["min_pivots"] == 2
    assert params["max_pivot_age"] == 16
    assert params["min_r2"] == 0.55
    assert params["touch_atr"] == 0.50
    assert params["rsi_short_min"] == 45.0
    assert params["canary_expiry_utc"] == "2026-07-20"

    payload = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert contract["sha256"] == hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_runtime_contract_hash_changes_when_entry_gate_changes(monkeypatch):
    monkeypatch.setenv("ATT1_RSI_SHORT_MIN", "45")
    first = build_att1_runtime_contract(risk_mult=0.10)
    monkeypatch.setenv("ATT1_RSI_SHORT_MIN", "50")
    second = build_att1_runtime_contract(risk_mult=0.10)

    assert first["params"]["rsi_short_min"] == 45.0
    assert second["params"]["rsi_short_min"] == 50.0
    assert first["sha256"] != second["sha256"]
