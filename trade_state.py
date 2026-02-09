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

    # Legacy (чтобы не ломать текущие проверки, если они есть)
    PENDING_ENTRY = "PENDING_ENTRY"


@dataclass
class TradeState:
    """
    ВАЖНО: это расширенная сущность сделки, но она сохраняет старые поля,
    чтобы текущий smart_pump_reversal_bot.py не упал.

    Дальше мы:
    - переведём бот на TradeStatus.*,
    - добавим заполнение fills/fees/pnl/timestamps,
    - исправим SYNC и дерганье open_trades.
    """

    # --- identity / base ---
    symbol: str
    side: str  # "Buy" / "Sell"

    trade_id: str = ""               # опционально (позже можно делать uuid)
    strategy: str = "pump"           # "pump" / "bounce"

    qty: float = 0.0
    entry_ts: int = 0
    exit_ts: int = 0

    # --- orders ---
    entry_order_id: Optional[str] = None
    exit_order_id: Optional[str] = None

    # --- status ---
    # Оставляем legacy-дефолт, чтобы не ломать текущие if'ы в боте.
    # В следующем шаге в main-файле заменим на TradeStatus.PLACING_ENTRY и т.д.
    status: str = TradeStatus.PENDING_ENTRY

    # --- pricing / execution (legacy + расширение) ---
    entry_price_req: float = 0.0
    entry_price: Optional[float] = None

    # legacy: у тебя код "везде использует tr.avg"
    avg: float = 0.0

    entry_avg_price: Optional[float] = None
    entry_exec_qty: Optional[float] = None

    exit_price: Optional[float] = None
    exit_avg_price: Optional[float] = None
    exit_exec_qty: Optional[float] = None

    # --- TP/SL (legacy) ---
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None

    tpsl_on_exchange: bool = False
    tpsl_manual_lock: bool = False
    tpsl_last_set_ts: int = 0

    # --- pump strategy state (legacy) ---
    leg1_done: bool = False
    leg2_done: bool = False
    local_low: Optional[float] = None

    # --- diagnostics / accounting (new, optional) ---
    fills: List[Dict[str, Any]] = field(default_factory=list)  # entry/exit fills
    fees: float = 0.0
    realized_pnl: Optional[float] = None
    unrealized_pnl: Optional[float] = None

    reason_open: Optional[str] = None
    reason_close: Optional[str] = None

    # --- misc ---
    entry_confirm_sent: bool = False

    # legacy: оставляю, но дальше будем использовать reason_close
    close_reason: Optional[str] = None

    last_sync_ts: int = 0
