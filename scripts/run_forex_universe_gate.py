#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PRESETS: Dict[str, Dict[str, float | int]] = {
    "conservative": {
        "ema_fast": 55,
        "ema_slow": 220,
        "breakout_lookback": 42,
        "retest_window_bars": 8,
        "sl_atr_mult": 1.4,
        "rr": 2.5,
        "cooldown_bars": 32,
    },
    "balanced": {
        "ema_fast": 48,
        "ema_slow": 200,
        "breakout_lookback": 36,
        "retest_window_bars": 6,
        "sl_atr_mult": 1.5,
        "rr": 2.2,
        "cooldown_bars": 24,
    },
    "active": {
        "ema_fast": 34,
        "ema_slow": 144,
        "breakout_lookback": 24,
        "retest_window_bars": 5,
        "sl_atr_mult": 1.6,
        "rr": 1.9,
        "cooldown_bars": 14,
    },
}


def _default_spread(pair: str) -> float:
    p = pair.upper()
    if p.endswith("JPY"):
        return 1.0
    if p in {"EURUSD", "USDCHF"}:
        return 1.0
    if p in {"GBPUSD", "GBPAUD", "GBPJPY", "GBPCHF", "GBPCAD"}:
        return 1.2
    if p in {"AUDUSD", "USDCAD", "NZDUSD", "EURGBP", "EURJPY", "AUDJPY", "CADJPY", "CHFJPY"}:
        return 1.3
    return 1.5


def _default_swap(pair: str) -> float:
    p = pair.upper()
    if p in {"EURUSD", "USDJPY", "USDCHF"}:
        return -0.3
    if p in {"GBPUSD", "GBPJPY", "GBPAUD", "GBPCHF", "GBPCAD"}:
        return -0.4
    return -0.35


@dataclass
class RunRow:
    pair: str
    preset: str
    cost: str
    status: str
    trades: int
    winrate: float
    net_pips: float
    gross_pips: float
    max_dd_pips: float
    run_dir: str
    error: str


@dataclass
class RecentStats:
    net_pips: float
    trades: int
    winrate: float
    status: str


def _run_one(
    *,
    pair: str,
    preset: str,
    cost: str,
    csv_path: Path,
    spread: float,
    swap_long: float,
    swap_short: float,
    session_start_utc: int,
    session_end_utc: int,
    out_dir: Path,
) -> RunRow:
    cfg = PRESETS[preset]
    tag = f"gate_{pair}_{preset}_{cost}"
    log = out_dir / f"{pair}_{preset}_{cost}.log"

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_forex_backtest.py"),
        "--symbol",
        pair,
        "--csv",
        str(csv_path),
        "--tag",
        tag,
        "--spread_pips",
        str(spread),
        "--swap_long",
        str(swap_long),
        "--swap_short",
        str(swap_short),
        "--session_start_utc",
        str(session_start_utc),
        "--session_end_utc",
        str(session_end_utc),
        "--ema_fast",
        str(int(cfg["ema_fast"])),
        "--ema_slow",
        str(int(cfg["ema_slow"])),
        "--breakout_lookback",
        str(int(cfg["breakout_lookback"])),
        "--retest_window_bars",
        str(int(cfg["retest_window_bars"])),
        "--sl_atr_mult",
        str(float(cfg["sl_atr_mult"])),
        "--rr",
        str(float(cfg["rr"])),
        "--cooldown_bars",
        str(int(cfg["cooldown_bars"])),
    ]

    with log.open("w", encoding="utf-8") as lf:
        proc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(ROOT), text=True)

    if proc.returncode != 0:
        err = ""
        try:
            lines = log.read_text(encoding="utf-8", errors="ignore").splitlines()
            err = lines[-1] if lines else f"exit={proc.returncode}"
        except Exception:
            err = f"exit={proc.returncode}"
        return RunRow(pair, preset, cost, "fail", 0, 0.0, 0.0, 0.0, 0.0, "", err.replace(",", ";"))

    run_dir = ""
    try:
        for line in log.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("saved="):
                run_dir = line.split("=", 1)[1].strip()
        if not run_dir:
            run_dir = str(next((ROOT / "backtest_runs").glob(f"forex_{tag}_{pair}")))
    except Exception:
        pass

    if not run_dir:
        return RunRow(pair, preset, cost, "fail", 0, 0.0, 0.0, 0.0, 0.0, "", "run_dir_not_found")

    summary_csv = Path(run_dir) / "summary.csv"
    if not summary_csv.exists():
        return RunRow(pair, preset, cost, "fail", 0, 0.0, 0.0, 0.0, 0.0, run_dir, "summary_missing")

    with summary_csv.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        row = next(r, None)
    if not row:
        return RunRow(pair, preset, cost, "fail", 0, 0.0, 0.0, 0.0, 0.0, run_dir, "summary_empty")

    return RunRow(
        pair=pair,
        preset=preset,
        cost=cost,
        status="ok",
        trades=int(float(row.get("trades") or 0)),
        winrate=float(row.get("winrate") or 0.0),
        net_pips=float(row.get("net_pips") or 0.0),
        gross_pips=float(row.get("gross_pips") or 0.0),
        max_dd_pips=float(row.get("max_dd_pips") or 0.0),
        run_dir=run_dir,
        error="",
    )


