#!/usr/bin/env python3
"""discovery_paket1.py — дешёвый экран пачки Discovery №1 (DISCOVERY_PAKET1_2026_09_30.md).

Экран убивает, а не доказывает. Правило объявлено ДО прогона и одно на всех:
  SURVIVED  = эдж после издержек > 0, t по кластерам дат ≥ 2.0, обе половины истории > 0,
              и сырой доход после издержек > 0 (добавлено в ходе пачки ко ВСЕМ экранам:
              эдж против контроля бывает положительным при убыточной сделке, см. C5)
  KILLED    = всё остальное
SURVIVED даёт право только на предрегистрацию и проверку на будущих данных, не на PASS.
Подтверждающие окна фабрики не используются: крипта — вся история pit_daily (до 2026-09-21),
Polymarket — закрытые рынки из istoriya. Выживание pit_daily: только ныне торгуемые
перпы, делистинги отсутствуют → лонги смещены вверх, шорты — вниз (консервативно).

    python3 research_lab/discovery_paket1.py            # все экраны
    python3 research_lab/discovery_paket1.py C3 P2      # выборочно
    python3 research_lab/discovery_paket1.py C8V        # судья предрегистрации C8 на будущих данных
"""
import glob, json, math, sys, datetime as dt
from collections import defaultdict
import numpy as np

LAB = __import__("pathlib").Path(__file__).resolve().parent
D = LAB / "data"
DEN = 86400000
KOM_KRIPTO = 12e-4          # круг: тейкер+проскальзывание на перпах, доля
KOM_POLY = 0.02             # спред Polymarket на круг, в долях доллара
rng = np.random.default_rng(7)


# ── данные ────────────────────────────────────────────────────────────
def zagruzit_kripto():
    M = {}
    for f in glob.glob(str(D / "pit_daily/*.json")):
        p = json.load(open(f))
        if not isinstance(p, dict) or not p.get("daily") or len(p["daily"]) < 60:
            continue
        a = np.array(p["daily"], dtype=float)
        fr = np.array(p.get("funding") or [[0, 0]], dtype=float)
        s = p["symbol"]
        oi = None
        fo = D / "basis/oi_sutochnyy" / f"{s}.json"
        if fo.exists():
            r = np.array(json.load(open(fo))["ryad"], dtype=float)
            if len(r):
                m = dict(zip(r[:, 0].astype(np.int64), r[:, 1]))
                oi = np.array([m.get(int(t), np.nan) for t in a[:, 0]])
        M[s] = dict(ts=a[:, 0].astype(np.int64), o=a[:, 1], h=a[:, 2], l=a[:, 3], c=a[:, 4],
                    usd=a[:, 5] * a[:, 4], fts=fr[:, 0].astype(np.int64), fr=fr[:, 1], oi=oi)
    return M


def fand(x, t0, t1):
    """сумма ставок фандинга в (t0, t1]"""
    i, j = np.searchsorted(x["fts"], [t0, t1], side="right")
    return float(x["fr"][i:j].sum())


def sdelka(x, i, hold, side):
    """вход закрытием бара i, выход закрытием i+hold; фандинг: лонг платит положительный"""
    j = i + hold
    if j >= len(x["c"]):
        return None
    r = side * (x["c"][j] / x["c"][i] - 1) - side * fand(x, x["ts"][i], x["ts"][j]) - KOM_KRIPTO
    return r


