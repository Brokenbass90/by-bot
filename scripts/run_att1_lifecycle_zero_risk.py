#!/usr/bin/env python3
"""Public-only ATT1 lifecycle simulation runner."""

from __future__ import annotations

import json
import hashlib
import argparse
import os
import re
import sys
import tempfile
import time
import stat
import fcntl
import shutil
import signal as signal_module
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener
from urllib.parse import urlencode
from urllib.error import URLError
from fractions import Fraction
from pathlib import Path
from typing import Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.sbr1_universe import FIXED51_UNIVERSE
from research_lab.att1_lifecycle_profile import build_profile
from research_lab.att1_lifecycle_session import LifecycleSession, implementation_hash
from research_lab.att1_lifecycle_profile import admit_signal, ProfileViolation
from research_lab.att1_lifecycle_coordinator import replay_lifecycle
from research_lab.att1_lifecycle_journal import LifecycleJournal
from research_lab.att1_lifecycle_public_inputs import signal_from_rows
from bot.public_h1_cache_store import CanonicalH1Cache, validate_closed_h1_rows, PublicCacheViolation, H1_MS


AUTHORITY = {
    "money_authority": False,
    "orders_allowed": False,
    "private_api_allowed": False,
    "promotion_authority": False,
}
CONFIG_FIELDS = {
    "schema_id", "enabled", "authority", "profile_sha256", "runtime_dir",
    "l1_cache_dir", "public_base_url", "poll_seconds", "max_response_bytes",
    "min_free_bytes", "scenario_taker_fee_rate", "max_book_participation", "epoch_id",
}


class RunnerViolation(ValueError):
    """The public-only runner cannot establish a required safety invariant."""


