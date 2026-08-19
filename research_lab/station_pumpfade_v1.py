"""РЕШАЮЩАЯ СТАНЦИЯ: pump/dump-fade на ПОЛНОМ movers-универсе (2026-07-21).

Контекст: на 37 монетах pumpfade — единственное плюсовое семейство; лучший вариант
(short, lb24, spike12%, rr1.5) дал IS +18.06R (гейт PASS) / fwd +1.57R / OOS-монеты
+13.09R — плюс на ВСЕХ ступенях. Теперь: 36 комбо × 100 монет (IS 60 старших / OOS 40
младших листингов). PASS-критерий тот же тройной гейт станции. Прогон ~сутки, resumable.

    nohup bash research_lab/run_station.sh pumpfade_v1 station_pumpfade_v1.py >/dev/null 2>&1 &
    tail -5 research_lab/results/pumpfade_v1.log
"""
from __future__ import annotations
import glob, hashlib, itertools, json, os, sys, time

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for p in (ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from station_movers_v1 import load, bt, DATA, RESULTS
from search_station import _gate
from pump_spike_fade import PumpSpikeFade


def universe(run_id, cap=100):
    upath = os.path.join(RESULTS, f"{run_id}_universe.json")
    if os.path.exists(upath):
        u = json.load(open(upath))
        return u["is"], u["oos"]
    syms = []
    for f in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        try:
            if os.path.getsize(f) < 1_500_000:
                continue
            rows = json.load(open(f))
            if len(rows) >= 20000:
                syms.append((int(rows[0][0]), os.path.basename(f)[:-5]))
        except Exception:
            pass
    syms.sort()
    syms = syms[:cap]
    cut = int(len(syms) * 0.6)
    IS = [s for _, s in syms[:cut]]
    OOS = [s for _, s in syms[cut:]]
    json.dump({"is": IS, "oos": OOS, "frozen_at": int(time.time())}, open(upath, "w"))
    print(f"универс: IS={len(IS)} OOS={len(OOS)} (из {len(syms)})")
    return IS, OOS


GRID = {
    "side": ["short", "long"],
    "lookback_bars": [12, 24, 48],
    "spike_pct": [0.10, 0.15, 0.22],
    "rr": [1.5, 2.2],
}


def run(run_id="pumpfade_v1"):
    IS, OOS = universe(run_id)
    path = os.path.join(RESULTS, f"{run_id}.jsonl")
    done = set()
    if os.path.exists(path):
        for line in open(path):
            try:
                done.add(json.loads(line)["key"])
            except Exception:
                pass
    print(f"[{run_id}] resume: {len(done)}")
    survivors = 0
    keys = list(GRID)
    for vals in itertools.product(*[GRID[k] for k in keys]):
        params = dict(zip(keys, vals))
        k = hashlib.sha1(("pf" + json.dumps(params, sort_keys=True)).encode()).hexdigest()[:12]
        if k in done:
            continue
        fac = lambda: PumpSpikeFade(**params)
        tr, by = bt(fac, IS, "first")
        ok, reason = _gate(tr, by)
        rec = {"key": k, "strategy": "pumpfade", "params": params, "is_pass": ok,
               "is_reason": reason, "is_net_r": round(sum(t["r"] for t in tr), 2),
               "is_n": len(tr), "ts": int(time.time())}
        if ok:
            tr2, by2 = bt(fac, IS, "second")
            ok2, r2 = _gate(tr2, by2)
            tr3, by3 = bt(fac, OOS, "all")
            ok3, r3 = _gate(tr3, by3)
            rec.update({"fwd_pass": ok2, "fwd_reason": r2,
                        "fwd_net_r": round(sum(t["r"] for t in tr2), 2),
                        "oos_pass": ok3, "oos_reason": r3,
                        "oos_net_r": round(sum(t["r"] for t in tr3), 2),
                        "survivor": bool(ok2 and ok3)})
            if rec["survivor"]:
                survivors += 1
                print(f"🟢 SURVIVOR {params}")
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"pf {params}: net={rec['is_net_r']}R n={rec['is_n']} [{reason}]", flush=True)
    print(f"[{run_id}] ГОТОВО: survivors={survivors}. Результаты: {path}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "pumpfade_v1")
