#!/usr/bin/env python3
"""Контроль направления: те же сигналы, но вход в шорт.

ЗАЧЕМ. Если шорт по тем же самым сетапам тоже прибылен, значит сетап
не содержит направления, и весь плюс приходит откуда-то ещё — из общего
дрейфа рынка, из геометрии барьеров или из выборки. Это дешёвая проверка,
которая ловит целый класс самообмана.

Геометрия зеркалится точно: тот же риск в процентах, то же расстояние
до цели, то же правило удержания, те же издержки.
"""
import numpy as np, types, json
src = open("mpl_v3.py").read().replace('if __name__ == "__main__":\n    main()', '')
m = types.ModuleType("m"); m.__dict__['__name__'] = 'm'
exec(compile(src, "mpl_v3.py", "exec"), m.__dict__)

def sim_short(d, sig, slip):
    H = d["H"]; hidx = d["hidx"]; h15, l15, c15 = d["h"], d["l"], d["c"]
    rt = 2 * (m.FEE_BPS + slip); res = []
    for ts, i, entry, stop, lvl, a in sig:
        risk = entry - stop
        reward = (lvl - m.TGT_BUF * a) - entry
        if risk <= 0 or reward <= 0: continue
        s_stop, s_tgt = entry + risk, entry - reward       # зеркало
        limit = m.HOLD_H * m.PER_H
        exitp, why, jend = None, "time", i + limit
        j = i + 1
        while j < min(i + 1 + limit, len(h15)):
            if h15[j] >= s_stop: exitp, why, jend = s_stop, "stop", j; break
            if l15[j] <= s_tgt: exitp, why, jend = s_tgt, "target", j; break
            if j == i + limit and limit < m.CAP_H * m.PER_H:
                kk = hidx[j]
                if c15[j] < entry and c15[j] < H["ema"][kk]:
                    limit = min(m.CAP_H * m.PER_H, limit + m.EXTEND_H * m.PER_H)
            j += 1
        extra = 0.0
        if exitp is None:
            jend = min(i + limit, len(h15) - 1); exitp = c15[jend]; extra = m.TIME_EXIT_SLIP
        hours = (jend - i) / m.PER_H
        cost = entry * (rt + extra + m.FUND_PER_8H * hours / 8) / 1e4
        res.append(dict(ts=ts, R=float((entry - exitp - cost) / risk), why=why))
    return res

data = m.load(); syms = sorted(data)
m.TURN = {s: float(np.median(data[s]["c"] * data[s]["v"])) * 96 for s in syms}
for s in syms: m.prepare(data[s])
m.cross_rank(data, syms)
allsig = {s: m.signals(data[s]) for s in syms}

L, S = [], []
for s in syms:
    if not allsig[s]: continue
    slip = next(v for t, v in m.SLIP_TIERS if m.TURN[s] >= t)
    L += m.simulate(data[s], allsig[s], s)
    S += sim_short(data[s], allsig[s], slip)

def rep(tag, res):
    R = np.array([r["R"] for r in res])
    print(f"{tag:<22} n={len(R):>4}  R {R.mean():+.4f}  винрейт {(R>0).mean():.1%}  "
          f"цель {np.mean([r['why']=='target' for r in res]):.0%}")
    return float(R.mean())
print("КОНТРОЛЬ НАПРАВЛЕНИЯ на 2023-2025 (не заявление об эдже)\n")
a = rep("лонг (как задумано)", L)
b = rep("шорт по тем же сетапам", S)
print(f"\nсумма двух сторон: {a+b:+.4f} R")
print("если бы сетап не содержал направления, сумма была бы около")
print("минус двойных издержек, а разница сторон — около нуля")
print(f"разница сторон: {a-b:+.4f} R")
json.dump(dict(long=a, short=b, sum=a+b, diff=a-b), open("mpl_side_check.json","w"), indent=2)
