#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import pstdev
from typing import Iterable

import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex.data import load_m5_csv

EXCLUDED_SYMBOLS = {"SPY", "QQQ", "IWM", "DIA"}


@dataclass
class SymbolMetrics:
    symbol: str
    bars: int
    close: float
    avg_dollar_vol_1d: float
    atr_pct_1d: float
    ret_1d_pct: float
    ret_3d_pct: float
    ret_5d_pct: float
    realized_vol_1d_pct: float
    eff_ratio_3d: float
    breakout_score: float
    reversion_score: float
    strategy_class: str


def _safe_pct(a: float, b: float) -> float:
    if not math.isfinite(a) or not math.isfinite(b) or abs(b) < 1e-12:
        return 0.0
    return (a / b - 1.0) * 100.0


def _sma(vals: list[float], period: int) -> float:
    if len(vals) < period or period <= 0:
        return float("nan")
    seg = vals[-period:]
    return sum(seg) / float(period)


def _discover_symbols(data_dir: Path) -> list[str]:
    out: list[str] = []
    for csv_path in sorted(data_dir.glob("*_M5.csv")):
        sym = csv_path.stem.replace("_M5", "").strip().upper()
        if not sym or sym in EXCLUDED_SYMBOLS:
            continue
        out.append(sym)
    return out


def _recent_returns(closes: list[float], bars: int) -> float:
    if len(closes) <= bars or bars <= 0:
        return 0.0
    return _safe_pct(closes[-1], closes[-1 - bars])


def _efficiency_ratio(closes: list[float], bars: int) -> float:
    if len(closes) <= bars or bars <= 1:
        return 0.0
    seg = closes[-(bars + 1):]
    net = abs(seg[-1] - seg[0])
    path = sum(abs(b - a) for a, b in zip(seg[:-1], seg[1:]))
    if path <= 1e-12:
        return 0.0
    return net / path


def _load_metrics(csv_path: Path) -> SymbolMetrics | None:
    candles = load_m5_csv(str(csv_path))
    if len(candles) < 78 * 6:
        return None

    closes = [float(c.c) for c in candles]
    highs = [float(c.h) for c in candles]
    lows = [float(c.l) for c in candles]
    vols = [float(c.v) for c in candles]
    close = closes[-1]
    if close <= 0:
        return None

    bars_1d = 78
    bars_3d = 78 * 3
    bars_5d = 78 * 5
    bars_10d = 78 * 10

    recent_closes = closes[-bars_1d:]
    recent_highs = highs[-bars_1d:]
    recent_lows = lows[-bars_1d:]
    recent_vols = vols[-bars_1d:]

    avg_dollar_vol_1d = sum(c * v for c, v in zip(recent_closes, recent_vols)) / max(1, len(recent_closes))
    atr_pct_1d = (
        100.0 * sum((h - l) / max(1e-12, c) for h, l, c in zip(recent_highs, recent_lows, recent_closes)) / max(1, len(recent_closes))
    )
    returns_1d = []
    for prev, cur in zip(recent_closes[:-1], recent_closes[1:]):
        if prev > 0:
            returns_1d.append(cur / prev - 1.0)
    realized_vol_1d_pct = 100.0 * pstdev(returns_1d) if len(returns_1d) >= 5 else 0.0

    ret_1d_pct = _recent_returns(closes, bars_1d)
    ret_3d_pct = _recent_returns(closes, bars_3d)
    ret_5d_pct = _recent_returns(closes, bars_5d)
    eff_ratio_3d = _efficiency_ratio(closes, min(bars_3d, max(20, len(closes) - 1)))

    vol_gate = 1.0 if 0.15 <= realized_vol_1d_pct <= 1.8 else 0.7
    liq_score = math.log10(max(avg_dollar_vol_1d, 1.0))
    breakout_score = (
        1.1 * liq_score
        + 0.14 * abs(ret_3d_pct)
        + 0.06 * abs(ret_5d_pct)
        + 1.2 * eff_ratio_3d
        + 0.35 * atr_pct_1d
    ) * vol_gate
    reversion_score = (
        1.0 * liq_score
        + 0.25 * atr_pct_1d
        + 0.10 * realized_vol_1d_pct
        - 0.10 * abs(ret_3d_pct)
        - 0.06 * abs(ret_5d_pct)
        - 0.8 * eff_ratio_3d
    ) * vol_gate

    trend_strength = max(abs(ret_3d_pct), abs(ret_5d_pct))
    is_breakout = (
        trend_strength >= 10.0
        or eff_ratio_3d >= 0.12
        or (atr_pct_1d >= 1.05 and abs(ret_3d_pct) >= 6.0)
    )
    strategy_class = "breakout_continuation" if is_breakout else "grid_reversion"

    return SymbolMetrics(
        symbol=csv_path.stem.replace("_M5", "").upper(),
        bars=len(candles),
        close=round(close, 4),
        avg_dollar_vol_1d=round(avg_dollar_vol_1d, 2),
        atr_pct_1d=round(atr_pct_1d, 4),
        ret_1d_pct=round(ret_1d_pct, 4),
        ret_3d_pct=round(ret_3d_pct, 4),
        ret_5d_pct=round(ret_5d_pct, 4),
        realized_vol_1d_pct=round(realized_vol_1d_pct, 4),
        eff_ratio_3d=round(eff_ratio_3d, 4),
        breakout_score=round(breakout_score, 6),
        reversion_score=round(reversion_score, 6),
        strategy_class=strategy_class,
    )


