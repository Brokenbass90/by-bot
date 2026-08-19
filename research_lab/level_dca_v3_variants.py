"""RESEARCH-ONLY: финальные варианты сетки по уточнению владельца (2026-07-20).

A) MIDTERM_BTCETH: усреднение ТОЛЬКО BTC/ETH (супер-ликвидные), 5 колен, rescue,
   ПО ТРЕНДУ (EMA200 1h + наклон: long только в аптренде, short в даунтренде).
B) INTRADAY_FLAT: гибкая сетка на ликвидных альтах ВНУТРИДЕНЬ: 5m сим, уровни 1h,
   4 колена, rescue, флет-гейт ER(24h), цели 1.2-2.4%, hold<=3д.

Это ПОСЛЕДНИЙ тест семейства усреднения на крипте: FAIL здесь = семейство закрыто.
"""
from __future__ import annotations
import json, os, sys, time

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for p in (ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from level_dca_v1 import load_5m, to_1h
from level_dca_v2_midterm import simulate_mid

JOBS = []
# A) midterm BTC/ETH, тренд-гейт
for sym in ("BTCUSDT", "ETHUSDT"):
    for side in ("long", "short"):
        for tp in (0.05, 0.03):
            JOBS.append({"job": "midterm_btceth", "sym": sym, "tf": "1h",
                         "params": {"side": side, "trend_gate": "with", "tranches": 5,
                                    "min_tp_pct": tp, "max_tp_pct": tp * 2}})
# B) intraday flat alts
ALTS = ["SOLUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT", "XRPUSDT",
        "DOGEUSDT", "DOTUSDT", "LTCUSDT", "ATOMUSDT"]
for sym in ALTS:
    for side in ("long", "short"):
        JOBS.append({"job": "intraday_flat", "sym": sym, "tf": "5m",
                     "params": {"side": side, "tranches": 4, "er_gate": 0.20, "er_n": 288,
                                "level_agg": 12, "refit_bars": 288,
                                "min_tp_pct": 0.012, "max_tp_pct": 0.024,
                                "max_hold_days": 3, "level_gap_atr": 1.0}})


def run(run_id="level_dca_v3_variants"):
    path = os.path.join(_HERE, "results", f"{run_id}.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    done = set()
    if os.path.exists(path):
        for line in open(path):
            try:
                r = json.loads(line)
                done.add((r["job"], r["sym"], json.dumps(r["params"], sort_keys=True)))
            except Exception:
                pass
    t0 = time.time()
    cache = {}
    for j in JOBS:
        key = (j["job"], j["sym"], json.dumps(j["params"], sort_keys=True))
        if key in done:
            continue
        if j["sym"] not in cache:
            b5 = load_5m(j["sym"])
            cache[j["sym"]] = (b5, to_1h(b5) if b5 else None)
        b5, h1 = cache[j["sym"]]
        if not b5:
            continue
        bars = h1 if j["tf"] == "1h" else b5
        p = dict(j["params"])
        m = simulate_mid(bars, **p)
        rec = {"job": j["job"], "sym": j["sym"], "params": j["params"], **m}
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"{j['job']} {j['sym']} {p['side']}: net={m['net']} cyc={m['cycles']} "
              f"wr={m['wr']} worst={m['worst']} resc={m['rescues']}", flush=True)
        if time.time() - t0 > 38:
            print("CHUNK_TIMEOUT")
            return False
    print("ALL_DONE")
    return True


if __name__ == "__main__":
    run()
