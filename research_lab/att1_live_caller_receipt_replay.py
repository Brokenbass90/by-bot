"""Authority-free replay entrypoint for the production ATT1 receipt boundary.

This adapter deliberately contains no alternate receipt construction.  A
replay supplies the exact same live-shaped inputs and receives bytes produced
and verified by :mod:`bot.att1_live_caller_receipt`.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from bot.att1_live_caller_receipt import (
    build_att1_decision_receipt,
    receipt_jsonl_bytes,
)
from bot.persisted_btc_h1_regime import BTCRegimeReceipt
from strategies.signals import TradeSignal


REPLAY_MONEY_AUTHORITY = False
REPLAY_PROMOTION_AUTHORITY = False


def build_att1_replay_receipt(
    *,
    symbol: str,
    observed_at_ms: object,
    consumed_closed_rows: Sequence[Sequence[object]],
    signal: TradeSignal | None,
    no_signal_reason: str,
    runtime_contract: Mapping[str, object],
    source_files: Mapping[str, bytes],
    expected_source_hashes: Mapping[str, str],
    source_manifest_sha256: str,
    regime_required: bool = False,
    persisted_regime_receipt: BTCRegimeReceipt | None = None,
    caller_context: Mapping[str, object],
    max_decision_age_ms: object = 300_000,
    evaluation_error: Exception | None = None,
) -> dict[str, object]:
    """Call the shared pure boundary and independently verify its self hash."""

    receipt = build_att1_decision_receipt(
        symbol=symbol,
        observed_at_ms=observed_at_ms,
        consumed_closed_rows=consumed_closed_rows,
        signal=signal,
        no_signal_reason=no_signal_reason,
        runtime_contract=runtime_contract,
        source_files=source_files,
        expected_source_hashes=expected_source_hashes,
        source_manifest_sha256=source_manifest_sha256,
        regime_required=regime_required,
        persisted_regime_receipt=persisted_regime_receipt,
        max_decision_age_ms=max_decision_age_ms,
        caller_context=caller_context,
        evaluation_error=evaluation_error,
        error_stage="replay_strategy_evaluation",
    )
    receipt_jsonl_bytes(receipt)
    return receipt


__all__ = [
    "REPLAY_MONEY_AUTHORITY",
    "REPLAY_PROMOTION_AUTHORITY",
    "build_att1_replay_receipt",
]