def _recent_stats(run_dir: str, recent_days: int) -> RecentStats:
    if recent_days <= 0:
        return RecentStats(net_pips=0.0, trades=0, winrate=0.0, status="disabled")

    trades_csv = Path(run_dir) / "trades.csv"
    if not trades_csv.exists():
        return RecentStats(net_pips=0.0, trades=0, winrate=0.0, status="missing_trades_csv")

    rows: List[Tuple[int, float]] = []
    with trades_csv.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                ts = int(float(row.get("entry_ts") or 0))
                net = float(row.get("net_pips") or 0.0)
            except Exception:
                continue
            rows.append((ts, net))

    if not rows:
        return RecentStats(net_pips=0.0, trades=0, winrate=0.0, status="no_trades")

    max_ts = max(ts for ts, _ in rows)
    cutoff = max_ts - int(recent_days) * 86400
    recent = [(ts, net) for ts, net in rows if ts >= cutoff]
    if not recent:
        return RecentStats(net_pips=0.0, trades=0, winrate=0.0, status="empty_recent_window")

    trades = len(recent)
    net_pips = sum(net for _, net in recent)
    wins = sum(1 for _, net in recent if net > 0)
    winrate = wins / trades if trades else 0.0
    return RecentStats(net_pips=net_pips, trades=trades, winrate=winrate, status="ok")


