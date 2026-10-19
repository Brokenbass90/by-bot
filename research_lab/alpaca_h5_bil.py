#!/usr/bin/env python3
"""Прогон PREREG_ALPACA_H5_KESH_V_BIL_2026_10_19 (62cae66): свободный кэш Monthly в BIL / SGOV.
Книга Monthly — alpaca_h3.monthly_kniga без изменений; механика оверлея — как alpaca_h3.overlay (режим ALL),
только инструмент — фонд векселей и свои издержки на сторону.
python3 research_lab/alpaca_h5_bil.py --vselennaya U2|U58 [--u2 .. --sprav ..] --fondy data/bilsgov --vyvod out/h5_U2.json"""
from __future__ import annotations
import argparse, json, sys
from collections import namedtuple
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, ".")
from research_lab.alpaca_dannye import chasovye, v_dnevnye
import research_lab.alpaca_u2 as U2M
import research_lab.alpaca_h3 as H3

NY = ZoneInfo("America/New_York")
Bar = namedtuple("Bar", "open close")
SGOV_START = "2020-06-01"
FOND_BPS = (3.0, 10.0)


def fond(put: Path):
    d = json.loads(put.read_text())
    return {datetime.fromtimestamp(r["t"] / 1000, NY).date(): Bar(float(r["o"]), float(r["c"])) for r in d["records"]}


def overlay_fond(rows, rot, stop, F, bp, vorota=None, polosa=0.0):
    P = 0.0; u = 0.0; eq, daty, v_fonde, oborot, sdelok, potr, prodazh = [], [], [], 0.0, 0, 0.0, 0
    prev = None; po_godam = {}
    for r in rows:
        d = date.fromisoformat(r["session"]); ds = r["session"]
        if d not in F:
            raise SystemExit(f"FAIL_CLOSED: нет бара фонда на {ds}")
        b = F[d]
        if prev is None:
            svob_open = r["cash"] - stop.get(ds, 0.0); posval_open = r["equity"] - r["cash"]
        else:
            svob_open = r["cash"] - stop.get(ds, 0.0)
            posval_open = max(0.0, prev["equity"] - prev["cash"] + (prev["cash"] + rot.get(ds, 0.0) + stop.get(ds, 0.0)
                                                                   - r["cash"]) - rot.get(ds, 0.0))
            dp = u * (b.open - F[date.fromisoformat(prev["session"])].close); P += dp
            po_godam[d.year] = po_godam.get(d.year, 0.0) + dp
        vsego_open = posval_open + svob_open + P
        cel = max(0.0, svob_open + P)
        if vorota is not None and not vorota.get(d, False):
            cel = 0.0
        diff = cel - u * b.open
        if diff > 0 and diff <= polosa * vsego_open:
            diff = 0.0
        if abs(diff) > 1e-9:
            c = abs(diff) * bp / 1e4; P -= c; po_godam[d.year] = po_godam.get(d.year, 0.0) - c
            oborot += abs(diff) / max(vsego_open, 1e-9)
            if abs(diff) > 0.01 * vsego_open:
                sdelok += 1
            if diff < 0:
                potr = max(potr, -diff / max(vsego_open, 1e-9))
                if -diff > 0.001 * vsego_open:
                    prodazh += 1
            u = (u * b.open + diff) / b.open
        dc = u * (b.close - b.open); P += dc; po_godam[d.year] = po_godam.get(d.year, 0.0) + dc
        vsego = r["equity"] + P
        eq.append(vsego); daty.append(d); v_fonde.append(u * b.close / vsego if vsego > 0 else 0.0)
        prev = r
    m = H3.metriki(daty, eq, 1000.0)
    m.update(dolya_v_fonde_srednyaya=float(np.mean(v_fonde)), oborot_dol_kapitala=oborot, sdelok_overleya=sdelok,
             potrebnost_likvidnosti_max=potr, sessiy_prodazha_fonda=prodazh,
             dohod_overleya_po_godam_usd={str(k): round(v, 2) for k, v in sorted(po_godam.items())})
    return m, daty, eq


def vorota_stavki(B, prag=0.01, n=63):
    """H5b: фонд разрешён на t, если доход BIL_all за n сессий по закрытие t−1, ×252/n, ≥ prag."""
    ks = sorted(B); out = {}
    for i, d in enumerate(ks):
        out[d] = i - 1 - n >= 0 and (B[ks[i - 1]].close / B[ks[i - 1 - n]].close - 1) * 252 / n >= prag
    return out


