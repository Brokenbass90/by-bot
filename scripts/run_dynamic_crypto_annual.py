#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.metrics import Trade, summarize_trades  # noqa: E402
from bot.strategy_health_timeline import load_strategy_health_timeline, select_health_snapshot  # noqa: E402
from scripts.build_regime_state import (  # noqa: E402
    _apply_decision_softeners,
    _classify_regime,
    _fetch_4h,
)
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
    _parse_env,
    _parse_end_date_utc,
)


RUN_PORTFOLIO = ROOT / "backtest" / "run_portfolio.py"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
BACKTEST_RUNS = ROOT / "backtest_runs"
DEFAULT_BASE_ENV = ROOT / "configs" / "server_clean.env"


def _parse_date(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def _fmt_date(value: dt.date) -> str:
    return value.strftime("%Y-%m-%d")


def _default_out_dir(tag: str) -> Path:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    return BACKTEST_RUNS / f"dynamic_annual_{ts}_{tag}"


def _resolve_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


def _build_windows(*, end_date: dt.date, total_days: int, window_days: int, step_days: int) -> List[tuple[dt.date, dt.date]]:
    if total_days < window_days:
        raise ValueError("total_days must be >= window_days")
    if step_days != window_days:
        raise ValueError("stitched dynamic annual requires non-overlapping windows: step_days must equal window_days")
    start_anchor = end_date - dt.timedelta(days=total_days)
    windows: List[tuple[dt.date, dt.date]] = []
    cursor = start_anchor + dt.timedelta(days=window_days)
    while cursor <= end_date:
        window_end = cursor
        window_start = window_end - dt.timedelta(days=window_days)
        windows.append((window_start, window_end))
        cursor += dt.timedelta(days=step_days)
    return windows


def _find_run_dir(tag: str) -> Path:
    matches = sorted(BACKTEST_RUNS.glob(f"portfolio_*_{tag}"))
    if not matches:
        raise FileNotFoundError(f"No run dir found for tag={tag}")
    return matches[-1]


def _load_summary(run_dir: Path) -> Dict[str, Any]:
    summary_path = run_dir / "summary.csv"
    with summary_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"Empty summary.csv in {run_dir}")
    row = rows[0]
    pf_raw = str(row.get("profit_factor", "0") or "0").strip().lower()
    pf = float("inf") if pf_raw == "inf" else float(pf_raw or 0.0)
    return {
        "tag": row.get("tag", ""),
        "days": int(float(row.get("days", 0) or 0)),
        "end_date_utc": row.get("end_date_utc", ""),
        "trades": int(float(row.get("trades", 0) or 0)),
        "net_pnl": float(row.get("net_pnl", 0.0) or 0.0),
        "profit_factor": pf,
        "winrate": float(row.get("winrate", 0.0) or 0.0),
        "max_drawdown": float(row.get("max_drawdown", 0.0) or 0.0),
        "starting_equity": float(row.get("starting_equity", 0.0) or 0.0),
        "ending_equity": float(row.get("ending_equity", 0.0) or 0.0),
        "symbols": str(row.get("symbols", "") or ""),
        "strategies": str(row.get("strategies", "") or ""),
    }


def _load_trades(run_dir: Path) -> List[Trade]:
    trades_path = run_dir / "trades.csv"
    with trades_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    trades: List[Trade] = []
    for row in rows:
        trades.append(
            Trade(
                strategy=str(row["strategy"]),
                symbol=str(row["symbol"]),
                side=str(row["side"]),
                entry_ts=int(float(row["entry_ts"])),
                exit_ts=int(float(row["exit_ts"])),
                entry_price=float(row["entry_price"]),
                exit_price=float(row["exit_price"]),
                qty=float(row["qty"]),
                pnl=float(row["pnl"]),
                pnl_pct_equity=float(row["pnl_pct_equity"]),
                fees=float(row["fees"]),
                reason=str(row["reason"]),
                outcome=str(row["outcome"]),
            )
        )
    return trades


def _write_env_file(path: Path, env_map: Dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in sorted(env_map.items())]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _month_key(ts: int) -> str:
    ts_i = int(ts)
    if ts_i > 10_000_000_000:
        ts_i = ts_i // 1000
    return dt.datetime.fromtimestamp(ts_i, tz=dt.timezone.utc).strftime("%Y-%m")


