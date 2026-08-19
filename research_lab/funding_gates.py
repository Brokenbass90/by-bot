"""ФАНДИНГ — три гейта перед тем, как называть это ногой.

1. ROLLING БЕТА (out-of-sample). В v2 бета считалась на тех же наблюдениях,
   что и результат — это завышает остаток. Здесь бета берётся из ПРЕДЫДУЩИХ
   `beta_window` наблюдений и применяется к следующему. Так честнее.

2. ПЛАТО. Проверяем сетку отсечка x удержание. Хорошая настройка — та,
   у которой работают соседи. Одиночный пик = подгонка.

3. PER-SYMBOL. Разброс по символам огромный (LINK +27.8, ETH -15.4).
   Смотрим, сколько символов положительны и не держится ли всё на одном.
"""
from __future__ import annotations

import glob
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from research_lab.funding_squeeze import load_funding, load_bars, _bar_index
from research_lab.funding_squeeze_v2 import _ret

FD = "data/funding_rates/crypto_static_v1_20260425"


def signals(symbol: str, pct: float, hold_h: int, btc_bars, lookback: int = 90):
    """Список (ts, r_sym_signed, r_btc_signed) по строгой отсечке."""
    fund = load_funding(symbol)
    bars = load_bars(symbol)
    if len(fund) < lookback + 10 or not bars:
        return []
    hb = hold_h * 12
    out = []
    for i in range(lookback, len(fund)):
        hist = sorted(x[1] for x in fund[i - lookback:i])
        rate = fund[i][1]
        hi = hist[min(len(hist) - 1, int(len(hist) * pct / 100))]
        lo = hist[max(0, int(len(hist) * (100 - pct) / 100))]
        side = -1 if (rate > hi and rate > 0) else (1 if (rate < lo and rate < 0) else 0)
        if side == 0:
            continue
        ts = fund[i][0]
        rs = _ret(bars, _bar_index(bars, ts), hb)
        rb = _ret(btc_bars, _bar_index(btc_bars, ts), hb)
        if rs is None or rb is None:
            continue
        out.append((ts, side * rs, side * rb))
    return out


def rolling_residual(rows, beta_window: int = 60):
    """Остаток после снятия беты, ОЦЕНЁННОЙ НА ПРЕДЫДУЩИХ наблюдениях."""
    rows = sorted(rows)
    res = []
    for i in range(beta_window, len(rows)):
        hist = rows[i - beta_window:i]
        xs = [b for _, _, b in hist]
        ys = [y for _, y, _ in hist]
        mx, my = statistics.fmean(xs), statistics.fmean(ys)
        var = sum((x - mx) ** 2 for x in xs)
        beta = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var) if var > 0 else 0.0
        _, y, x = rows[i]
        res.append(y - beta * x)
    return res


def collect(pct: float, hold: int, btc, syms):
    per = {}
    for s in syms:
        r = signals(s, pct, hold, btc)
        if len(r) >= 30:
            per[s] = r
    return per


if __name__ == "__main__":
    btc = load_bars("BTCUSDT")
    syms = sorted(os.path.basename(p)[:-4] for p in glob.glob(f"{FD}/*.csv"))
    mode = sys.argv[1] if len(sys.argv) > 1 else "plateau"

    if mode == "plateau":
        print("ГЕЙТ 2 — ПЛАТО. Остаток после ROLLING беты, bps/сделку\n")
        print(f"{'отсечка':>9}" + "".join(f"{h:>8}ч" for h in (8, 12, 16, 24)))
        for pct in (85, 90, 95):
            row = f"{'p'+str(pct):>9}"
            for h in (8, 12, 16, 24):
                per = collect(pct, h, btc, syms)
                allr = []
                for s, rows in per.items():
                    allr += rolling_residual(rows)
                row += f"{statistics.fmean(allr)*10000 if allr else 0:>+9.1f}"
            print(row)

    elif mode == "symbols":
        pct = float(sys.argv[2]) if len(sys.argv) > 2 else 90
        hold = int(sys.argv[3]) if len(sys.argv) > 3 else 16
        print(f"ГЕЙТ 3 — ПО СИМВОЛАМ, p{pct:.0f}/{hold}ч, rolling бета\n")
        print(f"{'символ':<11}{'сделок':>8}{'остаток bps':>13}")
        per = collect(pct, hold, btc, syms)
        tot = []
        pos = 0
        for s, rows in sorted(per.items()):
            r = rolling_residual(rows)
            if not r:
                continue
            m = statistics.fmean(r) * 10000
            pos += (m > 0)
            tot += r
            print(f"{s:<11}{len(r):>8}{m:>+13.1f}")
        print(f"\nположительных символов: {pos}/{len(per)}")
        print(f"общий остаток: {statistics.fmean(tot)*10000:+.1f} bps на {len(tot)} сделках")
