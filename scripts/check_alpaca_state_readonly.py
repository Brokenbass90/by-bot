#!/usr/bin/env python3
"""Read-only Alpaca account/position/order truth for operational checks.

This helper performs GET requests only. It never submits, replaces, cancels,
or closes an order or position, and it never prints credentials.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import equities_alpaca_intraday_bridge as bridge


DEFAULT_LIVE_ENV_FILE = bridge.ROOT / "configs" / "alpaca_live_v38.env"


def _finite_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _position_view(row: dict[str, Any]) -> dict[str, Any]:
    qty = float(row.get("qty") or 0.0)
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "side": "long" if qty > 0 else ("short" if qty < 0 else "flat"),
        "qty": qty,
        "avg_entry_price": _finite_text(row.get("avg_entry_price")),
        "current_price": _finite_text(row.get("current_price")),
        "market_value": _finite_text(row.get("market_value")),
        "unrealized_pl": _finite_text(row.get("unrealized_pl")),
    }


def _order_view(row: dict[str, Any]) -> dict[str, Any]:
    legs = row.get("legs") if isinstance(row.get("legs"), list) else []
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "side": _finite_text(row.get("side")),
        "type": _finite_text(row.get("type")),
        "status": _finite_text(row.get("status")),
        "time_in_force": _finite_text(row.get("time_in_force")),
        "qty": _finite_text(row.get("qty")),
        "filled_qty": _finite_text(row.get("filled_qty")),
        "limit_price": _finite_text(row.get("limit_price")),
        "stop_price": _finite_text(row.get("stop_price")),
        "order_class": _finite_text(row.get("order_class")),
        "created_at": _finite_text(row.get("created_at")),
        "filled_at": _finite_text(row.get("filled_at")),
        "legs": [
            {
                "side": _finite_text(leg.get("side")),
                "type": _finite_text(leg.get("type")),
                "status": _finite_text(leg.get("status")),
                "limit_price": _finite_text(leg.get("limit_price")),
                "stop_price": _finite_text(leg.get("stop_price")),
            }
            for leg in legs
            if isinstance(leg, dict)
        ],
    }


def collect(symbol: str = "", env_file: str | Path | None = None) -> dict[str, Any]:
    selected_env_file = Path(env_file) if env_file else DEFAULT_LIVE_ENV_FILE
    bridge._load_env_file(selected_env_file)
    bridge._refresh_runtime_paths()
    key_id = bridge._env("ALPACA_API_KEY_ID")
    secret = bridge._env("ALPACA_API_SECRET_KEY")
    base_url = bridge._env("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    if not key_id or not secret:
        raise RuntimeError("Alpaca credentials are not configured")
    client = bridge.AlpacaClient(base_url, key_id, secret)
    account = client.get_account()
    positions = [_position_view(row) for row in client.list_positions()]
    orders = [_order_view(row) for row in client.list_orders(status="open")]
    recent_after = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent_orders = [
        _order_view(row)
        for row in client.list_orders(status="all", after=recent_after)
    ]
    target = symbol.strip().upper()
    if target:
        positions = [row for row in positions if row["symbol"] == target]
        orders = [row for row in orders if row["symbol"] == target]
        recent_orders = [row for row in recent_orders if row["symbol"] == target]
    return {
        "schema_id": "alpaca_broker_truth_readonly_v1",
        "authority": "read_only_get_no_order_mutation",
        "configured_env_file": str(selected_env_file),
        "broker_mode": "PAPER" if "paper-api" in base_url.lower() else "LIVE",
        "account": {
            "status": _finite_text(account.get("status")),
            "equity": _finite_text(account.get("equity") or account.get("portfolio_value")),
            "cash": _finite_text(account.get("cash")),
        },
        "position_count": len(positions),
        "positions": positions,
        "open_order_count": len(orders),
        "open_orders": orders,
        "recent_order_count": len(recent_orders),
        "recent_orders": recent_orders,
        "symbol_filter": target or None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="")
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_LIVE_ENV_FILE),
        help="credential env file; defaults to the protected Alpaca live v38 file",
    )
    args = parser.parse_args()
    print(json.dumps(collect(args.symbol, args.env_file), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
