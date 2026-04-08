from __future__ import annotations

import json
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
    degraded_sleeves = sorted(
        [
            str(name)
            for name, state in sleeve_states.items()
            if str((state or {}).get("status") or "").strip().lower() in {"watch", "degraded", "kill", "paused"}
        ]
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
        },
        "allocator": {
            "path": _path_text(allocator_path),
            "exists": bool(allocator_path.exists()),
            "age_sec": _file_age_sec(allocator_path),
            "status": str(allocator.get("status") or ""),
            "global_risk_mult": _safe_float(allocator.get("global_risk_mult"), 0.0),
            "hard_block_new_entries": bool(allocator.get("hard_block_new_entries")),
            "degraded_sleeves": degraded_sleeves,
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
    entries = _load_jsonl_tail(path, limit=limit)
    return {
        "path": _path_text(path),
        "exists": bool(path.exists()),
        "age_sec": _file_age_sec(path),
        "count": len(entries),
        "entries": entries,
    }


def build_operator_snapshot(root: Path | None = None) -> Dict[str, Any]:
    base = Path(root or ROOT)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "heartbeat": _heartbeat_block(base),
        "ws_transport_guard": _ws_guard_block(base),
        "control_plane": _control_plane_block(base),
        "health": _health_block(base),
        "geometry": _geometry_block(base),
        "memory": _memory_block(base),
    }


def format_operator_snapshot_text(snapshot: Dict[str, Any]) -> str:
    hb = dict(snapshot.get("heartbeat") or {})
    ws = dict(snapshot.get("ws_transport_guard") or {})
    cp = dict(snapshot.get("control_plane") or {})
    health = dict(snapshot.get("health") or {})
    geo = dict(snapshot.get("geometry") or {})
    memory = dict(snapshot.get("memory") or {})
    regime = dict(cp.get("regime") or {})
    router = dict(cp.get("router") or {})
    allocator = dict(cp.get("allocator") or {})
    watchdog = dict(cp.get("watchdog") or {})
    health_timeline = dict(health.get("timeline") or {})

    lines = [
        "operator snapshot",
        f"generated_at_utc={snapshot.get('generated_at_utc','')}",
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
        f"allocator_status={allocator.get('status')} global_risk_mult={allocator.get('global_risk_mult')} hard_block={int(bool(allocator.get('hard_block_new_entries')))}",
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
            "[memory]",
            f"exists={int(bool(memory.get('exists')))} age_sec={memory.get('age_sec')} count={memory.get('count')}",
        ]
    )
    for item in list(memory.get("entries") or [])[-3:]:
        lines.append(
            f" - {str(item.get('kind') or 'event')}: {str(item.get('summary') or '-')[:180]}"
        )
    return "\n".join(lines)
