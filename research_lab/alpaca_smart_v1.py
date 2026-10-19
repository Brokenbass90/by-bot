#!/usr/bin/env python3
"""Прогон PREREG_ALPACA_SMART_SELECTION_V1_2026_10_19 (d1fab6e): H1 RESID_MKT, H2 STAB21.
Замороженный select_v38_successor не меняется: рука = подмена ОДНОЙ функции оценки кандидата на время вызова
(monkeypatch backtest.alpaca_honest_portfolio._v38_candidate), тест тождества — рука без изменений = baseline.
python3 research_lab/alpaca_smart_v1.py --vselennaya U2|U58 [--u2 .. --sprav ..] --vyvod out/smart_U2.json"""
from __future__ import annotations
import argparse, json, math, sys
from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
import backtest.alpaca_honest_portfolio as HP
from research_lab.alpaca_dannye import chasovye, v_dnevnye
from research_lab.alpaca_dvizhok_x_v1 import dvizhok_x
import research_lab.alpaca_u2 as U2M
import research_lab.alpaca_h3 as H3

ORIG_CAND = HP._v38_candidate
ORIG_SEL = HP.select_v38_successor
CTX = {"ruka": "BASE", "spy": None, "stab": None, "zscore": None}
TREQ = 2.24


# ---------------------------------------------------------------- признаки
def beta60(bars, spy):
    sd = {r.session_date: r.close for r in spy}
    pary = []
    for a, b in zip(bars[-61:-1], bars[-60:]):
        if a.session_date in sd and b.session_date in sd and a.close > 0 and sd[a.session_date] > 0:
            pary.append((b.close / a.close - 1, sd[b.session_date] / sd[a.session_date] - 1))
    if len(pary) < 40:
        return 1.0
    x = np.array([p[1] for p in pary]); y = np.array([p[0] for p in pary])
    v = x.var()
    return float(((x - x.mean()) * (y - y.mean())).mean() / v) if v > 0 else 1.0


def spy_mom28(bars, spy):
    sd = {r.session_date: r.close for r in spy}
    d0, d1 = bars[-28].session_date, bars[-1].session_date
    return sd[d1] / sd[d0] - 1 if d0 in sd and d1 in sd else 0.0


def mom28(bars):
    return bars[-1].close / bars[-28].close - 1


def resid28(bars, spy):
    return mom28(bars) - beta60(bars, spy) * spy_mom28(bars, spy)


# ---------------------------------------------------------------- подмена оценки
def cand_patch(symbol, bars):
    c = ORIG_CAND(symbol, bars)
    if c is None or CTX["ruka"] in ("BASE", "ID"):
        return c
    if CTX["ruka"] == "H1":
        m = mom28(bars)
        return replace(c, score=c.score - 1.20 * m + 1.20 * resid28(bars, CTX["spy"]))
    if CTX["ruka"] == "H2":
        return replace(c, score=CTX["zscore"].get(symbol, c.score))
    if CTX["ruka"] == "MOM":
        return replace(c, score=mom28(bars))
    return c


def top18(history):
    h = {s: HP._universe_health(b) for s, b in history.items() if s not in {"SPY", "QQQ"}}
    return {s for s, _ in sorted(((s, v) for s, v in h.items() if math.isfinite(v)), key=lambda x: x[1], reverse=True)[:18]}


def sel_patch(history, **kw):
    CTX["spy"] = history.get("SPY")
    if CTX["ruka"] == "H2":
        el = top18(history)
        kand = {s: ORIG_CAND(s, history[s]) for s in el}
        kand = {s: c for s, c in kand.items() if c is not None}
        z = {}
        if len(kand) >= 3:
            sc = np.array([c.score for c in kand.values()]); st = np.array([CTX["stab"].get(s, 0.0) for s in kand])
            sz = st.std()
            for (s, c), v in zip(kand.items(), st):
                z[s] = c.score + (sc.std() * (v - st.mean()) / sz if sz > 0 else 0.0)
        CTX["zscore"] = z
    return ORIG_SEL(history, **kw)


HP._v38_candidate = cand_patch
U2M.select_v38_successor = sel_patch


# ---------------------------------------------------------------- STAB21
_kesh = {}


def prohod_dnya(U, s):
    if s not in _kesh:
        hist = U.istoriya(s, U.dopustimye(s))
        el = top18(hist)
        _kesh[s] = (el, {x for x in el if ORIG_CAND(x, hist[x]) is not None})
    return _kesh[s]


