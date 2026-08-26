"""Explicitly enabled public updater for the persisted BTC H1 regime.

The persisted state machine intentionally has no network or scheduler code.
This module is the narrow production-shaped boundary that supplies it with
Bybit public market data.  It is disabled unless ``enabled=True`` is passed,
uses only the public linear kline endpoint, and exposes no order, account,
configuration, or promotion authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Mapping

from bot.persisted_btc_h1_regime import (
    BTCRegimeContractError,
    BTCRegimeReceipt,
    MIN_BOOTSTRAP_BARS,
    advance_btc_h1_regime,
    bootstrap_btc_h1_regime,
    load_btc_h1_regime,
    persist_btc_h1_regime,
    regime_evidence,
)
from bot.live_native_regime_gate import H1_MS


PUBLIC_HOST = "api.bybit.com"
PUBLIC_PATH = "/v5/market/kline"
PUBLIC_BASE = "https://api.bybit.com"
DEFAULT_STATE_PATH = Path("runtime/live_native_parity/btc_h1_regime.json")
BTC_SYMBOL = "BTCUSDT"
H1_INTERVAL = "60"
DEFAULT_HISTORY_LIMIT = 1000
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
UPDATER_ENABLED_BY_DEFAULT = False
UPDATER_AUTHORITY = "public_research_only_no_orders_no_money_no_promotion"


class BTCRegimeUpdaterError(ValueError):
    """Stable fail-closed error for the public updater boundary."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = str(code)
        self.detail = str(detail)
        super().__init__(self.code if not detail else f"{self.code}: {detail}")


@dataclass(frozen=True)
class PublicBTCH1Snapshot:
    rows: tuple[tuple[object, ...], ...]
    observed_at_ms: int
    source_sha256: str
    data_sha256: str


@dataclass(frozen=True)
class BTCRegimeUpdateResult:
    receipt: BTCRegimeReceipt
    action: Literal["bootstrapped", "advanced", "unchanged"]
    applied_bars: int
    observed_at_ms: int
    source_sha256: str
    research_only: bool = True
    money_authority: bool = False
    orders_allowed: bool = False


@dataclass(frozen=True)
class BTCRegimeRestartProof:
    receipt_sha256: str
    state_sha256: str
    last_closed_h1_ts_ms: int
    observed_at_ms: int
    regime_value: str
    research_only: bool = True
    money_authority: bool = False
    orders_allowed: bool = False


FetchBytes = Callable[..., bytes]


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
        raise BTCRegimeUpdaterError("noncanonical_public_payload") from exc


def _strict_json_constant(value: str) -> object:
    raise BTCRegimeUpdaterError("public_kline_invalid_json", value)


def _strict_int(value: object, field: str) -> int:
    if isinstance(value, bool) or isinstance(value, float):
        raise BTCRegimeUpdaterError("invalid_integer", field)
    try:
        result = int(str(value))
    except (TypeError, ValueError) as exc:
        raise BTCRegimeUpdaterError("invalid_integer", field) from exc
    if str(result) != str(value).strip() or result <= 0:
        raise BTCRegimeUpdaterError("invalid_integer", field)
    return result


def _public_url(base: str, *, limit: int) -> str:
    if isinstance(base, bytes):
        raise BTCRegimeUpdaterError("nonpublic_bybit_request_rejected")
    root = str(base or "").rstrip("/")
    parsed = urllib.parse.urlparse(root)
    if (
        parsed.scheme != "https"
        or parsed.hostname != PUBLIC_HOST
        or parsed.port not in (None, 443)
        or parsed.path not in ("", "/")
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise BTCRegimeUpdaterError("nonpublic_bybit_request_rejected")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < MIN_BOOTSTRAP_BARS or limit > 1000:
        raise BTCRegimeUpdaterError("invalid_public_kline_limit")
    query = urllib.parse.urlencode(
        {
            "category": "linear",
            "symbol": BTC_SYMBOL,
            "interval": H1_INTERVAL,
            "limit": limit,
        }
    )
    return f"{root}{PUBLIC_PATH}?{query}"


def _public_get_bytes(url: str, *, timeout: float) -> bytes:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "bybit-btc-h1-regime-updater/1.0"},
    )

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise BTCRegimeUpdaterError("public_bybit_redirect_rejected")

    try:
        opener = urllib.request.build_opener(_NoRedirect)
        with opener.open(request, timeout=timeout) as response:
            final = urllib.parse.urlparse(response.geturl())
            if final.scheme != "https" or final.hostname != PUBLIC_HOST or final.path != PUBLIC_PATH:
                raise BTCRegimeUpdaterError("public_bybit_final_url_rejected")
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except BTCRegimeUpdaterError:
        raise
    except Exception as exc:
        raise BTCRegimeUpdaterError("public_kline_fetch_failed") from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise BTCRegimeUpdaterError("public_kline_response_too_large")
    return body


