#!/usr/bin/env python3
"""Public-data-only ATT1+ETS2S zero-risk signal-shadow runner."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import sys
import time
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.att1_ets2s_shadow_journal import HashChainedJournal, JournalViolation
from bot.att1_ets2s_signal_shadow_contract import (
    AUTHORITY,
    PROFILE_CONFIG_HASHES,
    PROFILE_FIXED51_CONFIG_HASHES,
    PROFILE_SOURCE_HASHES,
    PUBLIC_KLINE_ENDPOINT,
    STORE_CONTRACT_ID,
    ContractViolation,
    load_contract,
    load_contract_from_deployment_anchor,
    load_contract_from_deployment_anchor_fd,
    preflight as contract_preflight,
    require_operator_ack,
    resolve_runtime_paths,
    validate_public_endpoint,
)
from bot.public_h1_cache_store import (
    H1_MS,
    CanonicalCachedFeed,
    CanonicalH1Cache,
    PublicCacheViolation,
    classify_stream,
    validate_closed_h1_rows,
)
from bot.sbr1_universe import FIXED51_UNIVERSE
from research_lab.att1_ets2s_signal_shadow_parity import (
    ATT1_PROFILE,
    ETS2S_PROFILE,
    _resolved_config_hash,
    frozen_profile_env,
)
from research_lab.research_ohlcv_store import timeframe_minutes
from strategies.att1_live import ATT1LiveEngine
from strategies.elder_live import ElderShadowEngine
from strategies.signals import TradeSignal


DECISION_SCHEMA_ID = "att1_ets2s_signal_shadow_decision_v1"
CYCLE_SCHEMA_ID = "att1_ets2s_signal_shadow_cycle_v1"
HEARTBEAT_SCHEMA_ID = "att1_ets2s_signal_shadow_heartbeat_v1"
REPLAY_DECISION_BARS = 48
_SYMBOL = re.compile(r"[A-Z0-9]{2,40}\Z")


class PublicFetchViolation(ValueError):
    """Fail-closed public transport or response violation."""


class PublicSymbolUnavailable(PublicFetchViolation):
    """A public symbol is structurally unavailable from the approved endpoint."""


class RunnerViolation(ValueError):
    """Fail-closed runner contract violation."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise RunnerViolation("noncanonical runner payload") from exc


def validate_public_request(endpoint: str, params: Mapping[str, object]) -> dict[str, object]:
    validate_public_endpoint(endpoint)
    expected = {"category", "interval", "limit", "symbol"}
    if "end" in params:
        expected.add("end")
    if set(params) != expected:
        raise PublicFetchViolation("unexpected public request parameters")
    symbol = str(params.get("symbol") or "")
    if _SYMBOL.fullmatch(symbol) is None or symbol not in FIXED51_UNIVERSE:
        raise PublicFetchViolation("unsafe public symbol")
    if params.get("category") != "linear" or params.get("interval") != "60":
        raise PublicFetchViolation("unapproved public market contract")
    limit = params.get("limit")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise PublicFetchViolation("invalid public page limit")
    if "end" in params:
        end = params["end"]
        if isinstance(end, bool) or not isinstance(end, int) or end < 0:
            raise PublicFetchViolation("invalid public page cursor")
    return dict(params)


def parse_public_payload(
    payload: object, *, symbol: str, limit: int, max_response_bytes: int
) -> list[list[object]]:
    try:
        size = len(_canonical(payload))
    except RunnerViolation as exc:
        raise PublicFetchViolation("malformed public response") from exc
    if size > int(max_response_bytes):
        raise PublicFetchViolation("oversized public response")
    if not isinstance(payload, Mapping):
        raise PublicFetchViolation("public response is not an object")
    if payload.get("retCode") != 0:
        raise PublicFetchViolation(f"public response retCode={payload.get('retCode')}")
    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise PublicFetchViolation("public response result is invalid")
    if result.get("category", "linear") != "linear":
        raise PublicFetchViolation("public response category mismatch")
    if result.get("symbol", symbol) != symbol:
        raise PublicFetchViolation("public response symbol mismatch")
    rows = result.get("list")
    if not isinstance(rows, list) or len(rows) > limit:
        raise PublicFetchViolation("public response rows are invalid")
    if any(not isinstance(row, list) or len(row) < 6 for row in rows):
        raise PublicFetchViolation("public response row is malformed")
    return rows


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise PublicFetchViolation("public endpoint redirect rejected")


