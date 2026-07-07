#!/usr/bin/env python3
"""MRB1 crypto mean-reversion basket exploration.

Research-only. Uses local Bybit candle cache, no network and no live orders.

Hypothesis:
  Every 4h, rank liquid-ish cached symbols by distance from a rolling mean.
  Short the strongest positive z-scores, long the strongest negative z-scores.
  Exit with asymmetric but bounded ATR rails.

This is an exploration gate, not a promotion gate. A PASS here can only justify
follow-up validation/shadow, never live money.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

ROOT = Path(__file__).resolve().parent.parent

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.geometry_cache import aggregate_rows, load_cache_rows


@dataclass(frozen=True)
class Bar:
    ts: int
    o: float
    h: float
    l: float
    c: float
    v: float


@dataclass
class Trade:
    symbol: str
    side: str
    entry_ts: int
    exit_ts: int
    entry: float
    exit: float
    gross_r: float
    net_r: float
    fees_r: float
    reason: str
    z: float


def _utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _safe_float(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def _bars(rows: Sequence[Sequence[float]]) -> List[Bar]:
    out: List[Bar] = []
    for r in rows:
        if len(r) < 5:
            continue
        out.append(
            Bar(
                ts=int(float(r[0])),
                o=_safe_float(r[1]),
                h=_safe_float(r[2]),
                l=_safe_float(r[3]),
                c=_safe_float(r[4]),
                v=_safe_float(r[5]) if len(r) > 5 else 0.0,
            )
        )
    out.sort(key=lambda b: b.ts)
    return out


def _atr(bars: Sequence[Bar], idx: int, period: int) -> float:
    start = max(1, idx - period + 1)
    vals: List[float] = []
    for i in range(start, idx + 1):
        prev = bars[i - 1].c
        vals.append(max(bars[i].h - bars[i].l, abs(bars[i].h - prev), abs(bars[i].l - prev)))
    return sum(vals) / len(vals) if vals else 0.0


def _zscore(closes: Sequence[float], value: float) -> float:
    if len(closes) < 3:
        return 0.0
    mean = statistics.fmean(closes)
    sd = statistics.stdev(closes)
    if sd <= 1e-12:
        return 0.0
    return (value - mean) / sd


def _discover_symbols(cache_dir: Path, min_rows_5m: int, limit: int) -> List[str]:
    counts: Dict[str, int] = {}
    for p in cache_dir.glob("*_5_*.json"):
        sym = p.name.split("_5_", 1)[0]
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        counts[sym] = counts.get(sym, 0) + len(raw if isinstance(raw, list) else [])
    syms = [s for s, n in counts.items() if n >= int(min_rows_5m)]
    syms.sort(key=lambda s: counts.get(s, 0), reverse=True)
    return syms[: max(1, int(limit))]


def _load_symbol_bars(cache_dir: Path, symbol: str, days: int) -> List[Bar]:
    rows_60 = load_cache_rows(symbol, "60", data_cache_dir=cache_dir)
    if not rows_60:
        rows_5 = load_cache_rows(symbol, "5", data_cache_dir=cache_dir)
        rows_60 = aggregate_rows(rows_5, 60)
    bars = _bars(rows_60)
    if not bars:
        return []
    end_ts = bars[-1].ts
    start_ts = end_ts - int(days) * 86400 * 1000
    return [b for b in bars if b.ts >= start_ts]


def _simulate_one(
    symbol: str,
    bars: Sequence[Bar],
    *,
    lookback: int,
    z_entry: float,
    atr_period: int,
    sl_atr: float,
    tp_atr: float,
    max_hold_bars: int,
    fee_bps_entry: float,
    fee_bps_exit: float,
    rebalance_hours: int,
) -> List[Trade]:
    trades: List[Trade] = []
    if len(bars) < max(lookback + atr_period + 5, max_hold_bars + 5):
        return trades
    i = max(lookback, atr_period) + 1
    step = max(1, int(rebalance_hours))
    while i < len(bars) - 2:
        b = bars[i]
        hour_bucket = int((b.ts // 3_600_000) % step)
        if hour_bucket != 0:
            i += 1
            continue
        closes = [x.c for x in bars[i - lookback : i]]
        z = _zscore(closes, b.c)
        if abs(z) < z_entry:
            i += 1
            continue
        side = "short" if z > 0 else "long"
        entry = bars[i + 1].o
        atr = _atr(bars, i, atr_period)
        if atr <= 0 or entry <= 0:
            i += 1
            continue
        risk = sl_atr * atr
        if side == "long":
            sl = entry - risk
            tp = entry + tp_atr * atr
        else:
            sl = entry + risk
            tp = entry - tp_atr * atr
        exit_px = bars[min(len(bars) - 1, i + max_hold_bars)].c
        exit_idx = min(len(bars) - 1, i + max_hold_bars)
        reason = "time"
        for j in range(i + 1, min(len(bars), i + max_hold_bars + 1)):
            bj = bars[j]
            if side == "long":
                if bj.l <= sl:
                    exit_px = sl
                    exit_idx = j
                    reason = "sl"
                    break
                if bj.h >= tp:
                    exit_px = tp
                    exit_idx = j
                    reason = "tp"
                    break
            else:
                if bj.h >= sl:
                    exit_px = sl
                    exit_idx = j
                    reason = "sl"
                    break
                if bj.l <= tp:
                    exit_px = tp
                    exit_idx = j
                    reason = "tp"
                    break
        gross = ((exit_px - entry) if side == "long" else (entry - exit_px)) / risk
        fee_frac = (fee_bps_entry + fee_bps_exit) / 10_000.0
        fees_r = (entry * fee_frac) / risk
        trades.append(
            Trade(
                symbol=symbol,
                side=side,
                entry_ts=bars[i + 1].ts,
                exit_ts=bars[exit_idx].ts,
                entry=entry,
                exit=exit_px,
                gross_r=gross,
                net_r=gross - fees_r,
                fees_r=fees_r,
                reason=reason,
                z=z,
            )
        )
        i = exit_idx + 1
    return trades


def _pf(vals: Sequence[float]) -> float:
    gains = sum(v for v in vals if v > 0)
    losses = -sum(v for v in vals if v < 0)
    if losses <= 1e-12:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _max_dd(vals: Sequence[float]) -> float:
    eq = 0.0
    peak = 0.0
    dd = 0.0
    for v in vals:
        eq += v
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return dd


def _fold_stats(trades: Sequence[Trade], folds: int) -> List[dict]:
    if not trades:
        return []
    ts0 = min(t.entry_ts for t in trades)
    ts1 = max(t.entry_ts for t in trades)
    span = max(1, ts1 - ts0 + 1)
    out = []
    for f in range(folds):
        lo = ts0 + span * f // folds
        hi = ts0 + span * (f + 1) // folds
        vals = [t.net_r for t in trades if lo <= t.entry_ts < hi]
        out.append(
            {
                "fold": f + 1,
                "trades": len(vals),
                "net_r": round(sum(vals), 4),
                "pf": round(_pf(vals), 4) if vals else 0.0,
                "dd_r": round(_max_dd(vals), 4),
            }
        )
    return out


def _write_outputs(out_dir: Path, trades: Sequence[Trade], symbols: Sequence[str], args) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    trade_csv = out_dir / "trades.csv"
    with trade_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "side", "entry_ts", "exit_ts", "entry", "exit", "gross_r", "net_r", "fees_r", "reason", "z"])
        for t in trades:
            w.writerow([t.symbol, t.side, t.entry_ts, t.exit_ts, t.entry, t.exit, round(t.gross_r, 5), round(t.net_r, 5), round(t.fees_r, 5), t.reason, round(t.z, 4)])

    vals = [t.net_r for t in trades]
    sym_rows = []
    for sym in sorted(set(t.symbol for t in trades)):
        sv = [t.net_r for t in trades if t.symbol == sym]
        sym_rows.append((sym, len(sv), sum(sv), _pf(sv), _max_dd(sv)))
    sym_rows.sort(key=lambda r: r[2], reverse=True)
    with (out_dir / "symbol_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "trades", "net_r", "pf", "dd_r"])
        for r in sym_rows:
            w.writerow([r[0], r[1], round(r[2], 4), round(r[3], 4), round(r[4], 4)])

    folds = _fold_stats(trades, int(args.folds))
    with (out_dir / "folds.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["fold", "trades", "net_r", "pf", "dd_r"])
        w.writeheader()
        w.writerows(folds)

    net = sum(vals)
    pf = _pf(vals)
    wins = sum(1 for v in vals if v > 0)
    fold_pos = sum(1 for r in folds if r["net_r"] > 0)
    passed_exploration = bool(len(vals) >= int(args.min_trades) and net > 0 and pf >= float(args.min_pf) and fold_pos >= int(args.min_positive_folds))
    verdict = {
        "strategy": "MRB1 crypto mean-reversion basket exploration",
        "passed_exploration": passed_exploration,
        "symbols_loaded": list(symbols),
        "trades": len(vals),
        "net_r": round(net, 4),
        "pf": round(pf, 4),
        "winrate": round(wins / len(vals), 4) if vals else 0.0,
        "dd_r": round(_max_dd(vals), 4),
        "positive_folds": fold_pos,
        "folds": folds,
        "args": vars(args),
        "note": "Exploration-only. PASS is not live/canary approval.",
    }
    (out_dir / "verdict.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    lines = [
        "# MRB1 Crypto Mean-Reversion Basket Exploration",
        "",
        f"- output: `{out_dir}`",
        f"- symbols: {len(symbols)}",
        f"- trades: {len(vals)}",
        f"- netR: {net:.2f}",
        f"- PF: {pf:.3f}",
        f"- WR: {verdict['winrate']:.1%}",
        f"- maxDD: {verdict['dd_r']:.2f}R",
        f"- positive folds: {fold_pos}/{len(folds)}",
        f"- exploration verdict: {'PASS' if passed_exploration else 'FAIL'}",
        "",
        "Top symbols:",
    ]
    for r in sym_rows[:12]:
        lines.append(f"- {r[0]}: trades={r[1]}, netR={r[2]:.2f}, PF={r[3]:.2f}, DD={r[4]:.2f}")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Research-only crypto MRB mean-reversion exploration.")
    ap.add_argument("--symbols", default="", help="Comma-separated symbols. Empty = discover from data_cache.")
    ap.add_argument("--data-cache", default="data_cache")
    ap.add_argument("--days", type=int, default=360)
    ap.add_argument("--symbol-limit", type=int, default=40)
    ap.add_argument("--min-rows-5m", type=int, default=20_000)
    ap.add_argument("--lookback", type=int, default=20)
    ap.add_argument("--z-entry", type=float, default=1.75)
    ap.add_argument("--atr-period", type=int, default=14)
    ap.add_argument("--sl-atr", type=float, default=1.5)
    ap.add_argument("--tp-atr", type=float, default=2.0)
    ap.add_argument("--max-hold-bars", type=int, default=48)
    ap.add_argument("--rebalance-hours", type=int, default=4)
    ap.add_argument("--fee-bps-entry", type=float, default=6.0)
    ap.add_argument("--fee-bps-exit", type=float, default=6.0)
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--min-trades", type=int, default=80)
    ap.add_argument("--min-pf", type=float, default=1.05)
    ap.add_argument("--min-positive-folds", type=int, default=3)
    ap.add_argument("--tag", default="crypto_mrb_exploration_20260707")
    args = ap.parse_args()

    cache_dir = (ROOT / args.data_cache).resolve()
    if args.symbols.strip():
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = _discover_symbols(cache_dir, int(args.min_rows_5m), int(args.symbol_limit))
    if not symbols:
        raise SystemExit("No symbols discovered. Check data_cache or --symbols.")

    print("crypto MRB exploration start", flush=True)
    print(f"symbols={','.join(symbols)}", flush=True)
    print(f"cache={cache_dir}", flush=True)

    all_trades: List[Trade] = []
    loaded_symbols: List[str] = []
    for sym in symbols:
        bars = _load_symbol_bars(cache_dir, sym, int(args.days))
        if len(bars) < max(int(args.lookback) + int(args.atr_period) + 20, 120):
            print(f"{sym}: skip bars={len(bars)}", flush=True)
            continue
        loaded_symbols.append(sym)
        trades = _simulate_one(
            sym,
            bars,
            lookback=int(args.lookback),
            z_entry=float(args.z_entry),
            atr_period=int(args.atr_period),
            sl_atr=float(args.sl_atr),
            tp_atr=float(args.tp_atr),
            max_hold_bars=int(args.max_hold_bars),
            fee_bps_entry=float(args.fee_bps_entry),
            fee_bps_exit=float(args.fee_bps_exit),
            rebalance_hours=int(args.rebalance_hours),
        )
        all_trades.extend(trades)
        print(f"{sym}: bars={len(bars)} trades={len(trades)} netR={sum(t.net_r for t in trades):.2f}", flush=True)

    all_trades.sort(key=lambda t: t.entry_ts)
    out_dir = ROOT / "reports" / "research" / f"{args.tag}_{_utc_compact()}"
    _write_outputs(out_dir, all_trades, loaded_symbols, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
