#!/usr/bin/env python3
"""Causal BTC-regime explanation test for the observed SOL RMR1 pocket."""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab.run_passport import AUTHORITY, build_passport, write_passport
from scripts.backtest_candidates import WINDOW, load_1h_ohlc
from strategies.range_mean_reversion_v1 import RangeMeanReversionV1

INPUT = ROOT / "research_lab/data/bybit_major8_m5_preholdout_20240301_20250930"
PREREG = ROOT / "research_lab/prereg/PREREG_RMR1_SOL_REGIME_V1_2026_08_13.md"
DEFAULT_OUT = ROOT / "research_lab/results/rmr1_sol_regime_v1_20260813"
HOURS_30D = 720
HOURS_180D = 4320


def _write_once(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"write-once output exists: {path}") from exc
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _trades(ts, o, h, l, c) -> list[dict[str, Any]]:
    strategy = RangeMeanReversionV1()
    out = []
    i, n = WINDOW, len(ts)
    while i < n - 1:
        signal = strategy.signal(h[i - WINDOW:i + 1], l[i - WINDOW:i + 1], c[i - WINDOW:i + 1])
        if not signal:
            i += 1
            continue
        side = signal["side"]
        entry = o[i + 1]
        stop = signal["sl"] + (entry - signal["entry"])
        target = signal["tp"] + (entry - signal["entry"])
        stop_pct = abs(entry - stop) / entry
        if stop_pct <= 0:
            i += 1
            continue
        j, exit_price, reason = i + 1, None, ""
        while j < n:
            hit_stop = l[j] <= stop if side == "long" else h[j] >= stop
            hit_target = h[j] >= target if side == "long" else l[j] <= target
            if hit_stop:
                exit_price, reason = stop, "SL"
                break
            if hit_target:
                exit_price, reason = target, "TP"
                break
            if j - i >= 96:
                exit_price, reason = c[j], "time"
                break
            j += 1
        if exit_price is None:
            exit_price, reason, j = c[-1], "eod", n - 1
        raw = (exit_price - entry) / entry if side == "long" else (entry - exit_price) / entry
        out.append({
            "signal_ts_ms": ts[i], "entry_ts_ms": ts[i + 1], "exit_ts_ms": ts[j],
            "side": side, "r_mult": (raw - 0.0016) / stop_pct, "exit": reason,
        })
        i = j + 1
    return out


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(row["r_mult"]) for row in rows]
    if not values:
        return {"n": 0, "mean_r": None, "tstat": None}
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    return {
        "n": len(values),
        "mean_r": statistics.fmean(values),
        "tstat": statistics.fmean(values) / sd * math.sqrt(len(values)) if sd > 0 else 0.0,
        "positive": sum(value > 0 for value in values),
    }


