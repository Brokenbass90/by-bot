#!/usr/bin/env python3
"""ETF_PREMIYA вариант спасения (заранее назван в PREREG_ETF_PREMIYA_2026_10_17): те же события, вход — первый часовой бар,
открывшийся не раньше открытия NYSE (09:30 ET) СЛЕДУЮЩЕЙ сессии, удержание 6 баров (до закрытия 16:00 ET).
Календарь сессий — даты из data/akcii_grouped."""
import json, sys, hashlib, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import etf_premiya_izmereniya as M
LAB = M.LAB
dni = sorted(p.stem for p in (LAB / "data/akcii_grouped").glob("20*.json"))
def sled_otkrytie(den):
    nxt = [d for d in dni if d > den][:1]
    if not nxt: return None
    t = dt.datetime.combine(dt.date.fromisoformat(nxt[0]), dt.time(9, 30), M.NY).astimezone(dt.timezone.utc)
    return int(t.timestamp() * 1000)
for t in ("ETHA",):
    det = json.load(open(LAB / f"data/etf_premiya/sobytiya_{t}_v1_detali.json")); out = []
    for e in det:
        o = sled_otkrytie(e["den"])
        if o: out.append(dict(t_ms=o, simvol=e["simvol"], znak=e["znak"]))
    f = LAB / f"data/etf_premiya/sobytiya_{t}_v2_sessiya.json"; f.write_text(json.dumps(out))
    print(t, len(out), hashlib.sha256(f.read_bytes()).hexdigest())