def itog(sob, s_kontrolem=True):
    """sob: список (ts_входа, доход, доход_контроля|None). t по кластерам дат."""
    if len(sob) < 20:
        return dict(n=len(sob), verdikt="KILLED", prichina=f"мало событий ({len(sob)})")
    po_dnyam = defaultdict(list)
    for t, r, k in sob:
        po_dnyam[t // DEN].append(r - (k if (s_kontrolem and k is not None) else 0.0))
    dni = sorted(po_dnyam); v = np.array([np.mean(po_dnyam[d]) for d in dni])
    m = v.mean(); t = m / (v.std(ddof=1) / math.sqrt(len(v))) if len(v) > 2 and v.std() > 0 else 0.0
    h = len(v) // 2; m1, m2 = v[:h].mean(), v[h:].mean()
    syroy = float(np.mean([r for _, r, _ in sob]))          # то, что реально попадёт на счёт
    ok = m > 0 and t >= 2.0 and m1 > 0 and m2 > 0 and syroy > 0
    return dict(n=len(sob), dney=len(v), edge_bps=round(float(m) * 1e4, 1), t=round(float(t), 2),
                polovinki_bps=(round(float(m1) * 1e4, 1), round(float(m2) * 1e4, 1)),
                syroy_bps=round(syroy * 1e4, 1), verdikt="SURVIVED" if ok else "KILLED",
                prichina="t≥2, обе половины > 0, сырой доход > 0" if ok else
                ("эдж ≤ 0" if m <= 0 else (f"t={t:.2f} < 2" if t < 2 else
                 ("одна половина ≤ 0" if min(m1, m2) <= 0 else "против контроля плюс, но сырой доход ≤ 0 — не торгуется"))))


def sobytiya(M, uslovie, hold, side, mesyac_kontrol=True, filtr=None):
    sob = []
    for s, x in M.items():
        if filtr and not filtr(s, x):
            continue
        idx = np.flatnonzero(uslovie(x))
        blok = -1
        for i in idx:
            if i < 30 or i <= blok:
                continue
            r = sdelka(x, i, hold, side)
            if r is None:
                continue
            blok = i + hold
            k = None
            if mesyac_kontrol:
                pool = np.flatnonzero((np.abs(x["ts"] - x["ts"][i]) < 15 * DEN) & (np.arange(len(x["ts"])) >= 30))
                kk = [sdelka(x, int(j), hold, side) for j in rng.choice(pool, size=min(20, len(pool)))]
                kk = [q for q in kk if q is not None]
                k = float(np.mean(kk)) if kk else None
            sob.append((int(x["ts"][i]), r, k))
    return sob


def ret(x, n):
    r = np.full(len(x["c"]), np.nan); r[n:] = x["c"][n:] / x["c"][:-n] - 1; return r


def med_prev(v, n):
    out = np.full(len(v), np.nan)
    for i in range(n, len(v)):
        out[i] = np.median(v[i - n:i])
    return out


def fand_dnevnoy(x):
    """сумма фандинга за сутки, заканчивающиеся на баре"""
    return np.array([fand(x, t - DEN, t) for t in x["ts"]])


def hvost(s, x):     # нижняя половина по медианному обороту — ёмкостно ограниченное
    return np.nanmedian(x["usd"][-120:]) < HVOST_POROG


HVOST_POROG = None


# ── экраны крипты ──────────────────────────────────────────────────────
def C1(M):
    """FND_XS_CARRY: раз в 7 дней шорт верхнего дециля 7-дневного фандинга, лонг нижнего, держать 7 дней"""
    ts_all = sorted({int(t) for x in M.values() for t in x["ts"]})
    sob = []
    for t in ts_all[60::7]:
        rows = []
        for s, x in M.items():
            i = int(np.searchsorted(x["ts"], t))
            if i >= len(x["ts"]) or x["ts"][i] != t or i < 60:
                continue
            rows.append((fand(x, t - 7 * DEN, t), s, i))
        if len(rows) < 40:
            continue
        rows.sort(); k = len(rows) // 10
        leg = [sdelka(M[s], i, 7, +1) for _, s, i in rows[:k]] + [sdelka(M[s], i, 7, -1) for _, s, i in rows[-k:]]
        leg = [r for r in leg if r is not None]
        if leg:
            sob.append((t, float(np.mean(leg)), None))
    return itog(sob, s_kontrolem=False)


def C2(M):
    """FND_PRICE_DIVERGENCE: цена +15% за 7 дней при отрицательном фандинге за 3 дня → лонг 3 дня"""
    def u(x):
        f3 = np.array([fand(x, t - 3 * DEN, t) for t in x["ts"]])
        return (ret(x, 7) > 0.15) & (f3 < 0)
    return itog(sobytiya(M, u, 3, +1))


def C3(M):
    """OI_FLUSH_REBOUND: OI −25% за день и цена −10% → лонг 3 дня (вынужденные продавцы ушли)"""
    def u(x):
        if x["oi"] is None:
            return np.zeros(len(x["c"]), bool)
        d = np.full(len(x["c"]), np.nan); d[1:] = x["oi"][1:] / x["oi"][:-1] - 1
        return (d < -0.25) & (ret(x, 1) < -0.10)
    return itog(sobytiya(M, u, 3, +1))


def C4(M):
    """NEW_LISTING_FADE: перп, появившийся после 2023-03-01, шорт с 3-го по 30-й день"""
    sob = []
    for s, x in M.items():
        if x["ts"][0] < 1677628800000 or len(x["c"]) < 40:
            continue
        r = sdelka(x, 2, 27, -1)
        if r is not None:
            sob.append((int(x["ts"][2]), r, None))
    return itog(sob, s_kontrolem=False)


def C5(M):
    """PUMP_FADE_TAIL: хвост, день +30% при обороте ≥5 медиан за 30 дней → шорт 5 дней"""
    def u(x):
        return (ret(x, 1) > 0.30) & (x["usd"] > 5 * med_prev(x["usd"], 30))
    return itog(sobytiya(M, u, 5, -1, filtr=hvost))


def C6(M):
    """CRASH_BOUNCE_TAIL: хвост, день −25% → лонг 2 дня (премия за ликвидность)"""
    return itog(sobytiya(M, lambda x: ret(x, 1) < -0.25, 2, +1, filtr=hvost))


def C7(M):
    """BTC_SHOCK_LAG: BTC за день |≥5%| → хвост на следующий день в сторону BTC (медленная диффузия)"""
    b = M["BTCUSDT"]; br = dict(zip(b["ts"].tolist(), ret(b, 1).tolist()))
    sob = []
    for s, x in M.items():
        if s == "BTCUSDT" or not hvost(s, x):
            continue
        for i in range(30, len(x["ts"]) - 1):
            r0 = br.get(int(x["ts"][i]))
            if r0 is None or not np.isfinite(r0) or abs(r0) < 0.05:
                continue
            side = 1 if r0 > 0 else -1
            r = sdelka(x, i, 1, side)
            if r is not None:
                sob.append((int(x["ts"][i]), r, None))
    return itog(sob, s_kontrolem=False)


def C8(M):
    """FND_PERSIST_TREND: фандинг >0.1%/сутки 5 дней подряд у хвоста → шорт 7 дней (перегретые лонги платят и сдаются).
    ОТЛИЧИЕ от SHORT_HVOST_FANDING: дневной горизонт устойчивой перегрузки, не 16 ч после одной выплаты."""
    def u(x):
        fd = fand_dnevnoy(x); ok = fd > 0.001
        run = np.zeros(len(ok), bool)
        for i in range(5, len(ok)):
            run[i] = ok[i - 4:i + 1].all()
        return run
    return itog(sobytiya(M, u, 7, -1, filtr=hvost))


C8_ZAMOROZKA = 1790035200000   # 2026-09-22 00:00 UTC — первый день после конца истории: всё дальше — будущее
# вселенная заморожена: ровно те перпы, что были в pit_daily на 2026-09-30 (новые листинги не входят)
C8_VSELENNAYA = set(json.load(open(D / "discovery_c8_vselennaya.json"))) if (D / "discovery_c8_vselennaya.json").exists() else set()


def C8V(M):
    """Судья предрегистрации C8 (PREREG в DISCOVERY_PAKET1_2026_09_30.md). Только входы после заморозки.
    PASS: n ≥ 30, сырой доход > 0, медиана > 0, t по датам ≥ 2, одна монета ≤ 50% плюса. FAIL: n ≥ 30 и не PASS."""
    rows = []
    for s, x in M.items():
        # хвост заморожен числом и окном ДО заморозки: медианный оборот < $502 571 за 120 дней до 2026-09-22
        pre = x["usd"][x["ts"] < C8_ZAMOROZKA][-120:]
        if s not in C8_VSELENNAYA or not len(pre) or not np.nanmedian(pre) < 502570.77:
            continue
        fd = fand_dnevnoy(x); ok = fd > 0.001; blok = -1
        for i in range(5, len(ok)):
            if not ok[i - 4:i + 1].all() or i <= blok or x["ts"][i] < C8_ZAMOROZKA:
                continue
            r = sdelka(x, i, 7, -1)
            if r is not None:
                blok = i + 7; rows.append((s, int(x["ts"][i]), r))
    if len(rows) < 30:
        return dict(n=len(rows), verdikt="ЖДЁМ")
    po = defaultdict(list)
    for _, t, r in rows:
        po[t // DEN].append(r)
    v = np.array([np.mean(q) for q in po.values()]); t_ = v.mean() / (v.std(ddof=1) / math.sqrt(len(v)))
    r = np.array([q for *_, q in rows]); plus = defaultdict(float)
    for s, _, q in rows:
        plus[s] += q
    dolya = max(plus.values()) / (sum(q for q in plus.values() if q > 0) or 1e-9)
    ok = r.mean() > 0 and np.median(r) > 0 and t_ >= 2 and dolya <= 0.5
    return dict(n=len(rows), syroy_bps=round(float(r.mean()) * 1e4), med_bps=round(float(np.median(r)) * 1e4),
                t=round(float(t_), 2), dolya=round(dolya, 2), verdikt="PASS" if ok else "FAIL")


# ── Polymarket ─────────────────────────────────────────────────────────
AKTIV = {"Bitcoin": "BTCUSDT", "Ethereum": "ETHUSDT", "Solana": "SOLUSDT", "XRP": "XRPUSDT"}


def zagruzit_poly():
    """Только «<актив> above $K on <дата>», исход считается САМИ по часовой цене Bybit на момент
    konec (последняя точка ряда Polymarket — ещё не разрешение: отбор по ней смещал выборку).
    Цена ближе 0.3% к страйку — неоднозначно, выкидывается независимо от пути цены."""
    import re
    H = {}
    for a_, s_ in AKTIV.items():
        z = np.load(str(D / f"h1/{s_}.npz")); H[a_] = (z["ts"].astype(np.int64) // 1000, z["ohlcv"][:, 3])
    R = []
    for f in glob.glob(str(D / "poly/istoriya/*.json")):
        d = json.load(open(f)); r = d.get("ryad") or []
        if not d.get("closed") or len(r) < 5:
            continue
        g = re.search(r"(Bitcoin|Ethereum|Solana|XRP) (?:be )?above \$([\d,]+(?:\.\d+)?)([kK]?) on", d["vopros"])
        if not g:
            continue
        K = float(g.group(2).replace(",", "")) * (1000 if g.group(3) else 1)
        konec = dt.datetime.fromisoformat(d["konec"].replace("Z", "+00:00")).timestamp()
        ts_, c_ = H[g.group(1)]; k = int(np.searchsorted(ts_, konec - 3600))
        if k >= len(ts_) or ts_[k] != konec - 3600:
            continue
        px = c_[k]
        if abs(px / K - 1) < 0.003:
            continue
        R.append(dict(ishod=1.0 if px > K else 0.0, t=np.array([q[0] for q in r], float),
                      p=np.array([q[1] for q in r], float), konec=konec, sob=d.get("sobytie") or d["vopros"],
                      vopros=d["vopros"], kat=d.get("kat")))
    return R


def cena_do(m, sek):
    k = int(np.searchsorted(m["t"], m["konec"] - sek)) - 1
    return (m["p"][k], m["t"][k]) if k >= 0 else (None, None)


def poly_itog(sob):
    """sob: (время_конца_рынка, доход на $1 ставки). Кластер = сутки разрешения:
    все страйки и все монеты одного дня — одно наблюдение; половины хронологические."""
    return itog([(int(t * 1000), r, None) for t, r in sob], s_kontrolem=False)


def P1(R):
    """LONGSHOT: за 24 ч до конца YES ≤ 10¢ → покупаем NO (переоценка лотерейных билетов)"""
    sob = []
    for m in R:
        p, _ = cena_do(m, 86400)
        if p is not None and 0.01 < p <= 0.10:
            sob.append((m["konec"], ((1 - m["ishod"]) - (1 - p)) / (1 - p) - KOM_POLY))
    return poly_itog(sob)


def P2(R):
    """FAVORITE_NEAR_EXPIRY: за 24 ч до конца YES 90–97¢ → покупаем YES (никто не хочет морозить капитал ради 3–10%)"""
    sob = []
    for m in R:
        p, _ = cena_do(m, 86400)
        if p is not None and 0.90 <= p <= 0.97:
            sob.append((m["konec"], (m["ishod"] - p) / p - KOM_POLY))
    return poly_itog(sob)


def P3(R):
    """OVERREACTION: в середине жизни рынка сдвиг ≥15 пунктов за ~6 ч → ставка на откат, выход за 24 ч до конца"""
    sob = []
    for m in R:
        t, p = m["t"], m["p"]
        for i in range(1, len(t)):
            j = int(np.searchsorted(t, t[i] - 6 * 3600))
            if j >= i or t[i] > m["konec"] - 3 * 86400 or t[i] < t[0] + 86400:
                continue
            d = p[i] - p[j]
            if abs(d) >= 0.15 and 0.05 < p[i] < 0.95:
                px, _ = cena_do(m, 86400)
                if px is None:
                    break
                side = -1 if d > 0 else 1
                stavka = p[i] if side > 0 else 1 - p[i]
                sob.append((m["konec"], side * (px - p[i]) / stavka - KOM_POLY))
                break
    return poly_itog(sob)


def P4(R, M):
    """MODEL_MISPRICE: «BTC above K on date» против лог-нормальной модели от спота и 30-дневной реализованной вол.
    Если модель − цена ≥ 10 пунктов — покупаем YES, если ≤ −10 — NO. Кто платит: розница с якорем на круглые страйки."""
    import re
    h1 = np.load(str(D / "h1/BTCUSDT.npz")); ts = h1["ts"].astype(np.int64) // 1000; c = h1["ohlcv"][:, 3]
    lr = np.diff(np.log(c))
    sob = []
    for m in R:
        q = m["vopros"]
        if "Bitcoin" not in q or "above" not in q:
            continue
        g = re.search(r"\$([\d,]+(?:\.\d+)?)(k?)", q)
        if not g:
            continue
        K = float(g.group(1).replace(",", "")) * (1000 if g.group(2) else 1)
        p, tp = cena_do(m, 86400)
        if p is None:
            continue
        k = int(np.searchsorted(ts, tp)) - 1
        if k < 720 or k >= len(c):
            continue
        sig = lr[k - 720:k].std() * math.sqrt(24 * 365); T = (m["konec"] - tp) / (365 * 86400)
        if T <= 0 or sig <= 0:
            continue
        d2 = (math.log(c[k] / K) - 0.5 * sig * sig * T) / (sig * math.sqrt(T))
        pm = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
        if pm - p >= 0.10 and p < 0.95:
            sob.append((m["konec"], (m["ishod"] - p) / p - KOM_POLY))
        elif p - pm >= 0.10 and p > 0.05:
            sob.append((m["konec"], ((1 - m["ishod"]) - (1 - p)) / (1 - p) - KOM_POLY))
    return poly_itog(sob)


if __name__ == "__main__":
    kto = set(sys.argv[1:])
    rez = {}
    if not kto or any(k.startswith("C") for k in kto) or "P4" in kto:
        M = zagruzit_kripto()
        HVOST_POROG = float(np.median([np.nanmedian(x["usd"][-120:]) for x in M.values()]))
        if "C8V" in kto:
            print("C8V", C8V(M)); sys.exit(0)
        for k, f in [("C1", C1), ("C2", C2), ("C3", C3), ("C4", C4), ("C5", C5), ("C6", C6), ("C7", C7), ("C8", C8)]:
            if not kto or k in kto:
                rez[k] = f(M); print(k, rez[k], flush=True)
    if not kto or any(k.startswith("P") for k in kto):
        R = zagruzit_poly()
        for k, f in [("P1", P1), ("P2", P2), ("P3", P3)]:
            if not kto or k in kto:
                rez[k] = f(R); print(k, rez[k], flush=True)
        if not kto or "P4" in kto:
            rez["P4"] = P4(R, None); print("P4", rez["P4"], flush=True)
    json.dump(rez, open(LAB / "data/discovery_paket1.json", "w"), ensure_ascii=False, indent=1)
