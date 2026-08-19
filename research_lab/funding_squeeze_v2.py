"""ФАНДИНГ V2 — с исправлением моего бага и со снятием рыночной беты.

Что было сломано в v1:
  ставки фандинга часто РАВНЫ друг другу (много значений ровно 0.0001 — это
  дефолтный кап Bybit). При нестрогом сравнении `rate >= p90` условие срабатывало
  на всей плоской вершине распределения, а не на её хвосте. Из-за этого выборка
  раздувалась и перекашивалась в шорты. Вывод «это бета» был сделан на другой
  выборке, чем я думал.

Что исправлено:
  1. СТРОГОЕ сравнение (`>` вместо `>=`) — берём настоящий хвост;
  2. отдельно считается доля лонгов/шортов, чтобы перекос был виден сразу;
  3. **снятие беты**: из результата вычитается движение рынка (BTC) за тот же
     период удержания, умноженное на бету символа. Остаток — это то, что
     не объясняется направлением рынка.

Без п.3 любой перекос в одну сторону на трендовом периоде выглядит как эдж.
"""
from __future__ import annotations

import csv
import glob
import os
import statistics
import sys

import sys as _s, os as _o
_s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from research_lab.funding_squeeze import load_funding, load_bars, _bar_index

FD = "data/funding_rates/crypto_static_v1_20260425"


def _ret(bars, j, hold_bars):
    if j is None or j + hold_bars >= len(bars):
        return None
    e = float(bars[j][1])
    x = float(bars[j + hold_bars][4])
    return (x / e - 1.0) if e > 0 else None


def run(symbol: str, pct: float, hold_h: int, btc_bars,
        lookback: int = 90, strict: bool = True):
    fund = load_funding(symbol)
    bars = load_bars(symbol)
    if len(fund) < lookback + 10 or not bars or not btc_bars:
        return None
    hb = hold_h * 12
    raw, resid, sides = [], [], []
    for i in range(lookback, len(fund)):
        hist = sorted(x[1] for x in fund[i - lookback:i])
        rate = fund[i][1]
        hi = hist[min(len(hist) - 1, int(len(hist) * pct / 100))]
        lo = hist[max(0, int(len(hist) * (100 - pct) / 100))]
        if strict:
            long_sig = rate < lo and rate < 0
            short_sig = rate > hi and rate > 0
        else:
            long_sig = rate <= lo and rate < 0
            short_sig = rate >= hi and rate > 0
        side = -1 if short_sig else (1 if long_sig else 0)
        if side == 0:
            continue
        ts = fund[i][0]
        r_sym = _ret(bars, _bar_index(bars, ts), hb)
        r_btc = _ret(btc_bars, _bar_index(btc_bars, ts), hb)
        if r_sym is None or r_btc is None:
            continue
        raw.append(side * r_sym)
        resid.append((side * r_sym, side * r_btc))
        sides.append(side)
    if len(raw) < 30:
        return None
    # бета символа к BTC на этих же наблюдениях
    ys = [a for a, _ in resid]
    xs = [b for _, b in resid]
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    var = sum((x - mx) ** 2 for x in xs)
    beta = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var) if var > 0 else 0.0
    net_resid = [y - beta * x for x, y in zip(xs, ys)]
    return {
        "symbol": symbol, "n": len(raw),
        "raw_bps": statistics.fmean(raw) * 10000,
        "resid_bps": statistics.fmean(net_resid) * 10000,
        "beta": beta,
        "long_share": sum(1 for s in sides if s > 0) / len(sides),
    }


if __name__ == "__main__":
    pct = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
    hold = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    strict = (sys.argv[3] != "loose") if len(sys.argv) > 3 else True
    btc = load_bars("BTCUSDT")
    syms = sorted(os.path.basename(p)[:-4] for p in glob.glob(f"{FD}/*.csv"))
    mode = "СТРОГО >" if strict else "нестрого >="
    print(f"ФАНДИНГ V2 — p{pct:.0f}, удержание {hold}ч, {mode}")
    print(f"{'символ':<11}{'сделок':>7}{'сырой bps':>11}{'без беты':>10}"
          f"{'бета':>7}{'лонгов':>8}")
    tn = 0
    wr = wres = 0.0
    for s in syms:
        r = run(s, pct, hold, btc, strict=strict)
        if not r:
            continue
        print(f"{r['symbol']:<11}{r['n']:>7}{r['raw_bps']:>+11.1f}"
              f"{r['resid_bps']:>+10.1f}{r['beta']:>7.2f}{r['long_share']*100:>7.0f}%")
        tn += r["n"]
        wr += r["raw_bps"] * r["n"]
        wres += r["resid_bps"] * r["n"]
    if tn:
        print(f"{'ИТОГО':<11}{tn:>7}{wr/tn:>+11.1f}{wres/tn:>+10.1f}")
