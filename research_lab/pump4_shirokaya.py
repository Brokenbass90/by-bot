#!/usr/bin/env python3
"""pump4_shirokaya.py — prereg/PREREG_PUMP4_SHIROKAYA_VSELENNAYA_2026_10_27.md. Mac (сеть Bybit), ~20–30 мин. Только чтение.
    .venv/bin/python3 research_lab/pump4_shirokaya.py > research_lab/data/pump4_shirokaya.log 2>&1"""
import collections, hashlib, importlib, json, math, os, statistics as st, sys, time, urllib.request
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import pump4_pereschet as P, pump4_polnyy_povtor as PP
from research_machine import simulate as SIM
SHA = "b350bd608e830588dfc9816c5af7faf37ac64df2ee3a78756135f51b57229822"

def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "research-readonly/1.0"}), timeout=25) as r: return json.loads(r.read())

def priznaki(b, i):
    c = lambda k: b[k][4]
    try:
        r9 = (c(i - 3) / c(i - 12) - 1) / 9; r3 = (c(i) / c(i - 3) - 1) / 3
        rng = b[i][2] - b[i][3]
        return dict(rost24=c(i) / c(i - 24) - 1, rost72=c(i) / c(i - 72) - 1, zamedlenie=r3 - r9,
                    fitil=(b[i][2] - max(b[i][1], b[i][4])) / rng if rng > 0 else 0.0,
                    obem=b[i][5] / (sum(b[k][5] for k in range(i - 24, i)) / 24 or 1), ot_maksimuma=c(i) / max(b[k][2] for k in range(i - 24, i + 1)) - 1)
    except Exception: return {}

def progon(syms, metka):
    os.environ.update({f"{P.PFX}_SYMBOL_ALLOWLIST": ",".join(syms), f"{P.PFX}_ALLOW_LONGS": "1", f"{P.PFX}_ALLOW_SHORTS": "1"})
    K = getattr(importlib.import_module(f"strategies.{P.MODUL}"), P.KLASS)
    now = int(time.time() * 1000); konec = (now // P.CHAS) * P.CHAS; rng = np.random.default_rng(P.SEED); out = []
    for n, sym in enumerate(syms, 1):
        try: b = [x for x in P.svechi_okno(sym, PP.START - PP.PROGREV_CH * P.CHAS, konec) if x[0] + P.CHAS <= now]
        except Exception: continue
        strat = K(); stt = P.Store(sym); perv = sym if P.pervyy_argument(K) == "symbol" else stt
        pool = list(range(200, max(200, len(b) - P.HOLD - 2)))
        for i in range(len(b) - 1):
            stt.rows = b[: i + 1]; r_ = b[i]
            try: s = strat.maybe_signal(perv, *r_)
            except Exception: s = None
            if s is None or getattr(s, "side", None) not in ("long", "short") or r_[0] < PP.START or i < 200: continue
            r = SIM(b, i, s.side, s.sl, list(s.tps or []), (s.tp_fracs or [P.F1])[0], P.STOP_MULT, P.HOLD)
            if r is None or r.get("lev", 0) > P.MAX_LEV or not P.zaversheno(b, i, r): continue
            e = b[i + 1][1]; risk = abs(e - (e + (s.sl - e) * P.STOP_MULT)); rr = [abs(q - e) / risk for q in (s.tps or [])] if risk > 0 else []
            k1, k2 = (rr + [999.0, 999.0])[:2]
            c = [P.sim_geo(b, int(rng.choice(pool)), s.side == "short", 1.0 / r["lev"], k1, k2, (s.tp_fracs or [P.F1])[0], P.HOLD) for _ in range(P.DRAWS)] if pool else []
            c = [x for x in c if x is not None]
            out.append(dict(sym=sym, ts=r_[0], side=s.side, R=round(r["R"], 4), ctrl=round(float(np.mean(c)), 4) if c else None,
                            risk_pct=round(risk / e * 100, 3), vyborka=metka, **priznaki(b, i)))
        if n % 25 == 0: print(metka, n, len(syms), len(out), flush=True)
    return out

def t_dni(x):
    po = collections.defaultdict(list)
    for d, v in x: po[d].append(v)
    m = [st.mean(v) for v in po.values()]
    return round(st.mean(m) / (st.stdev(m) / math.sqrt(len(m))), 2) if len(m) > 2 and st.stdev(m) > 0 else None

def svod(g):
    g = [x for x in g if x["ctrl"] is not None]
    if not g: return dict(n=0)
    return dict(n=len(g), monet=len({x["sym"] for x in g}), R=round(st.mean(x["R"] for x in g), 4), kontrol=round(st.mean(x["ctrl"] for x in g), 4),
                R_minus_kontrol=round(st.mean(x["R"] - x["ctrl"] for x in g), 4),
                t_dni=t_dni([(time.strftime("%Y-%m-%d", time.gmtime(x["ts"] / 1000)), x["R"] - x["ctrl"]) for x in g]),
                summa_R=round(sum(x["R"] for x in g), 2), vyigr=round(sum(x["R"] > 0 for x in g) / len(g), 3))

def main():
    if hashlib.sha256((HERE / "prereg/PREREG_PUMP4_SHIROKAYA_VSELENNAYA_2026_10_27.md").read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    v1 = json.load(open(HERE / "data" / "pump4_v1_universe_20261020.json"))["symbols"]
    tk = get("https://api.bybit.com/v5/market/tickers?category=linear")["result"]["list"]
    novye = [t["symbol"] for t in sorted(tk, key=lambda t: -float(t.get("turnover24h") or 0)) if t["symbol"].endswith("USDT") and t["symbol"] not in v1][:250]
    st_ = progon(v1, "V1"); nv = progon(novye, "NOVYE")
    a, b = svod(st_), svod(nv)
    ok = b.get("n", 0) >= 60 and b.get("R", 0) > 0 and b.get("R_minus_kontrol", 0) > 0 and (b.get("t_dni") or 0) >= 2
    vse = st_ + nv; pr = {}
    for p in ("rost24", "rost72", "zamedlenie", "fitil", "obem", "ot_maksimuma"):
        g = sorted([x for x in vse if x.get(p) is not None], key=lambda x: x[p]); k = len(g) // 3
        if k < 10: continue
        pr[p] = dict(granicy=[round(g[k - 1][p], 4), round(g[-k][p], 4)], niz=svod(g[:k]), sered=svod(g[k:-k]), verh=svod(g[-k:]))
    out = dict(V1=a, NOVYE=b, vyvod="PASS_RASSHIRENIE" if ok else "FAIL", priznaki=pr)
    print(json.dumps({k: out[k] for k in ("V1", "NOVYE", "vyvod")}, ensure_ascii=False, indent=1))
    for p, v in pr.items(): print(p, "низ", v["niz"].get("R"), "середина", v["sered"].get("R"), "верх", v["verh"].get("R"), "границы", v["granicy"])
    f = HERE / "results" / time.strftime("pump4_shirokaya_%Y%m%dT%H%MZ.json", time.gmtime()); f.write_text(json.dumps(dict(out, sdelki=vse), ensure_ascii=False)); print("файл", f)

if __name__ == "__main__":
    main()
