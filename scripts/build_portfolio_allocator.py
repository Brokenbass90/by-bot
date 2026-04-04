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


def main() -> int:
    ap = argparse.ArgumentParser(description="Build deterministic portfolio allocator overlay.")
    ap.add_argument("--orchestrator-state", default=str(ORCH_STATE_PATH))
    ap.add_argument("--router-state", default=str(ROUTER_STATE_PATH))
    ap.add_argument("--health-path", default=str(HEALTH_PATH))
    ap.add_argument("--policy-path", default=str(POLICY_PATH))
    ap.add_argument("--out-env", default=str(OUT_ENV_PATH))
    ap.add_argument("--out-state", default=str(OUT_STATE_PATH))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    orch_path = Path(args.orchestrator_state).expanduser()
    router_path = Path(args.router_state).expanduser()
    health_path = Path(args.health_path).expanduser()
    policy_path = Path(args.policy_path).expanduser()
    out_env = Path(args.out_env).expanduser()
    out_state = Path(args.out_state).expanduser()

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
    if str(health.get("overall_health", "OK")).upper() == "WATCH":
        degraded_reasons.append("overall_health_watch")
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

    sleeve_states: Dict[str, Any] = {}
    for sleeve in list(policy.get("sleeves") or []):
        name = str(sleeve.get("name") or "").strip()
        if not name:
            continue
        enable_env = str(sleeve.get("enable_env") or "").strip()
        risk_env = str(sleeve.get("risk_env") or "").strip()
        symbol_env_key = str(sleeve.get("symbol_env_key") or "").strip()
        base_enable = str(strategy_overrides.get(enable_env, "1")).strip() == "1"
        router_info = dict(router_profiles.get(symbol_env_key) or {})
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

        lines.extend(
            [
                f"{enable_env}={_bool_to_env(enabled)}",
                f"{risk_env}={final_risk:.4f}",
                f"ALLOCATOR_STATUS_{name.upper()}={health_status}",
                f"ALLOCATOR_COUNT_{name.upper()}={symbol_count}",
                ""
            ]
        )

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
        issues.extend(f"{name}:{note}" for note in notes if note)

    allocator_status = "safe_mode" if safe_mode else ("degraded" if degraded else "ok")
    lines.extend(
        [
            f"PORTFOLIO_ALLOCATOR_STATUS={allocator_status}",
            f"PORTFOLIO_ALLOCATOR_SAFE_MODE={_bool_to_env(safe_mode)}",
            f"PORTFOLIO_ALLOCATOR_DEGRADED={_bool_to_env(degraded)}",
            f"ALLOCATOR_GLOBAL_RISK_MULT={global_mult:.4f}",
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
        "degraded_reasons": degraded_reasons,
        "safe_mode_reasons": safe_mode_reasons,
        "issues": issues,
        "orchestrator_age_sec": orch_age,
        "router_age_sec": router_age,
        "health_age_sec": health_age,
        "paths": {
            "orchestrator_state": str(orch_path),
            "router_state": str(router_path),
            "health_file": str(health_path),
            "policy_file": str(policy_path),
            "env_path": str(out_env),
            "state_path": str(out_state),
            "history_path": str(HISTORY_PATH),
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
