import hashlib
import json
from types import SimpleNamespace

import bot.att1_runtime_contract as runtime_contract
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
    monkeypatch.setenv("ATT1_TREND_GUARD_BARS", "3")
    monkeypatch.setenv("ATT1_MAX_ENTRY_DIST_ATR", "1.25")
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
    assert params["trend_guard_bars"] == 3
    assert params["max_entry_dist_atr"] == 1.25
    assert len(params["strategy_source_sha256"]) == 64
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


def test_runtime_contract_hash_changes_when_source_changes(monkeypatch):
    monkeypatch.setattr(
        runtime_contract,
        "_strategy_source_sha256",
        lambda: "a" * 64,
    )
    first = build_att1_runtime_contract(risk_mult=0.10)
    monkeypatch.setattr(
        runtime_contract,
        "_strategy_source_sha256",
        lambda: "b" * 64,
    )
    second = build_att1_runtime_contract(risk_mult=0.10)

    assert first["params"]["strategy_source_sha256"] == "a" * 64
    assert second["params"]["strategy_source_sha256"] == "b" * 64
    assert first["sha256"] != second["sha256"]


def test_runtime_contract_supports_deployed_legacy_cfg_without_rsi_short_max(monkeypatch):
    current = runtime_contract.AltTrendlineTouchV1Strategy().cfg
    legacy_values = {
        key: value
        for key, value in vars(current).items()
        if key != "rsi_short_max"
    }
    legacy = SimpleNamespace(**legacy_values)
    monkeypatch.setattr(
        runtime_contract,
        "AltTrendlineTouchV1Strategy",
        lambda: SimpleNamespace(cfg=legacy),
    )

    contract = runtime_contract.build_att1_runtime_contract(risk_mult=0.10)

    assert contract["params"]["rsi_short_max"] == 100.0
