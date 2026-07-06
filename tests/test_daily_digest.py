"""Daily digest — composition, 24h aggregation, fault tolerance."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.daily_digest import build_digest, compose_from_runtime

NOW = 1_800_000_000.0


def _bus(ts, decision, pnl=None, r=None):
    rec = {"ts": ts, "symbol": "ADAUSDT", "strategy": "att1_trendline_touch",
           "side": "short", "decision": decision, "context": {}, "outcome": {}}
    if decision == "outcome":
        rec["outcome"] = {"filled": True, "pnl": pnl, "r_multiple": r, "exit_reason": "TP"}
    return rec


def test_full_digest_has_all_sections():
    msg = build_digest(
        heartbeat={"dry_run": False, "trade_on": True, "regime": "bull_trend"},
        positions=[{"symbol": "ADAUSDT", "side": "Sell", "upnl": 0.76, "sl": 0.1936}],
        bus_records=[_bus(NOW - 100, "enter"),
                     _bus(NOW - 50, "outcome", pnl=0.28, r=0.6),
                     _bus(NOW - 40, "outcome", pnl=-0.45, r=-1.0)],
        health={"status": "watch", "n": 3, "live_expectancy_R": 0.1},
        research=[{"name": "inplay_maker", "verdict": "PASS", "note": "PF 1.86 stress"},
                  {"name": "hzbo_long", "verdict": "FAIL"}],
        pending_owner=["OK на shadow inplay"],
        now_ts=NOW,
    )
    assert "ЖИВ, торгует" in msg and "bull_trend" in msg
    assert "ADAUSDT Sell" in msg and "SL 0.1936" in msg
    assert "закрыто 2 (побед 1)" in msg and "-0.17$" in msg and "-0.40R" in msg
    assert "🟡 watch" in msg
    assert "✅ inplay_maker" in msg and "❌ hzbo_long" in msg
    assert "OK на shadow inplay" in msg
    assert len(msg) < 3900


def test_position_without_sl_is_flagged():
    msg = build_digest(heartbeat=None, positions=[{"symbol": "X", "side": "Buy", "upnl": 1.0}],
                       bus_records=[], health=None, now_ts=NOW)
    assert "SL: НЕТ (!)" in msg
    assert "heartbeat недоступен" in msg


def test_quiet_day_message():
    msg = build_digest(heartbeat={"dry_run": False, "trade_on": True, "regime": "range"},
                       positions=[], bus_records=[], health=None, now_ts=NOW)
    assert "Открытых позиций нет" in msg
    assert "закрытых нет" in msg
    assert "Решений от тебя сегодня не требуется" in msg


def test_compose_from_runtime_tolerates_missing_and_reads_bus(tmp_path):
    # empty root: no runtime dir at all -> still a message
    msg = compose_from_runtime(tmp_path, now_ts=NOW)
    assert "СВОДКА ДНЯ" in msg and "heartbeat недоступен" in msg

    # partial runtime: bus with one fresh and one stale record, broken health file
    rt = tmp_path / "runtime"
    rt.mkdir()
    (rt / "bot_heartbeat.json").write_text(json.dumps({"dry_run": False, "trade_on": True, "regime": "bull"}))
    with (rt / "decision_bus.jsonl").open("w") as f:
        f.write(json.dumps(_bus(NOW - 3600, "outcome", pnl=1.0, r=2.0)) + "\n")
        f.write(json.dumps(_bus(NOW - 200_000, "outcome", pnl=-9.0, r=-9.0)) + "\n")  # stale >24h
        f.write("НЕ JSON\n")
    (rt / "att1_edge_health.json").write_text("{broken")
    msg2 = compose_from_runtime(tmp_path, now_ts=NOW)
    assert "закрыто 1" in msg2 and "+1.00$" in msg2       # stale record excluded
    assert "ЖИВ" in msg2


def test_compose_from_runtime_reads_live_positions_data_wrapper(tmp_path):
    rt = tmp_path / "runtime"
    rt.mkdir()
    (rt / "bot_heartbeat.json").write_text(json.dumps({"dry_run": False, "trade_on": True, "regime": "bull"}))
    (rt / "live_positions.json").write_text(json.dumps({
        "data": {
            "positions": [{
                "symbol": "ADAUSDT",
                "side": "Sell",
                "upnl_usd": 0.6675,
                "exchange_sl": 0.1893,
            }]
        }
    }))
    msg = compose_from_runtime(tmp_path, now_ts=NOW)
    assert "ADAUSDT Sell" in msg
    assert "uPnL +0.67$" in msg
    assert "SL 0.1893" in msg
