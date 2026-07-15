from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from bot.strategy_catalog import build_strategy_catalog, strategy_catalog_prompt_lines


AI_FULL_CONTEXT_MAX_AGE_SEC = 900


def load_json_dict(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compact_positions(payload: Any, *, max_positions: int) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"count": None, "positions": []}
    rows = payload.get("positions")
    if not isinstance(rows, list):
        rows = []
    compact: list[dict[str, Any]] = []
    for row in rows[: max(0, max_positions)]:
        if not isinstance(row, dict):
            continue
        compact.append(
            {
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "strategy": row.get("strategy"),
                "exchange": row.get("exchange"),
                "entry": row.get("entry"),
                "current": row.get("current"),
                "qty": row.get("qty"),
                "tp": row.get("tp"),
                "tp_model": row.get("tp_model"),
                "exchange_tp": row.get("exchange_tp"),
                "exchange_sl": row.get("exchange_sl"),
                "runner": row.get("runner"),
                "sl": row.get("sl"),
                "upnl_usd": row.get("upnl_usd"),
                "upnl_pct": row.get("upnl_pct"),
                "entry_ts": row.get("entry_ts"),
            }
        )
    return {
        "count": payload.get("count", len(compact)),
        "dry_run": payload.get("dry_run"),
        "trade_on": payload.get("trade_on"),
        "ts": payload.get("ts"),
        "positions": compact,
    }


def _compact_setup_cards(setup: dict[str, Any], *, max_cards: int) -> list[dict[str, Any]]:
    raw_cards = list(setup.get("cards_top") or [])
    cards: list[dict[str, Any]] = []
    for card in raw_cards[: max(0, max_cards)]:
        if not isinstance(card, dict):
            continue
        runtime = card.get("runtime") if isinstance(card.get("runtime"), dict) else {}
        cards.append(
            {
                "symbol": card.get("symbol"),
                "interval": card.get("interval"),
                "side": card.get("side"),
                "setup_type": card.get("setup_type"),
                "strategy": card.get("strategy"),
                "score": card.get("score"),
                "runtime_enabled": runtime.get("enabled"),
                "runtime_risk": runtime.get("risk_mult"),
                "reasons": list(card.get("reasons") or [])[:4],
            }
        )
    return cards


def _freshest_runtime_path(root: Path, *parts: str) -> Path:
    """Prefer the freshest direct or live-mirror copy of a runtime artifact."""
    candidates = [root / "runtime" / Path(*parts), root / "runtime" / "live_mirror" / Path(*parts)]
    existing = [path for path in candidates if path.exists()]
    if not existing:
        return candidates[0]
    return max(existing, key=lambda path: path.stat().st_mtime)


