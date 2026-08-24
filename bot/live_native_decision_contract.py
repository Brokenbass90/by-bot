"""Pure, default-off ATT1/SBR1 decision-to-final-fill contract.

This module deliberately has no broker, environment, runner, storage, or order
imports. It does not grant trading or promotion authority. It only defines a
deterministic seam that future research and live adapters may both implement.

The contract freezes three different things:

* a decision fingerprint binds complete geometry and exact config, source, and
  data byte hashes;
* only a finalized, timely fill may rebuild targets around the unchanged stop;
* a deterministic receipt has one stable claim key per decision, so a caller
  can atomically create it and safely recover after a crash.

Persistence remains the caller's responsibility. The intended durable protocol
is ``INSERT receipt UNDER UNIQUE claim_key``. An existing byte-equal receipt is
an idempotent recovery; a different receipt under the same claim key is a hard
conflict. Nothing here is wired into live execution.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from typing import Literal, Mapping, Sequence


H1_MS = 3_600_000
LIVE_NATIVE_PARITY_ENABLED_BY_DEFAULT = False
DECISION_SCHEMA_ID = "live_native_decision_v2"
REBASE_RECEIPT_SCHEMA_ID = "live_native_rebase_receipt_v1"

Side = Literal["long", "short"]
TickDirection = Literal["up", "down"]


class ContractViolation(ValueError):
    """A fail-closed violation with a stable machine-readable code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = str(code)
        self.detail = str(detail)
        message = self.code if not self.detail else f"{self.code}: {self.detail}"
        super().__init__(message)


