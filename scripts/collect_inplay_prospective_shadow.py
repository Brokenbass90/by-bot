#!/usr/bin/env python3
"""Prospective, public-only ETH inplay collector with zero trading authority.

The collector replays only completed public Bybit 5m candles, observes signals
at the completed-candle boundary, assigns the next 5m open as the executable
entry, and measures the preregistered 0.75 typical-move stop / 24h outcome.
It never imports credentials and has no order, broker, risk, or promotion path.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "research_lab") not in sys.path:
    sys.path.insert(0, str(ROOT / "research_lab"))

from backtest.engine import Candle, KlineStore
from research_lab import strategy_adapter
from scripts.materialize_bybit_5m_preholdout import fetch_5m
from scripts.materialize_bybit_daily_preholdout import atomic_json
from strategies.inplay_breakout import InPlayBreakoutWrapper


SCHEMA_ID = "inplay_prospective_shadow_v1"
AUTHORITY = "research_only_public_data_zero_risk_no_orders"
SYMBOL = "ETHUSDT"
INTERVAL_MS = 5 * 60_000
HORIZON_BARS = 24 * 12
STOP_MULTIPLIER = 0.75
ATR_N = 24
COST_BPS = 16.0


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _side(signal: Any) -> int:
    value = str(getattr(signal, "side", "") or "").lower()
    if value in {"sell", "short", "-1", "down"}:
        return -1
    if value in {"buy", "long", "1", "up"}:
        return 1
    raise RuntimeError(f"unsupported signal side: {value!r}")


def _atr(candles: list[Candle]) -> np.ndarray:
    close = np.asarray([row.c for row in candles], dtype=float)
    high = np.asarray([row.h for row in candles], dtype=float)
    low = np.asarray([row.l for row in candles], dtype=float)
    previous = np.r_[close[0], close[:-1]]
    true_range = np.maximum.reduce([high - low, np.abs(high - previous), np.abs(low - previous)])
    return pd.Series(true_range).ewm(alpha=1 / ATR_N, adjust=False, min_periods=ATR_N).mean().to_numpy()


def settle_event(event: dict[str, Any], candles: list[Candle], *, signal_index: int, atr: np.ndarray) -> dict[str, Any]:
    """Fill and, when enough bars exist, settle one fixed-contract event."""
    side = int(event["side"])
    entry_index = signal_index + 1
    if entry_index >= len(candles) or not np.isfinite(atr[signal_index]) or atr[signal_index] <= 0:
        event["state"] = "awaiting_next_open"
        return event

    entry = float(candles[entry_index].o)
    risk = float(STOP_MULTIPLIER * math.sqrt(HORIZON_BARS) * atr[signal_index])
    stop = entry - side * risk
    exit_index = entry_index + HORIZON_BARS - 1
    path_end = min(exit_index, len(candles) - 1)
    mfe_r = 0.0
    mae_r = 0.0
    stopped_at: int | None = None
    for index in range(entry_index, path_end + 1):
        row = candles[index]
        favorable = (row.h - entry) / risk if side > 0 else (entry - row.l) / risk
        adverse = (entry - row.l) / risk if side > 0 else (row.h - entry) / risk
        mfe_r = max(mfe_r, favorable)
        mae_r = max(mae_r, adverse)
        if (side > 0 and row.l <= stop) or (side < 0 and row.h >= stop):
            stopped_at = index
            break

    event.update({
        "entry_ts_ms": int(candles[entry_index].ts),
        "entry": entry,
        "risk_price": risk,
        "stop": stop,
        "mfe_r": round(float(mfe_r), 6),
        "mae_r": round(float(mae_r), 6),
        "cost_bps_round_trip": COST_BPS,
    })
    if stopped_at is not None:
        gross_r = -1.0
        event.update({
            "state": "closed",
            "exit_reason": "stop_first",
            "exit_ts_ms": int(candles[stopped_at].ts),
            "exit": stop,
        })
    elif exit_index < len(candles):
        exit_price = float(candles[exit_index].c)
        gross_r = side * (exit_price - entry) / risk
        event.update({
            "state": "closed",
            "exit_reason": "fixed_24h_close",
            "exit_ts_ms": int(candles[exit_index].ts),
            "exit": exit_price,
        })
    else:
        event["state"] = "open_shadow"
        event["bars_observed"] = path_end - entry_index + 1
        return event

    cost_r = (COST_BPS / 10_000.0) * entry / risk
    event["gross_r"] = round(float(gross_r), 6)
    event["cost_r"] = round(float(cost_r), 6)
    event["net_r"] = round(float(gross_r - cost_r), 6)
    return event


def replay(candles: list[Candle], state: dict[str, Any]) -> dict[str, Any]:
    if len(candles) < 1_000:
        raise RuntimeError(f"insufficient completed candles: {len(candles)}")
    overrides = sorted(key for key in os.environ if key.startswith("BREAKOUT_"))
    if overrides:
        raise RuntimeError(f"BREAKOUT env overrides are forbidden for fixed shadow: {overrides}")
    store = KlineStore(SYMBOL, candles, base_interval_min=5)
    wrapper = InPlayBreakoutWrapper()
    convention, _ = strategy_adapter.detect_convention(wrapper)
    if convention is None:
        raise RuntimeError("inplay strategy convention is not supported")
    caller = strategy_adapter.make_caller(convention, wrapper, SYMBOL)
    started_at = int(state["prospective_start_ts_ms"])
    existing = {str(row["signal_information_ts_ms"]): row for row in state.get("events", [])}
    signal_indices: dict[str, int] = {}
    for index, candle in enumerate(candles):
        store.set_index(index)
        signal = caller(store, candles, index)
        if signal is None:
            continue
        information_ts = int(candle.ts) + INTERVAL_MS
        key = str(information_ts)
        if information_ts >= started_at and key not in existing:
            existing[key] = {
                "schema_id": "inplay_prospective_event_v1",
                "signal_bar_start_ts_ms": int(candle.ts),
                "signal_information_ts_ms": information_ts,
                "symbol": SYMBOL,
                "side": _side(signal),
                "signal_information": "completed_5m_close",
                "entry_execution": "next_5m_open",
                "stop_typical_move_multiplier": STOP_MULTIPLIER,
                "horizon_hours": 24,
                "state": "awaiting_next_open",
            }
        if key in existing:
            signal_indices[key] = index

    atr = _atr(candles)
    for key, event in existing.items():
        index = signal_indices.get(key)
        if index is not None:
            settle_event(event, candles, signal_index=index, atr=atr)
    events = [existing[key] for key in sorted(existing, key=int)]
    closed = [row for row in events if row.get("state") == "closed"]
    state.update({
        "schema_id": SCHEMA_ID,
        "authority": AUTHORITY,
        "public_only": True,
        "authentication": False,
        "order_capability": False,
        "capital_authorized": False,
        "promotion_authority": False,
        "symbol": SYMBOL,
        "events": events,
        "event_count": len(events),
        "closed_count": len(closed),
        "open_count": len(events) - len(closed),
        "closed_net_r": round(sum(float(row.get("net_r", 0.0)) for row in closed), 6),
        "last_completed_bar_ts_ms": int(candles[-1].ts),
        "updated_at_utc": _utc_now().isoformat(),
        "status": "collecting",
    })
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--runtime-dir", type=Path, default=ROOT / "runtime/inplay_prospective_shadow_v1")
    parser.add_argument("--lookback-days", type=int, default=35)
    parser.add_argument("--min-free-gb", type=float, default=50.0)
    args = parser.parse_args()
    if not args.allow_public_network:
        raise RuntimeError("--allow-public-network acknowledgement required")
    if shutil.disk_usage(args.runtime_dir.parent).free < args.min_free_gb * 1024**3:
        raise RuntimeError("disk guard active")
    now = _utc_now()
    end_ms = int(now.timestamp() * 1000)
    start_ms = end_ms - args.lookback_days * 86_400_000
    rows = fetch_5m(SYMBOL, start_ms=start_ms, end_exclusive_ms=end_ms)
    completed = [row for row in rows if int(row["ts_ms"]) + INTERVAL_MS <= end_ms]
    candles = [Candle(int(row["ts_ms"]), row["open"], row["high"], row["low"], row["close"], row["volume"]) for row in completed]
    state_path = args.runtime_dir / "status.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("authority") != AUTHORITY or state.get("symbol") != SYMBOL:
            raise RuntimeError("existing state contract mismatch")
    else:
        state = {
            "schema_id": SCHEMA_ID,
            "authority": AUTHORITY,
            "symbol": SYMBOL,
            "prospective_start_ts_ms": int(candles[-1].ts) + INTERVAL_MS,
            "created_at_utc": now.isoformat(),
            "events": [],
        }
    result = replay(candles, state)
    args.runtime_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(state_path, result)
    print(json.dumps({key: result[key] for key in ("status", "event_count", "closed_count", "open_count", "last_completed_bar_ts_ms")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
