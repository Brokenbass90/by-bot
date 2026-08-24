"""Persistable, causal BTC closed-H1 EMA200 evidence.

This module is an authority-free boundary for future ATT1/SBR1 callers.  It
does not fetch candles, read configuration, call a broker, submit orders, or
decide risk.  A caller supplies closed Bybit-shaped rows and provenance; this
module only validates, advances, classifies, and durably records the state.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping, Sequence

from bot.live_native_regime_gate import (
    EMA_PERIOD,
    H1_MS,
    ClosedH1RegimeEvidence,
    classify_deviation,
)


STATE_SCHEMA_ID = "btc_closed_h1_ema200_state_v1"
RECEIPT_SCHEMA_ID = "btc_closed_h1_ema200_receipt_v1"
HISTORY_BOOTSTRAP_SCHEMA_ID = "btc_closed_h1_ema200_history_v1"
HISTORY_ADVANCE_SCHEMA_ID = "btc_closed_h1_ema200_advance_v1"
MIN_BOOTSTRAP_BARS = 500
STATE_FILE_MODE = 0o600
APPROVED_PUBLIC_PROVIDER = "bybit-public"
APPROVED_PUBLIC_ENDPOINT = "/v5/market/kline"
BTC_SYMBOL = "BTCUSDT"
H1_INTERVAL = "60"
SOURCE_PROVENANCE_KEYS = frozenset({"provider", "endpoint", "source_sha256"})
DATA_PROVENANCE_KEYS = frozenset(
    {"symbol", "interval", "data_sha256", "provenance"}
)


class BTCRegimeContractError(ValueError):
    """Stable, fail-closed validation error."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = str(code)
        self.detail = str(detail)
        super().__init__(self.code if not detail else f"{self.code}: {detail}")


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise BTCRegimeContractError("invalid_decimal", field)
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BTCRegimeContractError("invalid_decimal", field) from exc
    if not result.is_finite():
        raise BTCRegimeContractError("non_finite_decimal", field)
    return result


def _decimal_text(value: Decimal, field: str) -> str:
    result = _decimal(value, field)
    return "0" if result == 0 else format(result.normalize(), "f")


def _strict_int(value: object, field: str) -> int:
    if isinstance(value, bool) or isinstance(value, float):
        raise BTCRegimeContractError("invalid_integer", field)
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BTCRegimeContractError("invalid_integer", field) from exc
    if not result.is_finite() or result != result.to_integral_value():
        raise BTCRegimeContractError("invalid_integer", field)
    return int(result)


def _jsonable(value: object, field: str = "json") -> object:
    if isinstance(value, Decimal):
        return _decimal_text(value, field)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or key in result:
                raise BTCRegimeContractError("invalid_provenance", field)
            result[key] = _jsonable(item, field)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(item, field) for item in value]
    raise BTCRegimeContractError("invalid_provenance", field)


def _canonical(value: object, field: str = "json") -> bytes:
    try:
        normalized = _jsonable(value, field)
        return json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise BTCRegimeContractError("noncanonical_json", field) from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_hex(value: object, field: str) -> str:
    result = str(value or "")
    if len(result) != 64 or any(char not in "0123456789abcdef" for char in result):
        raise BTCRegimeContractError("invalid_sha256", field)
    return result


def _provenance(value: Mapping[str, object], field: str) -> dict[str, object]:
    if not isinstance(value, Mapping) or not value:
        raise BTCRegimeContractError("missing_provenance", field)
    normalized = _jsonable(value, field)
    assert isinstance(normalized, dict)
    return normalized


def _source_provenance(value: Mapping[str, object]) -> dict[str, object]:
    normalized = _provenance(value, "source_provenance")
    if (
        set(normalized) != SOURCE_PROVENANCE_KEYS
        or normalized.get("provider") != APPROVED_PUBLIC_PROVIDER
        or normalized.get("endpoint") != APPROVED_PUBLIC_ENDPOINT
    ):
        raise BTCRegimeContractError("invalid_source_provenance")
    normalized["source_sha256"] = _sha256_hex(
        normalized.get("source_sha256"), "source_sha256"
    )
    return normalized


