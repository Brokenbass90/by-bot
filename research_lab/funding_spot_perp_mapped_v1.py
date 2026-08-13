#!/usr/bin/env python3
"""Exact-mapped spot/perpetual funding diagnostic; no broker authority."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab.run_passport import AUTHORITY, build_passport, write_passport

START_MS = 1672531200000
END_MS = 1759276800000
DAY_MS = 86_400_000
LOOKBACK_DAYS = 60
HOLD_DAYS = 30
TOP_K = 3
COSTS_BPS = {"base_31bps": 31.0, "stress_51bps": 51.0}
PREREG = ROOT / "research_lab/prereg/PREREG_FUNDING_SPOT_PERP_MAPPED_V1_2026_08_13.md"
SPOT = ROOT / "research_lab/data/bybit_spot_daily_preholdout_2023_20250930"
PERP = ROOT / "research_lab/data/bybit_daily_preholdout_2023_20250930"
FUNDING = ROOT / "research_lab/data/bybit_public_preholdout_2023_20250930"
DEFAULT_OUT = ROOT / "research_lab/results/funding_spot_perp_mapped_v1_20260813"


class DiagnosticError(RuntimeError):
    pass


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DiagnosticError(f"{path}: expected object")
    return value


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def _write_once(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise DiagnosticError(f"write-once output exists: {path}") from exc
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def pair_return(
    spot_entry: float,
    spot_exit: float,
    perp_entry: float,
    perp_exit: float,
    funding_rates: Iterable[float],
    *,
    cost_bps: float,
) -> dict[str, float]:
    prices = (spot_entry, spot_exit, perp_entry, perp_exit)
    if not all(math.isfinite(float(x)) and float(x) > 0 for x in prices):
        raise ValueError("prices must be positive and finite")
    if not math.isfinite(cost_bps) or cost_bps < 0:
        raise ValueError("cost_bps must be finite and non-negative")
    spot = float(spot_exit) / float(spot_entry) - 1.0
    perp_short = -(float(perp_exit) / float(perp_entry) - 1.0)
    funding = sum(float(rate) for rate in funding_rates)
    cost = float(cost_bps) / 10_000.0
    return {
        "spot_return": spot,
        "perp_short_return": perp_short,
        "funding_received": funding,
        "basis_return": spot + perp_short,
        "cost": cost,
        "net_return": spot + perp_short + funding - cost,
    }


def _validate_status(root: Path, *, allow_failed: bool) -> dict[str, Any]:
    status = _read(root / "status.json")
    if status.get("state") != "complete":
        raise DiagnosticError(f"{root}: incomplete input")
    if status.get("private_api_calls") is not False or status.get("orders_or_risk_mutation") is not False:
        raise DiagnosticError(f"{root}: unsafe authority")
    if not allow_failed and status.get("failed"):
        raise DiagnosticError(f"{root}: failures present")
    boundary = int(status.get("end_exclusive_ms") or (int(status.get("as_of_ms") or 0) + 1))
    if boundary > END_MS:
        raise DiagnosticError(f"{root}: crosses sealed boundary")
    return status


def _records(path: Path, key: str, ts_key: str) -> list[dict[str, Any]]:
    payload = _read(path)
    rows = list(payload.get(key) or [])
    if payload.get("payload_sha256") and payload["payload_sha256"] != _canonical_sha(rows):
        # Historical funding files use a newline-aware hash and are validated
        # by their archive receipt; daily bars use this exact canonical hash.
        if ts_key == "ts_ms":
            raise DiagnosticError(f"{path}: payload hash mismatch")
    if any(int(row[ts_key]) >= END_MS for row in rows):
        raise DiagnosticError(f"{path}: sealed row present")
    return rows


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def _annualized(values: list[float]) -> float | None:
    if not values:
        return None
    return _mean(values) * (365.0 / HOLD_DAYS) * 100.0


def _scenario(periods: list[dict[str, Any]], cost_bps: float) -> dict[str, Any]:
    selected = [float(row["selected_gross_return"]) - cost_bps / 10_000.0 for row in periods]
    basket = [float(row["basket_gross_return"]) - cost_bps / 10_000.0 for row in periods]
    edge = [a - b for a, b in zip(selected, basket)]
    half = len(edge) // 2
    halves = [edge[:half], edge[half:]]
    return {
        "cost_bps": cost_bps,
        "periods": len(periods),
        "selected_annualized_pair_notional_pct": _annualized(selected),
        "selected_annualized_on_two_leg_gross_capital_pct": (
            _annualized(selected) / 2.0 if selected else None
        ),
        "basket_annualized_pair_notional_pct": _annualized(basket),
        "selection_edge_annualized_pct": _annualized(edge),
        "selection_edge_halves_annualized_pct": [_annualized(part) for part in halves],
        "positive_periods": sum(value > 0 for value in selected),
        "red_periods": sum(value < 0 for value in selected),
        "selected_total_simple_pct": sum(selected) * 100.0,
        "basket_total_simple_pct": sum(basket) * 100.0,
    }


def _manifest(common: list[str]) -> dict[str, Any]:
    rows = []
    for symbol in common:
        paths = {
            "spot": SPOT / "bars" / f"{symbol}.json",
            "perp": PERP / "bars" / f"{symbol}.json",
            "funding": FUNDING / "funding" / f"{symbol}.json",
        }
        rows.append({
            "symbol": symbol,
            **{f"{name}_sha256": _sha(path) for name, path in paths.items()},
            **{f"{name}_bytes": path.stat().st_size for name, path in paths.items()},
        })
    return {
        "schema_id": "funding_spot_perp_mapped_input_manifest_v1",
        "window": {"start_utc": "2023-01-01T00:00:00Z", "end_utc_exclusive": "2025-10-01T00:00:00Z"},
        "sealed_holdout_rows_decoded": 0,
        "exact_mapped_symbols": common,
        "files": rows,
        "files_sha256": _canonical_sha(rows),
    }


def run(out: Path) -> dict[str, Any]:
    spot_status = _validate_status(SPOT, allow_failed=True)
    _validate_status(PERP, allow_failed=False)
    _validate_status(FUNDING, allow_failed=False)
    spot_symbols = {p.stem for p in (SPOT / "bars").glob("*.json")}
    perp_symbols = {p.stem for p in (PERP / "bars").glob("*.json")}
    funding_symbols = {p.stem for p in (FUNDING / "funding").glob("*.json")}
    common = sorted(spot_symbols & perp_symbols & funding_symbols)
    if len(common) < 20:
        raise DiagnosticError(f"exact mapped universe unexpectedly small: {len(common)}")

    manifest = _manifest(common)
    manifest_path = out / "input_manifest.json"
    _write_once(manifest_path, manifest)
    request = {
        "schema_id": "research_run_passport_request_v1",
        "authority": AUTHORITY,
        "promotion_authority": False,
        "live_or_broker_calls": False,
        "experiment_id": "funding_spot_perp_mapped_v1_20260813",
        "code_paths": [
            "research_lab/funding_spot_perp_mapped_v1.py",
            str(PREREG.relative_to(ROOT)),
        ],
        "inputs": [{
            "path": str(manifest_path.relative_to(ROOT)),
            "role": "hashed exact-mapped public input manifest",
            "temporal_data": True,
            "contains_sealed_holdout": False,
            "data_window": manifest["window"],
        }],
        "measurement_contract": {
            "engine": "exact_spot_long_perp_short_next_open_v1",
            "timeframe": "1D plus crossed funding events",
            "costs": COSTS_BPS,
            "label_contract": "60d_funding_top3_next_open_hold30d",
            "split_contract": "nonoverlap_periods_plus_fixed_halves",
            "universe": common,
            "window": manifest["window"],
        },
        "search_contract": {"variant_count": 1, "random_seed": 20260813, "pre_registered": True},
        "sealed_holdouts": [{
            "id": "mpl_reserved_2025_10_2026_06",
            "start_utc": "2025-10-01T00:00:00Z",
            "end_utc_exclusive": "2026-07-01T00:00:00Z",
            "must_not_be_read": True,
        }],
    }
    passport = build_passport(request, project_root=ROOT)
    write_passport(out / "run_passport.json", passport)

    spot_open: dict[str, dict[int, float]] = {}
    perp_open: dict[str, dict[int, float]] = {}
    funding: dict[str, list[tuple[int, float]]] = {}
    for symbol in common:
        srows = _records(SPOT / "bars" / f"{symbol}.json", "records", "ts_ms")
        prows = _records(PERP / "bars" / f"{symbol}.json", "records", "ts_ms")
        frows = _records(FUNDING / "funding" / f"{symbol}.json", "records", "funding_time_ms")
        spot_open[symbol] = {int(row["ts_ms"]): float(row["open"]) for row in srows}
        perp_open[symbol] = {int(row["ts_ms"]): float(row["open"]) for row in prows}
        funding[symbol] = [(int(row["funding_time_ms"]), float(row["funding_rate"])) for row in frows]

    calendar = sorted(ts for ts in perp_open["BTCUSDT"] if START_MS <= ts < END_MS)
    periods = []
    start_index = LOOKBACK_DAYS
    for signal_i in range(start_index, len(calendar) - HOLD_DAYS - 1, HOLD_DAYS):
        signal_ts = calendar[signal_i]
        entry_ts = calendar[signal_i + 1]
        exit_ts = calendar[signal_i + 1 + HOLD_DAYS]
        trailing_start = signal_ts - LOOKBACK_DAYS * DAY_MS
        scores = []
        for symbol in common:
            if any(ts not in spot_open[symbol] or ts not in perp_open[symbol] for ts in (entry_ts, exit_ts)):
                continue
            past = [rate for ts, rate in funding[symbol] if trailing_start < ts <= signal_ts]
            if len(past) < 30:
                continue
            score = sum(past)
            if score > 0:
                scores.append((score, symbol))
        scores.sort(reverse=True)
        if len(scores) < TOP_K:
            continue
        chosen = [symbol for _, symbol in scores[:TOP_K]]
        eligible = [symbol for _, symbol in scores]

        def gross(symbol: str) -> dict[str, float]:
            crossed = [rate for ts, rate in funding[symbol] if entry_ts < ts <= exit_ts]
            return pair_return(
                spot_open[symbol][entry_ts], spot_open[symbol][exit_ts],
                perp_open[symbol][entry_ts], perp_open[symbol][exit_ts],
                crossed, cost_bps=0.0,
            )

        chosen_rows = [gross(symbol) for symbol in chosen]
        eligible_rows = [gross(symbol) for symbol in eligible]
        periods.append({
            "signal_ts_ms": signal_ts,
            "entry_ts_ms": entry_ts,
            "exit_ts_ms": exit_ts,
            "selected": chosen,
            "eligible_count": len(eligible),
            "selected_gross_return": _mean([row["net_return"] for row in chosen_rows]),
            "basket_gross_return": _mean([row["net_return"] for row in eligible_rows]),
            "selected_funding_received": _mean([row["funding_received"] for row in chosen_rows]),
            "selected_basis_return": _mean([row["basis_return"] for row in chosen_rows]),
        })

    scenarios = {name: _scenario(periods, cost) for name, cost in COSTS_BPS.items()}
    stress = scenarios["stress_51bps"]
    halves = stress["selection_edge_halves_annualized_pct"]
    candidate = (
        len(periods) >= 12
        and float(stress["selected_annualized_pair_notional_pct"] or -1) > 0
        and all(value is not None and value > 0 for value in halves)
    )
    result = {
        "schema_id": "funding_spot_perp_mapped_result_v1",
        "authority": AUTHORITY,
        "capital_authorized": False,
        "promotion_authorized": False,
        "survivorship_resolved": False,
        "sealed_holdout_rows_decoded": 0,
        "passport_sha256": passport["passport_sha256"],
        "requested_symbols": int(spot_status.get("requested") or 0),
        "spot_completed_symbols": len(spot_symbols),
        "exact_mapped_symbols": len(common),
        "exact_mapping": common,
        "periods": periods,
        "scenarios": scenarios,
        "verdict": "CANDIDATE_DIAGNOSTIC_ONLY" if candidate else "REJECT",
        "limitations": [
            "current-survivor universe; PIT delistings unresolved",
            "spot archive covers only exact Bybit spot symbols and failed unsupported aliases",
            "daily open proxy omits spread, book impact, borrow, transfer and hedge-failure risk",
            "historical selection rule was previously explored on eight symbols",
        ],
    }
    _write_once(out / "result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    result = run(args.out.resolve())
    print(json.dumps({
        "verdict": result["verdict"],
        "exact_mapped_symbols": result["exact_mapped_symbols"],
        "scenarios": result["scenarios"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
