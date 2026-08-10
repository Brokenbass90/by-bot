from __future__ import annotations

import asyncio

import pytest

from bot.maker_execution import assess_entry_risk, execute_maker_first


async def _no_sleep(_: float) -> None:
    return None


class FakeClient:
    def __init__(self, statuses, *, position=(0.0, None, 0, None, None, None), price=100.0):
        self.statuses = list(statuses)
        self.position = position
        self.price = price
        self.cancelled = False
        self.market_calls = 0

    def place_post_only(self, symbol, side, qty, reference_price, offset_bps):
        return "maker-1", qty, 99.98 if side == "Buy" else 100.02

    def get_order(self, symbol, order_id):
        if self.statuses:
            return self.statuses.pop(0)
        return {"orderStatus": "Cancelled" if self.cancelled else "New", "cumExecQty": "0"}

    def cancel_order(self, symbol, order_id):
        self.cancelled = True
        return True

    def get_position_summary(self, symbol):
        return self.position

    def get_last_price(self, symbol):
        return self.price

    def place_market(self, symbol, side, qty, allow_quote_fallback):
        self.market_calls += 1
        return "market-1", qty


class UnconfirmedCancelClient(FakeClient):
    def cancel_order(self, symbol, order_id):
        self.cancelled = False
        return True


class OneStatusErrorClient(FakeClient):
    def __init__(self, statuses, **kwargs):
        super().__init__(statuses, **kwargs)
        self.status_error_pending = True

    def get_order(self, symbol, order_id):
        if self.status_error_pending:
            self.status_error_pending = False
            raise RuntimeError("temporary status timeout")
        return super().get_order(symbol, order_id)


def test_assess_entry_risk_blocks_expansion() -> None:
    result = assess_entry_risk(
        side="Buy",
        qty=10,
        planned_entry=100,
        actual_entry=100.4,
        stop_price=99,
        max_risk_expansion=1.15,
    )
    assert result.allowed is False
    assert result.reason == "risk_expansion"
    assert result.expansion_ratio == pytest.approx(1.4)


@pytest.mark.parametrize(
    ("side", "planned", "actual", "stop", "targets"),
    [
        ("Sell", 0.8136, 0.8023, 0.8205, [0.805391, 0.796499]),
        ("Buy", 100.0, 101.2, 99.0, [101.0, 102.0]),
    ],
)
def test_assess_entry_risk_rejects_fill_that_already_crossed_target(
    side, planned, actual, stop, targets
) -> None:
    result = assess_entry_risk(
        side=side,
        qty=10,
        planned_entry=planned,
        actual_entry=actual,
        stop_price=stop,
        max_risk_expansion=10.0,
        max_adverse_bps=1000.0,
        target_prices=targets,
    )

    assert result.allowed is False
    assert result.reason == "target_crossed_before_fill"


def test_assess_entry_risk_accepts_targets_still_ahead_of_fill() -> None:
    result = assess_entry_risk(
        side="Sell",
        qty=10,
        planned_entry=100.0,
        actual_entry=99.95,
        stop_price=101.0,
        max_risk_expansion=1.20,
        max_adverse_bps=25.0,
        target_prices=[99.0, 98.0],
    )

    assert result.allowed is True


def test_maker_fill_never_calls_market() -> None:
    client = FakeClient([{"orderStatus": "Filled", "cumExecQty": "2", "avgPrice": "99.98"}])
    result = asyncio.run(
        execute_maker_first(
            client,
            symbol="BTCUSDT",
            side="Buy",
            qty=2,
            reference_price=100,
            stop_price=99,
            wait_sec=1,
            poll_sec=1,
            sleep=_no_sleep,
        )
    )
    assert result.ok is True
    assert result.mode == "maker"
    assert result.fill_price == pytest.approx(99.98)
    assert client.market_calls == 0


