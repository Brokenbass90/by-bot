#!/usr/bin/env python3
"""Walk-forward OOS validation of pair stat-arb on local kline cache (2026-06-10).

Builds 1h closes by resampling cached 5m bars (merging every cache file per
symbol), aligns the pair, then evaluates strategies/pair_stat_arb_v1 on rolling
out-of-sample folds (warmup = lookback bars before each fold, config FIXED — no
per-fold fitting, so every fold is honest OOS). Aggregates via
backtest.robustness.aggregate_oos + fee_sensitivity (4 fills per round trip).

Usage:
    python3 scripts/walkforward_pair_arb.py --a ETHUSDT --b BTCUSDT
    python3 scripts/walkforward_pair_arb.py --a SOLUSDT --b ETHUSDT --oos-days 30
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.pair_stat_arb_v1 import PairConfig, PairStatArbV1
from backtest.robustness import walk_forward_windows, aggregate_oos, fee_sensitivity

_HOUR_MS = 3_600_000

import math


def simulate_pair_realizable(prices_a, prices_b, cfg: PairConfig | None = None,
                             fee_bps: float = 6.0, max_hold_bars: int = 168,
                             funding_bps_per_8h: float = 0.0) -> List[dict]:
    """Honest pair simulation: P&L = realizable log-returns of the two legs.

    Unlike scripts/validate_pair_arb.simulate_pair (which measures the change of
    a spread RE-FITTED with fresh beta/intercept at exit — not a realizable
    quantity), this books the trade exactly as the executor would: equal-notional
    LONG one leg + SHORT the other, P&L = ret(long) - ret(short) per leg notional.
    Includes a max-hold time stop (executor has one; the old sim did not).
    """
    cfg = cfg or PairConfig()
    n = min(len(prices_a), len(prices_b))
    a, b = list(prices_a[:n]), list(prices_b[:n])
    eng = PairStatArbV1(cfg)
    trades: List[dict] = []
    in_pos = False
    entry_sign = 0          # +1: z>0 -> short A long B ; -1: z<0 -> long A short B
    a_e = b_e = 0.0
    entry_i = 0
    fee_cost = 4.0 * fee_bps / 10000.0
    funding_cost_per_bar = 2.0 * funding_bps_per_8h / 10000.0 / 8.0
    lb = cfg.lookback

    def book(i: int, reason: str) -> None:
        nonlocal in_pos
        ret_a = math.log(a[i] / a_e)
        ret_b = math.log(b[i] / b_e)
        gross = entry_sign * (ret_b - ret_a)
        hold_bars = max(0, i - entry_i)
        funding_cost = hold_bars * funding_cost_per_bar
        net = gross - fee_cost - funding_cost
        trades.append({"pnl": net, "return_pct": net,
                       "fees": fee_cost, "funding_cost": funding_cost,
                       "hold_bars": hold_bars, "exit_reason": reason})
        in_pos = False

    for i in range(lb, n):
        wa, wb = a[: i + 1], b[: i + 1]
        d = eng.diagnostics(wa, wb)
        if not in_pos:
            if not d.get("tradeable"):
                continue
            z = d["z"]
            if abs(z) >= cfg.entry_z and abs(z) < cfg.stop_z:
                in_pos = True
                entry_sign = 1 if z > 0 else -1
                a_e, b_e = a[i], b[i]
                entry_i = i
        else:
            z = d.get("z", 0.0)
            exit_now, why = eng.should_exit(z)
            if not d.get("tradeable"):
                # pair lost cointegration mid-trade -> bail (safety)
                exit_now, why = True, "lost_cointegration"
            if not exit_now and (i - entry_i) >= max_hold_bars:
                exit_now, why = True, "max_hold"
            if exit_now:
                book(i, why)
    if in_pos:
        book(n - 1, "end_of_data")
    return trades


def load_1h_closes(sym: str, cache_dir: str = "data_cache") -> Dict[int, float]:
    """Merge all 5m cache files for sym and resample to 1h closes.

    Bucket key = hour start (ms). Close = close of the LAST 5m bar in the hour.
    Merging overlapping files is safe: same ts -> same bar.
    """
    bars: Dict[int, Tuple[int, float]] = {}  # hour_start -> (bar_ts, close)
    for f in sorted(glob.glob(f"{cache_dir}/{sym}_5_*.json")):
        try:
            rows = json.load(open(f))
        except Exception:
            continue
        for r in rows:
            try:
                ts = int(r["ts"]); c = float(r["c"])
            except Exception:
                continue
            hour = ts - (ts % _HOUR_MS)
            prev = bars.get(hour)
            if prev is None or ts > prev[0]:
                bars[hour] = (ts, c)
    return {h: c for h, (_, c) in bars.items()}


def align(ra: Dict[int, float], rb: Dict[int, float]) -> Tuple[List[int], List[float], List[float]]:
    common = sorted(set(ra) & set(rb))
    return common, [ra[t] for t in common], [rb[t] for t in common]


def fold_metrics(trades: List[dict]) -> Dict[str, float]:
    if not trades:
        return {"profit_factor": 1.0, "return_pct": 0.0, "trades": 0,
                "win_rate": 0.0, "max_drawdown": 0.0}
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [-t["pnl"] for t in trades if t["pnl"] < 0]
    pf = (sum(wins) / sum(losses)) if losses else (99.0 if wins else 1.0)
    eq, peak, mdd = 1.0, 1.0, 0.0
    for t in trades:
        eq *= (1.0 + t["pnl"])
        peak = max(peak, eq)
        mdd = max(mdd, (peak - eq) / peak)
    return {
        "profit_factor": round(min(pf, 99.0), 4),
        "return_pct": round((eq - 1.0) * 100.0, 4),
        "trades": len(trades),
        "win_rate": round(len(wins) / len(trades), 4),
        "max_drawdown": round(mdd * 100.0, 4),
    }


def run_walkforward(a_sym: str, b_sym: str, cfg: PairConfig, fee_bps: float,
                    oos_days: int, warmup_extra_bars: int = 24,
                    funding_bps_per_8h: float = 0.0) -> dict:
    ts, a, b = align(load_1h_closes(a_sym), load_1h_closes(b_sym))
    if len(ts) < cfg.lookback + 200:
        return {"error": f"not_enough_aligned_bars_{len(ts)}"}
    warmup_bars = cfg.lookback + warmup_extra_bars
    warmup_days = max(1, (warmup_bars + 23) // 24)
    folds = walk_forward_windows(ts[0], ts[-1] + _HOUR_MS,
                                 is_days=warmup_days, oos_days=oos_days)
    per_fold: List[Dict[str, float]] = []
    all_trades: List[dict] = []
    fold_rows = []
    for fd in folds:
        idx = [i for i, t in enumerate(ts) if fd["is_start"] <= t < fd["oos_end"]]
        if len(idx) <= warmup_bars + 10:
            continue
        s, e = idx[0], idx[-1] + 1
        trades = simulate_pair_realizable(a[s:e], b[s:e], cfg, fee_bps, funding_bps_per_8h=funding_bps_per_8h)
        m = fold_metrics(trades)
        per_fold.append(m)
        all_trades.extend(trades)
        from datetime import datetime, timezone
        fold_rows.append({
            "oos_start": datetime.fromtimestamp(fd["oos_start"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
            **m,
        })
    gross = [t["pnl"] + t.get("fees", 0.0) for t in all_trades]
    return {
        "pair": f"{a_sym}/{b_sym}",
        "aligned_bars_1h": len(ts),
        "config": vars(cfg),
        "fee_bps_per_fill": fee_bps,
        "funding_bps_per_8h_conservative": funding_bps_per_8h,
        "folds_detail": fold_rows,
        "oos_aggregate": aggregate_oos(per_fold),
        "win_rate_all": round(sum(1 for t in all_trades if t["pnl"] > 0) / len(all_trades), 4) if all_trades else None,
        "total_oos_trades": len(all_trades),
        "fee_sensitivity": fee_sensitivity(gross, fee_bps_list=(6.0, 8.0, 10.0, 12.0), sides=4) if gross else {"verdict": "no_trades"},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="ETHUSDT")
    ap.add_argument("--b", default="BTCUSDT")
    ap.add_argument("--fee-bps", type=float, default=6.0)
    ap.add_argument("--funding-bps-per-8h", type=float, default=0.0)
    ap.add_argument("--lookback", type=int, default=168)
    ap.add_argument("--oos-days", type=int, default=30)
    ap.add_argument("--entry-z", type=float, default=2.0)
    ap.add_argument("--exit-z", type=float, default=0.5)
    ap.add_argument("--stop-z", type=float, default=3.5)
    args = ap.parse_args()
    cfg = PairConfig(lookback=args.lookback, entry_z=args.entry_z,
                     exit_z=args.exit_z, stop_z=args.stop_z)
    out = run_walkforward(args.a, args.b, cfg, args.fee_bps, args.oos_days, funding_bps_per_8h=args.funding_bps_per_8h)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
