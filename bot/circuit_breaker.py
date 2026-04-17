"""
bot/circuit_breaker.py
======================
Portfolio-level circuit breaker that automatically reduces or halts new trade
entries when the portfolio suffers excessive drawdown.

States:
  NORMAL  — risk_mult = 1.0  (no drawdown protection triggered)
  CAUTION — risk_mult = 0.5  (moderate drawdown, halved position sizes)
  HALT    — risk_mult = 0.0  (severe drawdown, no new entries for cooldown hours)

Drawdown is measured two ways:
  1. DAILY  — drop from start-of-day equity to current equity
  2. PEAK   — drop from all-time peak equity seen this session

ENV vars:
  CB_ENABLED=1                (default: 1 — enabled)
  CB_DAILY_CAUTION_PCT=0.04   (4% daily drawdown → CAUTION)
  CB_DAILY_HALT_PCT=0.08      (8% daily drawdown → HALT)
  CB_PEAK_CAUTION_PCT=0.06    (6% peak drawdown → CAUTION)
  CB_PEAK_HALT_PCT=0.12       (12% peak drawdown → HALT)
  CB_HALT_COOLDOWN_HOURS=24   (hours before re-enabling after HALT)
  CB_NOTIFY_ON_STATE_CHANGE=1 (log state transitions)

Usage in smart_pump_reversal_bot.py:
    from bot.circuit_breaker import PortfolioCircuitBreaker
    _CB = PortfolioCircuitBreaker()

    # Before every try_*_entry_async:
    cb_mult = _CB.get_risk_mult()
    if cb_mult == 0.0:
        return  # HALT — no new entries

    # Apply multiplier to position sizing (optional, or just block on HALT):
    # position_usd = calc_position_usd(...) * cb_mult
"""

from __future__ import annotations

import os
import time
import json
import logging
from typing import Callable, Optional

log = logging.getLogger(__name__)


# ─── States ──────────────────────────────────────────────────────────────────

class CBState:
    NORMAL  = "NORMAL"
    CAUTION = "CAUTION"
    HALT    = "HALT"


# ─── Circuit Breaker ─────────────────────────────────────────────────────────

