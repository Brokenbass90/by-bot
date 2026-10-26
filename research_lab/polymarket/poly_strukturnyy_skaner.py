#!/usr/bin/env python3
"""PREREG_POLY_STRUKTURNYY_SKANER_2026_10_26 (33dc8bb). Только чтение снимков стаканов.
python3 research_lab/polymarket/poly_strukturnyy_skaner.py den <snimki/YYYY-MM-DD.jsonl> <out_dir>   # по дню
python3 research_lab/polymarket/poly_strukturnyy_skaner.py itog <out_dir> <itog.json>"""
import json, re, sys, collections
from pathlib import Path

RATE = {"negrisk": 0.05, "strike": 0.07}
RX = re.compile(r"price of (\w+) be above \$([\d,\.]+)(k?) on (.+?)\?", re.I)


def kupit(levels, q, rate):
    """Купить q долей по аскам [(p, size)]: (стоимость, комиссия) или None, если не хватает глубины."""
    ost, c, f = q, 0.0, 0.0
    for p, s in levels:
        x = min(ost, s); c += x * p; f += x * rate * p * (1 - p); ost -= x
        if ost <= 1e-9: return c, f
    return None


def lomanye(books):
    pts = set()
    for lv in books:
        acc = 0.0
        for p, s in lv:
            acc += s; pts.add(acc)
    return sorted(pts)


def luchshee(books, vyplata, rate):
    """Максимум прибыли по q (кусочно-линейна → максимум в изломах). books — списки асков покупаемых ног."""
    best = (0.0, 0.0, 0.0)  # прибыль $, q, прибыль на долю-набор при q
    top = vyplata - sum(lv[0][0] + rate * lv[0][0] * (1 - lv[0][0]) for lv in books)
    for q in lomanye(books):
        cf = [kupit(lv, q, rate) for lv in books]
        if any(x is None for x in cf): break
        pr = q * vyplata - sum(c + f for c, f in cf)
        if pr > best[0]: best = (pr, q, pr / q)
    # прибыль на $10 вложений (по верху стакана при малом q)
    return best, top


def den(fayl, out_dir):
    raundy = collections.defaultdict(list)
    for l in open(fayl):
        r = json.loads(l); raundy[r["t"]].append(r)
    nahodki, blizost = [], collections.Counter()
    n_s1 = n_s2 = 0
    for t, rows in sorted(raundy.items()):
        sob = collections.defaultdict(list)
        for r in rows: sob[(r["kat"], r["sobytie"])].append(r)
        for (kat, ev), rs in sob.items():
            if kat == "negrisk":
                n = rs[0].get("iskhodov_v_sobytii") or 0
                if len({r["conditionId"] for r in rs}) != n or n < 2: continue
                if all(r["asks"] for r in rs):
                    n_s1 += 1
                    (pr, q, e), top = luchshee([[(float(p), float(s)) for p, s in r["asks"]] for r in rs], 1.0, RATE[kat])
                    blizost[("S1_BUY_ALL", round(top, 2))] += 1
                    if pr > 0.01: nahodki.append({"t": t, "tip": "S1_BUY_ALL", "klyuch": ev, "n": n, "pribyl_usd": round(pr, 3), "dolej": q, "verh_na_nabor": round(top, 4)})
                if all(r["bids"] for r in rs):
                    no = [[(1 - float(p), float(s)) for p, s in r["bids"]] for r in rs]
                    (pr, q, e), top = luchshee(no, n - 1.0, RATE[kat])
                    blizost[("S1_SELL_ALL", round(top, 2))] += 1
                    if pr > 0.01: nahodki.append({"t": t, "tip": "S1_SELL_ALL", "klyuch": ev, "n": n, "pribyl_usd": round(pr, 3), "dolej": q, "verh_na_nabor": round(top, 4)})
            else:
                ks = []
                for r in rs:
                    m = RX.search(r.get("vopros") or "")
                    if not m: continue
                    k = float(m.group(2).replace(",", "")) * (1000 if m.group(3) else 1)
                    ks.append((k, r))
                ks.sort(key=lambda x: x[0])
                for i in range(len(ks)):
                    for j in range(i + 1, len(ks)):
                        (k1, r1), (k2, r2) = ks[i], ks[j]
                        if not r1["asks"] or not r2["bids"]: continue
                        n_s2 += 1
                        legs = [[(float(p), float(s)) for p, s in r1["asks"]], [(1 - float(p), float(s)) for p, s in r2["bids"]]]
                        (pr, q, e), top = luchshee(legs, 1.0, RATE["strike"])
                        blizost[("S2_STRIKE", round(top, 2))] += 1
                        if pr > 0.01:
                            nahodki.append({"t": t, "tip": "S2_STRIKE", "klyuch": f"{ev}:{k1:g}<{k2:g}", "vopros1": r1["vopros"],
                                            "pribyl_usd": round(pr, 3), "dolej": q, "verh_na_nabor": round(top, 4),
                                            "ask1": r1["asks"][0], "bid2": r2["bids"][0]})
    out = {"fayl": Path(fayl).name, "raundov": len(raundy), "raundy_t": sorted(raundy), "proverok_S1": n_s1, "par_S2": n_s2,
           "nahodki": nahodki, "blizost": {f"{a}|{b}": c for (a, b), c in blizost.items()}}
    Path(out_dir, Path(fayl).stem + ".json").write_text(json.dumps(out, ensure_ascii=False))
    print(Path(fayl).name, len(raundy), n_s1, n_s2, "находок", len(nahodki), flush=True)


