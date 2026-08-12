#!/usr/bin/env python3
"""Fail-closed, write-once MPL V3 sealed-holdout evaluator.

The strategy thresholds live in ``mpl_v3.py``.  This file only enforces the
measurement boundary: exact UTC window, explicit universe, input integrity,
time-matched random control, censored end-of-window labels and write-once
receipts.  ``--preflight-only`` never opens an NPZ input.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
START_MS = int(dt.datetime(2025, 10, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
END_MS_EXCLUSIVE = int(dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
BAR_MS = 900_000
MIN_OBSERVED_COVERAGE = 0.98


class HoldoutError(RuntimeError):
    """The one-time evaluation is not admissible."""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise HoldoutError(f"write-once receipt already exists: {path}") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _load_engine(script_path: Path, source_dir: Path):
    source = script_path.read_text(encoding="utf-8")
    source = source.replace('if __name__ == "__main__":\n    main()', "")
    module = types.ModuleType("mpl_v3_frozen")
    module.__dict__["__name__"] = "mpl_v3_frozen"
    exec(compile(source, str(script_path), "exec"), module.__dict__)
    module.DIR = str(source_dir)
    return module


def metadata_preflight(source_dir: Path, symbols: list[str]) -> dict[str, Any]:
    if not source_dir.is_dir():
        raise HoldoutError(f"MPL source directory is missing: {source_dir}")
    expected = {f"{symbol}.npz" for symbol in symbols}
    present = {path.name for path in source_dir.glob("*.npz")}
    missing = sorted(expected - present)
    if missing:
        raise HoldoutError(f"missing {len(missing)} MPL files: {missing}")
    return {
        "expected_symbol_count": len(symbols),
        "expected_files": sorted(expected),
        "extra_npz_ignored": sorted(present - expected),
        "input_bytes": sum((source_dir / name).stat().st_size for name in expected),
    }


def validate_loaded_inputs(data: dict[str, dict[str, np.ndarray]], symbols: list[str]) -> dict[str, Any]:
    if sorted(data) != sorted(symbols):
        raise HoldoutError("loaded universe does not exactly match the preregistered universe")
    rows = []
    usable = 0
    for symbol in symbols:
        d = data[symbol]
        ts = np.asarray(d["ts"], dtype=np.int64)
        if len(ts) < 2 or np.any(np.diff(ts) <= 0) or np.any(ts % BAR_MS != 0):
            raise HoldoutError(f"{symbol}: timestamps are not unique, ascending 15m bars")
        o, h, l, c, v = (np.asarray(d[key], dtype=float) for key in ("o", "h", "l", "c", "v"))
        if not all(len(x) == len(ts) for x in (o, h, l, c, v)):
            raise HoldoutError(f"{symbol}: OHLCV length mismatch")
        if not np.all(np.isfinite(np.column_stack((o, h, l, c, v)))):
            raise HoldoutError(f"{symbol}: non-finite OHLCV")
        if np.any(np.minimum.reduce((o, h, l, c)) <= 0) or np.any(v < 0):
            raise HoldoutError(f"{symbol}: non-positive price or negative volume")
        if np.any(h < np.maximum.reduce((o, l, c))) or np.any(l > np.minimum.reduce((o, h, c))):
            raise HoldoutError(f"{symbol}: invalid OHLC geometry")
        expected = int((ts[-1] - ts[0]) // BAR_MS) + 1
        coverage = len(ts) / max(1, expected)
        if coverage < MIN_OBSERVED_COVERAGE:
            raise HoldoutError(f"{symbol}: observed-span coverage {coverage:.4%} < {MIN_OBSERVED_COVERAGE:.0%}")
        has_holdout = bool(np.any((ts >= START_MS) & (ts < END_MS_EXCLUSIVE)))
        usable += int(has_holdout)
        rows.append({
            "symbol": symbol,
            "bars": len(ts),
            "first_ts_ms": int(ts[0]),
            "last_ts_ms": int(ts[-1]),
            "observed_span_coverage": round(float(coverage), 8),
            "has_holdout_rows": has_holdout,
        })
    if usable < 10:
        raise HoldoutError(f"only {usable} symbols contain holdout rows; cross-rank needs at least 10")
    return {"usable_symbol_count": usable, "symbols": rows}


def week_boot(r_values: np.ndarray, timestamps: np.ndarray, n: int = 3000, seed: int = 5):
    weeks = (np.asarray(timestamps) // (7 * 86_400_000)).astype(np.int64)
    unique = np.unique(weeks)
    if len(unique) < 2:
        raise HoldoutError("too few independent weeks for block bootstrap")
    indices = {week: np.flatnonzero(weeks == week) for week in unique}
    rng = np.random.default_rng(seed)
    out = np.empty(n)
    for i in range(n):
        picked = rng.choice(unique, len(unique), replace=True)
        out[i] = r_values[np.concatenate([indices[week] for week in picked])].mean()
    return float(np.quantile(out, 0.025)), float(np.quantile(out, 0.975))


def evaluate(engine, data: dict[str, dict[str, Any]], symbols: list[str]) -> dict[str, Any]:
    engine.TURN = {s: float(np.median(data[s]["c"] * data[s]["v"])) * 96 for s in symbols}
    for symbol in symbols:
        engine.prepare(data[symbol])
    engine.cross_rank(data, symbols)

    signal_end_exclusive = END_MS_EXCLUSIVE - int(engine.CAP_H * engine.HOUR)
    rng = np.random.default_rng(3)
    real: list[dict[str, Any]] = []
    control: list[dict[str, Any]] = []
    signal_counts: dict[str, int] = {}
    for symbol in symbols:
        d = data[symbol]
        signals = [
            row for row in engine.signals(d)
            if START_MS <= int(row[0]) < signal_end_exclusive
        ]
        if not signals:
            continue
        real_symbol = engine.simulate(d, signals, symbol, enforce_no_overlap=True)
        if not real_symbol:
            continue
        signal_counts[symbol] = len(real_symbol)
        real.extend(real_symbol)

        candidate_indices = np.flatnonzero(
            (d["ts"] >= START_MS)
            & (d["ts"] < signal_end_exclusive)
            & (d["hidx"] >= 0)
        )
        candidate_indices = np.array([
            j for j in candidate_indices
            if np.isfinite(d["H"]["atr"][d["hidx"][j]])
            and np.isfinite(d["H"]["lvl"][d["hidx"][j]])
        ], dtype=np.int64)
        if len(candidate_indices) < len(real_symbol):
            raise HoldoutError(f"{symbol}: insufficient time-matched random-control bars")
        picked = rng.choice(candidate_indices, len(real_symbol), replace=False)
        fake = []
        for source, j in zip(real_symbol, picked):
            k = int(d["hidx"][j])
            p = float(d["o"][j])
            atr_j = float(d["H"]["atr"][k])
            risk_pct = float(source["risk_pct"])
            target_room = float(source["target_room"])
            fake_level = p + target_room + engine.TGT_BUF * atr_j
            fake.append((int(d["ts"][j]), int(j), p, p * (1.0 - risk_pct), fake_level, atr_j))
        control.extend(engine.simulate(d, fake, symbol, enforce_no_overlap=False))

    if not real or len(control) != len(real):
        raise HoldoutError(f"real/control mismatch: real={len(real)} control={len(control)}")
    r_values = np.array([row["R"] for row in real], dtype=float)
    control_r = np.array([row["R"] for row in control], dtype=float)
    timestamps = np.array([row["ts"] for row in real], dtype=np.int64)
    lo, hi = week_boot(r_values, timestamps)

    calendar_quarters = {
        "2025Q4": (START_MS, int(dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)),
        "2026Q1": (int(dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000), int(dt.datetime(2026, 4, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)),
        "2026Q2": (int(dt.datetime(2026, 4, 1, tzinfo=dt.timezone.utc).timestamp() * 1000), signal_end_exclusive),
    }
    quarters = {
        name: {"n": int(mask.sum()), "mean_r": float(r_values[mask].mean()) if mask.any() else None}
        for name, (start, end) in calendar_quarters.items()
        for mask in [(timestamps >= start) & (timestamps < end)]
    }
    midpoint = START_MS + (signal_end_exclusive - START_MS) // 2
    half_masks = (timestamps < midpoint, timestamps >= midpoint)
    halves = [
        {"n": int(mask.sum()), "mean_r": float(r_values[mask].mean()) if mask.any() else None}
        for mask in half_masks
    ]
    if any(row["n"] == 0 for row in halves) or any(row["n"] < 10 for row in quarters.values()):
        raise HoldoutError("insufficient trades in a fixed half or calendar quarter")

    mean_r = float(r_values.mean())
    excess = float(mean_r - control_r.mean())
    death = {
        "mean_r_positive": mean_r > 0,
        "excess_at_least_0_05r": excess >= 0.05,
        "minimum_150_trades": len(r_values) >= 150,
    }
    acceptance = {
        **death,
        "bootstrap_lower_positive": lo > 0,
        "all_three_calendar_quarters_positive": all(float(row["mean_r"]) > 0 for row in quarters.values()),
        "both_fixed_halves_same_positive_sign_and_not_below_minus_0_02": (
            halves[0]["mean_r"] > 0 and halves[1]["mean_r"] > 0
            and min(float(halves[0]["mean_r"]), float(halves[1]["mean_r"])) >= -0.02
        ),
    }
    if not all(death.values()):
        verdict = "REJECT"
    elif all(acceptance.values()):
        verdict = "SHADOW_CANDIDATE_ONLY"
    else:
        verdict = "NO_PROMOTION"
    return {
        "schema_id": "mpl_v3_holdout_result_v2",
        "authority": "research_only_no_live_or_promotion",
        "window": {"start_ms": START_MS, "entry_end_exclusive_ms": signal_end_exclusive, "data_end_exclusive_ms": END_MS_EXCLUSIVE},
        "n": len(r_values),
        "mean_r": mean_r,
        "bootstrap_95": [lo, hi],
        "control_n": len(control_r),
        "control_mean_r": float(control_r.mean()),
        "excess_r": excess,
        "quarters": quarters,
        "halves": halves,
        "signal_counts": signal_counts,
        "death_gates": death,
        "acceptance_gates": acceptance,
        "verdict": verdict,
        "capital_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--allowlist", type=Path, default=ROOT / "research_lab/allowlist_v3.json")
    parser.add_argument("--prereg", type=Path, default=ROOT / "research_lab/prereg/PREREG_MPL_V3_2026_08_12.md")
    parser.add_argument("--engine", type=Path, default=ROOT / "research_lab/mpl_v3.py")
    parser.add_argument("--manifest", type=Path, default=ROOT / "reports/research/mpl_v3_holdout_20260812/unseal_manifest.json")
    parser.add_argument("--result", type=Path, default=ROOT / "reports/research/mpl_v3_holdout_20260812/result.json")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--owner-authorization", default="")
    args = parser.parse_args()

    symbols = json.loads(args.allowlist.read_text(encoding="utf-8"))
    if not isinstance(symbols, list) or len(symbols) != len(set(symbols)) or not symbols:
        raise HoldoutError("allowlist must be a non-empty unique JSON list")
    preflight = metadata_preflight(args.source, symbols)
    code_hashes = {
        str(path.resolve()): _sha256(path)
        for path in (Path(__file__), args.engine, args.prereg, args.allowlist)
    }
    if args.preflight_only:
        print(json.dumps({"status": "READY_METADATA_ONLY", "preflight": preflight, "code_sha256": code_hashes}, indent=2, ensure_ascii=False))
        return 0
    if args.owner_authorization != "owner-explicit-2026-08-12":
        raise HoldoutError("exact one-time owner authorization token is required")
    if args.result.exists():
        raise HoldoutError(f"write-once result already exists: {args.result}")

    manifest = {
        "schema_id": "mpl_v3_holdout_unseal_manifest_v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "owner_authorization": args.owner_authorization,
        "code_sha256": code_hashes,
        "preflight": preflight,
        "window": {"start_ms": START_MS, "end_ms_exclusive": END_MS_EXCLUSIVE},
        "authority": "research_only_no_live_or_promotion",
    }
    _write_once(args.manifest, manifest)

    engine = _load_engine(args.engine, args.source)
    data = engine.load(symbols=symbols, cutoff_ms=END_MS_EXCLUSIVE - 1)
    integrity = validate_loaded_inputs(data, symbols)
    result = evaluate(engine, data, symbols)
    result["input_integrity"] = integrity
    result["manifest_sha256"] = _sha256(args.manifest)
    _write_once(args.result, result)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