def _monthly_returns(trades: List[Trade], starting_equity: float) -> List[Dict[str, Any]]:
    ordered = sorted(trades, key=lambda t: (int(t.exit_ts), int(t.entry_ts)))
    if not ordered:
        return []
    current_equity = float(starting_equity)
    current_month = _month_key(ordered[0].exit_ts)
    month_start_equity = current_equity
    month_trades = 0
    rows: List[Dict[str, Any]] = []
    for trade in ordered:
        trade_month = _month_key(trade.exit_ts)
        if trade_month != current_month:
            month_end_equity = current_equity
            ret_pct = ((month_end_equity - month_start_equity) / max(1e-9, month_start_equity)) * 100.0
            rows.append(
                {
                    "month": current_month,
                    "starting_equity": round(month_start_equity, 4),
                    "ending_equity": round(month_end_equity, 4),
                    "return_pct": round(ret_pct, 4),
                    "trades": month_trades,
                }
            )
            current_month = trade_month
            month_start_equity = current_equity
            month_trades = 0
        current_equity += float(trade.pnl)
        month_trades += 1
    month_end_equity = current_equity
    ret_pct = ((month_end_equity - month_start_equity) / max(1e-9, month_start_equity)) * 100.0
    rows.append(
        {
            "month": current_month,
            "starting_equity": round(month_start_equity, 4),
            "ending_equity": round(month_end_equity, 4),
            "return_pct": round(ret_pct, 4),
            "trades": month_trades,
        }
    )
    return rows


def _risk_multiplier_product(decision: Dict[str, Any], allocator: Dict[str, Any]) -> float:
    orch_mult = float(decision.get("global_risk_mult", 1.0) or 1.0)
    alloc_mult = float(allocator.get("allocator_global_risk_mult", 1.0) or 1.0)
    return max(0.0, orch_mult * alloc_mult)


def _build_window_env(
    *,
    base_env: Dict[str, str],
    decision: Dict[str, Any],
    router_state: Dict[str, Any],
    allocator_state: Dict[str, Any],
) -> Dict[str, str]:
    env = dict(base_env)
    overrides = dict(decision.get("overrides") or {})
    env.update({str(k): str(v) for k, v in overrides.items()})
    env["ORCH_GLOBAL_RISK_MULT"] = str(decision.get("global_risk_mult", 1.0))
    env["ALLOCATOR_GLOBAL_RISK_MULT"] = str(allocator_state.get("allocator_global_risk_mult", 1.0))
    env["PORTFOLIO_ALLOCATOR_ENABLE"] = "1"
    env["ALLOCATOR_ENABLE"] = "1"
    env["ALLOCATOR_HARD_BLOCK_NEW_ENTRIES"] = "1" if bool(allocator_state.get("hard_block_new_entries")) else "0"
    env["BACKTEST_CACHE_ONLY"] = "1"
    env["BACKTEST_CACHE_FALLBACK_ENABLE"] = "1"
    for env_key, info in dict(router_state.get("profiles") or {}).items():
        symbols = [str(sym).strip().upper() for sym in (info.get("symbols") or []) if str(sym).strip()]
        env[str(env_key)] = ",".join(symbols)
    for sleeve in dict(allocator_state.get("sleeves") or {}).values():
        env[str(sleeve["enable_env"])] = "1" if bool(sleeve.get("enabled")) else "0"
        env[str(sleeve["risk_env"])] = f"{float(sleeve.get('final_risk_mult', 0.0) or 0.0):.4f}"
    return env


def _active_package(
    policy: Dict[str, Any],
    allocator_state: Dict[str, Any],
    router_state: Dict[str, Any],
) -> tuple[List[str], List[str], List[str]]:
    sleeves_by_name = {
        str(item.get("name") or "").strip(): dict(item)
        for item in list(policy.get("sleeves") or [])
        if str(item.get("name") or "").strip()
    }
    router_profiles = dict(router_state.get("profiles") or {})
    enabled_sleeves: List[str] = []
    strategies: List[str] = []
    symbols: List[str] = []
    seen_strategies: set[str] = set()
    seen_symbols: set[str] = set()
    for name, sleeve_state in dict(allocator_state.get("sleeves") or {}).items():
        if not bool(sleeve_state.get("enabled")):
            continue
        policy_item = sleeves_by_name.get(str(name))
        if policy_item is None:
            continue
        enabled_sleeves.append(str(name))
        for strategy_name in policy_item.get("strategy_names") or []:
            st = str(strategy_name or "").strip()
            if st and st not in seen_strategies:
                seen_strategies.add(st)
                strategies.append(st)
        symbol_env_key = str(policy_item.get("symbol_env_key") or "").strip()
        router_symbols = []
        if symbol_env_key:
            router_symbols = list((router_profiles.get(symbol_env_key) or {}).get("symbols") or [])
        for sym in router_symbols:
            s = str(sym or "").strip().upper()
            if s and s not in seen_symbols:
                seen_symbols.add(s)
                symbols.append(s)
    return enabled_sleeves, strategies, symbols


