from dataclasses import replace

import pytest

from bot.att1_coordinator_adapter import (
    AdapterViolation,
    validate_att1_broker_snapshot,
    validate_old_att1_broker_identity,
)


OBSERVED_MS = 1_700_000_060_000
CONFIG = {
    "name": "att1",
    "key": "key-att1-test",
    "base": "https://api.bybit.com",
}


def _identity(*, user_id=731, response_ms=OBSERVED_MS - 1_000):
    return validate_old_att1_broker_identity(
        CONFIG,
        {
            "retCode": 0,
            "time": response_ms,
            "result": {"apiKey": CONFIG["key"], "userID": user_id},
        },
        received_ms=OBSERVED_MS,
    )


def _envelope(rows, *, cursor=""):
    return {
        "retCode": 0,
        "time": OBSERVED_MS - 500,
        "result": {"category": "linear", "list": rows, "nextPageCursor": cursor},
    }


def _position(*, symbol="BTCUSDT", size="0", position_idx=0, side=""):
    return {"symbol": symbol, "size": size, "positionIdx": position_idx, "side": side}


def _order(*, order_id="order-1", symbol="BTCUSDT", qty="1", cum_exec_qty="0",
           side="Buy", status="New"):
    return {
        "orderId": order_id,
        "symbol": symbol,
        "qty": qty,
        "cumExecQty": cum_exec_qty,
        "side": side,
        "orderStatus": status,
    }


def _snapshot(*, identity=None, positions=None, orders=None, position_pages=None,
              order_pages=None):
    return validate_att1_broker_snapshot(
        CONFIG,
        identity or _identity(),
        position_pages=position_pages if position_pages is not None else [_envelope(positions or [])],
        order_pages=order_pages if order_pages is not None else [_envelope(orders or [])],
        observed_ms=OBSERVED_MS,
    )


def test_valid_flat_snapshot_is_redacted_and_has_complete_source_digest():
    out = _snapshot()

    assert out["schema_id"] == "att1_broker_snapshot_v1"
    assert out["account"] == _identity().account
    assert out["observed_ms"] == OBSERVED_MS
    assert out["position_count"] == 0
    assert out["order_count"] == 0
    assert out["flat_no_orders"] is True
    assert len(out["source_sha256"]) == 64
    assert CONFIG["key"] not in repr(out)


def test_existing_nonflat_account_is_accepted_but_flat_no_orders_is_false():
    out = _snapshot(
        positions=[_position(size="0.25", side="Sell")],
        orders=[],
    )

    assert out["position_count"] == 1
    assert out["order_count"] == 0
    assert out["flat_no_orders"] is False


@pytest.mark.parametrize(
    "identity",
    [
        replace(_identity(), account="uid:not-a-sha256"),
        replace(_identity(), credential_binding_sha256="f" * 64),
        replace(_identity(), observed_at_ms=OBSERVED_MS - 61_000),
    ],
    ids=["malformed-uid", "wrong-key-binding", "stale-identity"],
)
def test_identity_binding_uid_key_and_staleness_are_rejected(identity):
    with pytest.raises(AdapterViolation):
        _snapshot(identity=identity)


def test_identity_from_wrong_config_key_is_rejected():
    identity = _identity()
    wrong_config = {**CONFIG, "key": "another-key"}
    with pytest.raises(AdapterViolation):
        validate_att1_broker_snapshot(
            wrong_config,
            identity,
            position_pages=[_envelope([])],
            order_pages=[_envelope([])],
            observed_ms=OBSERVED_MS,
        )


def test_partial_pagination_is_rejected():
    with pytest.raises(AdapterViolation):
        _snapshot(position_pages=[_envelope([], cursor="next")], order_pages=[_envelope([])])


def test_pagination_cursor_must_be_unique_and_terminal_page_empty():
    page = _envelope([_position(symbol="ETHUSDT")], cursor="same")
    with pytest.raises(AdapterViolation):
        _snapshot(position_pages=[page, page], order_pages=[_envelope([])])


