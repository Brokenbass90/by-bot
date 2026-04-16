#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_portfolio_allocator.py — deterministic portfolio allocator + safe mode

Consumes:
  - runtime/regime/orchestrator_state.json
  - runtime/router/symbol_router_state.json
  - configs/strategy_health.json
  - configs/portfolio_allocator_policy.json

Produces:
  - runtime/control_plane/portfolio_allocator_state.json
  - configs/portfolio_allocator_latest.env
  - runtime/control_plane/portfolio_allocator_history.jsonl

Purpose:
  - translate regime/router/health into final sleeve enable flags
  - distribute risk across sleeves
  - enter degraded mode when evidence is weaker
  - enter safe mode / hard-block new entries when control-plane data is stale
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ENV_PATH = ROOT / ".env"
ORCH_STATE_PATH = ROOT / "runtime" / "regime" / "orchestrator_state.json"
ROUTER_STATE_PATH = ROOT / "runtime" / "router" / "symbol_router_state.json"
HEALTH_PATH = ROOT / "configs" / "strategy_health.json"
POLICY_PATH = ROOT / "configs" / "portfolio_allocator_policy.json"
OUT_ENV_PATH = ROOT / "configs" / "portfolio_allocator_latest.env"
CONTROL_PLANE_DIR = ROOT / "runtime" / "control_plane"
OUT_STATE_PATH = CONTROL_PLANE_DIR / "portfolio_allocator_state.json"
HISTORY_PATH = CONTROL_PLANE_DIR / "portfolio_allocator_history.jsonl"
STATE_VERSION = "1"


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _append_history(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _parse_env(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        if not path.exists():
            return out
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    except Exception:
        return {}
    return out


def _mirror_env_dict_aliases(env_map: Dict[str, str], alias_map: Dict[str, str]) -> None:
    for canonical, alias in alias_map.items():
        canonical_value = str(env_map.get(canonical, "")).strip()
        if canonical_value:
            continue
        alias_value = str(env_map.get(alias, "")).strip()
        if alias_value:
            env_map[canonical] = alias_value


def _env_enabled(env_map: Dict[str, str], key: str, default: bool = True) -> bool:
    raw = str(env_map.get(key, "1" if default else "0")).strip().lower()
    return raw not in {"0", "false", "no", "off", ""}


def _bool_to_env(value: bool) -> str:
    return "1" if bool(value) else "0"


def _state_age_sec(path: Path, now_ts: int) -> int | None:
    if not path.exists():
        return None
    try:
        return max(0, now_ts - int(path.stat().st_mtime))
    except Exception:
        return None


def _severity_rank(status: str) -> int:
    order = {"OK": 0, "WATCH": 1, "PAUSE": 2, "KILL": 3}
    return order.get(str(status or "OK").upper(), 0)


def _max_health_status(statuses: List[str]) -> str:
    if not statuses:
        return "OK"
    return max((str(x or "OK").upper() for x in statuses), key=_severity_rank)


def _symbol_count_mult(count: int, tiers: List[Dict[str, Any]]) -> float:
    count_i = max(0, int(count or 0))
    for item in tiers:
        if count_i <= _safe_int(item.get("max_count"), 999999):
            return max(0.0, _safe_float(item.get("mult"), 1.0))
    return 1.0


def _sleeve_health_status(sleeve: Dict[str, Any], health_map: Dict[str, Any]) -> Tuple[str, List[str]]:
    statuses: List[str] = []
    notes: List[str] = []
    for strategy_name in sleeve.get("strategy_names", []):
        info = health_map.get(str(strategy_name), {})
        status = str(info.get("status", "OK")).upper()
        statuses.append(status)
        if status != "OK":
            notes.append(f"{strategy_name}={status}")
    return _max_health_status(statuses), notes


def _pair_overlap_ratio(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    denom = float(max(1, min(len(a), len(b))))
    return float(len(a & b) / denom)


def _portfolio_overlap_ratio(symbol_sets: List[set[str]]) -> float:
    filtered = [s for s in symbol_sets if s]
    if not filtered:
        return 0.0
    total = sum(len(s) for s in filtered)
    unique = len(set().union(*filtered))
    if total <= 0:
        return 0.0
    return float(max(0.0, 1.0 - (unique / float(total))))


def _haircut_from_ratio(ratio: float, tiers: List[Dict[str, Any]]) -> float:
    mult = 1.0
    ordered = sorted(tiers, key=lambda item: _safe_float(item.get("min_overlap_ratio"), 0.0))
    for item in ordered:
        threshold = _safe_float(item.get("min_overlap_ratio"), 0.0)
        if float(ratio) >= threshold:
            mult = max(0.0, _safe_float(item.get("mult"), mult))
    return float(mult)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build deterministic portfolio allocator overlay.")
    ap.add_argument("--base-env", default=str(ENV_PATH))
    ap.add_argument("--orchestrator-state", default=str(ORCH_STATE_PATH))
    ap.add_argument("--router-state", default=str(ROUTER_STATE_PATH))
    ap.add_argument("--health-path", default=str(HEALTH_PATH))
    ap.add_argument("--policy-path", default=str(POLICY_PATH))
    ap.add_argument("--out-env", default=str(OUT_ENV_PATH))
    ap.add_argument("--out-state", default=str(OUT_STATE_PATH))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    base_env_path = Path(args.base_env).expanduser()
    orch_path = Path(args.orchestrator_state).expanduser()
    router_path = Path(args.router_state).expanduser()
    health_path = Path(args.health_path).expanduser()
    policy_path = Path(args.policy_path).expanduser()
    out_env = Path(args.out_env).expanduser()
    out_state = Path(args.out_state).expanduser()

    base_env = _parse_env(base_env_path)
    _mirror_env_dict_aliases(base_env, {
        "ENABLE_ELDER_TRADING": "ENABLE_ELDER_V2_TRADING",
        "ELDER_RISK_MULT": "ELDER_V2_RISK_MULT",
    })
    orch = _load_json(orch_path, {})
    router = _load_json(router_path, {})
    health = _load_json(health_path, {})
    policy = _load_json(policy_path, {})

    now = datetime.now(timezone.utc)
    now_ts = int(time.time())
    generated_at = now.isoformat()

    regime = str(orch.get("regime") or "unknown").strip()
    profile_version = str(router.get("profile_version") or "unknown")
    policy_version = str(policy.get("policy_version") or policy.get("version") or "unknown")
    strategy_overrides = dict(orch.get("strategy_overrides") or {})
    router_profiles = dict(router.get("profiles") or {})
    health_map = dict(health.get("strategies") or {})

    staleness = dict(policy.get("staleness_seconds") or {})
    orch_age = _state_age_sec(orch_path, now_ts)
    router_age = _state_age_sec(router_path, now_ts)
    health_age = _state_age_sec(health_path, now_ts)

    issues: List[str] = []
    degraded_reasons: List[str] = []
    safe_mode_reasons: List[str] = []

    if not orch:
        safe_mode_reasons.append("orchestrator_state_missing")
    if not router:
        safe_mode_reasons.append("router_state_missing")
    if regime == "unknown":
        safe_mode_reasons.append("unknown_regime")

    orch_max_age = _safe_int(staleness.get("orchestrator"), 14400)
    router_max_age = _safe_int(staleness.get("router"), 43200)
    health_max_age = _safe_int(staleness.get("health"), 691200)
    if orch_age is None or orch_age > orch_max_age:
        safe_mode_reasons.append(f"orchestrator_stale:{orch_age}")
    if router_age is None or router_age > router_max_age:
        safe_mode_reasons.append(f"router_stale:{router_age}")

    if bool(router.get("degraded")) or str(router.get("status") or "").strip().lower() != "ok":
        degraded_reasons.append(f"router_status={router.get('status')}")
    if not bool(router.get("scan_ok", True)):
        degraded_reasons.append("router_scan_not_ok")
    if health_age is None:
        degraded_reasons.append("health_file_missing")
    elif health_age > health_max_age:
        degraded_reasons.append(f"health_stale:{health_age}")

    global_risk_map = dict(policy.get("allocator_global_risk_by_regime") or {})
    base_global_mult = max(0.0, _safe_float(global_risk_map.get(regime), 1.0))
    global_mult = base_global_mult
    safe_mode = bool(safe_mode_reasons)
    degraded = bool(degraded_reasons) or safe_mode
    if degraded and not safe_mode:
        global_mult *= max(0.0, _safe_float(policy.get("degraded_global_risk_mult"), 0.75))
    if safe_mode:
        global_mult = min(global_mult, max(0.0, _safe_float(policy.get("safe_mode_global_risk_mult"), 0.25)))
    overall_health = str(health.get("overall_health", "OK")).upper()

    lines = [
        "# Auto-generated by build_portfolio_allocator.py — do not edit manually",
        f"# Generated: {generated_at}",
        f"PORTFOLIO_ALLOCATOR_ENABLE=1",
        f"PORTFOLIO_ALLOCATOR_STATE_VERSION={STATE_VERSION}",
        f"PORTFOLIO_ALLOCATOR_POLICY_VERSION={policy_version}",
        f"PORTFOLIO_ALLOCATOR_PROFILE_VERSION={profile_version}",
        f"PORTFOLIO_ALLOCATOR_GENERATED_AT_UTC={generated_at}",
        f"PORTFOLIO_ALLOCATOR_REGIME={regime}",
        f"PORTFOLIO_ALLOCATOR_OVERALL_HEALTH={overall_health}",
        f"PORTFOLIO_ALLOCATOR_STATE_PATH={out_state}",
        f"PORTFOLIO_ALLOCATOR_HISTORY_PATH={HISTORY_PATH}",
        f"PORTFOLIO_ALLOCATOR_PATH={out_env}",
        ""
    ]

    status_multipliers = {
        str(k).upper(): max(0.0, _safe_float(v, 1.0))
        for k, v in dict(policy.get("health_status_multipliers") or {}).items()
    }
    count_tiers = list(policy.get("symbol_count_multipliers") or [])
    exposure_controls = dict(policy.get("exposure_controls") or {})
    portfolio_overlap_tiers = list(
        exposure_controls.get("portfolio_overlap_global_haircuts")
        or [
            {"min_overlap_ratio": 0.25, "mult": 0.93},
            {"min_overlap_ratio": 0.40, "mult": 0.85},
            {"min_overlap_ratio": 0.55, "mult": 0.75},
        ]
    )
    sleeve_overlap_tiers = list(
        exposure_controls.get("sleeve_overlap_haircuts")
        or [
            {"min_overlap_ratio": 0.34, "mult": 0.90},
            {"min_overlap_ratio": 0.50, "mult": 0.80},
            {"min_overlap_ratio": 0.75, "mult": 0.65},
        ]
    )

    sleeve_states: Dict[str, Any] = {}
    for sleeve in list(policy.get("sleeves") or []):
        name = str(sleeve.get("name") or "").strip()
        if not name:
            continue
        enable_env = str(sleeve.get("enable_env") or "").strip()
        risk_env = str(sleeve.get("risk_env") or "").strip()
        symbol_env_key = str(sleeve.get("symbol_env_key") or "").strip()
        base_enable_env = _env_enabled(base_env, enable_env, True)
        regime_enable = str(strategy_overrides.get(enable_env, "1")).strip() == "1"
        base_enable = bool(base_enable_env and regime_enable)
        router_info = dict(router_profiles.get(symbol_env_key) or {})
        sleeve_symbols = [str(sym).strip().upper() for sym in (router_info.get("symbols") or []) if str(sym).strip()]
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
            "base_enabled": base_enable,
            "enabled": enabled,
            "symbol_count": symbol_count,
            "symbols": sleeve_symbols,
            "health_status": health_status,
            "base_risk_mult": base_risk,
            "count_mult": count_mult,
            "health_mult": health_mult,
            "final_risk_mult": final_risk,
            "overlap_mult": 1.0,
            "max_overlap_ratio": 0.0,
            "overlap_with": {},
            "notes": notes,
        }

    active_health_states = [
        str(state.get("health_status") or "OK").upper()
        for state in sleeve_states.values()
        if bool(state.get("base_enabled")) and float(state.get("base_risk_mult", 0.0) or 0.0) > 0.0
    ]
    active_watch_sleeves = sorted(
        name
        for name, state in sleeve_states.items()
        if bool(state.get("base_enabled"))
        and float(state.get("base_risk_mult", 0.0) or 0.0) > 0.0
        and str(state.get("health_status") or "OK").upper() == "WATCH"
    )
    if active_watch_sleeves:
        degraded_reasons.append("overall_health_watch")
        issues.append(f"active_health_watch:{','.join(active_watch_sleeves)}")

    enabled_symbol_sets = {
        name: set(state.get("symbols") or [])
        for name, state in sleeve_states.items()
        if bool(state.get("enabled")) and state.get("symbols")
    }
    portfolio_overlap_ratio = _portfolio_overlap_ratio(list(enabled_symbol_sets.values()))
    portfolio_overlap_mult = _haircut_from_ratio(portfolio_overlap_ratio, portfolio_overlap_tiers)
    if portfolio_overlap_mult < 1.0:
        global_mult *= portfolio_overlap_mult
        degraded = True
        degraded_reasons.append(f"portfolio_overlap:{portfolio_overlap_ratio:.2f}")

    for name, state in sleeve_states.items():
        if not bool(state.get("enabled")):
            continue
        base_set = set(state.get("symbols") or [])
        overlap_with: Dict[str, float] = {}
        max_overlap_ratio = 0.0
        for other_name, other_set in enabled_symbol_sets.items():
            if other_name == name:
                continue
            ratio = _pair_overlap_ratio(base_set, other_set)
            if ratio > 0.0:
                overlap_with[other_name] = round(ratio, 4)
                max_overlap_ratio = max(max_overlap_ratio, ratio)
        overlap_mult = _haircut_from_ratio(max_overlap_ratio, sleeve_overlap_tiers)
        state["overlap_with"] = overlap_with
        state["max_overlap_ratio"] = round(max_overlap_ratio, 4)
        state["overlap_mult"] = round(overlap_mult, 4)
        state["final_risk_mult"] = float(state.get("final_risk_mult", 0.0) or 0.0) * overlap_mult
        if overlap_mult < 1.0:
            state["notes"].append(f"overlap_haircut:{max_overlap_ratio:.2f}")

    for name, state in sleeve_states.items():
        lines.extend(
            [
                f"{state['enable_env']}={_bool_to_env(state['enabled'])}",
                f"{state['risk_env']}={float(state['final_risk_mult']):.4f}",
                f"ALLOCATOR_STATUS_{name.upper()}={state['health_status']}",
                f"ALLOCATOR_COUNT_{name.upper()}={int(state['symbol_count'])}",
                f"ALLOCATOR_OVERLAP_{name.upper()}={float(state.get('max_overlap_ratio', 0.0)):.4f}",
                ""
            ]
        )
        issues.extend(f"{name}:{note}" for note in state.get("notes") or [] if note)

    allocator_status = "safe_mode" if safe_mode else ("degraded" if degraded else "ok")
    health_summary = {
        "overall_health_file": overall_health,
        "active_watch_sleeves": active_watch_sleeves,
        "active_status_counts": {
            "OK": sum(1 for st in active_health_states if st == "OK"),
            "WATCH": sum(1 for st in active_health_states if st == "WATCH"),
            "PAUSE": sum(1 for st in active_health_states if st == "PAUSE"),
            "KILL": sum(1 for st in active_health_states if st == "KILL"),
        },
    }
    lines.extend(
        [
            f"PORTFOLIO_ALLOCATOR_STATUS={allocator_status}",
            f"PORTFOLIO_ALLOCATOR_SAFE_MODE={_bool_to_env(safe_mode)}",
            f"PORTFOLIO_ALLOCATOR_DEGRADED={_bool_to_env(degraded)}",
            f"ALLOCATOR_GLOBAL_RISK_MULT={global_mult:.4f}",
            f"ALLOCATOR_PORTFOLIO_OVERLAP_RATIO={portfolio_overlap_ratio:.4f}",
            f"ALLOCATOR_PORTFOLIO_OVERLAP_MULT={portfolio_overlap_mult:.4f}",
            f"ALLOCATOR_HARD_BLOCK_NEW_ENTRIES={_bool_to_env(safe_mode)}",
            f"ALLOCATOR_SAFE_MODE_REASON={json.dumps(';'.join(safe_mode_reasons[:6]))}",
            "",
        ]
    )
    state_obj = {
        "version": STATE_VERSION,
        "policy_version": policy_version,
        "profile_version": profile_version,
        "timestamp_utc": generated_at,
        "status": allocator_status,
        "safe_mode": safe_mode,
        "degraded": degraded,
        "hard_block_new_entries": safe_mode,
        "regime": regime,
        "overall_health": overall_health,
        "allocator_global_risk_mult": global_mult,
        "base_global_risk_mult": base_global_mult,
        "portfolio_overlap_ratio": round(portfolio_overlap_ratio, 4),
        "portfolio_overlap_mult": round(portfolio_overlap_mult, 4),
        "degraded_reasons": degraded_reasons,
        "safe_mode_reasons": safe_mode_reasons,
        "health_summary": health_summary,
        "issues": issues,
        "orchestrator_age_sec": orch_age,
        "router_age_sec": router_age,
        "health_age_sec": health_age,
        "paths": {
            "orchestrator_state": str(orch_path),
            "router_state": str(router_path),
            "health_file": str(health_path),
            "policy_file": str(policy_path),
            "base_env_file": str(base_env_path),
            "env_path": str(out_env),
            "state_path": str(out_state),
            "history_path": str(HISTORY_PATH),
        },
        "exposure": {
            "enabled_sleeves": sorted(enabled_symbol_sets.keys()),
            "portfolio_overlap_ratio": round(portfolio_overlap_ratio, 4),
            "portfolio_overlap_mult": round(portfolio_overlap_mult, 4),
            "portfolio_overlap_tiers": portfolio_overlap_tiers,
            "sleeve_overlap_tiers": sleeve_overlap_tiers,
        },
        "sleeves": sleeve_states,
    }

    env_text = "\n".join(lines)
    if args.dry_run:
        print(json.dumps(state_obj, indent=2))
        print("\n" + env_text)
        return 0

    _write_text_atomic(out_env, env_text + "\n")
    _write_text_atomic(out_state, json.dumps(state_obj, indent=2) + "\n")
    _append_history(HISTORY_PATH, state_obj)

    print(f"Written env:   {out_env}")
    print(f"Written state: {out_state}")
    print(f"History path:  {HISTORY_PATH}")
    print(
        f"Allocator status: {allocator_status} | regime={regime} | "
        f"global_risk={global_mult:.2f} | hard_block={int(safe_mode)}"
    )
    for name, sleeve_state in sleeve_states.items():
        print(
            f"{name}: enabled={int(sleeve_state['enabled'])} "
            f"risk={sleeve_state['final_risk_mult']:.2f} "
            f"count={sleeve_state['symbol_count']} "
            f"health={sleeve_state['health_status']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
