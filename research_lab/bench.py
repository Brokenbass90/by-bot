#!/usr/bin/env python3
"""bench.py — стенд проверки технологий.

Берёт готовый набор сделок стратегии и прогоняет через него фильтры
по одному. Для каждого фильтра считает:
    сколько сделок осталось
    результат чистый и до издержек
    вклад относительно «без фильтра»
    видно ли этот вклад вообще (значимость и минимально видимый эффект)

И сразу проверяет то же самое на ВТОРОМ периоде, где фильтр не искали.
Технология считается полезной, только если помогла на обоих.
"""
import json, math, glob, os
from collections import defaultdict
import numpy as np

D = "/home/claude/att1_wide"
FEE_RT = 12 / 1e4          # круг тейкером
MAKER_RT = 8 / 1e4         # вход мейкером, выход тейкером

PERIODS = {
    "2024-03..2025-09": ("wide_trades.json", 1709251200000, 1759276800000),
    "2023-01..2024-02": ("oos2023_trades.json", 1672531200000, 1709251200000),
}


def ema(x, n):
    k = 2 / (n + 1); e = x[0]; out = np.empty(len(x))
    for i, v in enumerate(x):
        e = v * k + e * (1 - k); out[i] = e
    return out


def market_state():
    d = np.load(f"{D}/h1/BTCUSDT.npz")
    ts, c = d["ts"], d["ohlcv"][:, 3].astype(float)
    return ts, c > ema(c, 200)


def sym_stats(a, b):
    out = {}
    for fp in sorted(glob.glob(f"{D}/h1/*.npz")):
        s = os.path.basename(fp)[:-4]
        d = np.load(fp); ts = d["ts"]; o = d["ohlcv"].astype(float)
        m = (ts >= a) & (ts < b)
        if m.sum() < 1500:
            continue
        h, l, c, v = o[m, 1], o[m, 2], o[m, 3], o[m, 4]
        out[s] = dict(atrp=float(np.median((h - l) / c)) * 100,
                      turn=float(np.median(c * v)) * 24,
                      trend=float(c[-1] / c[0] - 1) * 100)
    return out


# ── технологии. каждая: имя -> функция(сделка, справка) -> брать ли ──
TECHS = [
    ("без фильтра", lambda t, r: True),
    ("шумность актива > 1.0%/час", lambda t, r: r["st"].get(t["sym"], {}).get("atrp", 0) > 1.0),
    ("шумность > 1.23%/час", lambda t, r: r["st"].get(t["sym"], {}).get("atrp", 0) > 1.23),
    ("оборот > $14 млн/сут", lambda t, r: r["st"].get(t["sym"], {}).get("turn", 0) > 14e6),
    ("актив не в сильном росте", lambda t, r: r["st"].get(t["sym"], {}).get("trend", 0) < 22),
    ("рынок падает (BTC<EMA200)", lambda t, r: not r["btc_up"](t["ts"])),
    ("не новостное окно 12-16 UTC", lambda t, r: not (12 <= (t["ts"] // 3600000) % 24 < 16)),
    ("плечо < 40 (широкий стоп)", lambda t, r: t["lev"] < 40),
    ("плечо < 25", lambda t, r: t["lev"] < 25),
]


def stats(sel, maker=False):
    if len(sel) < 40:
        return None
    R = np.array([t["R"] for t in sel]); lev = np.array([t["lev"] for t in sel])
    gross = R + lev * FEE_RT
    net = gross - lev * (MAKER_RT if maker else FEE_RT)
    se = net.std(ddof=1) / math.sqrt(len(net))
    return dict(n=len(net), net=net.mean(), gross=gross.mean(), se=se,
                sigma=net.mean() / se, mde=1.96 * net.std(ddof=1) / math.sqrt(len(net)))


def main():
    res = {}
    for pname, (fn, a, b) in PERIODS.items():
        trades = json.load(open(f"{D}/{fn}"))
        st = sym_stats(a, b)
        bts, bup = market_state()
        idx = {}

        def btc_up(ts):
            j = int(np.searchsorted(bts, ts, side="right")) - 1
            return bool(bup[j]) if 0 <= j < len(bup) else False

        ref = dict(st=st, btc_up=btc_up)
        base = stats(trades)
        for name, fn_ in TECHS:
            sel = [t for t in trades if fn_(t, ref)]
            for maker in (False, True):
                s = stats(sel, maker)
                res.setdefault((name, maker), {})[pname] = s
        res.setdefault(("__base__", False), {})[pname] = base

    print("=" * 104)
    print("СТЕНД ТЕХНОЛОГИЙ — ATT1. «вклад» = насколько лучше, чем без фильтра, в R на сделку")
    print("Технология принимается, только если помогла на ОБОИХ периодах.\n")
    hdr = f"{'технология':<32}{'вход':<8}"
    for p in PERIODS:
        hdr += f"{p:>34}"
    print(hdr)
    print(f"{'':<40}" + "".join(f"{'n / итог / вклад / видно':>34}" for _ in PERIODS))
    print("-" * 104)
    for maker in (False, True):
        for name, _ in TECHS:
            row = f"{name:<32}{'мейкер' if maker else 'рынок':<8}"
            ok = []
            for p in PERIODS:
                s = res[(name, maker)].get(p)
                b = res[("без фильтра", maker)].get(p)
                if not s:
                    row += f"{'мало сделок':>34}"; ok.append(False); continue
                d = s["net"] - b["net"]
                vis = "видно" if abs(d) > s["mde"] else "в шуме"
                row += f"{s['n']:>7} {s['net']:+.4f} {d:+.4f} {vis:>7}"
                ok.append(d > 0)
            mark = "  <<<" if all(ok) and name != "без фильтра" else ""
            print(row + mark)
        print("-" * 104)
    print("\nвклад считается против «без фильтра» той же колонки")
    print("«видно» = вклад больше минимально различимого эффекта на этом числе сделок")


if __name__ == "__main__":
    main()
