# trade_state.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


class TradeStatus:
    # Новая статус-машина (переедем на неё в smart_pump_reversal_bot.py)
    PLACING_ENTRY = "PLACING_ENTRY"
    ENTRY_WORKING = "ENTRY_WORKING"
    OPEN = "OPEN"
    PLACING_EXIT = "PLACING_EXIT"
    EXIT_WORKING = "EXIT_WORKING"
    CLOSED = "CLOSED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    # Legacy (чтобы не ломать текущие проверки)
    PENDING_ENTRY = "PENDING_ENTRY"


@dataclass
class TradeState:
    """
    Состояние одной сделки.

    Канонические поля (используй их в новом коде):
        avg           — средняя цена входа (float)
        close_reason  — причина закрытия (str | None)

    Устаревшие алиасы (не удалены ради обратной совместимости):
        entry_avg_price  →  property, читает/пишет avg
        reason_close     →  property, читает/пишет close_reason

    fills — список dict с ключами {role, price, qty, fee, ts}.
        Заполняется через add_fill('entry'|'exit', ...).
        Используй realized_pnl_from_fills для точного PnL.
    """

    # --- identity / base ---
    symbol: str
    side: str  # "Buy" / "Sell"

    trade_id: str = ""
    strategy: str = "pump"       # "pump" / "bounce" / "breakout" / ...

    qty: float = 0.0
    entry_ts: int = 0
    exit_ts: int = 0

    # --- orders ---
    entry_order_id: Optional[str] = None
    exit_order_id: Optional[str] = None

    # --- status ---
    status: str = TradeStatus.PENDING_ENTRY

    # --- pricing / execution ---
    entry_price_req: float = 0.0
    entry_price: Optional[float] = None

    # Канонический avg: используется ботом как «средняя цена входа»
    avg: float = 0.0

    # NOTE: entry_avg_price объявлен ниже как @property → avg

    entry_exec_qty: Optional[float] = None

    exit_price: Optional[float] = None
    exit_avg_price: Optional[float] = None
    exit_exec_qty: Optional[float] = None

    # --- TP/SL ---
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None

    tpsl_on_exchange: bool = False
    tpsl_manual_lock: bool = False
    tpsl_last_set_ts: int = 0

    # --- pump strategy state (legacy) ---
    leg1_done: bool = False
    leg2_done: bool = False
    local_low: Optional[float] = None

    # --- accounting ---
    fills: List[Dict[str, Any]] = field(default_factory=list)
    fees: float = 0.0
    realized_pnl: Optional[float] = None       # manual override; None → use fills
    unrealized_pnl: Optional[float] = None

    reason_open: Optional[str] = None

    # Канонический close_reason: используется ботом
    close_reason: Optional[str] = None

    # NOTE: reason_close объявлен ниже как @property → close_reason

    # --- misc ---
    entry_confirm_sent: bool = False
    last_sync_ts: int = 0

    # --- inplay runner (live) ---
    runner_enabled: bool = False
    initial_qty: float = 0.0
    remaining_qty: float = 0.0
    tps: List[float] = field(default_factory=list)
    tp_fracs: List[float] = field(default_factory=list)
    tp_hit: List[bool] = field(default_factory=list)
    trail_mult: float = 0.0
    trail_period: int = 14
    hh: Optional[float] = None
    ll: Optional[float] = None
    time_stop_sec: int = 0
    last_runner_action_ts: int = 0

    # ─── Deprecated property aliases ────────────────────────────────────────

    @property
    def entry_avg_price(self) -> Optional[float]:
        """Deprecated alias for avg. Use tr.avg in new code."""
        return self.avg if self.avg else None

    @entry_avg_price.setter
    def entry_avg_price(self, value: Optional[float]) -> None:
        if value is not None:
            self.avg = float(value)

    @property
    def reason_close(self) -> Optional[str]:
        """Deprecated alias for close_reason. Use tr.close_reason in new code."""
        return self.close_reason

    @reason_close.setter
    def reason_close(self, value: Optional[str]) -> None:
        self.close_reason = value

    # ─── Fill helpers ────────────────────────────────────────────────────────

    def add_fill(
        self,
        role: str,
        price: float,
        qty: float,
        fee: float = 0.0,
        ts: int = 0,
    ) -> None:
        """Record an execution fill.

        Args:
            role:  'entry' or 'exit'
            price: execution price
            qty:   executed quantity (positive)
            fee:   taker/maker fee in quote currency (positive = cost)
            ts:    unix timestamp of fill
        """
        self.fills.append({
            "role": str(role),
            "price": float(price),
            "qty": float(qty),
            "fee": float(fee),
            "ts": int(ts),
        })
        self.fees += float(fee)

    # ─── PnL ────────────────────────────────────────────────────────────────

    @property
    def realized_pnl_from_fills(self) -> Optional[float]:
        """Compute realized PnL from fills, net of fees.

        Returns None if entry or exit fills are missing.
        For Long:  (sum exit values) - (sum entry values) - total_fees
        For Short: (sum entry values) - (sum exit values) - total_fees
        """
        entry_fills = [f for f in self.fills if f["role"] == "entry"]
        exit_fills  = [f for f in self.fills if f["role"] == "exit"]
        if not entry_fills or not exit_fills:
            return None
        entry_value = sum(f["price"] * f["qty"] for f in entry_fills)
        exit_value  = sum(f["price"] * f["qty"] for f in exit_fills)
        gross = (exit_value - entry_value) if self.side == "Buy" else (entry_value - exit_value)
        return round(gross - self.fees, 8)

    @property
    def best_pnl(self) -> Optional[float]:
        """Return realized_pnl_from_fills if available, else realized_pnl field."""
        pnl = self.realized_pnl_from_fills
        if pnl is not None:
            return pnl
        return self.realized_pnl
