#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import pstdev
from typing import Iterable

import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.bybit_data import fetch_klines_public


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
    symbol: str
    snapshot_day: str
    entry_day: str
    entry_price: float
    stop_price: float
    score: float
    atr14_pct: float
    momentum14_pct: float
    momentum30_pct: float
    pullback7_pct: float
    universe_score: float = float("nan")
    selection_score: float = float("nan")
    corr_penalty: float = 0.0
    max_corr_to_existing: float = float("nan")


def _parse_iso_date(s: str) -> datetime:
    return datetime.strptime(str(s).strip()[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _to_day(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


def _sma(vals: list[float], period: int) -> float:
    if len(vals) < period:
        return float("nan")
    seg = vals[-period:]
    return sum(seg) / float(period)


def _atr(daily: list[DailyBar], end_idx: int, period: int) -> float:
    if end_idx < period:
        return float("nan")
    trs: list[float] = []
    start_idx = end_idx - period + 1
    for i in range(start_idx, end_idx + 1):
        cur = daily[i]
        prev_close = daily[i - 1].c if i > 0 else cur.o
        trs.append(max(cur.h - cur.l, abs(cur.h - prev_close), abs(cur.l - prev_close)))
    return sum(trs) / float(len(trs) or 1)


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


def _parse_cluster_groups(raw: str) -> list[set[str]]:
    out: list[set[str]] = []
    if not raw:
        return out
    for group in str(raw).split(";"):
        symbols = {x.strip().upper() for x in group.split(",") if x.strip()}
        if len(symbols) >= 2:
            out.append(symbols)
    return out


def _clusters_for_symbol(symbol: str, groups: list[set[str]]) -> list[int]:
    symbol = (symbol or "").strip().upper()
    return [idx for idx, group in enumerate(groups) if symbol in group]


def _cache_rows(cache_dir: Path, symbol: str, interval: str, start_ms: int, end_ms: int) -> list[list[float]]:
    interval = str(interval)
    exact = cache_dir / f"{symbol}_{interval}_{start_ms}_{end_ms}.json"
    if exact.exists():
        return json.loads(exact.read_text(encoding="utf-8"))

    candidates = sorted(
        cache_dir.glob(f"{symbol}_{interval}_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    best_rows: list[list[float]] | None = None
    best_key = None
    for cand in candidates:
        try:
            rows = json.loads(cand.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not rows:
            continue
        first_ts = int(float(rows[0][0]))
        last_ts = int(float(rows[-1][0]))
        if first_ts <= 0 or last_ts <= 0:
            continue
        overlap_ms = max(0, min(last_ts, end_ms) - max(first_ts, start_ms))
        coverage_ms = max(0, last_ts - first_ts)
        key = (overlap_ms, coverage_ms, len(rows), cand.stat().st_mtime)
        if best_key is None or key > best_key:
            best_key = key
            best_rows = rows
    if best_rows is not None:
        return best_rows
    raise FileNotFoundError(f"no cached klines for {symbol} interval={interval}")


def _load_5m_rows(
    symbol: str,
    start_ms: int,
    end_ms: int,
    *,
    cache_dir: Path,
    cache_only: bool,
    bybit_base: str,
) -> list[list[float]]:
    if cache_only:
        rows = _cache_rows(cache_dir, symbol, "5", start_ms, end_ms)
    else:
        try:
            kl = fetch_klines_public(symbol, interval="5", start_ms=start_ms, end_ms=end_ms, base=bybit_base, cache=True)
            rows = [[k.ts, k.o, k.h, k.l, k.c, k.v] for k in kl]
        except Exception:
            rows = _cache_rows(cache_dir, symbol, "5", start_ms, end_ms)
    out: list[list[float]] = []
    for row in rows:
        ts = int(float(row[0]))
        if start_ms <= ts < end_ms:
            out.append([ts, float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])])
    return out


def _aggregate_daily(rows_5m: list[list[float]]) -> list[DailyBar]:
    by_day: dict[str, list[list[float]]] = defaultdict(list)
    for row in rows_5m:
        by_day[_to_day(int(row[0]))].append(row)
    out: list[DailyBar] = []
    for day in sorted(by_day):
        rows = by_day[day]
        out.append(
            DailyBar(
                ts=int(rows[0][0]),
                day=day,
                o=float(rows[0][1]),
                h=max(float(x[2]) for x in rows),
                l=min(float(x[3]) for x in rows),
                c=float(rows[-1][4]),
                v=sum(float(x[5]) for x in rows),
            )
        )
    return out


def _iter_snapshots(daily: list[DailyBar], cycle_days: int) -> Iterable[int]:
    if not daily:
        return
    step = max(1, int(cycle_days))
    start_idx = max(30, step - 1)
    for i in range(start_idx, len(daily) - 1, step):
        yield i


def _btc_regime_ok(
    regime_daily: list[DailyBar],
    snapshot_day: str,
    *,
    require_bull: bool,
    regime_sma_days: int,
    regime_mom_days: int,
) -> bool:
    if not require_bull:
        return True
    idx = next((i for i, bar in enumerate(regime_daily) if bar.day == snapshot_day), None)
    if idx is None or idx < max(regime_sma_days, regime_mom_days):
        return False
    closes = [x.c for x in regime_daily[: idx + 1]]
    close = closes[-1]
    sma = _sma(closes, regime_sma_days)
    if not math.isfinite(sma) or sma <= 0:
        return False
    mom = close / closes[-regime_mom_days] - 1.0
    return close > sma and mom > 0.0


def _universe_health_score(daily: list[DailyBar], i: int, lookback_days: int) -> float:
    if i < max(20, lookback_days):
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
    rets = []
    for j in range(max(1, i - lookback_days + 1), i + 1):
        prev = daily[j - 1].c
        cur = daily[j].c
        if prev <= 0:
            continue
        rets.append(cur / prev - 1.0)
    vol = pstdev(rets) if len(rets) >= 5 else 0.0
    return 1.40 * mom - 0.70 * abs(min(0.0, dd_from_high)) - 2.20 * vol


def _candidate_from_snapshot(
    symbol: str,
    daily: list[DailyBar],
    i: int,
    *,
    lookback_fast: int,
    lookback_slow: int,
    pullback_lookback: int,
    min_mom_fast: float,
    min_mom_slow: float,
    pullback_min: float,
    pullback_max: float,
    stop_atr_mult: float,
) -> Candidate | None:
    hist_need = max(lookback_slow + 5, pullback_lookback + 5, 35)
    if i < hist_need or i + 1 >= len(daily):
        return None
    closes = [x.c for x in daily[: i + 1]]
    close = closes[-1]
    sma20 = _sma(closes, 20)
    sma30 = _sma(closes, 30)
    if not (math.isfinite(sma20) and math.isfinite(sma30) and close > 0):
        return None
    mom_fast = close / closes[-lookback_fast] - 1.0
    mom_slow = close / closes[-lookback_slow] - 1.0
    high_pullback = max(x.h for x in daily[i - (pullback_lookback - 1) : i + 1])
    pullback = close / high_pullback - 1.0
    atr14 = _atr(daily, i, 14)
    if not math.isfinite(atr14) or atr14 <= 0:
        return None
    rets = []
    for j in range(max(1, i - 13), i + 1):
        prev = daily[j - 1].c
        cur = daily[j].c
        if prev <= 0:
            continue
        rets.append(cur / prev - 1.0)
    vol14 = pstdev(rets) if len(rets) >= 5 else 0.0

    if close < sma30:
        return None
    if mom_fast <= min_mom_fast or mom_slow <= min_mom_slow:
        return None
    if not (pullback_min <= pullback <= pullback_max):
        return None

    score = (
        0.50 * mom_fast
        + 0.30 * mom_slow
        - 0.20 * abs(pullback)
        + (0.02 if close > sma20 else -0.02)
        - 1.80 * vol14
    )
    entry_bar = daily[i + 1]
    stop = entry_bar.o - stop_atr_mult * atr14
    if stop <= 0 or stop >= entry_bar.o:
        return None
    return Candidate(
        symbol=symbol,
        snapshot_day=daily[i].day,
        entry_day=entry_bar.day,
        entry_price=entry_bar.o,
        stop_price=stop,
        score=score,
        atr14_pct=atr14 / entry_bar.o * 100.0,
        momentum14_pct=mom_fast * 100.0,
        momentum30_pct=mom_slow * 100.0,
        pullback7_pct=pullback * 100.0,
    )


def _position_weight(cand: Candidate, mode: str) -> float:
    mode = (mode or "equal").strip().lower()
    atr_pct = max(1e-6, float(cand.atr14_pct))
    score = max(1e-6, float(cand.score))
    if mode == "inv_vol":
        return 1.0 / atr_pct
    if mode == "score":
        return score
    if mode == "score_inv_vol":
        return score / atr_pct
    return 1.0


def _simulate_trade(
    daily: list[DailyBar],
    entry_idx: int,
    entry_price: float,
    initial_stop: float,
    max_hold_days: int,
    trail_atr_mult: float,
    atr14: float,
) -> tuple[int, float, str]:
    stop = initial_stop
    peak = entry_price
    last_idx = min(len(daily) - 1, entry_idx + max_hold_days)
    for i in range(entry_idx, last_idx + 1):
        bar = daily[i]
        peak = max(peak, bar.h)
        if trail_atr_mult > 0 and atr14 > 0:
            stop = max(stop, peak - trail_atr_mult * atr14)
        if bar.l <= stop:
            return i, stop, "stop"
    return last_idx, daily[last_idx].c, "time"


def main() -> int:
    ap = argparse.ArgumentParser(description="Crypto momentum rotation research on Bybit cached/public data")
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,DOGEUSDT,XRPUSDT,BNBUSDT,AVAXUSDT,APTUSDT,NEARUSDT,AAVEUSDT,ATOMUSDT,INJUSDT,TAOUSDT,SUIUSDT")
    ap.add_argument("--start", default="2025-04-01")
    ap.add_argument("--end", default="2026-04-01")
    ap.add_argument("--cache-dir", default=".cache/klines")
    ap.add_argument("--cache-only", action="store_true")
    ap.add_argument("--bybit-base", default="https://api.bybit.com")
    ap.add_argument("--cycle-days", type=int, default=7)
    ap.add_argument("--top-n", type=int, default=3)
    ap.add_argument("--max-hold-days", type=int, default=10)
    ap.add_argument("--lookback-fast", type=int, default=14)
    ap.add_argument("--lookback-slow", type=int, default=30)
    ap.add_argument("--pullback-lookback", type=int, default=7)
    ap.add_argument("--min-mom-fast-pct", type=float, default=4.0)
    ap.add_argument("--min-mom-slow-pct", type=float, default=8.0)
    ap.add_argument("--pullback-min-pct", type=float, default=-10.0)
    ap.add_argument("--pullback-max-pct", type=float, default=-0.5)
    ap.add_argument("--stop-atr-mult", type=float, default=1.8)
    ap.add_argument("--trail-atr-mult", type=float, default=2.2)
    ap.add_argument("--regime-symbol", default="BTCUSDT")
    ap.add_argument("--require-bull-regime", type=int, default=1)
    ap.add_argument("--regime-sma-days", type=int, default=30)
    ap.add_argument("--regime-mom-days", type=int, default=30)
    ap.add_argument("--universe-top-k", type=int, default=0)
    ap.add_argument("--universe-score-lookback-days", type=int, default=45)
    ap.add_argument("--corr-lookback-days", type=int, default=30)
    ap.add_argument("--max-pair-corr", type=float, default=0.85)
    ap.add_argument("--corr-penalty-mult", type=float, default=1.5)
    ap.add_argument("--corr-penalty-threshold", type=float, default=0.55)
    ap.add_argument("--cluster-groups", default="BTCUSDT,ETHUSDT;SOLUSDT,AVAXUSDT,APTUSDT,SUIUSDT;LINKUSDT,AAVEUSDT,INJUSDT,TAOUSDT,ATOMUSDT;DOGEUSDT,XRPUSDT,ADAUSDT,NEARUSDT")
    ap.add_argument("--max-per-cluster", type=int, default=1)
    ap.add_argument("--position-weight-mode", default="score_inv_vol")
    ap.add_argument("--tag", default="crypto_momentum_rotation")
    args = ap.parse_args()

    start_dt = _parse_iso_date(args.start)
    end_dt = _parse_iso_date(args.end)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    cache_dir = ROOT / args.cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)

    symbols = [x.strip().upper() for x in str(args.symbols).split(",") if x.strip()]
    if args.regime_symbol and args.regime_symbol.upper() not in symbols:
        symbols = [args.regime_symbol.upper()] + symbols

    daily_map: dict[str, list[DailyBar]] = {}
    skipped_symbols: dict[str, str] = {}
    for symbol in symbols:
        try:
            rows = _load_5m_rows(
                symbol,
                start_ms,
                end_ms,
                cache_dir=cache_dir,
                cache_only=bool(args.cache_only),
                bybit_base=str(args.bybit_base),
            )
        except Exception as e:
            skipped_symbols[symbol] = str(e)
            continue
        daily = _aggregate_daily(rows)
        if len(daily) >= 40:
            daily_map[symbol] = daily
        else:
            skipped_symbols[symbol] = "insufficient_daily_bars"

    regime_daily = daily_map.get(args.regime_symbol.upper())
    if regime_daily is None:
        raise SystemExit(f"missing regime data for {args.regime_symbol}")

    out_dir = ROOT / "backtest_runs" / f"crypto_momentum_rotation_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{args.tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    clusters = _parse_cluster_groups(args.cluster_groups)
    monthly_cycle_returns: dict[str, list[float]] = defaultdict(list)
    trades_rows: list[list[str]] = []
    picks_rows: list[list[str]] = []
    cycle_rows: list[list[str]] = []
    equity = 1.0
    equity_curve: list[float] = [equity]

    snapshot_source = next(iter(daily_map.values()))
    corr_cache: dict[tuple[str, str, str], float | None] = {}
    cycle_count = 0

    for i in _iter_snapshots(snapshot_source, int(args.cycle_days)):
        snapshot_day = snapshot_source[i].day
        if not _btc_regime_ok(
            regime_daily,
            snapshot_day,
            require_bull=bool(int(args.require_bull_regime)),
            regime_sma_days=int(args.regime_sma_days),
            regime_mom_days=int(args.regime_mom_days),
        ):
            continue

        candidate_meta: dict[str, tuple[Candidate, int, list[DailyBar]]] = {}
        universe_scores: dict[str, float] = {}
        for symbol, daily in daily_map.items():
            if symbol == args.regime_symbol.upper():
                continue
            idx = next((j for j, bar in enumerate(daily) if bar.day == snapshot_day), None)
            if idx is None:
                continue
            universe_scores[symbol] = _universe_health_score(daily, idx, int(args.universe_score_lookback_days))
            cand = _candidate_from_snapshot(
                symbol,
                daily,
                idx,
                lookback_fast=int(args.lookback_fast),
                lookback_slow=int(args.lookback_slow),
                pullback_lookback=int(args.pullback_lookback),
                min_mom_fast=float(args.min_mom_fast_pct) / 100.0,
                min_mom_slow=float(args.min_mom_slow_pct) / 100.0,
                pullback_min=float(args.pullback_min_pct) / 100.0,
                pullback_max=float(args.pullback_max_pct) / 100.0,
                stop_atr_mult=float(args.stop_atr_mult),
            )
            if cand is None:
                continue
            cand.universe_score = universe_scores.get(symbol, float("nan"))
            candidate_meta[symbol] = (cand, idx + 1, daily)

        allowed_universe: set[str] | None = None
        if int(args.universe_top_k) > 0:
            scored = [(sym, score) for sym, score in universe_scores.items() if math.isfinite(score)]
            scored.sort(key=lambda x: x[1], reverse=True)
            allowed_universe = {sym for sym, _ in scored[: max(1, int(args.universe_top_k))]}

        candidates = [triplet for sym, triplet in candidate_meta.items() if allowed_universe is None or sym in allowed_universe]
        remaining = sorted(candidates, key=lambda x: x[0].score, reverse=True)
        picks: list[tuple[Candidate, int, list[DailyBar]]] = []
        cluster_counts: dict[int, int] = defaultdict(int)

        def _cached_pair_corr(left: tuple[Candidate, int, list[DailyBar]], right: tuple[Candidate, int, list[DailyBar]]) -> float | None:
            key = tuple(sorted((left[0].symbol, right[0].symbol)) + [snapshot_day])
            if key not in corr_cache:
                corr_cache[key] = _pair_corr(
                    left[2],
                    left[1] - 1,
                    right[2],
                    right[1] - 1,
                    int(args.corr_lookback_days),
                )
            return corr_cache[key]

        while remaining and len(picks) < max(1, int(args.top_n)):
            best_idx = None
            best_selection_score = float("-inf")
            best_penalty = 0.0
            best_max_corr = float("nan")
            for idx, cand_triplet in enumerate(remaining):
                cand = cand_triplet[0]
                blocked = False
                if int(args.max_per_cluster) > 0:
                    for cluster_id in _clusters_for_symbol(cand.symbol, clusters):
                        if cluster_counts.get(cluster_id, 0) >= int(args.max_per_cluster):
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
            for cluster_id in _clusters_for_symbol(picked[0].symbol, clusters):
                cluster_counts[cluster_id] += 1

        if not picks:
            continue

        cycle_count += 1
        cycle_weights = [_position_weight(cand, args.position_weight_mode) for cand, _, _ in picks]
        total_weight = sum(max(0.0, w) for w in cycle_weights) or float(len(cycle_weights))
        cycle_rets: list[float] = []
        pick_labels: list[str] = []

        for (cand, entry_idx, daily), weight in zip(picks, cycle_weights):
            atr14_abs = cand.atr14_pct / 100.0 * cand.entry_price
            exit_idx, exit_price, reason = _simulate_trade(
                daily,
                entry_idx,
                cand.entry_price,
                cand.stop_price,
                int(args.max_hold_days),
                float(args.trail_atr_mult),
                atr14_abs,
            )
            ret = exit_price / cand.entry_price - 1.0
            cycle_rets.append(ret * max(0.0, weight))
            pick_labels.append(cand.symbol)
            exit_day = daily[exit_idx].day if exit_idx < len(daily) else daily[-1].day

            picks_rows.append(
                [
                    snapshot_day,
                    cand.symbol,
                    cand.entry_day,
                    f"{cand.score:.6f}",
                    f"{cand.atr14_pct:.4f}",
                    f"{cand.momentum14_pct:.4f}",
                    f"{cand.momentum30_pct:.4f}",
                    f"{cand.pullback7_pct:.4f}",
                    f"{cand.universe_score:.6f}" if math.isfinite(cand.universe_score) else "",
                    f"{cand.selection_score:.6f}" if math.isfinite(cand.selection_score) else "",
                    f"{cand.corr_penalty:.6f}",
                    f"{cand.max_corr_to_existing:.6f}" if math.isfinite(cand.max_corr_to_existing) else "",
                    f"{cand.entry_price:.6f}",
                    f"{cand.stop_price:.6f}",
                    f"{weight:.6f}",
                ]
            )
            trades_rows.append(
                [
                    snapshot_day,
                    cand.symbol,
                    cand.entry_day,
                    exit_day,
                    f"{cand.entry_price:.6f}",
                    f"{exit_price:.6f}",
                    f"{cand.stop_price:.6f}",
                    f"{cand.score:.6f}",
                    f"{cand.momentum14_pct:.4f}",
                    f"{cand.momentum30_pct:.4f}",
                    f"{cand.pullback7_pct:.4f}",
                    f"{cand.selection_score:.6f}" if math.isfinite(cand.selection_score) else "",
                    f"{weight:.6f}",
                    f"{ret * 100.0:.4f}",
                    reason,
                ]
            )

        cycle_ret = sum(cycle_rets) / total_weight
        equity *= 1.0 + cycle_ret
        equity_curve.append(equity)
        cycle_month = snapshot_day[:7]
        monthly_cycle_returns[cycle_month].append(cycle_ret)
        cycle_rows.append([snapshot_day, cycle_month, ",".join(pick_labels), str(len(pick_labels)), f"{cycle_ret * 100.0:.4f}", f"{equity * 100.0:.4f}"])

    monthly_rows: list[list[str]] = []
    month_returns_pct: list[float] = []
    month_equity = 1.0
    for month in sorted(monthly_cycle_returns):
        month_ret = 1.0
        for cycle_ret in monthly_cycle_returns[month]:
            month_ret *= 1.0 + cycle_ret
        month_ret -= 1.0
        month_returns_pct.append(month_ret * 100.0)
        month_equity *= 1.0 + month_ret
        monthly_rows.append([month, str(len(monthly_cycle_returns[month])), f"{month_ret * 100.0:.4f}", f"{month_equity * 100.0:.4f}"])

    trades_csv = out_dir / "trades.csv"
    with trades_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "snapshot_day",
            "symbol",
            "entry_day",
            "exit_day",
            "entry_price",
            "exit_price",
            "stop_price",
            "score",
            "momentum14_pct",
            "momentum30_pct",
            "pullback7_pct",
            "selection_score",
            "weight",
            "return_pct",
            "reason",
        ])
        w.writerows(trades_rows)

    picks_csv = out_dir / "picks.csv"
    with picks_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "snapshot_day",
            "symbol",
            "entry_day",
            "score",
            "atr14_pct",
            "momentum14_pct",
            "momentum30_pct",
            "pullback7_pct",
            "universe_score",
            "selection_score",
            "corr_penalty",
            "max_corr_to_existing",
            "entry_price",
            "stop_price",
            "weight",
        ])
        w.writerows(picks_rows)

    cycles_csv = out_dir / "cycles.csv"
    with cycles_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["snapshot_day", "month", "symbols", "positions", "cycle_return_pct", "equity_index"])
        w.writerows(cycle_rows)

    monthly_csv = out_dir / "monthly.csv"
    with monthly_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["month", "cycles", "month_return_pct", "equity_index"])
        w.writerows(monthly_rows)

    returns = [float(row[-2]) for row in trades_rows]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    sum_wins = sum(wins) if wins else 0.0
    sum_losses = abs(sum(losses)) if losses else 0.0
    profit_factor = (sum_wins / sum_losses) if sum_losses > 0 else float("nan")
    positive_months = [x for x in month_returns_pct if x > 0]
    negative_months = [x for x in month_returns_pct if x < 0]
    max_eq = equity_curve[0]
    max_dd = 0.0
    for eq in equity_curve:
        max_eq = max(max_eq, eq)
        max_dd = min(max_dd, eq / max_eq - 1.0)

    streak = 0
    max_negative_streak = 0
    for val in month_returns_pct:
        if val < 0:
            streak += 1
            max_negative_streak = max(max_negative_streak, streak)
        else:
            streak = 0

    summary_csv = out_dir / "summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "months",
            "cycles",
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
            "max_negative_streak",
            "worst_month_pnl",
            "symbols",
            "top_n",
            "cycle_days",
            "max_hold_days",
            "lookback_fast",
            "lookback_slow",
            "pullback_lookback",
            "trail_atr_mult",
            "require_bull_regime",
        ])
        w.writerow([
            len(monthly_rows),
            cycle_count,
            len(trades_rows),
            f"{(len(wins) / max(1, len(returns))) * 100.0:.4f}",
            f"{(sum(returns) / max(1, len(returns))):.4f}",
            f"{profit_factor:.4f}" if math.isfinite(profit_factor) else "",
            len(positive_months),
            len(negative_months),
            f"{(len(positive_months) / max(1, len(monthly_rows))) * 100.0:.4f}",
            f"{(sum(month_returns_pct) / max(1, len(month_returns_pct))):.4f}" if month_returns_pct else "0.0000",
            f"{(equity - 1.0) * 100.0:.4f}",
            f"{abs(max_dd) * 100.0:.4f}",
            max_negative_streak,
            f"{min(month_returns_pct):.4f}" if month_returns_pct else "0.0000",
            ";".join(sorted(sym for sym in daily_map if sym != args.regime_symbol.upper())),
            int(args.top_n),
            int(args.cycle_days),
            int(args.max_hold_days),
            int(args.lookback_fast),
            int(args.lookback_slow),
            int(args.pullback_lookback),
            float(args.trail_atr_mult),
            int(args.require_bull_regime),
        ])

    if skipped_symbols:
        print("skipped_symbols=" + json.dumps(skipped_symbols, ensure_ascii=False, sort_keys=True))
    print(f"saved={out_dir}")
    with summary_csv.open(newline="", encoding="utf-8") as f:
        print(f.read().strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
