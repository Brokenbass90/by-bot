#!/usr/bin/env python3
"""KITY M3 public-data evidence façade; it has no order or credential path."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib
import importlib.util
import json
import os
import re
import secrets
import stat
import sys
import time
from datetime import date
from pathlib import Path, PurePath
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


REPO_ROOT = Path(__file__).resolve().parents[1]
BODY_MAX_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 10
_HEX64 = re.compile(r"[0-9a-f]{64}")
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_SYMBOL = re.compile(r"[A-Z0-9_\u3400-\u4dbf\u4e00-\u9fff]{2,44}")
_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
PINNED_RESEARCH_REF = "d6ed8126c041969de0bc6191e39fefe4a1272d5b"
PURE_CORE_PATH = REPO_ROOT / "bot" / "kity_m3_orders_off.py"


class PublicIOError(ValueError):
    """The supplied public evidence is unsafe, incomplete, or malformed."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        raise PublicIOError("redirects are not allowed")


_ALLOWED: dict[str, dict[str, tuple[str, set[str]]]] = {
    "binance": {
        "/fapi/v1/exchangeInfo": ("https://fapi.binance.com", set()),
        "/futures/data/openInterestHist": ("https://fapi.binance.com", {"symbol", "period", "limit", "startTime", "endTime"}),
        "/fapi/v1/klines": ("https://fapi.binance.com", {"symbol", "interval", "limit", "startTime", "endTime"}),
        "/fapi/v1/depth": ("https://fapi.binance.com", {"symbol", "limit"}),
        "/fapi/v1/fundingInfo": ("https://fapi.binance.com", set()),
        "/fapi/v1/fundingRate": ("https://fapi.binance.com", {"symbol", "startTime", "endTime", "limit"}),
        "/fapi/v1/time": ("https://fapi.binance.com", set()),
    },
    "bybit": {
        "/v5/market/instruments-info": ("https://api.bybit.com", {"category", "symbol", "limit", "cursor"}),
        "/v5/market/orderbook": ("https://api.bybit.com", {"category", "symbol", "limit"}),
        "/v5/market/tickers": ("https://api.bybit.com", {"category", "symbol", "baseCoin", "expDate"}),
        "/v5/market/funding/history": ("https://api.bybit.com", {"category", "symbol", "limit", "startTime", "endTime"}),
        "/v5/market/time": ("https://api.bybit.com", set()),
    },
}


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PublicIOError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json_loads(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicates, parse_constant=lambda value: (_ for _ in ()).throw(PublicIOError(f"non-finite JSON value: {value}")))
    except PublicIOError:
        raise
    except (TypeError, json.JSONDecodeError) as exc:
        raise PublicIOError("invalid JSON") from exc


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise PublicIOError("non-canonical JSON value") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _validate_params(venue: str, endpoint: str, params: Any) -> tuple[str, str, dict[str, Any]]:
    if not isinstance(venue, str):
        raise PublicIOError("venue/endpoint is not allowlisted")
    venue_key = venue.lower()
    if venue_key not in _ALLOWED or endpoint not in _ALLOWED[venue_key]:
        raise PublicIOError("venue/endpoint is not allowlisted")
    if not isinstance(params, dict):
        raise PublicIOError("params must be an object")
    base, allowed = _ALLOWED[venue_key][endpoint]
    if set(params) - allowed:
        raise PublicIOError("parameter is not allowlisted")
    clean: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, bool) or value is None:
            raise PublicIOError(f"parameter {key} has an invalid type")
        if key in {"limit", "startTime", "endTime"}:
            if not isinstance(value, int) or value < 0:
                raise PublicIOError(f"parameter {key} must be a non-negative integer")
            clean[key] = value
        elif key == "symbol":
            if not isinstance(value, str) or not _SYMBOL.fullmatch(value):
                raise PublicIOError("parameter symbol must be an uppercase contract symbol")
            clean[key] = value
        elif key == "category":
            if value != "linear":
                raise PublicIOError("parameter category must be linear")
            clean[key] = value
        elif key in {"period", "interval", "cursor", "baseCoin", "expDate"}:
            if not isinstance(value, str) or not value or len(value) > 128:
                raise PublicIOError(f"parameter {key} must be a bounded string")
            clean[key] = value
        else:  # pragma: no cover - guarded by the explicit allowlist above
            raise PublicIOError("parameter is not allowlisted")
    return venue_key, base, clean


