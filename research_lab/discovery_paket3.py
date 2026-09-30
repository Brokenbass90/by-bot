#!/usr/bin/env python3
"""discovery_paket3.py — пачка Discovery №3, часть А: временная структура (квартальные фьючерсы Bybit).
Правило экрана то же (discovery_paket1.itog). Данные: data/kvartaly (выгрузка 30.09), перп — pit_daily.
Осторожно: обороты квартальных контрактов малы (BTC ~10 BTC/сутки), дневное закрытие может быть
несвежим — поэтому базис берётся только по дням с оборотом > 0 и |базис| < 5%.
    python3 research_lab/discovery_paket3.py
"""
import glob, json, sys
import numpy as np
import discovery_paket1 as P

D, DEN = P.D, P.DEN
KOM_DVE_NOGI = 22e-4     # 4 тейкер-исполнения фьючерс+перп


def kontrakty():
    K = {}
    for f in glob.glob(str(D / "kvartaly/*.json")):
        if f.endswith("_net_dannyh.json"):
            continue
        d = json.load(open(f)); a = np.array(d["daily"], float)
        if len(a) < 30:
            continue
        base = d["symbol"].split("-")[0].replace("USDT", "")
        K[d["symbol"]] = dict(base=base, ts=a[:, 0].astype(np.int64), c=a[:, 4], v=a[:, 5], ekspir=int(a[-1, 0]))
    return K


def ryad(M, K):
    """по каждому контракту и дню: базис к перпу и дней до экспирации"""
    out = []
    for s, k in K.items():
        x = M.get(k["base"] + "USDT")
        if x is None:
            continue
        pm = dict(zip(x["ts"].tolist(), x["c"].tolist()))
        for i, t in enumerate(k["ts"]):
            p = pm.get(int(t)); dte = (k["ekspir"] - t) / DEN
            if not p or k["v"][i] <= 0 or dte < 1:
                continue
            b = k["c"][i] / p - 1
            if abs(b) < 0.05:
                out.append(dict(s=s, base=k["base"], t=int(t), i=i, b=b, dte=dte, ann=b * 365 / dte))
    return out


def T1(M, K, R):
    """TERM_CARRY: годовой базис ≥ 8% → шорт фьючерса + лонг перпа до экспирации (сходимость гарантирована
    поставкой; лонг перпа платит фандинг — это и есть цена). Одно вхождение на контракт."""
    sob, vzyat = [], set()
    for r in sorted(R, key=lambda z: z["t"]):
        if r["s"] in vzyat or r["ann"] < 0.08 or not (14 <= r["dte"] <= 120):
            continue
        k = K[r["s"]]; x = M[r["base"] + "USDT"]
        j = int(np.searchsorted(x["ts"], k["ekspir"]))
        if j >= len(x["ts"]) or x["ts"][j] != k["ekspir"]:
            continue
        i = int(np.searchsorted(x["ts"], r["t"]))
        fut = -(k["c"][-1] / k["c"][r["i"]] - 1); perp = x["c"][j] / x["c"][i] - 1
        fand = -P.fand(x, r["t"], k["ekspir"])
        sob.append((r["t"], fut + perp + fand - KOM_DVE_NOGI, None)); vzyat.add(r["s"])
    return P.itog(sob, s_kontrolem=False)


def T2(M, K, R):
    """TERM_SIGNAL: годовой базис ближнего контракта в верхнем дециле своих 90 дней (плечевые лонги
    переплачивают за срок) → шорт перпа 7 дней; в нижнем дециле → лонг. Только BTC и ETH."""
    sob = []
    for base in ("BTC", "ETH"):
        x = M[base + "USDT"]
        bl = {}
        for r in R:
            if r["base"] == base and 14 <= r["dte"] <= 120:
                if r["t"] not in bl or r["dte"] < bl[r["t"]]["dte"]:
                    bl[r["t"]] = r
        ts = sorted(bl); ann = np.array([bl[t]["ann"] for t in ts]); blok = -1
        for n in range(90, len(ts)):
            okno = ann[n - 90:n]; hi, lo = np.percentile(okno, 90), np.percentile(okno, 10)
            side = -1 if ann[n] > hi else (1 if ann[n] < lo else 0)
            i = int(np.searchsorted(x["ts"], ts[n]))
            if side == 0 or i <= blok or i >= len(x["ts"]) or x["ts"][i] != ts[n]:
                continue
            r = P.sdelka(x, i, 7, side)
            if r is not None:
                sob.append((ts[n], r, None)); blok = i + 7
    return P.itog(sob, s_kontrolem=False)


def T3(M, K, R):
    """ROLL_PRESSURE: за 10 дней до экспирации держатели длинных фьючерсов перекатываются — продают
    ближний. Шорт ближнего + лонг перпа с T−10 до T−1."""
    sob = []
    for s, k in K.items():
        x = M.get(k["base"] + "USDT")
        if x is None:
            continue
        t0, t1 = k["ekspir"] - 10 * DEN, k["ekspir"] - DEN
        i0, i1 = np.searchsorted(k["ts"], [t0, t1]); j0, j1 = np.searchsorted(x["ts"], [t0, t1])
        if i1 >= len(k["ts"]) or k["ts"][i0] != t0 or k["ts"][i1] != t1 or j1 >= len(x["ts"]) or x["ts"][j0] != t0 \
                or x["ts"][j1] != t1 or k["v"][i0] <= 0:
            continue
        r = -(k["c"][i1] / k["c"][i0] - 1) + (x["c"][j1] / x["c"][j0] - 1) - P.fand(x, t0, t1) - KOM_DVE_NOGI
        sob.append((int(t0), r, None))
    return P.itog(sob, s_kontrolem=False)


if __name__ == "__main__":
    M = P.zagruzit_kripto(); K = kontrakty(); R = ryad(M, K)
    print("контрактов", len(K), "наблюдений базиса", len(R),
          "годовой базис медиана", round(float(np.median([r["ann"] for r in R])) * 100, 1), "%")
    rez = {}
    for k, f in [("T1", T1), ("T2", T2), ("T3", T3)]:
        rez[k] = f(M, K, R); print(k, rez[k], flush=True)
    json.dump(rez, open(D / "discovery_paket3.json", "w"), ensure_ascii=False, indent=1)
