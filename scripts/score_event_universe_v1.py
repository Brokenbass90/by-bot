#!/usr/bin/env python3
"""Deterministically label the immutable event-universe snapshot chain.

This is a research-only, local, no-network scorer.  It cannot place orders,
read credentials, mutate risk, tune thresholds, or authorize promotion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.event_universe_v1 import (  # noqa: E402
    M5_INTERVAL_MS,
    EventUniverseConfigV1,
    EventUniverseError,
    canonical_bytes,
    sha256_payload,
    validate_snapshot_payload,
)
from scripts.run_event_universe_v1 import (  # noqa: E402
    REPLAY_SCHEMA_ID,
    _atomic_write,
    _load_spec,
    _read_snapshot_regular,
    _validate_replay_object,
)


SCORER_SCHEMA_ID = "event_universe_label_scorer_preregistered_v1"
RECEIPT_SCHEMA_ID = "event_universe_label_receipt_v1"
DEFAULT_SPEC = ROOT / "configs/preregistered/event_universe_label_scorer_v1_20260721.json"
DEFAULT_RUN_ROOT = ROOT / "runtime/research/event_universe_v1_20260718_public1"
DEFAULT_OUTPUT_DIR = ROOT / "reports/research/event_universe_v1_labels"
IMPLEMENTATION_RELATIVE_PATHS = (
    "bot/event_universe_v1.py",
    "scripts/run_event_universe_v1.py",
    "scripts/score_event_universe_v1.py",
)


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise EventUniverseError(f"{label} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise EventUniverseError(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise EventUniverseError(f"{label} must be finite")
    return result


def _exact_int(value: Any, label: str, *, positive: bool = False) -> int:
    if isinstance(value, bool):
        raise EventUniverseError(f"{label} must be an exact integer")
    try:
        result = int(value)
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise EventUniverseError(f"{label} must be an exact integer") from exc
    if not math.isfinite(numeric) or numeric != float(result) or (positive and result <= 0):
        raise EventUniverseError(f"{label} must be an exact integer")
    return result


def load_scorer_spec(path: Path) -> tuple[dict[str, Any], dict[str, Any], EventUniverseConfigV1]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_id") != SCORER_SCHEMA_ID:
        raise EventUniverseError("event label scorer spec identity mismatch")
    if payload.get("scorer_id") != "event_universe_label_scorer_v1":
        raise EventUniverseError("event label scorer id mismatch")
    if payload.get("status") != "RESEARCH_ONLY_FROZEN_NO_PROMOTION_AUTHORITY":
        raise EventUniverseError("event label scorer status mismatch")
    authority = payload.get("authority")
    expected_authority = {
        "research_only": True,
        "executable": False,
        "network_calls": False,
        "environment_or_api_key_reads": False,
        "private_api_calls": False,
        "broker_calls": False,
        "orders_transfers_withdrawals": False,
        "risk_or_live_router_mutation": False,
        "parameter_tuning": False,
        "performance_claims": False,
        "promotion_authority": False,
    }
    if authority != expected_authority:
        raise EventUniverseError("event label scorer authority is not frozen fail-closed")

    selection = payload.get("selection")
    if not isinstance(selection, Mapping) or selection.get("candidate_ok") is not True:
        raise EventUniverseError("event label scorer selection is missing")
    expected_selection = {
        "candidate_ok": True,
        "candidate_reason": "event_ok",
        "allowed_directions": ["long", "short"],
        "episode_identity": "symbol_plus_direction",
        "episode_rule": "chronologically_first_eligible_candidate_then_first_after_cooldown",
        "cooldown_ms": 86_400_000,
        "selection_uses_future_outcomes": False,
    }
    if dict(selection) != expected_selection:
        raise EventUniverseError("event label scorer selection contract changed")

    execution = payload.get("execution_model")
    if not isinstance(execution, Mapping):
        raise EventUniverseError("event label scorer execution model is missing")
    expected_execution = {
        "entry_rule": "open_of_exact_next_contiguous_closed_m5_bar_after_signal_tail",
        "entry_delay_bars": 1,
        "roundtrip_cost_bps": 16.0,
        "cost_scope": "fixed_research_hurdle_deducted_once_from_endpoint_return",
        "cost_warning": "not_an_account_or_symbol_specific_executable_cost_contract",
    }
    if dict(execution) != expected_execution:
        raise EventUniverseError("event label scorer execution contract changed")

    horizons = payload.get("horizons")
    if horizons != [
        {"id": "1h", "bars": 12},
        {"id": "4h", "bars": 48},
        {"id": "24h", "bars": 288},
    ]:
        raise EventUniverseError("event label scorer horizons changed")

    source = payload.get("source_contract")
    if not isinstance(source, Mapping):
        raise EventUniverseError("event label scorer source contract is missing")
    if source.get("replay_schema_id") != REPLAY_SCHEMA_ID or source.get("interval_ms") != M5_INTERVAL_MS:
        raise EventUniverseError("event label scorer source interval/replay identity mismatch")
    collector_spec_path = ROOT / str(source.get("collector_spec_path") or "")
    collector_spec, collector_config = _load_spec(collector_spec_path)
    if sha256_payload(collector_spec) != source.get("collector_spec_payload_sha256"):
        raise EventUniverseError("collector spec payload hash no longer matches scorer preregistration")
    if collector_config.config_sha256 != source.get("collector_config_sha256"):
        raise EventUniverseError("collector config hash no longer matches scorer preregistration")
    if source.get("snapshot_schema_id") != "event_universe_snapshot_v1":
        raise EventUniverseError("collector snapshot schema changed")

    feature_buckets = payload.get("feature_buckets")
    expected_features = {
        "heuristic_rank",
        "inflow_mult",
        "abs_recent_return_pct",
        "range_expansion_atr",
        "latest_body_fraction",
    }
    if not isinstance(feature_buckets, Mapping) or set(feature_buckets) != expected_features:
        raise EventUniverseError("fixed feature buckets are missing")
    for name, raw_bounds in feature_buckets.items():
        if not isinstance(raw_bounds, list) or len(raw_bounds) < 2:
            raise EventUniverseError(f"feature bucket {name} is invalid")
        bounds = [_finite(item, f"feature bucket {name}") for item in raw_bounds]
        if bounds != sorted(bounds) or len(set(bounds)) != len(bounds):
            raise EventUniverseError(f"feature bucket {name} is not strictly increasing")

    return payload, collector_spec, collector_config


def _implementation_hashes() -> dict[str, str]:
    return {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in IMPLEMENTATION_RELATIVE_PATHS
    }


def freeze_snapshot_paths(root: Path, *, through_sequence: int | None = None) -> list[Path]:
    paths = sorted(root.glob("snapshot_*.json.gz"))
    if through_sequence is not None:
        if through_sequence <= 0:
            raise EventUniverseError("through sequence must be positive")
        paths = paths[:through_sequence]
        if len(paths) != through_sequence:
            raise EventUniverseError("requested through sequence is not fully present")
    if not paths:
        raise EventUniverseError("event-universe snapshot chain is empty")
    return paths


def frozen_file_set_identity(paths: Sequence[Path]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise EventUniverseError("frozen snapshot input path is not a regular file")
        rows.append(
            {
                "file": path.name,
                "compressed_file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return {
        "snapshot_count": len(rows),
        "first_snapshot_file": rows[0]["file"],
        "last_snapshot_file": rows[-1]["file"],
        "frozen_snapshot_file_set_sha256": sha256_payload(rows),
    }


def load_frozen_source(
    root: Path,
    paths: Sequence[Path],
    *,
    config: EventUniverseConfigV1,
) -> tuple[
    list[dict[str, Any]],
    dict[str, dict[int, list[Any]]],
    dict[int, dict[str, int]],
    dict[str, Any],
]:
    """Validate the frozen chain and return snapshots plus a conflict-free M5 union."""
    snapshots: list[dict[str, Any]] = []
    bars_by_symbol: dict[str, dict[int, list[Any]]] = defaultdict(dict)
    candidate_tail_end_by_sequence: dict[int, dict[str, int]] = {}
    previous_normalized: dict[str, list[list[Any]]] = {}
    previous_snapshot_hash: str | None = None
    previous_as_of_ms: int | None = None
    chain_identity: list[dict[str, Any]] = []

    for expected_sequence, path in enumerate(paths, 1):
        payload = _read_snapshot_regular(path, config=config)
        validate_snapshot_payload(payload, config=config, require_replay=True)
        if payload.get("sequence") != expected_sequence:
            raise EventUniverseError("frozen snapshot sequence is not contiguous from one")
        if payload.get("previous_snapshot_sha256") != previous_snapshot_hash:
            raise EventUniverseError("frozen snapshot hash chain is broken")
        as_of_ms = _exact_int(payload.get("as_of_ms"), "snapshot as_of_ms", positive=True)
        if previous_as_of_ms is not None and as_of_ms <= previous_as_of_ms:
            raise EventUniverseError("frozen snapshot chronology is not strictly increasing")
        expected_name = f"snapshot_{expected_sequence:06d}_{as_of_ms}.json.gz"
        if path.name != expected_name:
            raise EventUniverseError("frozen snapshot filename identity mismatch")
        normalized = _validate_replay_object(
            root,
            payload,
            previous_normalized_m5_by_symbol=previous_normalized,
            config=config,
        )
        for symbol, rows in normalized.items():
            symbol_bars = bars_by_symbol[symbol]
            for raw_row in rows:
                row = list(raw_row)
                start_ms = _exact_int(row[0], "M5 start", positive=True)
                existing = symbol_bars.get(start_ms)
                if existing is not None and existing != row:
                    raise EventUniverseError(f"conflicting immutable M5 bar for {symbol} at {start_ms}")
                symbol_bars[start_ms] = row
        candidate_symbols = {
            str(score["symbol"])
            for score in payload["scores"]
            if score.get("ok") is True
            and score.get("reason") == "event_ok"
            and score.get("direction") in {"long", "short"}
        }
        candidate_tail_end_by_sequence[expected_sequence] = {
            symbol: _exact_int(normalized[symbol][-1][0], "candidate signal tail end", positive=True)
            for symbol in sorted(candidate_symbols)
        }
        replay = payload["replay_bundle"]
        chain_identity.append(
            {
                "sequence": expected_sequence,
                "snapshot_file": path.name,
                "snapshot_sha256": payload["snapshot_sha256"],
                "replay_uncompressed_sha256": replay["uncompressed_sha256"],
                "replay_compressed_sha256": replay["compressed_sha256"],
            }
        )
        snapshots.append(payload)
        previous_normalized = normalized
        previous_snapshot_hash = str(payload["snapshot_sha256"])
        previous_as_of_ms = as_of_ms

    source_identity = {
        "snapshot_count": len(snapshots),
        "first_snapshot_sha256": snapshots[0]["snapshot_sha256"],
        "last_snapshot_sha256": snapshots[-1]["snapshot_sha256"],
        "first_as_of_ms": snapshots[0]["as_of_ms"],
        "last_as_of_ms": snapshots[-1]["as_of_ms"],
        "source_chain_sha256": sha256_payload(chain_identity),
    }
    return snapshots, dict(bars_by_symbol), candidate_tail_end_by_sequence, source_identity


def select_episodes(
    snapshots: Sequence[Mapping[str, Any]],
    tail_end_by_sequence: Mapping[int, Mapping[str, int]] | None = None,
    *,
    cooldown_ms: int = 86_400_000,
) -> list[dict[str, Any]]:
    """Select candidates causally; outcomes are deliberately not an input."""
    last_selected: dict[tuple[str, str], int] = {}
    episodes: list[dict[str, Any]] = []
    for snapshot in snapshots:
        sequence = _exact_int(snapshot["sequence"], "snapshot sequence", positive=True)
        as_of_ms = _exact_int(snapshot["as_of_ms"], "snapshot as_of_ms", positive=True)
        score_rows = snapshot.get("scores")
        if not isinstance(score_rows, list):
            raise EventUniverseError("snapshot scores are missing during episode selection")
        for score in score_rows:
            if not isinstance(score, Mapping):
                raise EventUniverseError("snapshot score is invalid during episode selection")
            if score.get("ok") is not True or score.get("reason") != "event_ok":
                continue
            direction = str(score.get("direction") or "")
            if direction not in {"long", "short"}:
                continue
            symbol = str(score.get("symbol") or "")
            key = (symbol, direction)
            prior = last_selected.get(key)
            if prior is not None and as_of_ms - prior < cooldown_ms:
                continue
            if tail_end_by_sequence is None:
                tail_end_ms = None
            else:
                tail_end_ms = tail_end_by_sequence.get(sequence, {}).get(symbol)
                if tail_end_ms is None:
                    raise EventUniverseError("selected candidate has no validated replay tail")
            episode = {
                "episode_index": len(episodes) + 1,
                "symbol": symbol,
                "direction": direction,
                "listing_tier": str(score["listing_tier"]),
                "signal_sequence": sequence,
                "signal_as_of_ms": as_of_ms,
                "signal_snapshot_sha256": str(snapshot["snapshot_sha256"]),
                "signal_tail_end_ms": tail_end_ms,
                "candidate_id": str(score["candidate_id"]),
                "input_sha256": str(score["input_sha256"]),
                "features": {
                    "heuristic_rank": _finite(score["heuristic_rank"], "heuristic rank"),
                    "inflow_mult": _finite(score["inflow_mult"], "inflow mult"),
                    "abs_recent_return_pct": abs(_finite(score["recent_return_pct"], "recent return")),
                    "range_expansion_atr": _finite(score["range_expansion_atr"], "range expansion"),
                    "latest_body_fraction": _finite(score["latest_body_fraction"], "latest body"),
                },
            }
            episodes.append(episode)
            last_selected[key] = as_of_ms
    return episodes
def score_episode_outcomes(
    episode: Mapping[str, Any],
    bars_by_symbol: Mapping[str, Mapping[int, Sequence[Any]]],
    *,
    chain_head_as_of_ms: int,
    horizons: Sequence[Mapping[str, Any]],
    roundtrip_cost_bps: float,
) -> dict[str, Any]:
    result = dict(episode)
    signal_tail_end_ms = episode.get("signal_tail_end_ms")
    if signal_tail_end_ms is None:
        raise EventUniverseError("episode signal tail end is not bound")
    entry_start_ms = _exact_int(signal_tail_end_ms, "signal tail end", positive=True) + M5_INTERVAL_MS
    symbol = str(episode["symbol"])
    direction = str(episode["direction"])
    symbol_bars = bars_by_symbol.get(symbol, {})
    outcome_by_horizon: dict[str, Any] = {}
    for horizon in horizons:
        horizon_id = str(horizon["id"])
        bar_count = _exact_int(horizon["bars"], f"{horizon_id} bars", positive=True)
        exit_start_ms = entry_start_ms + (bar_count - 1) * M5_INTERVAL_MS
        observable_at_ms = exit_start_ms + M5_INTERVAL_MS
        if observable_at_ms > chain_head_as_of_ms:
            outcome_by_horizon[horizon_id] = {
                "status": "pending",
                "required_bars": bar_count,
                "observable_at_ms": observable_at_ms,
            }
            continue
        starts = [entry_start_ms + index * M5_INTERVAL_MS for index in range(bar_count)]
        missing = [start for start in starts if start not in symbol_bars]
        if missing:
            outcome_by_horizon[horizon_id] = {
                "status": "unscorable_missing_future_bars",
                "required_bars": bar_count,
                "missing_bar_count": len(missing),
                "first_missing_start_ms": missing[0],
                "observable_at_ms": observable_at_ms,
            }
            continue
        rows = [symbol_bars[start] for start in starts]
        entry = _finite(rows[0][1], "entry open")
        exit_close = _finite(rows[-1][4], "exit close")
        highs = [_finite(row[2], "bar high") for row in rows]
        lows = [_finite(row[3], "bar low") for row in rows]
        if entry <= 0 or exit_close <= 0 or any(low <= 0 or high < low for low, high in zip(lows, highs)):
            raise EventUniverseError("outcome M5 OHLC is invalid")
        if direction == "long":
            gross_return_bps = (exit_close / entry - 1.0) * 10_000.0
            mfe_bps = max(high / entry - 1.0 for high in highs) * 10_000.0
            mae_bps = max(1.0 - low / entry for low in lows) * 10_000.0
        elif direction == "short":
            gross_return_bps = (1.0 - exit_close / entry) * 10_000.0
            mfe_bps = max(1.0 - low / entry for low in lows) * 10_000.0
            mae_bps = max(high / entry - 1.0 for high in highs) * 10_000.0
        else:
            raise EventUniverseError("episode direction is invalid")
        outcome_by_horizon[horizon_id] = {
            "status": "scored",
            "required_bars": bar_count,
            "entry_start_ms": entry_start_ms,
            "exit_start_ms": exit_start_ms,
            "entry_open": round(entry, 12),
            "exit_close": round(exit_close, 12),
            "gross_return_bps": round(gross_return_bps, 9),
            "roundtrip_cost_bps": round(roundtrip_cost_bps, 9),
            "net_return_bps": round(gross_return_bps - roundtrip_cost_bps, 9),
            "mfe_bps": round(max(0.0, mfe_bps), 9),
            "mae_bps": round(max(0.0, mae_bps), 9),
            "observable_at_ms": observable_at_ms,
        }
    result["entry_start_ms"] = entry_start_ms
    result["outcomes"] = outcome_by_horizon
    return result


def _mean(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 9)


def _metrics_for_rows(rows: Sequence[Mapping[str, Any]], horizon_id: str) -> dict[str, Any]:
    outcomes = [row["outcomes"][horizon_id] for row in rows if row["outcomes"][horizon_id]["status"] == "scored"]
    if not outcomes:
        return {
            "n": 0,
            "mean_net_return_bps": None,
            "median_net_return_bps": None,
            "positive_rate": None,
            "mean_mfe_bps": None,
            "mean_mae_bps": None,
        }
    net = [float(item["net_return_bps"]) for item in outcomes]
    mfe = [float(item["mfe_bps"]) for item in outcomes]
    mae = [float(item["mae_bps"]) for item in outcomes]
    return {
        "n": len(outcomes),
        "mean_net_return_bps": _mean(net),
        "median_net_return_bps": round(float(statistics.median(net)), 9),
        "positive_rate": round(sum(value > 0 for value in net) / len(net), 9),
        "mean_mfe_bps": _mean(mfe),
        "mean_mae_bps": _mean(mae),
    }


def _bucket_label(bounds: Sequence[float], value: float) -> str:
    for left, right in zip(bounds, bounds[1:]):
        if left <= value < right:
            return f"[{left:g},{right:g})"
    raise EventUniverseError(f"feature value {value} is outside frozen buckets")


def build_summaries(
    episodes: Sequence[Mapping[str, Any]],
    *,
    horizons: Sequence[Mapping[str, Any]],
    feature_buckets: Mapping[str, Sequence[Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for episode in episodes:
        grouped[("all", "all")].append(episode)
        direction = str(episode["direction"])
        tier = str(episode["listing_tier"])
        grouped[("direction", direction)].append(episode)
        grouped[("listing_tier", tier)].append(episode)
        grouped[("direction_x_listing_tier", f"{direction}|{tier}")].append(episode)
        features = episode["features"]
        for name in sorted(feature_buckets):
            bounds = [_finite(item, f"feature bucket {name}") for item in feature_buckets[name]]
            label = _bucket_label(bounds, _finite(features[name], name))
            grouped[(f"feature:{name}", label)].append(episode)
    result: list[dict[str, Any]] = []
    horizon_ids = [str(item["id"]) for item in horizons]
    for (group_type, key), rows in sorted(grouped.items()):
        result.append(
            {
                "group_type": group_type,
                "key": key,
                "selected_episode_count": len(rows),
                "metrics_by_horizon": {
                    horizon_id: _metrics_for_rows(rows, horizon_id)
                    for horizon_id in horizon_ids
                },
            }
        )
    return result


def build_receipt(
    *,
    spec: Mapping[str, Any],
    source_identity: Mapping[str, Any],
    episodes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    horizons = spec["horizons"]
    status_counts = {
        str(horizon["id"]): dict(
            sorted(
                Counter(
                    str(episode["outcomes"][str(horizon["id"])]["status"])
                    for episode in episodes
                ).items()
            )
        )
        for horizon in horizons
    }
    body: dict[str, Any] = {
        "schema_id": RECEIPT_SCHEMA_ID,
        "validation_status": "passed",
        "scorer_id": "event_universe_label_scorer_v1",
        "research_only": True,
        "executable": False,
        "network_calls": False,
        "environment_or_api_key_reads": False,
        "private_api_calls": False,
        "broker_calls": False,
        "orders_or_risk_mutation": False,
        "parameter_tuning": False,
        "performance_claims": False,
        "promotion_authority": False,
        "implementation_sha256_by_path": _implementation_hashes(),
        "preregistered_spec_sha256": sha256_payload(spec),
        "collector_spec_payload_sha256": spec["source_contract"]["collector_spec_payload_sha256"],
        "collector_config_sha256": spec["source_contract"]["collector_config_sha256"],
        "source_identity": dict(source_identity),
        "roundtrip_cost_bps": spec["execution_model"]["roundtrip_cost_bps"],
        "selected_episode_count": len(episodes),
        "status_counts_by_horizon": status_counts,
        "episodes": list(episodes),
        "summaries": build_summaries(
            episodes,
            horizons=horizons,
            feature_buckets=spec["feature_buckets"],
        ),
        "interpretation": {
            "heuristic_rank_is_probability": False,
            "fixed_cost_is_executable_cost_contract": False,
            "receipt_can_authorize_promotion": False,
            "promising_observation_requires_new_strategy_prereg_and_untouched_forward": True,
        },
    }
    body["receipt_sha256"] = sha256_payload(body)
    return body


def build_validation_failure_receipt(
    *,
    spec: Mapping[str, Any],
    frozen_input_identity: Mapping[str, Any],
    error: EventUniverseError,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_id": RECEIPT_SCHEMA_ID,
        "validation_status": "failed_closed_no_outcomes_scored",
        "scorer_id": "event_universe_label_scorer_v1",
        "research_only": True,
        "executable": False,
        "network_calls": False,
        "environment_or_api_key_reads": False,
        "private_api_calls": False,
        "broker_calls": False,
        "orders_or_risk_mutation": False,
        "parameter_tuning": False,
        "performance_claims": False,
        "promotion_authority": False,
        "implementation_sha256_by_path": _implementation_hashes(),
        "preregistered_spec_sha256": sha256_payload(spec),
        "collector_spec_payload_sha256": spec["source_contract"]["collector_spec_payload_sha256"],
        "collector_config_sha256": spec["source_contract"]["collector_config_sha256"],
        "frozen_input_identity": dict(frozen_input_identity),
        "validation_error": f"{type(error).__name__}: {error}",
        "selected_episode_count": 0,
        "outcomes_scored": False,
        "interpretation": {
            "source_is_valid_for_label_scoring": False,
            "receipt_can_authorize_promotion": False,
            "performance_inference_allowed": False,
        },
    }
    body["receipt_sha256"] = sha256_payload(body)
    return body


def write_receipt(output_dir: Path, receipt: Mapping[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_dir.is_symlink():
        raise EventUniverseError("receipt output directory cannot be a symlink")
    if receipt.get("validation_status") == "failed_closed_no_outcomes_scored":
        source = receipt["frozen_input_identity"]
        name = (
            f"event_universe_label_failure_s{int(source['snapshot_count']):06d}_"
            f"{str(source['frozen_snapshot_file_set_sha256'])[:12]}_"
            f"{str(receipt['receipt_sha256'])[:12]}.json"
        )
    else:
        source = receipt["source_identity"]
        name = (
            f"event_universe_label_receipt_s{int(source['snapshot_count']):06d}_"
            f"{str(source['last_snapshot_sha256'])[:12]}_"
            f"{str(receipt['receipt_sha256'])[:12]}.json"
        )
    path = output_dir / name
    data = canonical_bytes(receipt) + b"\n"
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data:
            raise EventUniverseError("existing deterministic receipt differs from rebuilt bytes")
        return path
    _atomic_write(path, data, replace=False)
    return path


def score_chain(
    *,
    scorer_spec_path: Path,
    run_root: Path,
    output_dir: Path,
    through_sequence: int | None = None,
    write: bool = True,
) -> tuple[dict[str, Any], Path | None]:
    scorer_spec, _collector_spec, config = load_scorer_spec(scorer_spec_path)
    frozen_paths = freeze_snapshot_paths(run_root, through_sequence=through_sequence)
    frozen_input_identity = frozen_file_set_identity(frozen_paths)
    try:
        snapshots, bars_by_symbol, tail_end_by_sequence, source_identity = load_frozen_source(
            run_root,
            frozen_paths,
            config=config,
        )
    except EventUniverseError as exc:
        receipt = build_validation_failure_receipt(
            spec=scorer_spec,
            frozen_input_identity=frozen_input_identity,
            error=exc,
        )
        return receipt, write_receipt(output_dir, receipt) if write else None
    selected = select_episodes(
        snapshots,
        tail_end_by_sequence,
        cooldown_ms=int(scorer_spec["selection"]["cooldown_ms"]),
    )
    scored = [
        score_episode_outcomes(
            episode,
            bars_by_symbol,
            chain_head_as_of_ms=int(source_identity["last_as_of_ms"]),
            horizons=scorer_spec["horizons"],
            roundtrip_cost_bps=float(scorer_spec["execution_model"]["roundtrip_cost_bps"]),
        )
        for episode in selected
    ]
    receipt = build_receipt(spec=scorer_spec, source_identity=source_identity, episodes=scored)
    return receipt, write_receipt(output_dir, receipt) if write else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--through-sequence", type=int)
    parser.add_argument("--no-write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        receipt, path = score_chain(
            scorer_spec_path=args.spec,
            run_root=args.run_root,
            output_dir=args.output_dir,
            through_sequence=args.through_sequence,
            write=not args.no_write,
        )
        passed = receipt.get("validation_status") == "passed"
        print(
            json.dumps(
                {
                    "ok": passed,
                    "research_only": True,
                    "executable": False,
                    "validation_status": receipt["validation_status"],
                    "snapshot_count": (
                        receipt["source_identity"]["snapshot_count"]
                        if passed
                        else receipt["frozen_input_identity"]["snapshot_count"]
                    ),
                    "selected_episode_count": receipt["selected_episode_count"],
                    "status_counts_by_horizon": receipt.get("status_counts_by_horizon"),
                    "validation_error": receipt.get("validation_error"),
                    "receipt_sha256": receipt["receipt_sha256"],
                    "receipt_path": str(path) if path else None,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if passed else 2
    except (EventUniverseError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
