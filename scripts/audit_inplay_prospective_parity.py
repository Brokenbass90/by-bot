#!/usr/bin/env python3
"""Run the exact prospective Inplay replay on sealed-safe historical slices."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.engine import Candle
from scripts.collect_inplay_prospective_shadow import INTERVAL_MS, replay


DEFAULT_DATA = ROOT / "research_lab/data/bybit_eth_m5_preholdout_20240301_20250930/ETHUSDT.json"
DEFAULT_REFERENCE = ROOT / "research_lab/results/path_sim_v4_causal_preholdout_r2/run_passport.json"
FROZEN_BASELINE_RAW_COUNTS = (32, 40, 62, 81)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candles(records: list[dict[str, Any]]) -> list[Candle]:
    return [
        Candle(
            int(row["ts_ms"]), float(row["open"]), float(row["high"]),
            float(row["low"]), float(row["close"]), float(row["volume"]),
        )
        for row in records
    ]


def audit(data_path: Path, reference_passport: Path, *, slice_days: int, slices: int) -> dict[str, Any]:
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    if int(payload.get("end_exclusive_ms") or 0) > 1_759_276_800_000:
        raise RuntimeError("input crosses the 2025-10-01 sealed-holdout boundary")
    records = list(payload.get("records") or [])
    if not records:
        raise RuntimeError("no records")
    reference = json.loads(reference_passport.read_text(encoding="utf-8"))
    reference_hashes = {
        Path(str(row["path"])).name: str(row["sha256"])
        for row in reference.get("code", [])
        if str(row.get("path") or "").endswith(("strategies/inplay_breakout.py", "research_lab/strategy_adapter.py"))
    }
    current_hashes = {
        "inplay_breakout.py": _sha256(ROOT / "strategies/inplay_breakout.py"),
        "strategy_adapter.py": _sha256(ROOT / "research_lab/strategy_adapter.py"),
    }
    window_ms = int(slice_days) * 86_400_000
    final_exclusive = int(records[-1]["ts_ms"]) + INTERVAL_MS
    results = []
    for ordinal in range(int(slices)):
        right = final_exclusive - ordinal * window_ms
        left = right - window_ms
        selected = [row for row in records if left <= int(row["ts_ms"]) < right]
        candles = _candles(selected)
        if len(candles) < 1_000:
            raise RuntimeError(f"slice {ordinal} has only {len(candles)} bars")
        state = replay(candles, {"prospective_start_ts_ms": int(candles[0].ts) + INTERVAL_MS, "events": []})
        results.append({
            "slice": ordinal,
            "start_ts_ms": int(candles[0].ts),
            "end_exclusive_ts_ms": int(candles[-1].ts) + INTERVAL_MS,
            "bars": len(candles),
            "raw_signals": int(state["raw_signal_count_after_prospective"]),
            "frequency_per_day": float(state["raw_signal_frequency_per_day_lookback"]),
        })
    return {
        "schema_id": "inplay_prospective_parity_audit_v1",
        "authority": "research_only_no_live_or_promotion",
        "sealed_holdout_rows_decoded": 0,
        "data_path": str(data_path),
        "data_sha256": _sha256(data_path),
        "reference_passport_sha256": str(reference.get("passport_sha256") or ""),
        "reference_code_hashes": reference_hashes,
        "current_code_hashes": current_hashes,
        "current_code_matches_reference": all(reference_hashes.get(name) == digest for name, digest in current_hashes.items()),
        "slice_days": int(slice_days),
        "slices": results,
        "interpretation": "Exact prospective code on pre-holdout slices; signal frequency only, not edge or promotion evidence.",
    }


def frozen_baseline_errors(result: dict[str, Any]) -> list[str]:
    """Return hard startup blockers for the frozen prospective contract.

    These checks deliberately bind only code identity and signal *frequency* on
    pre-holdout data.  They do not make any claim about edge or promotion.
    """
    errors: list[str] = []
    sealed_rows = result.get("sealed_holdout_rows_decoded")
    if sealed_rows is None or int(sealed_rows) != 0:
        errors.append("sealed_holdout_was_decoded")
    if not bool(result.get("current_code_matches_reference")):
        errors.append("code_hash_mismatch")
    observed = tuple(
        int(row.get("raw_signals") or 0)
        for row in list(result.get("slices") or [])
    )
    if observed != FROZEN_BASELINE_RAW_COUNTS:
        errors.append(
            "historical_frequency_mismatch:"
            f"expected={list(FROZEN_BASELINE_RAW_COUNTS)}:observed={list(observed)}"
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--reference-passport", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--slice-days", type=int, default=35)
    parser.add_argument("--slices", type=int, default=4)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require-frozen-baseline",
        action="store_true",
        help="exit nonzero unless hashes and pre-holdout signal counts match the frozen contract",
    )
    args = parser.parse_args()
    result = audit(args.data, args.reference_passport, slice_days=args.slice_days, slices=args.slices)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    if args.require_frozen_baseline:
        errors = frozen_baseline_errors(result)
        if errors:
            print(json.dumps({"startup_gate": "FAIL", "errors": errors}, ensure_ascii=False))
            return 2
        print(json.dumps({"startup_gate": "PASS", "authority": "research_only"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