def _compact_capability_registry(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    components = [row for row in (payload.get("components") or []) if isinstance(row, dict)]
    stage_counts: dict[str, int] = {}
    for row in components:
        stage = str(row.get("stage") or "unknown")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
    return {
        "schema_version": payload.get("schema_version"),
        "as_of_utc": payload.get("as_of_utc"),
        "component_count": len(components),
        "stage_counts": dict(sorted(stage_counts.items())),
        "components": [
            {
                "component_id": row.get("component_id"),
                "market": row.get("market"),
                "physical_side": row.get("physical_side"),
                "stage": row.get("stage"),
                "execution_authority": row.get("execution_authority"),
                "promotion_authorized": row.get("promotion_authorized"),
                "known_gaps": list(row.get("known_gaps") or [])[:3],
                "next_gate": row.get("next_gate"),
            }
            for row in components
        ],
    }


def compact_ai_full_context(
    repo_root: Path,
    *,
    max_cards: int = 12,
    max_positions: int = 12,
) -> dict[str, Any]:
    """Return the shared compact AI context used by Telegram and web chat."""
    root = Path(repo_root)
    context_path = _freshest_runtime_path(root, "ai_context", "full_context.json")
    ctx = load_json_dict(context_path)
    static_capability_registry = _compact_capability_registry(
        load_json_dict(root / "configs" / "project_capability_registry_v1.json")
    )
    if not ctx:
        return {
            "critical_truth_assessment": {
                "control_recommendations_allowed": False,
                "blockers": ["ai_full_context_missing"],
                "live_money_sleeves_by_heartbeat": [],
            },
            "project_capability_registry": static_capability_registry,
        }
    context_age_sec = max(0, int(time.time() - context_path.stat().st_mtime))
    if context_age_sec > AI_FULL_CONTEXT_MAX_AGE_SEC:
        return {
            "generated_at_utc": ctx.get("generated_at_utc"),
            "context_path": str(context_path),
            "context_file_age_sec": context_age_sec,
            "critical_truth_assessment": {
                "control_recommendations_allowed": False,
                "blockers": [f"ai_full_context_stale:{context_age_sec}s"],
                "live_money_sleeves_by_heartbeat": [],
            },
            "heartbeat": {},
            "open_positions": {"count": None, "positions": []},
            "router": {},
            "allocator": {},
            "setup_cards_top": [],
            "strategy_catalog": build_strategy_catalog(),
            "project_capability_registry": static_capability_registry,
        }

    setup = ctx.get("setups_scanner") if isinstance(ctx.get("setups_scanner"), dict) else {}
    sources = ctx.get("sources_used") if isinstance(ctx.get("sources_used"), dict) else {}
    missing_sources = [str(k) for k, v in sources.items() if not v]
    grouped = ctx.get("grouped_no_signal") if isinstance(ctx.get("grouped_no_signal"), dict) else {}

    positions_payload = ctx.get("open_positions")
    if not isinstance(positions_payload, dict):
        positions_payload = load_json_dict(_freshest_runtime_path(root, "live_positions.json"))

    router = ctx.get("router_state") if isinstance(ctx.get("router_state"), dict) else {}
    allocator = ctx.get("allocator_state") if isinstance(ctx.get("allocator_state"), dict) else {}
    heartbeat = ctx.get("heartbeat") if isinstance(ctx.get("heartbeat"), dict) else {}
    weekly = ctx.get("weekly_live_vs_backtest") if isinstance(ctx.get("weekly_live_vs_backtest"), dict) else {}
    blocker = ctx.get("crypto_blocker_summary") if isinstance(ctx.get("crypto_blocker_summary"), dict) else {}
    att1_edge_health = ctx.get("att1_edge_health") if isinstance(ctx.get("att1_edge_health"), dict) else {}
    pnl_by_sleeve = ctx.get("pnl_by_sleeve_usd") if isinstance(ctx.get("pnl_by_sleeve_usd"), dict) else {}
    alpaca_state = ctx.get("alpaca_account_state") if isinstance(ctx.get("alpaca_account_state"), dict) else {}
    git_rev = ctx.get("git_revision") if isinstance(ctx.get("git_revision"), dict) else {}
    errors_tail = ctx.get("errors_tail") if isinstance(ctx.get("errors_tail"), dict) else {}
    truth = ctx.get("critical_truth_assessment") if isinstance(ctx.get("critical_truth_assessment"), dict) else {}
    freshness = ctx.get("source_freshness") if isinstance(ctx.get("source_freshness"), dict) else {}
    canonical = ctx.get("canonical_project_state") if isinstance(ctx.get("canonical_project_state"), dict) else {}

    return {
        "generated_at_utc": ctx.get("generated_at_utc"),
        "context_path": str(context_path),
        "context_file_age_sec": context_age_sec,
        "git_revision": git_rev,
        "ai_context_brief": ctx.get("ai_context_brief"),
        "missing_sources": missing_sources[:8],
        "heartbeat": {
            "open_trades": heartbeat.get("open_trades"),
            "trade_on": heartbeat.get("trade_on"),
            "dry_run": heartbeat.get("dry_run"),
            "regime": heartbeat.get("regime"),
            "ws_guard_active": heartbeat.get("ws_guard_active"),
            "strategy_runtime_config": heartbeat.get("strategy_runtime_config"),
        },
        "critical_truth_assessment": truth,
        "source_freshness": freshness,
        "canonical_project_state": canonical,
        "project_capability_registry": (
            ctx.get("project_capability_registry")
            if isinstance(ctx.get("project_capability_registry"), dict)
            else static_capability_registry
        ),
        "open_positions": _compact_positions(positions_payload, max_positions=max_positions),
        "router": {
            "status": router.get("status"),
            "regime": router.get("regime"),
            "scan_ok": router.get("scan_ok"),
            "timestamp_utc": router.get("timestamp_utc"),
        },
        "allocator": {
            "status": allocator.get("status"),
            "safe_mode": allocator.get("safe_mode"),
            "hard_block_new_entries": allocator.get("hard_block_new_entries"),
            "global_risk_mult": allocator.get("allocator_global_risk_mult", allocator.get("global_risk_mult")),
            "degraded_kind": allocator.get("degraded_kind"),
        },
        "setup_card_count": setup.get("card_count"),
        "setup_cards_top": _compact_setup_cards(setup, max_cards=max_cards),
        "grouped_no_signal": grouped,
        "crypto_blocker_summary": {
            "generated_at_utc": blocker.get("generated_at_utc"),
            "cards_analyzed": blocker.get("cards_analyzed"),
            "classification_counts": blocker.get("classification_counts") or {},
            "strategy_counts": blocker.get("strategy_counts") or {},
        } if blocker else {},
        "att1_edge_health": att1_edge_health,
        "pnl_by_sleeve_usd": {
            "lookback_days": pnl_by_sleeve.get("lookback_days"),
            "rows": list(pnl_by_sleeve.get("rows") or [])[:12],
        },
        "alpaca_account_state": alpaca_state,
        "errors_tail": {
            "path": errors_tail.get("path"),
            "lines": list(errors_tail.get("lines") or [])[-20:],
        },
        "weekly_live_vs_backtest": weekly,
        "strategy_catalog": build_strategy_catalog(),
    }


def append_ai_context_lines(parts: list[str], repo_root: Path) -> None:
    """Append the shared compact context as human-readable prompt lines."""
    compact = compact_ai_full_context(repo_root)
    if not compact:
        return

    positions = compact.get("open_positions") if isinstance(compact.get("open_positions"), dict) else {}
    pos_rows = list(positions.get("positions") or [])
    heartbeat = compact.get("heartbeat") if isinstance(compact.get("heartbeat"), dict) else {}
    allocator = compact.get("allocator") if isinstance(compact.get("allocator"), dict) else {}
    router = compact.get("router") if isinstance(compact.get("router"), dict) else {}
    pos_ts = positions.get("ts")
    pos_age = int(time.time()) - int(pos_ts) if isinstance(pos_ts, (int, float)) and pos_ts > 0 else None

    parts.append(
        "UNIFIED AI CONTEXT: "
        f"generated={compact.get('generated_at_utc')} "
        f"context_age_sec={compact.get('context_file_age_sec')} "
        f"git={((compact.get('git_revision') or {}).get('head') if isinstance(compact.get('git_revision'), dict) else '') or '?'} "
        f"open_positions={positions.get('count')} "
        f"positions_age_sec={pos_age if pos_age is not None else '?'} "
        f"heartbeat_open_trades={heartbeat.get('open_trades')} "
        f"trade_on={heartbeat.get('trade_on')} dry_run={heartbeat.get('dry_run')} "
        f"regime={heartbeat.get('regime')} "
        f"router={router.get('status')} allocator={allocator.get('status')} "
        f"allocator_hard_block={allocator.get('hard_block_new_entries')} "
        f"safe_mode={allocator.get('safe_mode')}\n"
    )

    truth = compact.get("critical_truth_assessment") if isinstance(compact.get("critical_truth_assessment"), dict) else {}
    parts.append(
        "AI CONTROL TRUTH: "
        f"recommendations_allowed={truth.get('control_recommendations_allowed')} "
        f"blockers={truth.get('blockers') or []} "
        f"live_money_sleeves={truth.get('live_money_sleeves_by_heartbeat') or []}\n"
    )

    capability = compact.get("project_capability_registry")
    if isinstance(capability, dict) and capability:
        live_ids = [
            str(row.get("component_id"))
            for row in (capability.get("components") or [])
            if isinstance(row, dict) and str(row.get("stage") or "").startswith("live_")
        ]
        parts.append(
            "PROJECT CAPABILITY REGISTRY: "
            f"as_of={capability.get('as_of_utc')} components={capability.get('component_count')} "
            f"live={','.join(live_ids) or '-'} stages={capability.get('stage_counts')}\n"
        )

    brief = str(compact.get("ai_context_brief") or "").strip()
    if brief:
        parts.append(f"AI_CONTEXT_BRIEF:\n{brief}\n")

    # Strategy config + TP/SL model so the AI can answer questions like
    # "why is there a stop on the exchange but no take-profit?".
    parts.extend(strategy_catalog_prompt_lines())

    for row in pos_rows[:8]:
        if not isinstance(row, dict):
            continue
        entry = _as_float(row.get("entry"))
        current = _as_float(row.get("current"))
        sl = _as_float(row.get("sl"))
        tp = _as_float(row.get("tp"))
        runner = row.get("runner") if isinstance(row.get("runner"), dict) else {}
        runner_targets = list(runner.get("targets") or []) if runner else []
        runner_text = ""
        if row.get("tp_model") == "runner_ladder":
            target_bits = []
            for target in runner_targets[:4]:
                if not isinstance(target, dict):
                    continue
                frac = target.get("frac")
                frac_txt = f" frac={frac}" if frac is not None else ""
                target_bits.append(
                    f"TP{target.get('index')}={target.get('price')}{frac_txt} {target.get('status')}"
                )
            trail = runner.get("trailing") if isinstance(runner.get("trailing"), dict) else {}
            be = runner.get("breakeven") if isinstance(runner.get("breakeven"), dict) else {}
            runner_text = (
                " exchange_tp=None runner_targets=["
                + "; ".join(target_bits)
                + "]"
                + f" trailing_enabled={trail.get('enabled')}"
                + f" be_enabled={be.get('enabled')}"
                + f" time_stop_sec={runner.get('time_stop_sec')}"
            )
        upnl = _as_float(row.get("upnl_usd"))
        upnl_pct = _as_float(row.get("upnl_pct"))
        parts.append(
            "OPEN POSITION: "
            f"{row.get('symbol')} {row.get('side')} strategy={row.get('strategy') or '-'} "
            f"qty={row.get('qty')} entry={entry if entry is not None else row.get('entry')} "
            f"current={current if current is not None else row.get('current')} "
            f"tp_model={row.get('tp_model') or '-'} "
            f"exchange_tp={row.get('exchange_tp')} "
            f"tp={tp if tp is not None else row.get('tp')} "
            f"sl={sl if sl is not None else row.get('sl')} "
            f"upnl_usd={upnl if upnl is not None else row.get('upnl_usd')} "
            f"upnl_pct={upnl_pct if upnl_pct is not None else row.get('upnl_pct')}"
            f"{runner_text}\n"
        )
