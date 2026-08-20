# -*- coding: utf-8 -*-
"""Защита от протухших сигналов. Проверяем на реальном случае из чата."""
import json, pathlib, tempfile
import store
store.DB_PATH = pathlib.Path(tempfile.mkdtemp()) / "t.db"
import config
from pipeline import build_cards

BASE = dict(symbol="EURUSD", description="Euro vs US Dollar", point=1e-05, digits=5,
            contract_size=100000.0, currency_profit="USD", currency_base="EUR",
            volume_min=0.01, volume_max=500, volume_step=0.01,
            tick_size=0.0, tick_value=0.0, trade_stops_level=0)

MSG = """✒️SELL EUR/USD

1.16840 - 1.16820

📌Stop loss (SL): 1.16920

• Take profit 1: 1.16765
• Take profit 2: 1.16735
• Take profit 3: 1.16703
• Take profit 4: 1.16600"""

class Fake:
    def __init__(self, bid, ask): self.bid, self.ask = bid, ask
    def account(self):  return dict(login=1, server="MetaQuotes-Demo", type="demo",
                                    margin_mode="hedging", equity=2000.0,
                                    currency="EUR", margin_free=2000.0, read_only=False)
    def terminal(self): return dict(server_connected=True, mcp_trade_allowed=True)
    def symbols(self):  return [dict(BASE, bid=self.bid, ask=self.ask)]
    def positions(self):return []

CASES = [
    ("рынок В зоне входа — норма",         1.16825, 1.16827),
    ("рынок чуть ниже зоны (нам лучше)",   1.16800, 1.16802),
    ("рынок 1.16619, как было ночью",      1.16619, 1.16621),
    ("рынок уехал вверх, за стоп",         1.16950, 1.16952),
    ("рынок почти у цели TP4",             1.16610, 1.16612),
]

for name, bid, ask in CASES:
    conn = store.connect()
    conn.execute("DELETE FROM message")   # чтобы дедуп не мешал прогону
    conn.commit()
    c = build_cards(MSG, Fake(bid, ask), conn, use_llm=False)[0]
    verdict = "✅ МОЖНО" if c.can_execute else "⛔ ОТКАЗ"
    print(f"\n{name}")
    print(f"  рынок {bid}/{ask} · войдём по {c.entry_used} · лот {c.lot} · "
          f"осталось {c.rr}R · уход от зоны {c.drift_r}R")
    print(f"  {verdict}")
    for b in c.blockers: print(f"     ⛔ {b}")
    for w in c.warnings: print(f"     ⚠  {w}")
