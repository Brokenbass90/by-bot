"""AI Chat with full bot context, proposal inbox, and truth-first controls.

The AI sees:
  - Current regime, confidence, risk mult
  - All allocator sleeves and their status
  - Last 50 trades + strategy performance summary
  - Strategy health
  - Bot heartbeat / liveness
  - Alpaca monthly picks and metrics

Trading mutations are proposal-only until the live bot exposes a verified,
acknowledged consumer.  The implemented write paths are the operator-review
backtest inbox and admin user management.

All executed commands are written to runtime/web_audit_log.jsonl.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from bot.ai_context import append_ai_context_lines, compact_ai_full_context

from ..deps import require_admin, require_auth

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


def _http_error_summary(exc: Exception) -> str:
    code = getattr(exc, "code", None) or getattr(exc, "status", None)
    if code == 402:
        return "AI provider returned 402 Payment Required"
    if code:
        return f"AI provider returned HTTP {code}"
    return str(exc)[:160] or exc.__class__.__name__


def _local_chat_fallback(command_result: Optional[str] = None, reason: str = "") -> "ChatResponse":
    hb = _json(_rt("bot_heartbeat.json")) or {}
    alloc = _json(_rt("control_plane", "portfolio_allocator_state.json")) or {}
    op = _json(_rt("operator", "operator_snapshot.json")) or {}
    cp_alloc = dict((op.get("control_plane") or {}).get("allocator") or {})
    alpaca = dict(op.get("alpaca") or {})
    monthly = dict(alpaca.get("monthly") or {})
    enabled = alloc.get("exposure", {}).get("enabled_sleeves") or cp_alloc.get("enabled_sleeves") or []
    reason_line = f" External AI недоступен: {reason}." if reason else ""
    reply = (
        "Работаю в локальном fallback-режиме без внешней LLM."
        f"{reason_line}\n\n"
        f"Серверный снимок: open_trades={hb.get('open_trades')}, dry_run={hb.get('dry_run')}, "
        f"regime={hb.get('regime') or 'unknown'}.\n"
        f"Control-plane: status={alloc.get('status') or cp_alloc.get('status')}, "
        f"hard_block={bool(alloc.get('hard_block_new_entries') or cp_alloc.get('hard_block_new_entries'))}, "
        f"enabled_sleeves={','.join(enabled) or '-'}.\n"
        f"Alpaca monthly: selected={monthly.get('current_cycle_tickers') or monthly.get('current_cycle_selected') or '-'}.\n\n"
        "Следующий лучший шаг: если crypto за 24 часа после strict3 всё ещё не даёт входов, "
        "строим setup-to-entry blocker report по каждому sleeve и чиним конкретный фильтр."
    )
    return ChatResponse(reply=reply, command_result=command_result)


def _local_setup_analysis(body: "SetupAnalysisRequest", *, reason: str = "") -> "SetupAnalysisResponse":
    side = str(body.side or "").lower()
    strategy = str(body.strategy or "").lower()
    setup_type = str(body.setup_type or "").lower()
    runtime = str(body.runtime_status or "").lower()
    regime = str(body.regime or "").lower()
    score = float(body.score or 0.0)
    dist = float(body.distance_atr or 999.0)
    funding = body.funding_rate_pct
    reasons = [str(x).lower() for x in (body.reasons or [])]

    verdict = "ok"
    notes: List[str] = []
    risks: List[str] = []

    if runtime in {"pause", "watch", "false", "disabled"}:
        verdict = "weak"
        notes.append(f"runtime={runtime}: это кандидат для наблюдения, а не разрешение на вход")
    if "bear" in regime and side == "long" and strategy in {"asb1", "bounce1", "support_bounce"}:
        verdict = "skip"
        notes.append("лонговый отскок конфликтует с медвежьим режимом без свежего успешного исследования")
    if side == "short" and strategy in {"flat", "breakdown", "arf1"} and "bear" in regime:
        notes.append("направление SHORT совпадает с текущим медвежьим режимом")
        if verdict == "ok" and score >= 90 and dist <= 0.8:
            verdict = "strong"
    if strategy in {"flat", "arf1"} and ("near resistance" in reasons or "resistance" in setup_type):
        notes.append("контекст сопротивления подходит для логики flat/fade")
    if strategy == "breakdown" and dist <= 0.5:
        notes.append("цена достаточно близко к уровню, можно ждать чистый триггер стратегии")
    if funding is not None and side == "short" and funding > 0.03:
        notes.append("положительный funding дополнительно поддерживает SHORT carry")
    if funding is not None and side == "short" and funding < -0.03:
        risks.append("отрицательный funding делает удержание SHORT дороже")
        if verdict == "strong":
            verdict = "ok"
    if score < 75:
        verdict = "weak" if verdict != "skip" else verdict
        risks.append("score недостаточно высокий для продвижения без подтверждения бэктестом")
    if dist > 1.5:
        verdict = "weak" if verdict != "skip" else verdict
        risks.append("setup далеко от уровня, качество входа может быть слабым")

    if not notes:
        notes.append("setup требует подтверждения live-стратегией, сама карточка ещё не сделка")
    if reason:
        notes.append(f"внешний AI недоступен: {reason}")
    if not risks:
        risks.append("главный риск: scanner card не гарантирует, что стратегия реально даст вход")

    return SetupAnalysisResponse(
        verdict=verdict,
        reasoning=". ".join(notes[:4]) + ".",
        risk_note=risks[0],
        model="local-setup-fallback",
    )


def _has_cyrillic(text: str) -> bool:
    return bool(re.search(r"[А-Яа-яЁё]", text or ""))


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _append_cross_exchange_context(parts: List[str], full_ctx: Dict[str, Any]) -> None:
    raw = full_ctx.get("cross_exchange_funding")
    validated = full_ctx.get("cross_exchange_funding_validated")
    shadow = full_ctx.get("cross_exchange_funding_shadow")
    roi = full_ctx.get("arb_roi_estimate")
    account_status = full_ctx.get("exchange_account_readonly_status")
    arb_account_status = full_ctx.get("exchange_account_status")
    arb_dry_run = full_ctx.get("cross_exchange_arb_dry_run")

    if isinstance(account_status, dict):
        binance = account_status.get("binance") if isinstance(account_status.get("binance"), dict) else {}
        bitget = account_status.get("bitget") if isinstance(account_status.get("bitget"), dict) else {}
        parts.append(
            "AI CROSS-EXCHANGE ACCOUNT READONLY: "
            f"generated={account_status.get('generated_at_utc')} "
            f"binance_ok={binance.get('ok')} binance_usdt_available={((binance.get('usdt_balance') or {}).get('available_balance'))} "
            f"bitget_ok={bitget.get('ok')} bitget_usdt_available={((bitget.get('usdt_account') or {}).get('available'))} "
            "trading_locked_until_explicit_canary=true\n"
        )

    if isinstance(arb_account_status, dict):
        exch = arb_account_status.get("exchanges") if isinstance(arb_account_status.get("exchanges"), dict) else {}
        summary = []
        for name in ("bybit", "binance", "bitget"):
            row = exch.get(name) if isinstance(exch.get(name), dict) else {}
            summary.append(
                f"{name}:ok={row.get('ok')},available={row.get('available_usdt')},equity={row.get('equity_usdt')}"
            )
        parts.append(
            "AI CROSS-EXCHANGE ACCOUNT STATUS: "
            f"generated={arb_account_status.get('generated_at_utc')} "
            f"validated_pairs={arb_account_status.get('validated_pair_count')} "
            f"{'; '.join(summary)} "
            "trading_locked_until_explicit_canary=true\n"
        )

    if isinstance(arb_dry_run, dict):
        plans = list(arb_dry_run.get("plans") or [])[:6]
        parts.append(
            "AI CROSS-EXCHANGE DRY RUN: "
            f"generated={arb_dry_run.get('generated_at_utc')} "
            f"validated={arb_dry_run.get('validated_count')} ready={arb_dry_run.get('ready_count')} "
            f"mode={arb_dry_run.get('mode')} trading_locked={arb_dry_run.get('trading_locked')}\n"
        )
        for plan in plans:
            if not isinstance(plan, dict):
                continue
            parts.append(
                "AI ARB DRY RUN PLAN: "
                f"{plan.get('pair_key')} ready={plan.get('ready_for_order_dry_run')} "
                f"net_24h={plan.get('estimated_net_pct_for_hold')}% "
                f"notional={plan.get('planned_notional_usdt_per_leg')} "
                f"blockers={'; '.join(plan.get('blockers') or []) or '-'}\n"
            )

    if isinstance(raw, dict):
        rows = list(raw.get("opportunities") or [])[:5]
        top = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            top.append(
                f"{item.get('symbol')} {item.get('long_exchange')}→{item.get('short_exchange')} "
                f"monthly={item.get('spread_monthly_pct')}%"
            )
        parts.append(
            "AI CROSS-EXCHANGE RAW: "
            f"generated={raw.get('generated_at_utc')} rows={raw.get('rows')} "
            f"opportunities={len(raw.get('opportunities') or [])} top={'; '.join(top) or '-'}\n"
        )

    if isinstance(validated, dict):
        items = list(validated.get("items") or [])[:6]
        parts.append(
            "AI CROSS-EXCHANGE VALIDATED: "
            f"generated={validated.get('generated_at_utc')} "
            f"count={validated.get('validated_count')} "
            f"notional_per_leg={validated.get('notional_usd_per_leg')} "
            f"hold_h={validated.get('hold_hours')}\n"
        )
        for item in items:
            if not isinstance(item, dict):
                continue
            parts.append(
                "AI ARB VALIDATED ITEM: "
                f"{item.get('pair_key') or (str(item.get('symbol')) + ':' + str(item.get('long_exchange')) + '→' + str(item.get('short_exchange')))} "
                f"net_24h={item.get('estimated_net_pct_for_hold')}% "
                f"persistence={item.get('persistence_count_in_window')} "
                f"error={item.get('error') or '-'}\n"
            )

    if isinstance(shadow, dict):
        open_rows = list(shadow.get("open") or shadow.get("open_positions") or [])
        closed_rows = list(shadow.get("closed") or shadow.get("closed_positions") or [])
        latest_open = []
        equal_weight_values = []
        for item in open_rows[:6]:
            if not isinstance(item, dict):
                continue
            updates = item.get("updates") if isinstance(item.get("updates"), list) else []
            last = updates[-1] if updates and isinstance(updates[-1], dict) else item
            pct = _as_float(
                last.get("total_shadow_pct_total_capital")
                if isinstance(last, dict) and last.get("total_shadow_pct_total_capital") is not None
                else last.get("total_estimated_pct_total_capital")
                if isinstance(last, dict)
                else item.get("estimated_total_capital_pct")
            )
            equal_weight_values.append(pct)
            latest_open.append(
                f"{item.get('pair_key') or item.get('symbol')} age_h={_as_float(last.get('age_hours') if isinstance(last, dict) else item.get('age_hours')):.1f} "
                f"pnl={pct:.3f}% valid={last.get('current_validated') if isinstance(last, dict) else item.get('current_validated')}"
            )
        equal_weight_pct = (
            sum(equal_weight_values) / len(equal_weight_values)
            if equal_weight_values
            else 0.0
        )
        parts.append(
            "AI CROSS-EXCHANGE SHADOW: "
            f"generated={shadow.get('generated_at_utc')} open={shadow.get('open_count')} "
            f"closed={shadow.get('closed_count')} "
            f"sum_pct={shadow.get('open_shadow_total_capital_pct', shadow.get('open_estimated_total_capital_pct'))} "
            f"model={shadow.get('model_version') or 'legacy'} "
            f"equal_weight_basket_pct={equal_weight_pct:.3f} "
            f"closed_items={len(closed_rows)}\n"
        )
        for row in latest_open:
            parts.append(f"AI ARB SHADOW OPEN: {row}\n")

    if isinstance(roi, dict):
        sample = roi.get("sample") if isinstance(roi.get("sample"), dict) else {}
        projection = roi.get("projection") if isinstance(roi.get("projection"), dict) else {}
        parts.append(
            "AI ARB ROI EVIDENCE: "
            f"status={roi.get('status')} closed_cycles={sample.get('closed_cycles')} "
            f"open_cycles={sample.get('open_cycles')} win_rate={sample.get('win_rate')} "
            f"next_expected_close={sample.get('next_expected_close_utc')} "
            f"monthly_pct_deployed={projection.get('monthly_return_pct_deployed_capital')} "
            "rule=open shadow PnL is not earned return; never project monthly or annual ROI "
            "until status=projection_available\n"
        )


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
        _append_cross_exchange_context(parts, full_ctx)

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
    append_ai_context_lines(parts, _ROOT)

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
        if (
            str(allocator.get("status") or "").lower() == "disabled"
            and not bool(allocator.get("safe_mode"))
            and not bool(allocator.get("hard_block_new_entries"))
        ):
            parts.append(
                "ALLOCATOR HUMAN MEANING: allocator overlay is disabled, but approved live env remains active; "
                "new entries are not globally blocked.\n"
            )
        parts.append(f"SLEEVES ACTIVE: {', '.join(active) or 'none'}\n")
        parts.append(f"SLEEVES OFF: {', '.join(inactive[:8]) or 'none'}\n")

    # Legacy web overlay is not consumed by the live bot.  Keep it visible only
    # as explicitly non-effective history so stale files cannot mislead the AI.
    overlay = _read_env(_OVERLAY_ENV)
    if overlay:
        try:
            overlay_age = max(0, int(time.time() - _OVERLAY_ENV.stat().st_mtime))
        except OSError:
            overlay_age = -1
        parts.append(
            "WEB OVERLAY (historical_non_effective_proposal; no live acknowledgement): "
            f"age_sec={overlay_age} values={json.dumps(overlay)}\n"
        )

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
            parts.append(
                f"MIXED HISTORICAL TRADES LAST 50: wins={wins} losses={losses} net={net:.4f}; "
                "may include old strategies, versions and risk settings; not current-canary PF.\n"
            )
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
            f"MIXED LIVE CLOSED EVENTS LAST {len(live_closes)}: wins={wins} losses={losses} "
            f"net={net:.4f} strategies={', '.join(sorted(strats)) or '-'}; "
            "not a current-canary window unless a deployment boundary is supplied.\n"
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
        "Implemented actions:\n"
        "  run_backtest    {\"sleeve\": \"att1\", \"symbols\": [\"BTCUSDT\"], \"days\": 360} — add a validated request to the operator-review inbox; no automatic runner is connected\n"
        "  add_user        {\"email\": \"x@y.com\"}         — pre-create user slot (no TOTP yet)\n"
        "  remove_user     {\"email\": \"x@y.com\"}         — revoke web access\n"
        "Trading mutations (enable/disable sleeve, safe mode, reload) are intentionally blocked: "
        "the current web overlay has no acknowledged live-consumer path. Describe them as proposals, not executed controls.\n"
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

_UNACKNOWLEDGED_TRADING_CONTROLS = {
    "enable_sleeve",
    "disable_sleeve",
    "set_safe_mode",
    "clear_safe_mode",
    "reload_config",
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


def _parse_backtest_days(params: dict) -> Optional[int]:
    raw = params.get("days", params.get("period"))
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)) and float(raw).is_integer():
        return int(raw)
    match = re.fullmatch(r"\s*(\d+)\s*[dD]?\s*", str(raw or ""))
    return int(match.group(1)) if match else None


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
    if not isinstance(params, dict):
        return (False, ["params must be a JSON object"], "unknown")
    params = dict(params)
    reasons: List[str] = []

    if action in _UNACKNOWLEDGED_TRADING_CONTROLS:
        reasons.append(
            "web trading control is proposal-only until the live bot consumes it and writes an effective-state acknowledgement"
        )
        return (False, reasons, _infer_command_market(action, params))

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
        elif len(symbols) > 20:
            reasons.append("too many symbols; maximum is 20")
        bad_format = [s for s in symbols if not re.fullmatch(r"[A-Z0-9/._:-]{2,24}", s)]
        if bad_format:
            reasons.append(f"invalid symbol format: {', '.join(bad_format[:5])}")
        days = _parse_backtest_days(params)
        if days is None:
            reasons.append("days/period must be an integer number of days")
        elif not 30 <= days <= 3650:
            reasons.append("days/period must be between 30 and 3650")
        return (not reasons, reasons, market)

    if action in {"set_sleeve_params", "set_global_params"}:
        reasons.append("direct parameter mutation is not enabled; create a proposal + backtest first")
        return (False, reasons, _infer_command_market(action, params))

    if action in {"add_user", "remove_user"}:
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

    if action == "add_user":
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
            "params": {
                "sleeve": str(params.get("sleeve") or params.get("strategy") or "").strip().lower(),
                "symbols": _params_symbols(params),
                "days": _parse_backtest_days(params),
            },
            "status": "operator_review_required",
            "note": "Validated proposal inbox only; no automatic research-runner consumer is connected.",
        }
        with open(queue_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
        _audit(email, action, params, "validated backtest request queued")
        return (
            "✓ Backtest request is valid and stored in the operator-review inbox. "
            "No automatic runner is connected, so it has not executed."
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
        "Always answer the operator in Russian unless the operator explicitly asks for another language. "
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
        "allocator.status=disabled does not block entries by itself: approved live env may remain active. Treat entries as globally blocked only when hard_block_new_entries=true or safe_mode=true; an individual sleeve is blocked when it is disabled or has risk_mult=0. "
        "Never present MIXED HISTORICAL TRADES or MIXED LIVE CLOSED EVENTS as the PF of the current package. Current-canary metrics require an explicit deployment/version boundary. "
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
        return _local_chat_fallback(
            command_result=cmd_result,
            reason=_http_error_summary(e),
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
        "unified_ai_context": compact_ai_full_context(_ROOT),
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


@router.get("/activity")
async def get_activity(limit: int = 50, email: str = Depends(require_admin)):
    """Operational feed reconstructed from trade events, pulse and web chat.

    Reads files the bot already writes:
    runtime/live_mirror/live_trade_events.jsonl and reports/PROOF_OF_LIFE_telegram.txt.
    Telegram charts, free-text messages and AI post-trade reviews are not mirrored.
    """
    from web.activity_feed import build_activity_feed, read_trade_events

    events_path = _RUNTIME_ROOT / "live_mirror" / "live_trade_events.jsonl"
    if not events_path.exists():
        events_path = _RUNTIME_ROOT / "live_trade_events.jsonl"
    events = read_trade_events(events_path, limit=30)

    pulse_path = _ROOT / "reports" / "PROOF_OF_LIFE_telegram.txt"
    pulse_text, pulse_ts = "", 0
    if pulse_path.exists():
        try:
            pulse_text = pulse_path.read_text(encoding="utf-8", errors="ignore")
            pulse_ts = int(pulse_path.stat().st_mtime)
        except Exception:
            pulse_text = ""

    feed = build_activity_feed(
        trade_events=events,
        chat_history=_load_shared_history(),
        pulse_text=pulse_text,
        pulse_ts=pulse_ts,
        limit=int(limit),
    )
    return {"feed": feed}


# ── Setup Card AI Analysis ────────────────────────────────────────────────────

class SetupAnalysisRequest(BaseModel):
    symbol:   str
    side:     str
    setup_type: str
    strategy: str
    score:    Optional[float] = None
    price:    Optional[float] = None
    level_price: Optional[float] = None
    distance_atr: Optional[float] = None
    invalidation: Optional[float] = None
    reasons:  List[str] = []
    regime:   Optional[str] = None
    interval: Optional[str] = None
    runtime_status: Optional[str] = None  # "live" / "watch" / "pause" etc.
    funding_rate_pct: Optional[float] = None  # e.g. +0.0120


class SetupAnalysisResponse(BaseModel):
    verdict:    str   # "strong" | "ok" | "weak" | "skip"
    reasoning:  str   # 2-4 sentence plain text
    risk_note:  str   # one sentence
    model:      str   # model used


@router.post("/analyze-setup", response_model=SetupAnalysisResponse)
async def analyze_setup(body: SetupAnalysisRequest, _: str = Depends(require_auth)):
    """
    Fast AI analysis of a single setup card.
    Uses claude-haiku for low latency. Returns verdict + reasoning in ~1-2s.
    """
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()

    # ── Read current regime for context ──────────────────────────────────────
    regime_label = body.regime or "unknown"
    try:
        _orch_path = _rt("regime", "orchestrator_state.json")
        if _orch_path.exists():
            _orch = json.loads(_orch_path.read_text())
            regime_label = _orch.get("regime", regime_label)
    except Exception:
        pass

    # ── Build concise prompt ──────────────────────────────────────────────────
    fr_str = (
        f"Funding rate: {body.funding_rate_pct:+.4f}% (8h)\n"
        if body.funding_rate_pct is not None else ""
    )
    inval_str = f"Invalidation: {body.invalidation}\n" if body.invalidation else ""
    level_str = f"Level: {body.level_price} ({body.distance_atr} ATR away)\n" if body.level_price else ""
    reasons_str = " · ".join(body.reasons) if body.reasons else "none"

    user_msg = f"""Проанализируй setup crypto perpetual и дай вердикт.
