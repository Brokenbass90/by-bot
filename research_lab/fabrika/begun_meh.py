#!/usr/bin/env python3
"""begun_meh.py — прогонщик фабрики для механизмов из mehanizmy.py.

Механика сделки = sim_geo из random_control (проверена паритетом):
вход открытием следующего бара, стоп и две цели в R, доля f1 на первой,
стоп выигрывает внутри бара, по сроку — выход закрытием. Издержки —
fee_bps рынка на сторону, умноженные на плечо (entry/risk), как там.
Контроль: та же монета, случайный бар того же 30-дневного месяца, та же
сторона и геометрия, 20 розыгрышей, seed 7. Блок после сигнала hold//4.

    python3 begun_meh.py --param '{"meh":"PROBOY_55","rynok":"crypto137","side":"long"}' --vyhod rez.json
"""
from __future__ import annotations
import argparse, glob, json, math, sys
from pathlib import Path
import numpy as np

DIR = Path(__file__).resolve().parent; LAB = DIR.parent
sys.path.insert(0, str(DIR))
from mehanizmy import MEHANIZMY, RYNKI  # noqa: E402

DRAWS, PROGREV = 20, 250

try:
    from numba import njit
except Exception:                      # без numba работает, только медленнее
    def njit(*a, **k):
        return (lambda fn: fn) if not (a and callable(a[0])) else a[0]


@njit(cache=True)
def sim(o, h, l, c, i, short, stop_pct, rr1, rr2, f1, hold, fee_bps):
    e = i + 1
    n = len(o)
    if e >= n:
        return np.nan
    entry = o[e]; risk = entry * stop_pct
    if risk <= 0:
        return np.nan
    sl = entry + risk if short else entry - risk
    tp1 = entry - rr1 * risk if short else entry + rr1 * risk
    tp2 = entry - rr2 * risk if short else entry + rr2 * risk
    cost = (entry / risk) * 2 * fee_bps / 1e4
    rem = 1.0; gross = 0.0; done = False
    end = min(e + hold, n)
    for j in range(e, end):
        hh = h[j]; ll = l[j]
        hit_stop = (hh >= sl) if short else (ll <= sl)
        if hit_stop:
            gross += rem * ((entry - sl) if short else (sl - entry)) / risk
            return gross - cost
        if (not done) and ((ll <= tp1) if short else (hh >= tp1)):
            gross += f1 * rr1; rem -= f1; done = True
        if rem > 1e-9 and ((ll <= tp2) if short else (hh >= tp2)):
            gross += rem * rr2
            return gross - cost
    px = c[end - 1]
    gross += rem * ((entry - px) if short else (px - entry)) / risk
    return gross - cost


def okno_itog(R, C):
    R = np.array(R); cm = np.array([np.mean(x) for x in C if len(x) > 20])
    out = {"n": int(len(R))}
    if len(R) < 2 or len(cm) < 5:
        out["kontrol_sobran"] = False; return out
    edge = float(R.mean() - cm.mean())
    se = math.sqrt(R.std(ddof=1) ** 2 / len(R) + cm.var(ddof=1))
    out.update(kontrol_sobran=True, mean=float(R.mean()), ctrl=float(cm.mean()), ctrl_sd=float(cm.std(ddof=1)),
               edge=edge, se=se, z=edge / se if se > 0 else 0.0, summa_R=float(R.sum()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--param", required=True); ap.add_argument("--vyhod", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args(); p = json.loads(a.param)
    M = MEHANIZMY[p["meh"]]; RY = RYNKI[p["rynok"]]; short = p["side"] == "short"
    OKNA = dict(RY["okna"]); etap = p.get("etap")          # None = каталог v1 (все окна сразу)
    obrez = None
    if etap == "discovery" and "O3" in OKNA:               # обнаружение не видит O3 вообще
        obrez = OKNA.pop("O3")[0]
    elif etap == "confirmation":
        OKNA = {"O3": OKNA["O3"]}
    files = sorted(glob.glob(str(LAB / RY["papka"] / "*.npz")))
    if a.limit:
        files = files[: a.limit]
    real = {w: [] for w in OKNA}; ctrl = {w: [[] for _ in range(DRAWS)] for w in OKNA}
    rng = np.random.default_rng(7)
    for k, fp in enumerate(files):
        d = np.load(fp); ts = d["ts"].astype(np.int64)
        o, h, l, c, v = (np.ascontiguousarray(d["ohlcv"][:, j], dtype=np.float64) for j in range(5))
        if obrez is not None:
            k_ = int(np.searchsorted(ts, obrez)); ts = ts[:k_]
            o, h, l, c, v = (np.ascontiguousarray(x[:k_]) for x in (o, h, l, c, v))
        if len(ts) < PROGREV + 300:
            continue
        L, S, atr_ = M["fn"](o, h, l, c, v, ts) if M.get("nuzhen_ts") else M["fn"](o, h, l, c, v)
        sig = S if short else L
        month = ts // (30 * 86400000); idx = np.arange(len(ts))
        block = -1
        for i in np.flatnonzero(sig):
            if i < PROGREV or i <= block or i >= len(ts) - 1 or not (atr_[i] > 0):
                continue
            stop_pct = M["stop"] * atr_[i] / o[i + 1]
            r = sim(o, h, l, c, i, short, stop_pct, M["rr1"], M["rr2"], M["f1"], M["hold"], RY["fee_bps"])
            if not np.isfinite(r):
                continue
            block = i + M["hold"] // 4
            for w, (lo, hi) in OKNA.items():
                if lo <= ts[i] < hi:
                    real[w].append(r)
                    pool = np.flatnonzero((month == month[i]) & (idx >= PROGREV) & (idx < len(ts) - 1))
                    if len(pool) >= 5:
                        for dr in range(DRAWS):
                            j = int(rng.choice(pool))
                            rc = sim(o, h, l, c, j, short, stop_pct, M["rr1"], M["rr2"], M["f1"], M["hold"], RY["fee_bps"])
                            if np.isfinite(rc):
                                ctrl[w][dr].append(rc)
        if (k + 1) % 20 == 0:
            print(f"... {k+1}/{len(files)}", flush=True)
    rez = {"param": p, "monet": len(files), "limit": a.limit,
           "okna": {w: okno_itog(real[w], ctrl[w]) for w in OKNA}}
    tmp = Path(a.vyhod + ".tmp"); tmp.write_text(json.dumps(rez, ensure_ascii=False, indent=1))
    tmp.replace(a.vyhod)
    print("готово, сделок по окнам:", {w: x["n"] for w, x in rez["okna"].items()})


if __name__ == "__main__":
    main()
