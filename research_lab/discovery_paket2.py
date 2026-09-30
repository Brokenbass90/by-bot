#!/usr/bin/env python3
"""discovery_paket2.py — дешёвый экран пачки Discovery №2 (DISCOVERY_PAKET2_2026_09_30.md).

То же правило, что в пачке 1, без изменений (discovery_paket1.itog): SURVIVED = эдж после издержек > 0,
t по кластерам дат ≥ 2, обе хронологические половины > 0, сырой доход > 0. Иначе KILLED.
Цель пачки — семейства, НЕЗАВИСИМЫЕ от PEREGREV_HVOSTA.

Данные: pit_daily (+фандинг), basis/oi_sutochnyy, спот дневной 74 монеты (2023…2025-09),
5-минутки 99 монет (2024-03…2025-09, кэш строится сам в ~/.cache/discovery_m5), h1 для Polymarket.

    python3 research_lab/discovery_paket2.py [D1 D2 ...]
"""
import glob, json, math, os, re, sys, datetime as dt
from collections import defaultdict
import numpy as np
import discovery_paket1 as P

D = P.D; DEN = P.DEN; rng = np.random.default_rng(11)
M5_SRC = D / "bybit_wide137_m5_preholdout_20240301_20250930"
M5_KESH = os.path.expanduser("~/.cache/discovery_m5")
SPOT = D / "bybit_spot_daily_preholdout_2023_20250930/bars"
KOM_PARA = 31e-4          # четыре исполнения спот+перп (как в прошлом аудите carry), доля
POROG_F = 3e-4            # «сильный» фандинг за одну выплату: 0.03%


def m5(s):
    os.makedirs(M5_KESH, exist_ok=True)
    k = f"{M5_KESH}/{s}.npz"
    if not os.path.exists(k):
        p = M5_SRC / s / f"{s}.json"
        r = json.load(open(p))["records"] if p.exists() else []
        a = np.array([[x["ts_ms"], x["open"]] for x in r], float) if r else np.zeros((0, 2))
        np.savez(k, ts=a[:, 0].astype(np.int64), o=a[:, 1])
    z = np.load(k); return z["ts"], z["o"]


def cena_m5(ts, o, t):
    i = int(np.searchsorted(ts, t))
    return o[i] if i < len(ts) and ts[i] == t else None


# ── SETTLEMENT_FLOW ────────────────────────────────────────────────────
def _settlement(M, pered):
    """pered=True: окно T−60м→T против плательщиков (они закрываются до выплаты).
    pered=False: окно T→T+60м по стороне плательщиков (они возвращаются после).
    Знак — по ПРЕДЫДУЩЕЙ выплате (известна заранее, без заглядывания)."""
    sob = []
    for s in sorted(os.listdir(M5_SRC)):
        if s not in M:
            continue
        ts, o = m5(s)
        if len(ts) < 1000:
            continue
        x = M[s]; fts, fr = x["fts"], x["fr"]
        for k in range(1, len(fts)):
            T = int(fts[k]); f0 = fr[k - 1]
            if abs(f0) < POROG_F or T < ts[0] + 3600000 or T > ts[-1] - 3600000:
                continue
            a, b = (T - 3600000, T) if pered else (T, T + 3600000)
            pa, pb = cena_m5(ts, o, a), cena_m5(ts, o, b)
            if not pa or not pb:
                continue
            side = -np.sign(f0) if pered else np.sign(f0)
            r = side * (pb / pa - 1) - P.KOM_KRIPTO
            kk = []
            for _ in range(10):                       # контроль: случайный час того же месяца
                j = int(rng.integers(0, len(ts) - 13)); tj = ts[j]
                if abs(tj - T) > 15 * DEN or ts[j + 12] != tj + 3600000:
                    continue
                kk.append(side * (o[j + 12] / o[j] - 1) - P.KOM_KRIPTO)
            sob.append((T, r, float(np.mean(kk)) if kk else None))
    return P.itog(sob)


def D1(M):
    """PRE_SETTLE_EXIT: час до выплаты — против плательщиков"""
    return _settlement(M, True)


def D2(M):
    """POST_SETTLE_REENTRY: час после выплаты — по стороне плательщиков"""
    return _settlement(M, False)


