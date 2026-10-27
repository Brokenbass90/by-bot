#!/usr/bin/env python3
"""ets2_hedzh.py — prereg/PREREG_ETS2_HEDZH_2026_10_27.md (27.10.2026, Claude). Шорт ETS2 (сделки полного повтора) + лонг корзины альт."""
import collections, glob, hashlib, json, math, sys, time
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; H = 3600000
PREREG = HERE / "prereg/PREREG_ETS2_HEDZH_2026_10_27.md"; SHA = "475e7288645aa1ab91b3a2797ae281050dadfbd765a00db0285a9992e608d0a5"
FEE = 5.5

def main():
    if hashlib.sha256(PREREG.read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    sd = json.load(open(HERE / "results/ets2s_polnyy_povtor_20261027T0730Z.json"))["sdelki"]
    C = {}
    for f in glob.glob(str(HERE / "data/oos_bybit_h1_20261020/*.json")):
        b = json.load(open(f)); C[Path(f).stem] = {int(x[0]): (float(x[1]), float(x[4])) for x in b}
    C = {s: d for s, d in C.items() if d}
    gran = max(max(v) for v in C.values())
    def korzina(t0, t1, krome):
        r = []
        for s, d in C.items():
            if s == krome or t0 not in d or t1 not in d: continue
            r.append(d[t1][1] / d[t0][0] - 1)
        return (float(np.mean(r)), len(r)) if r else (None, 0)
    out, isk = [], collections.Counter()
    for x in sd:
        t0 = x["ts"] + H; t1 = x["ts"] + (x["barov"] + 1) * H
        if t1 > gran: isk["posle_konca_dannyh"] += 1; continue
        k, n = korzina(t0, t1, x["sym"])
        if k is None or n < 50: isk["korzina_nepolnaya"] += 1; continue
        b = C.get("BTCUSDT", {}); kb = (b[t1][1] / b[t0][0] - 1) if t0 in b and t1 in b else None
        hc = 2 * FEE / 1e4 * x["plecho"]
        out.append(dict(sym=x["sym"], ts=x["ts"], R=x["R"], korz=k, R_h=x["R"] + k * x["plecho"] - hc,
                        R_btc=(x["R"] + kb * x["plecho"] - hc) if kb is not None else None, barov=x["barov"]))
    def svod(g, kl):
        g = [y for y in g if y.get(kl) is not None]
        if len(g) < 3: return dict(n=len(g))
        R = np.array([y[kl] for y in g]); dni = collections.defaultdict(list)
        for y in g: dni[y["ts"] // 86400000].append(y[kl])
        a = np.array([np.mean(v) for v in dni.values()]); c = np.cumsum(R[np.argsort([y["ts"] for y in g])])
        return dict(n=len(g), sred=round(float(R.mean()), 4), summa=round(float(R.sum()), 1), t_dni=round(float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))), 2),
                    prosadka=round(float((np.maximum.accumulate(np.concatenate([[0], c]))[1:] - c).max()), 1), ubyt=int((R < 0).sum()))
    def sloty(g, k):
        otkr, vz = [], []
        for y in sorted(g, key=lambda y: y["ts"]):
            t0 = y["ts"] + H; otkr = [t for t in otkr if t > t0]
            if len(otkr) >= k: continue
            otkr.append(t0 + (y["barov"] + 1) * H); vz.append(y)
        return svod(vz, "R_h")
    mes = lambda m: [y for y in out if time.strftime("%Y-%m", time.gmtime(y["ts"] / 1000)) == m]
    rez = dict(isklyucheno=dict(isk), golyy=svod(out, "R"), hedzh=svod(out, "R_h"), hedzh_btc=svod(out, "R_btc"),
               sentyabr=dict(golyy=svod(mes("2026-09"), "R"), hedzh=svod(mes("2026-09"), "R_h")),
               oktyabr=dict(golyy=svod(mes("2026-10"), "R"), hedzh=svod(mes("2026-10"), "R_h")),
               sloty={str(k): sloty(out, k) for k in (3, 5, 10)},
               po_nedelyam={time.strftime("%m-%d", time.gmtime(w * 7 * 86400)): round(float(np.mean([y["R_h"] for y in out if y["ts"] // (7 * 86400000) == w])), 4)
                            for w in sorted({y["ts"] // (7 * 86400000) for y in out})})
    h = rez["hedzh"]
    v = dict(sred_gt0=h["sred"] > 0, t_ge2=h["t_dni"] >= 2.0, sent_gt0=rez["sentyabr"]["hedzh"].get("sred", -1) > 0, okt_gt0=rez["oktyabr"]["hedzh"].get("sred", -1) > 0)
    v["itog"] = "PASS" if all(v.values()) else ("FAIL" if h["sred"] <= 0 or (v["sent_gt0"] != v["okt_gt0"]) else "INCONCLUSIVE")
    rez.update(verdikt=v, kogda_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), kod_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), prereg_sha256=SHA)
    f = HERE / "results" / time.strftime("ets2_hedzh_%Y%m%dT%H%MZ.json", time.gmtime())
    f.write_text(json.dumps(dict(svod=rez, sdelki=out), ensure_ascii=False, indent=1)); print(json.dumps(rez, ensure_ascii=False, indent=1)); print("файл:", f)

if __name__ == "__main__": main()
