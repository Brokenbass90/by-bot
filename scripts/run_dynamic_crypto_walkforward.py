#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.strategy_health_timeline import load_strategy_health_timeline, select_health_snapshot  # noqa: E402
from scripts.build_regime_state import _apply_decision_softeners, _classify_regime, _fetch_4h  # noqa: E402
from scripts.run_control_plane_replay import (  # noqa: E402
    DEFAULT_HEALTH,
    DEFAULT_HEALTH_TIMELINE,
    DEFAULT_POLICY,
    DEFAULT_REGISTRY,
    DEFAULT_SYMBOL_MEMORY,
    _advance_hysteresis,
    _build_router_state,
    _compute_allocator_snapshot,
    _historical_scan,
    _load_json,
    _parse_end_date_utc,
    _parse_env,
)
from scripts.run_dynamic_crypto_annual import (  # noqa: E402
    DEFAULT_BASE_ENV,
    _active_package,
    _build_window_env,
    _find_run_dir,
    _fmt_date,
    _load_summary,
    _merge_runtime_env_overrides,
    _resolve_path,
    _run_window,
)


BACKTEST_RUNS = ROOT / "backtest_runs"


def _parse_date(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def _default_out_dir(tag: str) -> Path:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    return BACKTEST_RUNS / f"dynamic_walkforward_{ts}_{tag}"


def _build_windows(*, end_date: dt.date, total_days: int, window_days: int, step_days: int) -> List[tuple[dt.date, dt.date]]:
    if total_days < window_days:
        raise ValueError("total_days must be >= window_days")
    if step_days <= 0:
        raise ValueError("step_days must be > 0")
    start_anchor = end_date - dt.timedelta(days=total_days)
    windows: List[tuple[dt.date, dt.date]] = []
    cursor = start_anchor + dt.timedelta(days=window_days)
    while cursor <= end_date:
        window_end = cursor
        window_start = window_end - dt.timedelta(days=window_days)
        windows.append((window_start, window_end))
        cursor += dt.timedelta(days=step_days)
    return windows


def _write_outputs(out_dir: Path, *, args: argparse.Namespace, rows: List[Dict[str, Any]], current_equity: float) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "walkforward_windows.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "window_index",
                "window_start",
                "window_end",
                "regime",
                "raw_regime",
                "allocator_status",
                "enabled_sleeves",
                "strategies",
                "symbols",
                "risk_pct_effective",
                "starting_equity",
                "ending_equity",
                "trades",
                "net_pnl",
                "profit_factor",
                "winrate",
                "max_drawdown",
                "hard_block",
                "passed",
                "run_dir",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    total = len(rows)
    passed = sum(1 for row in rows if bool(row["passed"]))
    avg_pf = 0.0
    avg_net = 0.0
    avg_dd = 0.0
    avg_wr = 0.0
    tradeful = 0
    regime_counts = Counter()
    allocator_counts = Counter()
    sleeve_counts = Counter()
    for row in rows:
        pf = row["profit_factor"]
        if isinstance(pf, str):
            pf_val = float("inf") if pf == "inf" else 0.0
        else:
            pf_val = float(pf)
        if math.isfinite(pf_val):
            avg_pf += pf_val
            tradeful += 1
        avg_net += float(row["net_pnl"])
        avg_dd += float(row["max_drawdown"])
        avg_wr += float(row["winrate"])
        regime_counts[str(row["regime"])] += 1
        allocator_counts[str(row["allocator_status"])] += 1
        for sleeve in str(row["enabled_sleeves"]).split(";"):
            sleeve_name = sleeve.strip()
            if sleeve_name:
                sleeve_counts[sleeve_name] += 1

    latest = {
        "tag": args.tag,
        "windows": total,
        "passed": passed,
        "pass_ratio": round((passed / total) if total else 0.0, 4),
        "avg_pf": round(avg_pf / max(1, tradeful), 4) if tradeful else 0.0,
        "avg_net_pnl": round(avg_net / max(1, total), 4),
        "avg_winrate": round(avg_wr / max(1, total), 4),
        "avg_max_drawdown": round(avg_dd / max(1, total), 4),
        "carry_equity": bool(args.carry_equity),
        "ending_equity": round(float(current_equity), 4),
        "regime_counts": dict(regime_counts),
        "allocator_status_counts": dict(allocator_counts),
        "sleeve_enable_counts": dict(sleeve_counts),
        "csv": str(csv_path),
    }
    (out_dir / "walkforward_latest.json").write_text(json.dumps(latest, indent=2), encoding="utf-8")

    report_path = out_dir / "walkforward_report.md"
    with report_path.open("w", encoding="utf-8") as f:
        f.write(f"# Dynamic Crypto Walk-Forward: {args.tag}\n\n")
        f.write(f"- End date: `{args.end}`\n")
        f.write(f"- Total horizon: `{args.total_days}` days\n")
        f.write(f"- Window: `{args.window_days}` days\n")
        f.write(f"- Step: `{args.step_days}` days\n")
        f.write(f"- Historical hold cycles: `{int(args.historical_hold_cycles)}`\n")
        f.write(f"- Carry equity: `{bool(args.carry_equity)}`\n")
        f.write(
            f"- Pass rule: PF >= `{args.min_pf}` and net >= `{args.min_net}` and DD <= `{args.max_dd}`"
            f" and trades >= `{args.min_trades}`\n\n"
        )
        f.write("## Aggregate\n\n")
        f.write(f"- Windows: `{total}`\n")
        f.write(f"- Passed: `{passed}` / `{total}`\n")
        f.write(f"- Pass ratio: `{(passed / total) if total else 0.0:.3f}`\n")
        f.write(f"- Avg PF: `{(avg_pf / max(1, tradeful)) if tradeful else 0.0:.3f}`\n")
        f.write(f"- Avg net PnL: `{avg_net / max(1, total):.2f}`\n")
        f.write(f"- Avg winrate: `{avg_wr / max(1, total):.3f}`\n")
        f.write(f"- Avg DD: `{avg_dd / max(1, total):.2f}`\n")
        if bool(args.carry_equity):
            f.write(f"- Ending carry equity: `{float(current_equity):.2f}`\n")
        f.write("\n## Regime counts\n\n")
        for regime, count in sorted(regime_counts.items()):
            f.write(f"- `{regime}`: `{count}`\n")
        f.write("\n## Windows\n\n")
        for row in rows:
            pf = row["profit_factor"]
            pf_txt = pf if isinstance(pf, str) else f"{float(pf):.3f}"
            f.write(
                f"- `{row['window_start']} -> {row['window_end']}` | "
                f"regime `{row['regime']}` | allocator `{row['allocator_status']}` | "
                f"sleeves `{row['enabled_sleeves'] or '-'}` | "
                f"net `{float(row['net_pnl']):.2f}` | PF `{pf_txt}` | "
                f"DD `{float(row['max_drawdown']):.2f}` | "
                f"trades `{int(row['trades'])}` | pass `{bool(row['passed'])}`\n"
            )


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a dynamic full-stack walk-forward backtest of the crypto system.")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--total_days", type=int, default=360)
    ap.add_argument("--window_days", type=int, default=45)
    ap.add_argument("--step_days", type=int, default=15)
    ap.add_argument("--base-env-file", default=str(DEFAULT_BASE_ENV))
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    ap.add_argument("--policy", default=str(DEFAULT_POLICY))
    ap.add_argument("--health", default=str(DEFAULT_HEALTH))
    ap.add_argument("--health-timeline", default=str(DEFAULT_HEALTH_TIMELINE))
    ap.add_argument("--symbol-memory", default=str(DEFAULT_SYMBOL_MEMORY))
    ap.add_argument("--max-scan-symbols", type=int, default=80)
    ap.add_argument("--starting_equity", type=float, default=100.0)
    ap.add_argument("--base_risk_pct", type=float, default=0.01)
    ap.add_argument("--leverage", type=float, default=3.0)
    ap.add_argument("--max_positions", type=int, default=5)
    ap.add_argument("--fee_bps", type=float, default=6.0)
    ap.add_argument("--slippage_bps", type=float, default=2.0)
    ap.add_argument("--historical-hold-cycles", type=int, default=1)
    ap.add_argument("--min_pf", type=float, default=1.20)
    ap.add_argument("--min_net", type=float, default=0.0)
    ap.add_argument("--max_dd", type=float, default=12.0)
    ap.add_argument("--min_trades", type=int, default=8)
    ap.add_argument("--carry-equity", action="store_true", help="Carry ending equity across windows instead of resetting each window.")
    ap.add_argument("--tag", default="dynamic_crypto_walkforward")
    ap.add_argument("--out-dir", default="")
    args = ap.parse_args()

    end_date = _parse_date(args.end)
    windows = _build_windows(
        end_date=end_date,
        total_days=int(args.total_days),
        window_days=int(args.window_days),
        step_days=int(args.step_days),
    )

    base_env = _merge_runtime_env_overrides(_parse_env(_resolve_path(args.base_env_file)))
    registry = _load_json(_resolve_path(args.registry), {})
    policy = _load_json(_resolve_path(args.policy), {})
    fallback_health = _load_json(_resolve_path(args.health), {})
    health_timeline = load_strategy_health_timeline(_resolve_path(args.health_timeline))
    symbol_memory = _load_json(_resolve_path(args.symbol_memory), {})

    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir(args.tag)
    out_dir.mkdir(parents=True, exist_ok=True)

    applied_regime: str | None = None
    pending_regime: str | None = None
    pending_count = 0
    current_equity = float(args.starting_equity)
    rows: List[Dict[str, Any]] = []

    for idx, (window_start, window_end) in enumerate(windows, start=1):
        checkpoint_dt = dt.datetime.combine(window_end, dt.time(23, 59, 59), tzinfo=dt.timezone.utc)
        checkpoint_ms = int(checkpoint_dt.timestamp() * 1000)
        checkpoint_ts = int(checkpoint_dt.timestamp())
        candles = _fetch_4h("BTCUSDT", 120, end_ms=checkpoint_ms, cache_only=True)
        if len(candles) < 60:
            raise RuntimeError(f"Insufficient BTC data for {window_end}: got {len(candles)} bars")
        raw_regime, indicators = _classify_regime(candles)
        applied_regime, pending_regime, pending_count, _ = _advance_hysteresis(
            raw_regime=raw_regime,
            applied_regime=applied_regime,
            pending_regime=pending_regime,
            pending_count=pending_count,
            min_hold_cycles=max(1, int(args.historical_hold_cycles)),
        )
        decision = _apply_decision_softeners(applied_regime, indicators)
        scan = _historical_scan(checkpoint_ms, max_scan_symbols=int(args.max_scan_symbols))
        router_state = _build_router_state(
            regime=applied_regime,
            registry=registry,
            base_overlay=base_env,
            router_mode="historical_scan",
            historical_scan=scan,
            symbol_memory=symbol_memory,
        )
        health_snapshot = select_health_snapshot(health_timeline, checkpoint_ts, fallback_health=fallback_health)
        allocator_state = _compute_allocator_snapshot(
            regime=applied_regime,
            router_state=router_state,
            health=health_snapshot,
            policy=policy,
            base_env=base_env,
        )
        enabled_sleeves, strategies, symbols = _active_package(policy, allocator_state, router_state)
        env_map = _build_window_env(
            base_env=base_env,
            decision=decision,
            router_state=router_state,
            allocator_state=allocator_state,
        )
        risk_mult = float(decision.get("global_risk_mult", 1.0) or 1.0) * float(
            allocator_state.get("allocator_global_risk_mult", 1.0) or 1.0
        )
        risk_mult = max(0.0, float(risk_mult))
        risk_pct_eff = float(args.base_risk_pct) * risk_mult
        window_starting_equity = current_equity if bool(args.carry_equity) else float(args.starting_equity)
        row: Dict[str, Any] = {
            "window_index": idx,
            "window_start": _fmt_date(window_start),
            "window_end": _fmt_date(window_end),
            "regime": applied_regime,
            "raw_regime": raw_regime,
            "allocator_status": str(allocator_state.get("status") or "unknown"),
            "enabled_sleeves": ";".join(enabled_sleeves),
            "strategies": ";".join(strategies),
            "symbols": ";".join(symbols),
            "risk_pct_effective": round(risk_pct_eff, 6),
            "starting_equity": round(window_starting_equity, 4),
            "ending_equity": round(window_starting_equity, 4),
            "trades": 0,
            "net_pnl": 0.0,
            "profit_factor": 0.0,
            "winrate": 0.0,
            "max_drawdown": 0.0,
            "hard_block": bool(allocator_state.get("hard_block_new_entries")),
            "passed": False,
            "run_dir": "",
        }

        if strategies and symbols and not bool(allocator_state.get("hard_block_new_entries")):
            run_tag = f"{args.tag}_w{idx:02d}_{window_end.strftime('%Y%m%d')}"
            run_dir = _run_window(
                run_tag=run_tag,
                symbols=symbols,
                strategies=strategies,
                window_days=int(args.window_days),
                window_end=window_end,
                starting_equity=window_starting_equity,
                risk_pct=risk_pct_eff,
                leverage=float(args.leverage),
                max_positions=int(args.max_positions),
                fee_bps=float(args.fee_bps),
                slippage_bps=float(args.slippage_bps),
                env_map=env_map,
            )
            summary = _load_summary(run_dir)
            pf_val = float(summary["profit_factor"])
            passed = (
                summary["trades"] >= int(args.min_trades)
                and pf_val >= float(args.min_pf)
                and float(summary["net_pnl"]) >= float(args.min_net)
                and float(summary["max_drawdown"]) <= float(args.max_dd)
            )
            row.update(
                {
                    "ending_equity": round(float(summary["ending_equity"]), 4),
                    "trades": int(summary["trades"]),
                    "net_pnl": round(float(summary["net_pnl"]), 4),
                    "profit_factor": round(pf_val, 4) if math.isfinite(pf_val) else "inf",
                    "winrate": round(float(summary["winrate"]), 4),
                    "max_drawdown": round(float(summary["max_drawdown"]), 4),
                    "passed": bool(passed),
                    "run_dir": str(run_dir),
                }
            )
            if bool(args.carry_equity):
                current_equity = float(summary["ending_equity"])
            print(
                f"[{idx}/{len(windows)}] {run_tag} regime={applied_regime} "
                f"pf={pf_val:.3f} net={float(summary['net_pnl']):.2f} "
                f"dd={float(summary['max_drawdown']):.2f} trades={int(summary['trades'])} "
                f"pass={bool(passed)} sleeves={','.join(enabled_sleeves) or '-'}"
            )
        else:
            reason = "hard_block" if bool(allocator_state.get("hard_block_new_entries")) else (
                "no_enabled_strategies" if not strategies else "no_symbols"
            )
            row["run_dir"] = reason
            print(
                f"[{idx}/{len(windows)}] skip {window_end} regime={applied_regime} "
                f"reason={reason} sleeves={','.join(enabled_sleeves) or '-'}"
            )
        rows.append(row)

    _write_outputs(out_dir, args=args, rows=rows, current_equity=current_equity)
    print(f"dynamic walk-forward complete: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
