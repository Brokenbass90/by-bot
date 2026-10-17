#!/usr/bin/env python3
"""kontekst_v2.py — BRAIN_V2 этап 1: Context Engine (17.10.2026, PREREG_BRAIN_V2_KONTEKST_2026_10_17). Shadow-only.

Добавляет к ContextRecord v1 поля, вычисленные ТОЛЬКО из данных с меткой ≤ момента наблюдения t_obs.
На решения политик BASELINE/BRAIN/HEDGE не влияет — только записывается. Набор полей заморожен prereg.
"""
import bisect, datetime as dt, json, math
from pathlib import Path
from zoneinfo import ZoneInfo
LAB = Path(__file__).resolve().parents[1]; H = 3_600_000; NY = ZoneInfo("America/New_York"); U = "UNKNOWN"
_KAL = None


def _kalendar():
    global _KAL
    if _KAL is None:
        k = json.loads((LAB / "data/makro/kalendar_v2.json").read_text()); ev = []
        def ms(d, hh, mm):
            return int(dt.datetime.combine(dt.date.fromisoformat(d), dt.time(hh, mm), NY).astimezone(dt.timezone.utc).timestamp() * 1000)
        for kk in ("cpi", "nfp", "ppi"): ev += [(ms(d, 8, 30), kk) for d in k[kk]]
        ev += [(ms(d, 14, 0), "fomc") for d in k["fomc"]]
        _KAL = sorted(ev)
    return _KAL


def _etf(t_obs):
    p = LAB / "data/etf_premiya/ten_ETF_PREMIYA.jsonl"
    if not p.exists(): return U, U
    best = None
    for s in p.read_text().splitlines():
        r = json.loads(s)
        if r.get("zapisano_ms", 1 << 62) <= t_obs and (best is None or r["den"] > best["den"]): best = r
    return (best["z"], best["den"]) if best else (U, U)


def dopolnit(ctx, t_obs_ms, btc_bary):
    ctx = dict(ctx, schema="ContextRecord v2", kontekst_v2=dict(v=1))
    k = ctx["kontekst_v2"]
    kal = _kalendar(); i = bisect.bisect_right(kal, (t_obs_ms, "~"))
    sled = kal[i] if i < len(kal) else None; pred = kal[i - 1] if i > 0 else None
    k["makro_sled"] = sled[1] if sled else U
    k["makro_cherez_ch"] = round((sled[0] - t_obs_ms) / H, 2) if sled else U
    k["makro_posle_ch"] = round((t_obs_ms - pred[0]) / H, 2) if pred else U
    k["makro_okno_24ch"] = bool(sled and sled[0] - t_obs_ms <= 24 * H) or bool(pred and t_obs_ms - pred[0] <= 24 * H)
    k["vyhodnye"] = dt.datetime.fromtimestamp(t_obs_ms / 1000, dt.timezone.utc).weekday() >= 5
    k["etf_premiya_z"], k["etf_den"] = _etf(t_obs_ms)
    k["vol_24ch_bps"] = k["vol_pct_720"] = U
    if btc_bary:
        b = [x for x in btc_bary if x[0] + H <= t_obs_ms]
        if len(b) >= 744:
            c = [float(x[4]) for x in b]; r = [math.log(c[j] / c[j - 1]) for j in range(1, len(c))]
            def sd(a): m = sum(a) / len(a); return math.sqrt(sum((x - m) ** 2 for x in a) / (len(a) - 1))
            v = sd(r[-24:]); hist = [sd(r[j - 24:j]) for j in range(len(r) - 720, len(r))]
            k["vol_24ch_bps"] = round(v * 1e4, 2); k["vol_pct_720"] = round(sum(h <= v for h in hist) / len(hist), 3)
    return ctx
