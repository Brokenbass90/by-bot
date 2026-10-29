#!/usr/bin/env python3
"""flet_setka_2025.py — prereg/PREREG_FLET_SETKA_V2_TREND_2026_10_29.md. Mac (сеть Bybit), ~20–40 мин (кэш data/flet_2025_kesh). Только чтение.
    .venv/bin/python3 research_lab/flet_setka_2025.py > research_lab/data/flet_2025.log 2>&1"""
import collections, hashlib, json, math, random, statistics as st, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import flet_setka as FS, pump4_pereschet as P
SHA = "1ebb19f4ee6c94cd8caafe6571e764c0b8c9f6f1b6fffc275216c67bdc884313"; OT, DO = 1735689600000, 1759276800000; KESH = HERE / "data" / "flet_2025_kesh"; KESH.mkdir(parents=True, exist_ok=True)

def bary(sym):
    f = KESH / f"{sym}.json"
    if f.exists(): return json.loads(f.read_text())
    try: b = P.svechi_okno(sym, OT - 760 * 3600000, DO + 80 * 3600000)
    except Exception: b = []
    f.write_text(json.dumps(b)); return b

def main():
    if hashlib.sha256((HERE / "prereg/PREREG_FLET_SETKA_V2_TREND_2026_10_29.md").read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    syms = json.load(open(HERE / "data" / "pump4_v1_universe_20261020.json"))["symbols"]; rng = random.Random(20261029)
    out = {"V1": [], "V2": []}
    for n, s in enumerate(syms, 1):
        b = bary(s)
        if len(b) < 1000: continue
        ne_flet = [i for i in range(800, len(b) - 80, 6) if b[i][0] >= OT and FS.flet(b, i) is None]
        for var in ("V1", "V2"):
            for side in (1, -1):
                zan = 0
                for i in range(800, len(b) - 80):
                    if i <= zan or not (OT <= b[i][0] < DO): continue
                    if var == "V2" and (b[i][4] / b[i - 720][4] - 1) * side <= 0: continue
                    f = FS.flet(b, i)
                    if not f: continue
                    r, k = FS.setka(b, i, f[0], f[1], side)
                    if r is None: zan = k; continue
                    cs = []
                    for _ in range(5):
                        if not ne_flet: break
                        j = rng.choice(ne_flet); c = b[j][4]; rg = c * (f[1] - f[0]) / ((f[0] + f[1]) / 2)
                        rc, _ = FS.setka(b, j, c - rg / 2, c + rg / 2, side)
                        if rc is not None: cs.append(rc)
                    out[var].append(dict(sym=s, ts=b[i][0], side=side, pct=round(r, 3), ctrl=st.mean(cs) if cs else None)); zan = k
        if n % 20 == 0: print(n, len(syms), {k: len(v) for k, v in out.items()}, flush=True)
    res = {}
    for var, sd in out.items():
        g = [x for x in sd if x["ctrl"] is not None]
        po = collections.defaultdict(list); mes = collections.defaultdict(float)
        for x in g: po[time.strftime("%Y-%m-%d", time.gmtime(x["ts"] / 1000))].append(x["pct"] - x["ctrl"]); mes[time.strftime("%Y-%m", time.gmtime(x["ts"] / 1000))] += x["pct"]
        m = [st.mean(v) for v in po.values()]; t = st.mean(m) / (st.stdev(m) / math.sqrt(len(m))) if len(m) > 2 and st.stdev(m) > 0 else None
        res[var] = dict(n=len(g), sred_pct=round(st.mean(x["pct"] for x in g), 3) if g else None, kontrol=round(st.mean(x["ctrl"] for x in g), 3) if g else None,
                        raznica=round(st.mean(x["pct"] - x["ctrl"] for x in g), 3) if g else None, t_dni=round(t, 2) if t else None,
                        mesyacy_pct_summa={k: round(v, 1) for k, v in sorted(mes.items())}, mesyacev_plus=sum(v > 0 for v in mes.values()),
                        vyigr=round(sum(x["pct"] > 0 for x in g) / len(g), 3) if g else None)
    v = res["V2"]; res["vyvod_V2"] = "PASS_V_TEN" if v["n"] >= 200 and v["sred_pct"] > 0 and v["raznica"] > 0 and (v["t_dni"] or 0) >= 2 and v["mesyacev_plus"] >= 6 else "FAIL"
    print(json.dumps(res, ensure_ascii=False, indent=1))
    (HERE / "results" / time.strftime("flet_setka_2025_%Y%m%dT%H%MZ.json", time.gmtime())).write_text(json.dumps(dict(res, setki=out), ensure_ascii=False))

if __name__ == "__main__":
    main()
