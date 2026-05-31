#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.equities_monthly_research_sim import (  # noqa: E402
    Candidate,
    DailyBar,
    _aggregate_daily,
    _candidate_from_snapshot,
    _clusters_for_ticker,
    _load_earnings_blackouts,
    _pair_corr,
    _parse_cluster_groups,
    _parse_forbid_pairs,
    _position_weight,
    _simulate_trades_portfolio_stop,
    _sma,
    _universe_health_score,
)


def _idx_by_day(daily: list[DailyBar]) -> dict[str, int]:
    return {bar.day: i for i, bar in enumerate(daily)}


def _last_idx_on_or_before(daily: list[DailyBar], day: str) -> int | None:
    # Data sets are small enough that this simple scan keeps the script clear.
    out: int | None = None
    for i, bar in enumerate(daily):
        if bar.day <= day:
            out = i
        else:
            break
    return out


def _regime_ok(
    daily_map: dict[str, list[DailyBar]],
    snapshot_day: str,
    lookback_days: int,
    min_breadth_sma_pct: float,
    min_breadth_mom_pct: float,
    min_avg_mom_pct: float,
) -> bool:
    if min_breadth_sma_pct <= 0 and min_breadth_mom_pct <= 0 and min_avg_mom_pct <= -999:
        return True
    total = 0
    above = 0
    pos = 0
    moms: list[float] = []
    need = max(lookback_days + 5, 25)
    for daily in daily_map.values():
        idx = _last_idx_on_or_before(daily, snapshot_day)
        if idx is None or idx < need:
            continue
        closes = [x.c for x in daily[: idx + 1]]
        close = closes[-1]
        sma = _sma(closes, lookback_days)
        if not (math.isfinite(sma) and close > 0):
            continue
        mom = close / closes[-lookback_days] - 1.0
        total += 1
        above += int(close > sma)
        pos += int(mom > 0)
        moms.append(mom * 100.0)
    if total <= 0:
        return False
    return (
        100.0 * above / total >= min_breadth_sma_pct
        and 100.0 * pos / total >= min_breadth_mom_pct
        and sum(moms) / max(1, len(moms)) >= min_avg_mom_pct
    )


def _benchmark_ok(
    benchmark_map: dict[str, list[DailyBar]],
    snapshot_day: str,
    lookback_days: int,
    min_above_sma_count: int,
    min_positive_mom_count: int,
    min_avg_mom_pct: float,
) -> bool:
    if not benchmark_map:
        return True
    total = 0
    above = 0
    pos = 0
    moms: list[float] = []
    need = max(lookback_days + 5, 25)
    for daily in benchmark_map.values():
        idx = _last_idx_on_or_before(daily, snapshot_day)
        if idx is None or idx < need:
            continue
        closes = [x.c for x in daily[: idx + 1]]
        close = closes[-1]
        sma = _sma(closes, lookback_days)
        if not (math.isfinite(sma) and close > 0):
            continue
        mom = close / closes[-lookback_days] - 1.0
        total += 1
        above += int(close > sma)
        pos += int(mom > 0)
        moms.append(mom * 100.0)
    if total <= 0:
        return False
    return (
        above >= min_above_sma_count
        and pos >= min_positive_mom_count
        and sum(moms) / max(1, len(moms)) >= min_avg_mom_pct
    )


def _select_candidates(
    candidates: list[tuple[Candidate, int, list[DailyBar]]],
    top_n: int,
    cluster_groups: list[set[str]],
    max_per_cluster: int,
    forbid_pairs: set[tuple[str, str]],
    corr_lookback_days: int,
    max_pair_corr: float,
) -> list[tuple[Candidate, int, list[DailyBar]]]:
    picks: list[tuple[Candidate, int, list[DailyBar]]] = []
    cluster_counts: dict[int, int] = defaultdict(int)
    remaining = sorted(candidates, key=lambda x: x[0].score, reverse=True)
    for triplet in remaining:
        cand = triplet[0]
        if any(tuple(sorted((cand.ticker, p[0].ticker))) in forbid_pairs for p in picks):
            continue
        clusters = _clusters_for_ticker(cand.ticker, cluster_groups)
        if clusters and any(cluster_counts[c] >= max_per_cluster for c in clusters):
            continue
        if corr_lookback_days > 0 and max_pair_corr < 1.0:
            too_corr = False
            for picked in picks:
                corr = _pair_corr(
                    triplet[2],
                    triplet[1] - 1,
                    picked[2],
                    picked[1] - 1,
                    corr_lookback_days,
                )
                if corr is not None and corr > max_pair_corr:
                    too_corr = True
                    break
            if too_corr:
                continue
        picks.append(triplet)
        for c in clusters:
            cluster_counts[c] += 1
        if len(picks) >= top_n:
            break
    return picks


