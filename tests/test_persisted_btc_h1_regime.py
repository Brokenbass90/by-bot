from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal

import pytest

from bot.live_native_regime_gate import ClosedH1EMA200RegimeGate, H1_MS
from bot.persisted_btc_h1_regime import (
    BTCRegimeContractError,
    BTCRegimeReceipt,
    advance_btc_h1_regime,
    bootstrap_btc_h1_regime,
    load_btc_h1_regime,
    persist_btc_h1_regime,
    regime_evidence,
)


START = 1_700_000_000_000 // H1_MS * H1_MS
SOURCE = {
    "provider": "bybit-public",
    "endpoint": "/v5/market/kline",
    "source_sha256": "a" * 64,
}
DATA = {
    "symbol": "BTCUSDT",
    "interval": "60",
    "data_sha256": "b" * 64,
    "provenance": "fixed-test-feed",
}


def rows(count: int = 500, last_close: str = "99") -> list[list[str]]:
    result: list[list[str]] = []
    for index in range(count):
        close = last_close if index == count - 1 else "100"
        result.append(
            [str(START + index * H1_MS), "100", "101", "99", close, "1"]
        )
    return result


def observed_for(raw_rows: list[list[str]]) -> int:
    return int(raw_rows[-1][0]) + H1_MS + 1


def test_bootstrap_requires_500_contiguous_closed_rows_and_records_provenance() -> None:
    raw_rows = rows()
    receipt = bootstrap_btc_h1_regime(
        raw_rows,
        observed_at_ms=observed_for(raw_rows),
        max_age_ms=300_000,
        source_provenance=SOURCE,
        data_provenance=DATA,
    )

    assert receipt.state.observation_count == 500
    assert receipt.state.value == "flat_down"
    assert receipt.state.allows("ATT1") is True
    assert receipt.state.allows("SBR1") is False
    assert receipt.state.source_provenance["source_sha256"] == "a" * 64
    assert receipt.state.data_provenance["data_sha256"] == "b" * 64
    assert receipt.money_authority is False
    with pytest.raises(BTCRegimeContractError, match="insufficient_bootstrap_history"):
        bootstrap_btc_h1_regime(
            raw_rows[:-1],
            observed_at_ms=observed_for(raw_rows),
            max_age_ms=300_000,
            source_provenance=SOURCE,
            data_provenance=DATA,
        )


def test_bootstrap_rejects_gap_and_open_or_stale_last_bar() -> None:
    raw_rows = rows()
    raw_rows[100][0] = str(int(raw_rows[99][0]) + 2 * H1_MS)
    with pytest.raises(BTCRegimeContractError, match="noncontiguous_bootstrap"):
        bootstrap_btc_h1_regime(
            raw_rows,
            observed_at_ms=observed_for(raw_rows),
            max_age_ms=300_000,
            source_provenance=SOURCE,
            data_provenance=DATA,
        )

    raw_rows = rows()
    with pytest.raises(BTCRegimeContractError, match="bar_not_closed"):
        bootstrap_btc_h1_regime(
            raw_rows,
            observed_at_ms=int(raw_rows[-1][0]) + H1_MS - 1,
            max_age_ms=300_000,
            source_provenance=SOURCE,
            data_provenance=DATA,
        )
    with pytest.raises(BTCRegimeContractError, match="evidence_too_old"):
        bootstrap_btc_h1_regime(
            raw_rows,
            observed_at_ms=observed_for(raw_rows) + 300_001,
            max_age_ms=300_000,
            source_provenance=SOURCE,
            data_provenance=DATA,
        )


def test_advance_is_exactly_one_bar_and_identical_duplicate_is_idempotent() -> None:
    raw_rows = rows()
    receipt = bootstrap_btc_h1_regime(
        raw_rows,
        observed_at_ms=observed_for(raw_rows),
        max_age_ms=300_000,
        source_provenance=SOURCE,
        data_provenance=DATA,
    )
    next_row = [str(START + 500 * H1_MS), "100", "101", "99", "101", "1"]
    advanced = advance_btc_h1_regime(
        receipt,
        next_row,
        observed_at_ms=int(next_row[0]) + H1_MS + 1,
        max_age_ms=300_000,
    )
    repeated = advance_btc_h1_regime(
        advanced,
        list(next_row),
        observed_at_ms=int(next_row[0]) + H1_MS + 2,
        max_age_ms=300_000,
    )
    assert advanced.state.observation_count == 501
    assert advanced.state.last_bar_start_ts_ms == int(next_row[0])
    assert repeated.to_dict() == advanced.to_dict()