def fetch_public_btc_h1(
    base: str = PUBLIC_BASE,
    *,
    limit: int = DEFAULT_HISTORY_LIMIT,
    timeout: float = 15.0,
    fetch: FetchBytes = _public_get_bytes,
) -> PublicBTCH1Snapshot:
    """Fetch and validate only public BTCUSDT closed-H1 input material."""

    url = _public_url(base, limit=limit)
    if isinstance(timeout, bool) or float(timeout) <= 0:
        raise BTCRegimeUpdaterError("invalid_public_timeout")
    try:
        body = fetch(url, timeout=float(timeout))
    except BTCRegimeUpdaterError:
        raise
    except Exception as exc:
        raise BTCRegimeUpdaterError("public_kline_fetch_failed") from exc
    if not isinstance(body, bytes) or len(body) > MAX_RESPONSE_BYTES:
        raise BTCRegimeUpdaterError("public_kline_response_too_large")
    try:
        payload = json.loads(
            body.decode("utf-8"),
            parse_constant=_strict_json_constant,
        )
    except BTCRegimeUpdaterError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BTCRegimeUpdaterError("public_kline_invalid_json") from exc
    if (
        not isinstance(payload, Mapping)
        or isinstance(payload.get("retCode"), bool)
        or not isinstance(payload.get("retCode"), int)
        or payload.get("retCode") != 0
    ):
        raise BTCRegimeUpdaterError("public_kline_missing_result")
    observed = _strict_int(payload.get("time"), "bybit_observed_at_ms")
    result = payload.get("result")
    raw_rows = result.get("list") if isinstance(result, Mapping) else None
    if not isinstance(raw_rows, list) or not raw_rows:
        raise BTCRegimeUpdaterError("public_kline_missing_result")
    normalized: list[tuple[object, ...]] = []
    for raw in raw_rows:
        if not isinstance(raw, list) or len(raw) < 5:
            raise BTCRegimeUpdaterError("public_kline_invalid_row")
        normalized.append(tuple(raw))
    normalized.sort(key=lambda row: _strict_int(row[0], "bar_start_ts_ms"))
    return PublicBTCH1Snapshot(
        rows=tuple(normalized),
        observed_at_ms=observed,
        source_sha256=hashlib.sha256(body).hexdigest(),
        data_sha256=hashlib.sha256(_canonical([list(row) for row in normalized])).hexdigest(),
    )


def _closed_rows(snapshot: PublicBTCH1Snapshot) -> list[list[object]]:
    closed: list[list[object]] = []
    previous_start: int | None = None
    for raw in snapshot.rows:
        start = _strict_int(raw[0], "bar_start_ts_ms")
        if start % H1_MS != 0:
            raise BTCRegimeUpdaterError("public_kline_invalid_row")
        if start + H1_MS <= snapshot.observed_at_ms:
            if previous_start is not None and start != previous_start + H1_MS:
                raise BTCRegimeUpdaterError("noncontiguous_public_h1_rows")
            closed.append(list(raw))
            previous_start = start
    if len(closed) < MIN_BOOTSTRAP_BARS:
        raise BTCRegimeUpdaterError("public_h1_history_short")
    return closed


def _is_absent_state(path: Path, exc: BTCRegimeContractError) -> bool:
    return exc.code == "state_file_unreadable" and not os.path.lexists(path)


def _source_data(snapshot: PublicBTCH1Snapshot) -> tuple[dict[str, object], dict[str, object]]:
    return (
        {
            "provider": "bybit-public",
            "endpoint": PUBLIC_PATH,
            "source_sha256": snapshot.source_sha256,
        },
        {
            "symbol": BTC_SYMBOL,
            "interval": H1_INTERVAL,
            "data_sha256": snapshot.data_sha256,
            "provenance": "public_bybit_linear_closed_h1",
        },
    )


