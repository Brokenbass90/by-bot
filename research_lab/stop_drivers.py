#!/usr/bin/env python3
"""stop_drivers.py — систематический поиск того, что предсказывает стоп.

ПОЧЕМУ ЭТОТ СКРИПТ СУЩЕСТВУЕТ. Четыре версии про красные месяцы были
проверены руками и отклонены. Четыре — это не поиск, это четыре тычка.
Здесь считаются ВСЕ признаки, которые можно посчитать на момент входа,
и каждый проверяется одинаково.

Признаки (все causal — только данные до входа включительно):
    рынок:   волатильность BTC 24/72/168 ч, доходность BTC 24/72/168 ч,
             отклонение BTC от EMA200, |отклонение|
    монета:  своя волатильность, своя доходность 24/72/168 ч,
             объём против среднего, корреляция с BTC за 168 ч
    сделка:  плечо, расстояние входа от стопа в ATR, час суток UTC,
             день недели, сколько своих сделок открыто в этот час
             (скученность), сколько своих сделок было за прошлые 24 ч

Для каждого признака: делим сделки на четыре части по его величине
и смотрим долю стопов и средний итог в каждой части, ОТДЕЛЬНО
на двух окнах.

КРИТЕРИЙ, ОБЪЯВЛЕННЫЙ ДО ПРОГОНА. Признак считается кандидатом,
только если одновременно:
  1. разница долей стопов между худшей и лучшей четвертью >= 5 пп
     НА ОБОИХ окнах;
  2. знак направления совпадает на обоих окнах;
  3. разница средних итогов между крайними четвертями >= 0.03R
     на обоих окнах.

Признаков около двадцати, поэтому поправка на множественность
обязательна: даже при выполнении всех трёх условий признак идёт
в кандидаты, а не в правила.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REG = {"ATT1": "флет-", "SBR1": "флет+"}
PRIO = {"SBR1": 0, "ATT1": 1}
SLOTS, WIN_H = 12, 6
W = {"окно1": (1709251200000, 1759276800000), "окно2": (1672531200000, 1709251200000)}


def ema(x, n):
    k = 2 / (n + 1); e = x[0]; o = np.empty(len(x))
    for i, v in enumerate(x):
        e = v * k + e * (1 - k); o[i] = e
    return o


def main():
    tr = json.loads((ROOT / "research_lab/orch_signals.json").read_text(encoding="utf-8"))
    pool = [t for t in tr if t["reg"] == REG.get(t["leg"])]
    b = {}
    for t in pool:
        b.setdefault(t["ts"] // (WIN_H * 3600000), []).append(t)
    pool = []
    for k in sorted(b):
        pool.extend(sorted(b[k], key=lambda x: (PRIO.get(x["leg"], 9), x["ts"])))
    op, tk = [], []
    for t in pool:
        op = [x for x in op if x[0] > t["ts"]]
        if any(x[1] == t["sym"] for x in op) or len(op) >= SLOTS:
            continue
        op.append((t["ts"] + t["hours"] * 3600000, t["sym"]))
        t["open_now"] = len(op)
        tk.append(t)
    tk.sort(key=lambda x: x["ts"])
    print(f"сделок в портфеле: {len(tk)}")

    # --- рынок
    d = np.load(ROOT / "research_lab/data/h1/BTCUSDT.npz")
    bts = d["ts"]; bc = d["ohlcv"][:, 3].astype(float)
    bem = ema(bc, 200)
    lr = np.concatenate([[0.0], np.diff(np.log(bc))])
    def roll_std(n):
        out = np.full(len(bc), np.nan)
        cs = np.cumsum(lr); cs2 = np.cumsum(lr ** 2)
        for i in range(n, len(bc)):
            m = (cs[i] - cs[i - n]) / n
            out[i] = math_sqrt(max(0.0, (cs2[i] - cs2[i - n]) / n - m * m)) * 100
        return out
    def math_sqrt(x):
        return x ** 0.5
    bvol = {n: roll_std(n) for n in (24, 72, 168)}
    bret = {n: np.concatenate([np.full(n, np.nan), (bc[n:] / bc[:-n] - 1) * 100])
            for n in (24, 72, 168)}
    bdist = (bc - bem) / bem * 100

    # --- по монетам
    cache = {}
    for t in tk:
        s = t["sym"]
        if s not in cache:
            p = ROOT / f"research_lab/data/h1/{s}.npz"
            if not p.exists():
                cache[s] = None; continue
            dd = np.load(p); ts = dd["ts"]; o = dd["ohlcv"].astype(float)
            c2 = o[:, 3]; h, l = o[:, 1], o[:, 2]
            pc = np.concatenate([[c2[0]], c2[:-1]])
            trr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
            atr = np.convolve(trr, np.ones(14) / 14, mode="same")
            vol = o[:, 4]
            vavg = np.convolve(vol, np.ones(20) / 20, mode="same")
            r24 = np.concatenate([np.full(24, np.nan), (c2[24:] / c2[:-24] - 1) * 100])
            r72 = np.concatenate([np.full(72, np.nan), (c2[72:] / c2[:-72] - 1) * 100])
            cache[s] = dict(ts=ts, c=c2, atr=atr, vol=vol, vavg=vavg, r24=r24, r72=r72)
    def at(arr, tsarr, t):
        j = max(0, int(np.searchsorted(tsarr, t, side="right")) - 1)
        return float(arr[j]) if j < len(arr) else np.nan

    prev24 = []
    for t in tk:
        prev24 = [x for x in prev24 if x > t["ts"] - 86400000]
        t["own24"] = len(prev24); prev24.append(t["ts"])
        f = {}
        for n in (24, 72, 168):
            f[f"вола BTC {n}ч"] = at(bvol[n], bts, t["ts"])
            f[f"ход BTC {n}ч %"] = at(bret[n], bts, t["ts"])
        f["откл BTC от EMA200"] = at(bdist, bts, t["ts"])
        f["|откл| BTC"] = abs(at(bdist, bts, t["ts"]))
        cc = cache.get(t["sym"])
        if cc:
            a = at(cc["atr"], cc["ts"], t["ts"]); c0 = at(cc["c"], cc["ts"], t["ts"])
            f["вола монеты (ATR/цена)"] = a / c0 * 100 if c0 else np.nan
            f["ход монеты 24ч %"] = at(cc["r24"], cc["ts"], t["ts"])
            f["ход монеты 72ч %"] = at(cc["r72"], cc["ts"], t["ts"])
            v0 = at(cc["vol"], cc["ts"], t["ts"]); va = at(cc["vavg"], cc["ts"], t["ts"])
            f["объём против среднего"] = v0 / va if va else np.nan
        f["плечо сделки"] = t["lev"]
        f["час суток UTC"] = (t["ts"] // 3600000) % 24
        f["день недели"] = (t["ts"] // 86400000 + 4) % 7
        f["открыто позиций"] = t["open_now"]
        f["своих сделок за 24ч"] = t["own24"]
        t["f"] = f

    names = sorted(tk[0]["f"].keys())
    print(f"признаков: {len(names)}\n")
    print(f"{'признак':<26}{'окно':<7}{'стопы: низ->верх':<20}{'разброс':>9}"
          f"{'итог: низ->верх':<22}{'разница':>9}")
    cand = []
    for nm in names:
        rows = {}
        for w, (a, b2) in W.items():
            g = [t for t in tk if a <= t["ts"] < b2 and not np.isnan(t["f"].get(nm, np.nan))]
            if len(g) < 120:
                continue
            v = np.array([t["f"][nm] for t in g])
            R = np.array([t["R"] for t in g])
            S = (R < -0.9).astype(float)
            qs = np.percentile(v, [25, 50, 75])
            idx = [(v <= qs[0]), (v > qs[0]) & (v <= qs[1]),
                   (v > qs[1]) & (v <= qs[2]), (v > qs[2])]
            st = [S[i].mean() for i in idx if i.sum() > 15]
            rr = [R[i].mean() for i in idx if i.sum() > 15]
            if len(st) < 4:
                continue
            rows[w] = (st, rr)
            print(f"{nm:<26}{w:<7}" +
                  "".join(f"{x*100:>4.0f}%" for x in st) + " " * 0 +
                  f"{(max(st)-min(st))*100:>8.0f}пп " +
                  "".join(f"{x:>+6.3f}" for x in rr) +
                  f"{max(rr)-min(rr):>+9.3f}")
        if len(rows) == 2:
            (s1, r1), (s2, r2) = rows["окно1"], rows["окно2"]
            d1, d2 = s1[-1] - s1[0], s2[-1] - s2[0]
            e1, e2 = r1[-1] - r1[0], r2[-1] - r2[0]
            if (abs(d1) >= 0.05 and abs(d2) >= 0.05 and np.sign(d1) == np.sign(d2)
                    and abs(e1) >= 0.03 and abs(e2) >= 0.03 and np.sign(e1) == np.sign(e2)):
                cand.append((nm, d1, d2, e1, e2))
        print()
    print("\n╔══ КАНДИДАТЫ (все три условия выполнены на обоих окнах)")
    if not cand:
        print("  ни одного")
    for nm, d1, d2, e1, e2 in cand:
        print(f"  {nm:<26} стопы {d1*100:+.0f}пп / {d2*100:+.0f}пп   "
              f"итог {e1:+.3f}R / {e2:+.3f}R")


if __name__ == "__main__":
    main()