def _data_provenance(value: Mapping[str, object]) -> dict[str, object]:
    normalized = _provenance(value, "data_provenance")
    if (
        set(normalized) != DATA_PROVENANCE_KEYS
        or normalized.get("symbol") != BTC_SYMBOL
        or normalized.get("interval") != H1_INTERVAL
        or not isinstance(normalized.get("provenance"), str)
        or not str(normalized.get("provenance") or "").strip()
    ):
        raise BTCRegimeContractError("invalid_data_provenance")
    normalized["data_sha256"] = _sha256_hex(
        normalized.get("data_sha256"), "data_sha256"
    )
    return normalized


def _row(raw: Sequence[object], code: str) -> tuple[int, Decimal, str]:
    if isinstance(raw, (str, bytes, bytearray)) or len(raw) < 5:
        raise BTCRegimeContractError(code)
    start = _strict_int(raw[0], "bar_start_ts_ms")
    close = _decimal(raw[4], "close")
    if start <= 0 or start % H1_MS != 0 or close <= 0:
        raise BTCRegimeContractError(code)
    return start, close, _sha256(_canonical(list(raw), "h1_row"))


def _observation(observed_at_ms: object, max_age_ms: object, start: int) -> None:
    observed = _strict_int(observed_at_ms, "observed_at_ms")
    max_age = _strict_int(max_age_ms, "max_age_ms")
    close_ts = start + H1_MS
    if observed < close_ts:
        raise BTCRegimeContractError("bar_not_closed")
    if max_age <= 0:
        raise BTCRegimeContractError("nonpositive_max_age")
    if observed - close_ts > max_age:
        raise BTCRegimeContractError("evidence_too_old")


def _history_bootstrap(row_hashes: Sequence[str]) -> str:
    return _sha256(
        _canonical(
            {"schema_id": HISTORY_BOOTSTRAP_SCHEMA_ID, "row_hashes": list(row_hashes)},
            "history",
        )
    )


def _history_advance(previous: str, row_hash: str, count: int) -> str:
    return _sha256(
        _canonical(
            {
                "schema_id": HISTORY_ADVANCE_SCHEMA_ID,
                "previous_history_hash": previous,
                "row_hash": row_hash,
                "observation_count": count,
            },
            "history",
        )
    )


