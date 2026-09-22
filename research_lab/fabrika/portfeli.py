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
    for j, s in enumerate(S):
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
    return dict(dates=dates, simvoly=S, C=C, DV=None, M=M, F=F, FOK=FOK, HH=HH, VV=VV, fee_bps=7.0,
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
    if C.shape[0] < 202:
        return np.full(C.shape[1], np.nan)
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
}
