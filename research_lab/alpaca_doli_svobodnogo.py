#!/usr/bin/env python3
"""PREREG_ALPACA_DOLI_SVOBODNOGO_2026_10_27. Из корня репо:
python3 research_lab/alpaca_doli_svobodnogo.py --dannye runtime/equities_1h_parity_20260914 --fondy research_lab/data/alpaca_bil_sgov_20261019"""
import argparse, hashlib, json, sys, time
from datetime import date
from pathlib import Path
sys.path.insert(0, ".")
import research_lab.alpaca_u2 as U2M
import research_lab.alpaca_h3 as H3
import research_lab.alpaca_h5_bil as H5
SHA = "e29a5ba0860c1eac1eecd19efd84b44e23e7232fca8ce353ce95337c135f60f4"

def smes(S, B, x):
    """синтетический фонд x·SPY + (1−x)·BIL, ребаланс ежедневно (open→close и close→open по долям)"""
    ks = sorted(set(S) & set(B)); out = {}; px = 1.0; prev = None
    for d in ks:
        if prev is not None:
            r_on = x * (S[d].open / S[prev].close - 1) + (1 - x) * (B[d].open / B[prev].close - 1); px *= 1 + r_on
        o = px; r_d = x * (S[d].close / S[d].open - 1) + (1 - x) * (B[d].close / B[d].open - 1); px *= 1 + r_d
        out[d] = H5.Bar(o, px); prev = d
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dannye", required=True); ap.add_argument("--fondy", required=True); a = ap.parse_args()
    if hashlib.sha256(Path("research_lab/prereg/PREREG_ALPACA_DOLI_SVOBODNOGO_2026_10_27.md").read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    cfg = json.loads(Path("configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json").read_text())
    clusters = [{str(x) for x in g} for g in cfg["clusters"]]
    U = U2M.zagruzit_u58(Path(a.dannye), bez_sektorov=False)
    BIL = H5.fond(Path(a.fondy) / "all" / "bars" / "BIL.json"); SPY = {r.session_date: H5.Bar(float(r.open), float(r.close)) for r in U.p["SPY"]}
    o0, o1 = date.fromisoformat(U2M.OKNO[0]), date.fromisoformat(U2M.OKNO[1])
    okno = [s for s in U.sessii if o0 <= s <= o1 and s in BIL and s in SPY]
    resh = U2M.mesyachnye(U, U2M.raspisanie(U.sessii, okno), clusters)
    z, rows, rot, stop = H3.monthly_kniga(U, okno, resh, 20.0)
    m, daty, eq = H3.overlay(U, okno, rows, rot, stop, 20.0, "NONE")
    res = {"M (кэш)": m}
    for nazv, x in (("M+BIL", 0.0), ("M+25/75", 0.25), ("M+50/50", 0.5), ("M+75/25", 0.75), ("M+SPY", 1.0)):
        F = smes(SPY, BIL, x); mm, dd, ee = H5.overlay_fond(rows, rot, stop, F, 3.0, polosa=0.05); res[nazv] = mm
    sc = [SPY[d].close for d in okno]; res["SPY 100 %"] = H3.metriki(okno, [v / sc[0] * 1000 for v in sc], 1000.0)
    out = dict(kogda_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), period=[str(okno[0]), str(okno[-1])], sessiy=len(okno),
               dannye=a.dannye, rezultat=res, prereg_sha256=SHA)
    f = Path("research_lab/results") / time.strftime("alpaca_doli_svobodnogo_%Y%m%dT%H%MZ.json", time.gmtime())
    f.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    for k, v in res.items(): print(f"{k:12s} годовых {v.get('cagr_pct', 0):6.2f} %  просадка {v.get('maxDD_pct', 0):6.2f} %  Calmar {v.get('calmar', 0):.2f}  в фонде {v.get('dolya_v_fonde_srednyaya', '-')}")
    print("период", out["period"], "файл", f)

if __name__ == "__main__": main()
