"""Default-off pure ATT1/SBR1 research/live parity-ledger emitters.

The two public emitters deliberately represent separate adapter boundaries.
They share only the immutable decision/fill contract and final row validation;
neither imports a runner, broker client, environment, strategy, or order path.
Producing equal rows is evidence about this fixture boundary only, never money
or promotion authority.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, Mapping

from bot.live_native_decision_contract import (
    ActualFill,
    ContractViolation,
    FillRebasePolicy,
    H1_MS,
    LiveNativeDecisionPlan,
    RebaseReceipt,
    rebase_targets_once,
    time_stop_deadline_ms,
    validate_fill_before_rebase,
)
from research_lab.adapter_parity import SCHEMA_ID, validate_normalized_row


LIVE_NATIVE_ADAPTER_EMITTERS_ENABLED_BY_DEFAULT = False

CooldownState = Literal["ready", "blocked"]


def _strict_int(value: object, field: str) -> int:
    if isinstance(value, bool) or isinstance(value, float):
        raise ContractViolation("invalid_integer", field)
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, str):
        try:
            number = Decimal(value.strip())
        except (InvalidOperation, AttributeError) as exc:
            raise ContractViolation("invalid_integer", field) from exc
    else:
        raise ContractViolation("invalid_integer", field)
    if not number.is_finite() or number != number.to_integral_value():
        raise ContractViolation("invalid_integer", field)
    return int(number)


def _decimal(value: Decimal | int | float | str, field: str) -> Decimal:
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ContractViolation("invalid_decimal", field) from exc
    if not number.is_finite():
        raise ContractViolation("non_finite_decimal", field)
    return number


def _decimal_text(value: Decimal | int | float | str, field: str) -> str:
    number = _decimal(value, field)
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


def _nonempty(value: str, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ContractViolation("missing_adapter_context_field", field)
    return result


def _sha256(value: str, field: str) -> str:
    result = str(value or "").strip()
    if re.fullmatch(r"[0-9a-f]{64}", result) is None:
        raise ContractViolation("invalid_sha256", field)
    return result


@dataclass(frozen=True)
class AdapterParityContext:
    """Outcome/cost/regime state that is outside the fill geometry contract."""

    cooldown_state: CooldownState
    cooldown_until_ts_ms: int | None
    regime_value: str
    regime_bar_ts_ms: int
    outcome: str
    net_r: Decimal
    exit_ts_ms: int
    cost_contract_hash: str

    def __post_init__(self) -> None:
        state = str(self.cooldown_state or "").strip().lower()
        if state not in {"ready", "blocked"}:
            raise ContractViolation("invalid_cooldown_state")
        object.__setattr__(self, "cooldown_state", state)
        if self.cooldown_until_ts_ms is None:
            until = None
        else:
            until = _strict_int(self.cooldown_until_ts_ms, "cooldown_until_ts_ms")
            if until <= 0:
                raise ContractViolation("invalid_cooldown_until_ts")
        object.__setattr__(self, "cooldown_until_ts_ms", until)
        if state == "ready" and until is not None:
            raise ContractViolation("ready_cooldown_has_deadline")
        if state == "blocked" and until is None:
            raise ContractViolation("blocked_cooldown_missing_deadline")

        object.__setattr__(self, "regime_value", _nonempty(self.regime_value, "regime_value"))
        regime_ts = _strict_int(self.regime_bar_ts_ms, "regime_bar_ts_ms")
        if regime_ts <= 0 or regime_ts % H1_MS != 0:
            raise ContractViolation("regime_bar_ts_not_closed_h1")
        object.__setattr__(self, "regime_bar_ts_ms", regime_ts)
        object.__setattr__(self, "outcome", _nonempty(self.outcome, "outcome"))
        object.__setattr__(self, "net_r", _decimal(self.net_r, "net_r"))
        exit_ts = _strict_int(self.exit_ts_ms, "exit_ts_ms")
        if exit_ts <= 0:
            raise ContractViolation("invalid_exit_ts")
        object.__setattr__(self, "exit_ts_ms", exit_ts)
        object.__setattr__(
            self,
            "cost_contract_hash",
            _sha256(self.cost_contract_hash, "cost_contract_hash"),
        )


def _validate_context(plan: LiveNativeDecisionPlan, context: AdapterParityContext) -> None:
    if not isinstance(context, AdapterParityContext):
        raise ContractViolation("invalid_adapter_parity_context")
    if context.regime_bar_ts_ms > plan.closed_h1_ts_ms:
        raise ContractViolation("regime_bar_after_decision")
    if (
        context.cooldown_state == "blocked"
        and context.cooldown_until_ts_ms is not None
        and context.cooldown_until_ts_ms <= plan.closed_h1_ts_ms
    ):
        raise ContractViolation("blocked_cooldown_deadline_not_future")
    if context.exit_ts_ms < plan.closed_h1_ts_ms:
        raise ContractViolation("exit_ts_before_decision")


def _cooldown_payload(context: AdapterParityContext) -> dict[str, object]:
    return {
        "state": context.cooldown_state,
        "until_ts_ms": context.cooldown_until_ts_ms,
    }


def _time_stop_payload(
    plan: LiveNativeDecisionPlan, execution_deadline_ms: int
) -> dict[str, object]:
    return {
        "anchor": "accepted_final_fill",
        "deadline_ms": execution_deadline_ms,
        "hours": plan.time_stop_hours,
    }


def _validated_row(row: dict[str, object]) -> dict[str, object]:
    try:
        validate_normalized_row(row)
    except ValueError as exc:
        raise ContractViolation("invalid_normalized_adapter_row", str(exc)) from exc
    return row


def emit_research_adapter_row(
    plan: LiveNativeDecisionPlan,
    final_fill: ActualFill,
    policy: FillRebasePolicy,
    context: AdapterParityContext,
    *,
    persisted_receipt: RebaseReceipt | Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Normalize the research boundary from frozen decision inputs."""

    _validate_context(plan, context)
    validation = validate_fill_before_rebase(plan, final_fill, policy)
    if not validation.accepted:
        raise ContractViolation(validation.code)
    execution = rebase_targets_once(
        plan,
        final_fill,
        policy,
        persisted_receipt=persisted_receipt,
    )
    receipt = execution.receipt
    row: dict[str, object] = {
        "schema_id": SCHEMA_ID,
        "release_or_promotion_authority": False,
        "adapter_emitters_default_off": True,
        "sleeve_id": plan.sleeve_id,
        "spec_id": plan.spec_id,
        "profile_id": plan.profile.profile_id,
        "profile_hash": plan.profile_hash,
        "symbol": plan.symbol,
        "bar_ts": plan.closed_h1_ts_ms,
        "side": plan.side,
        "signal_id": plan.decision_id,
        "decision_id": plan.decision_id,
        "entry": _decimal_text(final_fill.fill_price, "entry"),
        "sl": _decimal_text(plan.frozen_sl, "sl"),
        "tp1": _decimal_text(execution.rebased_tps[0], "tp1"),
        "tp2": _decimal_text(execution.rebased_tps[1], "tp2"),
        "tp_fracs": [_decimal_text(value, "tp_fracs") for value in plan.tp_fractions],
        "runner_fraction": _decimal_text(plan.residual_fraction, "runner_fraction"),
        "time_stop": _time_stop_payload(plan, time_stop_deadline_ms(execution)),
        "cooldown_state": _cooldown_payload(context),
        "regime_value": context.regime_value,
        "regime_bar_ts": context.regime_bar_ts_ms,
        "validator_drop_reason": "",
        "config_hash": plan.config_hash,
        "source_hash": plan.source_hash,
        "data_hash": plan.data_hash,
        "tick_size": _decimal_text(policy.tick_size, "tick_size"),
        "fill_id": final_fill.fill_id,
        "order_id": final_fill.order_id,
        "fill_lifecycle": final_fill.lifecycle,
        "fill_ts_ms": final_fill.fill_ts_ms,
        "fill_finalized_ts_ms": final_fill.finalized_ts_ms,
        "fill_age_ms": validation.fill_age_ms,
        "fill_finalization_delay_ms": validation.finalization_delay_ms,
        "exit_ts_ms": context.exit_ts_ms,
        "fill_fingerprint": final_fill.fill_fingerprint,
        "policy_fingerprint": policy.policy_fingerprint,
        "rebase_claim_key": receipt.claim_key,
        "rebase_receipt_id": receipt.receipt_id,
        "execution_fingerprint": receipt.execution_fingerprint,
        "frozen_decision": plan.decision_payload(),
        "final_fill": final_fill.fingerprint_payload(),
        "rebase_policy": policy.fingerprint_payload(),
        "rebase_receipt": receipt.to_dict(),
        "cost_contract_hash": context.cost_contract_hash,
        "outcome": context.outcome,
        "net_r": _decimal_text(context.net_r, "net_r"),
        "exception": None,
    }
    return _validated_row(row)


