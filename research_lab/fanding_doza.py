"""PREREG_FANDING_DOZA_2026_10_26. python3 research_lab/fanding_doza.py <m5_dir> <funding_dir> <out.json> [simvoly через запятую]"""
import bisect, collections, json, math, sys, datetime as dt
from pathlib import Path
M5, FD, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
KORZ = [(0, 1e-4, "<0.01%"), (1e-4, 3e-4, "0.01-0.03%"), (3e-4, 1e-3, "0.03-0.10%"), (1e-3, 9, ">=0.10%")]
part = json.loads(OUT.read_text()) if OUT.exists() else {"zapisi": []}
gotovo = {z[0] for z in part["zapisi"]}
syms = sorted(p.name for p in M5.iterdir() if p.is_dir())
if len(sys.argv) > 4: syms = sys.argv[4].split(",")
for s in syms:
    if s in gotovo or not (FD / f"{s}.json").exists(): continue
    rec = json.loads((M5 / s / f"{s}.json").read_text())["records"]
    ts = [r["ts_ms"] for r in rec]; pos = {t: i for i, t in enumerate(ts)}
    fr = sorted((x["funding_time_ms"], x["funding_rate"]) for x in json.loads((FD / f"{s}.json").read_text())["records"])
    for k in range(1, len(fr)):
        T, prev_r = fr[k][0], fr[k - 1][1]
        if T - fr[k - 1][0] > 9 * 3600e3 or prev_r == 0: continue
        i0, i1 = pos.get(T - 3600_000), pos.get(T - 300_000)
        j0, j1 = pos.get(T), pos.get(T + 3300_000)
        if i0 is None or i1 is None: continue
        pre = rec[i1]["close"] / rec[i0]["open"] - 1
        post = rec[j1]["close"] / rec[j0]["open"] - 1 if j0 is not None and j1 is not None else None
        sg = -1 if prev_r > 0 else 1
        part["zapisi"].append([s, T, prev_r, sg * pre * 1e4, (-sg * post * 1e4) if post is not None else None])
    part["zapisi"].append([s, None, None, None, None])
    OUT.write_text(json.dumps(part))
    print(s, flush=True)
Z = [z for z in part["zapisi"] if z[1] is not None]
def st_kl(rows):
    if len(rows) < 3: return None
    g = collections.defaultdict(list)
    for z in rows: g[dt.datetime.utcfromtimestamp(z[1] / 1000).date()].append(z[3])
    m = sum(z[3] for z in rows) / len(rows); dm = [sum(v) / len(v) for v in g.values()]
    mm = sum(dm) / len(dm); sd = math.sqrt(sum((x - mm) ** 2 for x in dm) / (len(dm) - 1))
    return {"n": len(rows), "dat": len(dm), "sred_bps": round(m, 2), "t_po_datam": round(mm / (sd / math.sqrt(len(dm))), 2)}
res = {}
for lo, hi, nm in KORZ:
    rows = [z for z in Z if lo <= abs(z[2]) < hi]
    res[nm] = st_kl(rows)
    post = [z[4] for z in rows if z[4] is not None]
    if res[nm]: res[nm]["posle_sred_bps"] = round(sum(post) / len(post), 2) if post else None
print(json.dumps({"monet": len({z[0] for z in Z}), "vyplat": len(Z), "korziny": res}, ensure_ascii=False, indent=1))
