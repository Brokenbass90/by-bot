#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex.data import load_m5_csv
from forex.engine import EngineConfig, run_backtest
from forex.types import Signal
from forex.strategies.trend_retest_session_v1 import Config, TrendRetestSessionV1
from forex.types import Candle
from news_filter import is_news_blocked, load_news_events, load_news_policy
from run_forex_multi_strategy_gate import _build_strategy as _build_preset_strategy


PRESETS: Dict[str, Dict[str, float | int]] = {
    "conservative": {
        "ema_fast": 55,
        "ema_slow": 220,
        "breakout_lookback": 42,
        "retest_window_bars": 8,
        "sl_atr_mult": 1.4,
        "rr": 2.5,
        "cooldown_bars": 32,
    },
    "balanced": {
        "ema_fast": 48,
        "ema_slow": 200,
        "breakout_lookback": 36,
        "retest_window_bars": 6,
        "sl_atr_mult": 1.5,
        "rr": 2.2,
        "cooldown_bars": 24,
    },
    "active": {
        "ema_fast": 34,
        "ema_slow": 144,
        "breakout_lookback": 24,
        "retest_window_bars": 5,
        "sl_atr_mult": 1.6,
        "rr": 1.9,
        "cooldown_bars": 14,
    },
}


class _NewsFilteredStrategy:
    def __init__(self, inner, *, symbol: str, strategy_name: str, events, policy):
        self.inner = inner
        self.symbol = symbol
        self.strategy_name = strategy_name
        self.events = list(events)
        self.policy = dict(policy or {})
        self.blocked_signals = 0

    def maybe_signal(self, candles, i: int) -> Signal | None:
        sig = self.inner.maybe_signal(candles, i)
        if sig is None:
            return None
        ts_utc = int(candles[i].ts)
        blocked, _reason = is_news_blocked(
            symbol=self.symbol,
            ts_utc=ts_utc,
            strategy_name=self.strategy_name,
            events=self.events,
            policy=self.policy,
        )
        if blocked:
            self.blocked_signals += 1
            return None
        return sig


def _default_pip_size(symbol: str) -> float:
    return 0.01 if symbol.upper().endswith("JPY") else 0.0001


def _utc_day(ts: int) -> int:
    return ts // 86400


