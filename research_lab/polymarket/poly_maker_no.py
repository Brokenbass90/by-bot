#!/usr/bin/env python3
"""PREREG_POLY_MAKER_NO_2026_10_26 (008efb1).
python3 research_lab/polymarket/poly_maker_no.py <strike.jsonl из poly_px1_zapazdyvanie izvlech> <m5_dir> <out.json>"""
import bisect, collections, datetime as dt, json, math, sys
from pathlib import Path
FEE = lambda p: 0.07 * p * (1 - p); H = 3600_000; OKNO = 60 * 60_000


def main(fin, m5, vyv):
    px = {}
    for a in ("BTCUSDT", "ETHUSDT"):
        rows = sorted(json.loads(l) for l in open(Path(m5) / f"{a}.jsonl")); px[a] = ([r[0] + 300000 for r in rows], [r[4] for r in rows])
    def cena(a, t):
        e, c = px[a]; i = bisect.bisect_right(e, t) - 1
        return (c[i], i) if i >= 0 and t - e[i] < 600000 else (None, None)
    def sigma(a, i):
        c = px[a][1]
        if i < 289: return None
        r = [math.log(c[j] / c[j - 1]) for j in range(i - 287, i + 1)]; m = sum(r) / len(r)
        return math.sqrt(sum((x - m) ** 2 for x in r) / len(r)) * math.sqrt(288 * 365)
    def fair(a, t, K, rasch):
        S, i = cena(a, t)
        if S is None: return None
        s = sigma(a, i); tau = (rasch - t) / 1000 / 86400 / 365
        if not s or tau <= 0: return None
        return 0.5 * (1 + math.erf(((math.log(S / K) - 0.5 * s * s * tau) / (s * math.sqrt(tau))) / math.sqrt(2)))
    def ishod(a, K, rasch):
        e, c = px[a]; i = bisect.bisect_left(e, rasch)
        if i >= len(e) or e[i] != rasch: return None
        if abs(c[i] / K - 1) < 0.001: return "NEODNOZNACHNO"
        return 1.0 if c[i] > K else 0.0
    po = collections.defaultdict(list)
    for l in open(fin):
        x = json.loads(l); po[x[1]].append(x)
    REZ = {"MAKER": [], "TAKER": [], "MAKER_BEZ_FILTRA": []}; zayavok = collections.Counter(); neodn = 0
    for cid, xs in po.items():
        xs.sort()
        akt, K, rasch = xs[0][2], xs[0][3], xs[0][4]
        y = ishod(akt, K, rasch)
        if y is None: continue
        if y == "NEODNOZNACHNO": neodn += 1; continue
        for ruka in REZ:
            i = 0
            while i < len(xs):
                t, _, _, _, _, bid, bsz, ask, asz = xs[i]
                mid = (bid + ask) / 2
                if not (0.10 <= mid <= 0.90) or rasch - t < 2 * H: i += 1; continue
                if ruka != "MAKER_BEZ_FILTRA":
                    f = fair(akt, t, K, rasch)
                    if f is None or ask < f + 0.02: i += 1; continue
                zayavok[ruka] += 1
                if ruka == "TAKER":
                    c = 1 - bid; sh = 10 / c; REZ[ruka].append((rasch, akt, sh * ((1 - y) - c - FEE(c)), mid)); i += 1
                    while i < len(xs) and xs[i][0] < t + OKNO: i += 1          # та же частота решений, что у мейкера
                    continue
                a = ask; j = i + 1; isp = None
                while j < len(xs) and xs[j][0] <= t + OKNO:
                    if xs[j][5] >= a: isp = j; break
                    j += 1
                if isp is not None:
                    c = 1 - a; sh = 10 / c; REZ[ruka].append((rasch, akt, sh * ((1 - y) - c), mid)); i = isp + 1
                else:
                    i = j
    def svod(R, nz):
        if not R: return dict(zayavok=nz, ispolneno=0)
        g = collections.defaultdict(list)
        for r, a, p, _ in R: g[(r, a)].append(p)
        dm = [sum(v) for v in g.values()]; m = sum(dm) / len(dm)
        sd = math.sqrt(sum((x - m) ** 2 for x in dm) / (len(dm) - 1)) if len(dm) > 2 else float("nan")
        return dict(zayavok=nz, ispolneno=len(R), dolya_isp=round(len(R) / nz, 3) if nz else None, dat_x_akt=len(g),
                    dat=len({r for r, a in g}), sred_usd_na_10=round(sum(p for *_, p, _ in R) / len(R), 3), itogo_usd=round(sum(p for *_, p, _ in R), 2),
                    t_po_datam=round(m / (sd / math.sqrt(len(dm))), 2) if len(dm) > 2 and sd > 0 else None,
                    dolya_plyus=round(sum(p > 0 for *_, p, _ in R) / len(R), 3),
                    po_aktivu={a: round(sum(p for _, aa, p, _ in R if aa == a), 2) for a in ("BTCUSDT", "ETHUSDT")},
                    po_datam={str(r): round(sum(p for rr, _, p, _ in R if rr == r), 3) for r in sorted({r for r, *_ in R})})
    out = {k: svod(v, zayavok[k]) for k, v in REZ.items()}; out["neodnoznachnyh_rynkov"] = neodn
    m, tk = out["MAKER"], out["TAKER"]
    if m.get("ispolneno", 0) < 100 or m.get("dat", 0) < 15: out["verdikt"] = "INCONCLUSIVE_MALO" if m.get("sred_usd_na_10", -1) > 0 else "FAIL"
    elif m["sred_usd_na_10"] <= 0: out["verdikt"] = "FAIL"
    elif (m["t_po_datam"] or 0) >= 2 and m["sred_usd_na_10"] > tk.get("sred_usd_na_10", -9): out["verdikt"] = "PASS"
    else: out["verdikt"] = "INCONCLUSIVE"
    Path(vyv).write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
