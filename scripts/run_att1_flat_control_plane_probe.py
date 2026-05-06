#!/usr/bin/env python3
from __future__ import annotations

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
BACKTEST_RUNS = ROOT / "backtest_runs"
DEFAULT_POLICY = ROOT / "configs" / "portfolio_allocator_policy.json"
DEFAULT_REGISTRY = ROOT / "configs" / "strategy_profile_registry.json"
DEFAULT_QUEUE = ROOT / "configs" / "stack_comparison_queue_20260423.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_stack_comparison_queue import (  # noqa: E402
    _best_strategy_only_row,
    _load_json,
    _parse_overrides,
    _repo_python,
    _resolve,
    _write_json,
)


ALL_REGIMES = ("bull_trend", "bull_chop", "bear_chop", "bear_trend")
CORE_STRATEGIES = {"alt_trendline_touch_v1", "alt_resistance_fade_v1"}
CORE_SLEEVES = {"att1", "flat"}
FIXED_SYMBOLS = {
    "ATT1_SYMBOL_ALLOWLIST": [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "LINKUSDT",
        "LTCUSDT",
        "ADAUSDT",
        "DOTUSDT",
        "SUIUSDT",
    ],
    "ARF1_SYMBOL_ALLOWLIST": ["LINKUSDT", "LTCUSDT", "SUIUSDT", "ADAUSDT", "DOTUSDT"],
}


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _candidate_map() -> dict[str, dict[str, Any]]:
    queue = _load_json(DEFAULT_QUEUE)
    return {str(item.get("id")): dict(item) for item in queue.get("candidates") or []}


def _core_health(policy: dict[str, Any]) -> dict[str, Any]:
    candidates = _candidate_map()
    att1_row = _best_strategy_only_row(_resolve(candidates["att1"]["spec"]))
    flat_row = _best_strategy_only_row(_resolve(candidates["flat_arf1"]["spec"]))
    rows_by_strategy = {
        "alt_trendline_touch_v1": att1_row,
        "alt_resistance_fade_v1": flat_row,
    }
    strategies: dict[str, Any] = {}
    for sleeve in policy.get("sleeves") or []:
        for raw_name in sleeve.get("strategy_names") or []:
            name = str(raw_name or "").strip()
            if not name or name in strategies:
                continue
            row = rows_by_strategy.get(name, {})
            ok = name in CORE_STRATEGIES
            strategies[name] = {
                "status": "OK" if ok else "PAUSE",
                "total_pnl": float(row.get("net_pnl") or 0.0) if ok else 0.0,
                "rolling_30d_pnl": 0.0,
                "rolling_60d_pnl": 0.0,
                "curve_vs_ma20": 0.0,
                "trades_total": int(float(row.get("trades") or 0.0)) if ok else 0,
                "trades_30d": 0,
                "winrate_total": float(row.get("winrate") or 0.0) if ok else 0.0,
                "winrate_30d": 0.0,
                "pf_30d": 0.0,
                "notes": "ATT1+flat control-plane probe core." if ok else "Paused by ATT1+flat probe.",
            }
    return {
        "overall_health": "OK",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_dir": "att1_flat_control_plane_probe",
        "strategies": strategies,
    }


def _core_policy(
    policy: dict[str, Any],
    *,
    force_regime_enable: bool = False,
    force_regime_enable_sleeves: set[str] | None = None,
    flat_allocator_global: bool = False,
    bear_allocator_global: bool = False,
    flat_count_mult: bool = False,
    low_risk_core: bool = False,
) -> dict[str, Any]:
    payload = copy.deepcopy(policy)
    payload["policy_version"] = f"{payload.get('policy_version', 'policy')}-att1-flat-probe"
    if flat_allocator_global:
        payload["allocator_global_risk_by_regime"] = {regime: 1.0 for regime in ALL_REGIMES}
        payload["degraded_global_risk_mult"] = 1.0
    if bear_allocator_global:
        risk_map = dict(payload.get("allocator_global_risk_by_regime") or {})
        risk_map["bear_chop"] = 1.0
        risk_map["bear_trend"] = 1.0
        payload["allocator_global_risk_by_regime"] = risk_map
    if flat_count_mult:
        payload["symbol_count_multipliers"] = [
            {"max_count": 0, "mult": 0.0},
            {"max_count": 999, "mult": 1.0},
        ]

    force_sleeves = set(force_regime_enable_sleeves or set())
    if force_regime_enable:
        force_sleeves.update(CORE_SLEEVES)

    for sleeve in payload.get("sleeves") or []:
        name = str(sleeve.get("name") or "").strip()
        if name not in CORE_SLEEVES:
            sleeve["base_risk_mult_by_regime"] = {regime: 0.0 for regime in ALL_REGIMES}
            continue
        if name in force_sleeves:
            # Simulates relaxing orchestrator hard-disable gates while preserving
            # the allocator regime risk map for the sleeve.
            sleeve["enable_env"] = f"PROBE_FORCE_ENABLE_{name.upper()}"
        if low_risk_core:
            sleeve["base_risk_mult_by_regime"] = {
                regime: round(float(mult) * 0.5, 6)
                for regime, mult in dict(sleeve.get("base_risk_mult_by_regime") or {}).items()
            }
    return payload


