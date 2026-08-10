from __future__ import annotations

from bot.position_reconciliation import entry_allowed, reconcile_positions


NOW = 1_800_000_000.0
FRESH = {name: NOW - 10 for name in ("broker", "runner", "owner", "accounting")}


def _position(*, qty: float = 12.0, side: str = "Sell", strategy: str = "att1") -> dict:
    return {
        "symbol": "ADAUSDT",
        "side": side,
        "qty": qty,
        "strategy": strategy,
        "stop": 0.1992,
    }


def _run(**overrides):
    args = {
        "broker_rows": [_position()],
        "runner_rows": [_position()],
        "owner_rows": [_position()],
        "accounting_rows": [_position()],
        "source_as_of_ts": FRESH,
        "now_ts": NOW,
    }
    args.update(overrides)
    return reconcile_positions(**args)


def test_four_equal_sources_reconcile_and_allow_entry() -> None:
    receipt = _run()

    assert receipt["ok"] is True
    assert receipt["blocked_symbols"] == []
    assert receipt["records"][0]["status"] == "RECONCILED"
    assert entry_allowed(receipt, "ADAUSDT") is True


def test_broker_without_runner_blocks_only_conflicted_symbol() -> None:
    receipt = _run(runner_rows=[])

    assert receipt["global_block_new_entries"] is False
    assert receipt["blocked_symbols"] == ["ADAUSDT"]
    assert "runner_missing_for_broker_position" in receipt["records"][0]["conflict_codes"]
    assert entry_allowed(receipt, "ADAUSDT") is False
    assert entry_allowed(receipt, "BTCUSDT") is True


def test_qty_and_owner_mismatches_are_both_visible() -> None:
    receipt = _run(
        runner_rows=[_position(qty=11.0)],
        owner_rows=[_position(strategy="breakdown")],
    )

    codes = receipt["records"][0]["conflict_codes"]
    assert "qty_mismatch" in codes
    assert "strategy_owner_mismatch" in codes
    assert entry_allowed(receipt, "ADAUSDT") is False


def test_missing_broker_stop_blocks_additions_not_management() -> None:
    broker = _position()
    broker.pop("stop")
    receipt = _run(broker_rows=[broker])

    assert "broker_stop_missing" in receipt["records"][0]["conflict_codes"]
    assert receipt["scope"] == "block_new_entries_only_existing_management_continues"


def test_stale_source_is_global_fail_close() -> None:
    stale = dict(FRESH)
    stale["accounting"] = NOW - 181
    receipt = _run(source_as_of_ts=stale)

    assert receipt["global_block_new_entries"] is True
    assert entry_allowed(receipt, "BTCUSDT") is False
    assert any(row["code"] == "source_stale_or_missing" for row in receipt["conflicts"])


def test_duplicate_or_hedged_rows_block_symbol() -> None:
    receipt = _run(broker_rows=[_position(), _position(side="Buy")])

    assert receipt["blocked_symbols"] == ["ADAUSDT"]
    assert "duplicate_or_hedged_rows" in receipt["records"][0]["conflict_codes"]


def test_unknown_receipt_schema_fails_closed() -> None:
    assert entry_allowed({}, "ADAUSDT") is False


def test_missing_source_container_is_global_fail_close() -> None:
    receipt = _run(owner_rows=None)

    assert receipt["global_block_new_entries"] is True
    assert any(row["code"] == "invalid_source_container" for row in receipt["conflicts"])
    assert entry_allowed(receipt, "BTCUSDT") is False
