#!/usr/bin/env python3
"""Fail-closed data/news/cost preflight for the FX/CFD V3 research branch.

This runner intentionally does not compute strategy PnL.  The V3 configuration
is frozen before outcomes, but performance research is permitted only after all
of the following are present and hash-pinned:

* promotion-grade M5/H1 data for enough instruments;
* a historical macro-news calendar covering the research window;
* target-broker spread/commission/financing calibration.

When those inputs are absent, the only authorized output is data diagnostics.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.fx_calendar import assess_schedule_coverage  # noqa: E402
from bot.fx_instruments import get_instrument  # noqa: E402
from bot.fx_setups_v3 import (  # noqa: E402
    FailedBreakRetestShortConfig,
    HorizontalRangeConfig,
    HorizontalRangeRejectionConfig,
    RangeEdgeExpansionRetestConfig,
)
from scripts.run_fx_v2_preregistered_gate_20260711 import (  # noqa: E402
    _aggregate_h1_complete,
    _load_m5,
)


DEFAULT_CONFIG = ROOT / "configs" / "research" / "fx_v3_preflight_20260711.json"
DEFAULT_OUTPUT = ROOT / "reports" / "research" / "fx_v3_preflight_20260711"

FAMILY_CLASSES = {
    "failed_break_retest_short_v3": FailedBreakRetestShortConfig,
    "horizontal_range_rejection_v3": HorizontalRangeRejectionConfig,
    "range_edge_expansion_retest_v3": RangeEdgeExpansionRetestConfig,
}

SOURCE_PATHS = {
    "runner_sha256": "scripts/run_fx_v3_preflight_20260711.py",
    "setups_v3_sha256": "bot/fx_setups_v3.py",
    "contracts_sha256": "bot/fx_contracts.py",
    "instruments_sha256": "bot/fx_instruments.py",
    "calendar_sha256": "bot/fx_calendar.py",
    "harness_sha256": "bot/fx_harness_v2.py",
    "market_context_sha256": "bot/market_context.py",
    "range_filter_sha256": "bot/range_filter.py",
    "level_memory_sha256": "bot/level_memory.py",
    "news_session_filter_sha256": "bot/news_session_filter.py",
    "forex_regime_sha256": "forex/regime.py",
    "forex_types_sha256": "forex/types.py",
    "base_preflight_sha256": "scripts/run_fx_v2_preregistered_gate_20260711.py",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    data = [dict(row) for row in rows]
    if not data:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    for row in data:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)


def _instantiate_config(cls: type, params: Mapping[str, Any]) -> Any:
    allowed = {field.name for field in fields(cls)}
    unknown = sorted(set(params) - allowed)
    if unknown:
        raise ValueError(f"unknown {cls.__name__} fields: {unknown}")
    payload = dict(params)
    range_payload = payload.get("range")
    if range_payload is not None:
        if not isinstance(range_payload, Mapping):
            raise ValueError(f"{cls.__name__}.range must be an object")
        range_allowed = {field.name for field in fields(HorizontalRangeConfig)}
        range_unknown = sorted(set(range_payload) - range_allowed)
        if range_unknown:
            raise ValueError(f"unknown HorizontalRangeConfig fields: {range_unknown}")
        payload["range"] = HorizontalRangeConfig(**dict(range_payload))
    if "allowed_sessions" in payload:
        payload["allowed_sessions"] = tuple(payload["allowed_sessions"])
    return cls(**payload)


def validate_frozen_families(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    seen: set[str] = set()
    validated: Dict[str, Any] = {}
    for family in cfg.get("families", []):
        name = str(family.get("name", ""))
        if name not in FAMILY_CLASSES or name in seen:
            raise ValueError(f"unknown or duplicate V3 family: {name}")
        seen.add(name)
        sides = tuple(str(side) for side in family.get("sides", []))
        expected = ("short",) if name == "failed_break_retest_short_v3" else ("long", "short")
        if sides != expected:
            raise ValueError(f"{name} sides must be exactly {expected}")
        validated[name] = _instantiate_config(FAMILY_CLASSES[name], family.get("params", {}))
    if seen != set(FAMILY_CLASSES):
        raise ValueError(f"missing V3 families: {sorted(set(FAMILY_CLASSES) - seen)}")
    return validated


def external_artifact_status(root: Path, contract: Mapping[str, Any]) -> Dict[str, Any]:
    path = root / str(contract.get("path", ""))
    exists = path.is_file()
    actual = _sha256(path) if exists else ""
    expected = str(contract.get("sha256", ""))
    hash_ok = bool(exists and expected and actual == expected)
    parse_ok = False
    schema_ok = False
    coverage_ok = False
    quality_ok = False
    rows: list[Mapping[str, Any]] = []
    payload: Any = None

    if hash_ok:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            parse_ok = True
        except Exception:
            payload = None

    if parse_ok:
        if isinstance(payload, list):
            rows = [row for row in payload if isinstance(row, Mapping)]
        elif isinstance(payload, Mapping):
            collection_key = str(contract.get("collection_key", "") or "")
            candidates = [collection_key] if collection_key else []
            candidates.extend(["events", "rows", "costs", "calibrations"])
            for key in candidates:
                raw_rows = payload.get(key) if key else None
                if isinstance(raw_rows, list):
                    rows = [row for row in raw_rows if isinstance(row, Mapping)]
                    break

        required_fields = {str(field) for field in contract.get("required_fields", [])}
        min_rows = max(1, int(contract.get("min_rows", 1)))
        schema_ok = len(rows) >= min_rows and all(
            required_fields.issubset(row.keys()) for row in rows
        )

        required_start = contract.get("required_window_start_ts")
        required_end = contract.get("required_window_end_ts_exclusive")
        if required_start is None and required_end is None:
            coverage_ok = True
        elif isinstance(payload, Mapping):
            try:
                coverage_ok = (
                    int(payload.get("window_start_ts")) <= int(required_start)
                    and int(payload.get("window_end_ts_exclusive")) >= int(required_end)
                )
            except (TypeError, ValueError):
                coverage_ok = False

        min_observations = max(0, int(contract.get("min_observations_per_row", 0)))
        if min_observations:
            try:
                quality_ok = schema_ok and all(
                    int(row.get("observations", 0)) >= min_observations for row in rows
                )
            except (TypeError, ValueError):
                quality_ok = False
        else:
            quality_ok = schema_ok

    content_ok = bool(parse_ok and schema_ok and coverage_ok and quality_ok)
    return {
        "path": str(path),
        "required": bool(contract.get("required", True)),
        "exists": exists,
        "expected_sha256": expected,
        "actual_sha256": actual,
        "hash_ok": hash_ok,
        "parse_ok": parse_ok,
        "schema_ok": schema_ok,
        "coverage_ok": coverage_ok,
        "quality_ok": quality_ok,
        "rows": len(rows),
        "ok": (
            hash_ok and content_ok
            if bool(contract.get("required", True))
            else (not exists or (hash_ok and content_ok))
        ),
    }


def classify_permission(
    *,
    diagnostic_symbols: int,
    promotion_symbols: int,
    min_diagnostic_symbols: int,
    min_promotion_symbols: int,
    news_ok: bool,
    costs_ok: bool,
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if diagnostic_symbols < min_diagnostic_symbols:
        blockers.append("insufficient_diagnostic_data")
    if promotion_symbols < min_promotion_symbols:
        blockers.append("strict_promotion_data_gate_failed")
    if not news_ok:
        blockers.append("historical_news_calendar_missing_or_unpinned")
    if not costs_ok:
        blockers.append("target_broker_cost_calibration_missing_or_unpinned")
    if "insufficient_diagnostic_data" in blockers:
        return "INVALID_DATA", blockers
    if blockers:
        return "DATA_DIAGNOSTICS_ONLY", blockers
    return "PERFORMANCE_RESEARCH_ALLOWED", blockers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite evidence: {output}")
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    if not (
        cfg.get("research_only")
        and cfg.get("frozen_before_results")
        and cfg.get("no_parameter_scan")
        and cfg.get("execution_permission") == "preflight_decides"
    ):
        raise SystemExit("config must be frozen research-only/no-scan and preflight-decides")

    source_mismatches = []
    for key, rel in SOURCE_PATHS.items():
        actual = _sha256(ROOT / rel)
        expected = str(cfg.get("source_code", {}).get(key, ""))
        if not expected or expected != actual:
            source_mismatches.append(
                {"key": key, "path": rel, "expected": expected, "actual": actual}
            )
    if source_mismatches:
        raise SystemExit("source SHA256 gate failed: " + json.dumps(source_mismatches, sort_keys=True))
    validated = validate_frozen_families(cfg)
    output.mkdir(parents=True)

    data = cfg["data"]
    start = int(data["window_start_ts"])
    end = int(data["window_end_ts_exclusive"])
    as_of = int(data["snapshot_as_of_ts"])
    interval_sec = int(data["source_interval_min"]) * 60
    coverage: list[Dict[str, Any]] = []
    diagnostic_symbols: list[str] = []
    promotion_symbols: list[str] = []

    for symbol in data["symbols"]:
        spec = get_instrument(symbol)
        path = ROOT / data["data_dir"] / f"{symbol}_M5.csv"
        if not path.exists():
            coverage.append({"symbol": symbol, "diagnostic_data_ok": False, "promotion_data_ok": False, "reasons": "missing_file"})
            continue
        actual_hash = _sha256(path)
        input_hash_ok = actual_hash == str(data["input_sha256"].get(symbol, ""))
        try:
            raw = _load_m5(path)
        except ValueError as exc:
            coverage.append({
                "symbol": symbol,
                "diagnostic_data_ok": False,
                "promotion_data_ok": False,
                "input_sha256": actual_hash,
                "input_hash_ok": input_hash_ok,
                "reasons": f"loader:{exc}",
            })
            continue
        source = [row for row in raw if start <= int(row[0]) < end]
        latest = max((int(row[0]) for row in raw), default=0)
        snapshot_age_hours = max(0.0, (as_of - latest) / 3600.0)
        source_report = assess_schedule_coverage(
            source,
            symbol=symbol,
            schedule=spec.schedule,
            interval_sec=interval_sec,
            min_coverage=float(data["source_min_coverage"]),
            max_missing_run=int(data["source_max_missing_run"]),
            min_bars=int(data["source_min_bars"]),
            min_span_days=float(data["min_span_days"]),
            max_off_schedule_bars=int(data["max_off_schedule_bars"]),
            window_start_ts=start,
            window_end_ts_exclusive=end,
        )
        h1, incomplete = _aggregate_h1_complete(
            source,
            schedule=spec.schedule,
            source_interval_sec=interval_sec,
        )
        h1_report = assess_schedule_coverage(
            h1,
            symbol=symbol,
            schedule=spec.schedule,
            interval_sec=3600,
            min_coverage=float(data["h1_min_coverage"]),
            max_missing_run=int(data["h1_max_missing_run"]),
            min_bars=int(data["h1_min_bars"]),
            min_span_days=float(data["min_span_days"]),
            max_off_schedule_bars=0,
            window_start_ts=start,
            window_end_ts_exclusive=end,
        )
        snapshot_fresh = snapshot_age_hours <= float(data["max_snapshot_age_hours"])
        promotion_ok = bool(
            input_hash_ok
            and snapshot_fresh
            and source_report.ok
            and h1_report.ok
            and not incomplete
        )
        diagnostic_ok = bool(
            input_hash_ok
            and source_report.coverage >= float(data["source_min_coverage"])
            and source_report.duplicate_bars == 0
            and source_report.invalid_ohlc_bars == 0
            and source_report.actual_expected_bars >= int(data["source_min_bars"])
            and h1_report.coverage >= float(data["h1_min_coverage"])
            and h1_report.duplicate_bars == 0
            and h1_report.invalid_ohlc_bars == 0
            and h1_report.actual_expected_bars >= int(data["h1_min_bars"])
            and h1_report.span_days >= float(data["min_span_days"])
        )
        if diagnostic_ok:
            diagnostic_symbols.append(symbol)
        if promotion_ok:
            promotion_symbols.append(symbol)
        coverage.append({
            "symbol": symbol,
            "diagnostic_data_ok": diagnostic_ok,
            "promotion_data_ok": promotion_ok,
            "input_sha256": actual_hash,
            "input_hash_ok": input_hash_ok,
            "snapshot_age_hours": round(snapshot_age_hours, 3),
            "snapshot_fresh": snapshot_fresh,
            "source_coverage": source_report.coverage,
            "source_max_missing_run": source_report.max_missing_run,
            "source_off_schedule_bars": source_report.off_schedule_bars,
            "source_reasons": ";".join(source_report.reasons),
            "h1_coverage": h1_report.coverage,
            "h1_max_missing_run": h1_report.max_missing_run,
            "h1_reasons": ";".join(h1_report.reasons),
            "incomplete_h1_buckets": len(incomplete),
            "max_h1_missing_subbars": max((int(row["missing_subbars"]) for row in incomplete), default=0),
        })

    news = external_artifact_status(ROOT, cfg["historical_news"])
    costs = external_artifact_status(ROOT, cfg["broker_cost_calibration"])
    status, blockers = classify_permission(
        diagnostic_symbols=len(diagnostic_symbols),
        promotion_symbols=len(promotion_symbols),
        min_diagnostic_symbols=int(data["min_diagnostic_symbols"]),
        min_promotion_symbols=int(data["min_promotion_symbols"]),
        news_ok=bool(news["ok"]),
        costs_ok=bool(costs["ok"]),
    )
    _write_csv(output / "coverage.csv", coverage)
    preflight = {
        "status": status,
        "performance_research_allowed": status == "PERFORMANCE_RESEARCH_ALLOWED",
        "diagnostic_symbols": sorted(diagnostic_symbols),
        "promotion_symbols": sorted(promotion_symbols),
        "blocked_symbols": sorted(set(data["symbols"]) - set(promotion_symbols)),
        "historical_news": news,
        "broker_cost_calibration": costs,
        "blockers": blockers,
        "validated_families": sorted(validated),
        "candidate_sides": {
            family["name"]: family["sides"] for family in cfg["families"]
        },
        "config": str(config_path),
        "config_sha256": _sha256(config_path),
        "source_sha256": {key: _sha256(ROOT / rel) for key, rel in SOURCE_PATHS.items()},
    }
    (output / "preflight.json").write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
    summary = [
        "# FX/CFD V3 fail-closed preflight — 2026-07-11",
        "",
        f"- Status: **{status}**.",
        f"- Performance research allowed: **{str(preflight['performance_research_allowed']).lower()}**.",
        f"- Diagnostic symbols: `{','.join(sorted(diagnostic_symbols)) or 'none'}`.",
        f"- Promotion-grade symbols: `{','.join(sorted(promotion_symbols)) or 'none'}`.",
        f"- Historical news artifact valid: `{news['ok']}`.",
        f"- Target-broker cost calibration valid: `{costs['ok']}`.",
        f"- Blockers: `{';'.join(blockers) or 'none'}`.",
        "",
        "No strategy PnL, demo order, or live order is produced by this runner.",
    ]
    (output / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "blockers": blockers, "diagnostic_symbols": sorted(diagnostic_symbols)}), flush=True)
    return 2 if status == "INVALID_DATA" else 0


if __name__ == "__main__":
    raise SystemExit(main())