def itog(out_dir, vyvod):
    dni = [json.loads(f.read_text()) for f in sorted(Path(out_dir).glob("*.json"))]
    vse_t = sorted(t for d in dni for t in d["raundy_t"]); pos = {t: i for i, t in enumerate(vse_t)}
    po = collections.defaultdict(list)
    for d in dni:
        for x in d["nahodki"]: po[(x["tip"], x["klyuch"])].append(x)
    sp = []
    for (tip, k), xs in po.items():
        idx = sorted(pos[x["t"]] for x in xs)
        dlin = best = 1
        for a, b in zip(idx, idx[1:]):
            dlin = dlin + 1 if b == a + 1 else 1; best = max(best, dlin)
        sp.append({"tip": tip, "klyuch": k, "raundov": len(xs), "podryad_max": best,
                   "pribyl_max_usd": max(x["pribyl_usd"] for x in xs), "pribyl_med_usd": sorted(x["pribyl_usd"] for x in xs)[len(xs) // 2],
                   "pervyy_t": min(x["t"] for x in xs), "primer": max(xs, key=lambda x: x["pribyl_usd"])})
    sp.sort(key=lambda z: -z["pribyl_max_usd"])
    blz = collections.Counter()
    for d in dni:
        for k, c in d["blizost"].items(): blz[k] += c
    zachet = [z for z in sp if z["pribyl_max_usd"] >= 1 and z["podryad_max"] >= 2]
    out = {"dney": len(dni), "raundov": len(vse_t), "proverok_S1": sum(d["proverok_S1"] for d in dni), "par_S2": sum(d["par_S2"] for d in dni),
           "razlichnyh_rashozhdeniy": len(sp), "po_tipu": dict(collections.Counter(z["tip"] for z in sp)),
           "zachetnyh_(>=1$,>=2_kruga)": len(zachet), "verdikt": "STRUCTURAL_FOUND" if len({z["klyuch"].split(":")[0] for z in zachet}) >= 5 else "STRUCTURAL_NONE",
           "top": sp[:25], "blizost_verha_stakana": dict(sorted(blz.items(), key=lambda x: (x[0].split("|")[0], float(x[0].split("|")[1]))))}
    Path(vyvod).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k not in ("top", "blizost_verha_stakana")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    {"den": lambda: den(sys.argv[2], sys.argv[3]), "itog": lambda: itog(sys.argv[2], sys.argv[3])}[sys.argv[1]]()
