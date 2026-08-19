#!/usr/bin/env python3
"""Выбор правила удержания по УСТОЙЧИВОСТИ, а не по среднему.

Замечание аудита принято: выбирать hold по максимуму среднего R —
это подгонка. Здесь критерий объявлен ДО просмотра таблицы:
  выигрывает вариант с лучшим ХУДШИМ годом, при равенстве —
  с лучшим нижним краем недельного бутстрапа.

Издержки: 16 bps круг + фандинг 1 bp/8ч + 2 bps проскальзывания
на принудительном выходе по времени (замечание аудита).
"""
import numpy as np, types

src = open("mpl_v1.py").read().replace('if __name__ == "__main__":\n    main()', '')
mod = types.ModuleType("m"); mod.__dict__['__name__'] = 'm'
exec(compile(src, "mpl_v1.py", "exec"), mod.__dict__)

FUND_PER_8H = 1.0
TIME_EXIT_SLIP = 2.0
EMA_HOURS = 24            # период задан В ЧАСАХ, чтобы пережить смену таймфрейма

def sim(d, sig, hold, runner=False, cap=168, unlimited=False):
    h, l, c = d["h"], d["l"], d["c"]
    n_ema = EMA_HOURS
    ema = np.empty(len(c)); k = 2 / (n_ema + 1); e = c[0]
    for i in range(len(c)):
        e = c[i] * k + e * (1 - k); ema[i] = e
    out = []
    for ts, i, entry, stop, lvl, a in sig:
        tgt = lvl - mod.TGT_BUF * a
        risk = entry - stop
        if risk <= 0 or tgt <= entry: continue
        limit = 10**6 if unlimited else hold
        exitp, why, j_end = None, "time", i + limit
        j = i + 1
        while j < min(i + 1 + limit, len(h)):
            if l[j] <= stop: exitp, why, j_end = stop, "stop", j; break
            if h[j] >= tgt: exitp, why, j_end = tgt, "target", j; break
            if runner and j == i + limit and c[j] > entry and c[j] > ema[j] and limit < cap:
                limit = min(cap, limit + hold)
            j += 1
        slip = 0.0
        if exitp is None:
            j_end = min(i + limit, len(h) - 1); exitp = c[j_end]; slip = TIME_EXIT_SLIP
        hours = j_end - i
        cost = entry * (mod.COST_BPS + slip + FUND_PER_8H * hours / 8) / 1e4
        out.append(dict(ts=ts, R=float((exitp - entry - cost) / risk), why=why, hours=hours))
    return out

data = mod.load(); syms = sorted(data)
for s in syms: mod.prepare(data[s])
mod.cross_rank(data, syms)
allsig = {s: mod.signals(data[s], s) for s in syms}
YR = {"2023": (0, 1704067200000), "2024": (1704067200000, 1735689600000), "2025": (1735689600000, 9e12)}

def line(tag, res):
    R = np.array([r["R"] for r in res]); ts = np.array([r["ts"] for r in res])
    lo, hi = mod.week_boot(R, ts)
    ys = []
    for y, (a, b) in YR.items():
        m = (ts >= a) & (ts < b)
        ys.append(R[m].mean() if m.sum() >= 30 else np.nan)
    worst = np.nanmin(ys)
    print(f"{tag:<26} n={len(R):>4} R {R.mean():+.4f} низ {lo:+.3f}  "
          f"годы {ys[0]:+.3f}/{ys[1]:+.3f}/{ys[2]:+.3f}  ХУДШИЙ {worst:+.3f}  "
          f"время {np.mean([r['why']=='time' for r in res]):.0%}")
    return worst, lo

print("КРИТЕРИЙ ОБЪЯВЛЕН ДО ПРОСМОТРА: лучший ХУДШИЙ год, потом нижний край\n")
best = None
for hold in (24, 48, 72, 120, 168):
    res = []
    for s in syms:
        if allsig[s]: res += sim(data[s], allsig[s], hold)
    w, lo = line(f"предел {hold} ч", res)
    if best is None or (w, lo) > best[0]: best = ((w, lo), f"предел {hold} ч")
print()
for hold in (24, 48, 72):
    res = []
    for s in syms:
        if allsig[s]: res += sim(data[s], allsig[s], hold, runner=True)
    w, lo = line(f"{hold} ч + продление", res)
    if (w, lo) > best[0]: best = ((w, lo), f"{hold} ч + продление")
print(f"\nПОБЕДИТЕЛЬ ПО ОБЪЯВЛЕННОМУ КРИТЕРИЮ: {best[1]}  "
      f"(худший год {best[0][0]:+.3f}, нижний край {best[0][1]:+.3f})")

print("\n=== ЧТО БЫЛО БЫ С ТАЙМАУТАМИ, ЕСЛИ ИХ НЕ ЗАКРЫВАТЬ ===")
for hold in (48, 72):
    lim, unl = [], []
    for s in syms:
        if not allsig[s]: continue
        a = sim(data[s], allsig[s], hold); b = sim(data[s], allsig[s], hold, unlimited=True)
        for x, y in zip(a, b):
            if x["why"] == "time": lim.append(x); unl.append(y)
    Rl = np.array([r["R"] for r in lim]); Ru = np.array([r["R"] for r in unl])
    tg = np.mean([r["why"] == "target" for r in unl])
    print(f"предел {hold} ч: таймаутов {len(lim)}, при закрытии R {Rl.mean():+.3f}, "
          f"без предела R {Ru.mean():+.3f}, из них дошли до цели {tg:.0%}, "
          f"среднее время {np.mean([r['hours'] for r in unl]):.0f} ч")
