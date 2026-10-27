#!/usr/bin/env python3
"""binance_fanding_oi_vpered.py — хук сторожа (27.10.2026, Claude): дневные фандинг и открытый интерес перпов Binance для Фабрики v2
и зрения Brain. Только публичный REST без ключей, только дописывание. С 2026-09-01 (вне запечатанного окна).
  fanding: /fapi/v1/fundingRate → сумма ставок за день UTC; oi: /futures/data/openInterestHist period=1d (биржа отдаёт ~30 последних дней —
  собирать ежедневно, иначе история теряется). Выход data/binance_fanding_oi_vpered/{fanding,oi}/<SYM>.json: [[t_dnya, значение], ...]
  (oi: [t, контрактов, $]). Журнал data/binance_fanding_oi_vpered.jsonl. Не чаще раза в 6 ч."""
import datetime as dt, json, os, sys, time, urllib.error, urllib.request
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]
OUT = LAB / "data" / "binance_fanding_oi_vpered"; ZH = LAB / "data" / "binance_fanding_oi_vpered.jsonl"; SOST = OUT / "sostoyanie.json"
DEN = 86_400_000; START = 1788220800000                     # 2026-09-01
MAKS, PAUZA = 800, 0.2

def _get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "research-d1/1"}), timeout=20) as r: return json.loads(r.read())

def _jl(p): return json.loads(p.read_text()) if p.exists() else []

def _zap(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True); tmp = p.with_suffix(".tmp"); tmp.write_text(json.dumps(rows)); os.replace(tmp, p)

def simvoly(): return sorted(f.stem for f in (LAB / "data" / "binance_d1_vpered" / "klines").glob("*.json"))

def prohod(get=_get, maks=MAKS, pauza=PAUZA):
    now = int(time.time() * 1000); vchera = (now // DEN - 1) * DEN
    s = json.loads(SOST.read_text()) if SOST.exists() else {}
    if s.get("posledniy_prohod_ms") and now - s["posledniy_prohod_ms"] < 6 * 3600_000: return {"status": "rano"}
    zap, dop, osh = 0, 0, []
    for sym in simvoly():
        if zap >= maks: break
        # фандинг
        pf = OUT / "fanding" / f"{sym}.json"; f = _jl(pf); last = f[-1][0] if f else START - DEN
        if last < vchera:
            try:
                rows = get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&startTime={last + DEN}&limit=1000"); zap += 1
                po = {}
                for r in rows:
                    d = int(r["fundingTime"]) // DEN * DEN
                    if d <= last or d > vchera: continue
                    po[d] = po.get(d, 0.0) + float(r["fundingRate"])
                nov = [[d, round(v, 8)] for d, v in sorted(po.items())]
                if nov: _zap(pf, f + nov); dop += len(nov)
            except Exception as e: zap += 1; osh.append(f"f:{sym}:{type(e).__name__}")
            time.sleep(pauza)
        # открытый интерес
        po_ = OUT / "oi" / f"{sym}.json"; o = _jl(po_); last = o[-1][0] if o else START - DEN
        if last < vchera:
            try:
                rows = get(f"https://fapi.binance.com/futures/data/openInterestHist?symbol={sym}&period=1d&limit=30"); zap += 1
                nov = sorted({int(r["timestamp"]) // DEN * DEN: [int(r["timestamp"]) // DEN * DEN, float(r["sumOpenInterest"]), float(r["sumOpenInterestValue"])]
                              for r in rows if last < int(r["timestamp"]) // DEN * DEN <= vchera and int(r["timestamp"]) >= START}.values())
                if nov: _zap(po_, o + nov); dop += len(nov)
            except Exception as e: zap += 1; osh.append(f"oi:{sym}:{type(e).__name__}")
            time.sleep(pauza)
    s["posledniy_prohod_ms"] = now; SOST.parent.mkdir(parents=True, exist_ok=True); SOST.write_text(json.dumps(s))
    z = dict(kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), zaprosov=zap, dopisano=dop, oshibok=len(osh), primery=osh[:5])
    with ZH.open("a") as fh: fh.write(json.dumps(z, ensure_ascii=False) + "\n")
    return z

if __name__ == "__main__":
    print(json.dumps(prohod(), ensure_ascii=False))
