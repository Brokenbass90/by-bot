#!/usr/bin/env python3
"""Frozen next-open and funding-aware XSEC replay; research only."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab import xsec_v3_reference as X
from research_lab.run_passport import (
    AUTHORITY as PASSPORT_AUTHORITY,
    build_passport,
    write_passport,
)
from research_lab.xsec_causal_contract import period_return

PREREG = ROOT / "research_lab/prereg/PREREG_XSEC_CAUSAL_V1_2026_08_12.md"
DAILY = ROOT / "research_lab/data/bybit_daily_preholdout_2023_20250930"
FUNDING = ROOT / "research_lab/data/bybit_public_preholdout_2023_20250930"
OUT = ROOT / "research_lab/results/xsec_causal_v1_20260812"
START = pd.Timestamp("2023-01-01", tz="UTC")
END = pd.Timestamp("2025-10-01", tz="UTC")
MATURITY_DAYS = 390
HOLD_DAYS = 3
COSTS = {"base_15bps": 0.0015, "stress_30bps": 0.0030}


class ReplayError(RuntimeError):
    pass


def canonical_sha(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReplayError(f"{path}: expected object")
    return value


def write_once(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ReplayError(f"write-once output exists: {path}") from exc
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def validate_status(root: Path, schema: str) -> dict[str, Any]:
    status = read_json(root / "status.json")
    if status.get("schema_id") != schema or status.get("state") != "complete":
        raise ReplayError(f"{root}: incomplete or wrong schema")
    if status.get("private_api_calls") is not False or status.get("orders_or_risk_mutation") is not False:
        raise ReplayError(f"{root}: unsafe authority")
    if status.get("failed"):
        raise ReplayError(f"{root}: failures present")
    end_ms = int(status.get("end_exclusive_ms") or (int(status.get("as_of_ms") or 0) + 1))
    if end_ms > int(END.timestamp() * 1000):
        raise ReplayError(f"{root}: input crosses sealed boundary")
    return status


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.Timestamp], dict[str, list[tuple[int, float]]], dict[str, Any]]:
    daily_status = validate_status(DAILY, "bybit_daily_preholdout_status_v1")
    funding_status = validate_status(FUNDING, "bybit_research_archive_status_v1")
    daily_files = sorted((DAILY / "bars").glob("*.json"))
    funding_files = sorted((FUNDING / "funding").glob("*.json"))
    if [p.stem for p in daily_files] != [p.stem for p in funding_files]:
        raise ReplayError("daily/funding symbol sets differ")
    expected = int(daily_status.get("requested") or 0)
    if len(daily_files) != expected or expected != int(funding_status.get("requested_symbol_count") or 0):
        raise ReplayError("input file count mismatch")

    opens, closes, launch, funding = {}, {}, {}, {}
    manifest_rows = []
    for daily_path, funding_path in zip(daily_files, funding_files):
        symbol = daily_path.stem
        daily = read_json(daily_path)
        fpay = read_json(funding_path)
        drows = list(daily.get("records") or [])
        frows = list(fpay.get("records") or [])
        if daily.get("payload_sha256") != canonical_sha(drows):
            raise ReplayError(f"{symbol}: daily hash mismatch")
        # Funding archive uses a canonical newline in its historical hash; the
        # validator already proves it.  Recheck temporal boundary here.
        times = [int(row["ts_ms"]) for row in drows]
        ftimes = [int(row["funding_time_ms"]) for row in frows]
        if any(ts >= int(END.timestamp() * 1000) for ts in times + ftimes):
            raise ReplayError(f"{symbol}: sealed timestamp present")
        idx = pd.to_datetime(times, unit="ms", utc=True)
        opens[symbol] = pd.Series([float(row["open"]) for row in drows], index=idx)
        closes[symbol] = pd.Series([float(row["close"]) for row in drows], index=idx)
        instrument = dict(fpay.get("instrument") or {})
        launch_ms = int(instrument.get("launchTime") or (times[0] if times else 0))
        launch[symbol] = pd.to_datetime(launch_ms, unit="ms", utc=True)
        funding[symbol] = [(int(row["funding_time_ms"]), float(row["funding_rate"])) for row in frows]
        manifest_rows.append({
            "symbol": symbol, "daily_file_sha256": hashlib.sha256(daily_path.read_bytes()).hexdigest(),
            "funding_file_sha256": hashlib.sha256(funding_path.read_bytes()).hexdigest(),
            "daily_rows": len(drows), "funding_rows": len(frows),
        })
    op = pd.DataFrame(opens).sort_index().loc[START:END - pd.Timedelta(nanoseconds=1)]
    cl = pd.DataFrame(closes).sort_index().loc[START:END - pd.Timedelta(nanoseconds=1)]
    manifest = {
        "schema_id": "xsec_causal_v1_input_manifest", "window": [str(START), str(END)],
        "sealed_holdout_rows_decoded": 0, "symbols": len(manifest_rows),
        "files": manifest_rows, "payload_sha256": canonical_sha(manifest_rows),
    }
    return op, cl, launch, funding, manifest


def market_stress(closes: pd.DataFrame, i: int) -> bool:
    current = (closes.iloc[i] / closes.iloc[i - 1] - 1.0).abs().median(skipna=True)
    hist = []
    for j in range(max(1, i - X.STRESS_LOOKBACK_DAYS), i):
        hist.append(float((closes.iloc[j] / closes.iloc[j - 1] - 1.0).abs().median(skipna=True)))
    return X.is_market_stress([x for x in hist if math.isfinite(x)], float(current))


def vol_target(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    past = []
    for row in rows:
        raw = float(row["net_return"])
        lev = X.leverage(past)
        item = dict(row)
        for key in ("price_return", "funding_cashflow", "cost", "net_return"):
            item[key] = float(item[key]) * lev
        item["leverage"] = lev
        out.append(item)
        past.append(raw)
    return out


def phase(opens: pd.DataFrame, closes: pd.DataFrame, launch: dict[str, pd.Timestamp], funding, offset: int, cost: float):
    rows, skips = [], {"stress": 0, "universe": 0, "missing_execution": 0}
    need = max(X.LOOKBACKS) + 2
    for i in range(need + offset, len(closes) - HOLD_DAYS - 1, HOLD_DAYS):
        signal_day = closes.index[i]
        entry_i, exit_i = i + 1, i + 1 + HOLD_DAYS
        if market_stress(closes, i):
            skips["stress"] += 1
            continue
        history = {}
        for symbol in closes.columns:
            if signal_day - launch[symbol] < pd.Timedelta(days=MATURITY_DAYS):
                continue
            series = closes[symbol].iloc[i - max(X.LOOKBACKS): i + 1]
            if len(series) < max(X.LOOKBACKS) + 1 or series.isna().any():
                continue
            values = series.astype(float).tolist()
            if X.is_post_event_noise(values, max(X.LOOKBACKS)):
                continue
            history[symbol] = values
        if len(history) < X.MIN_UNIVERSE:
            skips["universe"] += 1
            continue
        weights = X.target_weights(history)
        if not weights:
            skips["universe"] += 1
            continue
        entry = {s: float(opens[s].iloc[entry_i]) for s in weights}
        exit_ = {s: float(opens[s].iloc[exit_i]) for s in weights}
        try:
            result = period_return(
                weights, entry, exit_, funding,
                entry_ts_ms=int(opens.index[entry_i].timestamp() * 1000),
                exit_ts_ms=int(opens.index[exit_i].timestamp() * 1000),
                round_trip_cost_fraction=cost,
            )
        except ValueError:
            skips["missing_execution"] += 1
            continue
        result.update({
            "signal_day": signal_day.date().isoformat(),
            "entry_day": opens.index[entry_i].date().isoformat(),
            "exit_day": opens.index[exit_i].date().isoformat(),
            "positions": len(weights), "gross_weight": sum(abs(v) for v in weights.values()),
        })
        rows.append(result)
    return vol_target(rows), skips


def metrics(values: list[float]) -> dict[str, float | int]:
    arr = np.asarray(values, dtype=float)
    if len(arr) < 8:
        return {"n": len(arr)}
    eq = np.cumprod(1.0 + arr)
    years = len(arr) * HOLD_DAYS / 365.0
    sd = float(arr.std(ddof=1))
    return {
        "n": len(arr), "total_pct": float((eq[-1] - 1.0) * 100),
        "cagr_pct": float((eq[-1] ** (1 / years) - 1) * 100),
        "max_drawdown_pct": float(np.max(1 - eq / np.maximum.accumulate(eq)) * 100),
        "sharpe_ann": float(arr.mean() / sd * math.sqrt(365 / HOLD_DAYS)) if sd > 0 else 0.0,
        "tstat": float(arr.mean() / sd * math.sqrt(len(arr))) if sd > 0 else 0.0,
    }


def scenario(opens, closes, launch, funding, cost):
    phases, skips = [], []
    for offset in (0, 1, 2):
        rows, skip = phase(opens, closes, launch, funding, offset, cost)
        phases.append(rows); skips.append(skip)
    m = min(len(rows) for rows in phases)
    combined = []
    for i in range(m):
        row = {key: sum(float(phases[p][i][key]) for p in range(3)) / 3.0 for key in (
            "price_return", "funding_cashflow", "cost", "net_return"
        )}
        row["date"] = phases[0][i]["exit_day"]
        combined.append(row)
    ser = pd.Series([row["net_return"] for row in combined], index=pd.to_datetime([row["date"] for row in combined], utc=True))
    yearly = {str(y): metrics(group.tolist()) for y, group in ser.groupby(ser.index.year)}
    monthly = {}
    for key, group in ser.groupby(ser.index.to_period("M")):
        monthly[str(key)] = float((np.prod(1 + group.to_numpy()) - 1) * 100)
    return {
        "metrics": metrics(ser.tolist()),
        "attribution_pct_simple_sum": {
            key: sum(row[key] for row in combined) * 100 for key in ("price_return", "funding_cashflow", "cost")
        },
        "phase_metrics": [metrics([float(row["net_return"]) for row in phase_rows]) for phase_rows in phases],
        "yearly": yearly, "monthly": monthly,
        "red_months": sum(value < 0 for value in monthly.values()), "months": len(monthly),
        "skips": skips, "rows": combined,
    }


def build_passport_before_metrics(manifest_path: Path) -> dict[str, Any]:
    request = {
        "schema_id": "research_run_passport_request_v1", "authority": PASSPORT_AUTHORITY,
        "promotion_authority": False, "live_or_broker_calls": False,
        "experiment_id": "xsec_causal_v1_20260812",
        "code_paths": [
            "research_lab/xsec_causal_replay.py", "research_lab/xsec_causal_contract.py",
            "research_lab/xsec_v3_reference.py", str(PREREG.relative_to(ROOT)),
        ],
        "inputs": [{
            "path": str(manifest_path.relative_to(ROOT)), "role": "hashed_daily_and_funding_manifest",
            "temporal_data": True, "contains_sealed_holdout": False,
            "data_window": {"start_utc": "2023-01-01T00:00:00Z", "end_utc_exclusive": "2025-10-01T00:00:00Z"},
        }],
        "measurement_contract": {
            "engine": "xsec_causal_v1_next_open", "timeframe": "1D",
            "universe": [p.stem for p in sorted((DAILY / "bars").glob("*.json"))],
            "window": {"start_utc": "2023-01-01T00:00:00Z", "end_utc_exclusive": "2025-10-01T00:00:00Z"},
            "costs": COSTS, "label_contract": "next_open_to_open_plus_crossed_funding",
            "split_contract": "calendar_years_plus_phases_no_selection",
        },
        "search_contract": {"variant_count": 1, "random_seed": 20260812, "pre_registered": True},
        "sealed_holdouts": [{
            "id": "mpl_reserved_2025_10_2026_06", "must_not_be_read": True,
            "start_utc": "2025-10-01T00:00:00Z", "end_utc_exclusive": "2026-07-01T00:00:00Z",
        }],
    }
    passport = build_passport(request, project_root=ROOT)
    write_passport(OUT / "run_passport.json", passport)
    return passport


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-token", required=True)
    args = parser.parse_args()
    if args.owner_token != "RUN_XSEC_CAUSAL_V1_ONCE":
        raise ReplayError("exact owner token required")
    if (OUT / "result.json").exists() or (OUT / "run_passport.json").exists():
        raise ReplayError("write-once run already exists")
    opens, closes, launch, funding, manifest = load_inputs()
    write_once(OUT / "input_manifest.json", manifest)
    passport = build_passport_before_metrics(OUT / "input_manifest.json")
    results = {name: scenario(opens, closes, launch, funding, cost) for name, cost in COSTS.items()}
    base, stress = results["base_15bps"], results["stress_30bps"]
    years = base["yearly"]
    phase_ok = all(float(row.get("total_pct", -1)) >= 0 for row in base["phase_metrics"])
    if float(base["metrics"].get("cagr_pct", -1)) <= 0 or float(stress["metrics"].get("total_pct", -1)) <= 0:
        verdict = "REJECT"
    elif (
        float(base["metrics"].get("sharpe_ann", 0)) >= 0.5
        and all(float(years.get(y, {}).get("total_pct", -1)) > 0 for y in ("2024", "2025"))
        and phase_ok
    ):
        verdict = "SHADOW_CANDIDATE_ONLY"
    else:
        verdict = "INCONCLUSIVE"
    output = {
        "schema_id": "xsec_causal_v1_result", "authority": "research_only_no_capital",
        "promotion_authorized": False, "sealed_holdout_rows_decoded": 0,
        "passport_sha256": passport["passport_sha256"], "verdict": verdict,
        "survivorship_resolved": False, "results": results,
    }
    write_once(OUT / "result.json", output)
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
