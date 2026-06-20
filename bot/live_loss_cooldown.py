"""Small persistent cooldown helpers for live strategy loss clusters."""
from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path
from typing import MutableMapping


def record_loss_cooldown(
    state: MutableMapping[str, int],
    *,
    symbol: str,
    pnl: float,
    closed_ts: int,
    cooldown_sec: int,
) -> int:
    """Record a cooldown for a losing close and return its expiry."""
    symbol_u = str(symbol or "").strip().upper()
    if not symbol_u or float(pnl) >= 0 or int(cooldown_sec) <= 0:
        return int(state.get(symbol_u, 0) or 0)
    until = int(closed_ts) + int(cooldown_sec)
    state[symbol_u] = max(int(state.get(symbol_u, 0) or 0), until)
    return int(state[symbol_u])


def restore_loss_cooldowns(
    events_path: str | Path,
    *,
    strategy: str,
    cooldown_sec: int,
    now_ts: int | None = None,
    tail_lines: int = 5000,
) -> dict[str, int]:
    """Restore still-active cooldowns from the append-only live event journal."""
    path = Path(events_path).expanduser()
    if int(cooldown_sec) <= 0 or not path.exists():
        return {}
    now = int(now_ts if now_ts is not None else time.time())
    target = str(strategy or "").strip()
    out: dict[str, int] = {}
    try:
        with path.open(encoding="utf-8", errors="ignore") as handle:
            lines = deque(handle, maxlen=max(1, int(tail_lines)))
    except OSError:
        return {}
    for raw in lines:
        try:
            row = json.loads(raw)
        except Exception:
            continue
        if str(row.get("event") or "").strip().lower() != "close":
            continue
        if str(row.get("strategy") or "").strip() != target:
            continue
        try:
            pnl = float(row.get("pnl") or 0.0)
            closed_ts = int(float(row.get("ts") or 0))
        except Exception:
            continue
        until = closed_ts + int(cooldown_sec)
        if pnl < 0 and until > now:
            record_loss_cooldown(
                out,
                symbol=str(row.get("symbol") or ""),
                pnl=pnl,
                closed_ts=closed_ts,
                cooldown_sec=int(cooldown_sec),
            )
    return out