class PortfolioCircuitBreaker:
    """
    Monitors equity drawdown and returns a risk multiplier for position sizing.

    Call update(equity) whenever equity is refreshed.
    Call get_risk_mult() before opening any new position.
    """

    def __init__(self) -> None:
        self._state = CBState.NORMAL
        self._peak_equity: Optional[float] = None
        self._day_start_equity: Optional[float] = None
        self._day_key: Optional[int] = None
        self._halt_until: float = 0.0    # epoch seconds
        self._last_log_state = CBState.NORMAL

        # Optional Telegram / notification callback.
        # Set via set_notify_func() in smart_pump_reversal_bot.py at startup.
        # Signature: func(message: str) -> None
        # Kept out of __init__ args to avoid circular imports.
        self._notify_func: Optional[Callable[[str], None]] = None

        # Load thresholds from env
        self._reload_config()

    def _reload_config(self) -> None:
        self.enabled              = os.getenv("CB_ENABLED", "1").strip() == "1"
        self.daily_caution_pct    = float(os.getenv("CB_DAILY_CAUTION_PCT",  "0.04"))
        self.daily_halt_pct       = float(os.getenv("CB_DAILY_HALT_PCT",     "0.08"))
        self.peak_caution_pct     = float(os.getenv("CB_PEAK_CAUTION_PCT",   "0.06"))
        self.peak_halt_pct        = float(os.getenv("CB_PEAK_HALT_PCT",      "0.12"))
        self.halt_cooldown_hours  = float(os.getenv("CB_HALT_COOLDOWN_HOURS","24"))
        self.notify_on_change     = os.getenv("CB_NOTIFY_ON_STATE_CHANGE", "1").strip() == "1"

    def update(self, equity: float) -> None:
        """
        Feed current equity to the circuit breaker.
        Call this whenever equity is updated (e.g. every _get_equity_now() call).
        """
        if not self.enabled:
            return
        if equity <= 0:
            return

        now = time.time()

        # Track all-time session peak
        if self._peak_equity is None or equity > self._peak_equity:
            self._peak_equity = equity

        # Track day-start equity
        day_key = int(now) // 86400
        if self._day_key != day_key:
            self._day_key = day_key
            self._day_start_equity = equity  # reset at start of each day

        if self._day_start_equity is None:
            self._day_start_equity = equity

        # Compute drawdowns
        daily_dd = self._daily_drawdown(equity)
        peak_dd  = self._peak_drawdown(equity)

        # Determine new state
        new_state = self._compute_state(daily_dd, peak_dd, now)

        # Handle HALT cooldown: once HALTed, stay HALT until cooldown expires
        if self._state == CBState.HALT and now < self._halt_until:
            new_state = CBState.HALT

        # Set HALT timer when transitioning into HALT
        if new_state == CBState.HALT and self._state != CBState.HALT:
            self._halt_until = now + self.halt_cooldown_hours * 3600.0
            self._log_state_change(CBState.HALT, daily_dd, peak_dd, equity)

        # Log state changes
        elif new_state != self._state:
            self._log_state_change(new_state, daily_dd, peak_dd, equity)

        self._state = new_state

    def _daily_drawdown(self, equity: float) -> float:
        """Fraction dropped from start-of-day equity (0.05 = 5% drop)."""
        if self._day_start_equity and self._day_start_equity > 0:
            return max(0.0, (self._day_start_equity - equity) / self._day_start_equity)
        return 0.0

    def _peak_drawdown(self, equity: float) -> float:
        """Fraction dropped from all-time session peak (0.10 = 10% drop)."""
        if self._peak_equity and self._peak_equity > 0:
            return max(0.0, (self._peak_equity - equity) / self._peak_equity)
        return 0.0

    def _compute_state(self, daily_dd: float, peak_dd: float, now: float) -> str:
        """Compute target state based on current drawdowns."""
        # HALT conditions (worst case)
        if daily_dd >= self.daily_halt_pct or peak_dd >= self.peak_halt_pct:
            return CBState.HALT

        # CAUTION conditions
        if daily_dd >= self.daily_caution_pct or peak_dd >= self.peak_caution_pct:
            return CBState.CAUTION

        # Check if HALT cooldown has expired
        if self._state == CBState.HALT and now >= self._halt_until:
            return CBState.CAUTION  # come back slowly, not straight to NORMAL

        return CBState.NORMAL

    def get_risk_mult(self) -> float:
        """
        Returns the risk multiplier to apply to position sizing:
          NORMAL  → 1.0
          CAUTION → 0.5
          HALT    → 0.0 (caller should skip new entries entirely)
        """
        if not self.enabled:
            return 1.0
        if self._state == CBState.HALT:
            return 0.0
        if self._state == CBState.CAUTION:
            return 0.5
        return 1.0

    def get_state(self) -> str:
        return self._state

    def status_report(self) -> dict:
        """Returns a dict suitable for diagnostics/health reporting."""
        return {
            "cb_enabled": self.enabled,
            "cb_state": self._state,
            "cb_risk_mult": self.get_risk_mult(),
            "cb_peak_equity": round(float(self._peak_equity or 0), 2),
            "cb_day_start_equity": round(float(self._day_start_equity or 0), 2),
            "cb_halt_until": self._halt_until if self._state == CBState.HALT else 0,
        }

    def _log_state_change(self, new_state: str, daily_dd: float, peak_dd: float, equity: float) -> None:
        if not self.notify_on_change:
            return
        msg = (
            f"[CircuitBreaker] {self._state} → {new_state} | "
            f"equity={equity:.2f} | "
            f"daily_dd={daily_dd*100:.1f}% (halt≥{self.daily_halt_pct*100:.0f}%) | "
            f"peak_dd={peak_dd*100:.1f}% (halt≥{self.peak_halt_pct*100:.0f}%)"
        )
        if new_state == CBState.HALT:
            log.warning(msg)
            # Write runtime state file for external monitoring / Codex audit
            try:
                with open("runtime/circuit_breaker.json", "w") as f:
                    json.dump({
                        "state": new_state,
                        "equity": equity,
                        "daily_dd_pct": round(daily_dd * 100, 2),
                        "peak_dd_pct": round(peak_dd * 100, 2),
                        "halt_until_epoch": self._halt_until,
                        "ts": time.time(),
                    }, f, indent=2)
            except Exception:
                pass
            # Telegram alert for HALT — highest urgency
            tg_msg = (
                f"🚨 CIRCUIT BREAKER HALT 🚨\n"
                f"New entries BLOCKED for {self.halt_cooldown_hours:.0f}h\n"
                f"Equity: {equity:.2f} USDT\n"
                f"Daily DD: {daily_dd*100:.1f}% (limit {self.daily_halt_pct*100:.0f}%)\n"
                f"Peak DD: {peak_dd*100:.1f}% (limit {self.peak_halt_pct*100:.0f}%)\n"
                f"Resumes after cooldown (CAUTION mode first)"
            )
            if self._notify_func:
                try:
                    self._notify_func(tg_msg)
                except Exception:
                    pass
        elif new_state == CBState.CAUTION:
            log.warning(msg)
            # Telegram alert for CAUTION — moderate urgency
            prev = self._state
            if prev == CBState.NORMAL:
                tg_msg = (
                    f"⚠️ CIRCUIT BREAKER CAUTION\n"
                    f"Position sizes halved (0.5×)\n"
                    f"Equity: {equity:.2f} USDT\n"
                    f"Daily DD: {daily_dd*100:.1f}% (limit {self.daily_caution_pct*100:.0f}%)\n"
                    f"Peak DD: {peak_dd*100:.1f}% (limit {self.peak_caution_pct*100:.0f}%)"
                )
            else:
                # Recovering from HALT → CAUTION
                tg_msg = (
                    f"🟡 CIRCUIT BREAKER → CAUTION (recovering from HALT)\n"
                    f"Position sizes at 0.5× | Equity: {equity:.2f} USDT"
                )
            if self._notify_func:
                try:
                    self._notify_func(tg_msg)
                except Exception:
                    pass
        elif new_state == CBState.NORMAL and self._state in (CBState.CAUTION, CBState.HALT):
            log.info(msg)
            # Notify recovery to NORMAL
            tg_msg = (
                f"✅ CIRCUIT BREAKER → NORMAL\n"
                f"Full position sizes restored | Equity: {equity:.2f} USDT"
            )
            if self._notify_func:
                try:
                    self._notify_func(tg_msg)
                except Exception:
                    pass
        else:
            log.info(msg)

    def set_notify_func(self, func: Callable[[str], None]) -> None:
        """Register a notification callback (e.g. tg_send from the main bot).

        Called on every state transition with a human-readable message.
        Must be set externally to avoid circular imports.

        Example (in smart_pump_reversal_bot.py)::

            from bot.circuit_breaker import get_circuit_breaker
            get_circuit_breaker().set_notify_func(tg_send)
        """
        self._notify_func = func

    def reset_for_testing(self) -> None:
        """Reset state — useful in unit tests and backtests."""
        self._state = CBState.NORMAL
        self._peak_equity = None
        self._day_start_equity = None
        self._day_key = None
        self._halt_until = 0.0
        self._notify_func = None


# ─── Singleton (used by bot) ─────────────────────────────────────────────────

_circuit_breaker: Optional[PortfolioCircuitBreaker] = None


def get_circuit_breaker() -> PortfolioCircuitBreaker:
    """Get the global circuit breaker instance."""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = PortfolioCircuitBreaker()
    return _circuit_breaker