# ── FUNDING_CAP_STRESS ─────────────────────────────────────────────────
def _interval(M, znak):
    """биржа укоротила интервал фандинга (упёрлись в лимит ставки) → против плательщиков 3 дня"""
    sob = []
    for s, x in M.items():
        fts, fr = x["fts"], x["fr"]
        d = np.diff(fts)
        for k in range(2, len(fts)):
            if not (d[k - 1] < d[k - 2] and d[k - 1] <= 4 * 3600000):
                continue
            if np.sign(fr[k]) != znak:
                continue
            i = int(np.searchsorted(x["ts"], fts[k] - fts[k] % DEN))
            if i < 30 or i >= len(x["ts"]):
                continue
            r = P.sdelka(x, i, 3, -znak)
            if r is None:
                continue
            pool = np.flatnonzero((np.abs(x["ts"] - x["ts"][i]) < 15 * DEN) & (np.arange(len(x["ts"])) >= 30))
            kk = [P.sdelka(x, int(j), 3, -znak) for j in rng.choice(pool, size=min(20, len(pool)))]
            kk = [q for q in kk if q is not None]
            sob.append((int(x["ts"][i]), r, float(np.mean(kk)) if kk else None))
    # один символ — одно событие в неделю (смена интервала идёт сериями)
    seen, out = set(), []
    for t, r, k in sorted(sob):
        key = (t // (7 * DEN), r)
        if key in seen:
            continue
        seen.add(key); out.append((t, r, k))
    return P.itog(out)


def D3(M):
    """CAP_STRESS_SHORTS_PAY: интервал укорочен при отрицательном фандинге → лонг 3 дня (шорты под давлением)"""
    return _interval(M, -1)


def D3p(M):
    """то же при положительном — пересекается с PEREGREV_HVOSTA, только справка"""
    return _interval(M, +1)


# ── BASIS ──────────────────────────────────────────────────────────────
def spot():
    S = {}
    for f in glob.glob(str(SPOT / "*.json")):
        r = json.load(open(f))["records"]
        S[os.path.basename(f)[:-5]] = {x["ts_ms"]: x["close"] for x in r}
    return S


def D4(M):
    """BASIS_CONVERGE: перп дороже спота на >1% → шорт перп + лонг спот 3 дня (базис сходится, фандинг в плюс)"""
    S = spot(); sob = []
    for s, sp in S.items():
        if s not in M:
            continue
        x = M[s]; blok = -1
        for i in range(30, len(x["ts"]) - 3):
            t = int(x["ts"][i]); q = sp.get(t); q3 = sp.get(int(x["ts"][i + 3]))
            if not q or not q3 or i <= blok:
                continue
            b = x["c"][i] / q - 1
            if b > 0.01:
                r = -(x["c"][i + 3] / x["c"][i] - 1) + (q3 / q - 1) + P.fand(x, t, int(x["ts"][i + 3])) - KOM_PARA
                sob.append((t, r, None)); blok = i + 3
    return P.itog(sob, s_kontrolem=False)


def D5(M):
    """BASIS_DISCOUNT_SIGNAL: перп дешевле спота на >0.5% (давление хеджеров) → лонг перп 3 дня"""
    S = spot(); sob = []
    for s, sp in S.items():
        if s not in M:
            continue
        x = M[s]; blok = -1
        for i in range(30, len(x["ts"]) - 3):
            q = sp.get(int(x["ts"][i]))
            if not q or i <= blok or x["c"][i] / q - 1 > -0.005:
                continue
            r = P.sdelka(x, i, 3, +1)
            if r is None:
                continue
            pool = np.flatnonzero((np.abs(x["ts"] - x["ts"][i]) < 15 * DEN) & (np.arange(len(x["ts"])) >= 30))
            kk = [P.sdelka(x, int(j), 3, +1) for j in rng.choice(pool, size=min(20, len(pool)))]
            kk = [z for z in kk if z is not None]
            sob.append((int(x["ts"][i]), r, float(np.mean(kk)) if kk else None)); blok = i + 3
    return P.itog(sob)


# ── поперечные ─────────────────────────────────────────────────────────
def _xs(M, score, filtr=None, hold=7):
    ts_all = sorted({int(t) for x in M.values() for t in x["ts"]})
    sob = []
    for t in ts_all[60::7]:
        rows = []
        for s, x in M.items():
            if filtr and not filtr(s, x):
                continue
            i = int(np.searchsorted(x["ts"], t))
            if i >= len(x["ts"]) or x["ts"][i] != t or i < 60:
                continue
            v = score(x, i)
            if v is not None and np.isfinite(v):
                rows.append((v, s, i))
        if len(rows) < 40:
            continue
        rows.sort(); k = len(rows) // 10
        leg = [P.sdelka(M[s], i, hold, +1) for _, s, i in rows[:k]] + [P.sdelka(M[s], i, hold, -1) for _, s, i in rows[-k:]]
        leg = [r for r in leg if r is not None]
        if leg:
            sob.append((t, float(np.mean(leg)), None))
    return P.itog(sob, s_kontrolem=False)


def D6(M):
    """OI_CROWDING_XS: шорт верхнего дециля роста OI в $ за 7 дней, лонг нижнего, 7 дней"""
    def sc(x, i):
        if x["oi"] is None or not np.isfinite(x["oi"][i]) or not np.isfinite(x["oi"][i - 7]) or x["oi"][i - 7] <= 0:
            return None
        return (x["oi"][i] * x["c"][i]) / (x["oi"][i - 7] * x["c"][i - 7]) - 1
    return _xs(M, sc)


def D7(M):
    """LIQ_PROVISION_XS: хвост, лонг худшего дециля 7-дневной доходности, шорт лучшего, 7 дней"""
    return _xs(M, lambda x, i: x["c"][i] / x["c"][i - 7] - 1, filtr=P.hvost)


def D9(M):
    """LOTTERY_DEMAND: лонг нижнего дециля 30-дневной волатильности, шорт верхнего, 7 дней
    (кредитное плечо ограничено → розница переплачивает за «лотерейные» монеты; betting-against-beta)"""
    def sc(x, i):
        r = np.diff(np.log(x["c"][i - 30:i + 1]))
        return float(r.std()) if len(r) == 30 else None
    return _xs(M, sc)


def D10(M):
    """SPECULATION_SHARE: шорт верхнего дециля доли перп-оборота к спот-обороту за 7 дней, лонг нижнего, 7 дней
    (спрос, раздутый плечом, выдыхается)"""
    SV = {}
    for f in glob.glob(str(SPOT / "*.json")):
        SV[os.path.basename(f)[:-5]] = {x["ts_ms"]: x["turnover"] for x in json.load(open(f))["records"]}
    def sc(x, i):
        sv = SV.get(x["_s"])
        if not sv:
            return None
        s_ = sum(sv.get(int(t), 0) for t in x["ts"][i - 6:i + 1])
        return float(x["usd"][i - 6:i + 1].sum() / s_) if s_ > 0 else None
    for s, x in M.items():
        x["_s"] = s
    return _xs(M, sc)


# ── Polymarket: касание против закрытия ────────────────────────────────
MES = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                    "September", "October", "November", "December"], 1)}


