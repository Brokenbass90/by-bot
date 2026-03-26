#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex.data import load_m5_csv
from forex.engine import EngineConfig, run_backtest
from forex.types import Candle, Trade
from run_forex_multi_strategy_gate import _build_strategy, _default_pip_size, _default_spread, _default_swap


@dataclass
class RunMetrics:
    trades: int
    winrate: float
    net_pips: float
    gross_pips: float
    max_dd_pips: float
    recent_net_pips: float
    recent_trades: int
    recent_winrate: float
    sum_r: float
    return_pct_est: float
    return_pct_est_month: float
    status: str
    error: str


@dataclass
class WfMetrics:
    segments: int
    both_positive_segments: int
    both_positive_share_pct: float
    total_base_net_pips: float
    total_stress_net_pips: float
    total_base_trades: int
    total_stress_trades: int


@dataclass
class Candidate:
    pair: str
    strategy: str
    session_start_utc: int
    session_end_utc: int
    base: RunMetrics
    stress: RunMetrics
    monthly: WfMetrics | None = None
    rolling: WfMetrics | None = None


def _utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _month_key(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")


def _utc_day(ts: int) -> int:
    return ts // 86400


def _monthly_pct_from_total(total_pct: float, span_days: float) -> float:
    if span_days <= 0:
        return 0.0
    months = span_days / 30.4375
    if months <= 0:
        return 0.0
    base = max(0.0, 1.0 + float(total_pct) / 100.0)
    if base <= 0:
        return -100.0
    return ((base ** (1.0 / months)) - 1.0) * 100.0


def _recent_stats(trades: Sequence[Trade], recent_days: int) -> Tuple[float, int, float]:
    if recent_days <= 0 or not trades:
        return 0.0, 0, 0.0
    max_ts = max(t.entry_ts for t in trades)
    cutoff = max_ts - int(recent_days) * 86400
    recent = [t for t in trades if t.entry_ts >= cutoff]
    if not recent:
        return 0.0, 0, 0.0
    wins = sum(1 for t in recent if t.net_pips > 0)
    return sum(t.net_pips for t in recent), len(recent), wins / len(recent)


def _group_month_segments(candles: Sequence[Candle], min_bars: int) -> List[Tuple[str, List[Candle]]]:
    buckets: Dict[str, List[Candle]] = {}
    for candle in candles:
        buckets.setdefault(_month_key(candle.ts), []).append(candle)
    out: List[Tuple[str, List[Candle]]] = []
    for key in sorted(buckets.keys()):
        seg = buckets[key]
        if len(seg) >= min_bars:
            out.append((key, seg))
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


def _parse_session_windows(raw: str) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    for part in (raw or "").split(","):
        token = part.strip()
        if not token:
            continue
        if "-" not in token:
            raise SystemExit(f"Bad session window '{token}'. Expected START-END, e.g. 06-14")
        start_s, end_s = token.split("-", 1)
        start = int(start_s)
        end = int(end_s)
        if start < 0 or start > 23 or end < 1 or end > 24 or start >= end:
            raise SystemExit(f"Bad session window '{token}'. Hours must satisfy 0<=start<end<=24")
        out.append((start, end))
    if not out:
        raise SystemExit("No session windows parsed")
    return out


def _run_metrics(
    *,
    pair: str,
    strategy_name: str,
    candles: Sequence[Candle],
    session_start_utc: int,
    session_end_utc: int,
    spread_pips: float,
    swap_pips: float,
    recent_days: int,
    risk_pct: float,
) -> RunMetrics:
    try:
        strategy = _build_strategy(strategy_name, session_start=session_start_utc, session_end=session_end_utc)
        cfg = EngineConfig(
            pip_size=_default_pip_size(pair),
            spread_pips=spread_pips,
            swap_long_pips_per_day=swap_pips,
            swap_short_pips_per_day=swap_pips,
            risk_per_trade_pct=float(risk_pct) / 100.0,
        )
        trades, summary = run_backtest(list(candles), strategy, cfg)
        recent_net_pips, recent_trades, recent_winrate = _recent_stats(trades, recent_days=recent_days)
        span_days = 0.0
        if candles:
            span_days = max(0.0, float(candles[-1].ts - candles[0].ts) / 86400.0)
        return RunMetrics(
            trades=int(summary.trades),
            winrate=float(summary.winrate),
            net_pips=float(summary.net_pips),
            gross_pips=float(summary.gross_pips),
            max_dd_pips=float(summary.max_dd_pips),
            recent_net_pips=float(recent_net_pips),
            recent_trades=int(recent_trades),
            recent_winrate=float(recent_winrate),
            sum_r=float(summary.sum_r),
            return_pct_est=float(summary.return_pct_est),
            return_pct_est_month=float(_monthly_pct_from_total(summary.return_pct_est, span_days)),
            status="ok",
            error="",
        )
    except Exception as exc:
        return RunMetrics(
            trades=0,
            winrate=0.0,
            net_pips=0.0,
            gross_pips=0.0,
            max_dd_pips=0.0,
            recent_net_pips=0.0,
            recent_trades=0,
            recent_winrate=0.0,
            sum_r=0.0,
            return_pct_est=0.0,
            return_pct_est_month=0.0,
            status="fail",
            error=str(exc).replace(",", ";"),
        )


def _run_walkforward(
    *,
    pair: str,
    strategy_name: str,
    candles: Sequence[Candle],
    session_start_utc: int,
    session_end_utc: int,
    base_spread: float,
    base_swap: float,
    stress_spread_mult: float,
    stress_swap_mult: float,
    risk_pct: float,
    mode: str,
    month_min_bars: int,
    rolling_window_days: int,
    rolling_step_days: int,
    rolling_min_bars: int,
) -> WfMetrics | None:
    if mode == "monthly":
        segments = _group_month_segments(candles, min_bars=month_min_bars)
    else:
        segments = _rolling_segments(
            candles,
            window_days=rolling_window_days,
            step_days=rolling_step_days,
            min_bars=rolling_min_bars,
        )
    if not segments:
        return None

    both_positive_segments = 0
    total_base_net_pips = 0.0
    total_stress_net_pips = 0.0
    total_base_trades = 0
    total_stress_trades = 0

    for _, seg in segments:
        base = _run_metrics(
            pair=pair,
            strategy_name=strategy_name,
            candles=seg,
            session_start_utc=session_start_utc,
            session_end_utc=session_end_utc,
            spread_pips=base_spread,
            swap_pips=base_swap,
            recent_days=0,
            risk_pct=risk_pct,
        )
        stress = _run_metrics(
            pair=pair,
            strategy_name=strategy_name,
            candles=seg,
            session_start_utc=session_start_utc,
            session_end_utc=session_end_utc,
            spread_pips=base_spread * stress_spread_mult,
            swap_pips=base_swap * stress_swap_mult,
            recent_days=0,
            risk_pct=risk_pct,
        )
        total_base_net_pips += base.net_pips
        total_stress_net_pips += stress.net_pips
        total_base_trades += base.trades
        total_stress_trades += stress.trades
        if base.net_pips > 0 and stress.net_pips > 0:
            both_positive_segments += 1

    segments_n = len(segments)
    return WfMetrics(
        segments=segments_n,
        both_positive_segments=both_positive_segments,
        both_positive_share_pct=(both_positive_segments / segments_n * 100.0) if segments_n else 0.0,
        total_base_net_pips=total_base_net_pips,
        total_stress_net_pips=total_stress_net_pips,
        total_base_trades=total_base_trades,
        total_stress_trades=total_stress_trades,
    )


def _candidate_rank_key(candidate: Candidate) -> Tuple[float, float, float, float, float]:
    monthly_share = candidate.monthly.both_positive_share_pct if candidate.monthly else -1.0
    rolling_share = candidate.rolling.both_positive_share_pct if candidate.rolling else -1.0
    return (
        rolling_share,
        monthly_share,
        candidate.stress.return_pct_est,
        candidate.stress.recent_net_pips,
        -candidate.stress.max_dd_pips,
    )


def _write_raw_csv(path: Path, raw_rows: Iterable[dict]) -> None:
    fieldnames = [
        "pair",
        "strategy",
        "session_start_utc",
        "session_end_utc",
        "cost",
        "status",
        "trades",
        "winrate",
        "net_pips",
        "gross_pips",
        "max_dd_pips",
        "recent_net_pips",
        "recent_trades",
        "recent_winrate",
        "sum_r",
        "return_pct_est",
        "return_pct_est_month",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(raw_rows)


def _write_summary_csv(path: Path, candidates: Sequence[Candidate]) -> None:
    fieldnames = [
        "pair",
        "strategy",
        "session_start_utc",
        "session_end_utc",
        "base_trades",
        "base_net_pips",
        "base_dd_pips",
        "base_return_pct_est",
        "stress_trades",
        "stress_net_pips",
        "stress_dd_pips",
        "stress_return_pct_est",
        "stress_return_pct_est_month",
        "recent_stress_net_pips",
        "recent_stress_trades",
        "monthly_segments",
        "monthly_both_positive_segments",
        "monthly_both_positive_share_pct",
        "monthly_total_stress_net_pips",
        "rolling_segments",
        "rolling_both_positive_segments",
        "rolling_both_positive_share_pct",
        "rolling_total_stress_net_pips",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for c in candidates:
            w.writerow(
                {
                    "pair": c.pair,
                    "strategy": c.strategy,
                    "session_start_utc": c.session_start_utc,
                    "session_end_utc": c.session_end_utc,
                    "base_trades": c.base.trades,
                    "base_net_pips": f"{c.base.net_pips:.4f}",
                    "base_dd_pips": f"{c.base.max_dd_pips:.4f}",
                    "base_return_pct_est": f"{c.base.return_pct_est:.4f}",
                    "stress_trades": c.stress.trades,
                    "stress_net_pips": f"{c.stress.net_pips:.4f}",
                    "stress_dd_pips": f"{c.stress.max_dd_pips:.4f}",
                    "stress_return_pct_est": f"{c.stress.return_pct_est:.4f}",
                    "stress_return_pct_est_month": f"{c.stress.return_pct_est_month:.4f}",
                    "recent_stress_net_pips": f"{c.stress.recent_net_pips:.4f}",
                    "recent_stress_trades": c.stress.recent_trades,
                    "monthly_segments": c.monthly.segments if c.monthly else 0,
                    "monthly_both_positive_segments": c.monthly.both_positive_segments if c.monthly else 0,
                    "monthly_both_positive_share_pct": f"{c.monthly.both_positive_share_pct:.2f}" if c.monthly else "",
                    "monthly_total_stress_net_pips": f"{c.monthly.total_stress_net_pips:.4f}" if c.monthly else "",
                    "rolling_segments": c.rolling.segments if c.rolling else 0,
                    "rolling_both_positive_segments": c.rolling.both_positive_segments if c.rolling else 0,
                    "rolling_both_positive_share_pct": f"{c.rolling.both_positive_share_pct:.2f}" if c.rolling else "",
                    "rolling_total_stress_net_pips": f"{c.rolling.total_stress_net_pips:.4f}" if c.rolling else "",
                }
            )


def _write_selected_csv(path: Path, candidates: Sequence[Candidate], top_n: int) -> None:
    best_by_pair: Dict[str, Candidate] = {}
    for candidate in candidates:
        prev = best_by_pair.get(candidate.pair)
        if prev is None or _candidate_rank_key(candidate) > _candidate_rank_key(prev):
            best_by_pair[candidate.pair] = candidate

    selected = sorted(best_by_pair.values(), key=_candidate_rank_key, reverse=True)[: max(1, top_n)]
    _write_summary_csv(path, selected)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Probe pair x trend preset x session-window combos and run walk-forward only for top full-history candidates."
    )
    ap.add_argument("--pairs", default="GBPJPY,AUDJPY,USDJPY,EURJPY,GBPUSD,EURUSD")
    ap.add_argument(
        "--strategies",
        default=(
            "trend_retest_session_v1:conservative,"
            "trend_retest_session_v1:gbpjpy_stability_a,"
            "trend_retest_session_v1:gbpjpy_stability_b,"
            "trend_retest_session_v2:conservative,"
            "trend_retest_session_v2:gbpjpy_core"
        ),
    )
    ap.add_argument("--session-windows", default="05-13,06-14,07-15,06-20,08-16")
    ap.add_argument("--data-dir", default="data_cache/forex")
    ap.add_argument("--max-bars", type=int, default=0)
    ap.add_argument("--recent-days", type=int, default=28)
    ap.add_argument("--risk-pct", type=float, default=0.5)
    ap.add_argument("--stress-spread-mult", type=float, default=1.5)
    ap.add_argument("--stress-swap-mult", type=float, default=1.5)
    ap.add_argument("--top-n-wf", type=int, default=8, help="Run monthly+rolling walk-forward only for top N full-history candidates; 0 disables walk-forward.")
    ap.add_argument("--top-n-selected", type=int, default=4)
    ap.add_argument("--month-min-bars", type=int, default=600)
    ap.add_argument("--rolling-window-days", type=int, default=28)
    ap.add_argument("--rolling-step-days", type=int, default=7)
    ap.add_argument("--rolling-min-bars", type=int, default=600)
    ap.add_argument("--tag", default="fx_trend_router")
    args = ap.parse_args()

    pairs = [p.strip().upper() for p in args.pairs.split(",") if p.strip()]
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    session_windows = _parse_session_windows(args.session_windows)
    data_dir = (ROOT / args.data_dir).resolve()
    out_dir = ROOT / "backtest_runs" / f"forex_trend_router_probe_{args.tag}_{_utc_compact()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    candles_cache: Dict[str, List[Candle]] = {}
    for pair in pairs:
        csv_path = data_dir / f"{pair}_M5.csv"
        if not csv_path.exists():
            print(f"warn_missing_csv={csv_path}")
            continue
        candles = load_m5_csv(str(csv_path))
        if int(args.max_bars) > 0 and len(candles) > int(args.max_bars):
            candles = candles[-int(args.max_bars) :]
        candles_cache[pair] = candles

    print("forex trend router probe start")
    print(f"pairs={','.join(candles_cache.keys())}")
    print(f"strategies={','.join(strategies)}")
    print(f"session_windows={','.join(f'{s:02d}-{e:02d}' for s, e in session_windows)}")
    print(f"out_dir={out_dir}")

    raw_rows: List[dict] = []
    candidates: List[Candidate] = []
    for pair, candles in candles_cache.items():
        base_spread = _default_spread(pair)
        base_swap = _default_swap(pair)
        for strategy_name in strategies:
            for session_start, session_end in session_windows:
                base = _run_metrics(
                    pair=pair,
                    strategy_name=strategy_name,
                    candles=candles,
                    session_start_utc=session_start,
                    session_end_utc=session_end,
                    spread_pips=base_spread,
                    swap_pips=base_swap,
                    recent_days=int(args.recent_days),
                    risk_pct=float(args.risk_pct),
                )
                stress = _run_metrics(
                    pair=pair,
                    strategy_name=strategy_name,
                    candles=candles,
                    session_start_utc=session_start,
                    session_end_utc=session_end,
                    spread_pips=base_spread * float(args.stress_spread_mult),
                    swap_pips=base_swap * float(args.stress_swap_mult),
                    recent_days=int(args.recent_days),
                    risk_pct=float(args.risk_pct),
                )
                for cost_name, metrics in (("base", base), ("stress", stress)):
                    raw_rows.append(
                        {
                            "pair": pair,
                            "strategy": strategy_name,
                            "session_start_utc": session_start,
                            "session_end_utc": session_end,
                            "cost": cost_name,
                            "status": metrics.status,
                            "trades": metrics.trades,
                            "winrate": f"{metrics.winrate:.4f}",
                            "net_pips": f"{metrics.net_pips:.4f}",
                            "gross_pips": f"{metrics.gross_pips:.4f}",
                            "max_dd_pips": f"{metrics.max_dd_pips:.4f}",
                            "recent_net_pips": f"{metrics.recent_net_pips:.4f}",
                            "recent_trades": metrics.recent_trades,
                            "recent_winrate": f"{metrics.recent_winrate:.4f}",
                            "sum_r": f"{metrics.sum_r:.6f}",
                            "return_pct_est": f"{metrics.return_pct_est:.4f}",
                            "return_pct_est_month": f"{metrics.return_pct_est_month:.4f}",
                            "error": metrics.error,
                        }
                    )
                if base.status == "ok" and stress.status == "ok":
                    candidates.append(
                        Candidate(
                            pair=pair,
                            strategy=strategy_name,
                            session_start_utc=session_start,
                            session_end_utc=session_end,
                            base=base,
                            stress=stress,
                        )
                    )

    raw_csv = out_dir / "raw_runs.csv"
    _write_raw_csv(raw_csv, raw_rows)

    candidates.sort(
        key=lambda c: (
            c.stress.return_pct_est,
            c.stress.recent_net_pips,
            c.stress.trades,
            -c.stress.max_dd_pips,
        ),
        reverse=True,
    )

    wf_candidates = candidates[: max(0, int(args.top_n_wf))]
    for candidate in wf_candidates:
        pair = candidate.pair
        candles = candles_cache[pair]
        base_spread = _default_spread(pair)
        base_swap = _default_swap(pair)
        candidate.monthly = _run_walkforward(
            pair=pair,
            strategy_name=candidate.strategy,
            candles=candles,
            session_start_utc=candidate.session_start_utc,
            session_end_utc=candidate.session_end_utc,
            base_spread=base_spread,
            base_swap=base_swap,
            stress_spread_mult=float(args.stress_spread_mult),
            stress_swap_mult=float(args.stress_swap_mult),
            risk_pct=float(args.risk_pct),
            mode="monthly",
            month_min_bars=int(args.month_min_bars),
            rolling_window_days=int(args.rolling_window_days),
            rolling_step_days=int(args.rolling_step_days),
            rolling_min_bars=int(args.rolling_min_bars),
        )
        candidate.rolling = _run_walkforward(
            pair=pair,
            strategy_name=candidate.strategy,
            candles=candles,
            session_start_utc=candidate.session_start_utc,
            session_end_utc=candidate.session_end_utc,
            base_spread=base_spread,
            base_swap=base_swap,
            stress_spread_mult=float(args.stress_spread_mult),
            stress_swap_mult=float(args.stress_swap_mult),
            risk_pct=float(args.risk_pct),
            mode="rolling",
            month_min_bars=int(args.month_min_bars),
            rolling_window_days=int(args.rolling_window_days),
            rolling_step_days=int(args.rolling_step_days),
            rolling_min_bars=int(args.rolling_min_bars),
        )

    candidates.sort(key=_candidate_rank_key, reverse=True)

    ranked_csv = out_dir / "ranked_summary.csv"
    _write_summary_csv(ranked_csv, candidates)

    selected_csv = out_dir / "selected_best_per_pair.csv"
    _write_selected_csv(selected_csv, candidates, top_n=int(args.top_n_selected))

    print("top_candidates:")
    for candidate in candidates[: max(1, min(8, len(candidates)))]:
        monthly_share = candidate.monthly.both_positive_share_pct if candidate.monthly else -1.0
        rolling_share = candidate.rolling.both_positive_share_pct if candidate.rolling else -1.0
        print(
            f"  {candidate.pair} {candidate.strategy} @{candidate.session_start_utc:02d}-{candidate.session_end_utc:02d} "
            f"stress_ret={candidate.stress.return_pct_est:.2f}% "
            f"stress_ret_m={candidate.stress.return_pct_est_month:.2f}% "
            f"recent={candidate.stress.recent_net_pips:.2f} "
            f"monthly_both={monthly_share:.2f}% "
            f"rolling_both={rolling_share:.2f}% "
            f"dd={candidate.stress.max_dd_pips:.2f}"
        )

    print(f"raw_csv={raw_csv}")
    print(f"ranked_csv={ranked_csv}")
    print(f"selected_csv={selected_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
