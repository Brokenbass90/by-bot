from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent.parent
MEMORY_DIR = ROOT / "runtime" / "ai_operator"
MEMORY_PATH = MEMORY_DIR / "memory.jsonl"


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _allocator_meaning(allocator: Dict[str, Any]) -> str:
    status = str(allocator.get("status") or "").strip().lower()
    degraded_kind = str(allocator.get("degraded_kind") or "").strip().lower()
    if status == "degraded" and degraded_kind == "protective_overlap":
        return "protective risk haircut for overlapping sleeves; not a broken allocator"
    if status == "degraded":
        return "allocator degraded; inspect degraded_reasons before suggesting actions"
    if status in {"ok", "healthy"}:
        return "allocator ok"
    return "allocator status unknown"


def _file_age_sec(path: Path) -> int | None:
    try:
        if path.exists():
            return max(0, int(time.time() - path.stat().st_mtime))
    except Exception:
        return None
    return None


def _path_text(path: Path) -> str:
    return str(path.resolve())


def _load_jsonl_tail(path: Path, limit: int = 12) -> list[dict[str, Any]]:
    try:
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        out: list[dict[str, Any]] = []
        for raw in lines[-max(1, int(limit)):]:
            raw = str(raw or "").strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except Exception:
                continue
            if isinstance(item, dict):
                out.append(item)
        return out
    except Exception:
        return []


def _parse_ts_utc(value: Any) -> int:
    try:
        raw = str(value or "").strip()
        if not raw:
            return 0
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return int(datetime.fromisoformat(raw).timestamp())
    except Exception:
        return 0


