"""Safety tests for the server snapshot exporter — secrets must NEVER leak."""

import json

import scripts.export_server_snapshot as exporter
from scripts.export_server_snapshot import redact, safe_env, _is_secret_key


def test_redact_masks_secret_keys_recursively():
    payload = {
        "BYBIT_ACCOUNTS_JSON": [{"key": "abc", "secret": "xyz"}],
        "tg_token": "12345:AAAA",
        "api_key": "sk-live",
        "open_trades": 3,
        "nested": {"webhook_url": "https://x", "regime": "bear_chop"},
    }
    out = redact(payload)
    assert out["BYBIT_ACCOUNTS_JSON"] == "***REDACTED***"
    assert out["tg_token"] == "***REDACTED***"
    assert out["api_key"] == "***REDACTED***"
    assert out["open_trades"] == 3                       # non-secret kept
    assert out["nested"]["webhook_url"] == "***REDACTED***"
    assert out["nested"]["regime"] == "bear_chop"        # non-secret kept


def test_redact_preserves_strategy_catalog_names_but_masks_real_secrets():
    payload = {
        "strategy_catalog": {
            "active_keys": ["flat", "ivb1"],
            "families": [{"key": "flat", "api_key": "LEAK"}],
        }
    }
    out = redact(payload)
    assert out["strategy_catalog"]["active_keys"] == ["flat", "ivb1"]
    assert out["strategy_catalog"]["families"][0]["key"] == "flat"
    assert out["strategy_catalog"]["families"][0]["api_key"] == "***REDACTED***"


def test_secret_key_detector():
    for k in ("BYBIT_KEY", "API_SECRET", "TG_TOKEN", "withdraw_password", "hmac_sig"):
        assert _is_secret_key(k) is True
    for k in ("ENABLE_ATT1_TRADING", "ASB1_RISK_MULT", "regime", "open_trades"):
        assert _is_secret_key(k) is False


def test_safe_env_excludes_secrets_includes_config(monkeypatch):
    monkeypatch.setenv("BYBIT_ACCOUNTS_JSON", '[{"key":"LEAK","secret":"LEAK"}]')
    monkeypatch.setenv("TG_TOKEN", "LEAK")
    monkeypatch.setenv("ENABLE_ATT1_TRADING", "1")
    monkeypatch.setenv("ASB1_RISK_MULT", "1.0")
    monkeypatch.setenv("NO_ENTRY_HOURS_UTC", "0,1,2")
    env = safe_env()
    blob = str(env)
    assert "LEAK" not in blob                       # no secret value anywhere
    assert "BYBIT_ACCOUNTS_JSON" not in env
    assert "TG_TOKEN" not in env
    assert env.get("ENABLE_ATT1_TRADING") == "1"     # safe config present
    assert env.get("ASB1_RISK_MULT") == "1.0"
    assert env.get("NO_ENTRY_HOURS_UTC") == "0,1,2"


def test_build_snapshot_prefers_live_runtime_paths(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    (runtime / "regime").mkdir(parents=True)
    (runtime / "bot_heartbeat.json").write_text(json.dumps({"open_trades": 0, "trade_on": True}))
    (runtime / "regime" / "orchestrator_state.json").write_text(json.dumps({"regime": "bull_trend"}))
    (runtime / "live_positions.json").write_text(json.dumps({"count": 0, "positions": []}))
    (runtime / "arb_roi_estimate.json").write_text(json.dumps({"status": "ready"}))
    (runtime / "live_trade_events.jsonl").write_text(
        json.dumps({"event": "close", "strategy": "flat", "pnl": "1.25"}) + "\n"
    )

    monkeypatch.setattr(exporter, "ROOT", tmp_path)

    snap = exporter.build_snapshot()
    assert snap["heartbeat"]["open_trades"] == 0
    assert snap["regime"]["regime"] == "bull_trend"
    assert snap["live_positions"]["count"] == 0
    assert snap["pnl_by_sleeve"]["flat"]["pnl"] == 1.25