def _network_fetch(endpoint: str, params: dict[str, object], *, max_response_bytes: int) -> object:
    validate_public_request(endpoint, params)
    request = Request(
        f"{endpoint}?{urlencode(params)}",
        headers={"User-Agent": "att1-ets2s-public-shadow/1"},
    )
    try:
        with build_opener(_RejectRedirects).open(request, timeout=20) as response:
            if response.status != 200:
                raise PublicFetchViolation(f"public HTTP status {response.status}")
            data = response.read(max_response_bytes + 1)
    except PublicFetchViolation:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise PublicFetchViolation("public request failed") from exc
    if len(data) > max_response_bytes:
        raise PublicFetchViolation("oversized public response")
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PublicFetchViolation("public response JSON is invalid") from exc


def fetch_public_page(
    fetch: Callable[[str, dict[str, object]], object],
    symbol: str,
    *,
    limit: int,
    max_response_bytes: int,
    end: int | None = None,
) -> list[list[object]]:
    params: dict[str, object] = {
        "category": "linear",
        "interval": "60",
        "limit": int(limit),
        "symbol": str(symbol),
    }
    if end is not None:
        params["end"] = int(end)
    validate_public_request(PUBLIC_KLINE_ENDPOINT, params)
    payload = fetch(PUBLIC_KLINE_ENDPOINT, params)
    return parse_public_payload(
        payload, symbol=symbol, limit=limit, max_response_bytes=max_response_bytes
    )


def fetch_closed_history(
    fetch: Callable[[str, dict[str, object]], object],
    symbol: str,
    *,
    observed_at_ms: int,
    min_bars: int,
    page_limit: int,
    max_response_bytes: int,
) -> list[list[float | int]]:
    by_timestamp: dict[int, list[float | int]] = {}
    end: int | None = None
    previous_earliest: int | None = None
    for _page_number in range(16):
        page = fetch_public_page(
            fetch,
            symbol,
            limit=page_limit,
            end=end,
            max_response_bytes=max_response_bytes,
        )
        if not page:
            break
        closed = validate_closed_h1_rows(page, observed_at_ms, min_bars=0)
        if not closed:
            break
        for row in closed:
            timestamp = int(row[0])
            prior = by_timestamp.get(timestamp)
            if prior is not None and prior != row:
                raise PublicFetchViolation("conflicting public H1 page overlap")
            by_timestamp[timestamp] = row
        rows = [by_timestamp[key] for key in sorted(by_timestamp)]
        try:
            validated = validate_closed_h1_rows(rows, observed_at_ms, min_bars=0)
        except PublicCacheViolation as exc:
            raise PublicFetchViolation(str(exc)) from exc
        if len(validated) >= min_bars:
            return validated
        earliest = int(closed[0][0])
        if previous_earliest is not None and earliest >= previous_earliest:
            raise PublicFetchViolation("public pagination did not move backward")
        previous_earliest = earliest
        if earliest == 0:
            break
        end = earliest - 1
    raise PublicSymbolUnavailable(f"insufficient closed H1 history:{symbol}")


class CausalCanonicalFeed:
    """Cursor-scoped feed delegating every H1/H4/D1 view to the canonical Store."""

    def __init__(self, symbol: str, rows: Sequence[Sequence[object]]):
        self.symbol = symbol
        self.rows = [list(row) for row in rows]
        self.cursor = -1
        self._feed: CanonicalCachedFeed | None = None
        self.requested_timeframes: set[int] = set()

    def set_cursor(self, cursor: int) -> None:
        if cursor < 0 or cursor >= len(self.rows):
            raise RunnerViolation("causal feed cursor outside history")
        self.cursor = int(cursor)
        self._feed = CanonicalCachedFeed(self.symbol, self.rows[: self.cursor + 1])

    def __call__(self, symbol: str, timeframe: object, limit: int) -> list:
        if self._feed is None:
            raise RunnerViolation("causal feed cursor is unset")
        minutes = timeframe_minutes(timeframe)
        self.requested_timeframes.add(minutes)
        return self._feed(symbol, timeframe, limit)


def _signal_payload(signal: TradeSignal | None) -> dict[str, object] | None:
    if signal is None:
        return None
    return {
        "side": str(signal.side),
        "entry": float(signal.entry),
        "sl": float(signal.sl),
        "tps": [float(value) for value in list(signal.tps or [])],
        "tp_fracs": [float(value) for value in list(signal.tp_fracs or [])],
        "reason": str(signal.reason or ""),
        "time_stop_bars_5m": int(signal.time_stop_bars),
    }