def _open_public(request: Request, *, timeout: int):
    """The only network call, deliberately public GET with redirect refusal."""
    opener = build_opener(_NoRedirect())
    return opener.open(request, timeout=timeout)


def get_public(venue: str, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    """Capture one bounded allowlisted public JSON GET response verbatim."""
    venue_key, base, clean = _validate_params(venue, endpoint, params)
    query = urlencode(sorted(clean.items()), doseq=False)
    url = f"{base}{endpoint}" + (f"?{query}" if query else "")
    request = Request(url, method="GET", headers={"Accept": "application/json"})
    request_ms = time.time_ns() // 1_000_000
    try:
        with _open_public(request, timeout=TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            if final_url != url:
                raise PublicIOError("redirected public request rejected")
            raw_bytes = response.read(BODY_MAX_BYTES + 1)
    except PublicIOError:
        raise
    except HTTPError as exc:
        raise PublicIOError(f"public endpoint returned HTTP {exc.code}") from exc
    except OSError as exc:
        raise PublicIOError("public request failed") from exc
    receive_ms = time.time_ns() // 1_000_000
    if len(raw_bytes) > BODY_MAX_BYTES:
        raise PublicIOError("response body exceeds bound")
    try:
        raw = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise PublicIOError("response is not UTF-8") from exc
    _json_loads(raw)
    return {
        "venue": venue_key.upper(),
        "endpoint": endpoint,
        "params": clean,
        "request_ms": request_ms,
        "receive_ms": receive_ms,
        "raw": raw,
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
    }


def _blocked(*reasons: str, **extra: Any) -> dict[str, Any]:
    return {"status": "BLOCKED_DATA", "orders_allowed": False, "reasons": list(reasons), **extra}


def _reconstruct_signal(bundle: dict[str, Any], now_ms: int) -> dict[str, Any]:
    """Import the pure core only when a command actually needs it."""
    module = _core_module()
    result = module.reconstruct_signal(bundle, now_ms)
    if not isinstance(result, dict):
        raise PublicIOError("core reconstruction returned non-object")
    return result


def _core_module():
    """Load the isolated file, without package initialization or PYTHONPATH."""
    name = "_kity_m3_isolated_pure_core"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, PURE_CORE_PATH)
        if spec is None or spec.loader is None:
            raise PublicIOError("pure core unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[name] = module
    return sys.modules[name]


def _safe_forward_dir(forward_dir: Path | str) -> Path:
    raw = Path(forward_dir)
    if raw.is_symlink():
        raise PublicIOError("forward directory must not be a symlink")
    try:
        resolved = raw.resolve(strict=True)
    except OSError as exc:
        raise PublicIOError("forward directory is unavailable") from exc
    if not resolved.is_dir():
        raise PublicIOError("forward directory is not a directory")
    return resolved


def _safe_file_name(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise PublicIOError("FORWARD_MANIFEST_PATH_INVALID")
    candidate = PurePath(value)
    if candidate.name != value or value in {".", ".."} or "\\" in value:
        raise PublicIOError("FORWARD_MANIFEST_PATH_INVALID")
    return value


def _read_regular(path: Path) -> bytes:
    if path.is_symlink():
        raise PublicIOError("FORWARD_MANIFEST_SYMLINK")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise PublicIOError("FORWARD_FILE_UNAVAILABLE") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise PublicIOError("FORWARD_FILE_NOT_REGULAR")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, 1_048_576)
            if not chunk:
                break
            total += len(chunk)
            if total > BODY_MAX_BYTES:
                raise PublicIOError("FORWARD_FILE_TOO_LARGE")
            chunks.append(chunk)
        after = os.fstat(fd)
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise PublicIOError("FORWARD_FILE_CHANGED")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _basket_symbols(value: Any) -> list[tuple[str, str]]:
    """Normalize either an explicit basket or the core frozen long/short shape."""
    if isinstance(value, dict):
        if isinstance(value.get("frozen_signal"), dict):
            value = value["frozen_signal"]
        if isinstance(value, dict) and isinstance(value.get("basket"), list):
            value = value["basket"]
        if isinstance(value, dict) and isinstance(value.get("long"), list) and isinstance(value.get("short"), list):
            result: list[tuple[str, str]] = []
            for side, legs in (("LONG", value["long"]), ("SHORT", value["short"])):
                for leg in legs:
                    if not isinstance(leg, dict):
                        return []
                    symbol = leg.get("symbol", leg.get("s"))
                    if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
                        return []
                    declared_side = leg.get("side", side)
                    if declared_side != side:
                        return []
                    result.append((symbol, side))
            return result
    if not isinstance(value, list):
        return []
    result: list[tuple[str, str]] = []
    for leg in value:
        if not isinstance(leg, dict) or not isinstance(leg.get("symbol"), str) or not isinstance(leg.get("side"), str):
            return []
        result.append((leg["symbol"], leg["side"]))
    return result


def _consistent_alias(value: dict[str, Any], names: tuple[str, ...], reason: str) -> Any:
    found = [value[name] for name in names if name in value]
    if not found:
        return None
    if any(item != found[0] for item in found[1:]):
        raise PublicIOError(reason)
    return found[0]


def _declared_forward_files(directory: Path, external: dict[str, Any]) -> dict[str, str]:
    """Accept the current syroe map or a future strict file manifest, never both ambiguously."""
    manifest_path = directory / "file_manifest.json"
    try:
        manifest_stat = manifest_path.lstat()
    except FileNotFoundError:
        manifest_stat = None
    if manifest_stat is not None:
        manifest = _json_loads(_read_regular(manifest_path).decode("utf-8", errors="strict"))
        if not isinstance(manifest, dict) or set(manifest) != {"files"} or not isinstance(manifest["files"], list):
            raise PublicIOError("FORWARD_MANIFEST_MALFORMED")
        declared: dict[str, str] = {}
        for item in manifest["files"]:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                raise PublicIOError("FORWARD_MANIFEST_MALFORMED")
            name = _safe_file_name(item["path"])
            if not isinstance(item["sha256"], str) or not _HEX64.fullmatch(item["sha256"]):
                raise PublicIOError("FORWARD_MANIFEST_HASH_INVALID")
            if name in declared:
                raise PublicIOError("FORWARD_MANIFEST_DUPLICATE")
            declared[name] = item["sha256"]
        if "signal.json" not in declared:
            raise PublicIOError("FORWARD_MANIFEST_SIGNAL_MISSING")
        for name, expected in declared.items():
            if hashlib.sha256(_read_regular(directory / name)).hexdigest() != expected:
                raise PublicIOError("FORWARD_MANIFEST_HASH_MISMATCH")
        return declared
    hashes = external.get("sha256")
    if not isinstance(hashes, dict) or not hashes:
        raise PublicIOError("FORWARD_SOURCE_HASHES_MISSING")
    syroe = directory / "syroe"
    if syroe.is_symlink() or not syroe.is_dir():
        raise PublicIOError("FORWARD_SOURCE_DIRECTORY_INVALID")
    declared = {}
    for name, expected in hashes.items():
        name = _safe_file_name(name)
        if not isinstance(expected, str) or not _HEX64.fullmatch(expected) or name in declared:
            raise PublicIOError("FORWARD_SOURCE_HASH_INVALID")
        if hashlib.sha256(_read_regular(syroe / name)).hexdigest() != expected:
            raise PublicIOError("FORWARD_SOURCE_HASH_MISMATCH")
        declared[name] = expected
    return declared


def compare_forward(bundle: dict[str, Any], forward_dir: Path | str, now_ms: int) -> dict[str, Any]:
    """Compare untrusted external derived files with an independent local rebuild."""
    reasons: list[str] = []
    try:
        local = _reconstruct_signal(bundle, now_ms)
    except Exception:
        local = _blocked("LOCAL_RECONSTRUCTION_FAILED")
        reasons.append("LOCAL_RECONSTRUCTION_FAILED")
    try:
        directory = _safe_forward_dir(forward_dir)
        signal_bytes = _read_regular(directory / "signal.json")
        external = _json_loads(signal_bytes.decode("utf-8", errors="strict"))
        if not isinstance(external, dict):
            raise PublicIOError("FORWARD_SIGNAL_MALFORMED")
        declared = _declared_forward_files(directory, external)
        external_day = _consistent_alias(external, ("d", "date", "day"), "FORWARD_DAY_ALIAS_CONFLICT")
        local_frozen = local.get("frozen_signal") if isinstance(local.get("frozen_signal"), dict) else local
        local_day = _consistent_alias(local_frozen, ("day", "date", "d"), "LOCAL_DAY_ALIAS_CONFLICT")
        local_ref = _consistent_alias(local_frozen, ("research_ref", "ref"), "LOCAL_REF_ALIAS_CONFLICT")
        if local_frozen is not local and local_day is None:
            local_day = _consistent_alias(local, ("day", "date", "d"), "LOCAL_DAY_ALIAS_CONFLICT")
        if local_frozen is not local and local_ref is None:
            local_ref = _consistent_alias(local, ("research_ref", "ref"), "LOCAL_REF_ALIAS_CONFLICT")
        if not isinstance(external_day, str) or external_day != local_day:
            reasons.append("FORWARD_DAY_MISMATCH")
        external_ref = _consistent_alias(external, ("research_ref", "ref"), "FORWARD_REF_ALIAS_CONFLICT")
        if not isinstance(external_ref, str):
            reasons.append("FORWARD_RESEARCH_REF_MISSING")
        elif external_ref != local_ref:
            reasons.append("FORWARD_RESEARCH_REF_MISMATCH")
        external_basket = _basket_symbols(external)
        local_basket = _basket_symbols(local)
        comparison = {
            "matches": bool(external_basket) and external_basket == local_basket,
            "external": external_basket,
            "local": local_basket,
        }
        if not local.get("signal_valid") or len(external_basket) != len(local_basket):
            reasons.append("FORWARD_BASKET_INCOMPLETE")
        if not comparison["matches"]:
            reasons.append("FORWARD_BASKET_MISMATCH")
        # Derived files cannot establish origin without their exact raw captures.
        if not isinstance(external.get("raw_captures"), list) or not external["raw_captures"]:
            reasons.append("RAW_WIRE_PROVENANCE_MISSING")
        elif any(
            not isinstance(item, dict)
            or not isinstance(item.get("raw"), str)
            or not isinstance(item.get("path"), str)
            or not _HEX64.fullmatch(str(item.get("sha256", "")))
            or _safe_file_name(item["path"]) not in declared
            or declared[_safe_file_name(item["path"])] != item["sha256"]
            or hashlib.sha256(item["raw"].encode("utf-8")).hexdigest() != item["sha256"]
            for item in external["raw_captures"]
        ):
            reasons.append("RAW_WIRE_PROVENANCE_INVALID")
        return _blocked(*dict.fromkeys(reasons or ["FORWARD_COMPARISON_BLOCKED"]), local_status=local.get("status"), external_signal_sha256=hashlib.sha256(signal_bytes).hexdigest(), basket_comparison=comparison)
    except (UnicodeDecodeError, PublicIOError, OSError) as exc:
        text = str(exc)
        if not text.startswith("FORWARD_"):
            text = "FORWARD_EVIDENCE_INVALID"
        return _blocked(*dict.fromkeys(reasons + [text]), local_status=local.get("status"), basket_comparison={"matches": False, "external": [], "local": _basket_symbols(local)})


def _validate_receipt(identity: str, receipt: Any) -> None:
    required = {'identity','day','research_ref','request_digest','status','orders_allowed','money_ready','signal'}
    if not isinstance(receipt,dict) or set(receipt)!=required:
        raise PublicIOError('receipt schema invalid: complete signal and source bundle required')
    if not isinstance(identity,str) or identity!='signal-'+str(receipt['day']) or receipt['identity']!=identity:
        raise PublicIOError('receipt identity must be the single pinned signal week')
    if receipt['research_ref']!=PINNED_RESEARCH_REF or receipt['status'] not in ('BLOCKED_DATA','BLOCKED_EXECUTION'):
        raise PublicIOError('receipt ref/status invalid')
    if receipt['orders_allowed'] is not False or receipt['money_ready'] is not False:
        raise PublicIOError('receipt must keep money authority false')
    signal=receipt['signal']
    if not isinstance(signal,dict) or not isinstance(signal.get('source_bundle'),dict) or type(signal.get('evaluated_ms')) is not int:
        raise PublicIOError('receipt source decision invalid')
    core=_core_module()
    reconstructed=core.reconstruct_signal(signal['source_bundle'],signal['evaluated_ms'])
    if signal!=reconstructed or signal.get('signal_valid') is not True:
        raise PublicIOError('receipt source decision invalid')
    if receipt['day']!=signal['frozen_signal']['day'] or receipt['status']!=signal['status']:
        raise PublicIOError('receipt week/status invalid')
    if receipt['request_digest']!=core.digest(signal['source_bundle']):
        raise PublicIOError('receipt request digest invalid')
    _canonical(receipt)


def _signal_seal(receipt: dict[str,Any], sealed_ms: int) -> dict[str,Any]:
    signal=receipt['signal']
    if type(sealed_ms) is not int or sealed_ms<max(signal['source_available_ms'],signal['evaluated_ms']):
        raise PublicIOError('receipt cannot seal evidence before actual availability/evaluation')
    core=_core_module()
    cutoff=signal['frozen_signal']['oi_cutoff_ms']
    boundary=cutoff+300000+core.DAY_MS
    prospective=signal['prospective_eligible'] is True and sealed_ms<boundary
    return {'schema_id':'kity_m3_signal_seal_v1','day':receipt['day'],'research_ref':PINNED_RESEARCH_REF,
            'signal_hash':signal['signal_hash'],'source_bundle_digest':receipt['request_digest'],
            'source_available_ms':signal['source_available_ms'],'evaluated_ms':signal['evaluated_ms'],
            'sealed_ms':sealed_ms,'entry_boundary_ms':boundary,'prospective_eligible':prospective,
            'orders_allowed':False,'money_ready':False,
            'reasons':[] if prospective else ['RETROSPECTIVE_OR_PRIOR_PERIOD_SEAL_NOT_PROSPECTIVE']}


def _safe_runtime(runtime: Path | str) -> Path:
    root = Path(REPO_ROOT)
    if root.is_symlink():
        raise PublicIOError("repository root symlink refused")
    root = root.resolve(strict=True)
    raw = Path(runtime)
    if raw.is_symlink():
        raise PublicIOError("runtime symlink refused")
    try:
        runtime_path = raw.resolve(strict=True)
    except OSError as exc:
        raise PublicIOError("runtime directory unavailable") from exc
    allowed = (root / ".private" / "kity_m3_orders_off", root / "runtime" / "kity_m3_orders_off")
    if runtime_path not in allowed or not runtime_path.is_dir():
        raise PublicIOError("runtime must be explicit KITY private/runtime root")
    # Refuse every symlink component between the canonical repository and runtime.
    relative = runtime_path.relative_to(root)
    cursor = root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise PublicIOError("runtime symlink refused")
    return runtime_path


def _open_dir(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(path, flags)
    except OSError as exc:
        raise PublicIOError("unsafe runtime directory") from exc


def _ensure_child_dir(parent_fd: int, name: str) -> int:
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    except OSError as exc:
        raise PublicIOError("cannot create receipt directory") from exc
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise PublicIOError("unsafe receipt directory") from exc


def _read_receipt(parent_fd: int, leaf: str) -> tuple[dict[str, Any], bytes]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(leaf, flags, dir_fd=parent_fd)
    except OSError as exc:
        if getattr(exc, "errno", None) == 2:
            raise FileNotFoundError from exc
        raise PublicIOError("existing receipt is unavailable or symlink") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise PublicIOError("existing receipt is not a regular file")
        raw = b""
        while True:
            piece = os.read(fd, 1_048_576)
            if not piece:
                break
            raw += piece
            if len(raw) > BODY_MAX_BYTES:
                raise PublicIOError("existing receipt too large")
    finally:
        os.close(fd)
    try:
        envelope = _json_loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, PublicIOError) as exc:
        raise PublicIOError("existing receipt invalid") from exc
    if not isinstance(envelope, dict) or set(envelope) != {"receipt", "receipt_sha256", "seal", "seal_sha256"} or not isinstance(envelope["receipt_sha256"], str):
        raise PublicIOError("existing receipt invalid")
    if _digest(envelope["receipt"]) != envelope["receipt_sha256"] or _digest(envelope["seal"]) != envelope["seal_sha256"]:
        raise PublicIOError("existing receipt invalid")
    return envelope, raw


def publish_receipt(runtime: Path | str, identity: str, receipt: dict[str, Any]) -> dict[str, Any]:
    """Publish a content-addressed, create-exclusive orders-OFF receipt."""
    _validate_receipt(identity, receipt)
    runtime_path = _safe_runtime(runtime)
    runtime_fd = _open_dir(runtime_path)
    receipts_fd = -1
    lock_fd = -1
    leaf = f"{identity}.json"
    try:
        receipts_fd = _ensure_child_dir(runtime_fd, "receipts")
        lock_flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            lock_fd = os.open(".publish.lock", lock_flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=receipts_fd)
        except FileExistsError:
            try:
                lock_fd = os.open(".publish.lock", lock_flags, dir_fd=receipts_fd)
            except OSError as exc:
                raise PublicIOError("unsafe receipt lock") from exc
        except OSError as exc:
            raise PublicIOError("unsafe receipt lock") from exc
        if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
            raise PublicIOError("unsafe receipt lock")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            existing, existing_raw = _read_receipt(receipts_fd, leaf)
        except FileNotFoundError:
            existing = None
            existing_raw = b''
        def reuse(envelope):
            _validate_receipt(identity,envelope['receipt'])
            if _canonical(envelope['receipt'])!=_canonical(receipt):
                raise PublicIOError('receipt conflict: immutable week already has different content')
            oldseal=envelope['seal']
            if not isinstance(oldseal,dict) or _signal_seal(receipt,oldseal.get('sealed_ms'))!=oldseal:
                raise PublicIOError('existing receipt seal invalid')
            return {'status':receipt['status'],'orders_allowed':False,'money_ready':False,'reused':True,
                    'path':str(runtime_path/'receipts'/leaf),'receipt_sha256':envelope['receipt_sha256'],
                    'seal':oldseal,'seal_sha256':envelope['seal_sha256']}
        if existing is not None:
            return reuse(existing)
        seal=_signal_seal(receipt,time.time_ns()//1_000_000)
        candidate={'receipt':receipt,'receipt_sha256':_digest(receipt),'seal':seal,'seal_sha256':_digest(seal)}
        payload=_canonical(candidate)+b'\n'
        if len(payload)>BODY_MAX_BYTES:
            raise PublicIOError('receipt body exceeds bound')
        temp = f".{leaf}.tmp.{os.getpid()}.{secrets.token_hex(8)}"
        temp_fd = -1
        try:
            temp_fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0), 0o600, dir_fd=receipts_fd)
            view = memoryview(payload)
            while view:
                written = os.write(temp_fd, view)
                view = view[written:]
            os.fsync(temp_fd)
            os.close(temp_fd)
            temp_fd = -1
            try:
                os.link(temp, leaf, src_dir_fd=receipts_fd, dst_dir_fd=receipts_fd, follow_symlinks=False)
            except FileExistsError:
                existing, existing_raw = _read_receipt(receipts_fd, leaf)
                return reuse(existing)
            os.fsync(receipts_fd)
        finally:
            if temp_fd >= 0:
                os.close(temp_fd)
            try:
                os.unlink(temp, dir_fd=receipts_fd)
            except FileNotFoundError:
                pass
        return {"status": receipt["status"], "orders_allowed": False, "reused": False, "path": str(runtime_path / "receipts" / leaf), "receipt_sha256": candidate["receipt_sha256"], "money_ready":False,"seal":seal,"seal_sha256":candidate["seal_sha256"]}
    finally:
        if lock_fd >= 0:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        if receipts_fd >= 0:
            os.close(receipts_fd)
        os.close(runtime_fd)


def _load_json_file(path: str) -> Any:
    return _json_loads(_read_regular(Path(path)).decode("utf-8", errors="strict"))


def _write_capture(path_text: str, capture: dict[str, Any]) -> None:
    path = Path(path_text)
    if path.name in {"", ".", ".."} or path.is_symlink() or path.parent.is_symlink():
        raise PublicIOError("capture output must be a safe non-symlink file")
    runtime = _safe_runtime(path.parent)
    if path.parent.resolve(strict=True) != runtime or path.name != path_text.split(os.sep)[-1]:
        raise PublicIOError("capture output must be directly inside KITY runtime")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    parent_fd = _open_dir(runtime)
    try:
        fd = os.open(path.name, flags, 0o600, dir_fd=parent_fd)
    except OSError as exc:
        raise PublicIOError("capture output must be a new non-symlink path") from exc
    finally:
        os.close(parent_fd)
    try:
        payload = _canonical(capture) + b"\n"
        view = memoryview(payload)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)


