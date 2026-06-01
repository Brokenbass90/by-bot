#!/usr/bin/env python3
"""Validate public cross-exchange funding opportunities.

Research-only. This script reads the snapshot produced by
`cross_exchange_funding_scan.py`, checks order-book depth for both legs, applies
rough taker-fee/slippage costs, and writes a filtered candidate list for the AI
context. It never reads private keys and never places orders.
"""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _f(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def _get_json(url: str, timeout: float = 15.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "by-bot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


@dataclass
class Book:
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]


def _pairs(rows: Any) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for row in rows or []:
        try:
            price = float(row[0])
            qty = float(row[1])
        except Exception:
            continue
        if price > 0 and qty > 0:
            out.append((price, qty))
    return out


def fetch_orderbook(exchange: str, symbol: str, *, limit: int = 100) -> Book:
    exchange = exchange.lower()
    symbol = symbol.upper()
    if exchange == "binance":
        qs = urllib.parse.urlencode({"symbol": symbol, "limit": min(max(limit, 5), 1000)})
        data = _get_json(f"https://fapi.binance.com/fapi/v1/depth?{qs}")
        return Book(bids=_pairs(data.get("bids")), asks=_pairs(data.get("asks")))
    if exchange == "bybit":
        qs = urllib.parse.urlencode({"category": "linear", "symbol": symbol, "limit": min(max(limit, 1), 200)})
        data = _get_json(f"https://api.bybit.com/v5/market/orderbook?{qs}")
        result = data.get("result") or {}
        return Book(bids=_pairs(result.get("b")), asks=_pairs(result.get("a")))
    if exchange == "bitget":
        qs = urllib.parse.urlencode({"symbol": symbol, "productType": "USDT-FUTURES", "limit": min(max(limit, 5), 100)})
        data = _get_json(f"https://api.bitget.com/api/v2/mix/market/orderbook?{qs}")
        result = data.get("data") or {}
        return Book(bids=_pairs(result.get("bids")), asks=_pairs(result.get("asks")))
    raise ValueError(f"unsupported exchange: {exchange}")


def _walk_book(levels: list[tuple[float, float]], notional_usd: float) -> tuple[bool, float, float, float]:
    """Return (filled, avg_price, filled_notional, best_price)."""
    if not levels or notional_usd <= 0:
        return False, 0.0, 0.0, 0.0
    best = levels[0][0]
    remaining = notional_usd
    qty_total = 0.0
    paid_total = 0.0
    for price, qty in levels:
        level_notional = price * qty
        take_notional = min(remaining, level_notional)
        take_qty = take_notional / price
        qty_total += take_qty
        paid_total += take_notional
        remaining -= take_notional
        if remaining <= 1e-9:
            break
    if paid_total <= 0 or qty_total <= 0:
        return False, 0.0, paid_total, best
    return remaining <= max(1e-6, notional_usd * 0.001), paid_total / qty_total, paid_total, best


def _entry_leg(book: Book, side: str, notional_usd: float) -> dict[str, Any]:
    if side == "long":
        filled, avg, filled_notional, best = _walk_book(book.asks, notional_usd)
        slip_bps = ((avg / best) - 1.0) * 10_000.0 if best > 0 and avg > 0 else 9999.0
    elif side == "short":
        filled, avg, filled_notional, best = _walk_book(book.bids, notional_usd)
        slip_bps = ((best / avg) - 1.0) * 10_000.0 if best > 0 and avg > 0 else 9999.0
    else:
        raise ValueError(f"bad side: {side}")
    return {
        "filled": bool(filled),
        "best_price": round(best, 8),
        "avg_price": round(avg, 8),
        "filled_notional_usd": round(filled_notional, 4),
        "slippage_bps": round(max(0.0, slip_bps), 4),
    }


def _load_history(path: Path, *, window_min: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    cutoff = time.time() - max(1, window_min) * 60
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[-2000:]:
        try:
            row = json.loads(line)
        except Exception:
            continue
        if _f(row.get("ts_epoch")) >= cutoff:
            rows.append(row)
    return rows


def _persist_count(history: list[dict[str, Any]], key: str, min_apr: float) -> int:
    count = 0
    for row in history:
        if row.get("pair_key") == key and _f(row.get("spread_apr_pct")) >= min_apr:
            count += 1
    return count


def validate(args: argparse.Namespace) -> dict[str, Any]:
    in_path = ROOT / args.in_json
    data = json.loads(in_path.read_text(encoding="utf-8"))
    opportunities = data.get("opportunities") or []
    history_path = ROOT / args.history_jsonl
    history = _load_history(history_path, window_min=args.persistence_window_min)

    validated: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    for row in opportunities[: max(1, args.top)]:
        symbol = str(row.get("symbol") or "").upper()
        long_ex = str(row.get("long_exchange") or "").lower()
        short_ex = str(row.get("short_exchange") or "").lower()
        if not symbol or not long_ex or not short_ex:
            continue
        pair_key = f"{symbol}:{long_ex}->{short_ex}"
        spread_apr = _f(row.get("spread_apr_pct"))
        spread_hold_pct = spread_apr * (float(args.hold_hours) / 24.0) / 365.0
        try:
            long_book = fetch_orderbook(long_ex, symbol, limit=args.book_limit)
            short_book = fetch_orderbook(short_ex, symbol, limit=args.book_limit)
            long_leg = _entry_leg(long_book, "long", args.notional_usd)
            short_leg = _entry_leg(short_book, "short", args.notional_usd)
            error = ""
        except Exception as exc:
            long_leg = {"filled": False, "slippage_bps": 9999.0}
            short_leg = {"filled": False, "slippage_bps": 9999.0}
            error = f"{type(exc).__name__}: {exc}"

        entry_cost_bps = _f(long_leg.get("slippage_bps")) + _f(short_leg.get("slippage_bps")) + 2.0 * args.taker_fee_bps
        roundtrip_cost_pct = (entry_cost_bps * 2.0) / 100.0
        net_hold_pct = spread_hold_pct - roundtrip_cost_pct
        persistence_count = _persist_count(history, pair_key, args.min_spread_apr_pct)
        passed = (
            not error
            and bool(long_leg.get("filled"))
            and bool(short_leg.get("filled"))
            and _f(long_leg.get("slippage_bps")) <= args.max_slippage_bps
            and _f(short_leg.get("slippage_bps")) <= args.max_slippage_bps
            and spread_apr >= args.min_spread_apr_pct
            and net_hold_pct > 0
            and (persistence_count + 1) >= args.min_persistence_count
        )

        item = {
            "pair_key": pair_key,
            "symbol": symbol,
            "long_exchange": long_ex,
            "short_exchange": short_ex,
            "spread_apr_pct": round(spread_apr, 4),
            "spread_monthly_pct": round(spread_apr / 12.0, 4),
            "hold_hours": float(args.hold_hours),
            "expected_funding_pct_for_hold": round(spread_hold_pct, 4),
            "estimated_roundtrip_cost_pct": round(roundtrip_cost_pct, 4),
            "estimated_net_pct_for_hold": round(net_hold_pct, 4),
            "notional_usd_per_leg": float(args.notional_usd),
            "long_leg": long_leg,
            "short_leg": short_leg,
            "persistence_count_in_window": persistence_count + 1,
            "persistence_window_min": int(args.persistence_window_min),
            "passed": bool(passed),
            "error": error,
            "note": "research_only; no private keys; no orders; verify margin/liquidation before live",
        }
        observations.append(
            {
                "ts_epoch": time.time(),
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "pair_key": pair_key,
                "spread_apr_pct": spread_apr,
                "passed_depth": bool(long_leg.get("filled")) and bool(short_leg.get("filled")),
                "net_hold_pct": net_hold_pct,
            }
        )
        if passed:
            validated.append(item)
        elif args.keep_failed:
            validated.append(item)

    validated.sort(key=lambda x: (_f(x.get("estimated_net_pct_for_hold")), _f(x.get("spread_apr_pct"))), reverse=True)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(Path(args.in_json)),
        "notional_usd_per_leg": float(args.notional_usd),
        "hold_hours": float(args.hold_hours),
        "taker_fee_bps": float(args.taker_fee_bps),
        "min_spread_apr_pct": float(args.min_spread_apr_pct),
        "max_slippage_bps": float(args.max_slippage_bps),
        "min_persistence_count": int(args.min_persistence_count),
        "persistence_window_min": int(args.persistence_window_min),
        "validated_count": sum(1 for x in validated if x.get("passed")),
        "items": validated[: max(1, args.out_top)],
    }

    out_path = ROOT / args.out_json
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    if observations:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with history_path.open("a", encoding="utf-8") as f:
            for obs in observations:
                f.write(json.dumps(obs, ensure_ascii=True) + "\n")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="Research-only orderbook/fee/persistence validator for cross-exchange funding.")
    ap.add_argument("--in-json", default="runtime/arb/cross_exchange_funding_latest.json")
    ap.add_argument("--out-json", default="runtime/arb/cross_exchange_funding_validated.json")
    ap.add_argument("--history-jsonl", default="runtime/arb/cross_exchange_funding_validate_history.jsonl")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--out-top", type=int, default=20)
    ap.add_argument("--notional-usd", type=float, default=100.0)
    ap.add_argument("--hold-hours", type=float, default=24.0)
    ap.add_argument("--taker-fee-bps", type=float, default=6.0)
    ap.add_argument("--max-slippage-bps", type=float, default=12.0)
    ap.add_argument("--min-spread-apr-pct", type=float, default=36.0)
    ap.add_argument("--min-persistence-count", type=int, default=2)
    ap.add_argument("--persistence-window-min", type=int, default=90)
    ap.add_argument("--book-limit", type=int, default=100)
    ap.add_argument("--keep-failed", action="store_true")
    args = ap.parse_args()

    payload = validate(args)
    print(
        f"validated={payload['validated_count']} items={len(payload.get('items') or [])} "
        f"notional=${payload['notional_usd_per_leg']:.0f}/leg hold={payload['hold_hours']:.0f}h"
    )
    for row in (payload.get("items") or [])[:10]:
        marker = "PASS" if row.get("passed") else "FAIL"
        print(
            f"{marker} {row.get('pair_key')} net_hold={row.get('estimated_net_pct_for_hold')}% "
            f"spread={row.get('spread_monthly_pct')}%/mo persist={row.get('persistence_count_in_window')}"
        )
    print(f"saved={ROOT / args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
