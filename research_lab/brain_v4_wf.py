#!/usr/bin/env python3
"""brain_v4_wf.py — prereg/PREREG_BRAIN_V4_WF_2026_10_27.md (27.10.2026, Claude). Только чтение."""
import collections, hashlib, json, sys, time
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; H = 3600000; SHA = "152f2f805d24a2d230716fb8a87edf47cef1cf251d97474c424cad6f7f6884be"
def mes(t): g = time.gmtime(t / 1000); return g.tm_year * 12 + g.tm_mon - 1
def main():
    if hashlib.sha256((HERE / "prereg/PREREG_BRAIN_V4_WF_2026_10_27.md").read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    s = [dict(ts=x["ts"], R=x["R"], rez=x["rezhim"], shir=x["shirina"], t1=x["ts"] + (x["barov"] + 2) * H)
         for x in json.load(open(HERE / "results/pump4_shirina_e1_20261027T0513Z.json"))["sdelki"]]
    for l in open(HERE / "data/brain_shadow_v1/zhurnal_nog.jsonl"):
        z = json.loads(l)
        if z["noga"] == "PUMP4" and z["ishod"] is not None:
            s.append(dict(ts=z["t_signala"], R=z["ishod"], rez=z["rezhim_btc"], shir=z["shirina_24ch"], t1=z["t_signala"] + 170 * H))
    s.sort(key=lambda x: x["ts"]); pravila = {"P1_volna_v_bull": lambda x: x["rez"] == "BULL_TREND" and x["shir"] >= 3,
                                              "P2_bull": lambda x: x["rez"] == "BULL_TREND"}
    out = {}; rng = np.random.default_rng(27); m0 = mes(s[0]["ts"])
    for imya, f in pravila.items():
        vkl, eff, zhurnal = {}, collections.defaultdict(float), []
        for M in sorted({mes(x["ts"]) for x in s}):
            if M < m0 + 6: vkl[M] = "NAKOPLENIE"; continue
            gran = (M // 12 - 1970) * 0  # не используется
            ist = [x for x in s if f(x) and x["t1"] < time.mktime((M // 12, M % 12 + 1, 1, 0, 0, 0, 0, 0, 0)) * 1000]
            dni = collections.defaultdict(list)
            for x in ist: dni[x["ts"] // 86400000].append(x["R"])
            if len(dni) < 15: vkl[M] = "INCONCLUSIVE"; continue
            a = np.array([np.mean(v) for v in dni.values()]); bs = np.array([a[rng.integers(0, len(a), len(a))].mean() for _ in range(2000)])
            hi = float(np.quantile(bs, 0.95)); vkl[M] = "VKL" if hi < 0 else "INCONCLUSIVE"
            zhurnal.append(dict(mesyac=f"{M // 12}-{M % 12 + 1:02d}", dney=len(a), sred=round(float(a.mean()), 3), verh90=round(hi, 3), reshenie=vkl[M]))
        bez, s_b, ned_a, ned_b, prop = [], [], collections.defaultdict(float), collections.defaultdict(float), 0
        for x in s:
            w = x["ts"] // (7 * 86400000); bez.append(x["R"]); ned_a[w] += x["R"]
            if vkl.get(mes(x["ts"])) == "VKL" and f(x): prop += 1; continue
            s_b.append(x["R"]); ned_b[w] += x["R"]
        def dd(r): c = np.cumsum(r); return float((np.maximum.accumulate(np.concatenate([[0], c]))[1:] - c).max())
        ks = sorted(ned_a); d = np.array([ned_b.get(k, 0) - ned_a[k] for k in ks])
        bsd = np.array([d[rng.integers(0, len(d), len(d))].sum() for _ in range(2000)])
        A, B = float(sum(bez)), float(sum(s_b)); ver = "POLEZNO" if (B >= A and dd(s_b) <= dd(bez)) else ("VREDNO" if B < A else "NEYTRALNO")
        out[imya] = dict(sdelok=len(s), propushcheno=prop, mesyacev_vkl=sum(1 for v in vkl.values() if v == "VKL"),
                         bez_brain=dict(summa_R=round(A, 1), prosadka_R=round(dd(bez), 1)), s_brain=dict(summa_R=round(B, 1), prosadka_R=round(dd(s_b), 1)),
                         effekt_R=round(B - A, 1), dolya_butstrap_le0=round(float((bsd <= 0).mean()), 3), verdikt=ver, reshenia=zhurnal)
    res = dict(kogda_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), pravila=out, prereg_sha256=SHA)
    (HERE / "results" / time.strftime("brain_v4_wf_%Y%m%dT%H%MZ.json", time.gmtime())).write_text(json.dumps(res, ensure_ascii=False, indent=1))
    for k, v in out.items(): print(k, {a: v[a] for a in v if a != "reshenia"}); print("  включено:", [r["mesyac"] for r in v["reshenia"] if r["reshenie"] == "VKL"])
if __name__ == "__main__": main()
