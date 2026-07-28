#!/usr/bin/env python3
"""Bounded audit of extreme-funding positioning as a feature, not a sleeve.

Repairs the exploratory funding_squeeze prototype by:

* requiring a strict percentile exceedance (common 0.01% funding ties do not
  become thousands of "extreme" signals);
* preventing overlapping positions on one symbol;
* including funding cashflows crossed during the holding period;
* reporting maker/taker costs separately;
* using a point-in-time BTC 30-day regime instead of ex-post date windows;
* reporting a simple beta-one BTC-residual return for altcoins.

This is still a bar-level research audit. It does not model maker fill
probability and cannot authorize live capital.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import glob
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
FUNDING_DIR = ROOT / "data" / "funding_rates" / "crypto_static_v1_20260425"
KLINE_DIR = ROOT / ".cache" / "klines"


@dataclass(frozen=True)
class Trade:
    symbol: str
    event_ts: int
    entry_ts: int
    exit_ts: int
    side: int
    funding_rate: float
    regime: str
    asset_return: float
    btc_return: float
    funding_cashflow: float

    @property
    def gross_return(self) -> float:
        return self.side * self.asset_return + self.funding_cashflow

    @property
    def residual_return(self) -> float | None:
        if self.symbol == "BTCUSDT":
            return None
        return self.side * (self.asset_return - self.btc_return) + self.funding_cashflow


def _load_funding(symbol: str) -> list[tuple[int, float]]:
    path = FUNDING_DIR / f"{symbol}.csv"
    out: list[tuple[int, float]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                out.append((int(row["timestamp_ms"]), float(row["funding_rate"])))
            except (KeyError, TypeError, ValueError):
                continue
    return sorted(out)


def _best_5m_cache(symbol: str) -> list[list[float]]:
    best: list[list[float]] = []
    for raw_path in glob.glob(str(KLINE_DIR / f"{symbol}_5_*.json")):
        try:
            rows = json.loads(Path(raw_path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if len(rows) > len(best):
            best = rows
    return best


def _first_after(timestamps: list[int], ts: int) -> int | None:
    idx = bisect.bisect_right(timestamps, int(ts))
    return idx if idx < len(timestamps) else None


def _close_at_or_before(rows: list[list[float]], timestamps: list[int], ts: int) -> float | None:
    idx = bisect.bisect_right(timestamps, int(ts)) - 1
    if idx < 0:
        return None
    return float(rows[idx][4])


def _quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, max(0, int(len(sorted_values) * q)))
    return float(sorted_values[idx])


def _funding_cashflow(
    funding: list[tuple[int, float]],
    *,
    entry_ts: int,
    exit_ts: int,
    side: int,
) -> float:
    # long pays positive funding, short receives it
    return sum(-side * rate for ts, rate in funding if entry_ts < ts <= exit_ts)


def build_trades(symbol: str, *, percentile: float, hold_hours: int, lookback: int = 90) -> list[Trade]:
    funding = _load_funding(symbol)
    rows = _best_5m_cache(symbol)
    btc_rows = rows if symbol == "BTCUSDT" else _best_5m_cache("BTCUSDT")
    if len(funding) < lookback + 2 or not rows or not btc_rows:
        return []
    timestamps = [int(row[0]) for row in rows]
    btc_timestamps = [int(row[0]) for row in btc_rows]
    hold_ms = int(hold_hours) * 3_600_000
    last_exit_ts = -1
    trades: list[Trade] = []

    for idx in range(lookback, len(funding)):
        event_ts, rate = funding[idx]
        history = sorted(value for _, value in funding[idx - lookback : idx])
        high = _quantile(history, percentile / 100.0)
        low = _quantile(history, 1.0 - percentile / 100.0)
        side = -1 if rate > high and rate > 0 else (1 if rate < low and rate < 0 else 0)
        if side == 0:
            continue
        entry_idx = _first_after(timestamps, event_ts)
        if entry_idx is None:
            continue
        entry_ts = timestamps[entry_idx]
        if entry_ts < last_exit_ts:
            continue
        exit_idx = _first_after(timestamps, entry_ts + hold_ms - 1)
        if exit_idx is None:
            continue
        exit_ts = timestamps[exit_idx]
        entry = float(rows[entry_idx][1])
        exit_price = float(rows[exit_idx][1])
        if entry <= 0:
            continue
        btc_entry_idx = _first_after(btc_timestamps, event_ts)
        btc_exit_idx = _first_after(btc_timestamps, entry_ts + hold_ms - 1)
        if btc_entry_idx is None or btc_exit_idx is None:
            continue
        btc_entry = float(btc_rows[btc_entry_idx][1])
        btc_exit = float(btc_rows[btc_exit_idx][1])
        trailing_start = _close_at_or_before(btc_rows, btc_timestamps, event_ts - 30 * 86_400_000)
        btc_now = _close_at_or_before(btc_rows, btc_timestamps, event_ts)
        if btc_entry <= 0 or trailing_start is None or trailing_start <= 0 or btc_now is None:
            continue
        trailing_return = btc_now / trailing_start - 1.0
        regime = "bull" if trailing_return > 0.03 else ("bear" if trailing_return < -0.03 else "neutral")
        trades.append(
            Trade(
                symbol=symbol,
                event_ts=event_ts,
                entry_ts=entry_ts,
                exit_ts=exit_ts,
                side=side,
                funding_rate=rate,
                regime=regime,
                asset_return=exit_price / entry - 1.0,
                btc_return=btc_exit / btc_entry - 1.0,
                funding_cashflow=_funding_cashflow(funding, entry_ts=entry_ts, exit_ts=exit_ts, side=side),
            )
        )
        last_exit_ts = exit_ts
    return trades


def _summary(trades: Iterable[Trade], round_cost_bps: float) -> dict:
    rows = list(trades)
    cost = float(round_cost_bps) / 10_000.0
    net = [trade.gross_return - cost for trade in rows]
    residual = [
        value - cost
        for trade in rows
        if (value := trade.residual_return) is not None
    ]
    return {
        "n": len(rows),
        "short_share": (sum(1 for trade in rows if trade.side < 0) / len(rows)) if rows else None,
        "avg_gross_bps": (sum(trade.gross_return for trade in rows) / len(rows) * 10_000) if rows else None,
        "avg_net_bps": (sum(net) / len(net) * 10_000) if net else None,
        "positive_net_share": (sum(1 for value in net if value > 0) / len(net)) if net else None,
        "avg_residual_net_bps": (sum(residual) / len(residual) * 10_000) if residual else None,
    }


def run(percentile: float, hold_hours: int) -> dict:
    symbols = sorted(path.stem for path in FUNDING_DIR.glob("*.csv"))
    trades = [trade for symbol in symbols for trade in build_trades(symbol, percentile=percentile, hold_hours=hold_hours)]
    return {
        "percentile": percentile,
        "hold_hours": hold_hours,
        "symbols": symbols,
        "data_start_utc": datetime.fromtimestamp(min(t.event_ts for t in trades) / 1000, tz=timezone.utc).isoformat() if trades else None,
        "data_end_utc": datetime.fromtimestamp(max(t.event_ts for t in trades) / 1000, tz=timezone.utc).isoformat() if trades else None,
        "maker_6bps": _summary(trades, 6.0),
        "taker_16bps": _summary(trades, 16.0),
        "regimes_maker_6bps": {
            regime: _summary((trade for trade in trades if trade.regime == regime), 6.0)
            for regime in ("bull", "neutral", "bear")
        },
        "per_symbol_maker_6bps": {
            symbol: _summary((trade for trade in trades if trade.symbol == symbol), 6.0)
            for symbol in symbols
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--percentile", type=float, default=90.0)
    parser.add_argument("--holds", default="4,8,12,16")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = {
        "schema_id": "funding_positioning_v2_audit",
        "research_only": True,
        "executable": False,
        "method": {
            "strict_percentile_exceedance": True,
            "no_symbol_overlap": True,
            "funding_cashflows_included": True,
            "regime": "point_in_time_btc_trailing_30d_return",
            "residual": "alt_signed_return_minus_beta1_btc_return",
            "maker_fill_probability_modelled": False,
        },
        "runs": [
            run(args.percentile, int(raw))
            for raw in str(args.holds).split(",")
            if str(raw).strip()
        ],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

