"""Position panel view — aggregation, risk calc, fault tolerance (offline)."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _view(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_RUNTIME_ROOT", str(tmp_path / "runtime"))
    # re-import with fresh env
    for mod in list(sys.modules):
        if mod.endswith("position_view"):
            del sys.modules[mod]
    from bot.position_view import build_position_view
    return build_position_view


def test_empty_runtime_is_safe(tmp_path, monkeypatch):
    build = _view(tmp_path, monkeypatch)
    v = build()
    assert v["alive"] is False
    assert v["positions"] == []
    assert v["manage"]["enabled"] is False


def test_position_enriched_with_risk_and_events(tmp_path, monkeypatch):
    rt = tmp_path / "runtime"
    rt.mkdir(parents=True)
    (rt / "bot_heartbeat.json").write_text(json.dumps(
        {"trade_on": True, "dry_run": False, "regime": "bull_trend"}))
    (rt / "live_positions.json").write_text(json.dumps({"data": {"positions": [{
        "symbol": "ADAUSDT", "side": "Sell", "entry": 0.189, "qty": 138,
        "exchange_sl": 0.1893, "upnl_usd": 0.76, "strategy": "att1_trendline_touch",
    }]}}))
    now = time.time()
    with (rt / "decision_bus.jsonl").open("w") as f:
        f.write(json.dumps({"ts": now - 100, "symbol": "ADAUSDT", "decision": "enter"}) + "\n")
        f.write(json.dumps({"ts": now - 50, "symbol": "OTHER", "decision": "enter"}) + "\n")

    build = _view(tmp_path, monkeypatch)
    v = build(now_ts=now)
    assert v["alive"] is True and v["regime"] == "bull_trend"
    p = v["positions"][0]
    assert p["sl_present"] is True
    assert abs(p["risk_usd_at_sl"] - abs(0.189 - 0.1893) * 138) < 1e-9
    # events filtered to the open symbol only
    assert len(v["recent_events"]) == 1
    assert v["recent_events"][0]["symbol"] == "ADAUSDT"


def test_missing_sl_flagged(tmp_path, monkeypatch):
    rt = tmp_path / "runtime"
    rt.mkdir(parents=True)
    (rt / "live_positions.json").write_text(json.dumps(
        [{"symbol": "X", "side": "Buy", "entry": 1.0, "qty": 10}]))
    build = _view(tmp_path, monkeypatch)
    p = build()["positions"][0]
    assert p["sl_present"] is False
    assert p["risk_usd_at_sl"] is None


def test_holding_math_short_with_targets(tmp_path, monkeypatch):
    rt = tmp_path / "runtime"
    rt.mkdir(parents=True)
    (rt / "live_positions.json").write_text(json.dumps([{
        "symbol": "ADAUSDT", "side": "Sell", "entry": 0.190, "qty": 100,
        "exchange_sl": 0.194, "upnl_usd": 0.20,           # -> current = 0.188
        "runner_targets": [0.184, 0.178],
    }]))
    build = _view(tmp_path, monkeypatch)
    p = build()["positions"][0]
    assert p["tp_targets"][0] == 0.184                    # ближняя цель первой
    assert abs(p["current_price"] - 0.188) < 1e-9
    # прогресс к TP1: (0.190-0.188)/(0.190-0.184) = 33.3%
    assert abs(p["progress_to_tp1_pct"] - 33.3) < 0.2
    # r_now: risk=0.004*100=0.4$, upnl 0.2 -> 0.5R
    assert abs(p["r_now"] - 0.5) < 1e-6
    exp = {e["target"]: e["approx_usd"] for e in p["expected_at_targets"]}
    assert abs(exp[0.184] - 0.60) < 1e-9 and abs(exp[0.178] - 1.20) < 1e-9