def test_same_start_and_close_is_semantic_duplicate_even_if_raw_row_changes() -> None:
    raw_rows = rows()
    gate = ClosedH1EMA200RegimeGate()
    live = None
    for row in raw_rows:
        live = gate.update(
            row,
            observed_at_ms=int(row[0]) + H1_MS + 1,
            max_age_ms=300_000,
        )
    receipt = bootstrap_btc_h1_regime(
        raw_rows,
        observed_at_ms=observed_for(raw_rows),
        max_age_ms=300_000,
        source_provenance=SOURCE,
        data_provenance=DATA,
    )
    original_row_hash = receipt.state.last_row_hash
    semantic_duplicate = [
        raw_rows[-1][0],
        "1",
        "999999",
        "0.1",
        raw_rows[-1][4],
        "999",
    ]

    repeated = advance_btc_h1_regime(
        receipt,
        semantic_duplicate,
        observed_at_ms=observed_for(raw_rows) + 1,
        max_age_ms=300_000,
    )
    live_repeated = gate.update(
        semantic_duplicate,
        observed_at_ms=observed_for(raw_rows) + 1,
        max_age_ms=300_000,
    )

    assert repeated.to_dict() == receipt.to_dict()
    assert repeated.state.last_row_hash == original_row_hash
    assert live_repeated is not None and live is not None
    assert live_repeated.history_bars == live.history_bars
    assert live_repeated.ema200 == live.ema200
    assert live_repeated.value == live.value
    assert regime_evidence(
        repeated,
        observed_at_ms=observed_for(raw_rows) + 1,
        max_age_ms=300_000,
    ) == live_repeated


@pytest.mark.parametrize(
    ("row_start", "close", "error"),
    [
        (START + 500 * H1_MS + 2 * H1_MS, "101", "gap_in_regime_history"),
        (START + 498 * H1_MS, "101", "out_of_order_regime_bar"),
        (START + 499 * H1_MS, "102", "conflicting_regime_duplicate"),
    ],
)
def test_advance_rejects_gap_out_of_order_and_conflicting_duplicate(
    row_start: int, close: str, error: str
) -> None:
    raw_rows = rows()
    receipt = bootstrap_btc_h1_regime(
        raw_rows,
        observed_at_ms=observed_for(raw_rows),
        max_age_ms=300_000,
        source_provenance=SOURCE,
        data_provenance=DATA,
    )
    next_row = [str(row_start), "100", "101", "99", close, "1"]
    with pytest.raises(BTCRegimeContractError, match=error):
        advance_btc_h1_regime(
            receipt,
            next_row,
            observed_at_ms=row_start + H1_MS + 1,
            max_age_ms=300_000,
        )


