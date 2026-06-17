"""Operational activity feed for the web chat.

The feed reconstructs trade lifecycle events and the pulse digest from files
the bot already writes. It is not a byte-for-byte Telegram mirror: charts,
free-text Telegram chat and AI post-trade reviews are not present yet.

This module builds a human-Russian, time-sorted feed from:
  - trade alerts  -> runtime/live_mirror/live_trade_events.jsonl  (channel "tg")
  - pulse digest  -> reports/PROOF_OF_LIFE_telegram.txt           (channel "tg")
  - chat turns    -> the shared web AI history json                (channel "web")

The only piece that still needs the monolith is mirroring free-text TG
conversation into the shared history (a small append in `_tg_reply` / `_tg_send_raw`).
That is documented for Codex; everything here is additive and testable.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


# Human Russian names per strategy code (matches scripts/proof_of_life.py).
STRATEGY_RU = {
    "flat_resistance_fade": "шорт от сопротивления",
    "alt_range_scalp_v1": "пила во флэте",
    "range": "пила во флэте",
    "att1_trendline_touch": "отбой от наклонной",
    "alt_inplay_breakdown_v1": "слом поддержки",
    "alt_inplay_breakdown_v2": "слом поддержки",
    "breakdown_retest_v3": "слом поддержки (v3)",
    "impulse_volume_breakout_v1": "старый импульсный пробой",
    "inplay_retest_v3": "ретест уровня (v3)",
    "bounce1": "отбой от поддержки",
    "btc_eth_midterm": "среднесрок BTC/ETH",
    "elder": "тройной экран Элдера",
}

SIDE_RU = {"buy": "лонг", "long": "лонг", "sell": "шорт", "short": "шорт"}

EVENT_RU = {
    "order_submitted": "Заявка на вход",
    "entry_filled": "Вход исполнен",
    "open": "Открытие",
    "close": "Закрытие",
    "exit": "Выход",
}


def _f(v: Any) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def _strategy_ru(evt: Dict[str, Any]) -> str:
    code = str(evt.get("strategy") or "").strip()
    if code in STRATEGY_RU:
        return STRATEGY_RU[code]
    reason = str(evt.get("signal_reason") or "").strip()
    for key, label in STRATEGY_RU.items():
        if key in reason:
            return label
    return code or reason or "стратегия"


def _side_ru(evt: Dict[str, Any]) -> str:
    return SIDE_RU.get(str(evt.get("side") or "").strip().lower(), str(evt.get("side") or ""))


def render_trade_event_ru(evt: Dict[str, Any]) -> str:
    """One human-Russian line for a trade event (no emoji, plain text)."""
    ev = str(evt.get("event") or evt.get("type") or "").strip().lower()
    head = EVENT_RU.get(ev, ev or "событие")
    side = _side_ru(evt)
    sym = str(evt.get("symbol") or "")
    strat = _strategy_ru(evt)
    parts = [f"{head}: {side} {sym} ({strat})"]
    if ev == "order_submitted":
        px = _f(evt.get("request_price")) or _f(evt.get("entry_price"))
        sl = _f(evt.get("request_sl")) or _f(evt.get("sl_price"))
        if px is not None:
            parts.append(f"цена {px:g}")
        if sl is not None:
            parts.append(f"стоп {sl:g}")
    elif ev in ("entry_filled", "open"):
        px = _f(evt.get("fill_price")) or _f(evt.get("entry_price"))
        sl = _f(evt.get("sl_price"))
        if px is not None:
            parts.append(f"@ {px:g}")
        if sl is not None:
            parts.append(f"стоп {sl:g}")
    elif ev in ("close", "exit"):
        px = _f(evt.get("exit_price"))
        pnl = _f(evt.get("pnl"))
        if px is not None:
            parts.append(f"@ {px:g}")
        if pnl is not None:
            parts.append(f"P&L {pnl:+.2f}")
    return ", ".join(parts)


def _ts_of_event(evt: Dict[str, Any]) -> int:
    return int(_f(evt.get("ts")) or 0)


def build_activity_feed(
    *,
    trade_events: Sequence[Dict[str, Any]] = (),
    chat_history: Sequence[Dict[str, Any]] = (),
    pulse_text: str = "",
    pulse_ts: int = 0,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Merge reconstructed trade events, pulse and chat turns into one sorted feed.

    Each item: {ts, channel, kind, text, role?}. Sorted ascending by ts; the last
    `limit` items are returned (newest at the end, ready to render like a chat).
    """
    items: List[Dict[str, Any]] = []
    for evt in trade_events:
        items.append({
            "ts": _ts_of_event(evt),
            "channel": "tg",
            "kind": "trade",
            "text": render_trade_event_ru(evt),
        })
    if pulse_text.strip():
        items.append({
            "ts": int(pulse_ts or 0),
            "channel": "tg",
            "kind": "pulse",
            "text": pulse_text.strip(),
        })
    for m in chat_history:
        role = str(m.get("role") or "").strip().lower()
        content = str(m.get("content") or "").strip()
        if not content or role not in ("user", "assistant", "system"):
            continue
        items.append({
            "ts": int(_f(m.get("ts")) or 0),
            "channel": str(m.get("channel") or "web"),
            "kind": "chat",
            "role": role,
            "text": content,
        })
    items.sort(key=lambda x: x.get("ts") or 0)
    return items[-max(1, int(limit)):]


# ---------- file readers (used by the web endpoint) ----------
def read_trade_events(path: Path, limit: int = 30) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        for raw in path.read_text(errors="ignore").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(json.loads(raw))
            except Exception:
                continue
    except Exception:
        return []
    # show meaningful lifecycle events only
    keep = {"order_submitted", "entry_filled", "open", "close", "exit"}
    out = [e for e in out if str(e.get("event") or "").strip().lower() in keep]
    return out[-max(1, int(limit)):]