def _decimal(value: Decimal | int | float | str, field: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ContractViolation("invalid_decimal", field) from exc
    if not result.is_finite():
        raise ContractViolation("non_finite_decimal", field)
    return result


def _decimal_text(value: Decimal | int | float | str, field: str) -> str:
    number = _decimal(value, field)
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


def _decimal_tuple(
    values: Sequence[Decimal | int | float | str], field: str
) -> tuple[Decimal, ...]:
    if isinstance(values, (str, bytes)):
        raise ContractViolation("invalid_decimal_sequence", field)
    try:
        return tuple(_decimal(value, field) for value in values)
    except TypeError as exc:
        raise ContractViolation("invalid_decimal_sequence", field) from exc


def _strict_int(value: object, field: str) -> int:
    """Parse an integer without ever truncating a float or a fraction."""

    if isinstance(value, bool) or isinstance(value, float):
        raise ContractViolation("invalid_integer", field)
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ContractViolation("invalid_integer", field)
        try:
            number = Decimal(raw)
        except InvalidOperation as exc:
            raise ContractViolation("invalid_integer", field) from exc
    else:
        raise ContractViolation("invalid_integer", field)
    if not number.is_finite() or number != number.to_integral_value():
        raise ContractViolation("invalid_integer", field)
    return int(number)


def _nonempty(value: str, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ContractViolation("missing_identity_field", field)
    return result


def _side(value: str) -> Side:
    result = str(value or "").strip().lower()
    if result not in {"long", "short"}:
        raise ContractViolation("invalid_side", result)
    return result  # type: ignore[return-value]


def _sha256_hex(value: str, field: str) -> str:
    result = str(value or "").strip()
    if re.fullmatch(r"[0-9a-f]{64}", result) is None:
        raise ContractViolation("invalid_sha256", field)
    return result


def _closed_h1_ts_ms(value: object) -> int:
    ts = _strict_int(value, "closed_h1_ts_ms")
    if ts <= 0 or ts % H1_MS != 0:
        raise ContractViolation("closed_h1_ts_not_aligned")
    return ts


def _canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ContractViolation("noncanonical_fingerprint_payload") from exc


def _fingerprint(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True)
class FrozenSleeveProfile:
    """Exact selected live-native exit profile, expressed in H1 hours."""

    profile_id: str
    sleeve_id: str
    side: Side
    nominal_rrs: tuple[Decimal, ...]
    tp_fractions: tuple[Decimal, ...]
    residual_fraction: Decimal
    time_stop_hours: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", _nonempty(self.profile_id, "profile_id"))
        object.__setattr__(self, "sleeve_id", _nonempty(self.sleeve_id, "sleeve_id").upper())
        object.__setattr__(self, "side", _side(self.side))
        object.__setattr__(
            self, "nominal_rrs", _decimal_tuple(self.nominal_rrs, "nominal_rrs")
        )
        object.__setattr__(
            self, "tp_fractions", _decimal_tuple(self.tp_fractions, "tp_fractions")
        )
        object.__setattr__(
            self,
            "residual_fraction",
            _decimal(self.residual_fraction, "residual_fraction"),
        )
        hours = _strict_int(self.time_stop_hours, "time_stop_hours")
        object.__setattr__(self, "time_stop_hours", hours)

        if not self.nominal_rrs or any(value <= 0 for value in self.nominal_rrs):
            raise ContractViolation("invalid_profile_rrs")
        if any(left >= right for left, right in zip(self.nominal_rrs, self.nominal_rrs[1:])):
            raise ContractViolation("profile_rrs_not_strictly_ordered")
        if len(self.nominal_rrs) != len(self.tp_fractions):
            raise ContractViolation("profile_target_fraction_length_mismatch")
        if any(value <= 0 for value in self.tp_fractions):
            raise ContractViolation("invalid_profile_tp_fractions")
        if self.residual_fraction < 0 or self.residual_fraction >= 1:
            raise ContractViolation("invalid_profile_residual_fraction")
        if sum(self.tp_fractions, Decimal("0")) + self.residual_fraction != Decimal("1"):
            raise ContractViolation("profile_exit_fractions_do_not_sum_to_one")
        if hours <= 0:
            raise ContractViolation("invalid_profile_time_stop_hours")

    @property
    def profile_hash(self) -> str:
        return _fingerprint(
            {
                "nominal_rrs": [_decimal_text(value, "nominal_rrs") for value in self.nominal_rrs],
                "profile_id": self.profile_id,
                "residual_fraction": _decimal_text(
                    self.residual_fraction, "residual_fraction"
                ),
                "side": self.side,
                "sleeve_id": self.sleeve_id,
                "time_stop_hours": self.time_stop_hours,
                "tp_fractions": [
                    _decimal_text(value, "tp_fractions") for value in self.tp_fractions
                ],
            }
        )


# Exact selected profiles. They do not prove either real adapter implements the
# contract; adapter parity remains a separate evidence gate.
ATT1_FROZEN_PROFILE = FrozenSleeveProfile(
    profile_id="att1-wide-stop-live-native-v1",
    sleeve_id="ATT1",
    side="short",
    nominal_rrs=(Decimal("1.20"), Decimal("2.50")),
    tp_fractions=(Decimal("0.55"), Decimal("0.45")),
    residual_fraction=Decimal("0"),
    time_stop_hours=336,
)
SBR1_FROZEN_PROFILE = FrozenSleeveProfile(
    profile_id="sbr1-wide-stop-live-native-v1",
    sleeve_id="SBR1",
    side="long",
    nominal_rrs=(Decimal("1.10"), Decimal("2.60")),
    tp_fractions=(Decimal("0.50"), Decimal("0.30")),
    residual_fraction=Decimal("0.20"),
    time_stop_hours=168,
)
FROZEN_SLEEVE_PROFILES: Mapping[str, FrozenSleeveProfile] = {
    ATT1_FROZEN_PROFILE.sleeve_id: ATT1_FROZEN_PROFILE,
    SBR1_FROZEN_PROFILE.sleeve_id: SBR1_FROZEN_PROFILE,
}


def _profile_for_sleeve(sleeve_id: str) -> FrozenSleeveProfile:
    sleeve = _nonempty(sleeve_id, "sleeve_id").upper()
    try:
        return FROZEN_SLEEVE_PROFILES[sleeve]
    except KeyError as exc:
        raise ContractViolation("unsupported_sleeve", sleeve) from exc


def validate_residual_fraction(
    *,
    sleeve_id: str,
    tp_fractions: Sequence[Decimal | int | float | str],
    residual_fraction: Decimal | int | float | str,
) -> None:
    """Validate exact fractions, including the intentional SBR1 runner."""

    profile = _profile_for_sleeve(sleeve_id)
    fractions = _decimal_tuple(tp_fractions, "tp_fractions")
    residual = _decimal(residual_fraction, "residual_fraction")
    if not fractions or any(value <= 0 for value in fractions):
        raise ContractViolation("invalid_tp_fractions")
    if residual < 0 or residual >= 1:
        raise ContractViolation("invalid_residual_fraction")
    if sum(fractions, Decimal("0")) + residual != Decimal("1"):
        raise ContractViolation("exit_fractions_do_not_sum_to_one")
    if fractions != profile.tp_fractions:
        raise ContractViolation(
            "wrong_strategy_tp_fractions",
            f"{profile.sleeve_id} requires {profile.tp_fractions}",
        )
    if residual != profile.residual_fraction:
        raise ContractViolation(
            "wrong_strategy_residual",
            f"{profile.sleeve_id} requires {profile.residual_fraction}",
        )


@dataclass(frozen=True)
class LiveNativeDecisionPlan:
    """Immutable, evidence-bound geometry emitted on one closed H1 bar."""

    spec_id: str
    sleeve_id: str
    symbol: str
    side: Side
    closed_h1_ts_ms: int
    planned_entry: Decimal
    frozen_sl: Decimal
    planned_tps: tuple[Decimal, ...]
    tp_fractions: tuple[Decimal, ...]
    residual_fraction: Decimal
    time_stop_hours: int
    config_hash: str
    source_hash: str
    data_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "spec_id", _nonempty(self.spec_id, "spec_id"))
        object.__setattr__(self, "sleeve_id", _nonempty(self.sleeve_id, "sleeve_id").upper())
        object.__setattr__(self, "symbol", _nonempty(self.symbol, "symbol").upper())
        object.__setattr__(self, "side", _side(self.side))
        object.__setattr__(self, "closed_h1_ts_ms", _closed_h1_ts_ms(self.closed_h1_ts_ms))
        object.__setattr__(self, "planned_entry", _decimal(self.planned_entry, "planned_entry"))
        object.__setattr__(self, "frozen_sl", _decimal(self.frozen_sl, "frozen_sl"))
        object.__setattr__(self, "planned_tps", _decimal_tuple(self.planned_tps, "planned_tps"))
        object.__setattr__(
            self, "tp_fractions", _decimal_tuple(self.tp_fractions, "tp_fractions")
        )
        object.__setattr__(
            self,
            "residual_fraction",
            _decimal(self.residual_fraction, "residual_fraction"),
        )
        hours = _strict_int(self.time_stop_hours, "time_stop_hours")
        object.__setattr__(self, "time_stop_hours", hours)
        object.__setattr__(self, "config_hash", _sha256_hex(self.config_hash, "config_hash"))
        object.__setattr__(self, "source_hash", _sha256_hex(self.source_hash, "source_hash"))
        object.__setattr__(self, "data_hash", _sha256_hex(self.data_hash, "data_hash"))

        profile = _profile_for_sleeve(self.sleeve_id)
        if self.side != profile.side:
            raise ContractViolation("wrong_strategy_side", profile.sleeve_id)
        if self.time_stop_hours != profile.time_stop_hours:
            raise ContractViolation(
                "wrong_strategy_time_stop",
                f"{profile.sleeve_id} requires {profile.time_stop_hours}h",
            )
        if self.planned_entry <= 0 or self.frozen_sl <= 0:
            raise ContractViolation("nonpositive_geometry")
        if not self.planned_tps or len(self.planned_tps) != len(self.tp_fractions):
            raise ContractViolation("target_fraction_length_mismatch")
        if any(target <= 0 for target in self.planned_tps):
            raise ContractViolation("nonpositive_geometry")

        if self.side == "long":
            if not self.frozen_sl < self.planned_entry:
                raise ContractViolation("stop_on_wrong_side")
            if any(target <= self.planned_entry for target in self.planned_tps):
                raise ContractViolation("target_on_wrong_side")
            if any(left >= right for left, right in zip(self.planned_tps, self.planned_tps[1:])):
                raise ContractViolation("targets_not_strictly_ordered")
        else:
            if not self.frozen_sl > self.planned_entry:
                raise ContractViolation("stop_on_wrong_side")
            if any(target >= self.planned_entry for target in self.planned_tps):
                raise ContractViolation("target_on_wrong_side")
            if any(left <= right for left, right in zip(self.planned_tps, self.planned_tps[1:])):
                raise ContractViolation("targets_not_strictly_ordered")

        validate_residual_fraction(
            sleeve_id=self.sleeve_id,
            tp_fractions=self.tp_fractions,
            residual_fraction=self.residual_fraction,
        )
        if nominal_rrs(self) != profile.nominal_rrs:
            raise ContractViolation(
                "wrong_strategy_nominal_rrs",
                f"{profile.sleeve_id} requires {profile.nominal_rrs}",
            )

    @property
    def profile(self) -> FrozenSleeveProfile:
        return _profile_for_sleeve(self.sleeve_id)

    @property
    def profile_hash(self) -> str:
        return self.profile.profile_hash

    def decision_payload(self) -> dict[str, object]:
        return {
            "closed_h1_ts_ms": self.closed_h1_ts_ms,
            "config_hash": self.config_hash,
            "data_hash": self.data_hash,
            "frozen_sl": _decimal_text(self.frozen_sl, "frozen_sl"),
            "planned_entry": _decimal_text(self.planned_entry, "planned_entry"),
            "planned_tps": [_decimal_text(value, "planned_tps") for value in self.planned_tps],
            "profile_hash": self.profile_hash,
            "residual_fraction": _decimal_text(
                self.residual_fraction, "residual_fraction"
            ),
            "schema_id": DECISION_SCHEMA_ID,
            "side": self.side,
            "sleeve_id": self.sleeve_id,
            "source_hash": self.source_hash,
            "spec_id": self.spec_id,
            "symbol": self.symbol,
            "time_stop_hours": self.time_stop_hours,
            "tp_fractions": [
                _decimal_text(value, "tp_fractions") for value in self.tp_fractions
            ],
        }

    @property
    def decision_id(self) -> str:
        return decision_identity(self)


def decision_identity(plan: LiveNativeDecisionPlan) -> str:
    """Return a geometry/config/source/data-bound decision fingerprint."""

    if not isinstance(plan, LiveNativeDecisionPlan):
        raise ContractViolation("invalid_decision_plan")
    return _fingerprint(plan.decision_payload())


def nominal_rrs(plan: LiveNativeDecisionPlan) -> tuple[Decimal, ...]:
    """Extract decision-time target RRs around the frozen stop."""

    risk = abs(plan.planned_entry - plan.frozen_sl)
    if risk <= 0:
        raise ContractViolation("nonpositive_nominal_risk")
    if plan.side == "long":
        return tuple((target - plan.planned_entry) / risk for target in plan.planned_tps)
    return tuple((plan.planned_entry - target) / risk for target in plan.planned_tps)


@dataclass(frozen=True)
class ActualFill:
    """Final broker aggregate; provisional/working fills are invalid inputs."""

    decision_id: str
    order_id: str
    fill_id: str
    lifecycle: Literal["finalized"]
    fill_ts_ms: int
    finalized_ts_ms: int
    fill_price: Decimal
    cumulative_filled_qty: Decimal
    leaves_qty: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", _sha256_hex(self.decision_id, "decision_id"))
        object.__setattr__(self, "order_id", _nonempty(self.order_id, "order_id"))
        object.__setattr__(self, "fill_id", _nonempty(self.fill_id, "fill_id"))
        lifecycle = str(self.lifecycle or "").strip().lower()
        object.__setattr__(self, "lifecycle", lifecycle)
        if lifecycle != "finalized":
            raise ContractViolation("fill_not_finalized")
        fill_ts = _strict_int(self.fill_ts_ms, "fill_ts_ms")
        finalized_ts = _strict_int(self.finalized_ts_ms, "finalized_ts_ms")
        object.__setattr__(self, "fill_ts_ms", fill_ts)
        object.__setattr__(self, "finalized_ts_ms", finalized_ts)
        object.__setattr__(self, "fill_price", _decimal(self.fill_price, "fill_price"))
        object.__setattr__(
            self,
            "cumulative_filled_qty",
            _decimal(self.cumulative_filled_qty, "cumulative_filled_qty"),
        )
        object.__setattr__(self, "leaves_qty", _decimal(self.leaves_qty, "leaves_qty"))
        if fill_ts <= 0 or finalized_ts <= 0:
            raise ContractViolation("invalid_fill_ts")
        if finalized_ts < fill_ts:
            raise ContractViolation("finalized_before_fill")
        if self.fill_price <= 0:
            raise ContractViolation("nonpositive_fill_price")
        if self.cumulative_filled_qty <= 0:
            raise ContractViolation("nonpositive_filled_qty")
        if self.leaves_qty != 0:
            raise ContractViolation("finalized_fill_has_leaves")

    def fingerprint_payload(self) -> dict[str, object]:
        return {
            "cumulative_filled_qty": _decimal_text(
                self.cumulative_filled_qty, "cumulative_filled_qty"
            ),
            "decision_id": self.decision_id,
            "fill_id": self.fill_id,
            "fill_price": _decimal_text(self.fill_price, "fill_price"),
            "fill_ts_ms": self.fill_ts_ms,
            "finalized_ts_ms": self.finalized_ts_ms,
            "leaves_qty": _decimal_text(self.leaves_qty, "leaves_qty"),
            "lifecycle": self.lifecycle,
            "order_id": self.order_id,
        }

    @property
    def fill_fingerprint(self) -> str:
        return _fingerprint(self.fingerprint_payload())


@dataclass(frozen=True)
class FillRebasePolicy:
    """Explicit tick, risk-expansion, fill-age, and finalization contract."""

    spec_id: str
    profile_hash: str
    tick_size: Decimal
    max_adverse_risk_expansion: Decimal
    max_fill_age_ms: int
    max_finalize_delay_ms: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "spec_id", _nonempty(self.spec_id, "spec_id"))
        object.__setattr__(self, "profile_hash", _sha256_hex(self.profile_hash, "profile_hash"))
        object.__setattr__(self, "tick_size", _decimal(self.tick_size, "tick_size"))
        object.__setattr__(
            self,
            "max_adverse_risk_expansion",
            _decimal(self.max_adverse_risk_expansion, "max_adverse_risk_expansion"),
        )
        fill_age = _strict_int(self.max_fill_age_ms, "max_fill_age_ms")
        finalize_delay = _strict_int(self.max_finalize_delay_ms, "max_finalize_delay_ms")
        object.__setattr__(self, "max_fill_age_ms", fill_age)
        object.__setattr__(self, "max_finalize_delay_ms", finalize_delay)
        if self.tick_size <= 0:
            raise ContractViolation("nonpositive_tick_size")
        if self.max_adverse_risk_expansion < 0:
            raise ContractViolation("negative_adverse_risk_expansion")
        if fill_age <= 0:
            raise ContractViolation("nonpositive_max_fill_age")
        if finalize_delay < 0:
            raise ContractViolation("negative_max_finalize_delay")

    def fingerprint_payload(self) -> dict[str, object]:
        return {
            "max_adverse_risk_expansion": _decimal_text(
                self.max_adverse_risk_expansion, "max_adverse_risk_expansion"
            ),
            "max_fill_age_ms": self.max_fill_age_ms,
            "max_finalize_delay_ms": self.max_finalize_delay_ms,
            "profile_hash": self.profile_hash,
            "spec_id": self.spec_id,
            "tick_size": _decimal_text(self.tick_size, "tick_size"),
        }

    @property
    def policy_fingerprint(self) -> str:
        return _fingerprint(self.fingerprint_payload())