def D8(_M):
    """POLY_TOUCH: «Will X reach $K in <месяц>?» Касание вероятнее закрытия примерно вдвое (принцип отражения),
    розница думает о закрытии → недооценивает. За 7 дней до конца YES 15–50¢ → покупаем YES."""
    H = {}
    for a_, s_ in P.AKTIV.items():
        z = np.load(str(D / f"h1/{s_}.npz")); H[a_] = (z["ts"].astype(np.int64) // 1000, z["ohlcv"][:, 1])
    sob = []; sver = [0, 0]
    for f in glob.glob(str(D / "poly/istoriya/*.json")):
        d = json.load(open(f)); r = d.get("ryad") or []
        g = re.search(r"(Bitcoin|Ethereum|Solana|XRP) reach \$([\d,]+(?:\.\d+)?)([kK]?) in (\w+)\?", d["vopros"])
        if not g or not d.get("closed") or len(r) < 5 or g.group(4) not in MES:
            continue
        K = float(g.group(2).replace(",", "")) * (1000 if g.group(3) else 1)
        konec = dt.datetime.fromisoformat(d["konec"].replace("Z", "+00:00"))
        nach = dt.datetime(konec.year if MES[g.group(4)] <= konec.month else konec.year - 1, MES[g.group(4)], 1,
                           tzinfo=dt.timezone.utc).timestamp()
        ts_, hi = H[g.group(1)]
        if konec.timestamp() > ts_[-1] or nach < ts_[0]:
            continue
        m_ = (ts_ >= nach) & (ts_ < konec.timestamp())
        if not m_.any():
            continue
        ishod = 1.0 if hi[m_].max() >= K else 0.0
        last = r[-1][1]
        if last >= 0.99 or last <= 0.01:
            sver[0 if (last >= 0.99) == (ishod == 1) else 1] += 1
        t = np.array([q[0] for q in r], float); k = int(np.searchsorted(t, konec.timestamp() - 7 * 86400)) - 1
        if k < 0:
            continue
        p = r[k][1]
        if 0.15 <= p <= 0.50:
            sob.append((int(konec.timestamp() * 1000), (ishod - p) / p - P.KOM_POLY, None))
    res = P.itog(sob, s_kontrolem=False); res["sverka_razresheniya"] = f"совпало {sver[0]}, расходится {sver[1]}"
    return res


if __name__ == "__main__":
    kto = set(sys.argv[1:])
    M = P.zagruzit_kripto()
    P.HVOST_POROG = float(np.median([np.nanmedian(x["usd"][-120:]) for x in M.values()]))
    rez = {}
    for k, f in [("D1", D1), ("D2", D2), ("D3", D3), ("D3p", D3p), ("D4", D4), ("D5", D5), ("D6", D6), ("D7", D7), ("D8", D8), ("D9", D9), ("D10", D10)]:
        if not kto or k in kto:
            rez[k] = f(M); print(k, rez[k], flush=True)
    out = D / "discovery_paket2.json"
    old = json.load(open(out)) if out.exists() else {}
    old.update(rez); json.dump(old, open(out, "w"), ensure_ascii=False, indent=1)
