#!/usr/bin/env python3
"""Диагностика расхождения U2/U58 для H2 (PM 19.10 VALIDATION CORRECTION, P1). Без новых рук и порогов:
те же замороженные BASE и H2 из alpaca_smart_v1 (d1fab6e), 20 bps; считаются только описательные величины."""
from __future__ import annotations
import argparse, json, sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
import numpy as np
sys.path.insert(0, ".")
import research_lab.alpaca_smart_v1 as S
from research_lab.alpaca_dannye import chasovye, v_dnevnye
from research_lab.alpaca_dvizhok_x_v1 import dvizhok_x
import research_lab.alpaca_u2 as U2M


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--u2"); ap.add_argument("--sprav"); ap.add_argument("--dannye", default="data_cache/equities_daily_10y")
    ap.add_argument("--vselennaya", default="U2"); ap.add_argument("--vyvod", required=True)
    a = ap.parse_args()
    cfg = json.loads(Path("configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json").read_text())
    clusters = [{str(x) for x in g} for g in cfg["clusters"]]
    if a.vselennaya == "U2":
        syrye, _ = chasovye(Path(a.dannye)); U = U2M.zagruzit_u2(Path(a.u2), Path(a.sprav), v_dnevnye(syrye))
    else:
        U = U2M.zagruzit_u58(Path(a.dannye), bez_sektorov=False)
    o0, o1 = date.fromisoformat(U2M.OKNO[0]), date.fromisoformat(U2M.OKNO[1])
    okno = [s for s in U.sessii if o0 <= s <= o1]; rasp = U2M.raspisanie(U.sessii, okno)
    S.CTX["ruka"] = "BASE"; base = U2M.mesyachnye(U, rasp, clusters)
    S.CTX["ruka"] = "H2"; h2 = []
    kand_n, stab_ok = [], []
    for sig, vh in rasp:
        S.CTX["stab"] = S.stab21(U, sig); h2 += U2M.mesyachnye(U, [(sig, vh)], clusters)
        el, prosh = S.prohod_dnya(U, sig); kand_n.append(len(prosh))
    S.CTX["ruka"] = "BASE"
    out = {"vselennaya": a.vselennaya, "kandidatov_setapa_na_datu": {
        "median": float(np.median(kand_n)), "p25": float(np.percentile(kand_n, 25)), "p75": float(np.percentile(kand_n, 75)),
        "dolya_dat_lt4": float(np.mean([k < 4 for k in kand_n])), "dolya_dat_0": float(np.mean([k == 0 for k in kand_n]))}}
    for nm, rr in (("BASE", base), ("H2", h2)):
        z = dvizhok_x(U.p, okno, rr, initial_capital=1000.0, target_gross_exposure=0.70, cost_bps_per_side=20.0,
                      policy=U2M.POL, mest=4)
        tr = z["trades"]; po_g = defaultdict(float); po_s = defaultdict(float)
        for t in tr:
            po_g[t["exit_session"][:4]] += t["pnl"]; po_s[t["symbol"]] += t["pnl"]
        pnl = sorted((t["pnl"] for t in tr), reverse=True)
        picks = [tuple(sorted(c.symbol for c in d.picks)) for d in rr]
        smena = np.mean([len(set(x) ^ set(y)) / max(1, len(set(x) | set(y))) for x, y in zip(picks[1:], picks[:-1])])
        sym_cnt = Counter(s for p in picks for s in p)
        out[nm] = {"sdelok": len(tr), "pnl_vsego": float(sum(pnl)), "pnl_top5_sdelok": float(sum(pnl[:5])),
                   "pnl_bez_top5": float(sum(pnl[5:])), "hudshie5": [round(x, 1) for x in pnl[-5:]],
                   "po_godam": {k: round(v, 1) for k, v in sorted(po_g.items())},
                   "top_bumagi_pnl": sorted(((k, round(v, 1)) for k, v in po_s.items()), key=lambda x: -abs(x[1]))[:8],
                   "smena_nabora_srednyaya": float(smena), "unikalnyh_bumag": len(sym_cnt),
                   "dolya_top3_bumag_v_vyborah": float(sum(c for _, c in sym_cnt.most_common(3)) / max(1, sum(sym_cnt.values()))),
                   "pustyh_resheniy": sum(1 for p in picks if not p), "srednee_mest": float(np.mean([len(p) for p in picks]))}
    Path(a.vyvod).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
