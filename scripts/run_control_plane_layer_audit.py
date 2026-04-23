#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "stack_comparison_queue_20260423.json"
DEFAULT_POLICY = ROOT / "configs" / "portfolio_allocator_policy.json"
DEFAULT_REGISTRY = ROOT / "configs" / "strategy_profile_registry.json"
BACKTEST_RUNS = ROOT / "backtest_runs"


if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_stack_comparison_queue import (  # noqa: E402
    _best_strategy_only_row,
    _dynamic_summary,
    _load_json,
    _parse_command_option,
    _parse_overrides,
    _repo_python,
    _resolve,
    _slug,
    _write_json,
)


ALL_REGIMES = ("bull_trend", "bull_chop", "bear_chop", "bear_trend")
VARIANTS = (
    "fixed_all_regimes",
    "router_all_regimes",
    "fixed_policy",
    "full_stack",
)


def _csv_symbols(raw: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in str(raw or "").split(","):
        sym = item.strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def _policy_sleeves(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for sleeve in list(policy.get("sleeves") or []):
        name = str(sleeve.get("name") or "").strip()
        if name:
            out[name] = sleeve
    return out


def _command_symbols(spec: dict[str, Any]) -> list[str]:
    return _csv_symbols(_parse_command_option(list(spec.get("command") or []), "--symbols", ""))


def _variant_fixed_symbols(
    *,
    candidate: dict[str, Any],
    spec: dict[str, Any],
    strategy_row: dict[str, Any],
    sleeves_by_name: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    merged_env = dict(spec.get("base_env") or {})
    merged_env.update(_parse_overrides(strategy_row))
    fallback_symbols = _command_symbols(spec)
    out: dict[str, list[str]] = {}
    for sleeve_name in list(candidate.get("sleeves") or []):
        sleeve = sleeves_by_name[str(sleeve_name)]
        env_key = str(sleeve.get("symbol_env_key") or "").strip()
        if not env_key:
            continue
        symbols = _csv_symbols(str(merged_env.get(env_key) or ""))
        if not symbols:
            symbols = list(fallback_symbols)
        out[env_key] = symbols
    return out


def _health_candidate_only(policy: dict[str, Any], candidate: dict[str, Any], strategy_row: dict[str, Any]) -> dict[str, Any]:
    ok_strategies = {str(x) for x in list(candidate.get("strategies") or [])}
    strategies: dict[str, Any] = {}
    for sleeve in list(policy.get("sleeves") or []):
        for strategy in list(sleeve.get("strategy_names") or []):
            name = str(strategy or "").strip()
            if not name or name in strategies:
                continue
            is_ok = name in ok_strategies
            strategies[name] = {
                "status": "OK" if is_ok else "PAUSE",
                "total_pnl": float(strategy_row.get("net_pnl") or 0.0) if is_ok else 0.0,
                "rolling_30d_pnl": 0.0,
                "rolling_60d_pnl": 0.0,
                "curve_vs_ma20": 0.0,
                "trades_total": int(float(strategy_row.get("trades") or 0.0)) if is_ok else 0,
                "trades_30d": 0,
                "winrate_total": float(strategy_row.get("winrate") or 0.0) if is_ok else 0.0,
                "winrate_30d": 0.0,
                "pf_30d": 0.0,
                "notes": (
                    f"Layer audit candidate {candidate.get('id')}: enabled for isolated control-plane comparison."
                    if is_ok
                    else "Paused by layer audit harness."
                ),
            }
    return {
        "overall_health": "OK",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_dir": "control_plane_layer_audit",
        "strategies": strategies,
    }


def _flatten_policy_controls(policy: dict[str, Any]) -> None:
    policy["allocator_global_risk_by_regime"] = {regime: 1.0 for regime in ALL_REGIMES}
    policy["degraded_global_risk_mult"] = 1.0
    policy["safe_mode_global_risk_mult"] = 1.0
    policy["health_status_multipliers"] = {"OK": 1.0, "WATCH": 1.0, "PAUSE": 0.0, "KILL": 0.0}
    policy["symbol_count_multipliers"] = [
        {"max_count": 0, "mult": 0.0},
        {"max_count": 999, "mult": 1.0},
    ]


def _policy_variant(policy: dict[str, Any], *, target_sleeves: set[str], variant: str) -> dict[str, Any]:
    payload = copy.deepcopy(policy)
    if variant != "full_stack":
        _flatten_policy_controls(payload)

    for sleeve in list(payload.get("sleeves") or []):
        name = str(sleeve.get("name") or "").strip()
        base_map = dict(sleeve.get("base_risk_mult_by_regime") or {})
        if name not in target_sleeves:
            sleeve["base_risk_mult_by_regime"] = {regime: 0.0 for regime in ALL_REGIMES}
            continue
        if variant in {"fixed_all_regimes", "router_all_regimes"}:
            # Bypass regime overlay ENABLE_* kills so this variant truly measures
            # router/fixed-symbol impact without orchestrator disabling the sleeve.
            sleeve["enable_env"] = f"LAYER_AUDIT_FORCE_{_slug(name).upper()}"
            sleeve["base_risk_mult_by_regime"] = {regime: 1.0 for regime in ALL_REGIMES}
        elif variant == "fixed_policy":
            sleeve["base_risk_mult_by_regime"] = {
                regime: float(base_map.get(regime, 0.0) or 0.0) for regime in ALL_REGIMES
            }
    return payload


def _fixed_registry(
    *,
    fixed_symbols_by_env: dict[str, list[str]],
    tag: str,
) -> dict[str, Any]:
    profiles: list[dict[str, Any]] = []
    for env_key, symbols in fixed_symbols_by_env.items():
        profiles.append(
            {
                "profile_id": f"{tag}_{env_key.lower()}",
                "env_key": env_key,
                "active_regimes": ["*"],
                "fixed_symbols": list(symbols),
            }
        )
    return {
        "version": 1,
        "profile_version": f"layer-audit-{tag}",
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "profiles": profiles,
    }


def _run_variant(
    *,
    candidate: dict[str, Any],
    spec: dict[str, Any],
    strategy_row: dict[str, Any],
    config: dict[str, Any],
    policy_path: Path,
    registry_path: Path,
    health_path: Path,
    timeline_path: Path,
    output_root: Path,
    variant: str,
) -> Path:
    command = list(spec.get("command") or [])
    overrides = dict(spec.get("base_env") or {})
    overrides.update(_parse_overrides(strategy_row))

    max_positions = str(overrides.get("MAX_POSITIONS") or _parse_command_option(command, "--max_positions", "3"))
    end = str(config.get("end") or _parse_command_option(command, "--end", "2026-04-01"))
    total_days = str(config.get("total_days") or _parse_command_option(command, "--days", "360"))
    window_days = str(config.get("window_days") or 30)
    step_days = str(config.get("step_days") or window_days)
    starting_equity = _parse_command_option(command, "--starting_equity", "100")
    risk_pct = _parse_command_option(command, "--risk_pct", "0.01")
    leverage = _parse_command_option(command, "--leverage", "1")
    fee_bps = _parse_command_option(command, "--fee_bps", "6")
    slippage_bps = _parse_command_option(command, "--slippage_bps", "2")

    env = os.environ.copy()
    env.update({str(k): str(v) for k, v in overrides.items()})
    env["BACKTEST_CACHE_ONLY"] = str(spec.get("cache_only", True)).lower()
    env["BACKTEST_CACHE_FALLBACK_ENABLE"] = "1"

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = output_root / candidate["id"] / variant
    tag = f"layeraudit_{candidate['id']}_{variant}_{stamp}"
    log_path = output_root / candidate["id"] / f"{variant}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        _repo_python(),
        "scripts/run_dynamic_crypto_annual.py",
        "--end",
        end,
        "--total_days",
        total_days,
        "--window_days",
        window_days,
        "--step_days",
        step_days,
        "--policy",
        str(policy_path),
        "--registry",
        str(registry_path),
        "--health",
        str(health_path),
        "--health-timeline",
        str(timeline_path),
        "--max-scan-symbols",
        str(config.get("max_scan_symbols") or 80),
        "--starting_equity",
        starting_equity,
        "--base_risk_pct",
        risk_pct,
        "--leverage",
        leverage,
        "--max_positions",
        max_positions,
        "--fee_bps",
        fee_bps,
        "--slippage_bps",
        slippage_bps,
        "--tag",
        tag,
        "--out-dir",
        str(out_dir),
    ]
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    if proc.returncode != 0:
        raise RuntimeError(f"{candidate['id']} {variant} failed rc={proc.returncode}; see {log_path}")
    return out_dir


def _retention(strategy_value: float, variant_value: float) -> float:
    if abs(strategy_value) <= 1e-9:
        return 0.0
    return variant_value / strategy_value * 100.0


def _variant_notes(rows: dict[str, dict[str, Any]]) -> str:
    fixed_all = rows.get("fixed_all_regimes", {})
    router_all = rows.get("router_all_regimes", {})
    fixed_policy = rows.get("fixed_policy", {})
    full_stack = rows.get("full_stack", {})
    parts: list[str] = []
    if fixed_all and router_all:
        if float(router_all.get("trades", 0) or 0) < float(fixed_all.get("trades", 0) or 0) * 0.7:
            parts.append("router_cuts_frequency")
        if float(router_all.get("net_pnl", 0) or 0) < float(fixed_all.get("net_pnl", 0) or 0) * 0.5:
            parts.append("router_cuts_edge")
    if fixed_all and fixed_policy:
        if float(fixed_policy.get("trades", 0) or 0) < float(fixed_all.get("trades", 0) or 0) * 0.7:
            parts.append("regime_gating_cuts_frequency")
        if float(fixed_policy.get("net_pnl", 0) or 0) < float(fixed_all.get("net_pnl", 0) or 0) * 0.5:
            parts.append("regime_gating_cuts_edge")
    if fixed_policy and full_stack:
        if float(full_stack.get("net_pnl", 0) or 0) < float(fixed_policy.get("net_pnl", 0) or 0) * 0.5:
            parts.append("router_plus_stack_destroy_edge")
    return ",".join(parts) or "see_variant_table"


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit which control-plane layer is killing or helping a candidate.")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--only", default="impulse_ivb1,breakdown_v1,support_bounce")
    ap.add_argument("--variants", default="fixed_all_regimes,router_all_regimes,fixed_policy,full_stack")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    config = _load_json(_resolve(args.config))
    policy = _load_json(DEFAULT_POLICY)
    registry = _load_json(DEFAULT_REGISTRY)
    sleeves_by_name = _policy_sleeves(policy)

    only = {item.strip() for item in str(args.only or "").split(",") if item.strip()}
    variants = [item.strip() for item in str(args.variants or "").split(",") if item.strip()]
    for variant in variants:
        if variant not in VARIANTS:
            raise ValueError(f"Unsupported variant: {variant}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_root = BACKTEST_RUNS / f"control_plane_layer_audit_{stamp}"
    output_root.mkdir(parents=True, exist_ok=True)
    empty_timeline = output_root / "empty_strategy_health_timeline.json"
    _write_json(empty_timeline, {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "snapshots": []})

    summary_rows: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []

    for candidate in list(config.get("candidates") or []):
        candidate_id = str(candidate.get("id") or "").strip()
        if not candidate_id or (only and candidate_id not in only):
            continue
        spec = _load_json(_resolve(candidate["spec"]))
        strategy_row = _best_strategy_only_row(_resolve(candidate["spec"]))
        fixed_symbols = _variant_fixed_symbols(
            candidate=candidate,
            spec=spec,
            strategy_row=strategy_row,
            sleeves_by_name=sleeves_by_name,
        )
        target_sleeves = {str(x) for x in list(candidate.get("sleeves") or [])}
        health_path = output_root / candidate_id / "health.json"
        _write_json(health_path, _health_candidate_only(policy, candidate, strategy_row))

        candidate_variants: dict[str, dict[str, Any]] = {}
        for variant in variants:
            if args.dry_run:
                candidate_variants[variant] = {}
                continue
            policy_variant = _policy_variant(policy, target_sleeves=target_sleeves, variant=variant)
            registry_variant = (
                _fixed_registry(fixed_symbols_by_env=fixed_symbols, tag=f"{candidate_id}_{variant}")
                if variant in {"fixed_all_regimes", "fixed_policy"}
                else registry
            )
            policy_path = output_root / candidate_id / f"policy_{variant}.json"
            registry_path = output_root / candidate_id / f"registry_{variant}.json"
            _write_json(policy_path, policy_variant)
            _write_json(registry_path, registry_variant)
            run_dir = _run_variant(
                candidate=candidate,
                spec=spec,
                strategy_row=strategy_row,
                config=config,
                policy_path=policy_path,
                registry_path=registry_path,
                health_path=health_path,
                timeline_path=empty_timeline,
                output_root=output_root,
                variant=variant,
            )
            summary = _dynamic_summary(run_dir)
            summary["run_dir"] = str(run_dir)
            candidate_variants[variant] = summary
            print(
                f"[layeraudit] {candidate_id} {variant}: net={float(summary.get('net_pnl') or 0.0):+.2f} "
                f"pf={summary.get('profit_factor')} trades={int(summary.get('trades') or 0)} dd={float(summary.get('max_drawdown') or 0.0):.2f}",
                flush=True,
            )

        row = {
            "id": candidate_id,
            "label": candidate.get("label") or candidate_id,
            "strategy_only_net": float(strategy_row.get("net_pnl") or 0.0),
            "strategy_only_trades": int(float(strategy_row.get("trades") or 0.0)),
            "strategy_only_pf": float(strategy_row.get("profit_factor") or 0.0),
            "strategy_only_dd": float(strategy_row.get("max_drawdown") or 0.0),
            "variant_notes": _variant_notes(candidate_variants),
        }
        for variant in variants:
            summary = candidate_variants.get(variant, {})
            net = float(summary.get("net_pnl") or 0.0)
            trades = int(summary.get("trades") or 0)
            row[f"{variant}_net"] = net
            row[f"{variant}_trades"] = trades
            row[f"{variant}_pf"] = float(summary.get("profit_factor") or 0.0)
            row[f"{variant}_dd"] = float(summary.get("max_drawdown") or 0.0)
            row[f"{variant}_trade_retention_pct"] = round(_retention(row["strategy_only_trades"], trades), 2)
            row[f"{variant}_net_retention_pct"] = round(_retention(row["strategy_only_net"], net), 2)
        summary_rows.append(row)
        details.append(
            {
                "candidate": candidate,
                "spec": str(_resolve(candidate["spec"])),
                "strategy_only": strategy_row,
                "fixed_symbols": fixed_symbols,
                "variants": candidate_variants,
                "row": row,
            }
        )

    summary_json = output_root / "summary.json"
    _write_json(summary_json, {"rows": summary_rows, "details": details})

    summary_csv = output_root / "summary.csv"
    fields = [
        "id",
        "label",
        "strategy_only_net",
        "strategy_only_trades",
        "strategy_only_pf",
        "strategy_only_dd",
        "fixed_all_regimes_net",
        "fixed_all_regimes_trades",
        "fixed_all_regimes_trade_retention_pct",
        "fixed_all_regimes_net_retention_pct",
        "router_all_regimes_net",
        "router_all_regimes_trades",
        "router_all_regimes_trade_retention_pct",
        "router_all_regimes_net_retention_pct",
        "fixed_policy_net",
        "fixed_policy_trades",
        "fixed_policy_trade_retention_pct",
        "fixed_policy_net_retention_pct",
        "full_stack_net",
        "full_stack_trades",
        "full_stack_trade_retention_pct",
        "full_stack_net_retention_pct",
        "variant_notes",
    ]
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in summary_rows:
            writer.writerow({field: row.get(field, "") for field in fields})

    report = output_root / "report.md"
    lines = [
        "# Control-Plane Layer Audit",
        "",
        "Variants:",
        "- `fixed_all_regimes`: fixed symbols from strategy-only winner, sleeve enabled in all regimes.",
        "- `router_all_regimes`: router keeps choosing symbols, but sleeve allowed in all regimes.",
        "- `fixed_policy`: fixed symbols, but original regime sleeve policy kept.",
        "- `full_stack`: original router + original regime policy.",
        "",
        "| Candidate | Fixed all | Router all | Fixed policy | Full stack | Notes |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in summary_rows:
        lines.append(
            f"| {row['label']} | net {row.get('fixed_all_regimes_net', 0):+.2f}, tr {row.get('fixed_all_regimes_trades', 0)} | "
            f"net {row.get('router_all_regimes_net', 0):+.2f}, tr {row.get('router_all_regimes_trades', 0)} | "
            f"net {row.get('fixed_policy_net', 0):+.2f}, tr {row.get('fixed_policy_trades', 0)} | "
            f"net {row.get('full_stack_net', 0):+.2f}, tr {row.get('full_stack_trades', 0)} | "
            f"{row.get('variant_notes', '')} |"
        )
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"summary_csv={summary_csv}")
    print(f"summary_json={summary_json}")
    print(f"report={report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
