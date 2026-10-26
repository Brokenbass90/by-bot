#!/usr/bin/env python3
"""PREREG_ALPACA_FREE_CAPITAL_INDEX_2026_10_26 (98a6585). Из корня репо:
python3 research_lab/alpaca_free_capital_index.py --dannye <alpaca-wt>/data_cache/equities_daily_10y --fondy research_lab/data/alpaca_bil_sgov_20261019 --vyvod out.json"""
import argparse, json, sys
from datetime import date
from pathlib import Path
sys.path.insert(0, ".")
import research_lab.alpaca_u2 as U2M
import research_lab.alpaca_h3 as H3
import research_lab.alpaca_h5_bil as H5

FB = (3.0, 10.0)


def spy_bars(U):
    return {r.session_date: H5.Bar(float(r.open), float(r.close)) for r in U.p["SPY"]}


def sostavnoy(S, B, vor, fb):
    """Синтетический фонд: SPY если SPY>SMA200 на t−1, иначе BIL при воротах ставки, иначе кэш."""
    ks = sorted(set(S) & set(B)); closes = []; out = {}; px = 1.0; prev_mode = None; rezh = {}
    sp = sorted(S); spc = [S[d].close for d in sp]; pos = {d: i for i, d in enumerate(sp)}
    for n, d in enumerate(ks):
        i = pos[d]
        if i >= 201:
            sma = sum(spc[i - 200:i]) / 200; mode = "SPY" if spc[i - 1] > sma else ("BIL" if vor.get(d, False) else "CASH")
        else:
            mode = "BIL" if vor.get(d, False) else "CASH"
        rezh[d] = mode
        if n == 0:
            o = px
        else:
            pd_ = ks[n - 1]; pm = prev_mode
            inst = S if pm == "SPY" else B
            o = px * (inst[d].open / inst[pd_].close if pm != "CASH" else 1.0)
            if mode != pm:
                o *= (1 - (fb / 1e4 if pm != "CASH" else 0)) * (1 - (fb / 1e4 if mode != "CASH" else 0))
        inst = S if mode == "SPY" else B
        c = o * (inst[d].close / inst[d].open if mode != "CASH" else 1.0)
        out[d] = H5.Bar(o, c); px = c; prev_mode = mode
    return out, rezh


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dannye", required=True); ap.add_argument("--fondy", required=True)
    ap.add_argument("--vyvod", required=True); ap.add_argument("--bps", default="20,10,30")
    a = ap.parse_args()
    cfg = json.loads(Path("configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json").read_text())
    clusters = [{str(x) for x in g} for g in cfg["clusters"]]
    U = U2M.zagruzit_u58(Path(a.dannye), bez_sektorov=False)
    BIL = H5.fond(Path(a.fondy) / "all" / "BIL.json"); vor = H5.vorota_stavki(BIL); SPY = spy_bars(U)
    o0, o1 = date.fromisoformat(U2M.OKNO[0]), date.fromisoformat(U2M.OKNO[1])
    okno = [s for s in U.sessii if o0 <= s <= o1]
    out = {"prereg": "PREREG_ALPACA_FREE_CAPITAL_INDEX_2026_10_26", "commit_prereg": "98a6585", "vselennaya": "U58", "A": {}}
    sc = [SPY[d].close for d in okno]; out["SPY_100"] = H3.metriki(okno, [x / sc[0] * 1000 for x in sc], 1000.0)
    out["SPY_100"]["podperiody"] = H3.podperiody(okno, [x / sc[0] * 1000 for x in sc])
    def varianty(rows, rot, stop, fb):
        C, rezh = sostavnoy(SPY, BIL, vor, fb)
        return {"M+BIL": H5.overlay_fond(rows, rot, stop, BIL, fb, vorota=vor, polosa=0.05),
                "M+SPY": H5.overlay_fond(rows, rot, stop, SPY, fb, polosa=0.05),
                "M+SPY/BIL": H5.overlay_fond(rows, rot, stop, C, fb, polosa=0.05)}, rezh
    for bp in [float(x) for x in a.bps.split(",")]:
        res = {}
        resh = U2M.mesyachnye(U, U2M.raspisanie(U.sessii, okno), clusters)
        z, rows, rot, stop = H3.monthly_kniga(U, okno, resh, bp)
        m, daty, eq = H3.overlay(U, okno, rows, rot, stop, bp, "NONE"); m["podperiody"] = H3.podperiody(daty, eq); res["M"] = m
        for fb in FB:
            v, rezh = varianty(rows, rot, stop, fb)
            for k, (mm, dd, ee) in v.items():
                mm["podperiody"] = H3.podperiody(dd, ee); res[f"{k}_{fb:.0f}"] = mm
            if bp == 20 and fb == 3:
                res["dolya_dney_rezhima"] = {k: round(sum(1 for d in okno if rezh.get(d) == k) / len(okno), 3) for k in ("SPY", "BIL", "CASH")}
        if bp == 20:
            kriz = {}
            for kn, (k0, k1) in H3.KRIZISY.items():
                ok = [s for s in U.sessii if date.fromisoformat(k0) <= s <= date.fromisoformat(k1)]
                rr = U2M.mesyachnye(U, U2M.raspisanie(U.sessii, ok), clusters)
                _, rw, ro, st = H3.monthly_kniga(U, ok, rr, bp)
                m0, _, e0 = H3.overlay(U, ok, rw, ro, st, bp, "NONE")
                kriz[kn] = {"M": round((e0[-1] / 1000 - 1) * 100, 2)}
                v, _ = varianty(rw, ro, st, 3.0)
                for k, (mm, dd, ee) in v.items():
                    kriz[kn][k] = round((ee[-1] / 1000 - 1) * 100, 2)
                kriz[kn]["SPY_100"] = round((SPY[ok[-1]].close / SPY[ok[0]].open - 1) * 100, 2)
            res["krizisy"] = kriz
        out["A"][f"{bp:.0f}bps"] = res
        Path(a.vyvod).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
        print(f"{bp:.0f}bps", {k: (round(v["cagr_pct"], 2), round(v["maxDD_pct"], 2), round(v["calmar"], 2)) for k, v in res.items() if isinstance(v, dict) and "cagr_pct" in v}, flush=True)


if __name__ == "__main__":
    main()
