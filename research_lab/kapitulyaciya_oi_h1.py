#!/usr/bin/env python3
"""PREREG_KAPITULYACIYA_OI_H1_2026_10_26 (2c096b6). python3 research_lab/kapitulyaciya_oi_h1.py [monety_cherez_zapyatuyu]
→ results/kapitulyaciya_oi_h1_20261026.json. Перцентили — только прошлые 336 ч (rolling closed='left'), вход h+1 открытие, выход h+4 закрытие."""
import collections, datetime as dt, json, math, random, sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; D = HERE / "data"; H = 3600_000
A, B = 1704067200000, 1790812800000          # 2024-01-01 … 2026-10-01
COST, SEED, NCTRL, HALF = 16.0, 20261026, 20, 1735689600000   # половины: 2024 | 2025-01…


def bars(sym):
    out = {}
    p = D / "h1" / f"{sym}.npz"
    if p.exists():
        z = np.load(p); ts = z["ts"].astype(np.int64); ts = ts if ts[0] > 1e11 else ts * 1000
        for t, (o, h, l, c, v) in zip(ts.tolist(), z["ohlcv"].tolist()): out[int(t)] = (o, h, l, c)
    p = D / "bybit_fanding_h1_2025_2026" / f"{sym}.json"
    if p.exists():
        for r in json.loads(p.read_text())["h1"]: out[int(r[0])] = tuple(r[1:5])
    return out


def funding(sym):
    fu = {}
    p = D / "bybit_public_preholdout_2023_20250930" / "funding" / f"{sym}.json"
    if p.exists():
        for x in json.loads(p.read_text())["records"]: fu[int(x["funding_time_ms"])] = float(x["funding_rate"])
    p = D / "bybit_fanding_h1_2025_2026" / f"{sym}.json"
    if p.exists():
        for t, r in json.loads(p.read_text())["funding"]: fu[int(t)] = float(r)
    return fu


def sdelka(b, fu, t, side):
    """Вход открытие часа t+1ч, выход закрытие часа t+4ч; bps после расходов и фандинга."""
    e, x = b.get(t + H), b.get(t + 4 * H)
    if e is None or x is None or any(b.get(t + k * H) is None for k in (2, 3)): return None
    r = side * (x[3] / e[0] - 1) * 1e4 - COST
    t_in, t_out = t + H, t + 5 * H
    r -= sum(side * rate * 1e4 for T, rate in fu.items() if t_in < T <= t_out)
    return r


def main():
    univ = json.load(open(D / "pump4_v1_universe_20261020.json"))["symbols"]
    if len(sys.argv) > 1: univ = sys.argv[1].split(",")
    rng = random.Random(SEED); sob, net_oi = [], []
    for sym in univ:
        p = D / "bybit_oi_h1_full" / f"{sym}.json"
        if not p.exists(): net_oi.append(sym); continue
        oi = {int(t): v for t, v in json.loads(p.read_text())}
        b = bars(sym); fu = {T: r for T, r in funding(sym).items() if A - H <= T <= B + 6 * H}
        rows = [(t, oi[t + H] / oi[t] - 1, b[t][3] / b[t][0] - 1) for t in sorted(oi)
                if t + H in oi and t in b and oi[t] > 0 and b[t][0] > 0]
        if len(rows) < 400: continue
        df = pd.DataFrame(rows, columns=["t", "doi", "ret"]); df.index = pd.to_datetime(df.t, unit="ms")
        q = lambda s, a: s.rolling("336h", closed="left", min_periods=300).quantile(a)
        df["q_doi"], df["q_lo"], df["q_hi"] = q(df.doi, 0.01), q(df.ret, 0.01), q(df.ret, 0.99)
        po_mes = collections.defaultdict(list)
        for t in df.t.tolist():
            if A <= t < B and t + 4 * H in b: po_mes[dt.datetime.utcfromtimestamp(t / 1000).strftime("%Y-%m")].append(t)
        zanyato_do = -1
        for t, doi, ret, qd, ql, qh in df[["t", "doi", "ret", "q_doi", "q_lo", "q_hi"]].itertuples(index=False):
            if not (A <= t < B) or np.isnan(qd) or t <= zanyato_do: continue
            side = 1 if (doi <= qd and ret <= ql) else (-1 if (doi <= qd and ret >= qh) else 0)
            if side == 0: continue
            r = sdelka(b, fu, int(t), side)
            if r is None: continue
            zanyato_do = int(t) + 3 * H
            pool = po_mes[dt.datetime.utcfromtimestamp(t / 1000).strftime("%Y-%m")]
            c = [sdelka(b, fu, tt, side) for tt in rng.sample(pool, min(NCTRL, len(pool)))] if pool else []
            c = [x for x in c if x is not None]
            sob.append(dict(sym=sym, t=int(t), side=side, r=round(r, 2), ctrl=round(float(np.mean(c)), 2) if c else None))
        print(sym, sum(1 for x in sob if x["sym"] == sym), flush=True)
    def svod(g):
        g = [x for x in g if x["ctrl"] is not None]
        if len(g) < 3: return dict(n=len(g))
        bl = collections.defaultdict(list)
        for x in g: bl[(x["t"] + H) // (4 * H)].append(x["r"] - x["ctrl"])
        v = np.array([np.mean(a) for a in bl.values()])
        dat = {dt.datetime.utcfromtimestamp(x["t"] / 1000).date() for x in g}
        return dict(n=len(g), dat=len(dat), monet=len({x["sym"] for x in g}), net_bps=round(float(np.mean([x["r"] for x in g])), 2),
                    ctrl_bps=round(float(np.mean([x["ctrl"] for x in g])), 2), prevyshenie_bps=round(float(v.mean()), 2),
                    t_prev=round(float(v.mean() / (v.std(ddof=1) / math.sqrt(len(v)))), 2) if len(v) > 2 else None, blokov=len(v),
                    dolya_plyus=round(sum(x["r"] > 0 for x in g) / len(g), 3))
    vse = svod(sob); p1 = svod([x for x in sob if x["t"] < HALF]); p2 = svod([x for x in sob if x["t"] >= HALF])
    out = dict(prereg="PREREG_KAPITULYACIYA_OI_H1_2026_10_26", net_oi=net_oi, vse=vse, polovina_2024=p1, polovina_2025_26=p2,
               long=svod([x for x in sob if x["side"] == 1]), short=svod([x for x in sob if x["side"] == -1]),
               po_godam={y: svod([x for x in sob if dt.datetime.utcfromtimestamp(x["t"] / 1000).year == y]) for y in (2024, 2025, 2026)},
               sobytiy_v_mesyac=round(len(sob) / ((B - A) / (30.44 * 86400_000)), 1))
    ok = vse.get("n", 0) >= 300 and vse.get("dat", 0) >= 60 and vse.get("monet", 0) >= 20
    if not ok: out["verdikt"] = "INCONCLUSIVE_MALO"
    elif vse["net_bps"] > 0 and vse["prevyshenie_bps"] > 0 and (vse["t_prev"] or 0) >= 2 and p1.get("net_bps", -1) > 0 and p2.get("net_bps", -1) > 0:
        out["verdikt"] = "HISTORY_SUPPORT"
    elif vse["net_bps"] <= 0 or (vse["t_prev"] or 0) < 1: out["verdikt"] = "HISTORY_AGAINST"
    else: out["verdikt"] = "INCONCLUSIVE"
    (HERE / "results" / "kapitulyaciya_oi_h1_20261026.json").write_text(json.dumps(dict(svod=out, sobytiya=sob), ensure_ascii=False))
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