@dataclass(frozen=True)
class BTCRegimeState:
    seed_bar_start_ts_ms: int
    seed_close: Decimal
    last_bar_start_ts_ms: int
    last_closed_h1_ts_ms: int
    close: Decimal
    ema200: Decimal
    observation_count: int
    history_hash: str
    last_row_hash: str
    source_provenance: Mapping[str, object]
    data_provenance: Mapping[str, object]

    @property
    def deviation(self) -> Decimal:
        return (self.close - self.ema200) / self.ema200

    @property
    def value(self) -> str:
        return classify_deviation(self.deviation)

    def allows(self, sleeve_id: str) -> bool:
        sleeve = str(sleeve_id or "").strip().upper()
        if sleeve == "ATT1":
            return self.value == "flat_down"
        if sleeve == "SBR1":
            return self.value == "flat_up"
        raise BTCRegimeContractError("unknown_regime_sleeve", sleeve)

    def _validate(self) -> None:
        if (
            self.seed_bar_start_ts_ms <= 0
            or self.seed_bar_start_ts_ms % H1_MS != 0
            or self.last_bar_start_ts_ms < self.seed_bar_start_ts_ms
            or self.last_bar_start_ts_ms % H1_MS != 0
            or self.last_bar_start_ts_ms
            != self.seed_bar_start_ts_ms + (self.observation_count - 1) * H1_MS
            or self.last_closed_h1_ts_ms != self.last_bar_start_ts_ms + H1_MS
            or self.observation_count < MIN_BOOTSTRAP_BARS
            or self.observation_count < 1
            or min(self.seed_close, self.close, self.ema200) <= 0
        ):
            raise BTCRegimeContractError("invalid_persisted_regime_state")
        _sha256_hex(self.history_hash, "history_hash")
        _sha256_hex(self.last_row_hash, "last_row_hash")
        _source_provenance(self.source_provenance)
        _data_provenance(self.data_provenance)
        if self.value not in {"below_band", "flat_down", "flat_up", "above_band"}:
            raise BTCRegimeContractError("invalid_regime_value")

    def _unsigned_payload(self) -> dict[str, object]:
        self._validate()
        return {
            "schema_id": STATE_SCHEMA_ID,
            "seed_bar_start_ts_ms": self.seed_bar_start_ts_ms,
            "seed_close": _decimal_text(self.seed_close, "seed_close"),
            "last_bar_start_ts_ms": self.last_bar_start_ts_ms,
            "last_closed_h1_ts_ms": self.last_closed_h1_ts_ms,
            "close": _decimal_text(self.close, "close"),
            "ema200": _decimal_text(self.ema200, "ema200"),
            "deviation": _decimal_text(self.deviation, "deviation"),
            "value": self.value,
            "observation_count": self.observation_count,
            "history_hash": self.history_hash,
            "last_row_hash": self.last_row_hash,
            "source_provenance": dict(self.source_provenance),
            "data_provenance": dict(self.data_provenance),
            "sleeve_decisions": {
                "ATT1": self.allows("ATT1"),
                "SBR1": self.allows("SBR1"),
            },
        }

    @property
    def state_sha256(self) -> str:
        return _sha256(_canonical(self._unsigned_payload(), "state"))

    def to_dict(self) -> dict[str, object]:
        payload = self._unsigned_payload()
        payload["state_sha256"] = self.state_sha256
        return payload

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "BTCRegimeState":
        if not isinstance(raw, Mapping) or raw.get("schema_id") != STATE_SCHEMA_ID:
            raise BTCRegimeContractError("invalid_state_schema")
        state = cls(
            seed_bar_start_ts_ms=_strict_int(
                raw.get("seed_bar_start_ts_ms"), "seed_bar_start_ts_ms"
            ),
            seed_close=_decimal(raw.get("seed_close"), "seed_close"),
            last_bar_start_ts_ms=_strict_int(
                raw.get("last_bar_start_ts_ms"), "last_bar_start_ts_ms"
            ),
            last_closed_h1_ts_ms=_strict_int(
                raw.get("last_closed_h1_ts_ms"), "last_closed_h1_ts_ms"
            ),
            close=_decimal(raw.get("close"), "close"),
            ema200=_decimal(raw.get("ema200"), "ema200"),
            observation_count=_strict_int(raw.get("observation_count"), "observation_count"),
            history_hash=_sha256_hex(raw.get("history_hash"), "history_hash"),
            last_row_hash=_sha256_hex(raw.get("last_row_hash"), "last_row_hash"),
            source_provenance=_source_provenance(
                raw.get("source_provenance")  # type: ignore[arg-type]
            ),
            data_provenance=_data_provenance(raw.get("data_provenance")),  # type: ignore[arg-type]
        )
        expected = str(raw.get("state_sha256") or "")
        if expected != state.state_sha256:
            raise BTCRegimeContractError("state_hash_mismatch")
        if raw.get("deviation") != _decimal_text(state.deviation, "deviation"):
            raise BTCRegimeContractError("state_invariant_mismatch")
        if raw.get("value") != state.value or raw.get("sleeve_decisions") != {
            "ATT1": state.allows("ATT1"),
            "SBR1": state.allows("SBR1"),
        }:
            raise BTCRegimeContractError("state_invariant_mismatch")
        return state


