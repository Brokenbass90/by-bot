"""Deterministic, zero-risk SBR1 random-control assignment capture.

This boundary freezes only paired sampled hours.  It does not read private
state, compute terminal results, change shadow slots, or advance any money
authority.  A later causal replay may classify each persisted assignment.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

from bot.sbr1_zero_risk_shadow import AppendOnlyShadowJournal, ShadowViolation


H1_MS = 3_600_000
CONTROL_AUTHORITY = "zero_risk_public_shadow_random_control_no_orders_no_money"
ASSIGNMENT_EVENT_TYPE = "control_assignment"
ASSIGNMENT_SCHEMA_ID = "sbr1_random_control_assignment_v1"
PREREG_RELATIVE_PATH = (
    "research_lab/prereg/PREREG_SBR1_SHADOW_RANDOM_CONTROL_2026_08_24.md"
)
_SHA256 = set("0123456789abcdef")


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ShadowViolation("noncanonical_control_payload") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _strict_ms(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise ShadowViolation(f"invalid_timestamp:{field}")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ShadowViolation(f"invalid_timestamp:{field}") from exc
    if result <= 0 or result % H1_MS != 0:
        raise ShadowViolation(f"invalid_timestamp:{field}")
    return result


def _validate_sha(value: object, field: str) -> str:
    result = str(value or "").strip().lower()
    if len(result) != 64 or any(char not in _SHA256 for char in result):
        raise ShadowViolation(f"invalid_sha256:{field}")
    return result


def calendar_month_bounds(ts_ms: object) -> tuple[int, int]:
    """Return [start, end) for the real UTC calendar month containing ts_ms."""

    if isinstance(ts_ms, bool):
        raise ShadowViolation("invalid_timestamp:calendar_timestamp")
    try:
        timestamp = int(ts_ms)
    except (TypeError, ValueError) as exc:
        raise ShadowViolation("invalid_timestamp:calendar_timestamp") from exc
    if timestamp <= 0:
        raise ShadowViolation("invalid_timestamp:calendar_timestamp")
    current = datetime.fromtimestamp(timestamp / 1000, timezone.utc)
    if current.month == 12:
        following = datetime(current.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        following = datetime(current.year, current.month + 1, 1, tzinfo=timezone.utc)
    start = datetime(current.year, current.month, 1, tzinfo=timezone.utc)
    return int(start.timestamp() * 1000), int(following.timestamp() * 1000)


def preregistration_sha256(path: Path) -> str:
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ShadowViolation("preregistration_unreadable") from exc
    return digest


def _sample_hour(
    *, prereg_sha256: str, main_decision_id: str, draw_index: int, collision_attempt: int, hour_count: int
) -> tuple[int, str]:
    key = f"{prereg_sha256}|{main_decision_id}|{draw_index}|{collision_attempt}".encode("ascii")
    digest = hashlib.sha256(key).hexdigest()
    return int(digest, 16) % hour_count, digest


def build_control_assignments(
    *,
    prereg_sha256: str,
    main_decision_id: str,
    main_decision_ts_ms: object,
    now_ms: object | None = None,
    eligible_hour: Callable[[int], bool | None] | None = None,
    required_count: int = 20,
    main_context: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    """Freeze deterministic sampled hours for one admitted main decision.

    ``eligible_hour`` is intentionally injectable: a future causal replay may
    reject a sampled hour with ``False``.  ``None`` means eligibility is not yet
    evaluated and is persisted as a replay obligation, never as a result.
    """

    prereg = _validate_sha(prereg_sha256, "prereg_sha256")
    decision_id = str(main_decision_id or "").strip()
    if not decision_id or "|" in decision_id:
        raise ShadowViolation("invalid_main_decision_id")
    context = dict(main_context or {})
    main_symbol = str(context.get("symbol") or "").strip().upper()
    main_side = str(context.get("side") or "").strip().lower()
    if main_symbol and main_side not in {"long", "short"}:
        raise ShadowViolation("invalid_main_side")
    geometry_sha = context.get("geometry_sha256")
    if geometry_sha is not None:
        geometry_sha = _validate_sha(geometry_sha, "geometry_sha256")
    source_sha = context.get("source_sha256")
    if source_sha is not None:
        source_sha = _validate_sha(source_sha, "source_sha256")
    data_sha = context.get("data_sha256")
    if data_sha is not None:
        data_sha = _validate_sha(data_sha, "data_sha256")
    config_sha = context.get("config_sha256")
    if config_sha is not None:
        config_sha = _validate_sha(config_sha, "config_sha256")
    cost_contract_sha = context.get("cost_contract_sha256")
    if cost_contract_sha is not None:
        cost_contract_sha = _validate_sha(
            cost_contract_sha, "cost_contract_sha256"
        )
    main_ts = _strict_ms(main_decision_ts_ms, "main_decision_ts_ms")
    if isinstance(required_count, bool) or not 1 <= int(required_count) <= 20:
        raise ShadowViolation("invalid_control_count")
    count = int(required_count)
    month_start, month_end = calendar_month_bounds(main_ts)
    hour_count = (month_end - month_start) // H1_MS
    main_hour = (main_ts // H1_MS) * H1_MS
    if now_ms is None:
        observed_now = 0
    else:
        observed_now = int(now_ms)
        if observed_now < 0:
            raise ShadowViolation("invalid_now_ms")

    assignments: list[dict[str, object]] = []
    sampled_hours: set[int] = set()
    draw_index = 0
    attempts = 0
    max_attempts = max(hour_count * 4, count * 20)
    while len(assignments) < count and attempts < max_attempts:
        collision_attempt = 0
        while True:
            offset, draw_hash = _sample_hour(
                prereg_sha256=prereg,
                main_decision_id=decision_id,
                draw_index=draw_index,
                collision_attempt=collision_attempt,
                hour_count=hour_count,
            )
            sampled = month_start + offset * H1_MS
            if sampled != main_hour and sampled not in sampled_hours:
                break
            collision_attempt += 1
            if collision_attempt >= hour_count:
                raise ShadowViolation("control_hour_collision_exhausted")
        draw_index += 1
        attempts += 1
        is_future = sampled + H1_MS > observed_now
        if eligible_hour is not None and not is_future:
            try:
                is_eligible = eligible_hour(sampled)
            except Exception as exc:
                raise ShadowViolation("causal_regime_check_failed") from exc
            if is_eligible is False:
                continue
        sampled_hours.add(sampled)
        lifecycle = "pending" if is_future else "ready_for_causal_replay"
        payload: dict[str, object] = {
            "schema_id": ASSIGNMENT_SCHEMA_ID,
            "authority": CONTROL_AUTHORITY,
            "main_decision_id": decision_id,
            "main_symbol": main_symbol or None,
            "main_side": main_side or None,
            "main_geometry_sha256": geometry_sha,
            "main_source_sha256": source_sha,
            "main_data_sha256": data_sha,
            "main_config_sha256": config_sha,
            "cost_contract_sha256": cost_contract_sha,
            "main_decision_hour_start_ms": main_hour,
            "prereg_sha256": prereg,
            "draw_index": draw_index - 1,
            "collision_attempt": collision_attempt,
            "draw_sha256": draw_hash,
            "month_start_ms": month_start,
            "month_end_exclusive_ms": month_end,
            "sampled_hour_start_ms": sampled,
            "sampled_hour_end_exclusive_ms": sampled + H1_MS,
            "lifecycle": lifecycle,
            "causal_regime_status": "pending",
            "evidence_universe_role": "smoke_not_final_n",
            "orders_allowed": False,
            "private_api_allowed": False,
            "money_authority": False,
        }
        payload["assignment_id"] = _sha(
            {key: value for key, value in payload.items() if key != "assignment_id"}
        )
        assignments.append(payload)
    if len(assignments) != count:
        raise ShadowViolation("insufficient_regime_eligible_hours")
    return assignments


def persist_control_assignments(
    journal: AppendOnlyShadowJournal,
    assignments: Sequence[Mapping[str, object]],
) -> int:
    """Append exactly one immutable event per assignment; replay is a no-op."""

    written = 0
    seen: set[tuple[str, int]] = set()
    for assignment in assignments:
        if not isinstance(assignment, Mapping):
            raise ShadowViolation("invalid_control_assignment")
        decision_id = str(assignment.get("main_decision_id") or "").strip()
        draw_index = assignment.get("draw_index")
        if isinstance(draw_index, bool) or not isinstance(draw_index, int):
            raise ShadowViolation("invalid_control_draw_index")
        key = (decision_id, draw_index)
        if not decision_id or key in seen:
            raise ShadowViolation("duplicate_control_assignment")
        seen.add(key)
        claim = f"control-assignment:{decision_id}:{draw_index}"
        if journal.append(ASSIGNMENT_EVENT_TYPE, claim, dict(assignment)):
            written += 1
    return written


def persist_controlled_admission(
    *,
    main_journal: AppendOnlyShadowJournal,
    main_claim: str,
    main_payload: Mapping[str, object],
    control_journal: AppendOnlyShadowJournal,
    assignments: Sequence[Mapping[str, object]],
) -> tuple[bool, int]:
    """Persist the control precommit before making an admission visible.

    A partial control-journal failure leaves no admitted main event.  Retrying
    is safe because assignment claims are deterministic and idempotent.
    """

    if main_payload.get("admitted") is not True:
        raise ShadowViolation("controlled_admission_requires_admitted_payload")
    if len(assignments) != 20:
        raise ShadowViolation("controlled_admission_requires_20_assignments")
    controls_written = persist_control_assignments(control_journal, assignments)
    main_written = main_journal.append("evaluation", main_claim, dict(main_payload))
    return main_written, controls_written


__all__ = [
    "ASSIGNMENT_EVENT_TYPE",
    "ASSIGNMENT_SCHEMA_ID",
    "CONTROL_AUTHORITY",
    "H1_MS",
    "PREREG_RELATIVE_PATH",
    "build_control_assignments",
    "calendar_month_bounds",
    "persist_control_assignments",
    "persist_controlled_admission",
    "preregistration_sha256",
]
