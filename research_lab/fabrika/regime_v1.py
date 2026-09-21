"""regime_v1.py — REGIME_V1: метка состояния крипторынка на день. ЗАМОРОЖЕНО 21.09.2026.

Это МЕТКА, а не торговый фильтр. Фабрика использует её, чтобы ответить
«в каком режиме механизм работает». Пороги ниже не меняются после
результатов тестов; изменение = REGIME_V2 с новой предрегистрацией.

Всё причинно: метка дня t считается по закрытиям до t включительно.
    тренд    : BTC выше SMA200 и наклон SMA50 за 20 дней > 0  → +1
               BTC ниже SMA200 и наклон SMA50 за 20 дней < 0  → −1, иначе 0
    ширина   : доля монет PIT-вселенной (топ-50 по OI в ДОЛЛАРАХ на дату, ≥50 дней цен) выше своей SMA50
    волат.   : реализованная волатильность BTC 30 дней, перцентиль к прошлым 365 дням
    разброс  : разброс 7-дневных доходностей монет вселенной, перцентиль к прошлым 365 дням
    СОСТОЯНИЕ: BULL      если тренд = +1 и ширина ≥ 0.55
               BEAR      если тренд = −1 и ширина ≤ 0.45
               SIDEWAYS  иначе
    ТЕГИ     : VOL_HIGH (≥0.8), VOL_LOW (≤0.2), DISP_HIGH (≥0.8), DISP_LOW (≤0.2)
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np

LAB = Path(__file__).resolve().parents[1]
DEN = 86400000
POROGI = dict(sma_dlin=200, sma_kor=50, naklon_dney=20, shir_bull=0.55, shir_bear=0.45,
              vol_okno=30, disp_okno=7, pct_okno=365, vysoko=0.8, nizko=0.2)


def _sma(x, n):
    out = np.full(len(x), np.nan)
    ok = np.isfinite(x)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        if np.isfinite(w).all():
            out[i] = w.mean()
    return out


def _pct(x, okno):
    out = np.full(len(x), np.nan)
    for i in range(okno, len(x)):
        h = x[i - okno:i]; h = h[np.isfinite(h)]
        if len(h) >= okno // 2 and np.isfinite(x[i]):
            out[i] = (h < x[i]).mean()
    return out


def btc_dnevnye(dates):
    """BTC: data/pit_daily/BTCUSDT.json, иначе дневные закрытия из data/h1/BTCUSDT.npz"""
    c = {}
    p = LAB / "data/pit_daily/BTCUSDT.json"
    if p.exists():
        c = {int(r[0]) // DEN * DEN: float(r[4]) for r in json.load(open(p))["daily"]}
    else:
        z = np.load(LAB / "data/h1/BTCUSDT.npz")
        for t, x in zip(z["ts"] // DEN * DEN, z["ohlcv"][:, 3]):
            c[int(t)] = float(x)
    return np.array([c.get(int(t), np.nan) for t in dates])


FAYL_VSELENNOY = "basis/vselennaya_pit_usd50.json"


def metki():
    import portfeli
    R = portfeli.zagruzit_kripto_pit(FAYL_VSELENNOY); dates, C, M = R["dates"], R["C"], R["M"]
    P = POROGI
    b = btc_dnevnye(dates)
    s200, s50 = _sma(b, P["sma_dlin"]), _sma(b, P["sma_kor"])
    naklon = np.full(len(b), np.nan); naklon[P["naklon_dney"]:] = s50[P["naklon_dney"]:] / s50[:-P["naklon_dney"]] - 1
    trend = np.where((b > s200) & (naklon > 0), 1, np.where((b < s200) & (naklon < 0), -1, 0))
    trend = np.where(np.isfinite(s200) & np.isfinite(naklon), trend, 0).astype(int)
    sma50 = np.column_stack([_sma(C[:, j], P["sma_kor"]) for j in range(C.shape[1])])
    shir = np.full(len(dates), np.nan); disp = np.full(len(dates), np.nan)
    r7 = np.full_like(C, np.nan); r7[P["disp_okno"]:] = C[P["disp_okno"]:] / C[:-P["disp_okno"]] - 1
    for t in range(len(dates)):
        el = M[t] & np.isfinite(sma50[t]) & np.isfinite(C[t])
        if el.sum() >= 8:
            shir[t] = (C[t, el] > sma50[t, el]).mean()
        el7 = M[t] & np.isfinite(r7[t])
        if el7.sum() >= 8:
            disp[t] = np.std(r7[t, el7])
    lr = np.diff(np.log(b), prepend=np.nan)
    vol = np.full(len(b), np.nan)
    for t in range(P["vol_okno"], len(b)):
        w = lr[t - P["vol_okno"] + 1:t + 1]
        if np.isfinite(w).all():
            vol[t] = w.std(ddof=1) * np.sqrt(365)
    vp, dp = _pct(vol, P["pct_okno"]), _pct(disp, P["pct_okno"])
    out = {}
    for t in range(len(dates)):
        if not (np.isfinite(s200[t]) and np.isfinite(shir[t])):
            continue
        st = ("BULL" if trend[t] == 1 and shir[t] >= P["shir_bull"] else
              "BEAR" if trend[t] == -1 and shir[t] <= P["shir_bear"] else "SIDEWAYS")
        tegi = []
        if np.isfinite(vp[t]):
            tegi += ["VOL_HIGH"] if vp[t] >= P["vysoko"] else ["VOL_LOW"] if vp[t] <= P["nizko"] else []
        if np.isfinite(dp[t]):
            tegi += ["DISP_HIGH"] if dp[t] >= P["vysoko"] else ["DISP_LOW"] if dp[t] <= P["nizko"] else []
        out[int(dates[t])] = {"sost": st, "trend": int(trend[t]), "shirina": round(float(shir[t]), 3),
                              "vol_pct": None if not np.isfinite(vp[t]) else round(float(vp[t]), 3),
                              "disp_pct": None if not np.isfinite(dp[t]) else round(float(dp[t]), 3), "tegi": tegi}
    return out


if __name__ == "__main__":
    import collections, datetime as dt, sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    m = metki(); ks = sorted(m)
    print("дней с меткой:", len(m), dt.datetime.utcfromtimestamp(ks[0] / 1000).date(), "…",
          dt.datetime.utcfromtimestamp(ks[-1] / 1000).date())
    print("доля дней по состояниям:", {k: round(v / len(m), 2) for k, v in collections.Counter(x["sost"] for x in m.values()).items()})


def proverka_prichinnosti(obrez_dnya=900):
    """метки до даты обреза не должны меняться, если будущих данных нет вовсе"""
    import portfeli
    polnye = metki()
    orig = portfeli.zagruzit_kripto_pit
    def obrez(*a, **kw):
        R = orig(*a, **kw); k = obrez_dnya
        return dict(R, dates=R["dates"][:k], C=R["C"][:k], M=R["M"][:k], F=R["F"][:k])
    portfeli.zagruzit_kripto_pit = obrez
    try:
        chast = metki()
    finally:
        portfeli.zagruzit_kripto_pit = orig
    raznye = [t for t in chast if chast[t] != polnye.get(t)]
    return len(chast), raznye
