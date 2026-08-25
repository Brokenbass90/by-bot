#!/usr/bin/env python3
"""Collect ATT1 fixed-51 public raw decisions without execution authority.

The runner replays the real ATT1 live wrapper over a causal closed-H1 window,
but records only the latest decision. It never imports an exchange account,
broker, order client, trading monolith, or promotion surface.
"""
from __future__ import annotations

import argparse
import contextlib
import errno
import fcntl
import hashlib
import json
import os
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.att1_fixed51_shadow import (  # noqa: E402
    ACK,
    ATT1_FIXED51_UNIVERSE,
    AUTHORITY,
    ShadowViolation,
    load_config,
    preflight,
    verify_manifest,
)
from bot.att1_runtime_contract import build_att1_runtime_contract  # noqa: E402
from bot.live_native_regime_gate import closed_h1_btc_ema200_regime  # noqa: E402
from strategies.att1_live import ATT1LiveEngine  # noqa: E402

PUBLIC_HOST = "api.bybit.com"
PUBLIC_PATH = "/v5/market/kline"
H1_MS = 3_600_000
EVENT_SCHEMA_ID = "att1_fixed51_raw_shadow_event_v2"


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ShadowViolation("noncanonical_runtime_payload") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _strict_int(value: object, field: str) -> int:
    if isinstance(value, bool) or isinstance(value, float):
        raise ShadowViolation(f"invalid_integer:{field}")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ShadowViolation(f"invalid_integer:{field}") from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise ShadowViolation(f"invalid_integer:{field}")
    return int(number)


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ShadowViolation(f"invalid_closed_h1_ohlcv:{field}")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ShadowViolation(f"invalid_closed_h1_ohlcv:{field}") from exc
    if not number.is_finite():
        raise ShadowViolation(f"invalid_closed_h1_ohlcv:{field}")
    return number


def _raw_signal_payload(signal: object) -> dict[str, object] | None:
    if signal is None:
        return None
    payload = {
        "strategy": str(getattr(signal, "strategy", "") or ""),
        "symbol": str(getattr(signal, "symbol", "") or ""),
        "side": str(getattr(signal, "side", "") or ""),
        "reason": str(getattr(signal, "reason", "") or ""),
        "entry": str(getattr(signal, "entry", "") or ""),
        "sl": str(getattr(signal, "sl", "") or ""),
        "tp": str(getattr(signal, "tp", "") or ""),
        "tps": [str(value) for value in list(getattr(signal, "tps", []) or [])],
        "tp_fracs": [str(value) for value in list(getattr(signal, "tp_fracs", []) or [])],
        "time_stop_bars": getattr(signal, "time_stop_bars", None),
    }
    return json.loads(_canonical(payload))


def _public_get_bytes(url: str, *, timeout: float) -> bytes:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query, strict_parsing=True)
    if (
        parsed.scheme != "https"
        or parsed.hostname != PUBLIC_HOST
        or parsed.port not in (None, 443)
        or parsed.path != PUBLIC_PATH
        or parsed.username is not None
        or parsed.password is not None
        or set(query) - {"category", "symbol", "interval", "limit"}
        or query.get("category") != ["linear"]
        or query.get("interval") != ["60"]
    ):
        raise ShadowViolation("nonpublic_bybit_request_rejected")
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "by-bot-att1-fixed51-raw-shadow/2.0"},
    )

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ShadowViolation("public_bybit_redirect_rejected")

    with urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout) as response:
        final = urllib.parse.urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != PUBLIC_HOST or final.path != PUBLIC_PATH:
            raise ShadowViolation("public_bybit_final_url_rejected")
        body = response.read(2 * 1024 * 1024 + 1)
        if len(body) > 2 * 1024 * 1024:
            raise ShadowViolation("public_bybit_response_too_large")
        return body


