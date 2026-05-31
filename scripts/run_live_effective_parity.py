#!/usr/bin/env python3
"""Run a backtest using the currently effective live allocator universe.

This is a guard against the worst failure mode for this project: live stays
silent while a nearby backtest would have traded. The script intentionally does
not print secrets from .env; it only forwards loaded values to the child
backtest process.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SLEEVE_STRATEGY = {
    "bounce1": "alt_support_bounce_v1",
    "att1": "alt_trendline_touch_v1",
    "sloped": "alt_sloped_channel_v1",
    "midterm": "btc_eth_midterm_pullback",
    "asm1": "alt_sloped_momentum_v1",
    "asb1": "alt_slope_break_v1",
    "impulse": "impulse_volume_breakout_v1",
    "breakout": "inplay_breakout",
    "flat": "alt_resistance_fade_v1",
    "breakdown": "alt_inplay_breakdown_v1",
}

SLEEVE_RISK_ENV = {
    "bounce1": "BOUNCE1_RISK_MULT",
    "att1": "ATT1_RISK_MULT",
    "sloped": "SLOPED_RISK_MULT",
    "midterm": "MIDTERM_RISK_MULT",
    "asm1": "ASM1_RISK_MULT",
    "asb1": "ASB1_RISK_MULT",
    "impulse": "IVB1_RISK_MULT",
    "breakout": "BREAKOUT_RISK_MULT",
    "flat": "FLAT_RISK_MULT",
    "breakdown": "BREAKDOWN_RISK_MULT",
}


def _clean_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    loaded: dict[str, str] = {}
    for raw in path.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or re.search(r"\s", key):
            continue
        loaded[key] = _clean_env_value(value)
    return loaded


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def _active_sleeves(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    active = state.get("active_sleeves") or state.get("sleeves") or {}
    if isinstance(active, list):
        out: dict[str, dict[str, Any]] = {}
        for item in active:
            if not isinstance(item, dict):
                continue
            name = str(item.get("sleeve") or item.get("name") or "").strip()
            if name:
                out[name] = item
        return out
    if isinstance(active, dict):
        return {str(k): v for k, v in active.items() if isinstance(v, dict)}
    return {}


def _health_allowed(health: str, health_filter: str) -> bool:
    normalized = (health or "").strip().upper()
    health_filter = (health_filter or "all").strip().lower()
    if health_filter == "all":
        return True
    if health_filter == "ok":
        return normalized == "OK"
    if health_filter in {"ok-watch", "ok_watch"}:
        return normalized in {"OK", "WATCH"}
    raise ValueError(f"Unsupported health_filter: {health_filter}")


def _resolve_repo_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def build_live_effective_inputs(
    root: Path,
    health_filter: str = "all",
    *,
    env_paths: list[str] | None = None,
    allocator_state_path: str | None = None,
) -> tuple[list[str], list[str], dict[str, str], list[dict[str, Any]]]:
    env: dict[str, str] = {}
    paths = env_paths or [
        ".env",
        "configs/dynamic_allowlist_latest.env",
        "configs/regime_overlay_bull_chop.env",
        "runtime/control_plane/portfolio_allocator_latest.env",
    ]
    for rel in paths:
        env.update(load_env_file(_resolve_repo_path(root, rel)))

    state_path = _resolve_repo_path(
        root,
        allocator_state_path or "runtime/control_plane/portfolio_allocator_state.json",
    )
    state = json.loads(state_path.read_text())
    active = _active_sleeves(state)

    symbols: list[str] = []
    strategies: list[str] = []
    rows: list[dict[str, Any]] = []

    for sleeve, cfg in active.items():
        runtime = str(cfg.get("runtime") or cfg.get("status") or cfg.get("health_status") or "").lower()
        if cfg.get("enabled") is False or runtime in {"off", "disabled", "rejected"}:
            continue

        strategy = SLEEVE_STRATEGY.get(sleeve)
        if not strategy:
            continue
        health = str(cfg.get("health") or cfg.get("health_status") or cfg.get("status") or "")
        if not _health_allowed(health, health_filter):
            continue

        strategies.append(strategy)
        sleeve_symbols = _as_list(cfg.get("symbols") or cfg.get("symbol_allowlist"))
        for symbol in sleeve_symbols:
            if symbol not in symbols:
                symbols.append(symbol)

        risk = (
            cfg.get("final_risk_mult")
            or cfg.get("risk_mult")
            or cfg.get("risk_multiplier")
            or cfg.get("effective_risk_mult")
        )
        risk_env = SLEEVE_RISK_ENV.get(sleeve)
        if risk is not None and risk_env:
            env[risk_env] = str(risk)

        rows.append(
            {
                "sleeve": sleeve,
                "strategy": strategy,
                "risk": risk,
                "symbols": sleeve_symbols,
                "runtime": cfg.get("runtime") or cfg.get("status") or cfg.get("health_status"),
                "health": health,
            }
        )

    return symbols, strategies, env, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--days", type=int, default=15)
    parser.add_argument("--end", default="")
    parser.add_argument("--starting-equity", type=float, default=100.0)
    parser.add_argument("--risk-pct", type=float, default=0.01)
    parser.add_argument("--leverage", type=float, default=3.0)
    parser.add_argument("--max-positions", type=int, default=3)
    parser.add_argument("--fee-bps", type=float, default=6.0)
    parser.add_argument("--slippage-bps", type=float, default=2.0)
    parser.add_argument("--tag", default="live_effective_parity")
    parser.add_argument("--health-filter", choices=["all", "ok", "ok-watch"], default=os.getenv("LIVE_EFFECTIVE_HEALTH_FILTER", "all"))
    parser.add_argument(
        "--env-path",
        action="append",
        dest="env_paths",
        help="Env overlay path to load. Repeat to replace the default live env overlay list.",
    )
    parser.add_argument(
        "--allocator-state",
        default="runtime/control_plane/portfolio_allocator_state.json",
        help="Allocator state JSON to use for sleeve/symbol inputs.",
    )
    parser.add_argument("--print-only", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    symbols, strategies, loaded_env, rows = build_live_effective_inputs(
        root,
        health_filter=args.health_filter,
        env_paths=args.env_paths,
        allocator_state_path=args.allocator_state,
    )
    if not symbols or not strategies:
        print("NO_ACTIVE_STRATEGIES_OR_SYMBOLS")
        return 2

    print("LIVE_EFFECTIVE_PARITY_INPUT")
    print(f"health_filter={args.health_filter}")
    for row in rows:
        sample = ",".join(row["symbols"][:8])
        print(
            f"  {row['sleeve']} -> {row['strategy']} "
            f"risk={row['risk']} runtime={row['runtime']} symbols={sample}"
        )
    print(f"symbols={len(symbols)} strategies={len(strategies)}")
    print("strategies_csv=" + ",".join(strategies))

    cmd = [
        sys.executable,
        "backtest/run_portfolio.py",
        "--symbols",
        ",".join(symbols),
        "--strategies",
        ",".join(strategies),
        "--days",
        str(args.days),
        "--starting_equity",
        str(args.starting_equity),
        "--risk_pct",
        str(args.risk_pct),
        "--leverage",
        str(args.leverage),
        "--max_positions",
        str(args.max_positions),
        "--fee_bps",
        str(args.fee_bps),
        "--slippage_bps",
        str(args.slippage_bps),
        "--tag",
        args.tag,
    ]
    if args.end:
        cmd.extend(["--end", args.end])

    if args.print_only:
        print(" ".join(cmd))
        return 0

    child_env = os.environ.copy()
    child_env.update(loaded_env)
    child_env["BACKTEST_CACHE_ONLY"] = "0"
    child_env["BACKTEST_CACHE_FALLBACK_ENABLE"] = "1"
    child_env["PYTHONUNBUFFERED"] = "1"

    print("RUNNING_BACKTEST...")
    return subprocess.call(cmd, cwd=root, env=child_env)


if __name__ == "__main__":
    raise SystemExit(main())