def _emit(value: dict[str, Any]) -> None:
    value = dict(value)
    value["orders_allowed"] = False
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    reconstruct = commands.add_parser("reconstruct")
    reconstruct.add_argument("--bundle", required=True)
    assess = commands.add_parser("assess")
    assess.add_argument("--signal", required=True)
    assess.add_argument("--execution", required=True)
    compare = commands.add_parser("compare-forward")
    compare.add_argument("--bundle", required=True)
    compare.add_argument("--forward-dir", required=True)
    capture = commands.add_parser("capture")
    capture.add_argument("--venue", required=True)
    capture.add_argument("--endpoint", required=True)
    capture.add_argument("--params", required=True)
    capture.add_argument("--output", required=True)
    publish = commands.add_parser("publish")
    publish.add_argument("--receipt", required=True)
    publish.add_argument("--runtime", required=True)
    publish.add_argument("--identity", required=True)
    args = parser.parse_args(argv)
    now_ms = time.time_ns() // 1_000_000
    try:
        if args.command == "reconstruct":
            result = _reconstruct_signal(_load_json_file(args.bundle), now_ms)
        elif args.command == "assess":
            core = _core_module()
            result = core.assess_execution(_load_json_file(args.signal), _load_json_file(args.execution), now_ms)
        elif args.command == "compare-forward":
            result = compare_forward(_load_json_file(args.bundle), args.forward_dir, now_ms)
        elif args.command == "capture":
            params = _json_loads(args.params)
            result = get_public(args.venue, args.endpoint, params)
            _write_capture(args.output, result)
        else:  # publish
            result = publish_receipt(args.runtime, args.identity, _load_json_file(args.receipt))
        if not isinstance(result, dict):
            raise PublicIOError("command returned non-object")
        _emit(result)
        return 0
    except (OSError, PublicIOError, ValueError, TypeError) as exc:
        _emit(_blocked("CLI_INPUT_INVALID", error=str(exc)))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