def fetch_public_h1(
    base: str,
    symbol: str,
    *,
    limit: int,
    timeout: float,
    fetch: Callable[..., bytes] = _public_get_bytes,
) -> tuple[list[list[object]], int, str]:
    symbol = str(symbol or "").strip().upper()
    url = f"{base}{PUBLIC_PATH}?{urllib.parse.urlencode({'category': 'linear', 'symbol': symbol, 'interval': '60', 'limit': int(limit)})}"
    raw = fetch(url, timeout=timeout)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShadowViolation("public_kline_invalid_json") from exc
    result = payload.get("result") if isinstance(payload, Mapping) else None
    rows = result.get("list") if isinstance(result, Mapping) else None
    observed = _strict_int(payload.get("time"), "bybit_observed_at_ms") if isinstance(payload, Mapping) else 0
    if not isinstance(rows, list) or not rows or payload.get("retCode") != 0 or observed <= 0:
        raise ShadowViolation("public_kline_missing_result")
    normalized: list[list[object]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            raise ShadowViolation("public_kline_invalid_row")
        normalized.append(list(row))
    normalized.sort(key=lambda row: _strict_int(row[0], "bar_start_ts_ms"))
    return normalized, observed, hashlib.sha256(raw).hexdigest()


def validate_closed_h1_window(
    rows: Sequence[Sequence[object]],
    *,
    observed_at_ms: object,
    max_age_ms: int,
    min_bars: int,
) -> list[list[object]]:
    """Return a validated causal closed-H1 prefix and reject any used gap."""

    observed = _strict_int(observed_at_ms, "observed_at_ms")
    if observed <= 0 or max_age_ms <= 0 or min_bars < 2:
        raise ShadowViolation("invalid_closed_h1_boundary")
    closed: list[list[object]] = []
    previous_start: int | None = None
    for raw_row in rows:
        if isinstance(raw_row, (str, bytes)) or len(raw_row) < 6:
            raise ShadowViolation("invalid_closed_h1_row")
        row = list(raw_row)
        start = _strict_int(row[0], "bar_start_ts_ms")
        if start <= 0 or start % H1_MS != 0:
            raise ShadowViolation("h1_bar_start_not_aligned")
        if start + H1_MS > observed:
            continue
        if previous_start is not None and start != previous_start + H1_MS:
            raise ShadowViolation("noncontiguous_closed_h1_rows")
        previous_start = start
        open_, high, low, close, volume = (
            _decimal(row[1], "open"),
            _decimal(row[2], "high"),
            _decimal(row[3], "low"),
            _decimal(row[4], "close"),
            _decimal(row[5], "volume"),
        )
        if min(open_, high, low, close) <= 0 or volume < 0:
            raise ShadowViolation("invalid_closed_h1_ohlcv")
        if high < max(open_, close) or low > min(open_, close) or low > high:
            raise ShadowViolation("incoherent_closed_h1_ohlc")
        closed.append(row)
    if len(closed) < min_bars:
        raise ShadowViolation("public_h1_history_short")
    latest_close = _strict_int(closed[-1][0], "latest_bar_start_ts_ms") + H1_MS
    age = observed - latest_close
    if age < 0:
        raise ShadowViolation("latest_h1_not_closed")
    if age > max_age_ms:
        raise ShadowViolation("closed_h1_decision_too_old")
    return closed


@contextlib.contextmanager
def _frozen_att1_environment(universe: tuple[str, ...]):
    names = {
        "ATT1_ALLOW_LONGS": "0", "ATT1_ALLOW_SHORTS": "1", "ATT1_SIGNAL_TF": "60",
        "ATT1_SIGNAL_LOOKBACK": "120", "ATT1_ATR_PERIOD": "14", "ATT1_RSI_PERIOD": "14",
        "ATT1_PIVOT_LEFT": "3", "ATT1_PIVOT_RIGHT": "3", "ATT1_MIN_PIVOTS": "2",
        "ATT1_MAX_PIVOTS_USED": "3", "ATT1_MAX_PIVOT_AGE": "16", "ATT1_MIN_SLOPE_PCT": "0.03",
        "ATT1_MAX_SLOPE_PCT": "4.0", "ATT1_LONG_MAX_NEG_SLOPE": "0.5", "ATT1_SHORT_MAX_POS_SLOPE": "0.5",
        "ATT1_MIN_R2": "0.80", "ATT1_TOUCH_ATR": "0.35", "ATT1_REJECT_ATR": "0.08",
        "ATT1_MIN_BODY_FRAC": "0.20", "ATT1_RSI_LONG_MAX": "55", "ATT1_RSI_SHORT_MIN": "45",
        "ATT1_RSI_SHORT_MAX": "100", "ATT1_TREND_GUARD_BARS": "0", "ATT1_GEOMETRY_V2_ENABLE": "0",
        "ATT1_GEOMETRY_V2_OBSERVE": "0", "ATT1_G2_MIN_DESC_SLOPE": "0.03", "ATT1_G2_MIN_R2": "0.65",
        "ATT1_G2_MAX_ENTRY_DIST_ATR": "0.75", "ATT1_G2_MAX_TOUCH_MISS_ATR": "0.10",
        "ATT1_G2_MIN_ROOM_R": "0.80", "ATT1_G2_PROFILE": "all", "ATT1_SL_ATR_MULT": "6.6",
        "ATT1_MAX_ENTRY_DIST_ATR": "2.0", "ATT1_MIN_ENTRY_DIST_ATR": "0", "ATT1_MIN_RR": "1.15",
        "ATT1_MIN_STOP_PCT": "0.0015", "ATT1_MAX_STOP_PCT": "0.25", "ATT1_TP1_RR": "1.2",
        "ATT1_TP2_RR": "2.5", "ATT1_TP1_FRAC": "0.55", "ATT1_BE_TRIGGER_RR": "0",
        "ATT1_BE_LOCK_RR": "0.02", "ATT1_TRAIL_ATR_MULT": "0", "ATT1_TRAIL_ACTIVATE_RR": "1",
        "ATT1_TIME_STOP_BARS_5M": "4032", "ATT1_COOLDOWN_BARS_5M": "96",
        "ATT1_SYMBOL_ALLOWLIST": ",".join(universe), "ATT1_SYMBOL_DENYLIST": "", "ATT1_CANARY_EXPIRY_UTC": "",
    }
    previous = {name: os.environ.get(name) for name in names}
    try:
        os.environ.update(names)
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def replay_att1_latest(
    symbol: str,
    closed_rows: Sequence[Sequence[object]],
    *,
    signal_lookback: int,
) -> dict[str, object]:
    """Causally rebuild ATT1 first-bar/cooldown state; return only latest."""

    rows = [list(row) for row in closed_rows]
    symbol = str(symbol).upper()
    if signal_lookback < 2 or len(rows) < signal_lookback + 1:
        raise ShadowViolation("att1_replay_history_short")
    active_end = signal_lookback

    def replay_fetch(request_symbol: str, interval: str, limit: int) -> list[list[object]]:
        if str(request_symbol).upper() != symbol or str(interval) != "60":
            raise ShadowViolation("att1_replay_fetch_contract_mismatch")
        return rows[:active_end][-max(1, int(limit)):]

    engine = ATT1LiveEngine(replay_fetch)
    final_signal = None
    final_reason = ""
    evaluations = 0
    for index in range(signal_lookback - 1, len(rows)):
        active_end = index + 1
        row = rows[index]
        close_ts = _strict_int(row[0], "replay_bar_start_ts_ms") + H1_MS
        final_signal = engine.signal(
            symbol,
            close_ts,
            float(row[1]),
            float(row[2]),
            float(row[3]),
            float(row[4]),
            float(row[5]),
        )
        final_reason = "" if final_signal is not None else str(engine.last_no_signal_reason(symbol) or "unknown_no_signal")
        evaluations += 1
    consumed = engine.last_closed_rows(symbol)
    if len(consumed) != signal_lookback:
        raise ShadowViolation("att1_replay_consumed_rows_mismatch")
    decision_latest_start = _strict_int(rows[-1][0], "decision_latest_start_ts_ms")
    consumed_latest_start = _strict_int(
        consumed[-1][0], "consumed_latest_start_ts_ms"
    )
    consumed_is_latest = consumed == rows[-signal_lookback:]
    if not consumed_is_latest:
        # The real wrapper deliberately returns before fetching klines while
        # its post-signal cooldown is active.  That is a causal no-signal, not
        # a data-integrity error.  Prove that the retained consumed window is
        # an exact historical prefix and report the lag explicitly.
        if final_reason != "cooldown" or consumed_latest_start >= decision_latest_start:
            raise ShadowViolation("att1_replay_consumed_rows_mismatch")
        matching_end = next(
            (
                index
                for index, row in enumerate(rows)
                if _strict_int(row[0], "replay_prefix_start_ts_ms")
                == consumed_latest_start
            ),
            None,
        )
        if (
            matching_end is None
            or matching_end + 1 < signal_lookback
            or consumed
            != rows[matching_end + 1 - signal_lookback : matching_end + 1]
        ):
            raise ShadowViolation("att1_replay_consumed_rows_mismatch")
    if final_signal is None and final_reason in {"", "first_signal_bar", "same_signal_bar"}:
        raise ShadowViolation("att1_replay_not_causal")
    return {
        "raw_signal": _raw_signal_payload(final_signal),
        "no_signal_reason": final_reason,
        "replay_evaluations": evaluations,
        "consumed_rows_sha256": _sha(consumed),
        "consumed_is_latest_window": consumed_is_latest,
        "consumed_latest_start_ts_ms": consumed_latest_start,
        "decision_latest_start_ts_ms": decision_latest_start,
    }


def _assert_secure_parent(path: Path, root: Path) -> None:
    root = root.resolve(strict=True)
    path = Path(path)
    try:
        relative_parent = path.parent.relative_to(root)
    except ValueError as exc:
        raise ShadowViolation("journal_outside_root") from exc
    cursor = root
    for part in relative_parent.parts:
        cursor = cursor / part
        if cursor.exists() or cursor.is_symlink():
            if cursor.is_symlink():
                raise ShadowViolation("journal_parent_symlink_rejected")
        else:
            cursor.mkdir(mode=0o700)
        os.chmod(cursor, 0o700)
    parent_real = path.parent.resolve(strict=True)
    if parent_real != root and root not in parent_real.parents:
        raise ShadowViolation("journal_outside_root")


class _LockedJournal:
    """O_NOFOLLOW, mode-0600, nonblocking-lock, hash-chained journal."""

    def __init__(self, path: Path, *, root: Path):
        self.path = Path(path)
        self.root = Path(root)
        self.handle = None
        self.previous = "0" * 64
        self.claims: dict[str, tuple[str, str]] = {}
        self.events = 0

    def __enter__(self):
        _assert_secure_parent(self.path, self.root)
        if self.path.is_symlink():
            raise ShadowViolation("journal_symlink_rejected")
        flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self.path, flags, 0o600)
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.EMLINK}:
                raise ShadowViolation("journal_symlink_rejected") from exc
            raise ShadowViolation("journal_open_failed") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ShadowViolation("journal_not_regular_file")
            os.fchmod(fd, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ShadowViolation("journal_lock_busy") from exc
            self.handle = os.fdopen(fd, "a+", encoding="ascii", newline="\n")
            fd = -1
            self.handle.seek(0)
            for line_number, line in enumerate(self.handle.read().splitlines(), start=1):
                try:
                    old = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ShadowViolation(f"journal_invalid_json:{line_number}") from exc
                if old.get("schema_id") != EVENT_SCHEMA_ID or old.get("previous_event_hash") != self.previous:
                    raise ShadowViolation("journal_chain_broken")
                body = {
                    "schema_id": old.get("schema_id"),
                    "event_type": old.get("event_type"),
                    "claim_key": old.get("claim_key"),
                    "identity_sha256": old.get("identity_sha256"),
                    "payload": old.get("payload"),
                    "previous_event_hash": old.get("previous_event_hash"),
                }
                event_id = _sha(body)
                event_hash = _sha({"event_id": event_id, "previous_event_hash": self.previous})
                if old.get("event_id") != event_id or old.get("event_hash") != event_hash:
                    raise ShadowViolation("journal_chain_broken")
                claim = str(old.get("claim_key") or "")
                identity = str(old.get("identity_sha256") or "")
                if not claim or len(identity) != 64 or claim in self.claims:
                    raise ShadowViolation("journal_claim_conflict")
                self.claims[claim] = (identity, event_id)
                self.previous = event_hash
                self.events += 1
            return self
        except Exception:
            if self.handle is not None:
                self.handle.close()
                self.handle = None
            elif fd >= 0:
                os.close(fd)
            raise

    def append(
        self,
        event_type: str,
        claim_key: str,
        *,
        stable_identity: Mapping[str, object],
        payload: Mapping[str, object],
    ) -> bool:
        identity = _sha(dict(stable_identity))
        existing = self.claims.get(claim_key)
        if existing is not None:
            if existing[0] == identity:
                return False
            raise ShadowViolation("journal_claim_conflict")
        normalized = json.loads(_canonical(dict(payload)))
        body = {
            "schema_id": EVENT_SCHEMA_ID,
            "event_type": str(event_type),
            "claim_key": str(claim_key),
            "identity_sha256": identity,
            "payload": normalized,
            "previous_event_hash": self.previous,
        }
        event_id = _sha(body)
        event = dict(body)
        event.update(
            {
                "event_id": event_id,
                "event_hash": _sha({"event_id": event_id, "previous_event_hash": self.previous}),
            }
        )
        assert self.handle is not None
        self.handle.seek(0, os.SEEK_END)
        self.handle.write(_canonical(event).decode("ascii") + "\n")
        self.handle.flush()
        os.fsync(self.handle.fileno())
        self.claims[claim_key] = (identity, event_id)
        self.previous = str(event["event_hash"])
        self.events += 1
        return True

    def __exit__(self, *_exc):
        if self.handle is not None:
            try:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            finally:
                self.handle.close()
                self.handle = None


def _regime_payload(
    btc_rows: Sequence[Sequence[object]],
    *,
    observed_at_ms: int,
    max_age_ms: int,
) -> dict[str, object]:
    evidence = closed_h1_btc_ema200_regime(
        btc_rows,
        observed_at_ms=observed_at_ms,
        max_age_ms=max_age_ms,
    )
    return {
        "seed_start_ts_ms": evidence.seed_start_ts_ms,
        "history_bars": evidence.history_bars,
        "bar_start_ts_ms": evidence.bar_start_ts_ms,
        "closed_h1_ts_ms": evidence.closed_h1_ts_ms,
        "observed_at_ms": evidence.observed_at_ms,
        "age_ms": evidence.age_ms,
        "close": str(evidence.close),
        "ema200": str(evidence.ema200),
        "deviation": str(evidence.deviation),
        "value": evidence.value,
        "regime_eligible": evidence.allows("ATT1"),
    }


def _base_event_payload(
    *,
    symbol: str,
    runtime_contract: Mapping[str, object],
    manifest: Mapping[str, object],
    config_sha256: str,
) -> dict[str, object]:
    return {
        "authority": AUTHORITY,
        "symbol": symbol,
        "measurement_authority": "raw_decision_only",
        "evidence_admitted": False,
        "performance_authority": False,
        "final_n_eligible": False,
        "money_authority": False,
        "orders_allowed": False,
        "private_api_allowed": False,
        "release_or_promotion_authority": False,
        "raw_signal": None,
        "no_signal_reason": "",
        "runtime_contract": runtime_contract["params"],
        "runtime_contract_sha256": runtime_contract["sha256"],
        "manifest_sha256": manifest["manifest_sha256"],
        "source_closure_sha256": manifest["source_closure_sha256"],
        "config_sha256": config_sha256,
        "closed_history_sha256": None,
        "latest_closed_row_sha256": None,
        "btc_regime_history_sha256": None,
    }


def _error_class(exc: Exception) -> str:
    if isinstance(exc, (OSError, TimeoutError, urllib.error.URLError)):
        return "public_fetch_error"
    if isinstance(exc, ShadowViolation):
        text = str(exc)
        if any(token in text for token in ("h1_", "ohlc", "history", "kline", "integer")):
            return "data_validation_error"
    return "processing_error"


def run_cycle(
    root: Path,
    config_path: Path,
    *,
    acknowledgement: str,
    fetch: Callable[..., bytes] = _public_get_bytes,
) -> dict[str, object]:
    report = preflight(root, config_path)
    config = load_config(config_path)
    if not config.enabled or acknowledgement != ACK:
        raise ShadowViolation("att1_fixed51_shadow_not_explicitly_enabled")
    manifest = verify_manifest(root, config)
    config_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()
    journal = root / config.journal_path

    with _frozen_att1_environment(config.evidence_universe):
        runtime_contract = build_att1_runtime_contract(risk_mult=0.0)
        signal_lookback = int(runtime_contract["params"]["signal_lookback"])
        if signal_lookback + 1 > config.min_replay_bars:
            raise ShadowViolation("configured_replay_cannot_restore_wrapper_state")

        btc_rows_raw, btc_observed, btc_response_sha = fetch_public_h1(
            config.public_base,
            "BTCUSDT",
            limit=config.max_h1_bars,
            timeout=15.0,
            fetch=fetch,
        )
        btc_closed = validate_closed_h1_window(
            btc_rows_raw,
            observed_at_ms=btc_observed,
            max_age_ms=config.max_decision_age_ms,
            min_bars=max(200, config.min_replay_bars),
        )
        cycle_close_ts = _strict_int(btc_closed[-1][0], "btc_latest_start") + H1_MS
        regime = _regime_payload(
            btc_closed,
            observed_at_ms=btc_observed,
            max_age_ms=config.max_decision_age_ms,
        )
        if regime["closed_h1_ts_ms"] != cycle_close_ts:
            raise ShadowViolation("btc_regime_cycle_mismatch")
        btc_history_hash = _sha(btc_closed)
        cache = {"BTCUSDT": (btc_rows_raw, btc_observed, btc_response_sha)}

        failures: list[str] = []
        expected_unavailable: list[str] = []
        failed_types: dict[str, int] = {}
        successful = 0
        written = 0

        with _LockedJournal(journal, root=root) as journal_writer:
            for symbol in config.evidence_universe:
                base = _base_event_payload(
                    symbol=symbol,
                    runtime_contract=runtime_contract,
                    manifest=manifest,
                    config_sha256=config_sha,
                )
                try:
                    raw_rows, observed, response_sha = cache.get(symbol) or fetch_public_h1(
                        config.public_base,
                        symbol,
                        limit=config.max_h1_bars,
                        timeout=15.0,
                        fetch=fetch,
                    )
                    closed = validate_closed_h1_window(
                        raw_rows,
                        observed_at_ms=observed,
                        max_age_ms=config.max_decision_age_ms,
                        min_bars=config.min_replay_bars,
                    )
                    closed_ts = _strict_int(closed[-1][0], "latest_start") + H1_MS
                    if closed_ts != cycle_close_ts:
                        raise ShadowViolation("symbol_latest_h1_cycle_mismatch")
                    replay = replay_att1_latest(symbol, closed, signal_lookback=signal_lookback)
                    raw_signal = replay["raw_signal"]
                    no_signal_reason = str(replay["no_signal_reason"] or "")
                    status = "RAW_DECISION_SHADOW_SIGNAL" if raw_signal is not None else "RAW_DECISION_SHADOW_NO_SIGNAL"
                    payload = dict(base)
                    payload.update(
                        {
                            "status": status,
                            "observed_at_ms": observed,
                            "closed_h1_ts_ms": closed_ts,
                            "response_sha256": response_sha,
                            "closed_history_sha256": _sha(closed),
                            "latest_closed_row_sha256": _sha(closed[-1]),
                            "btc_regime_history_sha256": btc_history_hash,
                            "consumed_rows_sha256": replay["consumed_rows_sha256"],
                            "consumed_is_latest_window": replay[
                                "consumed_is_latest_window"
                            ],
                            "consumed_latest_start_ts_ms": replay[
                                "consumed_latest_start_ts_ms"
                            ],
                            "decision_latest_start_ts_ms": replay[
                                "decision_latest_start_ts_ms"
                            ],
                            "replay_evaluations": replay["replay_evaluations"],
                            "raw_signal": raw_signal,
                            "no_signal_reason": no_signal_reason,
                            "regime": {key: value for key, value in regime.items() if key != "regime_eligible"},
                            "regime_eligible": regime["regime_eligible"],
                            "regime_role": "diagnostic_only_never_admission",
                        }
                    )
                    stable_identity = {
                        key: payload[key]
                        for key in (
                            "symbol",
                            "closed_h1_ts_ms",
                            "closed_history_sha256",
                            "latest_closed_row_sha256",
                            "btc_regime_history_sha256",
                            "runtime_contract_sha256",
                            "source_closure_sha256",
                            "manifest_sha256",
                            "config_sha256",
                            "raw_signal",
                            "no_signal_reason",
                            "regime_eligible",
                            "consumed_is_latest_window",
                            "consumed_latest_start_ts_ms",
                            "decision_latest_start_ts_ms",
                        )
                    }
                    if journal_writer.append(
                        "raw_decision",
                        f"att1-raw:{symbol}:{closed_ts}",
                        stable_identity=stable_identity,
                        payload=payload,
                    ):
                        written += 1
                    successful += 1
                except ShadowViolation as exc:
                    if str(exc) in {"journal_claim_conflict", "journal_chain_broken"} or str(exc).startswith("journal_invalid_json"):
                        raise
                    failure_type = _error_class(exc)
                    is_expected = symbol in config.expected_unavailable_symbols and failure_type in {
                        "public_fetch_error",
                        "data_validation_error",
                    }
                    if is_expected:
                        expected_unavailable.append(symbol)
                        event_type = "expected_symbol_unavailable"
                        error_status = "RAW_DECISION_SHADOW_EXPECTED_UNAVAILABLE"
                    else:
                        failures.append(symbol)
                        event_type = failure_type
                        error_status = "RAW_DECISION_SHADOW_ERROR"
                        failed_types[failure_type] = failed_types.get(failure_type, 0) + 1
                    payload = dict(base)
                    payload.update(
                        {
                            "status": error_status,
                            "closed_h1_ts_ms": cycle_close_ts,
                            "btc_regime_history_sha256": btc_history_hash,
                            "no_signal_reason": f"{type(exc).__name__}:{exc}",
                            "regime": {key: value for key, value in regime.items() if key != "regime_eligible"},
                            "regime_eligible": regime["regime_eligible"],
                            "regime_role": "diagnostic_only_never_admission",
                        }
                    )
                    stable_identity = {
                        "symbol": symbol,
                        "cycle_close_ts_ms": cycle_close_ts,
                        "error_class": event_type,
                        "runtime_contract_sha256": runtime_contract["sha256"],
                        "source_closure_sha256": manifest["source_closure_sha256"],
                        "config_sha256": config_sha,
                        "btc_regime_history_sha256": btc_history_hash,
                    }
                    if journal_writer.append(
                        event_type,
                        f"att1-error:{symbol}:{cycle_close_ts}:{event_type}",
                        stable_identity=stable_identity,
                        payload=payload,
                    ):
                        written += 1
                except Exception as exc:
                    failure_type = _error_class(exc)
                    is_expected = symbol in config.expected_unavailable_symbols and failure_type in {
                        "public_fetch_error",
                        "data_validation_error",
                    }
                    if is_expected:
                        expected_unavailable.append(symbol)
                        event_type = "expected_symbol_unavailable"
                        error_status = "RAW_DECISION_SHADOW_EXPECTED_UNAVAILABLE"
                    else:
                        failures.append(symbol)
                        event_type = failure_type
                        error_status = "RAW_DECISION_SHADOW_ERROR"
                        failed_types[failure_type] = failed_types.get(failure_type, 0) + 1
                    payload = dict(base)
                    payload.update(
                        {
                            "status": error_status,
                            "closed_h1_ts_ms": cycle_close_ts,
                            "btc_regime_history_sha256": btc_history_hash,
                            "no_signal_reason": f"{type(exc).__name__}:{exc}",
                            "regime": {key: value for key, value in regime.items() if key != "regime_eligible"},
                            "regime_eligible": regime["regime_eligible"],
                            "regime_role": "diagnostic_only_never_admission",
                        }
                    )
                    stable_identity = {
                        "symbol": symbol,
                        "cycle_close_ts_ms": cycle_close_ts,
                        "error_class": event_type,
                        "runtime_contract_sha256": runtime_contract["sha256"],
                        "source_closure_sha256": manifest["source_closure_sha256"],
                        "config_sha256": config_sha,
                        "btc_regime_history_sha256": btc_history_hash,
                    }
                    if journal_writer.append(
                        event_type,
                        f"att1-error:{symbol}:{cycle_close_ts}:{event_type}",
                        stable_identity=stable_identity,
                        payload=payload,
                    ):
                        written += 1
            total_events = journal_writer.events

    if successful == 0:
        status, ok, failure_reason = "RAW_DECISION_SHADOW_FAIL_CLOSED", False, "zero_successful_symbol_evaluations"
    elif failures:
        status, ok, failure_reason = "RAW_DECISION_SHADOW_PARTIAL", False, "unknown_symbol_failures"
    elif expected_unavailable:
        status, ok, failure_reason = (
            "RAW_DECISION_SHADOW_PARTIAL_EXPECTED_HFT",
            True,
            "frozen_hft_member_expected_stale_or_unavailable",
        )
    else:
        status, ok, failure_reason = "RAW_DECISION_SHADOW_OK", True, None
    return {
        "status": status,
        "ok": ok,
        "failure_reason": failure_reason,
        "authority": AUTHORITY,
        "measurement_authority": "raw_decision_only",
        "evidence_admitted": False,
        "performance_authority": False,
        "final_n_eligible": False,
        "money_authority": False,
        "orders_created_or_changed": 0,
        "private_api_calls": False,
        "broker_calls": False,
        "evidence_universe": list(ATT1_FIXED51_UNIVERSE),
        "failed_symbols": failures,
        "expected_unavailable_symbols": expected_unavailable,
        "failed_event_types": failed_types,
        "successful_symbol_evaluations": successful,
        "journal_events": written,
        "journal_path": str(journal),
        "journal_total_events": total_events,
        "cycle_closed_h1_ts_ms": cycle_close_ts,
        "preflight": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/att1_fixed51_zero_risk_shadow_v1.json")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--ack", default="")
    args = parser.parse_args()
    try:
        result = (
            run_cycle(args.root.resolve(), args.config.resolve(), acknowledgement=args.ack)
            if args.once
            else preflight(args.root.resolve(), args.config.resolve())
        )
    except Exception as exc:
        print(json.dumps({"status": "RAW_DECISION_SHADOW_FAIL_CLOSED", "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if not args.once or result.get("ok") is True else 3


if __name__ == "__main__":
    raise SystemExit(main())
