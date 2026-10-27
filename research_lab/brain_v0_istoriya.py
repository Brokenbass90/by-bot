#!/usr/bin/env python3
"""brain_v0_istoriya.py — prereg/PREREG_BRAIN_V0_RISK_ISTORIYA_2026_10_27.md (27.10.2026, Claude)."""
import collections, hashlib, json, math, sys, time, calendar
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; H = 3600000; SHA = "9474ff32a886266fc1e5bb4cba185cd22b0ae368511044f6b2848e1c70552060"
T = lambda s: calendar.timegm(time.strptime(s, "%Y-%m-%d")) * 1000
A0, A1 = T("2024-03-01"), T("2025-10-01")

def main():
    if hashlib.sha256((HERE / "prereg/PREREG_BRAIN_V0_RISK_ISTORIYA_2026_10_27.md").read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    p4 = json.load(open(HERE / "results/pump4_rezhim_e1_20261027T0510Z.json"))["sdelki"]
    sd = [dict(noga="PUMP4", sym=x["sym"], t0=x["ts"] + H, t1=x["ts"] + (x["barov"] + 2) * H, R=x["R"]) for x in p4 if A0 <= x["ts"] < A1]
    sd += [dict(noga="ETS2", sym=x["sym"], t0=x["ts"] + 900000, t1=x["ts"] + 900000 + x["hours"] * H, R=x["R"])
           for x in json.load(open(HERE / "os2/potoki/ETS2.json")) if A0 <= x["ts"] < A1]
    sd.sort(key=lambda x: x["t0"])
    dl = collections.defaultdict(list)
    for e in json.load(open(HERE / "data/delist_forced/sobytiya.json")): dl[e["sym"]].append(e["t_obyavleniya"])
    def portfel(brain):
        otkr, vz, prop = [], [], collections.Counter()
        for x in sd:
            otkr = [o for o in otkr if o["t1"] > x["t0"]]
            if sum(1 for o in otkr if o["noga"] == x["noga"]) >= 5: prop["limit_nogi"] += 1; continue
            if brain:
                if any(o["sym"] == x["sym"] for o in otkr): prop["R1_moneta_zanyata"] += 1; continue
                if len(otkr) >= 8: prop["R2_obshchiy_limit"] += 1; continue
                if any(x["t0"] - 7 * 24 * H <= t <= x["t0"] for t in dl.get(x["sym"], [])): prop["R3_delisting"] += 1; continue
            otkr.append(x); vz.append(x)
        R = np.array([x["R"] for x in vz]); c = np.cumsum(R); dd = float((np.maximum.accumulate(np.concatenate([[0], c]))[1:] - c).max())
        ned = collections.defaultdict(float)
        for x in vz: ned[x["t0"] // (7 * 86400000)] += x["R"]
        return dict(sdelok=len(vz), po_nogam=dict(collections.Counter(x["noga"] for x in vz)), summa_R=round(float(R.sum()), 1), prosadka_R=round(dd, 1),
                    summa_k_prosadke=round(float(R.sum()) / dd, 2) if dd else None, hudshaya_nedelya_R=round(min(ned.values()), 1), propuski=dict(prop)), ned
    a, na = portfel(False); b, nb = portfel(True)
    ks = sorted(set(na) | set(nb)); d = np.array([nb.get(k, 0) - na.get(k, 0) for k in ks]); rng = np.random.default_rng(27)
    bs = np.array([d[rng.integers(0, len(d), len(d))].sum() for _ in range(2000)])
    v = "POLEZEN" if (b["prosadka_R"] <= a["prosadka_R"] and (b["summa_k_prosadke"] or -9) > (a["summa_k_prosadke"] or -9)) else         ("VREDEN" if (b["summa_R"] < a["summa_R"] and b["prosadka_R"] > a["prosadka_R"]) else "NEYTRALEN")
    out = dict(kogda_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), A_bez_brain=a, B_brain_v0=b,
               B_minus_A=dict(summa_R=round(float(d.sum()), 1), dolya_butstrap_le0=round(float((bs <= 0).mean()), 3), nedel=len(ks)), verdikt=v, prereg_sha256=SHA)
    f = HERE / "results" / time.strftime("brain_v0_istoriya_%Y%m%dT%H%MZ.json", time.gmtime()); f.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1))

if __name__ == "__main__": main()