Ответ должен быть строго на русском языке.

Symbol: {body.symbol} | Side: {body.side.upper()} | Interval: {body.interval or "?"}
Setup type: {body.setup_type} | Strategy: {body.strategy}
Score: {body.score or "?"} | Regime: {regime_label}
Price: {body.price} | {level_str}{inval_str}{fr_str}Reasons: {reasons_str}
Runtime health: {body.runtime_status or "unknown"}

Respond with ONLY this JSON (no markdown):
{{"verdict":"strong|ok|weak|skip","reasoning":"2-4 коротких предложения на русском, почему setup стоит или не стоит внимания","risk_note":"одно короткое предложение на русском с главным риском"}}"""

    system_msg = (
        "You are a senior crypto quant analyst reviewing algorithmic trading setup cards. "
        "Always answer in Russian, including JSON field values. "
        "Be concise, data-driven, and honest about risks. "
        "Use STRONG only when geometry, regime, and fundamentals all align. "
        "Use SKIP when the setup conflicts with regime or has weak reasons."
    )

    try:
        model = "local-setup-fallback"
        prefer_anthropic = os.getenv("WEB_SETUP_AI_PROVIDER", "deepseek").strip().lower() == "anthropic"
        if deepseek_key and not prefer_anthropic:
            import ssl as _ssl
            import urllib.request as _urllib_req

            model = os.getenv("WEB_SETUP_AI_MODEL", os.getenv("WEB_AI_MODEL", "deepseek-chat"))
            payload = json.dumps({
                "model": model,
                "max_tokens": 400,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
            }).encode()
            req = _urllib_req.Request(
                "https://api.deepseek.com/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {deepseek_key}",
                },
            )
            with _urllib_req.urlopen(req, context=_ssl.create_default_context(), timeout=30) as resp:
                js = json.loads(resp.read().decode())
            raw = js["choices"][0]["message"]["content"].strip()
        elif anthropic_key:
            import anthropic as _ant
            client = _ant.Anthropic(api_key=anthropic_key)
            model = os.getenv("WEB_SETUP_AI_MODEL", "claude-haiku-4-5-20251001")
            resp = client.messages.create(
                model=model,
                max_tokens=400,
                system=system_msg,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = resp.content[0].text.strip()
        elif deepseek_key:
            import ssl as _ssl
            import urllib.request as _urllib_req

            model = os.getenv("WEB_SETUP_AI_MODEL", os.getenv("WEB_AI_MODEL", "deepseek-chat"))
            payload = json.dumps({
                "model": model,
                "max_tokens": 400,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
            }).encode()
            req = _urllib_req.Request(
                "https://api.deepseek.com/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {deepseek_key}",
                },
            )
            with _urllib_req.urlopen(req, context=_ssl.create_default_context(), timeout=30) as resp:
                js = json.loads(resp.read().decode())
            raw = js["choices"][0]["message"]["content"].strip()
        else:
            return _local_setup_analysis(body, reason="no AI API key configured")

        # Strip markdown code fences if model adds them anyway
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        parsed = json.loads(raw)
        verdict   = str(parsed.get("verdict", "ok")).lower()
        reasoning = str(parsed.get("reasoning", "")).strip()
        risk_note = str(parsed.get("risk_note", "")).strip()

        if verdict not in ("strong", "ok", "weak", "skip"):
            verdict = "ok"
        if not _has_cyrillic(reasoning + " " + risk_note):
            return _local_setup_analysis(body, reason="external AI returned non-Russian text")

        return SetupAnalysisResponse(
            verdict=verdict,
            reasoning=reasoning,
            risk_note=risk_note,
            model=model,
        )

    except json.JSONDecodeError as exc:
        # Model didn't return valid JSON — return raw as reasoning
        return SetupAnalysisResponse(
            verdict="ok",
            reasoning=raw[:300] if "raw" in dir() else "Parse error",
            risk_note=str(exc)[:100],
            model=model,
        )
    except Exception as exc:
        return _local_setup_analysis(body, reason=_http_error_summary(exc))
