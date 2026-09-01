from __future__ import annotations

import pytest

from backtest.engine import _apply_slippage
from bot.side_contract import SideContractError


@pytest.mark.parametrize(
    ("internal", "exchange", "is_entry", "expected"),
    [
        ("long", "Buy", True, 100.05),
        ("long", "buy", False, 99.95),
        ("short", "Sell", True, 99.95),
        ("short", "SELL", False, 100.05),
    ],
)
def test_slippage_is_identical_for_internal_and_exchange_aliases(
    internal: str,
    exchange: str,
    is_entry: bool,
    expected: float,
) -> None:
    assert _apply_slippage(100.0, internal, is_entry, 5.0) == pytest.approx(expected)
    assert _apply_slippage(100.0, exchange, is_entry, 5.0) == pytest.approx(expected)


def test_slippage_rejects_unknown_side_instead_of_treating_it_as_short() -> None:
    with pytest.raises(SideContractError, match="unsupported side"):
        _apply_slippage(100.0, "hold", True, 5.0)