def test_duplicate_entity_rows_across_pages_are_rejected():
    first = _envelope([_position(symbol="ETHUSDT")], cursor="next")
    second = _envelope([_position(symbol="ETHUSDT")])
    with pytest.raises(AdapterViolation):
        _snapshot(position_pages=[first, second], order_pages=[_envelope([])])


@pytest.mark.parametrize(
    "position",
    [
        {"symbol": "BTCUSDT", "size": True, "positionIdx": 0, "side": ""},
        {"symbol": "BTCUSDT", "positionIdx": 0, "side": ""},
        {"symbol": "BTCUSDT", "size": "NaN", "positionIdx": 0, "side": ""},
        {"symbol": "BTCUSDT", "size": "1", "positionIdx": 0, "side": ""},
    ],
    ids=["boolean-size", "missing-size", "unknown-size", "nonzero-missing-side"],
)
def test_position_missing_unknown_boolean_and_direction_fields_are_rejected(position):
    with pytest.raises(AdapterViolation):
        _snapshot(positions=[position])


def test_position_identity_must_be_unique_by_symbol_and_position_idx():
    with pytest.raises(AdapterViolation):
        _snapshot(positions=[_position(), _position()])


@pytest.mark.parametrize(
    "order",
    [
        _order(qty=True),
        {**_order(), "cumExecQty": "2"},
        {**_order(), "orderStatus": "Filled"},
        {**_order(), "side": ""},
        {**_order(), "orderId": ""},
    ],
    ids=["boolean-qty", "cum-exceeds-qty", "inactive-status", "unknown-side", "missing-id"],
)
def test_order_schema_and_active_lifecycle_constraints_are_rejected(order):
    with pytest.raises(AdapterViolation):
        _snapshot(orders=[order])


def test_order_identity_must_be_unique():
    with pytest.raises(AdapterViolation):
        _snapshot(orders=[_order(), _order()])


def test_nonterminal_page_must_be_followed_by_complete_terminal_page():
    pages = [_envelope([_position(symbol="ETHUSDT", size="0.1", side="Sell")], cursor="next"), _envelope([])]
    out = _snapshot(position_pages=pages, order_pages=[_envelope([])])
    assert out["position_count"] == 1


@pytest.mark.parametrize(
    "mutate",
    [
        lambda page: page.update(retCode="0"),
        lambda page: page.update(time=True),
        lambda page: page["result"].update(category="spot"),
        lambda page: page["result"].update(list={}),
        lambda page: page["result"].update(nextPageCursor=1),
    ],
    ids=["retcode-type", "time-type", "wrong-category", "list-type", "cursor-type"],
)
def test_signed_page_envelope_types_and_category_are_strict(mutate):
    page = _envelope([])
    mutate(page)
    with pytest.raises(AdapterViolation):
        _snapshot(position_pages=[page], order_pages=[_envelope([])])


def test_more_than_sixteen_pages_is_rejected():
    pages = [_envelope([], cursor=f"cursor-{index}") for index in range(16)]
    pages.append(_envelope([]))
    with pytest.raises(AdapterViolation):
        _snapshot(position_pages=pages, order_pages=[_envelope([])])


def test_source_digest_changes_when_any_complete_raw_page_changes():
    first = _snapshot()
    second = _snapshot(order_pages=[_envelope([_order(order_id="order-2")])])

    assert first["source_sha256"] != second["source_sha256"]


@pytest.mark.parametrize(
    "page_time",
    [OBSERVED_MS - 60_001, OBSERVED_MS + 1],
    ids=["stale-page", "future-page"],
)
def test_page_timestamp_must_be_fresh_and_not_from_the_future(page_time):
    page = _envelope([])
    page["time"] = page_time
    with pytest.raises(AdapterViolation):
        _snapshot(position_pages=[page], order_pages=[_envelope([])])
