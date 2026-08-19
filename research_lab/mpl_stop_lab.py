#!/usr/bin/env python3
"""Разбор стопов MPL: где именно выбивает и что было бы, будь стоп шире.

ДИАГНОСТИКА, НЕ РЕЗУЛЬТАТ. Пороги здесь перебираются, значит числа
годятся только для того, чтобы объявить правило в V4, и не годятся
как заявление о доходности.

Считается на исправленном причинном контуре Codex: вход по открытию
следующего бара, ярус проскальзывания по скользящему обороту.
"""
import types, json
import numpy as np

src = open("mpl_v3_codex.py").read().replace('if __name__ == "__main__":\n    main()', '')
m = types.ModuleType("m"); m.__dict__['__name__'] = 'm'
exec(compile(src, "mpl_v3.py", "exec"), m.__dict__)

data = m.load(); syms = sorted(data)
m.TURN = {s: float(np.median(data[s]["c"] * data[s]["v"])) * 96 for s in syms}
for s in syms: m.prepare(data[s])
m.cross_rank(data, syms)

HOLD = m.HOLD_H * m.PER_H
CAP = m.CAP_H * m.PER_H

rows = []
for s in syms:
    d = data[s]; h, l, c = d["h"], d["l"], d["c"]
    for ts, i, entry, stop, lvl, a in m.signals(d):
        risk = entry - stop
        tgt = lvl - m.TGT_BUF * a
        if risk <= 0 or tgt <= entry: continue
        # проходим путь и записываем, что случилось
        mfe = 0.0; hit = None; j_hit = None
        for j in range(i + 1, min(i + 1 + CAP, len(h))):
            mfe = max(mfe, (h[j] - entry) / risk)
            if l[j] <= stop:
                hit, j_hit = "stop", j; break
            if h[j] >= tgt:
                hit, j_hit = "target", j; break
        if hit is None:
            j_hit = min(i + HOLD, len(h) - 1); hit = "time"
        # что было бы со стопом шире (позиция меньше, R переопределён)
        wider = {}
        for mult in (1.5, 2.0, 3.0):
            st2 = entry - risk * mult
            r2 = risk * mult
            res = None
            for j in range(i + 1, min(i + 1 + CAP, len(h))):
                if l[j] <= st2: res = -1.0; break
                if h[j] >= tgt: res = (tgt - entry) / r2; break
            if res is None:
                jj = min(i + HOLD, len(h) - 1)
                res = (c[jj] - entry) / r2
            wider[mult] = res
        # вернулась ли цена ко входу после выбивания
        back = None
        if hit == "stop":
            for j in range(j_hit + 1, min(j_hit + 24 * m.PER_H, len(h))):
                if h[j] >= entry: back = (j - j_hit) / m.PER_H; break
        rows.append(dict(sym=s, ts=ts, why=hit, mfe=float(mfe),
                         rr=(tgt - entry) / risk, risk_pct=risk / entry * 1e4,
                         hours=(j_hit - i) / m.PER_H, back=back, **{f"w{k}": v for k, v in wider.items()}))

n = len(rows)
st = [r for r in rows if r["why"] == "stop"]
print(f"сделок {n}, из них по стопу {len(st)} ({len(st)/n:.0%})\n")

print("=== 1. НАСКОЛЬКО ДАЛЕКО ЦЕНА УХОДИЛА В ПЛЮС ПЕРЕД ТЕМ, КАК ВЫБИЛО")
print("    (MFE в долях риска: 0.0 = сразу вниз, 1.0 = прошла целый риск вверх)")
mf = np.array([r["mfe"] for r in st])
for lo, hi, lab in ((0, .1, "почти сразу вниз (0-0.1R)"), (.1, .5, "0.1-0.5R"),
                    (.5, 1.0, "0.5-1.0R"), (1.0, 99, "больше 1R — была в хорошем плюсе")):
    k = ((mf >= lo) & (mf < hi)).sum()
    print(f"    {lab:<38} {k:>5}  {k/len(st):>5.0%}")
print(f"    медианный MFE перед стопом: {np.median(mf):.2f}R")

print("\n=== 2. СКОЛЬКО ПРОШЛИ БОЛЬШУЮ ЧАСТЬ ПУТИ К ЦЕЛИ И РАЗВЕРНУЛИСЬ")
rr = np.array([r["rr"] for r in st])
frac = mf / rr
for thr in (0.5, 0.7, 0.9):
    k = (frac >= thr).sum()
    print(f"    дошли до {thr:.0%} расстояния до цели и всё равно выбило: {k:>4}  {k/len(st):>5.0%}")

print("\n=== 3. ВОЗВРАЩАЕТСЯ ЛИ ЦЕНА КО ВХОДУ ПОСЛЕ ВЫБИВАНИЯ (за 24 ч)")
bk = [r["back"] for r in st]
ok = [x for x in bk if x is not None]
print(f"    вернулась: {len(ok)}/{len(st)} = {len(ok)/len(st):.0%}, медиана через {np.median(ok):.1f} ч")

print("\n=== 4. ЧТО БЫЛО БЫ СО СТОПОМ ШИРЕ (R переопределён под новый стоп)")
base = np.array([1.0 if r["why"] == "target" else (-1.0 if r["why"] == "stop" else 0.0) for r in rows])
print(f"{'стоп':<12}{'R/сделку (до издержек)':>26}{'винрейт':>10}")
cur = np.array([(r["rr"] if r["why"] == "target" else (-1.0 if r["why"] == "stop" else 0.0)) for r in rows])
print(f"{'как сейчас':<12}{cur.mean():>+26.4f}{(cur>0).mean():>10.1%}")
for mult in (1.5, 2.0, 3.0):
    x = np.array([r[f"w{mult}"] for r in rows])
    print(f"{'x'+str(mult):<12}{x.mean():>+26.4f}{(x>0).mean():>10.1%}")
print("\n    ВНИМАНИЕ: числа тут БЕЗ издержек и без фандинга. При более")
print("    широком стопе позиция меньше, поэтому издержки в долях R растут")
print("    примерно во столько же раз — это учитывать в V4 отдельно.")
json.dump(dict(n=n, stops=len(st), mfe_median=float(np.median(mf)),
               back_frac=len(ok)/len(st)), open("mpl_stop_lab.json","w"), indent=2)

print("\n=== 5. ЧЕСТНЫЙ ПЕРЕСЧЁТ: полный контур с издержками, стоп шире")
print("    (издержки в долях R ПАДАЮТ при широком стопе: позиция меньше)")
print(f"{'стоп':<10}{'сделок':>8}{'R/сделку':>11}{'винрейт':>10}{'цель':>8}{'изд. в R':>10}")
for mult in (1.0, 1.25, 1.5, 2.0, 3.0):
    allr = []; costR = []
    for s in syms:
        d = data[s]
        sig = []
        for ts, i, entry, stop, lvl, a in m.signals(d):
            sig.append((ts, i, entry, entry - (entry - stop) * mult, lvl, a))
        if not sig: continue
        res = m.simulate(d, sig, s)
        allr += res
        for r in res:
            costR.append(r.get("slip_bps", 4.0) * 2 + 12.0)
    if not allr: continue
    R = np.array([r["R"] for r in allr])
    rp = np.array([r["risk_pct"] for r in allr])
    cst = np.array(costR) / 1e4 / rp
    print(f"{'x'+str(mult):<10}{len(R):>8}{R.mean():>+11.4f}{(R>0).mean():>10.1%}"
          f"{np.mean([r['why']=='target' for r in allr]):>8.0%}{cst.mean():>10.4f}")
