"""AI Chat — Anthropic Claude with full bot context injection and safe control commands.

The AI sees:
  - Current regime, confidence, risk mult
  - All allocator sleeves and their status
  - Last 50 trades + strategy performance summary
  - Strategy health
  - Bot heartbeat / liveness
  - Alpaca monthly picks and metrics

Safe control commands the AI can request (user must confirm, then they execute):
  - enable_sleeve   / disable_sleeve
  - set_safe_mode   / clear_safe_mode
  - reload_config

All executed commands are written to runtime/web_audit_log.jsonl.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..deps import require_admin

router = APIRouter(prefix="/api/ai", tags=["ai"])

_ROOT = Path(__file__).parent.parent.parent
_RUNTIME_ROOT = Path(os.getenv("WEB_RUNTIME_ROOT", str(_ROOT / "runtime")))
_AUDIT_LOG = _ROOT / "runtime" / "web_audit_log.jsonl"
_OVERLAY_ENV = _ROOT / "configs" / "web_control_overlay.env"
_SHARED_HISTORY_PATH = Path(
    str(os.getenv("DEEPSEEK_CHAT_STATE_PATH", _ROOT / "runtime" / "web_ai_history.json"))
)
_HISTORY_MAX = max(1, int(os.getenv("DEEPSEEK_HISTORY_MAX_MESSAGES", "20") or 20))
_HISTORY_TTL_SEC = max(0, int(os.getenv("DEEPSEEK_HISTORY_TTL_SEC", "21600") or 21600))
_CHAT_RATE: Dict[str, List[float]] = {}  # email → list of timestamps
_MAX_RPM = 20  # requests per minute per user


def _rt(*p: str) -> Path:
    return _RUNTIME_ROOT / Path(*p)


def _cfg(*p: str) -> Path:
    return _ROOT / "configs" / Path(*p)


def _json(p: Path) -> Optional[dict]:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _read_env(p: Path) -> Dict[str, str]:
    result = {}
    if not p.exists():
        return result
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _resolve_rooted_path(raw: str) -> Optional[Path]:
    raw = str(raw or "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p
    return (_ROOT / p).resolve()


def _load_monthly_picks() -> List[str]:
    import csv as _csv

    candidates = [_rt("equities_monthly_v36", "current_cycle_picks.csv")]
    latest_refresh = _read_env(_rt("equities_monthly_v36", "latest_refresh.env"))
    for key in ("EQ_CURRENT_CYCLE_PICKS_CSV", "ALPACA_CURRENT_CYCLE_PICKS_CSV", "EQ_LATEST_PICKS_CSV"):
        p = _resolve_rooted_path(latest_refresh.get(key, ""))
        if p:
            candidates.append(p)
    for picks_path in candidates:
        if not picks_path or not picks_path.exists():
            continue
        try:
            with open(picks_path) as f:
                rows = [r["ticker"] for r in _csv.DictReader(f) if r.get("ticker")]
            if rows:
                return rows
        except Exception:
            continue
    return []


def _load_live_trade_event_closes(limit: int = 50) -> List[Dict[str, Any]]:
    path = _rt("live_trade_events.jsonl")
    if not path.exists():
        return []
    closes: List[Dict[str, Any]] = []
    try:
        for raw in path.read_text(errors="ignore").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                evt = json.loads(raw)
            except Exception:
                continue
            if str(evt.get("event") or "").strip().lower() != "close":
                continue
            closes.append(evt)
    except Exception:
        return []
    return closes[-limit:]


def _latest_report_files(rel_dir: str, *, limit: int = 8) -> List[Dict[str, Any]]:
    root = _ROOT / rel_dir
    if not root.exists():
        return []
    files: List[Dict[str, Any]] = []
    for path in sorted(root.glob("*"), key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True):
        if not path.is_file():
            continue
        preview = ""
        if path.suffix.lower() in {".md", ".txt", ".json", ".csv"}:
            try:
                preview = path.read_text(encoding="utf-8", errors="ignore")[:1200]
            except Exception:
                preview = ""
        files.append(
            {
                "path": str(path.relative_to(_ROOT)),
                "mtime": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                "size_bytes": path.stat().st_size,
                "preview": preview,
            }
        )
        if len(files) >= limit:
            break
    return files


def _append_operator_snapshot_context(parts: List[str]) -> None:
    snap = _json(_rt("operator", "operator_snapshot.json"))
    if not snap:
        return
    cp = dict(snap.get("control_plane") or {})
    allocator = dict(cp.get("allocator") or {})
    regime = dict(cp.get("regime") or {})
    alpaca = dict(snap.get("alpaca") or {})
    alpaca_monthly = dict(alpaca.get("monthly") or {})
    alpaca_intraday = dict(alpaca.get("intraday") or {})
    setup_scanner = dict(snap.get("setup_scanner") or {})
    trade_forensics = dict(snap.get("trade_forensics") or {})
    strategy_settings = dict(snap.get("strategy_settings") or {})
    self_audit = dict(snap.get("self_audit") or {})
    project_doctor = dict(snap.get("project_doctor") or {})
    urgent = list(snap.get("urgent_alerts") or [])

    if regime or allocator:
        parts.append(
            "OPERATOR SNAPSHOT: "
            f"regime={regime.get('regime','?')} conf={regime.get('confidence','?')} "
            f"allocator={allocator.get('status','?')} safe_mode={allocator.get('safe_mode', False)} "
            f"enabled_sleeves={','.join(allocator.get('enabled_sleeves') or []) or '-'}\n"
        )
    if urgent:
        parts.append(
            "URGENT ALERTS: "
            + "; ".join(str((x or {}).get("summary") or x)[:160] for x in urgent[:5])
            + "\n"
        )
    if alpaca_monthly:
        parts.append(
            "ALPACA MONTHLY: "
            f"selected={alpaca_monthly.get('current_cycle_tickers') or alpaca_monthly.get('selected_symbols') or '-'} "
            f"capital={alpaca_monthly.get('effective_capital')} "
            f"per_position={alpaca_monthly.get('per_position_notional')} "
            f"backtest_pf={alpaca_monthly.get('latest_summary_profit_factor')} "
            f"backtest_return_pct={alpaca_monthly.get('latest_summary_compounded_return_pct')}\n"
        )
    if alpaca_intraday:
        parts.append(
            "ALPACA INTRADAY PAPER: "
            f"tracked_positions={','.join(alpaca_intraday.get('tracked_positions') or []) or '-'} "
            f"pending_close={','.join(alpaca_intraday.get('pending_close_positions') or []) or '-'} "
            f"monthly_owned={','.join(alpaca_intraday.get('monthly_managed_positions') or []) or '-'} "
            f"paper_journal_pnl_usd={alpaca_intraday.get('today_pnl_usd')} "
            f"pnl_status={alpaca_intraday.get('pnl_status') or '-'} "
            f"entries_blocked={alpaca_intraday.get('entries_blocked')}\n"
        )
    top_cards = list(setup_scanner.get("top_cards") or [])[:12]
    if setup_scanner:
        parts.append(
            "SETUP SCANNER: "
            f"regime={setup_scanner.get('regime','?')} cards={setup_scanner.get('card_count',0)} "
            f"geometry_age_sec={setup_scanner.get('geometry_age_sec')} "
            f"router_age_sec={setup_scanner.get('router_age_sec')} "
            f"allocator_age_sec={setup_scanner.get('allocator_age_sec')}\n"
        )
        for card in top_cards[:8]:
            runtime = dict(card.get("runtime") or {})
            parts.append(
                "SETUP CARD: "
                f"{card.get('symbol')} {card.get('interval')} {card.get('side')} "
                f"{card.get('setup_type')} strategy={card.get('strategy')} score={card.get('score')} "
                f"level={card.get('level_price')} dist_atr={card.get('distance_atr')} "
                f"runtime_enabled={runtime.get('enabled')} runtime_risk={runtime.get('risk_mult')} "
                f"reasons={'; '.join(str(x) for x in (card.get('reasons') or [])[:4])}\n"
            )
    latest_reports = list(trade_forensics.get("latest_reports") or [])
    if trade_forensics:
        parts.append(
            "TRADE FORENSICS: "
            f"script_exists={trade_forensics.get('script_exists')} "
            f"latest_reports={len(latest_reports)}\n"
        )
        for report in latest_reports[:2]:
            parts.append(
                "FORENSICS REPORT: "
                f"{report.get('name')} age_sec={report.get('age_sec')} "
                f"preview={str(report.get('preview') or '-')[:500]}\n"
            )
    if strategy_settings:
        for source, block in strategy_settings.items():
            if not isinstance(block, dict):
                continue
            settings = dict(block.get("settings") or {})
            preview = []
            for key in sorted(settings)[:18]:
                value = settings[key]
                if isinstance(value, dict):
                    value = f"{value.get('count')} symbols: {','.join(value.get('preview') or [])}"
                preview.append(f"{key}={value}")
            parts.append(
                f"STRATEGY SETTINGS [{source}]: "
                f"exists={block.get('exists')} age_sec={block.get('age_sec')} "
                f"{'; '.join(preview)[:900]}\n"
            )
    if self_audit:
        parts.append(
            "SELF AUDIT: "
            f"highest={self_audit.get('highest_severity') or '-'} "
            f"age_sec={self_audit.get('age_sec')} "
            f"headline={self_audit.get('headline') or '-'}\n"
        )
        for item in list(self_audit.get("top_findings") or [])[:3]:
            parts.append(
                "SELF AUDIT FINDING: "
                f"{item.get('severity') or 'info'} {str(item.get('summary') or '-')[:240]} "
                f"detail={str(item.get('detail') or '-')[:300]}\n"
            )
    if project_doctor:
        parts.append(
            "PROJECT DOCTOR: "
            f"highest={project_doctor.get('highest_severity') or '-'} "
            f"age_sec={project_doctor.get('age_sec')} "
            f"headline={project_doctor.get('headline') or '-'} "
            f"live_ready={','.join(project_doctor.get('live_ready_sleeves') or []) or '-'} "
            f"watch={','.join(project_doctor.get('watch_candidates') or []) or '-'} "
            f"dirty_meaningful={project_doctor.get('meaningful_dirty_count')}\n"
        )
        for item in list(project_doctor.get("top_findings") or [])[:3]:
            parts.append(
                "PROJECT DOCTOR FINDING: "
                f"{item.get('severity') or 'info'} {str(item.get('summary') or '-')[:240]} "
                f"detail={str(item.get('detail') or '-')[:300]}\n"
            )


def _append_ai_runtime_packs_context(parts: List[str]) -> None:
    full_ctx = _json(_rt("ai_context", "full_context.json")) or {}
    if full_ctx:
        setup = dict(full_ctx.get("setups_scanner") or {})
        router_state = dict(full_ctx.get("router_state") or {})
        sources = dict(full_ctx.get("sources_used") or {})
        missing = [str(k) for k, v in sources.items() if not v]
        parts.append(
            "AI FULL CONTEXT PACK: "
            f"generated={full_ctx.get('generated_at_utc')} "
            f"setup_cards={setup.get('card_count')} "
            f"missing_sources={','.join(missing[:6]) or '-'}\n"
        )
        if router_state:
            profiles = dict(router_state.get("profiles") or {})
            parts.append(
                "AI DYNAMIC ROUTER: "
                f"generated={router_state.get('timestamp_utc')} "
                f"status={router_state.get('status')} regime={router_state.get('regime')} "
                f"scan_ok={router_state.get('scan_ok')} profiles={len(profiles)}\n"
            )
            for key in ("BREAKDOWN_SYMBOL_ALLOWLIST", "ATT1_SYMBOL_ALLOWLIST", "ARF1_SYMBOL_ALLOWLIST"):
                row = profiles.get(key)
                if not isinstance(row, dict):
                    continue
                symbols = row.get("symbols") or row.get("selected_symbols") or []
                parts.append(
                    f"AI ROUTER PROFILE {key}: symbols={','.join(str(x) for x in list(symbols)[:15]) or '-'}\n"
                )
        grouped = dict(full_ctx.get("grouped_no_signal") or {})
        for sleeve in ("att1", "asm1", "flat", "breakdown", "midterm"):
            rows = grouped.get(sleeve)
            if not isinstance(rows, dict):
                continue
            items = sorted(rows.items(), key=lambda kv: -int(kv[1] or 0))[:5]
            if items:
                parts.append(
                    f"AI NO_SIGNAL {sleeve}: "
                    + ", ".join(f"{k}={v}" for k, v in items)
                    + "\n"
                )
        for card in list(setup.get("cards_top") or [])[:10]:
            runtime = dict(card.get("runtime") or {})
            parts.append(
                "AI SETUP CARD: "
                f"{card.get('symbol')} {card.get('interval')} {card.get('side')} "
                f"{card.get('setup_type')} strategy={card.get('strategy')} score={card.get('score')} "
                f"runtime_enabled={runtime.get('enabled')} risk={runtime.get('risk_mult')} "
                f"reasons={'; '.join(str(x) for x in (card.get('reasons') or [])[:4])}\n"
            )

    extras = _json(_rt("ai_context", "extras.json")) or {}
    if extras:
        trade_history = dict(extras.get("trade_history") or {})
        bot_errors = dict(extras.get("bot_errors") or {})
        indicators = dict(extras.get("indicators") or {})
        bybit_positions = dict(extras.get("bybit_positions") or {})
        ohlc = dict(extras.get("ohlc") or {})
        memory_lines = list(extras.get("memory_lines") or [])
        parts.append(
            "AI EXTRAS PACK: "
            f"generated={extras.get('generated_at_utc')} "
            f"closed_trades_tail={trade_history.get('closed_in_tail')} "
            f"log_error_lines={bot_errors.get('error_lines_total')} "
            f"indicator_symbols={indicators.get('n_symbols')} "
            f"ohlc_symbols={ohlc.get('n_symbols_found')} "
            f"memory_lines={len(memory_lines)}\n"
        )
        per_sleeve = trade_history.get("per_sleeve") if isinstance(trade_history.get("per_sleeve"), dict) else {}
        for sleeve, row in sorted(
            per_sleeve.items(),
            key=lambda kv: -float((kv[1] or {}).get("n_closed") or 0),
        )[:8]:
            if not isinstance(row, dict):
                continue
            parts.append(
                f"AI TRADE HISTORY {sleeve}: "
                f"n={row.get('n_closed')} pf={row.get('profit_factor')} "
                f"wr={row.get('winrate_pct')} avg_pnl={row.get('avg_pnl')} "
                f"total_pnl={row.get('total_pnl')}\n"
            )
        for item in list(bot_errors.get("top_patterns") or [])[:6]:
            if not isinstance(item, dict):
                continue
            parts.append(
                "AI BOT ERROR PATTERN: "
                f"{item.get('pattern')} count={item.get('count')} "
                f"example={str(item.get('example') or '')[:220]}\n"
            )
        bybit_keys = [k for k in bybit_positions.keys() if not str(k).startswith("_") and k != "source"]
        if bybit_keys:
            parts.append("AI BYBIT POSITIONS/ORDERS: sections=" + ",".join(bybit_keys[:8]) + "\n")
        per_symbol = ohlc.get("per_symbol") if isinstance(ohlc.get("per_symbol"), dict) else {}
        for sym, row in list(per_symbol.items())[:5]:
            if not isinstance(row, dict):
                continue
            bars = list(row.get("bars_tail") or [])
            last_bar = bars[-1] if bars else None
            parts.append(
                f"AI OHLC {sym}: "
                f"tf={ohlc.get('timeframe_minutes')} bars={row.get('bars_count')} "
                f"last_bar={str(last_bar)[:220]}\n"
            )
        for mem in memory_lines[-8:]:
            if not isinstance(mem, dict):
                continue
            parts.append(
                "AI MEMORY LINE: "
                f"{mem.get('ts_utc') or ''} {mem.get('author') or ''} "
                f"{mem.get('topic') or ''}: {str(mem.get('text') or '')[:260]}\n"
            )

    ohlc_logs = _json(_rt("ai_context", "ohlc_and_logs.json")) or {}
    if ohlc_logs:
        log_tail = dict(ohlc_logs.get("log_tail") or {})
        parts.append(
            "AI OHLC/LOGS PACK: "
            f"generated={ohlc_logs.get('generated_at_utc')} "
            f"top_symbols={','.join(ohlc_logs.get('top_symbols') or []) or '-'} "
            f"log_lines={log_tail.get('n_lines')} "
            f"log_age_sec={log_tail.get('log_file_age_sec')}\n"
        )
        ohlc_pack = ohlc_logs.get("ohlc") if isinstance(ohlc_logs.get("ohlc"), dict) else {}
        for sym, data in list(ohlc_pack.items())[:3]:
            if not isinstance(data, dict):
                continue
            stats = dict(data.get("stats") or {})
            parts.append(
                f"AI CANDLE SNAPSHOT {sym}: "
                f"tf={data.get('timeframe')} close={stats.get('last_close')} "
                f"rsi14={stats.get('rsi_14')} atr14_pct={stats.get('atr_14_pct')} "
                f"dist_hi20_pct={stats.get('dist_to_hi_20_pct')} "
                f"dist_lo20_pct={stats.get('dist_to_lo_20_pct')} "
                f"cache_age_sec={data.get('cache_age_sec')}\n"
            )
        for line in list(log_tail.get("lines") or [])[-12:]:
            parts.append(f"AI RAW LOG TAIL: {str(line)[:260]}\n")

    blocker = _json(_rt("crypto_blocker", "latest.json")) or {}
    if blocker:
        parts.append(
            "CRYPTO BLOCKER REPORT: "
            f"generated={blocker.get('generated_at_utc')} "
            f"cards={blocker.get('cards_analyzed')} "
            f"classifications={json.dumps(blocker.get('classification_counts') or {}, ensure_ascii=False)}\n"
        )
        sleeves = dict(blocker.get("sleeves") or {})
        for sleeve_name in ("att1", "asm1", "flat", "breakdown", "brc1", "asb1"):
            sleeve = dict(sleeves.get(sleeve_name) or {})
            if not sleeve:
                continue
            top = list(sleeve.get("top_no_signal") or [])[:4]
            top_txt = ", ".join(f"{x.get('reason')}={x.get('count')}" for x in top) or "-"
            parts.append(
                f"CRYPTO BLOCKER {sleeve_name}: "
                f"try={sleeve.get('try')} entry={sleeve.get('entry')} "
                f"no_signal={sleeve.get('no_signal')} status={sleeve.get('status')} top={top_txt}\n"
            )


def _load_shared_history() -> List[Dict[str, str]]:
    if not _SHARED_HISTORY_PATH.exists():
        return []
    try:
        payload = json.loads(_SHARED_HISTORY_PATH.read_text())
    except Exception:
        return []
    if isinstance(payload, dict):
        payload = payload.get("messages", [])
    if not isinstance(payload, list):
        return []
    now = time.time()
    file_recent = (now - _SHARED_HISTORY_PATH.stat().st_mtime) <= float(_HISTORY_TTL_SEC or 0) if _HISTORY_TTL_SEC > 0 else True
    user_msgs: List[Dict[str, str]] = []
    last_assistant: Optional[Dict[str, str]] = None
    for item in payload[-_HISTORY_MAX:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        ts = int(item.get("ts") or 0)
        if _HISTORY_TTL_SEC > 0:
            if ts:
                if now - ts > float(_HISTORY_TTL_SEC):
                    continue
            elif not file_recent:
                continue
        if role == "user" and content:
            user_msgs.append({"role": role, "content": content, "ts": ts or int(now)})
        elif role in {"assistant", "system"} and content:
            last_assistant = {"role": role, "content": content, "ts": ts or int(now)}
    result = user_msgs[-_HISTORY_MAX:]
    if last_assistant:
        result.append(last_assistant)
    return result[-_HISTORY_MAX:]


def _save_shared_history(messages: List[Dict[str, str]]) -> None:
    cleaned = []
    now = int(time.time())
    for item in messages[-_HISTORY_MAX:]:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant", "system"} and content:
            cleaned.append({"role": role, "content": content, "ts": int(item.get("ts") or now)})
    _SHARED_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SHARED_HISTORY_PATH.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2))


def _merge_history(current: List[Dict[str, str]]) -> List[Dict[str, str]]:
    shared = _load_shared_history()
    merged = list(shared)
    now = int(time.time())
    for item in current:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant", "system"} or not content:
            continue
        if merged and merged[-1].get("role") == role and merged[-1].get("content") == content:
            continue
        merged.append({"role": role, "content": content, "ts": int(item.get("ts") or now)})
    return merged[-_HISTORY_MAX:]


# ── Rate limiter ──────────────────────────────────────────────────────────────

def _check_rate(email: str) -> None:
    now = time.time()
    times = [t for t in _CHAT_RATE.get(email, []) if now - t < 60]
    if len(times) >= _MAX_RPM:
        raise HTTPException(status_code=429, detail="Rate limit: max 20 messages/minute")
    times.append(now)
    _CHAT_RATE[email] = times


# ── Context builder ───────────────────────────────────────────────────────────

def _build_context() -> str:
    """Build a compact context string injected into every AI request."""
    parts: List[str] = []
    now = datetime.now(timezone.utc).isoformat()
    parts.append(f"=== BOT CONTEXT [{now}] ===\n")

    # Bot liveness
    hb = _json(_rt("bot_heartbeat.json"))
    hb_path = _rt("bot_heartbeat.json")
    hb_age = int(time.time() - hb_path.stat().st_mtime) if hb_path.exists() else -1
    alive = hb_path.exists() and hb_age < 120
    open_trades = hb.get("open_trades", 0) if hb else 0
    flat_note = "flat/no open positions" if alive and int(open_trades or 0) == 0 else "has open positions"
    parts.append(
        f"BOT: {'ALIVE' if alive else 'OFFLINE'} | heartbeat_age_sec={hb_age} | "
        f"open_trades={open_trades} ({flat_note})\n"
    )

    # Regime
    reg = _json(_rt("regime", "orchestrator_state.json")) or _json(_rt("regime.json"))
    if reg:
        reg_state_path = _rt("regime", "orchestrator_state.json")
        reg_age = int(time.time() - reg_state_path.stat().st_mtime) if reg_state_path.exists() else -1
        parts.append(
            f"REGIME: {reg.get('regime','?')} conf={reg.get('confidence','?')} "
            f"risk_mult={reg.get('global_risk_mult','?')} "
            f"longs={'Y' if reg.get('allow_longs') else 'N'} shorts={'Y' if reg.get('allow_shorts') else 'N'} "
            f"age_sec={reg_age}\n"
        )

    # Allocator sleeves: always prefer runtime control-plane truth over static policy.
    allocator = _json(_rt("control_plane", "portfolio_allocator_state.json")) or {}
    sleeve_states = dict(allocator.get("sleeves") or {})
    if sleeve_states:
        alloc_state_path = _rt("control_plane", "portfolio_allocator_state.json")
        alloc_age = int(time.time() - alloc_state_path.stat().st_mtime) if alloc_state_path.exists() else -1
        active = sorted(
            [
                str(name)
                for name, state in sleeve_states.items()
                if bool((state or {}).get("enabled"))
                and float((state or {}).get("final_risk_mult") or 0.0) > 0.0
            ]
        )
        inactive = sorted(
            [
                str(name)
                for name, state in sleeve_states.items()
                if not (
                    bool((state or {}).get("enabled"))
                    and float((state or {}).get("final_risk_mult") or 0.0) > 0.0
                )
            ]
        )
        parts.append(
            f"ALLOCATOR: status={allocator.get('status','?')} "
            f"degraded_kind={allocator.get('degraded_kind','none') or 'none'} "
            f"global_risk={allocator.get('allocator_global_risk_mult', allocator.get('global_risk_mult','?'))} "
            f"safe_mode={allocator.get('safe_mode', False)} "
            f"hard_block={allocator.get('hard_block_new_entries', False)} "
            f"overall_health={allocator.get('overall_health','?')} "
            f"overlap_ratio={allocator.get('portfolio_overlap_ratio','?')} "
            f"age_sec={alloc_age}\n"
        )
        if (
            str(allocator.get("status") or "").lower() == "degraded"
            and str(allocator.get("degraded_kind") or "").lower() == "protective_overlap"
        ):
            parts.append(
                "ALLOCATOR HUMAN MEANING: protective risk haircut for overlapping sleeves; "
                "not a broken allocator, not an emergency by itself.\n"
            )
        parts.append(f"SLEEVES ACTIVE: {', '.join(active) or 'none'}\n")
        parts.append(f"SLEEVES OFF: {', '.join(inactive[:8]) or 'none'}\n")

    # Control overlay (web-applied commands)
    overlay = _read_env(_OVERLAY_ENV)
    if overlay:
        parts.append(f"WEB OVERLAY: {json.dumps(overlay)}\n")

    # Recent trades summary
    trades_path = None
    for p in sorted(_RUNTIME_ROOT.glob("**/trades.csv"), key=lambda x: x.stat().st_mtime, reverse=True):
        trades_path = p
        break
    if trades_path:
        import csv
        rows = []
        try:
            with open(trades_path) as f:
                rows = list(csv.DictReader(f))
        except Exception:
            pass
        rows = rows[-50:]  # last 50
        if rows:
            wins = sum(1 for r in rows if float(r.get("pnl", 0) or 0) > 0)
            losses = sum(1 for r in rows if float(r.get("pnl", 0) or 0) < 0)
            net = sum(float(r.get("pnl", 0) or 0) for r in rows)
            strats = list({r.get("strategy", "?") for r in rows})[:6]
            parts.append(f"LAST 50 TRADES: wins={wins} losses={losses} net={net:.4f}\n")
            parts.append(f"ACTIVE STRATEGIES: {', '.join(strats)}\n")

    live_closes = _load_live_trade_event_closes(limit=50)
    if live_closes:
        wins = 0
        losses = 0
        net = 0.0
        strats = set()
        last = live_closes[-1]
        for evt in live_closes:
            pnl = float(evt.get("pnl") or evt.get("pnl_usd") or 0.0)
            net += pnl
            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1
            if evt.get("strategy"):
                strats.add(str(evt.get("strategy")))
        parts.append(
            f"LIVE CLOSED EVENTS LAST {len(live_closes)}: wins={wins} losses={losses} "
            f"net={net:.4f} strategies={', '.join(sorted(strats)) or '-'}\n"
        )
        parts.append(
            "LAST CLOSED EVENT: "
            f"strategy={last.get('strategy','?')} symbol={last.get('symbol','?')} "
            f"side={last.get('side','?')} pnl={float(last.get('pnl') or last.get('pnl_usd') or 0.0):.4f} "
            f"reason={last.get('close_reason') or last.get('reason') or '-'}\n"
        )

    # Alpaca
    alpaca_picks = _load_monthly_picks()
    if alpaca_picks:
        parts.append(f"ALPACA PICKS: {', '.join(alpaca_picks)}\n")

    _append_operator_snapshot_context(parts)
    _append_ai_runtime_packs_context(parts)

    # Health
    health = _json(_rt("strategy_health.json"))
    if health:
        statuses = {k: v.get("status", "?") for k, v in health.items() if isinstance(v, dict)}
        bad = [f"{k}={v}" for k, v in statuses.items() if v not in ("OK", "ok")]
        if bad:
            parts.append(f"HEALTH ALERTS: {', '.join(bad[:5])}\n")

    parts.append(
        "\n=== AVAILABLE CONTROL COMMANDS ===\n"
        "You can suggest control actions. The user will confirm before execution.\n"
        "If you suggest a command, first explain in plain language what is wrong, why the command helps, what evidence supports it, and what the risk/preconditions are.\n"
        "To suggest a command, include a JSON block: ```command\n{\"action\": \"...\", \"params\": {...}, \"evidence\": [\"...\"], \"risk\": \"low|medium|high\", \"preconditions\": [\"...\"]}\n```\n"
        "Available actions:\n"
        "  enable_sleeve   {\"sleeve\": \"asb1\"}          — set sleeve multipliers active\n"
        "  disable_sleeve  {\"sleeve\": \"ivb1\"}          — zero out sleeve risk mults\n"
        "  set_safe_mode   {}                             — set global risk mult to 0.25\n"
        "  clear_safe_mode {}                             — restore normal risk mult\n"
        "  reload_config   {}                             — trigger bot hot-reload\n"
        "  add_user        {\"email\": \"x@y.com\"}         — pre-create user slot (no TOTP yet)\n"
        "  remove_user     {\"email\": \"x@y.com\"}         — revoke web access\n"
    )

    return "".join(parts)


# ── Control command executor ──────────────────────────────────────────────────

_VALID_SLEEVE_NAMES = {
    # original sleeves
    "breakout", "breakdown", "flat", "sloped", "att1", "asm1",
    "midterm", "midterm_short", "midterm_short_v2", "range_scalp",
    "asb1", "hzbo1", "bounce1", "impulse", "pump_fade",
    "elder_ts", "elder_ts_v3", "vwap_mr",
    # v7 new sleeves
    "breakdown_v2", "slope_choch", "liq_cascade", "funding_rev", "micro_scalp",
}

_CRYPTO_SLEEVES = set(_VALID_SLEEVE_NAMES)
_EQUITY_BACKTEST_SLEEVES = {
    "alpaca_monthly",
    "alpaca_intraday",
    "alpaca_intraday_v1",
    "alpaca_intraday_v3",
    "equities_monthly",
    "equities_intraday",
}

_COMMAND_TITLES = {
    "enable_sleeve": "Включить крипто-рукав",
    "disable_sleeve": "Выключить крипто-рукав",
    "set_safe_mode": "Включить защитный режим",
    "clear_safe_mode": "Выключить защитный режим",
    "reload_config": "Перезагрузить конфиг бота",
    "add_user": "Создать слот пользователя",
    "remove_user": "Удалить пользователя",
    "run_backtest": "Запросить бэктест",
    "set_sleeve_params": "Предложить параметры рукава",
    "set_global_params": "Предложить глобальные параметры",
}


def _symbol_market(symbol: str) -> str:
    s = str(symbol or "").strip().upper()
    if not s:
        return "unknown"
    if s.endswith(("USDT", "USDC", "USDTPERP")) or "/" in s or ":" in s:
        return "crypto"
    return "equities"


def _params_symbols(params: dict) -> List[str]:
    raw = params.get("symbols")
    if raw is None:
        raw = params.get("symbol")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [x.strip().upper() for x in raw.replace(",", " ").split() if x.strip()]
    if isinstance(raw, list):
        return [str(x).strip().upper() for x in raw if str(x).strip()]
    return []


def _infer_command_market(action: str, params: dict) -> str:
    sleeve = str(params.get("sleeve") or params.get("strategy") or "").strip().lower()
    if sleeve in _CRYPTO_SLEEVES:
        return "crypto"
    if sleeve in _EQUITY_BACKTEST_SLEEVES:
        return "equities"
    symbols = _params_symbols(params)
    markets = {_symbol_market(x) for x in symbols}
    markets.discard("unknown")
    if len(markets) == 1:
        return next(iter(markets))
    return "unknown"


def _validate_command(action: str, params: dict) -> Tuple[bool, List[str], str]:
    """Validate AI-suggested commands before the UI can execute them."""
    action = str(action or "").strip()
    params = dict(params or {})
    reasons: List[str] = []

    if action in {"enable_sleeve", "disable_sleeve"}:
        sleeve = str(params.get("sleeve") or "").strip().lower()
        if sleeve not in _VALID_SLEEVE_NAMES:
            reasons.append(f"unknown crypto sleeve '{sleeve or '-'}'")
        return (not reasons, reasons, "crypto")

    if action == "run_backtest":
        sleeve = str(params.get("sleeve") or params.get("strategy") or "").strip().lower()
        symbols = _params_symbols(params)
        market = _infer_command_market(action, params)
        if not sleeve:
            reasons.append("missing sleeve/strategy")
        elif sleeve in _CRYPTO_SLEEVES:
            bad = [s for s in symbols if _symbol_market(s) != "crypto"]
            if bad:
                reasons.append(
                    f"market mismatch: '{sleeve}' is a crypto sleeve, but symbols are equities: {', '.join(bad)}"
                )
        elif sleeve in _EQUITY_BACKTEST_SLEEVES:
            bad = [s for s in symbols if _symbol_market(s) != "equities"]
            if bad:
                reasons.append(
                    f"market mismatch: '{sleeve}' is an equities sleeve, but symbols are crypto: {', '.join(bad)}"
                )
        else:
            reasons.append(f"unknown backtest sleeve/strategy '{sleeve}'")
        if not symbols:
            reasons.append("missing symbols")
        period = str(params.get("period") or params.get("days") or "").strip()
        if not period:
            reasons.append("missing period/days")
        return (not reasons, reasons, market)

    if action in {"set_sleeve_params", "set_global_params"}:
        reasons.append("direct parameter mutation is not enabled; create a proposal + backtest first")
        return (False, reasons, _infer_command_market(action, params))

    if action in {"set_safe_mode", "clear_safe_mode", "reload_config", "add_user", "remove_user"}:
        return (True, [], _infer_command_market(action, params))

    reasons.append(f"unknown action '{action or '-'}'")
    return (False, reasons, "unknown")


def _decorate_command(raw: dict) -> dict:
    """Add human-readable, validated metadata for the frontend approval box."""
    cmd = dict(raw or {})
    action = str(cmd.get("action") or "").strip()
    params = dict(cmd.get("params") or {})
    ok, reasons, market = _validate_command(action, params)
    sleeve = str(params.get("sleeve") or params.get("strategy") or "").strip()
    symbols = _params_symbols(params)
    title = _COMMAND_TITLES.get(action, f"Команда: {action or '-'}")
    summary_bits = []
    if sleeve:
        summary_bits.append(f"рукав/стратегия: {sleeve}")
    if symbols:
        summary_bits.append(f"символы: {', '.join(symbols[:12])}")
    if params.get("period") or params.get("days"):
        summary_bits.append(f"период: {params.get('period') or params.get('days')}")
    summary = "; ".join(summary_bits) or "параметры не указаны"
    cmd["title"] = title
    cmd["summary"] = summary
    cmd["market"] = market
    cmd["blocked"] = not ok
    cmd["validation_errors"] = reasons
    cmd.setdefault("evidence", [])
    cmd.setdefault("preconditions", [])
    cmd.setdefault("risk", "unknown")
    return cmd

_ENABLE_ENV_MAP = {
    "breakout": "ENABLE_BREAKOUT_TRADING", "breakdown": "ENABLE_BREAKDOWN_TRADING",
    "flat": "ENABLE_FLAT_TRADING", "sloped": "ENABLE_SLOPED_TRADING",
    "att1": "ENABLE_ATT1_TRADING", "asm1": "ENABLE_ASM1_TRADING",
    "midterm": "ENABLE_MIDTERM_TRADING", "midterm_short": "ENABLE_MTSV1_TRADING",
    "midterm_short_v2": "ENABLE_MTSV2_TRADING", "range_scalp": "ENABLE_RANGE_TRADING",
    "asb1": "ENABLE_ASB1_TRADING", "hzbo1": "ENABLE_HZBO1_TRADING",
    "bounce1": "ENABLE_BOUNCE1_TRADING", "impulse": "ENABLE_IVB1_TRADING",
    "pump_fade": "ENABLE_PUMP_FADE_TRADING", "elder_ts": "ENABLE_ELDER_TRADING",
    "elder_ts_v3": "ENABLE_ETS3_TRADING", "vwap_mr": "ENABLE_VWAP_TRADING",
    # v7 new sleeves
    "breakdown_v2": "ENABLE_BREAKDOWN2_TRADING",
    "slope_choch":  "ENABLE_SLOPE_CHOCH_TRADING",
    "liq_cascade":  "ENABLE_LC_TRADING",
    "funding_rev":  "ENABLE_FR_TRADING",
    "micro_scalp":  "ENABLE_MSCALP_TRADING",
}


def _write_overlay(updates: Dict[str, str]) -> None:
    """Merge updates into the web control overlay env file."""
    existing = _read_env(_OVERLAY_ENV)
    existing.update(updates)
    _OVERLAY_ENV.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in sorted(existing.items())]
    _OVERLAY_ENV.write_text("\n".join(lines) + "\n")


def _audit(email: str, action: str, params: dict, result: str) -> None:
    _AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "user": email,
        "action": action,
        "params": params,
        "result": result,
    }
    with open(_AUDIT_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def execute_command(action: str, params: dict, email: str) -> str:
    """Execute a confirmed control command. Returns result message."""
    ok, reasons, _market = _validate_command(action, params)
    if not ok:
        result = "Blocked by command validator: " + "; ".join(reasons)
        _audit(email, action, params, result)
        return result

    hb = _json(_rt("bot_heartbeat.json")) or {}
    open_trades = int(hb.get("open_trades", 0) or 0)
    if action == "enable_sleeve":
        sleeve = params.get("sleeve", "").lower()
        if sleeve not in _VALID_SLEEVE_NAMES:
            return f"Unknown sleeve: {sleeve}"
        env_key = _ENABLE_ENV_MAP.get(sleeve)
        if env_key:
            _write_overlay({env_key: "1"})
        _audit(email, action, params, f"enabled {sleeve}")
        return f"✓ Sleeve '{sleeve}' enabled in overlay. Bot will pick up on next reload."

    elif action == "disable_sleeve":
        sleeve = params.get("sleeve", "").lower()
        if sleeve not in _VALID_SLEEVE_NAMES:
            return f"Unknown sleeve: {sleeve}"
        env_key = _ENABLE_ENV_MAP.get(sleeve)
        if env_key:
            _write_overlay({env_key: "0"})
        _audit(email, action, params, f"disabled {sleeve}")
        return f"✓ Sleeve '{sleeve}' disabled in overlay."

    elif action == "set_safe_mode":
        _write_overlay({"WEB_SAFE_MODE": "1", "PORTFOLIO_GLOBAL_RISK_MULT": "0.25"})
        _audit(email, action, params, "safe_mode=ON risk=0.25")
        return "⚠️ Safe mode ON — global risk mult set to 0.25×."

    elif action == "clear_safe_mode":
        _write_overlay({"WEB_SAFE_MODE": "0", "PORTFOLIO_GLOBAL_RISK_MULT": "1.0"})
        _audit(email, action, params, "safe_mode=OFF")
        return "✓ Safe mode cleared — risk back to normal."

    elif action == "reload_config":
        if open_trades > 0:
            _audit(email, action, params, f"blocked open_trades={open_trades}")
            return f"Reload blocked: bot has {open_trades} open trade(s). Close or reconcile them first."
        # Send SIGHUP to bot process if PID file exists
        pid_path = _rt("bot.pid")
        if pid_path.exists():
            try:
                import signal
                pid = int(pid_path.read_text().strip())
                os.kill(pid, signal.SIGHUP)
                _audit(email, action, params, f"SIGHUP sent to pid {pid}")
                return f"✓ SIGHUP sent to bot (PID {pid}) — config will reload."
            except Exception as e:
                return f"Could not send SIGHUP: {e}"
        _audit(email, action, params, "no pid file")
        return "PID file not found — restart bot manually to apply overlay."

    elif action == "add_user":
        # Pre-create user slot without TOTP (they run setup_totp.py separately)
        from ..auth import _load_config, _save_config
        target_email = params.get("email", "").strip().lower()
        if not target_email or "@" not in target_email:
            return "Invalid email."
        cfg = _load_config()
        cfg.setdefault("users", {})[target_email] = {"enabled": False, "note": "pending_totp_setup"}
        _save_config(cfg)
        _audit(email, action, params, f"added slot for {target_email}")
        return f"✓ User slot created for {target_email}. They must run setup_totp.py to activate."

    elif action == "remove_user":
        from ..auth import _load_config, _save_config
        target_email = params.get("email", "").strip().lower()
        if target_email == email:
            return "Cannot remove yourself."
        cfg = _load_config()
        if target_email in cfg.get("users", {}):
            del cfg["users"][target_email]
            _save_config(cfg)
            _audit(email, action, params, f"removed {target_email}")
            return f"✓ User {target_email} removed."
        return f"User {target_email} not found."

    elif action == "run_backtest":
        queue_path = _ROOT / "runtime" / "ai_operator" / "backtest_requests.jsonl"
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        item = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "user": email,
            "action": action,
            "params": params,
            "status": "queued_for_operator",
            "note": "Web AI can request validated backtests; execution is handled by the research runner, not by arbitrary shell.",
        }
        with open(queue_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
        _audit(email, action, params, "validated backtest request queued")
        return (
            "✓ Backtest request is valid and queued for the research runner. "
            "It was not executed as an arbitrary shell command."
        )

    else:
        return f"Unknown action: {action}"


# ── Models ────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    execute_command: Optional[Dict[str, Any]] = None  # confirmed command to run


class ChatResponse(BaseModel):
    reply: str
    suggested_command: Optional[Dict[str, Any]] = None
    command_result: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, email: str = Depends(require_admin)):
    """Send a message to the AI with full bot context.

    If body.execute_command is set, execute that command first, then send chat.
    """
    _check_rate(email)

    # Execute a confirmed command first if provided
    cmd_result = None
    if body.execute_command:
        action = body.execute_command.get("action", "")
        params = body.execute_command.get("params", {})
        cmd_result = execute_command(action, params, email)

    # ── pick AI provider: DeepSeek > Anthropic ───────────────────────────────
    deepseek_key  = os.getenv("DEEPSEEK_API_KEY", "").strip()
    anthropic_key = (os.getenv("ANTHROPIC_API_KEY") or os.getenv("AI_API_KEY", "")).strip()

    if not deepseek_key and not anthropic_key:
        return ChatResponse(
            reply=(
                "⚠️ AI не настроен. Добавь в .env файл:\n"
                "  DEEPSEEK_API_KEY=sk-...    (дешевле, рекомендуется)\n"
                "  или ANTHROPIC_API_KEY=sk-ant-...\n"
                "Затем перезапусти сервер."
            ),
            command_result=cmd_result,
        )

    system_prompt = (
        "You are an AI assistant embedded in a cryptocurrency + equities trading bot dashboard. "
        "You help the operator understand performance, diagnose issues, and manage the system. "
        "You have access to live bot data (injected below). "
        "Be concise and precise. When you spot issues, say so directly. "
        "Never treat stale chat memory as a source of truth when current runtime ages disagree. "
        "Do not claim you know everything; say what the injected live context shows. "
        "open_trades=0 means flat/no open positions, not offline, when BOT is ALIVE. "
        "The server has a backtest infrastructure, but this chat may not have a direct safe execution endpoint yet; propose an approved/spec-based backtest instead of saying the project has no backtester. "
        "Do not recommend enabling a sleeve from setup cards alone. A setup card is only a candidate; live enablement requires regime fit plus backtest/research evidence from the injected context. "
        "In bear_trend, do not recommend ASB1/long-bounce activation unless current injected research shows a validated pass; if evidence is missing or weak, recommend a backtest/proposal instead. "
        "If allocator status is degraded only because degraded_kind=protective_overlap, explain it as a protective overlap risk haircut, not a broken allocator or critical incident. "
        "Do not recommend safe mode or reload solely for protective_overlap. "
        "Do not convert websocket connect/disconnect counters into percent data loss unless the live context shows ws guard active, critical_streak/no_connect_streak, or stale/zero market messages. "
        "When suggesting control commands, explain the issue in human language first, cite current evidence from the injected context, state risk/preconditions, and only then emit a ```command JSON block. "
        "Never suggest actions that could cause significant losses without clear justification. "
        "Never suggest reload/restart while open trades exist unless the injected context proves an active emergency.\n\n"
        + _build_context()
    )
    current_messages = [{"role": m.role, "content": m.content} for m in body.messages[-20:]]
    messages_payload = _merge_history(current_messages)

    try:
        if deepseek_key:
            # ── DeepSeek (OpenAI-compatible API) ─────────────────────────────
            import urllib.request as _urllib_req
            import ssl as _ssl

            model = os.getenv("WEB_AI_MODEL", "deepseek-chat")
            payload = json.dumps({
                "model": model,
                "max_tokens": 1500,
                "temperature": 0.4,
                "messages": [{"role": "system", "content": system_prompt}] + messages_payload,
            }).encode()
            req = _urllib_req.Request(
                "https://api.deepseek.com/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {deepseek_key}",
                },
            )
            ctx = _ssl.create_default_context()
            with _urllib_req.urlopen(req, context=ctx, timeout=60) as resp:
                js = json.loads(resp.read().decode())
            reply_text = js["choices"][0]["message"]["content"].strip()

        else:
            # ── Anthropic Claude ──────────────────────────────────────────────
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            model = os.getenv("WEB_AI_MODEL", "claude-sonnet-4-6")
            response = client.messages.create(
                model=model,
                max_tokens=1500,
                system=system_prompt,
                messages=messages_payload,
            )
            reply_text = response.content[0].text

        # Parse suggested command from reply if any
        suggested_cmd = None
        import re
        cmd_match = re.search(r"```command\s*\n(\{.*?\})\s*\n```", reply_text, re.DOTALL)
        if cmd_match:
            try:
                suggested_cmd = _decorate_command(json.loads(cmd_match.group(1)))
            except Exception:
                pass

        _save_shared_history(messages_payload + [{"role": "assistant", "content": reply_text}])

        return ChatResponse(
            reply=reply_text,
            suggested_command=suggested_cmd,
            command_result=cmd_result,
        )

    except Exception as e:
        return ChatResponse(
            reply=f"AI error: {str(e)[:200]}",
            command_result=cmd_result,
        )


@router.get("/audit")
async def get_audit(email: str = Depends(require_admin)):
    """Recent command audit log."""
    if not _AUDIT_LOG.exists():
        return {"entries": []}
    entries = []
    for line in _AUDIT_LOG.read_text().splitlines()[-50:]:
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return {"entries": list(reversed(entries))}


@router.get("/context")
async def get_context(email: str = Depends(require_admin)):
    """Return the current context that gets injected into AI. Useful for debugging."""
    return {"context": _build_context()}


@router.get("/full-context")
async def get_full_context(email: str = Depends(require_admin)):
    """Return AI ORACLE-stage context plus source runtime packs."""
    return {
        "context": _build_context(),
        "operator_snapshot": _json(_rt("operator", "operator_snapshot.json")),
        "ai_full_context": _json(_rt("ai_context", "full_context.json")),
        "ai_extras": _json(_rt("ai_context", "extras.json")),
        "ai_ohlc_and_logs": _json(_rt("ai_context", "ohlc_and_logs.json")),
        "crypto_blocker": _json(_rt("crypto_blocker", "latest.json")),
        "self_audit": _json(_rt("self_audit", "latest.json")),
        "project_doctor": _json(_rt("project_doctor", "latest.json")),
        "weekly_live_vs_backtest_reports": _latest_report_files("reports/weekly_live_vs_backtest", limit=8),
        "trade_forensics_reports": _latest_report_files("reports/trade_forensics", limit=8),
    }


@router.get("/code-context")
async def get_code_context(email: str = Depends(require_admin)):
    """Return compact code/config health context for AI review without dumping secrets."""
    important_files = [
        "smart_pump_reversal_bot.py",
        "bot/operator_snapshot.py",
        "scripts/build_portfolio_allocator.py",
        "scripts/allocator_diagnostic.py",
        "scripts/build_project_doctor_report.py",
        "scripts/setup_server_crons.sh",
        "configs/portfolio_allocator_policy.json",
        "configs/strategy_health.json",
        "configs/strategy_profile_registry.json",
    ]
    files = []
    for rel in important_files:
        p = _ROOT / rel
        files.append(
            {
                "path": rel,
                "exists": p.exists(),
                "mtime": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat() if p.exists() else None,
                "size_bytes": p.stat().st_size if p.exists() else None,
            }
        )
    return {
        "project_doctor": _json(_rt("project_doctor", "latest.json")),
        "self_audit": _json(_rt("self_audit", "latest.json")),
        "operator_snapshot_age_sec": int(time.time() - _rt("operator", "operator_snapshot.json").stat().st_mtime)
        if _rt("operator", "operator_snapshot.json").exists()
        else None,
        "important_files": files,
        "note": "This endpoint is read-only and intentionally omits .env/secrets.",
    }


@router.get("/history")
async def get_history(email: str = Depends(require_admin)):
    """Return shared AI history used by web chat."""
    return {"messages": _load_shared_history()}
