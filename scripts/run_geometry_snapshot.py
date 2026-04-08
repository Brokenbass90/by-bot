#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.geometry_cache import load_rows  # noqa: E402
from bot.chart_geometry import analyze_geometry  # noqa: E402

def main() -> int:
    ap = argparse.ArgumentParser(description="Build deterministic geometry snapshot from cached OHLCV.")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--interval", default="60", help="Cache interval: 5, 60, 240.")
    ap.add_argument("--bars", type=int, default=240)
    ap.add_argument("--json", action="store_true", help="Print JSON only.")
    args = ap.parse_args()

    symbol = str(args.symbol).strip().upper()
    interval = str(args.interval).strip()
    rows = load_rows(symbol, interval)
    if not rows:
        raise SystemExit(f"No cached rows for {symbol} interval={interval}")
    rows = rows[-max(20, int(args.bars)) :]
    snapshot = analyze_geometry(rows)
    if args.json:
        print(json.dumps(snapshot, indent=2, ensure_ascii=True))
        return 0

    print(f"symbol={symbol}")
    print(f"interval={interval}")
    print(f"rows={snapshot.get('rows')}")
    print(f"current_price={snapshot.get('current_price'):.6f}")
    print(f"atr={snapshot.get('atr'):.6f}")
    channel = dict(snapshot.get("channel") or {})
    compression = dict(snapshot.get("compression") or {})
    if channel:
        print(
            "channel="
            f"r2={channel.get('r2', 0.0):.3f} "
            f"width_pct={channel.get('width_pct', 0.0):.2f} "
            f"pos={channel.get('position', 0.0):.2f} "
            f"slope_pct_per_bar={channel.get('slope_pct_per_bar', 0.0):+.4f}"
        )
    if compression:
        print(
            "compression="
            f"ratio={compression.get('compression_ratio', 0.0):.3f} "
            f"is_compressed={int(bool(compression.get('is_compressed')))}"
        )
    nearest = dict(snapshot.get("nearest_levels") or {})
    print("nearest_below=" + json.dumps(nearest.get("below", []), ensure_ascii=True))
    print("nearest_above=" + json.dumps(nearest.get("above", []), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