def _max_drawdown_pct(curve: list[float]) -> float:
    peak = curve[0] if curve else 1.0
    max_dd = 0.0
    for x in curve:
        peak = max(peak, x)
        if peak > 0:
            max_dd = min(max_dd, x / peak - 1.0)
    return max_dd * 100.0


def main() -> int:
    ap = argparse.ArgumentParser(description="Point-in-time equities swing/intraweek research simulator")
    ap.add_argument("--tickers", required=True)
    ap.add_argument("--data-dir", default="data_cache/equities_1h")
    ap.add_argument("--benchmark-tickers", default="SPY,QQQ")
    ap.add_argument("--benchmark-data-dir", default="")
    ap.add_argument("--start-date", default="2024-05-01")
    ap.add_argument("--end-date", default="2026-04-27")
    ap.add_argument("--rebalance-days", type=int, default=5)
    ap.add_argument("--top-n", type=int, default=3)
    ap.add_argument("--max-hold-days", type=int, default=5)
    ap.add_argument("--lookback-days", type=int, default=28)
    ap.add_argument("--min-mom-lookback-pct", type=float, default=5.0)
    ap.add_argument("--pullback-min-pct", type=float, default=-12.0)
    ap.add_argument("--pullback-max-pct", type=float, default=-1.0)
    ap.add_argument("--regime-min-breadth-sma-pct", type=float, default=55.0)
    ap.add_argument("--regime-min-breadth-mom-pct", type=float, default=40.0)
    ap.add_argument("--regime-min-avg-mom-pct", type=float, default=0.5)
    ap.add_argument("--benchmark-lookback-days", type=int, default=60)
    ap.add_argument("--benchmark-min-above-sma-count", type=int, default=1)
    ap.add_argument("--benchmark-min-positive-mom-count", type=int, default=1)
    ap.add_argument("--benchmark-min-avg-mom-pct", type=float, default=0.0)
    ap.add_argument("--earnings-csv", default="")
    ap.add_argument("--earnings-blackout-days-before", type=int, default=3)
    ap.add_argument("--earnings-blackout-days-after", type=int, default=1)
    ap.add_argument("--cluster-groups", default="")
    ap.add_argument("--forbid-pairs", default="")
    ap.add_argument("--max-per-cluster", type=int, default=1)
    ap.add_argument("--corr-lookback-days", type=int, default=60)
    ap.add_argument("--max-pair-corr", type=float, default=0.80)
    ap.add_argument("--universe-top-k", type=int, default=18)
    ap.add_argument("--universe-score-lookback-days", type=int, default=80)
    ap.add_argument("--stop-atr-mult", type=float, default=1.6)
    ap.add_argument("--target-atr-mult", type=float, default=2.4)
    ap.add_argument("--portfolio-stop-pct", type=float, default=0.04)
    ap.add_argument("--be-trigger-r", type=float, default=0.8)
    ap.add_argument("--trail-atr-mult", type=float, default=1.2)
    ap.add_argument("--position-weight-mode", default="score_inv_vol")
    ap.add_argument("--tag", default="equities_swing_research")
    args = ap.parse_args()

    tickers = [x.strip().upper() for x in args.tickers.split(",") if x.strip()]
    data_dir = Path(args.data_dir)
    daily_map: dict[str, list[DailyBar]] = {}
    for ticker in tickers:
        p = data_dir / f"{ticker}_M5.csv"
        if p.exists():
            daily_map[ticker] = _aggregate_daily(p)

    benchmark_map: dict[str, list[DailyBar]] = {}
    benchmark_data_dir = Path(args.benchmark_data_dir) if args.benchmark_data_dir else data_dir
    for ticker in [x.strip().upper() for x in args.benchmark_tickers.split(",") if x.strip()]:
        p = benchmark_data_dir / f"{ticker}_M5.csv"
        if p.exists():
            benchmark_map[ticker] = _aggregate_daily(p)

    if benchmark_map:
        calendar_source = next(iter(benchmark_map.values()))
    elif daily_map:
        calendar_source = next(iter(daily_map.values()))
    else:
        raise SystemExit("no daily data loaded")

    days = [b.day for b in calendar_source if args.start_date <= b.day <= args.end_date]
    snapshot_days = days[:: max(1, int(args.rebalance_days))]
    earnings = _load_earnings_blackouts(
        args.earnings_csv,
        int(args.earnings_blackout_days_before),
        int(args.earnings_blackout_days_after),
    )
    forbid_pairs = _parse_forbid_pairs(args.forbid_pairs)
    clusters = _parse_cluster_groups(args.cluster_groups)

    out_dir = ROOT / "backtest_runs" / f"equities_swing_research_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{args.tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    trades_rows: list[dict[str, object]] = []
    picks_rows: list[dict[str, object]] = []
    cycle_rows: list[dict[str, object]] = []
    equity = 1.0
    curve = [equity]

    for snapshot_day in snapshot_days:
        if not _benchmark_ok(
            benchmark_map,
            snapshot_day,
            int(args.benchmark_lookback_days),
            int(args.benchmark_min_above_sma_count),
            int(args.benchmark_min_positive_mom_count),
            float(args.benchmark_min_avg_mom_pct),
        ):
            cycle_rows.append({"snapshot_day": snapshot_day, "status": "benchmark_block", "cycle_return_pct": 0.0, "picks": ""})
            continue
        if not _regime_ok(
            daily_map,
            snapshot_day,
            int(args.lookback_days),
            float(args.regime_min_breadth_sma_pct),
            float(args.regime_min_breadth_mom_pct),
            float(args.regime_min_avg_mom_pct),
        ):
            cycle_rows.append({"snapshot_day": snapshot_day, "status": "regime_block", "cycle_return_pct": 0.0, "picks": ""})
            continue

        snapshot_meta: dict[str, tuple[int, list[DailyBar]]] = {}
        universe_scores: dict[str, float] = {}
        for ticker, daily in daily_map.items():
            idx = _last_idx_on_or_before(daily, snapshot_day)
            if idx is None or idx + 1 >= len(daily):
                continue
            snapshot_meta[ticker] = (idx, daily)
            universe_scores[ticker] = _universe_health_score(daily, idx, int(args.universe_score_lookback_days))
        allowed: set[str] | None = None
        if int(args.universe_top_k) > 0:
            scored = [(t, s) for t, s in universe_scores.items() if math.isfinite(s)]
            scored.sort(key=lambda x: x[1], reverse=True)
            allowed = {t for t, _ in scored[: int(args.universe_top_k)]}

        candidates: list[tuple[Candidate, int, list[DailyBar]]] = []
        for ticker, (idx, daily) in snapshot_meta.items():
            if allowed is not None and ticker not in allowed:
                continue
            cand = _candidate_from_snapshot(
                ticker,
                daily,
                idx,
                lookback_days=int(args.lookback_days),
                min_mom60=float(args.min_mom_lookback_pct) / 100.0,
                pullback_min=float(args.pullback_min_pct) / 100.0,
                pullback_max=float(args.pullback_max_pct) / 100.0,
                stop_atr_mult=float(args.stop_atr_mult),
                target_atr_mult=float(args.target_atr_mult),
            )
            if cand is None:
                continue
            if cand.entry_day in earnings.get(ticker, set()):
                continue
            cand.universe_score = universe_scores.get(ticker, float("nan"))
            candidates.append((cand, idx + 1, daily))

        picks = _select_candidates(
            candidates,
            max(1, int(args.top_n)),
            clusters,
            int(args.max_per_cluster),
            forbid_pairs,
            int(args.corr_lookback_days),
            float(args.max_pair_corr),
        )
        if not picks:
            cycle_rows.append({"snapshot_day": snapshot_day, "status": "no_picks", "cycle_return_pct": 0.0, "picks": ""})
            continue

        raw_weights = [_position_weight(p[0], str(args.position_weight_mode)) for p in picks]
        total_weight = sum(max(0.0, x) for x in raw_weights) or float(len(raw_weights))
        weights = [max(0.0, x) / total_weight for x in raw_weights]
        exits = _simulate_trades_portfolio_stop(
            picks,
            weights,
            int(args.max_hold_days),
            float(args.portfolio_stop_pct),
            be_trigger_r=float(args.be_trigger_r),
            trail_atr_mult=float(args.trail_atr_mult),
        )
        cycle_ret = 0.0
        for (cand, entry_idx, daily), weight, (exit_idx, exit_price, reason) in zip(picks, weights, exits):
            ret = exit_price / cand.entry_price - 1.0
            cycle_ret += weight * ret
            exit_day = daily[min(exit_idx, len(daily) - 1)].day
            trades_rows.append(
                {
                    "snapshot_day": snapshot_day,
                    "ticker": cand.ticker,
                    "entry_day": cand.entry_day,
                    "exit_day": exit_day,
                    "entry_price": f"{cand.entry_price:.4f}",
                    "exit_price": f"{exit_price:.4f}",
                    "stop_price": f"{cand.stop_price:.4f}",
                    "target_price": f"{cand.target_price:.4f}",
                    "return_pct": f"{ret * 100.0:.4f}",
                    "weight": f"{weight:.6f}",
                    "reason": reason,
                    "score": f"{cand.score:.6f}",
                    "atr20_pct": f"{cand.atr20_pct:.3f}",
                    "momentum_pct": f"{cand.momentum60_pct:.3f}",
                    "pullback_pct": f"{cand.pullback60_pct:.3f}",
                }
            )
            picks_rows.append(
                {
                    "snapshot_day": snapshot_day,
                    "ticker": cand.ticker,
                    "entry_day": cand.entry_day,
                    "score": f"{cand.score:.6f}",
                    "weight": f"{weight:.6f}",
                    "atr20_pct": f"{cand.atr20_pct:.3f}",
                    "momentum_pct": f"{cand.momentum60_pct:.3f}",
                    "pullback_pct": f"{cand.pullback60_pct:.3f}",
                    "universe_score": f"{cand.universe_score:.6f}" if math.isfinite(cand.universe_score) else "",
                }
            )
        equity *= 1.0 + cycle_ret
        curve.append(equity)
        cycle_rows.append(
            {
                "snapshot_day": snapshot_day,
                "status": "active",
                "cycle_return_pct": f"{cycle_ret * 100.0:.4f}",
                "picks": ";".join(p[0].ticker for p in picks),
            }
        )

    trade_returns = [float(r["return_pct"]) for r in trades_rows]
    wins = [x for x in trade_returns if x > 0]
    losses = [x for x in trade_returns if x < 0]
    pf = (sum(wins) / abs(sum(losses))) if losses else (float("inf") if wins else 0.0)
    active_cycles = sum(1 for r in cycle_rows if r.get("status") == "active")
    neg_cycles = sum(1 for r in cycle_rows if r.get("status") == "active" and float(r.get("cycle_return_pct") or 0) < 0)
    ret_pct = (equity - 1.0) * 100.0
    cal_days = max(1, (datetime.strptime(args.end_date, "%Y-%m-%d") - datetime.strptime(args.start_date, "%Y-%m-%d")).days)
    ann_pct = (math.pow(max(1e-9, equity), 365.0 / cal_days) - 1.0) * 100.0

    with (out_dir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        fields = [
            "cycles",
            "active_cycles",
            "inactive_cycles",
            "trades",
            "winrate_pct",
            "profit_factor",
            "avg_trade_return_pct",
            "compounded_return_pct",
            "annualized_return_pct",
            "max_cycle_dd_pct",
            "negative_cycles",
            "start_date",
            "end_date",
            "rebalance_days",
            "top_n",
            "max_hold_days",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerow(
            {
                "cycles": len(cycle_rows),
                "active_cycles": active_cycles,
                "inactive_cycles": len(cycle_rows) - active_cycles,
                "trades": len(trades_rows),
                "winrate_pct": f"{(len(wins) / len(trade_returns) * 100.0) if trade_returns else 0.0:.2f}",
                "profit_factor": f"{pf:.4f}" if math.isfinite(pf) else "inf",
                "avg_trade_return_pct": f"{(sum(trade_returns) / len(trade_returns)) if trade_returns else 0.0:.4f}",
                "compounded_return_pct": f"{ret_pct:.4f}",
                "annualized_return_pct": f"{ann_pct:.4f}",
                "max_cycle_dd_pct": f"{_max_drawdown_pct(curve):.4f}",
                "negative_cycles": neg_cycles,
                "start_date": args.start_date,
                "end_date": args.end_date,
                "rebalance_days": int(args.rebalance_days),
                "top_n": int(args.top_n),
                "max_hold_days": int(args.max_hold_days),
            }
        )

    def _write_rows(name: str, rows: list[dict[str, object]]) -> None:
        if not rows:
            (out_dir / name).write_text("", encoding="utf-8")
            return
        with (out_dir / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    _write_rows("cycles.csv", cycle_rows)
    _write_rows("picks.csv", picks_rows)
    _write_rows("trades.csv", trades_rows)
    print(f"saved={out_dir}")
    with (out_dir / "summary.csv").open(encoding="utf-8") as f:
        print(f.read().strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