def _load_csv_rows(path: Path) -> list[dict[str, str]]:
    try:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _load_env_map(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        if not path.exists():
            return out
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = str(raw or "").strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    except Exception:
        return {}
    return out


def append_operator_memory(entry: Dict[str, Any], root: Path | None = None, *, keep_last: int = 200) -> None:
    base = Path(root or ROOT)
    path = base / "runtime" / "ai_operator" / "memory.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(entry or {})
    payload.setdefault("ts_utc", datetime.now(timezone.utc).isoformat())
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > max(keep_last * 2, keep_last + 50):
            path.write_text("\n".join(lines[-keep_last:]) + "\n", encoding="utf-8")
    except Exception:
        pass


def _heartbeat_block(root: Path) -> Dict[str, Any]:
    path = root / "runtime" / "bot_heartbeat.json"
    payload = _load_json(path, {})
    return {
        "path": _path_text(path),
        "exists": bool(path.exists()),
        "age_sec": _file_age_sec(path),
        "ts": _safe_int(payload.get("ts"), 0),
        "uptime_s": _safe_int(payload.get("uptime_s"), 0),
        "open_trades": _safe_int(payload.get("open_trades"), 0),
        "ws_guard_active": bool(payload.get("ws_guard_active")),
        "bybit_msgs": _safe_int(payload.get("bybit_msgs"), 0),
        "regime": str(payload.get("regime") or "unknown"),
    }


def _ws_guard_block(root: Path) -> Dict[str, Any]:
    path = root / "runtime" / "control_plane" / "ws_transport_guard_state.json"
    payload = _load_json(path, {})
    return {
        "path": _path_text(path),
        "exists": bool(path.exists()),
        "age_sec": _file_age_sec(path),
        "active": bool(payload.get("active")),
        "status": str(payload.get("status") or ""),
        "critical_streak": _safe_int(payload.get("critical_streak"), 0),
        "no_connect_streak": _safe_int(payload.get("no_connect_streak"), 0),
        "guard_action": str(payload.get("guard_action") or ""),
        "reason": str(payload.get("reason") or ""),
    }


def _control_plane_block(root: Path) -> Dict[str, Any]:
    regime_path = root / "runtime" / "regime" / "orchestrator_state.json"
    router_path = root / "runtime" / "router" / "symbol_router_state.json"
    allocator_path = root / "runtime" / "control_plane" / "portfolio_allocator_state.json"
    watchdog_path = root / "runtime" / "control_plane" / "control_plane_watchdog_state.json"

    regime = _load_json(regime_path, {})
    router = _load_json(router_path, {})
    allocator = _load_json(allocator_path, {})
    watchdog = _load_json(watchdog_path, {})

    router_profiles = router.get("profiles") or {}
    router_symbols_total = 0
    for item in router_profiles.values():
        router_symbols_total += len(item.get("symbols") or [])

    sleeve_states = allocator.get("sleeves") or {}
    enabled_sleeves = sorted(
        [
            str(name)
            for name, state in sleeve_states.items()
            if bool((state or {}).get("enabled"))
            and _safe_float((state or {}).get("final_risk_mult"), 0.0) > 0.0
        ]
    )
    degraded_sleeves = sorted(
        [
            str(name)
            for name, state in sleeve_states.items()
            if str((state or {}).get("health_status") or (state or {}).get("status") or "").strip().lower()
            in {"watch", "degraded", "kill", "pause", "paused"}
        ]
    )
    sleeve_summary: List[Dict[str, Any]] = []
    for name, state in sorted(sleeve_states.items()):
        block = dict(state or {})
        sleeve_summary.append(
            {
                "name": str(name),
                "enabled": bool(block.get("enabled")),
                "health_status": str(block.get("health_status") or block.get("status") or "").upper(),
                "symbol_count": _safe_int(block.get("symbol_count"), 0),
                "final_risk_mult": _safe_float(block.get("final_risk_mult"), 0.0),
                "notes": list(block.get("notes") or [])[:3],
            }
        )

    return {
        "watchdog": {
            "path": _path_text(watchdog_path),
            "exists": bool(watchdog_path.exists()),
            "age_sec": _file_age_sec(watchdog_path),
            "status": str(watchdog.get("status") or ""),
            "repair_enabled": bool(watchdog.get("repair_enabled")),
            "problems_before": list(watchdog.get("problems_before") or []),
            "problems_after": list(watchdog.get("problems_after") or []),
            "actions": list(watchdog.get("actions") or []),
        },
        "regime": {
            "path": _path_text(regime_path),
            "exists": bool(regime_path.exists()),
            "age_sec": _file_age_sec(regime_path),
            "regime": str(regime.get("regime") or ""),
            "raw_regime": str(regime.get("raw_regime") or ""),
            "pending_regime": str(regime.get("pending_regime") or ""),
            "confidence": _safe_float(regime.get("confidence"), 0.0),
        },
        "router": {
            "path": _path_text(router_path),
            "exists": bool(router_path.exists()),
            "age_sec": _file_age_sec(router_path),
            "regime": str(router.get("regime") or ""),
            "profile_count": len(router_profiles),
            "symbols_total": int(router_symbols_total),
            "degraded": bool(router.get("degraded")),
            "backtest_path": str(router.get("backtest_path") or ""),
            "symbol_memory_loaded": bool(router.get("symbol_memory_loaded")),
        },
        "allocator": {
            "path": _path_text(allocator_path),
            "exists": bool(allocator_path.exists()),
            "age_sec": _file_age_sec(allocator_path),
            "status": str(allocator.get("status") or ""),
            "degraded_kind": str(allocator.get("degraded_kind") or ""),
            "meaning": _allocator_meaning(allocator),
            "allocator_mode": str(allocator.get("allocator_mode") or ""),
            "allocator_effective_mode": str(allocator.get("allocator_effective_mode") or ""),
            "haircut_strength": _safe_float(allocator.get("haircut_strength"), 1.0),
            "effective_equity_usd": allocator.get("effective_equity_usd"),
            "equity_source": str(allocator.get("equity_source") or ""),
            "safe_mode": bool(allocator.get("safe_mode")),
            "overall_health": str(allocator.get("overall_health") or ""),
            "portfolio_overlap_ratio": _safe_float(allocator.get("portfolio_overlap_ratio"), 0.0),
            "portfolio_overlap_mult": _safe_float(allocator.get("portfolio_overlap_mult"), 1.0),
            "global_risk_mult": _safe_float(
                allocator.get("allocator_global_risk_mult", allocator.get("global_risk_mult")),
                0.0,
            ),
            "hard_block_new_entries": bool(allocator.get("hard_block_new_entries")),
            "enabled_sleeves": enabled_sleeves,
            "degraded_sleeves": degraded_sleeves,
            "sleeve_summary": sleeve_summary[:16],
        },
    }


def _interval_flags(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    flags = dict(snapshot.get("flags") or {})
    nearest = dict(snapshot.get("nearest_levels") or {})
    above = list(nearest.get("above") or [])
    below = list(nearest.get("below") or [])
    return {
        "trend_label": str(flags.get("trend_label") or ""),
        "level_context": str(flags.get("level_context") or ""),
        "is_compressed": bool(flags.get("is_compressed")),
        "compression_ratio": _safe_float(flags.get("compression_ratio"), 0.0),
        "channel_r2": _safe_float(flags.get("channel_r2"), 0.0),
        "channel_position": _safe_float(flags.get("channel_position"), 0.0),
        "nearest_above": _safe_float((above[0] or {}).get("price"), 0.0) if above else None,
        "nearest_below": _safe_float((below[0] or {}).get("price"), 0.0) if below else None,
    }


def _geometry_block(root: Path, *, max_highlights: int = 6) -> Dict[str, Any]:
    path = root / "runtime" / "geometry" / "geometry_state.json"
    payload = _load_json(path, {})
    symbols = payload.get("symbols") or {}
    highlights: List[Dict[str, Any]] = []
    for symbol in list((payload.get("requested_symbols") or symbols.keys()))[: max(1, int(max_highlights))]:
        per_symbol = symbols.get(symbol) or {}
        item: Dict[str, Any] = {"symbol": str(symbol)}
        for interval, snapshot in sorted(per_symbol.items(), key=lambda kv: kv[0]):
            item[str(interval)] = _interval_flags(dict(snapshot or {}))
        highlights.append(item)
    return {
        "path": _path_text(path),
        "exists": bool(path.exists()),
        "age_sec": _file_age_sec(path),
        "generated_at_utc": str(payload.get("generated_at_utc") or ""),
        "symbols_analyzed": _safe_int(payload.get("symbols_analyzed"), 0),
        "snapshots_built": _safe_int(payload.get("snapshots_built"), 0),
        "intervals": list(payload.get("intervals") or []),
        "highlights": highlights,
    }


def _setup_scanner_block(root: Path, *, limit: int = 16) -> Dict[str, Any]:
    geometry_path = root / "runtime" / "geometry" / "geometry_state.json"
    router_path = root / "runtime" / "router" / "symbol_router_state.json"
    allocator_path = root / "runtime" / "control_plane" / "portfolio_allocator_state.json"
    geometry_state = _load_json(geometry_path, {})
    router_state = _load_json(router_path, {})
    allocator_state = _load_json(allocator_path, {})
    cards: list[dict[str, Any]] = []
    error = ""
    if geometry_state:
        try:
            from web.routes.data_routes import _build_setup_cards  # type: ignore

            cards = list(_build_setup_cards(geometry_state, router_state, allocator_state))
        except Exception as exc:
            error = str(exc)[:160]
    compact_cards = []
    for card in cards[: max(1, int(limit))]:
        compact_cards.append(
            {
                "symbol": str(card.get("symbol") or ""),
                "interval": str(card.get("interval") or ""),
                "setup_type": str(card.get("setup_type") or ""),
                "side": str(card.get("side") or ""),
                "strategy": str(card.get("strategy") or ""),
                "score": _safe_float(card.get("score"), 0.0),
                "price": _safe_float(card.get("price"), 0.0),
                "level_price": card.get("level_price"),
                "distance_atr": card.get("distance_atr"),
                "invalidation": card.get("invalidation"),
                "runtime": dict(card.get("runtime") or {}),
                "reasons": list(card.get("reasons") or [])[:5],
                "router_profiles": list(card.get("router_profiles") or [])[:3],
            }
        )
    return {
        "geometry_path": _path_text(geometry_path),
        "router_path": _path_text(router_path),
        "allocator_path": _path_text(allocator_path),
        "exists": bool(geometry_state),
        "error": error,
        "geometry_age_sec": _file_age_sec(geometry_path),
        "router_age_sec": _file_age_sec(router_path),
        "allocator_age_sec": _file_age_sec(allocator_path),
        "regime": str(router_state.get("regime") or allocator_state.get("regime") or ""),
        "confidence": _safe_float(router_state.get("confidence"), 0.0),
        "card_count": len(cards),
        "top_cards": compact_cards,
        "notes": [
            "Setup scanner cards are candidates, not trade approvals.",
            "Live promotion still requires annual/OOS/additivity checks.",
        ],
    }


def _latest_forensics_reports(root: Path, *, limit: int = 4) -> list[dict[str, Any]]:
    reports: list[Path] = []
    for base in [root / "reports", root / "runtime"]:
        if not base.exists():
            continue
        for path in base.rglob("*forensics*"):
            if path.is_file() and path.suffix.lower() in {".md", ".json", ".txt"}:
                reports.append(path)
    reports.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[dict[str, Any]] = []
    for path in reports[: max(1, int(limit))]:
        preview = ""
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            preview = " | ".join(lines[:4])[:700]
        except Exception:
            pass
        out.append(
            {
                "path": _path_text(path),
                "age_sec": _file_age_sec(path),
                "name": path.name,
                "preview": preview,
            }
        )
    return out


def _trade_forensics_block(root: Path) -> Dict[str, Any]:
    return {
        "script_path": _path_text(root / "scripts" / "trade_forensics_report.py"),
        "script_exists": bool((root / "scripts" / "trade_forensics_report.py").exists()),
        "latest_reports": _latest_forensics_reports(root),
    }


def _safe_setting_value(key: str, value: str) -> Any:
    raw = str(value or "").strip()
    if "," in raw and ("ALLOWLIST" in key or key.endswith("SYMBOLS")):
        symbols = [x.strip().upper() for x in raw.split(",") if x.strip()]
        return {"count": len(symbols), "preview": symbols[:12]}
    if len(raw) > 160:
        return raw[:157] + "..."
    return raw


def _strategy_settings_block(root: Path) -> Dict[str, Any]:
    sources = {
        ".env": root / ".env",
        "portfolio_allocator_latest.env": root / "configs" / "portfolio_allocator_latest.env",
        "alpaca_paper_local.env": root / "configs" / "alpaca_paper_local.env",
        "alpaca_v38_hybrid_top4_candidate.env": root / "configs" / "alpaca_v38_hybrid_top4_candidate.env",
    }
    allowed_fragments = (
        "ENABLE_",
        "ALLOWLIST",
        "SYMBOLS",
        "RISK",
        "LEVERAGE",
        "DRY_RUN",
        "SL",
        "STOP",
        "TP",
        "RR",
        "TRAIL",
        "MAX_OPEN",
        "TRY_EVERY",
        "TIME_STOP",
        "CAPITAL",
        "ALLOC",
    )
    secret_fragments = ("API", "SECRET", "TOKEN", "PASSWORD", "PRIVATE", "JWT", "KEY")
    payload: dict[str, Any] = {}
    for name, path in sources.items():
        env_map = _load_env_map(path)
        selected: dict[str, Any] = {}
        for key, value in sorted(env_map.items()):
            key_u = key.upper()
            if any(secret in key_u for secret in secret_fragments):
                continue
            if not any(fragment in key_u for fragment in allowed_fragments):
                continue
            selected[key] = _safe_setting_value(key_u, value)
        payload[name] = {
            "path": _path_text(path),
            "exists": bool(path.exists()),
            "age_sec": _file_age_sec(path),
            "setting_count": len(selected),
            "settings": selected,
        }
    return payload


def _health_block(root: Path) -> Dict[str, Any]:
    path = root / "configs" / "strategy_health.json"
    timeline_path = root / "runtime" / "control_plane" / "strategy_health_timeline.json"
    payload = _load_json(path, {})
    timeline = _load_json(timeline_path, {})
    strategies = dict(payload.get("strategies") or {})
    status_counts: Dict[str, int] = {}
    for info in strategies.values():
        status = str((info or {}).get("status") or "OK").upper()
        status_counts[status] = int(status_counts.get(status, 0)) + 1
    snapshots = list(timeline.get("snapshots") or [])
    return {
        "path": _path_text(path),
        "exists": bool(path.exists()),
        "age_sec": _file_age_sec(path),
        "timestamp": str(payload.get("timestamp") or ""),
        "overall_health": str(payload.get("overall_health") or ""),
        "run_dir": str(payload.get("run_dir") or ""),
        "strategy_count": len(strategies),
        "status_counts": status_counts,
        "timeline": {
            "path": _path_text(timeline_path),
            "exists": bool(timeline_path.exists()),
            "age_sec": _file_age_sec(timeline_path),
            "snapshot_count": len(snapshots),
            "run_dir": str(timeline.get("run_dir") or ""),
            "step_days": _safe_int(timeline.get("step_days"), 0),
            "first_checkpoint_date_utc": str((snapshots[0] or {}).get("checkpoint_date_utc") if snapshots else ""),
            "last_checkpoint_date_utc": str((snapshots[-1] or {}).get("checkpoint_date_utc") if snapshots else ""),
        },
    }


def _memory_block(root: Path, *, limit: int = 12) -> Dict[str, Any]:
    path = root / "runtime" / "ai_operator" / "memory.jsonl"
    raw_entries = _load_jsonl_tail(path, limit=max(limit * 6, limit))
    ttl_sec = max(0, _safe_int(os.getenv("OPERATOR_MEMORY_TTL_SEC"), 7200))
    now = int(time.time())
    entries: list[dict[str, Any]] = []
    for item in raw_entries:
        ts = _parse_ts_utc(item.get("ts_utc"))
        if ttl_sec > 0 and ts > 0 and now - ts > ttl_sec:
            continue
        entries.append(item)
    entries = entries[-limit:]
    return {
        "path": _path_text(path),
        "exists": bool(path.exists()),
        "age_sec": _file_age_sec(path),
        "count": len(entries),
        "ttl_sec": ttl_sec,
        "entries": entries,
    }


def _nightly_research_block(root: Path) -> Dict[str, Any]:
    status_path = root / "runtime" / "research_nightly" / "status.json"
    history_path = root / "runtime" / "research_nightly" / "history.jsonl"
    status = _load_json(status_path, {})
    history = _load_jsonl_tail(history_path, limit=6)
    tasks = dict(status.get("tasks") or {})
    states: Dict[str, int] = {}
    for item in tasks.values():
        state = str((item or {}).get("state") or "unknown")
        states[state] = int(states.get(state, 0)) + 1
    return {
        "status_path": _path_text(status_path),
        "history_path": _path_text(history_path),
        "exists": bool(status_path.exists()),
        "age_sec": _file_age_sec(status_path),
        "state": str(status.get("state") or ""),
        "active_process_count": _safe_int(status.get("active_process_count"), 0),
        "launched_count": len(list(status.get("launched") or [])),
        "proposed_count": len(list(status.get("proposed") or [])),
        "blocked_count": len(list(status.get("blocked") or [])),
        "task_state_counts": states,
        "recent_history": history,
    }


def _operator_controls_block(root: Path) -> Dict[str, Any]:
    capabilities_path = root / "configs" / "operator_capabilities.json"
    capabilities_cfg = _load_json(capabilities_path, {})
    research_cfg = _load_json(root / "configs" / "research_nightly_queue.json", {})
    approval_queue_path = root / "runtime" / "ai_operator" / "approval_queue.json"
    approval_queue = _load_json(approval_queue_path, [])

    capabilities = dict(capabilities_cfg.get("capabilities") or {})
    enabled_caps = sorted(
        name for name, meta in capabilities.items()
        if bool((meta or {}).get("enabled", False))
    )
    pending_approval = 0
    for item in approval_queue if isinstance(approval_queue, list) else []:
        if str((item or {}).get("status") or "").strip().lower() == "pending":
            pending_approval += 1

    return {
        "path": _path_text(capabilities_path),
        "exists": bool(capabilities_path.exists()),
        "version": _safe_int(capabilities_cfg.get("version"), 0),
        "enabled_count": len(enabled_caps),
        "enabled_capabilities": enabled_caps,
        "server_deploy_allowed": str(os.getenv("DEEPSEEK_EXECUTOR_ALLOW_SERVER_DEPLOY", "0")).strip().lower() in {"1", "true", "yes", "on"},
        "nightly_queue_enabled": bool(research_cfg.get("enabled", True)),
        "nightly_task_count": len(list(research_cfg.get("tasks") or [])),
        "nightly_enabled_tasks": sum(1 for task in list(research_cfg.get("tasks") or []) if bool((task or {}).get("enabled", True))),
        "approval_queue_exists": bool(approval_queue_path.exists()),
        "approval_queue_pending": pending_approval,
    }


def _self_audit_block(root: Path) -> Dict[str, Any]:
    path = root / "runtime" / "self_audit" / "latest.json"
    payload = _load_json(path, {})
    findings = list(payload.get("findings") or [])
    actions = list(payload.get("actions") or [])
    highest = "ok"
    rank = {"ok": 0, "info": 1, "warn": 2, "critical": 3}
    for item in findings:
        severity = str((item or {}).get("severity") or "info").strip().lower()
        if rank.get(severity, 0) > rank.get(highest, 0):
            highest = severity
    return {
        "path": _path_text(path),
        "exists": bool(path.exists()),
        "age_sec": _file_age_sec(path),
        "highest_severity": highest,
        "headline": str(payload.get("headline") or ""),
        "finding_count": len(findings),
        "action_count": len(actions),
        "top_findings": findings[:3],
        "top_actions": actions[:3],
    }


def _project_doctor_block(root: Path) -> Dict[str, Any]:
    path = root / "runtime" / "project_doctor" / "latest.json"
    payload = _load_json(path, {})
    findings = list(payload.get("findings") or [])
    actions = list(payload.get("actions") or [])
    hygiene = dict(payload.get("project_hygiene") or {})
    status = dict(payload.get("strategy_status") or {})
    return {
        "path": _path_text(path),
        "exists": bool(path.exists()),
        "age_sec": _file_age_sec(path),
        "highest_severity": str(payload.get("highest_severity") or ""),
        "headline": str(payload.get("headline") or ""),
        "finding_count": len(findings),
        "action_count": len(actions),
        "top_findings": findings[:3],
        "top_actions": actions[:3],
        "meaningful_dirty_count": len(list(hygiene.get("meaningful_dirty_files") or [])),
        "nightly_state": str(hygiene.get("nightly_research_state") or ""),
        "nightly_active_process_count": _safe_int(hygiene.get("nightly_active_process_count"), 0),
        "nightly_proposed_count": _safe_int(hygiene.get("nightly_proposed_count"), 0),
        "live_ready_sleeves": list(status.get("live_ready_sleeves") or [])[:12],
        "watch_candidates": list(status.get("watch_candidates") or [])[:12],
        "policy_missing_health": list(status.get("policy_missing_health") or [])[:12],
    }


def _alpaca_block(root: Path) -> Dict[str, Any]:
    monthly_candidates = [
        root / "runtime" / "equities_monthly_v36",
        root / "runtime" / "equities_monthly",
    ]
    monthly_dir = monthly_candidates[0]
    for candidate in monthly_candidates:
        if (candidate / "current_cycle_summary.csv").exists():
            monthly_dir = candidate
            break
    else:
        for candidate in monthly_candidates:
            if (candidate / "latest_refresh.env").exists() or (candidate / "latest_summary.csv").exists():
                monthly_dir = candidate
                break
    monthly_cycle_summary = _load_csv_rows(monthly_dir / "current_cycle_summary.csv")
    monthly_cycle_picks = _load_csv_rows(monthly_dir / "current_cycle_picks.csv")
    monthly_latest_advisory = _load_json(monthly_dir / "latest_advisory.json", {})
    monthly_latest_summary = _load_csv_rows(monthly_dir / "latest_summary.csv")
    monthly_refresh_env = _load_env_map(monthly_dir / "latest_refresh.env")
    monthly_config_env = _load_env_map(root / "configs" / "alpaca_paper_local.env")

    monthly_cycle = monthly_cycle_summary[0] if monthly_cycle_summary else {}
    monthly_metrics = monthly_latest_summary[0] if monthly_latest_summary else {}
    monthly_report = dict((monthly_latest_advisory or {}).get("report") or {})
    monthly_cycle_symbols = [str(row.get("ticker") or "").strip() for row in monthly_cycle_picks if str(row.get("ticker") or "").strip()]
    monthly_selected = list(monthly_report.get("selected") or monthly_cycle_symbols)
    monthly_new_buys = list(monthly_report.get("new_buy_symbols") or monthly_cycle_symbols)
    monthly_status = str(monthly_report.get("status") or "")
    if not monthly_status and monthly_cycle_symbols:
        monthly_status = "selected_current_cycle"
    monthly_cycle_reason = str(monthly_report.get("cycle_reason") or "")
    if not monthly_cycle_reason and monthly_cycle_symbols:
        monthly_cycle_reason = "current_cycle_from_summary"
    monthly_capital = _safe_float(monthly_report.get("effective_capital"), 0.0)
    if monthly_capital <= 0:
        monthly_capital = _safe_float(
            monthly_refresh_env.get("ALPACA_CAPITAL_OVERRIDE_USD")
            or monthly_refresh_env.get("CAPITAL_OVERRIDE_USD")
            or monthly_config_env.get("ALPACA_CAPITAL_OVERRIDE_USD")
            or monthly_config_env.get("CAPITAL_OVERRIDE_USD"),
            0.0,
        )
    monthly_per_position = _safe_float(monthly_report.get("per_position_notional"), 0.0)
    if monthly_per_position <= 0 and monthly_capital > 0:
        top_n = max(1, _safe_int(monthly_cycle.get("top_n"), 0))
        target_alloc_pct = _safe_float(monthly_refresh_env.get("ALPACA_TARGET_ALLOC_PCT"), 0.0)
        if target_alloc_pct <= 0:
            target_alloc_pct = _safe_float(monthly_config_env.get("ALPACA_TARGET_ALLOC_PCT"), 0.0)
        if target_alloc_pct <= 0:
            target_alloc_pct = 0.675
        monthly_per_position = round(monthly_capital * target_alloc_pct / top_n, 2)

    intraday_dir = root / "runtime" / "equities_intraday_dynamic_v1"
    intraday_advisory = _load_json(intraday_dir / "latest_advisory.json", {})
    intraday_state = _load_json(root / "configs" / "intraday_state.json", {})
    intraday_symbols = list((intraday_advisory.get("symbols") or []))
    broker_occupied = list(intraday_advisory.get("open_positions") or [])
    tracked_intraday = sorted(str(sym) for sym in intraday_state.keys()) if isinstance(intraday_state, dict) else []
    pending_close = list(intraday_advisory.get("pending_close_positions") or [])
    monthly_owned = list(intraday_advisory.get("monthly_managed_positions") or [])
    if not broker_occupied:
        broker_occupied = list(tracked_intraday)
    intraday_remote_only = list(intraday_advisory.get("remote_only_positions") or [])

    return {
        "monthly": {
            "runtime_dir": _path_text(monthly_dir),
            "exists": bool(monthly_dir.exists()),
            "age_sec": _file_age_sec(monthly_dir / "current_cycle_summary.csv"),
            "current_cycle_mode": str(monthly_cycle.get("mode") or ""),
            "current_cycle_month": str(monthly_cycle.get("latest_pick_month") or ""),
            "current_cycle_entry_day": str(monthly_cycle.get("latest_entry_day") or ""),
            "current_cycle_entry_age_days": _safe_int(monthly_cycle.get("latest_entry_age_days"), -1),
            "current_cycle_selected": _safe_int(monthly_cycle.get("selected"), 0),
            "current_cycle_tickers": str(monthly_cycle.get("tickers") or ""),
            "current_cycle_pick_rows": len(monthly_cycle_picks),
            "advisory_status": monthly_status,
            "cycle_reason": monthly_cycle_reason,
            "effective_capital": monthly_capital,
            "per_position_notional": monthly_per_position,
            "earnings_blocked": sorted((monthly_report.get("earnings_blocked") or {}).keys()),
            "new_buy_symbols": monthly_new_buys,
            "selected_symbols": monthly_selected,
            "latest_summary_profit_factor": _safe_float(monthly_metrics.get("profit_factor"), 0.0),
            "latest_summary_compounded_return_pct": _safe_float(monthly_metrics.get("compounded_return_pct"), 0.0),
            "latest_summary_max_monthly_dd_pct": _safe_float(monthly_metrics.get("max_monthly_dd_pct"), 0.0),
        },
        "intraday": {
            "runtime_dir": _path_text(intraday_dir),
            "exists": bool(intraday_dir.exists()),
            "age_sec": _file_age_sec(intraday_dir / "latest_advisory.json"),
            "generated_at_utc": str(intraday_advisory.get("generated_at_utc") or ""),
            "mode": str(intraday_advisory.get("mode") or ""),
            "equity": _safe_float(((intraday_advisory.get("account") or {}).get("equity")), 0.0),
            "cash": _safe_float(((intraday_advisory.get("account") or {}).get("cash")), 0.0),
            "entries_blocked": bool(intraday_advisory.get("entries_blocked")),
            "today_pnl_usd": _safe_float(intraday_advisory.get("today_pnl_usd"), 0.0),
            "pnl_status": "paper_journal_verify_fills",
            "broker_occupied_positions": broker_occupied,
            "tracked_positions": tracked_intraday,
            "pending_close_positions": pending_close,
            "monthly_managed_positions": monthly_owned,
            "open_positions": broker_occupied,
            "remote_only_positions": intraday_remote_only,
            "watchlist_count": len(list(intraday_advisory.get("watchlist") or [])),
            "watchlist_preview": list(intraday_advisory.get("watchlist") or [])[:10],
            "signal_state_counts": {
                "entry": sum(1 for item in intraday_symbols if str((item or {}).get("status") or "") == "entry"),
                "no_signal": sum(1 for item in intraday_symbols if str((item or {}).get("status") or "") == "no_signal"),
                "remote_only_position": sum(1 for item in intraday_symbols if str((item or {}).get("status") or "") == "remote_only_position"),
            },
        },
    }


def _urgent_alerts(snapshot: Dict[str, Any]) -> List[Dict[str, str]]:
    alerts: List[Dict[str, str]] = []
    hb = dict(snapshot.get("heartbeat") or {})
    ws = dict(snapshot.get("ws_transport_guard") or {})
    cp = dict(snapshot.get("control_plane") or {})
    allocator = dict(cp.get("allocator") or {})
    watchdog = dict(cp.get("watchdog") or {})

    hb_age = _safe_int(hb.get("age_sec"), -1)
    if hb_age >= 0 and hb_age > 90:
        alerts.append(
            {
                "level": "critical",
                "kind": "heartbeat_stale",
                "summary": f"Heartbeat stale: {hb_age}s old",
            }
        )

    if bool(ws.get("active")):
        reason = str(ws.get("reason") or ws.get("status") or "transport_guard_active")
        alerts.append(
            {
                "level": "critical",
                "kind": "ws_transport_guard",
                "summary": f"WS guard active: {reason}",
            }
        )

    allocator_status = str(allocator.get("status") or "").strip().lower()
    degraded_kind = str(allocator.get("degraded_kind") or "").strip().lower()
    if allocator_status == "degraded" and degraded_kind not in {"", "none", "protective_overlap"}:
        alerts.append(
            {
                "level": "warn",
                "kind": "allocator_degraded",
                "summary": f"Allocator degraded ({degraded_kind or 'unknown'})",
            }
        )

    if str(watchdog.get("status") or "").strip().lower() not in {"", "ok", "healthy"}:
        alerts.append(
            {
                "level": "warn",
                "kind": "control_plane_watchdog",
                "summary": f"Control-plane watchdog status={watchdog.get('status')}",
            }
        )

    return alerts


def build_operator_snapshot(root: Path | None = None) -> Dict[str, Any]:
    base = Path(root or ROOT)
    snapshot = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "heartbeat": _heartbeat_block(base),
        "ws_transport_guard": _ws_guard_block(base),
        "control_plane": _control_plane_block(base),
        "health": _health_block(base),
        "geometry": _geometry_block(base),
        "setup_scanner": _setup_scanner_block(base),
        "trade_forensics": _trade_forensics_block(base),
        "strategy_settings": _strategy_settings_block(base),
        "memory": _memory_block(base),
        "nightly_research": _nightly_research_block(base),
        "operator_controls": _operator_controls_block(base),
        "self_audit": _self_audit_block(base),
        "project_doctor": _project_doctor_block(base),
        "alpaca": _alpaca_block(base),
    }
    snapshot["urgent_alerts"] = _urgent_alerts(snapshot)
    return snapshot


def format_operator_snapshot_text(snapshot: Dict[str, Any]) -> str:
    hb = dict(snapshot.get("heartbeat") or {})
    ws = dict(snapshot.get("ws_transport_guard") or {})
    cp = dict(snapshot.get("control_plane") or {})
    health = dict(snapshot.get("health") or {})
    geo = dict(snapshot.get("geometry") or {})
    setup_scanner = dict(snapshot.get("setup_scanner") or {})
    trade_forensics = dict(snapshot.get("trade_forensics") or {})
    strategy_settings = dict(snapshot.get("strategy_settings") or {})
    memory = dict(snapshot.get("memory") or {})
    nightly = dict(snapshot.get("nightly_research") or {})
    operator_controls = dict(snapshot.get("operator_controls") or {})
    self_audit = dict(snapshot.get("self_audit") or {})
    project_doctor = dict(snapshot.get("project_doctor") or {})
    alpaca = dict(snapshot.get("alpaca") or {})
    urgent_alerts = list(snapshot.get("urgent_alerts") or [])
    regime = dict(cp.get("regime") or {})
    router = dict(cp.get("router") or {})
    allocator = dict(cp.get("allocator") or {})
    watchdog = dict(cp.get("watchdog") or {})
    health_timeline = dict(health.get("timeline") or {})
    alpaca_monthly = dict(alpaca.get("monthly") or {})
    alpaca_intraday = dict(alpaca.get("intraday") or {})

    lines = [
        "operator snapshot",
        f"generated_at_utc={snapshot.get('generated_at_utc','')}",
        "",
        "[urgent_alerts]",
        f"count={len(urgent_alerts)}",
    ]
    for item in urgent_alerts[:5]:
        lines.append(
            f" - {str(item.get('level') or 'info')}:{str(item.get('kind') or 'event')} {str(item.get('summary') or '-')[:180]}"
        )
    lines.extend(
        [
            "",
        "[heartbeat]",
        f"exists={int(bool(hb.get('exists')))} age_sec={hb.get('age_sec')} uptime_s={hb.get('uptime_s')} open_trades={hb.get('open_trades')}",
        f"ws_guard_active={int(bool(hb.get('ws_guard_active')))} bybit_msgs={hb.get('bybit_msgs')} regime={hb.get('regime')}",
        "",
        "[ws_transport_guard]",
        f"exists={int(bool(ws.get('exists')))} age_sec={ws.get('age_sec')} active={int(bool(ws.get('active')))} status={ws.get('status')}",
        f"critical_streak={ws.get('critical_streak')} no_connect_streak={ws.get('no_connect_streak')} reason={ws.get('reason') or '-'}",
        "",
        "[control_plane]",
        f"watchdog_status={watchdog.get('status')} actions={len(watchdog.get('actions') or [])} problems_after={len(watchdog.get('problems_after') or [])}",
        f"regime={regime.get('regime')} raw_regime={regime.get('raw_regime')} confidence={regime.get('confidence')} age_sec={regime.get('age_sec')}",
        f"router_profiles={router.get('profile_count')} router_symbols_total={router.get('symbols_total')} router_age_sec={router.get('age_sec')}",
        f"router_backtest_gate={'on' if router.get('backtest_path') else 'off'} symbol_memory_loaded={int(bool(router.get('symbol_memory_loaded')))}",
        f"allocator_status={allocator.get('status')} degraded_kind={allocator.get('degraded_kind') or '-'} global_risk_mult={allocator.get('global_risk_mult')} hard_block={int(bool(allocator.get('hard_block_new_entries')))}",
        f"allocator_mode={allocator.get('allocator_mode') or '-'}->{allocator.get('allocator_effective_mode') or '-'} haircut_strength={allocator.get('haircut_strength')} equity={allocator.get('effective_equity_usd')} source={allocator.get('equity_source') or '-'}",
        f"allocator_meaning={allocator.get('meaning') or '-'} safe_mode={int(bool(allocator.get('safe_mode')))} overall_health={allocator.get('overall_health') or '-'} overlap_ratio={allocator.get('portfolio_overlap_ratio')} overlap_mult={allocator.get('portfolio_overlap_mult')}",
        f"enabled_sleeves={','.join(allocator.get('enabled_sleeves') or []) or '-'}",
        f"degraded_sleeves={','.join(allocator.get('degraded_sleeves') or []) or '-'}",
        "",
        "[health]",
        f"exists={int(bool(health.get('exists')))} age_sec={health.get('age_sec')} overall_health={health.get('overall_health')} strategy_count={health.get('strategy_count')}",
        f"status_counts={json.dumps(health.get('status_counts') or {}, ensure_ascii=True)}",
        f"timeline_exists={int(bool(health_timeline.get('exists')))} timeline_age_sec={health_timeline.get('age_sec')} snapshot_count={health_timeline.get('snapshot_count')}",
        f"timeline_range={health_timeline.get('first_checkpoint_date_utc') or '-'}..{health_timeline.get('last_checkpoint_date_utc') or '-'} step_days={health_timeline.get('step_days')}",
        "",
        "[geometry]",
        f"exists={int(bool(geo.get('exists')))} age_sec={geo.get('age_sec')} symbols_analyzed={geo.get('symbols_analyzed')} snapshots_built={geo.get('snapshots_built')}",
        f"intervals={','.join(str(x) for x in (geo.get('intervals') or [])) or '-'}",
        ]
    )
    for item in list(allocator.get("sleeve_summary") or []):
        if not item.get("enabled") and str(item.get("health_status") or "") == "OK":
            continue
        lines.append(
            f" - sleeve[{item.get('name')}]: enabled={int(bool(item.get('enabled')))} "
            f"risk={_safe_float(item.get('final_risk_mult'), 0.0):.2f} "
            f"count={_safe_int(item.get('symbol_count'), 0)} "
            f"health={item.get('health_status') or '-'}"
        )
    for item in geo.get("highlights") or []:
        symbol = str(item.get("symbol") or "")
        bits: List[str] = []
        for interval in sorted(k for k in item.keys() if k != "symbol"):
            block = dict(item.get(interval) or {})
            bits.append(
                f"{interval}:trend={block.get('trend_label')} level={block.get('level_context')} "
                f"compressed={int(bool(block.get('is_compressed')))} r2={block.get('channel_r2')}"
            )
        lines.append(f"{symbol}: " + " | ".join(bits))
    lines.extend(
        [
            "",
            "[setup_scanner]",
            f"exists={int(bool(setup_scanner.get('exists')))} cards={setup_scanner.get('card_count', 0)} regime={setup_scanner.get('regime') or '-'} confidence={setup_scanner.get('confidence')}",
            f"ages geometry={setup_scanner.get('geometry_age_sec')} router={setup_scanner.get('router_age_sec')} allocator={setup_scanner.get('allocator_age_sec')} error={setup_scanner.get('error') or '-'}",
        ]
    )
    for card in list(setup_scanner.get("top_cards") or [])[:8]:
        runtime = dict(card.get("runtime") or {})
        level = card.get("level_price")
        dist = card.get("distance_atr")
        lines.append(
            f" - setup[{card.get('strategy')}]: {card.get('symbol')} {card.get('interval')} "
            f"{card.get('side')} {card.get('setup_type')} score={card.get('score')} "
            f"level={level if level is not None else '-'} dist_atr={dist if dist is not None else '-'} "
            f"runtime={'LIVE' if runtime.get('enabled') else 'WATCH'} risk={runtime.get('risk_mult')}"
        )
    lines.extend(
        [
            "",
            "[trade_forensics]",
            f"script_exists={int(bool(trade_forensics.get('script_exists')))} latest_reports={len(trade_forensics.get('latest_reports') or [])}",
        ]
    )
    for report in list(trade_forensics.get("latest_reports") or [])[:2]:
        lines.append(
            f" - {report.get('name')} age_sec={report.get('age_sec')} preview={str(report.get('preview') or '-')[:240]}"
        )
    lines.extend(
        [
            "",
            "[strategy_settings]",
        ]
    )
    for source, block in strategy_settings.items():
        if not isinstance(block, dict):
            continue
        settings = dict(block.get("settings") or {})
        interesting = []
        for key in sorted(settings)[:18]:
            value = settings[key]
            if isinstance(value, dict):
                value = f"{value.get('count')} symbols"
            interesting.append(f"{key}={value}")
        lines.append(
            f" - {source}: exists={int(bool(block.get('exists')))} age_sec={block.get('age_sec')} "
            f"settings={block.get('setting_count')} preview={'; '.join(interesting)[:420] or '-'}"
        )
    lines.extend(
        [
            "",
            "[memory]",
            f"exists={int(bool(memory.get('exists')))} age_sec={memory.get('age_sec')} count={memory.get('count')}",
        ]
    )
    for item in list(memory.get("entries") or [])[-3:]:
        lines.append(
            f" - {str(item.get('kind') or 'event')}: {str(item.get('summary') or '-')[:180]}"
        )
    lines.extend(
        [
            "",
            "[nightly_research]",
            f"exists={int(bool(nightly.get('exists')))} age_sec={nightly.get('age_sec')} state={nightly.get('state') or '-'} active_process_count={nightly.get('active_process_count')}",
            f"launched={nightly.get('launched_count')} proposed={nightly.get('proposed_count')} blocked={nightly.get('blocked_count')}",
            f"task_state_counts={json.dumps(nightly.get('task_state_counts') or {}, ensure_ascii=True)}",
        ]
    )
    for item in list(nightly.get("recent_history") or [])[-3:]:
        lines.append(
            f" - history: state={item.get('state')} active={item.get('active_process_count')} launched={item.get('launched')} proposed={item.get('proposed')}"
        )
    lines.extend(
        [
            "",
            "[operator_controls]",
            f"exists={int(bool(operator_controls.get('exists')))} version={operator_controls.get('version')} enabled_count={operator_controls.get('enabled_count')}",
            f"nightly_queue_enabled={int(bool(operator_controls.get('nightly_queue_enabled')))} nightly_tasks={operator_controls.get('nightly_enabled_tasks')}/{operator_controls.get('nightly_task_count')}",
            f"server_deploy_allowed={int(bool(operator_controls.get('server_deploy_allowed')))} approval_queue_pending={operator_controls.get('approval_queue_pending')}",
            f"enabled_capabilities={','.join(operator_controls.get('enabled_capabilities') or []) or '-'}",
        ]
    )
    lines.extend(
        [
            "",
            "[self_audit]",
            f"exists={int(bool(self_audit.get('exists')))} age_sec={self_audit.get('age_sec')} highest_severity={self_audit.get('highest_severity') or '-'} finding_count={self_audit.get('finding_count')}",
            f"headline={self_audit.get('headline') or '-'}",
        ]
    )
    for item in list(self_audit.get("top_findings") or [])[:2]:
        lines.append(f" - finding[{item.get('severity') or 'info'}]: {str(item.get('summary') or '-')[:180]}")
    for item in list(self_audit.get("top_actions") or [])[:2]:
        lines.append(f" - action: {str(item.get('summary') or '-')[:180]}")
    lines.extend(
        [
            "",
            "[project_doctor]",
            f"exists={int(bool(project_doctor.get('exists')))} age_sec={project_doctor.get('age_sec')} highest_severity={project_doctor.get('highest_severity') or '-'} finding_count={project_doctor.get('finding_count')}",
            f"headline={project_doctor.get('headline') or '-'}",
            f"live_ready={','.join(project_doctor.get('live_ready_sleeves') or []) or '-'} watch={','.join(project_doctor.get('watch_candidates') or []) or '-'}",
            f"dirty_meaningful={project_doctor.get('meaningful_dirty_count')} nightly={project_doctor.get('nightly_state') or '-'} active={project_doctor.get('nightly_active_process_count')} proposed={project_doctor.get('nightly_proposed_count')}",
        ]
    )
    for item in list(project_doctor.get("top_findings") or [])[:2]:
        lines.append(f" - finding[{item.get('severity') or 'info'}]: {str(item.get('summary') or '-')[:180]}")
    for item in list(project_doctor.get("top_actions") or [])[:2]:
        lines.append(f" - action: {str(item.get('summary') or '-')[:180]}")
    lines.extend(
        [
            "",
            "[alpaca_monthly]",
            f"exists={int(bool(alpaca_monthly.get('exists')))} age_sec={alpaca_monthly.get('age_sec')} cycle_mode={alpaca_monthly.get('current_cycle_mode') or '-'} cycle_month={alpaca_monthly.get('current_cycle_month') or '-'}",
            f"selected={alpaca_monthly.get('current_cycle_selected')} tickers={alpaca_monthly.get('current_cycle_tickers') or '-'} advisory_status={alpaca_monthly.get('advisory_status') or '-'}",
            f"capital={alpaca_monthly.get('effective_capital')} per_position={alpaca_monthly.get('per_position_notional')} earnings_blocked={','.join(alpaca_monthly.get('earnings_blocked') or []) or '-'}",
            "",
            "[alpaca_intraday]",
            f"exists={int(bool(alpaca_intraday.get('exists')))} age_sec={alpaca_intraday.get('age_sec')} mode={alpaca_intraday.get('mode') or '-'} entries_blocked={int(bool(alpaca_intraday.get('entries_blocked')))}",
            f"equity={alpaca_intraday.get('equity')} cash={alpaca_intraday.get('cash')} paper_journal_pnl_usd={alpaca_intraday.get('today_pnl_usd')} pnl_status={alpaca_intraday.get('pnl_status') or '-'}",
            f"tracked_positions={','.join(alpaca_intraday.get('tracked_positions') or []) or '-'} pending_close={','.join(alpaca_intraday.get('pending_close_positions') or []) or '-'} monthly_owned={','.join(alpaca_intraday.get('monthly_managed_positions') or []) or '-'}",
            f"broker_occupied={','.join(alpaca_intraday.get('broker_occupied_positions') or []) or '-'} remote_only={','.join(alpaca_intraday.get('remote_only_positions') or []) or '-'}",
            f"watchlist_count={alpaca_intraday.get('watchlist_count')} watchlist_preview={','.join(alpaca_intraday.get('watchlist_preview') or []) or '-'}",
            f"signal_state_counts={json.dumps(alpaca_intraday.get('signal_state_counts') or {}, ensure_ascii=True)}",
        ]
    )
    return "\n".join(lines)
