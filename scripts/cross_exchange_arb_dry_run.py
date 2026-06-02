#!/usr/bin/env python3
"""Dry-run planner for cross-exchange funding opportunities.

Reads validated public opportunities plus read-only account balances and writes
the exact pair/leg plan the bot would consider. It never submits orders and does
not require trading permissions.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VALIDATED = ROOT / "runtime" / "arb" / "cross_exchange_funding_validated.json"
DEFAULT_ACCOUNTS = ROOT / "runtime" / "arb" / "exchange_account_status.json"
DEFAULT_OUT_DIR = ROOT / "runtime" / "arb" / "dry_run"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _validated_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        rows = payload.get("items") or payload.get("validated") or payload.get("pairs") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []
    return [r for r in rows if isinstance(r, dict) and r.get("passed", True)]


def _available_usdt(accounts: dict[str, Any], exchange: str) -> float:
    row = accounts.get("exchanges", {}).get(exchange.lower(), {})
    if not isinstance(row, dict) or not row.get("ok"):
        return 0.0
    return _f(row.get("available_usdt"))


def _exchange_ok(accounts: dict[str, Any], exchange: str) -> bool:
    row = accounts.get("exchanges", {}).get(exchange.lower(), {})
    return bool(isinstance(row, dict) and row.get("ok"))


def _leg_plan(exchange: str, side: str, symbol: str, notional: float) -> dict[str, Any]:
    return {
        "exchange": exchange,
        "symbol": symbol,
        "side": side,
        "notional_usdt": round(notional, 4),
        "order_type": "market",
        "dry_run": True,
    }


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    validated_payload = _load_json(Path(args.validated_json))
    account_payload = _load_json(Path(args.account_json))
    items = _validated_items(validated_payload)

    plans: list[dict[str, Any]] = []
    for item in items[: max(1, args.top)]:
        symbol = str(item.get("symbol") or "").upper()
        long_ex = str(item.get("long_exchange") or "").lower()
        short_ex = str(item.get("short_exchange") or "").lower()
        if not symbol or not long_ex or not short_ex:
            continue

        long_ok = _exchange_ok(account_payload, long_ex)
        short_ok = _exchange_ok(account_payload, short_ex)
        long_available = _available_usdt(account_payload, long_ex)
        short_available = _available_usdt(account_payload, short_ex)
        max_by_balance = min(long_available, short_available) * float(args.margin_share)
        requested = min(float(args.per_leg_cap_usdt), _f(item.get("notional_usd_per_leg"), args.per_leg_cap_usdt))
        planned_notional = min(requested, max_by_balance)
        funds_ok = planned_notional >= float(args.min_leg_usdt)

        blockers: list[str] = []
        if not long_ok:
            blockers.append(f"{long_ex}_account_not_ok")
        if not short_ok:
            blockers.append(f"{short_ex}_account_not_ok")
        if not funds_ok:
            blockers.append(
                f"insufficient_balance need>={args.min_leg_usdt:.2f}/leg "
                f"available_long={long_available:.2f} available_short={short_available:.2f}"
            )

        ready = bool(long_ok and short_ok and funds_ok)
        plans.append(
            {
                "pair_key": item.get("pair_key") or f"{symbol}:{long_ex}->{short_ex}",
                "symbol": symbol,
                "long_exchange": long_ex,
                "short_exchange": short_ex,
                "ready_for_order_dry_run": ready,
                "blockers": blockers,
                "planned_notional_usdt_per_leg": round(planned_notional if ready else requested, 4),
                "estimated_net_pct_for_hold": _f(item.get("estimated_net_pct_for_hold")),
                "spread_apr_pct": _f(item.get("spread_apr_pct")),
                "persistence_count": item.get("persistence_count_in_window"),
                "legs": [
                    _leg_plan(long_ex, "buy_long", symbol, planned_notional if ready else requested),
                    _leg_plan(short_ex, "sell_short", symbol, planned_notional if ready else requested),
                ],
            }
        )

    ready_count = sum(1 for p in plans if p["ready_for_order_dry_run"])
    return {
        "generated_at_utc": _utc_now_iso(),
        "schema_version": "1.0",
        "mode": "dry_run_only_no_orders",
        "trading_locked": True,
        "inputs": {
            "validated_json": str(Path(args.validated_json)),
            "account_json": str(Path(args.account_json)),
            "per_leg_cap_usdt": float(args.per_leg_cap_usdt),
            "min_leg_usdt": float(args.min_leg_usdt),
            "margin_share": float(args.margin_share),
        },
        "validated_count": len(items),
        "ready_count": ready_count,
        "plans": plans,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Dry-run only cross-exchange funding arb planner.")
    ap.add_argument("--validated-json", default=str(DEFAULT_VALIDATED))
    ap.add_argument("--account-json", default=str(DEFAULT_ACCOUNTS))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--per-leg-cap-usdt", type=float, default=100.0)
    ap.add_argument("--min-leg-usdt", type=float, default=20.0)
    ap.add_argument("--margin-share", type=float, default=0.35)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    payload = build_plan(args)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"dry_run_{stamp}.json"
    latest_path = out_dir / "latest.json"
    text = json.dumps(payload, ensure_ascii=True, indent=2) + "\n"
    out_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")

    if not args.quiet:
        print(
            f"[arb_dry_run] validated={payload['validated_count']} "
            f"ready={payload['ready_count']} out={latest_path}"
        )
        for plan in payload["plans"][:5]:
            mark = "READY" if plan["ready_for_order_dry_run"] else "BLOCKED"
            print(
                f"{mark} {plan['pair_key']} net={plan['estimated_net_pct_for_hold']:.4f}% "
                f"notional=${plan['planned_notional_usdt_per_leg']:.2f} "
                f"blockers={';'.join(plan['blockers']) or '-'}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
