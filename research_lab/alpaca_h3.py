#!/usr/bin/env python3
"""Прогон PREREG_ALPACA_H3_KESH_I_PONEDELNIK_2026_10_18 (f37ae4f).
Часть A — оверлей SPY на простаивающий кэш Monthly (книга Monthly не меняется).
Часть B — W_ROT (полная ротация каждую неделю) и кривая превышения выбора по горизонтам 5/10/21/42.
python3 research_lab/alpaca_h3.py --vselennaya U2|U58 [--u2 ... --sprav ...] --vyvod out/h3_U2.json"""
from __future__ import annotations

import argparse, json, math, random, sys
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from backtest.alpaca_bakeoff_v2_contract import spy200_gate
from research_lab.alpaca_dannye import chasovye, v_dnevnye
from research_lab.alpaca_dvizhok_x_v1 import dvizhok_x
import research_lab.alpaca_u2 as U2M

KRIZISY = {"2018_Q4": ("2018-10-01", "2019-01-31"), "2020_covid": ("2020-02-15", "2020-05-31"),
           "2022_bear": ("2022-01-01", "2022-12-31"), "2025_fevral": ("2025-02-19", "2025-05-07")}
STOP_PRICHINY = ("protective_stop",)          # стоп-выходы освобождают деньги только к следующему открытию


def godovyh(e0, e1, d0: date, d1: date):
    let = max((d1 - d0).days / 365.25, 1 / 12)
    return ((e1 / e0) ** (1 / let) - 1) * 100 if e1 > 0 else -100.0


def metriki(daty: list[date], eq: list[float], e0: float):
    pik, dd, dlit, tek = e0, 0.0, 0, 0
    for x in eq:
        if x >= pik:
            pik, tek = x, 0
        else:
            tek += 1; dlit = max(dlit, tek)
        dd = min(dd, x / pik - 1)
    cagr = godovyh(e0, eq[-1], daty[0], daty[-1])
    return {"cagr_pct": cagr, "maxDD_pct": -dd * 100, "calmar": cagr / (-dd * 100) if dd < 0 else float("inf"),
            "vosstanovlenie_max_sessiy": dlit, "itog": eq[-1] / e0}


def monthly_kniga(U, okno, resh, bp):
    z = dvizhok_x(U.p, okno, resh, initial_capital=1000.0, target_gross_exposure=0.70, cost_bps_per_side=bp,
                  policy=U2M.POL, mest=4)
    rows = z["daily_equity"]
    rot, stop = {}, {}
    for t in z["trades"]:
        d = t["exit_session"]; v = t["qty"] * t["exit_fill"]
        if t["reason"].startswith(STOP_PRICHINY) or t["reason"].startswith("entry_gap"):
            stop[d] = stop.get(d, 0.0) + v
        else:
            rot[d] = rot.get(d, 0.0) + v
    return z, rows, rot, stop


def overlay(U, okno, rows, rot, stop, bp, rezhim: str):
    """rezhim: NONE | G200 | ALL | G200_R30. Возвращает дневной капитал всей книги и показатели оверлея."""
    spy = {r.session_date: r for r in U.p["SPY"]}
    spy_c = [r.close for r in U.p["SPY"]]
    k_spy = {r.session_date: i for i, r in enumerate(U.p["SPY"])}
    P = 0.0                     # накопленный результат оверлея (деньги книги оверлея)
    u = 0.0                     # единиц SPY
    eq, daty, dolya_svob, oborot, sdelok, potrebnost, pozicii = [], [], [], 0.0, 0, 0.0, []
    prev = None
    for r in rows:
        d = date.fromisoformat(r["session"]); ds = r["session"]
        b = spy[d]
        if prev is None:
            svob_open = r["cash"] - stop.get(ds, 0.0)
            posval_open = r["equity"] - r["cash"]
        else:
            svob_open = r["cash"] - stop.get(ds, 0.0)            # = кэш(t−1) − покупки(t) + ротация(t)
            posval_open = max(0.0, prev["equity"] - prev["cash"] + (prev["cash"] + rot.get(ds, 0.0) + stop.get(ds, 0.0)
                                                                   - r["cash"]) - rot.get(ds, 0.0))
        # переоценка оверлея на открытии t
        P += u * (b.open - (spy[date.fromisoformat(prev["session"])].close if prev else b.open)) if prev else 0.0
        vsego_open = posval_open + svob_open + P
        svob = max(0.0, svob_open + P)
        i = k_spy[d]
        vorota = spy200_gate(spy_c[:i]) if i >= 200 else False          # закрытие t−1
        if rezhim == "NONE":
            cel = 0.0
        elif rezhim == "ALL":
            cel = svob
        else:
            cel = svob if vorota else 0.0
            if rezhim == "G200_R30":
                cel = min(cel, max(0.0, 0.70 * vsego_open - posval_open))
        tek = u * b.open
        diff = cel - tek
        if abs(diff) > 1e-9:
            P -= abs(diff) * bp / 1e4
            oborot += abs(diff) / max(vsego_open, 1e-9)
            if abs(diff) > 0.01 * vsego_open:
                sdelok += 1
            if diff < 0:
                potrebnost = max(potrebnost, -diff / max(vsego_open, 1e-9))
            u = cel / b.open
        # закрытие t
        P += u * (b.close - b.open)
        vsego = r["equity"] + P
        eq.append(vsego); daty.append(d)
        dolya_svob.append(max(0.0, r["cash"] + P - u * b.close) / vsego if vsego > 0 else 0.0)
        pozicii.append((r["equity"] - r["cash"] + u * b.close) / vsego if vsego > 0 else 0.0)
        prev = r
    m = metriki(daty, eq, 1000.0)
    m.update(oborot_dol_kapitala=oborot, sdelok_overleya=sdelok, svobodno_srednee=float(np.mean(dolya_svob)),
             ekspoziciya_srednyaya=float(np.mean(pozicii)), potrebnost_likvidnosti_max=potrebnost)
    return m, daty, eq