@dataclass(frozen=True)
class FillValidation:
    accepted: bool
    code: str
    nominal_risk: Decimal
    fill_risk: Decimal
    adverse_risk_expansion: Decimal
    favorable_fill: bool
    fill_age_ms: int
    finalization_delay_ms: int


def round_price_to_tick(
    price: Decimal | int | float | str,
    tick_size: Decimal | int | float | str,
    *,
    direction: TickDirection,
) -> Decimal:
    """Round a positive raw price deterministically in one direction."""

    value = _decimal(price, "price")
    tick = _decimal(tick_size, "tick_size")
    if value <= 0 or tick <= 0:
        raise ContractViolation("nonpositive_tick_rounding_input")
    normalized_direction = str(direction or "").strip().lower()
    if normalized_direction == "up":
        units = (value / tick).to_integral_value(rounding=ROUND_CEILING)
    elif normalized_direction == "down":
        units = (value / tick).to_integral_value(rounding=ROUND_FLOOR)
    else:
        raise ContractViolation("invalid_tick_direction", normalized_direction)
    return units * tick


def apply_exchange_stop_filter(
    plan: LiveNativeDecisionPlan,
    tick_size: Decimal | int | float | str,
) -> LiveNativeDecisionPlan:
    """Return the desired live decision with an exchange-native frozen stop.

    Market entries are not submitted with a limit price and their weighted
    average fill can legitimately be off tick.  The protective stop *is* an
    exchange price, so it is rounded away from entry exactly like the current
    production helper: down for a long and up for a short.  Planned targets are
    then rebuilt at the frozen nominal R multiples; accepted-fill targets are
    rounded separately by :func:`rebase_targets_once`.
    """

    if not isinstance(plan, LiveNativeDecisionPlan):
        raise ContractViolation("invalid_decision_plan")
    direction: TickDirection = "down" if plan.side == "long" else "up"
    stop = round_price_to_tick(plan.frozen_sl, tick_size, direction=direction)
    risk = abs(plan.planned_entry - stop)
    if risk <= 0:
        raise ContractViolation("stop_collapsed_after_tick_rounding")
    rrs = plan.profile.nominal_rrs
    if plan.side == "long":
        targets = tuple(plan.planned_entry + rr * risk for rr in rrs)
    else:
        targets = tuple(plan.planned_entry - rr * risk for rr in rrs)
    return LiveNativeDecisionPlan(
        spec_id=plan.spec_id,
        sleeve_id=plan.sleeve_id,
        symbol=plan.symbol,
        side=plan.side,
        closed_h1_ts_ms=plan.closed_h1_ts_ms,
        planned_entry=plan.planned_entry,
        frozen_sl=stop,
        planned_tps=targets,
        tp_fractions=plan.tp_fractions,
        residual_fraction=plan.residual_fraction,
        time_stop_hours=plan.time_stop_hours,
        config_hash=plan.config_hash,
        source_hash=plan.source_hash,
        data_hash=plan.data_hash,
    )


