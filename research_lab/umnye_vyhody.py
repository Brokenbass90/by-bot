#!/usr/bin/env python3
"""umnye_vyhody.py — prereg/PREREG_UMNYE_VYHODY_2026_10_27.md. Mac (сеть Bybit), ~15–25 мин. Только чтение публичных свечей.
    .venv/bin/python3 research_lab/umnye_vyhody.py > research_lab/data/umnye_vyhody.log 2>&1"""
import collections, hashlib, importlib, json, math, os, statistics as st, sys, time, urllib.request
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import pump4_pereschet as P, pump4_polnyy_povtor as PP, fanding_hvost as F
from research_machine import simulate as SIM_V1
SHA = "1f0c19a5347bfd5cb8af2c425ec467992ca3fcf808d356f52eeef2b76d4dc953"; H = 3600000

def atr(b, j, n=14):
    tr = [max(b[k][2] - b[k][3], abs(b[k][2] - b[k - 1][4]), abs(b[k][3] - b[k - 1][4])) for k in range(max(1, j - n), j)]
    return sum(tr) / len(tr) if tr else None

def sim_p4(b, i, side, sl0, tps, f1, rule):
    if rule == "V1": return SIM_V1(b, i, side, sl0, tps, f1, P.STOP_MULT, P.HOLD)
    if rule == "V2_BE": return P.simulate_v2(b, i, side, sl0, tps, f1, P.STOP_MULT, P.HOLD)
    if rule == "TIME48": return SIM_V1(b, i, side, sl0, tps, f1, P.STOP_MULT, 48)
    e = i + 1
    if e >= len(b): return None
    short = side == "short"; entry = b[e][1]; sl = entry + (sl0 - entry) * P.STOP_MULT
    risk = (sl - entry) if short else (entry - sl)
    if risk <= 0: return None
    cost = entry / risk * 2 * 6 / 1e4; stop, rem, gross, best, part = sl, 1.0, 0.0, entry, False
    for j in range(e, min(e + P.HOLD, len(b))):
        h, l = b[j][2], b[j][3]
        if (h >= stop) if short else (l <= stop):
            return dict(R=gross + rem * ((entry - stop) if short else (stop - entry)) / risk - cost, bars=j - e)
        if rule == "PART_TRAIL" and not part and ((l <= entry - risk) if short else (h >= entry + risk)):
            gross += 0.5; rem = 0.5; part = True
        best = min(best, l) if short else max(best, h)
        if ((entry - best) if short else (best - entry)) >= risk:
            a = atr(b, j) or 0
            ns = best + 3 * a if short else best - 3 * a
            ns = min(ns, entry) if short else max(ns, entry)
            stop = min(stop, ns) if short else max(stop, ns)
    j = min(e + P.HOLD, len(b)) - 1; px = b[j][4]
    return dict(R=gross + rem * ((entry - px) if short else (px - entry)) / risk - cost, bars=j - e)

def pump4():
    syms = json.load(open(HERE / "data" / "pump4_v1_universe_20261020.json"))["symbols"]
    os.environ.update({f"{P.PFX}_SYMBOL_ALLOWLIST": ",".join(syms), f"{P.PFX}_ALLOW_LONGS": "1", f"{P.PFX}_ALLOW_SHORTS": "1"})
    K = getattr(importlib.import_module(f"strategies.{P.MODUL}"), P.KLASS)
    now = int(time.time() * 1000); konec = (now // P.CHAS) * P.CHAS; out = []
    for n, sym in enumerate(syms, 1):
        try: b = [x for x in P.svechi_okno(sym, PP.START - PP.PROGREV_CH * P.CHAS, konec) if x[0] + P.CHAS <= now]
        except Exception: continue
        strat = K(); stt = P.Store(sym); perv = sym if P.pervyy_argument(K) == "symbol" else stt
        for i in range(len(b) - 1):
            stt.rows = b[: i + 1]; r_ = b[i]
            try: s = strat.maybe_signal(perv, *r_)
            except Exception: s = None
            if s is None or getattr(s, "side", None) not in ("long", "short") or r_[0] < PP.START or i < 200: continue
            base = SIM_V1(b, i, s.side, s.sl, list(s.tps or []), (s.tp_fracs or [P.F1])[0], P.STOP_MULT, P.HOLD)
            if base is None or base.get("lev", 0) > P.MAX_LEV or not P.zaversheno(b, i, base): continue
            z = dict(sym=sym, ts=r_[0])
            for rule in ("V1", "V2_BE", "TRAIL_ATR3", "TIME48", "PART_TRAIL"):
                r = sim_p4(b, i, s.side, s.sl, list(s.tps or []), (s.tp_fracs or [P.F1])[0], rule); z[rule] = round(r["R"], 4) if r else None
            out.append(z)
        if n % 20 == 0: print("PUMP4", n, len(syms), len(out), flush=True)
    return out

def svechi(sym, t0, t1):
    u = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={sym}&interval=60&start={t0}&end={t1}&limit=60"
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "research-readonly/1.0"}), timeout=25) as r:
        return sorted([[int(x[0])] + [float(v) for v in x[1:5]] for x in (json.loads(r.read()).get("result") or {}).get("list") or []])

