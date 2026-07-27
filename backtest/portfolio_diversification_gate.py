"""Fixed-weight portfolio gate for independent strategy trade ledgers.

This module does not search weights or strategy subsets.  It evaluates a
preregistered set of trades with one fixed risk unit per accepted position,
enforces the owner's maximum number of simultaneous entries, and reports red
calendar months separately for train and untouched OOS/holdout segments.

Input trade fields:
    strategy, opened_at_utc, closed_at_utc, net_return_r, segment

`segment` must be one of train/oos/holdout.  Promotion statistics use only
oos+holdout.  A zero-red-month result is reported as an aspirational diagnostic,
not as permission to optimize weights after seeing the same months.
"""

from __future__ import annotations

import argparse
import calendar
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


VALID_SEGMENTS = {"train", "oos", "holdout"}


@dataclass(frozen=True)
class PortfolioTrade:
    strategy: str
    opened_at: datetime
    closed_at: datetime
    net_return_r: float
    segment: str


def _parse_utc(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("timestamp is required")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_trades(rows: Iterable[dict[str, Any]]) -> list[PortfolioTrade]:
    trades: list[PortfolioTrade] = []
    for index, row in enumerate(rows):
        strategy = str(row.get("strategy") or "").strip()
        segment = str(row.get("segment") or "").strip().lower()
        if not strategy:
            raise ValueError(f"trade {index}: strategy is required")
        if segment not in VALID_SEGMENTS:
            raise ValueError(
                f"trade {index}: segment must be one of "
                f"{sorted(VALID_SEGMENTS)}"
            )
        opened = _parse_utc(row.get("opened_at_utc"))
        closed = _parse_utc(row.get("closed_at_utc"))
        if closed <= opened:
            raise ValueError(f"trade {index}: close must be after open")
        try:
            result = float(row.get("net_return_r"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"trade {index}: net_return_r is required") from exc
        if not math.isfinite(result):
            raise ValueError(f"trade {index}: net_return_r must be finite")
        trades.append(
            PortfolioTrade(
                strategy=strategy,
                opened_at=opened,
                closed_at=closed,
                net_return_r=result,
                segment=segment,
            )
        )
    return sorted(
        trades,
        key=lambda row: (
            row.opened_at,
            row.closed_at,
            row.strategy,
        ),
    )


def _month_key(value: datetime) -> str:
    return value.strftime("%Y-%m")


def _next_month(key: str) -> str:
    year, month = (int(part) for part in key.split("-", 1))
    if month == 12:
        return f"{year + 1:04d}-01"
    return f"{year:04d}-{month + 1:02d}"


def _calendar_months(start: datetime, end: datetime) -> list[str]:
    first = _month_key(start)
    last = _month_key(end)
    out = [first]
    while out[-1] != last:
        out.append(_next_month(out[-1]))
    return out


def _accept_with_slot_cap(
    trades: list[PortfolioTrade],
    *,
    max_open_positions: int,
) -> tuple[list[PortfolioTrade], list[PortfolioTrade], int]:
    if max_open_positions < 1:
        raise ValueError("max_open_positions must be at least 1")
    active_closes: list[datetime] = []
    accepted: list[PortfolioTrade] = []
    rejected: list[PortfolioTrade] = []
    peak_open = 0
    for trade in trades:
        active_closes = [
            close for close in active_closes if close > trade.opened_at
        ]
        if len(active_closes) >= max_open_positions:
            rejected.append(trade)
            continue
        accepted.append(trade)
        active_closes.append(trade.closed_at)
        peak_open = max(peak_open, len(active_closes))
    return accepted, rejected, peak_open


def _segment_metrics(
    trades: list[PortfolioTrade],
    *,
    risk_pct_per_r: float,
) -> dict[str, Any]:
    if not trades:
        return {
            "trades": 0,
            "months": 0,
            "positive_months": 0,
            "negative_months": 0,
            "zero_months": 0,
            "zero_red_months": False,
            "total_return_pct_simple": 0.0,
            "annualized_return_pct_simple": None,
            "max_drawdown_pct_simple": 0.0,
            "monthly": [],
            "by_strategy_return_pct": {},
            "top_positive_strategy_profit_share": None,
        }

    monthly_values: dict[str, float] = {
        key: 0.0
        for key in _calendar_months(
            min(row.opened_at for row in trades),
            max(row.closed_at for row in trades),
        )
    }
    by_strategy: dict[str, float] = {}
    realized: list[tuple[datetime, float]] = []
    for trade in trades:
        value = float(trade.net_return_r) * float(risk_pct_per_r)
        monthly_values[_month_key(trade.closed_at)] += value
        by_strategy[trade.strategy] = by_strategy.get(trade.strategy, 0.0) + value
        realized.append((trade.closed_at, value))

    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for _, value in sorted(realized):
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    positive_contributions = [
        value for value in by_strategy.values() if value > 0
    ]
    positive_sum = sum(positive_contributions)
    top_share = (
        max(positive_contributions) / positive_sum
        if positive_contributions and positive_sum > 0
        else None
    )
    values = list(monthly_values.values())
    months = len(values)
    total = sum(values)
    return {
        "trades": len(trades),
        "months": months,
        "positive_months": sum(value > 0 for value in values),
        "negative_months": sum(value < 0 for value in values),
        "zero_months": sum(value == 0 for value in values),
        "zero_red_months": bool(values) and all(value >= 0 for value in values),
        "total_return_pct_simple": round(total, 6),
        "annualized_return_pct_simple": round(total * 12.0 / months, 6)
        if months
        else None,
        "max_drawdown_pct_simple": round(max_drawdown, 6),
        "monthly": [
            {"month": key, "return_pct_simple": round(value, 6)}
            for key, value in sorted(monthly_values.items())
        ],
        "by_strategy_return_pct": {
            key: round(value, 6)
            for key, value in sorted(by_strategy.items())
        },
        "top_positive_strategy_profit_share": round(top_share, 6)
        if top_share is not None
        else None,
    }


def evaluate_portfolio(
    rows: Iterable[dict[str, Any]],
    *,
    max_open_positions: int = 3,
    risk_pct_per_r: float = 0.5,
    min_oos_months: int = 12,
    max_negative_oos_months_per_year: int = 2,
    min_oos_annualized_return_pct: float = 8.0,
    max_oos_drawdown_pct: float = 12.0,
    max_top_strategy_profit_share: float = 0.60,
    min_oos_strategies: int = 2,
) -> dict[str, Any]:
    """Evaluate a fixed portfolio without subset or weight optimization."""
    if risk_pct_per_r <= 0:
        raise ValueError("risk_pct_per_r must be positive")
    trades = parse_trades(rows)
    accepted, rejected, peak_open = _accept_with_slot_cap(
        trades,
        max_open_positions=max_open_positions,
    )
    train = [row for row in accepted if row.segment == "train"]
    oos = [row for row in accepted if row.segment in {"oos", "holdout"}]
    all_metrics = _segment_metrics(
        accepted,
        risk_pct_per_r=risk_pct_per_r,
    )
    train_metrics = _segment_metrics(
        train,
        risk_pct_per_r=risk_pct_per_r,
    )
    oos_metrics = _segment_metrics(
        oos,
        risk_pct_per_r=risk_pct_per_r,
    )

    oos_months = int(oos_metrics["months"])
    allowed_negative = math.floor(
        max(0, int(max_negative_oos_months_per_year))
        * oos_months
        / 12.0
    )
    if oos_months >= int(min_oos_months):
        allowed_negative = max(1, allowed_negative)
    oos_strategy_count = len({row.strategy for row in oos})
    top_share = oos_metrics["top_positive_strategy_profit_share"]
    gates = {
        "minimum_oos_months": oos_months >= int(min_oos_months),
        "minimum_oos_strategies": oos_strategy_count >= int(min_oos_strategies),
        "positive_oos_annualized_return": bool(
            oos_metrics["annualized_return_pct_simple"] is not None
            and oos_metrics["annualized_return_pct_simple"]
            >= float(min_oos_annualized_return_pct)
        ),
        "oos_drawdown_within_limit": (
            oos_metrics["max_drawdown_pct_simple"]
            <= float(max_oos_drawdown_pct)
        ),
        "oos_red_month_budget": (
            oos_metrics["negative_months"] <= allowed_negative
        ),
        "oos_strategy_concentration": bool(
            top_share is not None
            and top_share <= float(max_top_strategy_profit_share)
        ),
    }
    hard_pass = bool(gates) and all(gates.values())
    return {
        "schema_version": "portfolio_diversification_gate_v1",
        "research_only": True,
        "weights_optimized": False,
        "capital_authorized": False,
        "verdict": "PASS_NEXT_NON_MONEY_GATE" if hard_pass else "NO_PROMOTION",
        "configuration": {
            "max_open_positions": int(max_open_positions),
            "risk_pct_per_r": float(risk_pct_per_r),
            "min_oos_months": int(min_oos_months),
            "max_negative_oos_months_per_year": int(
                max_negative_oos_months_per_year
            ),
            "min_oos_annualized_return_pct": float(
                min_oos_annualized_return_pct
            ),
            "max_oos_drawdown_pct": float(max_oos_drawdown_pct),
            "max_top_strategy_profit_share": float(
                max_top_strategy_profit_share
            ),
            "min_oos_strategies": int(min_oos_strategies),
        },
        "occupancy": {
            "input_trades": len(trades),
            "accepted_trades": len(accepted),
            "rejected_by_three_slot_cap": len(rejected),
            "peak_simultaneous_positions": peak_open,
        },
        "all": all_metrics,
        "train": train_metrics,
        "oos": oos_metrics,
        "oos_strategy_count": oos_strategy_count,
        "allowed_negative_oos_months": allowed_negative,
        "aspirational_zero_red_oos_months": bool(
            oos_metrics["zero_red_months"]
        ),
        "gates": gates,
        "warnings": [
            (
                "Zero red months is an aspirational holdout diagnostic, not a "
                "weight-optimization objective on already observed months."
            ),
            (
                "Returns are simple fixed-risk approximations; execution costs "
                "must already be included in each trade's net_return_r."
            ),
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate a preregistered multi-strategy trade ledger"
    )
    parser.add_argument("input_json", help="JSON file containing a trades array")
    parser.add_argument("output_json", help="Destination report JSON")
    parser.add_argument("--max-open-positions", type=int, default=3)
    parser.add_argument("--risk-pct-per-r", type=float, default=0.5)
    parser.add_argument("--min-oos-months", type=int, default=12)
    parser.add_argument(
        "--max-negative-oos-months-per-year",
        type=int,
        default=2,
    )
    args = parser.parse_args()

    source = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    if not isinstance(source, dict) or not isinstance(
        source.get("trades"), list
    ):
        raise SystemExit("input JSON must contain a trades array")
    result = evaluate_portfolio(
        source["trades"],
        max_open_positions=args.max_open_positions,
        risk_pct_per_r=args.risk_pct_per_r,
        min_oos_months=args.min_oos_months,
        max_negative_oos_months_per_year=(
            args.max_negative_oos_months_per_year
        ),
    )
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == "PASS_NEXT_NON_MONEY_GATE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
