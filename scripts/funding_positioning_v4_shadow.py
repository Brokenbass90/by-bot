#!/usr/bin/env python3
"""Prospective public-data shadow for funding positioning V4.

No credentials and no order endpoint are used. Each completed Bybit funding
event is evaluated once using only the previous 90 funding observations. A
hypothetical maker quote is then followed through fill/nonfill and a 16-hour
markout. The append-only ledger is the evidence; the mutable state only resumes
pending lifecycles.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://api.bybit.com"
SYMBOLS = (
    "ADAUSDT",
    "BTCUSDT",
    "DOTUSDT",
    "ETHUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "SOLUSDT",
    "SUIUSDT",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_json(path: str, params: dict[str, Any]) -> dict[str, Any]:
    url = BASE_URL + path + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "funding-v4-shadow/1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if int(payload.get("retCode", -1)) != 0:
        raise RuntimeError(f"Bybit public API error: {payload.get('retCode')} {payload.get('retMsg')}")
    return payload


def _funding_history(symbol: str, limit: int = 100) -> list[tuple[int, float]]:
    payload = _http_json(
        "/v5/market/funding/history",
        {"category": "linear", "symbol": symbol, "limit": limit},
    )
    rows = []
    for row in payload.get("result", {}).get("list", []):
        try:
            rows.append((int(row["fundingRateTimestamp"]), float(row["fundingRate"])))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(rows)


def _klines(symbol: str, *, start_ms: int, end_ms: int) -> list[list[float]]:
    payload = _http_json(
        "/v5/market/kline",
        {
            "category": "linear",
            "symbol": symbol,
            "interval": "5",
            "start": int(start_ms),
            "end": int(end_ms),
            "limit": 1000,
        },
    )
    rows = []
    for row in payload.get("result", {}).get("list", []):
        try:
            rows.append([float(value) for value in row[:6]])
        except (TypeError, ValueError):
            continue
    return sorted(rows, key=lambda row: row[0])


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(len(ordered) * q)))
    return float(ordered[idx])


def _signal(history: list[tuple[int, float]], lookback: int = 90) -> dict[str, Any] | None:
    if len(history) < lookback + 1:
        return None
    event_ts, rate = history[-1]
    prior = [value for _, value in history[-lookback - 1 : -1]]
    high = _quantile(prior, 0.70)
    low = _quantile(prior, 0.30)
    side = -1 if rate > high and rate > 0 else (1 if rate < low and rate < 0 else 0)
    return {
        "event_ts": event_ts,
        "funding_rate": rate,
        "threshold_high": high,
        "threshold_low": low,
        "side": side,
    }


def _strict_fill(
    rows: list[list[float]],
    *,
    side: int,
    limit_price: float,
) -> int | None:
    for row in rows:
        traded_through = row[3] < limit_price if side > 0 else row[2] > limit_price
        if traded_through:
            return int(row[0])
    return None


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _record(ledger: Path, record_type: str, trial: dict[str, Any], **extra: Any) -> None:
    _append(
        ledger,
        {
            "schema_id": "funding_positioning_v4_shadow",
            "record_type": record_type,
            "recorded_at_utc": _now_iso(),
            "trial_id": trial["trial_id"],
            "symbol": trial["symbol"],
            "event_ts": trial["event_ts"],
            **extra,
        },
    )


def _reference_open(symbol: str, event_ts: int) -> float | None:
    rows = _klines(symbol, start_ms=event_ts, end_ms=event_ts + 10 * 60_000)
    row = next((row for row in rows if int(row[0]) >= event_ts), None)
    return float(row[1]) if row else None


def _funding_cashflow(symbol: str, *, entry_ts: int, exit_ts: int, side: int) -> float:
    history = _funding_history(symbol, limit=100)
    return sum(-side * rate for ts, rate in history if entry_ts < ts <= exit_ts)


def _update_trials(
    state: dict[str, Any],
    *,
    ledger: Path,
    now_ms: int,
    offset_bps: float,
    timeout_minutes: int,
    hold_hours: int,
    maker_round_trip_bps: float,
) -> None:
    for trial in state["trials"].values():
        status = trial["status"]
        if status == "pending_fill" and now_ms >= trial["fill_deadline_ts"]:
            rows = _klines(
                trial["symbol"],
                start_ms=trial["event_ts"],
                end_ms=trial["fill_deadline_ts"],
            )
            fill_ts = _strict_fill(rows, side=trial["side"], limit_price=trial["limit_price"])
            if fill_ts is None:
                trial["status"] = "nonfill"
                _record(
                    ledger,
                    "execution",
                    trial,
                    status="nonfill",
                    limit_price=trial["limit_price"],
                    timeout_minutes=timeout_minutes,
                )
                continue
            trial["status"] = "open"
            trial["fill_ts"] = fill_ts
            trial["exit_due_ts"] = fill_ts + hold_hours * 3_600_000
            _record(
                ledger,
                "execution",
                trial,
                status="filled",
                fill_ts=fill_ts,
                limit_price=trial["limit_price"],
            )
        if trial["status"] == "open" and now_ms >= trial["exit_due_ts"]:
            end_ms = trial["exit_due_ts"] + 10 * 60_000
            rows = _klines(trial["symbol"], start_ms=trial["exit_due_ts"], end_ms=end_ms)
            btc_rows = _klines("BTCUSDT", start_ms=trial["fill_ts"], end_ms=end_ms)
            asset_exit = next((row for row in rows if int(row[0]) >= trial["exit_due_ts"]), None)
            btc_entry = next((row for row in btc_rows if int(row[0]) >= trial["fill_ts"]), None)
            btc_exit = next((row for row in btc_rows if int(row[0]) >= trial["exit_due_ts"]), None)
            if not asset_exit or not btc_entry or not btc_exit:
                continue
            asset_return = float(asset_exit[1]) / float(trial["limit_price"]) - 1.0
            btc_return = float(btc_exit[1]) / float(btc_entry[1]) - 1.0
            funding = _funding_cashflow(
                trial["symbol"],
                entry_ts=trial["fill_ts"],
                exit_ts=trial["exit_due_ts"],
                side=trial["side"],
            )
            net_raw = trial["side"] * asset_return + funding - maker_round_trip_bps / 10_000.0
            trial.update(
                {
                    "status": "closed",
                    "asset_return": asset_return,
                    "btc_return": btc_return,
                    "funding_cashflow": funding,
                    "net_raw_return": net_raw,
                }
            )
            _record(
                ledger,
                "outcome",
                trial,
                status="closed",
                side=trial["side"],
                asset_return=asset_return,
                btc_return=btc_return,
                funding_cashflow=funding,
                net_raw_bps=net_raw * 10_000,
            )


def _discover(
    state: dict[str, Any],
    *,
    ledger: Path,
    now_ms: int,
    offset_bps: float,
    timeout_minutes: int,
    max_positions: int,
) -> None:
    proposals: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        history = _funding_history(symbol, limit=100)
        signal = _signal(history)
        if not signal or signal["event_ts"] < state["started_at_ms"]:
            continue
        trial_id = hashlib.sha256(f"{symbol}:{signal['event_ts']}".encode()).hexdigest()[:20]
        if trial_id in state["trials"]:
            continue
        reference = _reference_open(symbol, signal["event_ts"])
        if reference is None:
            continue
        proposals.append(
            {
                **signal,
                "trial_id": trial_id,
                "symbol": symbol,
                "reference_price": reference,
                "limit_price": reference
                * (1.0 - signal["side"] * offset_bps / 10_000.0)
                if signal["side"]
                else None,
            }
        )

    active = sum(
        trial["status"] in {"pending_fill", "open"}
        for trial in state["trials"].values()
    )
    available = max(0, max_positions - active)
    signalled = sorted(
        (row for row in proposals if row["side"]),
        key=lambda row: (-abs(row["funding_rate"]), row["symbol"]),
    )
    accepted = {row["trial_id"] for row in signalled[:available]}
    for proposal in proposals:
        if not proposal["side"]:
            status = "no_signal"
        elif proposal["trial_id"] not in accepted:
            status = "slot_reject"
        else:
            status = "pending_fill"
        trial = {
            **proposal,
            "status": status,
            "fill_deadline_ts": proposal["event_ts"] + timeout_minutes * 60_000,
        }
        state["trials"][trial["trial_id"]] = trial
        _record(
            ledger,
            "decision",
            trial,
            status=status,
            side=trial["side"],
            funding_rate=trial["funding_rate"],
            threshold_high=trial["threshold_high"],
            threshold_low=trial["threshold_low"],
            reference_price=trial["reference_price"],
            limit_price=trial["limit_price"],
        )


def _summary(state: dict[str, Any]) -> dict[str, Any]:
    trials = list(state["trials"].values())
    closed = [row for row in trials if row["status"] == "closed"]
    fills = [row for row in trials if row["status"] in {"open", "closed"}]
    submitted = [row for row in trials if row["side"] and row["status"] != "slot_reject"]
    return {
        "schema_id": "funding_positioning_v4_shadow_summary",
        "generated_at_utc": _now_iso(),
        "started_at_ms": state["started_at_ms"],
        "trials": len(trials),
        "submitted": len(submitted),
        "fills": len(fills),
        "nonfills": sum(row["status"] == "nonfill" for row in trials),
        "open": sum(row["status"] == "open" for row in trials),
        "closed": len(closed),
        "fill_rate": len(fills) / len(submitted) if submitted else None,
        "mean_closed_raw_net_bps": (
            statistics.fmean(row["net_raw_return"] for row in closed) * 10_000
            if closed
            else None
        ),
        "status_counts": {
            status: sum(row["status"] == status for row in trials)
            for status in ("no_signal", "slot_reject", "pending_fill", "nonfill", "open", "closed")
        },
        "capital_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=ROOT / "runtime/funding_positioning_v4_shadow_state.json")
    parser.add_argument("--ledger", type=Path, default=ROOT / "runtime/funding_positioning_v4_shadow_ledger.jsonl")
    parser.add_argument("--summary", type=Path, default=ROOT / "runtime/funding_positioning_v4_shadow_summary.json")
    parser.add_argument("--offset-bps", type=float, default=5.0)
    parser.add_argument("--timeout-minutes", type=int, default=60)
    parser.add_argument("--hold-hours", type=int, default=16)
    parser.add_argument("--max-positions", type=int, default=3)
    parser.add_argument("--maker-round-trip-bps", type=float, default=6.0)
    args = parser.parse_args()

    now_ms = int(time.time() * 1000)
    if args.state.exists():
        state = json.loads(args.state.read_text(encoding="utf-8"))
    else:
        state = {
            "schema_id": "funding_positioning_v4_shadow_state",
            "started_at_ms": now_ms,
            "created_at_utc": _now_iso(),
            "trials": {},
        }
    _update_trials(
        state,
        ledger=args.ledger,
        now_ms=now_ms,
        offset_bps=args.offset_bps,
        timeout_minutes=args.timeout_minutes,
        hold_hours=args.hold_hours,
        maker_round_trip_bps=args.maker_round_trip_bps,
    )
    _discover(
        state,
        ledger=args.ledger,
        now_ms=now_ms,
        offset_bps=args.offset_bps,
        timeout_minutes=args.timeout_minutes,
        max_positions=args.max_positions,
    )
    state["updated_at_utc"] = _now_iso()
    _atomic_json(args.state, state)
    _atomic_json(args.summary, _summary(state))
    print(json.dumps(_summary(state), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
