"""portfeli.py — рынки и сигналы для портфельного прогонщика.

Сигнал видит только матрицу цен до даты t включительно (закрытие t).
Позиции открываются закрытием t и держатся H торговых дней.
У каждого сигнала один канонический набор параметров.
"""
from __future__ import annotations
import datetime as dt, glob, json, os
from pathlib import Path
import numpy as np

LAB = Path(__file__).resolve().parents[1]
DATA = LAB / "data"
DEN = 86400000


def _ms(s):
    return int(dt.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


# ── рынки ─────────────────────────────────────────────────────────────
def zagruzit_akcii():
    """Alpaca PIT: 962 чистых тикера, из них 262 делистингованы. Членство:
    бар существует и дата не позже делистинга. Фильтр ликвидности считается
    в сигнале по прошлому (цена ≥ $5, медиана оборота 20 дней ≥ $5 млн)."""
    m = json.load(open(DATA / "alpaca_pit_daily_v1/membership_intervals.json"))
    syms = [x["symbol"] for x in m["intervals"]]
    delist = {x["symbol"]: (_ms(x["delisted_utc"]) if x["delisted_utc"] else None) for x in m["intervals"]}
    ser = {}
    for s in syms:
        p = DATA / f"alpaca_pit_daily_v1/bars/{s}.json"
        if p.exists():
            ser[s] = {r["t"] // DEN * DEN: (r["c"], r["v"] * r.get("vw", r["c"])) for r in json.load(open(p))["records"]}
    dates = np.array(sorted({t for v in ser.values() for t in v}), dtype=np.int64)
    S = sorted(ser); di = {t: i for i, t in enumerate(dates)}
    C = np.full((len(dates), len(S)), np.nan); DV = np.full_like(C, np.nan)
    for j, s in enumerate(S):
        for t, (c, dv) in ser[s].items():
            if delist[s] is None or t <= delist[s]:
                C[di[t], j] = c; DV[di[t], j] = dv
    return dict(dates=dates, simvoly=S, C=C, DV=DV, M=~np.isnan(C), F=None, fee_bps=5.0,
                razdel=_ms("2026-01-01"), opisanie="Alpaca PIT, 962 тикера (262 делистинга)")


def zagruzit_kripto_pit(fayl="basis/vselennaya_pit.json", razdel="2025-10-01", vse_chleny=None):
    """Топ-20 по открытому интересу, известному строго до даты (basis/vselennaya_pit.json).
    Цены: data/pit_daily/*.json (скачиваются dannye_pit_kripto.py), иначе из data/h1.
    Фандинг: оттуда же и из bybit_public_archive_2023/funding."""
    if vse_chleny is not None:            # фиксированный список: все всегда члены (диагностика)
        v = {"simvoly": sorted(vse_chleny), "sostav": {}, "pravilo": f"фиксированные {len(vse_chleny)} символов"}
    else:
        v = json.load(open(DATA / fayl))
    if "bez_ceny" in v and len(v["bez_ceny"]) > 0.05 * (len(v["bez_ceny"]) + v.get("s_cenoy", len(v["simvoly"]))):
        raise FileNotFoundError(f"{fayl}: собрана без цен у {len(v['bez_ceny'])} инструментов — вселенная неполная")
    S = sorted(v["simvoly"]); ser, fnd, hv = {}, {}, {}
    for s in S:
        p = DATA / f"pit_daily/{s}.json"
        if p.exists():
            d = json.load(open(p))
            ser[s] = {int(r[0]) // DEN * DEN: float(r[4]) for r in d.get("daily", [])}
            hv[s] = {int(r[0]) // DEN * DEN: (float(r[2]), float(r[5])) for r in d.get("daily", [])}
            fnd[s] = [(int(t), float(r)) for t, r in d.get("funding", [])]
        elif (DATA / f"h1/{s}.npz").exists():
            z = np.load(DATA / f"h1/{s}.npz"); ts = z["ts"]; c = z["ohlcv"][:, 3]
            day = ts // DEN * DEN; ser[s] = {}
            for t, x in zip(day, c):
                ser[s][int(t)] = float(x)            # последнее закрытие дня
        fp = DATA / f"bybit_public_archive_2023/funding/{s}.json"
        if s not in fnd and fp.exists():
            fnd[s] = [(r["funding_time_ms"], r["funding_rate"]) for r in json.load(open(fp))["records"]]
    dates = np.arange(_ms("2023-01-02"), _ms("2026-09-04"), DEN, dtype=np.int64)
    di = {int(t): i for i, t in enumerate(dates)}
    C = np.full((len(dates), len(S)), np.nan); M = np.zeros_like(C, dtype=bool); F = np.zeros_like(C)
    FOK = np.zeros_like(C, dtype=bool); HH = np.full_like(C, np.nan); VV = np.full_like(C, np.nan)
    OI = np.full_like(C, np.nan)                      # открытый интерес в штуках монеты
    for j, s in enumerate(S):
        po = DATA / f"basis/oi_sutochnyy/{s}.json"
        if po.exists():
            for t_oi, v_oi in json.load(open(po)).get("ryad", []):
                k_oi = di.get(int(t_oi) // DEN * DEN)
                if k_oi is not None:
                    OI[k_oi, j] = float(v_oi)
        for t, c in ser.get(s, {}).items():
            if t in di: C[di[t], j] = c
        for t, (hh, vv) in hv.get(s, {}).items():
            if t in di: HH[di[t], j] = hh; VV[di[t], j] = vv
        for t, r in fnd.get(s, []):
            k = di.get(int(t) // DEN * DEN)
            if k is not None: F[k, j] += r; FOK[k, j] = True
    if vse_chleny is not None:
        M[:, :] = True
    for d, sl in v["sostav"].items():
        k = di.get(_ms(d))
        if k is not None:
            for s in sl:
                M[k, S.index(s)] = True
    return dict(dates=dates, simvoly=S, C=C, DV=None, M=M, F=F, FOK=FOK, HH=HH, VV=VV, OI=OI, fee_bps=7.0,
                razdel=_ms(razdel), opisanie=f"крипта PIT: {v.get('pravilo', fayl)}")


def zagruzit_kripto_poly():
    R = zagruzit_kripto_pit("basis/vselennaya_pit_usd50.json")
    import poly_priznaki
    pz = poly_priznaki.priznaki(R["dates"])
    R["POLY"] = np.array([pz[int(t)]["kripto"][0] if pz[int(t)]["kripto"][0] is not None and pz[int(t)]["kripto"][1] >= 3
                          else np.nan for t in R["dates"]])
    okno = (R["dates"] >= _ms("2023-03-01")) & (R["dates"] < R["razdel"])
    pokr = float(np.isfinite(R["POLY"][okno]).mean()) if okno.any() else 0.0
    if pokr < 0.6:
        raise FileNotFoundError(f"покрытие Polymarket {pokr:.0%} дней окна обнаружения (нужно ≥60% дней с ≥3 рынками)")
    return R


RYNKI_P = {"akcii_pit": zagruzit_akcii, "kripto_pit": zagruzit_kripto_pit, "kripto_pit50_poly": zagruzit_kripto_poly,
           "kripto_pit50": lambda: zagruzit_kripto_pit("basis/vselennaya_pit_usd50.json")}


# ── сигналы: fn(C_do_t, DV_do_t) -> оценка по бумагам (NaN = не участвует) ──
def _ret(C, n, skip=0):
    if C.shape[0] <= n + skip:
        return np.full(C.shape[1], np.nan)
    return C[-1 - skip] / C[-1 - skip - n] - 1


def _likvid(C, DV):
    if DV is None:
        return np.ones(C.shape[1], dtype=bool)
    if C.shape[0] < 21:
        return np.zeros(C.shape[1], dtype=bool)
    with np.errstate(all="ignore"):
        med = np.nanmedian(DV[-20:], axis=0)
    return (C[-1] >= 5) & (med >= 5e6)


def mom_6_1(C, DV):
    r = _ret(C, 105, 21); return np.where(_likvid(C, DV), r, np.nan)


def reversal_5d(C, DV):
    r = -_ret(C, 5); return np.where(_likvid(C, DV), r, np.nan)


def low_vol_60(C, DV):
    if C.shape[0] < 61:
        return np.full(C.shape[1], np.nan)
    with np.errstate(all="ignore"):
        v = np.nanstd(np.diff(np.log(C[-61:]), axis=0), axis=0)
    return np.where(_likvid(C, DV), -v, np.nan)


def blizost_k_maksimumu(C, DV):
    if C.shape[0] < 127:
        return np.full(C.shape[1], np.nan)
    with np.errstate(all="ignore"):
        r = C[-1] / np.nanmax(C[-126:], axis=0)
    return np.where(_likvid(C, DV), r, np.nan)


def xsec_v3(C, DV):
    """ранг моментума + ранг волатильности по 5 окнам (xsec_v3_reference), как оценка"""
    out = np.zeros(C.shape[1]); cnt = np.zeros(C.shape[1])
    for L in (7, 14, 21, 30, 45):
        if C.shape[0] <= L + 1:
            continue
        mom = C[-1] / C[-1 - L] - 1
        with np.errstate(all="ignore"):
            vol = np.nanstd(np.diff(C[-1 - L:], axis=0) / C[-1 - L:-1], axis=0, ddof=1)
        ok = np.isfinite(mom) & np.isfinite(vol)
        if ok.sum() < 14:
            continue
        rk = np.zeros(C.shape[1]); idx = np.flatnonzero(ok)
        rk[idx[np.argsort(mom[idx])]] += np.arange(len(idx)); rk[idx[np.argsort(vol[idx])]] += np.arange(len(idx))
        out[ok] += rk[ok] / len(idx); cnt[ok] += 1
    return np.where(cnt > 0, out / np.maximum(cnt, 1), np.nan)


def fanding_kerri(C, DV, F=None):
    """низкий фандинг за 7 дней — в лонг, высокий — в шорт (переполненная сторона платит)"""
    if F is None or F.shape[0] < 8:
        return np.full(C.shape[1], np.nan)
    f7 = F[-7:].sum(axis=0)
    return np.where(np.isfinite(C[-1]), -f7, np.nan)


# ── пакет v3 (предрегистрация PREREG_PAKET_V3_2026_09_21.md) ─────────
def _sma_last(C, n):
    if C.shape[0] < n:
        return np.full(C.shape[1], np.nan)
    w = C[-n:]
    return np.where(np.isfinite(w).all(axis=0), np.nanmean(w, axis=0), np.nan)


def _shirina(C, M):
    s50 = _sma_last(C, 50); el = M[-1] & np.isfinite(s50) & np.isfinite(C[-1])
    return (C[-1, el] > s50[el]).mean() if el.sum() >= 8 else np.nan


def _ne_peregret(C, ctx):
    """фандинг монеты за 7 дней не выше медианы членов вселенной"""
    F = ctx.get("F")
    if F is None or F.shape[0] < 8:
        return np.zeros(C.shape[1], dtype=bool)
    f7 = F[-7:].sum(axis=0); el = ctx["M"][-1] & np.isfinite(C[-1])
    return f7 <= np.median(f7[el]) if el.sum() else np.zeros(C.shape[1], dtype=bool)


def reversal_3d(C, DV, ctx):
    r = -_ret(C, 3); return np.where(ctx["M"][-1], r, np.nan)


def _lider_otkat(C, ctx):
    if C.shape[0] < 61:
        return np.full(C.shape[1], np.nan)
    M = ctx["M"][-1]; r30 = _ret(C, 30); r3 = _ret(C, 3)
    with np.errstate(all="ignore"):
        sd = np.nanstd(np.diff(np.log(C[-21:]), axis=0), axis=0, ddof=1)
    s50 = _sma_last(C, 50)
    el = M & np.isfinite(r30) & np.isfinite(r3) & np.isfinite(sd) & np.isfinite(s50)
    out = np.where(el, 0.0, np.nan)
    if el.sum() < 5:
        return out
    porog = np.quantile(r30[el], 0.8)
    vyb = el & (r30 >= porog) & (r3 <= -sd * np.sqrt(3)) & (C[-1] > s50)
    return np.where(vyb, 1.0, out)


def lider_otkat_base(C, DV, ctx):
    return _lider_otkat(C, ctx)


def lider_otkat_filtr(C, DV, ctx):
    x = _lider_otkat(C, ctx)
    if not (_shirina(C, ctx["M"]) >= 0.55):
        return np.where(np.isfinite(x), 0.0, np.nan)
    return np.where(np.isfinite(x), np.where((x > 0) & _ne_peregret(C, ctx), 1.0, 0.0), np.nan)


def _szhatie_rasshirenie(C, ctx):
    HH, VV, M = ctx["HH"], ctx["VV"], ctx["M"][-1]
    if C.shape[0] < 202 or HH is None or VV is None:
        return np.full(C.shape[1], np.nan)   # без экстремумов и объёма механизм не определён
    with np.errstate(all="ignore"):
        lr = np.diff(np.log(C[-202:]), axis=0)                       # 201 доходность
        vol = np.array([np.nanstd(lr[i - 20:i], axis=0, ddof=1) for i in range(20, lr.shape[0] + 1)])  # 182 окна
        vchera, istoriya = vol[-2], vol[-182:-2]
        pct = (istoriya < vchera).mean(axis=0)
        maks20 = np.nanmax(HH[-21:-1], axis=0); med_v = np.nanmedian(VV[-21:-1], axis=0)
    el = M & np.isfinite(vchera) & np.isfinite(maks20) & np.isfinite(med_v) & np.isfinite(VV[-1])
    out = np.where(el, 0.0, np.nan)
    vyb = el & (pct <= 0.2) & (C[-1] > maks20) & (VV[-1] >= 1.5 * med_v)
    return np.where(vyb, 1.0, out)


def szhatie_base(C, DV, ctx):
    return _szhatie_rasshirenie(C, ctx)


def szhatie_filtr(C, DV, ctx):
    x = _szhatie_rasshirenie(C, ctx)
    if not (_shirina(C, ctx["M"]) >= 0.55):
        return np.where(np.isfinite(x), 0.0, np.nan)
    return np.where(np.isfinite(x), np.where((x > 0) & _ne_peregret(C, ctx), 1.0, 0.0), np.nan)


PV3 = "research_lab/fabrika/PREREG_PAKET_V3_2026_09_21.md"
PPOLY = "research_lab/fabrika/PREREG_POLY_V1_2026_09_21.md"


def szhatie_poly(C, DV, ctx):
    """BULL_VOL_EXPANSION_BASE, но только в дни, когда рынки предсказаний сдвинулись в risk-on (>0)"""
    x = _szhatie_rasshirenie(C, ctx)
    ro = ctx.get("POLY")
    if ro is None or not np.isfinite(ro[-1]) or ro[-1] <= 0:
        return np.where(np.isfinite(x), 0.0, np.nan)
    return x


# ── пакет v4 «рост» (PREREG_PAKET_V4_BULL_2026_09_23.md) ─────────────
# Половина А: признаки дня — вопрос «отличаются ли такие дни», прогонщик sensor.
# Половина Б: отбор бумаг внутри растущего рынка, прогонщик portfel (vybor).
PV4 = "research_lab/fabrika/PREREG_PAKET_V4_BULL_2026_09_23.md"


def _shirina_ryad(R):
    """доля членов вселенной выше своей SMA50, по каждому дню"""
    C, M, T = R["C"], R["M"], len(R["dates"])
    out = np.full(T, np.nan)
    for t in range(50, T):
        s50 = _sma_last(C[:t + 1], 50)
        el = M[t] & np.isfinite(s50) & np.isfinite(C[t])
        if el.sum() >= 8:
            out[t] = float((C[t, el] > s50[el]).mean())
    return out


def priznak_shirina_tolchok(R):
    """толчок участия: доля членов выше своей SMA50 выросла за 10 дней больше чем на 0.15.
    Порог выбран по числу дней (мощность), до любого счёта доходности: 0.10/0.15/0.20 дают
    267/214/181 дня окна обнаружения — взят средний."""
    b = _shirina_ryad(R); out = np.full(len(b), np.nan)
    for t in range(10, len(b)):
        if np.isfinite(b[t]) and np.isfinite(b[t - 10]):
            out[t] = float(b[t] - b[t - 10] - 0.15)
    return out


def priznak_maks_minus_min(R):
    """новые максимумы минус новые минимумы (60 дней), сверх своей медианы за 120 дней"""
    C, M, T = R["C"], R["M"], len(R["dates"])
    sp = np.full(T, np.nan)
    for t in range(60, T):
        w = C[t - 59:t + 1]
        el = M[t] & np.isfinite(C[t]) & np.isfinite(w).all(axis=0)
        if el.sum() < 8:
            continue
        mx = w[:, el].max(axis=0); mn = w[:, el].min(axis=0)
        sp[t] = float((C[t, el] >= mx).mean() - (C[t, el] <= mn).mean())
    out = np.full(T, np.nan)
    for t in range(181, T):
        h = sp[t - 120:t]
        if np.isfinite(sp[t]) and np.isfinite(h).sum() >= 60:
            out[t] = sp[t] - float(np.nanmedian(h))
    return out


def priznak_oborot_tolchok(R):
    """толчок оборота: медианный объём членов сегодня к своей медиане за 20 дней, порог 1.3"""
    VV, M, T = R.get("VV"), R["M"], len(R["dates"])
    if VV is None:
        return np.full(T, np.nan)
    med = np.full(T, np.nan)
    for t in range(T):
        el = M[t] & np.isfinite(VV[t]) & (VV[t] > 0)
        if el.sum() >= 8:
            med[t] = float(np.median(VV[t, el]))
    out = np.full(T, np.nan)
    for t in range(20, T):
        h = med[t - 20:t]
        if np.isfinite(med[t]) and np.isfinite(h).sum() >= 15:
            b = float(np.nanmedian(h))
            if b > 0:
                out[t] = med[t] / b - 1.3
    return out


PRIZNAKI_DNYA = {"POLY": lambda R: R["POLY"],
                 "ROTACIYA_IZ_BTC": lambda R: priznak_rotaciya_iz_btc(R),
                 "SHIRINA_TOLCHOK": priznak_shirina_tolchok,
                 "MAKS_MINUS_MIN": priznak_maks_minus_min,
                 "OBOROT_TOLCHOK": priznak_oborot_tolchok}


def bull_novyy_maksimum(C, DV, ctx):
    """пробой вверх: закрытие = максимум 60 дней, бумага выше SMA200, участие ≥50%"""
    if C.shape[0] < 201:
        return np.full(C.shape[1], np.nan)
    M = ctx["M"][-1]; s200 = _sma_last(C, 200)
    mx60 = np.nanmax(C[-60:], axis=0)
    el = M & np.isfinite(C[-1]) & np.isfinite(s200) & np.isfinite(mx60)
    out = np.where(el, 0.0, np.nan)
    if not (_shirina(C, ctx["M"]) >= 0.50):
        return out
    return np.where(el & (C[-1] >= mx60) & (C[-1] > s200), 1.0, out)


def bull_otstayushchiy(C, DV, ctx):
    """ротация в растущем рынке: участие ≥55%, бумага выше SMA200, но в нижних 30% по 20 дням"""
    if C.shape[0] < 201:
        return np.full(C.shape[1], np.nan)
    M = ctx["M"][-1]; s200 = _sma_last(C, 200); r20 = _ret(C, 20)
    el = M & np.isfinite(C[-1]) & np.isfinite(s200) & np.isfinite(r20)
    out = np.where(el, 0.0, np.nan)
    if not (_shirina(C, ctx["M"]) >= 0.55):
        return out
    v = el & (C[-1] > s200)
    if v.sum() < 8:
        return out
    porog = np.quantile(r20[v], 0.3)
    return np.where(v & (r20 <= porog), 1.0, out)


def bull_sila_k_btc(C, DV, ctx):
    """лидерство альтов: BTC выше своей SMA50, бумага обгоняет BTC за 20 дней больше чем на 1 сигму"""
    S = ctx.get("simvoly") or []
    if C.shape[0] < 51 or "BTCUSDT" not in S:
        return np.full(C.shape[1], np.nan)
    b = S.index("BTCUSDT"); M = ctx["M"][-1]; r20 = _ret(C, 20)
    s50 = _sma_last(C, 50)
    el = M & np.isfinite(C[-1]) & np.isfinite(r20)
    out = np.where(el, 0.0, np.nan)
    if not (np.isfinite(s50[b]) and np.isfinite(C[-1, b]) and C[-1, b] > s50[b]):
        return out
    if el.sum() < 8 or not np.isfinite(r20[b]):
        return out
    sd = float(np.nanstd(r20[el], ddof=1))
    if not np.isfinite(sd) or sd <= 0:
        return out
    return np.where(el & (r20 - r20[b] > sd), 1.0, out)


# ── пакет v5 (PREREG_PAKET_V5_2026_09_23.md) ─────────────────────────
# Единственный механизм роста, переживший пакет v4, — относительная сила
# к эталону. Проверяем его в другом рынке (акции) и в другой конструкции
# (рыночно-нейтральная), плюс два самостоятельных вопроса.
PV5 = "research_lab/fabrika/PREREG_PAKET_V5_2026_09_23.md"


def _indeks(C, M):
    """равновзвешенный индекс вселенной: ряд средних доходностей членов"""
    el = M[-1] & np.isfinite(C[-1])
    return el


def _r20_etalon_akcii(C, ctx):
    """доходность равновзвешенного индекса за 20 дней и его SMA50"""
    if C.shape[0] < 51:
        return None, None
    M = ctx["M"]
    lr = np.diff(np.log(C[-21:]), axis=0)
    el = M[-1] & np.isfinite(lr).all(axis=0)
    if el.sum() < 10:
        return None, None
    r_ind = float(np.exp(lr[:, el].mean(axis=1).sum()) - 1)
    lr50 = np.diff(np.log(C[-51:]), axis=0)
    el2 = M[-1] & np.isfinite(lr50).all(axis=0)
    if el2.sum() < 10:
        return r_ind, None
    put = np.concatenate([[1.0], np.cumprod(np.exp(lr50[:, el2].mean(axis=1)))])
    return r_ind, bool(put[-1] > put.mean())


def akc_sila_k_indeksu(C, DV, ctx):
    """акция обгоняет равновзвешенный индекс за 20 дней больше чем на сигму сечения,
    сам индекс выше своей средней за 50 дней"""
    if C.shape[0] < 51:
        return np.full(C.shape[1], np.nan)
    r_ind, rastyot = _r20_etalon_akcii(C, ctx)
    r20 = _ret(C, 20)
    el = ctx["M"][-1] & np.isfinite(r20) & _likvid(C, DV)
    out = np.where(el, 0.0, np.nan)
    if r_ind is None or not rastyot or el.sum() < 10:
        return out
    sd = float(np.nanstd(r20[el], ddof=1))
    if not np.isfinite(sd) or sd <= 0:
        return out
    return np.where(el & (r20 - r_ind > sd), 1.0, out)


def akc_novyy_maksimum(C, DV, ctx):
    """акция закрылась на 60-дневном максимуме, выше своей SMA100, участие ≥ 0.50"""
    if C.shape[0] < 101:
        return np.full(C.shape[1], np.nan)
    s100 = _sma_last(C, 100); mx60 = np.nanmax(C[-60:], axis=0)
    el = ctx["M"][-1] & np.isfinite(C[-1]) & np.isfinite(s100) & np.isfinite(mx60) & _likvid(C, DV)
    out = np.where(el, 0.0, np.nan)
    sh = _shirina(C, ctx["M"])
    if not (np.isfinite(sh) and sh >= 0.50):
        return out
    return np.where(el & (C[-1] >= mx60) & (C[-1] > s100), 1.0, out)


def kr_sila_k_btc_ls(C, DV, ctx):
    """рыночно-нейтральная относительная сила: оценка = обгон BTC за 20 дней.
    Режима BTC здесь нет — короткая нога снимает общий рост."""
    S = ctx.get("simvoly") or []
    if C.shape[0] < 21 or "BTCUSDT" not in S:
        return np.full(C.shape[1], np.nan)
    b = S.index("BTCUSDT"); r20 = _ret(C, 20)
    if not np.isfinite(r20[b]):
        return np.full(C.shape[1], np.nan)
    el = ctx["M"][-1] & np.isfinite(r20)
    return np.where(el, r20 - r20[b], np.nan)


def kr_beta_ls(C, DV, ctx):
    """бета к BTC за 60 дней; оценка = минус бета: лонг тихих, шорт разгонных"""
    S = ctx.get("simvoly") or []
    if C.shape[0] < 61 or "BTCUSDT" not in S:
        return np.full(C.shape[1], np.nan)
    b = S.index("BTCUSDT")
    lr = np.diff(np.log(C[-61:]), axis=0)
    x = lr[:, b]
    if not np.isfinite(x).all():
        return np.full(C.shape[1], np.nan)
    vx = float(np.var(x, ddof=1))
    el = ctx["M"][-1] & np.isfinite(lr).all(axis=0)
    out = np.full(C.shape[1], np.nan)
    if vx <= 0 or el.sum() < 10:
        return out
    idx = np.flatnonzero(el)
    cov = ((lr[:, idx] - lr[:, idx].mean(axis=0)) * (x - x.mean())[:, None]).sum(axis=0) / (len(x) - 1)
    out[idx] = -cov / vx
    return out


# ── пакет v6 «рост»: четыре разных источника причинности ─────────────
# Каждый механизм отвечает на свой вопрос и имеет свою предрегистрацию.
# Ни один не является вариантом другого.
P6_OI = "research_lab/fabrika/PREREG_V6_OI_NAKOPLENIE_2026_09_24.md"
P6_ROT = "research_lab/fabrika/PREREG_V6_ROTACIYA_IZ_BTC_2026_09_24.md"
P6_ASI = "research_lab/fabrika/PREREG_V6_ASIMMETRIYA_VOL_2026_09_24.md"
P6_OST = "research_lab/fabrika/PREREG_V6_OSTATOCHNYY_MOMENT_2026_09_24.md"


def oi_nakoplenie(C, DV, ctx):
    """ДЕРИВАТИВЫ. Цена вверх И открытый интерес вверх — в позицию заходят
    новые деньги. Цена вверх при падающем OI — это закрытие шортов, чужая
    позиция гасится, продолжения ждать не от кого."""
    OI = ctx.get("OI")
    if OI is None or C.shape[0] < 6 or OI.shape[0] < 6:
        return np.full(C.shape[1], np.nan)
    M = ctx["M"][-1]; r5 = _ret(C, 5)
    o0, o5 = OI[-1], OI[-6]
    el = M & np.isfinite(r5) & np.isfinite(o0) & np.isfinite(o5) & (o5 > 0)
    out = np.where(el, 0.0, np.nan)
    if el.sum() < 10:
        return out
    doi = np.where(el, o0 / np.where(o5 > 0, o5, np.nan) - 1, np.nan)
    porog = float(np.quantile(doi[el], 0.6))          # верхние 40% по приросту OI
    return np.where(el & (r5 > 0) & (doi >= porog) & (doi > 0), 1.0, out)


def priznak_rotaciya_iz_btc(R):
    """РОТАЦИЯ. Доля BTC в долларовом открытом интересе вселенной за 10 дней.
    Признак > 0 — доля упала, то есть деньги переливаются из биткоина в альты."""
    OI, C, M, S = R.get("OI"), R["C"], R["M"], R["simvoly"]
    T = len(R["dates"])
    if OI is None or "BTCUSDT" not in S:
        return np.full(T, np.nan)
    b = S.index("BTCUSDT")
    dolya = np.full(T, np.nan)
    for t in range(T):
        el = M[t] & np.isfinite(OI[t]) & np.isfinite(C[t])
        if el.sum() < 10 or not (np.isfinite(OI[t, b]) and np.isfinite(C[t, b])):
            continue
        vsego = float((OI[t, el] * C[t, el]).sum())
        if vsego > 0:
            dolya[t] = float(OI[t, b] * C[t, b] / vsego)
    out = np.full(T, np.nan)
    for t in range(10, T):
        if np.isfinite(dolya[t]) and np.isfinite(dolya[t - 10]):
            out[t] = dolya[t - 10] - dolya[t]
    return out


def asimmetriya_vol(C, DV, ctx):
    """ВОЛАТИЛЬНОСТЬ. За 30 дней: разброс дней роста против разброса дней
    падения. Накопление выглядит как сильные подъёмы и мелкие откаты.
    Это не сжатие и не пробой: тут важна ФОРМА движения, а не его размер."""
    if C.shape[0] < 31:
        return np.full(C.shape[1], np.nan)
    lr = np.diff(np.log(C[-31:]), axis=0)
    M = ctx["M"][-1]
    out = np.full(C.shape[1], np.nan)
    for j in np.flatnonzero(M & np.isfinite(lr).all(axis=0)):
        x = lr[:, j]; up = x[x > 0]; dn = x[x < 0]
        if len(up) < 5 or len(dn) < 5:
            continue
        sd = float(dn.std(ddof=1))
        if sd > 0:
            out[j] = float(up.std(ddof=1)) / sd
    return out


def ostatochnyy_moment(C, DV, ctx):
    """СЕЧЕНИЕ. 20-дневная доходность за вычетом того, что объясняется бетой
    монеты к BTC. Наивное «минус доходность BTC» порядок не меняет вовсе —
    это общая константа дня. Бета у каждой монеты своя, и она меняет."""
    S = ctx.get("simvoly") or []
    if C.shape[0] < 61 or "BTCUSDT" not in S:
        return np.full(C.shape[1], np.nan)
    b = S.index("BTCUSDT")
    lr = np.diff(np.log(C[-61:]), axis=0)
    x = lr[:, b]
    if not np.isfinite(x).all():
        return np.full(C.shape[1], np.nan)
    vx = float(np.var(x, ddof=1)); r20 = _ret(C, 20); r20b = r20[b]
    el = ctx["M"][-1] & np.isfinite(r20) & np.isfinite(lr).all(axis=0)
    out = np.full(C.shape[1], np.nan)
    if vx <= 0 or el.sum() < 10 or not np.isfinite(r20b):
        return out
    idx = np.flatnonzero(el)
    sr = lr[:, idx] - lr[:, idx].mean(axis=0)
    cov = (sr * (x - x.mean())[:, None]).sum(axis=0) / (len(x) - 1)
    out[idx] = r20[idx] - (cov / vx) * r20b
    return out


# ── независимая проверка остаточного моментума на акциях ─────────────
# Ждёт глубокой истории Alpaca. Правила заморожены 24.09.2026 до прогона.
P7 = "research_lab/fabrika/PREREG_AKC_OSTATOCHNYY_MOMENT_2026_09_24.md"


def _indeks_ryad(C, M, n):
    """равновзвешенный индекс вселенной за n дней: ряд средних лог-доходностей"""
    if C.shape[0] < n + 1:
        return None
    lr = np.diff(np.log(C[-n - 1:]), axis=0)
    el = M[-1] & np.isfinite(lr).all(axis=0)
    if el.sum() < 10:
        return None
    return lr[:, el].mean(axis=1)


def akc_ostatochnyy_moment(C, DV, ctx):
    """То же, что KR_OSTATOCHNYY_MOMENT, но эталон — равновзвешенный индекс
    вселенной акций, а не BTC. Бета считается за 60 дней, из 20-дневной
    доходности вычитается бета × доходность индекса за те же 20 дней."""
    M = ctx["M"]
    ind = _indeks_ryad(C, M, 60)
    if ind is None or C.shape[0] < 61:
        return np.full(C.shape[1], np.nan)
    vx = float(np.var(ind, ddof=1))
    r20 = _ret(C, 20)
    ind20 = _indeks_ryad(C, M, 20)
    if ind20 is None or vx <= 0:
        return np.full(C.shape[1], np.nan)
    r20i = float(np.exp(ind20.sum()) - 1)
    lr = np.diff(np.log(C[-61:]), axis=0)
    el = M[-1] & np.isfinite(r20) & np.isfinite(lr).all(axis=0) & _likvid(C, DV)
    out = np.full(C.shape[1], np.nan)
    if el.sum() < 10:
        return out
    idx = np.flatnonzero(el)
    sr = lr[:, idx] - lr[:, idx].mean(axis=0)
    cov = (sr * (ind - ind.mean())[:, None]).sum(axis=0) / (len(ind) - 1)
    out[idx] = r20[idx] - (cov / vx) * r20i
    return out


# napravlenie: ls — лонг верх / шорт низ; long — только лонг верхней доли
SIGNALY = {
    "AKC_MOM_6_1":      dict(fn=mom_6_1, rynok="akcii_pit", napr="ls", kv=0.1, H=5, semya="xs_momentum"),
    "AKC_MOM_6_1_LONG": dict(fn=mom_6_1, rynok="akcii_pit", napr="long", kv=0.1, H=5, semya="xs_momentum_long"),
    "AKC_REVERSAL_5D":  dict(fn=reversal_5d, rynok="akcii_pit", napr="ls", kv=0.1, H=5, semya="xs_reversal"),
    "AKC_LOW_VOL_60":   dict(fn=low_vol_60, rynok="akcii_pit", napr="ls", kv=0.1, H=5, semya="low_volatility"),
    "AKC_BLIZ_MAX_126": dict(fn=blizost_k_maksimumu, rynok="akcii_pit", napr="ls", kv=0.1, H=5, semya="high_proximity"),
    "KR_XSEC_V3":       dict(fn=xsec_v3, rynok="kripto_pit", napr="ls", kv=0.25, H=3, semya="xs_momentum_vol"),
    "KR_FANDING_KERRI": dict(fn=fanding_kerri, rynok="kripto_pit", napr="ls", kv=0.25, H=3, semya="funding_carry",
                             nuzhen_fanding=True),
    # пакет v3
    "XSEC_3D_REVERSAL": dict(fn=reversal_3d, rynok="kripto_pit50", napr="ls", kv=0.25, H=3, semya="xs_reversal",
                             ctx=True, prereg=PV3, slot="neytral"),
    "BULL_LEADER_PULLBACK_BASE": dict(fn=lider_otkat_base, rynok="kripto_pit50", napr="long", vybor=True, H=5,
                                      semya="bull_leader_pullback", ctx=True, prereg=PV3, slot="rost"),
    "BULL_LEADER_PULLBACK_FILTERED": dict(fn=lider_otkat_filtr, rynok="kripto_pit50", napr="long", vybor=True, H=5,
                                          semya="bull_leader_pullback_f", ctx=True, prereg=PV3, slot="rost"),
    "BULL_VOL_EXPANSION_BASE": dict(fn=szhatie_base, rynok="kripto_pit50", napr="long", vybor=True, H=5,
                                    semya="bull_vol_expansion", ctx=True, prereg=PV3, slot="rost"),
    "BULL_VOL_EXPANSION_POLY": dict(fn=szhatie_poly, rynok="kripto_pit50_poly", napr="long", vybor=True, H=5,
                                    semya="bull_vol_expansion_poly", ctx=True, prereg=PPOLY, slot="rost"),
    "BULL_VOL_EXPANSION_FILTERED": dict(fn=szhatie_filtr, rynok="kripto_pit50", napr="long", vybor=True, H=5,
                                        semya="bull_vol_expansion_f", ctx=True, prereg=PV3, slot="rost"),
    # пакет v4 «рост»
    "BULL_NOVYY_MAKSIMUM": dict(fn=bull_novyy_maksimum, rynok="kripto_pit50", napr="long", vybor=True, H=5,
                                semya="bull_new_high", ctx=True, prereg=PV4, slot="rost"),
    "BULL_OTSTAYUSHCHIY": dict(fn=bull_otstayushchiy, rynok="kripto_pit50", napr="long", vybor=True, H=5,
                               semya="bull_laggard", ctx=True, prereg=PV4, slot="rost"),
    "BULL_SILA_K_BTC": dict(fn=bull_sila_k_btc, rynok="kripto_pit50", napr="long", vybor=True, H=5,
                            semya="bull_rs_btc", ctx=True, prereg=PV4, slot="rost"),
    # пакет v5
    "AKC_SILA_K_INDEKSU": dict(fn=akc_sila_k_indeksu, rynok="akcii_pit", napr="long", vybor=True, H=5,
                               semya="rs_vs_etalon", ctx=True, prereg=PV5, slot="akcii"),
    "AKC_NOVYY_MAKSIMUM": dict(fn=akc_novyy_maksimum, rynok="akcii_pit", napr="long", vybor=True, H=5,
                               semya="new_high", ctx=True, prereg=PV5, slot="akcii"),
    "KR_SILA_K_BTC_LS": dict(fn=kr_sila_k_btc_ls, rynok="kripto_pit50", napr="ls", kv=0.2, H=5,
                             semya="rs_vs_etalon_ls", ctx=True, prereg=PV5, slot="neytral"),
    "KR_BETA_LS": dict(fn=kr_beta_ls, rynok="kripto_pit50", napr="ls", kv=0.2, H=5,
                       semya="beta_k_btc", ctx=True, prereg=PV5, slot="neytral"),
    # пакет v6 «рост»
    "KR_OI_NAKOPLENIE": dict(fn=oi_nakoplenie, rynok="kripto_pit50", napr="long", vybor=True, H=5,
                             semya="oi_nakoplenie", ctx=True, prereg=P6_OI, slot="rost"),
    "KR_ASIMMETRIYA_VOL": dict(fn=asimmetriya_vol, rynok="kripto_pit50", napr="long", kv=0.2, H=5,
                               semya="asimmetriya_vol", ctx=True, prereg=P6_ASI, slot="rost"),
    "KR_OSTATOCHNYY_MOMENT": dict(fn=ostatochnyy_moment, rynok="kripto_pit50", napr="long", kv=0.2, H=5,
                                  semya="ostatochnyy_moment", ctx=True, prereg=P6_OST, slot="rost"),
    "AKC_OSTATOCHNYY_MOMENT": dict(fn=akc_ostatochnyy_moment, rynok="akcii_pit", napr="long", kv=0.2, H=5,
                                   semya="ostatochnyy_moment", ctx=True, prereg=P7, slot="akcii"),
}