def validate_fill_before_rebase(
    plan: LiveNativeDecisionPlan,
    fill: ActualFill,
    policy: FillRebasePolicy,
) -> FillValidation:
    """Fail closed unless a final fill is fresh and preserves bounded risk."""

    if not isinstance(plan, LiveNativeDecisionPlan):
        raise ContractViolation("invalid_decision_plan")
    if not isinstance(fill, ActualFill):
        raise ContractViolation("invalid_final_fill")
    if not isinstance(policy, FillRebasePolicy):
        raise ContractViolation("invalid_rebase_policy")

    nominal_risk = abs(plan.planned_entry - plan.frozen_sl)
    empty = Decimal("0")
    fill_age = fill.fill_ts_ms - plan.closed_h1_ts_ms
    finalize_delay = fill.finalized_ts_ms - fill.fill_ts_ms

    def rejected(code: str, *, favorable: bool = False) -> FillValidation:
        return FillValidation(
            False,
            code,
            nominal_risk,
            empty,
            empty,
            favorable,
            fill_age,
            finalize_delay,
        )

    if policy.spec_id != plan.spec_id:
        return rejected("spec_mismatch")
    if policy.profile_hash != plan.profile_hash:
        return rejected("profile_mismatch")
    if fill.decision_id != plan.decision_id:
        return rejected("decision_mismatch")
    if fill_age < 0:
        return rejected("fill_before_closed_h1")
    if fill_age > policy.max_fill_age_ms:
        return rejected("fill_too_old")
    if finalize_delay > policy.max_finalize_delay_ms:
        return rejected("fill_finalization_too_slow")

    fill_risk = abs(fill.fill_price - plan.frozen_sl)
    if plan.side == "long":
        favorable = fill.fill_price < plan.planned_entry
        if fill.fill_price <= plan.frozen_sl:
            code = "gap_through_stop"
        elif fill.fill_price >= plan.planned_tps[0]:
            code = "original_tp_already_crossed"
        else:
            code = ""
    else:
        favorable = fill.fill_price > plan.planned_entry
        if fill.fill_price >= plan.frozen_sl:
            code = "gap_through_stop"
        elif fill.fill_price <= plan.planned_tps[0]:
            code = "original_tp_already_crossed"
        else:
            code = ""
    if code:
        return FillValidation(
            False,
            code,
            nominal_risk,
            fill_risk,
            empty,
            favorable,
            fill_age,
            finalize_delay,
        )

    expansion = max(empty, (fill_risk / nominal_risk) - Decimal("1"))
    if expansion > policy.max_adverse_risk_expansion:
        return FillValidation(
            False,
            "adverse_risk_expansion_exceeded",
            nominal_risk,
            fill_risk,
            expansion,
            favorable,
            fill_age,
            finalize_delay,
        )
    return FillValidation(
        True,
        "accepted",
        nominal_risk,
        fill_risk,
        expansion,
        favorable,
        fill_age,
        finalize_delay,
    )


