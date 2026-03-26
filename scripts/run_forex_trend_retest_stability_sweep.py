#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex.data import load_m5_csv
from forex.engine import EngineConfig, run_backtest
from forex.strategies.trend_retest_session_v1 import Config, TrendRetestSessionV1
from forex.types import Candle


def _utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _utc_day(ts: int) -> int:
    return ts // 86400


def _month_key(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")


def _default_pip_size(symbol: str) -> float:
    return 0.01 if symbol.upper().endswith("JPY") else 0.0001


def _default_spread(symbol: str) -> float:
    p = symbol.upper()
    if p.endswith("JPY"):
        return 1.0
    if p in {"EURUSD", "USDCHF"}:
        return 1.0
    if p in {"GBPUSD", "GBPAUD", "GBPJPY", "GBPCHF", "GBPCAD"}:
        return 1.2
    if p in {"AUDUSD", "USDCAD", "NZDUSD", "EURGBP", "EURJPY", "AUDJPY", "CADJPY", "CHFJPY"}:
        return 1.3
    return 1.5


def _default_swap(symbol: str) -> float:
    p = symbol.upper()
    if p in {"EURUSD", "USDJPY", "USDCHF"}:
        return -0.3
    if p in {"GBPUSD", "GBPJPY", "GBPAUD", "GBPCHF", "GBPCAD"}:
        return -0.4
    return -0.35


def _group_months(candles: Sequence[Candle], min_bars: int) -> List[Tuple[str, List[Candle]]]:
    buckets: dict[str, list[Candle]] = {}
    for c in candles:
        buckets.setdefault(_month_key(c.ts), []).append(c)
    out: List[Tuple[str, List[Candle]]] = []
    for k in sorted(buckets):
        seg = buckets[k]
        if len(seg) >= min_bars:
            out.append((k, seg))
    return out


def _rolling_segments(candles: Sequence[Candle], window_days: int, step_days: int, min_bars: int) -> List[List[Candle]]:
    if not candles:
        return []
    start_day = _utc_day(candles[0].ts)
    end_day = _utc_day(candles[-1].ts)
    out: List[List[Candle]] = []
    cur = start_day
    while cur + window_days <= end_day + 1:
        w_start = cur
        w_end = cur + window_days
        seg = [c for c in candles if w_start <= _utc_day(c.ts) < w_end]
        if len(seg) >= min_bars:
            out.append(seg)
        cur += step_days
    return out


def _run(candles: Sequence[Candle], cfg: Config, eng: EngineConfig):
    return run_backtest(list(candles), TrendRetestSessionV1(cfg), eng)[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Stability-first sweep for trend_retest_session_v1.")
    ap.add_argument("--symbol", default="GBPJPY")
    ap.add_argument("--csv", default="data_cache/forex/GBPJPY_M5.csv")
    ap.add_argument("--session-start-utc", type=int, default=6)
    ap.add_argument("--session-end-utc", type=int, default=20)
    ap.add_argument("--risk-pct", type=float, default=0.5)
    ap.add_argument("--stress-spread-mult", type=float, default=1.5)
    ap.add_argument("--stress-swap-mult", type=float, default=1.5)
    ap.add_argument("--month-min-bars", type=int, default=600)
    ap.add_argument("--roll-window-days", type=int, default=28)
    ap.add_argument("--roll-step-days", type=int, default=7)
    ap.add_argument("--roll-min-bars", type=int, default=600)
    ap.add_argument("--full-min-trades", type=int, default=80)
    ap.add_argument("--full-max-dd", type=float, default=350.0)
    ap.add_argument("--monthly-top-n-for-rolling", type=int, default=8)
    ap.add_argument("--grid-profile", default="quick", choices=["quick", "balanced", "wide"])
    ap.add_argument(
        "--max-bars",
        type=int,
        default=0,
        help="Use only last N bars for sweep (0 = full history).",
    )
    ap.add_argument("--out-prefix", default="docs/forex_trend_retest_stability_latest")
    args = ap.parse_args()

    symbol = args.symbol.strip().upper()
    candles = load_m5_csv(args.csv)
    if not candles:
        raise SystemExit(f"No candles in {args.csv}")
    if int(args.max_bars) > 0:
        candles = candles[-int(args.max_bars) :]

    pip = _default_pip_size(symbol)
    spread = _default_spread(symbol) * float(args.stress_spread_mult)
    swap = _default_swap(symbol) * float(args.stress_swap_mult)
    eng = EngineConfig(
        pip_size=pip,
        spread_pips=spread,
        swap_long_pips_per_day=swap,
        swap_short_pips_per_day=swap,
        risk_per_trade_pct=float(args.risk_pct) / 100.0,
    )

    month_segments = _group_months(candles, min_bars=max(1, int(args.month_min_bars)))
    roll_segments = _rolling_segments(
        candles, window_days=max(7, int(args.roll_window_days)), step_days=max(1, int(args.roll_step_days)), min_bars=max(1, int(args.roll_min_bars))
    )
    if not month_segments:
        raise SystemExit("No month segments. Lower --month-min-bars.")
    if not roll_segments:
        raise SystemExit("No rolling segments. Lower --roll-min-bars.")

    if args.grid_profile == "quick":
        ema_fast_grid = [48, 55]
        ema_slow_grid = [180, 220]
        lookback_grid = [36, 42]
        retest_grid = [8, 10]
        sl_grid = [1.2, 1.3]
        rr_grid = [1.4, 1.8, 2.2]
        cooldown_grid = [24, 32]
    elif args.grid_profile == "balanced":
        ema_fast_grid = [40, 48, 55, 64]
        ema_slow_grid = [180, 220]
        lookback_grid = [30, 36, 42, 48]
        retest_grid = [6, 8, 10]
        sl_grid = [1.2, 1.3, 1.4]
        rr_grid = [1.4, 1.8, 2.2, 2.5]
        cooldown_grid = [14, 24, 32]
    else:
        ema_fast_grid = [34, 40, 48, 55, 64]
        ema_slow_grid = [144, 180, 220]
        lookback_grid = [24, 30, 36, 42, 48]
        retest_grid = [5, 6, 8, 10]
        sl_grid = [1.2, 1.3, 1.4, 1.5]
        rr_grid = [1.4, 1.8, 2.2, 2.5]
        cooldown_grid = [14, 24, 32]

    # Keep runtime manageable by evaluating a curated subset around known presets.
    candidates: list[Config] = []
    for ef in ema_fast_grid:
        for es in ema_slow_grid:
            if ef >= es:
                continue
            for lb in lookback_grid:
                for rt in retest_grid:
                    for sl in sl_grid:
                        for rr in rr_grid:
                            for cd in cooldown_grid:
                                if rr < 1.6 and sl > 1.3:
                                    continue
                                if rr >= 2.2 and sl < 1.25:
                                    continue
                                if lb < 30 and rt > 8:
                                    continue
                                candidates.append(
                                    Config(
                                        ema_fast=ef,
                                        ema_slow=es,
                                        breakout_lookback=lb,
                                        retest_window_bars=rt,
                                        sl_atr_mult=sl,
                                        rr=rr,
                                        cooldown_bars=cd,
                                        session_utc_start=int(args.session_start_utc),
                                        session_utc_end=int(args.session_end_utc),
                                    )
                                )

    full_rows = []
    for cfg in candidates:
        s = _run(candles, cfg, eng)
        if s.trades < int(args.full_min_trades):
            continue
        if s.max_dd_pips > float(args.full_max_dd):
            continue
        if s.net_pips <= 0:
            continue
        if s.return_pct_est <= 0:
            continue
        full_rows.append((cfg, s))

    if not full_rows:
        out_csv = ROOT / f"{args.out_prefix}.csv"
        out_txt = ROOT / f"{args.out_prefix}.txt"
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "symbol",
                    "ema_fast",
                    "ema_slow",
                    "lookback",
                    "retest",
                    "sl_atr",
                    "rr",
                    "cooldown",
                    "full_trades",
                    "full_winrate",
                    "full_net_pips",
                    "full_dd_pips",
                    "full_return_pct_est",
                    "month_pos",
                    "month_neg",
                    "month_zero",
                    "month_pos_share_pct",
                    "month_total_stress_pips",
                    "roll_pos_share_pct",
                    "roll_total_stress_pips",
                    "status",
                    "reason",
                ]
            )
        out_txt.write_text("", encoding="utf-8")
        print("no full-positive candidates")
        print(f"saved_csv={out_csv}")
        print(f"saved_txt={out_txt}")
        return 0

    month_eval = []
    for cfg, s in full_rows:
        pos = neg = zero = 0
        total = 0.0
        for _, seg in month_segments:
            ss = _run(seg, cfg, eng)
            total += float(ss.net_pips)
            if ss.net_pips > 0:
                pos += 1
            elif ss.net_pips < 0:
                neg += 1
            else:
                zero += 1
        share = (pos / max(1, (pos + neg + zero))) * 100.0
        month_eval.append((cfg, s, pos, neg, zero, share, total))

    month_eval.sort(key=lambda x: (x[5], x[6], x[1].return_pct_est), reverse=True)
    top_for_roll = month_eval[: max(1, int(args.monthly_top_n_for_rolling))]

    rows = []
    for cfg, s, pos, neg, zero, month_share, month_total in top_for_roll:
        r_pos = r_neg = r_zero = 0
        r_total = 0.0
        for seg in roll_segments:
            rs = _run(seg, cfg, eng)
            r_total += float(rs.net_pips)
            if rs.net_pips > 0:
                r_pos += 1
            elif rs.net_pips < 0:
                r_neg += 1
            else:
                r_zero += 1
        roll_share = (r_pos / max(1, (r_pos + r_neg + r_zero))) * 100.0

        status = "PASS"
        reason_parts = []
        if month_share < 55.0:
            status = "REJECT"
            reason_parts.append("month_share_low")
        if pos < neg:
            status = "REJECT"
            reason_parts.append("pos_lt_neg_months")
        if month_total <= 0:
            status = "REJECT"
            reason_parts.append("month_total_nonpos")
        if roll_share < 55.0:
            status = "REJECT"
            reason_parts.append("roll_share_low")
        if r_total <= 0:
            status = "REJECT"
            reason_parts.append("roll_total_nonpos")
        reason = ",".join(reason_parts) if reason_parts else "stable"

        rows.append(
            {
                "symbol": symbol,
                "ema_fast": cfg.ema_fast,
                "ema_slow": cfg.ema_slow,
                "lookback": cfg.breakout_lookback,
                "retest": cfg.retest_window_bars,
                "sl_atr": cfg.sl_atr_mult,
                "rr": cfg.rr,
                "cooldown": cfg.cooldown_bars,
                "full_trades": s.trades,
                "full_winrate": round(s.winrate, 4),
                "full_net_pips": round(s.net_pips, 4),
                "full_dd_pips": round(s.max_dd_pips, 4),
                "full_return_pct_est": round(s.return_pct_est, 4),
                "month_pos": pos,
                "month_neg": neg,
                "month_zero": zero,
                "month_pos_share_pct": round(month_share, 2),
                "month_total_stress_pips": round(month_total, 4),
                "roll_pos_share_pct": round(roll_share, 2),
                "roll_total_stress_pips": round(r_total, 4),
                "status": status,
                "reason": reason,
            }
        )

    rows.sort(
        key=lambda r: (
            r["status"] != "PASS",
            -r["month_pos_share_pct"],
            -r["roll_pos_share_pct"],
            -r["full_return_pct_est"],
        )
    )

    out_dir = ROOT / "backtest_runs" / f"forex_trend_retest_stability_sweep_{_utc_compact()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "results.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "symbol",
                "ema_fast",
                "ema_slow",
                "lookback",
                "retest",
                "sl_atr",
                "rr",
                "cooldown",
                "full_trades",
                "full_winrate",
                "full_net_pips",
                "full_dd_pips",
                "full_return_pct_est",
                "month_pos",
                "month_neg",
                "month_zero",
                "month_pos_share_pct",
                "month_total_stress_pips",
                "roll_pos_share_pct",
                "roll_total_stress_pips",
                "status",
                "reason",
            ],
        )
        w.writeheader()
        w.writerows(rows)

    latest_csv = ROOT / f"{args.out_prefix}.csv"
    latest_txt = ROOT / f"{args.out_prefix}.txt"
    latest_csv.parent.mkdir(parents=True, exist_ok=True)
    latest_csv.write_text(out_csv.read_text(encoding="utf-8"), encoding="utf-8")

    passed = [r for r in rows if r["status"] == "PASS"]
    with latest_txt.open("w", encoding="utf-8") as f:
        for r in passed:
            f.write(
                f"{r['symbol']} trend_retest_session_v1 "
                f"ef={r['ema_fast']} es={r['ema_slow']} lb={r['lookback']} rt={r['retest']} "
                f"sl={r['sl_atr']} rr={r['rr']} cd={r['cooldown']} "
                f"| win={r['full_winrate']}% ret={r['full_return_pct_est']}% "
                f"| month+={r['month_pos']}/{r['month_pos']+r['month_neg']+r['month_zero']} "
                f"| roll+={r['roll_pos_share_pct']}%\n"
            )

    print("trend_retest stability sweep done")
    print(
        f"symbol={symbol} grid={args.grid_profile} max_bars={int(args.max_bars)} "
        f"tested={len(candidates)} full_good={len(full_rows)} roll_checked={len(rows)} pass={len(passed)}"
    )
    print(f"saved={out_csv}")
    print(f"latest_csv={latest_csv}")
    print(f"latest_txt={latest_txt}")
    if rows:
        print("top:")
        for r in rows[: min(10, len(rows))]:
            print(
                f"  {r['status']} ef={r['ema_fast']} lb={r['lookback']} rt={r['retest']} "
                f"sl={r['sl_atr']} rr={r['rr']} cd={r['cooldown']} "
                f"win={r['full_winrate']} ret={r['full_return_pct_est']} "
                f"m+={r['month_pos']}/{r['month_pos']+r['month_neg']+r['month_zero']} "
                f"r+={r['roll_pos_share_pct']} reason={r['reason']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