def evaluate_symbol_decisions(
    *,
    symbol: str,
    rows: Sequence[Sequence[object]],
    observed_at_ms: int,
    stream: str,
    cycle_id: str,
    cache_hash: str,
) -> list[dict[str, object]]:
    if len(rows) < 120:
        raise RunnerViolation("strategy history is too short")
    latest = list(rows[-1])
    bar_start = int(latest[0])
    bar_close = bar_start + H1_MS
    output: list[dict[str, object]] = []
    for profile in (ATT1_PROFILE, ETS2S_PROFILE):
        signal: TradeSignal | None = None
        exception: str | None = None
        reason = ""
        feed = CausalCanonicalFeed(symbol, rows)
        with frozen_profile_env(profile, FIXED51_UNIVERSE):
            engine = ATT1LiveEngine(feed) if profile.sleeve_id == "ATT1" else ElderShadowEngine(feed)
            strategy = engine._get_strategy(symbol)
            resolved_hash = _resolved_config_hash(profile, strategy, FIXED51_UNIVERSE)
            if resolved_hash != PROFILE_FIXED51_CONFIG_HASHES[profile.sleeve_id]:
                raise RunnerViolation(f"resolved profile drift:{profile.sleeve_id}")
            start = max(0, len(rows) - REPLAY_DECISION_BARS)
            for index in range(start, len(rows)):
                feed.set_cursor(index)
                bar = rows[index]
                try:
                    signal = engine.signal(
                        symbol, *bar, observed_at_ms=int(bar[0]) + H1_MS
                    )
                except Exception as exc:  # exceptions are evidence, never no-signal
                    exception = f"{type(exc).__name__}: {str(exc)[:240]}"
                    signal = None
                    break
            if signal is None and exception is None:
                reason = str(engine.last_no_signal_reason(symbol) or "unspecified_no_signal")
        claim = f"decision:{stream}:{profile.sleeve_id}:{symbol}:{bar_close}"
        output.append(
            {
                "schema_id": DECISION_SCHEMA_ID,
                "claim_key": claim,
                "authority": AUTHORITY,
                "sleeve_id": profile.sleeve_id,
                "symbol": symbol,
                "bar_start_ms": bar_start,
                "bar_close_ms": bar_close,
                "observed_at_ms": int(observed_at_ms),
                "decision_age_ms": int(observed_at_ms) - bar_close,
                "stream": stream,
                "cycle_id": cycle_id,
                "signal": _signal_payload(signal) if exception is None else None,
                "no_signal_reason": reason if signal is None and exception is None else "",
                "exception": exception,
                "entry_type": profile.entry_type,
                "entry_offset": profile.entry_offset,
                "entry_wait_bars": profile.entry_wait_bars,
                "stop_transform_id": profile.stop_transform_id,
                "time_stop_hours": profile.time_stop_hours,
                "l1_profile_config_hash": PROFILE_CONFIG_HASHES[profile.sleeve_id],
                "profile_config_hash": PROFILE_FIXED51_CONFIG_HASHES[profile.sleeve_id],
                "profile_source_hash": PROFILE_SOURCE_HASHES[profile.sleeve_id],
                "store_contract_id": STORE_CONTRACT_ID,
                "requested_timeframes": sorted(feed.requested_timeframes),
                "cache_rows": len(rows),
                "cache_hash": cache_hash,
                "orders_allowed": False,
                "private_api_allowed": False,
                "money_authority": False,
                "broker_calls": 0,
                "order_calls": 0,
            }
        )
    return output


def _secure_runtime_dirs(paths: Mapping[str, Path]) -> None:
    directories = {
        paths["cache"], paths["journal"].parent, paths["heartbeat"].parent, paths["state"].parent
    }
    for directory in sorted(directories, key=lambda item: len(item.parts)):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory.is_symlink() or not directory.is_dir():
            raise RunnerViolation("unsafe runtime directory")
        os.chmod(directory, 0o700)


def _require_runtime_free_space(path: Path, minimum_free_bytes: int) -> None:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        free = int(shutil.disk_usage(probe).free)
    except OSError as exc:
        raise RunnerViolation("runtime free-space guard unavailable") from exc
    if free < minimum_free_bytes:
        raise RunnerViolation("runtime free-space guard below minimum")


