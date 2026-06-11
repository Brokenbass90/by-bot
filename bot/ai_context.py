from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


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


def compact_ai_full_context(
    repo_root: Path,
    *,
    max_cards: int = 12,
    max_positions: int = 12,
) -> dict[str, Any]:
    """Return the shared compact AI context used by Telegram and web chat."""
    root = Path(repo_root)
    ctx = load_json_dict(root / "runtime" / "ai_context" / "full_context.json")
    if not ctx:
        return {}

    setup = ctx.get("setups_scanner") if isinstance(ctx.get("setups_scanner"), dict) else {}
    sources = ctx.get("sources_used") if isinstance(ctx.get("sources_used"), dict) else {}
    missing_sources = [str(k) for k, v in sources.items() if not v]
    grouped = ctx.get("grouped_no_signal") if isinstance(ctx.get("grouped_no_signal"), dict) else {}

    positions_payload = ctx.get("open_positions")
    if not isinstance(positions_payload, dict):
        positions_payload = load_json_dict(root / "runtime" / "live_positions.json")

    router = ctx.get("router_state") if isinstance(ctx.get("router_state"), dict) else {}
    allocator = ctx.get("allocator_state") if isinstance(ctx.get("allocator_state"), dict) else {}
    heartbeat = ctx.get("heartbeat") if isinstance(ctx.get("heartbeat"), dict) else {}
    weekly = ctx.get("weekly_live_vs_backtest") if isinstance(ctx.get("weekly_live_vs_backtest"), dict) else {}
    blocker = ctx.get("crypto_blocker_summary") if isinstance(ctx.get("crypto_blocker_summary"), dict) else {}

    return {
        "generated_at_utc": ctx.get("generated_at_utc"),
        "missing_sources": missing_sources[:8],
        "heartbeat": {
            "open_trades": heartbeat.get("open_trades"),
            "trade_on": heartbeat.get("trade_on"),
            "dry_run": heartbeat.get("dry_run"),
            "regime": heartbeat.get("regime"),
            "ws_guard_active": heartbeat.get("ws_guard_active"),
        },
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
        "weekly_live_vs_backtest": weekly,
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
        f"open_positions={positions.get('count')} "
        f"positions_age_sec={pos_age if pos_age is not None else '?'} "
        f"heartbeat_open_trades={heartbeat.get('open_trades')} "
        f"trade_on={heartbeat.get('trade_on')} dry_run={heartbeat.get('dry_run')} "
        f"regime={heartbeat.get('regime')} "
        f"router={router.get('status')} allocator={allocator.get('status')} "
        f"allocator_hard_block={allocator.get('hard_block_new_entries')} "
        f"safe_mode={allocator.get('safe_mode')}\n"
    )

    for row in pos_rows[:8]:
        if not isinstance(row, dict):
            continue
        entry = _as_float(row.get("entry"))
        current = _as_float(row.get("current"))
        sl = _as_float(row.get("sl"))
        tp = _as_float(row.get("tp"))
        upnl = _as_float(row.get("upnl_usd"))
        upnl_pct = _as_float(row.get("upnl_pct"))
        parts.append(
            "OPEN POSITION: "
            f"{row.get('symbol')} {row.get('side')} strategy={row.get('strategy') or '-'} "
            f"qty={row.get('qty')} entry={entry if entry is not None else row.get('entry')} "
            f"current={current if current is not None else row.get('current')} "
            f"tp={tp if tp is not None else row.get('tp')} "
            f"sl={sl if sl is not None else row.get('sl')} "
            f"upnl_usd={upnl if upnl is not None else row.get('upnl_usd')} "
            f"upnl_pct={upnl_pct if upnl_pct is not None else row.get('upnl_pct')}\n"
        )
