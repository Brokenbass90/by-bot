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


def zagruzit_kripto_pit():
    """Топ-20 по открытому интересу, известному строго до даты (basis/vselennaya_pit.json).
    Цены: data/pit_daily/*.json (скачиваются dannye_pit_kripto.py), иначе из data/h1.
    Фандинг: оттуда же и из bybit_public_archive_2023/funding."""
    v = json.load(open(DATA / "basis/vselennaya_pit.json"))
    S = sorted(v["simvoly"]); ser, fnd = {}, {}
    for s in S:
        p = DATA / f"pit_daily/{s}.json"
        if p.exists():
            d = json.load(open(p))
            ser[s] = {int(r[0]) // DEN * DEN: float(r[4]) for r in d.get("daily", [])}
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
    FOK = np.zeros_like(C, dtype=bool)
    for j, s in enumerate(S):
        for t, c in ser.get(s, {}).items():
            if t in di: C[di[t], j] = c
        for t, r in fnd.get(s, []):
            k = di.get(int(t) // DEN * DEN)
            if k is not None: F[k, j] += r; FOK[k, j] = True
    for d, sl in v["sostav"].items():
        k = di.get(_ms(d))
        if k is not None:
            for s in sl:
                M[k, S.index(s)] = True
    return dict(dates=dates, simvoly=S, C=C, DV=None, M=M, F=F, FOK=FOK, fee_bps=7.0,
                razdel=_ms("2025-10-01"), opisanie="крипта PIT: топ-20 по OI на дату")


RYNKI_P = {"akcii_pit": zagruzit_akcii, "kripto_pit": zagruzit_kripto_pit}


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
}
