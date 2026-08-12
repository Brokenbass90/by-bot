#!/usr/bin/env python3
"""Verify one sanitized live order against the shared sizing contract.

The script is read-only: it accepts a receipt, performs no network calls and
has no exchange/order authority.  It compares the live stop-percent interface
with the backtest fixed-R interface before exchange rounding, then verifies the
submitted quantity after the exact qty-step floor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.risk_sizing_contract import calculate_notional_from_stop_pct, calculate_risk_size


class ParityError(RuntimeError):
    """The receipt is incomplete or the two sizing paths disagree."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _number(payload: dict[str, Any], key: str) -> float:
    try:
        value = float(payload[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ParityError(f"missing_or_invalid:{key}") from exc
    if not math.isfinite(value):
        raise ParityError(f"non_finite:{key}")
    return value


def floor_qty(notional_usd: float, price: float, qty_step: float) -> float:
    if notional_usd > 0 and price > 0 and qty_step > 0:
        step = Decimal(str(qty_step))
        raw = Decimal(str(notional_usd)) / Decimal(str(price))
        return float((raw / step).to_integral_value(rounding=ROUND_DOWN) * step)
    raise ParityError("nonpositive_rounding_input")


def verify(payload: dict[str, Any]) -> dict[str, Any]:
    equity = _number(payload, "effective_equity_usd")
    entry = _number(payload, "planned_entry_price")
    sizing_price = _number(payload, "sizing_price")
    stop = _number(payload, "stop_price")
    target = _number(payload, "target_risk_fraction")
    risk_mult = _number(payload, "strategy_risk_multiplier")
    vol_mult = _number(payload, "volatility_multiplier")
    cap = _number(payload, "max_notional_usd")
    min_fill = _number(payload, "min_fill_fraction")
    qty_step = _number(payload, "qty_step")
    min_qty = _number(payload, "min_qty")
    observed_qty = _number(payload, "submitted_qty")
    side = str(payload.get("side") or "").lower()

    stop_pct = abs(stop - entry) / entry * 100.0
    live = calculate_notional_from_stop_pct(
        equity=equity,
        stop_pct=stop_pct,
        target_risk_fraction=target,
        risk_multiplier=risk_mult,
        volatility_multiplier=vol_mult,
        max_notional_usd=cap,
        min_fill_fraction=min_fill,
    )
    backtest = calculate_risk_size(
        equity=equity,
        entry=entry,
        stop=stop,
        side=side,
        target_risk_fraction=target * risk_mult * vol_mult,
        max_notional_usd=cap,
        min_fill_fraction=min_fill,
    )
    expected_qty = floor_qty(live.effective_notional_usd, sizing_price, qty_step) if live.accepted else 0.0
    checks = {
        "live_accepted_equals_backtest": live.accepted == backtest.accepted,
        "pre_round_notional_equal": math.isclose(
            live.effective_notional_usd, backtest.effective_notional_usd, rel_tol=1e-12, abs_tol=1e-12
        ),
        "pre_round_risk_equal": math.isclose(
            live.effective_risk_usd, backtest.effective_risk_usd, rel_tol=1e-12, abs_tol=1e-12
        ),
        "submitted_qty_equals_step_floor": math.isclose(expected_qty, observed_qty, abs_tol=qty_step / 10.0),
        "submitted_qty_meets_minimum": observed_qty + 1e-12 >= min_qty,
    }
    return {
        "schema_id": "order_size_parity_result_v1",
        "authority": "read_only_no_orders_no_risk_mutation",
        "source_receipt_id": payload.get("receipt_id"),
        "checks": checks,
        "pass": all(checks.values()),
        "computed": {
            "stop_pct": stop_pct,
            "pre_round_notional_usd": live.effective_notional_usd,
            "pre_round_risk_usd": live.effective_risk_usd,
            "backtest_notional_usd": backtest.effective_notional_usd,
            "expected_qty": expected_qty,
            "observed_qty": observed_qty,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.receipt.read_text(encoding="utf-8"))
    result = verify(payload)
    result["input_sha256"] = _sha256(args.receipt)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
