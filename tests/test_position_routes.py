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


def test_exit_state_flags_unprotected_profit_runner(tmp_path, monkeypatch):
    rt = tmp_path / "runtime"
    rt.mkdir(parents=True)
    (rt / "live_positions.json").write_text(json.dumps([{
        "symbol": "ADAUSDT", "side": "Sell", "entry": 0.18913665, "qty": 138,
        "exchange_sl": 0.1893, "exchange_tp": None, "upnl_usd": 1.44,
        "runner": {
            "enabled": False,
            "targets": [],
            "trailing": {"enabled": False, "armed": False},
            "breakeven": {"enabled": False, "armed": False},
        },
    }]))
    build = _view(tmp_path, monkeypatch)
    p = build()["positions"][0]
    assert p["r_now"] is None
    assert p["r_now_raw_current_sl"] is not None
    assert p["exit_state"]["profit_lock_active"] is False
    assert "no_tp_plan_visible" in p["exit_state"]["warnings"]
    assert "profit_not_locked" in p["exit_state"]["warnings"]
    assert "trailing_disabled" in p["exit_state"]["warnings"]


def test_runner_nested_targets_are_visible(tmp_path, monkeypatch):
    rt = tmp_path / "runtime"
    rt.mkdir(parents=True)
    (rt / "live_positions.json").write_text(json.dumps([{
        "symbol": "ADAUSDT", "side": "Sell", "entry": 0.190, "qty": 100,
        "exchange_sl": 0.194, "upnl_usd": 0.20,
        "runner": {
            "enabled": True,
            "targets": [{"price": 0.184, "status": "pending"}, {"target": 0.178}],
            "trailing": {"enabled": True, "armed": False},
            "breakeven": {"enabled": True, "armed": True},
            "time_stop_enabled": True,
            "time_stop_sec": 604800,
        },
    }]))
    build = _view(tmp_path, monkeypatch)
    p = build()["positions"][0]
    assert p["tp_targets"] == [0.184, 0.178]
    assert p["exit_state"]["bot_targets_present"] is True
    assert p["runner_state"]["enabled"] is True
    assert p["runner_state"]["trailing_enabled"] is True
    assert p["runner_state"]["breakeven_armed"] is True


def test_alpaca_positions_tolerant_and_in_view(tmp_path, monkeypatch):
    rt = tmp_path / "runtime"
    (rt / "equities_monthly_v36").mkdir(parents=True)
    (rt / "equities_monthly_v36" / "latest_advisory.json").write_text(json.dumps({
        "report": {
            "open_positions": [
                {"symbol": "KO", "qty": 3, "avg_entry_price": 62.5,
                 "current_price": 63.1, "unrealized_pl": 1.8, "stop_price": 60.0},
                {"ticker": "AMD", "shares": 1, "avg_price": 150.0, "price": 149.0, "pl": -1.0},
            ],
            "monthly_managed_positions": [
                {"symbol": "KO"},  # дубликат — не должен задвоиться
            ],
        }
    }))
    build = _view(tmp_path, monkeypatch)
    v = build()
    syms = [a["symbol"] for a in v["alpaca"]]
    assert syms == ["KO", "AMD"]
    ko = v["alpaca"][0]
    assert ko["stop"] == 60.0 and ko["upnl"] == 1.8
    amd = v["alpaca"][1]
    assert amd["stop"] is None  # нет стопа -> None, панель подсветит


def test_alpaca_positions_prefer_live_account_state_with_stops(tmp_path, monkeypatch):
    rt = tmp_path / "runtime"
    (rt / "alpaca_live_v38").mkdir(parents=True)
    (rt / "equities_monthly_v36").mkdir(parents=True)
    (rt / "equities_monthly_v36" / "latest_advisory.json").write_text(json.dumps({
        "report": {"open_positions": [{"symbol": "OLD", "qty": 1}]}
    }))
    (rt / "alpaca_live_v38" / "account_state.json").write_text(json.dumps({
        "account": {"equity": "495.14"},
        "positions": [
            {"symbol": "SNOW", "qty": "0.5", "market_value": "100.0",
             "avg_entry_price": "190.0", "unrealized_pl": "5.0"},
            {"symbol": "BAC", "qty": "1", "market_value": "60.0",
             "avg_entry_price": "59.0", "unrealized_pl": "1.0"},
        ],
        "open_orders": [
            {"symbol": "SNOW", "side": "sell", "type": "stop", "status": "new", "stop_price": "180.0"},
            {"symbol": "BAC", "side": "sell", "type": "limit", "status": "new", "limit_price": "65.0"},
        ],
    }))
    build = _view(tmp_path, monkeypatch)
    v = build()
    syms = [a["symbol"] for a in v["alpaca"]]
    assert syms == ["SNOW", "BAC"]
    assert v["alpaca"][0]["current"] == 200.0
    assert v["alpaca"][0]["stop"] == 180.0
    assert v["alpaca"][1]["stop"] is None
    assert v["alpaca"][0]["source"] == "alpaca_live_v38_account_state"