def _fixed_core_registry(registry: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(registry)
    fixed_profiles = [
        {
            "profile_id": f"probe_fixed_{env_key.lower()}",
            "env_key": env_key,
            "active_regimes": ["*"],
            "fixed_symbols": symbols,
        }
        for env_key, symbols in FIXED_SYMBOLS.items()
    ]
    payload["profile_version"] = f"{payload.get('profile_version', 'registry')}-att1-flat-fixed-probe"
    payload["profiles"] = fixed_profiles + list(payload.get("profiles") or [])
    return payload


def _run_variant(
    *,
    variant: dict[str, Any],
    output_root: Path,
    policy: dict[str, Any],
    registry: dict[str, Any],
    health_path: Path,
    timeline_path: Path,
    end: str,
    total_days: int,
    base_risk_pct: float,
) -> dict[str, Any]:
    variant_id = str(variant["id"])
    variant_dir = output_root / variant_id
    variant_dir.mkdir(parents=True, exist_ok=True)
    policy_path = variant_dir / "policy.json"
    registry_path = variant_dir / "registry.json"
    _write_json(policy_path, policy)
    _write_json(registry_path, registry)

    cmd = [
        _repo_python(),
        "scripts/run_dynamic_crypto_annual.py",
        "--end",
        end,
        "--total_days",
        str(total_days),
        "--window_days",
        "30",
        "--step_days",
        "30",
        "--policy",
        str(policy_path),
        "--registry",
        str(registry_path),
        "--health",
        str(health_path),
        "--health-timeline",
        str(timeline_path),
        "--max-scan-symbols",
        "80",
        "--starting_equity",
        "100",
        "--base_risk_pct",
        str(base_risk_pct),
        "--leverage",
        "1",
        "--max_positions",
        "3",
        "--fee_bps",
        "6",
        "--slippage_bps",
        "2",
        "--tag",
        f"att1_flat_probe_{variant_id}_{_stamp()}",
        "--out-dir",
        str(variant_dir / "run_390d"),
    ]
    log_path = variant_dir / "run.log"
    env = os.environ.copy()
    env["BACKTEST_CACHE_ONLY"] = "1"
    env["BACKTEST_CACHE_FALLBACK_ENABLE"] = "1"
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.run(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"{variant_id} failed rc={proc.returncode}; see {log_path}")
    summary = json.loads((variant_dir / "run_390d" / "summary.json").read_text(encoding="utf-8"))
    summary["id"] = variant_id
    summary["description"] = str(variant.get("description") or "")
    summary["run_dir"] = str(variant_dir / "run_390d")
    return summary


def _write_summary(output_root: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "id",
        "description",
        "return_pct",
        "net_pnl",
        "profit_factor",
        "trades",
        "winrate",
        "max_drawdown",
        "negative_months",
        "sleeve_enable_counts",
        "run_dir",
    ]
    csv_path = output_root / "summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["sleeve_enable_counts"] = json.dumps(row.get("sleeve_enable_counts") or {}, sort_keys=True)
            writer.writerow({field: out.get(field, "") for field in fields})

    report = output_root / "report.md"
    lines = [
        "# ATT1 + Flat Control-Plane Probe",
        "",
        "| Variant | Return | PF | Trades | DD | Neg months | Notes |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| `{row['id']}` | {float(row.get('return_pct') or 0.0):+.2f}% | "
            f"{row.get('profit_factor')} | {int(row.get('trades') or 0)} | "
            f"{float(row.get('max_drawdown') or 0.0):.2f}% | {int(row.get('negative_months') or 0)} | "
            f"{row.get('description') or ''} |"
        )
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Probe narrow ATT1+flat canary control-plane relaxations.")
    ap.add_argument("--end", default="2026-04-21")
    ap.add_argument("--total-days", type=int, default=390)
    ap.add_argument("--base-risk-pct", type=float, default=0.005)
    ap.add_argument("--only", default="", help="Comma-separated variant ids to run.")
    args = ap.parse_args()

    output_root = BACKTEST_RUNS / f"att1_flat_control_probe_{_stamp()}"
    output_root.mkdir(parents=True, exist_ok=True)

    base_policy = _load_json(DEFAULT_POLICY)
    base_registry = _load_json(DEFAULT_REGISTRY)
    health_path = output_root / "health_att1_flat_only.json"
    timeline_path = output_root / "empty_strategy_health_timeline.json"
    _write_json(health_path, _core_health(base_policy))
    _write_json(timeline_path, {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "snapshots": []})

    variants = [
        {
            "id": "router_current",
            "description": "Current router and current ATT1/flat regime gates; other sleeves zeroed.",
            "policy": _core_policy(base_policy),
            "registry": base_registry,
        },
        {
            "id": "fixed_current",
            "description": "Freeze ATT1/ARF1 winner universes; keep current hard regime gates.",
            "policy": _core_policy(base_policy),
            "registry": _fixed_core_registry(base_registry),
        },
        {
            "id": "router_regime_soft",
            "description": "Keep router, but allow ATT1 in bear_trend and flat in bull_trend at existing low regime multipliers.",
            "policy": _core_policy(base_policy, force_regime_enable=True),
            "registry": base_registry,
        },
        {
            "id": "router_att1_bear_soft",
            "description": "Keep router; only relax ATT1 hard-disable in bear_trend.",
            "policy": _core_policy(base_policy, force_regime_enable_sleeves={"att1"}),
            "registry": base_registry,
        },
        {
            "id": "router_flat_bull_soft",
            "description": "Keep router; only relax flat hard-disable in bull_trend.",
            "policy": _core_policy(base_policy, force_regime_enable_sleeves={"flat"}),
            "registry": base_registry,
        },
        {
            "id": "fixed_regime_soft",
            "description": "Winner universes plus relaxed ATT1/flat hard regime gates.",
            "policy": _core_policy(base_policy, force_regime_enable=True),
            "registry": _fixed_core_registry(base_registry),
        },
        {
            "id": "router_allocator_flat",
            "description": "Keep hard regime gates, but flatten allocator global risk and degraded haircut.",
            "policy": _core_policy(base_policy, flat_allocator_global=True),
            "registry": base_registry,
        },
        {
            "id": "router_bear_allocator_flat",
            "description": "Keep hard regime gates, but flatten allocator global risk only in bear_chop/bear_trend.",
            "policy": _core_policy(base_policy, bear_allocator_global=True),
            "registry": base_registry,
        },
        {
            "id": "router_regime_allocator_flat",
            "description": "Relax hard regime gates and allocator global risk; keep dynamic router.",
            "policy": _core_policy(base_policy, force_regime_enable=True, flat_allocator_global=True),
            "registry": base_registry,
        },
        {
            "id": "router_att1_bear_allocator_flat",
            "description": "Only relax ATT1 in bear_trend, plus flatten allocator global risk.",
            "policy": _core_policy(
                base_policy,
                force_regime_enable_sleeves={"att1"},
                flat_allocator_global=True,
            ),
            "registry": base_registry,
        },
        {
            "id": "router_att1_bear_bear_allocator_flat",
            "description": "Only relax ATT1 in bear_trend, plus flatten allocator global risk only in bear regimes.",
            "policy": _core_policy(
                base_policy,
                force_regime_enable_sleeves={"att1"},
                bear_allocator_global=True,
            ),
            "registry": base_registry,
        },
        {
            "id": "router_flat_bull_allocator_flat",
            "description": "Only relax flat in bull_trend, plus flatten allocator global risk.",
            "policy": _core_policy(
                base_policy,
                force_regime_enable_sleeves={"flat"},
                flat_allocator_global=True,
            ),
            "registry": base_registry,
        },
        {
            "id": "fixed_regime_allocator_flat",
            "description": "Most relaxed narrow package: fixed winner universes, relaxed hard gates, flat allocator global risk.",
            "policy": _core_policy(base_policy, force_regime_enable=True, flat_allocator_global=True),
            "registry": _fixed_core_registry(base_registry),
        },
    ]

    only = {item.strip() for item in str(args.only or "").split(",") if item.strip()}
    if only:
        known = {str(variant["id"]) for variant in variants}
        unknown = sorted(only - known)
        if unknown:
            raise ValueError(f"Unknown --only variant(s): {','.join(unknown)}")
        variants = [variant for variant in variants if str(variant["id"]) in only]

    rows: list[dict[str, Any]] = []
    for variant in variants:
        print(f"[att1-flat-probe] start {variant['id']}: {variant['description']}", flush=True)
        row = _run_variant(
            variant=variant,
            output_root=output_root,
            policy=variant["policy"],
            registry=variant["registry"],
            health_path=health_path,
            timeline_path=timeline_path,
            end=str(args.end),
            total_days=int(args.total_days),
            base_risk_pct=float(args.base_risk_pct),
        )
        rows.append(row)
        _write_summary(output_root, rows)
        print(
            f"[att1-flat-probe] done {row['id']}: return={float(row.get('return_pct') or 0.0):+.2f}% "
            f"pf={row.get('profit_factor')} dd={float(row.get('max_drawdown') or 0.0):.2f}% "
            f"trades={int(row.get('trades') or 0)}",
            flush=True,
        )

    _write_summary(output_root, rows)
    print(f"summary_csv={output_root / 'summary.csv'}")
    print(f"report={output_root / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
