"""Live position panel API — thin FastAPI wrapper over bot.position_view.

Owner gap (2026-07-08): «нет возможности в вебе следить за открытой позицией,
управлять ей и обсуждать её с ИИшкой». WATCH + DISCUSS ship in v1 (this route +
web/static/position.html + existing /api/ai/chat). MANAGE deliberately waits:
live-money buttons need ai_manual_v1-grade token discipline.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

from fastapi import APIRouter, Depends

from bot.position_view import build_position_view
from ..deps import require_auth

router = APIRouter(prefix="/api/position", tags=["position"])

_TRUTH_CACHE: Dict[str, Any] = {"monotonic": 0.0, "value": None}


def _float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _side(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "buy" if text in {"buy", "long"} else "sell" if text in {"sell", "short"} else text


def reconcile_position_truth(bot_positions: list[dict[str, Any]],
                             broker_rows: list[dict[str, Any]],
                             *, fetched_at_utc: str) -> Dict[str, Any]:
    """Compare bot ownership state with direct Bybit position truth."""
    broker_positions: list[dict[str, Any]] = []
    for row in broker_rows:
        size = abs(_float(row.get("size")) or 0.0)
        if size <= 0:
            continue
        stop_loss = _float(row.get("stopLoss"))
        take_profit = _float(row.get("takeProfit"))
        broker_positions.append({
            "symbol": str(row.get("symbol") or "").upper(),
            "side": _side(row.get("side")),
            "qty": size,
            "entry": _float(row.get("avgPrice")),
            "mark": _float(row.get("markPrice")),
            "sl": stop_loss if stop_loss and stop_loss > 0 else None,
            "tp": take_profit if take_profit and take_profit > 0 else None,
        })
    bot_normalized = [{
        "symbol": str(row.get("symbol") or "").upper(),
        "side": _side(row.get("side")),
        "qty": abs(_float(row.get("qty", row.get("size"))) or 0.0),
        "sl": _float(row.get("sl", row.get("exchange_sl", row.get("sl_price")))),
    } for row in bot_positions]
    broker_map = {(row["symbol"], row["side"]): row for row in broker_positions}
    bot_map = {(row["symbol"], row["side"]): row for row in bot_normalized if row["qty"] > 0}
    issues: list[str] = []
    if len(broker_map) != len(broker_positions) or len(bot_map) != len([r for r in bot_normalized if r["qty"] > 0]):
        issues.append("duplicate_symbol_side")
    for key in sorted(set(broker_map) | set(bot_map)):
        broker = broker_map.get(key)
        bot = bot_map.get(key)
        label = f"{key[0]} {key[1]}"
        if broker is None:
            issues.append(f"bot_only:{label}")
            continue
        if bot is None:
            issues.append(f"broker_only:{label}")
            continue
        tolerance = max(1e-9, broker["qty"] * 1e-6)
        if abs(broker["qty"] - bot["qty"]) > tolerance:
            issues.append(f"qty:{label}:broker={broker['qty']}:bot={bot['qty']}")
        if broker["sl"] is None:
            issues.append(f"broker_sl_missing:{label}")
        elif bot["sl"] is None:
            issues.append(f"bot_sl_unknown:{label}")
        elif abs(broker["sl"] - bot["sl"]) > max(1e-9, abs(broker["sl"]) * 1e-7):
            issues.append(f"sl:{label}:broker={broker['sl']}:bot={bot['sl']}")
    status = "CONFIRMED" if not issues else "CONFLICT"
    return {
        "status": status,
        "source": "direct_bybit_signed_get",
        "fetched_at_utc": fetched_at_utc,
        "broker_count": len(broker_positions),
        "bot_count": len(bot_map),
        "broker_positions": broker_positions,
        "issues": issues,
        "mismatch": "" if not issues else "; ".join(issues[:8]),
    }


async def _direct_truth(view: Dict[str, Any]) -> Dict[str, Any]:
    now = time.monotonic()
    cached = _TRUTH_CACHE.get("value")
    if isinstance(cached, dict) and now - float(_TRUTH_CACHE.get("monotonic") or 0.0) < 3.0:
        return cached
    from .extra_routes import _bybit_signed_get, _utc_now

    data = await asyncio.to_thread(
        _bybit_signed_get,
        "/v5/position/list",
        {"category": "linear", "settleCoin": "USDT"},
    )
    if not isinstance(data, dict) or data.get("_error"):
        result = {
            "status": "NOT_CONFIRMED",
            "source": "direct_bybit_signed_get",
            "fetched_at_utc": _utc_now(),
            "mismatch": f"broker truth unavailable: {str((data or {}).get('_error') or 'invalid response')[:120]}",
            "issues": ["broker_truth_unavailable"],
        }
    else:
        rows = (data.get("result") or {}).get("list") or []
        result = reconcile_position_truth(
            list(view.get("positions") or []),
            list(rows),
            fetched_at_utc=_utc_now(),
        )
    _TRUTH_CACHE.update({"monotonic": now, "value": result})
    return result


@router.get("/live")
async def live_position(_: str = Depends(require_auth)) -> Dict[str, Any]:
    view = build_position_view()
    view["truth"] = await _direct_truth(view)
    return view