def run(out: Path) -> dict[str, Any]:
    sol_path = INPUT / "SOLUSDT/SOLUSDT.json"
    btc_path = INPUT / "BTCUSDT/BTCUSDT.json"
    request = {
        "schema_id": "research_run_passport_request_v1", "authority": AUTHORITY,
        "promotion_authority": False, "live_or_broker_calls": False,
        "experiment_id": "rmr1_sol_regime_v1_20260813",
        "code_paths": ["research_lab/rmr1_sol_regime_v1.py", str(PREREG.relative_to(ROOT))],
        "inputs": [
            {"path": str(sol_path.relative_to(ROOT)), "role": "SOL immutable M5", "temporal_data": True,
             "contains_sealed_holdout": False, "data_window": {"start_utc": "2024-03-01T00:00:00Z", "end_utc_exclusive": "2025-10-01T00:00:00Z"}},
            {"path": str(btc_path.relative_to(ROOT)), "role": "BTC immutable M5 regime", "temporal_data": True,
             "contains_sealed_holdout": False, "data_window": {"start_utc": "2024-03-01T00:00:00Z", "end_utc_exclusive": "2025-10-01T00:00:00Z"}},
        ],
        "measurement_contract": {
            "engine": "rmr1_next_open_btc_regime_v1", "timeframe": "1h",
            "costs": {"round_trip_bps": 16},
            "label_contract": "BTC_30d_trend_sign_x_prior_median_30d_realized_vol",
            "split_contract": "fixed_trade_chronological_halves",
            "universe": ["SOLUSDT", "BTCUSDT"],
            "window": {"start_utc": "2024-03-01T00:00:00Z", "end_utc_exclusive": "2025-10-01T00:00:00Z"},
        },
        "search_contract": {"variant_count": 1, "random_seed": 20260813, "pre_registered": True},
        "sealed_holdouts": [{"id": "reserved_2025_10_2026_06", "start_utc": "2025-10-01T00:00:00Z", "end_utc_exclusive": "2026-07-01T00:00:00Z", "must_not_be_read": True}],
    }
    passport = build_passport(request, project_root=ROOT)
    write_passport(out / "run_passport.json", passport)
    sts, so, sh, sl, sc = load_1h_ohlc("SOLUSDT", input_json=str(sol_path))
    bts, bo, bh, bl, bc = load_1h_ohlc("BTCUSDT", input_json=str(btc_path))
    btc_index = {timestamp: index for index, timestamp in enumerate(bts)}
    trades = _trades(sts, so, sh, sl, sc)

    classified = []
    for trade in trades:
        index = btc_index.get(int(trade["signal_ts_ms"]))
        if index is None or index < HOURS_180D + HOURS_30D:
            continue
        trend = bc[index] / bc[index - HOURS_30D] - 1.0
        returns = [bc[j] / bc[j - 1] - 1.0 for j in range(index - HOURS_30D + 1, index + 1)]
        vol = statistics.pstdev(returns)
        historical_vols = []
        for endpoint in range(index - HOURS_180D, index, 24):
            if endpoint < HOURS_30D:
                continue
            segment = [bc[j] / bc[j - 1] - 1.0 for j in range(endpoint - HOURS_30D + 1, endpoint + 1)]
            historical_vols.append(statistics.pstdev(segment))
        if not historical_vols:
            continue
        regime = ("btc_up" if trend >= 0 else "btc_down") + "__" + (
            "high_vol" if vol > statistics.median(historical_vols) else "low_vol"
        )
        row = dict(trade)
        row.update({"btc_30d_return": trend, "btc_30d_vol": vol, "regime": regime})
        classified.append(row)

    split = len(classified) // 2
    by_regime: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in classified:
        by_regime[str(row["regime"])].append(row)
    regimes = {}
    explained = []
    for name, rows in sorted(by_regime.items()):
        first = [row for row in rows if classified.index(row) < split]
        second = [row for row in rows if classified.index(row) >= split]
        regimes[name] = {"all": _summary(rows), "first_half": _summary(first), "second_half": _summary(second)}
        if len(first) >= 10 and len(second) >= 10 and _summary(first)["mean_r"] > 0 and _summary(second)["mean_r"] > 0:
            explained.append(name)
    result = {
        "schema_id": "rmr1_sol_regime_result_v1", "authority": AUTHORITY,
        "capital_authorized": False, "promotion_authorized": False,
        "sealed_holdout_rows_decoded": 0, "passport_sha256": passport["passport_sha256"],
        "all_trades": _summary(trades), "classified_trades": _summary(classified),
        "fixed_halves": {"first": _summary(classified[:split]), "second": _summary(classified[split:])},
        "regimes": regimes, "explaining_regimes": explained,
        "verdict": "REGIME_EXPLANATION_FOUND_EXPLORATORY" if explained else "REGIME_DID_NOT_EXPLAIN_SOL_POCKET",
        "trades": classified,
    }
    _write_once(out / "result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    result = run(args.out.resolve())
    print(json.dumps({key: result[key] for key in ("verdict", "all_trades", "classified_trades", "fixed_halves", "regimes")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
