#!/usr/bin/env python3
"""Default-off prospective SBR1 shadow over public Bybit closed candles only.

With no arguments this command performs a read-only, no-network preflight.
One collection cycle requires both an enabled server-side config copy and the
literal acknowledgement ``ZERO_RISK_SHADOW_ONLY``.  The file imports no broker,
account, position, execution-client, order, key, or trading monolith module.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.live_native_manifest import load_and_verify_manifest  # noqa: E402
from bot.live_native_decision_contract import ContractViolation  # noqa: E402
from bot.live_native_signal_adapters import (  # noqa: E402
    adapt_sbr1_live_signal_to_plan,
    closed_h1_evidence_from_row,
)
from bot.sbr1_zero_risk_shadow import (  # noqa: E402
    AUTHORITY,
    M5_MS,
    AppendOnlyShadowJournal,
    CausalEmaRegimeState,
    ShadowViolation,
    TickNativeShadowExecution,
    advance_causal_ema,
    bootstrap_causal_ema,
    evaluate_prospective_outcome,
    load_config,
    outcome_rows_hash,
    plan_from_payload,
    policy_for_plan,
    shadow_slot_gate,
    tick_native_shadow_execution,
    verify_source_closure,
)
from bot.sbr1_shadow_random_control import (  # noqa: E402
    PREREG_RELATIVE_PATH,
    build_control_assignments,
    persist_controlled_admission,
    preregistration_sha256,
)
from bot.sbr1_universe import (  # noqa: E402
    UniverseViolation,
    load_fixed51_manifest,
    verify_fixed51_manifest,
)
from strategies.live_kline_utils import closed_kline_rows  # noqa: E402
from strategies.sbr1_live import SBR1LiveEngine  # noqa: E402


DEFAULT_CONFIG = ROOT / "configs/sbr1_zero_risk_shadow_v1.json"
ACK = "ZERO_RISK_SHADOW_ONLY"
PUBLIC_HOST = "api.bybit.com"
PUBLIC_PATH = "/v5/market/kline"
PUBLIC_INSTRUMENT_PATH = "/v5/market/instruments-info"
H1_MS = 3_600_000
RAW_EVIDENCE_ROLE = "preparity_raw_not_final_n"
MAJOR8_EVIDENCE_ROLE = "major8_existing_lifecycle"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _row_bytes(row: Sequence[object]) -> bytes:
    return _canonical_bytes(list(row))


@dataclass(frozen=True)
class PublicKlineSnapshot:
    symbol: str
    interval: str
    rows: tuple[tuple[object, ...], ...]
    observed_at_ms: int
    response_sha256: str


@dataclass(frozen=True)
class PublicFilterSnapshot:
    symbol: str
    tick_size: str
    qty_step: str
    min_notional: str
    observed_at_ms: int
    response_sha256: str


def _public_get_bytes(url: str, *, timeout: float) -> bytes:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query, strict_parsing=True)
    allowed_query = {"category", "symbol", "interval", "limit", "end"}
    if (
        parsed.scheme != "https"
        or parsed.hostname != PUBLIC_HOST
        or parsed.path not in {PUBLIC_PATH, PUBLIC_INSTRUMENT_PATH}
        or parsed.username is not None
        or parsed.password is not None
        or set(query) - allowed_query
        or query.get("category") != ["linear"]
    ):
        raise ShadowViolation("nonpublic_bybit_request_rejected")
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "by-bot-sbr1-zero-risk-shadow/1.0"},
    )

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ShadowViolation("public_bybit_redirect_rejected")

    opener = urllib.request.build_opener(_NoRedirect)
    with opener.open(request, timeout=timeout) as response:
        final = urllib.parse.urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != PUBLIC_HOST or final.path != parsed.path:
            raise ShadowViolation("public_bybit_final_url_rejected")
        body = response.read(2 * 1024 * 1024 + 1)
        if len(body) > 2 * 1024 * 1024:
            raise ShadowViolation("public_bybit_response_too_large")
        return body


def fetch_public_filters(
    base: str,
    symbol: str,
    *,
    timeout: float,
    get_bytes: Callable[..., bytes] = _public_get_bytes,
) -> PublicFilterSnapshot:
    symbol = str(symbol or "").strip().upper()
    if base != "https://api.bybit.com" or not symbol.endswith("USDT"):
        raise ShadowViolation("invalid_public_filter_scope")
    url = f"{base}{PUBLIC_INSTRUMENT_PATH}?{urllib.parse.urlencode({'category': 'linear', 'symbol': symbol})}"
    raw = get_bytes(url, timeout=timeout)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShadowViolation("public_filter_invalid_json") from exc
    result = payload.get("result") if isinstance(payload, Mapping) else None
    rows = result.get("list") if isinstance(result, Mapping) else None
    observed = int(payload.get("time") or 0) if isinstance(payload, Mapping) else 0
    if (
        int(payload.get("retCode", -1)) != 0
        or not isinstance(rows, list)
        or len(rows) != 1
        or not isinstance(rows[0], Mapping)
        or observed <= 0
        or str(rows[0].get("symbol") or "").strip().upper() != symbol
    ):
        raise ShadowViolation("public_filter_missing_result")
    price = rows[0].get("priceFilter")
    lot = rows[0].get("lotSizeFilter")
    if not isinstance(price, Mapping) or not isinstance(lot, Mapping):
        raise ShadowViolation("public_filter_missing_rules")
    values = {
        "tick_size": str(price.get("tickSize") or "").strip(),
        "qty_step": str(lot.get("qtyStep") or "").strip(),
        "min_notional": str(lot.get("minNotionalValue") or "").strip(),
    }
    try:
        if any(Decimal(value) <= 0 for value in values.values()):
            raise ShadowViolation("public_filter_nonpositive_rule")
    except InvalidOperation as exc:
        raise ShadowViolation("public_filter_invalid_rule") from exc
    return PublicFilterSnapshot(
        symbol=symbol,
        observed_at_ms=observed,
        response_sha256=hashlib.sha256(raw).hexdigest(),
        **values,
    )


def verify_public_filters(snapshot: PublicFilterSnapshot, frozen: Mapping[str, object]) -> None:
    if not isinstance(frozen, Mapping):
        raise ShadowViolation("frozen_filter_missing")
    for field in ("tick_size", "qty_step", "min_notional"):
        try:
            if Decimal(str(getattr(snapshot, field))) != Decimal(str(frozen.get(field))):
                raise ShadowViolation(f"exchange_filter_drift:{snapshot.symbol}:{field}")
        except InvalidOperation as exc:
            raise ShadowViolation(f"exchange_filter_invalid:{snapshot.symbol}:{field}") from exc


def _observed_filter_mapping(snapshot: PublicFilterSnapshot) -> dict[str, str]:
    """Return a validated public filter contract for an evidence symbol."""
    return {
        "tick_size": snapshot.tick_size,
        "qty_step": snapshot.qty_step,
        "min_notional": snapshot.min_notional,
    }


def fetch_public_klines(
    base: str,
    symbol: str,
    interval: str,
    limit: int,
    *,
    timeout: float,
    end_ms: int | None = None,
    get_bytes: Callable[..., bytes] = _public_get_bytes,
) -> PublicKlineSnapshot:
    symbol = str(symbol or "").strip().upper()
    interval = str(interval or "").strip()
    if base != "https://api.bybit.com" or not symbol.endswith("USDT"):
        raise ShadowViolation("invalid_public_kline_scope")
    if interval not in {"5", "60"} or not 1 <= int(limit) <= 1000:
        raise ShadowViolation("invalid_public_kline_request")
    params: dict[str, object] = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": int(limit),
    }
    if end_ms is not None:
        if isinstance(end_ms, bool) or int(end_ms) <= 0:
            raise ShadowViolation("invalid_public_kline_end")
        params["end"] = int(end_ms)
    url = f"{base}{PUBLIC_PATH}?{urllib.parse.urlencode(params)}"
    raw = get_bytes(url, timeout=timeout)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShadowViolation("public_kline_invalid_json") from exc
    if not isinstance(payload, dict) or int(payload.get("retCode", -1)) != 0:
        raise ShadowViolation("public_kline_retcode_nonzero")
    result = payload.get("result")
    rows = result.get("list") if isinstance(result, Mapping) else None
    observed = int(payload.get("time") or 0)
    if not isinstance(rows, list) or not rows or observed <= 0:
        raise ShadowViolation("public_kline_missing_result")
    normalized: list[tuple[object, ...]] = []
    seen: set[int] = set()
    for raw_row in rows:
        if not isinstance(raw_row, list) or len(raw_row) < 6:
            raise ShadowViolation("public_kline_invalid_row")
        start = int(str(raw_row[0]))
        if start in seen:
            raise ShadowViolation("public_kline_duplicate_row")
        seen.add(start)
        normalized.append(tuple(raw_row))
    normalized.sort(key=lambda row: int(str(row[0])))
    return PublicKlineSnapshot(
        symbol=symbol,
        interval=interval,
        rows=tuple(normalized),
        observed_at_ms=observed,
        response_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _fetch_h1_decision_snapshots(
    config,
    btc: PublicKlineSnapshot,
    *,
    get_bytes: Callable[..., bytes],
    fetcher: Callable[..., PublicKlineSnapshot] = fetch_public_klines,
    symbols: Sequence[str] | None = None,
) -> tuple[dict[str, PublicKlineSnapshot], dict[str, str]]:
    """Fetch symbols independently so one public-data error cannot starve later symbols."""
    snapshots: dict[str, PublicKlineSnapshot] = {}
    errors: dict[str, str] = {}
    selected_symbols = config.universe if symbols is None else symbols
    for symbol in selected_symbols:
        if symbol == "BTCUSDT":
            snapshots[symbol] = btc
            continue
        try:
            snapshots[symbol] = fetcher(
                config.public_base,
                symbol,
                "60",
                config.h1_history_limit + 1,
                timeout=float(config.request_timeout_seconds),
                get_bytes=get_bytes,
            )
        except Exception as exc:
            errors[symbol] = f"{type(exc).__name__}:{exc}"[:500]
    return snapshots, errors


def _closed_rows(snapshot: PublicKlineSnapshot) -> list[list[object]]:
    rows = closed_kline_rows(
        [list(row) for row in snapshot.rows],
        snapshot.interval,
        now_ms=snapshot.observed_at_ms,
    )
    step = H1_MS if snapshot.interval == "60" else M5_MS
    previous = None
    for row in rows:
        try:
            start = int(str(row[0]))
            open_, high, low, close, volume = (
                Decimal(str(row[1])),
                Decimal(str(row[2])),
                Decimal(str(row[3])),
                Decimal(str(row[4])),
                Decimal(str(row[5])),
            )
        except (ValueError, InvalidOperation, IndexError) as exc:
            raise ShadowViolation("closed_kline_invalid_numeric") from exc
        if (
            start <= 0
            or start % step != 0
            or min(open_, high, low, close) <= 0
            or volume < 0
            or not all(value.is_finite() for value in (open_, high, low, close, volume))
            or high < max(open_, close)
            or low > min(open_, close)
            or low > high
        ):
            raise ShadowViolation("closed_kline_incoherent")
        if previous is not None and start != previous + step:
            raise ShadowViolation("closed_kline_noncontiguous")
        previous = start
    return rows


def fetch_closed_m5_path(
    base: str,
    symbol: str,
    start_ms: int,
    end_exclusive_ms: int,
    *,
    timeout: float,
    max_pages: int,
    get_bytes: Callable[..., bytes] = _public_get_bytes,
) -> tuple[list[list[object]], list[str], int]:
    if (
        start_ms <= 0
        or start_ms % M5_MS != 0
        or end_exclusive_ms <= start_ms
        or end_exclusive_ms % M5_MS != 0
    ):
        raise ShadowViolation("invalid_m5_path_window")
    cursor = end_exclusive_ms - 1
    by_ts: dict[int, list[object]] = {}
    response_hashes: list[str] = []
    observed_at = 0
    for _ in range(max_pages):
        snapshot = fetch_public_klines(
            base,
            symbol,
            "5",
            1000,
            timeout=timeout,
            end_ms=cursor,
            get_bytes=get_bytes,
        )
        response_hashes.append(snapshot.response_sha256)
        observed_at = max(observed_at, snapshot.observed_at_ms)
        closed = _closed_rows(snapshot)
        for row in closed:
            ts = int(str(row[0]))
            if start_ms <= ts < end_exclusive_ms:
                by_ts[ts] = row
        minimum = min(int(str(row[0])) for row in snapshot.rows)
        if minimum <= start_ms:
            break
        cursor = minimum - 1
    rows = [by_ts[ts] for ts in sorted(by_ts)]
    if not rows or int(str(rows[0][0])) != start_ms:
        raise ShadowViolation("m5_path_start_missing")
    for left, right in zip(rows, rows[1:]):
        if int(str(right[0])) != int(str(left[0])) + M5_MS:
            raise ShadowViolation("m5_path_not_contiguous")
    return rows, response_hashes, observed_at


@contextlib.contextmanager
def _frozen_sbr1_env(universe: Sequence[str]):
    values = {
        "SBR1_SYMBOL_ALLOWLIST": ",".join(universe),
        "SBR1_SIGNAL_TF": "60",
        "SBR1_SL_ATR_MULT": "4.60",
        "SBR1_TP1_RR": "1.10",
        "SBR1_TP2_RR": "2.60",
        "SBR1_TP1_FRAC": "0.50",
        "SBR1_TP2_FRAC": "0.30",
        "SBR1_BE_TRIGGER_RR": "0",
        "SBR1_TRAIL_ATR_MULT": "0",
        "SBR1_TIME_STOP_BARS_5M": "2016",
        "SBR1_COOLDOWN_TF_BARS": "6",
        "SBR1_ALLOW_LONGS": "1",
        "SBR1_ALLOW_SHORTS": "0",
    }
    keys = {key for key in os.environ if key.startswith("SBR1_")} | set(values)
    previous = {key: os.environ.get(key) for key in keys}
    try:
        for key in keys:
            os.environ.pop(key, None)
        os.environ.update(values)
        yield
    finally:
        for key in keys:
            os.environ.pop(key, None)
        for key, value in previous.items():
            if value is not None:
                os.environ[key] = value


def replay_latest_signal(symbol: str, closed_h1: Sequence[Sequence[object]]):
    if len(closed_h1) < 120:
        raise ShadowViolation("insufficient_strategy_h1_history")
    current: list[list[object]] = []

    def fetcher(_symbol: str, _interval: str, limit: int) -> list[list[object]]:
        return [list(row) for row in current[-int(limit) :]]

    engine = SBR1LiveEngine(fetcher)
    latest_signal = None
    start_index = max(95, len(closed_h1) - 72)
    for index in range(start_index, len(closed_h1)):
        current = [list(row) for row in closed_h1[: index + 1]]
        row = current[-1]
        latest_signal = engine.signal(
            symbol,
            int(str(row[0])) + H1_MS,
            float(row[1]),
            float(row[2]),
            float(row[3]),
            float(row[4]),
            float(row[5]),
        )
        if index != len(closed_h1) - 1:
            latest_signal = None
    return latest_signal, engine.effective_config(symbol), engine.last_closed_rows(symbol)


def _signal_payload(signal) -> dict[str, object] | None:
    if signal is None:
        return None
    return {
        "entry": str(signal.entry),
        "reason": signal.reason,
        "side": signal.side,
        "sl": str(signal.sl),
        "strategy": signal.strategy,
        "symbol": signal.symbol,
        "time_stop_bars": signal.time_stop_bars,
        "tp": str(signal.tp),
        "tp_fracs": [str(value) for value in list(signal.tp_fracs or [])],
        "tps": [str(value) for value in list(signal.tps or [])],
    }


def _manifest_source_bundle(root: Path, manifest):
    rows = {str(item["path"]): item for item in manifest.payload["source_files"]}
    paths = {
        "strategies/sloped_break_retest_v1.py",
        "strategies/sbr1_live.py",
    }
    if not paths.issubset(rows):
        raise ShadowViolation("manifest_missing_sbr1_source")
    return (
        {path: (root / path).read_bytes() for path in paths},
        {path: str(rows[path]["sha256"]) for path in paths},
    )


def _latest_regime_state(events: Sequence[Mapping[str, object]]) -> CausalEmaRegimeState | None:
    state: CausalEmaRegimeState | None = None
    for event in events:
        event_type = event.get("event_type")
        if event_type not in {"regime_bootstrap", "regime_update"}:
            continue
        payload = event.get("payload")
        if not isinstance(payload, Mapping) or not isinstance(payload.get("state"), Mapping):
            raise ShadowViolation("regime_journal_payload_invalid")
        persisted = CausalEmaRegimeState.from_dict(payload["state"])
        if event_type == "regime_bootstrap":
            if state is not None or not isinstance(payload.get("rows"), list):
                raise ShadowViolation("regime_journal_duplicate_bootstrap")
            rebuilt = bootstrap_causal_ema(payload["rows"])
        else:
            if state is None or not isinstance(payload.get("row"), list):
                raise ShadowViolation("regime_journal_update_without_bootstrap")
            rebuilt = advance_causal_ema(state, payload["row"])
        if persisted != rebuilt:
            raise ShadowViolation("regime_journal_state_mismatch")
        state = persisted
    return state


def _advance_regime(
    journal: AppendOnlyShadowJournal,
    events: list[dict[str, object]],
    btc_snapshot: PublicKlineSnapshot,
    bootstrap_bars: int,
) -> CausalEmaRegimeState:
    closed = _closed_rows(btc_snapshot)
    state = _latest_regime_state(events)
    if state is None:
        if len(closed) < bootstrap_bars:
            raise ShadowViolation("regime_bootstrap_response_too_short")
        bootstrap_rows = closed[-bootstrap_bars:]
        state = bootstrap_causal_ema(bootstrap_rows)
        journal.append(
            "regime_bootstrap",
            f"regime-bootstrap:{state.seed_bar_start_ts_ms}:{state.bar_start_ts_ms}",
            {
                "authority": AUTHORITY,
                "observed_at_ms": btc_snapshot.observed_at_ms,
                "response_sha256": btc_snapshot.response_sha256,
                "rows": bootstrap_rows,
                "state": state.to_dict(),
            },
        )
        return state
    updates = [row for row in closed if int(str(row[0])) > state.bar_start_ts_ms]
    for row in updates:
        state = advance_causal_ema(state, row)
        journal.append(
            "regime_update",
            f"regime-update:{state.bar_start_ts_ms}",
            {
                "authority": AUTHORITY,
                "observed_at_ms": btc_snapshot.observed_at_ms,
                "response_sha256": btc_snapshot.response_sha256,
                "row": row,
                "state": state.to_dict(),
            },
        )
    return state


def _journal_index(
    events: Sequence[Mapping[str, object]],
    money_universe: Sequence[str] | None = None,
):
    decisions: dict[str, Mapping[str, object]] = {}
    fills: dict[str, Mapping[str, object]] = {}
    terminal: set[str] = set()
    claims = {str(event.get("claim_key")) for event in events}
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue
        decision_id = str(payload.get("decision_id") or "")
        if event.get("event_type") == "evaluation" and payload.get("admitted") is True:
            symbol = str(payload.get("symbol") or "").strip().upper()
            if money_universe is not None and symbol not in set(money_universe):
                raise ShadowViolation(f"admitted_non_money_symbol:{symbol}")
            decisions[decision_id] = payload
        elif event.get("event_type") == "fill":
            fills[decision_id] = payload
        elif event.get("event_type") in {"outcome", "fill_rejected"}:
            terminal.add(decision_id)
    return decisions, fills, terminal, claims


def _coverage_for_close(
    events: Sequence[Mapping[str, object]],
    *,
    expected_symbols: Sequence[str],
    expected_close: int,
) -> dict[str, object]:
    """Build stable fixed-universe coverage from the durable journal.

    A successful evaluation wins over an earlier retryable error.  Expected
    structural unavailability is a separate, explicit state and never causes
    a symbol substitution.
    """

    expected = tuple(expected_symbols)
    expected_set = set(expected)
    observed: set[str] = set()
    errors: set[str] = set()
    unavailable: set[str] = set()
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue
        try:
            close = int(str(payload.get("closed_h1_ts_ms") or 0))
        except ValueError:
            continue
        if close != expected_close:
            continue
        symbol = str(payload.get("symbol") or "").strip().upper()
        if symbol not in expected_set:
            continue
        event_type = event.get("event_type")
        if event_type == "evaluation":
            observed.add(symbol)
        elif event_type == "evaluation_unavailable":
            unavailable.add(symbol)
        elif event_type in {"evaluation_fetch_error", "evaluation_data_error"}:
            errors.add(symbol)
    errors -= observed | unavailable
    missing = expected_set - observed - unavailable - errors
    return {
        "expected_count": len(expected),
        "expected_symbols": list(expected),
        "observed_count": len(observed),
        "observed_symbols": sorted(observed),
        "error_count": len(errors),
        "error_symbols": sorted(errors),
        "structurally_unavailable_count": len(unavailable),
        "structurally_unavailable_symbols": sorted(unavailable),
        "missing_count": len(missing),
        "missing_symbols": sorted(missing),
    }


def _preflight(root: Path, config_path: Path) -> dict[str, object]:
    config = load_config(config_path)
    manifest = load_and_verify_manifest(
        root,
        root / config.parity_manifest_path,
        verify_data_bytes=False,
        verify_source_bytes=True,
    )
    if manifest.manifest_sha256 != config.expected_parity_manifest_sha256:
        raise ShadowViolation("parity_manifest_hash_mismatch")
    if tuple(manifest.universe) != config.money_universe:
        raise ShadowViolation("shadow_money_manifest_universe_mismatch")
    if not config.evidence_universe_manifest_path or not config.expected_evidence_universe_manifest_sha256:
        raise ShadowViolation("fixed51_manifest_fields_missing")
    evidence_manifest_path = root / config.evidence_universe_manifest_path
    try:
        evidence_manifest_sha256 = hashlib.sha256(evidence_manifest_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ShadowViolation("fixed51_manifest_unreadable") from exc
    if evidence_manifest_sha256 != config.expected_evidence_universe_manifest_sha256:
        raise ShadowViolation("fixed51_manifest_hash_mismatch")
    try:
        evidence_manifest = load_fixed51_manifest(evidence_manifest_path)
        verify_fixed51_manifest(root, evidence_manifest)
    except UniverseViolation as exc:
        raise ShadowViolation(str(exc)) from exc
    if evidence_manifest.universe != config.evidence_universe:
        raise ShadowViolation("fixed51_config_universe_mismatch")
    if evidence_manifest.money_universe != config.money_universe:
        raise ShadowViolation("fixed51_money_universe_mismatch")
    if config.evidence_universe_sha256 != evidence_manifest.universe_sha256:
        raise ShadowViolation("fixed51_config_hash_mismatch")
    if config.money_universe_sha256 != evidence_manifest.money_universe_sha256:
        raise ShadowViolation("fixed51_money_hash_mismatch")
    unavailable = dict(evidence_manifest.expected_structurally_unavailable)
    if not set(unavailable).issubset(config.evidence_universe):
        raise ShadowViolation("fixed51_expected_unavailable_outside_universe")
    prereg_sha = preregistration_sha256(root / PREREG_RELATIVE_PATH)
    if prereg_sha != config.expected_preregistration_sha256:
        raise ShadowViolation("random_control_preregistration_hash_mismatch")
    closure_hash = verify_source_closure(root, config)
    return {
        "schema_id": "sbr1_zero_risk_shadow_preflight_v1",
        "status": "RESEARCH_ONLY_DISABLED" if not config.enabled else "OPT_IN_CONFIG_PRESENT",
        "ok": True,
        "authority": AUTHORITY,
        "config_enabled": config.enabled,
        "default_enabled": False,
        "network_calls": False,
        "writes": False,
        "orders_allowed": False,
        "private_api_allowed": False,
        "money_authority": False,
        "release_or_promotion_authority": False,
        "sealed_data_rows_read": 0,
        "config_hash": config.config_hash,
        "manifest_sha256": manifest.manifest_sha256,
        "money_universe": list(config.money_universe),
        "evidence_universe": list(config.evidence_universe),
        "evaluation_universe": list(config.evaluation_universe),
        "evidence_universe_sha256": evidence_manifest.universe_sha256,
        "evidence_manifest_sha256": evidence_manifest_sha256,
        "expected_structurally_unavailable": unavailable,
        "evidence_role": RAW_EVIDENCE_ROLE,
        "fixed51_final_n_eligible": False,
        "promotion_eligible": False,
        "random_control_preregistration_sha256": prereg_sha,
        "source_closure_sha256": closure_hash,
    }


def run_once(
    root: Path,
    config_path: Path,
    *,
    acknowledgement: str,
    get_bytes: Callable[..., bytes] = _public_get_bytes,
) -> dict[str, object]:
    preflight = _preflight(root, config_path)
    config = load_config(config_path)
    if not config.enabled or acknowledgement != ACK:
        raise ShadowViolation("zero_risk_shadow_not_explicitly_enabled")
    manifest = load_and_verify_manifest(
        root,
        root / config.parity_manifest_path,
        verify_data_bytes=False,
        verify_source_bytes=True,
    )
    source_files, source_hashes = _manifest_source_bundle(root, manifest)
    filters = manifest.payload["exchange_filters"]
    observed_filters: dict[str, dict[str, str]] = {}
    timeout = float(config.request_timeout_seconds)
    journal = AppendOnlyShadowJournal(root / config.journal_path)
    before = journal.read()
    btc = fetch_public_klines(
        config.public_base,
        "BTCUSDT",
        "60",
        min(1000, config.regime_bootstrap_bars + 1),
        timeout=timeout,
        get_bytes=get_bytes,
    )
    btc_closed_before_write = _closed_rows(btc)
    if not btc_closed_before_write:
        raise ShadowViolation("btc_closed_h1_missing")
    btc_latest_close = int(str(btc_closed_before_write[-1][0])) + H1_MS
    if btc.observed_at_ms - btc_latest_close < 0:
        raise ShadowViolation("new_regime_bar_not_closed")
    regime = _advance_regime(journal, before, btc, config.regime_bootstrap_bars)
    if btc.observed_at_ms - regime.closed_h1_ts_ms < 0:
        raise ShadowViolation("regime_bar_not_closed")
    regime_age = btc.observed_at_ms - regime.closed_h1_ts_ms

    events = journal.read()
    decisions, fills, terminal, claims = _journal_index(
        events, money_universe=config.money_universe
    )
    active_ids = [decision_id for decision_id in decisions if decision_id not in terminal]
    active_symbols = [str(decisions[decision_id]["symbol"]) for decision_id in active_ids]
    expected_close = regime.closed_h1_ts_ms
    expected_unavailable = {
        str(symbol): str(reason)
        for symbol, reason in dict(
            preflight.get("expected_structurally_unavailable") or {}
        ).items()
    }
    for symbol, reason in sorted(expected_unavailable.items()):
        claim = f"evaluation-unavailable:SBR1:{symbol}:{expected_close}"
        if claim not in claims:
            journal.append(
                "evaluation_unavailable",
                claim,
                {
                    "admitted": False,
                    "authority": AUTHORITY,
                    "availability": "structurally_unavailable",
                    "closed_h1_ts_ms": expected_close,
                    "config_hash": config.config_hash,
                    "evidence_role": RAW_EVIDENCE_ROLE,
                    "expected_gap": True,
                    "money_authority": False,
                    "observed_at_ms": btc.observed_at_ms,
                    "orders_allowed": False,
                    "promotion_eligible": False,
                    "reason": reason,
                    "status": "expected_structural_gap",
                    "symbol": symbol,
                },
            )
            claims.add(claim)
    pending_symbols = tuple(
        symbol
        for symbol in config.evaluation_universe
        if symbol not in expected_unavailable
        and f"evaluation:SBR1:{symbol}:{expected_close}" not in claims
    )
    snapshots, snapshot_errors = _fetch_h1_decision_snapshots(
        config,
        btc,
        get_bytes=get_bytes,
        symbols=pending_symbols,
    )
    evaluations_written = 0
    missed_evaluations = 0
    decisions_admitted = 0
    control_assignments_written = 0
    fetch_errors_written = 0
    cycle_error_symbols: set[str] = set(snapshot_errors)
    attempt_minute = btc.observed_at_ms // 60_000
    for symbol, reason in sorted(snapshot_errors.items()):
        if journal.append(
            "evaluation_fetch_error",
            f"evaluation-fetch-error:SBR1:{symbol}:{expected_close}:{attempt_minute}",
            {
                "authority": AUTHORITY,
                "closed_h1_ts_ms": expected_close,
                "config_hash": config.config_hash,
                "evidence_role": (
                    MAJOR8_EVIDENCE_ROLE
                    if symbol in config.money_universe
                    else RAW_EVIDENCE_ROLE
                ),
                "money_authority": False,
                "observed_at_ms": btc.observed_at_ms,
                "orders_allowed": False,
                "promotion_eligible": False,
                "reason": reason,
                "retryable": True,
                "status": "public_h1_fetch_error",
                "symbol": symbol,
            },
        ):
            fetch_errors_written += 1
    with _frozen_sbr1_env(config.evaluation_universe):
        for symbol in config.evaluation_universe:
            snapshot = snapshots.get(symbol)
            if snapshot is None:
                continue
            closed = _closed_rows(snapshot)
            if len(closed) < config.h1_history_limit:
                if journal.append(
                    "evaluation_data_error",
                    f"evaluation-data-error:SBR1:{symbol}:{expected_close}:{attempt_minute}",
                    {
                        "authority": AUTHORITY,
                        "closed_h1_ts_ms": expected_close,
                        "config_hash": config.config_hash,
                        "evidence_role": (
                            MAJOR8_EVIDENCE_ROLE
                            if symbol in config.money_universe
                            else RAW_EVIDENCE_ROLE
                        ),
                        "money_authority": False,
                        "observed_at_ms": snapshot.observed_at_ms,
                        "orders_allowed": False,
                        "promotion_eligible": False,
                        "reason": "h1_history_short",
                        "received_rows": len(closed),
                        "required_rows": config.h1_history_limit,
                        "retryable": True,
                        "status": "public_h1_data_error",
                        "symbol": symbol,
                    },
                ):
                    fetch_errors_written += 1
                    cycle_error_symbols.add(symbol)
                continue
            closed = closed[-config.h1_history_limit :]
            latest_start = int(str(closed[-1][0]))
            latest_close = latest_start + H1_MS
            claim = f"evaluation:SBR1:{symbol}:{latest_close}"
            if claim in claims:
                continue
            age = snapshot.observed_at_ms - latest_close
            if (
                age < 0
                or age > config.max_decision_age_ms
                or regime_age > config.max_regime_age_ms
            ):
                if journal.append(
                    "evaluation",
                    claim,
                    {
                        "admitted": False,
                        "authority": AUTHORITY,
                        "closed_h1_ts_ms": latest_close,
                        "config_hash": config.config_hash,
                        "decision_age_ms": age,
                        "evidence_role": (
                            MAJOR8_EVIDENCE_ROLE
                            if symbol in config.money_universe
                            else RAW_EVIDENCE_ROLE
                        ),
                        "manifest_sha256": manifest.manifest_sha256,
                        "money_authority": False,
                        "observed_at_ms": snapshot.observed_at_ms,
                        "orders_allowed": False,
                        "promotion_eligible": False,
                        "reason": "production_or_regime_decision_clock_missed",
                        "regime_age_ms": regime_age,
                        "response_sha256": snapshot.response_sha256,
                        "source_closure_sha256": preflight["source_closure_sha256"],
                        "status": "missed_decision_window",
                        "symbol": symbol,
                    },
                ):
                    evaluations_written += 1
                    missed_evaluations += 1
                    cycle_error_symbols.add(symbol)
                continue
            if regime.closed_h1_ts_ms != latest_close:
                raise ShadowViolation(f"regime_symbol_clock_mismatch:{symbol}")
            signal, effective_config, consumed = replay_latest_signal(symbol, closed)
            raw_signal = _signal_payload(signal)
            payload: dict[str, object] = {
                "authority": AUTHORITY,
                "admitted": False,
                "closed_h1_ts_ms": latest_close,
                "config_hash": config.config_hash,
                "decision_age_ms": age,
                "manifest_sha256": manifest.manifest_sha256,
                "money_authority": False,
                "observed_at_ms": snapshot.observed_at_ms,
                "orders_allowed": False,
                "promotion_eligible": False,
                "regime": regime.to_dict(),
                "response_sha256": snapshot.response_sha256,
                "signal": raw_signal,
                "source_closure_sha256": preflight["source_closure_sha256"],
                "status": "no_signal",
                "symbol": symbol,
                "strategy_h1_window_sha256": _sha(
                    {"rows": consumed, "schema_id": "sbr1_consumed_h1_v1"}
                ),
            }
            is_money_symbol = symbol in config.money_universe
            payload["evidence_role"] = (
                MAJOR8_EVIDENCE_ROLE if is_money_symbol else RAW_EVIDENCE_ROLE
            )
            if not is_money_symbol:
                payload.update(
                    {
                        "regime_gate": "context_only_not_admission",
                        "status": (
                            "raw_signal_observed" if signal is not None else "raw_no_signal"
                        ),
                    }
                )
                if journal.append("evaluation", claim, payload):
                    evaluations_written += 1
                continue
            admitted = False
            if signal is not None:
                try:
                    current_filter = fetch_public_filters(
                        config.public_base,
                        symbol,
                        timeout=timeout,
                        get_bytes=get_bytes,
                    )
                    frozen_filter = filters.get(symbol)
                    if frozen_filter is not None:
                        verify_public_filters(current_filter, frozen_filter)
                    observed_filters[symbol] = _observed_filter_mapping(current_filter)
                except ShadowViolation as exc:
                    if journal.append(
                        "evaluation_data_error",
                        f"evaluation-filter-error:SBR1:{symbol}:{latest_close}:{attempt_minute}",
                        {
                            "authority": AUTHORITY,
                            "closed_h1_ts_ms": latest_close,
                            "config_hash": config.config_hash,
                            "evidence_role": MAJOR8_EVIDENCE_ROLE,
                            "money_authority": False,
                            "observed_at_ms": snapshot.observed_at_ms,
                            "orders_allowed": False,
                            "promotion_eligible": False,
                            "reason": getattr(exc, "code", str(exc)),
                            "retryable": True,
                            "status": "public_filter_error",
                            "symbol": symbol,
                        },
                    ):
                        fetch_errors_written += 1
                        cycle_error_symbols.add(symbol)
                    continue
                evidence = closed_h1_evidence_from_row(
                    consumed[-1],
                    row_bytes=_row_bytes(consumed[-1]),
                    observed_at_ms=snapshot.observed_at_ms,
                    max_decision_age_ms=config.max_decision_age_ms,
                )
                plan = adapt_sbr1_live_signal_to_plan(
                    signal,
                    evidence,
                    effective_config,
                    source_files=source_files,
                    expected_source_hashes=source_hashes,
                )
                slot_ok, slot_code = shadow_slot_gate(config, symbol, active_symbols)
                admitted = regime.allows_sbr1() and slot_ok
                payload.update(
                    {
                        "admitted": admitted,
                        "decision_id": plan.decision_id,
                        "decision_plan": plan.decision_payload(),
                        "regime_gate": "accepted" if regime.allows_sbr1() else "blocked",
                        "slot_gate": slot_code,
                        "exchange_filter_observed_at_ms": current_filter.observed_at_ms,
                        "exchange_filter_response_sha256": current_filter.response_sha256,
                        "status": "admitted_decision" if admitted else "signal_blocked",
                        "strategy_h1_rows": [list(row) for row in closed],
                    }
                )
            if admitted:
                decision_id = str(payload.get("decision_id") or "").strip()
                if not decision_id:
                    raise ShadowViolation("admitted_decision_id_missing")
                prereg_sha = preregistration_sha256(root / PREREG_RELATIVE_PATH)
                if prereg_sha != config.expected_preregistration_sha256:
                    raise ShadowViolation("random_control_preregistration_hash_mismatch")
                assignments = build_control_assignments(
                    prereg_sha256=prereg_sha,
                    main_decision_id=decision_id,
                    main_decision_ts_ms=latest_close,
                    now_ms=snapshot.observed_at_ms,
                    main_context={
                        "symbol": plan.symbol,
                        "side": plan.side,
                        "geometry_sha256": plan.profile_hash,
                        "source_sha256": plan.source_hash,
                        "data_sha256": plan.data_hash,
                        "config_sha256": plan.config_hash,
                        "cost_contract_sha256": _sha(
                            {
                                "entry_slippage_bps": str(
                                    config.entry_slippage_bps
                                ),
                                "exit_slippage_bps": str(config.exit_slippage_bps),
                                "fee_bps_per_side": str(config.fee_bps_per_side),
                                "parity_manifest_sha256": manifest.manifest_sha256,
                                "schema_id": "sbr1_shadow_cost_contract_v1",
                            }
                        ),
                    },
                )
                control_journal = AppendOnlyShadowJournal(
                    root
                    / Path(config.journal_path).parent
                    / "random_control_events.jsonl"
                )
                main_written, control_written = persist_controlled_admission(
                    main_journal=journal,
                    main_claim=claim,
                    main_payload=payload,
                    control_journal=control_journal,
                    assignments=assignments,
                )
                control_assignments_written += control_written
            else:
                main_written = journal.append("evaluation", claim, payload)
            if main_written:
                evaluations_written += 1
                if admitted:
                    active_symbols.append(symbol)
                    decisions_admitted += 1

    events = journal.read()
    decisions, fills, terminal, _ = _journal_index(
        events, money_universe=config.money_universe
    )
    fills_written = 0
    outcomes_written = 0
    rejected_written = 0
    now_closed_m5_exclusive = (btc.observed_at_ms // M5_MS) * M5_MS
    for decision_id, decision_payload in decisions.items():
        if decision_id in terminal:
            continue
        plan = plan_from_payload(decision_payload["decision_plan"], decision_id)  # type: ignore[arg-type]
        if plan.symbol not in config.money_universe:
            raise ShadowViolation(f"admitted_non_money_symbol:{plan.symbol}")
        filter_contract = observed_filters.get(plan.symbol) or filters.get(plan.symbol)
        if filter_contract is None:
            raise ShadowViolation(f"public_filter_missing:{plan.symbol}")
        tick = filter_contract["tick_size"]
        policy = policy_for_plan(plan, tick)
        fill_payload = fills.get(decision_id)
        tick_execution: TickNativeShadowExecution
        if fill_payload is None:
            if now_closed_m5_exclusive <= plan.closed_h1_ts_ms:
                continue
            try:
                current_filter = fetch_public_filters(
                    config.public_base,
                    plan.symbol,
                    timeout=timeout,
                    get_bytes=get_bytes,
                )
                frozen_filter = filters.get(plan.symbol)
                if frozen_filter is not None:
                    verify_public_filters(current_filter, frozen_filter)
                filter_contract = _observed_filter_mapping(current_filter)
                observed_filters[plan.symbol] = filter_contract
                fill_rows, response_hashes, observed = fetch_closed_m5_path(
                    config.public_base,
                    plan.symbol,
                    plan.closed_h1_ts_ms,
                    plan.closed_h1_ts_ms + M5_MS,
                    timeout=timeout,
                    max_pages=1,
                    get_bytes=get_bytes,
                )
                row = fill_rows[0]
                tick_execution = tick_native_shadow_execution(
                    plan,
                    policy,
                    row,
                    row_bytes=_row_bytes(row),
                    adverse_slippage_bps=config.entry_slippage_bps,
                    qty_step=filter_contract["qty_step"],
                    min_notional=filter_contract["min_notional"],
                )
            except (ContractViolation, ShadowViolation) as exc:
                code = getattr(exc, "code", str(exc))
                if journal.append(
                    "fill_rejected",
                    f"fill-rejected:{decision_id}",
                    {
                        "authority": AUTHORITY,
                        "decision_id": decision_id,
                        "money_authority": False,
                        "orders_allowed": False,
                        "reason": str(code),
                    },
                ):
                    rejected_written += 1
                continue
            fill_payload = {
                "authority": AUTHORITY,
                "decision_id": decision_id,
                "execution": tick_execution.to_dict(),
                "fill_mode": "simulated_public_next_m5_open_tick_native",
                "money_authority": False,
                "observed_at_ms": observed,
                "orders_allowed": False,
                "response_sha256": response_hashes[0],
                "exchange_filter_observed_at_ms": current_filter.observed_at_ms,
                "exchange_filter_response_sha256": current_filter.response_sha256,
                "row": row,
                "row_sha256": hashlib.sha256(_row_bytes(row)).hexdigest(),
            }
            if journal.append("fill", f"fill:{decision_id}", fill_payload):
                fills_written += 1
        else:
            tick_execution = TickNativeShadowExecution.from_dict(
                fill_payload["execution"], decision_id  # type: ignore[arg-type]
            )

        end_exclusive = min(
            now_closed_m5_exclusive,
            tick_execution.fill.fill_ts_ms + plan.time_stop_hours * H1_MS,
        )
        if end_exclusive <= tick_execution.fill.fill_ts_ms:
            continue
        path_rows, response_hashes, observed = fetch_closed_m5_path(
            config.public_base,
            plan.symbol,
            tick_execution.fill.fill_ts_ms,
            end_exclusive,
            timeout=timeout,
            max_pages=config.max_m5_pages,
            get_bytes=get_bytes,
        )
        outcome = evaluate_prospective_outcome(
            plan,
            tick_execution,
            policy,
            path_rows,
            fee_bps_per_side=config.fee_bps_per_side,
            exit_slippage_bps=config.exit_slippage_bps,
        )
        if outcome.finalized and journal.append(
            "outcome",
            f"outcome:{decision_id}",
            {
                "authority": AUTHORITY,
                "decision_id": decision_id,
                "deadline_ms": outcome.deadline_ms,
                "label": outcome.label,
                "m5_path_rows": path_rows,
                "m5_path_sha256": outcome_rows_hash(path_rows),
                "money_authority": False,
                "net_r": str(outcome.net_r),
                "observed_at_ms": observed,
                "orders_allowed": False,
                "response_sha256": _sha(response_hashes),
                "rows_used": outcome.rows_used,
            },
        ):
            outcomes_written += 1

    final_events = journal.read()
    coverage = _coverage_for_close(
        final_events,
        expected_symbols=config.evidence_universe,
        expected_close=expected_close,
    )
    coverage_degraded = bool(
        coverage["error_count"] or coverage["missing_count"] or cycle_error_symbols
    )
    expected_gap = bool(coverage["structurally_unavailable_count"])
    if coverage_degraded:
        cycle_status = "ZERO_RISK_SHADOW_DEGRADED_PUBLIC_DATA"
    elif expected_gap:
        cycle_status = "ZERO_RISK_SHADOW_OK_EXPECTED_STRUCTURAL_GAP"
    else:
        cycle_status = "ZERO_RISK_SHADOW_OK"
    return {
        "schema_id": "sbr1_zero_risk_shadow_cycle_receipt_v1",
        "status": cycle_status,
        "authority": AUTHORITY,
        "broker_calls": False,
        "private_api_calls": False,
        "orders_created_or_changed": 0,
        "money_authority": False,
        "release_or_promotion_authority": False,
        "promotion_eligible": False,
        "evidence_role": RAW_EVIDENCE_ROLE,
        "fixed51_final_n_eligible": False,
        "sealed_data_rows_read": 0,
        "regime": regime.to_dict(),
        "evaluations_written": evaluations_written,
        "missed_evaluations": missed_evaluations,
        "decisions_admitted": decisions_admitted,
        "control_assignments_written": control_assignments_written,
        "fetch_errors_written": fetch_errors_written,
        "fetch_error_symbols": sorted(snapshot_errors),
        "cycle_error_symbols": sorted(cycle_error_symbols),
        "coverage": coverage,
        "fills_written": fills_written,
        "fill_rejections_written": rejected_written,
        "outcomes_written": outcomes_written,
        "journal_events": len(final_events),
        "journal_tip_sha256": final_events[-1]["event_hash"] if final_events else None,
    }


def _cycle_exit_code(result: Mapping[str, object]) -> int:
    return (
        0
        if result.get("status")
        in {
            "ZERO_RISK_SHADOW_OK",
            "ZERO_RISK_SHADOW_OK_EXPECTED_STRUCTURAL_GAP",
        }
        else 3
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--ack", default="")
    args = parser.parse_args()
    try:
        result = (
            run_once(args.root.resolve(), args.config.resolve(), acknowledgement=args.ack)
            if args.once
            else _preflight(args.root.resolve(), args.config.resolve())
        )
    except Exception as exc:
        print(
            json.dumps(
                {"status": "FAIL_CLOSED", "error": f"{type(exc).__name__}:{exc}"},
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return _cycle_exit_code(result) if args.once else 0


if __name__ == "__main__":
    raise SystemExit(main())