@dataclass(frozen=True)
class BTCRegimeReceipt:
    state: BTCRegimeState
    money_authority: bool = False
    promotion_authority: bool = False

    def _validate(self) -> None:
        if not isinstance(self.state, BTCRegimeState):
            raise BTCRegimeContractError("invalid_receipt_state")
        self.state._validate()
        if (
            self.money_authority is not False
            or self.promotion_authority is not False
        ):
            raise BTCRegimeContractError("regime_receipt_authority_forbidden")

    def _unsigned_payload(self) -> dict[str, object]:
        self._validate()
        return {
            "schema_id": RECEIPT_SCHEMA_ID,
            "state": self.state.to_dict(),
            "money_authority": False,
            "promotion_authority": False,
            "research_only": True,
        }

    @property
    def receipt_sha256(self) -> str:
        return _sha256(_canonical(self._unsigned_payload(), "receipt"))

    def to_dict(self) -> dict[str, object]:
        payload = self._unsigned_payload()
        payload["receipt_sha256"] = self.receipt_sha256
        return payload

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "BTCRegimeReceipt":
        if not isinstance(raw, Mapping) or raw.get("schema_id") != RECEIPT_SCHEMA_ID:
            raise BTCRegimeContractError("invalid_receipt_schema")
        expected_receipt_hash = str(raw.get("receipt_sha256") or "")
        unsigned_raw = dict(raw)
        unsigned_raw.pop("receipt_sha256", None)
        if expected_receipt_hash != _sha256(_canonical(unsigned_raw, "receipt")):
            raise BTCRegimeContractError("receipt_hash_mismatch")
        if raw.get("money_authority") is not False or raw.get("promotion_authority") is not False:
            raise BTCRegimeContractError("regime_receipt_authority_forbidden")
        state_raw = raw.get("state")
        if not isinstance(state_raw, Mapping):
            raise BTCRegimeContractError("invalid_receipt_state")
        state = BTCRegimeState.from_dict(state_raw)
        receipt = cls(state=state)
        receipt._validate()
        if expected_receipt_hash != receipt.receipt_sha256:
            raise BTCRegimeContractError("receipt_hash_mismatch")
        if raw.get("research_only") is not True:
            raise BTCRegimeContractError("receipt_not_research_only")
        return receipt


def _evidence(
    receipt: BTCRegimeReceipt, observed_at_ms: object, max_age_ms: object
) -> ClosedH1RegimeEvidence:
    state = receipt.state
    _observation(observed_at_ms, max_age_ms, state.last_bar_start_ts_ms)
    observed = _strict_int(observed_at_ms, "observed_at_ms")
    closed = state.last_closed_h1_ts_ms
    return ClosedH1RegimeEvidence(
        seed_start_ts_ms=state.seed_bar_start_ts_ms,
        history_bars=state.observation_count,
        bar_start_ts_ms=state.last_bar_start_ts_ms,
        closed_h1_ts_ms=closed,
        observed_at_ms=observed,
        age_ms=observed - closed,
        close=state.close,
        ema200=state.ema200,
        deviation=state.deviation,
        value=state.value,  # type: ignore[arg-type]
    )


def _validated_receipt(receipt: object) -> BTCRegimeReceipt:
    if not isinstance(receipt, BTCRegimeReceipt):
        raise BTCRegimeContractError("invalid_regime_receipt")
    receipt._validate()
    return receipt


def bootstrap_btc_h1_regime(
    rows: Sequence[Sequence[object]],
    *,
    observed_at_ms: object,
    max_age_ms: object,
    source_provenance: Mapping[str, object],
    data_provenance: Mapping[str, object],
) -> BTCRegimeReceipt:
    """Seed once from at least 500 contiguous closed H1 rows."""

    if isinstance(rows, (str, bytes, bytearray)) or len(rows) < MIN_BOOTSTRAP_BARS:
        raise BTCRegimeContractError("insufficient_bootstrap_history")
    source = _source_provenance(source_provenance)
    data = _data_provenance(data_provenance)
    starts: list[int] = []
    closes: list[Decimal] = []
    row_hashes: list[str] = []
    for raw in rows:
        start, close, row_hash = _row(raw, "invalid_bootstrap_row")
        if starts and start != starts[-1] + H1_MS:
            raise BTCRegimeContractError("noncontiguous_bootstrap")
        if start + H1_MS > _strict_int(observed_at_ms, "observed_at_ms"):
            raise BTCRegimeContractError("bar_not_closed")
        starts.append(start)
        closes.append(close)
        row_hashes.append(row_hash)
    _observation(observed_at_ms, max_age_ms, starts[-1])
    alpha = Decimal("2") / Decimal(EMA_PERIOD + 1)
    ema200 = closes[0]
    for close in closes[1:]:
        ema200 = close * alpha + ema200 * (Decimal("1") - alpha)
    state = BTCRegimeState(
        seed_bar_start_ts_ms=starts[0],
        seed_close=closes[0],
        last_bar_start_ts_ms=starts[-1],
        last_closed_h1_ts_ms=starts[-1] + H1_MS,
        close=closes[-1],
        ema200=ema200,
        observation_count=len(rows),
        history_hash=_history_bootstrap(row_hashes),
        last_row_hash=row_hashes[-1],
        source_provenance=source,
        data_provenance=data,
    )
    state._validate()
    return BTCRegimeReceipt(state=state)


