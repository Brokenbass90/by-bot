#!/usr/bin/env python3
"""pump4_filtr_istoriya.py — prereg/PREREG_PUMP4_FILTR_ROST24_ISTORIYA_2025_2026_10_29.md. Mac (сеть Bybit), ~30–60 мин. Только чтение.
    .venv/bin/python3 research_lab/pump4_filtr_istoriya.py > research_lab/data/pump4_filtr_istoriya.log 2>&1"""
import collections, hashlib, importlib, json, math, os, statistics as st, sys, time
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import pump4_pereschet as P, pump4_shirokaya as PS
from research_machine import simulate as SIM
SHA = "b96f0590558451937d8068a72ac83e5fa90afb94df8fee551e4043d73b937cf8"; OT, DO = 1735689600000, 1759276800000          # 2025-01-01 … 2025-10-01 UTC
POROG = 0.0599; KONEC = DO + 7 * 24 * 3600000

def main():
    if hashlib.sha256((HERE / "prereg/PREREG_PUMP4_FILTR_ROST24_ISTORIYA_2025_2026_10_29.md").read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    syms = json.load(open(HERE / "data" / "pump4_v1_universe_20261020.json"))["symbols"]
    os.environ.update({f"{P.PFX}_SYMBOL_ALLOWLIST": ",".join(syms), f"{P.PFX}_ALLOW_LONGS": "1", f"{P.PFX}_ALLOW_SHORTS": "1"})
    K = getattr(importlib.import_module(f"strategies.{P.MODUL}"), P.KLASS); rng = np.random.default_rng(P.SEED); out = []
    for n, sym in enumerate(syms, 1):
        try: b = P.svechi_okno(sym, OT - 1200 * P.CHAS, KONEC)
        except Exception: continue
        if len(b) < 400: continue
        strat = K(); stt = P.Store(sym); perv = sym if P.pervyy_argument(K) == "symbol" else stt
        pool = list(range(200, max(200, len(b) - P.HOLD - 2)))
        for i in range(len(b) - 1):
            stt.rows = b[: i + 1]; r_ = b[i]
            try: s = strat.maybe_signal(perv, *r_)
            except Exception: s = None
            if s is None or getattr(s, "side", None) not in ("long", "short") or not (OT <= r_[0] < DO) or i < 200: continue
            r = SIM(b, i, s.side, s.sl, list(s.tps or []), (s.tp_fracs or [P.F1])[0], P.STOP_MULT, P.HOLD)
            if r is None or r.get("lev", 0) > P.MAX_LEV or not P.zaversheno(b, i, r): continue
            e = b[i + 1][1]; risk = abs(e - (e + (s.sl - e) * P.STOP_MULT)); rr = [abs(q - e) / risk for q in (s.tps or [])] if risk > 0 else []
            k1, k2 = (rr + [999.0, 999.0])[:2]
            c = [P.sim_geo(b, int(rng.choice(pool)), s.side == "short", 1.0 / r["lev"], k1, k2, (s.tp_fracs or [P.F1])[0], P.HOLD) for _ in range(P.DRAWS)] if pool else []
            c = [x for x in c if x is not None]
            out.append(dict(sym=sym, ts=r_[0], side=s.side, R=round(r["R"], 4), ctrl=round(float(np.mean(c)), 4) if c else None, **PS.priznaki(b, i)))
        if n % 20 == 0: print(n, len(syms), len(out), flush=True)
    fil = [x for x in out if x.get("rost24") is not None and x["rost24"] >= POROG and x["ctrl"] is not None]
    ost = [x for x in out if x.get("rost24") is not None and x["rost24"] < POROG and x["ctrl"] is not None]
    a, b_ = PS.svod(fil), PS.svod(ost)
    mes = collections.defaultdict(lambda: [[], []])
    for x in fil: mes[time.strftime("%Y-%m", time.gmtime(x["ts"] / 1000))][0].append(x["R"])
    for x in ost: mes[time.strftime("%Y-%m", time.gmtime(x["ts"] / 1000))][1].append(x["R"])
    po_mes = {m: dict(filtr=(len(f), round(st.mean(f), 3) if f else None, round(sum(f) * 10, 1)), ostalnye=(len(o), round(st.mean(o), 3) if o else None, round(sum(o) * 10, 1)))
              for m, (f, o) in sorted(mes.items())}
    reg = sum(1 for v in po_mes.values() if v["filtr"][1] is not None and v["ostalnye"][1] is not None and v["filtr"][1] >= v["ostalnye"][1])
    ok = a.get("n", 0) >= 60 and a.get("R", 0) > 0 and a.get("R", 0) > b_.get("R", 9) and a.get("R_minus_kontrol", 0) > 0 and (a.get("t_dni") or 0) >= 2 and reg >= 6
    res = dict(filtr=a, ostalnye=b_, vse=PS.svod([x for x in out if x["ctrl"] is not None]), po_mesyacam=po_mes, mesyacev_filtr_ne_huzhe=reg,
               usd_pri_riske_10=dict(filtr=round(sum(x["R"] for x in fil) * 10, 1), ostalnye=round(sum(x["R"] for x in ost) * 10, 1)),
               vyvod="FILTR_PODTVERZHDEN" if ok else "FILTR_NE_PODTVERZHDEN")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    (HERE / "results" / time.strftime("pump4_filtr_istoriya_%Y%m%dT%H%MZ.json", time.gmtime())).write_text(json.dumps(dict(res, sdelki=out), ensure_ascii=False))

if __name__ == "__main__":
    main()
