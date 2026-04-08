#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_control_plane_replay.py — historical replay for regime/router/allocator

Purpose:
  Replay the control-plane on a historical timeline so we can validate the
  "brain" of the bot, not only the sleeves in isolation.

Current scope:
  - historical regime classification on BTC 4H
  - hysteresis replay across checkpoints
  - frozen-symbol router replay using the current profile registry plus a
    frozen base overlay
  - allocator decisions per checkpoint

Important limitation:
  This is a control-plane replay, not a portfolio PnL simulator. Symbol
  selection is replayed from profile rules against a frozen overlay/anchors,
  not from a full historical market scan yet.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_portfolio_allocator import (  # noqa: E402
    _max_health_status,
    _safe_float,
    _safe_int,
    _symbol_count_mult,
)
from scripts.build_regime_state import (  # noqa: E402
    ALL_REGIMES,
    MIN_HOLD_CYCLES,
    _REGIME_DECISIONS,
    _classify_regime,
    _fetch_4h,
)


DEFAULT_BASE_OVERLAY = ROOT / "configs" / "dynamic_allowlist_latest.env"
DEFAULT_REGISTRY = ROOT / "configs" / "strategy_profile_registry.json"
DEFAULT_POLICY = ROOT / "configs" / "portfolio_allocator_policy.json"
DEFAULT_HEALTH = ROOT / "configs" / "strategy_health.json"
OUT_ROOT = ROOT / "backtest_runs"


