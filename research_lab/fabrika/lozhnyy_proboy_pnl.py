#!/usr/bin/env python3
"""Ложный пробой — единственный PnL-тест (PREREG_LOZHNYY_PROBOY_PNL_2026_10_12.md @ 648d2ae).
Сначала паритет: число событий до фильтров обязано совпасть с IZMERENIYA.json (20 881), иначе стоп без расчёта R."""
import datetime as dt, glob, hashlib, json, math, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB / "fabrika"))
import lozhnyy_proboy_izmereniya as IZ
H = 3_600_000; HOLD = 48; DRAWS = 20; KOST = 0.0016; KOST_STRESS = 0.0030; SER = 1751328000000   # 2025-07-01
OUT = LAB / "data/lozhnyy_proboy"


def sobytiya_s_indeksami(ts, o, h, l, c, v):
    """Та же логика, что IZ.sobytiya, плюс индексы и цены. Совпадение числа событий проверяется в main."""
    a = IZ.atr14(h, l, c); out = []; posl = {+1: -10**18, -1: -10**18}; n = len(c)
    for t in range(IZ.OKNO + IZ.ISKL + 1, n - IZ.K_PROVAL - 1):
        if not (IZ.T0 <= ts[t] < IZ.T1) or not np.isfinite(a[t]): continue
        if ts[t] - ts[t - IZ.OKNO - IZ.ISKL] != (IZ.OKNO + IZ.ISKL) * H: continue
        lo_w, hi_w = l[t - IZ.OKNO - IZ.ISKL:t - IZ.ISKL], h[t - IZ.OKNO - IZ.ISKL:t - IZ.ISKL]
        for st, uroven, proboy in ((+1, hi_w.max(), c[t] > hi_w.max() + IZ.BUF * a[t]), (-1, lo_w.min(), c[t] < lo_w.min() - IZ.BUF * a[t])):
            if not proboy or ts[t] - posl[st] < IZ.PAUZA * H: continue
            f = next((j for j in range(t + 1, t + 1 + IZ.K_PROVAL) if (c[j] < uroven if st > 0 else c[j] > uroven)), None)
            if f is None or f + 1 >= n or ts[f + 1] - ts[f] != H: continue
            vhod = o[f + 1]
            stop = (h[t:f + 1].max() + IZ.BUF * a[f]) if st > 0 else (l[t:f + 1].min() - IZ.BUF * a[f])
            risk = (stop - vhod) if st > 0 else (vhod - stop)
            med_v = np.median(v[t - 24:t]) if t >= 24 else np.nan
            out.append(dict(t=t, f=f, st=st, vhod=vhod, stop=stop, cel=(hi_w.max() + lo_w.min()) / 2, risk=risk,
                            vr=float(v[t] / med_v) if med_v > 0 else None, ts=int(ts[t])))
            posl[st] = ts[f]
    return out


def sdelka(ts, o, h, l, c, i, st, vhod, stop, cel):
    """st=+1 шорт (пробой вверх), −1 лонг. Возврат (R_цены, j_выхода, причина) или None, если нет 48 непрерывных баров."""
    if i + HOLD > len(c) or ts[i + HOLD - 1] - ts[i] != (HOLD - 1) * H: return None
    risk = (stop - vhod) if st > 0 else (vhod - stop)
    for j in range(i, i + HOLD):
        if st > 0:
            if h[j] >= stop: return ((vhod - max(stop, o[j])) / risk, j, "stop")
            if l[j] <= cel: return ((vhod - cel) / risk, j, "cel")
        else:
            if l[j] <= stop: return ((min(stop, o[j]) - vhod) / risk, j, "stop")
            if h[j] >= cel: return ((cel - vhod) / risk, j, "cel")
    j = i + HOLD - 1
    return (((vhod - c[j]) if st > 0 else (c[j] - vhod)) / risk, j, "vremya")


