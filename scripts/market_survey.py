#!/usr/bin/env python3
"""Market-wide opportunity survey — find WHERE conditions favor which edge, instead
of forcing one strategy onto everything and collecting negatives.

For each symbol's latest cached candles it reports current regime, volatility,
and level-structure quality, then tags the best-fit edge type:
  - flat + clean levels      -> RANGE/BOUNCE candidate
  - trending + valid sloped   -> TRENDLINE-TOUCH candidate
  - high volatility           -> caution (wide stops / pump-fade only)
This is data analysis (AI's right role), not prediction. Read-only on cache.

Usage: python3 scripts/market_survey.py --tf 60 --bars 300 --out reports/market_survey.csv
"""
from __future__ import annotations
import argparse, csv, glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot import market_context as mc


def latest_cache(symbol, tf):
    files = sorted(glob.glob(f"data_cache/{symbol}_{tf}_*.json"))
    return files[-1] if files else None


def load(path):
    raw = json.load(open(path))
    return [[r['ts'], r['o'], r['h'], r['l'], r['c'], r['v']] for r in raw]


def survey_symbol(rows):
    atr = mc.atr(rows, 14, exclude_last=True)
    price = rows[-1][4]
    if not (atr == atr and atr > 0 and price > 0):
        return None
    atr_pct = atr / price * 100.0
    ch = mc.classify_channel(rows, atr_value=atr)
    regime = ch.get("regime", "unknown")
    width_atr = ch.get("width_atr")
    res = mc.horizontal_levels(rows, side="resistance", atr_value=atr, tol_atr=0.4, min_touches=2)
    sup = mc.horizontal_levels(rows, side="support", atr_value=atr, tol_atr=0.4, min_touches=2)
    strong = len([c for c in res + sup if c["touches"] >= 3])
    sr = mc.sloped_level(rows, side="resistance", min_pivots=3, require_unbroken=True)
    ss = mc.sloped_level(rows, side="support", min_pivots=3, require_unbroken=True)
    valid_sloped = int(bool(sr)) + int(bool(ss))

    # best-fit edge tag
    if atr_pct >= 6.0:
        tag = "HIGH_VOL (pump-fade/caution)"
    elif regime == "flat" and strong >= 2:
        tag = "RANGE/BOUNCE"
    elif regime in ("ascending", "descending") and valid_sloped >= 1:
        tag = "TRENDLINE-TOUCH"
    elif strong >= 2:
        tag = "LEVELS (mixed)"
    else:
        tag = "no-clean-structure"
    # structure score (higher = cleaner tradeable structure)
    score = strong * 2 + valid_sloped * 2 - (2 if atr_pct >= 6 else 0)
    return {"regime": regime, "atr_pct": round(atr_pct, 2),
            "width_atr": width_atr, "strong_levels": strong,
            "valid_sloped": valid_sloped, "tag": tag, "score": score}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="60")
    ap.add_argument("--bars", type=int, default=300)
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--out", default="reports/market_survey.csv")
    a = ap.parse_args()

    syms = sorted({os.path.basename(f).split("_")[0]
                   for f in glob.glob(f"data_cache/*_{a.tf}_*.json")})[:a.limit]
    rows_out = []
    for sym in syms:
        f = latest_cache(sym, a.tf)
        if not f:
            continue
        try:
            data = load(f)[-a.bars:]
            if len(data) < 50:
                continue
            r = survey_symbol(data)
            if r:
                r["symbol"] = sym
                rows_out.append(r)
        except Exception:
            continue

    rows_out.sort(key=lambda x: x["score"], reverse=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["symbol", "tag", "regime", "atr_pct",
                                           "strong_levels", "valid_sloped", "width_atr", "score"])
        w.writeheader(); w.writerows(rows_out)

    from collections import Counter
    print(f"surveyed {len(rows_out)} symbols (tf={a.tf})")
    print("by edge-type:", dict(Counter(r["tag"] for r in rows_out)))
    print("\nTOP structure (where conditions are cleanest):")
    for r in rows_out[:15]:
        print(f"  {r['symbol']:14s} {r['tag']:28s} regime={r['regime']:10s} "
              f"atr%={r['atr_pct']:5.2f} strong_lvls={r['strong_levels']} sloped={r['valid_sloped']}")


if __name__ == "__main__":
    main()
