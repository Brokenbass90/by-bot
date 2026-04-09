#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
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
    entry_day: str
    score: float
    atr20_pct: float
    momentum20_pct: float
    momentum60_pct: float
    pullback60_pct: float
    universe_score: float
    selection_score: float = float("nan")
    corr_penalty: float = 0.0
    max_corr_to_existing: float = float("nan")
    entry_price: float = float("nan")
    stop_price: float = float("nan")
    target_price: float = float("nan")
    weight: float = 0.0


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


def _pair_corr(daily_a: list[DailyBar], daily_b: list[DailyBar], lookback_days: int) -> float | None:
    end_idx_a = len(daily_a) - 1
    end_idx_b = len(daily_b) - 1
    ra = _daily_returns_window(daily_a, end_idx_a, lookback_days)
    rb = _daily_returns_window(daily_b, end_idx_b, lookback_days)
    overlap = sorted(set(ra).intersection(rb))
    if len(overlap) < max(10, lookback_days // 3):
        return None
    xs = [ra[d] for d in overlap]
    ys = [rb[d] for d in overlap]
    return _pearson_corr(xs, ys)


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


def _universe_health_score(daily: list[DailyBar], lookback_days: int) -> float:
    i = len(daily) - 1
    if i < max(20, lookback_days):
        return float("nan")
    closes = [x.c for x in daily]
    close = closes[-1]
    if close <= 0:
        return float("nan")
    start_close = daily[i - lookback_days].c
    if start_close <= 0:
        return float("nan")
    mom = close / start_close - 1.0
    high = max(x.h for x in daily[i - lookback_days + 1 : i + 1])
    dd_from_high = close / max(1e-12, high) - 1.0
    rets = []
    start_idx = max(1, i - lookback_days + 1)
    for j in range(start_idx, i + 1):
        prev = daily[j - 1].c
        cur = daily[j].c
        if prev <= 0:
            continue
        rets.append(cur / prev - 1.0)
    vol = pstdev(rets) if len(rets) >= 5 else 0.0
    return 1.35 * mom - 0.90 * abs(min(0.0, dd_from_high)) - 2.20 * vol


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


def _candidate_latest(
    ticker: str,
    daily: list[DailyBar],
    *,
    lookback_days: int,
    min_mom60: float,
    pullback_min: float,
    pullback_max: float,
    stop_atr_mult: float,
    target_atr_mult: float,
    universe_score: float,
) -> tuple[Candidate | None, str]:
    hist_need = max(lookback_days + 5, 25)
    if len(daily) < hist_need:
        return None, "history_short"
    closes = [x.c for x in daily]
    close = closes[-1]
    sma20 = _sma(closes, 20)
    sma60 = _sma(closes, lookback_days)
    if not (math.isfinite(sma20) and math.isfinite(sma60) and close > 0):
        return None, "sma_invalid"
    mom20 = close / closes[-20] - 1.0
    mom60 = close / closes[-lookback_days] - 1.0
    high60 = max(x.h for x in daily[-lookback_days:])
    pullback60 = close / high60 - 1.0
    rets20 = []
    for j in range(len(daily) - 20, len(daily)):
        if j <= 0:
            continue
        rets20.append(daily[j].c / daily[j - 1].c - 1.0)
    vol20 = pstdev(rets20) if len(rets20) >= 5 else 0.0
    atr20 = _atr(daily, 20)
    if not math.isfinite(atr20) or atr20 <= 0:
        return None, "atr_invalid"
    if close < sma60:
        return None, "below_sma60"
    if mom60 <= min_mom60:
        return None, "mom60_low"
    if not (pullback_min <= pullback60 <= pullback_max):
        return None, "pullback_outside"

    score = (
        1.20 * mom60
        + 0.60 * mom20
        - 0.35 * abs(pullback60)
        - 2.50 * vol20
        + (0.02 if close > sma20 else -0.02)
    )
    stop = close - stop_atr_mult * atr20
    target = close + target_atr_mult * atr20
    if stop <= 0 or target <= close:
        return None, "stop_target_invalid"
    return Candidate(
        ticker=ticker,
        entry_day=daily[-1].day,
        score=score,
        atr20_pct=atr20 / close * 100.0,
        momentum20_pct=mom20 * 100.0,
        momentum60_pct=mom60 * 100.0,
        pullback60_pct=pullback60 * 100.0,
        universe_score=universe_score,
        entry_price=close,
        stop_price=stop,
        target_price=target,
    ), "ok"


def main() -> int:
    ap = argparse.ArgumentParser(description="Build live/current-cycle equities picks from latest cached data")
    ap.add_argument("--tickers", required=True)
    ap.add_argument("--data-dir", default="data_cache/equities_1h")
    ap.add_argument("--top-n", type=int, default=3)
    ap.add_argument("--lookback-days", type=int, default=28)
    ap.add_argument("--min-mom-lookback-pct", type=float, default=2.5)
    ap.add_argument("--pullback-min-pct", type=float, default=-12.0)
    ap.add_argument("--pullback-max-pct", type=float, default=-1.5)
    ap.add_argument("--benchmark-tickers", default="")
    ap.add_argument("--benchmark-data-dir", default="")
    ap.add_argument("--benchmark-lookback-days", type=int, default=60)
    ap.add_argument("--benchmark-min-above-sma-count", type=int, default=0)
    ap.add_argument("--benchmark-min-positive-mom-count", type=int, default=0)
    ap.add_argument("--benchmark-min-avg-mom-pct", type=float, default=-999.0)
    ap.add_argument("--corr-lookback-days", type=int, default=60)
    ap.add_argument("--max-pair-corr", type=float, default=2.0)
    ap.add_argument("--corr-penalty-mult", type=float, default=0.0)
    ap.add_argument("--corr-penalty-threshold", type=float, default=0.0)
    ap.add_argument("--universe-top-k", type=int, default=0)
    ap.add_argument("--universe-score-lookback-days", type=int, default=80)
    ap.add_argument("--position-weight-mode", default="score_inv_vol")
    ap.add_argument("--cluster-groups", default="")
    ap.add_argument("--max-per-cluster", type=int, default=999)
    ap.add_argument("--stop-atr-mult", type=float, default=1.7)
    ap.add_argument("--target-atr-mult", type=float, default=4.0)
    ap.add_argument("--out-picks-csv", required=True)
    ap.add_argument("--out-summary-csv", required=True)
    args = ap.parse_args()

    tickers = [x.strip().upper() for x in args.tickers.split(",") if x.strip()]
    data_dir = ROOT / args.data_dir if not Path(args.data_dir).is_absolute() else Path(args.data_dir)
    benchmark_data_dir = Path(args.benchmark_data_dir) if args.benchmark_data_dir else data_dir
    daily_map: dict[str, list[DailyBar]] = {}
    for ticker in tickers:
        csv_path = data_dir / f"{ticker}_M5.csv"
        if csv_path.exists():
            daily_map[ticker] = _aggregate_daily(csv_path)

    benchmark_map: dict[str, list[DailyBar]] = {}
    benchmark_tickers = [x.strip().upper() for x in args.benchmark_tickers.split(",") if x.strip()]
    for ticker in benchmark_tickers:
        csv_path = benchmark_data_dir / f"{ticker}_M5.csv"
        if csv_path.exists():
            benchmark_map[ticker] = _aggregate_daily(csv_path)

    if benchmark_map:
        total = 0
        above_sma = 0
        positive_mom = 0
        mom_vals: list[float] = []
        for daily in benchmark_map.values():
            if len(daily) < max(25, int(args.benchmark_lookback_days) + 5):
                continue
            closes = [x.c for x in daily]
            close = closes[-1]
            sma = _sma(closes, int(args.benchmark_lookback_days))
            if not (math.isfinite(sma) and close > 0):
                continue
            mom = close / closes[-int(args.benchmark_lookback_days)] - 1.0
            total += 1
            if close > sma:
                above_sma += 1
            if mom > 0:
                positive_mom += 1
            mom_vals.append(mom * 100.0)
        avg_mom = sum(mom_vals) / float(len(mom_vals) or 1)
        if total <= 0:
            raise SystemExit("benchmark data unavailable")
        if above_sma < int(args.benchmark_min_above_sma_count):
            raise SystemExit("benchmark gate: above_sma_count")
        if positive_mom < int(args.benchmark_min_positive_mom_count):
            raise SystemExit("benchmark gate: positive_mom_count")
        if avg_mom < float(args.benchmark_min_avg_mom_pct):
            raise SystemExit("benchmark gate: avg_mom")

    universe_scores: dict[str, float] = {}
    for ticker, daily in daily_map.items():
        universe_scores[ticker] = _universe_health_score(daily, int(args.universe_score_lookback_days))

    allowed_universe: set[str] | None = None
    if int(args.universe_top_k) > 0:
        scored = [(ticker, score) for ticker, score in universe_scores.items() if math.isfinite(score)]
        scored.sort(key=lambda x: x[1], reverse=True)
        allowed_universe = {ticker for ticker, _ in scored[: max(1, int(args.universe_top_k))]}

    candidates: list[tuple[Candidate, list[DailyBar]]] = []
    reject_counts: Counter[str] = Counter()
    for ticker, daily in daily_map.items():
        if allowed_universe is not None and ticker not in allowed_universe:
            reject_counts["outside_universe_top_k"] += 1
            continue
        cand, reason = _candidate_latest(
            ticker,
            daily,
            lookback_days=int(args.lookback_days),
            min_mom60=float(args.min_mom_lookback_pct) / 100.0,
            pullback_min=float(args.pullback_min_pct) / 100.0,
            pullback_max=float(args.pullback_max_pct) / 100.0,
            stop_atr_mult=float(args.stop_atr_mult),
            target_atr_mult=float(args.target_atr_mult),
            universe_score=universe_scores.get(ticker, float("nan")),
        )
        if cand is not None:
            candidates.append((cand, daily))
        else:
            reject_counts[str(reason or "unknown")] += 1

    clusters = _parse_cluster_groups(args.cluster_groups)
    corr_cache: dict[tuple[str, str], float | None] = {}
    picks: list[tuple[Candidate, list[DailyBar]]] = []
    cluster_counts: dict[int, int] = defaultdict(int)
    remaining = sorted(candidates, key=lambda x: x[0].score, reverse=True)

    def _cached_pair_corr(left: tuple[Candidate, list[DailyBar]], right: tuple[Candidate, list[DailyBar]]) -> float | None:
        key = tuple(sorted((left[0].ticker, right[0].ticker)))
        if key not in corr_cache:
            corr_cache[key] = _pair_corr(left[1], right[1], int(args.corr_lookback_days))
        return corr_cache[key]

    selection_rejects: Counter[str] = Counter()
    while remaining and len(picks) < max(1, int(args.top_n)):
        best_idx = None
        best_selection_score = float("-inf")
        best_penalty = 0.0
        best_max_corr = float("nan")
        for idx, cand_triplet in enumerate(remaining):
            cand = cand_triplet[0]
            blocked = False
            for cluster_id in _clusters_for_ticker(cand.ticker, clusters):
                if cluster_counts.get(cluster_id, 0) >= int(args.max_per_cluster):
                    selection_rejects["cluster_limit"] += 1
                    blocked = True
                    break
            if blocked:
                continue
            total_corr_penalty = 0.0
            max_corr_existing = float("nan")
            for existing_triplet in picks:
                corr = _cached_pair_corr(cand_triplet, existing_triplet)
                if corr is None:
                    continue
                if not math.isfinite(max_corr_existing) or corr > max_corr_existing:
                    max_corr_existing = corr
                if float(args.max_pair_corr) <= 1.0 and corr >= float(args.max_pair_corr):
                    selection_rejects["pair_corr_block"] += 1
                    blocked = True
                    break
                total_corr_penalty += max(0.0, corr - float(args.corr_penalty_threshold))
            if blocked:
                continue
            selection_score = cand.score - float(args.corr_penalty_mult) * total_corr_penalty
            if best_idx is None or selection_score > best_selection_score:
                best_idx = idx
                best_selection_score = selection_score
                best_penalty = total_corr_penalty
                best_max_corr = max_corr_existing
        if best_idx is None:
            break
        picked = remaining.pop(best_idx)
        picked[0].selection_score = best_selection_score
        picked[0].corr_penalty = best_penalty
        picked[0].max_corr_to_existing = best_max_corr
        picks.append(picked)
        for cluster_id in _clusters_for_ticker(picked[0].ticker, clusters):
            cluster_counts[cluster_id] += 1

    if not picks:
        if reject_counts:
            print("reject_counts=" + ",".join(f"{k}:{v}" for k, v in reject_counts.most_common(8)))
        if candidates:
            print(f"candidate_count={len(candidates)}")
        if selection_rejects:
            print("selection_rejects=" + ",".join(f"{k}:{v}" for k, v in selection_rejects.most_common(8)))
        raise SystemExit("no current-cycle picks")

    weights = [_position_weight(cand, args.position_weight_mode) for cand, _ in picks]
    out_picks = Path(args.out_picks_csv) if Path(args.out_picks_csv).is_absolute() else ROOT / args.out_picks_csv
    out_summary = Path(args.out_summary_csv) if Path(args.out_summary_csv).is_absolute() else ROOT / args.out_summary_csv
    out_picks.parent.mkdir(parents=True, exist_ok=True)
    out_summary.parent.mkdir(parents=True, exist_ok=True)

    latest_day = max(cand.entry_day for cand, _ in picks)
    month_label = latest_day[:7]

    with out_picks.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
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
        ])
        for (cand, _), weight in zip(picks, weights):
            cand.weight = float(weight)
            w.writerow([
                month_label,
                cand.ticker,
                cand.entry_day,
                f"{cand.score:.6f}",
                "0.000000",
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
            ])

    with out_summary.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "mode",
            "selected",
            "latest_pick_month",
            "latest_entry_day",
            "latest_entry_age_days",
            "tickers",
            "top_n",
            "lookback_days",
            "benchmark_tickers",
            "max_pair_corr",
            "position_weight_mode",
        ])
        w.writerow([
            "current_cycle",
            len(picks),
            month_label,
            latest_day,
            0,
            ";".join(cand.ticker for cand, _ in picks),
            int(args.top_n),
            int(args.lookback_days),
            args.benchmark_tickers.replace(",", ";"),
            float(args.max_pair_corr),
            args.position_weight_mode,
        ])

    print(f"saved_picks={out_picks}")
    print(f"saved_summary={out_summary}")
    print("symbols=" + ",".join(cand.ticker for cand, _ in picks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