def _month_key(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")


def _week_key(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _group_segments(candles: Sequence[Candle], mode: str, min_bars: int) -> List[Tuple[str, List[Candle]]]:
    if mode in {"monthly", "weekly"}:
        buckets: Dict[str, List[Candle]] = {}
        for c in candles:
            key = _month_key(c.ts) if mode == "monthly" else _week_key(c.ts)
            buckets.setdefault(key, []).append(c)
        out: List[Tuple[str, List[Candle]]] = []
        for k in sorted(buckets.keys()):
            seg = buckets[k]
            if len(seg) >= min_bars:
                out.append((k, seg))
        return out
    raise ValueError(f"Unsupported mode: {mode}")


def _rolling_segments(
    candles: Sequence[Candle],
    window_days: int,
    step_days: int,
    min_bars: int,
) -> List[Tuple[str, List[Candle]]]:
    if not candles:
        return []
    start_day = _utc_day(candles[0].ts)
    end_day = _utc_day(candles[-1].ts)

    out: List[Tuple[str, List[Candle]]] = []
    cur = start_day
    while cur + window_days <= end_day + 1:
        w_start = cur
        w_end = cur + window_days  # exclusive day
        seg = [c for c in candles if w_start <= _utc_day(c.ts) < w_end]
        if len(seg) >= min_bars:
            ds = datetime.fromtimestamp(w_start * 86400, tz=timezone.utc).strftime("%Y-%m-%d")
            de = datetime.fromtimestamp((w_end - 1) * 86400, tz=timezone.utc).strftime("%Y-%m-%d")
            out.append((f"{ds}..{de}", seg))
        cur += step_days
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Walk-forward stability check for Forex strategy")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--tag", default="walkforward")
    ap.add_argument("--strategy", default="trend_retest_session_v1:conservative")
    ap.add_argument("--preset", choices=sorted(PRESETS.keys()), default="conservative")
    ap.add_argument("--mode", choices=["weekly", "monthly", "rolling"], default="monthly")
    ap.add_argument("--window_days", type=int, default=28, help="For mode=rolling")
    ap.add_argument("--step_days", type=int, default=7, help="For mode=rolling")
    ap.add_argument("--min_bars", type=int, default=600, help="Skip segments with fewer bars")

    ap.add_argument("--spread_pips", type=float, default=1.2)
    ap.add_argument("--swap_long", type=float, default=-0.4)
    ap.add_argument("--swap_short", type=float, default=-0.4)
    ap.add_argument("--session_start_utc", type=int, default=6)
    ap.add_argument("--session_end_utc", type=int, default=20)
    ap.add_argument("--news-events-csv", default="", help="Optional normalized news events CSV for deterministic blackout gating")
    ap.add_argument("--news-policy-json", default="", help="Optional news policy JSON")

    # Optional override of preset params
    ap.add_argument("--ema_fast", type=int, default=None)
    ap.add_argument("--ema_slow", type=int, default=None)
    ap.add_argument("--breakout_lookback", type=int, default=None)
    ap.add_argument("--retest_window_bars", type=int, default=None)
    ap.add_argument("--sl_atr_mult", type=float, default=None)
    ap.add_argument("--rr", type=float, default=None)
    ap.add_argument("--cooldown_bars", type=int, default=None)
    args = ap.parse_args()

    candles = load_m5_csv(args.csv)
    if not candles:
        raise SystemExit(f"No candles loaded from {args.csv}")

    p = dict(PRESETS[args.preset])
    for key in ("ema_fast", "ema_slow", "breakout_lookback", "retest_window_bars", "sl_atr_mult", "rr", "cooldown_bars"):
        v = getattr(args, key)
        if v is not None:
            p[key] = v

    cfg = EngineConfig(
        pip_size=_default_pip_size(args.symbol),
        spread_pips=float(args.spread_pips),
        swap_long_pips_per_day=float(args.swap_long),
        swap_short_pips_per_day=float(args.swap_short),
    )

    if args.mode == "rolling":
        segments = _rolling_segments(
            candles=candles,
            window_days=max(7, int(args.window_days)),
            step_days=max(1, int(args.step_days)),
            min_bars=max(1, int(args.min_bars)),
        )
    else:
        segments = _group_segments(candles, mode=args.mode, min_bars=max(1, int(args.min_bars)))

    if not segments:
        raise SystemExit("No segments after filtering; lower --min_bars or use another mode")

    out_dir = Path("backtest_runs") / f"forex_wf_{args.tag}_{args.symbol.upper()}_{args.mode}"
    out_dir.mkdir(parents=True, exist_ok=True)
    news_events = load_news_events(args.news_events_csv) if args.news_events_csv else []
    news_policy = load_news_policy(args.news_policy_json) if args.news_policy_json else {}

    rows = []
    total_net = 0.0
    total_trades = 0
    pos = 0
    neg = 0
    flat = 0
    total_blocked_signals = 0

    for seg_name, seg_candles in segments:
        if ":" in args.strategy:
            strat = _build_preset_strategy(
                args.strategy,
                session_start=int(args.session_start_utc),
                session_end=int(args.session_end_utc),
            )
        else:
            strat = TrendRetestSessionV1(
                Config(
                    ema_fast=int(p["ema_fast"]),
                    ema_slow=int(p["ema_slow"]),
                    breakout_lookback=int(p["breakout_lookback"]),
                    retest_window_bars=int(p["retest_window_bars"]),
                    sl_atr_mult=float(p["sl_atr_mult"]),
                    rr=float(p["rr"]),
                    cooldown_bars=int(p["cooldown_bars"]),
                    session_utc_start=int(args.session_start_utc),
                    session_utc_end=int(args.session_end_utc),
                )
            )
        if news_events:
            strat = _NewsFilteredStrategy(
                strat,
                symbol=args.symbol.upper(),
                strategy_name=args.strategy.split(":", 1)[0],
                events=news_events,
                policy=news_policy,
            )
        trades, summary = run_backtest(seg_candles, strat, cfg)
        blocked_signals = int(strat.blocked_signals) if isinstance(strat, _NewsFilteredStrategy) else 0

        total_net += float(summary.net_pips)
        total_trades += int(summary.trades)
        total_blocked_signals += blocked_signals
        if summary.net_pips > 0:
            pos += 1
        elif summary.net_pips < 0:
            neg += 1
        else:
            flat += 1

        rows.append(
            {
                "segment": seg_name,
                "bars": len(seg_candles),
                "trades": int(summary.trades),
                "winrate": float(summary.winrate),
                "net_pips": float(summary.net_pips),
                "gross_pips": float(summary.gross_pips),
                "max_dd_pips": float(summary.max_dd_pips),
                "avg_win_pips": float(summary.avg_win_pips),
                "avg_loss_pips": float(summary.avg_loss_pips),
                "news_blocked_signals": blocked_signals,
            }
        )

    seg_csv = out_dir / "segments.csv"
    with seg_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "segment",
                "bars",
                "trades",
                "winrate",
                "net_pips",
                "gross_pips",
                "max_dd_pips",
                "avg_win_pips",
                "avg_loss_pips",
                "news_blocked_signals",
            ],
        )
        w.writeheader()
        w.writerows(rows)

    nets = [float(r["net_pips"]) for r in rows]
    best = max(rows, key=lambda x: float(x["net_pips"]))
    worst = min(rows, key=lambda x: float(x["net_pips"]))
    pos_share = (pos / len(rows) * 100.0) if rows else 0.0

    summary_csv = out_dir / "summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "symbol",
                "strategy",
                "mode",
                "preset",
                "segments",
                "positive_segments",
                "negative_segments",
                "flat_segments",
                "positive_share_pct",
                "total_trades",
                "total_net_pips",
                "avg_net_per_segment",
                "median_net_per_segment",
                "best_segment",
                "best_net_pips",
                "worst_segment",
                "worst_net_pips",
                "news_blocked_signals",
            ]
        )
        nets_sorted = sorted(nets)
        mid = len(nets_sorted) // 2
        median_net = (
            nets_sorted[mid]
            if len(nets_sorted) % 2 == 1
            else (nets_sorted[mid - 1] + nets_sorted[mid]) / 2.0
        )
        w.writerow(
            [
                args.symbol.upper(),
                args.strategy,
                args.mode,
                args.preset,
                len(rows),
                pos,
                neg,
                flat,
                f"{pos_share:.2f}",
                total_trades,
                f"{total_net:.4f}",
                f"{(total_net / len(rows)):.4f}",
                f"{median_net:.4f}",
                best["segment"],
                f"{float(best['net_pips']):.4f}",
                worst["segment"],
                f"{float(worst['net_pips']):.4f}",
                total_blocked_signals,
            ]
        )

    print(f"saved={out_dir}")
    print(summary_csv.read_text(encoding="utf-8").strip())
    print("top_segments:")
    for r in sorted(rows, key=lambda x: float(x["net_pips"]), reverse=True)[:5]:
        print(
            f"{r['segment']} net={float(r['net_pips']):.2f} trades={int(r['trades'])} "
            f"win={float(r['winrate']):.2f} dd={float(r['max_dd_pips']):.2f}"
        )
    print("worst_segments:")
    for r in sorted(rows, key=lambda x: float(x["net_pips"]))[:5]:
        print(
            f"{r['segment']} net={float(r['net_pips']):.2f} trades={int(r['trades'])} "
            f"win={float(r['winrate']):.2f} dd={float(r['max_dd_pips']):.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
