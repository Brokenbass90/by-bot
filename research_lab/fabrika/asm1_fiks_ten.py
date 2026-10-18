#!/usr/bin/env python3
"""asm1_fiks_ten.py — DATA-ONLY тень ASM1_FIKS (PREREG_ASM1_FIKS_VPERED_2026_10_17). Хук сторожа, раз в час.
Публичные свечи Bybit linear 60 мин; решения → data/asm1_fiks/resheniya.jsonl; исходы → ishody.jsonl (после 168 ч)."""
import json, sys, time, urllib.request
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB / "fabrika"))
import asm1_h1_sdelki as A
D = LAB / "data/asm1_fiks"; RES = D / "resheniya.jsonl"; ISH = D / "ishody.jsonl"; SOST = D / "sostoyanie.json"
H = 3_600_000; K, HOLD, IZD, FUND8 = 2.0, 168, 16.0, 1.0
VSELENNAYA = sorted(p.stem for p in (LAB / "data/h1").glob("*.npz") if not p.stem.endswith("_B21"))   # заморожено prereg


def _jsonl(p): return [json.loads(s) for s in p.read_text().splitlines() if s.strip()] if p.exists() else []


def svechi(sym, start_ms=None, limit=400):
    q = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={sym}&interval=60&limit={limit}" + (f"&start={start_ms}" if start_ms else "")
    with urllib.request.urlopen(urllib.request.Request(q, headers={"User-Agent": "trading-os-research/1.0"}), timeout=20) as r:
        d = json.loads(r.read().decode())
    rows = sorted(((int(x[0]), *map(float, x[1:6])) for x in (d.get("result") or {}).get("list") or []))
    seychas = int(time.time() * 1000)
    rows = [x for x in rows if x[0] + H <= seychas]                       # только закрытые
    if not rows: return None
    a = np.array(rows); return a[:, 0].astype(np.int64), a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]


def reshit(sym, ts, o, h, l, c, v, posl_ms, seychas_ms):
    """Сигнал только на последнем закрытом баре, которого ещё не видели. → запись решения или None."""
    if len(ts) < A.LB + 60 or ts[-1] <= posl_ms: return None
    sig = [x for x in A.signaly(ts, o, h, l, c, v) if x[0] == len(ts) - 1]
    if not sig: return None
    ib, s, a = sig[0]; t_vh = int(ts[ib]) + H
    vhod_isp = (seychas_ms // H + 1) * H                         # дополнение 1: первый полный бар после записи
    return dict(symbol=sym, bar_ms=int(ts[ib]), storona=int(s), atr=a, vhod_ms=vhod_isp, vhod_signal_ms=t_vh,
                zapisano_ms=seychas_ms, pozdno=bool(seychas_ms - t_vh > 2 * H), stop_atr=K, uderzhanie_ch=HOLD,
                prereg="PREREG_ASM1_FIKS_VPERED_2026_10_17 + дополнение 1")


def ishod(r, ts, o, h, l, c):
    idx = {int(t): j for j, t in enumerate(ts)}; e = idx.get(r["vhod_ms"])
    if e is None or e + HOLD > len(ts) or ts[e + HOLD - 1] - ts[e] != (HOLD - 1) * H: return None
    s, vh = r["storona"], o[e]; risk = K * r["atr"]; stop = vh - s * risk
    for j in range(e, e + HOLD):
        if (s > 0 and l[j] <= stop) or (s < 0 and h[j] >= stop):
            vy = min(o[j], stop) if s > 0 else max(o[j], stop); chas = j - e + 1; break
    else:
        vy, chas = c[e + HOLD - 1], HOLD
    return round((s * (vy - vh) - (IZD + FUND8 * chas / 8) / 1e4 * vh) / risk, 4)


def prohod(maks_sekund=240):
    D.mkdir(parents=True, exist_ok=True); t0 = time.time(); seychas = int(t0 * 1000)
    st = json.loads(SOST.read_text()) if SOST.exists() else {}
    otkr = {r["symbol"]: r for r in _jsonl(RES) if not r["pozdno"]}
    zakr = {(x["symbol"], x["vhod_ms"]) for x in _jsonl(ISH)}
    novyh = oshibok = ishodov = 0
    for sym in VSELENNAYA:
        if time.time() - t0 > maks_sekund: break
        try:
            d = svechi(sym)
        except Exception:
            oshibok += 1; continue
        if d is None: continue
        ts = d[0]
        r = otkr.get(sym)
        zanyato = r is not None and (r["symbol"], r["vhod_ms"]) not in zakr and ts[-1] < r["vhod_ms"] + HOLD * H
        if not zanyato:
            z = reshit(sym, *d, st.get(sym, 0), seychas)
            if z:
                with open(RES, "a") as f: f.write(json.dumps(z, ensure_ascii=False) + "\n")
                novyh += 1
        st[sym] = int(ts[-1])
        if r is not None and (sym, r["vhod_ms"]) not in zakr and seychas >= r["vhod_ms"] + HOLD * H:
            try:
                dd = svechi(sym, start_ms=r["vhod_ms"], limit=HOLD + 5)
                R = ishod(r, *dd[:5]) if dd else None
            except Exception:
                R = None
            if R is not None:
                with open(ISH, "a") as f: f.write(json.dumps(dict(symbol=sym, vhod_ms=r["vhod_ms"], R=R, zapisano_ms=seychas)) + "\n")
                ishodov += 1
        time.sleep(0.05)
    SOST.write_text(json.dumps(st))
    return dict(novyh=novyh, ishodov=ishodov, oshibok=oshibok, monet=len(st), sekund=round(time.time() - t0))


if __name__ == "__main__":
    print(prohod())