def _rebased_targets(
    plan: LiveNativeDecisionPlan,
    fill: ActualFill,
    policy: FillRebasePolicy,
) -> tuple[tuple[Decimal, ...], tuple[Decimal, ...], FillValidation]:
    validation = validate_fill_before_rebase(plan, fill, policy)
    if not validation.accepted:
        raise ContractViolation(validation.code)
    rrs = nominal_rrs(plan)
    if plan.side == "long":
        raw_targets = tuple(fill.fill_price + rr * validation.fill_risk for rr in rrs)
        direction: TickDirection = "up"
    else:
        raw_targets = tuple(fill.fill_price - rr * validation.fill_risk for rr in rrs)
        direction = "down"
    if any(target <= 0 for target in raw_targets):
        raise ContractViolation("target_nonpositive_after_rebase")
    targets = tuple(
        round_price_to_tick(target, policy.tick_size, direction=direction)
        for target in raw_targets
    )
    if any(target <= 0 for target in targets):
        raise ContractViolation("target_nonpositive_after_tick_rounding")
    if plan.side == "long":
        valid = all(target > fill.fill_price for target in targets) and all(
            left < right for left, right in zip(targets, targets[1:])
        )
    else:
        valid = all(target < fill.fill_price for target in targets) and all(
            left > right for left, right in zip(targets, targets[1:])
        )
    if not valid:
        raise ContractViolation("target_ladder_collapsed_after_tick_rounding")
    return rrs, targets, validation


