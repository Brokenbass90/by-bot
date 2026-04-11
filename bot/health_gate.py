"""
bot/health_gate.py — Strategy Health Gate
==========================================
Live entry gating based on equity_curve_autopilot.py output.
Reads configs/strategy_health.json (written weekly by autopilot).

Usage in smart_pump_reversal_bot.py — add ONE line before each maybe_signal call:
    from bot.health_gate import gate
    ...
    if not gate.allow_entry("alt_sloped_channel_v1", symbol): return
    sig = strat.maybe_signal(...)

Or use the decorator:
    @gate.guard("alt_sloped_channel_v1")
    async def handle_asc1_tick(symbol, price, ...):
        ...

Status levels:
    OK    → entry allowed
    WATCH → entry allowed + Telegram warning (once per day)
    PAUSE → entry BLOCKED + Telegram alert
    KILL  → entry BLOCKED + Telegram alert + flag for human review

Integration map (ENABLE_* → strategy name):
    ENABLE_SLOPED_TRADING    → alt_sloped_channel_v1 (legacy, disabled)
    ENABLE_ATT1_TRADING      → alt_trendline_touch_v1 (swing-pivot trendline bounce)
    ENABLE_ASM1_TRADING      → alt_sloped_momentum_v1 (sloped channel breakout)
    ENABLE_FLAT_TRADING      → alt_resistance_fade_v1
    ENABLE_BREAKDOWN_TRADING → alt_inplay_breakdown_v1
    ENABLE_MIDTERM_TRADING   → btc_eth_midterm_pullback
    ENABLE_INPLAY_TRADING    → inplay_breakout
    ENABLE_TS132_TRADING     → triple_screen_v132
"""
from __future__ import annotations

import json
import os
import ssl
import time
from datetime import date, datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib import request

ROOT        = Path(__file__).resolve().parent.parent
HEALTH_FILE = ROOT / "configs" / "strategy_health.json"
ALERT_LOG   = ROOT / "configs" / "health_gate_alerts.json"

# How often to re-read the health file (seconds). 3600 = 1 hour.
CACHE_TTL_S = 3600

# Map from strategy name used in health file → ENV enable flag
STRATEGY_ENV_MAP: Dict[str, str] = {
    "alt_sloped_channel_v1":     "ENABLE_SLOPED_TRADING",
    "alt_trendline_touch_v1":    "ENABLE_ATT1_TRADING",
    "alt_sloped_momentum_v1":    "ENABLE_ASM1_TRADING",
    "alt_resistance_fade_v1":    "ENABLE_FLAT_TRADING",
    "alt_inplay_breakdown_v1":   "ENABLE_BREAKDOWN_TRADING",
    "btc_eth_midterm_pullback":  "ENABLE_MIDTERM_TRADING",
    "btc_eth_midterm_pullback_v2": "ENABLE_MIDTERM_TRADING",
    "inplay_breakout":           "ENABLE_INPLAY_TRADING",
    "micro_scalper_v1":          "ENABLE_MICRO_SCALPER_TRADING",
    "alt_support_reclaim_v1":    "ENABLE_SUPPORT_RECLAIM_TRADING",
    "triple_screen_v132":        "ENABLE_TS132_TRADING",
    "pump_fade_simple":          "ENABLE_PUMP_FADE_TRADING",
    "sr_break_retest_volume_v1": "ENABLE_RETEST_TRADING",
}


