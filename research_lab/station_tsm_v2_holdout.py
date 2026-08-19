"""HOLDOUT-станция TSM: финальный вердикт на НЕВИДАННЫХ данных (prereg 2026-07-20).

Данные: research_lab/data/daily_{sym}.json (fetch_daily_history.py на Mac),
берём ТОЛЬКО бары ДО 2023-07-05 (начало видимого нами кэша) = чистый holdout:
2020-2023, включает бык-2021, медведь-2022, восстановление-2023.

ФИНАЛИСТЫ (заморожены ДО взгляда на holdout, менять нельзя):
  F1: tsm L=4  long_short   F2: tsm L=4  long_only
  F3: tsm L=5  long_short   F4: ens(4/8/12) long_short
  (vt=None; издержки/фандинг как всюду: 6+2bps/сторона, 3bps/день)

ГЕЙТ PASS (заморожен): (a) pooled net >= +10R; (b) BTC>0 И ETH>0 отдельно;
(c) ни один календарный год хуже -15R; (d) >=2 календарных лет в плюсе.
Иначе FAIL навсегда (без подгонки). PASS -> shadow-спека для сервера.
"""
from __future__ import annotations
import json, os, sys, datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for p in (ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from station_tsm_v1 import _sig, CAPITAL, R_UNIT
from level_dca_v1 import FEE_SIDE, FUNDING_PER_DAY

CUTOFF_MS = 1688515200000  # 2023-07-05 UTC — начало видимых нами данных
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT"]
FINALISTS = [
    {"kind": "tsm", "L": 4, "mode": "long_short", "vol_target": None},
    {"kind": "tsm", "L": 4, "mode": "long_only", "vol_target": None},
    {"kind": "tsm", "L": 5, "mode": "long_short", "vol_target": None},
    {"kind": "ens", "mode": "long_short", "vol_target": None},
]


def load_holdout(sym):
    path = os.path.join(_HERE, "data", f"daily_{sym}.json")
    if not os.path.exists(path):
        return None
    rows = json.load(open(path))
    return [r for r in rows if r[0] < CUTOFF_MS]


def backtest_daily(d, p):
    closes = [b[4] for b in d]
    trades = []
    pos = 0; entry = None; entry_ts = None; days_in = 0
    warm = p.get("L", 12) * 7 + 14
    for i in range(warm, len(d) - 1, 7):
        want = _sig(closes, i, p)
        if p["mode"] == "long_only" and want < 0:
            want = 0
        if want != pos:
            nxt = d[i + 1][1]
            if pos != 0 and entry:
                gross = (nxt / entry - 1.0) * CAPITAL * pos
                pnl = gross - CAPITAL * FEE_SIDE - CAPITAL * FUNDING_PER_DAY * days_in
                trades.append({"entry_ts": entry_ts, "exit_ts": d[i + 1][0], "r": pnl / R_UNIT})
            if want != 0:
                entry = nxt; entry_ts = d[i + 1][0]; days_in = 0
            pos = want
        if pos != 0:
            days_in += 7
    if pos != 0 and entry:
        pnl = (closes[-1] / entry - 1.0) * CAPITAL * pos - CAPITAL * FEE_SIDE \
              - CAPITAL * FUNDING_PER_DAY * days_in
        trades.append({"entry_ts": entry_ts, "exit_ts": d[-1][0], "r": pnl / R_UNIT})
    return trades


def year(ts):
    return datetime.datetime.utcfromtimestamp(ts / 1000).year


if __name__ == "__main__":
    out_path = os.path.join(_HERE, "results", "tsm_v2_holdout.json")
    verdicts = []
    for p in FINALISTS:
        per_sym = {}
        all_tr = []
        for sym in SYMBOLS:
            d = load_holdout(sym)
            if not d or len(d) < 200:
                continue
            tr = backtest_daily(d, p)
            per_sym[sym] = round(sum(t["r"] for t in tr), 2)
            all_tr += tr
        if not all_tr:
            print("НЕТ ДАННЫХ: сначала python3 research_lab/fetch_daily_history.py")
            sys.exit(1)
        pooled = round(sum(t["r"] for t in all_tr), 2)
        by_year = {}
        for t in all_tr:
            by_year[year(t["exit_ts"])] = round(by_year.get(year(t["exit_ts"]), 0.0) + t["r"], 2)
        ga = pooled >= 10.0
        gb = per_sym.get("BTCUSDT", -1) > 0 and per_sym.get("ETHUSDT", -1) > 0
        gc = all(v >= -15.0 for v in by_year.values())
        gd = sum(1 for v in by_year.values() if v > 0) >= 2
        verdict = "PASS" if (ga and gb and gc and gd) else "FAIL"
        rec = {"params": p, "pooled_r": pooled, "n": len(all_tr),
               "per_sym": per_sym, "by_year": by_year,
               "gates": {"pooled>=10": ga, "btc&eth>0": gb,
                         "year>=-15": gc, ">=2y_plus": gd},
               "verdict": verdict}
        verdicts.append(rec)
        tag = f"{p['kind']}{p.get('L','')} {p['mode']}"
        print(f"{tag:22} pooled={pooled:>7}R n={len(all_tr)} годы={by_year} -> {verdict}")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(verdicts, open(out_path, "w"), indent=1)
    print(f"-> {out_path}")
