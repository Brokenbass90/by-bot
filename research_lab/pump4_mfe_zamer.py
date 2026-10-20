import json, os, sys, glob, statistics as st
sys.path.insert(0, "."); sys.path.insert(0, "research_lab")
from research_machine import Store, simulate, pervyy_argument
import importlib
o = json.load(open("research_lab/results/pump4_pereschet_20261020.json"))
z = [x for x in o["resheniya"] if x["status"] == "ZAKRYTA"]
syms = sorted({x["sym"] for x in z})
os.environ.update({"PUMP4_SYMBOL_ALLOWLIST": ",".join(syms), "PUMP4_ALLOW_LONGS": "1", "PUMP4_ALLOW_SHORTS": "1"})
K = importlib.import_module("strategies.pump_fade_v4r").PumpFadeV4RStrategy
H = 3600000; rows = []
for sym in syms:
    p = f"research_lab/data/oos_bybit_h1_20261020/{sym}.json"
    if not os.path.exists(p): continue
    b = json.load(open(p)); idx = {r[0]: i for i, r in enumerate(b)}
    need = {x["ts"]: x for x in z if x["sym"] == sym}
    s = K(); st_ = Store(sym); pv = sym if pervyy_argument(K) == "symbol" else st_
    for i in range(200, len(b) - 1):
        st_.rows = b[:i + 1]; r = b[i]
        try: g = s.maybe_signal(pv, *r)
        except Exception: continue
        if g is None or r[0] not in need: continue
        x = need[r[0]]; e = b[i + 1][1]; sl = e + (g.sl - e) * 4.0; risk = abs(sl - e)
        res = simulate(b, i, g.side, g.sl, list(g.tps or []), (g.tp_fracs or [0.55])[0], 4.0, 168)
        n = res["bars"]; sh = g.side == "short"
        seg = b[i + 1:i + 2 + n]; full = b[i + 1:i + 1 + 168]
        mfe = max(((e - q[3]) if sh else (q[2] - e)) for q in seg) / risk
        mfe168 = max(((e - q[3]) if sh else (q[2] - e)) for q in full) / risk
        tp = [abs(t - e) / risk for t in (g.tps or [])]
        rows.append(dict(sym=sym, R=res["R"], R_zapis=x["R"], mfe=mfe, mfe168=mfe168, tp1=tp[0] if tp else None, tp2=tp[1] if len(tp) > 1 else None, bars=n))
print("vosproizvedeno", len(rows), "iz", len(z), "sovpadenie R", sum(abs(r["R"] - r["R_zapis"]) < 1e-3 for r in rows))
q = lambda v, p: sorted(v)[int(p * (len(v) - 1))]
for k in ("R", "mfe", "mfe168", "tp1", "tp2", "bars"):
    v = [r[k] for r in rows if r[k] is not None]; print(k, "med", round(st.median(v), 3), "p25", round(q(v, .25), 3), "p75", round(q(v, .75), 3), "mean", round(st.mean(v), 3))
w = [r for r in rows if r["R"] > 0]
print("plyusovye", len(w), "MFE do vyhoda med", round(st.median(r["mfe"] for r in w), 2), "MFE 168ch med", round(st.median(r["mfe168"] for r in w), 2))
print("dolya s MFE168 >= tp2:", round(sum(r["mfe168"] >= (r["tp2"] or 9e9) for r in rows) / len(rows), 3), " >=2R:", round(sum(r["mfe168"] >= 2 for r in rows)/len(rows),3), " >=3R:", round(sum(r["mfe168"] >= 3 for r in rows)/len(rows),3))
print("ostavleno na stole (MFE168 - R) med", round(st.median(r["mfe168"] - r["R"] for r in rows), 2), "mean", round(st.mean(r["mfe168"] - r["R"] for r in rows), 2))
json.dump(rows, open("research_lab/results/pump4_mfe_20261020.json", "w"), indent=1)
