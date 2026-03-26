#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import pstdev
from typing import Iterable

import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex.data import load_m5_csv


def _aggregate_daily(csv_path: Path) -> list[tuple[str, float, float, float, float]]:
    candles = load_m5_csv(str(csv_path))
    by_day: dict[str, list] = defaultdict(list)
    for c in candles:
        day = datetime.fromtimestamp(c.ts, tz=timezone.utc).strftime("%Y-%m-%d")
        by_day[day].append(c)
    out: list[tuple[str, float, float, float, float]] = []
    for day in sorted(by_day):
        rows = by_day[day]
        out.append(
            (
                day,
                float(rows[0].o),
                max(float(x.h) for x in rows),
                min(float(x.l) for x in rows),
                float(rows[-1].c),
            )
        )
    return out


def _sma(vals: list[float], period: int) -> float:
    if len(vals) < period:
        return float("nan")
    seg = vals[-period:]
    return sum(seg) / float(period)


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


def _universe_health_score(daily: list[tuple[str, float, float, float, float]], lookback_days: int) -> float:
    lookback_days = max(20, int(lookback_days))
    if len(daily) < max(lookback_days + 1, 80):
        return float("nan")
    closes = [x[4] for x in daily]
    close = closes[-1]
    if close <= 0:
        return float("nan")
    start_close = closes[-lookback_days]
    if start_close <= 0:
        return float("nan")
    mom = close / start_close - 1.0
    high = max(x[2] for x in daily[-lookback_days:])
    dd_from_high = close / max(1e-12, high) - 1.0
    sma20 = _sma(closes, 20)
    sma60 = _sma(closes, 60)
    close_vs_sma20 = close / sma20 - 1.0 if math.isfinite(sma20) and sma20 > 0 else 0.0
    close_vs_sma60 = close / sma60 - 1.0 if math.isfinite(sma60) and sma60 > 0 else 0.0
    rets = []
    for prev, cur in zip(closes[-lookback_days - 1 : -1], closes[-lookback_days:]):
        if prev <= 0:
            continue
        rets.append(cur / prev - 1.0)
    vol = pstdev(rets) if len(rets) >= 5 else 0.0
    return (
        1.35 * mom
        + 0.45 * close_vs_sma20
        + 0.35 * close_vs_sma60
        - 0.90 * abs(min(0.0, dd_from_high))
        - 2.20 * vol
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a refreshed equities watchlist from a broad pool")
    ap.add_argument("--tickers", default="ADBE,AMD,AMZN,AVGO,CRWD,GOOGL,META,MSFT,NFLX,NVDA,ORCL,PANW,PLTR,TSLA,UBER")
    ap.add_argument("--data-dir", default="data_cache/equities_1h")
    ap.add_argument("--lookback-days", type=int, default=80)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--cluster-groups", default="")
    ap.add_argument("--max-per-cluster", type=int, default=2)
    ap.add_argument("--tag", default="equities_universe_refresh")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    tickers = [x.strip().upper() for x in args.tickers.split(",") if x.strip()]
    groups = _parse_cluster_groups(args.cluster_groups)

    rows: list[tuple[str, float]] = []
    for ticker in tickers:
        csv_path = data_dir / f"{ticker}_M5.csv"
        if not csv_path.exists():
            continue
        daily = _aggregate_daily(csv_path)
        score = _universe_health_score(daily, int(args.lookback_days))
        if math.isfinite(score):
            rows.append((ticker, score))
    rows.sort(key=lambda x: x[1], reverse=True)

    chosen: list[tuple[str, float]] = []
    cluster_counts: dict[int, int] = defaultdict(int)
    for ticker, score in rows:
        blocked = False
        for cluster_id in _clusters_for_ticker(ticker, groups):
            if cluster_counts.get(cluster_id, 0) >= int(args.max_per_cluster):
                blocked = True
                break
        if blocked:
            continue
        chosen.append((ticker, score))
        for cluster_id in _clusters_for_ticker(ticker, groups):
            cluster_counts[cluster_id] += 1
        if len(chosen) >= max(1, int(args.top_k)):
            break

    out_dir = ROOT / "backtest_runs" / f"equities_universe_refresh_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{args.tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "watchlist.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "universe_score"])
        for ticker, score in chosen:
            w.writerow([ticker, f"{score:.6f}"])

    summary = out_dir / "summary.csv"
    with summary.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["top_k", "lookback_days", "cluster_groups", "max_per_cluster", "watchlist"])
        w.writerow(
            [
                int(args.top_k),
                int(args.lookback_days),
                args.cluster_groups,
                int(args.max_per_cluster),
                ";".join(t for t, _ in chosen),
            ]
        )

    print(f"saved={out_dir}")
    print(summary.read_text(encoding="utf-8").strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
