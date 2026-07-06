"""Daily owner digest — one Telegram message that answers «что происходит?».

The owner's recurring pain: state lives in heartbeats, logs, ledgers and chats.
This module composes ONE morning message from artifacts that ALREADY exist:

  runtime/bot_heartbeat.json        - alive, regime, risk, open trades
  runtime/live_positions.json       - current positions with SL/uPnL
  runtime/decision_bus.jsonl        - enters/outcomes of the last 24h (telemetry)
  runtime/att1_edge_health.json     - sleeve health vs baseline
  runtime/daily_digest_extra.json   - optional: research verdicts + owner TODOs
                                      {"research": [{"name","verdict","note"}],
                                       "pending_owner": ["..."]}

Pure composition (unit-tested offline, no network). Codex wires it to cron:
    python3 -m bot.daily_digest [--root .] --print   -> stdout for tg_send.
Missing/broken files NEVER crash the digest — the message just says so;
a digest that dies silently would recreate the exact problem it solves.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

__all__ = ["build_digest", "compose_from_runtime"]

DAY_S = 86_400


def _load_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_bus_tail(path: Path, since_ts: float) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if float(rec.get("ts", 0) or 0) >= since_ts:
                    out.append(rec)
    except Exception:
        pass
    return out


def _fmt_pos(p: Dict[str, Any]) -> str:
    sym = str(p.get("symbol", "?"))
    side = str(p.get("side", "?"))
    upnl = p.get("upnl", p.get("upnl_usd", p.get("unrealised_pnl")))
    sl = p.get("sl", p.get("exchange_sl", p.get("sl_price", p.get("stop_loss"))))
    upnl_s = f"{float(upnl):+.2f}$" if isinstance(upnl, (int, float)) else "?"
    sl_s = f"SL {sl}" if sl not in (None, "", 0) else "SL: НЕТ (!)"
    return f"{sym} {side} | uPnL {upnl_s} | {sl_s}"


def _extract_positions(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [p for p in raw if isinstance(p, dict)]
    if not isinstance(raw, dict):
        return []
    data = raw.get("data")
    if isinstance(data, dict) and isinstance(data.get("positions"), list):
        return [p for p in data["positions"] if isinstance(p, dict)]
    if isinstance(raw.get("positions"), list):
        return [p for p in raw["positions"] if isinstance(p, dict)]
    return []


def build_digest(
    *,
    heartbeat: Optional[Dict[str, Any]],
    positions: Optional[Sequence[Dict[str, Any]]],
    bus_records: Sequence[Dict[str, Any]],
    health: Optional[Dict[str, Any]],
    alpaca: Optional[Sequence[Dict[str, Any]]] = None,
    research: Optional[Sequence[Dict[str, Any]]] = None,
    pending_owner: Optional[Sequence[str]] = None,
    now_ts: Optional[float] = None,
) -> str:
    now = float(now_ts if now_ts is not None else time.time())
    day = datetime.fromtimestamp(now, timezone.utc).strftime("%d.%m.%Y")
    lines: List[str] = [f"📊 СВОДКА ДНЯ — {day} (UTC)"]

    # ── live status ──
    if heartbeat:
        alive = not bool(heartbeat.get("dry_run", False)) and bool(heartbeat.get("trade_on", False))
        regime = str(heartbeat.get("regime", "?"))
        lines.append(f"Бот: {'✅ ЖИВ, торгует' if alive else '⚠️ НЕ торгует'} | режим: {regime}")
    else:
        lines.append("Бот: ⚠️ heartbeat недоступен — проверить сервер!")

    # ── positions ──
    pos = [p for p in (positions or []) if p]
    if pos:
        lines.append(f"Открытые позиции ({len(pos)}):")
        lines += [f"  • {_fmt_pos(p)}" for p in pos[:5]]
    else:
        lines.append("Открытых позиций нет.")

    # ── last-24h trades from telemetry ──
    outcomes = [r for r in bus_records if str(r.get("decision")) == "outcome"]
    enters = [r for r in bus_records if str(r.get("decision")) == "enter"]
    if outcomes:
        pnl = sum(float((r.get("outcome") or {}).get("pnl", 0) or 0) for r in outcomes)
        rs = [float((r.get("outcome") or {}).get("r_multiple", float("nan"))) for r in outcomes]
        rs = [x for x in rs if x == x]
        wins = sum(1 for x in rs if x > 0)
        r_s = f", {sum(rs):+.2f}R" if rs else ""
        lines.append(f"Сделки за 24ч: закрыто {len(outcomes)} (побед {wins}) | P&L {pnl:+.2f}${r_s}"
                     f" | новых входов {len(enters)}")
    else:
        lines.append(f"Сделки за 24ч: закрытых нет | новых входов {len(enters)}")

    # ── alpaca stocks ──
    if alpaca:
        held = [p for p in alpaca if p]
        no_stop = sum(1 for p in held if p.get("stop") in (None, "", 0))
        upnl_sum = sum(float(p.get("upnl") or 0) for p in held
                       if isinstance(p.get("upnl"), (int, float)))
        warn = f" | БЕЗ СТОПА: {no_stop} (!)" if no_stop else ""
        names = ", ".join(str(p.get("symbol")) for p in held[:6])
        lines.append(f"Alpaca: {len(held)} позиций ({names}) | uPnL {upnl_sum:+.2f}${warn}")

    # ── sleeve health ──
    if health:
        st = str(health.get("status", "?"))
        icon = {"healthy": "🟢", "watch": "🟡", "degraded": "🟠", "halt": "🔴"}.get(st, "⚪")
        lines.append(f"Здоровье ATT1: {icon} {st} (n={health.get('n', '?')},"
                     f" exp={health.get('live_expectancy_R', '—')})")

    # ── research verdicts ──
    if research:
        lines.append("Research за ночь:")
        for r in list(research)[:6]:
            v = str(r.get("verdict", "?")).upper()
            icon = "✅" if v in ("PASS", "GO") else ("❌" if v in ("FAIL", "NO-GO") else "⏳")
            note = f" — {r.get('note')}" if r.get("note") else ""
            lines.append(f"  {icon} {r.get('name', '?')}: {v}{note}")

    # ── owner actions ──
    todos = [t for t in (pending_owner or []) if str(t).strip()]
    if todos:
        lines.append("⚡ Ждёт твоего решения:")
        lines += [f"  → {t}" for t in todos[:5]]
    else:
        lines.append("Решений от тебя сегодня не требуется.")

    return "\n".join(lines)[:3900]  # TG hard limit safety


def compose_from_runtime(root: Path | str = ".", *, now_ts: Optional[float] = None) -> str:
    """Gather the standard runtime artifacts and build the digest (fault-tolerant)."""
    root = Path(root)
    now = float(now_ts if now_ts is not None else time.time())
    heartbeat = _load_json(root / "runtime" / "bot_heartbeat.json")
    positions_raw = _load_json(root / "runtime" / "live_positions.json")
    positions = _extract_positions(positions_raw)
    bus = _load_bus_tail(root / "runtime" / "decision_bus.jsonl", now - DAY_S)
    health = _load_json(root / "runtime" / "att1_edge_health.json")
    extra = _load_json(root / "runtime" / "daily_digest_extra.json") or {}
    try:
        from bot.position_view import _alpaca_positions
        alpaca = _alpaca_positions(root / "runtime")
    except Exception:
        alpaca = []
    return build_digest(
        heartbeat=heartbeat if isinstance(heartbeat, dict) else None,
        positions=positions,
        bus_records=bus,
        health=health if isinstance(health, dict) else None,
        alpaca=alpaca,
        research=extra.get("research"),
        pending_owner=extra.get("pending_owner"),
        now_ts=now,
    )


if __name__ == "__main__":  # pragma: no cover - thin CLI for cron/tg_send
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--print", action="store_true")
    args = ap.parse_args()
    print(compose_from_runtime(args.root))
