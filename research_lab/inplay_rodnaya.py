#!/usr/bin/env python3
"""PREREG_INPLAY_RODNAYA_GEOMETRIYA_2026_10_20. python3 inplay_rodnaya.py (из ~/w/skan)."""
import json, math, sys, time
from pathlib import Path
import numpy as np
sys.path.insert(0, "."); sys.path.insert(0, "research_lab")
import skan_m15 as S
from research_machine import Store, pervyy_argument
FEE = 6.0; HOLD = 672; RAZ = 20; PROG = 2.50


def sim(b, i, short, stop_pct, rr, fr, be_r, hold=HOLD):
    """Родная геометрия: вход open i+1, стоп stop_pct, цели rr (в R), доли fr, БУ после цели1 или +be_r R. None — нет данных."""
    e = i + 1
    if e >= len(b): return None
    en = b[e][1]; risk = en * stop_pct
    if risk <= 0: return None
    sl = en + risk if short else en - risk
    tg = [en - x * risk if short else en + x * risk for x in rr]
    cost = 2 * FEE / 1e4 / stop_pct
    rem, gross, k, stop = 1.0, 0.0, 0, sl
    for j in range(e, min(e + hold, len(b))):
        h, l = b[j][2], b[j][3]
        if (h >= stop) if short else (l <= stop):
            gross += rem * ((en - stop) if short else (stop - en)) / risk; return dict(R=gross - cost, bars=j - e)
        while k < len(tg) and ((l <= tg[k]) if short else (h >= tg[k])):
            part = fr[k] if k < len(tg) - 1 else rem
            gross += part * rr[k]; rem -= part; k += 1
            if rem <= 1e-9: return dict(R=gross - cost, bars=j - e)
        mfe = ((en - l) if short else (h - en)) / risk
        if k >= 1 or mfe >= be_r: stop = en
    if e + hold > len(b): return None                     # не завершена
    px = b[min(e + hold, len(b)) - 1][4]
    gross += rem * ((en - px) if short else (px - en)) / risk
    return dict(R=gross - cost, bars=hold - 1)


def progon(K, B):
    rng = np.random.default_rng(31); real = {w: [] for w in S.OKNA}; po = {w: {} for w in S.OKNA}
    ctrl = {w: [[] for _ in range(RAZ)] for w in S.OKNA}; t0 = time.time()
    for sym, b in B.items():
        s = K(); st = Store(sym); pv = sym if pervyy_argument(K) == "symbol" else st
        vid = S.Vid(b); st.rows = vid; ts = np.array([r[0] for r in b], dtype=np.int64); block = -1
        for i in range(200, len(b) - 1):
            vid.n = i + 1; x = b[i]
            try: g = s.maybe_signal(pv, *x)
            except Exception: continue
            w = S.okno(x[0])
            if g is None or w is None or i <= block or getattr(g, "side", None) not in ("long", "short"): continue
            en = b[i + 1][1]; short = g.side == "short"; risk = (g.sl - en) if short else (en - g.sl)
            if risk <= 0: continue
            sp = risk / en; tps = list(g.tps or [g.tp]); fr = list(g.tp_fracs or [1.0])
            rr = [((en - t) if short else (t - en)) / risk for t in tps]
            if any(x_ <= 0 for x_ in rr): continue
            be = float(getattr(g, "be_trigger_rr", 0) or 1e9)
            r = sim(b, i, short, sp, rr, fr, be)
            if r is None: continue
            block = i + r["bars"] + 1; real[w].append(r["R"]); po[w].setdefault(sym, []).append(r["R"])
            a_, z_ = S.OKNA[w]; pool = np.flatnonzero((ts >= a_) & (ts < z_)); pool = pool[pool < len(b) - HOLD - 2]
            for d in range(RAZ):
                c = sim(b, int(rng.choice(pool)), short, sp, rr, fr, be) if len(pool) > 5 else None
                if c is not None: ctrl[w][d].append(c["R"])
    out = {"sek": round(time.time() - t0)}
    for w in S.OKNA:
        R = np.array(real[w]); cm = np.array([np.mean(c) for c in ctrl[w] if len(c) > 20])
        o = {"n": int(len(R))}
        if len(R) > 2 and len(cm) >= 5:
            ed = float(R.mean() - cm.mean()); se = math.sqrt(R.std(ddof=1) ** 2 / len(R) + cm.var(ddof=1))
            o.update(sredniy=float(R.mean()), kontrol=float(cm.mean()), edzh=ed, sigma=ed / se if se > 0 else 0.0,
                     vinreyt=float((R > 0).mean()), monet_v_pluse=sum(np.mean(v) > 0 for v in po[w].values()), monet=len(po[w]))
        out[w] = o
    out["DEV_PASS"] = all(isinstance(out[w], dict) and out[w].get("n", 0) >= 50 and out[w].get("edzh", -1) > 0 and
                          out[w].get("sigma", 0) >= PROG and out[w]["monet_v_pluse"] * 2 >= out[w]["monet"] for w in S.OKNA)
    return out


if __name__ == "__main__":
    mod = sys.argv[1]; B = S.bary()
    r = progon(S.klass(mod), B); r["strategiya"] = mod
    Path(f"inplay_rodnaya_{mod}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    print(json.dumps(r, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
