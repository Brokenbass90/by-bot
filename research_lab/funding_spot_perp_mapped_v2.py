#!/usr/bin/env python3
"""V2 funding diagnostic with a frozen cross-market data parity gate."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab import funding_spot_perp_mapped_v1 as V1
from research_lab.run_passport import AUTHORITY, build_passport, write_passport

MAX_ABS_BASIS = 0.05
PREREG = ROOT / "research_lab/prereg/PREREG_FUNDING_SPOT_PERP_MAPPED_V2_2026_08_13.md"
DEFAULT_OUT = ROOT / "research_lab/results/funding_spot_perp_mapped_v2_20260813"


def _basis_ok(spot: float, perp: float) -> bool:
    return abs(float(spot) / float(perp) - 1.0) <= MAX_ABS_BASIS


def run(out: Path) -> dict[str, Any]:
    spot_status = V1._validate_status(V1.SPOT, allow_failed=True)
    V1._validate_status(V1.PERP, allow_failed=False)
    V1._validate_status(V1.FUNDING, allow_failed=False)
    spot_symbols = {p.stem for p in (V1.SPOT / "bars").glob("*.json")}
    perp_symbols = {p.stem for p in (V1.PERP / "bars").glob("*.json")}
    funding_symbols = {p.stem for p in (V1.FUNDING / "funding").glob("*.json")}
    common = sorted(spot_symbols & perp_symbols & funding_symbols)
    if len(common) < 20:
        raise V1.DiagnosticError(f"exact mapped universe unexpectedly small: {len(common)}")

    manifest = V1._manifest(common)
    manifest["cross_market_parity_gate"] = {"max_abs_basis_fraction": MAX_ABS_BASIS}
    manifest_path = out / "input_manifest.json"
    V1._write_once(manifest_path, manifest)
    request = {
        "schema_id": "research_run_passport_request_v1",
        "authority": AUTHORITY,
        "promotion_authority": False,
        "live_or_broker_calls": False,
        "experiment_id": "funding_spot_perp_mapped_v2_20260813",
        "code_paths": [
            "research_lab/funding_spot_perp_mapped_v2.py",
            "research_lab/funding_spot_perp_mapped_v1.py",
            str(PREREG.relative_to(ROOT)),
        ],
        "inputs": [{
            "path": str(manifest_path.relative_to(ROOT)),
            "role": "hashed exact-mapped public input manifest plus parity gate",
            "temporal_data": True,
            "contains_sealed_holdout": False,
            "data_window": manifest["window"],
        }],
        "measurement_contract": {
            "engine": "exact_spot_long_perp_short_next_open_parity_v2",
            "timeframe": "1D plus crossed funding events",
            "costs": V1.COSTS_BPS,
            "label_contract": "60d_funding_top3_next_open_hold30d_basis_le_5pct",
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
        srows = V1._records(V1.SPOT / "bars" / f"{symbol}.json", "records", "ts_ms")
        prows = V1._records(V1.PERP / "bars" / f"{symbol}.json", "records", "ts_ms")
        frows = V1._records(V1.FUNDING / "funding" / f"{symbol}.json", "records", "funding_time_ms")
        spot_open[symbol] = {int(row["ts_ms"]): float(row["open"]) for row in srows}
        perp_open[symbol] = {int(row["ts_ms"]): float(row["open"]) for row in prows}
        funding[symbol] = [(int(row["funding_time_ms"]), float(row["funding_rate"])) for row in frows]

    calendar = sorted(ts for ts in perp_open["BTCUSDT"] if V1.START_MS <= ts < V1.END_MS)
    periods = []
    quarantined: dict[str, int] = {}
    for signal_i in range(V1.LOOKBACK_DAYS, len(calendar) - V1.HOLD_DAYS - 1, V1.HOLD_DAYS):
        signal_ts = calendar[signal_i]
        entry_ts = calendar[signal_i + 1]
        exit_ts = calendar[signal_i + 1 + V1.HOLD_DAYS]
        trailing_start = signal_ts - V1.LOOKBACK_DAYS * V1.DAY_MS
        scores = []
        for symbol in common:
            if any(ts not in spot_open[symbol] or ts not in perp_open[symbol] for ts in (entry_ts, exit_ts)):
                continue
            if not (
                _basis_ok(spot_open[symbol][entry_ts], perp_open[symbol][entry_ts])
                and _basis_ok(spot_open[symbol][exit_ts], perp_open[symbol][exit_ts])
            ):
                quarantined[symbol] = quarantined.get(symbol, 0) + 1
                continue
            past = [rate for ts, rate in funding[symbol] if trailing_start < ts <= signal_ts]
            if len(past) < 30:
                continue
            score = sum(past)
            if score > 0:
                scores.append((score, symbol))
        scores.sort(reverse=True)
        if len(scores) < V1.TOP_K:
            continue
        chosen = [symbol for _, symbol in scores[:V1.TOP_K]]
        eligible = [symbol for _, symbol in scores]

        def gross(symbol: str) -> dict[str, float]:
            crossed = [rate for ts, rate in funding[symbol] if entry_ts < ts <= exit_ts]
            return V1.pair_return(
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
            "selected_gross_return": V1._mean([row["net_return"] for row in chosen_rows]),
            "basket_gross_return": V1._mean([row["net_return"] for row in eligible_rows]),
            "selected_funding_received": V1._mean([row["funding_received"] for row in chosen_rows]),
            "selected_basis_return": V1._mean([row["basis_return"] for row in chosen_rows]),
        })

    scenarios = {name: V1._scenario(periods, cost) for name, cost in V1.COSTS_BPS.items()}
    stress = scenarios["stress_51bps"]
    halves = stress["selection_edge_halves_annualized_pct"]
    candidate = (
        len(periods) >= 12
        and float(stress["selected_annualized_pair_notional_pct"] or -1) > 0
        and all(value is not None and value > 0 for value in halves)
    )
    result = {
        "schema_id": "funding_spot_perp_mapped_result_v2",
        "authority": AUTHORITY,
        "capital_authorized": False,
        "promotion_authorized": False,
        "survivorship_resolved": False,
        "sealed_holdout_rows_decoded": 0,
        "passport_sha256": passport["passport_sha256"],
        "requested_symbols": int(spot_status.get("requested") or 0),
        "spot_completed_symbols": len(spot_symbols),
        "exact_mapped_symbols": len(common),
        "cross_market_parity_gate": {"max_abs_basis_fraction": MAX_ABS_BASIS},
        "quarantined_symbol_periods": quarantined,
        "periods": periods,
        "scenarios": scenarios,
        "verdict": "CANDIDATE_DIAGNOSTIC_ONLY" if candidate else "REJECT",
        "limitations": [
            "current-survivor universe; PIT delistings unresolved",
            "daily open proxy omits spread, book impact, borrow, transfer and hedge-failure risk",
            "historical selection rule was previously explored on eight symbols",
        ],
    }
    V1._write_once(out / "result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    result = run(args.out.resolve())
    print(json.dumps({
        "verdict": result["verdict"],
        "exact_mapped_symbols": result["exact_mapped_symbols"],
        "quarantined_symbol_periods": result["quarantined_symbol_periods"],
        "scenarios": result["scenarios"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
