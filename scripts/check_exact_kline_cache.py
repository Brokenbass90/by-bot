#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = ROOT / ".cache" / "klines"


def _parse_symbols(raw: str) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for part in str(raw or "").replace(";", ",").split(","):
        sym = part.strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def _parse_date_utc(raw: str) -> int:
    dt = datetime.strptime(str(raw).strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _candidate_meta(path: Path) -> Dict[str, Any] | None:
    try:
        stem = path.stem
        _, _, start_ms, end_ms = stem.rsplit("_", 3)
        return {
            "path": str(path),
            "name": path.name,
            "start_ms": int(start_ms),
            "end_ms": int(end_ms),
        }
    except Exception:
        return None


def _best_nearby(cache_dir: Path, symbol: str, interval: str, start_ms: int, end_ms: int, top_n: int = 3) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in sorted(cache_dir.glob(f"{symbol}_{interval}_*.json")):
        meta = _candidate_meta(path)
        if not meta:
            continue
        overlap_ms = max(0, min(meta["end_ms"], end_ms) - max(meta["start_ms"], start_ms))
        span_ms = max(0, meta["end_ms"] - meta["start_ms"])
        meta["overlap_ms"] = overlap_ms
        meta["span_ms"] = span_ms
        out.append(meta)
    out.sort(key=lambda x: (x["overlap_ms"], x["span_ms"], x["end_ms"]), reverse=True)
    return out[:top_n]


def check_exact_cache(*, symbols: List[str], interval: str, start_ms: int, end_ms: int, cache_dir: Path) -> Dict[str, Any]:
    cache_dir = cache_dir.expanduser().resolve()
    results: List[Dict[str, Any]] = []
    missing = 0
    for symbol in symbols:
        exact_path = cache_dir / f"{symbol}_{interval}_{start_ms}_{end_ms}.json"
        exists = exact_path.exists()
        item: Dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "exact_path": str(exact_path),
            "exact_exists": exists,
        }
        if not exists:
            missing += 1
            item["nearby_candidates"] = _best_nearby(cache_dir, symbol, interval, start_ms, end_ms)
        results.append(item)
    return {
        "cache_dir": str(cache_dir),
        "interval": interval,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "symbols_total": len(symbols),
        "symbols_missing": missing,
        "all_exact_present": missing == 0,
        "results": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Check exact .cache/klines coverage for a backtest window.")
    ap.add_argument("--symbols", required=True, help="CSV symbol list.")
    ap.add_argument("--interval", default="5", help="Bybit interval, default 5.")
    ap.add_argument("--start-date", default="", help="UTC start date YYYY-MM-DD.")
    ap.add_argument("--end-date", default="", help="UTC end date YYYY-MM-DD.")
    ap.add_argument("--start-ms", type=int, default=0)
    ap.add_argument("--end-ms", type=int, default=0)
    ap.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    ap.add_argument("--strict", action="store_true", help="Exit non-zero if any exact slice is missing.")
    args = ap.parse_args()

    symbols = _parse_symbols(args.symbols)
    if not symbols:
        raise SystemExit("no symbols provided")

    start_ms = int(args.start_ms or (_parse_date_utc(args.start_date) if args.start_date else 0))
    end_ms = int(args.end_ms or (_parse_date_utc(args.end_date) if args.end_date else 0))
    if start_ms <= 0 or end_ms <= 0 or end_ms <= start_ms:
        raise SystemExit("invalid start/end window")

    report = check_exact_cache(
        symbols=symbols,
        interval=str(args.interval),
        start_ms=start_ms,
        end_ms=end_ms,
        cache_dir=Path(args.cache_dir),
    )
    print(json.dumps(report, indent=2))
    if args.strict and not bool(report.get("all_exact_present")):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
