#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
from statistics import pstdev
from typing import Iterable

import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex.data import load_m5_csv


@dataclass
class DailyBar:
    ts: int
    day: str
    o: float
    h: float
    l: float
    c: float
    v: float


@dataclass
class Candidate:
    ticker: str
    snapshot_day: str
    entry_day: str
    entry_price: float
    stop_price: float
    target_price: float
    score: float
    atr20_pct: float
    momentum20_pct: float
    momentum60_pct: float
    pullback60_pct: float
    base_score: float = float("nan")
    overlay_score: float = 0.0
    universe_score: float = float("nan")
    selection_score: float = float("nan")
    corr_penalty: float = 0.0
    max_corr_to_existing: float = float("nan")


@dataclass
class RegimeStats:
    breadth_above_sma_pct: float
    breadth_positive_mom_pct: float
    avg_mom60_pct: float


@dataclass
class BenchmarkStats:
    total: int
    above_sma_count: int
    positive_mom_count: int
    avg_mom60_pct: float


def _parse_iso_date(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _load_earnings_blackouts(csv_path: str, days_before: int, days_after: int) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    if not csv_path:
        return out
    path = Path(csv_path)
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for row in rd:
            ticker = (row.get("ticker") or row.get("symbol") or "").strip().upper()
            dt = _parse_iso_date(row.get("date") or row.get("earnings_date") or row.get("report_date") or "")
            if not ticker or dt is None:
                continue
            for offset in range(-max(0, days_before), max(0, days_after) + 1):
                out[ticker].add((dt + timedelta(days=offset)).strftime("%Y-%m-%d"))
    return out


def _load_overlay_scores(csv_path: str) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    if not csv_path:
        return out
    path = Path(csv_path)
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for row in rd:
            ticker = (row.get("ticker") or row.get("symbol") or "").strip().upper()
            day = (row.get("day") or row.get("date") or row.get("snapshot_day") or row.get("month") or "").strip()
            raw_score = row.get("score") or row.get("overlay_score") or row.get("bonus") or ""
            if not ticker or not day or not str(raw_score).strip():
                continue
            try:
                out[(day, ticker)] = float(raw_score)
            except Exception:
                continue
    return out


def _overlay_score_for_snapshot(overlay_scores: dict[tuple[str, str], float], snapshot_day: str, ticker: str) -> float:
    if not overlay_scores:
        return 0.0
    ticker = (ticker or "").strip().upper()
    snapshot_day = (snapshot_day or "").strip()
    if not snapshot_day:
        return 0.0
    return float(
        overlay_scores.get((snapshot_day, ticker))
        or overlay_scores.get((snapshot_day[:7], ticker))
        or 0.0
    )


def _parse_forbid_pairs(raw: str) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    if not raw:
        return out
    for part in str(raw).split(";"):
        s = part.strip().upper()
        if not s or ":" not in s:
            continue
        a, b = [x.strip().upper() for x in s.split(":", 1)]
        if a and b and a != b:
            out.add(tuple(sorted((a, b))))
    return out


def _parse_cluster_groups(raw: str) -> list[set[str]]:
    out: list[set[str]] = []
    if not raw:
        return out
    for group in str(raw).split(";"):
        tickers = {x.strip().upper() for x in group.split(",") if x.strip()}
        if len(tickers) >= 2:
            out.append(tickers)
    return out


def _clusters_for_ticker(ticker: str, groups: list[set[str]]) -> list[int]:
    ticker = (ticker or "").strip().upper()
    return [idx for idx, group in enumerate(groups) if ticker in group]


def _daily_returns_window(daily: list[DailyBar], end_idx: int, lookback_days: int) -> dict[str, float]:
    out: dict[str, float] = {}
    if end_idx <= 0 or lookback_days <= 1:
        return out
    start_idx = max(1, end_idx - lookback_days + 1)
    for i in range(start_idx, end_idx + 1):
        prev = float(daily[i - 1].c)
        cur = float(daily[i].c)
        if prev <= 0:
            continue
        out[daily[i].day] = cur / prev - 1.0
    return out


def _pearson_corr(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mean_x = sum(xs) / float(len(xs))
    mean_y = sum(ys) / float(len(ys))
    cov = 0.0
    var_x = 0.0
    var_y = 0.0
    for x, y in zip(xs, ys):
        dx = x - mean_x
        dy = y - mean_y
        cov += dx * dy
        var_x += dx * dx
        var_y += dy * dy
    if var_x <= 0 or var_y <= 0:
        return None
    return cov / math.sqrt(var_x * var_y)


def _pair_corr(
    daily_a: list[DailyBar],
    end_idx_a: int,
    daily_b: list[DailyBar],
    end_idx_b: int,
    lookback_days: int,
) -> float | None:
    ra = _daily_returns_window(daily_a, end_idx_a, lookback_days)
    rb = _daily_returns_window(daily_b, end_idx_b, lookback_days)
    overlap = sorted(set(ra).intersection(rb))
    if len(overlap) < max(10, lookback_days // 3):
        return None
    xs = [ra[d] for d in overlap]
    ys = [rb[d] for d in overlap]
    return _pearson_corr(xs, ys)


def _universe_health_score(daily: list[DailyBar], i: int, lookback_days: int) -> float:
    lookback_days = max(20, int(lookback_days))
    if i < lookback_days or i < 25:
        return float("nan")
    closes = [x.c for x in daily[: i + 1]]
    close = closes[-1]
    if close <= 0:
        return float("nan")
    start_close = daily[i - lookback_days].c
    if start_close <= 0:
        return float("nan")
    mom = close / start_close - 1.0
    high = max(x.h for x in daily[i - lookback_days + 1 : i + 1])
    dd_from_high = close / max(1e-12, high) - 1.0
    sma20 = _sma(closes, 20)
    sma60 = _sma(closes, 60)
    close_vs_sma20 = close / sma20 - 1.0 if math.isfinite(sma20) and sma20 > 0 else 0.0
    close_vs_sma60 = close / sma60 - 1.0 if math.isfinite(sma60) and sma60 > 0 else 0.0
    rets = []
    start_idx = max(1, i - lookback_days + 1)
    for j in range(start_idx, i + 1):
        prev = daily[j - 1].c
        cur = daily[j].c
        if prev <= 0:
            continue
        rets.append(cur / prev - 1.0)
    vol = pstdev(rets) if len(rets) >= 5 else 0.0
    # Reward persistent strength, punish being too far below recent highs and excessive noise.
    return (
        1.35 * mom
        + 0.45 * close_vs_sma20
        + 0.35 * close_vs_sma60
        - 0.90 * abs(min(0.0, dd_from_high))
        - 2.20 * vol
    )


def _aggregate_daily(csv_path: Path) -> list[DailyBar]:
    candles = load_m5_csv(str(csv_path))
    by_day: dict[str, list] = defaultdict(list)
    for c in candles:
        day = datetime.fromtimestamp(c.ts, tz=timezone.utc).strftime("%Y-%m-%d")
        by_day[day].append(c)
    out: list[DailyBar] = []
    for day in sorted(by_day):
        rows = by_day[day]
        out.append(
            DailyBar(
                ts=int(rows[0].ts),
                day=day,
                o=float(rows[0].o),
                h=max(float(x.h) for x in rows),
                l=min(float(x.l) for x in rows),
                c=float(rows[-1].c),
                v=sum(float(x.v) for x in rows),
            )
        )
    return out


def _sma(vals: list[float], period: int) -> float:
    if len(vals) < period:
        return float("nan")
    seg = vals[-period:]
    return sum(seg) / float(period)


def _position_weight(cand: Candidate, mode: str) -> float:
    mode = (mode or "equal").strip().lower()
    atr_pct = max(1e-6, float(cand.atr20_pct))
    score = max(1e-6, float(cand.score))
    if mode == "inv_vol":
        return 1.0 / atr_pct
    if mode == "score":
        return score
    if mode == "score_inv_vol":
        return score / atr_pct
    return 1.0


def _atr(daily: list[DailyBar], period: int) -> float:
    if len(daily) < period + 1:
        return float("nan")
    trs: list[float] = []
    for i in range(-period, 0):
        h = daily[i].h
        l = daily[i].l
        pc = daily[i - 1].c
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / float(period) if trs else float("nan")


def _monthly_snapshot_idx(daily: list[DailyBar]) -> list[int]:
    out: list[int] = []
    for i in range(len(daily) - 1):
        cur = daily[i].day[:7]
        nxt = daily[i + 1].day[:7]
        if cur != nxt:
            out.append(i)
    return out


def _candidate_from_snapshot(
    ticker: str,
    daily: list[DailyBar],
    i: int,
    *,
    lookback_days: int,
    min_mom60: float,
    pullback_min: float,
    pullback_max: float,
    stop_atr_mult: float,
    target_atr_mult: float,
) -> Candidate | None:
    hist_need = max(lookback_days + 5, 25)
    if i < hist_need or i + 1 >= len(daily):
        return None
    closes = [x.c for x in daily[: i + 1]]
    close = closes[-1]
    sma20 = _sma(closes, 20)
    sma60 = _sma(closes, lookback_days)
    if not (math.isfinite(sma20) and math.isfinite(sma60) and close > 0):
        return None
    mom20 = close / closes[-20] - 1.0
    mom60 = close / closes[-lookback_days] - 1.0
    high60 = max(x.h for x in daily[i - (lookback_days - 1) : i + 1])
    pullback60 = close / high60 - 1.0
    rets20 = []
    for j in range(i - 19, i + 1):
        if j <= 0:
            continue
        rets20.append(daily[j].c / daily[j - 1].c - 1.0)
    vol20 = pstdev(rets20) if len(rets20) >= 5 else 0.0
    atr20 = _atr(daily[: i + 1], 20)
    if not math.isfinite(atr20) or atr20 <= 0:
        return None

    # Monthly swing shortlist: strong names with a controlled pullback, not parabolic junk.
    if close < sma60:
        return None
    if mom60 <= min_mom60:
        return None
    if not (pullback_min <= pullback60 <= pullback_max):
        return None

    score = (
        1.20 * mom60
        + 0.60 * mom20
        - 0.35 * abs(pullback60)
        - 2.50 * vol20
        + (0.02 if close > sma20 else -0.02)
    )
    entry_bar = daily[i + 1]
    stop = entry_bar.o - stop_atr_mult * atr20
    target = entry_bar.o + target_atr_mult * atr20
    if stop <= 0 or target <= entry_bar.o:
        return None
    return Candidate(
        ticker=ticker,
        snapshot_day=daily[i].day,
        entry_day=entry_bar.day,
        entry_price=entry_bar.o,
        stop_price=stop,
        target_price=target,
        score=score,
        atr20_pct=atr20 / entry_bar.o * 100.0,
        momentum20_pct=mom20 * 100.0,
        momentum60_pct=mom60 * 100.0,
        pullback60_pct=pullback60 * 100.0,
        base_score=score,
        overlay_score=0.0,
    )


def _regime_stats_for_snapshot(daily_map: dict[str, list[DailyBar]], month: str, lookback_days: int) -> RegimeStats | None:
    total = 0
    above_sma = 0
    positive_mom = 0
    mom_vals: list[float] = []
    for daily in daily_map.values():
        snapshots = _monthly_snapshot_idx(daily)
        idx = next((i for i in snapshots if daily[i].day[:7] == month), None)
        if idx is None:
            continue
        hist_need = max(lookback_days + 5, 25)
        if idx < hist_need:
            continue
        closes = [x.c for x in daily[: idx + 1]]
        close = closes[-1]
        sma60 = _sma(closes, lookback_days)
        if not (math.isfinite(sma60) and close > 0):
            continue
        mom60 = close / closes[-lookback_days] - 1.0
        total += 1
        if close > sma60:
            above_sma += 1
        if mom60 > 0:
            positive_mom += 1
        mom_vals.append(mom60 * 100.0)
    if total <= 0:
        return None
    return RegimeStats(
        breadth_above_sma_pct=100.0 * above_sma / float(total),
        breadth_positive_mom_pct=100.0 * positive_mom / float(total),
        avg_mom60_pct=sum(mom_vals) / float(len(mom_vals) or 1),
    )


def _benchmark_stats_for_snapshot(
    benchmark_map: dict[str, list[DailyBar]],
    month: str,
    lookback_days: int,
) -> BenchmarkStats | None:
    total = 0
    above_sma = 0
    positive_mom = 0
    mom_vals: list[float] = []
    for daily in benchmark_map.values():
        snapshots = _monthly_snapshot_idx(daily)
        idx = next((i for i in snapshots if daily[i].day[:7] == month), None)
        hist_need = max(lookback_days + 5, 25)
        if idx is None or idx < hist_need:
            continue
        closes = [x.c for x in daily[: idx + 1]]
        close = closes[-1]
        sma60 = _sma(closes, lookback_days)
        if not (math.isfinite(sma60) and close > 0):
            continue
        mom60 = close / closes[-lookback_days] - 1.0
        total += 1
        if close > sma60:
            above_sma += 1
        if mom60 > 0:
            positive_mom += 1
        mom_vals.append(mom60 * 100.0)
    if total <= 0:
        return None
    return BenchmarkStats(
        total=total,
        above_sma_count=above_sma,
        positive_mom_count=positive_mom,
        avg_mom60_pct=sum(mom_vals) / float(len(mom_vals) or 1),
    )


def _simulate_trades_portfolio_stop(
    picks_info: list[tuple["Candidate", int, list["DailyBar"]]],
    weights: list[float],
    max_hold_days: int,
    portfolio_stop_pct: float,
) -> list[tuple[int, float, str]]:
    """
    Simulate N concurrent trades with a portfolio-level intramonth stop.

    If the weighted-average portfolio drawdown from month-start reaches
    `portfolio_stop_pct` (e.g. 0.04 = 4%), all remaining positions are
    force-closed at that day's close ('portfolio_stop').

    Falls back to independent simulation when portfolio_stop_pct <= 0.
    """
    n = len(picks_info)
    if n == 0:
        return []

    # Independent results (used when portfolio_stop disabled or as fallback)
    indep_results: list[tuple[int, float, str]] = []
    for cand, entry_idx, daily in picks_info:
        indep_results.append(
            _simulate_trade(daily, entry_idx, cand.stop_price, cand.target_price, max_hold_days)
        )
    if portfolio_stop_pct <= 0.0:
        return indep_results

    total_weight = sum(max(0.0, w) for w in weights)
    if total_weight <= 0.0:
        total_weight = float(n)

    # Day range: first entry → last possible exit
    first_entry = min(entry_idx for _, entry_idx, _ in picks_info)
    last_exit_bound = max(entry_idx + max_hold_days for _, entry_idx, _ in picks_info)

    exit_results: list[tuple[int, float, str] | None] = [None] * n
    active = [True] * n
    entry_prices = [cand.entry_price for cand, _, _ in picks_info]

    for day_i in range(first_entry, last_exit_bound + 1):
        # --- 1. resolve individual SL/TP/time for each active trade this day ---
        for i, (cand, entry_idx, daily) in enumerate(picks_info):
            if not active[i] or exit_results[i] is not None:
                continue
            if day_i < entry_idx:
                continue  # not yet entered
            if day_i >= len(daily):
                exit_results[i] = (len(daily) - 1, daily[-1].c, "time")
                active[i] = False
                continue
            if day_i > entry_idx + max_hold_days:
                exit_results[i] = (day_i - 1, daily[day_i - 1].c, "time")
                active[i] = False
                continue
            bar = daily[day_i]
            if bar.l <= cand.stop_price:
                exit_results[i] = (day_i, cand.stop_price, "stop")
                active[i] = False
            elif bar.h >= cand.target_price:
                exit_results[i] = (day_i, cand.target_price, "target")
                active[i] = False

        if not any(active):
            break

        # --- 2. compute current portfolio return (mix of closed + open MTM) ---
        port_ret = 0.0
        for i, (cand, entry_idx, daily) in enumerate(picks_info):
            w = max(0.0, weights[i]) / total_weight
            if exit_results[i] is not None:
                # already closed
                ret = exit_results[i][1] / entry_prices[i] - 1.0
            elif day_i < entry_idx or day_i >= len(daily):
                ret = 0.0
            else:
                ret = daily[day_i].c / entry_prices[i] - 1.0
            port_ret += ret * w

        # --- 3. portfolio stop triggered? close remaining open positions ---
        if port_ret <= -portfolio_stop_pct:
            for i, (cand, entry_idx, daily) in enumerate(picks_info):
                if active[i] and exit_results[i] is None:
                    close_idx = min(day_i, len(daily) - 1)
                    exit_results[i] = (close_idx, daily[close_idx].c, "portfolio_stop")
                    active[i] = False
            break

    # fill any positions that never got an exit (edge case)
    for i, (cand, entry_idx, daily) in enumerate(picks_info):
        if exit_results[i] is None:
            last = min(entry_idx + max_hold_days, len(daily) - 1)
            exit_results[i] = (last, daily[last].c, "time")

    return exit_results  # type: ignore[return-value]


def _simulate_trade(daily: list[DailyBar], entry_idx: int, stop: float, target: float, max_hold_days: int) -> tuple[int, float, str]:
    last_idx = min(len(daily) - 1, entry_idx + max_hold_days)
    for i in range(entry_idx, last_idx + 1):
        bar = daily[i]
        # Conservative same-day ordering: stop first if both touched.
        if bar.l <= stop:
            return i, stop, "stop"
        if bar.h >= target:
            return i, target, "target"
    return last_idx, daily[last_idx].c, "time"


def main() -> int:
    ap = argparse.ArgumentParser(description="Point-in-time monthly equities research simulator")
    ap.add_argument("--tickers", default="AAPL,MSFT,NVDA,AMZN,META,TSLA,GOOGL,AMD,JPM,XOM")
    ap.add_argument("--data-dir", default="data_cache/equities")
    ap.add_argument("--top-n", type=int, default=3)
    ap.add_argument("--max-hold-days", type=int, default=20)
    ap.add_argument("--lookback-days", type=int, default=40)
    ap.add_argument("--min-mom-lookback-pct", type=float, default=2.0)
    ap.add_argument("--pullback-min-pct", type=float, default=-18.0)
    ap.add_argument("--pullback-max-pct", type=float, default=-0.5)
    ap.add_argument("--regime-min-breadth-sma-pct", type=float, default=0.0)
    ap.add_argument("--regime-min-breadth-mom-pct", type=float, default=0.0)
    ap.add_argument("--regime-min-avg-mom-pct", type=float, default=-999.0)
    ap.add_argument("--earnings-csv", default="")
    ap.add_argument("--earnings-blackout-days-before", type=int, default=0)
    ap.add_argument("--earnings-blackout-days-after", type=int, default=0)
    ap.add_argument("--benchmark-tickers", default="")
    ap.add_argument("--benchmark-data-dir", default="")
    ap.add_argument("--benchmark-lookback-days", type=int, default=60)
    ap.add_argument("--benchmark-min-above-sma-count", type=int, default=0)
    ap.add_argument("--benchmark-min-positive-mom-count", type=int, default=0)
    ap.add_argument("--benchmark-min-avg-mom-pct", type=float, default=-999.0)
    ap.add_argument("--forbid-pairs", default="")
    ap.add_argument("--cluster-groups", default="")
    ap.add_argument("--max-per-cluster", type=int, default=999)
    ap.add_argument("--corr-lookback-days", type=int, default=0)
    ap.add_argument("--max-pair-corr", type=float, default=2.0)
    ap.add_argument("--corr-penalty-mult", type=float, default=0.0)
    ap.add_argument("--corr-penalty-threshold", type=float, default=0.0)
    ap.add_argument("--universe-top-k", type=int, default=0)
    ap.add_argument("--universe-score-lookback-days", type=int, default=80)
    ap.add_argument("--stop-atr-mult", type=float, default=1.5)
    ap.add_argument("--target-atr-mult", type=float, default=2.5)
    ap.add_argument("--position-weight-mode", default="equal")
    ap.add_argument("--overlay-csv", default="")
    ap.add_argument("--overlay-score-mult", type=float, default=0.0)
    ap.add_argument("--intramonth-portfolio-stop-pct", type=float, default=0.0,
                    help="If >0: exit ALL positions when portfolio drops this %% from month-start. "
                         "E.g. 0.04 = exit everything if portfolio down 4%% in the month. "
                         "Reduces red-month severity at cost of some missed recoveries.")
    ap.add_argument("--tag", default="equities_monthly_research")
    args = ap.parse_args()

    tickers = [x.strip().upper() for x in args.tickers.split(",") if x.strip()]
    data_dir = Path(args.data_dir)
    daily_map: dict[str, list[DailyBar]] = {}
    for ticker in tickers:
        csv_path = data_dir / f"{ticker}_M5.csv"
        if csv_path.exists():
            daily_map[ticker] = _aggregate_daily(csv_path)
    benchmark_map: dict[str, list[DailyBar]] = {}
    benchmark_tickers = [x.strip().upper() for x in args.benchmark_tickers.split(",") if x.strip()]
    benchmark_data_dir = Path(args.benchmark_data_dir) if args.benchmark_data_dir else data_dir
    for ticker in benchmark_tickers:
        csv_path = benchmark_data_dir / f"{ticker}_M5.csv"
        if csv_path.exists():
            benchmark_map[ticker] = _aggregate_daily(csv_path)
    earnings_blackouts = _load_earnings_blackouts(
        str(args.earnings_csv),
        int(args.earnings_blackout_days_before),
        int(args.earnings_blackout_days_after),
    )
    overlay_scores = _load_overlay_scores(str(args.overlay_csv))
    forbid_pairs = _parse_forbid_pairs(args.forbid_pairs)
    cluster_groups = _parse_cluster_groups(args.cluster_groups)

    out_dir = ROOT / "backtest_runs" / f"equities_monthly_research_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{args.tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    trades_rows: list[list[str]] = []
    monthly_rows: list[list[str]] = []
    picks_rows: list[list[str]] = []
    monthly_equity = 1.0
    monthly_curve: list[float] = [monthly_equity]

    month_keys = sorted({bar.day[:7] for rows in daily_map.values() for bar in rows})
    for month in month_keys:
        benchmark = _benchmark_stats_for_snapshot(
            benchmark_map,
            month,
            int(args.benchmark_lookback_days),
        ) if benchmark_map else None
        if benchmark is not None:
            if benchmark.above_sma_count < int(args.benchmark_min_above_sma_count):
                continue
            if benchmark.positive_mom_count < int(args.benchmark_min_positive_mom_count):
                continue
            if benchmark.avg_mom60_pct < float(args.benchmark_min_avg_mom_pct):
                continue
        regime = _regime_stats_for_snapshot(daily_map, month, int(args.lookback_days))
        if regime is not None:
            if regime.breadth_above_sma_pct < float(args.regime_min_breadth_sma_pct):
                continue
            if regime.breadth_positive_mom_pct < float(args.regime_min_breadth_mom_pct):
                continue
            if regime.avg_mom60_pct < float(args.regime_min_avg_mom_pct):
                continue
        snapshot_meta: dict[str, tuple[int, list[DailyBar]]] = {}
        universe_scores: dict[str, float] = {}
        for ticker, daily in daily_map.items():
            snapshots = _monthly_snapshot_idx(daily)
            idx = next((i for i in snapshots if daily[i].day[:7] == month), None)
            if idx is None:
                continue
            snapshot_meta[ticker] = (idx, daily)
            universe_scores[ticker] = _universe_health_score(
                daily,
                idx,
                int(args.universe_score_lookback_days),
            )
        allowed_universe: set[str] | None = None
        if int(args.universe_top_k) > 0:
            scored = [(ticker, score) for ticker, score in universe_scores.items() if math.isfinite(score)]
            scored.sort(key=lambda x: x[1], reverse=True)
            allowed_universe = {ticker for ticker, _ in scored[: max(1, int(args.universe_top_k))]}
        candidates: list[tuple[Candidate, int, list[DailyBar]]] = []
        for ticker, daily in daily_map.items():
            if allowed_universe is not None and ticker not in allowed_universe:
                continue
            meta = snapshot_meta.get(ticker)
            if meta is None:
                continue
            idx, daily = meta
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
            if cand.entry_day in earnings_blackouts.get(ticker, set()):
                continue
            cand.overlay_score = _overlay_score_for_snapshot(overlay_scores, cand.snapshot_day, ticker)
            if float(args.overlay_score_mult) != 0.0 and cand.overlay_score != 0.0:
                cand.score = float(cand.base_score) + float(args.overlay_score_mult) * float(cand.overlay_score)
            cand.universe_score = universe_scores.get(ticker, float("nan"))
            candidates.append((cand, idx + 1, daily))
        picks: list[tuple[Candidate, int, list[DailyBar]]] = []
        cluster_counts: dict[int, int] = defaultdict(int)
        corr_cache: dict[tuple[str, str], float | None] = {}
        remaining = sorted(candidates, key=lambda x: x[0].score, reverse=True)

        def _cached_pair_corr(
            left: tuple[Candidate, int, list[DailyBar]],
            right: tuple[Candidate, int, list[DailyBar]],
        ) -> float | None:
            if int(args.corr_lookback_days) <= 0:
                return None
            key = tuple(sorted((left[0].ticker, right[0].ticker)))
            if key not in corr_cache:
                corr_cache[key] = _pair_corr(
                    left[2],
                    left[1] - 1,
                    right[2],
                    right[1] - 1,
                    int(args.corr_lookback_days),
                )
            return corr_cache[key]

        # Greedy diversification-aware selection: keep the strongest setup first,
        # then penalize follow-on picks that crowd the same correlation bucket.
        while remaining and len(picks) < max(1, int(args.top_n)):
            best_idx: int | None = None
            best_selection_score = float("-inf")
            best_penalty = 0.0
            best_max_corr = float("nan")

            for idx, cand_triplet in enumerate(remaining):
                cand = cand_triplet[0]
                blocked = False
                cand_clusters = _clusters_for_ticker(cand.ticker, cluster_groups)
                if int(args.max_per_cluster) > 0:
                    for cluster_id in cand_clusters:
                        if cluster_counts.get(cluster_id, 0) >= int(args.max_per_cluster):
                            blocked = True
                            break
                if blocked:
                    continue

                total_corr_penalty = 0.0
                max_corr_existing = float("nan")
                for existing_triplet in picks:
                    existing = existing_triplet[0]
                    if tuple(sorted((cand.ticker, existing.ticker))) in forbid_pairs:
                        blocked = True
                        break
                    corr = _cached_pair_corr(cand_triplet, existing_triplet)
                    if corr is None:
                        continue
                    if not math.isfinite(max_corr_existing) or corr > max_corr_existing:
                        max_corr_existing = corr
                    if float(args.max_pair_corr) <= 1.0 and corr >= float(args.max_pair_corr):
                        blocked = True
                        break
                    total_corr_penalty += max(0.0, corr - float(args.corr_penalty_threshold))
                if blocked:
                    continue

                selection_score = cand.score - float(args.corr_penalty_mult) * total_corr_penalty
                if (
                    best_idx is None
                    or selection_score > best_selection_score
                    or (
                        math.isclose(selection_score, best_selection_score)
                        and cand.score > remaining[best_idx][0].score
                    )
                ):
                    best_idx = idx
                    best_selection_score = selection_score
                    best_penalty = total_corr_penalty
                    best_max_corr = max_corr_existing

            if best_idx is None:
                break

            picked = remaining.pop(best_idx)
            picked_cand = picked[0]
            picked_cand.selection_score = best_selection_score
            picked_cand.corr_penalty = best_penalty
            picked_cand.max_corr_to_existing = best_max_corr
            picks.append(picked)
            for cluster_id in _clusters_for_ticker(picked_cand.ticker, cluster_groups):
                cluster_counts[cluster_id] += 1
        if not picks:
            continue

        month_returns: list[float] = []
        month_weights: list[float] = []
        pick_labels: list[str] = []
        # ── simulate trades (with optional portfolio-level intramonth stop) ──
        pick_weights_raw = [_position_weight(cand, args.position_weight_mode) for cand, _, _ in picks]
        portfolio_stop = float(args.intramonth_portfolio_stop_pct)
        sim_results = _simulate_trades_portfolio_stop(picks, pick_weights_raw, int(args.max_hold_days), portfolio_stop)

        for (cand, entry_idx, daily), weight, (exit_idx, exit_price, reason) in zip(picks, pick_weights_raw, sim_results):
            picks_rows.append(
                [
                    month,
                    cand.ticker,
                    cand.entry_day,
                    f"{cand.base_score:.6f}" if math.isfinite(cand.base_score) else "",
                    f"{cand.overlay_score:.6f}",
                    f"{cand.score:.6f}",
                    f"{cand.atr20_pct:.3f}",
                    f"{cand.momentum20_pct:.3f}",
                    f"{cand.momentum60_pct:.3f}",
                    f"{cand.pullback60_pct:.3f}",
                    f"{cand.universe_score:.6f}" if math.isfinite(cand.universe_score) else "",
                    f"{cand.selection_score:.6f}" if math.isfinite(cand.selection_score) else "",
                    f"{cand.corr_penalty:.6f}",
                    f"{cand.max_corr_to_existing:.6f}" if math.isfinite(cand.max_corr_to_existing) else "",
                    f"{cand.entry_price:.4f}",
                    f"{cand.stop_price:.4f}",
                    f"{cand.target_price:.4f}",
                    f"{weight:.6f}",
                ]
            )
            ret = exit_price / cand.entry_price - 1.0
            month_returns.append(ret)
            month_weights.append(weight)
            pick_labels.append(cand.ticker)
            exit_day_str = daily[exit_idx].day if exit_idx < len(daily) else daily[-1].day
            trades_rows.append(
                [
                    cand.snapshot_day,
                    cand.ticker,
                    cand.entry_day,
                    exit_day_str,
                    f"{cand.entry_price:.4f}",
                    f"{exit_price:.4f}",
                    f"{cand.stop_price:.4f}",
                    f"{cand.target_price:.4f}",
                    f"{cand.base_score:.6f}" if math.isfinite(cand.base_score) else "",
                    f"{cand.overlay_score:.6f}",
                    f"{cand.score:.6f}",
                    f"{cand.momentum20_pct:.3f}",
                    f"{cand.momentum60_pct:.3f}",
                    f"{cand.pullback60_pct:.3f}",
                    f"{cand.universe_score:.6f}" if math.isfinite(cand.universe_score) else "",
                    f"{cand.selection_score:.6f}" if math.isfinite(cand.selection_score) else "",
                    f"{cand.corr_penalty:.6f}",
                    f"{cand.max_corr_to_existing:.6f}" if math.isfinite(cand.max_corr_to_existing) else "",
                    f"{weight:.6f}",
                    f"{ret * 100.0:.4f}",
                    reason,
                ]
            )

        total_weight = sum(max(0.0, x) for x in month_weights)
        if total_weight <= 0:
            month_ret = sum(month_returns) / max(1, len(month_returns))
        else:
            month_ret = sum(ret * max(0.0, w) for ret, w in zip(month_returns, month_weights)) / total_weight
        monthly_equity *= 1.0 + month_ret
        monthly_curve.append(monthly_equity)
        monthly_rows.append([month, ",".join(pick_labels), str(len(month_returns)), f"{month_ret * 100.0:.4f}", f"{monthly_equity * 100.0:.4f}"])

    trades_csv = out_dir / "trades.csv"
    with trades_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "snapshot_month_end",
                "ticker",
                "entry_day",
                "exit_day",
                "entry_price",
                "exit_price",
                "stop_price",
                "target_price",
                "base_score",
                "overlay_score",
                "score",
                "momentum20_pct",
                "momentum60_pct",
                "pullback60_pct",
                "universe_score",
                "selection_score",
                "corr_penalty",
                "max_corr_to_existing",
                "weight",
                "return_pct",
                "reason",
            ]
        )
        w.writerows(trades_rows)

    monthly_csv = out_dir / "monthly.csv"
    with monthly_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["month", "tickers", "positions", "month_return_pct", "equity_index"])
        w.writerows(monthly_rows)

    picks_csv = out_dir / "picks.csv"
    with picks_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "month",
                "ticker",
                "entry_day",
                "base_score",
                "overlay_score",
                "score",
                "atr20_pct",
                "momentum20_pct",
                "momentum60_pct",
                "pullback60_pct",
                "universe_score",
                "selection_score",
                "corr_penalty",
                "max_corr_to_existing",
                "entry_price",
                "stop_price",
                "target_price",
                "weight",
            ]
        )
        w.writerows(picks_rows)

    returns = [float(r[-2]) for r in trades_rows]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    sum_wins = sum(wins) if wins else 0.0
    sum_losses = abs(sum(losses)) if losses else 0.0
    profit_factor_val = (sum_wins / sum_losses) if sum_losses > 0 else float("nan")
    month_returns_pct = [float(r[3]) for r in monthly_rows]
    active_months = len(monthly_rows)
    calendar_months = len(month_keys)
    inactive_months = max(0, calendar_months - active_months)
    positive_months = [x for x in month_returns_pct if x > 0]
    negative_months = [x for x in month_returns_pct if x < 0]
    max_eq = monthly_curve[0]
    max_dd = 0.0
    for eq in monthly_curve:
        max_eq = max(max_eq, eq)
        max_dd = min(max_dd, eq / max_eq - 1.0)

    summary_csv = out_dir / "summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "months",
                "calendar_months",
                "inactive_months",
                "trades",
                "winrate_pct",
                "avg_trade_return_pct",
                "profit_factor",
                "positive_months",
                "negative_months",
                "positive_months_pct",
                "avg_month_return_pct",
                "compounded_return_pct",
                "max_monthly_dd_pct",
                "intramonth_portfolio_stop_pct",
                "tickers",
                "top_n",
                "max_hold_days",
                "lookback_days",
                "benchmark_tickers",
                "forbid_pairs",
                "cluster_groups",
                "max_per_cluster",
                "corr_lookback_days",
                "max_pair_corr",
                "corr_penalty_mult",
                "corr_penalty_threshold",
                "universe_top_k",
                "universe_score_lookback_days",
                "position_weight_mode",
                "overlay_csv",
                "overlay_score_mult",
            ]
        )
        w.writerow(
            [
                len(monthly_rows),
                calendar_months,
                inactive_months,
                len(trades_rows),
                f"{(100.0 * len(wins) / max(1, len(returns))):.2f}",
                f"{(sum(returns) / max(1, len(returns))):.4f}",
                f"{profit_factor_val:.4f}" if math.isfinite(profit_factor_val) else "nan",
                len(positive_months),
                len(negative_months),
                f"{(100.0 * len(positive_months) / max(1, len(month_returns_pct))):.2f}",
                f"{(sum(month_returns_pct) / max(1, len(month_returns_pct))):.4f}",
                f"{(monthly_equity - 1.0) * 100.0:.4f}",
                f"{max_dd * 100.0:.4f}",
                f"{float(args.intramonth_portfolio_stop_pct):.4f}",
                ";".join(tickers),
                int(args.top_n),
                int(args.max_hold_days),
                int(args.lookback_days),
                ";".join(benchmark_tickers),
                args.forbid_pairs,
                args.cluster_groups,
                int(args.max_per_cluster),
                int(args.corr_lookback_days),
                float(args.max_pair_corr),
                float(args.corr_penalty_mult),
                float(args.corr_penalty_threshold),
                int(args.universe_top_k),
                int(args.universe_score_lookback_days),
                args.position_weight_mode,
                str(args.overlay_csv),
                float(args.overlay_score_mult),
            ]
        )

    print(f"saved={out_dir}")
    print(summary_csv.read_text(encoding='utf-8').strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