def stab21(U, sig):
    i = U.sessii.index(sig); cnt = {}
    for s in U.sessii[max(0, i - 20): i + 1]:
        for x in prohod_dnya(U, s)[1]:
            cnt[x] = cnt.get(x, 0) + 1
    return {x: v / 21 for x, v in cnt.items()}


# ---------------------------------------------------------------- IC
def fwd(U, s, vh, h):
    k = U._k(s, vh)
    if not k or U.p[s][k - 1].session_date != vh:
        return None
    o = U.p[s][k - 1].open; j = min(k - 1 + h - 1, len(U.p[s]) - 1)
    return U.p[s][j].close / o - 1 if o > 0 else None


def spearman(a, b):
    ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def nw_t(x, lag):
    x = np.asarray(x, float); n = len(x); e = x - x.mean()
    s = (e @ e) / n
    for L in range(1, lag + 1):
        s += 2 * (1 - L / (lag + 1)) * (e[L:] @ e[:-L]) / n
    return float(x.mean() / math.sqrt(s / n)) if s > 0 else 0.0


def izmereniya(U, rasp, bp):
    rows = {21: [], 42: []}
    for sig, vh in rasp:
        if not H3.spy200_gate([r.close for r in U.p["SPY"][:U._k("SPY", sig)]]):
            continue
        hist = U.istoriya(sig, U.dopustimye(sig)); spy = hist.get("SPY")
        el = sorted(top18(hist)); st = stab21(U, sig)
        f = {s: (mom28(hist[s]), resid28(hist[s], spy), st.get(s, 0.0)) for s in el if len(hist[s]) >= 61}
        for h in (21, 42):
            r = {s: fwd(U, s, vh, h) for s in f}
            ok = [s for s in f if r[s] is not None]
            if len(ok) < 8:
                continue
            y = np.array([r[s] for s in ok]); y = y - y.mean()
            F = np.array([f[s] for s in ok])
            rec = {"sig": sig.isoformat(), "n": len(ok),
                   "ic_raw": spearman(F[:, 0], y), "ic_resid": spearman(F[:, 1], y),
                   "ic_stab": spearman(F[:, 2], y) if F[:, 2].std() > 0 else 0.0}
            for nm, col in (("resid", 1), ("stab", 2), ("raw", 0)):
                o = np.argsort(F[:, col]); t3 = max(1, len(ok) // 3)
                rec[f"spred_{nm}"] = float(y[o[-t3:]].mean() - y[o[:t3]].mean() - 2 * 2 * bp / 1e4)
            rows[h].append(rec)
    out = {}
    for h, rr in rows.items():
        lag = 1 if h == 21 else 2
        d = lambda k: [x[k] for x in rr]
        inc = [a - b for a, b in zip(d("ic_resid"), d("ic_raw"))]
        out[str(h)] = {"dat": len(rr),
                       "H1_prirashchenie_IC": float(np.mean(inc)), "H1_t": nw_t(inc, lag),
                       "IC_raw": float(np.mean(d("ic_raw"))), "IC_raw_t": nw_t(d("ic_raw"), lag),
                       "IC_resid": float(np.mean(d("ic_resid"))), "IC_resid_t": nw_t(d("ic_resid"), lag),
                       "H2_IC_stab": float(np.mean(d("ic_stab"))), "H2_t": nw_t(d("ic_stab"), lag),
                       "sigma_IC_stab": float(np.std(d("ic_stab"))), "sigma_inc": float(np.std(inc)),
                       "spred_resid_pct": float(np.mean(d("spred_resid")) * 100), "spred_stab_pct": float(np.mean(d("spred_stab")) * 100),
                       "spred_raw_pct": float(np.mean(d("spred_raw")) * 100)}
    return out, rows


# ---------------------------------------------------------------- портфель
def portfel(U, okno, resh, bp):
    z = dvizhok_x(U.p, okno, resh, initial_capital=1000.0, target_gross_exposure=0.70, cost_bps_per_side=bp,
                  policy=U2M.POL, mest=4)
    eqd = {x["session"]: x["equity"] for x in z["daily_equity"]}
    ds = sorted(eqd); daty = [date.fromisoformat(x) for x in ds]; eq = [eqd[x] for x in ds]
    m = H3.metriki(daty, eq, 1000.0)
    m.update(net_pnl_usd=eq[-1] - 1000.0, sdelok=z["realized_trades"], ekspoziciya_pct=z["average_gross_exposure_pct"],
             podperiody={k: v["cagr_pct"] for k, v in H3.podperiody(daty, eq).items()})
    return m, [(d.signal_session.isoformat(), tuple(c.symbol for c in d.picks)) for d in resh], eq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--u2"); ap.add_argument("--sprav"); ap.add_argument("--dannye", default="data_cache/equities_daily_10y")
    ap.add_argument("--vselennaya", default="U2"); ap.add_argument("--vyvod", required=True)
    ap.add_argument("--bps", default="20,10,30"); ap.add_argument("--sidy", type=int, default=20)
    a = ap.parse_args()
    cfg = json.loads(Path("configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json").read_text())
    clusters = [{str(x) for x in g} for g in cfg["clusters"]]
    if a.vselennaya == "U2":
        syrye, _ = chasovye(Path(a.dannye)); U = U2M.zagruzit_u2(Path(a.u2), Path(a.sprav), v_dnevnye(syrye))
    else:
        U = U2M.zagruzit_u58(Path(a.dannye), bez_sektorov=False)
    o0, o1 = date.fromisoformat(U2M.OKNO[0]), date.fromisoformat(U2M.OKNO[1])
    okno = [s for s in U.sessii if o0 <= s <= o1]
    rasp = U2M.raspisanie(U.sessii, okno)
    out = {"prereg": "PREREG_ALPACA_SMART_SELECTION_V1_2026_10_19", "commit_prereg": "d1fab6e", "vselennaya": a.vselennaya}
    vyv = Path(a.vyvod); sohr = lambda: vyv.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    # решения рук
    resh = {}
    for ruka in ("BASE", "ID", "H1", "MOM"):
        CTX["ruka"] = ruka; resh[ruka] = U2M.mesyachnye(U, rasp, clusters)
    CTX["ruka"] = "H2"; r2 = []
    for sig, vh in rasp:
        CTX["stab"] = stab21(U, sig); r2 += U2M.mesyachnye(U, [(sig, vh)], clusters)
    resh["H2"] = r2; CTX["ruka"] = "BASE"
    ident = [(d.signal_session, tuple(c.symbol for c in d.picks)) for d in resh["ID"]] == \
            [(d.signal_session, tuple(c.symbol for c in d.picks)) for d in resh["BASE"]]
    out["test_tozhdestva_resheniy"] = ident
    if not ident:
        sohr(); raise SystemExit("FAIL: тест тождества решений")
    out["otlichie_resheniy"] = {r: sum(1 for x, y in zip(resh[r], resh["BASE"]) if {c.symbol for c in x.picks} != {c.symbol for c in y.picks})
                                for r in ("H1", "H2", "MOM")}
    out["resheniy"] = len(resh["BASE"])
    izm, syr = izmereniya(U, rasp, 20.0); out["faktor"] = izm; sohr()
    print("faktor", json.dumps(izm, ensure_ascii=False), flush=True)
    out["portfel"] = {}
    for bp in [float(x) for x in a.bps.split(",")]:
        res = {}
        for r in ("BASE", "ID", "H1", "H2", "MOM"):
            m, picks, eq = portfel(U, okno, resh[r], bp); res[r] = m
            if r == "ID":
                res["ID"]["kapital_sovpadaet"] = abs(m["itog"] - res["BASE"]["itog"]) < 1e-9
        rr = [portfel(U, okno, U2M.sluchaynye(U, resh["BASE"], clusters, sid, True), bp)[0] for sid in range(a.sidy)]
        res["R2_sredniy"] = {"cagr_pct": float(np.mean([x["cagr_pct"] for x in rr])), "maxDD_pct": float(np.mean([x["maxDD_pct"] for x in rr])),
                             "cagr_max_pct": float(np.max([x["cagr_pct"] for x in rr]))}
        res["SPY_BH"] = H3.spy_bh(U, okno, bp)
        out["portfel"][f"{bp:.0f}bps"] = res; sohr()
        print(f"{bp:.0f}bps", {k: (round(v["cagr_pct"], 2), round(v["maxDD_pct"], 2)) for k, v in res.items()}, flush=True)
    out["syrye_ic"] = syr; sohr()


if __name__ == "__main__":
    main()
