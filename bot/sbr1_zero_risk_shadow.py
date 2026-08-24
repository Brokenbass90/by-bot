"""Durable, default-off primitives for the prospective SBR1 public shadow.

This module deliberately has no HTTP, broker, account, position, order, key,
environment, or daemon imports.  A separate caller may provide public closed
Bybit rows, but this boundary can only produce research receipts.  It cannot
size or submit a position.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
from typing import Mapping, Sequence

from bot.live_native_decision_contract import (
    ActualFill,
    ContractViolation,
    FillRebasePolicy,
    LiveNativeDecisionPlan,
    rebase_targets_once,
    round_price_to_tick,
    time_stop_deadline_ms,
    validate_fill_before_rebase,
)
from bot.live_native_fill_adapter import adapt_next_open_replay_fill
from bot.live_native_regime_gate import (
    ClosedH1EMA200RegimeGate,
    classify_deviation,
)


SHADOW_ENABLED_BY_DEFAULT = False
CONFIG_SCHEMA_ID = "sbr1_zero_risk_shadow_config_v1"
EVENT_SCHEMA_ID = "sbr1_zero_risk_shadow_event_v1"
AUTHORITY = "zero_risk_public_shadow_no_orders_no_money_no_promotion"
M5_MS = 5 * 60 * 1000
_SHA256 = re.compile(r"[0-9a-f]{64}")


class ShadowViolation(ValueError):
    """Stable fail-closed error raised by the zero-risk shadow boundary."""


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
        raise ShadowViolation("noncanonical_shadow_payload") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_text(value: object, field: str) -> str:
    result = str(value or "").strip()
    if _SHA256.fullmatch(result) is None:
        raise ShadowViolation(f"invalid_sha256:{field}")
    return result


def _strict_int(value: object, field: str) -> int:
    if isinstance(value, bool) or isinstance(value, float):
        raise ShadowViolation(f"invalid_integer:{field}")
    if isinstance(value, int):
        result = value
    else:
        try:
            number = Decimal(str(value).strip())
        except (InvalidOperation, AttributeError, ValueError) as exc:
            raise ShadowViolation(f"invalid_integer:{field}") from exc
        if not number.is_finite() or number != number.to_integral_value():
            raise ShadowViolation(f"invalid_integer:{field}")
        result = int(number)
    return result


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ShadowViolation(f"invalid_decimal:{field}")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ShadowViolation(f"invalid_decimal:{field}") from exc
    if not result.is_finite():
        raise ShadowViolation(f"invalid_decimal:{field}")
    return result


def _decimal_text(value: object, field: str) -> str:
    number = _decimal(value, field)
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


def _relative_path(value: object, field: str) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or raw.startswith("../") or "/../" in raw:
        raise ShadowViolation(f"unsafe_path:{field}")
    return raw


@dataclass(frozen=True)
class ZeroRiskShadowConfig:
    """Explicit public-only config.  The repository copy must stay disabled."""

    enabled: bool
    authority: str
    public_base: str
    universe: tuple[str, ...]
    parity_manifest_path: str
    expected_parity_manifest_sha256: str
    journal_path: str
    max_decision_age_ms: int
    max_regime_age_ms: int
    h1_history_limit: int
    max_m5_pages: int
    request_timeout_seconds: Decimal
    entry_slippage_bps: Decimal
    exit_slippage_bps: Decimal
    fee_bps_per_side: Decimal
    regime_bootstrap_bars: int
    max_open_slots_total: int
    max_open_slots_sbr1: int
    max_open_slots_per_cluster: int
    symbol_clusters: Mapping[str, str]
    source_closure: Mapping[str, str]
    shadow_risk_fraction_per_slot: Decimal
    max_cluster_risk_fraction: Decimal

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "ZeroRiskShadowConfig":
        if not isinstance(raw, Mapping):
            raise ShadowViolation("config_not_object")
        required = {
            "schema_id",
            "enabled",
            "authority",
            "money_authority",
            "orders_allowed",
            "private_api_allowed",
            "release_or_promotion_authority",
            "sealed_data_allowed",
            "public_base",
            "universe",
            "parity_manifest_path",
            "expected_parity_manifest_sha256",
            "journal_path",
            "max_decision_age_ms",
            "max_regime_age_ms",
            "h1_history_limit",
            "max_m5_pages",
            "request_timeout_seconds",
            "entry_slippage_bps",
            "exit_slippage_bps",
            "fee_bps_per_side",
            "regime_bootstrap_bars",
            "max_open_slots_total",
            "max_open_slots_sbr1",
            "max_open_slots_per_cluster",
            "symbol_clusters",
            "source_closure",
            "shadow_risk_fraction_per_slot",
            "max_cluster_risk_fraction",
        }
        if set(raw) != required:
            raise ShadowViolation("config_fields_mismatch")
        if raw.get("schema_id") != CONFIG_SCHEMA_ID:
            raise ShadowViolation("wrong_config_schema")
        if not isinstance(raw.get("enabled"), bool):
            raise ShadowViolation("enabled_not_boolean")
        if raw.get("authority") != AUTHORITY:
            raise ShadowViolation("wrong_shadow_authority")
        for field in (
            "money_authority",
            "orders_allowed",
            "private_api_allowed",
            "release_or_promotion_authority",
            "sealed_data_allowed",
        ):
            if raw.get(field) is not False:
                raise ShadowViolation(f"unsafe_authority:{field}")
        if str(raw.get("public_base") or "").strip() != "https://api.bybit.com":
            raise ShadowViolation("unapproved_public_base")
        universe_raw = raw.get("universe")
        if not isinstance(universe_raw, list) or not universe_raw:
            raise ShadowViolation("invalid_universe")
        universe = tuple(str(value or "").strip().upper() for value in universe_raw)
        if (
            any(re.fullmatch(r"[A-Z0-9]{3,20}USDT", value) is None for value in universe)
            or len(set(universe)) != len(universe)
            or "BTCUSDT" not in universe
        ):
            raise ShadowViolation("invalid_universe")
        max_decision_age = _strict_int(raw.get("max_decision_age_ms"), "max_decision_age_ms")
        max_regime_age = _strict_int(raw.get("max_regime_age_ms"), "max_regime_age_ms")
        history_limit = _strict_int(raw.get("h1_history_limit"), "h1_history_limit")
        max_pages = _strict_int(raw.get("max_m5_pages"), "max_m5_pages")
        timeout = _decimal(raw.get("request_timeout_seconds"), "request_timeout_seconds")
        entry_slip = _decimal(raw.get("entry_slippage_bps"), "entry_slippage_bps")
        exit_slip = _decimal(raw.get("exit_slippage_bps"), "exit_slippage_bps")
        fee = _decimal(raw.get("fee_bps_per_side"), "fee_bps_per_side")
        shadow_risk = _decimal(
            raw.get("shadow_risk_fraction_per_slot"),
            "shadow_risk_fraction_per_slot",
        )
        max_cluster_risk = _decimal(
            raw.get("max_cluster_risk_fraction"), "max_cluster_risk_fraction"
        )
        bootstrap_bars = _strict_int(raw.get("regime_bootstrap_bars"), "regime_bootstrap_bars")
        max_total = _strict_int(raw.get("max_open_slots_total"), "max_open_slots_total")
        max_sbr1 = _strict_int(raw.get("max_open_slots_sbr1"), "max_open_slots_sbr1")
        max_cluster = _strict_int(
            raw.get("max_open_slots_per_cluster"), "max_open_slots_per_cluster"
        )
        if not 1 <= max_decision_age <= 300_000:
            raise ShadowViolation("unsafe_max_decision_age")
        if not 1 <= max_regime_age <= 300_000:
            raise ShadowViolation("unsafe_max_regime_age")
        if not 220 <= history_limit <= 1000:
            raise ShadowViolation("unsafe_h1_history_limit")
        if not 3 <= max_pages <= 8:
            raise ShadowViolation("unsafe_max_m5_pages")
        if timeout <= 0 or timeout > 30:
            raise ShadowViolation("unsafe_request_timeout")
        if min(entry_slip, exit_slip, fee) < 0:
            raise ShadowViolation("negative_cost")
        if not Decimal("0") < shadow_risk <= Decimal("0.02"):
            raise ShadowViolation("unsafe_shadow_risk_fraction")
        if not Decimal("0") < max_cluster_risk <= Decimal("0.04"):
            raise ShadowViolation("unsafe_cluster_risk_fraction")
        if not 500 <= bootstrap_bars <= 1000:
            raise ShadowViolation("unsafe_regime_bootstrap_bars")
        if not 1 <= max_cluster <= max_sbr1 <= max_total <= 12:
            raise ShadowViolation("unsafe_shadow_slot_limits")
        if Decimal(max_cluster) * shadow_risk > max_cluster_risk:
            raise ShadowViolation("cluster_slot_risk_exceeds_limit")
        clusters_raw = raw.get("symbol_clusters")
        if not isinstance(clusters_raw, Mapping) or set(clusters_raw) != set(universe):
            raise ShadowViolation("invalid_symbol_clusters")
        clusters = {
            symbol: str(clusters_raw.get(symbol) or "").strip().lower()
            for symbol in universe
        }
        if any(re.fullmatch(r"[a-z0-9_-]{1,32}", value) is None for value in clusters.values()):
            raise ShadowViolation("invalid_symbol_clusters")
        closure_raw = raw.get("source_closure")
        required_closure = {
            "strategies/sloped_break_retest_v1.py",
            "strategies/sbr1_live.py",
            "strategies/live_kline_utils.py",
            "strategies/signals.py",
            "bot/live_native_decision_contract.py",
            "bot/live_native_fill_adapter.py",
            "bot/live_native_regime_gate.py",
            "bot/live_native_manifest.py",
            "bot/live_native_signal_adapters.py",
            "bot/sbr1_zero_risk_shadow.py",
            "scripts/run_sbr1_zero_risk_shadow.py",
            "deploy/systemd/sbr1-zero-risk-shadow.service",
            "deploy/systemd/sbr1-zero-risk-shadow.timer",
        }
        if not isinstance(closure_raw, Mapping) or set(closure_raw) != required_closure:
            raise ShadowViolation("source_closure_mismatch")
        closure = {
            path: _sha256_text(closure_raw[path], f"source_closure:{path}")
            for path in sorted(required_closure)
        }
        return cls(
            enabled=bool(raw["enabled"]),
            authority=AUTHORITY,
            public_base="https://api.bybit.com",
            universe=universe,
            parity_manifest_path=_relative_path(raw.get("parity_manifest_path"), "parity_manifest_path"),
            expected_parity_manifest_sha256=_sha256_text(
                raw.get("expected_parity_manifest_sha256"),
                "expected_parity_manifest_sha256",
            ),
            journal_path=_relative_path(raw.get("journal_path"), "journal_path"),
            max_decision_age_ms=max_decision_age,
            max_regime_age_ms=max_regime_age,
            h1_history_limit=history_limit,
            max_m5_pages=max_pages,
            request_timeout_seconds=timeout,
            entry_slippage_bps=entry_slip,
            exit_slippage_bps=exit_slip,
            fee_bps_per_side=fee,
            regime_bootstrap_bars=bootstrap_bars,
            max_open_slots_total=max_total,
            max_open_slots_sbr1=max_sbr1,
            max_open_slots_per_cluster=max_cluster,
            symbol_clusters=clusters,
            source_closure=closure,
            shadow_risk_fraction_per_slot=shadow_risk,
            max_cluster_risk_fraction=max_cluster_risk,
        )

    @property
    def config_hash(self) -> str:
        return _sha(
            {
                "authority": self.authority,
                "enabled": self.enabled,
                "entry_slippage_bps": _decimal_text(self.entry_slippage_bps, "entry_slippage_bps"),
                "exit_slippage_bps": _decimal_text(self.exit_slippage_bps, "exit_slippage_bps"),
                "expected_parity_manifest_sha256": self.expected_parity_manifest_sha256,
                "fee_bps_per_side": _decimal_text(self.fee_bps_per_side, "fee_bps_per_side"),
                "h1_history_limit": self.h1_history_limit,
                "journal_path": self.journal_path,
                "max_decision_age_ms": self.max_decision_age_ms,
                "max_m5_pages": self.max_m5_pages,
                "max_regime_age_ms": self.max_regime_age_ms,
                "max_open_slots_per_cluster": self.max_open_slots_per_cluster,
                "max_open_slots_sbr1": self.max_open_slots_sbr1,
                "max_open_slots_total": self.max_open_slots_total,
                "max_cluster_risk_fraction": _decimal_text(
                    self.max_cluster_risk_fraction, "max_cluster_risk_fraction"
                ),
                "parity_manifest_path": self.parity_manifest_path,
                "public_base": self.public_base,
                "request_timeout_seconds": _decimal_text(
                    self.request_timeout_seconds, "request_timeout_seconds"
                ),
                "schema_id": CONFIG_SCHEMA_ID,
                "regime_bootstrap_bars": self.regime_bootstrap_bars,
                "source_closure": dict(self.source_closure),
                "shadow_risk_fraction_per_slot": _decimal_text(
                    self.shadow_risk_fraction_per_slot,
                    "shadow_risk_fraction_per_slot",
                ),
                "symbol_clusters": dict(self.symbol_clusters),
                "universe": list(self.universe),
            }
        )


def load_config(path: Path) -> ZeroRiskShadowConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShadowViolation("config_unreadable") from exc
    return ZeroRiskShadowConfig.from_mapping(raw)


def verify_source_closure(root: Path, config: ZeroRiskShadowConfig) -> str:
    """Verify every runtime-reachable strategy/adapter helper byte-for-byte."""

    rows: list[dict[str, str]] = []
    root = root.resolve()
    for relative, expected in sorted(config.source_closure.items()):
        path = root / _relative_path(relative, "source_closure")
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ShadowViolation(f"source_closure_unreadable:{relative}") from exc
        if actual != expected:
            raise ShadowViolation(f"source_closure_hash_mismatch:{relative}")
        rows.append({"path": relative, "sha256": actual})
    return _sha({"files": rows, "schema_id": "sbr1_shadow_source_closure_v1"})


@dataclass(frozen=True)
class CausalEmaRegimeState:
    """Persistable EMA state seeded once and advanced one closed H1 at a time."""

    seed_bar_start_ts_ms: int
    seed_close: Decimal
    bar_start_ts_ms: int
    closed_h1_ts_ms: int
    close: Decimal
    ema200: Decimal
    observation_count: int
    history_hash: str

    @property
    def deviation(self) -> Decimal:
        return (self.close - self.ema200) / self.ema200

    @property
    def value(self) -> str:
        return classify_deviation(self.deviation)

    def allows_sbr1(self) -> bool:
        return self.value == "flat_up"

    def to_dict(self) -> dict[str, object]:
        return {
            "bar_start_ts_ms": self.bar_start_ts_ms,
            "close": _decimal_text(self.close, "close"),
            "closed_h1_ts_ms": self.closed_h1_ts_ms,
            "deviation": _decimal_text(self.deviation, "deviation"),
            "ema200": _decimal_text(self.ema200, "ema200"),
            "history_hash": self.history_hash,
            "observation_count": self.observation_count,
            "seed_bar_start_ts_ms": self.seed_bar_start_ts_ms,
            "seed_close": _decimal_text(self.seed_close, "seed_close"),
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "CausalEmaRegimeState":
        state = cls(
            seed_bar_start_ts_ms=_strict_int(
                raw.get("seed_bar_start_ts_ms"), "seed_bar_start_ts_ms"
            ),
            seed_close=_decimal(raw.get("seed_close"), "seed_close"),
            bar_start_ts_ms=_strict_int(raw.get("bar_start_ts_ms"), "bar_start_ts_ms"),
            closed_h1_ts_ms=_strict_int(raw.get("closed_h1_ts_ms"), "closed_h1_ts_ms"),
            close=_decimal(raw.get("close"), "close"),
            ema200=_decimal(raw.get("ema200"), "ema200"),
            observation_count=_strict_int(raw.get("observation_count"), "observation_count"),
            history_hash=_sha256_text(raw.get("history_hash"), "history_hash"),
        )
        if raw.get("value") != state.value or _decimal(raw.get("deviation"), "deviation") != state.deviation:
            raise ShadowViolation("persisted_regime_state_mismatch")
        state._validate()
        return state

    def _validate(self) -> None:
        if (
            self.seed_bar_start_ts_ms <= 0
            or self.seed_bar_start_ts_ms % 3_600_000 != 0
            or self.bar_start_ts_ms < self.seed_bar_start_ts_ms
            or self.bar_start_ts_ms % 3_600_000 != 0
            or self.closed_h1_ts_ms != self.bar_start_ts_ms + 3_600_000
            or min(self.seed_close, self.close, self.ema200) <= 0
            or self.observation_count < 1
        ):
            raise ShadowViolation("invalid_regime_state")


def bootstrap_causal_ema(rows: Sequence[Sequence[object]]) -> CausalEmaRegimeState:
    """Seed EMA from the first explicit close in a long contiguous history."""

    if isinstance(rows, (str, bytes)) or len(rows) < 500:
        raise ShadowViolation("insufficient_regime_bootstrap_history")
    alpha = Decimal("2") / Decimal("201")
    starts: list[int] = []
    closes: list[Decimal] = []
    for raw in rows:
        if isinstance(raw, (str, bytes)) or len(raw) < 5:
            raise ShadowViolation("invalid_regime_bootstrap_row")
        start = _strict_int(raw[0], "bar_start_ts_ms")
        close = _decimal(raw[4], "close")
        if start <= 0 or start % 3_600_000 != 0 or close <= 0:
            raise ShadowViolation("invalid_regime_bootstrap_row")
        if starts and start != starts[-1] + 3_600_000:
            raise ShadowViolation("noncontiguous_regime_bootstrap")
        starts.append(start)
        closes.append(close)
    result = closes[0]
    for close in closes[1:]:
        result = close * alpha + result * (Decimal("1") - alpha)
    state = CausalEmaRegimeState(
        seed_bar_start_ts_ms=starts[0],
        seed_close=closes[0],
        bar_start_ts_ms=starts[-1],
        closed_h1_ts_ms=starts[-1] + 3_600_000,
        close=closes[-1],
        ema200=result,
        observation_count=len(rows),
        history_hash=_sha(
            {"rows": [list(row) for row in rows], "schema_id": "causal_ema_bootstrap_v1"}
        ),
    )
    state._validate()
    shared_gate = ClosedH1EMA200RegimeGate(200)
    shared_evidence = None
    for row in rows:
        row_close = _strict_int(row[0], "bar_start_ts_ms") + 3_600_000
        shared_evidence = shared_gate.update(
            row,
            observed_at_ms=row_close,
            max_age_ms=3_600_000,
        )
    if (
        shared_evidence is None
        or shared_evidence.seed_start_ts_ms != state.seed_bar_start_ts_ms
        or shared_evidence.history_bars != state.observation_count
        or shared_evidence.ema200 != state.ema200
        or shared_evidence.value != state.value
    ):
        raise ShadowViolation("shared_regime_gate_bootstrap_mismatch")
    return state


def advance_causal_ema(
    state: CausalEmaRegimeState, row: Sequence[object]
) -> CausalEmaRegimeState:
    if not isinstance(state, CausalEmaRegimeState):
        raise ShadowViolation("invalid_regime_state")
    state._validate()
    if isinstance(row, (str, bytes)) or len(row) < 5:
        raise ShadowViolation("invalid_regime_update_row")
    start = _strict_int(row[0], "bar_start_ts_ms")
    close = _decimal(row[4], "close")
    if start != state.bar_start_ts_ms + 3_600_000 or close <= 0:
        raise ShadowViolation("noncausal_regime_update")
    alpha = Decimal("2") / Decimal("201")
    ema200 = close * alpha + state.ema200 * (Decimal("1") - alpha)
    updated = CausalEmaRegimeState(
        seed_bar_start_ts_ms=state.seed_bar_start_ts_ms,
        seed_close=state.seed_close,
        bar_start_ts_ms=start,
        closed_h1_ts_ms=start + 3_600_000,
        close=close,
        ema200=ema200,
        observation_count=state.observation_count + 1,
        history_hash=_sha(
            {
                "previous_history_hash": state.history_hash,
                "row": list(row),
                "schema_id": "causal_ema_update_v1",
            }
        ),
    )
    updated._validate()
    return updated


class AppendOnlyShadowJournal:
    """Hash-chained JSONL with one immutable event per claim key."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _decode(self, text: str) -> list[dict[str, object]]:
        events: list[dict[str, object]] = []
        previous = "0" * 64
        claims: dict[str, str] = {}
        for line_number, line in enumerate(text.splitlines(), start=1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ShadowViolation(f"journal_invalid_json:{line_number}") from exc
            if not isinstance(event, dict) or event.get("schema_id") != EVENT_SCHEMA_ID:
                raise ShadowViolation(f"journal_invalid_event:{line_number}")
            required = {
                "schema_id",
                "event_type",
                "claim_key",
                "payload",
                "event_id",
                "previous_event_hash",
                "event_hash",
            }
            if set(event) != required or not isinstance(event.get("payload"), dict):
                raise ShadowViolation(f"journal_event_fields_mismatch:{line_number}")
            claim = str(event.get("claim_key") or "").strip()
            event_type = str(event.get("event_type") or "").strip()
            event_id = _sha256_text(event.get("event_id"), "event_id")
            previous_hash = _sha256_text(event.get("previous_event_hash"), "previous_event_hash")
            event_hash = _sha256_text(event.get("event_hash"), "event_hash")
            if not claim or not event_type or previous_hash != previous:
                raise ShadowViolation(f"journal_chain_broken:{line_number}")
            expected_id = _sha(
                {"claim_key": claim, "event_type": event_type, "payload": event["payload"]}
            )
            if event_id != expected_id:
                raise ShadowViolation(f"journal_event_id_mismatch:{line_number}")
            expected_hash = _sha({"event_id": event_id, "previous_event_hash": previous})
            if event_hash != expected_hash:
                raise ShadowViolation(f"journal_event_hash_mismatch:{line_number}")
            if claim in claims:
                raise ShadowViolation(f"journal_duplicate_claim:{line_number}")
            claims[claim] = event_id
            events.append(event)
            previous = event_hash
        return events

    def read(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="ascii") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            return self._decode(handle.read())

    def append(self, event_type: str, claim_key: str, payload: Mapping[str, object]) -> bool:
        event_type = str(event_type or "").strip()
        claim_key = str(claim_key or "").strip()
        if not event_type or not claim_key or not isinstance(payload, Mapping):
            raise ShadowViolation("invalid_journal_append")
        normalized_payload = json.loads(_canonical_bytes(dict(payload)).decode("ascii"))
        event_id = _sha(
            {"claim_key": claim_key, "event_type": event_type, "payload": normalized_payload}
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        with self.path.open("a+", encoding="ascii") as handle:
            os.chmod(self.path, 0o600)
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            events = self._decode(handle.read())
            for event in events:
                if event["claim_key"] != claim_key:
                    continue
                if event["event_id"] == event_id:
                    return False
                raise ShadowViolation("journal_claim_conflict")
            previous = str(events[-1]["event_hash"]) if events else "0" * 64
            event_hash = _sha({"event_id": event_id, "previous_event_hash": previous})
            event = {
                "schema_id": EVENT_SCHEMA_ID,
                "event_type": event_type,
                "claim_key": claim_key,
                "payload": normalized_payload,
                "event_id": event_id,
                "previous_event_hash": previous,
                "event_hash": event_hash,
            }
            handle.seek(0, os.SEEK_END)
            handle.write(_canonical_bytes(event).decode("ascii") + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return True


def plan_from_payload(raw: Mapping[str, object], expected_decision_id: object) -> LiveNativeDecisionPlan:
    """Rebuild and revalidate a decision persisted in the journal."""

    if not isinstance(raw, Mapping):
        raise ShadowViolation("invalid_persisted_plan")
    plan = LiveNativeDecisionPlan(
        spec_id=str(raw.get("spec_id") or ""),
        sleeve_id=str(raw.get("sleeve_id") or ""),
        symbol=str(raw.get("symbol") or ""),
        side=str(raw.get("side") or ""),  # type: ignore[arg-type]
        closed_h1_ts_ms=raw.get("closed_h1_ts_ms"),  # type: ignore[arg-type]
        planned_entry=_decimal(raw.get("planned_entry"), "planned_entry"),
        frozen_sl=_decimal(raw.get("frozen_sl"), "frozen_sl"),
        planned_tps=tuple(_decimal(value, "planned_tps") for value in raw.get("planned_tps", [])),  # type: ignore[arg-type]
        tp_fractions=tuple(_decimal(value, "tp_fractions") for value in raw.get("tp_fractions", [])),  # type: ignore[arg-type]
        residual_fraction=_decimal(raw.get("residual_fraction"), "residual_fraction"),
        time_stop_hours=raw.get("time_stop_hours"),  # type: ignore[arg-type]
        config_hash=str(raw.get("config_hash") or ""),
        source_hash=str(raw.get("source_hash") or ""),
        data_hash=str(raw.get("data_hash") or ""),
    )
    if plan.decision_id != _sha256_text(expected_decision_id, "expected_decision_id"):
        raise ShadowViolation("persisted_decision_id_mismatch")
    return plan


def fill_from_payload(raw: Mapping[str, object], expected_decision_id: str) -> ActualFill:
    if not isinstance(raw, Mapping):
        raise ShadowViolation("invalid_persisted_fill")
    fill = ActualFill(
        decision_id=str(raw.get("decision_id") or ""),
        order_id=str(raw.get("order_id") or ""),
        fill_id=str(raw.get("fill_id") or ""),
        lifecycle=str(raw.get("lifecycle") or ""),  # type: ignore[arg-type]
        fill_ts_ms=raw.get("fill_ts_ms"),  # type: ignore[arg-type]
        finalized_ts_ms=raw.get("finalized_ts_ms"),  # type: ignore[arg-type]
        fill_price=_decimal(raw.get("fill_price"), "fill_price"),
        cumulative_filled_qty=_decimal(
            raw.get("cumulative_filled_qty"), "cumulative_filled_qty"
        ),
        leaves_qty=_decimal(raw.get("leaves_qty"), "leaves_qty"),
    )
    if fill.decision_id != expected_decision_id:
        raise ShadowViolation("persisted_fill_decision_mismatch")
    return fill


def policy_for_plan(plan: LiveNativeDecisionPlan, tick_size: object) -> FillRebasePolicy:
    return FillRebasePolicy(
        spec_id=plan.spec_id,
        profile_hash=plan.profile_hash,
        tick_size=_decimal(tick_size, "tick_size"),
        max_adverse_risk_expansion=Decimal("0.20"),
        max_fill_age_ms=300_000,
        max_finalize_delay_ms=60_000,
    )


@dataclass(frozen=True)
class TickNativeShadowExecution:
    """Exchange-grid geometry layered on the immutable adapter decision."""

    fill: ActualFill
    stop: Decimal
    targets: tuple[Decimal, ...]
    tick_size: Decimal
    qty_step: Decimal
    min_notional: Decimal
    adapter_candidate_fill_fingerprint: str

    def to_dict(self) -> dict[str, object]:
        return {
            "adapter_candidate_fill_fingerprint": self.adapter_candidate_fill_fingerprint,
            "fill": self.fill.fingerprint_payload(),
            "stop": _decimal_text(self.stop, "stop"),
            "targets": [_decimal_text(value, "targets") for value in self.targets],
            "tick_size": _decimal_text(self.tick_size, "tick_size"),
            "qty_step": _decimal_text(self.qty_step, "qty_step"),
            "min_notional": _decimal_text(self.min_notional, "min_notional"),
        }

    @classmethod
    def from_dict(
        cls, raw: Mapping[str, object], expected_decision_id: str
    ) -> "TickNativeShadowExecution":
        if not isinstance(raw, Mapping) or not isinstance(raw.get("fill"), Mapping):
            raise ShadowViolation("invalid_persisted_tick_execution")
        result = cls(
            fill=fill_from_payload(raw["fill"], expected_decision_id),
            stop=_decimal(raw.get("stop"), "stop"),
            targets=tuple(
                _decimal(value, "targets") for value in raw.get("targets", [])  # type: ignore[arg-type]
            ),
            tick_size=_decimal(raw.get("tick_size"), "tick_size"),
            qty_step=_decimal(raw.get("qty_step"), "qty_step"),
            min_notional=_decimal(raw.get("min_notional"), "min_notional"),
            adapter_candidate_fill_fingerprint=_sha256_text(
                raw.get("adapter_candidate_fill_fingerprint"),
                "adapter_candidate_fill_fingerprint",
            ),
        )
        if (
            len(result.targets) != 2
            or min(result.tick_size, result.qty_step, result.min_notional) <= 0
            or result.fill.cumulative_filled_qty % result.qty_step != 0
            or result.fill.fill_price * result.fill.cumulative_filled_qty
            < result.min_notional
        ):
            raise ShadowViolation("invalid_persisted_tick_execution")
        for price in (result.fill.fill_price, result.stop, *result.targets):
            if price <= 0 or price % result.tick_size != 0:
                raise ShadowViolation("invalid_persisted_tick_execution")
        return result


def tick_native_shadow_execution(
    plan: LiveNativeDecisionPlan,
    policy: FillRebasePolicy,
    next_m5_row: Sequence[object],
    *,
    row_bytes: bytes,
    adverse_slippage_bps: object,
    qty_step: object,
    min_notional: object,
) -> TickNativeShadowExecution:
    """Apply the replay adapter, then conservatively snap all prices to tick.

    The original adapter candidate is retained as evidence.  The durable
    shadow fill uses adverse rounding, the protective stop uses risk-reducing
    rounding, and targets use harder-to-hit rounding.
    """

    tick = policy.tick_size
    step = _decimal(qty_step, "qty_step")
    minimum = _decimal(min_notional, "min_notional")
    if min(step, minimum) <= 0:
        raise ShadowViolation("invalid_exchange_quantity_filter")
    raw_open = _decimal(next_m5_row[1], "next_open")
    slippage = _decimal(adverse_slippage_bps, "adverse_slippage_bps")
    direction = Decimal("1") if plan.side == "long" else Decimal("-1")
    modeled_fill = raw_open * (Decimal("1") + direction * slippage / Decimal("10000"))
    fill_direction = "up" if plan.side == "long" else "down"
    fill_price = round_price_to_tick(
        modeled_fill, tick, direction=fill_direction  # type: ignore[arg-type]
    )
    quantity = max(
        Decimal("1"),
        (minimum / (fill_price * step)).to_integral_value(rounding=ROUND_CEILING),
    ) * step
    candidate = adapt_next_open_replay_fill(
        plan,
        policy,
        next_m5_row,
        row_bytes=row_bytes,
        adverse_slippage_bps=adverse_slippage_bps,
        quantity=quantity,
    )
    stop_direction = "up" if plan.side == "long" else "down"
    target_direction = "up" if plan.side == "long" else "down"
    if candidate.fill_price != modeled_fill:
        raise ShadowViolation("adapter_candidate_fill_mismatch")
    stop = round_price_to_tick(
        plan.frozen_sl, tick, direction=stop_direction  # type: ignore[arg-type]
    )
    if (plan.side == "long" and stop >= fill_price) or (
        plan.side == "short" and stop <= fill_price
    ):
        raise ShadowViolation("tick_native_stop_on_wrong_side")
    risk = abs(fill_price - stop)
    targets = tuple(
        round_price_to_tick(
            fill_price + rr * risk if plan.side == "long" else fill_price - rr * risk,
            tick,
            direction=target_direction,  # type: ignore[arg-type]
        )
        for rr in plan.profile.nominal_rrs
    )
    if plan.side == "long":
        valid_targets = all(target > fill_price for target in targets) and all(
            left < right for left, right in zip(targets, targets[1:])
        )
    else:
        valid_targets = all(target < fill_price for target in targets) and all(
            left > right for left, right in zip(targets, targets[1:])
        )
    if not valid_targets:
        raise ShadowViolation("tick_native_target_ladder_invalid")
    identity = _sha(
        {
            "adapter_candidate_fill_fingerprint": candidate.fill_fingerprint,
            "fill_price": _decimal_text(fill_price, "fill_price"),
            "policy_fingerprint": policy.policy_fingerprint,
            "quantity": _decimal_text(quantity, "quantity"),
            "qty_step": _decimal_text(step, "qty_step"),
            "min_notional": _decimal_text(minimum, "min_notional"),
            "schema_id": "tick_native_shadow_fill_v1",
            "stop": _decimal_text(stop, "stop"),
            "targets": [_decimal_text(value, "targets") for value in targets],
        }
    )
    fill = ActualFill(
        decision_id=plan.decision_id,
        order_id=f"tick-shadow-order:{identity}",
        fill_id=f"tick-shadow-fill:{identity}",
        lifecycle="finalized",
        fill_ts_ms=candidate.fill_ts_ms,
        finalized_ts_ms=candidate.finalized_ts_ms,
        fill_price=fill_price,
        cumulative_filled_qty=candidate.cumulative_filled_qty,
        leaves_qty=candidate.leaves_qty,
    )
    validation = validate_fill_before_rebase(plan, fill, policy)
    if not validation.accepted:
        raise ContractViolation(validation.code)
    for price in (fill.fill_price, stop, *targets):
        if price % tick != 0:
            raise ShadowViolation("non_tick_native_execution_geometry")
    return TickNativeShadowExecution(
        fill=fill,
        stop=stop,
        targets=targets,
        tick_size=tick,
        qty_step=step,
        min_notional=minimum,
        adapter_candidate_fill_fingerprint=candidate.fill_fingerprint,
    )


@dataclass(frozen=True)
class ProspectiveOutcome:
    finalized: bool
    label: str
    net_r: Decimal | None
    deadline_ms: int
    rows_used: int


def evaluate_prospective_outcome(
    plan: LiveNativeDecisionPlan,
    tick_execution: TickNativeShadowExecution,
    policy: FillRebasePolicy,
    closed_m5_rows: Sequence[Sequence[object]],
    *,
    fee_bps_per_side: object,
    exit_slippage_bps: object,
) -> ProspectiveOutcome:
    """Causally score closed M5 bars, with stop-first intrabar ordering."""

    if not isinstance(tick_execution, TickNativeShadowExecution):
        raise ShadowViolation("invalid_tick_native_execution")
    fill = tick_execution.fill
    if tick_execution.tick_size != policy.tick_size or fill.decision_id != plan.decision_id:
        raise ShadowViolation("tick_execution_contract_mismatch")
    if (
        fill.cumulative_filled_qty % tick_execution.qty_step != 0
        or fill.fill_price * fill.cumulative_filled_qty < tick_execution.min_notional
    ):
        raise ShadowViolation("tick_execution_quantity_mismatch")
    expected_stop = round_price_to_tick(
        plan.frozen_sl,
        policy.tick_size,
        direction="up" if plan.side == "long" else "down",
    )
    expected_risk = abs(fill.fill_price - expected_stop)
    expected_targets = tuple(
        round_price_to_tick(
            fill.fill_price + rr * expected_risk
            if plan.side == "long"
            else fill.fill_price - rr * expected_risk,
            policy.tick_size,
            direction="up" if plan.side == "long" else "down",
        )
        for rr in plan.profile.nominal_rrs
    )
    if tick_execution.stop != expected_stop or tick_execution.targets != expected_targets:
        raise ShadowViolation("tick_execution_geometry_mismatch")
    execution = rebase_targets_once(plan, fill, policy)
    deadline = time_stop_deadline_ms(execution)
    fee_bps = _decimal(fee_bps_per_side, "fee_bps_per_side")
    exit_slip = _decimal(exit_slippage_bps, "exit_slippage_bps")
    if min(fee_bps, exit_slip) < 0:
        raise ShadowViolation("negative_outcome_cost")
    normalized: list[tuple[int, Decimal, Decimal, Decimal]] = []
    previous_ts: int | None = None
    for raw in closed_m5_rows:
        if isinstance(raw, (str, bytes)) or len(raw) < 5:
            raise ShadowViolation("invalid_outcome_m5_row")
        ts = _strict_int(raw[0], "m5_ts")
        high = _decimal(raw[2], "m5_high")
        low = _decimal(raw[3], "m5_low")
        close = _decimal(raw[4], "m5_close")
        if ts % M5_MS != 0 or min(high, low, close) <= 0 or low > high:
            raise ShadowViolation("invalid_outcome_m5_row")
        if previous_ts is not None and ts != previous_ts + M5_MS:
            raise ShadowViolation("noncontiguous_outcome_m5_rows")
        previous_ts = ts
        normalized.append((ts, high, low, close))
    if not normalized or normalized[0][0] != fill.fill_ts_ms:
        raise ShadowViolation("outcome_window_does_not_start_at_fill")

    entry = fill.fill_price
    stop = tick_execution.stop
    risk = abs(entry - stop)
    direction = Decimal("1") if plan.side == "long" else Decimal("-1")
    net_r = -(fee_bps / Decimal("10000")) * entry / risk
    remaining = Decimal("1")
    target_index = 0
    labels: list[str] = []

    def realize(price: Decimal, fraction: Decimal, label: str) -> None:
        nonlocal net_r, remaining
        exit_direction = Decimal("-1") if plan.side == "long" else Decimal("1")
        executed = price * (
            Decimal("1") + exit_direction * exit_slip / Decimal("10000")
        )
        net_r += fraction * direction * (executed - entry) / risk
        net_r -= fraction * (fee_bps / Decimal("10000")) * executed / risk
        remaining -= fraction
        labels.append(label)

    used = 0
    for ts, high, low, close in normalized:
        if ts >= deadline:
            break
        used += 1
        stop_hit = low <= stop if plan.side == "long" else high >= stop
        if stop_hit:
            realize(stop, remaining, "stop")
            return ProspectiveOutcome(True, "+".join(labels), net_r, deadline, used)
        while target_index < len(tick_execution.targets):
            target = tick_execution.targets[target_index]
            hit = high >= target if plan.side == "long" else low <= target
            if not hit:
                break
            realize(target, plan.tp_fractions[target_index], f"tp{target_index + 1}")
            target_index += 1
        if remaining <= 0:
            return ProspectiveOutcome(True, "+".join(labels), net_r, deadline, used)
        if ts == deadline - M5_MS:
            realize(close, remaining, "time_stop")
            return ProspectiveOutcome(True, "+".join(labels), net_r, deadline, used)
    return ProspectiveOutcome(False, "pending", None, deadline, used)


def outcome_rows_hash(rows: Sequence[Sequence[object]]) -> str:
    return _sha({"rows": [list(row) for row in rows], "schema_id": "sbr1_m5_path_v1"})


def shadow_slot_gate(
    config: ZeroRiskShadowConfig,
    candidate_symbol: str,
    active_symbols: Sequence[str],
) -> tuple[bool, str]:
    """Enforce the preregistered zero-risk sleeve and cluster slot limits."""

    symbol = str(candidate_symbol or "").strip().upper()
    active = tuple(str(value or "").strip().upper() for value in active_symbols)
    if symbol not in config.universe or any(value not in config.universe for value in active):
        raise ShadowViolation("slot_gate_symbol_outside_universe")
    if symbol in active:
        return False, "symbol_already_open"
    if len(active) >= config.max_open_slots_total:
        return False, "total_slots_full"
    if len(active) >= config.max_open_slots_sbr1:
        return False, "sbr1_slots_full"
    cluster = config.symbol_clusters[symbol]
    cluster_count = sum(config.symbol_clusters[value] == cluster for value in active)
    cluster_risk = Decimal(cluster_count + 1) * config.shadow_risk_fraction_per_slot
    if cluster_risk > config.max_cluster_risk_fraction:
        return False, "cluster_risk_full"
    if cluster_count >= config.max_open_slots_per_cluster:
        return False, "cluster_slots_full"
    return True, "accepted"


__all__ = [
    "AUTHORITY",
    "AppendOnlyShadowJournal",
    "CONFIG_SCHEMA_ID",
    "EVENT_SCHEMA_ID",
    "M5_MS",
    "ProspectiveOutcome",
    "SHADOW_ENABLED_BY_DEFAULT",
    "ShadowViolation",
    "ZeroRiskShadowConfig",
    "CausalEmaRegimeState",
    "TickNativeShadowExecution",
    "advance_causal_ema",
    "bootstrap_causal_ema",
    "evaluate_prospective_outcome",
    "fill_from_payload",
    "load_config",
    "outcome_rows_hash",
    "plan_from_payload",
    "policy_for_plan",
    "shadow_slot_gate",
    "tick_native_shadow_execution",
    "verify_source_closure",
]
