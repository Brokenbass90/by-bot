#!/usr/bin/env python3
"""Прогон PREREG_ALPACA_H4_ZASHCHITA_2026_10_18 (55a55df): M / M_BEZ_TREYLA / M_BEZ_STOPOV.
python3 research_lab/alpaca_h4.py --vselennaya U2|U58 [--u2 ... --sprav ...] --vyvod out/h4_U2.json"""
from __future__ import annotations

import argparse, json, sys
from dataclasses import replace
from datetime import date
from pathlib import Path

sys.path.insert(0, ".")
from backtest.alpaca_honest_portfolio import Candidate, LiveProtectionDailyProxy, MonthlyDecision
from research_lab.alpaca_dannye import chasovye, v_dnevnye
from research_lab.alpaca_dvizhok_x_v1 import dvizhok_x
import research_lab.alpaca_u2 as U2M
from research_lab.alpaca_h3 import KRIZISY, metriki, podperiody

POL_M = LiveProtectionDailyProxy(initial_stop_anchor="entry_fill")
POL_BEZ_TREYLA = replace(POL_M, activate_gain_pct=1e12)
POL_BEZ_STOPOV = replace(POL_M, activate_gain_pct=1e12, fallback_stop_pct=0.99)


def bez_stopa(resh):
    """Начальный стоп = entry − 2·ATR; ATR = 1e12 → стоп отрицательный → запасной 99 % ниже входа = стопа нет."""
    return [MonthlyDecision(d.signal_session, d.entry_session,
                            tuple(Candidate(c.symbol, c.score, 1e12, c.atr_pct_at_signal, c.signal_close, c.weight)
                                  for c in d.picks), d.reason) for d in resh]


RUKI = {"M": (POL_M, False), "M_BEZ_TREYLA": (POL_BEZ_TREYLA, False), "M_BEZ_STOPOV": (POL_BEZ_STOPOV, True)}


def progon(U, okno, resh, bp, ruka):
    pol, bs = RUKI[ruka]
    z = dvizhok_x(U.p, okno, bez_stopa(resh) if bs else resh, initial_capital=1000.0, target_gross_exposure=0.70,
                  cost_bps_per_side=bp, policy=pol, mest=4)
    eqd = {x["session"]: x["equity"] for x in z["daily_equity"]}
    ds = sorted(eqd); daty = [date.fromisoformat(x) for x in ds]; eq = [eqd[x] for x in ds]
    m = metriki(daty, eq, 1000.0)
    tr = z["trades"]
    m.update(sdelok=len(tr), ekspoziciya_pct=z["average_gross_exposure_pct"], hudshiy_mesyac_pct=z["worst_month_pct"],
             dolya_stopov=sum(t["reason"].startswith(("protective_stop", "entry_gap")) for t in tr) / max(1, len(tr)),
             hudshaya_sdelka_pct=min((t["return_pct"] for t in tr), default=0.0),
             podperiody=podperiody(daty, eq), dvizhok_godovyh_pct=U2M._godovyh(float(z["return_pct"]), okno[0], okno[-1]))
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--u2"); ap.add_argument("--sprav"); ap.add_argument("--dannye", default="data_cache/equities_daily_10y")
    ap.add_argument("--vselennaya", default="U2"); ap.add_argument("--vyvod", required=True); ap.add_argument("--bps", default="20,10,30")
    a = ap.parse_args()
    cfg = json.loads(Path("configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json").read_text())
    clusters = [{str(x) for x in g} for g in cfg["clusters"]]
    if a.vselennaya == "U2":
        syrye, _ = chasovye(Path(a.dannye)); U = U2M.zagruzit_u2(Path(a.u2), Path(a.sprav), v_dnevnye(syrye))
    else:
        U = U2M.zagruzit_u58(Path(a.dannye), bez_sektorov=False)
    o0, o1 = date.fromisoformat(U2M.OKNO[0]), date.fromisoformat(U2M.OKNO[1])
    okno = [s for s in U.sessii if o0 <= s <= o1]
    resh = U2M.mesyachnye(U, U2M.raspisanie(U.sessii, okno), clusters)
    out = {"prereg": "PREREG_ALPACA_H4_ZASHCHITA_2026_10_18", "vselennaya": a.vselennaya, "polnoe": {}, "krizisy": {}}
    vyv = Path(a.vyvod); sohr = lambda: vyv.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    for bp in [float(x) for x in a.bps.split(",")]:
        kl = f"{bp:.0f}bps"
        out["polnoe"][kl] = {r: progon(U, okno, resh, bp, r) for r in RUKI}; sohr()
        print(kl, {r: (round(v["cagr_pct"], 2), round(v["maxDD_pct"], 1), round(v["calmar"], 2), round(v["ekspoziciya_pct"]))
                   for r, v in out["polnoe"][kl].items()}, flush=True)
    for kn, (k0, k1) in KRIZISY.items():
        ok = [s for s in U.sessii if date.fromisoformat(k0) <= s <= date.fromisoformat(k1)]
        rr = U2M.mesyachnye(U, U2M.raspisanie(U.sessii, ok), clusters)
        out["krizisy"][kn] = {}
        for r in RUKI:
            m = progon(U, ok, rr, 20.0, r)
            out["krizisy"][kn][r] = {"dohod_pct": (m["itog"] - 1) * 100, "maxDD_pct": m["maxDD_pct"]}
        sohr()
    print("krizisy", json.dumps(out["krizisy"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
