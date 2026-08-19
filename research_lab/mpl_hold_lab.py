#!/usr/bin/env python3
"""Диагностика удержания MPL: сколько времени давать сделке и стоит ли тянуть.

НЕ РЕЗУЛЬТАТ, А ДИАГНОСТИКА. Пороги здесь перебираются, значит числа
годятся только для выбора правила, которое потом объявляется заранее.

Издержки честные: 16 bps круг + фандинг 1 bp за 8 часов удержания.
"""
import numpy as np, types, json

src = open("mpl_v1.py").read().replace('if __name__ == "__main__":\n    main()', '')
mod = types.ModuleType("m"); mod.__dict__['__name__'] = 'm'
exec(compile(src, "mpl_v1.py", "exec"), mod.__dict__)

FUND_PER_8H = 1.0   # bps

def sim(d, sig, hold, runner=False, ema_n=24):
    h, l, c = d["h"], d["l"], d["c"]
    ema = np.full(len(c), np.nan)
    k = 2 / (ema_n + 1); e = c[0]
    for i in range(len(c)):
        e = c[i] * k + e * (1 - k); ema[i] = e
    out = []
    for ts, i, entry, stop, lvl, a in sig:
        tgt = lvl - mod.TGT_BUF * a
        risk = entry - stop
        if risk <= 0 or tgt <= entry: continue
        limit = hold
        exitp, why, j_end = None, "time", i + hold
        j = i + 1
        while j < min(i + 1 + limit, len(h)):
            if l[j] <= stop: exitp, why, j_end = stop, "stop", j; break
            if h[j] >= tgt: exitp, why, j_end = tgt, "target", j; break
            # правило «тянем дальше»: на исходе времени продлеваем,
            # если в плюсе и импульс жив (закрытие выше EMA24)
            if runner and j == i + limit and c[j] > entry and c[j] > ema[j] and limit < 168:
                limit = min(168, limit + hold)
            j += 1
        if exitp is None:
            j_end = min(i + limit, len(h) - 1); exitp = c[j_end]
        hours = j_end - i
        cost = entry * (mod.COST_BPS + FUND_PER_8H * hours / 8) / 1e4
        out.append(dict(ts=ts, R=float((exitp - entry - cost) / risk), why=why, hours=hours))
    return out

data = mod.load(); syms = sorted(data)
for s in syms: mod.prepare(data[s])
mod.cross_rank(data, syms)
allsig = {s: mod.signals(data[s], s) for s in syms}

def rep(tag, res):
    R = np.array([r["R"] for r in res]); ts = [r["ts"] for r in res]
    lo, hi = mod.week_boot(R, ts)
    to = np.mean([r["why"] == "time" for r in res]); tg = np.mean([r["why"] == "target" for r in res])
    hrs = np.mean([r["hours"] for r in res])
    print(f"{tag:<28} n={len(R):>4}  R {R.mean():+.4f} [{lo:+.3f}..{hi:+.3f}]  "
          f"винрейт {(R>0).mean():.1%}  цель {tg:.0%}  время {to:.0%}  часов {hrs:.0f}")

print("=== СКОЛЬКО ВРЕМЕНИ ДАВАТЬ (фиксированный предел) ===")
for hold in (24, 48, 72, 120, 168):
    res = []
    for s in syms:
        if allsig[s]: res += sim(data[s], allsig[s], hold)
    rep(f"предел {hold} ч", res)

print("\n=== ПРАВИЛО «ТЯНЕМ, ЕСЛИ ИМПУЛЬС ЖИВ» (механическое) ===")
for hold in (24, 48):
    res = []
    for s in syms:
        if allsig[s]: res += sim(data[s], allsig[s], hold, runner=True)
    rep(f"старт {hold} ч + продление", res)

print("\n=== ЧТО СТАЛО С ТЕМИ, КОГО ВЫБИЛО ПО ВРЕМЕНИ НА 48 Ч ===")
res48 = []
for s in syms:
    if allsig[s]: res48 += sim(data[s], allsig[s], 48)
tmo = [r for r in res48 if r["why"] == "time"]
R = np.array([r["R"] for r in tmo])
print(f"их {len(tmo)}, средний R {R.mean():+.4f}, в плюсе {(R>0).mean():.1%}")