def hvost():
    u = {}
    for fn in F.LEDGERY:
        for l in open(F.ROOT / fn):
            r = json.loads(l)
            if r.get("record_type") == "outcome" and r.get("status") == "closed" and r.get("side") == -1 and r.get("symbol") not in F.NE_HVOST:
                u[(r["symbol"], r["event_ts"])] = r
    out, KOM = [], 36.0
    for (s, t), r in sorted(u.items(), key=lambda kv: kv[0][1]):
        try: b = svechi(s, t, t + 33 * H); time.sleep(0.12)
        except Exception: continue
        if len(b) < 33: continue
        e = b[0][1]; z = dict(sym=s, ts=t)
        def vyhod(k): return (e - b[k][4]) / e * 1e4 - KOM          # закрытие бара k (k = 0..32)
        def avar(do):
            for k in range(do):
                if b[k][2] >= e * 1.8: return -(0.8 * 1.05) * 1e4 - KOM
            return None
        for nm, hh in (("BASE16", 16), ("T8", 8), ("T24", 24), ("T32", 32)):
            z[nm] = avar(hh) or vyhod(hh - 1)
        tp = next((k for k in range(16) if b[k][3] <= e * 0.90), None)
        z["TP10"] = avar(16) or (1000 - KOM if tp is not None and not any(b[k][2] >= e * 1.8 for k in range(tp + 1)) else vyhod(15))
        lo, stop, res = e, None, None
        for k in range(32):
            if b[k][2] >= e * 1.8: res = -(0.8 * 1.05) * 1e4 - KOM; break
            if stop and b[k][2] >= stop: res = (e - stop) / e * 1e4 - KOM; break
            lo = min(lo, b[k][3])
            if lo <= e * 0.95: stop = min(stop or 1e18, lo * 1.05)
        z["TRAIL5"] = res if res is not None else vyhod(31)
        out.append(z)
    return out

def otsenka(L, varianty, baza):
    L = sorted([x for x in L if all(x.get(v) is not None for v in varianty)], key=lambda x: x["ts"]); h = len(L) // 2
    ran, poz = L[:h], L[h:]
    sred = {v: round(st.mean(x[v] for x in ran), 4) for v in varianty}
    luch = max(varianty, key=lambda v: sred[v])
    po = collections.defaultdict(list)
    for x in poz: po[time.strftime("%Y-%m-%d", time.gmtime(x["ts"] / 1000))].append(x[luch] - x[baza])
    m = [st.mean(v) for v in po.values()]
    t = st.mean(m) / (st.stdev(m) / math.sqrt(len(m))) if len(m) > 2 and st.stdev(m) > 0 else None
    raz = st.mean(x[luch] - x[baza] for x in poz) if poz else None
    return dict(sdelok=len(L), rannyaya=sred, vybran=luch, pozdnyaya_vse={v: round(st.mean(x[v] for x in poz), 4) for v in varianty} if poz else None,
                pozdnyaya_raznica_s_bazoy=round(raz, 4) if raz is not None else None, t_dni=round(t, 2) if t else None,
                vyvod=("KANDIDAT_V_TEN" if luch != baza and raz is not None and raz > 0 else "BAZA_OSTAETSYA"))

def main():
    if hashlib.sha256((HERE / "prereg/PREREG_UMNYE_VYHODY_2026_10_27.md").read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    hv = hvost(); print("SHORT_HVOST сделок:", len(hv), flush=True)
    o2 = otsenka(hv, ["BASE16", "T8", "T24", "T32", "TP10", "TRAIL5"], "BASE16"); print("SHORT_HVOST:", json.dumps(o2, ensure_ascii=False), flush=True)
    p4 = pump4(); o1 = otsenka(p4, ["V1", "V2_BE", "TRAIL_ATR3", "TIME48", "PART_TRAIL"], "V1"); print("PUMP4:", json.dumps(o1, ensure_ascii=False), flush=True)
    f = HERE / "results" / time.strftime("umnye_vyhody_%Y%m%dT%H%MZ.json", time.gmtime())
    f.write_text(json.dumps(dict(PUMP4=o1, SHORT_HVOST=o2, sdelki_pump4=p4, sdelki_hvost=hv), ensure_ascii=False)); print("файл", f)

if __name__ == "__main__":
    main()
