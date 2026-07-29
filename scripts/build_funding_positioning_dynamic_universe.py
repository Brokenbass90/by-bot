#!/usr/bin/env python3
"""Build a public, strategy-specific universe for funding positioning.

Selection is based only on information available at build time: Bybit
instrument status/age, 24h turnover, executable spread and funding-history
coverage. It deliberately does not use future strategy PnL or the current
funding signal direction. The output is research-only and cannot authorize
orders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://api.bybit.com"
DEFAULT_OUT = ROOT / "runtime" / "funding_positioning_dynamic_universe.json"
ANCHORS = (
    "ADAUSDT", "BTCUSDT", "DOTUSDT", "ETHUSDT",
    "LINKUSDT", "LTCUSDT", "SOLUSDT", "SUIUSDT",
)
ALLOWED_CRYPTO_SYMBOL_TYPES = {"", "innovation"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_json(path: str, params: dict[str, Any]) -> dict[str, Any]:
    url = BASE_URL + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "funding-universe/1"})
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if int(payload.get("retCode", -1)) != 0:
        raise RuntimeError(f"Bybit public API error: {payload.get('retCode')} {payload.get('retMsg')}")
    return payload


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _instrument_rows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor = ""
    while True:
        params: dict[str, Any] = {"category": "linear", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        payload = _http_json("/v5/market/instruments-info", params)
        result = payload.get("result") or {}
        out.extend(row for row in result.get("list") or [] if isinstance(row, dict))
        next_cursor = str(result.get("nextPageCursor") or "")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
    return out


def _ticker_map() -> dict[str, dict[str, Any]]:
    payload = _http_json("/v5/market/tickers", {"category": "linear"})
    return {
        str(row.get("symbol") or "").upper(): row
        for row in (payload.get("result") or {}).get("list") or []
        if isinstance(row, dict)
    }


def _funding_coverage(symbol: str, limit: int) -> int:
    payload = _http_json(
        "/v5/market/funding/history",
        {"category": "linear", "symbol": symbol, "limit": limit},
    )
    return len((payload.get("result") or {}).get("list") or [])


def build_universe(
    *,
    top_n: int = 16,
    prefilter_n: int = 40,
    min_turnover_usd: float = 20_000_000.0,
    max_spread_bps: float = 12.0,
    min_listing_days: int = 90,
    min_funding_observations: int = 91,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    tickers = _ticker_map()
    eligible: list[dict[str, Any]] = []
    rejected: dict[str, int] = {}

    def reject(reason: str) -> None:
        rejected[reason] = rejected.get(reason, 0) + 1

    for instrument in _instrument_rows():
        symbol = str(instrument.get("symbol") or "").upper()
        symbol_type = str(instrument.get("symbolType") or "").strip().lower()
        if (
            instrument.get("status") != "Trading"
            or instrument.get("contractType") != "LinearPerpetual"
            or instrument.get("quoteCoin") not in {None, "", "USDT"}
            or instrument.get("settleCoin") != "USDT"
            or symbol_type not in ALLOWED_CRYPTO_SYMBOL_TYPES
        ):
            reject("not_trading_usdt_linear_perpetual")
            continue
        launch_ms = int(_finite(instrument.get("launchTime"), 0.0))
        listing_days = (now_ms - launch_ms) / 86_400_000 if launch_ms > 0 else 0.0
        if listing_days < min_listing_days:
            reject("listing_too_young")
            continue
        ticker = tickers.get(symbol) or {}
        turnover = _finite(ticker.get("turnover24h"))
        bid = _finite(ticker.get("bid1Price"))
        ask = _finite(ticker.get("ask1Price"))
        mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else 0.0
        spread_bps = (ask - bid) / mid * 10_000.0 if mid > 0 and ask >= bid else float("inf")
        if turnover < min_turnover_usd:
            reject("turnover_below_floor")
            continue
        if not math.isfinite(spread_bps) or spread_bps > max_spread_bps:
            reject("spread_above_ceiling")
            continue
        eligible.append(
            {
                "symbol": symbol,
                "turnover24h_usd": turnover,
                "spread_bps": spread_bps,
                "listing_days": listing_days,
            }
        )

    # Coverage calls are bounded to the most liquid candidates plus anchors.
    eligible.sort(key=lambda row: (-row["turnover24h_usd"], row["spread_bps"], row["symbol"]))
    anchor_rows = [row for row in eligible if row["symbol"] in ANCHORS]
    prefiltered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in anchor_rows + eligible[: max(1, int(prefilter_n))]:
        if row["symbol"] not in seen:
            seen.add(row["symbol"])
            prefiltered.append(row)
    covered: list[dict[str, Any]] = []
    for row in prefiltered:
        observations = _funding_coverage(row["symbol"], min_funding_observations + 9)
        if observations < min_funding_observations:
            reject("insufficient_funding_history")
            continue
        covered.append({**row, "funding_observations": observations})

    covered.sort(key=lambda row: (-row["turnover24h_usd"], row["spread_bps"], row["symbol"]))
    anchors = [row for row in covered if row["symbol"] in ANCHORS]
    others = [row for row in covered if row["symbol"] not in ANCHORS]
    selected_rows: list[dict[str, Any]] = []
    for row in anchors + others:
        if len(selected_rows) >= max(1, int(top_n)):
            break
        if row["symbol"] not in {item["symbol"] for item in selected_rows}:
            selected_rows.append(row)
    selected_rows.sort(key=lambda row: (-row["turnover24h_usd"], row["symbol"]))
    symbols = [row["symbol"] for row in selected_rows]
    universe_sha = hashlib.sha256(",".join(symbols).encode()).hexdigest()
    return {
        "schema_id": "funding_positioning_dynamic_universe_v1",
        "generated_at_utc": _now_iso(),
        "as_of_epoch_ms": now_ms,
        "authority": "research_only_no_orders",
        "selection_contract": {
            "top_n": int(top_n),
            "prefilter_n": int(prefilter_n),
            "min_turnover_usd": float(min_turnover_usd),
            "max_spread_bps": float(max_spread_bps),
            "min_listing_days": int(min_listing_days),
            "min_funding_observations": int(min_funding_observations),
            "rank": "turnover_desc_then_spread_then_symbol",
            "crypto_symbol_types": sorted(ALLOWED_CRYPTO_SYMBOL_TYPES),
            "signal_or_pnl_used": False,
            "anchors_retained_if_eligible": list(ANCHORS),
        },
        "symbols": symbols,
        "symbol_count": len(symbols),
        "universe_sha256": universe_sha,
        "rows": selected_rows,
        "rejected_counts": dict(sorted(rejected.items())),
        "capital_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--top-n", type=int, default=16)
    parser.add_argument("--prefilter-n", type=int, default=40)
    parser.add_argument("--min-turnover-usd", type=float, default=20_000_000.0)
    parser.add_argument("--max-spread-bps", type=float, default=12.0)
    parser.add_argument("--min-listing-days", type=int, default=90)
    args = parser.parse_args()
    payload = build_universe(
        top_n=args.top_n,
        prefilter_n=args.prefilter_n,
        min_turnover_usd=args.min_turnover_usd,
        max_spread_bps=args.max_spread_bps,
        min_listing_days=args.min_listing_days,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(args.out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(args.out)
    print(json.dumps({key: payload[key] for key in (
        "generated_at_utc", "symbol_count", "symbols", "universe_sha256"
    )}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