def test_atomic_persistence_is_0600_and_load_verifies_hash_and_invariants(tmp_path) -> None:
    raw_rows = rows()
    receipt = bootstrap_btc_h1_regime(
        raw_rows,
        observed_at_ms=observed_for(raw_rows),
        max_age_ms=300_000,
        source_provenance=SOURCE,
        data_provenance=DATA,
    )
    path = tmp_path / "btc-regime.json"
    persist_btc_h1_regime(path, receipt)
    assert os.stat(path).st_mode & 0o777 == 0o600
    loaded = load_btc_h1_regime(path)
    assert loaded.to_dict() == receipt.to_dict()

    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["state"]["ema200"] = "1"
    path.write_text(json.dumps(tampered, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(BTCRegimeContractError, match="receipt_hash_mismatch"):
        load_btc_h1_regime(path)


def test_loaded_state_rejects_unsafe_mode(tmp_path) -> None:
    raw_rows = rows()
    receipt = bootstrap_btc_h1_regime(
        raw_rows,
        observed_at_ms=observed_for(raw_rows),
        max_age_ms=300_000,
        source_provenance=SOURCE,
        data_provenance=DATA,
    )
    path = tmp_path / "btc-regime.json"
    persist_btc_h1_regime(path, receipt)
    path.chmod(0o644)
    with pytest.raises(BTCRegimeContractError, match="state_file_mode"):
        load_btc_h1_regime(path)


def test_persist_fails_closed_on_broken_symlink_target(tmp_path) -> None:
    raw_rows = rows()
    receipt = bootstrap_btc_h1_regime(
        raw_rows,
        observed_at_ms=observed_for(raw_rows),
        max_age_ms=300_000,
        source_provenance=SOURCE,
        data_provenance=DATA,
    )
    path = tmp_path / "btc-regime.json"
    path.symlink_to(tmp_path / "missing-state.json")

    with pytest.raises(BTCRegimeContractError, match="state_file_unreadable"):
        persist_btc_h1_regime(path, receipt)

    assert path.is_symlink()


@pytest.mark.parametrize(
    ("source_patch", "data_patch", "error"),
    [
        ({"provider": "evil"}, {}, "invalid_source_provenance"),
        ({"endpoint": "kline"}, {}, "invalid_source_provenance"),
        ({"source_sha256": "A" * 64}, {}, "invalid_sha256"),
        ({"unexpected": "value"}, {}, "invalid_source_provenance"),
        ({}, {"symbol": "ETHUSDT"}, "invalid_data_provenance"),
        ({}, {"interval": "5"}, "invalid_data_provenance"),
        ({}, {"interval": 60}, "invalid_data_provenance"),
        ({}, {"data_sha256": "B" * 64}, "invalid_sha256"),
        ({}, {"unexpected": "value"}, "invalid_data_provenance"),
    ],
)
def test_bootstrap_requires_strict_approved_public_provenance(
    source_patch: dict[str, object], data_patch: dict[str, object], error: str
) -> None:
    raw_rows = rows()
    source = dict(SOURCE)
    source.update(source_patch)
    data = dict(DATA)
    data.update(data_patch)
    with pytest.raises(BTCRegimeContractError, match=error):
        bootstrap_btc_h1_regime(
            raw_rows,
            observed_at_ms=observed_for(raw_rows),
            max_age_ms=300_000,
            source_provenance=source,
            data_provenance=data,
        )


@pytest.mark.parametrize("operation", ["advance", "evidence", "persist"])
def test_every_receipt_consuming_api_rejects_forged_authority(
    operation: str, tmp_path
) -> None:
    raw_rows = rows()
    valid = bootstrap_btc_h1_regime(
        raw_rows,
        observed_at_ms=observed_for(raw_rows),
        max_age_ms=300_000,
        source_provenance=SOURCE,
        data_provenance=DATA,
    )
    forged = BTCRegimeReceipt(state=valid.state, money_authority=True)
    next_row = [str(START + 500 * H1_MS), "100", "101", "99", "101", "1"]
    with pytest.raises(BTCRegimeContractError, match="regime_receipt_authority_forbidden"):
        if operation == "advance":
            advance_btc_h1_regime(
                forged,
                next_row,
                observed_at_ms=int(next_row[0]) + H1_MS + 1,
                max_age_ms=300_000,
            )
        elif operation == "evidence":
            regime_evidence(
                forged,
                observed_at_ms=observed_for(raw_rows),
                max_age_ms=300_000,
            )
        else:
            persist_btc_h1_regime(tmp_path / "forged.json", forged)


def test_falsey_non_boolean_authority_is_still_rejected() -> None:
    raw_rows = rows()
    valid = bootstrap_btc_h1_regime(
        raw_rows,
        observed_at_ms=observed_for(raw_rows),
        max_age_ms=300_000,
        source_provenance=SOURCE,
        data_provenance=DATA,
    )
    forged = BTCRegimeReceipt(state=valid.state, money_authority=0)  # type: ignore[arg-type]
    with pytest.raises(BTCRegimeContractError, match="regime_receipt_authority_forbidden"):
        regime_evidence(
            forged,
            observed_at_ms=observed_for(raw_rows),
            max_age_ms=300_000,
        )


@pytest.mark.parametrize("operation", ["advance", "evidence", "persist"])
def test_every_receipt_consuming_api_rejects_forged_state(
    operation: str, tmp_path
) -> None:
    raw_rows = rows()
    valid = bootstrap_btc_h1_regime(
        raw_rows,
        observed_at_ms=observed_for(raw_rows),
        max_age_ms=300_000,
        source_provenance=SOURCE,
        data_provenance=DATA,
    )
    forged = BTCRegimeReceipt(
        state=replace(
            valid.state,
            source_provenance={**SOURCE, "provider": "evil"},
        )
    )
    next_row = [str(START + 500 * H1_MS), "100", "101", "99", "101", "1"]
    with pytest.raises(BTCRegimeContractError, match="invalid_source_provenance"):
        if operation == "advance":
            advance_btc_h1_regime(
                forged,
                next_row,
                observed_at_ms=int(next_row[0]) + H1_MS + 1,
                max_age_ms=300_000,
            )
        elif operation == "evidence":
            regime_evidence(
                forged,
                observed_at_ms=observed_for(raw_rows),
                max_age_ms=300_000,
            )
        else:
            persist_btc_h1_regime(tmp_path / "forged.json", forged)


def test_persistence_rejects_rollback_and_failed_compare_and_swap(tmp_path) -> None:
    raw_rows = rows()
    initial = bootstrap_btc_h1_regime(
        raw_rows,
        observed_at_ms=observed_for(raw_rows),
        max_age_ms=300_000,
        source_provenance=SOURCE,
        data_provenance=DATA,
    )
    path = tmp_path / "btc-regime.json"
    persist_btc_h1_regime(path, initial)
    next_row = [str(START + 500 * H1_MS), "100", "101", "99", "101", "1"]
    advanced = advance_btc_h1_regime(
        initial,
        next_row,
        observed_at_ms=int(next_row[0]) + H1_MS + 1,
        max_age_ms=300_000,
    )
    persist_btc_h1_regime(
        path,
        advanced,
        expected_previous_receipt_sha256=initial.receipt_sha256,
    )

    with pytest.raises(BTCRegimeContractError, match="state_rollback_forbidden"):
        persist_btc_h1_regime(
            path,
            initial,
            expected_previous_receipt_sha256=advanced.receipt_sha256,
        )
    sibling_row = [str(START + 500 * H1_MS), "100", "101", "99", "102", "1"]
    sibling = advance_btc_h1_regime(
        initial,
        sibling_row,
        observed_at_ms=int(sibling_row[0]) + H1_MS + 1,
        max_age_ms=300_000,
    )
    with pytest.raises(BTCRegimeContractError, match="state_compare_and_swap_failed"):
        persist_btc_h1_regime(
            path,
            sibling,
            expected_previous_receipt_sha256=initial.receipt_sha256,
        )
    assert load_btc_h1_regime(path).to_dict() == advanced.to_dict()


def test_stable_lock_serializes_competing_compare_and_swap_writers(tmp_path) -> None:
    raw_rows = rows()
    initial = bootstrap_btc_h1_regime(
        raw_rows,
        observed_at_ms=observed_for(raw_rows),
        max_age_ms=300_000,
        source_provenance=SOURCE,
        data_provenance=DATA,
    )
    path = tmp_path / "btc-regime.json"
    persist_btc_h1_regime(path, initial)
    children = []
    for close in ("101", "102"):
        row = [str(START + 500 * H1_MS), "100", "101", "99", close, "1"]
        children.append(
            advance_btc_h1_regime(
                initial,
                row,
                observed_at_ms=int(row[0]) + H1_MS + 1,
                max_age_ms=300_000,
            )
        )

    def write(receipt: BTCRegimeReceipt) -> str:
        try:
            persist_btc_h1_regime(
                path,
                receipt,
                expected_previous_receipt_sha256=initial.receipt_sha256,
            )
        except BTCRegimeContractError as exc:
            return exc.code
        return "ok"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(write, children))

    assert sorted(outcomes) == ["ok", "state_compare_and_swap_failed"]
    lock_path = path.with_name(f".{path.name}.lock")
    assert lock_path.is_file()
    assert os.stat(lock_path).st_mode & 0o777 == 0o600
    assert load_btc_h1_regime(path).receipt_sha256 in {
        child.receipt_sha256 for child in children
    }


def test_persisted_evidence_matches_live_gate_through_bootstrap_and_advance() -> None:
    raw_rows = rows(last_close="99")
    gate = ClosedH1EMA200RegimeGate()
    live = None
    for row in raw_rows:
        live = gate.update(
            row,
            observed_at_ms=int(row[0]) + H1_MS + 1,
            max_age_ms=300_000,
        )
    persisted = bootstrap_btc_h1_regime(
        raw_rows,
        observed_at_ms=observed_for(raw_rows),
        max_age_ms=300_000,
        source_provenance=SOURCE,
        data_provenance=DATA,
    )
    projected = regime_evidence(
        persisted,
        observed_at_ms=observed_for(raw_rows),
        max_age_ms=300_000,
    )
    assert live is not None
    assert projected == live

    next_row = [str(START + 500 * H1_MS), "100", "101", "99", "101", "1"]
    live = gate.update(
        next_row,
        observed_at_ms=int(next_row[0]) + H1_MS + 1,
        max_age_ms=300_000,
    )
    persisted = advance_btc_h1_regime(
        persisted,
        next_row,
        observed_at_ms=int(next_row[0]) + H1_MS + 1,
        max_age_ms=300_000,
    )
    projected = regime_evidence(
        persisted,
        observed_at_ms=int(next_row[0]) + H1_MS + 1,
        max_age_ms=300_000,
    )
    assert projected == live
