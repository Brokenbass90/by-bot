"""PREREG_POLY_FAVORIT_VSE_TEMY_2026_10_26. python3 research_lab/polymarket/poly_favorit_temy.py → results/poly_favorit_temy_20261026.json"""
import collections, json, math, statistics as st
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]; F = HERE / "data/poly_favorit_temy/rynki.jsonl"
RATE = {"politics": 0.04, "geopolitics": 0.0}


def main():
    Z = [json.loads(l) for l in open(F)]; st_ = collections.Counter(); sd = []; kal = collections.defaultdict(list)
    for z in Z:
        it = z.get("itog")
        if not it or len(it) != 2 or max(it) < 0.99: st_["net_itoga"] += 1; continue
        y = 1.0 if it[0] > 0.99 else 0.0; T = z["konec"] - 86400
        do = [p for t, p in z["ryad"] if T - 6 * 3600 < t <= T]; posle = [p for t, p in z["ryad"] if t > T]
        if not do or not posle: st_["net_ceny"] += 1; continue
        p = do[-1]; kal[min(9, int(p * 10))].append(y); fr = RATE.get(z["tema"], 0.05)
        for c in (0.01, 0.02):
            if 0.80 <= p <= 0.95: q, vy, st_n = p + c, y, "fav_yes"
            elif 0.05 <= p <= 0.20: q, vy, st_n = (1 - p) + c, 1 - y, "fav_no"
            else: break
            fee = fr * q * (1 - q); sd.append(dict(c=c, sob=z["sobytie"], tema=z["tema"], konec=z["konec"], tip=st_n, d=(vy - q - fee) / (q + fee)))
    def svod(rows):
        g = collections.defaultdict(list)
        for r in rows: g[r["sob"]].append(r["d"])
        v = [sum(x) / len(x) for x in g.values()]
        if len(v) < 3: return dict(sobytiy=len(v))
        m = sum(v) / len(v); s = st.stdev(v)
        return dict(stavok=len(rows), sobytiy=len(v), sred_pct=round(m * 100, 2), t=round(m / (s / math.sqrt(len(v))), 2) if s else None)
    c1 = [r for r in sd if r["c"] == 0.01]; c2 = [r for r in sd if r["c"] == 0.02]
    med = st.median(r["konec"] for r in c1) if c1 else 0
    out = dict(rynkov=len(Z), otbrosheno=dict(st_), vse=svod(c1), stress_c2=svod(c2), polovina1=svod([r for r in c1 if r["konec"] <= med]),
               polovina2=svod([r for r in c1 if r["konec"] > med]), po_temam={t: svod([r for r in c1 if r["tema"] == t]) for t in sorted({r["tema"] for r in c1})},
               po_tipu={t: svod([r for r in c1 if r["tip"] == t]) for t in ("fav_yes", "fav_no")},
               kalibrovka={f"{k*10}-{k*10+10}c": dict(n=len(v), dolya_yes=round(sum(v) / len(v), 3)) for k, v in sorted(kal.items())})
    v = out["vse"]
    if v.get("sobytiy", 0) >= 100 and v["sred_pct"] > 0 and (v["t"] or 0) >= 2.5 and out["polovina1"].get("sred_pct", -1) > 0 \
            and out["polovina2"].get("sred_pct", -1) > 0 and out["stress_c2"].get("sred_pct", -1) > 0: out["verdikt"] = "POSITIVE_LEAD"
    elif v.get("sred_pct", 0) <= 0: out["verdikt"] = "NEGATIVE"
    else: out["verdikt"] = "INCONCLUSIVE"
    (HERE / "results/poly_favorit_temy_20261026.json").write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
