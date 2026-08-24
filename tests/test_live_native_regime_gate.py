from __future__ import annotations

from decimal import Decimal

import pytest

from bot.live_native_decision_contract import ContractViolation, H1_MS
from bot.live_native_regime_gate import (
    ClosedH1EMA200RegimeGate,
    LIVE_NATIVE_REGIME_GATE_ENABLED_BY_DEFAULT,
    classify_deviation,
    closed_h1_btc_ema200_regime,
)


START = 1_700_000_000_000 // H1_MS * H1_MS


def _rows(last_close: str = "100"):
    rows = []
    for index in range(200):
        close = last_close if index == 199 else "100"
        rows.append([START + index * H1_MS, "100", "101", "99", close, "1"])
    return rows


def test_regime_gate_is_default_off_and_sleeve_specific() -> None:
    assert LIVE_NATIVE_REGIME_GATE_ENABLED_BY_DEFAULT is False
    rows = _rows("99")
    close_ts = rows[-1][0] + H1_MS
    evidence = closed_h1_btc_ema200_regime(
        rows, observed_at_ms=close_ts + 1, max_age_ms=300_000
    )
    assert evidence.value == "flat_down"
    assert evidence.seed_start_ts_ms == rows[0][0]
    assert evidence.history_bars == 200
    assert evidence.allows("ATT1") is True
    assert evidence.allows("SBR1") is False


def test_flat_up_is_zero_inclusive_and_two_percent_exclusive() -> None:
    assert classify_deviation(Decimal("0")) == "flat_up"
    assert classify_deviation(Decimal("0.019999")) == "flat_up"
    assert classify_deviation(Decimal("0.02")) == "above_band"
    assert classify_deviation(Decimal("-0.02")) == "flat_down"


def test_ema_uses_full_causal_history_instead_of_reseeding_latest_200() -> None:
    rows = []
    for index in range(400):
        close = "50" if index < 200 else "100"
        rows.append([START + index * H1_MS, close, close, close, close, "1"])
    close_ts = rows[-1][0] + H1_MS
    evidence = closed_h1_btc_ema200_regime(
        rows, observed_at_ms=close_ts + 1, max_age_ms=300_000
    )
    assert evidence.history_bars == 400
    assert evidence.value == "above_band"


def test_stateful_gate_is_causal_and_same_bar_idempotent() -> None:
    gate = ClosedH1EMA200RegimeGate()
    evidence = None
    rows = _rows("99")
    for row in rows:
        close_ts = row[0] + H1_MS
        evidence = gate.update(
            row, observed_at_ms=close_ts + 1, max_age_ms=300_000
        )
    assert evidence is not None
    repeated = gate.update(
        rows[-1],
        observed_at_ms=rows[-1][0] + H1_MS + 2,
        max_age_ms=300_000,
    )
    assert repeated is not None
    assert repeated.history_bars == 200
    assert repeated.ema200 == evidence.ema200


@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (lambda rows: rows[:-1], "insufficient_regime_history"),
        (
            lambda rows: rows[:100]
            + [[rows[100][0] + H1_MS, *rows[100][1:]]]
            + rows[101:],
            "noncontiguous_regime_h1_rows",
        ),
    ],
)
def test_missing_or_noncontiguous_history_fails_closed(mutator, code: str) -> None:
    rows = mutator(_rows())
    with pytest.raises(ContractViolation, match=code):
        closed_h1_btc_ema200_regime(
            rows,
            observed_at_ms=START + 201 * H1_MS,
            max_age_ms=2 * H1_MS,
        )


def test_open_or_stale_regime_bar_fails_closed() -> None:
    rows = _rows()
    close_ts = rows[-1][0] + H1_MS
    with pytest.raises(ContractViolation, match="regime_h1_bar_not_closed"):
        closed_h1_btc_ema200_regime(
            rows, observed_at_ms=close_ts - 1, max_age_ms=300_000
        )
    with pytest.raises(ContractViolation, match="regime_evidence_too_old"):
        closed_h1_btc_ema200_regime(
            rows, observed_at_ms=close_ts + 300_001, max_age_ms=300_000
        )