def tr_fonda(F, d0, d1):
    ks = sorted(k for k in F if d0 <= k <= d1)
    return (F[ks[-1]].close / F[ks[0]].open - 1) * 100 if ks else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--u2"); ap.add_argument("--sprav"); ap.add_argument("--dannye", default="data_cache/equities_daily_10y")
    ap.add_argument("--vselennaya", default="U2"); ap.add_argument("--fondy", required=True); ap.add_argument("--vyvod", required=True)
    ap.add_argument("--bps", default="20,10,30"); ap.add_argument("--h5b", action="store_true")
    a = ap.parse_args()
    cfg = json.loads(Path("configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json").read_text())
    clusters = [{str(x) for x in g} for g in cfg["clusters"]]
    if a.vselennaya == "U2":
        syrye, _ = chasovye(Path(a.dannye)); U = U2M.zagruzit_u2(Path(a.u2), Path(a.sprav), v_dnevnye(syrye))
    else:
        U = U2M.zagruzit_u58(Path(a.dannye), bez_sektorov=False)
    fd = Path(a.fondy)
    BIL, SGOV = fond(fd / "all" / "BIL.json"), fond(fd / "all" / "SGOV.json")
    BILs, SGOVs = fond(fd / "split" / "BIL.json"), fond(fd / "split" / "SGOV.json")
    KW = dict(vorota=vorota_stavki(BIL), polosa=0.05) if a.h5b else {}
    if a.h5b:
        _ov = overlay_fond
        globals()["overlay_fond"] = lambda rw, ro, st, F, fb: _ov(rw, ro, st, F, fb, **KW)
    o0, o1 = date.fromisoformat(U2M.OKNO[0]), date.fromisoformat(U2M.OKNO[1])
    okno = [s for s in U.sessii if o0 <= s <= o1]
    oknoS = [s for s in okno if s >= date.fromisoformat(SGOV_START)]
    out = {"prereg": "PREREG_ALPACA_H5B_BIL_VOROTA_STAVKI_2026_10_19" if a.h5b else "PREREG_ALPACA_H5_KESH_V_BIL_2026_10_19", "commit_prereg": "69ff412" if a.h5b else "62cae66", "vselennaya": a.vselennaya,
           "fond_tr_pct": {"BIL_all": tr_fonda(BIL, okno[0], okno[-1]), "BIL_split": tr_fonda(BILs, okno[0], okno[-1]),
                           "SGOV_all": tr_fonda(SGOV, oknoS[0], oknoS[-1]), "SGOV_split": tr_fonda(SGOVs, oknoS[0], oknoS[-1])},
           "A": {}}
    vyv = Path(a.vyvod); sohr = lambda: vyv.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    for bp in [float(x) for x in a.bps.split(",")]:
        res = {}
        resh = U2M.mesyachnye(U, U2M.raspisanie(U.sessii, okno), clusters)
        z, rows, rot, stop = H3.monthly_kniga(U, okno, resh, bp)
        m, daty, eq = H3.overlay(U, okno, rows, rot, stop, bp, "NONE"); m["podperiody"] = H3.podperiody(daty, eq); res["M"] = m
        for fb in FOND_BPS:
            m, daty, eq = overlay_fond(rows, rot, stop, BIL, fb); m["podperiody"] = H3.podperiody(daty, eq)
            res[f"M+BIL_{fb:.0f}"] = m
        # окно SGOV
        reshS = U2M.mesyachnye(U, U2M.raspisanie(U.sessii, oknoS), clusters)
        _, rS, roS, stS = H3.monthly_kniga(U, oknoS, reshS, bp)
        res["S_okno_M"] = H3.overlay(U, oknoS, rS, roS, stS, bp, "NONE")[0]
        for fb in FOND_BPS:
            res[f"S_okno_M+SGOV_{fb:.0f}"] = overlay_fond(rS, roS, stS, SGOV, fb)[0]
            res[f"S_okno_M+BIL_{fb:.0f}"] = overlay_fond(rS, roS, stS, BIL, fb)[0]
        kriz = {}
        for kn, (k0, k1) in H3.KRIZISY.items():
            ok = [s for s in U.sessii if date.fromisoformat(k0) <= s <= date.fromisoformat(k1)]
            rr = U2M.mesyachnye(U, U2M.raspisanie(U.sessii, ok), clusters)
            _, rw, ro, st = H3.monthly_kniga(U, ok, rr, bp)
            m0, _, e0 = H3.overlay(U, ok, rw, ro, st, bp, "NONE")
            kriz[kn] = {"M": {"dohod_pct": (e0[-1] / 1000 - 1) * 100, "maxDD_pct": m0["maxDD_pct"]}}
            for fb in FOND_BPS:
                m1, _, e1 = overlay_fond(rw, ro, st, BIL, fb)
                kriz[kn][f"M+BIL_{fb:.0f}"] = {"dohod_pct": (e1[-1] / 1000 - 1) * 100, "maxDD_pct": m1["maxDD_pct"]}
        res["krizisy"] = kriz
        out["A"][f"{bp:.0f}bps"] = res; sohr()
        print(f"{bp:.0f}bps", {k: (round(v["cagr_pct"], 2), round(v["maxDD_pct"], 2)) for k, v in res.items() if k != "krizisy"}, flush=True)


if __name__ == "__main__":
    main()