class Fanding:
    """Тот же календарь A6, что раньше (s_a = последний расчёт ≤ входа, ≥ 10 интервалов до него, s_b = первый ≥ выхода,
    все интервалы на [s_a, s_b] ≤ медианы 10 последних до s_a), но через bisect и префиксные суммы."""
    def __init__(self, S):
        self.ts = np.array([x for x, _ in S], dtype=np.int64); r = np.array([y for _, y in S], dtype=float)
        self.cum = np.r_[0.0, np.cumsum(r)]; d = np.diff(self.ts)
        self.d = d                                                  # d[k] = ts[k+1] − ts[k]

    def r(self, t_vhod, t_vyh, st, lev):
        ts = self.ts
        if len(ts) == 0: return None
        a = int(np.searchsorted(ts, t_vhod, side="right")) - 1     # индекс последнего ≤ t_vhod
        b = int(np.searchsorted(ts, t_vyh, side="left"))           # индекс первого ≥ t_vyh
        if a < 10 or b >= len(ts): return None
        g0 = float(np.median(self.d[a - 10:a]))                     # 10 интервалов, заканчивающихся на s_a
        if (self.d[a:b] > g0).any(): return None
        i0 = int(np.searchsorted(ts, t_vhod, side="right")); i1 = int(np.searchsorted(ts, t_vyh, side="right"))
        return st * (self.cum[i1] - self.cum[i0]) * lev           # шорт (st=+1) получает положительную ставку


