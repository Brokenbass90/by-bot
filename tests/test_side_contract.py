from __future__ import annotations

import pytest

from bot.side_contract import SideContractError, normalize_side, to_exchange_side


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("long", "long"),
        ("LONG", "long"),
        (" Buy ", "long"),
        ("short", "short"),
        ("Sell", "short"),
        ("SELL", "short"),
    ],
)
def test_normalize_side_accepts_only_declared_aliases(value: object, expected: str) -> None:
    assert normalize_side(value) == expected


@pytest.mark.parametrize("value", [None, "", "hold", 1, True])
def test_normalize_side_rejects_unknown_empty_and_non_string_values(value: object) -> None:
    with pytest.raises(SideContractError, match="unsupported side"):
        normalize_side(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("long", "Buy"), ("buy", "Buy"), ("short", "Sell"), ("SELL", "Sell")],
)
def test_to_exchange_side_returns_exact_bybit_vocabulary(value: object, expected: str) -> None:
    assert to_exchange_side(value) == expected
