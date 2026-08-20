# -*- coding: utf-8 -*-
"""Проверка журнала: позиция появилась, пожила, исчезла — итог записан."""
import pathlib, tempfile
import store
store.DB_PATH = pathlib.Path(tempfile.mkdtemp()) / "t.db"
import journal

conn = store.connect(); journal.ensure_schema(conn)

# заводим сделку как будто из сигнала
mid,_ = store.save_message(conn, "BUY EURUSD", "h1", "SIGNAL", {})
gid = store.create_group(conn, mid, {"symbol":"EURUSD","side":"BUY","entry_min":1.1690,
    "entry_max":1.1694,"stop_loss":1.16786,"take_profits":[1.17386],"chosen_tp":1.17386},
    {"login":5054559379,"type":"demo"}, 1.1694)
journal.remember_planned_risk(conn, gid, 9.22)   # столько собирались рискнуть

class FakeMCP:
    history = None
    def call(self, *a, **k):
        if self.history is None:
            raise RuntimeError("истории нет")
        return {"positions": [self.history]}

POS = {"ticket": 777, "symbol": "EURUSD", "type": "buy", "volume": 0.07,
       "price_open": 1.1694, "price_current": 1.1694, "sl": 1.16786,
       "tp": 1.17386, "profit": 0.0, "swap": 0.0, "group_id": gid}

print("1. позиция открылась")
journal.reconcile(conn, FakeMCP(), [POS])
print("   в снимках:", conn.execute("SELECT COUNT(*) c FROM position_snapshot WHERE closed=0").fetchone()["c"])

print("2. цена дошла до цели, прибыль растёт")
journal.reconcile(conn, FakeMCP(), [{**POS, "price_current": 1.17386, "profit": 25.7}])

print("3. позиция исчезла, но без broker history закрытие не подтверждаем")
mcp = FakeMCP()
closed = journal.reconcile(conn, mcp, [])
assert closed == []
assert journal.metrics(conn)["trades"] == 0

print("4. broker history подтверждает закрытие")
mcp.history = {"ticket": 777, "price_close": 1.17386, "profit": 25.7, "swap": -0.2}
closed = journal.reconcile(conn, mcp, [])
for c in closed:
    print(f"   записано: {c['symbol']} {c['outcome']} {c['profit']:+.2f} · {c['r']}R")

print("\n5. статус сделки в базе:",
      conn.execute("SELECT status,note FROM signal_group WHERE id=?", (gid,)).fetchone()["status"])

m = journal.metrics(conn)
print("\n6. метрики:")
for k in ("trades","win_rate","total_profit","avg_r","total_r","profit_factor","max_drawdown","r_error_band"):
    print(f"   {k:<15} {m.get(k)}")
print("   по символам:", m["by_symbol"])

print("\n7. повторный вызов не должен дублировать:")
journal.reconcile(conn, mcp, [])
print("   сделок в журнале:", journal.metrics(conn)["trades"], "(должно остаться 1)")