def _atomic_json(path: Path, value: object) -> None:
    data = _canonical(value) + b"\n"
    parent_fd = os.open(
        path.parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    temp_name = f".{path.name}.{secrets.token_hex(12)}.tmp"
    file_fd = -1
    try:
        file_fd = os.open(
            temp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        os.fchmod(file_fd, 0o600)
        view = memoryview(data)
        while view:
            view = view[os.write(file_fd, view) :]
        os.fsync(file_fd)
        os.close(file_fd)
        file_fd = -1
        os.replace(temp_name, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
    except OSError as exc:
        if file_fd >= 0:
            os.close(file_fd)
        try:
            os.unlink(temp_name, dir_fd=parent_fd)
        except OSError:
            pass
        raise RunnerViolation("atomic heartbeat write failed") from exc
    finally:
        os.close(parent_fd)


def run_cycle(
    root: Path,
    config_path: Path,
    acknowledgement: str | None,
    *,
    expected_config_sha256: str,
    expected_manifest_sha256: str,
    fetch: Callable[[str, dict[str, object]], object] | None = None,
    observed_at_ms: int | None = None,
) -> dict[str, object]:
    observed = int(observed_at_ms if observed_at_ms is not None else time.time() * 1000)
    contract = load_contract(
        root,
        config_path,
        expected_config_sha256=expected_config_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    if not contract.enabled:
        raise RunnerViolation("signal shadow is disabled")
    require_operator_ack(contract, acknowledgement)
    paths = resolve_runtime_paths(root, contract)
    _require_runtime_free_space(
        paths["state"].parent,
        int(contract.data_policy["min_runtime_free_bytes"]),
    )
    _secure_runtime_dirs(paths)
    policy = contract.data_policy
    cache = CanonicalH1Cache(paths["cache"], max_bars=int(policy["max_cache_h1_bars"]))
    journal = HashChainedJournal(paths["journal"])
    existing_claims = set(journal.claim_keys())
    transport = fetch or (
        lambda endpoint, params: _network_fetch(
            endpoint, params, max_response_bytes=int(policy["max_response_bytes"])
        )
    )
    cycle_id = f"cycle:{observed}"
    errors: list[dict[str, str]] = []
    expected_unavailable: list[str] = []
    available: list[str] = []
    unchanged_symbols: list[str] = []
    coverage = {"ATT1": 0, "ETS2S": 0}
    signals = {"ATT1": 0, "ETS2S": 0}
    no_signals = {"ATT1": 0, "ETS2S": 0}
    exceptions = {"ATT1": 0, "ETS2S": 0}
    stream_counts = {"ALPHA_FORWARD_BACKFILL": 0, "EXECUTION_FORWARD": 0}
    rows_written = 0
    for symbol in contract.evidence_universe:
        try:
            cached_rows, before = cache.load(symbol)
            was_empty = not cached_rows
            if was_empty:
                incoming = fetch_closed_history(
                    transport,
                    symbol,
                    observed_at_ms=observed,
                    min_bars=int(policy["min_bootstrap_h1_bars"]),
                    page_limit=int(policy["page_limit"]),
                    max_response_bytes=int(policy["max_response_bytes"]),
                )
            else:
                page = fetch_public_page(
                    transport,
                    symbol,
                    limit=int(policy["page_limit"]),
                    max_response_bytes=int(policy["max_response_bytes"]),
                )
                incoming = validate_closed_h1_rows(page, observed, min_bars=1)
            cache.merge(symbol, incoming, observed)
            rows, after = cache.load(symbol)
            if len(rows) < int(policy["min_bootstrap_h1_bars"]):
                raise RunnerViolation("cache below bootstrap minimum")
            available.append(symbol)
            if not was_empty and after.last_start_ms == before.last_start_ms:
                unchanged_symbols.append(symbol)
                continue
            if was_empty:
                stream = "ALPHA_FORWARD_BACKFILL"
            else:
                stream = classify_stream(
                    bar_close_ts_ms=int(after.latest_close_ms),
                    observed_at_ms=observed,
                    max_forward_lag_ms=int(policy["max_forward_lag_ms"]),
                )
                if stream != "EXECUTION_FORWARD":
                    raise RunnerViolation("newly closed H1 was not observed within forward lag")
            latest_close = int(after.latest_close_ms)
            claims = {
                sleeve: f"decision:{stream}:{sleeve}:{symbol}:{latest_close}"
                for sleeve in ("ATT1", "ETS2S")
            }
            if all(claim in existing_claims for claim in claims.values()):
                unchanged_symbols.append(symbol)
                continue
            decisions = evaluate_symbol_decisions(
                symbol=symbol,
                rows=rows,
                observed_at_ms=observed,
                stream=stream,
                cycle_id=cycle_id,
                cache_hash=after.rows_hash,
            )
            if {row.get("sleeve_id") for row in decisions} != {"ATT1", "ETS2S"}:
                raise RunnerViolation("incomplete strategy decision pair")
            for decision in decisions:
                sleeve = str(decision["sleeve_id"])
                coverage[sleeve] += 1
                if decision.get("exception"):
                    exceptions[sleeve] += 1
                    errors.append({"symbol": symbol, "error": str(decision["exception"])})
                elif decision.get("signal") is None:
                    no_signals[sleeve] += 1
                else:
                    signals[sleeve] += 1
                stream_counts[stream] += 1
                if journal.append(decision):
                    rows_written += 1
                    existing_claims.add(str(decision["claim_key"]))
        except PublicSymbolUnavailable as exc:
            if symbol in contract.expected_unavailable_symbols:
                expected_unavailable.append(symbol)
            else:
                errors.append({"symbol": symbol, "error": f"unexpected_unavailable:{exc}"})
        except (ContractViolation, PublicFetchViolation, PublicCacheViolation, JournalViolation, RunnerViolation) as exc:
            errors.append({"symbol": symbol, "error": f"{type(exc).__name__}:{str(exc)}"})
        except Exception as exc:
            errors.append({"symbol": symbol, "error": f"unexpected:{type(exc).__name__}:{str(exc)[:240]}"})
    tip = journal.tip()
    healthy = (
        not errors
        and sum(exceptions.values()) == 0
        and len(available) + len(expected_unavailable) == len(contract.evidence_universe)
    )
    receipt: dict[str, object] = {
        "schema_id": CYCLE_SCHEMA_ID,
        "authority": AUTHORITY,
        "cycle_id": cycle_id,
        "observed_at_ms": observed,
        "healthy": healthy,
        "evidence_universe_count": len(contract.evidence_universe),
        "available_symbols": sorted(available),
        "expected_unavailable": sorted(expected_unavailable),
        "unchanged_symbols": sorted(unchanged_symbols),
        "coverage": coverage,
        "signals": signals,
        "no_signals": no_signals,
        "exceptions": exceptions,
        "stream_counts": stream_counts,
        "rows_written": rows_written,
        "errors": errors,
        "journal": tip,
        "config_sha256": expected_config_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "source_closure_sha256": contract.source_closure_sha256,
        "evidence_universe_sha256": contract.evidence_universe_sha256,
        "store_contract_id": contract.store_contract_id,
        "orders_allowed": False,
        "private_api_allowed": False,
        "money_authority": False,
        "broker_calls": 0,
        "order_calls": 0,
    }
    _atomic_json(paths["heartbeat"], {"schema_id": HEARTBEAT_SCHEMA_ID, **receipt})
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--once", action="store_true")
    anchor_group = parser.add_mutually_exclusive_group(required=True)
    anchor_group.add_argument("--deployment-anchor", type=Path)
    anchor_group.add_argument("--deployment-anchor-fd", type=int)
    args = parser.parse_args(argv)
    root = Path(os.path.abspath(os.fspath(args.root)))
    config = args.config or root / "configs/att1_ets2s_signal_shadow_v1.json"
    try:
        if args.deployment_anchor_fd is not None:
            _, anchor = load_contract_from_deployment_anchor_fd(
                root,
                config,
                args.deployment_anchor_fd,
            )
        else:
            _, anchor = load_contract_from_deployment_anchor(
                root,
                config,
                args.deployment_anchor,
            )
        expected_config_sha256 = str(anchor["config_sha256"])
        expected_manifest_sha256 = str(anchor["manifest_sha256"])
        if args.once:
            result = run_cycle(
                root,
                config,
                str(anchor["acknowledgement"]),
                expected_config_sha256=expected_config_sha256,
                expected_manifest_sha256=expected_manifest_sha256,
            )
            code = 0 if result.get("healthy") is True else 1
        else:
            result = contract_preflight(
                root,
                config,
                expected_config_sha256=expected_config_sha256,
                expected_manifest_sha256=expected_manifest_sha256,
            )
            code = 0
    except (ContractViolation, PublicFetchViolation, PublicCacheViolation, JournalViolation, RunnerViolation) as exc:
        result = {
            "schema_id": CYCLE_SCHEMA_ID,
            "healthy": False,
            "error": f"{type(exc).__name__}:{exc}",
        }
        code = 1
    print(_canonical(result).decode("ascii"))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
