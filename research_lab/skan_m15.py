#!/usr/bin/env python3
"""PREREG_SKAN_M15_KORPUS_2026_10_20. python3 skan_m15.py [--etap 1|2]  (из корня копии репо)"""
import glob, importlib, inspect, json, math, os, statistics, sys, time
from pathlib import Path
import numpy as np
sys.path.insert(0, "."); sys.path.insert(0, "research_lab")
from research_machine import Store, simulate, pervyy_argument, MAX_LEV, ROZYGRYSHEY   # noqa
from random_control import sim_geo                                                    # noqa
MODULI = """alt_range_scalp_v1 breakdown_retest_v3 elder_crypto_v1 elder_triple_screen_v2 elder_triple_screen_v3 inplay_retest_v3
micro_scalper_breakout_v1 micro_scalper_v1 sloped_break_retest_v2 sloped_break_retest_v3 spike_fade_v3 scalper_classic_v1
alt_range_reclaim_v1 alt_resistance_fade_v2 alt_support_reclaim_v1 btc_cycle_continuation_v1 btc_cycle_level_target_v2
btc_eth_midterm_short_v1 btc_eth_midterm_short_v2 btc_regime_retest_v1 funding_rate_reversion_v1 grid_smart_v1
liquidation_cascade_entry_v1""".split()
OKNA = {"W1": (1709251200000, 1759276800000), "W2": (1672531200000, 1709251200000)}
SEAL = 1759276800000
STOP_MULT, HOLD, F1, OKNO_SKLADA, ZERNO = 4.0, 672, 0.55, 3000, 31
CHAST = int(sys.argv[sys.argv.index("--chast") + 1]) if "--chast" in sys.argv else -1
OUT = Path(f"skan_m15_rez_{CHAST}.json" if CHAST >= 0 else "skan_m15_rez.json")


def bary():
    B = {}
    for f in sorted(glob.glob("research_lab/data/m15/*.npz")):
        d = np.load(f); ts = d["ts"].astype(np.int64); a = d["ohlcv"].astype(float); m = ts < SEAL
        B[Path(f).stem] = [[int(ts[x]), *map(float, a[x])] for x in np.flatnonzero(m)]
    return B


def klass(mod):
    m = importlib.import_module(f"strategies.{mod}")
    k = [o for _, o in vars(m).items() if inspect.isclass(o) and hasattr(o, "maybe_signal") and o.__module__ == m.__name__]
    return k[0] if k else None


def okno(t):
    for w, (a, b) in OKNA.items():
        if a <= t < b: return w
    return None


def progon(K, B, budget):
    rng = np.random.default_rng(ZERNO); t0 = time.time()
    real = {w: [] for w in OKNA}; po = {w: {} for w in OKNA}; ctrl = {w: [[] for _ in range(ROZYGRYSHEY)] for w in OKNA}
    for sym, b in B.items():
        if time.time() - t0 > budget: return {"medlennaya": f">{budget} с", "simvolov_proshlo": sym}
        try: s = K()
        except Exception as e: return {"oshibka_sozdaniya": repr(e)[:200]}
        st = Store(sym); pv = sym if pervyy_argument(K) == "symbol" else st
        ts = np.array([r[0] for r in b], dtype=np.int64); block = -1
        for i in range(200, len(b) - 1):
            st.rows = b[max(0, i - OKNO_SKLADA + 1): i + 1]; x = b[i]
            try: g = s.maybe_signal(pv, x[0], x[1], x[2], x[3], x[4], x[5])
            except Exception: continue
            w = okno(x[0])
            if g is None or w is None or i <= block or getattr(g, "side", None) not in ("long", "short"): continue
            res = simulate(b, i, g.side, g.sl, list(g.tps or []), (g.tp_fracs or [F1])[0], STOP_MULT, HOLD)
            if res is None or res.get("lev", 0) > MAX_LEV: continue
            e = i + 1
            if not (e + HOLD <= len(b) or res["bars"] < len(b) - 1 - e): continue
            block = i + res["bars"] + 1
            real[w].append(res["R"]); po[w].setdefault(sym, []).append(res["R"])
            a_, b_ = OKNA[w]; pool = np.flatnonzero((ts >= a_) & (ts < b_)); pool = pool[pool < len(b) - HOLD - 2]
            if len(pool) < 5: continue
            e_ = b[e][1]; sl_w = e_ + (float(g.sl) - e_) * STOP_MULT; rw = abs(e_ - sl_w)
            if rw <= 0: continue
            tl = list(g.tps or []); k1 = abs(tl[0] - e_) / rw if tl else 1.2; k2 = abs(tl[1] - e_) / rw if len(tl) > 1 else 2.5
            for d in range(ROZYGRYSHEY):
                y = sim_geo(b, int(rng.choice(pool)), g.side == "short", 1.0 / res["lev"], k1, k2, (g.tp_fracs or [F1])[0], HOLD)
                if y is not None: ctrl[w][d].append(y)
    out = {"sek": round(time.time() - t0)}
    for w in OKNA:
        R = np.array(real[w], float); cm = np.array([np.mean(c) for c in ctrl[w] if len(c) > 20], float)
        r = {"n": int(len(R))}
        if len(R) >= 2 and len(cm) >= 5:
            edge = float(R.mean() - cm.mean()); se = math.sqrt(R.std(ddof=1) ** 2 / len(R) + cm.var(ddof=1))
            r.update(sredniy=float(R.mean()), kontrol=float(cm.mean()), edzh=edge, sigma=edge / se if se > 1e-12 else 0.0,
                     monet_v_pluse=sum(1 for v in po[w].values() if np.mean(v) > 0), monet=len(po[w]))
        out[w] = r
    return out


def main():
    rez = json.loads(OUT.read_text()) if OUT.exists() else {}
    B = bary(); print("символов", len(B), flush=True)
    for j, mod in enumerate(MODULI):
        if mod in rez or (CHAST >= 0 and j % 2 != CHAST): continue
        try: K = klass(mod)
        except Exception as e: rez[mod] = {"oshibka_importa": repr(e)[:200]}; OUT.write_text(json.dumps(rez, ensure_ascii=False, indent=1)); continue
        rez[mod] = progon(K, B, budget=3600) if K else {"net_klassa": True}
        OUT.write_text(json.dumps(rez, ensure_ascii=False, indent=1)); print(mod, json.dumps(rez[mod], ensure_ascii=False)[:300], flush=True)
    if CHAST >= 0: return
    # этапы по правилу prereg (запуск без --chast после обеих частей: сливает части)
    for c in (0, 1):
        p = Path(f"skan_m15_rez_{c}.json")
        if p.exists(): rez.update(json.loads(p.read_text()))
    vyzhili = [m for m, v in rez.items() if all(isinstance(v.get(w), dict) and v[w]["n"] >= 50 for w in OKNA)]
    k = len(vyzhili); porog = statistics.NormalDist().inv_cdf(1 - 0.05 / (2 * 2 * k)) if k else None
    itog = {"vyzhili_etap1": vyzhili, "porog_sigma": porog, "dev_pass": [m for m in vyzhili if all(
        rez[m][w].get("edzh", -1) > 0 and rez[m][w].get("sigma", 0) >= porog and rez[m][w]["monet_v_pluse"] * 2 >= rez[m][w]["monet"] for w in OKNA)]}
    Path("skan_m15_itog.json").write_text(json.dumps(itog, ensure_ascii=False, indent=1)); print("ИТОГ", json.dumps(itog, ensure_ascii=False))


if __name__ == "__main__":
    main()
