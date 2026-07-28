#!/usr/bin/env python3
"""Sealed, research-only ATT1 seasonality filter study.

The script consumes an immutable saved trade ledger. It does not read broker
credentials, call the network, mutate live configuration, or place orders.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session(hour: int) -> str:
    if hour < 8:
        return "asia_00_07"
    if hour < 16:
        return "europe_08_15"
    return "us_16_23"


def _load_trades(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = []
        for raw in reader:
            entry_ms = int(raw["entry_ts"])
            entered = datetime.fromtimestamp(entry_ms / 1000.0, timezone.utc)
            row: dict[str, Any] = dict(raw)
            row["_entry_dt"] = entered
            row["_return"] = float(raw["pnl_pct_equity"])
            row["_hour"] = entered.hour
            row["_session"] = _session(entered.hour)
            row["_weekday"] = entered.strftime("%a")
            row["_month"] = entered.strftime("%Y-%m")
            rows.append(row)
    rows.sort(key=lambda row: int(row["entry_ts"]))
    return rows, fieldnames


def _split_rows(
    rows: list[dict[str, Any]],
    discovery_fraction: float,
    validation_fraction: float,
) -> dict[str, list[dict[str, Any]]]:
    n = len(rows)
    discovery_end = int(math.floor(n * discovery_fraction))
    validation_end = discovery_end + int(math.floor(n * validation_fraction))
    return {
        "discovery": rows[:discovery_end],
        "validation": rows[discovery_end:validation_end],
        "holdout": rows[validation_end:],
    }


def _sign_flip_negative_mean_p(
    values: list[float],
    *,
    draws: int,
    seed: int,
) -> float:
    if not values:
        return 1.0
    observed = statistics.mean(values)
    if observed >= 0:
        return 1.0
    rng = random.Random(seed)
    extreme = 1
    for _ in range(draws):
        randomized = sum(
            value if rng.random() >= 0.5 else -value for value in values
        ) / len(values)
        if randomized <= observed:
            extreme += 1
    return extreme / (draws + 1)


def _benjamini_hochberg(p_by_key: dict[str, float]) -> dict[str, float]:
    if not p_by_key:
        return {}
    ordered = sorted(p_by_key.items(), key=lambda item: (item[1], item[0]))
    total = len(ordered)
    out: dict[str, float] = {}
    running = 1.0
    for rank_from_end in range(total - 1, -1, -1):
        key, p_value = ordered[rank_from_end]
        rank = rank_from_end + 1
        running = min(running, p_value * total / rank)
        out[key] = min(1.0, running)
    return out


def _metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    returns = [float(row["_return"]) for row in materialized]
    monthly = defaultdict(float)
    for row in materialized:
        monthly[str(row["_month"])] += float(row["_return"])
    compound = 1.0
    for value in returns:
        compound *= 1.0 + value
    return {
        "trades": len(materialized),
        "sum_return": round(sum(returns), 8),
        "compound_return": round(compound - 1.0, 8),
        "mean_return": (
            round(statistics.mean(returns), 8) if returns else None
        ),
        "median_return": (
            round(statistics.median(returns), 8) if returns else None
        ),
        "win_rate": (
            round(sum(value > 0 for value in returns) / len(returns), 6)
            if returns
            else None
        ),
        "red_months": sum(value < 0 for value in monthly.values()),
        "months": len(monthly),
        "sides": sorted({str(row["side"]) for row in materialized}),
    }


def _descriptive_bin_rows(
    split_rows: dict[str, list[dict[str, Any]]],
    *,
    p_by_hour: dict[str, float],
    q_by_hour: dict[str, float],
) -> list[dict[str, Any]]:
    dimensions = {
        "entry_hour_utc": lambda row: f"{int(row['_hour']):02d}",
        "session_utc": lambda row: str(row["_session"]),
        "weekday_utc": lambda row: str(row["_weekday"]),
        "side": lambda row: str(row["side"]),
    }
    output = []
    for split, rows in split_rows.items():
        for dimension, key_fn in dimensions.items():
            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in rows:
                grouped[key_fn(row)].append(row)
            for key in sorted(grouped):
                metrics = _metrics(grouped[key])
                output.append(
                    {
                        "split": split,
                        "dimension": dimension,
                        "bin": key,
                        **metrics,
                        "discovery_p_negative": (
                            round(p_by_hour[key], 8)
                            if (
                                split == "discovery"
                                and dimension == "entry_hour_utc"
                                and key in p_by_hour
                            )
                            else None
                        ),
                        "discovery_bh_q": (
                            round(q_by_hour[key], 8)
                            if (
                                split == "discovery"
                                and dimension == "entry_hour_utc"
                                and key in q_by_hour
                            )
                            else None
                        ),
                    }
                )
    return output


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0].keys()),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_split_ledger(
    path: Path,
    rows: list[dict[str, Any]],
    original_fields: list[str],
    excluded_hours: set[int],
) -> None:
    fields = [*original_fields, "seasonality_kept"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            output = {field: row.get(field) for field in original_fields}
            output["seasonality_kept"] = int(int(row["_hour"]) not in excluded_hours)
            writer.writerow(output)


def run(prereg_path: Path, output_dir: Path) -> dict[str, Any]:
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    input_path = ROOT / str(prereg["input"]["trade_ledger"])
    observed_sha = _sha256(input_path)
    expected_sha = str(prereg["input"]["trade_ledger_sha256"])
    if observed_sha != expected_sha:
        raise ValueError(
            f"input ledger SHA mismatch: expected {expected_sha}, got {observed_sha}"
        )

    rows, original_fields = _load_trades(input_path)
    expected_trades = int(prereg["input"]["expected_trades"])
    if len(rows) != expected_trades:
        raise ValueError(
            f"input trade count mismatch: expected {expected_trades}, got {len(rows)}"
        )

    split_cfg = prereg["split"]
    splits = _split_rows(
        rows,
        float(split_cfg["discovery_fraction"]),
        float(split_cfg["validation_fraction"]),
    )
    filter_cfg = prereg["primary_filter"]
    discovery_by_hour: dict[str, list[float]] = defaultdict(list)
    for row in splits["discovery"]:
        discovery_by_hour[f"{int(row['_hour']):02d}"].append(float(row["_return"]))

    minimum_n = int(filter_cfg["minimum_discovery_trades_per_hour"])
    draws = int(filter_cfg["sign_flip_draws"])
    seed = int(filter_cfg["random_seed"])
    p_by_hour = {
        hour: _sign_flip_negative_mean_p(
            values,
            draws=draws,
            seed=seed + int(hour),
        )
        for hour, values in discovery_by_hour.items()
        if len(values) >= minimum_n
    }
    q_by_hour = _benjamini_hochberg(p_by_hour)
    maximum_q = float(filter_cfg["maximum_q_value"])
    candidate_rows = []
    for hour, q_value in q_by_hour.items():
        values = discovery_by_hour[hour]
        mean_return = statistics.mean(values)
        if q_value <= maximum_q and mean_return < 0:
            candidate_rows.append(
                (q_value, mean_return, int(hour), len(values))
            )
    candidate_rows.sort(key=lambda item: (item[0], item[1], item[2]))
    candidate_rows = candidate_rows[: int(filter_cfg["maximum_excluded_hours"])]
    excluded_hours = {row[2] for row in candidate_rows}

    split_results: dict[str, Any] = {}
    for split, split_data in splits.items():
        kept = [row for row in split_data if int(row["_hour"]) not in excluded_hours]
        baseline = _metrics(split_data)
        filtered = _metrics(kept)
        retention = len(kept) / len(split_data) if split_data else 0.0
        split_results[split] = {
            "baseline": baseline,
            "filtered": filtered,
            "retention": round(retention, 6),
            "sum_return_improvement": round(
                float(filtered["sum_return"]) - float(baseline["sum_return"]),
                8,
            ),
        }

    minimum_retention = float(
        prereg["pass_gate"]["minimum_trade_retention_each_split"]
    )
    reasons = []
    if not excluded_hours:
        reasons.append("no_discovery_hours_survived_BH")
    for split in ("validation", "holdout"):
        result = split_results[split]
        if result["retention"] < minimum_retention:
            reasons.append(f"{split}_retention_below_floor")
        if set(result["filtered"]["sides"]) != {"long", "short"}:
            reasons.append(f"{split}_does_not_retain_both_sides")
    validation = split_results["validation"]
    holdout = split_results["holdout"]
    if validation["filtered"]["sum_return"] <= validation["baseline"]["sum_return"]:
        reasons.append("validation_does_not_improve_baseline")
    if validation["filtered"]["sum_return"] <= 0:
        reasons.append("validation_filtered_return_not_positive")
    if holdout["filtered"]["sum_return"] < holdout["baseline"]["sum_return"]:
        reasons.append("holdout_underperforms_baseline")
    if holdout["filtered"]["sum_return"] <= 0:
        reasons.append("holdout_filtered_return_not_positive")
    verdict = "PASS_FILTER_CANDIDATE" if not reasons else "FAIL"

    bin_rows = _descriptive_bin_rows(
        splits,
        p_by_hour=p_by_hour,
        q_by_hour=q_by_hour,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "bin_table.csv", bin_rows)
    for split, split_data in splits.items():
        _write_split_ledger(
            output_dir / f"{split}_trades.csv",
            split_data,
            original_fields,
            excluded_hours,
        )

    receipt = {
        "schema_id": "att1_seasonality_filter_receipt_v1",
        "generated_at_utc": _utc_now(),
        "research_only": True,
        "executable": False,
        "capital_authorized": False,
        "live_config_mutated": False,
        "verdict": verdict,
        "failure_reasons": sorted(set(reasons)),
        "input_manifest": {
            "trade_ledger": str(input_path.relative_to(ROOT)),
            "trade_ledger_sha256": observed_sha,
            "trades": len(rows),
            "first_entry_utc": rows[0]["_entry_dt"].isoformat(),
            "last_entry_utc": rows[-1]["_entry_dt"].isoformat(),
            "prereg": str(prereg_path.relative_to(ROOT)),
            "prereg_sha256": _sha256(prereg_path),
            "script": str(Path(__file__).resolve().relative_to(ROOT)),
            "script_sha256": _sha256(Path(__file__).resolve()),
        },
        "split_counts": {key: len(value) for key, value in splits.items()},
        "excluded_hours_utc": sorted(excluded_hours),
        "selected_discovery_rows": [
            {
                "hour_utc": hour,
                "trades": count,
                "mean_return": round(mean_return, 8),
                "p_negative": round(p_by_hour[f"{hour:02d}"], 8),
                "bh_q": round(q_value, 8),
            }
            for q_value, mean_return, hour, count in candidate_rows
        ],
        "split_results": split_results,
        "blocked_bins": prereg["blocked_bins"],
        "artifacts": {
            "bin_table": "bin_table.csv",
            "discovery_ledger": "discovery_trades.csv",
            "validation_ledger": "validation_trades.csv",
            "holdout_ledger": "holdout_trades.csv",
        },
        "exact_command": (
            ".venv/bin/python scripts/analyze_att1_seasonality_filter.py "
            "--prereg configs/preregistered/"
            "att1_seasonality_filter_v1_20260728.json "
            "--output-dir reports/research/"
            "att1_seasonality_filter_v1_20260728"
        ),
    }
    (output_dir / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    verdict_lines = [
        "# ATT1 seasonality filter v1",
        "",
        f"Verdict: **{verdict}**",
        "",
        f"- Input trades: {len(rows)}; SHA `{observed_sha}`.",
        (
            "- Split: "
            f"{len(splits['discovery'])}/"
            f"{len(splits['validation'])}/"
            f"{len(splits['holdout'])}."
        ),
        f"- Excluded UTC hours selected in discovery: {sorted(excluded_hours)}.",
        f"- Failure reasons: {sorted(set(reasons)) or ['none']}.",
        "- Funding-relative and causal regime bins remain BLOCKED_DATA.",
        "- No live config, risk, universe, signal, broker, or order mutation.",
    ]
    (output_dir / "VERDICT.md").write_text(
        "\n".join(verdict_lines) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prereg",
        default="configs/preregistered/att1_seasonality_filter_v1_20260728.json",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/research/att1_seasonality_filter_v1_20260728",
    )
    args = parser.parse_args()
    prereg = Path(args.prereg)
    if not prereg.is_absolute():
        prereg = ROOT / prereg
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    receipt = run(prereg, output_dir)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