def main():
    vse_do = 0; rows = []; fu_unk = 0; otk_lev = 0; otk_vr = 0; net = 0
    for fpath in sorted(glob.glob(str(LAB / "data/h1/*.npz"))):
        sym = Path(fpath).stem
        if sym in IZ.DEV13: continue
        z = np.load(fpath); ts = z["ts"].astype(np.int64); x = z["ohlcv"].astype(float)
        if ts[-1] < IZ.T0: continue
        o, h, l, c, v = x[:, 0], x[:, 1], x[:, 2], x[:, 3], x[:, 4]
        ev = sobytiya_s_indeksami(ts, o, h, l, c, v); vse_do += len(ev)
        pf = LAB / "data/pit_daily" / f"{sym}.json"
        FD = Fanding(sorted((int(a), float(b)) for a, b in json.load(open(pf))["funding"])) if pf.exists() else None
        mes = defaultdict(list)
        ym = lambda tt: dt.datetime.fromtimestamp(int(tt) / 1000, dt.timezone.utc).strftime("%Y-%m")
        for k in range(len(ts) - HOLD):
            mes[ym(ts[k])].append(k)                                    # пул: тот же календарный месяц (UTC)
        for e in ev:
            if e["vr"] is None or e["vr"] < 1.5: otk_vr += 1; continue
            lev = e["vhod"] / e["risk"]
            if lev > 100: otk_lev += 1; continue
            i = e["f"] + 1
            r = sdelka(ts, o, h, l, c, i, e["st"], e["vhod"], e["stop"], e["cel"])
            if r is None: net += 1; continue
            fr = FD.r(int(ts[i]), int(ts[r[1]]) + H, e["st"], lev) if FD else None
            if fr is None: fu_unk += 1; continue
            R = r[0] - lev * KOST + fr; Rs = r[0] - lev * KOST_STRESS + fr
            ds, dc = e["risk"] / e["vhod"], abs(e["vhod"] - e["cel"]) / e["vhod"]
            rng = np.random.default_rng(int(hashlib.sha256(f"{sym}|{e['ts']}".encode()).hexdigest()[:12], 16))
            pool = mes[ym(ts[i])]; kr = []
            for _ in range(DRAWS * 3):
                if len(kr) >= DRAWS or not pool: break
                k = int(rng.choice(pool)); vk = o[k]
                stp = vk * (1 + ds) if e["st"] > 0 else vk * (1 - ds); cl = vk * (1 - dc) if e["st"] > 0 else vk * (1 + dc)
                rk = sdelka(ts, o, h, l, c, k, e["st"], vk, stp, cl)
                if rk is None: continue
                fk = FD.r(int(ts[k]), int(ts[rk[1]]) + H, e["st"], lev)
                if fk is None: continue
                kr.append(rk[0] - lev * KOST + fk)
            if len(kr) < 5: net += 1; continue
            rows.append(dict(s=sym, ts=e["ts"], st=e["st"], bar=e["f"] - e["t"], R=R, Rs=Rs, izb=R - float(np.mean(kr)), prich=r[2]))
    ozhid = json.load(open(OUT / "IZMERENIYA.json"))["sobytiy"]
    if vse_do != ozhid:
        print("ПАРИТЕТ ОПРЕДЕЛЕНИЯ FAIL", vse_do, ozhid); (OUT / "PNL_ITOG.json").write_text(json.dumps(dict(status="BLOCKED_PARITY", vse=vse_do, ozhid=ozhid))); return 2
    n = len(rows); R = np.array([x["R"] for x in rows]); I = np.array([x["izb"] for x in rows])
    def t_klaster(idx):
        if not idx: return None
        sub = [rows[i] for i in idx]; m = float(np.mean([x["izb"] for x in sub])); g = defaultdict(float)
        for x in sub: g[x["s"]] += x["izb"] - m
        se = math.sqrt(sum(v * v for v in g.values())) / len(sub); return dict(n=len(sub), sred_izb=round(m, 4), t=round(m / se, 2) if se > 0 else None)
    vse_i = list(range(n)); p1 = [i for i in vse_i if rows[i]["ts"] < SER]; p2 = [i for i in vse_i if rows[i]["ts"] >= SER]
    tk, h1, h2 = t_klaster(vse_i), t_klaster(p1), t_klaster(p2)
    fu_dolya = fu_unk / max(1, n + fu_unk)
    if fu_dolya > 0.05: verdikt = "BLOCKED_DATA"
    elif n >= 300 and R.mean() > 0 and tk["t"] is not None and tk["t"] >= 2.5 and h1 and h2 and np.sign(h1["sred_izb"]) == np.sign(h2["sred_izb"]) == np.sign(tk["sred_izb"]):
        verdikt = "PASS_KANDIDAT"
    else: verdikt = "FAIL"
    opis = lambda f: (lambda idx: dict(n=len(idx), sred_R=round(float(R[idx].mean()), 4) if idx else None, **({"t": t_klaster(idx)["t"]} if idx else {})))([i for i in vse_i if f(rows[i])])
    rez = dict(prereg="PREREG_LOZHNYY_PROBOY_PNL_2026_10_12.md @ 648d2ae", verdikt=verdikt, sobytiy_do_filtrov=vse_do,
               otkaz_vol=otk_vr, otkaz_lev=otk_lev, net_dannyh_ili_kontrolya=net, funding_unknown=fu_unk, funding_unknown_dolya=round(fu_dolya, 4),
               n=n, sred_net_R=round(float(R.mean()), 4), summa_R=round(float(R.sum()), 1), pf=round(float(R[R > 0].sum() / -R[R < 0].sum()), 3),
               izbytok=tk, polovina_1=h1, polovina_2=h2,
               opisatelno=dict(stress_sred=round(float(np.mean([x["Rs"] for x in rows])), 4),
                               verh_short=opis(lambda x: x["st"] > 0), niz_long=opis(lambda x: x["st"] < 0),
                               bar1=opis(lambda x: x["bar"] == 1), bar2=opis(lambda x: x["bar"] == 2), bar3=opis(lambda x: x["bar"] == 3),
                               vyhody={p: sum(1 for x in rows if x["prich"] == p) for p in ("stop", "cel", "vremya")}))
    (OUT / "PNL_ITOG.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1)); print(json.dumps(rez, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
