#!/usr/bin/env python3
"""One-combination, research-only gate for the FX/CFD V2 branch."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from dataclasses import fields
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.fx_calendar import assess_schedule_coverage, market_is_open
from bot.fx_contracts import FxBacktestResult
from bot.fx_harness_v2 import backtest_fx_plan_strategy, summarize_fx_trades
from bot.fx_instruments import get_instrument
from bot.fx_setups_v2 import (
    ImpulseBreakoutRetestConfig,
    RegimeRangeReversionConfig,
    SweepReclaimBounceConfig,
    impulse_breakout_retest_v2,
    regime_range_reversion_v2,
    sweep_reclaim_bounce_v2,
)


DEFAULT_CONFIG = ROOT / "configs" / "research" / "fx_v2_gate_20260711.json"
DEFAULT_OUTPUT = ROOT / "reports" / "research" / "fx_v2_gate_20260711"

FAMILIES = {
    "impulse_breakout_retest_v2": (impulse_breakout_retest_v2, ImpulseBreakoutRetestConfig),
    "sweep_reclaim_bounce_v2": (sweep_reclaim_bounce_v2, SweepReclaimBounceConfig),
    "regime_range_reversion_v2": (regime_range_reversion_v2, RegimeRangeReversionConfig),
}

SOURCE_PATHS = {
    "runner_sha256": "scripts/run_fx_v2_preregistered_gate_20260711.py",
    "contracts_sha256": "bot/fx_contracts.py",
    "instruments_sha256": "bot/fx_instruments.py",
    "calendar_sha256": "bot/fx_calendar.py",
    "context_sha256": "bot/fx_context.py",
    "setups_sha256": "bot/fx_setups_v2.py",
    "harness_sha256": "bot/fx_harness_v2.py",
    "market_context_sha256": "bot/market_context.py",
    "level_memory_sha256": "bot/level_memory.py",
    "range_filter_sha256": "bot/range_filter.py",
    "liquidity_sweep_sha256": "bot/liquidity_sweep.py",
    "unified_levels_sha256": "bot/unified_levels.py",
    "failed_breakout_sha256": "bot/failed_breakout.py",
    "news_session_filter_sha256": "bot/news_session_filter.py",
    "regime_hmm_sha256": "bot/regime_hmm.py",
    "elder_filter_sha256": "bot/elder_filter.py",
    "structure_break_sha256": "bot/structure_break.py",
    "forex_regime_sha256": "forex/regime.py",
    "forex_types_sha256": "forex/types.py",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _finite(value: Any) -> Any:
    if isinstance(value, float) and math.isinf(value):
        return "inf" if value > 0 else "-inf"
    if isinstance(value, dict):
        return {str(k): _finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_finite(v) for v in value]
    return value


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


def _load_m5(path: Path) -> list[list[float]]:
    out: list[list[float]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), 2):
            try:
                values = [
                    float(row["ts"]), float(row["o"]), float(row["h"]),
                    float(row["l"]), float(row["c"]), float(row.get("v") or 0.0),
                ]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"malformed row {line_number} in {path.name}") from exc
            ts, o, h, l, c, volume = values
            if not (
                all(math.isfinite(value) for value in values)
                and ts > 0 and 0 < l <= min(o, c) <= max(o, c) <= h
                and volume >= 0
            ):
                raise ValueError(f"invalid OHLCV row {line_number} in {path.name}")
            out.append(values)
    out.sort(key=lambda row: row[0])
    return out


def _aggregate_h1_complete(
    rows: Sequence[Sequence[float]],
    *,
    schedule: str,
    source_interval_sec: int,
) -> tuple[list[list[float]], list[Dict[str, Any]]]:
    """Aggregate only hours whose every expected source bar is present."""
    out: list[list[float]] = []
    incomplete: list[Dict[str, Any]] = []
    bucket = None
    chunk: list[Sequence[float]] = []

    def flush(ts: int, source: Sequence[Sequence[float]]) -> None:
        if not source:
            return
        expected = {
            point for point in range(ts, ts + 3600, source_interval_sec)
            if market_is_open(point, schedule)
        }
        actual = {int(float(row[0])) for row in source if market_is_open(float(row[0]), schedule)}
        if actual != expected:
            incomplete.append({
                "bucket_ts": ts,
                "expected_subbars": len(expected),
                "actual_subbars": len(actual.intersection(expected)),
                "missing_subbars": len(expected - actual),
            })
            return
        out.append([
            float(ts), float(source[0][1]), max(float(r[2]) for r in source),
            min(float(r[3]) for r in source), float(source[-1][4]),
            sum(float(r[5]) if len(r) > 5 else 0.0 for r in source),
        ])

    for row in rows:
        if not market_is_open(float(row[0]), schedule):
            continue
        ts = int(float(row[0]))
        current = (ts // 3600) * 3600
        if bucket is None:
            bucket = current
        if current != bucket:
            flush(bucket, chunk)
            bucket, chunk = current, [row]
        else:
            chunk.append(row)
    if bucket is not None:
        flush(bucket, chunk)
    return out, incomplete


def _contiguous_market_segments(
    rows: Sequence[Sequence[float]], *, schedule: str
) -> list[list[Sequence[float]]]:
    """Split at missing expected market hours, but not at scheduled closures."""
    if not rows:
        return []
    segments: list[list[Sequence[float]]] = [[rows[0]]]
    for row in rows[1:]:
        previous_ts = int(float(segments[-1][-1][0]))
        current_ts = int(float(row[0]))
        missing_expected = any(
            market_is_open(ts, schedule)
            for ts in range(previous_ts + 3600, current_ts, 3600)
        )
        if current_ts <= previous_ts or missing_expected:
            segments.append([row])
        else:
            segments[-1].append(row)
    return segments


_RESULT_COUNTERS = (
    "signals", "orders_placed", "unfilled", "duplicate_events",
    "invalid_plans", "skipped_gap", "skipped_rr", "blocked_fill_window",
    "censored_orders", "censored_trades",
)


def _run_segmented(
    rows: Sequence[Sequence[float]],
    *,
    schedule: str,
    strategy: Any,
    costs: Any,
    execution_cfg: Mapping[str, Any],
) -> FxBacktestResult:
    combined = FxBacktestResult()
    warmup = int(execution_cfg["warmup_bars"])
    for segment in _contiguous_market_segments(rows, schedule=schedule):
        if len(segment) < warmup + 3:
            continue
        run = backtest_fx_plan_strategy(
            segment,
            strategy,
            costs=costs,
            warmup=warmup,
            context_bars=int(execution_cfg["context_bars"]),
            cooldown_bars=int(execution_cfg["cooldown_bars"]),
            min_structural_rr=float(execution_cfg["min_structural_rr"]),
            news_events=None,
        )
        combined.trades.extend(run.trades)
        combined.signal_ledger.extend(run.signal_ledger)
        for name in _RESULT_COUNTERS:
            setattr(combined, name, int(getattr(combined, name)) + int(getattr(run, name)))
    return combined


def _config_instance(cls: type, values: Mapping[str, Any]) -> Any:
    allowed = {field.name for field in fields(cls)}
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(f"unknown {cls.__name__} fields: {unknown}")
    payload = dict(values)
    if "allowed_sessions" in payload:
        payload["allowed_sessions"] = tuple(payload["allowed_sessions"])
    return cls(**payload)


def _pf(rs: Sequence[float]) -> float:
    gp = sum(x for x in rs if x > 0)
    gl = -sum(x for x in rs if x < 0)
    return gp / gl if gl > 0 else (float("inf") if gp > 0 else 0.0)


def _fixed_time_folds(trades: Sequence[Dict[str, Any]], edges: Sequence[float], embargo_sec: float) -> list[Dict[str, Any]]:
    out: list[Dict[str, Any]] = []
    for index, (lo, hi) in enumerate(zip(edges, edges[1:]), 1):
        selected = [
            trade for trade in trades
            if float(trade["entry_ts"]) >= lo + embargo_sec
            and float(trade["entry_ts"]) < hi
            and float(trade["exit_ts"]) <= hi
        ]
        rs = [float(trade["r"]) for trade in selected]
        out.append({
            "fold": index,
            "start_ts": lo,
            "end_ts": hi,
            "trades": len(rs),
            "net_r": round(sum(rs), 6),
            "pf": _pf(rs),
        })
    return out


def _candidate_verdict(
    *,
    candidate: str,
    expected_side: str,
    trades: Sequence[Dict[str, Any]],
    signal_ledger: Sequence[Dict[str, Any]],
    holdout_trades: Sequence[Dict[str, Any]],
    folds: Sequence[Dict[str, Any]],
    symbol_rows: Sequence[Dict[str, Any]],
    diagnostics: Dict[str, Any],
    gates: Mapping[str, Any],
    blockers: Sequence[str],
) -> Dict[str, Any]:
    summary = summarize_fx_trades(trades)
    holdout = dict(folds[-1]) if folds else {"trades": 0, "net_r": 0.0, "pf": 0.0}
    positive_folds = sum(1 for row in folds if row["trades"] > 0 and row["net_r"] > 0 and float(row["pf"]) >= 1.0)
    traded_symbols = sum(1 for row in symbol_rows if int(row["trades"]) > 0)
    positive_symbols = sum(1 for row in symbol_rows if int(row["trades"]) > 0 and float(row["net_r"]) > 0)
    positive_net = {
        str(row["symbol"]): max(0.0, float(row["net_r"])) for row in symbol_rows
    }
    total_positive_net = sum(positive_net.values())
    concentration = (
        max(positive_net.values() or [0.0]) / total_positive_net
        if total_positive_net > 0 else 1.0
    )
    holdout_symbols = sorted({str(trade["symbol"]) for trade in holdout_trades})
    holdout_symbol_rows = []
    for symbol in holdout_symbols:
        part = [trade for trade in holdout_trades if str(trade["symbol"]) == symbol]
        holdout_symbol_rows.append({"symbol": symbol, **summarize_fx_trades(part)})
    holdout_positive = sum(1 for row in holdout_symbol_rows if float(row["net_r"]) > 0)
    holdout_positive_net = [max(0.0, float(row["net_r"])) for row in holdout_symbol_rows]
    holdout_total_positive = sum(holdout_positive_net)
    holdout_concentration = (
        max(holdout_positive_net or [0.0]) / holdout_total_positive
        if holdout_total_positive > 0 else 1.0
    )
    loso_rows: list[Dict[str, Any]] = []
    traded_symbol_names = [str(row["symbol"]) for row in symbol_rows if int(row["trades"]) > 0]
    for removed in traded_symbol_names:
        remaining = [trade for trade in trades if str(trade["symbol"]) != removed]
        metric = summarize_fx_trades(remaining)
        passed = (
            int(metric["trades"]) >= int(gates["loso_min_trades"])
            and float(metric["net_r"]) > 0
            and float(metric["pf"]) >= float(gates["loso_min_pf"])
        )
        loso_rows.append({"removed_symbol": removed, "passed": passed, **_finite(metric)})
    loso_pass_ratio = (
        sum(1 for row in loso_rows if row["passed"]) / len(loso_rows)
        if loso_rows else 0.0
    )
    duplicate_rate = float(diagnostics.get("duplicate_event_rate", 0.0))
    fill_rate = float(diagnostics.get("fill_rate", 0.0))
    order_count = max(1, int(diagnostics.get("orders_placed", 0)))
    skipped_gap_rate = float(diagnostics.get("skipped_gap", 0)) / order_count
    blocked_fill_rate = float(diagnostics.get("blocked_fill_window", 0)) / order_count
    censored_order_rate = float(diagnostics.get("censored_orders", 0)) / order_count
    completed_or_censored = len(trades) + int(diagnostics.get("censored_trades", 0))
    censored_trade_rate = (
        float(diagnostics.get("censored_trades", 0)) / completed_or_censored
        if completed_or_censored else 0.0
    )
    unfilled_rate = (
        float(diagnostics.get("unfilled", 0))
        / float(int(diagnostics.get("orders_placed", 0)) - int(diagnostics.get("censored_orders", 0)))
        if int(diagnostics.get("orders_placed", 0)) > int(diagnostics.get("censored_orders", 0))
        else 1.0
    )
    side_pure = all(str(row.get("side")) == expected_side for row in signal_ledger)
    reasons: list[str] = []
    checks = {
        "stress_min_trades": int(summary["trades"]) >= int(gates["stress_min_trades"]),
        "stress_min_pf": float(summary["pf"]) >= float(gates["stress_min_pf"]),
        "stress_net_positive": float(summary["net_r"]) > 0,
        "closed_trade_dd_diagnostic": float(summary["closed_trade_drawdown_r"]) <= float(gates["max_closed_trade_drawdown_r"]),
        "positive_folds": positive_folds >= int(gates["min_positive_folds"]),
        "min_fold_trades": min((int(row["trades"]) for row in folds), default=0) >= int(gates["min_fold_trades"]),
        "holdout_min_trades": int(holdout["trades"]) >= int(gates["holdout_min_trades"]),
        "holdout_pf": float(holdout["pf"]) >= float(gates["holdout_min_pf"]),
        "holdout_net_positive": float(holdout["net_r"]) > 0,
        "symbol_breadth": traded_symbols >= int(gates["min_traded_symbols"]),
        "positive_symbols": positive_symbols >= int(gates["min_positive_symbols"]),
        "profit_concentration": concentration < float(gates["max_profit_concentration"]),
        "holdout_symbol_breadth": len(holdout_symbols) >= int(gates["holdout_min_traded_symbols"]),
        "holdout_positive_symbols": holdout_positive >= int(gates["holdout_min_positive_symbols"]),
        "holdout_profit_concentration": holdout_concentration < float(gates["holdout_max_profit_concentration"]),
        "loso_robustness": loso_pass_ratio >= float(gates["min_loso_pass_ratio"]),
        "side_purity_all_plans": side_pure,
        "invalid_plans_zero": int(diagnostics.get("invalid_plans", 0)) == 0,
        "duplicate_event_rate": duplicate_rate <= float(gates["max_duplicate_event_rate"]),
        "min_fill_rate": fill_rate >= float(gates["min_fill_rate"]),
        "max_unfilled_rate": unfilled_rate <= float(gates["max_unfilled_rate"]),
        "skipped_rr_zero": int(diagnostics.get("skipped_rr", 0)) == 0,
        "max_skipped_gap_rate": skipped_gap_rate <= float(gates["max_skipped_gap_rate"]),
        "max_blocked_fill_rate": blocked_fill_rate <= float(gates["max_blocked_fill_rate"]),
        "max_censored_order_rate": censored_order_rate <= float(gates["max_censored_order_rate"]),
        "max_censored_trade_rate": censored_trade_rate <= float(gates["max_censored_trade_rate"]),
    }
    reasons.extend(key for key, passed in checks.items() if not passed)
    quant_pass = not reasons
    status = "NO_PROMOTION"
    if quant_pass and blockers:
        status = "RESEARCH_PASS_SHADOW_BLOCKED"
    elif quant_pass:
        status = "SHADOW_ELIGIBLE_NOT_LIVE"
    return {
        "candidate": candidate,
        "status": status,
        "quantitative_pass": quant_pass,
        "promotion_to_live": False,
        "reasons": reasons,
        "promotion_blockers": list(blockers),
        "checks": checks,
        "stress": _finite(summary),
        "holdout": _finite(holdout),
        "positive_folds": positive_folds,
        "traded_symbols": traded_symbols,
        "positive_symbols": positive_symbols,
        "profit_concentration": round(concentration, 6),
        "concentration_basis": "positive_net_symbol_contribution",
        "holdout_traded_symbols": len(holdout_symbols),
        "holdout_positive_symbols": holdout_positive,
        "holdout_profit_concentration": round(holdout_concentration, 6),
        "loso_pass_ratio": round(loso_pass_ratio, 6),
        "loso": loso_rows,
        "diagnostics": diagnostics,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite evidence: {output}")
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    if not cfg.get("research_only") or not cfg.get("no_parameter_scan"):
        raise SystemExit("config must be research_only and no_parameter_scan")
    mismatches = []
    for key, rel in SOURCE_PATHS.items():
        actual = _sha256(ROOT / rel)
        expected = str(cfg.get("source_code", {}).get(key, ""))
        if actual != expected:
            mismatches.append({"key": key, "path": rel, "expected": expected, "actual": actual})
    if mismatches:
        raise SystemExit("source SHA256 gate failed: " + json.dumps(mismatches, sort_keys=True))
    output.mkdir(parents=True)

    data_cfg = cfg["data"]
    window_start = int(data_cfg["window_start_ts"])
    window_end = int(data_cfg["window_end_ts_exclusive"])
    snapshot_as_of = int(data_cfg["snapshot_as_of_ts"])
    source_interval_sec = int(data_cfg["source_interval_min"]) * 60
    coverage_rows: list[Dict[str, Any]] = []
    rows_by_symbol: Dict[str, list[list[float]]] = {}
    promotion_valid_symbols: set[str] = set()
    actual_input_hashes: Dict[str, str] = {}
    for symbol in data_cfg["symbols"]:
        spec = get_instrument(symbol)
        path = ROOT / data_cfg["data_dir"] / f"{symbol}_M5.csv"
        if not path.exists():
            coverage_rows.append({"symbol": symbol, "ok": False, "reasons": "missing_file"})
            continue
        input_sha = _sha256(path)
        actual_input_hashes[symbol] = input_sha
        expected_input_sha = str(data_cfg["input_sha256"].get(symbol, ""))
        input_hash_ok = input_sha == expected_input_sha
        try:
            raw_source_rows = _load_m5(path)
        except ValueError as exc:
            coverage_rows.append({
                "symbol": symbol, "ok": False, "promotion_data_ok": False,
                "diagnostic_data_ok": False, "input_sha256": input_sha,
                "input_hash_ok": input_hash_ok, "loader_error": str(exc),
            })
            continue
        source_rows = [
            row for row in raw_source_rows
            if window_start <= int(float(row[0])) < window_end
        ]
        last_source_ts = max((int(float(row[0])) for row in raw_source_rows), default=0)
        snapshot_age_hours = max(0.0, (snapshot_as_of - last_source_ts) / 3600.0)
        snapshot_fresh = snapshot_age_hours <= float(data_cfg["max_snapshot_age_hours"])
        source_report = assess_schedule_coverage(
            source_rows,
            symbol=symbol,
            schedule=spec.schedule,
            interval_sec=source_interval_sec,
            min_coverage=float(data_cfg["source_min_coverage"]),
            max_missing_run=int(data_cfg["source_max_missing_run"]),
            min_bars=int(data_cfg["source_min_bars"]),
            min_span_days=float(data_cfg["min_span_days"]),
            max_off_schedule_bars=int(data_cfg["max_off_schedule_bars"]),
            window_start_ts=window_start,
            window_end_ts_exclusive=window_end,
        )
        rows, incomplete_h1 = _aggregate_h1_complete(
            source_rows,
            schedule=spec.schedule,
            source_interval_sec=source_interval_sec,
        )
        h1_report = assess_schedule_coverage(
            rows,
            symbol=symbol,
            schedule=spec.schedule,
            interval_sec=3600,
            min_coverage=float(data_cfg["h1_min_coverage"]),
            max_missing_run=int(data_cfg["h1_max_missing_run"]),
            min_bars=int(data_cfg["h1_min_bars"]),
            min_span_days=float(data_cfg["min_span_days"]),
            max_off_schedule_bars=0,
            window_start_ts=window_start,
            window_end_ts_exclusive=window_end,
        )
        # Source M5 is checked before aggregation so an H1 bar assembled from
        # one or two surviving sub-bars cannot disguise a broken feed.
        promotion_data_ok = (
            input_hash_ok and snapshot_fresh and source_report.ok
            and h1_report.ok and not incomplete_h1
        )
        diagnostic_data_ok = (
            input_hash_ok
            and source_report.coverage >= float(data_cfg["source_min_coverage"])
            and source_report.duplicate_bars == 0
            and source_report.invalid_ohlc_bars == 0
            and source_report.actual_expected_bars >= int(data_cfg["source_min_bars"])
            and h1_report.coverage >= float(data_cfg["h1_min_coverage"])
            and h1_report.duplicate_bars == 0
            and h1_report.invalid_ohlc_bars == 0
            and h1_report.actual_expected_bars >= int(data_cfg["h1_min_bars"])
            and h1_report.span_days >= float(data_cfg["min_span_days"])
        )
        record: Dict[str, Any] = {
            "symbol": symbol,
            "ok": promotion_data_ok,
            "promotion_data_ok": promotion_data_ok,
            "diagnostic_data_ok": diagnostic_data_ok,
            "input_sha256": input_sha,
            "input_hash_ok": input_hash_ok,
            "snapshot_age_hours": round(snapshot_age_hours, 3),
            "snapshot_fresh": snapshot_fresh,
            "incomplete_h1_buckets": len(incomplete_h1),
            "max_h1_missing_subbars": max(
                (int(row["missing_subbars"]) for row in incomplete_h1), default=0
            ),
            "incomplete_h1_examples": json.dumps(incomplete_h1[:20], sort_keys=True),
        }
        for prefix, report in (("source", source_report), ("h1", h1_report)):
            payload = report.to_dict()
            payload["reasons"] = ";".join(report.reasons)
            payload["largest_missing_runs"] = json.dumps(report.largest_missing_runs, sort_keys=True)
            record.update({f"{prefix}_{key}": value for key, value in payload.items() if key != "symbol"})
        coverage_rows.append(record)
        if promotion_data_ok:
            promotion_valid_symbols.add(symbol)
        if diagnostic_data_ok:
            rows_by_symbol[symbol] = rows
    _write_csv(output / "coverage.csv", coverage_rows)
    if len(rows_by_symbol) < int(data_cfg["min_diagnostic_symbols"]):
        verdict = {
            "status": "INVALID_DATA",
            "diagnostic_symbols": sorted(rows_by_symbol),
            "promotion_valid_symbols": sorted(promotion_valid_symbols),
        }
        (output / "verdict.json").write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(verdict), flush=True)
        return 2
    if args.preflight_only:
        preflight = {
            "status": (
                "PROMOTION_DATA_PASS"
                if len(promotion_valid_symbols) >= int(data_cfg["min_promotion_symbols"])
                else "DIAGNOSTIC_ONLY"
            ),
            "source_hashes": True,
            "diagnostic_symbols": sorted(rows_by_symbol),
            "promotion_valid_symbols": sorted(promotion_valid_symbols),
            "data_blocked_symbols": sorted(set(data_cfg["symbols"]) - promotion_valid_symbols),
        }
        (output / "preflight.json").write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(preflight), flush=True)
        return 0

    span = (window_end - window_start) / 4.0
    fold_edges = [window_start + index * span for index in range(5)]
    blockers = list(cfg.get("promotion_blockers", []))
    if len(promotion_valid_symbols) < int(data_cfg["min_promotion_symbols"]):
        blockers.append("strict_promotion_data_gate_failed")
    all_trades: list[Dict[str, Any]] = []
    all_signals: list[Dict[str, Any]] = []
    candidate_rows: list[Dict[str, Any]] = []
    fold_rows: list[Dict[str, Any]] = []
    symbol_metric_rows: list[Dict[str, Any]] = []
    verdicts: Dict[str, Any] = {}
    diagnostics_rows: list[Dict[str, Any]] = []

    for family_cfg in cfg["families"]:
        family = str(family_cfg["name"])
        setup_fn, config_cls = FAMILIES[family]
        strategy_cfg = _config_instance(config_cls, family_cfg["params"])
        for side in ("long", "short"):
            candidate = f"{family}:{side}"
            base_candidate: list[Dict[str, Any]] = []
            stress_candidate: list[Dict[str, Any]] = []
            stress_signal_ledger: list[Dict[str, Any]] = []
            diag_total = {
                "signals": 0, "orders_placed": 0, "unfilled": 0,
                "duplicate_events": 0, "invalid_plans": 0,
                "skipped_gap": 0, "skipped_rr": 0,
                "blocked_fill_window": 0,
                "censored_orders": 0, "censored_trades": 0,
            }
            for symbol, rows in rows_by_symbol.items():
                spec = get_instrument(symbol)
                strategy = partial(
                    setup_fn,
                    instrument=spec,
                    side_mode=side,
                    cfg=strategy_cfg,
                    events=None,
                )
                base_run = _run_segmented(
                    rows, schedule=spec.schedule, strategy=strategy,
                    costs=spec.base_costs, execution_cfg=cfg["execution"],
                )
                stress_run = _run_segmented(
                    rows, schedule=spec.schedule, strategy=strategy,
                    costs=spec.stress_costs, execution_cfg=cfg["execution"],
                )
                base = [dict(trade, symbol=symbol, candidate=candidate, scenario="base") for trade in base_run.trades]
                stress = [dict(trade, symbol=symbol, candidate=candidate, scenario="stress") for trade in stress_run.trades]
                base_candidate.extend(base)
                stress_candidate.extend(stress)
                base_signals = [
                    dict(row, symbol=symbol, candidate=candidate, scenario="base")
                    for row in base_run.signal_ledger
                ]
                stress_signals = [
                    dict(row, symbol=symbol, candidate=candidate, scenario="stress")
                    for row in stress_run.signal_ledger
                ]
                all_signals.extend(base_signals)
                all_signals.extend(stress_signals)
                stress_signal_ledger.extend(stress_signals)
                for key in _RESULT_COUNTERS:
                    diag_total[key] += int(getattr(stress_run, key))
                diagnostics_rows.append({
                    "candidate": candidate, "symbol": symbol, "scenario": "base",
                    **base_run.diagnostics(),
                })
                diagnostics_rows.append({
                    "candidate": candidate, "symbol": symbol, "scenario": "stress",
                    **stress_run.diagnostics(),
                })
            diag_total["duplicate_event_rate"] = (
                diag_total["duplicate_events"] / diag_total["signals"]
                if diag_total["signals"] else 0.0
            )
            diag_total["fill_rate"] = (
                (len(stress_candidate) + diag_total["censored_trades"])
                / (diag_total["orders_placed"] - diag_total["censored_orders"])
                if diag_total["orders_placed"] > diag_total["censored_orders"] else 0.0
            )
            base_candidate.sort(key=lambda row: (row["entry_ts"], row["symbol"]))
            stress_candidate.sort(key=lambda row: (row["entry_ts"], row["symbol"]))
            all_trades.extend(base_candidate)
            all_trades.extend(stress_candidate)
            base_summary = summarize_fx_trades(base_candidate)
            stress_summary = summarize_fx_trades(stress_candidate)
            folds = _fixed_time_folds(
                stress_candidate,
                fold_edges,
                float(cfg["execution"]["embargo_hours"]) * 3600.0,
            )
            holdout_trades = [
                trade for trade in stress_candidate
                if float(trade["entry_ts"]) >= fold_edges[-2] + float(cfg["execution"]["embargo_hours"]) * 3600.0
                and float(trade["entry_ts"]) < fold_edges[-1]
                and float(trade["exit_ts"]) <= fold_edges[-1]
            ]
            for row in folds:
                fold_rows.append({"candidate": candidate, **_finite(row)})
            per_symbol: list[Dict[str, Any]] = []
            for symbol in rows_by_symbol:
                part = [trade for trade in stress_candidate if trade["symbol"] == symbol]
                metric = summarize_fx_trades(part)
                record = {"candidate": candidate, "symbol": symbol, **_finite(metric)}
                per_symbol.append(record)
                symbol_metric_rows.append(record)
            verdict = _candidate_verdict(
                candidate=candidate,
                expected_side=side,
                trades=stress_candidate,
                signal_ledger=stress_signal_ledger,
                holdout_trades=holdout_trades,
                folds=folds,
                symbol_rows=per_symbol,
                diagnostics=diag_total,
                gates=cfg["gates"],
                blockers=blockers,
            )
            verdicts[candidate] = verdict
            candidate_rows.append({
                "candidate": candidate,
                "status": verdict["status"],
                **{f"base_{key}": value for key, value in _finite(base_summary).items()},
                **{f"stress_{key}": value for key, value in _finite(stress_summary).items()},
                "positive_folds": verdict["positive_folds"],
                "traded_symbols": verdict["traded_symbols"],
                "positive_symbols": verdict["positive_symbols"],
                "profit_concentration": verdict["profit_concentration"],
                "holdout_traded_symbols": verdict["holdout_traded_symbols"],
                "loso_pass_ratio": verdict["loso_pass_ratio"],
                "reasons": ";".join(verdict["reasons"]),
                "promotion_blockers": ";".join(verdict["promotion_blockers"]),
            })
            print(
                f"{candidate} status={verdict['status']} N={stress_summary['trades']} "
                f"netR={stress_summary['net_r']} PF={stress_summary['pf']}",
                flush=True,
            )

    for trade in all_trades:
        trade["metadata"] = json.dumps(_finite(trade.get("metadata", {})), sort_keys=True)
    _write_csv(output / "trades.csv", [_finite(row) for row in all_trades])
    _write_csv(output / "signals.csv", [_finite(row) for row in all_signals])
    _write_csv(output / "candidates.csv", candidate_rows)
    _write_csv(output / "folds.csv", fold_rows)
    _write_csv(output / "symbols.csv", symbol_metric_rows)
    _write_csv(output / "diagnostics.csv", diagnostics_rows)
    final = {
        "status": "NO_LIVE_PROMOTION",
        "evidence_class": "diagnostic" if blockers else "promotion_grade",
        "diagnostic_symbols": sorted(rows_by_symbol),
        "promotion_valid_symbols": sorted(promotion_valid_symbols),
        "data_blocked_symbols": sorted(set(data_cfg["symbols"]) - promotion_valid_symbols),
        "candidate_verdicts": verdicts,
        "promotion_blockers": blockers,
    }
    (output / "verdict.json").write_text(
        json.dumps(_finite(final), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "experiment_id": cfg["experiment_id"],
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": str(config_path),
        "config_sha256": _sha256(config_path),
        "source_sha256": {key: _sha256(ROOT / rel) for key, rel in SOURCE_PATHS.items()},
        "input_data_sha256": {
            symbol: actual_input_hashes.get(symbol, "missing") for symbol in data_cfg["symbols"]
        },
        "expected_input_data_sha256": dict(data_cfg["input_sha256"]),
        "frozen_window": {
            "start_ts": window_start,
            "end_ts_exclusive": window_end,
        },
        "parameter_combinations_per_candidate": 1,
        "research_only": True,
        "broker_calls": False,
        "network_calls": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# FX/CFD V2 preregistered research gate — 2026-07-11",
        "",
        f"- Final status: **{final['status']}**.",
        f"- Evidence class: **{final['evidence_class']}** (never promotion-grade while blockers remain).",
        f"- Diagnostic data: `{','.join(final['diagnostic_symbols'])}`.",
        f"- Promotion-valid data: `{','.join(final['promotion_valid_symbols']) or 'none'}`.",
        f"- Data-blocked: `{','.join(final['data_blocked_symbols']) or 'none'}`.",
        "- Every family is evaluated as separate long-only and short-only sleeves.",
        "- Signals use H1 close decision time; fills are rechecked by session/news window.",
        "- Synthetic bid/ask barriers are rerun independently under base and stress spread.",
        "- Incomplete H1 bars are removed and every unknown market-hours gap resets warmup/positions.",
        f"- Promotion blockers: `{'; '.join(blockers) or 'none'}`.",
        "",
        "| candidate | status | stress N | stress netR | stress PF | folds+ | symbols+ | concentration |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in candidate_rows:
        lines.append(
            f"| {row['candidate']} | {row['status']} | {row['stress_trades']} | "
            f"{row['stress_net_r']} | {row['stress_pf']} | {row['positive_folds']}/4 | "
            f"{row['positive_symbols']}/{row['traded_symbols']} | {row['profit_concentration']:.3f} |"
        )
    lines += [
        "",
        "Closed-trade drawdown is diagnostic only; portfolio mark-to-market/correlation risk is a blocker.",
        "A quantitative PASS would still be shadow-blocked until historical news, broker costs, DST/holiday contract, native bid/ask parity and independent-feed parity are complete.",
        "No result in this report authorizes demo orders or live capital.",
    ]
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
