#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex.data import load_m5_csv
from forex.engine import EngineConfig, run_backtest
from forex.types import Candle
from scripts.run_forex_multi_strategy_gate import _build_strategy, _default_pip_size, _default_spread, _default_swap


def _utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _utc_day(ts: int) -> int:
    return ts // 86400


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


def _parse_combo(s: str) -> Tuple[str, str]:
    raw = s.strip()
    if "@" not in raw:
        raise ValueError(f"Bad combo format (expected PAIR@strategy:preset): {raw}")
    pair, strategy = raw.split("@", 1)
    pair = pair.strip().upper()
    strategy = strategy.strip()
    if not pair or not strategy:
        raise ValueError(f"Bad combo format (empty pair/strategy): {raw}")
    return pair, strategy


@dataclass
class HealthRow:
    pair: str
    strategy: str
    windows: int
    both_positive_windows: int
    both_positive_share_pct: float
    total_base_net_pips: float
    total_stress_net_pips: float
    avg_stress_per_window: float
    status: str
    reason: str


def main() -> int:
    ap = argparse.ArgumentParser(description="Rolling health check for current ACTIVE forex combos.")
    ap.add_argument("--active-combos-txt", default="docs/forex_live_active_combos_latest.txt")
    ap.add_argument("--data-dir", default="data_cache/forex")
    ap.add_argument("--window-days", type=int, default=28)
    ap.add_argument("--step-days", type=int, default=7)
    ap.add_argument("--min-bars", type=int, default=600)
    ap.add_argument("--session-start-utc", type=int, default=6)
    ap.add_argument("--session-end-utc", type=int, default=20)
    ap.add_argument("--stress-spread-mult", type=float, default=1.5)
    ap.add_argument("--stress-swap-mult", type=float, default=1.5)
    ap.add_argument("--min-both-positive-share-pct", type=float, default=55.0)
    ap.add_argument("--min-total-stress-pips", type=float, default=0.0)
    ap.add_argument("--out-prefix", default="docs/forex_active_health_latest")
    args = ap.parse_args()

    active_path = (ROOT / args.active_combos_txt).resolve()
    if not active_path.exists():
        raise SystemExit(f"active combos file not found: {active_path}")
    combos_raw = active_path.read_text(encoding="utf-8").strip()
    combos = [x.strip() for x in combos_raw.split(",") if x.strip()]
    if not combos:
        raise SystemExit("No active combos found")

    data_dir = (ROOT / args.data_dir).resolve()

    rows: List[HealthRow] = []
    for combo in combos:
        pair, strategy_name = _parse_combo(combo)
        csv_path = data_dir / f"{pair}_M5.csv"
        if not csv_path.exists():
            rows.append(
                HealthRow(
                    pair=pair,
                    strategy=strategy_name,
                    windows=0,
                    both_positive_windows=0,
                    both_positive_share_pct=0.0,
                    total_base_net_pips=0.0,
                    total_stress_net_pips=0.0,
                    avg_stress_per_window=0.0,
                    status="FAIL",
                    reason="missing_csv",
                )
            )
            continue

        candles = load_m5_csv(str(csv_path))
        segs = _rolling_segments(
            candles=candles,
            window_days=max(7, int(args.window_days)),
            step_days=max(1, int(args.step_days)),
            min_bars=max(1, int(args.min_bars)),
        )
        if not segs:
            rows.append(
                HealthRow(
                    pair=pair,
                    strategy=strategy_name,
                    windows=0,
                    both_positive_windows=0,
                    both_positive_share_pct=0.0,
                    total_base_net_pips=0.0,
                    total_stress_net_pips=0.0,
                    avg_stress_per_window=0.0,
                    status="FAIL",
                    reason="no_segments",
                )
            )
            continue

        pip_size = _default_pip_size(pair)
        base_spread = _default_spread(pair)
        base_swap = _default_swap(pair)
        stress_spread = base_spread * float(args.stress_spread_mult)
        stress_swap = base_swap * float(args.stress_swap_mult)

        base_cfg = EngineConfig(
            pip_size=pip_size,
            spread_pips=base_spread,
            swap_long_pips_per_day=base_swap,
            swap_short_pips_per_day=base_swap,
        )
        stress_cfg = EngineConfig(
            pip_size=pip_size,
            spread_pips=stress_spread,
            swap_long_pips_per_day=stress_swap,
            swap_short_pips_per_day=stress_swap,
        )

        base_total = 0.0
        stress_total = 0.0
        both_pos = 0
        for _, seg in segs:
            base_st = _build_strategy(
                strategy_name,
                session_start=int(args.session_start_utc),
                session_end=int(args.session_end_utc),
            )
            _, bs = run_backtest(seg, base_st, base_cfg)

            stress_st = _build_strategy(
                strategy_name,
                session_start=int(args.session_start_utc),
                session_end=int(args.session_end_utc),
            )
            _, ss = run_backtest(seg, stress_st, stress_cfg)

            b = float(bs.net_pips)
            s = float(ss.net_pips)
            base_total += b
            stress_total += s
            if b > 0 and s > 0:
                both_pos += 1

        windows = len(segs)
        both_share = both_pos / windows * 100.0 if windows else 0.0
        avg_stress = stress_total / windows if windows else 0.0

        fail_reasons: List[str] = []
        if both_share < float(args.min_both_positive_share_pct):
            fail_reasons.append("low_both_positive_share")
        if stress_total < float(args.min_total_stress_pips):
            fail_reasons.append("negative_total_stress")
        status = "OK" if not fail_reasons else "WARN"

        rows.append(
            HealthRow(
                pair=pair,
                strategy=strategy_name,
                windows=windows,
                both_positive_windows=both_pos,
                both_positive_share_pct=both_share,
                total_base_net_pips=base_total,
                total_stress_net_pips=stress_total,
                avg_stress_per_window=avg_stress,
                status=status,
                reason=";".join(fail_reasons) if fail_reasons else "healthy",
            )
        )

    rows.sort(key=lambda r: (0 if r.status == "OK" else 1, -r.total_stress_net_pips, r.pair, r.strategy))

    out_csv = (ROOT / f"{args.out_prefix}.csv").resolve()
    out_txt = (ROOT / f"{args.out_prefix}.txt").resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "pair",
                "strategy",
                "status",
                "reason",
                "windows",
                "both_positive_windows",
                "both_positive_share_pct",
                "total_base_net_pips",
                "total_stress_net_pips",
                "avg_stress_per_window",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r.pair,
                    r.strategy,
                    r.status,
                    r.reason,
                    r.windows,
                    r.both_positive_windows,
                    f"{r.both_positive_share_pct:.2f}",
                    f"{r.total_base_net_pips:.4f}",
                    f"{r.total_stress_net_pips:.4f}",
                    f"{r.avg_stress_per_window:.4f}",
                ]
            )

    lines = []
    for r in rows:
        lines.append(
            f"{r.status} {r.pair}@{r.strategy} | both+ {r.both_positive_windows}/{r.windows} ({r.both_positive_share_pct:.1f}%) "
            f"| stress_total={r.total_stress_net_pips:.2f} | avg_win={r.avg_stress_per_window:.2f} | {r.reason}"
        )
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("forex active health check done")
    print(f"combos={len(rows)}")
    print(f"out_csv={out_csv}")
    print(f"out_txt={out_txt}")
    for r in rows:
        print(
            f"{r.status} {r.pair}@{r.strategy} "
            f"both+={r.both_positive_windows}/{r.windows} "
            f"stress_total={r.total_stress_net_pips:.2f} reason={r.reason}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
