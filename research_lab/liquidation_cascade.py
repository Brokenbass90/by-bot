"""КАСКАД ЛИКВИДАЦИЙ — на НАСТОЯЩИХ данных, а не на прокси.

Почему стоит перепроверить. В `runtime/liquidation_sweep_run_latest.json`
лежит вердикт «FAIL (noise / no edge)», PF 0.26, ожидание −0.62R.
Но там же написано `mode = proxy` — то есть каскады определялись по ЦЕНЕ
(резкое падение + z-score), а не по фактическому потоку ликвидаций.

При этом реальные данные собраны: `runtime/liquidations/bybit_liquidations.jsonl`,
85 009 записей за 21 день. Они ни разу не использовались для проверки.

Прокси и реальность здесь расходятся принципиально: резкое падение цены
бывает без ликвидаций (просто продажи), а каскад ликвидаций — это
ПРИНУДИТЕЛЬНЫЕ рыночные заявки, у которых нет выбора по цене. Именно
принудительность и создаёт временное смещение цены, на котором может быть эдж.

Гипотеза: после каскада ликвидаций ЛОНГОВ (принудительные продажи) цена
временно продавлена ниже справедливой и в ближайшие минуты отскакивает.
Симметрично для шортов.

Обязательные проверки, без которых цифра ничего не значит:
  * КОНТРОЛЬ — те же символы в случайные моменты, с тем же распределением
    по часам суток. Без него измерим общий дрейф, а не эффект события;
  * снятие движения BTC (беты), иначе общий обвал рынка выглядит как эдж;
  * издержки: круг ~8 bps, поэтому эффект меньше ~15 bps бесполезен;
  * обе стороны отдельно — перекос в одну сторону обычно означает бету.
"""
from __future__ import annotations

import bisect
import glob
import json
import os
import random
import statistics
import sys

LIQ = "runtime/liquidations/bybit_liquidations.jsonl"
CACHE = "data_cache"
BAR_MS = 5 * 60 * 1000


def load_bars(symbol: str):
    files = sorted(glob.glob(f"{CACHE}/{symbol}_5_*.json"),
                   key=os.path.getsize, reverse=True)
    if not files:
        return [], []
    rows = sorted(json.load(open(files[0])), key=lambda r: r["ts"])
    return rows, [r["ts"] for r in rows]


def bar_at(times, ts):
    i = bisect.bisect_right(times, ts) - 1
    return i if i >= 0 else None


def fwd_bps(rows, i, hold_bars):
    """Доходность от ОТКРЫТИЯ следующего бара на hold_bars вперёд, в bps."""
    j = i + 1
    if j + hold_bars >= len(rows):
        return None
    a = float(rows[j]["o"])
    b = float(rows[j + hold_bars]["c"])
    return (b / a - 1.0) * 10000 if a > 0 else None


def load_events(min_usd_mult: float, floor_usd: float):
    """Каскады = 5-минутные корзины с потоком много выше базовой линии."""
    buckets = {}
    for line in open(LIQ):
        try:
            d = json.loads(line)
            sym = d["symbol"]
            b = int(d["ts_ms"]) // BAR_MS * BAR_MS
            usd = float(d.get("usd") or 0.0)
            side = d.get("side")
        except Exception:
            continue
        k = (sym, b)
        r = buckets.setdefault(k, [0.0, 0.0])
        if side == "long":
            r[0] += usd
        else:
            r[1] += usd

    per_sym = {}
    for (sym, b), (lo, sh) in buckets.items():
        per_sym.setdefault(sym, []).append((b, lo, sh))

    events = []
    for sym, rows in per_sym.items():
        rows.sort()
        tot = [lo + sh for _, lo, sh in rows]
        if len(tot) < 50:
            continue
        base = statistics.median([t for t in tot if t > 0]) or 1.0
        for b, lo, sh in rows:
            if lo >= max(floor_usd, base * min_usd_mult) and lo > sh * 2:
                events.append((sym, b, "long"))      # ликвидировали лонги
            elif sh >= max(floor_usd, base * min_usd_mult) and sh > lo * 2:
                events.append((sym, b, "short"))
    return events, per_sym


def run(hold_bars: int, min_usd_mult: float, floor_usd: float, seed: int = 7):
    events, per_sym = load_events(min_usd_mult, floor_usd)
    if not events:
        print("событий нет")
        return
    syms = sorted({s for s, _, _ in events})
    bars = {s: load_bars(s) for s in syms}
    btc_rows, btc_times = load_bars("BTCUSDT")

    rnd = random.Random(seed)
    res = {"long": [], "short": []}
    ctrl = {"long": [], "short": []}
    skipped = 0

    for sym, b, side in events:
        rows, times = bars.get(sym, ([], []))
        if not rows:
            skipped += 1
            continue
        i = bar_at(times, b)
        if i is None:
            skipped += 1
            continue
        r = fwd_bps(rows, i, hold_bars)
        j = bar_at(btc_times, b)
        rb = fwd_bps(btc_rows, j, hold_bars) if j is not None else None
        if r is None or rb is None:
            skipped += 1
            continue
        # знак: после ликвидации ЛОНГОВ ждём отскок ВВЕРХ
        sign = 1.0 if side == "long" else -1.0
        res[side].append(sign * (r - rb))

        # контроль: случайный бар того же символа, тот же час суток
        hour = (b // 3600000) % 24
        for _ in range(6):
            k = rnd.randrange(50, len(rows) - hold_bars - 2)
            if (rows[k]["ts"] // 3600000) % 24 != hour:
                continue
            rc = fwd_bps(rows, k, hold_bars)
            jb = bar_at(btc_times, rows[k]["ts"])
            rcb = fwd_bps(btc_rows, jb, hold_bars) if jb is not None else None
            if rc is not None and rcb is not None:
                ctrl[side].append(sign * (rc - rcb))
                break

    print(f"КАСКАДЫ ЛИКВИДАЦИЙ — реальные данные, {len(events)} событий "
          f"({skipped} пропущено без цен)")
    print(f"порог: поток > {min_usd_mult}× медианы и > ${floor_usd:,.0f}, "
          f"удержание {hold_bars*5} мин, из движения снят BTC")
    print(f"{'сторона':<10}{'событий':>9}{'эффект bps':>13}{'контроль':>11}"
          f"{'разница':>10}{'t':>8}{'плюсовых':>10}")
    for side in ("long", "short"):
        a, c = res[side], ctrl[side]
        if len(a) < 25:
            print(f"{side:<10}{len(a):>9}   мало наблюдений")
            continue
        m, mc = statistics.fmean(a), (statistics.fmean(c) if c else 0.0)
        sd = statistics.pstdev(a)
        t = (m - mc) / (sd / len(a) ** 0.5) if sd > 0 else 0.0
        pos = sum(1 for x in a if x > 0) / len(a) * 100
        name = "лонги ликв." if side == "long" else "шорты ликв."
        print(f"{name:<10}{len(a):>9}{m:>+13.1f}{mc:>+11.1f}{m-mc:>+10.1f}"
              f"{t:>+8.2f}{pos:>9.0f}%")
    print("\nпорог осмысленности: разница с контролем > ~15 bps (круг ~8 bps)")


if __name__ == "__main__":
    hold = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    mult = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
    floor = float(sys.argv[3]) if len(sys.argv) > 3 else 50000.0
    run(hold, mult, floor)
