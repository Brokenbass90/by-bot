import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot import att1_live_wiring as w


class TrStub:
    strategy = "att1_trendline_touch"
    side = "Sell"
    qty = 100.0
    avg = 1.0
    entry_price = 1.0
    sl_price = 1.02   # risk_usd = 100*0.02 = 2.0
    att1_bus_id = "test_bus_id"


def _env(monkeypatch, tmp_path, bus=True, edge=False):
    monkeypatch.setenv("ATT1_DECISION_BUS_ENABLE", "1" if bus else "0")
    monkeypatch.setenv("ATT1_EDGE_MONITOR_ENABLE", "1" if edge else "0")
    monkeypatch.setenv("DECISION_BUS_PATH", str(tmp_path / "bus.jsonl"))
    monkeypatch.setenv("ATT1_EDGE_HEALTH_PATH", str(tmp_path / "health.json"))


def _read_bus(tmp_path):
    p = tmp_path / "bus.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def test_disabled_writes_nothing(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, bus=False)
    assert w.record_entry(symbol="BTCUSDT", side="short", entry=1.0, sl=1.02, tp=0.96,
                          breaker_mult=1.0, effective_risk_mult=0.1, stop_pct=2.0,
                          minqty_fallback=False, notional_usd=10.0, qty=10.0) == ""
    w.record_skip("BTCUSDT", "short", "skip_breaker")
    w.record_outcome(TrStub(), "BTCUSDT", pnl=-2.0)
    assert _read_bus(tmp_path) == []


def test_entry_skip_outcome_roundtrip(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, bus=True)
    bus_id = w.record_entry(symbol="ADAUSDT", side="short", entry=1.0, sl=1.02, tp=0.96,
                            breaker_mult=0.5, effective_risk_mult=0.05, stop_pct=2.0,
                            minqty_fallback=True, notional_usd=25.0, qty=25.0)
    assert bus_id
    w.record_skip("ADAUSDT", "short", "skip_breaker", breaker_reason="dd")
    tr = TrStub()
    tr.att1_bus_id = bus_id
    w.record_outcome(tr, "ADAUSDT", pnl=-2.0, exit_reason="SL")

    recs = _read_bus(tmp_path)
    assert [r["decision"] for r in recs] == ["enter", "skip", "outcome"]
    enter = recs[0]
    assert enter["context"]["minqty_fallback"] is True
    assert enter["context"]["effective_risk_mult"] == 0.05
    assert enter["plan"]["entry"] == 1.0 and enter["plan"]["stop"] == 1.02
    out = recs[2]
    assert out["context"]["bus_id"] == bus_id
    # r from ACTUAL risk: pnl -2.0 / risk 2.0 = -1R
    assert abs(out["outcome"]["r_multiple"] - (-1.0)) < 1e-9


def test_outcome_ignores_foreign_strategy(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, bus=True)
    tr = TrStub()
    tr.strategy = "inplay_breakout"
    w.record_outcome(tr, "DOGEUSDT", pnl=1.0)
    assert _read_bus(tmp_path) == []


def test_never_raises_on_bad_path(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, bus=True)
    monkeypatch.setenv("DECISION_BUS_PATH", "/dev/null/impossible/bus.jsonl")
    # must not raise — order path safety
    w.record_skip("BTCUSDT", "short", "skip_breaker")
    assert w.record_entry(symbol="BTCUSDT", side="short", entry=1.0, sl=1.02, tp=None,
                          breaker_mult=1.0, effective_risk_mult=0.1, stop_pct=2.0,
                          minqty_fallback=False, notional_usd=10.0, qty=10.0) == ""


def _mk_db(tmp_path, r_list, name="trades.db"):
    db = tmp_path / name
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE trade_events (ts INT, event TEXT, strategy TEXT, "
                    "qty REAL, entry_price REAL, sl_price REAL, pnl REAL)")
        now = int(time.time())
        for i, r in enumerate(r_list):
            # qty=100, entry=1.0, sl=1.02 -> risk 2.0; pnl = r*2.0
            con.execute("INSERT INTO trade_events VALUES (?,?,?,?,?,?,?)",
                        (now - 1000 + i, "CLOSE", "att1_trendline_touch", 100.0, 1.0, 1.02, r * 2.0))
    return str(db)


def test_edge_check_watch_then_halt(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, bus=False, edge=True)
    db = _mk_db(tmp_path, [1.5, -1.0, -1.0])  # n=3 < 20 -> watch
    d = w.edge_check(db)
    assert d["status"] == "watch" and d["n"] == 3

    alerts = []
    db2 = _mk_db(tmp_path, [-1.0] * 8, name="trades2.db")  # losing streak 8 -> halt
    d2 = w.edge_check(db2, notify=alerts.append)
    assert d2["status"] == "halt"
    assert alerts and "watch -> halt" in alerts[0]
    health = json.loads((tmp_path / "health.json").read_text())
    assert health["status"] == "halt"


def test_maybe_edge_check_disabled_and_ratelimit(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, bus=False, edge=False)
    assert w.maybe_edge_check(_mk_db(tmp_path, [1.0], name="t0.db")) is None
    _env(monkeypatch, tmp_path, bus=False, edge=True)
    w._last_edge_check_ts = 0.0
    db = _mk_db(tmp_path, [1.0, -1.0], name="t1.db")
    first = w.maybe_edge_check(db)
    assert first is not None
    assert w.maybe_edge_check(db) is None  # rate-limited
