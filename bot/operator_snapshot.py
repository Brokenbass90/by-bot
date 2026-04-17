from __future__ import annotations

import csv
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
    intraday_open = list(intraday_advisory.get("open_positions") or [])
    if not intraday_open and isinstance(intraday_state, dict):
        intraday_open = sorted(str(sym) for sym in intraday_state.keys())
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
            "open_positions": intraday_open,
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
        "nightly_research": _nightly_research_block(base),
        "self_audit": _self_audit_block(base),
        "alpaca": _alpaca_block(base),
    }


def format_operator_snapshot_text(snapshot: Dict[str, Any]) -> str:
    hb = dict(snapshot.get("heartbeat") or {})
    ws = dict(snapshot.get("ws_transport_guard") or {})
    cp = dict(snapshot.get("control_plane") or {})
    health = dict(snapshot.get("health") or {})
    geo = dict(snapshot.get("geometry") or {})
    memory = dict(snapshot.get("memory") or {})
    nightly = dict(snapshot.get("nightly_research") or {})
    self_audit = dict(snapshot.get("self_audit") or {})
    alpaca = dict(snapshot.get("alpaca") or {})
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
        f"allocator_status={allocator.get('status')} global_risk_mult={allocator.get('global_risk_mult')} hard_block={int(bool(allocator.get('hard_block_new_entries')))}",
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
            "[alpaca_monthly]",
            f"exists={int(bool(alpaca_monthly.get('exists')))} age_sec={alpaca_monthly.get('age_sec')} cycle_mode={alpaca_monthly.get('current_cycle_mode') or '-'} cycle_month={alpaca_monthly.get('current_cycle_month') or '-'}",
            f"selected={alpaca_monthly.get('current_cycle_selected')} tickers={alpaca_monthly.get('current_cycle_tickers') or '-'} advisory_status={alpaca_monthly.get('advisory_status') or '-'}",
            f"capital={alpaca_monthly.get('effective_capital')} per_position={alpaca_monthly.get('per_position_notional')} earnings_blocked={','.join(alpaca_monthly.get('earnings_blocked') or []) or '-'}",
            "",
            "[alpaca_intraday]",
            f"exists={int(bool(alpaca_intraday.get('exists')))} age_sec={alpaca_intraday.get('age_sec')} mode={alpaca_intraday.get('mode') or '-'} entries_blocked={int(bool(alpaca_intraday.get('entries_blocked')))}",
            f"equity={alpaca_intraday.get('equity')} cash={alpaca_intraday.get('cash')} today_pnl_usd={alpaca_intraday.get('today_pnl_usd')}",
            f"open_positions={','.join(alpaca_intraday.get('open_positions') or []) or '-'} remote_only={','.join(alpaca_intraday.get('remote_only_positions') or []) or '-'}",
            f"watchlist_count={alpaca_intraday.get('watchlist_count')} watchlist_preview={','.join(alpaca_intraday.get('watchlist_preview') or []) or '-'}",
            f"signal_state_counts={json.dumps(alpaca_intraday.get('signal_state_counts') or {}, ensure_ascii=True)}",
        ]
    )
    return "\n".join(lines)
