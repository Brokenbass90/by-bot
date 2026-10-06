#!/usr/bin/env python3
"""rebalancing_pressure.py — судья PREREG_REBALANCING_PRESSURE_2026_10_06.md. Один прогон, повтор запрещён."""
import collections, datetime as dt, hashlib, json, math, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parent; D = LAB / "data"
REZ = D / "rebalancing_pressure_rezultat.json"; KOM = 0.0002
OKNA = {"PRIMARY": ("2016-02", "2023-12"), "HOLDOUT": ("2024-01", "2026-09")}


def main():
    if REZ.exists():
        sys.exit("результат уже есть — прогон один")
    us = {b[0]: b[4] for b in json.loads((D / "mt5_d1/US30.json").read_text())["bary"]}
    tl = {t: c for t, c in json.loads((D / "etf_d1/TLT.json").read_text())["bary"]}
    po = collections.defaultdict(list)
    for d in sorted(us):
        if d >= "2015-12-01":
            po[d[:7]].append(d)
    mes = sorted(po); sob = []
    for a, b in zip(mes, mes[1:]):
        dn = po[b]
        if len(dn) < 10:
            continue
        d0, d5, dk = po[a][-1], dn[-5], dn[-1]
        if not all(x in tl for x in (d0, d5)):
            continue
        S = (us[d5] / us[d0] - 1) - (tl[d5] / tl[d0] - 1)
        r4 = us[dk] / us[d5] - 1
        sob.append(dict(m=b, S=S, poz=-int(np.sign(S)), r=-np.sign(S) * r4 - KOM, vsegda_long=r4))
    rez = dict(prereg="PREREG_REBALANCING_PRESSURE_2026_10_06.md", kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    for imya, (a, b) in OKNA.items():
        w = [x for x in sob if a <= x["m"] <= b]; v = np.array([x["r"] for x in w])
        if len(v) < 3:
            rez[imya] = dict(n=len(v)); continue
        t = v.mean() / (v.std(ddof=1) / math.sqrt(len(v))); h = len(v) // 2
        rez[imya] = dict(mesyacev=len(v), srednee_bps=round(v.mean() * 1e4, 1), t=round(float(t), 2),
                         polovinki_bps=(round(v[:h].mean() * 1e4, 1), round(v[h:].mean() * 1e4, 1)),
                         dolya_plyus=round(float((v > 0).mean()), 2),
                         korr_s_vsegda_long=round(float(np.corrcoef(v, [x["vsegda_long"] for x in w])[0, 1]), 2),
                         vsegda_long_srednee_bps=round(float(np.mean([x["vsegda_long"] for x in w])) * 1e4, 1))
    p, h = rez["PRIMARY"], rez["HOLDOUT"]
    pp = p.get("mesyacev", 0) >= 60 and p["srednee_bps"] > 0 and min(p["polovinki_bps"]) > 0 and p["t"] >= 2.0
    h["status"] = "SAME_SIGN" if h.get("srednee_bps", 0) > 0 else "OPPOSITE"
    rez["status"] = "READY_FOR_BUILD" if pp and h["status"] == "SAME_SIGN" else ("PRIMARY_PASS_HOLDOUT_OPPOSITE" if pp else "KILL")
    REZ.write_text(json.dumps(dict(rez, sobytiya=sob), ensure_ascii=False, indent=1, default=float))
    h_d = hashlib.sha256((D / "mt5_d1/US30.json").read_bytes() + (D / "etf_d1/TLT.json").read_bytes()).hexdigest()
    (D / "REBALANCING_KVITANCIYA.json").write_text(json.dumps(dict(dannye_sha256=h_d, rezultat_sha256=hashlib.sha256(REZ.read_bytes()).hexdigest(),
                                                                   rezultat=rez), ensure_ascii=False, indent=1, default=float))
    print(json.dumps(rez, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