def test_timeout_cancels_before_safe_market_fallback() -> None:
    client = FakeClient(
        [
            {"orderStatus": "New", "cumExecQty": "0"},
            {"orderStatus": "Cancelled", "cumExecQty": "0"},
        ],
        price=100.02,
    )
    result = asyncio.run(
        execute_maker_first(
            client,
            symbol="BTCUSDT",
            side="Buy",
            qty=2,
            reference_price=100,
            stop_price=99,
            wait_sec=1,
            poll_sec=1,
            max_adverse_bps=10,
            max_risk_expansion=1.15,
            sleep=_no_sleep,
        )
    )
    assert result.ok is True
    assert result.mode == "market_fallback"
    assert result.cancel_confirmed is True
    assert client.market_calls == 1


def test_timeout_blocks_fallback_when_risk_expands() -> None:
    client = FakeClient(
        [
            {"orderStatus": "New", "cumExecQty": "0"},
            {"orderStatus": "Cancelled", "cumExecQty": "0"},
        ],
        price=100.4,
    )
    result = asyncio.run(
        execute_maker_first(
            client,
            symbol="BTCUSDT",
            side="Buy",
            qty=2,
            reference_price=100,
            stop_price=99,
            wait_sec=1,
            poll_sec=1,
            max_adverse_bps=100,
            max_risk_expansion=1.15,
            sleep=_no_sleep,
        )
    )
    assert result.ok is False
    assert result.reason == "fallback_blocked:risk_expansion"
    assert client.market_calls == 0


def test_partial_fill_is_accepted_without_crossing_remainder() -> None:
    client = FakeClient(
        [
            {"orderStatus": "PartiallyFilled", "cumExecQty": "0.4", "avgPrice": "99.98"},
            {"orderStatus": "Cancelled", "cumExecQty": "0.4", "avgPrice": "99.98"},
        ],
        position=(0.4, "Buy", 0, None, None, 99.98),
    )
    result = asyncio.run(
        execute_maker_first(
            client,
            symbol="BTCUSDT",
            side="Buy",
            qty=2,
            reference_price=100,
            stop_price=99,
            wait_sec=1,
            poll_sec=1,
            sleep=_no_sleep,
        )
    )
    assert result.ok is True
    assert result.mode == "maker_partial"
    assert result.qty == pytest.approx(0.4)
    assert client.market_calls == 0


def test_partial_fill_cancelled_status_is_accepted() -> None:
    client = FakeClient(
        [
            {"orderStatus": "PartiallyFilled", "cumExecQty": "0.4", "avgPrice": "99.98"},
            {"orderStatus": "PartiallyFilledCanceled", "cumExecQty": "0.4", "avgPrice": "99.98"},
        ],
        position=(0.4, "Buy", 0, None, None, 99.98),
    )
    result = asyncio.run(
        execute_maker_first(
            client,
            symbol="BTCUSDT",
            side="Buy",
            qty=2,
            reference_price=100,
            stop_price=99,
            wait_sec=1,
            poll_sec=1,
            sleep=_no_sleep,
        )
    )
    assert result.ok is True
    assert result.mode == "maker_partial"
    assert result.cancel_confirmed is True
    assert client.market_calls == 0


def test_unconfirmed_cancel_never_falls_back_to_market() -> None:
    client = UnconfirmedCancelClient(
        [
            {"orderStatus": "New", "cumExecQty": "0"},
            {"orderStatus": "New", "cumExecQty": "0"},
        ],
        price=100.0,
    )
    result = asyncio.run(
        execute_maker_first(
            client,
            symbol="BTCUSDT",
            side="Buy",
            qty=2,
            reference_price=100,
            stop_price=99,
            wait_sec=1,
            poll_sec=1,
            sleep=_no_sleep,
        )
    )
    assert result.ok is False
    assert result.reason == "maker_cancel_unconfirmed"
    assert client.market_calls == 0


def test_status_error_attempts_cancel_before_fallback() -> None:
    client = OneStatusErrorClient(
        [{"orderStatus": "Cancelled", "cumExecQty": "0"}],
        price=100.01,
    )
    result = asyncio.run(
        execute_maker_first(
            client,
            symbol="BTCUSDT",
            side="Buy",
            qty=2,
            reference_price=100,
            stop_price=99,
            wait_sec=1,
            poll_sec=1,
            sleep=_no_sleep,
        )
    )
    assert client.cancelled is True
    assert result.ok is True
    assert result.cancel_confirmed is True
    assert result.mode == "market_fallback"
    assert client.market_calls == 1
