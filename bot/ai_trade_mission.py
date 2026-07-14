"""Research-only one-shot AI trade missions with fail-closed persistence.

The module deliberately has no broker, network, Telegram, allocator, or live
router imports.  A screener freezes deterministic candidate cards; an AI is
then allowed to return exactly ``SELECT <card_id>`` or ``ABSTAIN``.  It cannot
invent or alter a symbol, side, entry, stop, or target.

Every mission is physically ``shadow`` only.  A selected card is bound to the
mission by a deterministic plan hash/token and may be consumed once, at the
first execution-grid open strictly after both the closed snapshot and
validation.  The resulting shadow receipt is immutable and content-addressed.

The JSON store is intended for a local control-plane process.  It combines a
process lock, an atomic 0600 replace, a payload checksum, append-only replay
ledgers, and explicit FSM transition validation.  Corrupt state is never
silently reset.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import uuid
from dataclasses import asdict, dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional, Sequence, Tuple, TypeVar


SHADOW_MODE = "shadow"
STATE_SCHEMA = "ai_trade_mission_shadow_state"
STATE_VERSION = 1
PLAN_SCHEMA = "ai_trade_mission_shadow_plan_v1"
RECEIPT_SCHEMA = "ai_trade_mission_shadow_receipt_v1"
MAX_STATE_BYTES = 8 * 1024 * 1024
RESEARCH_ONLY = True
LIVE_READY = False
BROKER_CALLS = False
NETWORK_CALLS = False

_MISSION_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_HEX_32 = re.compile(r"^[0-9a-f]{32}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_TERMINAL_REASONS = re.compile(r"^[A-Za-z0-9_.:/ -]{1,128}$")


class MissionError(ValueError):
    """A mission operation would weaken the research-only contract."""


class MissionPersistenceError(RuntimeError):
    """Mission state is unsafe, corrupt, or could not be committed."""


class MissionStatus(str, Enum):
    REQUESTED = "REQUESTED"
    SNAPSHOT_FROZEN = "SNAPSHOT_FROZEN"
    AI_PROPOSED = "AI_PROPOSED"
    VALIDATED = "VALIDATED"
    SHADOW_OPEN = "SHADOW_OPEN"
    SHADOW_CLOSED = "SHADOW_CLOSED"
    ABSTAIN = "ABSTAIN"
    CANCELLED = "CANCELLED"


TERMINAL_STATUSES = frozenset(
    {MissionStatus.SHADOW_CLOSED, MissionStatus.ABSTAIN, MissionStatus.CANCELLED}
)
_ALLOWED_TRANSITIONS = {
    MissionStatus.REQUESTED: {MissionStatus.SNAPSHOT_FROZEN, MissionStatus.CANCELLED},
    MissionStatus.SNAPSHOT_FROZEN: {MissionStatus.AI_PROPOSED, MissionStatus.CANCELLED},
    MissionStatus.AI_PROPOSED: {
        MissionStatus.VALIDATED,
        MissionStatus.ABSTAIN,
        MissionStatus.CANCELLED,
    },
    MissionStatus.VALIDATED: {MissionStatus.SHADOW_OPEN, MissionStatus.CANCELLED},
    MissionStatus.SHADOW_OPEN: {MissionStatus.SHADOW_CLOSED},
}


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MissionError(f"value is not canonical JSON: {exc}") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _exact_ms(value: object, name: str, *, allow_zero: bool = False) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise MissionError(f"{name} must be an exact integer timestamp")
    if value < 0 or (value == 0 and not allow_zero):
        raise MissionError(f"{name} must be positive")
    return value


def _positive(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise MissionError(f"{name} must be finite and positive")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MissionError(f"{name} must be finite and positive") from exc
    if not math.isfinite(number) or number <= 0.0:
        raise MissionError(f"{name} must be finite and positive")
    return number


def _bounded_bps(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise MissionError(f"{name} must be finite in [0, 1000]")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MissionError(f"{name} must be finite in [0, 1000]") from exc
    if not math.isfinite(number) or number < 0.0 or number > 1000.0:
        raise MissionError(f"{name} must be finite in [0, 1000]")
    return number


def _expect_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MissionPersistenceError(f"{name} must be an object")
    return value


def _expect_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise MissionPersistenceError(f"{name} keys mismatch")


def _reason(value: object) -> str:
    text = str(value or "")
    if text != text.strip() or not _TERMINAL_REASONS.fullmatch(text):
        raise MissionError("reason must be a short canonical string")
    return text


def _mission_id(value: object) -> str:
    text = str(value or "")
    if text != text.strip() or not _MISSION_ID.fullmatch(text):
        raise MissionError("mission_id must contain only canonical identifier characters")
    return text


def _symbol(value: object) -> str:
    text = str(value or "")
    if not text or text != text.strip() or text != text.upper():
        raise MissionError("symbol must be canonical uppercase")
    if len(text) > 32 or not all(char.isalnum() or char in "._:-" for char in text):
        raise MissionError("symbol contains unsupported characters")
    return text


def _strict_tuple_strings(value: object, name: str) -> Tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise MissionPersistenceError(f"{name} must be a string array")
    items = tuple(value)
    if len(items) != len(set(items)):
        raise MissionPersistenceError(f"{name} contains duplicates")
    return items


@dataclass(frozen=True)
class CandidateCard:
    """A deterministic, immutable setup produced by a non-AI screener."""

    card_id: str
    symbol: str
    side: str
    closed_at_ms: int
    entry: float
    sl: float
    tp: float
    snapshot_hash: str

    def __post_init__(self) -> None:
        _symbol(self.symbol)
        if self.side not in {"long", "short"}:
            raise MissionError("candidate side must be long or short")
        _exact_ms(self.closed_at_ms, "closed_at_ms")
        entry = _positive(self.entry, "entry")
        sl = _positive(self.sl, "sl")
        tp = _positive(self.tp, "tp")
        if self.side == "long" and not sl < entry < tp:
            raise MissionError("long card geometry must be sl < entry < tp")
        if self.side == "short" and not tp < entry < sl:
            raise MissionError("short card geometry must be tp < entry < sl")
        if not _HEX_64.fullmatch(str(self.snapshot_hash or "")):
            raise MissionError("snapshot_hash must be lowercase SHA256")
        expected = _sha256(self.payload())[:32]
        if self.card_id != expected:
            raise MissionError("card_id does not bind the complete candidate card")

    def payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "closed_at_ms": self.closed_at_ms,
            "entry": self.entry,
            "sl": self.sl,
            "tp": self.tp,
            "snapshot_hash": self.snapshot_hash,
        }

    @property
    def reward_risk(self) -> float:
        return abs(self.tp - self.entry) / abs(self.entry - self.sl)

    @classmethod
    def build(
        cls,
        *,
        symbol: str,
        side: str,
        closed_at_ms: int,
        entry: float,
        sl: float,
        tp: float,
        snapshot_hash: str,
    ) -> "CandidateCard":
        values = {
            "symbol": _symbol(symbol),
            "side": str(side),
            "closed_at_ms": _exact_ms(closed_at_ms, "closed_at_ms"),
            "entry": _positive(entry, "entry"),
            "sl": _positive(sl, "sl"),
            "tp": _positive(tp, "tp"),
            "snapshot_hash": str(snapshot_hash),
        }
        return cls(card_id=_sha256(values)[:32], **values)


def candidate_from_input(raw: object) -> CandidateCard:
    """Build a card from a strict screener payload; extra fields are rejected."""
    obj = _expect_mapping(raw, "candidate")
    expected = {"symbol", "side", "closed_at_ms", "entry", "sl", "tp", "snapshot_hash"}
    if set(obj) != expected:
        raise MissionError("candidate input keys mismatch")
    return CandidateCard.build(**dict(obj))


@dataclass(frozen=True)
class MissionPolicy:
    allowlist: Tuple[str, ...]
    freshness_ms: int
    min_rr: float
    execution_interval_ms: int
    fee_bps_per_side: float
    slippage_bps_per_side: float

    def __post_init__(self) -> None:
        if not self.allowlist or tuple(sorted(set(self.allowlist))) != self.allowlist:
            raise MissionError("allowlist must be non-empty, unique, and sorted")
        for symbol in self.allowlist:
            _symbol(symbol)
        _exact_ms(self.freshness_ms, "freshness_ms")
        _exact_ms(self.execution_interval_ms, "execution_interval_ms")
        rr = _positive(self.min_rr, "min_rr")
        if rr < 1.0 or rr > 20.0:
            raise MissionError("min_rr must be in [1, 20]")
        _bounded_bps(self.fee_bps_per_side, "fee_bps_per_side")
        _bounded_bps(self.slippage_bps_per_side, "slippage_bps_per_side")

    @classmethod
    def build(
        cls,
        *,
        allowlist: Sequence[str],
        freshness_ms: int,
        min_rr: float,
        execution_interval_ms: int,
        fee_bps_per_side: float,
        slippage_bps_per_side: float,
    ) -> "MissionPolicy":
        canonical = tuple(sorted({_symbol(item) for item in allowlist}))
        return cls(
            allowlist=canonical,
            freshness_ms=_exact_ms(freshness_ms, "freshness_ms"),
            min_rr=_positive(min_rr, "min_rr"),
            execution_interval_ms=_exact_ms(execution_interval_ms, "execution_interval_ms"),
            fee_bps_per_side=_bounded_bps(fee_bps_per_side, "fee_bps_per_side"),
            slippage_bps_per_side=_bounded_bps(
                slippage_bps_per_side, "slippage_bps_per_side"
            ),
        )


@dataclass(frozen=True)
class AIDecision:
    """The entire AI authority surface: select an existing card or abstain."""

    action: str
    card_id: Optional[str]
    decision_id: str

    def __post_init__(self) -> None:
        if self.action not in {"SELECT", "ABSTAIN"}:
            raise MissionError("AI action must be SELECT or ABSTAIN")
        if self.action == "SELECT":
            if self.card_id is None or not _HEX_32.fullmatch(self.card_id):
                raise MissionError("SELECT requires one canonical card_id")
        elif self.card_id is not None:
            raise MissionError("ABSTAIN cannot name a card")
        expected = _sha256({"action": self.action, "card_id": self.card_id})[:32]
        if self.decision_id != expected:
            raise MissionError("decision_id does not bind the exact AI decision")

    @classmethod
    def select(cls, card_id: str) -> "AIDecision":
        payload = {"action": "SELECT", "card_id": str(card_id)}
        return cls(decision_id=_sha256(payload)[:32], **payload)

    @classmethod
    def abstain(cls) -> "AIDecision":
        payload = {"action": "ABSTAIN", "card_id": None}
        return cls(decision_id=_sha256(payload)[:32], **payload)


@dataclass(frozen=True)
class ShadowOpen:
    plan_token: str
    card_id: str
    opened_at_ms: int
    raw_open: float
    fill_price: float
    fee_bps_per_side: float
    slippage_bps_per_side: float

    def __post_init__(self) -> None:
        if not _HEX_32.fullmatch(self.plan_token) or not _HEX_32.fullmatch(self.card_id):
            raise MissionError("shadow open identities must be lowercase 32-character hex")
        _exact_ms(self.opened_at_ms, "opened_at_ms")
        _positive(self.raw_open, "raw_open")
        _positive(self.fill_price, "fill_price")
        _bounded_bps(self.fee_bps_per_side, "fee_bps_per_side")
        _bounded_bps(self.slippage_bps_per_side, "slippage_bps_per_side")


def _receipt_payload(receipt: "ShadowReceipt") -> dict[str, Any]:
    values = asdict(receipt)
    values.pop("receipt_sha256", None)
    return values


@dataclass(frozen=True)
class ShadowReceipt:
    receipt_sha256: str
    mission_id: str
    card_id: str
    plan_sha256: str
    plan_token: str
    symbol: str
    side: str
    opened_at_ms: int
    closed_at_ms: int
    raw_open: float
    entry_fill: float
    raw_close: float
    exit_fill: float
    fee_bps_per_side: float
    slippage_bps_per_side: float
    gross_return: float
    net_return: float
    pnl_r: float
    close_reason: str
    schema: str = RECEIPT_SCHEMA
    mode: str = SHADOW_MODE
    research_only: bool = True
    broker_calls: bool = False

    def __post_init__(self) -> None:
        _mission_id(self.mission_id)
        if not _HEX_32.fullmatch(self.card_id) or not _HEX_32.fullmatch(self.plan_token):
            raise MissionError("receipt card/token identity is malformed")
        if not _HEX_64.fullmatch(self.plan_sha256):
            raise MissionError("receipt plan_sha256 is malformed")
        _symbol(self.symbol)
        if self.side not in {"long", "short"}:
            raise MissionError("receipt side is invalid")
        _exact_ms(self.opened_at_ms, "opened_at_ms")
        _exact_ms(self.closed_at_ms, "closed_at_ms")
        if self.closed_at_ms <= self.opened_at_ms:
            raise MissionError("shadow close must follow the shadow open")
        for name in ("raw_open", "entry_fill", "raw_close", "exit_fill"):
            _positive(getattr(self, name), name)
        for name in ("gross_return", "net_return", "pnl_r"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(float(value)):
                raise MissionError(f"{name} must be finite")
        _bounded_bps(self.fee_bps_per_side, "fee_bps_per_side")
        _bounded_bps(self.slippage_bps_per_side, "slippage_bps_per_side")
        _reason(self.close_reason)
        if (
            self.schema != RECEIPT_SCHEMA
            or self.mode != SHADOW_MODE
            or not self.research_only
            or self.broker_calls
        ):
            raise MissionError("receipt must remain a research-only shadow receipt")
        expected = _sha256(_receipt_payload(self))
        if self.receipt_sha256 != expected:
            raise MissionError("receipt_sha256 does not bind the immutable receipt")


@dataclass(frozen=True)
class MissionRecord:
    mission_id: str
    status: MissionStatus
    requested_at_ms: int
    updated_at_ms: int
    policy: MissionPolicy
    cards: Tuple[CandidateCard, ...] = ()
    frozen_at_ms: Optional[int] = None
    decision: Optional[AIDecision] = None
    proposed_at_ms: Optional[int] = None
    selected_card_id: Optional[str] = None
    plan_sha256: Optional[str] = None
    plan_token: Optional[str] = None
    validated_at_ms: Optional[int] = None
    shadow_open: Optional[ShadowOpen] = None
    receipt: Optional[ShadowReceipt] = None
    terminal_reason: Optional[str] = None
    mode: str = SHADOW_MODE

    def __post_init__(self) -> None:
        _validate_record(self)


@dataclass(frozen=True)
class MissionBook:
    revision: int = 0
    kill_switch: bool = False
    kill_updated_at_ms: Optional[int] = None
    active: Optional[MissionRecord] = None
    history: Tuple[MissionRecord, ...] = ()
    seen_mission_ids: Tuple[str, ...] = ()
    used_plan_tokens: Tuple[str, ...] = ()
    receipt_sha256s: Tuple[str, ...] = ()
    mode: str = SHADOW_MODE

    def __post_init__(self) -> None:
        _validate_book(self)


def _card_obj(card: CandidateCard) -> dict[str, Any]:
    return {"card_id": card.card_id, **card.payload()}


def _policy_obj(policy: MissionPolicy) -> dict[str, Any]:
    return {
        "allowlist": list(policy.allowlist),
        "freshness_ms": policy.freshness_ms,
        "min_rr": policy.min_rr,
        "execution_interval_ms": policy.execution_interval_ms,
        "fee_bps_per_side": policy.fee_bps_per_side,
        "slippage_bps_per_side": policy.slippage_bps_per_side,
    }


def _decision_obj(decision: AIDecision) -> dict[str, Any]:
    return asdict(decision)


def _plan_payload(record: MissionRecord, card: CandidateCard) -> dict[str, Any]:
    assert record.decision is not None
    return {
        "schema": PLAN_SCHEMA,
        "mode": SHADOW_MODE,
        "mission_id": record.mission_id,
        "candidate": _card_obj(card),
        "policy": _policy_obj(record.policy),
        "decision": _decision_obj(record.decision),
        "research_only": True,
        "broker_calls": False,
    }


def _plan_identity(record: MissionRecord, card: CandidateCard) -> tuple[str, str]:
    plan_sha256 = _sha256(_plan_payload(record, card))
    token = _sha256(
        {
            "schema": "ai_trade_mission_shadow_plan_token_v1",
            "mission_id": record.mission_id,
            "card_id": card.card_id,
            "plan_sha256": plan_sha256,
        }
    )[:32]
    return plan_sha256, token


def _selected_card(record: MissionRecord) -> CandidateCard:
    matches = tuple(card for card in record.cards if card.card_id == record.selected_card_id)
    if len(matches) != 1:
        raise MissionError("selected card is not uniquely frozen in this mission")
    return matches[0]


def _validate_record(record: MissionRecord) -> None:
    _mission_id(record.mission_id)
    if record.mode != SHADOW_MODE:
        raise MissionError("mission mode is physically fixed to shadow")
    if not isinstance(record.status, MissionStatus):
        raise MissionError("mission status is invalid")
    _exact_ms(record.requested_at_ms, "requested_at_ms")
    _exact_ms(record.updated_at_ms, "updated_at_ms")
    if record.updated_at_ms < record.requested_at_ms:
        raise MissionError("mission timeline regressed")
    if tuple(sorted(record.cards, key=lambda card: card.card_id)) != record.cards:
        raise MissionError("candidate cards must be deterministically sorted")
    if len({card.card_id for card in record.cards}) != len(record.cards):
        raise MissionError("candidate cards contain duplicates")

    if record.frozen_at_ms is None:
        if record.cards or any(
            value is not None
            for value in (
                record.decision,
                record.proposed_at_ms,
                record.selected_card_id,
                record.plan_sha256,
                record.plan_token,
                record.validated_at_ms,
                record.shadow_open,
                record.receipt,
            )
        ):
            raise MissionError("unfrozen mission contains downstream evidence")
    else:
        _exact_ms(record.frozen_at_ms, "frozen_at_ms")
        if record.frozen_at_ms < record.requested_at_ms:
            raise MissionError("snapshot freeze predates mission request")
        if any(card.closed_at_ms > record.frozen_at_ms for card in record.cards):
            raise MissionError("snapshot contains a future-closed candidate")

    if record.decision is None:
        if any(
            value is not None
            for value in (
                record.proposed_at_ms,
                record.selected_card_id,
                record.plan_sha256,
                record.plan_token,
                record.validated_at_ms,
                record.shadow_open,
                record.receipt,
            )
        ):
            raise MissionError("mission contains evidence without an AI decision")
    else:
        if record.proposed_at_ms is None or record.frozen_at_ms is None:
            raise MissionError("AI proposal lacks a frozen snapshot/timestamp")
        _exact_ms(record.proposed_at_ms, "proposed_at_ms")
        if record.proposed_at_ms < record.frozen_at_ms:
            raise MissionError("AI proposal predates the frozen snapshot")
        if record.decision.action == "SELECT":
            if record.selected_card_id != record.decision.card_id:
                raise MissionError("selected_card_id diverges from AI decision")
            _selected_card(record)
        elif record.selected_card_id is not None:
            raise MissionError("ABSTAIN mission cannot select a card")

    plan_fields = (record.plan_sha256, record.plan_token, record.validated_at_ms)
    if all(value is None for value in plan_fields):
        if record.shadow_open is not None or record.receipt is not None:
            raise MissionError("shadow evidence exists without a validated plan")
    elif any(value is None for value in plan_fields):
        raise MissionError("validated plan identity is incomplete")
    else:
        assert record.plan_sha256 is not None
        assert record.plan_token is not None
        assert record.validated_at_ms is not None
        if not _HEX_64.fullmatch(record.plan_sha256) or not _HEX_32.fullmatch(record.plan_token):
            raise MissionError("validated plan hash/token is malformed")
        _exact_ms(record.validated_at_ms, "validated_at_ms")
        assert record.proposed_at_ms is not None
        if record.validated_at_ms < record.proposed_at_ms:
            raise MissionError("validation predates the AI proposal")
        card = _selected_card(record)
        expected_hash, expected_token = _plan_identity(record, card)
        if (record.plan_sha256, record.plan_token) != (expected_hash, expected_token):
            raise MissionError("plan hash/token is not bound to the mission and card")

    if record.shadow_open is not None:
        assert record.plan_token is not None and record.selected_card_id is not None
        if (
            record.shadow_open.plan_token != record.plan_token
            or record.shadow_open.card_id != record.selected_card_id
        ):
            raise MissionError("shadow open is not bound to the validated plan")
        if (
            record.shadow_open.fee_bps_per_side != record.policy.fee_bps_per_side
            or record.shadow_open.slippage_bps_per_side
            != record.policy.slippage_bps_per_side
        ):
            raise MissionError("shadow open costs diverge from frozen policy")
        card = _selected_card(record)
        adverse = record.policy.slippage_bps_per_side / 10_000.0
        expected_fill = record.shadow_open.raw_open * (
            1.0 + adverse if card.side == "long" else 1.0 - adverse
        )
        if not math.isclose(record.shadow_open.fill_price, expected_fill, rel_tol=1e-12):
            raise MissionError("shadow entry fill does not apply adverse slippage")

    if record.receipt is not None:
        if record.shadow_open is None or record.plan_sha256 is None:
            raise MissionError("receipt exists without an open validated plan")
        receipt = record.receipt
        card = _selected_card(record)
        if (
            receipt.mission_id != record.mission_id
            or receipt.card_id != card.card_id
            or receipt.plan_sha256 != record.plan_sha256
            or receipt.plan_token != record.plan_token
            or receipt.symbol != card.symbol
            or receipt.side != card.side
            or receipt.opened_at_ms != record.shadow_open.opened_at_ms
            or receipt.raw_open != record.shadow_open.raw_open
            or receipt.entry_fill != record.shadow_open.fill_price
        ):
            raise MissionError("receipt diverges from the frozen mission/open")

    if record.status == MissionStatus.REQUESTED and record.frozen_at_ms is not None:
        raise MissionError("REQUESTED mission is already frozen")
    if record.status == MissionStatus.SNAPSHOT_FROZEN and (
        record.frozen_at_ms is None or record.decision is not None
    ):
        raise MissionError("SNAPSHOT_FROZEN evidence mismatch")
    if record.status == MissionStatus.AI_PROPOSED and (
        record.decision is None or record.plan_sha256 is not None
    ):
        raise MissionError("AI_PROPOSED evidence mismatch")
    if record.status == MissionStatus.VALIDATED and (
        record.plan_sha256 is None or record.shadow_open is not None
    ):
        raise MissionError("VALIDATED evidence mismatch")
    if record.status == MissionStatus.SHADOW_OPEN and (
        record.shadow_open is None or record.receipt is not None
    ):
        raise MissionError("SHADOW_OPEN evidence mismatch")
    if record.status == MissionStatus.SHADOW_CLOSED and record.receipt is None:
        raise MissionError("SHADOW_CLOSED requires an immutable receipt")
    if record.status == MissionStatus.ABSTAIN and (
        record.decision is None or record.decision.action != "ABSTAIN"
    ):
        raise MissionError("ABSTAIN terminal state lacks an abstain decision")
    if record.status == MissionStatus.CANCELLED and record.shadow_open is not None:
        raise MissionError("an opened shadow mission must close with a receipt, not cancel")
    if record.status in TERMINAL_STATUSES:
        if record.terminal_reason is None:
            raise MissionError("terminal mission requires a reason")
        _reason(record.terminal_reason)
    elif record.terminal_reason is not None:
        raise MissionError("non-terminal mission cannot have a terminal reason")


def _validate_book(book: MissionBook) -> None:
    if book.mode != SHADOW_MODE:
        raise MissionError("mission book mode is physically fixed to shadow")
    if not isinstance(book.revision, int) or isinstance(book.revision, bool) or book.revision < 0:
        raise MissionError("book revision must be a non-negative integer")
    if not isinstance(book.kill_switch, bool):
        raise MissionError("kill_switch must be boolean")
    if book.kill_updated_at_ms is not None:
        _exact_ms(book.kill_updated_at_ms, "kill_updated_at_ms")
    if book.active is not None and book.active.status in TERMINAL_STATUSES:
        raise MissionError("terminal mission cannot remain active")
    if any(item.status not in TERMINAL_STATUSES for item in book.history):
        raise MissionError("mission history contains a non-terminal record")
    expected_ids = tuple(item.mission_id for item in book.history)
    if book.active is not None:
        expected_ids += (book.active.mission_id,)
    if book.seen_mission_ids != expected_ids or len(expected_ids) != len(set(expected_ids)):
        raise MissionError("mission replay ledger diverges from active/history records")
    for name, ledger, pattern in (
        ("used_plan_tokens", book.used_plan_tokens, _HEX_32),
        ("receipt_sha256s", book.receipt_sha256s, _HEX_64),
    ):
        if len(ledger) != len(set(ledger)) or not all(pattern.fullmatch(item) for item in ledger):
            raise MissionError(f"{name} is malformed or contains duplicates")
    opened_tokens = tuple(
        item.plan_token
        for item in (*book.history, *((book.active,) if book.active else ()))
        if item.shadow_open is not None
    )
    if book.used_plan_tokens != opened_tokens:
        raise MissionError("consumed plan-token ledger diverges from shadow opens")
    receipts = tuple(
        item.receipt.receipt_sha256
        for item in book.history
        if item.receipt is not None
    )
    if book.receipt_sha256s != receipts:
        raise MissionError("receipt replay ledger diverges from immutable history")


def _record_obj(record: MissionRecord) -> dict[str, Any]:
    return {
        "mission_id": record.mission_id,
        "status": record.status.value,
        "requested_at_ms": record.requested_at_ms,
        "updated_at_ms": record.updated_at_ms,
        "policy": _policy_obj(record.policy),
        "cards": [_card_obj(card) for card in record.cards],
        "frozen_at_ms": record.frozen_at_ms,
        "decision": None if record.decision is None else _decision_obj(record.decision),
        "proposed_at_ms": record.proposed_at_ms,
        "selected_card_id": record.selected_card_id,
        "plan_sha256": record.plan_sha256,
        "plan_token": record.plan_token,
        "validated_at_ms": record.validated_at_ms,
        "shadow_open": None if record.shadow_open is None else asdict(record.shadow_open),
        "receipt": None if record.receipt is None else asdict(record.receipt),
        "terminal_reason": record.terminal_reason,
        "mode": record.mode,
    }


def _book_obj(book: MissionBook) -> dict[str, Any]:
    return {
        "revision": book.revision,
        "kill_switch": book.kill_switch,
        "kill_updated_at_ms": book.kill_updated_at_ms,
        "active": None if book.active is None else _record_obj(book.active),
        "history": [_record_obj(item) for item in book.history],
        "seen_mission_ids": list(book.seen_mission_ids),
        "used_plan_tokens": list(book.used_plan_tokens),
        "receipt_sha256s": list(book.receipt_sha256s),
        "mode": book.mode,
    }


def _card_from_obj(raw: object) -> CandidateCard:
    obj = _expect_mapping(raw, "card")
    _expect_keys(
        obj,
        {"card_id", "symbol", "side", "closed_at_ms", "entry", "sl", "tp", "snapshot_hash"},
        "card",
    )
    try:
        return CandidateCard(**dict(obj))
    except (TypeError, ValueError, MissionError) as exc:
        raise MissionPersistenceError(f"invalid candidate card: {exc}") from exc


def _policy_from_obj(raw: object) -> MissionPolicy:
    obj = _expect_mapping(raw, "policy")
    _expect_keys(
        obj,
        {
            "allowlist",
            "freshness_ms",
            "min_rr",
            "execution_interval_ms",
            "fee_bps_per_side",
            "slippage_bps_per_side",
        },
        "policy",
    )
    try:
        return MissionPolicy(allowlist=tuple(obj["allowlist"]), **{k: v for k, v in obj.items() if k != "allowlist"})
    except (TypeError, ValueError, MissionError) as exc:
        raise MissionPersistenceError(f"invalid mission policy: {exc}") from exc


def _decision_from_obj(raw: object) -> AIDecision:
    obj = _expect_mapping(raw, "decision")
    _expect_keys(obj, {"action", "card_id", "decision_id"}, "decision")
    try:
        return AIDecision(**dict(obj))
    except (TypeError, ValueError, MissionError) as exc:
        raise MissionPersistenceError(f"invalid AI decision: {exc}") from exc


def _record_from_obj(raw: object) -> MissionRecord:
    obj = _expect_mapping(raw, "mission")
    expected = {
        "mission_id",
        "status",
        "requested_at_ms",
        "updated_at_ms",
        "policy",
        "cards",
        "frozen_at_ms",
        "decision",
        "proposed_at_ms",
        "selected_card_id",
        "plan_sha256",
        "plan_token",
        "validated_at_ms",
        "shadow_open",
        "receipt",
        "terminal_reason",
        "mode",
    }
    _expect_keys(obj, expected, "mission")
    cards_raw = obj["cards"]
    if not isinstance(cards_raw, list):
        raise MissionPersistenceError("mission.cards must be an array")
    try:
        return MissionRecord(
            mission_id=obj["mission_id"],
            status=MissionStatus(obj["status"]),
            requested_at_ms=obj["requested_at_ms"],
            updated_at_ms=obj["updated_at_ms"],
            policy=_policy_from_obj(obj["policy"]),
            cards=tuple(_card_from_obj(item) for item in cards_raw),
            frozen_at_ms=obj["frozen_at_ms"],
            decision=None if obj["decision"] is None else _decision_from_obj(obj["decision"]),
            proposed_at_ms=obj["proposed_at_ms"],
            selected_card_id=obj["selected_card_id"],
            plan_sha256=obj["plan_sha256"],
            plan_token=obj["plan_token"],
            validated_at_ms=obj["validated_at_ms"],
            shadow_open=None if obj["shadow_open"] is None else ShadowOpen(**obj["shadow_open"]),
            receipt=None if obj["receipt"] is None else ShadowReceipt(**obj["receipt"]),
            terminal_reason=obj["terminal_reason"],
            mode=obj["mode"],
        )
    except (TypeError, ValueError, MissionError) as exc:
        raise MissionPersistenceError(f"invalid mission record: {exc}") from exc


def _book_from_obj(raw: object) -> MissionBook:
    obj = _expect_mapping(raw, "payload")
    _expect_keys(
        obj,
        {
            "revision",
            "kill_switch",
            "kill_updated_at_ms",
            "active",
            "history",
            "seen_mission_ids",
            "used_plan_tokens",
            "receipt_sha256s",
            "mode",
        },
        "payload",
    )
    history_raw = obj["history"]
    if not isinstance(history_raw, list):
        raise MissionPersistenceError("history must be an array")
    try:
        return MissionBook(
            revision=obj["revision"],
            kill_switch=obj["kill_switch"],
            kill_updated_at_ms=obj["kill_updated_at_ms"],
            active=None if obj["active"] is None else _record_from_obj(obj["active"]),
            history=tuple(_record_from_obj(item) for item in history_raw),
            seen_mission_ids=_strict_tuple_strings(obj["seen_mission_ids"], "seen_mission_ids"),
            used_plan_tokens=_strict_tuple_strings(obj["used_plan_tokens"], "used_plan_tokens"),
            receipt_sha256s=_strict_tuple_strings(obj["receipt_sha256s"], "receipt_sha256s"),
            mode=obj["mode"],
        )
    except (TypeError, ValueError, MissionError) as exc:
        raise MissionPersistenceError(f"invalid mission book: {exc}") from exc


def _validate_record_transition(old: MissionRecord, new: MissionRecord) -> None:
    if new.status not in _ALLOWED_TRANSITIONS.get(old.status, set()):
        raise MissionPersistenceError(f"illegal mission transition {old.status.value}->{new.status.value}")
    if (
        old.mission_id != new.mission_id
        or old.mode != new.mode
        or old.requested_at_ms != new.requested_at_ms
        or old.policy != new.policy
        or new.updated_at_ms < old.updated_at_ms
    ):
        raise MissionPersistenceError("mission identity/policy/timeline mutated")
    if old.frozen_at_ms is not None and (
        new.frozen_at_ms != old.frozen_at_ms or new.cards != old.cards
    ):
        raise MissionPersistenceError("frozen candidate snapshot mutated")
    if old.decision is not None and (
        new.decision != old.decision
        or new.proposed_at_ms != old.proposed_at_ms
        or new.selected_card_id != old.selected_card_id
    ):
        raise MissionPersistenceError("AI decision mutated")
    if old.plan_sha256 is not None and (
        new.plan_sha256 != old.plan_sha256
        or new.plan_token != old.plan_token
        or new.validated_at_ms != old.validated_at_ms
    ):
        raise MissionPersistenceError("validated plan mutated")
    if old.shadow_open is not None and new.shadow_open != old.shadow_open:
        raise MissionPersistenceError("shadow open mutated")


def _validate_book_transition(old: MissionBook, new: MissionBook) -> None:
    if new.revision != old.revision + 1:
        raise MissionPersistenceError("book revision must advance exactly once")
    if new.mode != old.mode:
        raise MissionPersistenceError("book mode mutated")
    if new.history[: len(old.history)] != old.history:
        raise MissionPersistenceError("terminal mission history mutated")
    if not new.seen_mission_ids[: len(old.seen_mission_ids)] == old.seen_mission_ids:
        raise MissionPersistenceError("mission replay ledger regressed")
    if not new.used_plan_tokens[: len(old.used_plan_tokens)] == old.used_plan_tokens:
        raise MissionPersistenceError("plan-token replay ledger regressed")
    if not new.receipt_sha256s[: len(old.receipt_sha256s)] == old.receipt_sha256s:
        raise MissionPersistenceError("receipt replay ledger regressed")

    if old.active is None:
        if new.active is None:
            if new.history != old.history or new.seen_mission_ids != old.seen_mission_ids:
                raise MissionPersistenceError("history changed without an active mission")
        else:
            if (
                new.active.status != MissionStatus.REQUESTED
                or new.history != old.history
                or new.seen_mission_ids != old.seen_mission_ids + (new.active.mission_id,)
            ):
                raise MissionPersistenceError("new active mission was not requested atomically")
    else:
        if new.active is not None:
            if new.history != old.history or new.seen_mission_ids != old.seen_mission_ids:
                raise MissionPersistenceError("active transition mutated mission ledgers")
            if new.active == old.active:
                if new.kill_switch == old.kill_switch:
                    raise MissionPersistenceError("refusing no-op book transition")
            else:
                _validate_record_transition(old.active, new.active)
        else:
            if len(new.history) != len(old.history) + 1 or new.history[-1].mission_id != old.active.mission_id:
                raise MissionPersistenceError("terminal transition did not append the active mission")
            if new.seen_mission_ids != old.seen_mission_ids:
                raise MissionPersistenceError("terminal transition mutated mission replay ids")
            _validate_record_transition(old.active, new.history[-1])


T = TypeVar("T")


class AtomicMissionStore:
    """Locked one-file state store with checksum, 0600 mode, and atomic replace."""

    def __init__(self, path: Path | str) -> None:
        raw = os.fspath(path)
        if not raw:
            raise ValueError("state path must be non-empty")
        candidate = Path(os.path.abspath(raw))
        # Pin the current canonical parent once.  This accommodates standard
        # platform aliases such as macOS ``/var -> /private/var`` while the
        # later component walk still refuses a parent that changes into a
        # symlink after controller construction.
        self.path = candidate.parent.resolve(strict=False) / candidate.name
        self.lock_path = self.path.with_name(f".{self.path.name}.lock")

    def _prepare_parent(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        current = Path(self.path.anchor)
        for part in self.path.parent.parts[1:]:
            current /= part
            try:
                info = current.lstat()
            except OSError as exc:
                raise MissionPersistenceError(f"cannot inspect state parent: {exc}") from exc
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise MissionPersistenceError("state parent contains a symlink/non-directory")

    @contextlib.contextmanager
    def _locked(self, *, exclusive: bool) -> Iterator[None]:
        self._prepare_parent()
        flags = os.O_RDWR | os.O_CREAT
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self.lock_path, flags, 0o600)
        except OSError as exc:
            raise MissionPersistenceError(f"cannot open mission lock safely: {exc}") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise MissionPersistenceError("mission lock is not a regular file")
            if stat.S_IMODE(info.st_mode) != 0o600:
                raise MissionPersistenceError("mission lock mode must be exactly 0600")
            fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def _read_unlocked(self) -> MissionBook:
        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return MissionBook()
        except OSError as exc:
            raise MissionPersistenceError(f"cannot inspect mission state: {exc}") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise MissionPersistenceError("mission state must be a regular non-symlink file")
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise MissionPersistenceError("mission state mode must be exactly 0600")
        if info.st_size > MAX_STATE_BYTES:
            raise MissionPersistenceError("mission state exceeds safety size limit")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self.path, flags)
            try:
                chunks: list[bytes] = []
                remaining = MAX_STATE_BYTES + 1
                while remaining:
                    chunk = os.read(fd, min(64 * 1024, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                raw = b"".join(chunks)
            finally:
                os.close(fd)
            if len(raw) > MAX_STATE_BYTES:
                raise MissionPersistenceError("mission state exceeds safety size limit")
            envelope = _expect_mapping(json.loads(raw.decode("utf-8")), "envelope")
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise MissionPersistenceError(f"mission state is unreadable: {exc}") from exc
        _expect_keys(
            envelope,
            {"schema", "version", "mode", "payload", "payload_sha256"},
            "envelope",
        )
        if (
            envelope["schema"] != STATE_SCHEMA
            or envelope["version"] != STATE_VERSION
            or envelope["mode"] != SHADOW_MODE
        ):
            raise MissionPersistenceError("mission state schema/version/mode mismatch")
        if envelope["payload_sha256"] != _sha256(envelope["payload"]):
            raise MissionPersistenceError("mission state payload checksum mismatch")
        return _book_from_obj(envelope["payload"])

    def _write_unlocked(self, book: MissionBook) -> None:
        payload = _book_obj(book)
        envelope = {
            "schema": STATE_SCHEMA,
            "version": STATE_VERSION,
            "mode": SHADOW_MODE,
            "payload": payload,
            "payload_sha256": _sha256(payload),
        }
        data = json.dumps(envelope, indent=2, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"
        if len(data) > MAX_STATE_BYTES:
            raise MissionPersistenceError("mission state exceeds safety size limit")
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd: Optional[int] = None
        try:
            fd = os.open(temporary, flags, 0o600)
            os.fchmod(fd, 0o600)
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short write")
                view = view[written:]
            os.fsync(fd)
            os.close(fd)
            fd = None
            os.replace(temporary, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise MissionPersistenceError(f"atomic mission state write failed: {exc}") from exc
        finally:
            if fd is not None:
                os.close(fd)
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def load(self) -> MissionBook:
        with self._locked(exclusive=False):
            return self._read_unlocked()

    def transact(self, transform: Callable[[MissionBook], tuple[MissionBook, T]]) -> T:
        with self._locked(exclusive=True):
            before = self._read_unlocked()
            after, result = transform(before)
            _validate_book_transition(before, after)
            self._write_unlocked(after)
            verified = self._read_unlocked()
            if verified != after:
                raise MissionPersistenceError("persisted mission transition verification failed")
            return result


def _next_grid_open(record: MissionRecord) -> int:
    assert record.validated_at_ms is not None
    card = _selected_card(record)
    boundary = max(card.closed_at_ms, record.validated_at_ms)
    interval = record.policy.execution_interval_ms
    return ((boundary // interval) + 1) * interval


def _terminal(book: MissionBook, record: MissionRecord) -> MissionBook:
    if record.status not in TERMINAL_STATUSES:
        raise MissionError("only terminal records can move to history")
    return replace(book, active=None, history=book.history + (record,))


class AITradeMissionController:
    """Safe control plane for one active shadow mission at a time."""

    RESEARCH_ONLY = True
    LIVE_READY = False
    BROKER_CALLS = False
    NETWORK_CALLS = False
    MODE = SHADOW_MODE

    def __init__(self, state_path: Path | str) -> None:
        self.store = AtomicMissionStore(state_path)

    def state(self) -> MissionBook:
        return self.store.load()

    def request(
        self,
        *,
        mission_id: str,
        requested_at_ms: int,
        allowlist: Sequence[str],
        freshness_ms: int = 900_000,
        min_rr: float = 1.5,
        execution_interval_ms: int = 300_000,
        fee_bps_per_side: float = 6.0,
        slippage_bps_per_side: float = 2.0,
    ) -> MissionRecord:
        canonical_id = _mission_id(mission_id)
        requested = _exact_ms(requested_at_ms, "requested_at_ms")
        policy = MissionPolicy.build(
            allowlist=allowlist,
            freshness_ms=freshness_ms,
            min_rr=min_rr,
            execution_interval_ms=execution_interval_ms,
            fee_bps_per_side=fee_bps_per_side,
            slippage_bps_per_side=slippage_bps_per_side,
        )

        def transform(book: MissionBook) -> tuple[MissionBook, MissionRecord]:
            if book.kill_switch:
                raise MissionError("kill switch is engaged")
            if book.active is not None:
                raise MissionError("at most one active AI trade mission is allowed")
            if canonical_id in book.seen_mission_ids:
                raise MissionError("mission_id replay/duplicate rejected")
            record = MissionRecord(
                mission_id=canonical_id,
                status=MissionStatus.REQUESTED,
                requested_at_ms=requested,
                updated_at_ms=requested,
                policy=policy,
            )
            after = replace(
                book,
                revision=book.revision + 1,
                active=record,
                seen_mission_ids=book.seen_mission_ids + (canonical_id,),
            )
            return after, record

        return self.store.transact(transform)

    def freeze_snapshot(
        self, cards: Sequence[CandidateCard], *, frozen_at_ms: int
    ) -> MissionRecord:
        frozen_at = _exact_ms(frozen_at_ms, "frozen_at_ms")
        deterministic = tuple(sorted(cards, key=lambda card: card.card_id))
        if len({card.card_id for card in deterministic}) != len(deterministic):
            raise MissionError("candidate snapshot contains duplicate cards")

        def transform(book: MissionBook) -> tuple[MissionBook, MissionRecord]:
            record = _require_active(book, MissionStatus.REQUESTED)
            if frozen_at < record.updated_at_ms:
                raise MissionError("snapshot freeze timestamp regressed")
            if any(card.closed_at_ms > frozen_at for card in deterministic):
                raise MissionError("candidate was not closed when the snapshot froze")
            updated = replace(
                record,
                status=MissionStatus.SNAPSHOT_FROZEN,
                updated_at_ms=frozen_at,
                cards=deterministic,
                frozen_at_ms=frozen_at,
            )
            return replace(book, revision=book.revision + 1, active=updated), updated

        return self.store.transact(transform)

    def propose(self, decision: AIDecision, *, proposed_at_ms: int) -> MissionRecord:
        proposed_at = _exact_ms(proposed_at_ms, "proposed_at_ms")

        def transform(book: MissionBook) -> tuple[MissionBook, MissionRecord]:
            record = _require_active(book, MissionStatus.SNAPSHOT_FROZEN)
            if proposed_at < record.updated_at_ms:
                raise MissionError("AI proposal timestamp regressed")
            if decision.action == "SELECT" and decision.card_id not in {
                card.card_id for card in record.cards
            }:
                raise MissionError("AI may only select a frozen candidate card")
            updated = replace(
                record,
                status=MissionStatus.AI_PROPOSED,
                updated_at_ms=proposed_at,
                decision=decision,
                proposed_at_ms=proposed_at,
                selected_card_id=decision.card_id,
            )
            return replace(book, revision=book.revision + 1, active=updated), updated

        return self.store.transact(transform)

    def validate(self, *, validated_at_ms: int) -> MissionRecord:
        validated_at = _exact_ms(validated_at_ms, "validated_at_ms")

        def transform(book: MissionBook) -> tuple[MissionBook, MissionRecord]:
            record = _require_active(book, MissionStatus.AI_PROPOSED)
            if validated_at < record.updated_at_ms:
                raise MissionError("validation timestamp regressed")
            assert record.decision is not None
            if record.decision.action == "ABSTAIN":
                terminal = replace(
                    record,
                    status=MissionStatus.ABSTAIN,
                    updated_at_ms=validated_at,
                    terminal_reason="AI_ABSTAIN",
                )
                after = _terminal(replace(book, revision=book.revision + 1), terminal)
                return after, terminal

            card = _selected_card(record)
            if card.symbol not in record.policy.allowlist:
                raise MissionError("selected card symbol is outside the frozen allowlist")
            age = validated_at - card.closed_at_ms
            if age < 0 or age > record.policy.freshness_ms:
                raise MissionError("selected card failed the freshness gate")
            if card.reward_risk + 1e-12 < record.policy.min_rr:
                raise MissionError("selected card failed the minimum reward/risk gate")
            plan_sha256, plan_token = _plan_identity(record, card)
            if plan_token in book.used_plan_tokens:
                raise MissionError("validated plan token was already consumed")
            updated = replace(
                record,
                status=MissionStatus.VALIDATED,
                updated_at_ms=validated_at,
                plan_sha256=plan_sha256,
                plan_token=plan_token,
                validated_at_ms=validated_at,
            )
            return replace(book, revision=book.revision + 1, active=updated), updated

        return self.store.transact(transform)

    def open_shadow(self, *, opened_at_ms: int, raw_open: float) -> MissionRecord:
        opened_at = _exact_ms(opened_at_ms, "opened_at_ms")
        raw = _positive(raw_open, "raw_open")

        def transform(book: MissionBook) -> tuple[MissionBook, MissionRecord]:
            if book.kill_switch:
                raise MissionError("kill switch blocks a new shadow open")
            record = _require_active(book, MissionStatus.VALIDATED)
            expected = _next_grid_open(record)
            if opened_at != expected:
                raise MissionError(f"shadow fill must use exact next grid open {expected}")
            assert record.plan_token is not None
            if record.plan_token in book.used_plan_tokens:
                raise MissionError("plan-token replay/duplicate rejected")
            card = _selected_card(record)
            slip = record.policy.slippage_bps_per_side / 10_000.0
            fill = raw * (1.0 + slip if card.side == "long" else 1.0 - slip)
            geometry_ok = (
                card.sl < fill < card.tp
                if card.side == "long"
                else card.tp < fill < card.sl
            )
            if not geometry_ok:
                raise MissionError("next-open gap invalidated the frozen SL/TP geometry")
            next_open_rr = abs(card.tp - fill) / abs(fill - card.sl)
            if next_open_rr + 1e-12 < record.policy.min_rr:
                raise MissionError("next-open gap failed the frozen minimum reward/risk gate")
            shadow_open = ShadowOpen(
                plan_token=record.plan_token,
                card_id=card.card_id,
                opened_at_ms=opened_at,
                raw_open=raw,
                fill_price=fill,
                fee_bps_per_side=record.policy.fee_bps_per_side,
                slippage_bps_per_side=record.policy.slippage_bps_per_side,
            )
            updated = replace(
                record,
                status=MissionStatus.SHADOW_OPEN,
                updated_at_ms=opened_at,
                shadow_open=shadow_open,
            )
            after = replace(
                book,
                revision=book.revision + 1,
                active=updated,
                used_plan_tokens=book.used_plan_tokens + (record.plan_token,),
            )
            return after, updated

        return self.store.transact(transform)

    def close_shadow(
        self, *, closed_at_ms: int, raw_close: float, reason: str
    ) -> MissionRecord:
        closed_at = _exact_ms(closed_at_ms, "closed_at_ms")
        raw = _positive(raw_close, "raw_close")
        close_reason = _reason(reason)

        def transform(book: MissionBook) -> tuple[MissionBook, MissionRecord]:
            record = _require_active(book, MissionStatus.SHADOW_OPEN)
            assert record.shadow_open is not None
            assert record.plan_sha256 is not None and record.plan_token is not None
            if closed_at <= record.shadow_open.opened_at_ms:
                raise MissionError("shadow close must follow its open")
            card = _selected_card(record)
            slip = record.policy.slippage_bps_per_side / 10_000.0
            exit_fill = raw * (1.0 - slip if card.side == "long" else 1.0 + slip)
            entry_fill = record.shadow_open.fill_price
            direction = 1.0 if card.side == "long" else -1.0
            gross_return = direction * (exit_fill - entry_fill) / entry_fill
            net_return = gross_return - 2.0 * record.policy.fee_bps_per_side / 10_000.0
            risk = abs(entry_fill - card.sl)
            pnl_r = direction * (exit_fill - entry_fill) / risk
            values = {
                "mission_id": record.mission_id,
                "card_id": card.card_id,
                "plan_sha256": record.plan_sha256,
                "plan_token": record.plan_token,
                "symbol": card.symbol,
                "side": card.side,
                "opened_at_ms": record.shadow_open.opened_at_ms,
                "closed_at_ms": closed_at,
                "raw_open": record.shadow_open.raw_open,
                "entry_fill": entry_fill,
                "raw_close": raw,
                "exit_fill": exit_fill,
                "fee_bps_per_side": record.policy.fee_bps_per_side,
                "slippage_bps_per_side": record.policy.slippage_bps_per_side,
                "gross_return": gross_return,
                "net_return": net_return,
                "pnl_r": pnl_r,
                "close_reason": close_reason,
                "schema": RECEIPT_SCHEMA,
                "mode": SHADOW_MODE,
                "research_only": True,
                "broker_calls": False,
            }
            receipt = ShadowReceipt(receipt_sha256=_sha256(values), **values)
            if receipt.receipt_sha256 in book.receipt_sha256s:
                raise MissionError("receipt replay/duplicate rejected")
            terminal = replace(
                record,
                status=MissionStatus.SHADOW_CLOSED,
                updated_at_ms=closed_at,
                receipt=receipt,
                terminal_reason=close_reason,
            )
            after = replace(
                book,
                revision=book.revision + 1,
                active=None,
                history=book.history + (terminal,),
                receipt_sha256s=book.receipt_sha256s + (receipt.receipt_sha256,),
            )
            return after, terminal

        return self.store.transact(transform)

    def cancel(self, *, cancelled_at_ms: int, reason: str = "OPERATOR_CANCEL") -> MissionRecord:
        cancelled_at = _exact_ms(cancelled_at_ms, "cancelled_at_ms")
        terminal_reason = _reason(reason)

        def transform(book: MissionBook) -> tuple[MissionBook, MissionRecord]:
            if book.active is None:
                raise MissionError("there is no active mission to cancel")
            if book.active.status == MissionStatus.SHADOW_OPEN:
                raise MissionError("opened shadow mission must close with an immutable receipt")
            if cancelled_at < book.active.updated_at_ms:
                raise MissionError("cancellation timestamp regressed")
            terminal = replace(
                book.active,
                status=MissionStatus.CANCELLED,
                updated_at_ms=cancelled_at,
                terminal_reason=terminal_reason,
            )
            after = _terminal(replace(book, revision=book.revision + 1), terminal)
            return after, terminal

        return self.store.transact(transform)

    def set_kill_switch(self, *, enabled: bool, changed_at_ms: int) -> MissionBook:
        if not isinstance(enabled, bool):
            raise MissionError("kill switch value must be boolean")
        changed_at = _exact_ms(changed_at_ms, "changed_at_ms")

        def transform(book: MissionBook) -> tuple[MissionBook, MissionBook]:
            if book.kill_switch == enabled:
                raise MissionError("kill switch is already in the requested state")
            if book.kill_updated_at_ms is not None and changed_at < book.kill_updated_at_ms:
                raise MissionError("kill-switch timestamp regressed")
            after = replace(
                book,
                revision=book.revision + 1,
                kill_switch=enabled,
                kill_updated_at_ms=changed_at,
            )
            if enabled and after.active is not None and after.active.status != MissionStatus.SHADOW_OPEN:
                if changed_at < after.active.updated_at_ms:
                    raise MissionError("kill-switch timestamp predates active mission state")
                terminal = replace(
                    after.active,
                    status=MissionStatus.CANCELLED,
                    updated_at_ms=changed_at,
                    terminal_reason="KILL_SWITCH",
                )
                after = _terminal(after, terminal)
            return after, after

        return self.store.transact(transform)


def _require_active(book: MissionBook, expected: MissionStatus) -> MissionRecord:
    if book.active is None:
        raise MissionError("there is no active AI trade mission")
    if book.active.status != expected:
        raise MissionError(
            f"active mission status is {book.active.status.value}, expected {expected.value}"
        )
    return book.active


def mission_book_to_dict(book: MissionBook) -> dict[str, Any]:
    """Public JSON-safe view for CLI/status UI; contains no secret or live token."""
    return _book_obj(book)


def mission_record_to_dict(record: MissionRecord) -> dict[str, Any]:
    return _record_obj(record)


__all__ = [
    "AIDecision",
    "AITradeMissionController",
    "AtomicMissionStore",
    "BROKER_CALLS",
    "CandidateCard",
    "LIVE_READY",
    "MissionBook",
    "MissionError",
    "MissionPersistenceError",
    "MissionPolicy",
    "MissionRecord",
    "MissionStatus",
    "NETWORK_CALLS",
    "RESEARCH_ONLY",
    "SHADOW_MODE",
    "ShadowOpen",
    "ShadowReceipt",
    "candidate_from_input",
    "mission_book_to_dict",
    "mission_record_to_dict",
]