def _time_stop_deadline(source: LiveNativeDecisionPlan, fill: ActualFill) -> int:
    return fill.fill_ts_ms + source.time_stop_hours * H1_MS


def _execution_fingerprint(
    source: LiveNativeDecisionPlan,
    fill: ActualFill,
    policy: FillRebasePolicy,
    targets: tuple[Decimal, ...],
) -> str:
    return _fingerprint(
        {
            "decision_id": source.decision_id,
            "execution_entry": _decimal_text(fill.fill_price, "fill_price"),
            "fill_fingerprint": fill.fill_fingerprint,
            "frozen_sl": _decimal_text(source.frozen_sl, "frozen_sl"),
            "policy_fingerprint": policy.policy_fingerprint,
            "rebased_tps": [_decimal_text(value, "rebased_tps") for value in targets],
            "residual_fraction": _decimal_text(
                source.residual_fraction, "residual_fraction"
            ),
            "time_stop_deadline_ms": _time_stop_deadline(source, fill),
            "tp_fractions": [
                _decimal_text(value, "tp_fractions") for value in source.tp_fractions
            ],
        }
    )


@dataclass(frozen=True)
class RebaseReceipt:
    """Deterministic durable claim value; use ``claim_key`` as a unique key."""

    schema_id: str
    claim_key: str
    decision_id: str
    order_id: str
    fill_id: str
    fill_fingerprint: str
    policy_fingerprint: str
    execution_fingerprint: str
    receipt_id: str

    _FIELDS = frozenset(
        {
            "schema_id",
            "claim_key",
            "decision_id",
            "order_id",
            "fill_id",
            "fill_fingerprint",
            "policy_fingerprint",
            "execution_fingerprint",
            "receipt_id",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_id != REBASE_RECEIPT_SCHEMA_ID:
            raise ContractViolation("wrong_rebase_receipt_schema")
        object.__setattr__(self, "decision_id", _sha256_hex(self.decision_id, "decision_id"))
        object.__setattr__(self, "order_id", _nonempty(self.order_id, "order_id"))
        object.__setattr__(self, "fill_id", _nonempty(self.fill_id, "fill_id"))
        object.__setattr__(
            self,
            "fill_fingerprint",
            _sha256_hex(self.fill_fingerprint, "fill_fingerprint"),
        )
        object.__setattr__(
            self,
            "policy_fingerprint",
            _sha256_hex(self.policy_fingerprint, "policy_fingerprint"),
        )
        object.__setattr__(
            self,
            "execution_fingerprint",
            _sha256_hex(self.execution_fingerprint, "execution_fingerprint"),
        )
        object.__setattr__(self, "receipt_id", _sha256_hex(self.receipt_id, "receipt_id"))
        expected_claim_key = f"{REBASE_RECEIPT_SCHEMA_ID}:{self.decision_id}"
        if self.claim_key != expected_claim_key:
            raise ContractViolation("wrong_rebase_claim_key")
        if self.receipt_id != _fingerprint(self._unsigned_payload()):
            raise ContractViolation("rebase_receipt_checksum_mismatch")

    def _unsigned_payload(self) -> dict[str, str]:
        return {
            "claim_key": self.claim_key,
            "decision_id": self.decision_id,
            "execution_fingerprint": self.execution_fingerprint,
            "fill_fingerprint": self.fill_fingerprint,
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "policy_fingerprint": self.policy_fingerprint,
            "schema_id": self.schema_id,
        }

    def to_dict(self) -> dict[str, str]:
        return {**self._unsigned_payload(), "receipt_id": self.receipt_id}

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "RebaseReceipt":
        if not isinstance(value, Mapping) or set(value) != cls._FIELDS:
            raise ContractViolation("rebase_receipt_schema_fields_mismatch")
        return cls(
            schema_id=str(value["schema_id"]),
            claim_key=str(value["claim_key"]),
            decision_id=str(value["decision_id"]),
            order_id=str(value["order_id"]),
            fill_id=str(value["fill_id"]),
            fill_fingerprint=str(value["fill_fingerprint"]),
            policy_fingerprint=str(value["policy_fingerprint"]),
            execution_fingerprint=str(value["execution_fingerprint"]),
            receipt_id=str(value["receipt_id"]),
        )


def _build_receipt(
    source: LiveNativeDecisionPlan,
    fill: ActualFill,
    policy: FillRebasePolicy,
    targets: tuple[Decimal, ...],
) -> RebaseReceipt:
    unsigned = {
        "claim_key": f"{REBASE_RECEIPT_SCHEMA_ID}:{source.decision_id}",
        "decision_id": source.decision_id,
        "execution_fingerprint": _execution_fingerprint(source, fill, policy, targets),
        "fill_fingerprint": fill.fill_fingerprint,
        "fill_id": fill.fill_id,
        "order_id": fill.order_id,
        "policy_fingerprint": policy.policy_fingerprint,
        "schema_id": REBASE_RECEIPT_SCHEMA_ID,
    }
    return RebaseReceipt(**unsigned, receipt_id=_fingerprint(unsigned))


@dataclass(frozen=True)
class RebasedExecutionPlan:
    """Immutable execution geometry proven by one accepted final-fill receipt."""

    source: LiveNativeDecisionPlan
    fill: ActualFill
    policy: FillRebasePolicy
    nominal_rrs: tuple[Decimal, ...]
    rebased_tps: tuple[Decimal, ...]
    receipt: RebaseReceipt

    def __post_init__(self) -> None:
        if not isinstance(self.source, LiveNativeDecisionPlan):
            raise ContractViolation("invalid_rebase_source")
        if not isinstance(self.fill, ActualFill) or not isinstance(self.policy, FillRebasePolicy):
            raise ContractViolation("invalid_rebase_inputs")
        if not isinstance(self.receipt, RebaseReceipt):
            raise ContractViolation("invalid_rebase_receipt")
        object.__setattr__(
            self, "nominal_rrs", _decimal_tuple(self.nominal_rrs, "nominal_rrs")
        )
        object.__setattr__(
            self, "rebased_tps", _decimal_tuple(self.rebased_tps, "rebased_tps")
        )
        expected_rrs, expected_targets, _ = _rebased_targets(
            self.source, self.fill, self.policy
        )
        if self.nominal_rrs != expected_rrs:
            raise ContractViolation("nominal_rrs_changed_during_rebase")
        if self.rebased_tps != expected_targets:
            raise ContractViolation("rebased_targets_do_not_match_contract")
        if self.receipt != _build_receipt(
            self.source, self.fill, self.policy, expected_targets
        ):
            raise ContractViolation("rebase_receipt_does_not_match_execution")

    @property
    def decision_id(self) -> str:
        return self.source.decision_id

    @property
    def frozen_sl(self) -> Decimal:
        return self.source.frozen_sl

    @property
    def execution_entry(self) -> Decimal:
        return self.fill.fill_price

    @property
    def rebase_applied(self) -> bool:
        return True


def _coerce_receipt(
    value: RebaseReceipt | Mapping[str, object] | None,
) -> RebaseReceipt | None:
    if value is None or isinstance(value, RebaseReceipt):
        return value
    return RebaseReceipt.from_dict(value)


def rebase_targets_once(
    plan: LiveNativeDecisionPlan | RebasedExecutionPlan,
    fill: ActualFill,
    policy: FillRebasePolicy,
    *,
    persisted_receipt: RebaseReceipt | Mapping[str, object] | None = None,
) -> RebasedExecutionPlan:
    """Create/recover the one deterministic rebase for a decision.

    ``receipt.claim_key`` is invariant for the decision, while ``receipt_id``
    binds the exact final fill, policy, and output. Pass a receipt read from
    durable storage during recovery. A mismatch fails closed rather than
    silently applying a second rebase.
    """

    durable = _coerce_receipt(persisted_receipt)
    if isinstance(plan, RebasedExecutionPlan):
        if plan.fill != fill or plan.policy != policy:
            raise ContractViolation("rebase_already_applied")
        if durable is not None and durable != plan.receipt:
            raise ContractViolation("rebase_claim_conflict")
        return plan
    if not isinstance(plan, LiveNativeDecisionPlan):
        raise ContractViolation("invalid_rebase_source")
    rrs, targets, _ = _rebased_targets(plan, fill, policy)
    expected_receipt = _build_receipt(plan, fill, policy, targets)
    if durable is not None and durable != expected_receipt:
        if durable.claim_key == expected_receipt.claim_key:
            raise ContractViolation("rebase_claim_conflict")
        raise ContractViolation("persisted_receipt_for_wrong_decision")
    return RebasedExecutionPlan(
        source=plan,
        fill=fill,
        policy=policy,
        nominal_rrs=rrs,
        rebased_tps=targets,
        receipt=expected_receipt,
    )


def time_stop_deadline_ms(plan: RebasedExecutionPlan) -> int:
    """Return the deadline only from an accepted and receipt-bound rebase."""

    if not isinstance(plan, RebasedExecutionPlan):
        raise ContractViolation("time_stop_requires_accepted_rebase")
    return _time_stop_deadline(plan.source, plan.fill)


__all__ = [
    "ATT1_FROZEN_PROFILE",
    "ActualFill",
    "ContractViolation",
    "DECISION_SCHEMA_ID",
    "FROZEN_SLEEVE_PROFILES",
    "FillRebasePolicy",
    "FillValidation",
    "FrozenSleeveProfile",
    "H1_MS",
    "LIVE_NATIVE_PARITY_ENABLED_BY_DEFAULT",
    "LiveNativeDecisionPlan",
    "REBASE_RECEIPT_SCHEMA_ID",
    "RebaseReceipt",
    "RebasedExecutionPlan",
    "SBR1_FROZEN_PROFILE",
    "decision_identity",
    "apply_exchange_stop_filter",
    "nominal_rrs",
    "rebase_targets_once",
    "round_price_to_tick",
    "time_stop_deadline_ms",
    "validate_fill_before_rebase",
    "validate_residual_fraction",
]
