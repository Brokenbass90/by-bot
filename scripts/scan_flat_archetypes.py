#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.engine import Candle, KlineStore
from backtest.run_portfolio import _flat_side_scores, _flat_side_scores_at_bar


def _classify_flat_family(meta: dict) -> tuple[str, str]:
    close_vs_ema = float(meta.get("close_vs_ema_pct", 0.0) or 0.0)
    dist_from_support = float(meta.get("dist_from_support_pct", 0.0) or 0.0)
    dist_from_res = float(meta.get("dist_from_res_pct", 0.0) or 0.0)
    range_pct = float(meta.get("range_pct", 0.0) or 0.0)
    signed_slope = float(meta.get("signed_slope_4h_pct", 0.0) or 0.0)
    flat_score = float(meta.get("flat_score", 0.0) or 0.0)
    long_score = float(meta.get("long_score", 0.0) or 0.0)
    short_score = float(meta.get("short_score", 0.0) or 0.0)

    long_family = "none"
    short_family = "none"

    if long_score >= 0.20 and flat_score >= 0.40:
        if signed_slope >= 0.18 and -2.4 <= close_vs_ema <= -0.4 and dist_from_support <= 1.4:
            long_family = "rising_channel_long_reclaim"
        elif signed_slope >= -0.10 and close_vs_ema <= -1.0 and dist_from_support <= 1.0:
            long_family = "depressed_long_reclaim"

    if short_score >= 0.05 and flat_score >= 0.35:
        if signed_slope <= -0.18 and -0.2 <= close_vs_ema <= 2.6 and dist_from_res <= 1.2:
            short_family = "slope_short_fade"
        elif abs(signed_slope) <= 0.18 and dist_from_res <= 1.0 and 4.0 <= range_pct <= 16.0:
            short_family = "horizontal_short_fade"

    return long_family, short_family


def _load_best_store(cache_dir: Path, symbol: str) -> KlineStore | None:
    best = None
    for path in cache_dir.glob(f"{symbol}_5_*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not raw:
            continue

        def _ts(item) -> int:
            if isinstance(item, dict):
                return int(float(item.get("ts", 0)))
            return int(float(item[0]))

        first_ts = _ts(raw[0])
        last_ts = _ts(raw[-1])
        key = (max(0, last_ts - first_ts), len(raw), path.stat().st_mtime)
        if best is None or key > best[0]:
            best = (key, path, raw)
    if best is None:
        return None

    _, _, raw = best
    candles = []
    for row in raw:
        if isinstance(row, dict):
            candles.append(
                Candle(
                    ts=int(float(row["ts"])),
                    o=float(row["o"]),
                    h=float(row["h"]),
                    l=float(row["l"]),
                    c=float(row["c"]),
                    v=float(row.get("v", 0.0)),
                )
            )
        elif isinstance(row, (list, tuple)) and len(row) >= 5:
            candles.append(
                Candle(
                    ts=int(float(row[0])),
                    o=float(row[1]),
                    h=float(row[2]),
                    l=float(row[3]),
                    c=float(row[4]),
                    v=float(row[5]) if len(row) > 5 else 0.0,
                )
            )
    if not candles:
        return None
    return KlineStore(symbol, candles)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", required=True, help="Comma-separated symbols")
    ap.add_argument("--cache", default="data_cache")
    ap.add_argument("--sample-step-bars", type=int, default=48, help="Sampling step in 5m bars for historical top-count scan")
    ap.add_argument("--warmup-bars", type=int, default=48 * 80, help="Warmup before counting top candidates")
    ap.add_argument("--long-top-n", type=int, default=4)
    ap.add_argument("--short-top-n", type=int, default=3)
    ap.add_argument("--long-min-score", type=float, default=0.20)
    ap.add_argument("--short-min-score", type=float, default=0.03)
    ap.add_argument("--out-csv", default="")
    args = ap.parse_args()

    cache_dir = Path(args.cache)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    stores = {}
    min_len = None
    for sym in symbols:
        store = _load_best_store(cache_dir, sym)
        if store is None:
            continue
        stores[sym] = store
        min_len = len(store.c5) if min_len is None else min(min_len, len(store.c5))

    if not stores or min_len is None:
        raise SystemExit("No stores loaded")

    long_ct = Counter()
    short_ct = Counter()
    current_rows = []
    for sym, store in stores.items():
        store.set_index(len(store.c5) - 1)
        meta = _flat_side_scores(store)
        current_rows.append(
            {
                "symbol": sym,
                "long_score": meta.get("long_score", 0.0),
                "short_score": meta.get("short_score", 0.0),
                "flat_score": meta.get("flat_score", 0.0),
                "close_vs_ema_pct": meta.get("close_vs_ema_pct", 0.0),
                "rsi_1h": meta.get("rsi_1h", 0.0),
                "range_pct": meta.get("range_pct", 0.0),
                "signed_slope_4h_pct": meta.get("signed_slope_4h_pct", 0.0),
            }
        )

    for i5 in range(args.warmup_bars, min_len, args.sample_step_bars):
        metas = {sym: _flat_side_scores_at_bar(store, i5) for sym, store in stores.items()}
        long_rank = sorted(stores, key=lambda s: metas[s].get("long_score", 0.0), reverse=True)[: max(1, args.long_top_n)]
        short_rank = sorted(stores, key=lambda s: metas[s].get("short_score", 0.0), reverse=True)[: max(1, args.short_top_n)]
        for sym in long_rank:
            if metas[sym].get("long_score", 0.0) >= args.long_min_score:
                long_ct[sym] += 1
        for sym in short_rank:
            if metas[sym].get("short_score", 0.0) >= args.short_min_score:
                short_ct[sym] += 1

    print("Current ranking:")
    for row in sorted(current_rows, key=lambda r: (r["long_score"], r["short_score"]), reverse=True):
        long_family, short_family = _classify_flat_family(row)
        print(
            f"{row['symbol']}: long={row['long_score']:.3f} short={row['short_score']:.3f} "
            f"flat={row['flat_score']:.3f} close_vs_ema={row['close_vs_ema_pct']:.3f} "
            f"slope4h={row['signed_slope_4h_pct']:.3f} rsi={row['rsi_1h']:.1f} "
            f"families={long_family}/{short_family}"
        )

    print("\nHistorical long top-counts:")
    for sym, n in long_ct.most_common():
        print(f"{sym},{n}")

    print("\nHistorical short top-counts:")
    for sym, n in short_ct.most_common():
        print(f"{sym},{n}")

    if args.out_csv:
        out = Path(args.out_csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["symbol", "current_long_score", "current_short_score", "current_flat_score", "current_close_vs_ema_pct", "current_signed_slope_4h_pct", "current_rsi_1h", "current_long_family", "current_short_family", "hist_long_top_count", "hist_short_top_count"])
            by_sym = {row["symbol"]: row for row in current_rows}
            for sym in symbols:
                row = by_sym.get(sym, {})
                long_family, short_family = _classify_flat_family(row)
                w.writerow([
                    sym,
                    row.get("long_score", 0.0),
                    row.get("short_score", 0.0),
                    row.get("flat_score", 0.0),
                    row.get("close_vs_ema_pct", 0.0),
                    row.get("signed_slope_4h_pct", 0.0),
                    row.get("rsi_1h", 0.0),
                    long_family,
                    short_family,
                    long_ct.get(sym, 0),
                    short_ct.get(sym, 0),
                ])
        print(f"\nSaved CSV to: {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