def update_btc_h1_regime(
    path: Path | str,
    *,
    enabled: bool = UPDATER_ENABLED_BY_DEFAULT,
    base: str = PUBLIC_BASE,
    limit: int = DEFAULT_HISTORY_LIMIT,
    timeout: float = 15.0,
    max_age_ms: int = 300_000,
    observed_at_ms: int | None = None,
    fetch: FetchBytes = _public_get_bytes,
) -> BTCRegimeUpdateResult:
    """Bootstrap or advance persisted state from one public response.

    The explicit enable check is before any HTTP or filesystem operation.
    Existing state is never rebuilt.  If the response cannot bridge the
    persisted last bar, the updater fails closed rather than silently
    re-seeding a new EMA.
    """

    if enabled is not True:
        raise BTCRegimeUpdaterError("regime_updater_disabled")
    snapshot = fetch_public_btc_h1(
        base,
        limit=limit,
        timeout=timeout,
        fetch=fetch,
    )
    observed = snapshot.observed_at_ms if observed_at_ms is None else _strict_int(observed_at_ms, "observed_at_ms")
    if observed < snapshot.observed_at_ms:
        raise BTCRegimeUpdaterError("observed_at_before_public_response")
    max_age = _strict_int(max_age_ms, "max_age_ms")
    if max_age <= 0:
        raise BTCRegimeUpdaterError("nonpositive_max_age")
    # Closed/open classification is anchored to Bybit's response timestamp,
    # never to a later local clock supplied by the caller.  Otherwise an open
    # mutable candle could be mistaken for a settled close after the response.
    closed = _closed_rows(snapshot)
    latest_age = observed - (_strict_int(closed[-1][0], "bar_start_ts_ms") + H1_MS)
    if latest_age < 0:
        raise BTCRegimeUpdaterError("latest_h1_not_closed")
    if latest_age > max_age:
        # Check this before any one-bar CAS writes, so a stale response cannot
        # leave a partially backfilled state behind.
        raise BTCRegimeUpdaterError("public_h1_decision_too_old")
    target = Path(path)
    try:
        existing = load_btc_h1_regime(target)
    except BTCRegimeContractError as exc:
        if not _is_absent_state(target, exc):
            raise
        source, data = _source_data(snapshot)
        receipt = bootstrap_btc_h1_regime(
            closed,
            observed_at_ms=observed,
            max_age_ms=max_age,
            source_provenance=source,
            data_provenance=data,
        )
        persist_btc_h1_regime(target, receipt)
        return BTCRegimeUpdateResult(
            receipt=receipt,
            action="bootstrapped",
            applied_bars=receipt.state.observation_count,
            observed_at_ms=observed,
            source_sha256=snapshot.source_sha256,
        )

    last = existing.state.last_bar_start_ts_ms
    starts = [_strict_int(row[0], "bar_start_ts_ms") for row in closed]
    try:
        index = starts.index(last)
    except ValueError as exc:
        if last < starts[0]:
            raise BTCRegimeUpdaterError("persisted_state_older_than_public_history") from exc
        raise BTCRegimeUpdaterError("persisted_state_ahead_of_public_history") from exc
    # Validate the persisted latest bar against the response even when there
    # are no newer rows.  A same-start candle with a changed close is a
    # conflicting duplicate and must never be silently ignored.
    current_age = observed - (last + H1_MS)
    advance_btc_h1_regime(
        existing,
        closed[index],
        observed_at_ms=observed,
        max_age_ms=max(max_age, current_age),
    )
    updated = existing
    applied = 0
    for row in closed[index + 1 :]:
        start = _strict_int(row[0], "bar_start_ts_ms")
        row_age = observed - (start + H1_MS)
        next_receipt = advance_btc_h1_regime(
            updated,
            row,
            observed_at_ms=observed,
            max_age_ms=max_age if row is closed[-1] else max(max_age, row_age),
        )
        # The persisted contract is one-bar CAS.  Keeping this write inside
        # the loop means every advance is durable before the next one starts;
        # a process crash can therefore resume from the last committed bar.
        persist_btc_h1_regime(
            target,
            next_receipt,
            expected_previous_receipt_sha256=updated.receipt_sha256,
        )
        updated = next_receipt
        applied += 1
    if applied == 0:
        return BTCRegimeUpdateResult(
            receipt=existing,
            action="unchanged",
            applied_bars=0,
            observed_at_ms=observed,
            source_sha256=snapshot.source_sha256,
        )
    return BTCRegimeUpdateResult(
        receipt=updated,
        action="advanced",
        applied_bars=applied,
        observed_at_ms=observed,
        source_sha256=snapshot.source_sha256,
    )


def verify_btc_h1_regime_restart(
    path: Path | str,
    *,
    observed_at_ms: object,
    max_age_ms: object,
) -> BTCRegimeRestartProof:
    """Require an existing verified, fresh receipt before a process restart."""

    receipt = load_btc_h1_regime(path)
    evidence = regime_evidence(
        receipt,
        observed_at_ms=observed_at_ms,
        max_age_ms=max_age_ms,
    )
    return BTCRegimeRestartProof(
        receipt_sha256=receipt.receipt_sha256,
        state_sha256=receipt.state.state_sha256,
        last_closed_h1_ts_ms=evidence.closed_h1_ts_ms,
        observed_at_ms=evidence.observed_at_ms,
        regime_value=evidence.value,
    )


__all__ = [
    "BTCRegimeRestartProof",
    "BTCRegimeUpdateResult",
    "BTCRegimeUpdaterError",
    "DEFAULT_HISTORY_LIMIT",
    "DEFAULT_STATE_PATH",
    "PUBLIC_BASE",
    "PublicBTCH1Snapshot",
    "UPDATER_AUTHORITY",
    "UPDATER_ENABLED_BY_DEFAULT",
    "fetch_public_btc_h1",
    "update_btc_h1_regime",
    "verify_btc_h1_regime_restart",
]
