#!/usr/bin/env python3
"""Расчёт PREREG_ATT1_ODNOVREMENNYY_KONTROL_2026_10_18 (5e157ed). Требует полного снимка data/h1_kesh_att1/GOTOVO.json."""
import bisect, collections, json, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parent; sys.path.insert(0, str(LAB))
from random_control import sim_geo
K = LAB / "data/h1_kesh_att1"; HOLD = 336; N_KONTR = 20


def main():
    if not (K / "GOTOVO.json").exists(): sys.exit("снимок свечей не готов (хук kesh_att1)")
    bars = {p.stem: json.loads(p.read_text()) for p in K.glob("*.json") if p.stem != "GOTOVO"}
    idx = {s: {int(b[0]): i for i, b in enumerate(v)} for s, v in bars.items()}
    rng = np.random.default_rng(20261018)
    resh = [x for x in map(json.loads, (LAB / "data/ten_ATT1.jsonl").read_text().splitlines()) if "R" in x]
    rows = []
    for r in resh:
        s, ts = r["sym"], int(r["ts"]); short = r["side"] == "short"
        if s not in idx or ts not in idx[s]: continue
        args = (short, r["stop_dolya"], r["rr1"], r["rr2"], r.get("f1", 0.55), HOLD)
        svoy = sim_geo(bars[s], idx[s][ts], *args)
        if svoy is None: continue
        kand = [m for m in idx if m != s and ts in idx[m] and idx[m][ts] + HOLD < len(bars[m])]
        if len(kand) < N_KONTR: continue
        vyb = rng.choice(kand, N_KONTR, replace=False)
        c = [sim_geo(bars[m], idx[m][ts], *args) for m in vyb]; c = [x for x in c if x is not None]
        if not c: continue
        rows.append((ts, svoy, float(np.mean(c))))
    rows.sort(); d = np.array([a - b for _, a, b in rows])
    po_dnyam = collections.defaultdict(list); po_ned = collections.defaultdict(list)
    for (ts, a, b), x in zip(rows, d): po_dnyam[ts // 86400000].append(x); po_ned[ts // (7 * 86400000)].append(x)
    m = np.array([np.mean(v) for v in po_dnyam.values()]); t = float(m.mean() / (m.std(ddof=1) / np.sqrt(len(m))))
    pol = len(d) // 2; ned = [float(np.mean(po_ned[k])) for k in sorted(po_ned)]
    rez = dict(n=len(d), svoy_sredn=round(float(np.mean([a for _, a, _ in rows])), 4), kontrol_sredn=round(float(np.mean([b for _, _, b in rows])), 4),
               d_sredn=round(float(d.mean()), 4), t_po_dnyam=round(t, 2), dney=len(m), polovinki=[round(float(d[:pol].mean()), 4), round(float(d[pol:].mean()), 4)],
               nedeli=[round(x, 4) for x in ned])
    rez["verdikt"] = "PASS" if d.mean() > 0 and t >= 2.5 and min(rez["polovinki"]) > 0 and sum(x > 0 for x in ned) >= min(5, len(ned)) else "FAIL"
    (LAB / "data/ATT1_ODNOVREMENNYY_KONTROL.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1))
    print(json.dumps(rez, ensure_ascii=False))


if __name__ == "__main__":
    main()
