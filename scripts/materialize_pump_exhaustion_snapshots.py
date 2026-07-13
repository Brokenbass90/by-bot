#!/usr/bin/env python3
"""Materialize deterministic immutable inputs for pump-exhaustion research.

The command is deliberately limited to local data preparation.  It reads the
already-frozen preregistration and legacy JSON cache files, writes canonical
``ts/o/h/l/c/v`` snapshots plus a provenance manifest, and never edits the
preregistration, computes performance, contacts a network, or changes live
state.

Legacy cache rows may be either mappings or six-value sequences.  The exact
numeric-window cache is authoritative when it exists (the eleven backfilled
symbols).  Otherwise candidate segments are considered deterministically from
largest to smallest and every segment that contributes a new timestamp is
merged (BTC/ETH).  Explicit source lists can be supplied to the library API or
with ``--source-map``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    ROOT
    / "configs"
    / "preregistered"
    / "pump_exhaustion_unwind_short_v1_20260711.json"
)
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "data_cache"
    / "immutable"
    / "pump_exhaustion_unwind_short_v1_720d_20260711"
)
SNAPSHOT_KEYS = ("ts", "o", "h", "l", "c", "v")
SYMBOL_RE = re.compile(r"^[A-Z0-9]+USDT$")


class MaterializationError(ValueError):
    """The frozen contract or one of its local inputs is unsafe/invalid."""


@dataclass(frozen=True)
class DataContract:
    experiment: str
    cache_source: str
    symbols: tuple[str, ...]
    start: int
    end: int
    interval: int
    min_coverage: float
    max_gap_bars: int

    @property
    def expected_rows(self) -> int:
        return (self.end - self.start) // self.interval


@dataclass(frozen=True)
class ParsedSource:
    path: Path
    sha256: str
    size: int
    row_format: str
    rows_total: int
    rows_in_window: tuple[tuple[int, float, float, float, float, float], ...]
    identical_duplicates: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_text(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _safe_repo_path(
    root: Path,
    raw: str | os.PathLike[str],
    *,
    under: Path | None = None,
) -> Path:
    text = os.fspath(raw)
    candidate = Path(text)
    if not text or candidate.is_absolute() or "\\" in text:
        raise MaterializationError(f"path must be repo-relative: {text!r}")
    if not candidate.parts or any(part in {"", ".", ".."} for part in candidate.parts):
        raise MaterializationError(f"unsafe path: {text!r}")
    if ".git" in candidate.parts:
        raise MaterializationError(f"git paths are forbidden: {text!r}")
    path = root.joinpath(*candidate.parts)
    cursor = root
    for part in candidate.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise MaterializationError(f"path contains a symlink: {text!r}")
    if under is not None:
        try:
            path.relative_to(under)
        except ValueError as exc:
            raise MaterializationError(
                f"path must remain under {_relative_text(under, root)}: {text!r}"
            ) from exc
    return path


def _load_json_file(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise MaterializationError(f"input is not a regular file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaterializationError(f"invalid JSON input {path}: {exc}") from exc


def load_contract(config_path: Path) -> tuple[dict[str, Any], DataContract]:
    raw = _load_json_file(config_path)
    if not isinstance(raw, dict):
        raise MaterializationError("preregistration must be a JSON object")
    if not (
        raw.get("research_only") is True
        and raw.get("frozen_before_results") is True
        and raw.get("no_parameter_scan") is True
        and raw.get("live_or_broker_calls") is False
    ):
        raise MaterializationError("only a frozen research-only preregistration is accepted")
    strategy = raw.get("strategy")
    if not isinstance(strategy, Mapping) or not (
        strategy.get("id") == "pump_exhaustion_unwind_short_v1"
        and strategy.get("physical_side_identity") == "short_only"
        and strategy.get("signal_side") == "short"
        and strategy.get("live_ready") is False
    ):
        raise MaterializationError("strategy must remain pump-exhaustion physical short-only")
    data = raw.get("data")
    if not isinstance(data, Mapping):
        raise MaterializationError("data contract is missing")
    cache_source = str(data.get("cache_source") or "")
    if not cache_source:
        raise MaterializationError("cache_source is missing")
    symbols_raw = data.get("symbols")
    if not isinstance(symbols_raw, list) or len(symbols_raw) < 3:
        raise MaterializationError("at least three frozen symbols are required")
    symbols = tuple(str(symbol) for symbol in symbols_raw)
    if len(symbols) != len(set(symbols)) or not all(SYMBOL_RE.fullmatch(s) for s in symbols):
        raise MaterializationError("symbols must be unique canonical USDT names")
    try:
        start = int(data["window_start_ts"])
        end = int(data["window_end_ts_exclusive"])
        interval = int(data["interval_ms"])
        min_coverage = float(data["min_coverage"])
        max_gap = int(data["max_internal_gap_bars"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MaterializationError("data quality contract is malformed") from exc
    if start <= 0 or end <= start or interval != 300_000 or (end - start) % interval:
        raise MaterializationError("window must be a whole number of five-minute bars")
    if not (0.0 < min_coverage <= 1.0) or max_gap < 0:
        raise MaterializationError("coverage/gap gates are invalid")
    snapshots = data.get("input_snapshots")
    if snapshots not in ({}, None):
        raise MaterializationError("preregistration already contains input snapshot pins")
    return raw, DataContract(
        experiment=str(raw.get("name") or ""),
        cache_source=cache_source,
        symbols=symbols,
        start=start,
        end=end,
        interval=interval,
        min_coverage=min_coverage,
        max_gap_bars=max_gap,
    )


def _number(value: Any, *, field: str, path: Path, index: int) -> float:
    if isinstance(value, bool):
        raise MaterializationError(f"boolean {field} at {path}:{index}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise MaterializationError(f"non-numeric {field} at {path}:{index}") from exc
    if not math.isfinite(result):
        raise MaterializationError(f"non-finite {field} at {path}:{index}")
    return result


def _normalize_row(
    raw: Any,
    *,
    path: Path,
    index: int,
    contract: DataContract,
) -> tuple[tuple[int, float, float, float, float, float], str]:
    if isinstance(raw, Mapping):
        if not all(key in raw for key in SNAPSHOT_KEYS):
            raise MaterializationError(f"mapping row is missing OHLCV keys at {path}:{index}")
        values = [raw[key] for key in SNAPSHOT_KEYS]
        row_format = "mapping"
    elif isinstance(raw, (list, tuple)):
        if len(raw) < 6:
            raise MaterializationError(f"sequence row has fewer than six fields at {path}:{index}")
        values = list(raw[:6])
        row_format = "sequence"
    else:
        raise MaterializationError(f"row must be a mapping or sequence at {path}:{index}")

    ts_value = values[0]
    if isinstance(ts_value, bool):
        raise MaterializationError(f"boolean timestamp at {path}:{index}")
    try:
        ts_float = float(ts_value)
        ts = int(ts_value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MaterializationError(f"invalid timestamp at {path}:{index}") from exc
    if not math.isfinite(ts_float) or ts_float != ts:
        raise MaterializationError(f"timestamp is not an exact integer at {path}:{index}")
    if (ts - contract.start) % contract.interval:
        raise MaterializationError(f"timestamp is off the frozen interval grid at {path}:{index}")
    o, h, l, c, v = (
        _number(values[position], field=field, path=path, index=index)
        for position, field in enumerate(SNAPSHOT_KEYS[1:], start=1)
    )
    if not (o > 0 and h > 0 and l > 0 and c > 0 and v >= 0):
        raise MaterializationError(f"non-positive OHLC or negative volume at {path}:{index}")
    if h < max(o, l, c) or l > min(o, h, c):
        raise MaterializationError(f"OHLC invariant failed at {path}:{index}")
    return (ts, o, h, l, c, v), row_format


def parse_source(path: Path, contract: DataContract) -> ParsedSource:
    payload = _load_json_file(path)
    if not isinstance(payload, list):
        raise MaterializationError(f"cache payload must be a JSON array: {path}")
    formats: set[str] = set()
    in_window: dict[int, tuple[int, float, float, float, float, float]] = {}
    identical_duplicates = 0
    for index, raw in enumerate(payload):
        row, row_format = _normalize_row(raw, path=path, index=index, contract=contract)
        formats.add(row_format)
        ts = row[0]
        if not (contract.start <= ts < contract.end):
            continue
        previous = in_window.get(ts)
        if previous is None:
            in_window[ts] = row
        elif previous == row:
            identical_duplicates += 1
        else:
            raise MaterializationError(f"conflicting duplicate timestamp {ts} inside {path}")
    row_format = next(iter(formats)) if len(formats) == 1 else ("mixed" if formats else "empty")
    return ParsedSource(
        path=path,
        sha256=sha256_file(path),
        size=path.stat().st_size,
        row_format=row_format,
        rows_total=len(payload),
        rows_in_window=tuple(in_window[ts] for ts in sorted(in_window)),
        identical_duplicates=identical_duplicates,
    )


def quality_stats(
    rows_by_ts: Mapping[int, tuple[int, float, float, float, float, float]],
    contract: DataContract,
) -> dict[str, Any]:
    timestamps = sorted(rows_by_ts)
    expected = contract.expected_rows
    if not timestamps:
        return {
            "rows": 0,
            "expected_rows": expected,
            "coverage": 0.0,
            "first_ts": None,
            "last_ts": None,
            "max_internal_gap_bars": expected,
            "missing_prefix_bars": expected,
            "missing_suffix_bars": expected,
            "quality_pass": False,
        }
    max_gap = max(
        ((right - left) // contract.interval - 1 for left, right in zip(timestamps, timestamps[1:])),
        default=0,
    )
    prefix = (timestamps[0] - contract.start) // contract.interval
    suffix = (contract.end - contract.interval - timestamps[-1]) // contract.interval
    coverage = len(timestamps) / expected
    return {
        "rows": len(timestamps),
        "expected_rows": expected,
        "coverage": round(coverage, 9),
        "first_ts": timestamps[0],
        "last_ts": timestamps[-1],
        "max_internal_gap_bars": max_gap,
        "missing_prefix_bars": max(0, prefix),
        "missing_suffix_bars": max(0, suffix),
        "quality_pass": coverage >= contract.min_coverage and max_gap <= contract.max_gap_bars,
    }


def _discover_sources(cache_dir: Path, symbol: str, contract: DataContract) -> list[Path]:
    exact = cache_dir / f"{symbol}_5_{contract.start}_{contract.end}.json"
    if exact.exists():
        if exact.is_symlink() or not exact.is_file():
            raise MaterializationError(f"exact cache is unsafe: {exact}")
        return [exact]
    candidates: list[Path] = []
    for path in cache_dir.glob(f"{symbol}_5_*.json"):
        if path.is_symlink():
            raise MaterializationError(f"cache candidate is a symlink: {path}")
        if path.is_file():
            candidates.append(path)
    if not candidates:
        raise MaterializationError(f"no local cache candidates found for {symbol}")
    return sorted(candidates, key=lambda path: (-path.stat().st_size, path.name))


def _merge_sources(
    paths: Sequence[Path],
    *,
    contract: DataContract,
    only_contributing_sources: bool,
) -> tuple[
    dict[int, tuple[int, float, float, float, float, float]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    merged: dict[int, tuple[int, float, float, float, float, float]] = {}
    provenance: list[dict[str, Any]] = []
    identical_across_sources = 0
    for path in paths:
        source = parse_source(path, contract)
        additions: list[tuple[int, float, float, float, float, float]] = []
        source_identical = source.identical_duplicates
        for row in source.rows_in_window:
            ts = row[0]
            previous = merged.get(ts)
            if previous is None:
                additions.append(row)
            elif previous == row:
                identical_across_sources += 1
                source_identical += 1
            else:
                raise MaterializationError(
                    f"conflicting duplicate timestamp {ts} across selected cache segments"
                )
        if only_contributing_sources and merged and not additions:
            # Discovery may find dozens of fully overlapping historical cache
            # files.  They are still parsed and compared above so a conflicting
            # duplicate can never hide, but byte-identical redundant files are
            # not declared as inputs to the immutable artifact.
            continue
        for row in additions:
            merged[row[0]] = row
        provenance.append(
            {
                "path": str(path),  # converted to repo-relative by the caller
                "sha256": source.sha256,
                "size": source.size,
                "row_format": source.row_format,
                "rows_total": source.rows_total,
                "rows_in_window": len(source.rows_in_window),
                "rows_contributed": len(additions),
                "identical_duplicate_rows": source_identical,
            }
        )
    stats = quality_stats(merged, contract)
    stats["identical_duplicates_across_sources"] = identical_across_sources
    if not stats["quality_pass"]:
        raise MaterializationError(
            "snapshot quality gate failed: "
            f"coverage={stats['coverage']} min={contract.min_coverage} "
            f"max_gap={stats['max_internal_gap_bars']} allowed={contract.max_gap_bars}"
        )
    return merged, provenance, stats


def _atomic_write_snapshot(
    path: Path,
    rows: Iterable[tuple[int, float, float, float, float, float]],
) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write("[")
        first = True
        for ts, o, h, l, c, v in rows:
            if not first:
                handle.write(",")
            first = False
            record = {"ts": ts, "o": o, "h": h, "l": l, "c": c, "v": v}
            handle.write(json.dumps(record, ensure_ascii=True, separators=(",", ":"), allow_nan=False))
        handle.write("]\n")
        handle.flush()
        os.fsync(handle.fileno())


def _atomic_write_manifest(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _load_source_map(
    root: Path,
    path: Path,
    *,
    cache_dir: Path,
) -> dict[str, list[Path]]:
    raw = _load_json_file(path)
    if not isinstance(raw, Mapping):
        raise MaterializationError("source map must be a JSON object")
    result: dict[str, list[Path]] = {}
    for symbol, values in raw.items():
        if not isinstance(values, list) or not values:
            raise MaterializationError(f"source map entry for {symbol} must be a non-empty list")
        paths = [_safe_repo_path(root, value, under=cache_dir) for value in values]
        result[str(symbol)] = sorted(paths, key=lambda item: _relative_text(item, root))
    return result


def materialize_snapshots(
    root: Path,
    *,
    config_path: Path,
    output_dir: Path,
    source_map: Mapping[str, Sequence[Path]] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    if config_path.is_symlink():
        raise MaterializationError("config must be a regular non-symlink file")
    try:
        config_path = config_path.resolve(strict=True)
        config_path.relative_to(root)
    except (OSError, ValueError) as exc:
        raise MaterializationError("config must be an existing regular file inside the repo") from exc
    if config_path.is_symlink() or not config_path.is_file():
        raise MaterializationError("config must be a regular non-symlink file")
    cfg, contract = load_contract(config_path)
    if source_map is not None:
        unknown = sorted(set(source_map) - set(contract.symbols))
        if unknown:
            raise MaterializationError(f"source map contains unknown symbols: {unknown}")
    cache_dir = _safe_repo_path(root, contract.cache_source)
    if not cache_dir.is_dir():
        raise MaterializationError("configured cache_source directory is missing")
    immutable_root = cache_dir / "immutable"
    try:
        output_dir = output_dir.relative_to(root)
    except ValueError as exc:
        raise MaterializationError("output directory must be inside the repo") from exc
    output_dir = _safe_repo_path(root, output_dir.as_posix(), under=immutable_root)
    if output_dir == immutable_root:
        raise MaterializationError("output must be a named directory below data_cache/immutable")
    if output_dir.exists() or output_dir.is_symlink():
        raise MaterializationError(f"refusing to overwrite immutable output: {output_dir}")
    immutable_root.mkdir(parents=True, exist_ok=True)
    stage = immutable_root / f".{output_dir.name}.stage.{os.getpid()}.{uuid.uuid4().hex}"
    stage.mkdir(mode=0o700)
    try:
        snapshots: dict[str, Any] = {}
        for symbol in contract.symbols:
            explicit = source_map.get(symbol) if source_map is not None else None
            if explicit is not None:
                if not explicit:
                    raise MaterializationError(f"explicit source list is empty for {symbol}")
                paths = []
                for item in explicit:
                    item_path = Path(item)
                    if item_path.is_absolute():
                        try:
                            item_path = item_path.relative_to(root)
                        except ValueError as exc:
                            raise MaterializationError(f"source escapes repo for {symbol}") from exc
                    paths.append(_safe_repo_path(root, item_path.as_posix(), under=cache_dir))
                paths = sorted(paths, key=lambda item: _relative_text(item, root))
                only_contributors = False
            else:
                paths = _discover_sources(cache_dir, symbol, contract)
                only_contributors = len(paths) > 1
            merged, provenance, stats = _merge_sources(
                paths,
                contract=contract,
                only_contributing_sources=only_contributors,
            )
            for record in provenance:
                record["path"] = _relative_text(Path(record["path"]), root)
            leaf = f"{symbol}_5_{contract.start}_{contract.end}.json"
            staged_snapshot = stage / leaf
            _atomic_write_snapshot(staged_snapshot, (merged[ts] for ts in sorted(merged)))
            final_snapshot = output_dir / leaf
            snapshots[symbol] = {
                "path": _relative_text(final_snapshot, root),
                "sha256": sha256_file(staged_snapshot),
                **stats,
                "provenance": provenance,
            }

        manifest = {
            "schema_version": 1,
            "kind": "pump_exhaustion_immutable_snapshot_manifest",
            "experiment": contract.experiment,
            "strategy": "pump_exhaustion_unwind_short_v1",
            "side_identity": "short_only",
            "config": _relative_text(config_path, root),
            "config_sha256": sha256_file(config_path),
            "window_start_ts": contract.start,
            "window_end_ts_exclusive": contract.end,
            "interval_ms": contract.interval,
            "quality_gate": {
                "min_coverage": contract.min_coverage,
                "max_internal_gap_bars": contract.max_gap_bars,
            },
            "symbols": list(contract.symbols),
            "input_snapshots": {
                symbol: {
                    "path": snapshot["path"],
                    "sha256": snapshot["sha256"],
                }
                for symbol, snapshot in snapshots.items()
            },
            "snapshots": snapshots,
            "performance_computed": False,
            "network_calls": False,
            "live_state_changed": False,
            "config_edited": False,
        }
        _atomic_write_manifest(stage / "manifest.json", manifest)
        try:
            dir_fd = os.open(stage, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
        if output_dir.exists() or output_dir.is_symlink():
            raise MaterializationError(f"refusing raced immutable output: {output_dir}")
        os.rename(stage, output_dir)
        try:
            parent_fd = os.open(output_dir.parent, os.O_RDONLY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        except OSError:
            pass
        return manifest
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=_relative_text(DEFAULT_CONFIG, ROOT))
    parser.add_argument("--output-dir", default=_relative_text(DEFAULT_OUTPUT_DIR, ROOT))
    parser.add_argument(
        "--source-map",
        default="",
        help="Optional repo-relative JSON mapping symbol -> ordered cache paths.",
    )
    args = parser.parse_args(argv)
    try:
        config = _safe_repo_path(ROOT, args.config)
        output = _safe_repo_path(ROOT, args.output_dir)
        _, contract = load_contract(config)
        cache_dir = _safe_repo_path(ROOT, contract.cache_source)
        sources = None
        if args.source_map:
            map_path = _safe_repo_path(ROOT, args.source_map)
            sources = _load_source_map(ROOT, map_path, cache_dir=cache_dir)
        manifest = materialize_snapshots(
            ROOT,
            config_path=config,
            output_dir=output,
            source_map=sources,
        )
    except (MaterializationError, OSError) as exc:
        raise SystemExit(f"pump snapshot materialization refused: {exc}") from exc
    print(
        json.dumps(
            {
                "output_dir": _relative_text(output, ROOT),
                "manifest": _relative_text(output / "manifest.json", ROOT),
                "symbols": len(manifest["snapshots"]),
                "performance_computed": False,
                "network_calls": False,
                "live_state_changed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
