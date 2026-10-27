#!/usr/bin/env python3
"""delist_forced_short.py — prereg/PREREG_DELIST_FORCED_SHORT_2026_10_27.md (+A1). Один денежный тест. 27.10.2026, Claude."""
import collections, hashlib, json, math, os, statistics as st, sys, time
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; D = HERE / "data" / "delist_forced"; H = 3600000
PREREG = HERE / "prereg/PREREG_DELIST_FORCED_STOP_2026_10_27.md"; SHA = "ebe4ea204828ed0f3a35a937710765793932f53d7b01c73d5514be9c030d7728"
COST = 42.0
STOP, SLIP = 1.30, 1.05
def shorte(b, i, j):
    e = b[i][1]
    for k in range(i, j + 1):
        if b[k][2] >= e * STOP: return (1 - STOP * SLIP) * 1e4 - COST, True
    return (1 - b[j][4] / e) * 1e4 - COST, False

def main():
    if hashlib.sha256(PREREG.read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    rng = np.random.default_rng(20261027); rows = []; propusk = collections.Counter()
    for x in json.load(open(D / "sobytiya.json")):
        f = D / f"{x['sym']}_{x['t_obyavleniya']}.json"
        if not f.exists(): propusk["net_cen"] += 1; continue
        b = json.load(open(f)); ts = [r[0] for r in b]; idx = {t: i for i, t in enumerate(ts)}
        t0 = x["t_obyavleniya"]; te = (t0 // H + 2) * H
        if te not in idx: propusk["net_bara_vhoda"] += 1; continue
        tx = min(te + 72 * H, ts[-1] - 2 * H)
        if tx - te < 6 * H or tx not in idx: propusk["korotko"] += 1; continue
        hold = tx - te; i, j = idx[te], idx[tx]
        net, stop = shorte(b, i, j)
        ok = [t for t in ts if t0 - 7 * 24 * H <= t <= t0 - hold - H and (t + hold) in idx]
        ctrl = None
        if ok:
            c = [shorte(b, idx[t], idx[t + hold])[0] for t in rng.choice(ok, size=min(20, len(ok)), replace=False)]
            ctrl = float(np.mean(c))
        rows.append(dict(sym=x["sym"], t0=t0, den=t0 // 86400000, god=time.gmtime(t0 / 1000).tm_year, hold_ch=hold // H, net=round(net, 1), stop=stop,
                         ctrl=None if ctrl is None else round(ctrl, 1)))
    def svod(g):
        if len(g) < 3: return dict(n=len(g))
        v = np.array([r["net"] for r in g]); dni = collections.defaultdict(list)
        for r in g: dni[r["den"]].append(r["net"])
        a = np.array([np.mean(z) for z in dni.values()]); t = float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a))))
        c = [r["net"] - r["ctrl"] for r in g if r["ctrl"] is not None]
        return dict(n=len(g), dney=len(a), sred=round(float(v.mean()), 1), med=round(float(np.median(v)), 1), t_dni=round(t, 2),
                    v_plyuse=int((v > 0).sum()), hudshaya=round(float(v.min()), 1), luchshaya=round(float(v.max()), 1),
                    bez_5_luchshih=round(float(np.sort(v)[:-5].mean()), 1), prevyshenie=round(float(np.mean(c)), 1) if c else None, n_ctrl=len(c))
    vse = svod(rows); ran = svod([r for r in rows if r["god"] <= 2025]); poz = svod([r for r in rows if r["god"] == 2026])
    po_g = {g: svod([r for r in rows if r["god"] == g]) for g in sorted({r["god"] for r in rows})}
    v = dict(n_ge100=vse["n"] >= 100, sred_gt0=vse["sred"] > 0, med_gt0=vse["med"] > 0, t_ge2=vse["t_dni"] >= 2.0,
             prev_gt0=(vse["prevyshenie"] or -1) > 0, znak_ran_poz=(ran.get("sred", 0) > 0) == (poz.get("sred", 0) > 0) == True)
    v = {k: bool(z) for k, z in v.items()}
    v["itog"] = "PASS" if all(v.values()) else ("FAIL" if vse["sred"] <= 0 else "INCONCLUSIVE")
    out = dict(kogda_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), propuski=dict(propusk), vse=vse, do_2025=ran, god_2026=poz, po_godam=po_g,
               dolya_stopa=round(sum(r["stop"] for r in rows) / len(rows), 3), verdikt=v, prereg_sha256=SHA, kod_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), primechanie="фандинг не учтён (не скачан)")
    f = HERE / "results" / time.strftime("delist_forced_stop_%Y%m%dT%H%MZ.json", time.gmtime())
    f.write_text(json.dumps(dict(svod=out, sdelki=rows), ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False, indent=1)); print("файл:", f)

if __name__ == "__main__": main()
