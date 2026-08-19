"""ЛЕСТНИЦА ВХОДА: один вход или два добора?

Зачем. В ручной сделке владельца было ДВА захода от базы, а не один.
Ни в одной нашей ноге добора нет вообще (`grep scale_in|pyramid|add_on` —
пусто). Прежде чем просить Codex это строить, надо проверить, даёт ли
разделение входа хоть что-нибудь.

Что сравнивается на ОДНИХ И ТЕХ ЖЕ событиях:

  A. один вход    — весь размер по открытию следующего бара;
  B. два входа    — половина сразу, половина ниже на `--dip`,
                    если цена туда дойдёт за `--window` баров;
                    не дойдёт — остаёмся половиной.

Обе версии имеют ОДИН И ТОТ ЖЕ стоп (под минимумом базы) и один и тот же
выход по времени. Результат считается в R, где R = (первый вход − стоп),
поэтому версии сравнимы напрямую.

Что тут может пойти не так и за чем следим:
  * усреднение вниз всегда красиво поднимает винрейт и всегда утяжеляет
    убыточные сделки. Поэтому смотрим не только среднее, но и худшие 5%;
  * половина размера при недошедшей цене — это недоинвестирование,
    и оно должно быть видно как потеря на выигрышах.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import statistics
import sys

CACHE = "data_cache"


def load_h1(symbol: str):
    files = sorted(glob.glob(f"{CACHE}/{symbol}_5_*.json"),
                   key=os.path.getsize, reverse=True)
    if not files:
        return []
    agg = {}
    for b in json.load(open(files[0])):
        try:
            h = int(b["ts"]) // 3600000 * 3600000
            o, hi, lo, c = float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])
        except Exception:
            continue
        if h not in agg:
            agg[h] = [o, hi, lo, c]
        else:
            r = agg[h]
            r[1] = max(r[1], hi)
            r[2] = min(r[2], lo)
            r[3] = c
    return [(k, *v) for k, v in sorted(agg.items())]


def simulate(bars, i, *, dip, window, hold, buffer, low_lb):
    """Возвращает (R_один_вход, R_два_входа) или None."""
    if i + 1 >= len(bars) or i + 1 + hold >= len(bars):
        return None
    e1 = bars[i + 1][1]                       # вход по открытию следующего бара
    low = min(b[3] for b in bars[i - low_lb + 1:i + 1])
    stop = low * (1.0 - buffer)
    if e1 <= stop or stop <= 0:
        return None
    risk = e1 - stop
    e2_target = e1 * (1.0 - dip)
    if e2_target <= stop:                     # добор ниже стопа — бессмысленно
        return None

    seg = bars[i + 1:i + 1 + hold + 1]
    # версия A: весь размер по e1
    # версия B: 0.5 по e1, 0.5 по e2 если коснулись за window баров
    filled2 = False
    exit_px_a = exit_px_b = None
    for k, b in enumerate(seg):
        hi, lo, c = b[2], b[3], b[4]
        if not filled2 and k <= window and lo <= e2_target:
            filled2 = True
        if lo <= stop:                        # стоп общий для обеих версий
            exit_px_a = exit_px_b = stop
            break
    if exit_px_a is None:
        exit_px_a = exit_px_b = seg[-1][4]

    r_a = (exit_px_a - e1) / risk
    if filled2:
        avg = 0.5 * e1 + 0.5 * e2_target
        r_b = (exit_px_b - avg) / risk * 2.0 * 0.5 * 2.0 / 2.0   # полный размер
        r_b = (exit_px_b - avg) / risk
    else:
        r_b = 0.5 * (exit_px_b - e1) / risk   # остались половиной
    return r_a, r_b, filled2


def run(dip, window, hold, buffer, near, upleg, low_lb):
    syms = sorted({os.path.basename(f).split("_5_")[0]
                   for f in glob.glob(f"{CACHE}/*_5_*.json")})
    A, B, fills = [], [], 0
    for s in syms:
        bars = load_h1(s)
        if len(bars) < upleg + 200:
            continue
        for i in range(max(upleg, low_lb) + 1, len(bars) - hold - 2):
            c = bars[i][4]
            if c <= bars[i - upleg][4]:                 # не было роста
                continue
            low = min(b[3] for b in bars[i - low_lb + 1:i + 1])
            if low <= 0 or (c / low - 1.0) > near:      # не у базы
                continue
            r = simulate(bars, i, dip=dip, window=window, hold=hold,
                         buffer=buffer, low_lb=low_lb)
            if r is None:
                continue
            A.append(r[0]); B.append(r[1]); fills += 1 if r[2] else 0
    if len(A) < 50:
        print(f"событий мало: {len(A)}")
        return
    def stat(name, x):
        m = statistics.fmean(x)
        wr = sum(1 for v in x if v > 0) / len(x) * 100
        tail = statistics.fmean(sorted(x)[:max(1, len(x) // 20)])
        sd = statistics.pstdev(x)
        t = m / (sd / len(x) ** 0.5) if sd > 0 else 0.0
        print(f"  {name:<22} среднее {m:>+6.3f}R  винрейт {wr:>4.1f}%  "
              f"худшие 5% {tail:>+6.2f}R  t={t:>+5.2f}")
    print(f"ЛЕСТНИЦА ВХОДА — {len(A)} событий, {len(syms)} монет, 1h бары")
    print(f"добор на −{dip*100:.1f}% за {window} баров, удержание {hold}ч, "
          f"стоп под базой −{buffer*100:.1f}%")
    print(f"добор реально исполнялся в {fills/len(A)*100:.0f}% случаев\n")
    stat("A: один вход", A)
    stat("B: два входа", B)
    d = statistics.fmean(B) - statistics.fmean(A)
    print(f"\n  разница B−A: {d:+.3f}R за сделку")


if __name__ == "__main__":
    dip = float(sys.argv[1]) if len(sys.argv) > 1 else 0.015
    window = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    hold = int(sys.argv[3]) if len(sys.argv) > 3 else 48
    run(dip, window, hold, buffer=0.005, near=0.02, upleg=240, low_lb=120)
