"""PREREG_FANDING_POSLE_VYPLATY_EKSTREM_2026_10_26. python3 research_lab/fanding_posle_vyplaty.py → results/fanding_posle_20261026.json"""
import collections, datetime as dt, json, math
from pathlib import Path
HERE = Path(__file__).resolve().parent; D = HERE / "data" / "bybit_fanding_h1_2025_2026"; H = 3600_000; COST = 16.0
# вселенная prereg: те же 99 монет, у которых были записи в FANDING_DOZA (загрузчик взял все 137 служебных — 38 лишних отбрасываются)
MON = {r[0] for r in json.load(open(HERE / "results/fanding_doza_20261026/zapisi.json"))["zapisi"] if r[1] is not None}
sd, ctrl = [], collections.defaultdict(list)
for f in sorted(D.glob("*.json")):
    if f.stem not in MON: continue
    z = json.loads(f.read_text()); h = {r[0]: r for r in z["h1"]}; fu = z["funding"]
    ext_chasy = set()
    for k in range(1, len(fu)):
        T, r = fu[k][0], fu[k - 1][1]
        if abs(r) < 1e-3 or fu[k][0] - fu[k - 1][0] > 9 * H: continue
        b = h.get(T // H * H)
        if b is None: continue
        sg = 1 if r > 0 else -1; x = sg * (b[4] / b[1] - 1) * 1e4
        sd.append((dt.datetime.utcfromtimestamp(T / 1000).date(), x - COST, x, f.stem)); ext_chasy.add(T // H * H)
    for t, b in h.items():
        if t not in ext_chasy and (t // H) % 8 == 0: ctrl[dt.datetime.utcfromtimestamp(t / 1000).hour].append((b[4] / b[1] - 1) * 1e4)
po = collections.defaultdict(list)
for d, n, g, s in sd: po[d].append(n)
dm = [sum(v) / len(v) for v in po.values()]
m = sum(dm) / len(dm) if dm else 0; s_ = math.sqrt(sum((x - m) ** 2 for x in dm) / (len(dm) - 1)) if len(dm) > 2 else float("nan")
out = {"vyplat": len(sd), "dat": len(dm), "monet": len({x[3] for x in sd}), "sred_net_bps": round(sum(x[1] for x in sd) / max(1, len(sd)), 2),
       "sred_gross_bps": round(sum(x[2] for x in sd) / max(1, len(sd)), 2), "t_po_datam": round(m / (s_ / math.sqrt(len(dm))), 2) if dm else None,
       "kontrol_abs_hod_bps": round(sum(abs(v) for vs in ctrl.values() for v in vs) / max(1, sum(len(v) for v in ctrl.values())), 2)}
out["verdikt"] = "PASS" if out["vyplat"] >= 300 and out["dat"] >= 60 and out["sred_net_bps"] > 0 and (out["t_po_datam"] or 0) >= 2 else "FAIL"
(HERE / "results" / "fanding_posle_20261026.json").write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False, indent=1))
