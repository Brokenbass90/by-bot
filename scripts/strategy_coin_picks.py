#!/usr/bin/env python3
"""Show the automatic per-strategy coin selection in action.

The bot ALREADY scores coins per strategy by current price state
(scripts/strategy_scorer.score_for_strategy: ASB1 wants coins near N-day low +
depressed RSI + ranging; ARF1 near highs; BREAKDOWN at/below lows; etc.). This
report runs that scorer across every cached symbol and ranks the top picks per
strategy — so you can SEE which coins each strategy would choose right now,
instead of wondering why a backtest only showed one symbol.

Additive / read-only. Uses the existing scorer (no new scoring logic). Run:
    PYTHONPATH=. python scripts/strategy_coin_picks.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data_cache"

from scripts.strategy_scorer import score_for_strategy

STRATS = {
    "ASB1": "ASB1_SYMBOL_ALLOWLIST",
    "ARF1": "ARF1_SYMBOL_ALLOWLIST",
    "BREAKDOWN": "BREAKDOWN_SYMBOL_ALLOWLIST",
    "ASC1": "ASC1_SYMBOL_ALLOWLIST",
    "BREAKOUT": "BREAKOUT_SYMBOL_ALLOWLIST",
    "ETS2": "ETS2_SYMBOL_ALLOWLIST",
}


def _load_1h(symbol: str):
    rows = {}
    for f in glob.glob(str(CACHE / f"{symbol}_60_*.json")):
        try:
            data = json.loads(Path(f).read_text())
        except Exception:
            continue
        seq = data if isinstance(data, list) else data.get("data") or []
        for r in seq:
            if isinstance(r, dict):
                rows[int(r.get("ts", 0))] = (float(r["h"]), float(r["l"]), float(r["c"]))
            else:
                rows[int(float(r[0]))] = (float(r[2]), float(r[3]), float(r[4]))
    ts = sorted(rows)
    highs = [rows[t][0] for t in ts]
    lows = [rows[t][1] for t in ts]
    closes = [rows[t][2] for t in ts]
    return closes, highs, lows


def main(top_n: int = 8, min_bars: int = 120, output_json: str = ""):
    symbols = sorted({Path(f).name.split("_60_")[0] for f in glob.glob(str(CACHE / "*_60_*.json"))})
    data = {}
    for s in symbols:
        c, h, l = _load_1h(s)
        if len(c) >= min_bars:
            data[s] = (c, h, l)
    print(f"=== per-strategy coin picks (current state, {len(data)} symbols with 1h data) ===")
    out = {}
    for strat, env_key in STRATS.items():
        scored = []
        for s, (c, h, l) in data.items():
            try:
                fit = score_for_strategy(env_key, c, h, l)
            except Exception:
                fit = None
            if isinstance(fit, (int, float)):
                scored.append((s, round(float(fit), 3)))
        scored.sort(key=lambda kv: kv[1], reverse=True)
        top = scored[:top_n]
        out[strat] = top
        picks = ", ".join(f"{s}:{f}" for s, f in top)
        print(f"  {strat:<10} -> {picks}")
    payload = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "top_n": int(top_n),
        "min_bars": int(min_bars),
        "symbols_scored": len(data),
        "picks": out,
    }
    # Backward-compatible shape for auto_pick_wf: keep latest as strategy -> list.
    path = Path(output_json) if output_json else ROOT / "reports" / "STRATEGY_COIN_PICKS_latest.json"
    (ROOT / "reports").mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    (ROOT / "reports" / "STRATEGY_COIN_PICKS_meta_latest.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("\nwrote reports/STRATEGY_COIN_PICKS_latest.json")
    print("wrote reports/STRATEGY_COIN_PICKS_meta_latest.json")
    print("note: fit 0-1 = how well a coin's CURRENT price state matches the strategy. "
          "This is the same scorer the live router/allowlist pipeline uses.")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rank current coin fit by strategy family")
    parser.add_argument("--top-n", type=int, default=8)
    parser.add_argument("--min-bars", type=int, default=120)
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()
    main(top_n=args.top_n, min_bars=args.min_bars, output_json=args.output_json)
