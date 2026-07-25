#!/usr/bin/env python3
"""Walk-forward diagnostic for public cross-exchange funding histories.

At the start of every out-of-sample block the model:

1. estimates each symbol's mean venue differential on the trailing window;
2. fixes the collection direction from that sign;
3. selects the largest absolute differentials;
4. holds that fixed basket and direction through the next OOS block.

This is research only.  It intentionally excludes basis, borrow, liquidation,
legging and fill risk, so a positive result is evidence for a funding
differential to investigate rather than authorization to trade.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DAY_MS = 86_400_000


class FundingAnalysisError(RuntimeError):
    """Invalid or insufficient research input."""


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _aligned_differentials(
    records: Iterable[dict[str, Any]],
    *,
    venue_a: str,
    venue_b: str,
) -> dict[str, list[tuple[int, float]]]:
    keyed: dict[tuple[str, int], dict[str, float]] = {}
    for row in records:
        venue = str(row.get("venue") or "").lower()
        if venue not in {venue_a, venue_b}:
            continue
        symbol = str(row.get("symbol") or "").upper()
        try:
            timestamp = int(row["funding_time_ms"])
            rate = float(row["funding_rate"])
        except (KeyError, TypeError, ValueError) as exc:
            raise FundingAnalysisError("malformed funding record") from exc
        if not symbol or timestamp <= 0 or not math.isfinite(rate):
            raise FundingAnalysisError("invalid funding record")
        slot = keyed.setdefault((symbol, timestamp), {})
        if venue in slot and slot[venue] != rate:
            raise FundingAnalysisError(
                f"conflicting duplicate for {venue}:{symbol}:{timestamp}"
            )
        slot[venue] = rate

    by_symbol: dict[str, list[tuple[int, float]]] = {}
    for (symbol, timestamp), rates in keyed.items():
        if venue_a not in rates or venue_b not in rates:
            continue
        by_symbol.setdefault(symbol, []).append(
            (timestamp, rates[venue_a] - rates[venue_b])
        )
    for rows in by_symbol.values():
        rows.sort()
    return by_symbol


def walk_forward(
    records: Iterable[dict[str, Any]],
    *,
    venue_a: str = "bybit",
    venue_b: str = "mexc",
    train_days: int = 60,
    oos_days: int = 30,
    top_k: int = 3,
    round_trip_cost_bps: Iterable[float] = (0.0, 8.0, 22.0, 40.0),
) -> dict[str, Any]:
    if train_days < 1 or oos_days < 1 or top_k < 1:
        raise FundingAnalysisError("train_days, oos_days and top_k must be positive")
    venue_a = venue_a.lower()
    venue_b = venue_b.lower()
    aligned = _aligned_differentials(
        records,
        venue_a=venue_a,
        venue_b=venue_b,
    )
    if len(aligned) < top_k:
        raise FundingAnalysisError(
            f"only {len(aligned)} aligned symbols, need top_k={top_k}"
        )

    common_first = max(rows[0][0] for rows in aligned.values() if rows)
    common_last = min(rows[-1][0] for rows in aligned.values() if rows)
    first_oos_ms = common_first + train_days * DAY_MS
    if first_oos_ms >= common_last:
        raise FundingAnalysisError("history is shorter than the training window")

    cost_levels = sorted({float(value) for value in round_trip_cost_bps})
    blocks: list[dict[str, Any]] = []
    start_ms = first_oos_ms
    while start_ms <= common_last:
        end_ms = min(start_ms + oos_days * DAY_MS, common_last + 1)
        selections: list[dict[str, Any]] = []
        train_start = start_ms - train_days * DAY_MS
        for symbol, rows in aligned.items():
            train = [
                diff
                for timestamp, diff in rows
                if train_start <= timestamp < start_ms
            ]
            test = [
                diff
                for timestamp, diff in rows
                if start_ms <= timestamp < end_ms
            ]
            if not train or not test:
                continue
            train_mean = sum(train) / len(train)
            direction = 1.0 if train_mean >= 0 else -1.0
            selections.append(
                {
                    "symbol": symbol,
                    "train_observations": len(train),
                    "oos_observations": len(test),
                    "train_mean_diff_bps_per_settlement": train_mean * 10_000.0,
                    "collection_route": (
                        f"short_{venue_a}_long_{venue_b}"
                        if direction > 0
                        else f"short_{venue_b}_long_{venue_a}"
                    ),
                    "oos_gross_bps": direction * sum(test) * 10_000.0,
                }
            )
        selected = sorted(
            selections,
            key=lambda row: abs(
                float(row["train_mean_diff_bps_per_settlement"])
            ),
            reverse=True,
        )[:top_k]
        if len(selected) < top_k:
            break
        gross_bps = sum(float(row["oos_gross_bps"]) for row in selected) / top_k
        blocks.append(
            {
                "oos_start_utc": datetime.fromtimestamp(
                    start_ms / 1000.0, tz=timezone.utc
                ).isoformat(),
                "oos_end_exclusive_utc": datetime.fromtimestamp(
                    end_ms / 1000.0, tz=timezone.utc
                ).isoformat(),
                "selected": selected,
                "basket_gross_bps": gross_bps,
                "basket_net_bps_by_round_trip_cost": {
                    f"{cost:g}": gross_bps - cost for cost in cost_levels
                },
            }
        )
        start_ms += oos_days * DAY_MS

    if not blocks:
        raise FundingAnalysisError("no complete OOS blocks could be formed")

    aggregate_costs: dict[str, dict[str, Any]] = {}
    for cost in cost_levels:
        values = [
            float(block["basket_net_bps_by_round_trip_cost"][f"{cost:g}"])
            for block in blocks
        ]
        aggregate_costs[f"{cost:g}"] = {
            "round_trip_cost_bps": cost,
            "positive_blocks": sum(value > 0 for value in values),
            "block_count": len(values),
            "cumulative_net_bps": sum(values),
            "mean_net_bps_per_block": sum(values) / len(values),
        }

    return {
        "schema_id": "cross_exchange_funding_walk_forward_v1",
        "research_only": True,
        "not_live_authorization": True,
        "omitted_risks": [
            "basis_convergence_or_divergence",
            "borrow_and_margin_availability",
            "liquidation",
            "legging_and_fill",
            "funding_rate_revision",
            "venue_credit_and_transfer",
        ],
        "venues": [venue_a, venue_b],
        "aligned_symbol_count": len(aligned),
        "train_days": train_days,
        "oos_days": oos_days,
        "top_k": top_k,
        "blocks": blocks,
        "aggregate_by_round_trip_cost_bps": aggregate_costs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Walk-forward diagnostic for cross-exchange funding."
    )
    parser.add_argument(
        "--input",
        default="research_lab/data/cross_exchange_funding_history_180d.json",
    )
    parser.add_argument(
        "--output",
        default="reports/research/cross_exchange_funding_walk_forward_20260726.json",
    )
    parser.add_argument("--venue-a", default="bybit")
    parser.add_argument("--venue-b", default="mexc")
    parser.add_argument("--train-days", type=int, default=60)
    parser.add_argument("--oos-days", type=int, default=30)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--cost-bps", default="0,8,22,40")
    args = parser.parse_args()

    input_path = ROOT / args.input
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise FundingAnalysisError("input must contain a records list")
    costs = [float(value.strip()) for value in args.cost_bps.split(",") if value.strip()]
    result = walk_forward(
        payload["records"],
        venue_a=args.venue_a,
        venue_b=args.venue_b,
        train_days=args.train_days,
        oos_days=args.oos_days,
        top_k=args.top_k,
        round_trip_cost_bps=costs,
    )
    result["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    result["input_path"] = str(input_path.relative_to(ROOT))
    result["input_file_sha256"] = _sha256_file(input_path)
    output_path = ROOT / args.output
    _atomic_json(output_path, result)
    maker = result["aggregate_by_round_trip_cost_bps"].get("8", {})
    taker = result["aggregate_by_round_trip_cost_bps"].get("22", {})
    print(
        f"blocks={len(result['blocks'])} "
        f"maker_positive={maker.get('positive_blocks')}/{maker.get('block_count')} "
        f"taker_positive={taker.get('positive_blocks')}/{taker.get('block_count')} "
        f"saved={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