def _run_window(
    *,
    run_tag: str,
    symbols: List[str],
    strategies: List[str],
    window_days: int,
    window_end: dt.date,
    starting_equity: float,
    risk_pct: float,
    leverage: float,
    max_positions: int,
    fee_bps: float,
    slippage_bps: float,
    env_map: Dict[str, str],
) -> Path:
    if not VENV_PYTHON.exists():
        raise FileNotFoundError(f"Missing virtualenv python: {VENV_PYTHON}")
    cmd = [
        str(VENV_PYTHON),
        str(RUN_PORTFOLIO),
        "--symbols",
        ",".join(symbols),
        "--strategies",
        ",".join(strategies),
        "--days",
        str(window_days),
        "--end",
        _fmt_date(window_end),
        "--tag",
        run_tag,
        "--starting_equity",
        f"{starting_equity:.8f}",
        "--risk_pct",
        f"{risk_pct:.8f}",
        "--leverage",
        str(leverage),
        "--max_positions",
        str(max_positions),
        "--fee_bps",
        str(fee_bps),
        "--slippage_bps",
        str(slippage_bps),
    ]
    env = dict(os.environ)
    env.update(env_map)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.run(cmd, cwd=str(ROOT), env=env, check=True)
    return _find_run_dir(run_tag)