def main() -> int:
    ap = argparse.ArgumentParser(description="Scan Forex universe and select dynamic candidate pairs.")
    ap.add_argument(
        "--pairs",
        default="EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,EURGBP,EURJPY,GBPJPY,AUDJPY,CADJPY",
    )
    ap.add_argument("--presets", default="conservative")
    ap.add_argument("--data-dir", default="data_cache/forex")
    ap.add_argument("--session-start-utc", type=int, default=6)
    ap.add_argument("--session-end-utc", type=int, default=20)
    ap.add_argument("--stress-spread-mult", type=float, default=1.5)
    ap.add_argument("--stress-swap-mult", type=float, default=1.5)

    ap.add_argument("--min-base-net", type=float, default=0.0)
    ap.add_argument("--min-stress-net", type=float, default=0.0)
    ap.add_argument("--min-trades", type=int, default=40)
    ap.add_argument("--max-stress-dd", type=float, default=300.0)
    ap.add_argument("--recent-days", type=int, default=28)
    ap.add_argument("--min-recent-base-net", type=float, default=0.0)
    ap.add_argument("--min-recent-stress-net", type=float, default=0.0)
    ap.add_argument("--min-recent-trades", type=int, default=8)
    ap.add_argument("--top-n", type=int, default=6)

    ap.add_argument("--tag", default="fx_gate")
    args = ap.parse_args()

    pairs = [p.strip().upper() for p in args.pairs.split(",") if p.strip()]
    presets = [p.strip().lower() for p in args.presets.split(",") if p.strip()]
    for p in presets:
        if p not in PRESETS:
            raise SystemExit(f"Unsupported preset '{p}'. Allowed: {sorted(PRESETS.keys())}")

    out_dir = ROOT / "backtest_runs" / f"forex_universe_gate_{args.tag}_{datetime_utc_compact()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: List[RunRow] = []
    data_dir = (ROOT / args.data_dir).resolve()
    print(f"forex universe gate start")
    print(f"pairs={','.join(pairs)}")
    print(f"presets={','.join(presets)}")
    print(f"data_dir={data_dir}")
    print(
        f"recent_gate=days:{int(args.recent_days)} "
        f"min_recent_base_net:{float(args.min_recent_base_net):.2f} "
        f"min_recent_stress_net:{float(args.min_recent_stress_net):.2f} "
        f"min_recent_trades:{int(args.min_recent_trades)}"
    )
    print(f"out_dir={out_dir}")

    for pair in pairs:
        csv_path = data_dir / f"{pair}_M5.csv"
        if not csv_path.exists():
            rows.append(RunRow(pair, "-", "base", "skip", 0, 0.0, 0.0, 0.0, 0.0, "", "missing_csv"))
            continue
        base_spread = _default_spread(pair)
        base_swap = _default_swap(pair)
        for preset in presets:
            base_row = _run_one(
                pair=pair,
                preset=preset,
                cost="base",
                csv_path=csv_path,
                spread=base_spread,
                swap_long=base_swap,
                swap_short=base_swap,
                session_start_utc=args.session_start_utc,
                session_end_utc=args.session_end_utc,
                out_dir=out_dir,
            )
            rows.append(base_row)

            stress_row = _run_one(
                pair=pair,
                preset=preset,
                cost="stress",
                csv_path=csv_path,
                spread=base_spread * float(args.stress_spread_mult),
                swap_long=base_swap * float(args.stress_swap_mult),
                swap_short=base_swap * float(args.stress_swap_mult),
                session_start_utc=args.session_start_utc,
                session_end_utc=args.session_end_utc,
                out_dir=out_dir,
            )
            rows.append(stress_row)

    raw_csv = out_dir / "raw_runs.csv"
    with raw_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "pair",
                "preset",
                "cost",
                "status",
                "trades",
                "winrate",
                "net_pips",
                "gross_pips",
                "max_dd_pips",
                "run_dir",
                "error",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r.pair,
                    r.preset,
                    r.cost,
                    r.status,
                    r.trades,
                    f"{r.winrate:.4f}",
                    f"{r.net_pips:.4f}",
                    f"{r.gross_pips:.4f}",
                    f"{r.max_dd_pips:.4f}",
                    r.run_dir,
                    r.error,
                ]
            )

    grouped: Dict[Tuple[str, str], Dict[str, RunRow]] = {}
    for r in rows:
        if r.status != "ok":
            continue
        grouped.setdefault((r.pair, r.preset), {})[r.cost] = r

    gated_rows = []
    for (pair, preset), d in grouped.items():
        if "base" not in d or "stress" not in d:
            continue
        b = d["base"]
        s = d["stress"]
        b_recent = _recent_stats(b.run_dir, int(args.recent_days))
        s_recent = _recent_stats(s.run_dir, int(args.recent_days))
        recent_ok = (
            int(args.recent_days) <= 0
            or (
                b_recent.status == "ok"
                and s_recent.status == "ok"
                and b_recent.net_pips >= float(args.min_recent_base_net)
                and s_recent.net_pips >= float(args.min_recent_stress_net)
                and min(b_recent.trades, s_recent.trades) >= int(args.min_recent_trades)
            )
        )
        ok = (
            b.net_pips >= float(args.min_base_net)
            and s.net_pips >= float(args.min_stress_net)
            and min(b.trades, s.trades) >= int(args.min_trades)
            and s.max_dd_pips <= float(args.max_stress_dd)
            and recent_ok
        )
        gated_rows.append(
            {
                "pair": pair,
                "preset": preset,
                "base_net_pips": b.net_pips,
                "stress_net_pips": s.net_pips,
                "base_trades": b.trades,
                "stress_trades": s.trades,
                "base_dd_pips": b.max_dd_pips,
                "stress_dd_pips": s.max_dd_pips,
                "recent_base_net_pips": b_recent.net_pips,
                "recent_stress_net_pips": s_recent.net_pips,
                "recent_base_trades": b_recent.trades,
                "recent_stress_trades": s_recent.trades,
                "recent_base_winrate": b_recent.winrate,
                "recent_stress_winrate": s_recent.winrate,
                "recent_base_status": b_recent.status,
                "recent_stress_status": s_recent.status,
                "pass_gate": 1 if ok else 0,
            }
        )

    gated_rows.sort(key=lambda x: (x["pass_gate"], x["stress_net_pips"]), reverse=True)
    gated_csv = out_dir / "gated_summary.csv"
    with gated_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "pair",
                "preset",
                "base_net_pips",
                "stress_net_pips",
                "base_trades",
                "stress_trades",
                "base_dd_pips",
                "stress_dd_pips",
                "recent_base_net_pips",
                "recent_stress_net_pips",
                "recent_base_trades",
                "recent_stress_trades",
                "recent_base_winrate",
                "recent_stress_winrate",
                "recent_base_status",
                "recent_stress_status",
                "pass_gate",
            ]
        )
        for r in gated_rows:
            w.writerow(
                [
                    r["pair"],
                    r["preset"],
                    f"{r['base_net_pips']:.4f}",
                    f"{r['stress_net_pips']:.4f}",
                    r["base_trades"],
                    r["stress_trades"],
                    f"{r['base_dd_pips']:.4f}",
                    f"{r['stress_dd_pips']:.4f}",
                    f"{r['recent_base_net_pips']:.4f}",
                    f"{r['recent_stress_net_pips']:.4f}",
                    r["recent_base_trades"],
                    r["recent_stress_trades"],
                    f"{r['recent_base_winrate']:.4f}",
                    f"{r['recent_stress_winrate']:.4f}",
                    r["recent_base_status"],
                    r["recent_stress_status"],
                    r["pass_gate"],
                ]
            )

    selected = [r for r in gated_rows if r["pass_gate"] == 1][: max(1, int(args.top_n))]
    selected_txt = out_dir / "selected_pairs.txt"
    selected_csv = out_dir / "selected_pairs.csv"
    with selected_txt.open("w", encoding="utf-8") as f:
        f.write(",".join([str(r["pair"]) for r in selected]))
    with selected_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "pair",
                "preset",
                "stress_net_pips",
                "stress_trades",
                "stress_dd_pips",
                "recent_stress_net_pips",
                "recent_stress_trades",
                "recent_stress_winrate",
            ]
        )
        for r in selected:
            w.writerow(
                [
                    r["pair"],
                    r["preset"],
                    f"{r['stress_net_pips']:.4f}",
                    r["stress_trades"],
                    f"{r['stress_dd_pips']:.4f}",
                    f"{r['recent_stress_net_pips']:.4f}",
                    r["recent_stress_trades"],
                    f"{r['recent_stress_winrate']:.4f}",
                ]
            )

    print("")
    print("=== GATE PASS (stress net desc) ===")
    for r in selected:
        print(
            f"{r['pair']:>8} {r['preset']:>12} "
            f"base={r['base_net_pips']:.2f} stress={r['stress_net_pips']:.2f} "
            f"recent_stress={r['recent_stress_net_pips']:.2f} "
            f"recent_trades={r['recent_stress_trades']} "
            f"trades={r['stress_trades']} dd={r['stress_dd_pips']:.2f}"
        )
    if not selected:
        print("no pairs passed current gate")

    print("")
    print(f"raw={raw_csv}")
    print(f"gated={gated_csv}")
    print(f"selected={selected_csv}")
    print(f"selected_pairs_txt={selected_txt}")
    return 0


def datetime_utc_compact() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


if __name__ == "__main__":
    raise SystemExit(main())
