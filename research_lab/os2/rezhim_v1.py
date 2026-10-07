#!/usr/bin/env python3
"""REZHIM_V1 — замороженное определение режима Trading OS v2 (выбран по B2_KRITERII_REZHIMA.md, 07.10.2026).
= bot/regime_orchestrator.compute_regime с параметрами по умолчанию (4h MACD 12/26/9, ≥3 бара; EMA20/50; ATR-chop 2%),
по последним 200 ЗАКРЫТЫМ 4h-барам BTCUSDT. Состояния: BULL_TREND / BEAR_TREND / NEUTRAL. Ничего не подбиралось.
Замок: os2/REZHIM_V1_ZAMOK.json (sha256 кода, параметров и меток истории < 2025-10-01).
    metki(ts_h1, ohlcv_h1) -> список состояний на каждый час (состояние, известное к концу часа)."""
import hashlib, json, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; ROOT = LAB.parent
sys.path.insert(0, str(ROOT))
from bot.regime_orchestrator import compute_regime
H = 3600000; H4 = 4 * H; OKNO = 200; MIN_BAROV = 60
PARAMS = dict(macd_fast=12, macd_slow=26, macd_signal=9, ema_fast_period=20, ema_slow_period=50,
              bear_consec=3, bull_consec=3, atr_chop_pct=0.02, okno_4h=OKNO, min_barov_4h=MIN_BAROV, simvol="BTCUSDT")
SOSTOYANIYA = ("BULL_TREND", "BEAR_TREND", "NEUTRAL")

def agg4h(ts, o):
    rows, cur = [], None
    for t, (op, hi, lo, cl, v) in zip(ts, o):
        b = int(t // H4 * H4)
        if cur is None or cur[0] != b:
            if cur: rows.append(cur)
            cur = [b, float(op), float(hi), float(lo), float(cl), float(v)]
        else:
            cur[2] = max(cur[2], hi); cur[3] = min(cur[3], lo); cur[4] = float(cl); cur[5] += float(v)
    if cur: rows.append(cur)
    return rows

def metki(ts, o):
    rows4 = agg4h(ts, o); close_t = [r[0] + H4 for r in rows4]; out, j, kesh = [], 0, {}
    for t in ts:
        while j < len(rows4) and close_t[j] <= int(t) + H: j += 1
        if j < MIN_BAROV: out.append(None); continue
        if j not in kesh: kesh[j] = compute_regime([list(x) for x in rows4[max(0, j - OKNO):j]])["regime"]
        out.append(kesh[j])
    return out

def sha_file(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def zamok(zapisat=False):
    d = np.load(LAB / "data/h1/BTCUSDT.npz"); ts = d["ts"].astype(np.int64); o = d["ohlcv"].astype(float)
    m = ts < 1759276800000; s = metki(ts[m], o[m])
    z = dict(imya="REZHIM_V1", vybran="D2_REGIME_ORCH_4H по os2/B2_KRITERII_REZHIMA.md", params=PARAMS,
             kod_sha256={"bot/regime_orchestrator.py": sha_file(ROOT / "bot/regime_orchestrator.py"),
                         "research_lab/os2/rezhim_v1.py": sha_file(__file__)},
             metki_do_2025_10_01_sha256=hashlib.sha256(json.dumps(s).encode()).hexdigest(), chasov=len(s))
    p = LAB / "os2/REZHIM_V1_ZAMOK.json"
    if zapisat:
        if p.exists(): sys.exit("замок уже есть: " + str(p))
        p.write_text(json.dumps(z, ensure_ascii=False, indent=1))
    return z

def proverit():
    z = json.loads((LAB / "os2/REZHIM_V1_ZAMOK.json").read_text()); t = zamok()
    ok = t["kod_sha256"] == z["kod_sha256"] and t["metki_do_2025_10_01_sha256"] == z["metki_do_2025_10_01_sha256"]
    print("REZHIM_V1 замок:", "PASS" if ok else "FAIL"); return ok

if __name__ == "__main__":
    if "--zamok" in sys.argv: print(json.dumps(zamok(True), ensure_ascii=False, indent=1))
    else: sys.exit(0 if proverit() else 1)
