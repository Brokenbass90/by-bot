#!/usr/bin/env python3
"""Read the current Bybit account fee tier without order authority."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Callable

from scripts.check_bybit_open_positions import _bybit_get, _first_bybit_account, _load_env


def fetch_fee_rate(
    *, category: str, symbol: str,
    getter: Callable[[str, str, str, str, dict[str, str]], dict],
    base: str, key: str, secret: str,
) -> dict:
    payload = getter(
        base, key, secret, "/v5/account/fee-rate",
        {"category": category, "symbol": symbol},
    )
    if int(payload.get("retCode", -1)) != 0:
        raise RuntimeError(f"fee query failed: {payload.get('retMsg')}")
    rows = ((payload.get("result") or {}).get("list") or [])
    if len(rows) != 1:
        raise RuntimeError(f"expected one fee row for {category}:{symbol}, got {len(rows)}")
    row = rows[0]
    maker = float(row["makerFeeRate"])
    taker = float(row["takerFeeRate"])
    return {
        "category": category,
        "symbol": symbol,
        "maker_fee_rate": maker,
        "taker_fee_rate": taker,
        "maker_bps": maker * 10_000,
        "taker_bps": taker * 10_000,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()
    env = _load_env(args.env)
    key, secret, base = _first_bybit_account(env)
    if not key or not secret:
        print(json.dumps({"error": "missing_bybit_credentials"}))
        return 2
    queries = (("spot", "BTCUSDT"), ("linear", "BTCUSDT"),
               ("linear", "ADAUSDT"), ("linear", "DOTUSDT"))
    rows = [
        fetch_fee_rate(
            category=category, symbol=symbol, getter=_bybit_get,
            base=base, key=key, secret=secret,
        )
        for category, symbol in queries
    ]
    print(json.dumps({
        "schema_id": "bybit_account_fee_readonly_v1",
        "authority": "read_only_no_orders",
        "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "fees": rows,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
