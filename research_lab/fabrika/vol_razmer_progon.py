#!/usr/bin/env python3
"""Прогон PREREG_VOL_PERSISTENCE_RAZMER_2026_10_17 (6246ab2). Окно KRIPTO_D1_2021H2_2022, одна попытка."""
import datetime as dt, json
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; H = 3_600_000
z = np.load(LAB / "data/h1/BTCUSDT_B21.npz"); ts = z["ts"].astype(np.int64); o = z["ohlcv"][:, 0].astype(float); c = z["ohlcv"][:, 3].astype(float)
lr = np.r_[np.nan, np.diff(np.log(c))]                     # lr[i] — доходность бара i (закрытие i-1 → закрытие i)
S = int(dt.datetime(2021, 7, 1, tzinfo=dt.timezone.utc).timestamp() * 1000); E = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
IZD = 11.0


def sd(i, n):                                               # по барам i-n … i-1 (закрыты до входа в бар i)
    x = lr[i - n:i]; return float(np.std(x, ddof=1)) if i - n >= 1 and np.all(np.isfinite(x)) and ts[i - 1] - ts[i - n] == (n - 1) * H else None


sdelki = []
for i in range(len(ts)):
    t = int(ts[i])
    if not (S <= t < E) or dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).hour != 16: continue
    if i + 23 >= len(ts) or ts[i + 23] - t != 23 * H or i < 1500: continue
    v24, v168, v720 = sd(i, 24), sd(i, 168), sd(i, 720)
    istor = [sd(j, 24) for j in range(i - 720, i, 24)]
    if None in (v24, v168, v720) or None in istor: continue
    prog = 0.3 * v24 + 0.4 * v168 + 0.3 * v720; cel = float(np.median(istor))
    sdelki.append(dict(t=t, r=(c[i + 23] / o[i] - 1) * 1e4, razmer=float(np.clip(cel / prog, 0.25, 2.0))))
sr = float(np.mean([s["razmer"] for s in sdelki]))


def metriki(pnl, razmery):
    pnl = np.array(pnl); kum = np.cumsum(pnl); dd = float(np.max(np.maximum.accumulate(np.r_[0, kum])[1:] - kum))
    hv = np.sort(pnl)[:max(1, int(round(0.05 * len(pnl))))]
    return dict(chistyy_pnl=round(float(kum[-1]), 1), maks_prosadka=round(dd, 1), pnl_k_prosadke=round(float(kum[-1]) / dd, 3) if dd else None,
                kapital_sredniy=round(float(np.mean(razmery)), 3), kapital_pik=round(float(np.max(razmery)), 3),
                cvar5=round(float(np.mean(hv)), 1), hudshaya=round(float(pnl.min()), 1))


rez = dict(n_sdelok=len(sdelki), sredniy_razmer_HAR=round(sr, 4), s=sdelki[0]["t"], po=sdelki[-1]["t"], potoki={})
ok = True
for imya, znak in (("LONG", 1), ("SHORT", -1)):
    p_c = [sr * (znak * s["r"] - IZD) for s in sdelki]; p_h = [s["razmer"] * (znak * s["r"] - IZD) for s in sdelki]
    mc, mh = metriki(p_c, [sr] * len(sdelki)), metriki(p_h, [s["razmer"] for s in sdelki])
    usl = dict(prosadka=mh["maks_prosadka"] <= 0.85 * mc["maks_prosadka"], cvar5=mh["cvar5"] >= 0.85 * mc["cvar5"],
               pnl=mh["chistyy_pnl"] >= mc["chistyy_pnl"] - 0.10 * abs(mc["chistyy_pnl"]))
    ok &= all(usl.values()); rez["potoki"][imya] = dict(POSTOYANNYY=mc, HAR=mh, usloviya=usl)
rez["verdikt"] = "PASS" if ok else "FAIL"
(LAB / "data/factory_v3/VOL_RAZMER_rezultat.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1))
print(json.dumps(rez, ensure_ascii=False, indent=1))