@dataclass
class ReplayPoint:
    end_dt: datetime
    raw_regime: str
    applied_regime: str
    pending_regime: str
    pending_count: int
    regime_changed: bool
    confidence: float
    global_risk_mult: float
    allocator_status: str
    hard_block_new_entries: bool
    sleeves_enabled: int
    sleeves_active: str
    breakout_enabled: bool
    breakdown_enabled: bool
    flat_enabled: bool
    sloped_enabled: bool
    midterm_enabled: bool
    breakout_risk_mult: float
    breakdown_risk_mult: float
    flat_risk_mult: float
    sloped_risk_mult: float
    midterm_risk_mult: float


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _parse_env(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _csv_symbols(raw: str) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for item in str(raw or "").replace(";", ",").split(","):
        sym = item.strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def _dedupe(values: List[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        sym = str(value or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def _pick_profiles(regime: str, registry: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in registry.get("profiles", []):
        env_key = str(item.get("env_key") or "").strip()
        if not env_key:
            continue
        grouped.setdefault(env_key, []).append(item)

    out: Dict[str, Dict[str, Any]] = {}
    for env_key, entries in grouped.items():
        chosen = None
        for item in entries:
            active = [str(x).strip() for x in (item.get("active_regimes") or [])]
            if regime in active or "*" in active:
                chosen = item
                break
        if chosen is None:
            for item in entries:
                if bool(item.get("default", False)):
                    chosen = item
                    break
        if chosen is None and entries:
            chosen = entries[0]
        if chosen is not None:
            out[env_key] = chosen
    return out


def _parse_end_date_utc(raw: str) -> datetime:
    dt = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return dt.replace(hour=23, minute=59, second=59)


def _build_checkpoints(end_dt: datetime, total_days: int, step_days: int) -> List[datetime]:
    start_dt = end_dt - timedelta(days=max(1, total_days))
    points: List[datetime] = []
    cur = start_dt
    while cur <= end_dt:
        points.append(cur)
        cur += timedelta(days=max(1, step_days))
    if not points or points[-1] != end_dt:
        points.append(end_dt)
    return points


def _advance_hysteresis(
    *,
    raw_regime: str,
    applied_regime: str | None,
    pending_regime: str | None,
    pending_count: int,
    min_hold_cycles: int,
) -> tuple[str, str, int, bool]:
    if applied_regime is None:
        return raw_regime, raw_regime, 0, True

    if raw_regime == applied_regime:
        return applied_regime, raw_regime, 0, False

    if pending_regime is None:
        return applied_regime, raw_regime, 1, False

    if raw_regime == pending_regime:
        next_count = int(pending_count) + 1
        if next_count >= int(min_hold_cycles):
            return raw_regime, raw_regime, 0, raw_regime != applied_regime
        return applied_regime, pending_regime, next_count, False

    return applied_regime, raw_regime, 1, False


def _build_frozen_router_state(
    *,
    regime: str,
    registry: Dict[str, Any],
    base_overlay: Dict[str, str],
) -> Dict[str, Any]:
    chosen = _pick_profiles(regime, registry)
    profiles: Dict[str, Any] = {}
    notes: List[str] = []
    degraded = False

    for env_key, entry in chosen.items():
        fixed_symbols = _dedupe([str(x) for x in entry.get("fixed_symbols", []) if str(x).strip()])
        anchor_symbols = _dedupe([str(x) for x in entry.get("anchor_symbols", []) if str(x).strip()])
        frozen_symbols = _csv_symbols(base_overlay.get(env_key, ""))

        if fixed_symbols:
            symbols = fixed_symbols
            source = "fixed_profile"
        elif frozen_symbols:
            symbols = frozen_symbols
            source = "frozen_overlay"
        else:
            symbols = anchor_symbols
            source = "anchor_fallback"
            if not symbols:
                degraded = True
                notes.append(f"{env_key}:no_symbols")

        profiles[env_key] = {
            "profile_id": str(entry.get("profile_id") or env_key),
            "regime": regime,
            "symbols": symbols,
            "count": len(symbols),
            "source": source,
            "fixed_symbols": bool(fixed_symbols),
        }

    return {
        "status": "ok" if not degraded else "degraded",
        "degraded": degraded,
        "scan_ok": True,
        "profile_version": str(registry.get("profile_version") or registry.get("version") or "unknown"),
        "profiles": profiles,
        "notes": notes,
        "router_mode": "frozen_overlay_replay",
    }


def _sleeve_health_status(sleeve: Dict[str, Any], health_map: Dict[str, Any]) -> tuple[str, List[str]]:
    statuses: List[str] = []
    notes: List[str] = []
    for strategy_name in sleeve.get("strategy_names", []):
        info = health_map.get(str(strategy_name), {})
        status = str(info.get("status", "OK")).upper()
        statuses.append(status)
        if status != "OK":
            notes.append(f"{strategy_name}={status}")
    return _max_health_status(statuses), notes


def _compute_allocator_snapshot(
    *,
    regime: str,
    router_state: Dict[str, Any],
    health: Dict[str, Any],
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    health_map = dict(health.get("strategies") or {})
    overall_health = str(health.get("overall_health", "OK")).upper()
    strategy_overrides = dict((_REGIME_DECISIONS.get(regime) or {}).get("overrides") or {})

    degraded_reasons: List[str] = []
    safe_mode_reasons: List[str] = []
    if regime not in ALL_REGIMES:
        safe_mode_reasons.append("unknown_regime")
    if bool(router_state.get("degraded")) or str(router_state.get("status") or "").strip().lower() != "ok":
        degraded_reasons.append(f"router_status={router_state.get('status')}")
    if str(overall_health).upper() == "WATCH":
        degraded_reasons.append("overall_health_watch")

    global_risk_map = dict(policy.get("allocator_global_risk_by_regime") or {})
    base_global_mult = max(0.0, _safe_float(global_risk_map.get(regime), 1.0))
    safe_mode = bool(safe_mode_reasons)
    degraded = bool(degraded_reasons) or safe_mode
    global_mult = base_global_mult
    if degraded and not safe_mode:
        global_mult *= max(0.0, _safe_float(policy.get("degraded_global_risk_mult"), 0.75))
    if safe_mode:
        global_mult = min(global_mult, max(0.0, _safe_float(policy.get("safe_mode_global_risk_mult"), 0.25)))

    status_multipliers = {
        str(k).upper(): max(0.0, _safe_float(v, 1.0))
        for k, v in dict(policy.get("health_status_multipliers") or {}).items()
    }
    count_tiers = list(policy.get("symbol_count_multipliers") or [])

    sleeve_states: Dict[str, Any] = {}
    for sleeve in list(policy.get("sleeves") or []):
        name = str(sleeve.get("name") or "").strip()
        if not name:
            continue
        enable_env = str(sleeve.get("enable_env") or "").strip()
        risk_env = str(sleeve.get("risk_env") or "").strip()
        symbol_env_key = str(sleeve.get("symbol_env_key") or "").strip()
        base_enable = str(strategy_overrides.get(enable_env, "1")).strip() == "1"
        router_info = dict((router_state.get("profiles") or {}).get(symbol_env_key) or {})
        symbol_count = _safe_int(router_info.get("count"), 0)
        health_status, health_notes = _sleeve_health_status(sleeve, health_map)
        health_mult = status_multipliers.get(health_status, 1.0)
        count_mult = _symbol_count_mult(symbol_count, count_tiers)
        base_risk = max(
            0.0,
            _safe_float(dict(sleeve.get("base_risk_mult_by_regime") or {}).get(regime), 0.0),
        )
        enabled = bool(base_enable and base_risk > 0 and symbol_count > 0 and health_mult > 0 and not safe_mode)
        final_risk = base_risk * count_mult * health_mult if enabled else 0.0

        notes = []
        if not base_enable:
            notes.append("orchestrator_disabled")
        if symbol_count <= 0:
            notes.append("no_symbols")
        notes.extend(health_notes)
        if degraded and not safe_mode:
            notes.append("degraded_mode")

        sleeve_states[name] = {
            "enable_env": enable_env,
            "risk_env": risk_env,
            "symbol_env_key": symbol_env_key,
            "enabled": enabled,
            "symbol_count": symbol_count,
            "health_status": health_status,
            "base_risk_mult": base_risk,
            "count_mult": count_mult,
            "health_mult": health_mult,
            "final_risk_mult": final_risk,
            "notes": notes,
        }

    allocator_status = "safe_mode" if safe_mode else ("degraded" if degraded else "ok")
    return {
        "status": allocator_status,
        "safe_mode": safe_mode,
        "degraded": degraded,
        "hard_block_new_entries": safe_mode,
        "regime": regime,
        "overall_health": overall_health,
        "allocator_global_risk_mult": global_mult,
        "base_global_risk_mult": base_global_mult,
        "degraded_reasons": degraded_reasons,
        "safe_mode_reasons": safe_mode_reasons,
        "sleeves": sleeve_states,
    }


def _summarize(points: List[ReplayPoint], out_dir: Path, meta: Dict[str, Any]) -> Dict[str, Any]:
    regime_counts = Counter(p.applied_regime for p in points)
    raw_counts = Counter(p.raw_regime for p in points)
    allocator_counts = Counter(p.allocator_status for p in points)
    sleeve_enable_counts = Counter()
    for p in points:
        if p.breakout_enabled:
            sleeve_enable_counts["breakout"] += 1
        if p.breakdown_enabled:
            sleeve_enable_counts["breakdown"] += 1
        if p.flat_enabled:
            sleeve_enable_counts["flat"] += 1
        if p.sloped_enabled:
            sleeve_enable_counts["sloped"] += 1
        if p.midterm_enabled:
            sleeve_enable_counts["midterm"] += 1

    avg_global_risk = sum(p.global_risk_mult for p in points) / max(1, len(points))
    changed_count = sum(1 for p in points if p.regime_changed)
    hard_block_count = sum(1 for p in points if p.hard_block_new_entries)

    summary = {
        "meta": meta,
        "checkpoints": len(points),
        "regime_counts": dict(regime_counts),
        "raw_regime_counts": dict(raw_counts),
        "allocator_status_counts": dict(allocator_counts),
        "sleeve_enable_counts": dict(sleeve_enable_counts),
        "avg_global_risk_mult": round(avg_global_risk, 4),
        "regime_change_count": changed_count,
        "hard_block_count": hard_block_count,
        "router_mode": "frozen_overlay_replay",
        "limitations": [
            "Historical regime is real.",
            "Router is replayed from profile rules against frozen overlay symbols and anchor fallbacks.",
            "This output validates control-plane decisions, not direct trading PnL.",
        ],
    }

    lines = [
        f"tag={meta['tag']}",
        f"checkpoints={len(points)}",
        f"avg_global_risk_mult={summary['avg_global_risk_mult']:.4f}",
        f"regime_change_count={changed_count}",
        f"hard_block_count={hard_block_count}",
        "regime_counts=" + json.dumps(summary["regime_counts"], ensure_ascii=True),
        "allocator_status_counts=" + json.dumps(summary["allocator_status_counts"], ensure_ascii=True),
        "sleeve_enable_counts=" + json.dumps(summary["sleeve_enable_counts"], ensure_ascii=True),
        "router_mode=frozen_overlay_replay",
        "limitations=historical regime real; router frozen from overlay; not a PnL simulation",
    ]

    _write_text(out_dir / "summary.json", json.dumps(summary, indent=2) + "\n")
    _write_text(out_dir / "summary.txt", "\n".join(lines) + "\n")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay regime/router/allocator on a historical timeline.")
    ap.add_argument("--end", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    ap.add_argument("--total-days", type=int, default=360)
    ap.add_argument("--step-days", type=int, default=15)
    ap.add_argument("--bars", type=int, default=120)
    ap.add_argument("--min-hold-cycles", type=int, default=MIN_HOLD_CYCLES)
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--base-overlay", default=str(DEFAULT_BASE_OVERLAY))
    ap.add_argument("--registry-path", default=str(DEFAULT_REGISTRY))
    ap.add_argument("--policy-path", default=str(DEFAULT_POLICY))
    ap.add_argument("--health-path", default=str(DEFAULT_HEALTH))
    ap.add_argument("--tag", default="control_plane_replay")
    ap.add_argument("--cache-only", action="store_true", help="Use cached data only for historical BTC fetch.")
    ap.add_argument(
        "--neutral-health",
        action="store_true",
        help="Ignore current strategy health file and replay pure regime/router/allocator structure.",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    end_dt = _parse_end_date_utc(args.end)
    checkpoints = _build_checkpoints(end_dt, int(args.total_days), int(args.step_days))

    base_overlay_path = Path(args.base_overlay).expanduser()
    registry_path = Path(args.registry_path).expanduser()
    policy_path = Path(args.policy_path).expanduser()
    health_path = Path(args.health_path).expanduser()
    if not base_overlay_path.is_absolute():
        base_overlay_path = ROOT / base_overlay_path
    if not registry_path.is_absolute():
        registry_path = ROOT / registry_path
    if not policy_path.is_absolute():
        policy_path = ROOT / policy_path
    if not health_path.is_absolute():
        health_path = ROOT / health_path

    base_overlay = _parse_env(base_overlay_path)
    registry = _load_json(registry_path, {})
    policy = _load_json(policy_path, {})
    health = _load_json(health_path, {})
    if args.neutral_health:
        health = {"overall_health": "OK", "strategies": {}}

    run_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tag = str(args.tag).strip() or "control_plane_replay"
    out_dir = OUT_ROOT / f"control_plane_replay_{run_ts}_{tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    applied_regime: str | None = None
    pending_regime: str | None = None
    pending_count = 0
    points: List[ReplayPoint] = []

    for checkpoint_dt in checkpoints:
        checkpoint_ms = int(checkpoint_dt.timestamp() * 1000)
        candles = _fetch_4h(args.symbol, int(args.bars), end_ms=checkpoint_ms, cache_only=bool(args.cache_only))
        if len(candles) < 60:
            raise RuntimeError(
                f"Insufficient BTC 4H candles for checkpoint {checkpoint_dt.date().isoformat()} "
                f"(got {len(candles)} bars)"
            )

        raw_regime, indicators = _classify_regime(candles)
        applied_regime, pending_regime, pending_count, changed = _advance_hysteresis(
            raw_regime=raw_regime,
            applied_regime=applied_regime,
            pending_regime=pending_regime,
            pending_count=pending_count,
            min_hold_cycles=int(args.min_hold_cycles),
        )

        router_state = _build_frozen_router_state(
            regime=applied_regime,
            registry=registry,
            base_overlay=base_overlay,
        )
        allocator = _compute_allocator_snapshot(
            regime=applied_regime,
            router_state=router_state,
            health=health,
            policy=policy,
        )
        sleeves = allocator.get("sleeves", {})
        active_names = [name for name, state in sleeves.items() if bool(state.get("enabled"))]

        points.append(
            ReplayPoint(
                end_dt=checkpoint_dt,
                raw_regime=raw_regime,
                applied_regime=applied_regime,
                pending_regime=pending_regime or applied_regime,
                pending_count=int(pending_count),
                regime_changed=bool(changed),
                confidence=float(indicators.get("er", 0.0) or 0.0),
                global_risk_mult=float(allocator.get("allocator_global_risk_mult", 0.0) or 0.0),
                allocator_status=str(allocator.get("status") or "unknown"),
                hard_block_new_entries=bool(allocator.get("hard_block_new_entries")),
                sleeves_enabled=len(active_names),
                sleeves_active=",".join(active_names),
                breakout_enabled=bool((sleeves.get("breakout") or {}).get("enabled")),
                breakdown_enabled=bool((sleeves.get("breakdown") or {}).get("enabled")),
                flat_enabled=bool((sleeves.get("flat") or {}).get("enabled")),
                sloped_enabled=bool((sleeves.get("sloped") or {}).get("enabled")),
                midterm_enabled=bool((sleeves.get("midterm") or {}).get("enabled")),
                breakout_risk_mult=float((sleeves.get("breakout") or {}).get("final_risk_mult", 0.0) or 0.0),
                breakdown_risk_mult=float((sleeves.get("breakdown") or {}).get("final_risk_mult", 0.0) or 0.0),
                flat_risk_mult=float((sleeves.get("flat") or {}).get("final_risk_mult", 0.0) or 0.0),
                sloped_risk_mult=float((sleeves.get("sloped") or {}).get("final_risk_mult", 0.0) or 0.0),
                midterm_risk_mult=float((sleeves.get("midterm") or {}).get("final_risk_mult", 0.0) or 0.0),
            )
        )

    meta = {
        "tag": tag,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "end_date_utc": end_dt.date().isoformat(),
        "total_days": int(args.total_days),
        "step_days": int(args.step_days),
        "bars": int(args.bars),
        "min_hold_cycles": int(args.min_hold_cycles),
        "base_overlay_path": str(base_overlay_path),
        "registry_path": str(registry_path),
        "policy_path": str(policy_path),
        "health_path": str(health_path),
        "cache_only": bool(args.cache_only),
        "neutral_health": bool(args.neutral_health),
    }

    timeline_path = out_dir / "timeline.csv"
    with timeline_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "checkpoint_date_utc",
                "raw_regime",
                "applied_regime",
                "pending_regime",
                "pending_count",
                "regime_changed",
                "confidence_er",
                "allocator_status",
                "global_risk_mult",
                "hard_block_new_entries",
                "sleeves_enabled",
                "sleeves_active",
                "breakout_enabled",
                "breakdown_enabled",
                "flat_enabled",
                "sloped_enabled",
                "midterm_enabled",
                "breakout_risk_mult",
                "breakdown_risk_mult",
                "flat_risk_mult",
                "sloped_risk_mult",
                "midterm_risk_mult",
            ]
        )
        for p in points:
            writer.writerow(
                [
                    p.end_dt.date().isoformat(),
                    p.raw_regime,
                    p.applied_regime,
                    p.pending_regime,
                    p.pending_count,
                    int(p.regime_changed),
                    f"{p.confidence:.4f}",
                    p.allocator_status,
                    f"{p.global_risk_mult:.4f}",
                    int(p.hard_block_new_entries),
                    p.sleeves_enabled,
                    p.sleeves_active,
                    int(p.breakout_enabled),
                    int(p.breakdown_enabled),
                    int(p.flat_enabled),
                    int(p.sloped_enabled),
                    int(p.midterm_enabled),
                    f"{p.breakout_risk_mult:.4f}",
                    f"{p.breakdown_risk_mult:.4f}",
                    f"{p.flat_risk_mult:.4f}",
                    f"{p.sloped_risk_mult:.4f}",
                    f"{p.midterm_risk_mult:.4f}",
                ]
            )

    summary = _summarize(points, out_dir, meta)
    _write_text(out_dir / "spec.json", json.dumps(meta, indent=2) + "\n")

    if args.dry_run:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Replay dir: {out_dir}")
        print(f"Timeline:   {timeline_path}")
        print(f"Summary:    {out_dir / 'summary.json'}")
        print(
            f"Checkpoints={summary['checkpoints']} "
            f"avg_global_risk={summary['avg_global_risk_mult']:.4f} "
            f"regime_changes={summary['regime_change_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