def advance_btc_h1_regime(
    receipt: BTCRegimeReceipt,
    row: Sequence[object],
    *,
    observed_at_ms: object,
    max_age_ms: object,
) -> BTCRegimeReceipt:
    """Advance exactly one contiguous bar; an identical duplicate is a no-op."""

    receipt = _validated_receipt(receipt)
    state = receipt.state
    state._validate()
    start, close, row_hash = _row(row, "invalid_update_row")
    _observation(observed_at_ms, max_age_ms, start)
    if start == state.last_bar_start_ts_ms:
        if close == state.close:
            return receipt
        raise BTCRegimeContractError("conflicting_regime_duplicate")
    if start < state.last_bar_start_ts_ms:
        raise BTCRegimeContractError("out_of_order_regime_bar")
    if start != state.last_bar_start_ts_ms + H1_MS:
        raise BTCRegimeContractError("gap_in_regime_history")
    alpha = Decimal("2") / Decimal(EMA_PERIOD + 1)
    ema200 = close * alpha + state.ema200 * (Decimal("1") - alpha)
    updated = BTCRegimeState(
        seed_bar_start_ts_ms=state.seed_bar_start_ts_ms,
        seed_close=state.seed_close,
        last_bar_start_ts_ms=start,
        last_closed_h1_ts_ms=start + H1_MS,
        close=close,
        ema200=ema200,
        observation_count=state.observation_count + 1,
        history_hash=_history_advance(state.history_hash, row_hash, state.observation_count + 1),
        last_row_hash=row_hash,
        source_provenance=dict(state.source_provenance),
        data_provenance=dict(state.data_provenance),
    )
    updated._validate()
    return BTCRegimeReceipt(state=updated)


def regime_evidence(
    receipt: BTCRegimeReceipt, *, observed_at_ms: object, max_age_ms: object
) -> ClosedH1RegimeEvidence:
    """Return existing-gate evidence after checking freshness at decision time."""

    receipt = _validated_receipt(receipt)
    return _evidence(receipt, observed_at_ms, max_age_ms)


def _load_btc_h1_regime_unlocked(target: Path) -> BTCRegimeReceipt:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd: int | None = None
    try:
        fd = os.open(target, flags)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise BTCRegimeContractError("state_file_not_regular")
        if stat.S_IMODE(info.st_mode) != STATE_FILE_MODE:
            raise BTCRegimeContractError("state_file_mode")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
    except FileNotFoundError as exc:
        raise BTCRegimeContractError("state_file_unreadable") from exc
    except OSError as exc:
        raise BTCRegimeContractError("state_file_unreadable") from exc
    finally:
        if fd is not None:
            os.close(fd)
    try:
        raw = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BTCRegimeContractError("state_file_invalid_json") from exc
    if not isinstance(raw, Mapping):
        raise BTCRegimeContractError("invalid_receipt")
    return BTCRegimeReceipt.from_dict(raw)


