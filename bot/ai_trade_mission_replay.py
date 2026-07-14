"""Hash-pinned, feed-bound replay for research-only AI trade missions.

This module is deliberately a separate adapter around :mod:`ai_trade_mission`.
It has no live, broker, Telegram, web, network, or allocator integration.  A
caller must pin the exact bytes of a finite JSON/JSONL M5 OHLC feed.  The AI
authority remains limited to selecting an already frozen card or abstaining;
entry and exit prices/timestamps are derived exclusively from the pinned feed.

The replay window is intentionally strict.  The feed must end at exactly the
predeclared ``max_bars`` horizon after the controller's exact next-grid entry.
This rejects both truncated evidence and arbitrary post-horizon tails.  A card
snapshot hash covers only bars closed by ``card.closed_at_ms``; latency and
outcome bars are never part of the AI-visible snapshot digest.

This produces strong execution provenance for one shadow mission, not proof of
an edge.  A byte hash cannot prevent post-hoc selection of cards or periods, so
every result has ``promotion_authority=false``.  Promotion research must add a
separately frozen preregistration hash and portfolio-level OOS gates.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from bot.ai_trade_mission import (
    AIDecision,
    AITradeMissionController,
    CandidateCard,
    MissionError,
    MissionRecord,
    candidate_from_input,
    mission_record_to_dict,
)


M5_MS = 300_000
DECISION_LATENCY_BARS = 1
MAX_FEED_BYTES = 64 * 1024 * 1024
MAX_REPLAY_BARS = 100_000
SNAPSHOT_SCHEMA = "ai_trade_mission_m5_snapshot_v1"
REPLAY_SCHEMA = "ai_trade_mission_feed_bound_replay_v1"
RESEARCH_ONLY = True
LIVE_READY = False
BROKER_CALLS = False
NETWORK_CALLS = False


class ReplayEvidenceError(MissionError):
    """Pinned market evidence is malformed, non-causal, or incomplete."""


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
        raise ReplayEvidenceError(f"value is not canonical JSON: {exc}") from exc


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _exact_int(value: object, name: str, *, minimum: int = 1) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ReplayEvidenceError(f"{name} must be an exact integer >= {minimum}")
    return value


def _positive_price(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReplayEvidenceError(f"{name} must be a finite positive JSON number")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ReplayEvidenceError(f"{name} must be a finite positive JSON number")
    return number


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReplayEvidenceError(f"duplicate JSON key rejected: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ReplayEvidenceError(f"non-finite JSON constant rejected: {value}")


def _strict_json(text: str, *, source: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except ReplayEvidenceError:
        raise
    except json.JSONDecodeError as exc:
        raise ReplayEvidenceError(f"invalid {source} JSON: {exc}") from exc


@dataclass(frozen=True)
class M5Bar:
    open_ts: int
    open: float
    high: float
    low: float
    close: float

    def __post_init__(self) -> None:
        ts = _exact_int(self.open_ts, "open_ts")
        if ts % M5_MS:
            raise ReplayEvidenceError("open_ts must lie on the canonical M5 grid")
        opening = _positive_price(self.open, "open")
        high = _positive_price(self.high, "high")
        low = _positive_price(self.low, "low")
        close = _positive_price(self.close, "close")
        if low > high or low > min(opening, close) or high < max(opening, close):
            raise ReplayEvidenceError("OHLC geometry is inconsistent")

    @property
    def close_ts(self) -> int:
        return self.open_ts + M5_MS


@dataclass(frozen=True)
class PinnedM5Feed:
    bars: tuple[M5Bar, ...]
    sha256: str
    source_format: str
    byte_count: int

    def __post_init__(self) -> None:
        if not self.bars:
            raise ReplayEvidenceError("feed must contain at least one M5 bar")
        if len(self.sha256) != 64 or any(ch not in "0123456789abcdef" for ch in self.sha256):
            raise ReplayEvidenceError("feed SHA256 must be lowercase hexadecimal")
        if self.source_format not in {"json", "jsonl"}:
            raise ReplayEvidenceError("unsupported feed format")
        _exact_int(self.byte_count, "byte_count")
        for previous, current in zip(self.bars, self.bars[1:]):
            if current.open_ts != previous.open_ts + M5_MS:
                raise ReplayEvidenceError("M5 feed has a gap, duplicate, or reordering")


def _bar_from_obj(raw: object, *, index: int) -> M5Bar:
    if not isinstance(raw, Mapping):
        raise ReplayEvidenceError(f"feed row {index} must be an object")
    expected = {"open_ts", "open", "high", "low", "close"}
    if set(raw) != expected:
        raise ReplayEvidenceError(f"feed row {index} keys must be exactly {sorted(expected)}")
    return M5Bar(
        open_ts=_exact_int(raw["open_ts"], f"row[{index}].open_ts"),
        open=_positive_price(raw["open"], f"row[{index}].open"),
        high=_positive_price(raw["high"], f"row[{index}].high"),
        low=_positive_price(raw["low"], f"row[{index}].low"),
        close=_positive_price(raw["close"], f"row[{index}].close"),
    )


def load_hash_pinned_m5_feed(
    path: Path | str,
    *,
    expected_sha256: str,
) -> PinnedM5Feed:
    """Load strict JSON/JSONL OHLC only after verifying its exact byte hash.

    The current wall clock is the only observation clock; callers cannot
    backdate it to make a future/forming bar appear closed.
    """

    expected = str(expected_sha256)
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        raise ReplayEvidenceError("expected feed SHA256 must be 64 lowercase hex characters")
    feed_path = Path(path)
    try:
        raw = feed_path.read_bytes()
    except OSError as exc:
        raise ReplayEvidenceError(f"cannot read pinned feed: {exc}") from exc
    if not raw or len(raw) > MAX_FEED_BYTES:
        raise ReplayEvidenceError("feed byte size is empty or exceeds the safety limit")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ReplayEvidenceError("feed SHA256 mismatch; tampered or wrong evidence")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReplayEvidenceError("feed must be strict UTF-8") from exc
    if text.startswith("\ufeff"):
        raise ReplayEvidenceError("UTF-8 BOM is not allowed in canonical evidence")

    stripped = text.strip()
    if not stripped:
        raise ReplayEvidenceError("feed is empty")
    if stripped.startswith("["):
        decoded = _strict_json(stripped, source="feed")
        if not isinstance(decoded, list):
            raise ReplayEvidenceError("JSON feed root must be an array")
        rows = decoded
        source_format = "json"
    else:
        rows = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                raise ReplayEvidenceError(f"blank JSONL line rejected at {line_number}")
            rows.append(_strict_json(line, source=f"feed line {line_number}"))
        source_format = "jsonl"
    bars = tuple(_bar_from_obj(row, index=index) for index, row in enumerate(rows))
    feed = PinnedM5Feed(
        bars=bars,
        sha256=actual,
        source_format=source_format,
        byte_count=len(raw),
    )
    observed = time.time_ns() // 1_000_000
    if feed.bars[-1].close_ts > observed:
        raise ReplayEvidenceError("feed contains a future or still-forming M5 bar")
    return feed


def snapshot_sha256(feed: PinnedM5Feed, *, symbol: str, closed_at_ms: int) -> str:
    """Hash only the causal prefix whose final bar closes at ``closed_at_ms``."""

    closed_at = _exact_int(closed_at_ms, "closed_at_ms")
    if closed_at % M5_MS:
        raise ReplayEvidenceError("card.closed_at_ms must lie on the M5 close grid")
    prefix = tuple(bar for bar in feed.bars if bar.close_ts <= closed_at)
    if not prefix or prefix[-1].close_ts != closed_at:
        raise ReplayEvidenceError("card.closed_at_ms is not an exact feed bar close")
    return _sha256_json(
        {
            "schema": SNAPSHOT_SCHEMA,
            "symbol": str(symbol),
            "interval_ms": M5_MS,
            "closed_at_ms": closed_at,
            "bars": [asdict(bar) for bar in prefix],
        }
    )


def read_candidate_cards(path: Path | str) -> tuple[CandidateCard, ...]:
    """Read a strict array of screener candidate payloads (without card_id)."""

    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ReplayEvidenceError(f"cannot read candidate JSON: {exc}") from exc
    decoded = _strict_json(text, source="candidate")
    if not isinstance(decoded, list) or not decoded:
        raise ReplayEvidenceError("candidate JSON root must be a non-empty array")
    return tuple(candidate_from_input(item) for item in decoded)


def _validate_frozen_cards(feed: PinnedM5Feed, cards: Sequence[CandidateCard]) -> tuple[
    tuple[CandidateCard, ...], int, str
]:
    if not all(isinstance(card, CandidateCard) for card in cards):
        raise ReplayEvidenceError("frozen cards must be validated CandidateCard objects")
    frozen = tuple(sorted(cards, key=lambda card: card.card_id))
    if not frozen:
        raise ReplayEvidenceError("at least one frozen candidate card is required")
    if len({card.card_id for card in frozen}) != len(frozen):
        raise ReplayEvidenceError("duplicate frozen candidate card")
    symbols = {card.symbol for card in frozen}
    closes = {card.closed_at_ms for card in frozen}
    if len(symbols) != 1 or len(closes) != 1:
        raise ReplayEvidenceError("all frozen cards must share one symbol and closed_at_ms")
    symbol = next(iter(symbols))
    closed_at = next(iter(closes))
    expected_snapshot = snapshot_sha256(feed, symbol=symbol, closed_at_ms=closed_at)
    if any(card.snapshot_hash != expected_snapshot for card in frozen):
        raise ReplayEvidenceError("candidate snapshot hash does not match the causal feed prefix")
    return frozen, closed_at, symbol


def _exit_from_bar(card: CandidateCard, bar: M5Bar) -> tuple[float, str] | None:
    if card.side == "long":
        hit_sl = bar.low <= card.sl
        hit_tp = bar.high >= card.tp
        adverse_stop = min(bar.open, card.sl)
    else:
        hit_sl = bar.high >= card.sl
        hit_tp = bar.low <= card.tp
        adverse_stop = max(bar.open, card.sl)
    if hit_sl and hit_tp:
        return adverse_stop, "AMBIGUOUS_SL_FIRST"
    if hit_sl:
        return adverse_stop, "SL"
    if hit_tp:
        return card.tp, "TP"
    return None


def _envelope(
    *,
    feed: PinnedM5Feed,
    observed_at_ms: int,
    max_bars: int,
    cards: tuple[CandidateCard, ...],
    terminal: MissionRecord,
    entry_open_ts: int | None,
    exit_open_ts: int | None,
    evaluated_bars: int,
) -> dict[str, Any]:
    selected = next(
        (card for card in cards if card.card_id == terminal.selected_card_id), None
    )
    controller_receipt = (
        None if terminal.receipt is None else asdict(terminal.receipt)
    )
    payload: dict[str, Any] = {
        "schema": REPLAY_SCHEMA,
        "research_only": True,
        "mode": "shadow",
        "historical_replay": True,
        "live": False,
        "broker": False,
        "network": False,
        "performance_authority": {
            "enabled": controller_receipt is not None,
            "scope": "single_mission_replay_only" if controller_receipt is not None else "none",
        },
        "promotion_authority": False,
        "selection_bias_control": {
            "preregistration_sha256": None,
            "post_hoc_card_or_period_selection_excluded": False,
        },
        "observed_at_ms": observed_at_ms,
        "feed": {
            "sha256": feed.sha256,
            "format": feed.source_format,
            "byte_count": feed.byte_count,
            "interval_ms": M5_MS,
            "row_count": len(feed.bars),
            "first_open_ts": feed.bars[0].open_ts,
            "last_open_ts": feed.bars[-1].open_ts,
            "last_close_ts": feed.bars[-1].close_ts,
        },
        "selected_bar_range": {
            "snapshot_closed_at_ms": cards[0].closed_at_ms,
            "entry_open_ts": entry_open_ts,
            "exit_open_ts": exit_open_ts,
            "exit_close_ts": None if exit_open_ts is None else exit_open_ts + M5_MS,
            "evaluated_bars": evaluated_bars,
            "max_bars": max_bars,
            "decision_latency_bars": DECISION_LATENCY_BARS,
            "feed_ends_at_preregistered_horizon": True,
        },
        "mission": {
            "mission_id": terminal.mission_id,
            "status": terminal.status.value,
            "decision": None if terminal.decision is None else asdict(terminal.decision),
            "selected_card": None if selected is None else {
                "card_id": selected.card_id,
                **selected.payload(),
            },
            "plan_sha256": terminal.plan_sha256,
            "plan_token": terminal.plan_token,
        },
        "controller_receipt": controller_receipt,
        "controller_terminal_record": mission_record_to_dict(terminal),
    }
    payload["envelope_sha256"] = _sha256_json(payload)
    return payload


def run_feed_bound_replay(
    *,
    feed_path: Path | str,
    expected_feed_sha256: str,
    state_path: Path | str,
    mission_id: str,
    cards: Sequence[CandidateCard],
    decision: AIDecision,
    max_bars: int,
    min_rr: float = 1.5,
    fee_bps_per_side: float = 6.0,
    slippage_bps_per_side: float = 2.0,
) -> dict[str, Any]:
    """Run one immutable shadow replay without accepting manual outcomes.

    Lifecycle, entry, and exit timestamps are derived from the frozen card and
    feed.  The only AI-controlled value is ``decision`` (SELECT/ABSTAIN).
    """

    observed = time.time_ns() // 1_000_000
    horizon = _exact_int(max_bars, "max_bars")
    if horizon > MAX_REPLAY_BARS:
        raise ReplayEvidenceError(f"max_bars exceeds safety limit {MAX_REPLAY_BARS}")
    feed = load_hash_pinned_m5_feed(
        feed_path,
        expected_sha256=expected_feed_sha256,
    )
    frozen, closed_at, symbol = _validate_frozen_cards(feed, cards)
    if not isinstance(decision, AIDecision):
        raise ReplayEvidenceError("decision must be a validated SELECT or ABSTAIN object")

    # AI/card evidence is frozen at the exact causal close.  The underlying
    # controller intentionally opens only at the first grid point strictly
    # after that boundary, which is one full M5 latency bar later.
    entry_open_ts = closed_at + DECISION_LATENCY_BARS * M5_MS
    by_ts = {bar.open_ts: index for index, bar in enumerate(feed.bars)}
    if entry_open_ts not in by_ts:
        raise ReplayEvidenceError("exact controller next-open bar is missing from feed")
    entry_index = by_ts[entry_open_ts]
    remaining = len(feed.bars) - entry_index
    if remaining < horizon:
        raise ReplayEvidenceError("feed is truncated before the fixed max-bars horizon")
    if remaining > horizon:
        raise ReplayEvidenceError("feed has a forbidden post-horizon tail")
    if feed.bars[-1].close_ts != entry_open_ts + horizon * M5_MS:
        raise ReplayEvidenceError("feed does not end at the deterministic horizon close")

    controller = AITradeMissionController(state_path)
    controller.request(
        mission_id=mission_id,
        requested_at_ms=closed_at,
        allowlist=(symbol,),
        freshness_ms=M5_MS,
        min_rr=min_rr,
        execution_interval_ms=M5_MS,
        fee_bps_per_side=fee_bps_per_side,
        slippage_bps_per_side=slippage_bps_per_side,
    )
    controller.freeze_snapshot(frozen, frozen_at_ms=closed_at)
    controller.propose(decision, proposed_at_ms=closed_at)
    validated = controller.validate(validated_at_ms=closed_at)
    if decision.action == "ABSTAIN":
        return _envelope(
            feed=feed,
            observed_at_ms=observed,
            max_bars=horizon,
            cards=frozen,
            terminal=validated,
            entry_open_ts=None,
            exit_open_ts=None,
            evaluated_bars=0,
        )

    entry_bar = feed.bars[entry_index]
    controller.open_shadow(opened_at_ms=entry_bar.open_ts, raw_open=entry_bar.open)
    selected = next(card for card in frozen if card.card_id == decision.card_id)
    exit_bar = feed.bars[entry_index + horizon - 1]
    raw_exit = exit_bar.close
    reason = "MAX_BARS"
    evaluated = horizon
    for offset, bar in enumerate(feed.bars[entry_index : entry_index + horizon], start=1):
        outcome = _exit_from_bar(selected, bar)
        if outcome is not None:
            raw_exit, reason = outcome
            exit_bar = bar
            evaluated = offset
            break
    terminal = controller.close_shadow(
        closed_at_ms=exit_bar.close_ts,
        raw_close=raw_exit,
        reason=reason,
    )
    return _envelope(
        feed=feed,
        observed_at_ms=observed,
        max_bars=horizon,
        cards=frozen,
        terminal=terminal,
        entry_open_ts=entry_bar.open_ts,
        exit_open_ts=exit_bar.open_ts,
        evaluated_bars=evaluated,
    )


def write_replay_receipt(path: Path | str, envelope: Mapping[str, Any]) -> None:
    """Create (never overwrite) a 0600 receipt with fsync + atomic replace."""

    destination = Path(path)
    if destination.exists():
        raise ReplayEvidenceError("receipt already exists; overwrite is forbidden")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = _canonical_bytes(dict(envelope)) + b"\n"
    temporary = destination.with_name(
        f".{destination.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd: int | None = None
    try:
        fd = os.open(temporary, flags, 0o600)
        os.fchmod(fd, 0o600)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short receipt write")
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        # Hard-link publication is create-only at the filesystem level: unlike
        # os.replace(), it cannot overwrite a receipt that appeared in the
        # check/publish race window.
        os.link(temporary, destination, follow_symlinks=False)
        temporary.unlink()
        directory_fd = os.open(
            destination.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except ReplayEvidenceError:
        raise
    except OSError as exc:
        raise ReplayEvidenceError(f"atomic receipt write failed: {exc}") from exc
    finally:
        if fd is not None:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


__all__ = [
    "BROKER_CALLS",
    "DECISION_LATENCY_BARS",
    "LIVE_READY",
    "M5Bar",
    "M5_MS",
    "NETWORK_CALLS",
    "PinnedM5Feed",
    "RESEARCH_ONLY",
    "ReplayEvidenceError",
    "load_hash_pinned_m5_feed",
    "read_candidate_cards",
    "run_feed_bound_replay",
    "snapshot_sha256",
    "write_replay_receipt",
]
