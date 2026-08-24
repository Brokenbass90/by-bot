"""Closed-H1 BTC EMA200 regime evidence for ATT1/SBR1 parity.

The gate is pure, default-off, and has no broker or environment access.  It
accepts only completed, strictly ordered Bybit-style H1 rows and records the
bar timestamp, observation age, EMA and deviation used by the decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, Sequence

from bot.live_native_decision_contract import ContractViolation, H1_MS


LIVE_NATIVE_REGIME_GATE_ENABLED_BY_DEFAULT = False
EMA_PERIOD = 200
FLAT_BAND = Decimal("0.02")
RegimeValue = Literal["below_band", "flat_down", "flat_up", "above_band"]


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ContractViolation("invalid_regime_decimal", field)
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ContractViolation("invalid_regime_decimal", field) from exc
    if not number.is_finite():
        raise ContractViolation("invalid_regime_decimal", field)
    return number


def _strict_int(value: object, field: str) -> int:
    if isinstance(value, bool) or isinstance(value, float):
        raise ContractViolation("invalid_regime_integer", field)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ContractViolation("invalid_regime_integer", field) from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise ContractViolation("invalid_regime_integer", field)
    return int(number)


def ema(values: Sequence[Decimal], period: int = EMA_PERIOD) -> Decimal:
    if period <= 1 or len(values) < period:
        raise ContractViolation("insufficient_regime_history")
    alpha = Decimal("2") / Decimal(period + 1)
    result = values[0]
    for value in values[1:]:
        result = value * alpha + result * (Decimal("1") - alpha)
    return result


@dataclass(frozen=True)
class ClosedH1RegimeEvidence:
    seed_start_ts_ms: int
    history_bars: int
    bar_start_ts_ms: int
    closed_h1_ts_ms: int
    observed_at_ms: int
    age_ms: int
    close: Decimal
    ema200: Decimal
    deviation: Decimal
    value: RegimeValue

    def allows(self, sleeve_id: str) -> bool:
        sleeve = str(sleeve_id or "").strip().upper()
        if sleeve == "ATT1":
            return self.value == "flat_down"
        if sleeve == "SBR1":
            return self.value == "flat_up"
        raise ContractViolation("unknown_regime_sleeve", sleeve)


class ClosedH1EMA200RegimeGate:
    """Stateful causal EMA gate with idempotent same-bar observation.

    A production scheduler may observe the same latest closed H1 candle more
    than once.  Re-observation must not advance the EMA twice.  New bars must
    be exactly contiguous; missing history therefore fails closed.
    """

    def __init__(self, period: int = EMA_PERIOD) -> None:
        if isinstance(period, bool) or not isinstance(period, int) or period <= 1:
            raise ContractViolation("invalid_regime_ema_period")
        self.period = period
        self._alpha = Decimal("2") / Decimal(period + 1)
        self._history_bars = 0
        self._seed_start_ts_ms: int | None = None
        self._last_start_ts_ms: int | None = None
        self._last_close: Decimal | None = None
        self._ema: Decimal | None = None

    def update(
        self,
        row: Sequence[object],
        *,
        observed_at_ms: object,
        max_age_ms: object,
    ) -> ClosedH1RegimeEvidence | None:
        if isinstance(row, (str, bytes)) or len(row) < 5:
            raise ContractViolation("invalid_regime_h1_row")
        start = _strict_int(row[0], "bar_start_ts_ms")
        close = _decimal(row[4], "close")
        observed = _strict_int(observed_at_ms, "observed_at_ms")
        max_age = _strict_int(max_age_ms, "max_age_ms")
        if start <= 0 or start % H1_MS != 0 or close <= 0:
            raise ContractViolation("invalid_regime_h1_row")
        if max_age <= 0:
            raise ContractViolation("nonpositive_regime_max_age")

        if self._last_start_ts_ms is None:
            self._seed_start_ts_ms = start
            self._last_start_ts_ms = start
            self._last_close = close
            self._ema = close
            self._history_bars = 1
        elif start == self._last_start_ts_ms:
            if close != self._last_close:
                raise ContractViolation("regime_same_bar_mutated")
        else:
            if start != self._last_start_ts_ms + H1_MS:
                raise ContractViolation("noncontiguous_regime_h1_rows")
            assert self._ema is not None
            self._ema = close * self._alpha + self._ema * (Decimal("1") - self._alpha)
            self._last_start_ts_ms = start
            self._last_close = close
            self._history_bars += 1

        close_ts = start + H1_MS
        age = observed - close_ts
        if age < 0:
            raise ContractViolation("regime_h1_bar_not_closed")
        if age > max_age:
            raise ContractViolation("regime_evidence_too_old")
        if self._history_bars < self.period:
            return None
        assert self._seed_start_ts_ms is not None and self._ema is not None
        deviation = (close - self._ema) / self._ema
        return ClosedH1RegimeEvidence(
            seed_start_ts_ms=self._seed_start_ts_ms,
            history_bars=self._history_bars,
            bar_start_ts_ms=start,
            closed_h1_ts_ms=close_ts,
            observed_at_ms=observed,
            age_ms=age,
            close=close,
            ema200=self._ema,
            deviation=deviation,
            value=classify_deviation(deviation),
        )


def classify_deviation(deviation: Decimal) -> RegimeValue:
    if deviation < -FLAT_BAND:
        return "below_band"
    if deviation < 0:
        return "flat_down"
    if deviation < FLAT_BAND:
        return "flat_up"
    return "above_band"


def closed_h1_btc_ema200_regime(
    rows: Sequence[Sequence[object]],
    *,
    observed_at_ms: object,
    max_age_ms: object,
) -> ClosedH1RegimeEvidence:
    if isinstance(rows, (str, bytes)) or len(rows) < EMA_PERIOD:
        raise ContractViolation("insufficient_regime_history")
    observed = _strict_int(observed_at_ms, "observed_at_ms")
    max_age = _strict_int(max_age_ms, "max_age_ms")
    gate = ClosedH1EMA200RegimeGate(EMA_PERIOD)
    evidence: ClosedH1RegimeEvidence | None = None
    for index, row in enumerate(rows):
        row_close_ts = _strict_int(row[0], "bar_start_ts_ms") + H1_MS
        row_observed = observed if index == len(rows) - 1 else row_close_ts
        evidence = gate.update(
            row,
            observed_at_ms=row_observed,
            max_age_ms=max_age if index == len(rows) - 1 else H1_MS,
        )
    if evidence is None:
        raise ContractViolation("insufficient_regime_history")
    return evidence


__all__ = [
    "ClosedH1RegimeEvidence",
    "ClosedH1EMA200RegimeGate",
    "EMA_PERIOD",
    "FLAT_BAND",
    "LIVE_NATIVE_REGIME_GATE_ENABLED_BY_DEFAULT",
    "classify_deviation",
    "closed_h1_btc_ema200_regime",
    "ema",
]