PUBLIC_BASE_URL = "https://api.bybit.com"
PUBLIC_ENDPOINTS = {
    "/v5/market/kline": {"category", "symbol", "interval", "limit", "start", "end"},
    "/v5/market/instruments-info": {"category", "symbol", "limit", "cursor"},
    "/v5/market/orderbook": {"category", "symbol", "limit"},
    "/v5/market/funding/history": {"category", "symbol", "limit", "startTime", "endTime"},
    "/v5/market/mark-price-kline": {"category", "symbol", "interval", "limit", "start", "end"},
}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _fraction_text(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        raise RunnerViolation("nonterminating decimal")
    places = max(twos, fives)
    coefficient = value.numerator * 2 ** (places - twos) * 5 ** (places - fives)
    raw = str(abs(coefficient)).rjust(places + 1, "0")
    return ("-" if coefficient < 0 else "") + raw[:-places] + "." + raw[-places:]


def _decimal(value: object, field: str, *, positive: bool = False) -> Fraction:
    if (not isinstance(value, str) or not value or len(value) > 128
            or len(value.replace('.', '').lstrip('-')) > 64
            or re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?', value) is None):
        raise RunnerViolation(f"invalid decimal:{field}")
    try:
        parsed = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise RunnerViolation(f"invalid decimal:{field}") from exc
    if positive and parsed <= 0:
        raise RunnerViolation(f"invalid decimal:{field}")
    return parsed


def _integer(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise RunnerViolation(f"invalid integer:{field}")
    return value


def _snapshot_levels(snapshot: Mapping[str, object], side: str) -> tuple[int, list[list[object]]]:
    required = {"ts", "cts", "u", "seq", "b", "a"}
    if not isinstance(snapshot, Mapping) or set(snapshot) != required:
        raise RunnerViolation("orderbook fields")
    _integer(snapshot["ts"], "book ts")
    cts = _integer(snapshot["cts"], "book cts")
    _integer(snapshot["u"], "book update")
    _integer(snapshot["seq"], "book sequence")
    bids = snapshot["b"]
    asks = snapshot["a"]
    if not isinstance(bids, list) or not isinstance(asks, list) or not bids or not asks:
        raise RunnerViolation("orderbook levels")
    best_bid = _decimal(bids[0][0], "book bid", positive=True) if isinstance(bids[0], list) and len(bids[0]) == 2 else None
    best_ask = _decimal(asks[0][0], "book ask", positive=True) if isinstance(asks[0], list) and len(asks[0]) == 2 else None
    if best_bid is None or best_ask is None or best_bid >= best_ask:
        raise RunnerViolation("orderbook crossed")
    levels = snapshot["b" if side == "bid" else "a"]
    if not isinstance(levels, list) or not levels:
        raise RunnerViolation("orderbook levels")
    parsed: list[tuple[Fraction, Fraction]] = []
    for level in levels:
        if not isinstance(level, list) or len(level) != 2:
            raise RunnerViolation("orderbook level")
        parsed.append((_decimal(level[0], "book price", positive=True), _decimal(level[1], "book qty", positive=True)))
    prices = [price for price, _qty in parsed]
    if any(left <= right for left, right in zip(prices, prices[1:])) if side == "bid" else any(left >= right for left, right in zip(prices, prices[1:])):
        raise RunnerViolation("orderbook sort")
    return cts, [list(level) for level in levels]


def simulate_ioc_fills(
    snapshot: Mapping[str, object], *, decision_id: str, order_id: str, kind: str,
    requested_qty: str, qty_step: str, submit_ms: int, received_ms: int, source_sha256: str,
) -> list[dict[str, object]]:
    """Derive capped simulated IOC fills from one post-submit public book snapshot."""

    if kind not in {"ENTRY_FILL", "EXIT_FILL"}:
        raise RunnerViolation("IOC fill kind")
    if not isinstance(decision_id, str) or SHA256.fullmatch(decision_id) is None:
        raise RunnerViolation("IOC decision")
    if not isinstance(order_id, str) or not order_id:
        raise RunnerViolation("IOC order")
    if not isinstance(source_sha256, str) or SHA256.fullmatch(source_sha256) is None:
        raise RunnerViolation("IOC source hash")
    submit = _integer(submit_ms, "submit ms")
    received = _integer(received_ms, "receive ms")
    if received < submit:
        raise RunnerViolation("IOC receive clock")
    cts, levels = _snapshot_levels(snapshot, "bid" if kind == "ENTRY_FILL" else "ask")
    if cts > received:
        raise RunnerViolation("IOC exchange after receive")
    if cts < submit or received - cts > 2_000:
        return []
    requested = _decimal(requested_qty, "requested qty", positive=True)
    step = _decimal(qty_step, "qty step", positive=True)
    if requested % step:
        raise RunnerViolation("IOC requested qty step")
    remaining = requested
    fills: list[dict[str, object]] = []
    for index, level in enumerate(levels):
        if remaining <= 0:
            break
        price = _decimal(level[0], "book price", positive=True)
        displayed = _decimal(level[1], "book qty", positive=True)
        quantity = min(remaining, displayed * Fraction(5, 100))
        quantity = (quantity // step) * step
        if quantity <= 0:
            continue
        stable = hashlib.sha256(
            json.dumps(
                {"decision_id": decision_id, "order_id": order_id, "kind": kind,
                 "book_u": snapshot["u"], "book_seq": snapshot["seq"], "level": index,
                 "price": _fraction_text(price), "qty": _fraction_text(quantity)},
                sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            ).encode("ascii")
        ).hexdigest()
        fills.append({
            "schema_id": "att1_lifecycle_event_v1", "event_id": f"ioc:{stable}", "kind": kind,
            "exchange_ms": cts, "received_ms": received, "source_sha256": source_sha256,
            "execution_id": f"public-sim:{stable}", "qty": _fraction_text(quantity),
            "price": _fraction_text(price), "fee_amount": _fraction_text(quantity * price * Fraction("0.001")),
            "fee_source_sha256": source_sha256, "liquidity": "TAKER",
        })
        remaining -= quantity
    return fills


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise RunnerViolation("noncanonical state") from exc


def persist_events(session: LifecycleSession, events: list[Mapping[str, object]]) -> dict[str, object]:
    """Append each immutable public-simulation event before returning its receipt."""

    if not isinstance(session, LifecycleSession) or not isinstance(events, list):
        raise RunnerViolation("persistence inputs")
    receipt = session.receipt
    for event in events:
        if not isinstance(event, Mapping):
            raise RunnerViolation("persistence event")
        receipt = session.apply(dict(event))
    return receipt


def _normalized_receipt(receipt: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(receipt, Mapping):
        raise RunnerViolation("session receipt")
    plan = receipt.get("plan")
    accounting = receipt.get("accounting")
    if not isinstance(plan, Mapping) or not isinstance(accounting, Mapping):
        raise RunnerViolation("session receipt")
    normalized = {
        "decision_id": plan.get("decision_id"), "symbol": plan.get("symbol"),
        "held_qty": receipt.get("held_qty"), "pending_entry_qty": receipt.get("pending_entry_qty"),
        "protected_qty": receipt.get("protected_qty"), "pending_exit": receipt.get("pending_exit"),
        "incidents": receipt.get("incidents"), "final_net_r": receipt.get("final_net_r"),
        "costs_complete": accounting.get("costs_complete"), "known_fee_total": accounting.get("known_fee_total"),
        "settled_funding": accounting.get("settled_funding"), "lifecycle_terminal": receipt.get("lifecycle_terminal"),
        "authority": receipt.get("authority"),
    }
    return normalized


def verify_state(paths: list[Path], profile: Mapping[str, object]) -> dict[str, object]:
    """Replay existing journals only and export a pid/wallclock-independent state digest."""

    if not isinstance(paths, list):
        raise RunnerViolation("verification paths")
    sessions = []
    for path in paths:
        receipt = LifecycleSession(Path(path), dict(profile)).refresh()
        normalized = _normalized_receipt(receipt)
        normalized["full_receipt_sha256"] = hashlib.sha256(_canonical(receipt)).hexdigest()
        normalized["receipt_sha256"] = hashlib.sha256(_canonical(normalized)).hexdigest()
        sessions.append(normalized)
    sessions.sort(key=lambda value: str(value["decision_id"]))
    state = {
        "schema_id": "att1_lifecycle_public_state_v1", "authority": dict(AUTHORITY),
        "continuous_market_path_verified": False, "execution_parity": False,
        "actual_account_costs_verified": False, "promotion_pass": False, "sessions": sessions,
    }
    state["state_sha256"] = hashlib.sha256(_canonical(state)).hexdigest()
    return state


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RunnerViolation("duplicate JSON key")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> object:
    raise RunnerViolation(f"nonfinite JSON:{value}")


def decode_public_json(raw: bytes, max_response_bytes: int) -> dict[str, object]:
    """Decode a bounded Bybit public response with duplicate/nonfinite rejection."""

    if type(max_response_bytes) is not int or max_response_bytes < 1:
        raise RunnerViolation("response byte cap")
    if not isinstance(raw, bytes) or not raw or len(raw) > max_response_bytes:
        raise RunnerViolation("response byte cap")
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_no_duplicates, parse_constant=_reject_nonfinite
        )
    except RunnerViolation:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RunnerViolation("invalid public JSON") from exc
    if not isinstance(value, dict):
        raise RunnerViolation("public response object")
    if "retCode" in value and type(value["retCode"]) is not int:
        raise RunnerViolation("public retCode")
    return value


def validate_public_request(path: str, params: Mapping[str, object]) -> None:
    if path not in PUBLIC_ENDPOINTS:
        raise RunnerViolation("endpoint allowlist")
    if not isinstance(params, Mapping) or set(params) - PUBLIC_ENDPOINTS[path]:
        raise RunnerViolation("public request fields")
    if params.get("category") != "linear":
        raise RunnerViolation("public request category")
    symbol = params.get("symbol")
    if path != "/v5/market/instruments-info" or symbol is not None:
        if not isinstance(symbol, str) or symbol not in FIXED51_UNIVERSE:
            raise RunnerViolation("public request symbol")
    for field in ("limit", "start", "end", "startTime", "endTime"):
        if field in params and (type(params[field]) is not int or int(params[field]) < 0):
            raise RunnerViolation(f"public request {field}")
    if "limit" in params and not 1 <= int(params["limit"]) <= 1000:
        raise RunnerViolation("public request limit")
    if path == "/v5/market/kline" and params.get("interval") != "60":
        raise RunnerViolation("public request H1 interval")
    if path == "/v5/market/mark-price-kline" and params.get("interval") != "1":
        raise RunnerViolation("public request mark interval")
    if "start" in params and "end" in params and int(params["start"]) > int(params["end"]):
        raise RunnerViolation("public request time window")
    if "startTime" in params and "endTime" in params and int(params["startTime"]) > int(params["endTime"]):
        raise RunnerViolation("public request time window")


def request_public(
    transport: Callable[..., bytes], path: str, params: Mapping[str, object], *, symbol: str | None,
    max_response_bytes: int,
) -> dict[str, object]:
    """Perform one injected, GET-only unauthenticated public request."""

    validate_public_request(path, params)
    raw = transport(PUBLIC_BASE_URL + path, dict(params), timeout_seconds=10, headers={})
    value = decode_public_json(raw, max_response_bytes)
    if type(value.get("retCode")) is not int or value["retCode"] != 0:
        raise RunnerViolation("public retCode")
    result = value.get("result")
    if not isinstance(result, dict):
        raise RunnerViolation("public result")
    if path == "/v5/market/orderbook":
        if result.get("s") != symbol or not all(key in result for key in ("b", "a", "ts", "u", "seq", "cts")):
            raise RunnerViolation("public orderbook result")
    elif path in {"/v5/market/funding/history", "/v5/market/instruments-info"}:
        rows = result.get("list")
        if result.get("category") != "linear" or not isinstance(rows, list) or any(not isinstance(row, dict) or row.get("symbol") != symbol for row in rows):
            raise RunnerViolation("public funding result")
    else:
        if result.get("category") != "linear" or (symbol is not None and result.get("symbol") != symbol):
            raise RunnerViolation("public result category/symbol")
    return value


def load_config(path: Path) -> dict[str, object]:
    """Load the complete, default-off public runner configuration without defaults."""

    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_no_duplicates, parse_constant=_reject_nonfinite)
    except (OSError, UnicodeError, json.JSONDecodeError, RunnerViolation) as exc:
        raise RunnerViolation("config unreadable") from exc
    if not isinstance(value, dict) or set(value) != CONFIG_FIELDS:
        raise RunnerViolation("config fields")
    if value["schema_id"] != "att1_lifecycle_public_config_v1":
        raise RunnerViolation("config schema")
    if type(value["enabled"]) is not bool:
        raise RunnerViolation("config enabled")
    if not isinstance(value["authority"], dict) or set(value["authority"]) != set(AUTHORITY) or any(value["authority"][key] is not False for key in AUTHORITY):
        raise RunnerViolation("config authority")
    if value["public_base_url"] != "https://api.bybit.com":
        raise RunnerViolation("config public base url")
    if not isinstance(value["profile_sha256"], str) or SHA256.fullmatch(value["profile_sha256"]) is None:
        raise RunnerViolation("config profile sha")
    for field in ("runtime_dir", "l1_cache_dir", "epoch_id"):
        if not isinstance(value[field], str) or not value[field]:
            raise RunnerViolation(f"config {field}")
    for field, expected in (("poll_seconds", 1), ("max_response_bytes", 5_000_000),
                            ("min_free_bytes", 536_870_912)):
        if type(value[field]) is not int or value[field] != expected:
            raise RunnerViolation(f"config {field}")
    if value["scenario_taker_fee_rate"] != "0.001" or value["max_book_participation"] != "0.05":
        raise RunnerViolation("config declared simulation")
    if not Path(value["runtime_dir"]).is_absolute() or not Path(value["l1_cache_dir"]).is_absolute():
        raise RunnerViolation("config absolute paths")
    cache = Path(value["l1_cache_dir"])
    if not cache.is_dir() or cache.is_symlink():
        raise RunnerViolation("config l1 cache")
    return value


def preflight(config_path: Path, *, root: Path) -> dict[str, object]:
    """Validate source-bound profile and read-only L1 inputs without network or writes."""

    config = load_config(config_path)
    profile = build_profile(Path(root))
    if config["profile_sha256"] != profile["profile_sha256"]:
        raise RunnerViolation("profile hash mismatch")
    return {
        "schema_id": "att1_lifecycle_public_preflight_v1", "profile_sha256": profile["profile_sha256"],
        "authority": dict(AUTHORITY), "l1_cache_dir": config["l1_cache_dir"],
        "network_used": False, "runtime_mutated": False,
    }


def require_run_authorization(config: Mapping[str, object], ack: str | None) -> None:
    if ack != "ATT1_PUBLIC_LIFECYCLE":
        raise RunnerViolation("run requires exact acknowledgement")
    if config.get("enabled") is not True:
        raise RunnerViolation("run disabled by config")


def write_heartbeat(path: Path, summary: Mapping[str, object]) -> None:
    """Atomically publish an explicitly limited public-observation heartbeat."""

    if not isinstance(summary, Mapping):
        raise RunnerViolation("heartbeat summary")
    target = Path(path)
    if target.parent.is_symlink() or not target.parent.is_dir():
        raise RunnerViolation("heartbeat parent")
    value = dict(summary)
    value.update({
        "schema_id": "att1_lifecycle_public_heartbeat_v1", "authority": dict(AUTHORITY),
        "continuous_market_path_verified": False, "execution_parity": False,
        "actual_account_costs_verified": False, "promotion_pass": False,
        "execution_evidence": "PUBLIC_SNAPSHOT_IOC_SIMULATION_NOT_BROKER_FILLS",
        "limitations": [
            "REST snapshots do not prove continuous market path or actual fills",
            "declared scenario fees and MARK_1M_PROXY do not prove account net edge",
        ],
    })
    data = _canonical(value) + b"\n"
    descriptor, temporary = tempfile.mkstemp(prefix=".heartbeat-", dir=str(target.parent))
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        os.chmod(target, 0o600)
        parent = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    except OSError as exc:
        raise RunnerViolation("heartbeat write") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _runtime_sessions(runtime_dir: Path) -> list[Path]:
    directory = runtime_dir / "sessions"
    if not directory.exists():
        return []
    if directory.is_symlink() or not directory.is_dir():
        raise RunnerViolation("runtime sessions directory")
    paths = sorted(directory.glob("*.jsonl"))
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise RunnerViolation("runtime session path")
    return paths


def _hash(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _read_json_file(path, cap=5_000_000):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>cap:
            raise RunnerViolation('invalid or oversized public file')
        with os.fdopen(fd,'rb',closefd=False) as f:raw=f.read(cap+1)
        if len(raw)>cap:raise RunnerViolation('public file cap')
        return json.loads(raw,object_pairs_hook=_no_duplicates,parse_constant=_reject_nonfinite)
    finally:os.close(fd)


def _save_json_once(path,value):
    raw=_canonical(value)+b'\n'
    if path.exists():
        if path.is_symlink() or path.read_bytes()!=raw:raise RunnerViolation('immutable public evidence conflict')
        return
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb',closefd=False) as f:f.write(raw);f.flush();os.fsync(fd)
    finally:os.close(fd)
    parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(parent)
    finally:os.close(parent)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise RunnerViolation('public redirect rejected')


def network_transport(endpoint,params,*,timeout_seconds,headers):
    if headers or not endpoint.startswith(PUBLIC_BASE_URL+'/v5/market/'):
        raise RunnerViolation('public transport authority')
    validate_public_request(endpoint[len(PUBLIC_BASE_URL):],params)
    request=Request(endpoint+'?'+urlencode(params),method='GET',headers={'User-Agent':'att1-public-lifecycle/1'})
    with build_opener(ProxyHandler({}),_NoRedirect()).open(request,timeout=timeout_seconds) as response:
        if response.status!=200:raise RunnerViolation('public HTTP status')
        raw=response.read(5_000_001)
    if len(raw)>5_000_000:raise RunnerViolation('public response cap')
    return raw


class PublicLifecycleRuntime:
    """One public observation loop; durable session journals are the only book truth."""
    def __init__(self,config,*,clock_ms=None,transport=None,sleep_fn=None):
        self.config=config
        self.clock=clock_ms or (lambda:time.time_ns()//1_000_000)
        self.sleep=sleep_fn or time.sleep
        self.transport=transport or network_transport
        self.profile=build_profile(ROOT)
        if config['profile_sha256']!=self.profile['profile_sha256']:raise RunnerViolation('profile hash mismatch')
        self.root=Path(config['runtime_dir'])
        for path in [self.root,self.root/'sessions',self.root/'sources',self.root/'cache']:
            # Reject symlink ancestry before and after creating only the configured runtime.
            for parent in [path,*path.parents]:
                if parent.is_symlink():raise RunnerViolation('runtime symlink')
            path.mkdir(parents=True,exist_ok=True,mode=0o700)
        identity={'schema_id':'att1_lifecycle_runtime_epoch_v1','config':config,
                  'implementation_sha256':implementation_hash(),
                  'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'inputs_sha256':hashlib.sha256((ROOT/'research_lab/att1_lifecycle_public_inputs.py').read_bytes()).hexdigest()}
        epoch=self.root/'epoch.json'
        if not epoch.exists() and _runtime_sessions(self.root):raise RunnerViolation('missing epoch for existing journals')
        _save_json_once(epoch,identity)
        self.cache=CanonicalH1Cache(self.root/'cache',max_bars=2880)
        self.scan_journal=LifecycleJournal(self.root/'scan_journal.jsonl')
        self.sessions={}
        for path in _runtime_sessions(self.root):
            session=LifecycleSession(path,self.profile)
            decision=session.receipt['plan']['decision_id']
            if path.name!=decision+'.jsonl' or decision in self.sessions:raise RunnerViolation('session path identity')
            self.sessions[decision]=session
        self.start_ms=self.clock();self.start_state=self.state()
        self.last_observed={};self.last_funding={};self.scanned=set();self.scan_close=None
        self.poll_errors={};self.scan_results={};self.get_count=0;self.running=True

    def state(self):
        return verify_state([s.journal.path for s in self.sessions.values()],self.profile)

    def _get(self,path,symbol,**params):
        params={'category':'linear','symbol':symbol,**params}
        value=request_public(self.transport,path,params,symbol=symbol,max_response_bytes=self.config['max_response_bytes'])
        self.get_count+=1
        return value,self.clock()

    def _save_source(self,value):
        sha=_hash(value);_save_json_once(self.root/'sources'/(sha+'.json'),value);return sha

    def _records(self,session):return list(session.journal.read()[1:])

    def _event(self,session,kind,*,exchange_ms=None,received_ms=None,source=None,**payload):
        records=self._records(session)
        rx=self.clock() if received_ms is None else received_ms
        last_ex=max([session.receipt['plan']['submit_ms']]+[e['exchange_ms'] for e in records if e['kind'] not in {'FUNDING','FUNDING_COVERAGE','CLOCK','RECOVERY_GAP'}])
        ex=last_ex if exchange_ms is None else exchange_ms
        event={'schema_id':'att1_lifecycle_event_v1','kind':kind,'exchange_ms':ex,'received_ms':rx,
               'source_sha256':source or _hash({'simulation':kind,'epoch':self.config['epoch_id'],'rx':rx}),**payload}
        event['event_id']=kind.lower()+':'+_hash({'decision':session.receipt['plan']['decision_id'],'sequence':len(records)+1,'event':event})
        return event

    def _emit(self,session,kind,**kwargs):return session.apply(self._event(session,kind,**kwargs))

    def _active(self,receipt):
        return not (receipt['terminal_nonfill'] or receipt['lifecycle_terminal'])

    def _observation_required(self):
        return any(Fraction(session.receipt['held_qty'])>0 or
                   Fraction(session.receipt['pending_entry_qty'])>0 or
                   session.receipt['pending_exit'] is not None
                   for session in self.sessions.values())

    def _mark_observation_gap(self,session,observed_ms):
        decision=session.receipt['plan']['decision_id'];last=self.last_observed.get(decision)
        if last is not None and observed_ms-last>2000 and 'RECOVERY_GAP' not in session.receipt['incidents']:
            self._emit(session,'RECOVERY_GAP',exchange_ms=observed_ms,received_ms=observed_ms,reason='public polling continuity gap')

    def book_state(self,symbol):
        related=[s for s in self.sessions.values() if s.receipt['plan']['symbol']==symbol]
        active=[s for s in related if self._active(s.receipt)]
        if len(active)>1:raise RunnerViolation('multiple active symbol books')
        terminals=[e['received_ms'] for s in related if not self._active(s.receipt)
                   for e in self._records(s) if e['kind'] in {'ENTRY_FINAL','EXIT_FINAL'}]
        return {'active_decision_id':active[0].receipt['plan']['decision_id'] if active else None,
                'last_admitted_bar_ms':max([s.receipt['plan']['bar_close_ms'] for s in related],default=None),
                'last_terminal_ms':max(terminals,default=None)}

    def admit_candidate(self,signal,instrument):
        intent={'signal':signal,'instrument':instrument,'book_state':self.book_state(signal['symbol']),
                'book':self.config['epoch_id']+':'+signal['symbol'],'submit_ms':self.clock()}
        admitted=admit_signal(self.profile,signal,instrument,intent['book_state'],book=intent['book'],submit_ms=intent['submit_ms'])
        if not admitted['accepted']:
            self.scan_results[signal['symbol']]=admitted['code'];return None
        decision=admitted['plan']['decision_id']
        session=LifecycleSession(self.root/'sessions'/(decision+'.jsonl'),self.profile,intent=intent)
        self.sessions[decision]=session
        self._emit(session,'ENTRY_ACK',exchange_ms=intent['submit_ms'],received_ms=intent['submit_ms'])
        self.execute_ioc(session,entry=True)
        return session

    def _book(self,symbol):
        raw,rx=self._get('/v5/market/orderbook',symbol,limit=50)
        result=raw['result']
        snapshot={k:result[k] for k in ('ts','cts','u','seq','b','a')}
        _snapshot_levels(snapshot,'bid');_snapshot_levels(snapshot,'ask')
        if Fraction(snapshot['b'][0][0])>Fraction(snapshot['a'][0][0]):raise RunnerViolation('crossed book')
        if snapshot['cts']>rx or rx-snapshot['cts']>2000:raise RunnerViolation('future/stale public book')
        return snapshot,rx,raw

    def execute_ioc(self,session,*,entry=False):
        receipt=session.receipt;p=receipt['plan'];pending=receipt['pending_exit']
        if not entry and pending is None:return
        order=p['order_id'] if entry else pending['exit_order_id']
        submit=p['submit_ms'] if entry else pending['submit_ms']
        requested=p['requested_qty'] if entry else _fraction_text(Fraction(pending['remaining_qty']))
        if not entry and not pending['acknowledged']:
            self._emit(session,'EXIT_ACK',exit_order_id=order,exchange_ms=submit)
        snapshot,rx,raw=self._book(p['symbol'])
        source=self._save_source({'public_response':raw,'received_ms':rx,
                                  'scenario_taker_fee_rate':'0.001','max_book_participation':'0.05'})
        fills=simulate_ioc_fills(snapshot,decision_id=p['decision_id'],order_id=order,
            kind='ENTRY_FILL' if entry else 'EXIT_FILL',requested_qty=requested,qty_step=p['qty_step'],
            submit_ms=submit,received_ms=rx,source_sha256=source)
        if entry and snapshot['cts']>submit+2000:fills=[]
        for event in fills:
            if not entry:event['exit_order_id']=order
            session.apply(event)
            if entry and Fraction(session.receipt['intents']['protect_qty'])>0:
                self._emit(session,'PROTECTION_ACK',qty=_fraction_text(Fraction(session.receipt['held_qty'])),
                           stop=p['original_stop'],exchange_ms=snapshot['cts'],received_ms=rx,source=source)
        remaining=Fraction(session.receipt['pending_entry_qty']) if entry else Fraction(session.receipt['pending_exit']['remaining_qty'])
        status='FILLED' if remaining==0 else 'CANCELLED'
        final_args={} if entry else {'exit_order_id':order}
        self._emit(session,'ENTRY_FINAL' if entry else 'EXIT_FINAL',status=status,source=source,**final_args)
        self.last_observed[p['decision_id']]=rx

    def mark_restart_gaps(self):
        for session in self.sessions.values():
            records=self._records(session);last_rx=max([session.receipt['plan']['submit_ms']]+[e['received_ms'] for e in records])
            if Fraction(session.receipt['held_qty'])>0 and self.clock()-last_rx>2000 and 'RECOVERY_GAP' not in session.receipt['incidents']:
                self._emit(session,'RECOVERY_GAP',exchange_ms=self.clock(),reason='restart lost public observation continuity')
            if session.receipt['entry_status'] not in {'FILLED','CANCELLED','REJECTED','EXPIRED'}:
                # A simulated IOC cannot remain outstanding across process recovery.
                self._emit(session,'ENTRY_FINAL',status='CANCELLED')

    def manage(self,session):
        receipt=session.receipt;p=receipt['plan'];decision=p['decision_id']
        if Fraction(receipt['held_qty'])<=0 and receipt['pending_exit'] is None:
            return
        self._mark_observation_gap(session,self.clock())
        if session.receipt['intents']['protect_qty']!='0':
            self._emit(session,'PROTECTION_ACK',qty=_fraction_text(Fraction(session.receipt['held_qty'])),stop=p['original_stop'])
        if session.receipt['pending_exit'] is not None:
            # Cancel outstanding partially filled synthetic orders before replacing them.
            if session.receipt['intents']['cancel_exit']:
                self._emit(session,'EXIT_FINAL',exit_order_id=session.receipt['pending_exit']['exit_order_id'],status='CANCELLED')
            else:
                self.execute_ioc(session);return
        snapshot,rx,raw=self._book(p['symbol'])
        self._mark_observation_gap(session,rx)
        self.last_observed[decision]=rx
        source=_hash({'public_response':raw,'received_ms':rx})
        event=self._event(session,'PRICE',exchange_ms=snapshot['cts'],received_ms=rx,source=source,
                          bid=snapshot['b'][0][0],ask=snapshot['a'][0][0])
        records=self._records(session)
        preview=replay_lifecycle(self.profile,session.journal.read()[0]['intent'],records+[event])
        relevant=('pending_exit','incidents','intents')
        if any(preview[key]!=session.receipt[key] for key in relevant):
            self._save_source({'public_response':raw,'received_ms':rx});session.apply(event)
        if session.receipt['pending_exit'] is not None:self.execute_ioc(session)

    def reconcile_funding(self,session):
        receipt=session.receipt;first=receipt['first_fill_ms']
        if first is None or receipt['lifecycle_terminal']:return
        records=self._records(session);fills=[e for e in records if e['kind'] in {'ENTRY_FILL','EXIT_FILL'}]
        now=self.clock();flat=Fraction(receipt['held_qty'])==0
        last_exit=max([e['exchange_ms'] for e in fills if e['kind']=='EXIT_FILL'],default=first)
        # A short publication buffer is an evidence delay, never a strategy rule.
        end=last_exit+5000 if flat else now-60000
        if end<first or now<end+60000:return
        prior=[e for e in records if e['kind']=='FUNDING_COVERAGE']
        if prior and prior[-1]['complete'] is True and end<=prior[-1]['end_ms']:return
        if now-self.last_funding.get(receipt['plan']['decision_id'],0)<60000:return
        symbol=receipt['plan']['symbol'];start=max(0,first-5000);upper=end;rows={};pages=[]
        for page in range(16):
            raw,rx=self._get('/v5/market/funding/history',symbol,startTime=start,endTime=upper,limit=200)
            pages.append(self._save_source({'endpoint':'funding/history','params':{'start':start,'end':upper},'response':raw,'received_ms':rx}))
            batch=raw['result']['list']
            if not isinstance(batch,list) or len(batch)>200:raise RunnerViolation('funding page bound')
            times=[]
            for row in batch:
                when=int(row['fundingRateTimestamp'])
                if row['symbol']!=symbol or not start<=when<=upper:raise RunnerViolation('funding page window/symbol')
                _decimal(row['fundingRate'],'funding rate');times.append(when)
                if when in rows and rows[when]!=row:raise RunnerViolation('funding revision')
                rows[when]=row
            if len(batch)<200:break
            earliest=min(times)
            if earliest<=start:break
            if earliest>=upper:raise RunnerViolation('funding pagination stalled')
            upper=earliest-1
        else:raise RunnerViolation('funding pagination incomplete')
        existing={e['settlement_ms'] for e in records if e['kind']=='FUNDING'}
        for when,row in sorted(rows.items()):
            if when in existing:continue
            if when%60000:raise RunnerViolation('funding timestamp not at minute for mark proxy')
            mark_raw,rx=self._get('/v5/market/mark-price-kline',symbol,interval='1',start=when,end=when+59999,limit=1)
            marks=mark_raw['result']['list']
            if len(marks)!=1 or int(marks[0][0])!=when:raise RunnerViolation('settlement mark proxy absent')
            mark=marks[0][1];_decimal(mark,'mark price',positive=True)
            qty=sum((Fraction(e['qty'])*(1 if e['kind']=='ENTRY_FILL' else -1) for e in fills if e['exchange_ms']<=when),Fraction(0))
            provenance={'funding':row,'mark_1m_open':marks[0],'mark_evidence':'MARK_1M_PROXY'}
            source=self._save_source(provenance)
            self._emit(session,'FUNDING',exchange_ms=when,received_ms=rx,source=source,
                settlement_id=symbol+':'+str(when),settlement_ms=when,qty_at_settlement=_fraction_text(qty),mark_price=mark,rate=row['fundingRate'])
        source=self._save_source({'funding_pages_sha256':pages,'window':[start,end],'complete':True})
        self._emit(session,'FUNDING_COVERAGE',source=source,start_ms=start,end_ms=end,settlement_ms=sorted(rows),complete=True)
        self.last_funding[receipt['plan']['decision_id']]=self.clock()

    def scan_symbol(self,symbol):
        rows,_=self.cache.load(symbol)
        if not rows:
            cached=_read_json_file(Path(self.config['l1_cache_dir'])/(symbol+'.json'))
            if cached.get('schema')!='public_h1_cache_v1' or cached.get('symbol')!=symbol:
                raise RunnerViolation('L1 cache schema')
            rows=validate_closed_h1_rows(cached.get('rows',[]),self.clock(),min_bars=2160)
            rows_sha=hashlib.sha256(json.dumps(rows,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')).hexdigest()
            if cached.get('rows_hash')!=rows_sha or cached.get('row_count')!=len(rows):raise RunnerViolation('L1 cache hash')
            self.cache.merge(symbol,rows,self.clock())
        raw,available=self._get('/v5/market/kline',symbol,interval='60',limit=1000)
        incoming=validate_closed_h1_rows(raw['result']['list'],available,min_bars=0)
        self.cache.merge(symbol,incoming,available)
        rows,meta=self.cache.load(symbol)
        if not rows or available-meta.latest_close_ms>300000:
            return {'result':'STALE_CLOSED_BAR','latest_close_ms':meta.latest_close_ms}
        signal=signal_from_rows(symbol,rows,self.profile,source_available_ms=available,clock_ms=self.clock)
        if signal is None:return {'result':'NO_SIGNAL','data_sha256':meta.rows_hash,'latest_close_ms':meta.latest_close_ms}
        self._save_source({'signal':signal,'closed_h1_rows':list(rows)})
        raw_instrument,observed=self._get('/v5/market/instruments-info',symbol)
        items=raw_instrument['result']['list']
        if len(items)!=1:raise RunnerViolation('instrument cardinality')
        item=items[0]
        if any(item.get(k)!=v for k,v in {'symbol':symbol,'status':'Trading','contractType':'LinearPerpetual','quoteCoin':'USDT','settleCoin':'USDT'}.items()):
            raise RunnerViolation('instrument unavailable/type')
        source=self._save_source({'instrument_response':raw_instrument,'received_ms':observed})
        lot=item['lotSizeFilter']
        instrument={'symbol':symbol,'tick_size':item['priceFilter']['tickSize'],'qty_step':lot['qtyStep'],
                    'min_order_qty':lot['minOrderQty'],'min_notional':lot['minNotionalValue'],
                    'max_market_qty':lot['maxMktOrderQty'],'observed_ms':observed,'source_sha256':source}
        session=self.admit_candidate(signal,instrument)
        return {'result':'ADMITTED' if session else self.scan_results[symbol],
                'decision_id':session.receipt['plan']['decision_id'] if session else None,
                'signal_source_sha256':signal['source_sha256'],'data_sha256':signal['data_sha256']}

    def tick(self):
        if shutil.disk_usage(self.root).free<self.config['min_free_bytes']:raise RunnerViolation('runtime free space guard')
        for session in list(self.sessions.values()):
            decision=session.receipt['plan']['decision_id']
            try:
                self.manage(session)
                self.poll_errors.pop(decision,None)
            except (URLError,TimeoutError,ConnectionError) as exc:
                self.poll_errors[decision]=type(exc).__name__
        if not self._observation_required():
            for session in list(self.sessions.values()):
                decision=session.receipt['plan']['decision_id']
                try:
                    self.reconcile_funding(session)
                    self.poll_errors.pop(decision,None)
                except (URLError,TimeoutError,ConnectionError) as exc:
                    self.poll_errors[decision]=type(exc).__name__
        now=self.clock();close=now//H1_MS*H1_MS
        if self.scan_close!=close:
            self.scan_close=close;self.scanned=set();self.scan_results={}
            for event in self.scan_journal.read():
                if event.get('bar_close_ms')==close:self.scanned.add(event['symbol']);self.scan_results[event['symbol']]=event['result']
        if not self._observation_required() and 20000<=now-close<=300000:
            symbol=next((s for s in FIXED51_UNIVERSE if s not in self.scanned),None)
            if symbol:
                try:result=self.scan_symbol(symbol)
                except (RunnerViolation,PublicCacheViolation,ProfileViolation,URLError,TimeoutError) as exc:
                    result={'result':'SCAN_REJECTED','error':type(exc).__name__+':'+str(exc)[:180]}
                row={'schema_id':'att1_lifecycle_event_v1','event_id':'scan:'+self.config['epoch_id']+':'+symbol+':'+str(close),
                     'kind':'SCAN','symbol':symbol,'bar_close_ms':close,'received_ms':self.clock(),**result}
                self.scan_journal.append(row);self.scanned.add(symbol);self.scan_results[symbol]=result['result']
        self.publish()

    def publish(self,status='RUNNING'):
        state=self.state()
        write_heartbeat(self.root/'heartbeat.json',{
            'status':status,'pid':os.getpid(),'start_ms':self.start_ms,'as_of_ms':self.clock(),
            'epoch_id':self.config['epoch_id'],'profile_sha256':self.profile['profile_sha256'],
            'state_sha256':state['state_sha256'],'startup_state_sha256':self.start_state['state_sha256'],
            'sessions':state['sessions'],'session_count':len(self.sessions),
            'open_positions':sum(Fraction(s.receipt['held_qty'])>0 for s in self.sessions.values()),
            'public_get_count':self.get_count,'broker_calls':0,'order_calls':0,
            'scan_bar_close_ms':self.scan_close,'scanned_symbols':len(self.scanned),
            'scan_results':self.scan_results,'poll_errors':self.poll_errors,
            'last_public_observed_ms':self.last_observed,
            'valuation_note':'durable state updates on lifecycle transitions; ordinary quote marks are not journaled'})

    def run(self,*,once=False):
        lock=os.open(self.root/'process.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc:raise RunnerViolation('another public lifecycle process is running') from exc
            self.mark_restart_gaps()
            self.publish()
            if not once:
                def stop(_signum,_frame):self.running=False
                signal_module.signal(signal_module.SIGTERM,stop);signal_module.signal(signal_module.SIGINT,stop)
            while self.running:
                self.tick()
                if once:break
                self.sleep(self.config['poll_seconds'])
            self.publish('STOPPED' if not once else 'ONCE_COMPLETE')
        finally:os.close(lock)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ATT1 public-only lifecycle simulation")
    parser.add_argument("--config", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--verify-state", action="store_true")
    parser.add_argument("--ack")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    profile = build_profile(ROOT)
    if config["profile_sha256"] != profile["profile_sha256"]:
        raise RunnerViolation("profile hash mismatch")
    if args.preflight:
        print(_canonical(preflight(args.config, root=ROOT)).decode("ascii"))
        return 0
    runtime = Path(config["runtime_dir"])
    if args.verify_state:
        paths = _runtime_sessions(runtime)
        if not paths:
            raise RunnerViolation("no session journals to verify")
        print(_canonical(verify_state(paths, profile)).decode("ascii"))
        return 0
    require_run_authorization(config, args.ack)
    PublicLifecycleRuntime(config).run(once=args.once)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunnerViolation as exc:
        print(f"ATT1 public lifecycle failed closed: {exc}", file=sys.stderr)
        raise SystemExit(2)
