#!/usr/bin/env python3
"""elder_hist_sudya.py — единственный судья PREREG_ELDER_ETS2M_HIST_DEV_2026_10_15.md. Запускается ОДИН раз после полного сбора.
Пишет data/elder_hist_dev/ITOG.json. Пороги — только из prereg, здесь не меняются."""
import json, sys, hashlib, calendar, datetime as dt
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]
D = LAB / "data" / "elder_hist_dev"
def ms(s): return calendar.timegm(dt.datetime.strptime(s, "%Y-%m-%d").timetuple()) * 1000
ERY = {"E1": (ms("2023-01-01"), ms("2024-03-01")), "E2": (ms("2024-03-01"), ms("2025-10-01")), "E3": (ms("2025-10-01"), ms("2026-08-12"))}
SIG_MONETA, SIG_NEDELYA, BOOT, ZERNO = 2.50, 2.00, 4000, 20261015
NEDELYA = 7 * 24 * 3600000


def era(ts):
    for k, (a, b) in ERY.items():
        if a <= ts < b: return k
    return None


def klaster_sigma(v, g, seed):
    v = np.asarray(v, float); g = np.asarray(g); u = np.unique(g)
    idx = {x: np.flatnonzero(g == x) for x in u}; rng = np.random.default_rng(seed); m = []
    for _ in range(BOOT):
        vyb = rng.choice(u, size=len(u), replace=True)
        m.append(np.concatenate([v[idx[x]] for x in vyb]).mean())
    sd = float(np.std(m, ddof=1))
    return float(v.mean() / sd) if sd > 0 else 0.0


def main():
    sdelki = [json.loads(l) for l in open(D / "sdelki.jsonl") if l.strip()]
    vse = len(sdelki); isp = [x for x in sdelki if x.get("ispolnen") and not x.get("nezaversheno")]
    for x in isp: x["era"] = era(x["ts"])
    isp = [x for x in isp if x["era"]]
    sym = np.array([x["sym"] for x in isp]); ned = np.array([x["ts"] // NEDELYA for x in isp]); er = np.array([x["era"] for x in isp])
    R = {k: np.array([x[f"R_{k}"] for x in isp]) for k in ("CONTROL", "24H", "WIDE")}
    itog = {"prereg": "PREREG_ELDER_ETS2M_HIST_DEV_2026_10_15.md", "resheniy": vse, "ispolneno": len(isp),
            "dolya_ispolneniya": round(len(isp) / max(1, sum(1 for x in sdelki if "ispolnen" in x)), 4),
            "sha256_sdelki": hashlib.sha256((D / "sdelki.jsonl").read_bytes()).hexdigest(),
            "po_eram_n": {e: int((er == e).sum()) for e in ERY}, "kandidaty": {}}
    # вторичное: информационный эдж CONTROL против случайного входа того же режима
    c = np.array([x["ctrl"] if x["ctrl"] is not None else np.nan for x in isp]); m = ~np.isnan(c)
    itog["info_edzh_CONTROL"] = {"vse": float((R["CONTROL"][m] - c[m]).mean()),
                                 "sigma_moneta": klaster_sigma(R["CONTROL"][m] - c[m], sym[m], ZERNO),
                                 **{e: float((R["CONTROL"][m & (er == e)] - c[m & (er == e)]).mean()) for e in ERY}}
    def kandidat(imya, v, mean_R):
        z = {"srednee": float(v.mean()), "sigma_moneta": klaster_sigma(v, sym, ZERNO), "sigma_nedelya": klaster_sigma(v, ned, ZERNO + 1),
             "po_eram": {e: float(v[er == e].mean()) for e in ERY}, "srednee_R": float(mean_R.mean()),
             "srednee_R_po_eram": {e: float(mean_R[er == e].mean()) for e in ERY}, "summa_R": float(mean_R.sum())}
        z["uslovia"] = {"1_srednee>0": z["srednee"] > 0, "2_sigma_moneta>2.50": z["sigma_moneta"] > SIG_MONETA,
                        "3_sigma_nedelya>2.00": z["sigma_nedelya"] > SIG_NEDELYA,
                        "4_znak_vo_vseh_erah": all(z["po_eram"][e] > 0 for e in ERY),
                        "5_srednee_R>0_vsego_i_vo_vseh_erah": z["srednee_R"] > 0 and all(z["srednee_R_po_eram"][e] > 0 for e in ERY)}
        z["verdikt"] = "PASS" if all(z["uslovia"].values()) else "FAIL"
        itog["kandidaty"][imya] = z
    kandidat("CONTROL_dengi", R["CONTROL"], R["CONTROL"])
    kandidat("24H_vs_CONTROL", R["24H"] - R["CONTROL"], R["24H"])
    kandidat("WIDE_vs_CONTROL", R["WIDE"] - R["CONTROL"], R["WIDE"])
    proshli = [k for k, z in itog["kandidaty"].items() if z["verdikt"] == "PASS"]
    if proshli:
        glavnyy = max(proshli, key=lambda k: itog["kandidaty"][k]["sigma_moneta"])
        itog["VERDIKT"] = "ELDER_HIST_DEV_PASS"; itog["glavnyy"] = glavnyy; itog["proshli"] = proshli
    else:
        itog["VERDIKT"] = "ELDER_HIST_DEV_KILL"
    (D / "ITOG.json").write_text(json.dumps(itog, ensure_ascii=False, indent=1))
    print(json.dumps(itog, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if (D / "ITOG.json").exists():
        print("ITOG.json уже есть — судья однократный."); sys.exit(2)
    main()