def spy_bh(U, okno, bp):
    spy = {r.session_date: r for r in U.p["SPY"]}
    u = 1000.0 / (spy[okno[0]].open * (1 + bp / 1e4))
    eq = [u * spy[d].close for d in okno]
    return metriki(list(okno), eq, 1000.0)


def podperiody(daty, eq):
    out = {}
    for k, (a, b) in U2M.PODPERIODY.items():
        idx = [i for i, d in enumerate(daty) if a <= d.isoformat() <= b]
        if len(idx) > 30:
            out[k] = metriki([daty[i] for i in idx], [eq[i] for i in idx], eq[idx[0]])
    return out


def nedelnoe(sessii, okno):
    """Сигнал — последняя сессия ISO-недели, вход — следующая сессия."""
    out = []
    for i in range(len(sessii) - 1):
        if sessii[i].isocalendar()[:2] != sessii[i + 1].isocalendar()[:2] and okno[0] <= sessii[i + 1] <= okno[-1]:
            out.append((sessii[i], sessii[i + 1]))
    return out


def gorizonty(U, resh, H=(5, 10, 21, 42), sid=20261018):
    rnd = random.Random(sid); acc = {h: [] for h in H}
    for d in resh:
        if not d.picks:
            continue
        sig = d.signal_session; i = U.i_sessii[sig]
        pul = sorted(U.dopustimye(sig)); hist = U.istoriya(sig, pul)
        vv = {}
        for s in pul:
            if s in hist and len(hist[s]) > 21:
                h_ = hist[s]; r = [h_[j].close / h_[j - 1].close - 1 for j in range(len(h_) - 20, len(h_))]
                vv[s] = float(np.std(r))
        if len(vv) < 20:
            continue
        kr = np.quantile(list(vv.values()), np.linspace(0, 1, 11))
        dec = lambda x: int(np.clip(np.searchsorted(kr, x, side="right") - 1, 0, 9))
        po = {}
        for s, x in vv.items():
            po.setdefault(dec(x), []).append(s)
        for c in d.picks:
            if c.symbol not in vv:
                continue
            gr = [s for s in po[dec(vv[c.symbol])] if s != c.symbol]
            kontr = rnd.sample(gr, min(5, len(gr)))
            if not kontr:
                continue
            for h in H:
                if i + h >= len(U.sessii):
                    continue
                sh = U.sessii[i + h]
                f = lambda s: U.p[s][U._k(s, sh) - 1].close / U.p[s][U._k(s, sig) - 1].close - 1
                acc[h].append(f(c.symbol) - float(np.mean([f(s) for s in kontr])))
    out = {}
    for h, x in acc.items():
        x = np.array(x)
        out[str(h)] = {"n": len(x), "prevyshenie_pct": float(x.mean() * 100),
                       "t": float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else None,
                       "za_sessiyu_bps": float(x.mean() / h * 1e4)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--u2"); ap.add_argument("--sprav"); ap.add_argument("--dannye", default="data_cache/equities_daily_10y")
    ap.add_argument("--vselennaya", default="U2"); ap.add_argument("--vyvod", required=True)
    ap.add_argument("--bps", default="20,10,30"); ap.add_argument("--chasti", default="A,B")
    a = ap.parse_args()
    cfg = json.loads(Path("configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json").read_text())
    clusters = [{str(x) for x in g} for g in cfg["clusters"]]
    if a.vselennaya == "U2":
        syrye, _ = chasovye(Path(a.dannye)); spy_p = v_dnevnye(syrye)
        U = U2M.zagruzit_u2(Path(a.u2), Path(a.sprav), spy_p)
    else:
        U = U2M.zagruzit_u58(Path(a.dannye), bez_sektorov=False)
    o0, o1 = date.fromisoformat(U2M.OKNO[0]), date.fromisoformat(U2M.OKNO[1])
    okno = [s for s in U.sessii if o0 <= s <= o1]
    out = {"prereg": "PREREG_ALPACA_H3_KESH_I_PONEDELNIK_2026_10_18", "vselennaya": a.vselennaya}
    vyv = Path(a.vyvod)
    sohr = lambda: vyv.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    if "A" in a.chasti:
        out["A"] = {}
        for bp in [float(x) for x in a.bps.split(",")]:
            kl = f"{bp:.0f}bps"; res = {}
            resh = U2M.mesyachnye(U, U2M.raspisanie(U.sessii, okno), clusters)
            z, rows, rot, stop = monthly_kniga(U, okno, resh, bp)
            for rz, imya in (("NONE", "M"), ("G200", "M+SPY_G200"), ("ALL", "M+SPY_ALL"), ("G200_R30", "M+SPY_G200_R30")):
                m, daty, eq = overlay(U, okno, rows, rot, stop, bp, rz)
                m["podperiody"] = podperiody(daty, eq)
                res[imya] = m
            res["M"]["dvizhok_godovyh_pct"] = U2M._godovyh(float(z["return_pct"]), okno[0], okno[-1])
            res["SPY_BH"] = spy_bh(U, okno, bp)
            kriz = {}
            for kn, (k0, k1) in KRIZISY.items():
                ok = [s for s in U.sessii if date.fromisoformat(k0) <= s <= date.fromisoformat(k1)]
                rr = U2M.mesyachnye(U, U2M.raspisanie(U.sessii, ok), clusters)
                _, rw, ro, st = monthly_kniga(U, ok, rr, bp)
                kriz[kn] = {}
                for rz, imya in (("NONE", "M"), ("G200", "M+SPY_G200"), ("ALL", "M+SPY_ALL"), ("G200_R30", "M+SPY_G200_R30")):
                    m, _, eq = overlay(U, ok, rw, ro, st, bp, rz)
                    kriz[kn][imya] = {"dohod_pct": (eq[-1] / 1000 - 1) * 100, "maxDD_pct": m["maxDD_pct"]}
                sb = spy_bh(U, ok, bp); kriz[kn]["SPY_BH"] = {"dohod_pct": (sb["itog"] - 1) * 100, "maxDD_pct": sb["maxDD_pct"]}
            res["krizisy"] = kriz
            out["A"][kl] = res; sohr()
            print(kl, {k: (round(v["cagr_pct"], 2), round(v["maxDD_pct"], 1), round(v["calmar"], 2)) for k, v in res.items() if k != "krizisy"}, flush=True)
    if "B" in a.chasti:
        out["B"] = {}
        rm = U2M.mesyachnye(U, U2M.raspisanie(U.sessii, okno), clusters)
        rw = U2M.mesyachnye(U, nedelnoe(U.sessii, okno), clusters)
        for bp in [float(x) for x in a.bps.split(",")]:
            kl = f"{bp:.0f}bps"; res = {}
            for imya, rr in (("MONTHLY", rm), ("W_ROT", rw)):
                z = dvizhok_x(U.p, okno, rr, initial_capital=1000.0, target_gross_exposure=0.70, cost_bps_per_side=bp,
                              policy=U2M.POL, mest=4)
                eqd = {x["session"]: x["equity"] for x in z["daily_equity"]}
                ds = sorted(eqd); daty = [date.fromisoformat(x) for x in ds]; eq = [eqd[x] for x in ds]
                m = metriki(daty, eq, 1000.0)
                m.update(sdelok=z["realized_trades"], ekspoziciya_pct=z["average_gross_exposure_pct"],
                         podperiody=podperiody(daty, eq))
                res[imya] = m
            out["B"][kl] = res; sohr()
            print("B", kl, {k: (round(v["cagr_pct"], 2), round(v["maxDD_pct"], 1), v["sdelok"]) for k, v in res.items()}, flush=True)
        out["B"]["gorizonty"] = {"mesyachnye_daty": gorizonty(U, rm), "nedelnye_daty": gorizonty(U, rw)}
        sohr(); print("gorizonty", json.dumps(out["B"]["gorizonty"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