def emit_live_adapter_row(
    decision: LiveNativeDecisionPlan,
    broker_final_fill: ActualFill,
    execution_policy: FillRebasePolicy,
    observed_context: AdapterParityContext,
    *,
    persisted_receipt: RebaseReceipt | Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Normalize the separate live-shaped boundary without live wiring."""

    _validate_context(decision, observed_context)
    execution = rebase_targets_once(
        decision,
        broker_final_fill,
        execution_policy,
        persisted_receipt=persisted_receipt,
    )
    accepted = validate_fill_before_rebase(
        execution.source, execution.fill, execution.policy
    )
    if not accepted.accepted:
        raise ContractViolation(accepted.code)
    source = execution.source
    fill = execution.fill
    policy = execution.policy
    receipt = execution.receipt
    row: dict[str, object] = {
        "schema_id": SCHEMA_ID,
        "release_or_promotion_authority": False,
        "adapter_emitters_default_off": True,
        "sleeve_id": source.sleeve_id,
        "spec_id": source.spec_id,
        "profile_id": source.profile.profile_id,
        "profile_hash": source.profile_hash,
        "symbol": source.symbol,
        "bar_ts": source.closed_h1_ts_ms,
        "side": source.side,
        "signal_id": execution.decision_id,
        "decision_id": execution.decision_id,
        "entry": _decimal_text(execution.execution_entry, "entry"),
        "sl": _decimal_text(execution.frozen_sl, "sl"),
        "tp1": _decimal_text(execution.rebased_tps[0], "tp1"),
        "tp2": _decimal_text(execution.rebased_tps[1], "tp2"),
        "tp_fracs": [_decimal_text(value, "tp_fracs") for value in source.tp_fractions],
        "runner_fraction": _decimal_text(source.residual_fraction, "runner_fraction"),
        "time_stop": _time_stop_payload(source, time_stop_deadline_ms(execution)),
        "cooldown_state": _cooldown_payload(observed_context),
        "regime_value": observed_context.regime_value,
        "regime_bar_ts": observed_context.regime_bar_ts_ms,
        "validator_drop_reason": "",
        "config_hash": source.config_hash,
        "source_hash": source.source_hash,
        "data_hash": source.data_hash,
        "tick_size": _decimal_text(policy.tick_size, "tick_size"),
        "fill_id": fill.fill_id,
        "order_id": fill.order_id,
        "fill_lifecycle": fill.lifecycle,
        "fill_ts_ms": fill.fill_ts_ms,
        "fill_finalized_ts_ms": fill.finalized_ts_ms,
        "fill_age_ms": accepted.fill_age_ms,
        "fill_finalization_delay_ms": accepted.finalization_delay_ms,
        "exit_ts_ms": observed_context.exit_ts_ms,
        "fill_fingerprint": fill.fill_fingerprint,
        "policy_fingerprint": policy.policy_fingerprint,
        "rebase_claim_key": receipt.claim_key,
        "rebase_receipt_id": receipt.receipt_id,
        "execution_fingerprint": receipt.execution_fingerprint,
        "frozen_decision": source.decision_payload(),
        "final_fill": fill.fingerprint_payload(),
        "rebase_policy": policy.fingerprint_payload(),
        "rebase_receipt": receipt.to_dict(),
        "cost_contract_hash": observed_context.cost_contract_hash,
        "outcome": observed_context.outcome,
        "net_r": _decimal_text(observed_context.net_r, "net_r"),
        "exception": None,
    }
    return _validated_row(row)


def normalized_row_jsonl_bytes(row: dict[str, object]) -> bytes:
    """Serialize one already validated row into deterministic JSONL bytes."""

    _validated_row(row)
    try:
        return (
            json.dumps(
                row,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ContractViolation("noncanonical_adapter_row") from exc


__all__ = [
    "AdapterParityContext",
    "LIVE_NATIVE_ADAPTER_EMITTERS_ENABLED_BY_DEFAULT",
    "emit_live_adapter_row",
    "emit_research_adapter_row",
    "normalized_row_jsonl_bytes",
]