def _tg(token: str, chat_id: str, msg: str) -> None:
    if not token or not chat_id:
        return
    payload = json.dumps({"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}).encode()
    req = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, context=ssl.create_default_context(), timeout=8):
            pass
    except Exception:
        pass


class HealthGate:
    """
    Singleton-style gate. Import and use `gate` from this module.
    Thread-safe for asyncio (single-threaded event loop).
    """
    def __init__(self) -> None:
        self._cache: Dict[str, Any] = {}
        self._cache_ts: float = 0.0
        self._alert_log: Dict[str, str] = {}   # strategy → last alert date
        self._tg_token  = os.getenv("TG_TOKEN", "")
        self._tg_chat   = os.getenv("TG_CHAT_ID", "")
        self._load_alert_log()

    # ── Cache management ────────────────────────────────────────────────────────
    def _reload_if_stale(self) -> None:
        now = time.monotonic()
        if now - self._cache_ts < CACHE_TTL_S and self._cache:
            return
        if not HEALTH_FILE.exists():
            self._cache = {}
            return
        try:
            data = json.loads(HEALTH_FILE.read_text())
            self._cache = data.get("strategies", {})
            self._cache_ts = now
        except Exception:
            pass

    def _load_alert_log(self) -> None:
        if ALERT_LOG.exists():
            try:
                self._alert_log = json.loads(ALERT_LOG.read_text())
            except Exception:
                self._alert_log = {}

    def _save_alert_log(self) -> None:
        try:
            ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
            ALERT_LOG.write_text(json.dumps(self._alert_log, indent=2))
        except Exception:
            pass

    # ── Status query ────────────────────────────────────────────────────────────
    def get_status(self, strategy_name: str) -> str:
        """
        Returns OK / WATCH / PAUSE / KILL.

        For known live sleeves that are missing from the health file, default to
        WATCH instead of silently returning OK. This keeps uncovered sleeves
        visible without unexpectedly hard-blocking them.
        """
        self._reload_if_stale()
        info = self._cache.get(strategy_name, {})
        if info:
            return str(info.get("status", "OK"))
        missing_default = str(os.getenv("HEALTH_GATE_MISSING_STATUS", "WATCH")).strip().upper() or "WATCH"
        if strategy_name in STRATEGY_ENV_MAP:
            return missing_default
        return "OK"

    def allow_entry(self, strategy_name: str, symbol: str = "") -> bool:
        """
        Call before every maybe_signal. Returns True if entry is allowed.
        Sends Telegram alert on status change (max once per day per strategy).
        """
        status = self.get_status(strategy_name)
        today  = date.today().isoformat()

        if status in ("PAUSE", "KILL"):
            # Alert once per day
            last_alert = self._alert_log.get(strategy_name, "")
            if last_alert != today:
                self._send_block_alert(strategy_name, status, symbol)
                self._alert_log[strategy_name] = today
                self._save_alert_log()
            return False

        if status == "WATCH":
            # Warning once per day, but still allow entry
            last_alert = self._alert_log.get(f"watch_{strategy_name}", "")
            if last_alert != today:
                self._send_watch_alert(strategy_name, symbol)
                self._alert_log[f"watch_{strategy_name}"] = today
                self._save_alert_log()

        return True

    # ── Decorator ───────────────────────────────────────────────────────────────
    def guard(self, strategy_name: str):
        """
        Decorator for async handler functions.
        Blocks execution if strategy is in PAUSE/KILL state.

        @gate.guard("alt_sloped_channel_v1")
        async def handle_asc1(symbol, price, ...):
            ...
        """
        def decorator(fn: Callable) -> Callable:
            @wraps(fn)
            async def wrapper(*args, **kwargs):
                symbol = kwargs.get("symbol", args[0] if args else "")
                if not self.allow_entry(strategy_name, str(symbol)):
                    return None
                return await fn(*args, **kwargs)
            return wrapper
        return decorator

    # ── Alerts ──────────────────────────────────────────────────────────────────
    def _send_block_alert(self, strategy: str, status: str, symbol: str) -> None:
        emoji = "🔴" if status == "KILL" else "🟠"
        info  = self._cache.get(strategy, {})
        env_flag = STRATEGY_ENV_MAP.get(strategy, "unknown")
        msg = (
            f"{emoji} <b>Health Gate BLOCKING {strategy}</b> [{status}]\n"
            f"Symbol: {symbol or 'all'}\n"
            f"30d PnL: {info.get('rolling_30d_pnl', 0):+.3f} | "
            f"Curve vs MA: {info.get('curve_vs_ma20', 0):+.3f}\n"
            f"Trades 30d: {info.get('trades_30d', 0)}\n"
            f"Notes: {info.get('notes', 'none')}\n\n"
            f"Action: Run autoresearch or set {env_flag}=0 to disable.\n"
            f"Review: /ai_tune {strategy}"
        )
        _tg(self._tg_token, self._tg_chat, msg)

    def _send_watch_alert(self, strategy: str, symbol: str) -> None:
        info = self._cache.get(strategy, {})
        msg = (
            f"⚠️ <b>Health Gate WATCH: {strategy}</b>\n"
            f"Equity curve below MA20 — entries still allowed but monitor closely.\n"
            f"30d PnL: {info.get('rolling_30d_pnl', 0):+.3f} | "
            f"Curve vs MA: {info.get('curve_vs_ma20', 0):+.3f}\n"
            f"No action needed yet. Run weekly autopilot to reassess."
        )
        _tg(self._tg_token, self._tg_chat, msg)

    # ── Bulk status ─────────────────────────────────────────────────────────────
    def status_summary(self) -> Dict[str, str]:
        """Returns {strategy_name: status} for all strategies."""
        self._reload_if_stale()
        return {k: v.get("status", "OK") for k, v in self._cache.items()}

    def any_blocked(self) -> bool:
        return any(s in ("PAUSE", "KILL") for s in self.status_summary().values())

    def force_reload(self) -> None:
        """Force re-read of health file (call after running autopilot manually)."""
        self._cache_ts = 0.0
        self._reload_if_stale()


# Module-level singleton — import this in the main bot
gate = HealthGate()


# ── Minimal integration snippet for smart_pump_reversal_bot.py ─────────────────
#
# Add near top of file (after imports):
#   from bot.health_gate import gate
#
# Then before EACH maybe_signal call, add ONE line:
#
# Example 1 — ASC1 (sloped channel):
#   if not gate.allow_entry("alt_sloped_channel_v1", symbol): return
#   sig = ASC1_STRATEGY[symbol].maybe_signal(store, ts_ms, o, h, l, c, v)
#
# Example 2 — breakdown:
#   if not gate.allow_entry("alt_inplay_breakdown_v1", symbol): return
#   sig = BREAKDOWN_STRATEGY[symbol].maybe_signal(store, ts_ms, o, h, l, c, v)
#
# Example 3 — decorator on handler function:
#   @gate.guard("btc_eth_midterm_pullback")
#   async def handle_midterm_tick(symbol, price, ts_ms):
#       ...
#
# That's it. The gate:
#   - Reads configs/strategy_health.json (cached 1h)
#   - Sends Telegram alert once/day on status change
#   - Returns False for PAUSE/KILL, True for OK/WATCH
# ──────────────────────────────────────────────────────────────────────────────