def _rank_and_select(
    metrics: Iterable[SymbolMetrics],
    *,
    max_symbols: int,
    breakout_target: int,
    reversion_target: int,
    min_avg_dollar_vol: float,
) -> tuple[list[str], dict[str, str], list[SymbolMetrics]]:
    valid = [m for m in metrics if m.avg_dollar_vol_1d >= min_avg_dollar_vol]
    breakout = sorted(
        [m for m in valid if m.strategy_class == "breakout_continuation"],
        key=lambda m: (m.breakout_score, m.avg_dollar_vol_1d),
        reverse=True,
    )
    reversion = sorted(
        [m for m in valid if m.strategy_class == "grid_reversion"],
        key=lambda m: (m.reversion_score, m.avg_dollar_vol_1d),
        reverse=True,
    )

    selected: list[SymbolMetrics] = []
    chosen: set[str] = set()
    for bucket, limit in ((breakout, breakout_target), (reversion, reversion_target)):
        for row in bucket:
            if row.symbol in chosen:
                continue
            selected.append(row)
            chosen.add(row.symbol)
            if sum(1 for x in selected if x.strategy_class == row.strategy_class) >= limit:
                break

    if len(selected) < max_symbols:
        fallback = sorted(
            [m for m in valid if m.symbol not in chosen],
            key=lambda m: max(m.breakout_score, m.reversion_score),
            reverse=True,
        )
        for row in fallback:
            selected.append(row)
            chosen.add(row.symbol)
            if len(selected) >= max_symbols:
                break

    selected = selected[:max_symbols]
    symbols = [m.symbol for m in selected]
    strategy_map = {m.symbol: m.strategy_class for m in selected}
    return symbols, strategy_map, selected


def main() -> int:
    ap = argparse.ArgumentParser(description="Build dynamic intraday equities watchlist/config from cached M5 data")
    ap.add_argument("--data-dir", default="data_cache/equities_1h")
    ap.add_argument("--symbols", default="", help="Optional explicit candidate pool (comma-separated); default = discover all *_M5.csv")
    ap.add_argument("--max-symbols", type=int, default=12)
    ap.add_argument("--breakout-target", type=int, default=6)
    ap.add_argument("--reversion-target", type=int, default=6)
    ap.add_argument("--min-avg-dollar-vol", type=float, default=25_000_000.0)
    ap.add_argument("--out-json", default="configs/intraday_config.json")
    args = ap.parse_args()

    data_dir = (ROOT / args.data_dir).resolve() if not Path(args.data_dir).is_absolute() else Path(args.data_dir)
    if args.symbols.strip():
        candidates = [
            s.strip().upper()
            for s in args.symbols.replace(";", ",").split(",")
            if s.strip() and s.strip().upper() not in EXCLUDED_SYMBOLS
        ]
    else:
        candidates = _discover_symbols(data_dir)

    metrics: list[SymbolMetrics] = []
    for symbol in candidates:
        csv_path = data_dir / f"{symbol}_M5.csv"
        if not csv_path.exists():
            continue
        row = _load_metrics(csv_path)
        if row is not None:
            metrics.append(row)

    symbols, strategy_map, selected = _rank_and_select(
        metrics,
        max_symbols=max(1, int(args.max_symbols)),
        breakout_target=max(0, int(args.breakout_target)),
        reversion_target=max(0, int(args.reversion_target)),
        min_avg_dollar_vol=float(args.min_avg_dollar_vol),
    )

    payload = {
        "_doc": "Auto-generated dynamic intraday watchlist for equities_alpaca_intraday_bridge.py",
        "_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "_builder": "build_equities_intraday_watchlist.py",
        "_selection": {
            "candidate_count": len(candidates),
            "ranked_count": len(metrics),
            "selected_count": len(symbols),
            "min_avg_dollar_vol": float(args.min_avg_dollar_vol),
        },
        "max_symbols": max(1, int(args.max_symbols)),
        "symbols": symbols,
        "strategy_map": strategy_map,
        "_scores": [asdict(m) for m in selected],
    }

    out_path = (ROOT / args.out_json).resolve() if not Path(args.out_json).is_absolute() else Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    print(f"saved={out_path}")
    print(f"symbols={','.join(symbols)}")
    for row in selected:
        score = row.breakout_score if row.strategy_class == "breakout_continuation" else row.reversion_score
        print(
            f"{row.symbol} class={row.strategy_class} score={score:.3f} "
            f"adv1d=${row.avg_dollar_vol_1d:,.0f} ret3d={row.ret_3d_pct:.2f}% "
            f"atr1d={row.atr_pct_1d:.3f}% er3d={row.eff_ratio_3d:.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
