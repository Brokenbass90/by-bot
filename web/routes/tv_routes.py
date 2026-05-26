"""
web/routes/tv_routes.py — TradingView Pine Script Webhook Receiver

Accepts POST /api/tv-signal from TradingView alerts.
Validates, filters through health gate + regime, logs, and optionally
notifies Telegram or queues for bot execution.

Setup in TradingView:
  Alert → Webhook URL: http://YOUR_SERVER:8000/api/tv-signal
  Message (JSON):
  {
    "secret": "{{strategy.order.comment}}",   ← or hardcode your TV_WEBHOOK_SECRET
    "symbol": "{{ticker}}",
    "side": "{{strategy.order.action}}",       ← "buy" or "sell"
    "price": {{close}},
    "strategy": "supertrend_4h",
    "timeframe": "{{interval}}",
    "reason": "SuperTrend flip"
  }

Modes (TV_WEBHOOK_MODE env var):
  log     — store to runtime/tv_signals.jsonl, no action
  notify  — log + Telegram alert with signal details
  auto    — log + notify + write runtime/tv_pending_signal.json for bot pickup

Security:
  TV_WEBHOOK_SECRET env var — must match "secret" field in payload.
  Set a long random string. TradingView alert message = that secret.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from ..deps import require_auth

router = APIRouter(prefix="/api", tags=["tradingview"])

_ROOT    = Path(__file__).resolve().parent.parent.parent
_RUNTIME = _ROOT / "runtime"

TV_SECRET  = os.getenv("TV_WEBHOOK_SECRET", "")
TV_MODE    = os.getenv("TV_WEBHOOK_MODE", "log").lower()   # log | notify | auto
TG_TOKEN   = os.getenv("TG_TOKEN", "")
TG_CHAT    = os.getenv("TG_CHAT", "") or os.getenv("TG_CHAT_ID", "")

_SIGNALS_LOG = _RUNTIME / "tv_signals.jsonl"
_PENDING     = _RUNTIME / "tv_pending_signal.json"
_HEALTH_FILE = _ROOT / "configs" / "strategy_health.json"
_REGIME_FILE = _RUNTIME / "regime" / "orchestrator_state.json"

# ── Regime ↔ side compatibility ───────────────────────────────────────────────
REGIME_SIDE_COMPAT = {
    "bull_trend":  {"long": True,  "short": False},
    "bull_chop":   {"long": True,  "short": False},
    "bear_trend":  {"long": False, "short": True},
    "bear_chop":   {"long": False, "short": True},
    "neutral":     {"long": True,  "short": True},
}


# ── Pydantic model ────────────────────────────────────────────────────────────
class TVSignal(BaseModel):
    secret:    str
    symbol:    str
    side:      str          # "buy"/"long" or "sell"/"short"
    price:     Optional[float] = None
    strategy:  Optional[str]  = "tv_signal"
    timeframe: Optional[str]  = None
    sl_pct:    Optional[float] = None   # stop-loss %  e.g. 1.5 → 1.5%
    tp_pct:    Optional[float] = None   # take-profit % e.g. 3.0
    reason:    Optional[str]  = None
    extra:     Optional[dict] = None    # pass-through for anything else


# ── Helpers ───────────────────────────────────────────────────────────────────
def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _append_log(record: dict) -> None:
    _SIGNALS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(_SIGNALS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _tg_send(msg: str) -> None:
    if not (TG_TOKEN and TG_CHAT):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"},
            timeout=8,
        )
    except Exception:
        pass


def _normalise_side(raw: str) -> str:
    """Convert buy/long → long, sell/short → short."""
    r = raw.strip().lower()
    if r in ("buy", "long"):
        return "long"
    if r in ("sell", "short"):
        return "short"
    return r


def _check_health_gate(strategy: str) -> tuple[bool, str]:
    """Returns (allowed, reason)."""
    hd = _read_json(_HEALTH_FILE)
    strats = hd.get("strategies") or {}
    # Try exact match, then fuzzy
    info = strats.get(strategy) or strats.get(f"alt_{strategy}") or strats.get(f"{strategy}_v1")
    if info is None:
        return True, "strategy not in health file — defaulting OK"
    st = str(info.get("status", "OK")).upper()
    if st in ("PAUSE", "KILL"):
        return False, f"health gate {st}"
    return True, f"health gate {st}"


def _check_regime(side: str) -> tuple[bool, str]:
    """Returns (compatible, reason)."""
    rd = _read_json(_REGIME_FILE)
    regime = str(rd.get("regime", "neutral")).lower()
    compat = REGIME_SIDE_COMPAT.get(regime, {"long": True, "short": True})
    allowed = compat.get(side, True)
    return allowed, f"regime={regime}"


# ── Endpoint ──────────────────────────────────────────────────────────────────
@router.post("/tv-signal")
async def receive_tv_signal(payload: TVSignal, request: Request):
    """
    Receive a TradingView Pine Script alert and process it.
    No auth cookie required — uses TV_WEBHOOK_SECRET instead.
    """
    ts = int(time.time())
    ts_iso = datetime.now(timezone.utc).isoformat()

    # ── 1. Secret check ───────────────────────────────────────────────────────
    if not TV_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TV_WEBHOOK_SECRET not configured on server",
        )
    if payload.secret != TV_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )

    # ── 2. Normalise ──────────────────────────────────────────────────────────
    symbol   = payload.symbol.strip().upper()
    side     = _normalise_side(payload.side)
    strategy = (payload.strategy or "tv_signal").strip()

    if side not in ("long", "short"):
        raise HTTPException(status_code=422, detail=f"Unknown side: {payload.side}")

    # ── 3. Health gate ────────────────────────────────────────────────────────
    gate_ok, gate_reason = _check_health_gate(strategy)

    # ── 4. Regime check ───────────────────────────────────────────────────────
    regime_ok, regime_reason = _check_regime(side)

    # ── 5. Decision ───────────────────────────────────────────────────────────
    blocked  = not gate_ok or not regime_ok
    block_reasons = []
    if not gate_ok:
        block_reasons.append(gate_reason)
    if not regime_ok:
        block_reasons.append(f"regime mismatch ({regime_reason})")

    record: dict[str, Any] = {
        "ts": ts,
        "ts_iso": ts_iso,
        "symbol": symbol,
        "side": side,
        "strategy": strategy,
        "price": payload.price,
        "timeframe": payload.timeframe,
        "sl_pct": payload.sl_pct,
        "tp_pct": payload.tp_pct,
        "reason": payload.reason,
        "gate_ok": gate_ok,
        "gate_reason": gate_reason,
        "regime_ok": regime_ok,
        "regime_reason": regime_reason,
        "blocked": blocked,
        "block_reasons": block_reasons,
        "mode": TV_MODE,
        "source_ip": request.client.host if request.client else "unknown",
    }

    # ── 6. Log always ─────────────────────────────────────────────────────────
    _append_log(record)

    # ── 7. Telegram notify ────────────────────────────────────────────────────
    if TV_MODE in ("notify", "auto"):
        side_icon  = "🟢" if side == "long" else "🔴"
        block_icon = "🚫" if blocked else "✅"
        price_str  = f"${payload.price:,.4f}" if payload.price else "—"
        sl_str     = f"{payload.sl_pct}%" if payload.sl_pct else "—"
        tp_str     = f"{payload.tp_pct}%" if payload.tp_pct else "—"

        msg = (
            f"📡 *TradingView Signal*\n"
            f"{side_icon} `{symbol}` {side.upper()} @ {price_str}\n"
            f"Strategy: `{strategy}` · TF: {payload.timeframe or '—'}\n"
            f"SL: {sl_str} · TP: {tp_str}\n"
            f"Reason: _{payload.reason or '—'}_\n\n"
            f"{block_icon} "
        )
        if blocked:
            msg += f"*BLOCKED* — {' | '.join(block_reasons)}"
        else:
            msg += f"*PASSED* — {gate_reason} | {regime_reason}"
            if TV_MODE == "auto":
                msg += "\n🤖 _Queued for bot pickup_"

        _tg_send(msg)

    # ── 8. Auto mode — write pending signal for bot ───────────────────────────
    if TV_MODE == "auto" and not blocked:
        _PENDING.parent.mkdir(parents=True, exist_ok=True)
        pending = {
            "ts": ts,
            "symbol": symbol,
            "side": side,
            "strategy": strategy,
            "price": payload.price,
            "sl_pct": payload.sl_pct,
            "tp_pct": payload.tp_pct,
            "reason": payload.reason,
            "timeframe": payload.timeframe,
            "source": "tradingview",
            "consumed": False,
        }
        _PENDING.write_text(json.dumps(pending, indent=2))

    return {
        "ok": True,
        "symbol": symbol,
        "side": side,
        "blocked": blocked,
        "block_reasons": block_reasons,
        "mode": TV_MODE,
        "ts": ts,
    }


# ── Signal history endpoint ───────────────────────────────────────────────────
@router.get("/tv-signals")
async def get_tv_signals(limit: int = 50, _: str = Depends(require_auth)):
    """
    Return recent TradingView signals from the log to authenticated operators.
    """
    if not _SIGNALS_LOG.exists():
        return {"signals": [], "total": 0}

    lines = _SIGNALS_LOG.read_text(encoding="utf-8").splitlines()
    signals = []
    for line in reversed(lines[-500:]):
        try:
            signals.append(json.loads(line))
        except Exception:
            continue
        if len(signals) >= limit:
            break

    return {
        "signals": signals,
        "total": len(lines),
        "log_path": str(_SIGNALS_LOG),
    }
