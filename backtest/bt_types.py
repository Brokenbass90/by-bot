"""Shared backtest types.

Historically, parts of this repo imported :class:`TradeSignal` from
``backtest.types`` while others imported it from ``strategies.signals``.

To keep the runtime simple (and avoid subtle mismatches when we add new
fields such as partial TPs and trailing stops), we re-export the canonical
definition from ``strategies.signals``.
"""

from strategies.signals import TradeSignal

__all__ = ["TradeSignal"]
