"""КОНТУР: сквиз перегруженной стороны вокруг расчёта фандинга.

Гипотеза. Фандинг платится каждые 8 часов (00/08/16 UTC). Когда ставка
экстремально положительна — лонги перегружены и платят шортам; когда
экстремально отрицательна — наоборот. Перегруженная сторона уязвима:
после расчёта её выносят.

Торгуем ПРОТИВ толпы:
    фандинг очень высокий  -> шорт
    фандинг очень низкий   -> лонг

Почему это интересно при нашем капитале:
  * событие датированное, 3 раза в сутки на символ — частота без тесных стопов;
  * механика, а не геометрия — не коррелирует с BOUNCE1/ATT1/BREAKDOWN;
  * данные уже есть (`data/funding_rates/`), покупать ничего не надо.

Честно: это НЕ проверенный эдж, это первая проверка гипотезы.

Запуск:
    python3 research_lab/funding_squeeze.py 90 8
    (перцентиль отсечки, часов удержания)
"""
from __future__ import annotations

import csv
import glob
import json
import os
import sys

FUND_DIR = "data/funding_rates/crypto_static_v1_20260425"
KL_DIR = ".cache/klines"


def load_funding(symbol: str) -> list[tuple[int, float]]:
    p = os.path.join(FUND_DIR, f"{symbol}.csv")
    if not os.path.exists(p):
        return []
    out = []
    for r in csv.DictReader(open(p)):
        try:
            out.append((int(r["timestamp_ms"]), float(r["funding_rate"])))
        except Exception:
            continue
    out.sort()
    return out


def load_bars(symbol: str) -> list:
    best, n = None, 0
    for f in glob.glob(os.path.join(KL_DIR, f"{symbol}_5_*.json")):
        try:
            rows = json.load(open(f))
        except Exception:
            continue
        if len(rows) > n:
            best, n = rows, len(rows)
    return best or []


def _bar_index(bars: list, ts_ms: int) -> int | None:
    """Первый бар строго ПОСЛЕ ts_ms (next-open, без заглядывания)."""
    lo, hi = 0, len(bars) - 1
    if not bars or ts_ms < bars[0][0] or ts_ms > bars[-1][0]:
        return None
    while lo < hi:
        mid = (lo + hi) // 2
        if bars[mid][0] <= ts_ms:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(bars) else None


def run_symbol(symbol: str, pct_cut: float, hold_hours: int,
               lookback: int = 90, fee_bps: float = 6.0,
               slip_bps: float = 2.0) -> dict:
    fund = load_funding(symbol)
    bars = load_bars(symbol)
    if len(fund) < lookback + 10 or not bars:
        return {}
    hold_bars = int(hold_hours * 12)
    cost = 2.0 * (fee_bps + slip_bps) / 10000.0
    wins = losses = 0
    gw = gl = 0.0
    rets = []
    for i in range(lookback, len(fund)):
        hist = sorted(x[1] for x in fund[i - lookback:i])
        rate = fund[i][1]
        hi_cut = hist[min(len(hist) - 1, int(len(hist) * pct_cut / 100))]
        lo_cut = hist[max(0, int(len(hist) * (100 - pct_cut) / 100))]
        side = 0
        if rate >= hi_cut and rate > 0:
            side = -1          # лонги перегружены -> шорт
        elif rate <= lo_cut and rate < 0:
            side = +1          # шорты перегружены -> лонг
        if side == 0:
            continue
        j = _bar_index(bars, fund[i][0])
        if j is None or j + hold_bars >= len(bars):
            continue
        entry = float(bars[j][1])
        exit_ = float(bars[j + hold_bars][4])
        if entry <= 0:
            continue
        r = side * (exit_ / entry - 1.0) - cost
        rets.append(r)
        if r >= 0:
            wins += 1
            gw += r
        else:
            losses += 1
            gl += -r
    if not rets:
        return {}
    return {
        "symbol": symbol, "n": len(rets),
        "net_pct": sum(rets) * 100,
        "pf": (gw / gl) if gl > 0 else float("inf"),
        "wr": wins / len(rets),
        "avg_bps": sum(rets) / len(rets) * 10000,
    }


if __name__ == "__main__":
    pct = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
    hold = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    syms = sorted(os.path.basename(p)[:-4] for p in glob.glob(f"{FUND_DIR}/*.csv"))
    print(f"СКВИЗ ФАНДИНГА — отсечка p{pct:.0f}, удержание {hold}ч, "
          f"next-open, издержки 16 bps круг")
    print(f"{'символ':<12}{'сделок':>7}{'net %':>9}{'PF':>7}{'WR':>7}{'ср.bps':>9}")
    tot_n = 0
    tot_net = 0.0
    tw = tl = 0.0
    for s in syms:
        r = run_symbol(s, pct, hold)
        if not r:
            continue
        print(f"{r['symbol']:<12}{r['n']:>7}{r['net_pct']:>+9.2f}"
              f"{r['pf']:>7.3f}{r['wr']*100:>6.0f}%{r['avg_bps']:>+9.1f}")
        tot_n += r["n"]
        tot_net += r["net_pct"]
    print(f"{'ИТОГО':<12}{tot_n:>7}{tot_net:>+9.2f}")
