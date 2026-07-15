#!/usr/bin/env python3
"""Run the bounded, discovery-only multi-coin H1 Pattern Atlas v1.

The runner deliberately stops decoding each immutable source before the
120-day sealed holdout.  It reports conditional forward paths, not trades,
and it cannot promote a strategy or call an exchange.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.closed_bar_aggregation_v1 import (  # noqa: E402
    ClosedBarAggregationConfigV1,
    aggregate_closed_m5_bars,
)
from scripts.validate_event_long_dev13_uniform_window_v1 import (  # noqa: E402
    UniformWindowError,
    sha256_file,
    validate_uniform_window_manifest,
)


DEFAULT_CONFIG = ROOT / "configs/preregistered/multicoin_pattern_atlas_v1_20260715.json"
H1_MS = 3_600_000
DAY_MS = 86_400_000
M5_MS = 300_000
EXPECTED_KIND = "multicoin_pattern_atlas_v1_preregistration"
EXPECTED_PATTERN_SIDES = {
    "horizontal_breakout_long": "long",
    "horizontal_breakout_short": "short",
    "failed_break_reversal_long": "long",
    "failed_break_reversal_short": "short",
    "horizontal_rejection_long": "long",
    "horizontal_rejection_short": "short",
}


class PatternAtlasError(ValueError):
    """The frozen contract or discovery evidence is invalid."""


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _repo_path(root: Path, raw: object) -> Path:
    relative = Path(str(raw or ""))
    if not str(raw or "") or relative.is_absolute() or ".." in relative.parts:
        raise PatternAtlasError(f"unsafe repo-relative path: {raw!r}")
    path = root.resolve().joinpath(relative)
    if path.is_symlink() or not path.is_file():
        raise PatternAtlasError(f"required regular file is missing: {relative}")
    return path


def _utc_label(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def load_preregistration(root: Path, config_path: Path) -> dict[str, Any]:
    """Load and fail-closed validate the small frozen hypothesis family."""
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PatternAtlasError(f"invalid preregistration JSON: {exc}") from exc
    if not isinstance(config, dict):
        raise PatternAtlasError("preregistration root must be an object")
    fingerprint = config.get("preregistration_fingerprint_sha256")
    frozen = dict(config)
    frozen.pop("preregistration_fingerprint_sha256", None)
    if fingerprint != _canonical_sha256(frozen):
        raise PatternAtlasError("preregistration fingerprint mismatch")
    if config.get("schema_version") != 1 or config.get("kind") != EXPECTED_KIND:
        raise PatternAtlasError("preregistration schema/kind mismatch")
    if not all(config.get(key) is True for key in ("research_only", "discovery_only")):
        raise PatternAtlasError("research_only and discovery_only must remain true")
    if any(config.get(key) is not False for key in (
        "promotion_eligible", "parameter_search", "live_or_broker_calls"
    )):
        raise PatternAtlasError("promotion/search/live flags must remain false")

    patterns = config.get("patterns")
    if not isinstance(patterns, list):
        raise PatternAtlasError("patterns must be a frozen list")
    identities = {str(item.get("id")): str(item.get("side")) for item in patterns if isinstance(item, dict)}
    if identities != EXPECTED_PATTERN_SIDES or len(patterns) != len(EXPECTED_PATTERN_SIDES):
        raise PatternAtlasError("the exact six physical-side hypotheses are required")

    event = config.get("event_contract")
    if not isinstance(event, dict):
        raise PatternAtlasError("event contract is missing")
    if event.get("forward_horizons_h1") != [6, 24, 72, 168]:
        raise PatternAtlasError("forward horizons changed")
    if int(event.get("same_pattern_cooldown_h1", 0)) < 168:
        raise PatternAtlasError("same-pattern cooldown must cover the longest horizon")
    if event.get("entry_time") != "next_H1_open" or event.get("gross_paths_only") is not True:
        raise PatternAtlasError("next-open gross-path contract changed")

    data = config.get("data_contract")
    aggregation = config.get("aggregation_contract")
    if not isinstance(data, dict) or not isinstance(aggregation, dict):
        raise PatternAtlasError("data/aggregation contracts are missing")
    uniform_path = _repo_path(root, data.get("uniform_manifest_path"))
    if sha256_file(uniform_path) != data.get("uniform_manifest_sha256"):
        raise PatternAtlasError("uniform-window manifest pin changed")
    aggregation_path = _repo_path(root, aggregation.get("path"))
    if sha256_file(aggregation_path) != aggregation.get("sha256"):
        raise PatternAtlasError("closed-bar aggregation pin changed")
    if int(data.get("holdout_days", 0)) != 120:
        raise PatternAtlasError("sealed holdout must remain exactly 120 days")
    return config


def discovery_end_exclusive(window_end_exclusive: int, holdout_days: int = 120) -> int:
    """Return the complete-H1 boundary strictly before the sealed holdout."""
    raw_cutoff = int(window_end_exclusive) - int(holdout_days) * DAY_MS
    cutoff = (raw_cutoff // H1_MS) * H1_MS
    if cutoff <= 0 or cutoff > window_end_exclusive:
        raise PatternAtlasError("invalid discovery/holdout boundary")
    return cutoff


def _iter_json_array_objects(path: Path, *, chunk_size: int = 64 * 1024) -> Iterator[Any]:
    """Incrementally decode a JSON array, permitting an early sealed stop."""
    decoder = json.JSONDecoder()
    with path.open("r", encoding="utf-8") as handle:
        buffer = ""
        pos = 0
        eof = False

        def fill() -> bool:
            nonlocal buffer, pos, eof
            if eof:
                return False
            if pos:
                buffer = buffer[pos:]
                pos = 0
            chunk = handle.read(chunk_size)
            if not chunk:
                eof = True
                return False
            buffer += chunk
            return True

        while not buffer and fill():
            pass
        while True:
            while pos >= len(buffer) and fill():
                pass
            while pos < len(buffer) and buffer[pos].isspace():
                pos += 1
            if pos < len(buffer):
                break
            if not fill():
                raise PatternAtlasError(f"empty JSON source: {path}")
        if buffer[pos] != "[":
            raise PatternAtlasError(f"source is not a JSON array: {path}")
        pos += 1
        first = True
        while True:
            while True:
                while pos < len(buffer) and buffer[pos].isspace():
                    pos += 1
                if pos < len(buffer):
                    break
                if not fill():
                    raise PatternAtlasError(f"unterminated JSON array: {path}")
            if buffer[pos] == "]":
                return
            if not first:
                if buffer[pos] != ",":
                    raise PatternAtlasError(f"expected array delimiter in {path}")
                pos += 1
                while True:
                    while pos < len(buffer) and buffer[pos].isspace():
                        pos += 1
                    if pos < len(buffer):
                        break
                    if not fill():
                        raise PatternAtlasError(f"unterminated JSON array: {path}")
            while True:
                try:
                    value, end = decoder.raw_decode(buffer, pos)
                    pos = end
                    break
                except json.JSONDecodeError as exc:
                    if not fill():
                        raise PatternAtlasError(f"invalid JSON source {path}: {exc}") from exc
            first = False
            yield value


def load_discovery_m5_rows(
    path: Path,
    *,
    start_ts: int,
    discovery_end_ts_exclusive: int,
) -> list[tuple[int, float, float, float, float, float]]:
    """Decode exactly the discovery prefix and never decode the sealed tail."""
    if start_ts % H1_MS or discovery_end_ts_exclusive % H1_MS:
        raise PatternAtlasError("discovery crop must use complete H1 boundaries")
    expected = (discovery_end_ts_exclusive - start_ts) // M5_MS
    if expected <= 0:
        raise PatternAtlasError("discovery crop is empty")
    iterator = _iter_json_array_objects(path)
    rows: list[tuple[int, float, float, float, float, float]] = []
    try:
        for index in range(expected):
            try:
                raw = next(iterator)
            except StopIteration as exc:
                raise PatternAtlasError(f"discovery prefix ended at row {index}, expected {expected}") from exc
            if not isinstance(raw, Mapping) or set(raw) != {"ts", "o", "h", "l", "c", "v"}:
                raise PatternAtlasError(f"non-canonical M5 row at discovery index {index}")
            try:
                ts = int(raw["ts"])
                o, h, low, c, volume = (float(raw[key]) for key in ("o", "h", "l", "c", "v"))
            except (TypeError, ValueError, OverflowError) as exc:
                raise PatternAtlasError(f"non-numeric M5 row at discovery index {index}") from exc
            expected_ts = start_ts + index * M5_MS
            if ts != expected_ts:
                raise PatternAtlasError(f"non-contiguous discovery prefix: expected {expected_ts}, got {ts}")
            if not all(math.isfinite(value) for value in (o, h, low, c, volume)):
                raise PatternAtlasError(f"non-finite M5 row at discovery index {index}")
            if min(o, h, low, c) <= 0 or volume < 0 or h < max(o, c) or low > min(o, c):
                raise PatternAtlasError(f"invalid M5 OHLCV geometry at discovery index {index}")
            rows.append((ts, o, h, low, c, volume))
    finally:
        iterator.close()
    return rows


def detect_pattern_ids(
    bars: Sequence[Sequence[float]],
    index: int,
    *,
    lookback: int = 20,
    touch_tolerance_bps: float = 10.0,
    minimum_wick_to_body_ratio: float = 1.5,
) -> tuple[str, ...]:
    """Detect the exact causal six-pattern family at one completed H1 bar."""
    if index < lookback or index >= len(bars):
        return ()
    current = bars[index]
    prior = bars[index - lookback:index]
    prior_high = max(float(bar[2]) for bar in prior)
    prior_low = min(float(bar[3]) for bar in prior)
    o, h, low, c = (float(current[position]) for position in (1, 2, 3, 4))
    tolerance = touch_tolerance_bps / 10_000.0
    body = max(abs(c - o), c * 1e-12)
    lower_wick = min(o, c) - low
    upper_wick = h - max(o, c)
    found: list[str] = []
    if o <= prior_high and c > prior_high:
        found.append("horizontal_breakout_long")
    if o >= prior_low and c < prior_low:
        found.append("horizontal_breakout_short")
    if low < prior_low and c >= prior_low and c > o:
        found.append("failed_break_reversal_long")
    if h > prior_high and c <= prior_high and c < o:
        found.append("failed_break_reversal_short")
    if (
        low <= prior_low * (1.0 + tolerance)
        and c > prior_low
        and c > o
        and lower_wick >= minimum_wick_to_body_ratio * body
    ):
        found.append("horizontal_rejection_long")
    if (
        h >= prior_high * (1.0 - tolerance)
        and c < prior_high
        and c < o
        and upper_wick >= minimum_wick_to_body_ratio * body
    ):
        found.append("horizontal_rejection_short")
    return tuple(found)


def forward_path(
    bars: Sequence[Sequence[float]],
    *,
    signal_index: int,
    horizon_h1: int,
    side: str,
) -> dict[str, float | int]:
    """Measure a gross path from the next H1 open without future features."""
    entry_index = signal_index + 1
    final_index = entry_index + int(horizon_h1) - 1
    if signal_index < 0 or final_index >= len(bars):
        raise PatternAtlasError("forward horizon crosses the available discovery evidence")
    if side not in {"long", "short"}:
        raise PatternAtlasError("physical side must be long or short")
    segment = bars[entry_index:final_index + 1]
    entry = float(segment[0][1])
    exit_price = float(segment[-1][4])
    if side == "long":
        return_bps = (exit_price / entry - 1.0) * 10_000.0
        mfe_bps = (max(float(bar[2]) for bar in segment) / entry - 1.0) * 10_000.0
        mae_bps = (min(float(bar[3]) for bar in segment) / entry - 1.0) * 10_000.0
    else:
        return_bps = (entry - exit_price) / entry * 10_000.0
        mfe_bps = (entry - min(float(bar[3]) for bar in segment)) / entry * 10_000.0
        mae_bps = (entry - max(float(bar[2]) for bar in segment)) / entry * 10_000.0
    return {
        "entry_ts": int(segment[0][0]),
        "exit_ts": int(segment[-1][0]) + H1_MS,
        "return_bps": return_bps,
        "mfe_bps": mfe_bps,
        "mae_bps": mae_bps,
    }


def analyze_h1_symbol(
    symbol: str,
    bars: Sequence[Sequence[float]],
    config: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return non-overlapping per-pattern observations and time controls."""
    event = config["event_contract"]
    lookback = int(event["prior_range_lookback_h1"])
    cooldown = int(event["same_pattern_cooldown_h1"])
    horizons = tuple(int(value) for value in event["forward_horizons_h1"])
    max_horizon = max(horizons)
    last_signal: dict[str, int] = {}
    observations: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    last_eligible_signal = len(bars) - max_horizon - 1

    for signal_index in range(lookback, last_eligible_signal + 1):
        if (signal_index - lookback) % cooldown == 0:
            for side in ("long", "short"):
                for horizon in horizons:
                    controls.append({
                        "symbol": symbol,
                        "side": side,
                        "horizon_h1": horizon,
                        **forward_path(bars, signal_index=signal_index, horizon_h1=horizon, side=side),
                    })
        detected = detect_pattern_ids(
            bars,
            signal_index,
            lookback=lookback,
            touch_tolerance_bps=float(event["touch_tolerance_bps"]),
            minimum_wick_to_body_ratio=float(event["minimum_wick_to_body_ratio"]),
        )
        for pattern_id in detected:
            if signal_index - last_signal.get(pattern_id, -cooldown) < cooldown:
                continue
            last_signal[pattern_id] = signal_index
            side = EXPECTED_PATTERN_SIDES[pattern_id]
            for horizon in horizons:
                observations.append({
                    "symbol": symbol,
                    "pattern_id": pattern_id,
                    "side": side,
                    "signal_close_ts": int(bars[signal_index][0]) + H1_MS,
                    "horizon_h1": horizon,
                    **forward_path(bars, signal_index=signal_index, horizon_h1=horizon, side=side),
                })
    return observations, controls


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def summarize_observations(
    observations: Sequence[Mapping[str, Any]],
    controls: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Summarize every frozen pattern/horizon, including empty cells."""
    grouped: dict[tuple[str, int], list[Mapping[str, Any]]] = defaultdict(list)
    control_grouped: dict[tuple[str, int], list[Mapping[str, Any]]] = defaultdict(list)
    for row in observations:
        grouped[(str(row["pattern_id"]), int(row["horizon_h1"]))].append(row)
    for row in controls:
        control_grouped[(str(row["side"]), int(row["horizon_h1"]))].append(row)

    result: list[dict[str, Any]] = []
    for pattern_id, side in EXPECTED_PATTERN_SIDES.items():
        for horizon in (6, 24, 72, 168):
            rows = grouped.get((pattern_id, horizon), [])
            returns = [float(row["return_bps"]) for row in rows]
            by_symbol: dict[str, list[float]] = defaultdict(list)
            for row in rows:
                by_symbol[str(row["symbol"])].append(float(row["return_bps"]))
            per_symbol = [
                {
                    "symbol": symbol,
                    "n": len(values),
                    "mean_return_bps": _round(statistics.fmean(values)),
                }
                for symbol, values in sorted(by_symbol.items())
            ]
            counts = [len(values) for values in by_symbol.values()]
            n = len(rows)
            largest_share = max(counts) / n if n else None
            hhi = sum((count / n) ** 2 for count in counts) if n else None
            control_rows = control_grouped.get((side, horizon), [])
            control_returns = [float(row["return_bps"]) for row in control_rows]
            mean_return = statistics.fmean(returns) if returns else None
            control_mean = statistics.fmean(control_returns) if control_returns else None
            result.append({
                "pattern_id": pattern_id,
                "side": side,
                "horizon_h1": horizon,
                "n": n,
                "mean_return_bps": _round(mean_return),
                "median_return_bps": _round(statistics.median(returns) if returns else None),
                "hit_rate": _round(sum(value > 0 for value in returns) / n if n else None),
                "p25_return_bps": _round(_percentile(returns, 0.25)),
                "p75_return_bps": _round(_percentile(returns, 0.75)),
                "mean_mfe_bps": _round(statistics.fmean(float(row["mfe_bps"]) for row in rows) if rows else None),
                "mean_mae_bps": _round(statistics.fmean(float(row["mae_bps"]) for row in rows) if rows else None),
                "control_n": len(control_rows),
                "control_mean_return_bps": _round(control_mean),
                "mean_excess_vs_time_sampled_side_control_bps": _round(
                    mean_return - control_mean if mean_return is not None and control_mean is not None else None
                ),
                "symbols_with_events": len(by_symbol),
                "largest_symbol_share": _round(largest_share),
                "symbol_count_hhi": _round(hhi),
                "per_symbol": per_symbol,
            })
    return result


def run(config_path: Path, *, integrity_only: bool) -> dict[str, Any]:
    config = load_preregistration(ROOT, config_path)
    data = config["data_contract"]
    uniform_path = _repo_path(ROOT, data["uniform_manifest_path"])
    integrity = validate_uniform_window_manifest(ROOT, uniform_path, verify_rows=False)
    uniform = json.loads(uniform_path.read_text(encoding="utf-8"))
    start = int(uniform["window"]["start_ts"])
    full_end = int(uniform["window"]["end_ts_exclusive"])
    discovery_end = discovery_end_exclusive(full_end, int(data["holdout_days"]))
    common = {
        "schema": "multicoin_pattern_atlas_v1_receipt",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "config": config_path.relative_to(ROOT).as_posix(),
        "config_sha256": sha256_file(config_path),
        "preregistration_fingerprint_sha256": config["preregistration_fingerprint_sha256"],
        "uniform_manifest_sha256": integrity["manifest_sha256"],
        "symbols": integrity["symbols"],
        "discovery_start_ts": start,
        "discovery_start_utc": _utc_label(start),
        "discovery_end_ts_exclusive": discovery_end,
        "discovery_end_utc_exclusive": _utc_label(discovery_end),
        "sealed_holdout_start_ts": discovery_end,
        "sealed_holdout_start_utc": _utc_label(discovery_end),
        "uniform_window_end_ts_exclusive": full_end,
        "uniform_window_end_utc_exclusive": _utc_label(full_end),
        "sealed_holdout_scored": False,
        "promotion_eligible": False,
        "live_or_broker_calls": False,
        "source_hashes_verified": integrity["source_hashes_verified"],
    }
    if integrity_only:
        return {**common, "mode": "integrity_only", "performance_computed": False}

    observations: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    aggregation_receipts: list[dict[str, Any]] = []
    provider_fingerprint = integrity["manifest_sha256"]
    for symbol in integrity["symbols"]:
        snapshot = uniform["snapshots"][symbol]
        source = _repo_path(ROOT, snapshot["source_path"])
        m5 = load_discovery_m5_rows(
            source,
            start_ts=start,
            discovery_end_ts_exclusive=discovery_end,
        )
        aggregated = aggregate_closed_m5_bars(
            m5,
            as_of_ms=discovery_end,
            provider_identity="immutable_dev13_uniform_window_v1",
            provider_fingerprint=provider_fingerprint,
            config=ClosedBarAggregationConfigV1(target_timeframe="H1"),
        )
        symbol_observations, symbol_controls = analyze_h1_symbol(
            symbol, aggregated.output_bars, config
        )
        observations.extend(symbol_observations)
        controls.extend(symbol_controls)
        aggregation_receipts.append({
            "symbol": symbol,
            "source_m5_rows_decoded": len(m5),
            "sealed_rows_decoded": 0,
            "h1_rows": aggregated.output_count,
            "h1_sha256": aggregated.output_sha256,
            "config_fingerprint": aggregated.config_fingerprint,
        })
    return {
        **common,
        "mode": "discovery",
        "performance_computed": True,
        "gross_paths_only": True,
        "costs_or_fill_model_included": False,
        "observation_rows": len(observations),
        "control_rows": len(controls),
        "aggregation_receipts": aggregation_receipts,
        "summaries": summarize_observations(observations, controls),
        "limitations": [
            "Discovery cohort only; the final 120 days remain unscored.",
            "Six related hypotheses are descriptive and receive no p-values or promotion status.",
            "Gross next-open paths omit fees, slippage, funding, fills, stops and portfolio overlap.",
            "Horizontal prior-20-H1 levels only; sloped levels are explicitly excluded.",
            "Any candidate requires a separately preregistered sealed-holdout and external-cohort gate.",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--integrity-only", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(argv)
    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    try:
        payload = run(config_path, integrity_only=args.integrity_only)
        exit_code = 0
    except (OSError, TypeError, ValueError, UniformWindowError, PatternAtlasError) as exc:
        payload = {
            "schema": "multicoin_pattern_atlas_v1_receipt",
            "integrity_pass": False,
            "performance_computed": False,
            "promotion_eligible": False,
            "live_or_broker_calls": False,
            "error": str(exc),
        }
        exit_code = 2
    rendered = json.dumps(payload, indent=None if args.compact else 2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