def _write_outputs(
    out_dir: Path,
    *,
    args: argparse.Namespace,
    window_rows: List[Dict[str, Any]],
    all_trades: List[Trade],
    all_trade_rows: List[Dict[str, Any]],
    starting_equity: float,
    ending_equity: float,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    windows_csv = out_dir / "dynamic_windows.csv"
    with windows_csv.open("w", newline="", encoding="utf-8") as f:
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
                "run_dir",
            ],
        )
        writer.writeheader()
        for row in window_rows:
            writer.writerow(row)

    stitched_trades_csv = out_dir / "stitched_trades.csv"
    with stitched_trades_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "window_index",
                "regime",
                "strategy",
                "symbol",
                "side",
                "entry_ts",
                "exit_ts",
                "entry_price",
                "exit_price",
                "qty",
                "pnl",
                "pnl_pct_equity",
                "fees",
                "outcome",
                "reason",
            ],
        )
        writer.writeheader()
        for row in all_trade_rows:
            writer.writerow(row)

    equity_curve = [float(starting_equity)]
    running_equity = float(starting_equity)
    for trade in sorted(all_trades, key=lambda t: (int(t.exit_ts), int(t.entry_ts))):
        running_equity += float(trade.pnl)
        equity_curve.append(running_equity)
    overall = summarize_trades(all_trades, equity_curve)
    monthly = _monthly_returns(all_trades, float(starting_equity))

    monthly_csv = out_dir / "stitched_monthly_returns.csv"
    with monthly_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["month", "starting_equity", "ending_equity", "return_pct", "trades"],
        )
        writer.writeheader()
        for row in monthly:
            writer.writerow(row)

    regime_counts = Counter(str(row["regime"]) for row in window_rows)
    allocator_counts = Counter(str(row["allocator_status"]) for row in window_rows)
    sleeve_counts = Counter()
    for row in window_rows:
        for sleeve in str(row["enabled_sleeves"]).split(";"):
            sleeve_name = sleeve.strip()
            if sleeve_name:
                sleeve_counts[sleeve_name] += 1

    neg_months = sum(1 for row in monthly if float(row["return_pct"]) < 0.0)
    ret_pct = ((float(ending_equity) - float(starting_equity)) / max(1e-9, float(starting_equity))) * 100.0
    summary = {
        "tag": args.tag,
        "end": args.end,
        "total_days": int(args.total_days),
        "window_days": int(args.window_days),
        "historical_hold_cycles": int(args.historical_hold_cycles),
        "windows": len(window_rows),
        "starting_equity": round(float(starting_equity), 4),
        "ending_equity": round(float(ending_equity), 4),
        "net_pnl": round(float(ending_equity) - float(starting_equity), 4),
        "return_pct": round(ret_pct, 4),
        "trades": int(overall.trades),
        "winrate": round(float(overall.winrate), 4),
        "profit_factor": ("inf" if not math.isfinite(float(overall.profit_factor)) else round(float(overall.profit_factor), 4)),
        "max_drawdown": round(float(overall.max_drawdown), 4),
        "negative_months": int(neg_months),
        "regime_counts": dict(regime_counts),
        "allocator_status_counts": dict(allocator_counts),
        "sleeve_enable_counts": dict(sleeve_counts),
        "windows_csv": str(windows_csv),
        "stitched_trades_csv": str(stitched_trades_csv),
        "monthly_returns_csv": str(monthly_csv),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    report = out_dir / "report.md"
    with report.open("w", encoding="utf-8") as f:
        f.write(f"# Dynamic Crypto Annual Harness: {args.tag}\n\n")
        f.write(f"- End date: `{args.end}`\n")
        f.write(f"- Horizon: `{args.total_days}` days\n")
        f.write(f"- Window size: `{args.window_days}` days\n")
        f.write(f"- Historical hold cycles: `{int(args.historical_hold_cycles)}`\n")
        f.write(f"- Windows: `{len(window_rows)}`\n")
        f.write(f"- Starting equity: `{starting_equity:.2f}`\n")
        f.write(f"- Ending equity: `{ending_equity:.2f}`\n")
        f.write(f"- Return: `{ret_pct:.2f}%`\n")
        f.write(f"- Trades: `{overall.trades}`\n")
        f.write(f"- PF: `{overall.profit_factor:.3f}`\n" if math.isfinite(float(overall.profit_factor)) else "- PF: `inf`\n")
        f.write(f"- Winrate: `{overall.winrate:.3f}`\n")
        f.write(f"- Max DD: `{overall.max_drawdown:.2f}%`\n")
        f.write(f"- Negative months: `{neg_months}`\n\n")
        f.write("## Window Regimes\n\n")
        for regime, count in sorted(regime_counts.items()):
            f.write(f"- `{regime}`: `{count}`\n")
        f.write("\n## Windows\n\n")
        for row in window_rows:
            f.write(
                f"- `{row['window_start']} -> {row['window_end']}` | "
                f"regime `{row['regime']}` | allocator `{row['allocator_status']}` | "
                f"net `{float(row['net_pnl']):.2f}` | PF `{float(row['profit_factor']):.3f}` | "
                f"DD `{float(row['max_drawdown']):.2f}` | sleeves `{row['enabled_sleeves'] or '-'}`\n"
            )


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a stitched annual backtest of the dynamic crypto system.")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--total_days", type=int, default=360)
    ap.add_argument("--window_days", type=int, default=30)
    ap.add_argument("--step_days", type=int, default=30)
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
    ap.add_argument("--tag", default="dynamic_crypto_annual")
    ap.add_argument("--out-dir", default="")
    ap.add_argument(
        "--historical-hold-cycles",
        type=int,
        default=1,
        help="Hysteresis cycles for stitched historical windows. Default 1 because monthly windows should not inherit live hourly hold=3.",
    )
    args = ap.parse_args()

    end_date = _parse_date(args.end)
    end_dt = _parse_end_date_utc(args.end)
    windows = _build_windows(
        end_date=end_date,
        total_days=int(args.total_days),
        window_days=int(args.window_days),
        step_days=int(args.step_days),
    )

    base_env_path = _resolve_path(args.base_env_file)
    base_env = _parse_env(base_env_path)

    registry = _load_json(_resolve_path(args.registry), {})
    policy = _load_json(_resolve_path(args.policy), {})
    fallback_health = _load_json(_resolve_path(args.health), {})
    health_timeline = load_strategy_health_timeline(_resolve_path(args.health_timeline))
    symbol_memory = _load_json(_resolve_path(args.symbol_memory), {})

    if not VENV_PYTHON.exists():
        raise FileNotFoundError(f"Missing virtualenv python: {VENV_PYTHON}")

    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir(args.tag)
    out_dir.mkdir(parents=True, exist_ok=True)

    applied_regime: str | None = None
    pending_regime: str | None = None
    pending_count = 0
    current_equity = float(args.starting_equity)
    window_rows: List[Dict[str, Any]] = []
    all_trades: List[Trade] = []
    all_trade_rows: List[Dict[str, Any]] = []

    for idx, (window_start, window_end) in enumerate(windows, start=1):
        checkpoint_dt = dt.datetime.combine(window_end, dt.time(23, 59, 59), tzinfo=dt.timezone.utc)
        checkpoint_ms = int(checkpoint_dt.timestamp() * 1000)
        checkpoint_ts = int(checkpoint_dt.timestamp())
        candles = _fetch_4h("BTCUSDT", 120, end_ms=checkpoint_ms, cache_only=True)
        if len(candles) < 60:
            raise RuntimeError(f"Insufficient BTC data for {window_end}: got {len(candles)} bars")
        raw_regime, indicators = _classify_regime(candles)
        applied_regime, pending_regime, pending_count, regime_changed = _advance_hysteresis(
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

        risk_mult = _risk_multiplier_product(decision, allocator_state)
        risk_pct_eff = float(args.base_risk_pct) * float(risk_mult)
        window_row: Dict[str, Any] = {
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
            "starting_equity": round(current_equity, 4),
            "ending_equity": round(current_equity, 4),
            "trades": 0,
            "net_pnl": 0.0,
            "profit_factor": 0.0,
            "winrate": 0.0,
            "max_drawdown": 0.0,
            "hard_block": bool(allocator_state.get("hard_block_new_entries")),
            "run_dir": "",
        }

        if strategies and symbols and not bool(allocator_state.get("hard_block_new_entries")):
            run_tag = f"{args.tag}_w{idx:02d}_{window_end.strftime('%Y%m%d')}"
            env_path = out_dir / "window_env" / f"{run_tag}.env"
            _write_env_file(env_path, env_map)
            run_dir = _run_window(
                run_tag=run_tag,
                symbols=symbols,
                strategies=strategies,
                window_days=int(args.window_days),
                window_end=window_end,
                starting_equity=current_equity,
                risk_pct=risk_pct_eff,
                leverage=float(args.leverage),
                max_positions=int(args.max_positions),
                fee_bps=float(args.fee_bps),
                slippage_bps=float(args.slippage_bps),
                env_map=env_map,
            )
            summary = _load_summary(run_dir)
            trades = _load_trades(run_dir)
            current_equity = float(summary["ending_equity"])
            window_row.update(
                {
                    "ending_equity": round(current_equity, 4),
                    "trades": int(summary["trades"]),
                    "net_pnl": round(float(summary["net_pnl"]), 4),
                    "profit_factor": round(float(summary["profit_factor"]), 4) if math.isfinite(float(summary["profit_factor"])) else "inf",
                    "winrate": round(float(summary["winrate"]), 4),
                    "max_drawdown": round(float(summary["max_drawdown"]), 4),
                    "run_dir": str(run_dir),
                }
            )
            all_trades.extend(trades)
            for trade in trades:
                all_trade_rows.append(
                    {
                        "window_index": idx,
                        "regime": applied_regime,
                        "strategy": trade.strategy,
                        "symbol": trade.symbol,
                        "side": trade.side,
                        "entry_ts": trade.entry_ts,
                        "exit_ts": trade.exit_ts,
                        "entry_price": f"{trade.entry_price:.8f}",
                        "exit_price": f"{trade.exit_price:.8f}",
                        "qty": f"{trade.qty:.8f}",
                        "pnl": f"{trade.pnl:.8f}",
                        "pnl_pct_equity": f"{trade.pnl_pct_equity:.6f}",
                        "fees": f"{trade.fees:.8f}",
                        "outcome": trade.outcome,
                        "reason": trade.reason,
                    }
                )
            print(
                f"[{idx}/{len(windows)}] {run_tag} regime={applied_regime} "
                f"pf={summary['profit_factor']:.3f} net={summary['net_pnl']:.2f} "
                f"dd={summary['max_drawdown']:.2f} trades={summary['trades']} "
                f"sleeves={','.join(enabled_sleeves) or '-'}"
            )
        else:
            if bool(allocator_state.get("hard_block_new_entries")):
                reason = "hard_block"
            elif not strategies:
                reason = "no_enabled_strategies"
            else:
                reason = "no_symbols"
            window_row["run_dir"] = reason
            print(
                f"[{idx}/{len(windows)}] skip {window_end} regime={applied_regime} "
                f"reason={reason} sleeves={','.join(enabled_sleeves) or '-'}"
            )
        window_rows.append(window_row)

    _write_outputs(
        out_dir,
        args=args,
        window_rows=window_rows,
        all_trades=all_trades,
        all_trade_rows=all_trade_rows,
        starting_equity=float(args.starting_equity),
        ending_equity=float(current_equity),
    )
    print(f"dynamic annual harness complete: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