def _same_lineage(previous: BTCRegimeReceipt, incoming: BTCRegimeReceipt) -> bool:
    old = previous.state
    new = incoming.state
    if (
        new.seed_bar_start_ts_ms != old.seed_bar_start_ts_ms
        or new.seed_close != old.seed_close
        or new.last_bar_start_ts_ms != old.last_bar_start_ts_ms + H1_MS
        or new.observation_count != old.observation_count + 1
        or dict(new.source_provenance) != dict(old.source_provenance)
        or dict(new.data_provenance) != dict(old.data_provenance)
        or new.history_hash
        != _history_advance(old.history_hash, new.last_row_hash, new.observation_count)
    ):
        return False
    alpha = Decimal("2") / Decimal(EMA_PERIOD + 1)
    expected_ema = new.close * alpha + old.ema200 * (Decimal("1") - alpha)
    return new.ema200 == expected_ema


def _atomic_write_receipt(target: Path, receipt: BTCRegimeReceipt) -> None:
    payload = _canonical(receipt.to_dict(), "receipt") + b"\n"
    fd: int | None = None
    temporary: str | None = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
        os.fchmod(fd, STATE_FILE_MODE)
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:  # pragma: no cover - os.write either progresses or raises
                raise OSError("short state write")
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.replace(temporary, target)
        temporary = None
        os.chmod(target, STATE_FILE_MODE)
        directory_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise BTCRegimeContractError("atomic_state_persist_failed") from exc
    finally:
        if fd is not None:
            os.close(fd)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def persist_btc_h1_regime(
    path: Path | str,
    receipt: BTCRegimeReceipt,
    *,
    expected_previous_receipt_sha256: str | None = None,
) -> None:
    """CAS-persist a monotonic research-only receipt under a stable lock."""

    receipt = _validated_receipt(receipt)
    expected = (
        None
        if expected_previous_receipt_sha256 is None
        else _sha256_hex(
            expected_previous_receipt_sha256,
            "expected_previous_receipt_sha256",
        )
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(f".{target.name}.lock")
    lock_flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    lock_fd: int | None = None
    try:
        lock_fd = os.open(lock_path, lock_flags, STATE_FILE_MODE)
        lock_info = os.fstat(lock_fd)
        if not stat.S_ISREG(lock_info.st_mode):
            raise BTCRegimeContractError("state_lock_not_regular")
        os.fchmod(lock_fd, STATE_FILE_MODE)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        existing: BTCRegimeReceipt | None
        try:
            existing = _load_btc_h1_regime_unlocked(target)
        except BTCRegimeContractError as exc:
            if exc.code != "state_file_unreadable" or os.path.lexists(target):
                raise
            existing = None

        if existing is None:
            if expected is not None:
                raise BTCRegimeContractError("state_compare_and_swap_failed")
        else:
            old = existing.state
            new = receipt.state
            if new.last_bar_start_ts_ms < old.last_bar_start_ts_ms:
                raise BTCRegimeContractError("state_rollback_forbidden")
            if receipt.receipt_sha256 == existing.receipt_sha256:
                return
            if expected is None:
                raise BTCRegimeContractError("state_compare_and_swap_required")
            if expected != existing.receipt_sha256:
                raise BTCRegimeContractError("state_compare_and_swap_failed")
            if new.last_bar_start_ts_ms == old.last_bar_start_ts_ms:
                raise BTCRegimeContractError("state_same_bar_conflict")
            if not _same_lineage(existing, receipt):
                raise BTCRegimeContractError("state_lineage_mismatch")

        _atomic_write_receipt(target, receipt)
    except OSError as exc:
        raise BTCRegimeContractError("state_lock_failed") from exc
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)


def load_btc_h1_regime(path: Path | str) -> BTCRegimeReceipt:
    """Load and verify a 0600 receipt, including envelope and state hashes."""
    return _load_btc_h1_regime_unlocked(Path(path))


__all__ = [
    "BTCRegimeContractError",
    "BTCRegimeReceipt",
    "BTCRegimeState",
    "MIN_BOOTSTRAP_BARS",
    "RECEIPT_SCHEMA_ID",
    "STATE_SCHEMA_ID",
    "advance_btc_h1_regime",
    "bootstrap_btc_h1_regime",
    "load_btc_h1_regime",
    "persist_btc_h1_regime",
    "regime_evidence",
]
