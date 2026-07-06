"""Position view — pure aggregation for web panel, AI chat and tests.

Extracted from web.routes.position_routes so the logic is importable without
FastAPI (sandbox tests, digest reuse, AI-brief reuse). Same fault-tolerance
contract as daily_digest: broken/missing runtime files never raise.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = ["build_position_view"]

_ROOT = Path(__file__).resolve().parents[1]


def _runtime_root() -> Path:
    return Path(os.getenv("WEB_RUNTIME_ROOT", str(_ROOT / "runtime")))


def _load_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _positions(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [p for p in raw if isinstance(p, dict)]
    if isinstance(raw, dict):
        data = raw.get("data")
        if isinstance(data, dict) and isinstance(data.get("positions"), list):
            return [p for p in data["positions"] if isinstance(p, dict)]
        if isinstance(raw.get("positions"), list):
            return [p for p in raw["positions"] if isinstance(p, dict)]
    return []


def _bus_tail_for(symbols: List[str], since_ts: float, limit: int = 40) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    path = _runtime_root() / "decision_bus.jsonl"
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
                if float(rec.get("ts", 0) or 0) < since_ts:
                    continue
                if symbols and str(rec.get("symbol", "")).upper() not in symbols:
                    continue
                out.append(rec)
    except Exception:
        pass
    return out[-limit:]


def build_position_view(now_ts: Optional[float] = None) -> Dict[str, Any]:
    """Aggregate everything the owner/AI needs about the open trade(s)."""
    rt = _runtime_root()
    now = float(now_ts if now_ts is not None else time.time())
    heartbeat = _load_json(rt / "bot_heartbeat.json")
    positions = _positions(_load_json(rt / "live_positions.json"))
    health = _load_json(rt / "att1_edge_health.json")
    symbols = [str(p.get("symbol", "")).upper() for p in positions if p.get("symbol")]
    events = _bus_tail_for(symbols, now - 3 * 86_400) if symbols else []

    enriched: List[Dict[str, Any]] = []
    for p in positions:
        q = dict(p)
        sl = p.get("sl", p.get("exchange_sl", p.get("sl_price")))
        entry = p.get("entry", p.get("entry_price", p.get("avg")))
        qty = p.get("qty", p.get("size"))
        side = str(p.get("side", "")).lower()
        is_short = side in ("sell", "short")
        try:
            risk_usd = abs(float(entry) - float(sl)) * float(qty)
        except (TypeError, ValueError):
            risk_usd = None
        q["sl_present"] = sl not in (None, "", 0)
        q["risk_usd_at_sl"] = round(risk_usd, 4) if isinstance(risk_usd, float) else None

        # ── holding math: targets, current price, progress, expected profit ──
        targets: List[float] = []
        for key in ("tp_targets", "targets", "runner_targets"):
            v = p.get(key)
            if isinstance(v, (list, tuple)):
                targets += [float(x) for x in v if isinstance(x, (int, float)) and x > 0]
        for key in ("tp1", "tp2", "tp_price", "tp"):
            v = p.get(key)
            if isinstance(v, (int, float)) and v > 0:
                targets.append(float(v))
        targets = sorted(set(targets), reverse=is_short is False)
        if is_short:
            targets = sorted(set(targets), reverse=True)  # ближняя цель первой (выше)
            targets = [t for t in targets if True]
        q["tp_targets"] = targets

        upnl = p.get("upnl", p.get("upnl_usd", p.get("unrealised_pnl")))
        current = None
        for key in ("mark_price", "last_price", "current_price", "current", "price"):
            v = p.get(key)
            if isinstance(v, (int, float)) and v > 0:
                current = float(v)
                break
        try:
            if current is None and isinstance(upnl, (int, float)):
                # derive from uPnL: short profit when price below entry
                current = float(entry) - float(upnl) / float(qty) if is_short \
                          else float(entry) + float(upnl) / float(qty)
        except (TypeError, ValueError, ZeroDivisionError):
            current = None
        q["current_price"] = round(current, 8) if isinstance(current, float) else None

        try:
            q["r_now"] = round(float(upnl) / risk_usd, 3) if risk_usd else None
        except (TypeError, ValueError):
            q["r_now"] = None

        # progress toward the NEAREST remaining target, % (can exceed 100)
        prog = None
        if targets and isinstance(current, float):
            try:
                t0 = float(targets[0])
                denom = (float(entry) - t0) if is_short else (t0 - float(entry))
                moved = (float(entry) - current) if is_short else (current - float(entry))
                if abs(denom) > 1e-12:
                    prog = max(-50.0, min(150.0, 100.0 * moved / denom))
            except (TypeError, ValueError):
                prog = None
        q["progress_to_tp1_pct"] = round(prog, 1) if isinstance(prog, float) else None

        # expected profit if each target hits (full remaining qty approximation)
        exp = []
        for t in targets:
            try:
                gain = (float(entry) - float(t)) if is_short else (float(t) - float(entry))
                exp.append({"target": float(t), "approx_usd": round(gain * float(qty), 2)})
            except (TypeError, ValueError):
                continue
        q["expected_at_targets"] = exp
        enriched.append(q)

    return {
        "ts": int(now),
        "alive": bool(heartbeat) and bool(heartbeat.get("trade_on"))
                 and not bool(heartbeat.get("dry_run")) if isinstance(heartbeat, dict) else False,
        "regime": (heartbeat or {}).get("regime") if isinstance(heartbeat, dict) else None,
        "positions": enriched,
        "health": health if isinstance(health, dict) else None,
        "recent_events": events,
        "manage": {
            "enabled": False,
            "note": "Управление позицией из веба отключено by design (v1 = наблюдение+обсуждение). "
                    "Ручные действия — через биржу или ai_manual_v1 токен.",
        },
    }
