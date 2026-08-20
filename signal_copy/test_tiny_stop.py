# -*- coding: utf-8 -*-
"""Случай из жизни: рынок подошёл вплотную к стопу, объём взрывается.

Реальная карточка 20 августа 11:03 — рынок 1.16911, стоп 1.16920, до стопа
0.9 пункта. Бот предлагал 0.5 лота (упёрся в потолок). Так быть не должно.
"""
import pathlib, tempfile
import store
store.DB_PATH = pathlib.Path(tempfile.mkdtemp()) / "t.db"
import config
from pipeline import build_cards

SPEC = dict(symbol="EURUSD", point=1e-05, digits=5, contract_size=100000.0,
            currency_profit="USD", currency_base="EUR", volume_min=0.01,
            volume_max=500, volume_step=0.01, tick_size=0.0, tick_value=0.0,
            trade_stops_level=0)

MSG = """✒️SELL EUR/USD

1.16840 - 1.16820

📌Stop loss (SL): 1.16920

• Take profit 1: 1.16765
• Take profit 2: 1.16735
• Take profit 3: 1.16703
• Take profit 4: 1.16600"""

class Fake:
    def __init__(s, bid, ask): s.bid, s.ask = bid, ask
    def account(s):  return dict(login=1, server="MetaQuotes-Demo", type="demo",
                                 margin_mode="hedging", equity=2000.0,
                                 currency="EUR", margin_free=2000.0, read_only=False)
    def terminal(s): return dict(server_connected=True, mcp_trade_allowed=True)
    def symbols(s):  return [dict(SPEC, bid=s.bid, ask=s.ask)]
    def positions(s):return []

CASES = [
    ("рынок 11:03 — вплотную к стопу", 1.16911, 1.16912),
    ("рынок в зоне входа",             1.16825, 1.16827),
    ("рынок на полпути к стопу",       1.16880, 1.16882),
]
for name, bid, ask in CASES:
    conn = store.connect(); conn.execute("DELETE FROM message"); conn.commit()
    c = build_cards(MSG, Fake(bid, ask), conn, use_llm=False)[0]
    print(f"\n{name}  (рынок {bid}/{ask})")
    print(f"  войдём по {c.entry_used} · до стопа "
          f"{abs((c.entry_used or 0)-(c.stop_loss or 0))/1e-5:.0f} п. · "
          f"лот {c.lot} · осталось {c.rr}R · уход {c.drift_r}R")
    print("  " + ("✅ МОЖНО" if c.can_execute else "⛔ ОТКАЗ"))
    for b in c.blockers: print(f"     ⛔ {b}")
