#!/usr/bin/env python3
"""PREREG_POLY_PX1_ZAPAZDYVANIE_2026_10_26 (527b9ba).
python3 .../poly_px1_zapazdyvanie.py izvlech <snimki_dir> <out.jsonl>   # компактные строки страйков BTC/ETH
python3 .../poly_px1_zapazdyvanie.py schet <out.jsonl> <m5_dir> <itog.json>"""
import bisect, collections, datetime as dt, json, math, re, sys
from pathlib import Path

RX = re.compile(r"price of (Bitcoin|Ethereum) be above \$([\d,\.]+)(k?) on (\w+) (\d+)\?", re.I)
AKT = {"bitcoin": "BTCUSDT", "ethereum": "ETHUSDT"}
MES = {m: i + 1 for i, m in enumerate("january february march april may june july august september october november december".split())}
FEE = lambda p: 0.07 * p * (1 - p)


def izvlech(d, out):
    n = 0
    with open(out, "w") as fo:
        for f in sorted(Path(d).glob("*.jsonl")):
            for l in open(f):
                if '"strike"' not in l: continue
                r = json.loads(l); m = RX.search(r.get("vopros") or "")
                if not m or not r["bids"] or not r["asks"]: continue
                k = float(m.group(2).replace(",", "")) * (1000 if m.group(3) else 1)
                rasch = dt.datetime(2026, MES[m.group(4).lower()], int(m.group(5)), 16, 0, tzinfo=dt.timezone.utc).timestamp() * 1000
                fo.write(json.dumps([r["t"], r["conditionId"], AKT[m.group(1).lower()], k, rasch,
                                     r["bids"][0][0], r["bids"][0][1], r["asks"][0][0], r["asks"][0][1]]) + "\n"); n += 1
    print("строк", n)


def ncdf(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def schet(fin, m5, vyv):
    px = {}
    for a in AKT.values():
        rows = [json.loads(l) for l in open(Path(m5) / f"{a}.jsonl")]
        rows.sort(); px[a] = ([r[0] + 300000 for r in rows], [r[4] for r in rows])
    def cena(a, t):
        ends, cl = px[a]; i = bisect.bisect_right(ends, t) - 1
        return (cl[i], i) if i >= 0 and t - ends[i] < 600000 else (None, None)
    def sigma(a, i):
        cl = px[a][1]
        if i < 289: return None
        r = [math.log(cl[j] / cl[j - 1]) for j in range(i - 287, i + 1)]
        m = sum(r) / len(r); return math.sqrt(sum((x - m) ** 2 for x in r) / len(r)) * math.sqrt(288 * 365)
    def fair(S, K, tau, s):
        if tau <= 0 or s is None or s <= 0: return None
        return ncdf((math.log(S / K) - 0.5 * s * s * tau) / (s * math.sqrt(tau)))
    po = collections.defaultdict(list)
    for l in open(fin):
        x = json.loads(l); po[x[1]].append(x)
    M, T = [], []
    for cid, xs in po.items():
        xs.sort()
        for a0, a1 in zip(xs, xs[1:]):
            t0, t1 = a0[0], a1[0]
            if not 600000 <= t1 - t0 <= 1200000: continue
            mid0, mid1 = (a0[5] + a0[7]) / 2, (a1[5] + a1[7]) / 2
            if not 0.10 <= mid0 <= 0.90: continue
            akt, K, rasch = a0[2], a0[3], a0[4]
            S0, i0 = cena(akt, t0); Sp, _ = cena(akt, t0 - 900000)
            if S0 is None or Sp is None: continue
            s = sigma(akt, i0); tau = (rasch - t0) / 1000 / 86400 / 365
            f0, fp = fair(S0, K, tau, s), fair(Sp, K, tau + 900 / 86400 / 365, s)
            if f0 is None or fp is None: continue
            P, D = f0 - fp, mid1 - mid0
            M.append((t0, P, D))
            bid0, ask0, bid1, ask1 = a0[5], a0[7], a1[5], a1[7]
            sd = None
            if P > 0 and f0 - ask0 > FEE(ask0):
                sh = 10 / ask0; sd = ("YES", sh * (bid1 - ask0 - FEE(ask0) - FEE(bid1)), a0[8] >= sh)
            elif P < 0 and (1 - f0) - (1 - bid0) > FEE(1 - bid0):
                c0, c1 = 1 - bid0, 1 - ask1; sh = 10 / c0; sd = ("NO", sh * (c1 - c0 - FEE(c0) - FEE(c1)), a0[6] >= sh)
            if sd: T.append((t0, sd[0], sd[1], sd[2], akt))
    def klaster_slope(rows):
        n = len(rows); mx = sum(r[1] for r in rows) / n; my = sum(r[2] for r in rows) / n
        sxx = sum((r[1] - mx) ** 2 for r in rows); b = sum((r[1] - mx) * (r[2] - my) for r in rows) / sxx
        g = collections.defaultdict(float)
        for t, x, y in rows: g[t] += (x - mx) * ((y - my) - b * (x - mx))
        se = math.sqrt(sum(v * v for v in g.values())) / sxx
        return b, b / se, n
    b, tb, n = klaster_slope(M)
    big = [r for r in M if abs(r[1]) >= 0.02]
    bb, tbb, nb = klaster_slope(big) if len(big) > 30 else (None, None, len(big))
    def t_kl(vals):
        g = collections.defaultdict(float)
        for t, v in vals: g[t] += v
        xs = list(g.values()); m = sum(xs) / len(xs); s = math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))
        return sum(v for _, v in vals) / len(vals), m / (s / math.sqrt(len(xs))), len(xs)
    out = {"M1": {"par": n, "beta": round(b, 3), "t": round(tb, 2), "sred_abs_P": round(sum(abs(r[1]) for r in M) / n, 4),
                  "bolshie_|P|>=2c": {"par": nb, "beta": round(bb, 3) if bb is not None else None, "t": round(tbb, 2) if tbb else None}}}
    if T:
        sr, tt, nk = t_kl([(t, p) for t, _, p, _, _ in T])
        dni = len({dt.datetime.utcfromtimestamp(t / 1000).date() for t, *_ in T})
        gl = [x for x in T if x[3]]
        out["PnL"] = {"sdelok": len(T), "sred_usd_na_10": round(sr, 4), "t_po_krugam": round(tt, 2), "krugov": nk, "dney": dni,
                      "plyus_dolya": round(sum(p > 0 for *_, p, _, _ in [(0, 0, x[2], 0, 0) for x in T]) / len(T), 3),
                      "itogo_usd": round(sum(x[2] for x in T), 2), "s_glubinoy_na_10$": len(gl),
                      "sred_s_glubinoy": round(sum(x[2] for x in gl) / len(gl), 4) if gl else None,
                      "po_storone": {s: round(sum(x[2] for x in T if x[1] == s) / max(1, sum(x[1] == s for x in T)), 4) for s in ("YES", "NO")},
                      "po_aktivu": {a: {"n": sum(x[4] == a for x in T), "sred": round(sum(x[2] for x in T if x[4] == a) / max(1, sum(x[4] == a for x in T)), 4)} for a in AKT.values()}}
        p = out["PnL"]; out["verdikt"] = "PASS" if p["sred_usd_na_10"] > 0 and p["t_po_krugam"] >= 2 and p["sdelok"] >= 100 and p["dney"] >= 10 else "FAIL"
    Path(vyv).write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    {"izvlech": lambda: izvlech(sys.argv[2], sys.argv[3]), "schet": lambda: schet(sys.argv[2], sys.argv[3], sys.argv[4])}[sys.argv[1]]()
