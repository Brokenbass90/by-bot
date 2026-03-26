#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from news_filter import is_news_blocked, load_news_events, load_news_policy
from forex.data import load_m5_csv
from forex.engine import EngineConfig, run_backtest
from forex.types import Candle, Signal
from run_forex_multi_strategy_gate import _build_strategy, _default_pip_size, _default_spread, _default_swap


def _month_key(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")


def _week_key(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _utc_day(ts: int) -> int:
    return ts // 86400


def _group_segments(candles: Sequence[Candle], mode: str, min_bars: int) -> List[Tuple[str, List[Candle]]]:
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


def _rolling_segments(
    candles: Sequence[Candle], window_days: int, step_days: int, min_bars: int
) -> List[Tuple[str, List[Candle]]]:
    if not candles:
        return []
    start_day = _utc_day(candles[0].ts)
    end_day = _utc_day(candles[-1].ts)

    out: List[Tuple[str, List[Candle]]] = []
    cur = start_day
    while cur + window_days <= end_day + 1:
        w_start = cur
        w_end = cur + window_days
        seg = [c for c in candles if w_start <= _utc_day(c.ts) < w_end]
        if len(seg) >= min_bars:
            ds = datetime.fromtimestamp(w_start * 86400, tz=timezone.utc).strftime("%Y-%m-%d")
            de = datetime.fromtimestamp((w_end - 1) * 86400, tz=timezone.utc).strftime("%Y-%m-%d")
            out.append((f"{ds}..{de}", seg))
        cur += step_days
    return out


def _sanitize_strategy_for_path(s: str) -> str:
    return s.replace(":", "_").replace("/", "_")


def _utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


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
        blocked, _reason = is_news_blocked(
            symbol=self.symbol,
            ts_utc=int(candles[i].ts),
            strategy_name=self.strategy_name,
            events=self.events,
            policy=self.policy,
        )
        if blocked:
            self.blocked_signals += 1
            return None
        return sig


def _run_segment(
    *,
    candles: Sequence[Candle],
    symbol: str,
    strategy_name: str,
    session_start: int,
    session_end: int,
    pip_size: float,
    spread_pips: float,
    swap_pips: float,
    news_events,
    news_policy,
):
    strategy = _build_strategy(strategy_name, session_start=session_start, session_end=session_end)
    if news_events:
        strategy = _NewsFilteredStrategy(
            strategy,
            symbol=symbol,
            strategy_name=strategy_name.split(":", 1)[0],
            events=news_events,
            policy=news_policy,
        )
    cfg = EngineConfig(
        pip_size=pip_size,
        spread_pips=spread_pips,
        swap_long_pips_per_day=swap_pips,
        swap_short_pips_per_day=swap_pips,
    )
    _, summary = run_backtest(candles, strategy, cfg)
    blocked_signals = int(strategy.blocked_signals) if isinstance(strategy, _NewsFilteredStrategy) else 0
    return summary, blocked_signals


def main() -> int:
    ap = argparse.ArgumentParser(description="Walk-forward for forex pair+strategy:preset with base+stress costs")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--strategy", required=True, help="Format: strategy or strategy:preset")
    ap.add_argument("--tag", default="fx_combo_wf")
    ap.add_argument("--mode", choices=["weekly", "monthly", "rolling"], default="monthly")
    ap.add_argument("--window_days", type=int, default=28, help="For mode=rolling")
    ap.add_argument("--step_days", type=int, default=7, help="For mode=rolling")
    ap.add_argument("--min_bars", type=int, default=600)
    ap.add_argument("--session_start_utc", type=int, default=6)
    ap.add_argument("--session_end_utc", type=int, default=20)
    ap.add_argument("--pip_size", type=float, default=0.0, help="Override pip size; <=0 means use pair default")
    ap.add_argument("--spread_pips", type=float, default=-1.0, help="<0 means use pair default")
    ap.add_argument("--swap_pips", type=float, default=999.0, help="999 means use pair default")
    ap.add_argument("--stress_spread_mult", type=float, default=1.5)
    ap.add_argument("--stress_swap_mult", type=float, default=1.5)
    ap.add_argument("--news-events-csv", default="", help="Optional normalized news events CSV for deterministic blackout gating")
    ap.add_argument("--news-policy-json", default="", help="Optional news policy JSON")
    args = ap.parse_args()

    symbol = args.symbol.strip().upper()
    candles = load_m5_csv(args.csv)
    if not candles:
        raise SystemExit(f"No candles loaded from {args.csv}")

    if args.mode == "rolling":
        segments = _rolling_segments(
            candles=candles,
            window_days=max(7, int(args.window_days)),
            step_days=max(1, int(args.step_days)),
            min_bars=max(1, int(args.min_bars)),
        )
    else:
        segments = _group_segments(candles=candles, mode=args.mode, min_bars=max(1, int(args.min_bars)))
    if not segments:
        raise SystemExit("No segments after filtering; lower --min_bars or change mode")

    spread = float(args.spread_pips) if float(args.spread_pips) >= 0 else _default_spread(symbol)
    swap = float(args.swap_pips) if float(args.swap_pips) != 999.0 else _default_swap(symbol)
    pip_size = float(args.pip_size) if float(args.pip_size) > 0 else _default_pip_size(symbol)

    out_dir = (
        ROOT
        / "backtest_runs"
        / f"forex_combo_wf_{args.tag}_{symbol}_{_sanitize_strategy_for_path(args.strategy)}_{args.mode}_{_utc_compact()}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    news_events = load_news_events(args.news_events_csv) if args.news_events_csv else []
    news_policy = load_news_policy(args.news_policy_json) if args.news_policy_json else {}

    rows: List[dict] = []
    total_blocked_signals = 0
    for seg_name, seg_candles in segments:
        base, blocked_signals = _run_segment(
            candles=seg_candles,
            symbol=symbol,
            strategy_name=args.strategy,
            session_start=int(args.session_start_utc),
            session_end=int(args.session_end_utc),
            pip_size=pip_size,
            spread_pips=spread,
            swap_pips=swap,
            news_events=news_events,
            news_policy=news_policy,
        )
        stress, _stress_blocked_signals = _run_segment(
            candles=seg_candles,
            symbol=symbol,
            strategy_name=args.strategy,
            session_start=int(args.session_start_utc),
            session_end=int(args.session_end_utc),
            pip_size=pip_size,
            spread_pips=spread * float(args.stress_spread_mult),
            swap_pips=swap * float(args.stress_swap_mult),
            news_events=news_events,
            news_policy=news_policy,
        )
        total_blocked_signals += blocked_signals
        rows.append(
            {
                "segment": seg_name,
                "bars": len(seg_candles),
                "base_trades": int(base.trades),
                "base_net_pips": float(base.net_pips),
                "base_dd_pips": float(base.max_dd_pips),
                "base_winrate": float(base.winrate),
                "stress_trades": int(stress.trades),
                "stress_net_pips": float(stress.net_pips),
                "stress_dd_pips": float(stress.max_dd_pips),
                "stress_winrate": float(stress.winrate),
                "news_blocked_signals": blocked_signals,
                "both_positive": int((float(base.net_pips) > 0) and (float(stress.net_pips) > 0)),
            }
        )

    seg_csv = out_dir / "segments.csv"
    with seg_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "segment",
                "bars",
                "base_trades",
                "base_net_pips",
                "base_dd_pips",
                "base_winrate",
                "stress_trades",
                "stress_net_pips",
                "stress_dd_pips",
                "stress_winrate",
                "news_blocked_signals",
                "both_positive",
            ],
        )
        w.writeheader()
        w.writerows(rows)

    base_nets = [float(r["base_net_pips"]) for r in rows]
    stress_nets = [float(r["stress_net_pips"]) for r in rows]
    both_pos = sum(int(r["both_positive"]) for r in rows)
    summary_csv = out_dir / "summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "symbol",
                "strategy",
                "mode",
                "segments",
                "both_positive_segments",
                "both_positive_share_pct",
                "total_base_net_pips",
                "total_stress_net_pips",
                "median_base_net_pips",
                "median_stress_net_pips",
                "total_base_trades",
                "total_stress_trades",
                "news_blocked_signals",
            ]
        )
        w.writerow(
            [
                symbol,
                args.strategy,
                args.mode,
                len(rows),
                both_pos,
                f"{(both_pos / len(rows) * 100.0):.2f}",
                f"{sum(base_nets):.4f}",
                f"{sum(stress_nets):.4f}",
                f"{median(base_nets):.4f}",
                f"{median(stress_nets):.4f}",
                sum(int(r["base_trades"]) for r in rows),
                sum(int(r["stress_trades"]) for r in rows),
                total_blocked_signals,
            ]
        )

    print("forex combo walkforward done")
    print(f"symbol={symbol} strategy={args.strategy} mode={args.mode} segments={len(rows)}")
    print(f"both_positive={both_pos}/{len(rows)} ({(both_pos / len(rows) * 100.0):.2f}%)")
    print(f"base_total={sum(base_nets):.2f} stress_total={sum(stress_nets):.2f}")
    print(f"news_blocked_signals={total_blocked_signals}")
    print(f"segments_csv={seg_csv}")
    print(f"summary_csv={summary_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
