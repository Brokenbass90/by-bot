#!/usr/bin/env python3
"""Fast research-only filter for many causal crypto strategy families.

This tool deliberately cannot promote or trade. It selects finalists on the
train segment only, then evaluates those frozen finalists on chronological OOS
under base and stress costs. Event-driven replay remains mandatory.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import vectorbt as vbt


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT",
    "ADAUSDT", "LTCUSDT", "DOTUSDT", "SUIUSDT",
]


@dataclass(frozen=True)
class Candidate:
    family: str
    side: str
    params: dict[str, Any]

    @property
    def candidate_id(self) -> str:
        payload = json.dumps(
            {"family": self.family, "side": self.side, "params": self.params},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _load_symbol(symbol: str) -> pd.DataFrame:
    rows: dict[int, dict[str, Any]] = {}
    for path in sorted((ROOT / "data_cache").glob(f"{symbol}_5_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for row in payload if isinstance(payload, list) else []:
            try:
                rows[int(row["ts"])] = row
            except (KeyError, TypeError, ValueError):
                continue
    if not rows:
        raise FileNotFoundError(f"No 5m cache for {symbol}")
    frame = pd.DataFrame(rows.values())
    frame.index = pd.to_datetime(frame.pop("ts"), unit="ms", utc=True)
    frame = frame.sort_index()
    for column in ("o", "h", "l", "c", "v"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    hourly = frame.resample("1h").agg(
        {"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"}
    )
    return hourly.dropna().loc[lambda x: (x[["o", "h", "l", "c"]] > 0).all(axis=1)]


def _candidates() -> list[Candidate]:
    out: list[Candidate] = []
    for fast, slow, side in itertools.product([12, 24, 48], [72, 120, 192], ["long", "short"]):
        if fast < slow:
            out.append(Candidate("ema_trend", side, {"fast": fast, "slow": slow}))
    for window, z, side in itertools.product([24, 48, 96], [1.0, 1.5, 2.0], ["long", "short"]):
        out.append(Candidate("z_reversion", side, {"window": window, "z": z}))
    for entry, exit_window, side in itertools.product([24, 48, 96, 168], [12, 24, 48], ["long", "short"]):
        if exit_window < entry:
            out.append(Candidate("donchian", side, {"entry": entry, "exit": exit_window}))
    for lookback, side in itertools.product([24, 48, 96, 168], ["long", "short"]):
        out.append(Candidate("sweep_reclaim", side, {"lookback": lookback}))
    for lookback, threshold, volume_z, hold, side in itertools.product(
        [3, 6, 12], [0.02, 0.04, 0.06], [1.0, 2.0], [4, 8, 12], ["long", "short"]
    ):
        out.append(
            Candidate(
                "exhaustion_reversal",
                side,
                {"lookback": lookback, "threshold": threshold, "volume_z": volume_z, "hold": hold},
            )
        )
    return out


def _signals(frame: pd.DataFrame, candidate: Candidate) -> tuple[pd.Series, pd.Series]:
    close, high, low, volume = frame["c"], frame["h"], frame["l"], frame["v"]
    p, side = candidate.params, candidate.side
    if candidate.family == "ema_trend":
        fast = close.ewm(span=int(p["fast"]), adjust=False).mean()
        slow = close.ewm(span=int(p["slow"]), adjust=False).mean()
        state = fast > slow if side == "long" else fast < slow
        entries = state & ~state.shift(1, fill_value=False)
        exits = ~state & state.shift(1, fill_value=False)
    elif candidate.family == "z_reversion":
        mean = close.rolling(int(p["window"]), min_periods=int(p["window"])).mean()
        std = close.rolling(int(p["window"]), min_periods=int(p["window"])).std(ddof=0)
        zscore = (close - mean) / std.replace(0.0, float("nan"))
        if side == "long":
            entries, exits = zscore <= -float(p["z"]), zscore >= 0.0
        else:
            entries, exits = zscore >= float(p["z"]), zscore <= 0.0
    elif candidate.family == "donchian":
        prior_high = high.rolling(int(p["entry"]), min_periods=int(p["entry"])).max().shift(1)
        prior_low = low.rolling(int(p["entry"]), min_periods=int(p["entry"])).min().shift(1)
        exit_high = high.rolling(int(p["exit"]), min_periods=int(p["exit"])).max().shift(1)
        exit_low = low.rolling(int(p["exit"]), min_periods=int(p["exit"])).min().shift(1)
        if side == "long":
            entries, exits = close > prior_high, close < exit_low
        else:
            entries, exits = close < prior_low, close > exit_high
    elif candidate.family == "sweep_reclaim":
        lookback = int(p["lookback"])
        prior_high = high.rolling(lookback, min_periods=lookback).max().shift(1)
        prior_low = low.rolling(lookback, min_periods=lookback).min().shift(1)
        midpoint = (prior_high + prior_low) / 2.0
        if side == "long":
            entries, exits = (low < prior_low) & (close > prior_low), close >= midpoint
        else:
            entries, exits = (high > prior_high) & (close < prior_high), close <= midpoint
    elif candidate.family == "exhaustion_reversal":
        lookback, hold = int(p["lookback"]), int(p["hold"])
        move = close.pct_change(lookback)
        vol_mean = volume.rolling(96, min_periods=96).mean()
        vol_std = volume.rolling(96, min_periods=96).std(ddof=0)
        vol_z = (volume - vol_mean) / vol_std.replace(0.0, float("nan"))
        direction = move <= -float(p["threshold"]) if side == "long" else move >= float(p["threshold"])
        entries = direction & (vol_z >= float(p["volume_z"]))
        exits = entries.shift(hold, fill_value=False)
    else:
        raise ValueError(candidate.family)
    # Signal is known after bar close; execution is next bar open.
    return entries.fillna(False).shift(1, fill_value=False), exits.fillna(False).shift(1, fill_value=False)


def _portfolio_metrics(
    frame: pd.DataFrame,
    candidate: Candidate,
    *,
    fee_per_order: float,
    slippage_per_order: float,
) -> dict[str, float | int]:
    entries, exits = _signals(frame, candidate)
    kwargs: dict[str, Any] = {
        "close": frame["o"],
        "init_cash": 10_000.0,
        "fees": fee_per_order,
        "slippage": slippage_per_order,
        "freq": "1h",
    }
    if candidate.side == "long":
        kwargs.update(entries=entries, exits=exits)
    else:
        kwargs.update(short_entries=entries, short_exits=exits)
    portfolio = vbt.Portfolio.from_signals(**kwargs)
    total_return = float(portfolio.total_return())
    drawdown = abs(float(portfolio.max_drawdown()))
    trades = int(portfolio.trades.count())
    return {
        "return": total_return if math.isfinite(total_return) else -1.0,
        "max_drawdown": drawdown if math.isfinite(drawdown) else 1.0,
        "trades": trades,
    }


def _aggregate(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(rows)
    returns = pd.Series([float(row["return"]) for row in items], dtype=float)
    drawdowns = pd.Series([float(row["max_drawdown"]) for row in items], dtype=float)
    trades = pd.Series([int(row["trades"]) for row in items], dtype=float)
    return {
        "symbols": len(items),
        "positive_symbols": int((returns > 0).sum()),
        "median_return": float(returns.median()),
        "mean_return": float(returns.mean()),
        "worst_return": float(returns.min()),
        "median_max_drawdown": float(drawdowns.median()),
        "total_trades": int(trades.sum()),
        "median_trades": float(trades.median()),
    }


def _evaluate(
    frames: dict[str, pd.DataFrame],
    candidate: Candidate,
    *,
    segment: str,
    fee_per_order: float,
    slippage_per_order: float,
    train_fraction: float,
) -> dict[str, Any]:
    rows = []
    for symbol, full in frames.items():
        split = max(1, min(len(full) - 1, int(len(full) * train_fraction)))
        frame = full.iloc[:split] if segment == "train" else full.iloc[split:]
        metrics = _portfolio_metrics(
            frame,
            candidate,
            fee_per_order=fee_per_order,
            slippage_per_order=slippage_per_order,
        )
        rows.append({"symbol": symbol, **metrics})
    return {"aggregate": _aggregate(rows), "per_symbol": rows}


def _score(metrics: dict[str, Any]) -> float:
    a = metrics["aggregate"]
    breadth = float(a["positive_symbols"]) / max(1.0, float(a["symbols"]))
    undertrade_penalty = max(0.0, 24.0 - float(a["total_trades"])) * 0.002
    return float(a["median_return"]) + 0.25 * float(a["mean_return"]) + 0.10 * breadth - 0.35 * float(a["median_max_drawdown"]) - undertrade_penalty


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--train-fraction", type=float, default=0.70)
    parser.add_argument("--top-per-family", type=int, default=3)
    parser.add_argument("--max-candidates", type=int, default=0)
    parser.add_argument(
        "--out-dir",
        default="reports/research/vectorbt_crypto_family_prefilter_20260802",
    )
    args = parser.parse_args()
    symbols = [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
    frames = {symbol: _load_symbol(symbol) for symbol in symbols}
    candidates = _candidates()
    if args.max_candidates > 0:
        candidates = candidates[: args.max_candidates]

    train_rows: list[dict[str, Any]] = []
    for ordinal, candidate in enumerate(candidates, start=1):
        metrics = _evaluate(
            frames,
            candidate,
            segment="train",
            fee_per_order=0.00025,
            slippage_per_order=0.00015,
            train_fraction=args.train_fraction,
        )
        train_rows.append(
            {
                "ordinal": ordinal,
                "candidate_id": candidate.candidate_id,
                "family": candidate.family,
                "side": candidate.side,
                "params": candidate.params,
                "score": _score(metrics),
                "train": metrics,
            }
        )
        print(f"train {ordinal}/{len(candidates)} {candidate.family} {candidate.side}", flush=True)

    finalists: list[dict[str, Any]] = []
    for family in sorted({row["family"] for row in train_rows}):
        family_rows = sorted(
            (row for row in train_rows if row["family"] == family),
            key=lambda row: float(row["score"]),
            reverse=True,
        )[: max(1, int(args.top_per_family))]
        for row in family_rows:
            candidate = Candidate(row["family"], row["side"], row["params"])
            row = dict(row)
            row["oos_base"] = _evaluate(
                frames,
                candidate,
                segment="oos",
                fee_per_order=0.00025,
                slippage_per_order=0.00015,
                train_fraction=args.train_fraction,
            )
            row["oos_stress"] = _evaluate(
                frames,
                candidate,
                segment="oos",
                fee_per_order=0.00055,
                slippage_per_order=0.00035,
                train_fraction=args.train_fraction,
            )
            finalists.append(row)

    output = {
        "schema_id": "vectorbt_crypto_family_prefilter_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "capital_authorized": False,
        "promotion_authority": False,
        "execution_contract": "signal_on_close_execute_next_open",
        "selection_contract": "rank train only; OOS evaluate frozen top-per-family",
        "costs": {
            "base_round_trip_bps": 8.0,
            "stress_round_trip_bps": 18.0,
        },
        "symbols": symbols,
        "bars": {symbol: len(frame) for symbol, frame in frames.items()},
        "train_fraction": args.train_fraction,
        "n_trials_planned": len(_candidates()),
        "n_trials_scheduled": len(candidates),
        "n_trials_evaluated": len(train_rows),
        "n_trials_effective_independent": None,
        "train_results": train_rows,
        "frozen_finalists": finalists,
        "next_gate": "Reimplement any surviving family in the native event-driven engine with PIT, LOSO, regime, power and execution parity.",
    }
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "result.json"
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
