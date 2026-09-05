"""Fail-closed public contract for the ATT1+ETS2S signal shadow.

This module is deliberately limited to configuration and provenance.  It has
no broker, order, or private API imports.  The eventual runner must call
``require_operator_ack`` before evaluating an enabled configuration.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from bot.sbr1_universe import FIXED51_UNIVERSE, FIXED51_UNIVERSE_SHA256


CONFIG_SCHEMA_ID = "att1_ets2s_signal_shadow_config_v1"
MANIFEST_SCHEMA_ID = "att1_ets2s_signal_shadow_manifest_v1"
DEPLOYMENT_ANCHOR_SCHEMA_ID = "att1_ets2s_signal_shadow_deployment_anchor_v1"
DEPLOYMENT_ANCHOR_PATH = "/etc/bybot-research/att1-ets2s-signal-shadow.anchor.json"
PRIVILEGED_LAUNCHER_SOURCE_PATH = "scripts/launch_att1_ets2s_shadow.py"
PRIVILEGED_LAUNCHER_INSTALL_PATH = "/usr/local/libexec/att1-ets2s-shadow-launcher"
AUTHORITY = "research_only_public_att1_ets2s_signal_shadow_no_orders_no_private_api_no_money_no_promotion"
ACK = "ATT1_ETS2S_SIGNAL_SHADOW"
PUBLIC_BASE_URL = "https://api.bybit.com"
PUBLIC_KLINE_ENDPOINT = "https://api.bybit.com/v5/market/kline"
STORE_CONTRACT_ID = "canonical_closed_utc_buckets_v1"
EXPECTED_UNAVAILABLE_SYMBOLS = ("HFTUSDT",)
TRUSTED_CONFIG_PATH = "configs/att1_ets2s_signal_shadow_v1.json"
TRUSTED_MANIFEST_PATH = "configs/research/att1_ets2s_signal_shadow_manifest_v1.json"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")

ATT1_SOURCE_PATHS = (
    "strategies/alt_trendline_touch_v1.py",
    "strategies/att1_live.py",
    "strategies/live_kline_utils.py",
    "strategies/signals.py",
    "research_lab/research_ohlcv_store.py",
    "research_lab/att1_ets2s_signal_shadow_parity.py",
)
ETS2S_SOURCE_PATHS = (
    "strategies/elder_triple_screen_v2.py",
    "strategies/elder_live.py",
    "strategies/live_kline_utils.py",
    "strategies/signals.py",
    "research_lab/research_ohlcv_store.py",
    "research_lab/att1_ets2s_signal_shadow_parity.py",
)
SOURCE_PATHS = frozenset(
    {
        *ATT1_SOURCE_PATHS,
        *ETS2S_SOURCE_PATHS,
        "bot/att1_ets2s_shadow_journal.py",
        "bot/att1_ets2s_signal_shadow_contract.py",
        "bot/public_h1_cache_store.py",
        "bot/sbr1_universe.py",
        TRUSTED_CONFIG_PATH,
        "scripts/launch_att1_ets2s_shadow.py",
        "scripts/run_att1_ets2s_signal_shadow.py",
        "scripts/prepare_att1_ets2s_shadow_release.py",
        "deploy/systemd/att1-ets2s-signal-shadow.service",
        "deploy/systemd/att1-ets2s-signal-shadow.timer",
    }
)
PROFILE_SOURCE_HASHES = {
    "ATT1": "a7b8d3f5d69ee3943aae8f4c9489fd1a5f5a84fe3ed89b08707231d647299f15",
    "ETS2S": "d682e034400f55e943ec1a43bfc093eee856624f1b7a1b59e0c5e5eb2ccf9c50",
}
PROFILE_CONFIG_HASHES = {
    "ATT1": "9d6f790d1d21b5597643a11d768d09b9234a1798b6db3f53490e0aad5af187b4",
    "ETS2S": "453378735642a9c27d9a5ffd94c8bd2d7ab77a28f9cc3f14dbf4334d7c8c0662",
}
PROFILE_FIXED51_CONFIG_HASHES = {
    "ATT1": "fbe3ad079bdf89a00786a5a9b3c27ffd8be27b7826ae3191d60dbb80ead47a9f",
    "ETS2S": "af1f846a73098a386d5bff84e589749372c760fc829ae49d95001e8b5f8a3cf5",
}


class ContractViolation(ValueError):
    """Stable fail-closed error for contract, authority, or provenance drift."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ContractViolation("noncanonical_shadow_payload") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha_field(value: object, field: str) -> str:
    text = str(value or "").strip()
    if _SHA256.fullmatch(text) is None:
        raise ContractViolation(f"invalid_sha256:{field}")
    return text


def _relative(value: object, field: str) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~") or "\x00" in text:
        raise ContractViolation(f"unsafe_path:{field}")
    parts = Path(text).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ContractViolation(f"unsafe_path:{field}")
    return text


def _open_nofollow(path: Path, *, directory: bool, violation: str) -> int:
    """Open every absolute path component relative to a pinned parent FD."""

    absolute = Path(os.path.abspath(os.fspath(path)))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    try:
        current_fd = os.open(absolute.anchor or "/", flags | directory_flag)
        for index, part in enumerate(absolute.parts[1:]):
            last = index == len(absolute.parts[1:]) - 1
            next_flags = flags | (directory_flag if not last or directory else 0)
            next_fd = os.open(part, next_flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        info = os.fstat(current_fd)
        expected = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        if not expected:
            os.close(current_fd)
            raise ContractViolation(violation)
        return current_fd
    except ContractViolation:
        raise
    except OSError as exc:
        try:
            os.close(current_fd)
        except (OSError, UnboundLocalError):
            pass
        raise ContractViolation(violation) from exc


def _read_regular_nofollow(path: Path, *, violation: str) -> bytes:
    fd = _open_nofollow(path, directory=False, violation=violation)
    try:
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    except OSError as exc:
        raise ContractViolation(violation) from exc
    finally:
        os.close(fd)


def _verify_trusted_root(root: Path) -> Path:
    absolute = Path(os.path.abspath(os.fspath(root)))
    fd = _open_nofollow(absolute, directory=True, violation="symlink_trusted_root")
    os.close(fd)
    return absolute


def _profile_source_hash(root: Path, paths: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for relative in paths:
        data = _read_regular_nofollow(root / relative, violation=f"symlink_source:{relative}")
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(data)
    return digest.hexdigest()


def _file_row(root: Path, relative: str) -> dict[str, object]:
    data = _read_regular_nofollow(root / relative, violation=f"symlink_source:{relative}")
    return {"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


@dataclass(frozen=True)
class SignalShadowContract:
    schema_id: str
    authority: str
    enabled: bool
    evidence_universe: tuple[str, ...]
    evidence_universe_sha256: str
    profiles: Mapping[str, Mapping[str, object]]
    store_contract_id: str
    public_base_url: str
    allowed_public_endpoints: tuple[str, ...]
    manifest_path: str
    operator_ack: str
    runtime_paths: Mapping[str, str]
    data_policy: Mapping[str, object]
    expected_unavailable_symbols: tuple[str, ...]
    source_paths: tuple[str, ...]
    source_closure_sha256: str

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "SignalShadowContract":
        if not isinstance(raw, Mapping):
            raise ContractViolation("config_not_object")
        required = {
            "schema_id", "enabled", "default_off", "authority", "money_authority", "orders_allowed",
            "private_api_allowed", "release_or_promotion_authority", "sealed_data_allowed",
            "public_base_url", "allowed_public_endpoints", "store_contract_id", "evidence_universe",
            "evidence_universe_sha256", "profiles", "manifest_path", "operator_ack", "runtime_paths",
            "data_policy", "expected_unavailable_symbols", "runner_placeholder_path", "systemd_service_path",
            "systemd_timer_path",
        }
        if set(raw) != required:
            raise ContractViolation("config_fields_mismatch")
        if raw.get("schema_id") != CONFIG_SCHEMA_ID:
            raise ContractViolation("wrong_config_schema")
        if raw.get("default_off") is not True:
            raise ContractViolation("config_not_default_off")
        if raw.get("authority") != AUTHORITY:
            raise ContractViolation("wrong_shadow_authority")
        if not isinstance(raw.get("enabled"), bool):
            raise ContractViolation("enabled_not_boolean")
        for field in ("money_authority", "orders_allowed", "private_api_allowed", "release_or_promotion_authority", "sealed_data_allowed"):
            if raw.get(field) is not False:
                raise ContractViolation(f"unsafe_authority:{field}")
        if raw.get("public_base_url") != PUBLIC_BASE_URL:
            raise ContractViolation("unapproved_public_base_url")
        endpoints = raw.get("allowed_public_endpoints")
        if endpoints != [PUBLIC_KLINE_ENDPOINT]:
            raise ContractViolation("unapproved_public_endpoints")
        if raw.get("store_contract_id") != STORE_CONTRACT_ID:
            raise ContractViolation("wrong_store_contract")

        universe = tuple(str(value or "").strip().upper() for value in raw.get("evidence_universe", []))
        if universe != FIXED51_UNIVERSE:
            raise ContractViolation("fixed51_universe_mismatch")
        if _sha(list(universe)) != _sha_field(raw.get("evidence_universe_sha256"), "evidence_universe_sha256"):
            raise ContractViolation("fixed51_universe_hash_mismatch")
        if raw.get("evidence_universe_sha256") != FIXED51_UNIVERSE_SHA256:
            raise ContractViolation("fixed51_universe_hash_mismatch")

        profiles = raw.get("profiles")
        if not isinstance(profiles, Mapping) or set(profiles) != {"ATT1", "ETS2S"}:
            raise ContractViolation("profiles_mismatch")
        normalized_profiles: dict[str, Mapping[str, object]] = {}
        for name in ("ATT1", "ETS2S"):
            item = profiles.get(name)
            if not isinstance(item, Mapping) or set(item) != {"config_hash", "fixed51_config_hash", "source_hash"}:
                raise ContractViolation(f"profile_fields_mismatch:{name}")
            if (item.get("config_hash") != PROFILE_CONFIG_HASHES[name]
                    or item.get("fixed51_config_hash") != PROFILE_FIXED51_CONFIG_HASHES[name]
                    or item.get("source_hash") != PROFILE_SOURCE_HASHES[name]):
                raise ContractViolation(f"profile_hash_mismatch:{name}")
            normalized_profiles[name] = dict(item)

        manifest_path = _relative(raw.get("manifest_path"), "manifest_path")
        if manifest_path != TRUSTED_MANIFEST_PATH:
            raise ContractViolation("untrusted_manifest_path")
        if raw.get("operator_ack") != ACK:
            raise ContractViolation("operator_ack_contract_mismatch")
        paths = raw.get("runtime_paths")
        if not isinstance(paths, Mapping) or set(paths) != {"cache", "journal", "heartbeat", "state"}:
            raise ContractViolation("runtime_paths_mismatch")
        normalized_paths = {key: _relative(paths[key], f"runtime_paths:{key}") for key in paths}
        data_policy = {
            "closed_timeframe": "60",
            "max_decision_age_ms": 300000,
            "max_forward_lag_ms": 300000,
            "min_bootstrap_h1_bars": 2160,
            "max_cache_h1_bars": 2880,
            "min_runtime_free_bytes": 536870912,
            "page_limit": 1000,
            "max_response_bytes": 5000000,
            "gap_free": True,
            "exclude_forming_bar": True,
            "public_only": True,
        }
        if raw.get("data_policy") != data_policy:
            raise ContractViolation("data_policy_mismatch")
        unavailable = tuple(str(item or "").upper() for item in raw.get("expected_unavailable_symbols", ()))
        if unavailable != EXPECTED_UNAVAILABLE_SYMBOLS:
            raise ContractViolation("expected_unavailable_symbols_mismatch")
        for field in ("runner_placeholder_path", "systemd_service_path", "systemd_timer_path"):
            _relative(raw.get(field), field)
        return cls(
            schema_id=CONFIG_SCHEMA_ID,
            authority=AUTHORITY,
            enabled=bool(raw["enabled"]),
            evidence_universe=universe,
            evidence_universe_sha256=FIXED51_UNIVERSE_SHA256,
            profiles=normalized_profiles,
            store_contract_id=STORE_CONTRACT_ID,
            public_base_url=PUBLIC_BASE_URL,
            allowed_public_endpoints=(PUBLIC_KLINE_ENDPOINT,),
            manifest_path=manifest_path,
            operator_ack=ACK,
            runtime_paths=normalized_paths,
            data_policy=data_policy,
            expected_unavailable_symbols=unavailable,
            source_paths=(),
            source_closure_sha256="",
        )


def _verify_manifest(
    root: Path,
    contract: SignalShadowContract,
    *,
    expected_manifest_sha256: str,
) -> tuple[tuple[str, ...], str]:
    manifest_path = root / contract.manifest_path
    try:
        manifest_bytes = _read_regular_nofollow(manifest_path, violation="symlink_source:manifest")
        if hashlib.sha256(manifest_bytes).hexdigest() != _sha_field(
            expected_manifest_sha256, "expected_manifest_sha256"
        ):
            raise ContractViolation("manifest_hash_mismatch")
        raw = json.loads(manifest_bytes.decode("utf-8"))
    except ContractViolation:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractViolation("manifest_unreadable") from exc
    required = {
        "schema_id", "authority", "default_off", "enabled", "money_authority", "orders_allowed",
        "private_api_allowed", "release_or_promotion_authority", "sealed_data_allowed", "public_base_url",
        "allowed_public_endpoints", "store_contract_id", "operator_ack", "evidence_universe",
        "evidence_universe_sha256", "profiles", "source_closure_sha256", "source_files",
    }
    if not isinstance(raw, Mapping) or set(raw) != required:
        raise ContractViolation("manifest_fields_mismatch")
    if not isinstance(raw, Mapping) or raw.get("schema_id") != MANIFEST_SCHEMA_ID:
        raise ContractViolation("wrong_manifest_schema")
    if raw.get("authority") != AUTHORITY or raw.get("default_off") is not True or raw.get("enabled") is not False:
        raise ContractViolation("manifest_claims_authority")
    for field in ("money_authority", "orders_allowed", "private_api_allowed", "release_or_promotion_authority", "sealed_data_allowed"):
        if raw.get(field) is not False:
            raise ContractViolation(f"unsafe_authority:{field}")
    if raw.get("public_base_url") != PUBLIC_BASE_URL or raw.get("allowed_public_endpoints") != [PUBLIC_KLINE_ENDPOINT]:
        raise ContractViolation("manifest_public_endpoint_mismatch")
    if raw.get("store_contract_id") != STORE_CONTRACT_ID:
        raise ContractViolation("manifest_store_contract_mismatch")
    if raw.get("evidence_universe") != list(FIXED51_UNIVERSE) or raw.get("evidence_universe_sha256") != FIXED51_UNIVERSE_SHA256:
        raise ContractViolation("fixed51_universe_hash_mismatch")
    if raw.get("operator_ack") != ACK:
        raise ContractViolation("operator_ack_contract_mismatch")
    profiles = raw.get("profiles")
    if not isinstance(profiles, Mapping) or set(profiles) != {"ATT1", "ETS2S"}:
        raise ContractViolation("manifest_profiles_mismatch")
    for name, paths in (("ATT1", ATT1_SOURCE_PATHS), ("ETS2S", ETS2S_SOURCE_PATHS)):
        item = profiles[name]
        if not isinstance(item, Mapping) or set(item) != {"config_hash", "fixed51_config_hash", "source_hash", "source_paths"}:
            raise ContractViolation(f"manifest_profile_fields_mismatch:{name}")
        if (item.get("config_hash") != PROFILE_CONFIG_HASHES[name]
                or item.get("fixed51_config_hash") != PROFILE_FIXED51_CONFIG_HASHES[name]
                or item.get("source_hash") != PROFILE_SOURCE_HASHES[name]):
            raise ContractViolation(f"profile_source_hash_mismatch:{name}")
        if tuple(item.get("source_paths", ())) != paths:
            raise ContractViolation(f"profile_source_paths_mismatch:{name}")
        if _profile_source_hash(root, paths) != PROFILE_SOURCE_HASHES[name]:
            raise ContractViolation(f"profile_source_hash_mismatch:{name}")
    rows = raw.get("source_files")
    if not isinstance(rows, list) or not rows:
        raise ContractViolation("manifest_source_files_missing")
    normalized: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ContractViolation("manifest_source_row_invalid")
        if set(row) != {"path", "bytes", "sha256"}:
            raise ContractViolation("manifest_source_row_fields_mismatch")
        rel = _relative(row.get("path"), "source_path")
        actual = _file_row(root, rel)
        if actual["bytes"] != row.get("bytes") or actual["sha256"] != row.get("sha256"):
            raise ContractViolation(f"source_hash_drift:{rel}")
        normalized.append(actual)
    if frozenset(row["path"] for row in normalized) != SOURCE_PATHS:
        raise ContractViolation("manifest_source_paths_mismatch")
    closure = _sha({"files": sorted(normalized, key=lambda item: str(item["path"])), "schema_id": "att1_ets2s_source_closure_v1"})
    if closure != raw.get("source_closure_sha256"):
        raise ContractViolation("source_closure_hash_mismatch")
    return tuple(sorted((str(row["path"]) for row in normalized))), closure


def load_contract(
    root: Path,
    config_path: Path | str,
    *,
    expected_config_sha256: str,
    expected_manifest_sha256: str,
) -> SignalShadowContract:
    root = _verify_trusted_root(Path(root))
    expected_config = root / TRUSTED_CONFIG_PATH
    supplied_config = Path(os.path.abspath(os.fspath(config_path)))
    if supplied_config != expected_config:
        raise ContractViolation("trusted_config_path_mismatch")
    try:
        config_bytes = _read_regular_nofollow(expected_config, violation="trusted_config_path_invalid")
        if hashlib.sha256(config_bytes).hexdigest() != _sha_field(
            expected_config_sha256, "expected_config_sha256"
        ):
            raise ContractViolation("config_hash_mismatch")
        raw = json.loads(config_bytes.decode("utf-8"))
    except ContractViolation:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractViolation("config_unreadable") from exc
    contract = SignalShadowContract.from_mapping(raw)
    source_paths, closure = _verify_manifest(
        root, contract, expected_manifest_sha256=expected_manifest_sha256
    )
    return SignalShadowContract(**{**contract.__dict__, "source_paths": source_paths, "source_closure_sha256": closure})


def load_deployment_anchor_fd(
    fd: int,
    *,
    expected_owner_uid: int = 0,
) -> dict[str, object]:
    """Validate and read an already-open deployment anchor without closing it."""

    try:
        owned_fd = os.dup(fd)
    except OSError as exc:
        raise ContractViolation("deployment_anchor_fd_invalid") from exc
    try:
        info = os.fstat(owned_fd)
        if info.st_uid != expected_owner_uid:
            raise ContractViolation("deployment_anchor_owner_mismatch")
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise ContractViolation("deployment_anchor_mode_mismatch")
        if info.st_nlink != 1:
            raise ContractViolation("deployment_anchor_link_count_mismatch")
        os.lseek(owned_fd, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(owned_fd, 64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
    except ContractViolation:
        raise
    except OSError as exc:
        raise ContractViolation("deployment_anchor_unreadable") from exc
    finally:
        os.close(owned_fd)
    try:
        raw = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractViolation("deployment_anchor_unreadable") from exc
    required = {
        "schema_id", "git_commit_sha", "config_path", "config_sha256", "manifest_path",
        "manifest_sha256", "source_closure_sha256", "privileged_launcher_sha256",
        "acknowledgement", "enabled",
        "money_authority", "orders_allowed", "private_api_allowed",
    }
    if not isinstance(raw, Mapping) or set(raw) != required:
        raise ContractViolation("deployment_anchor_fields_mismatch")
    if raw.get("schema_id") != DEPLOYMENT_ANCHOR_SCHEMA_ID:
        raise ContractViolation("deployment_anchor_schema_mismatch")
    if _GIT_SHA.fullmatch(str(raw.get("git_commit_sha") or "")) is None:
        raise ContractViolation("deployment_anchor_git_sha_invalid")
    if raw.get("config_path") != TRUSTED_CONFIG_PATH or raw.get("manifest_path") != TRUSTED_MANIFEST_PATH:
        raise ContractViolation("deployment_anchor_path_mismatch")
    _sha_field(raw.get("config_sha256"), "config_sha256")
    _sha_field(raw.get("manifest_sha256"), "manifest_sha256")
    _sha_field(raw.get("source_closure_sha256"), "source_closure_sha256")
    _sha_field(raw.get("privileged_launcher_sha256"), "privileged_launcher_sha256")
    if raw.get("acknowledgement") != ACK or raw.get("enabled") is not True:
        raise ContractViolation("deployment_anchor_authorization_mismatch")
    for field in ("money_authority", "orders_allowed", "private_api_allowed"):
        if raw.get(field) is not False:
            raise ContractViolation(f"unsafe_deployment_anchor:{field}")
    return dict(raw)


def load_deployment_anchor(
    path: Path | str,
    *,
    expected_owner_uid: int = 0,
) -> dict[str, object]:
    """Open a privilege-separated deployment anchor without following links."""

    anchor_path = Path(os.path.abspath(os.fspath(path)))
    fd = _open_nofollow(
        anchor_path,
        directory=False,
        violation="deployment_anchor_invalid",
    )
    try:
        return load_deployment_anchor_fd(fd, expected_owner_uid=expected_owner_uid)
    finally:
        os.close(fd)


def load_contract_from_deployment_anchor(
    root: Path,
    config_path: Path | str,
    deployment_anchor_path: Path | str,
    *,
    expected_owner_uid: int = 0,
) -> tuple[SignalShadowContract, dict[str, object]]:
    """Bind a deployed contract to its independently protected anchor file."""

    anchor = load_deployment_anchor(
        deployment_anchor_path,
        expected_owner_uid=expected_owner_uid,
    )
    contract = load_contract(
        root,
        config_path,
        expected_config_sha256=str(anchor["config_sha256"]),
        expected_manifest_sha256=str(anchor["manifest_sha256"]),
    )
    if not contract.enabled:
        raise ContractViolation("deployment_anchor_contract_not_enabled")
    if contract.source_closure_sha256 != anchor["source_closure_sha256"]:
        raise ContractViolation("deployment_anchor_source_closure_mismatch")
    require_operator_ack(contract, str(anchor["acknowledgement"]))
    return contract, anchor


def load_contract_from_deployment_anchor_fd(
    root: Path,
    config_path: Path | str,
    deployment_anchor_fd: int,
    *,
    expected_owner_uid: int = 0,
) -> tuple[SignalShadowContract, dict[str, object]]:
    """Bind a contract to the same inherited root-opened anchor file description."""

    anchor = load_deployment_anchor_fd(
        deployment_anchor_fd,
        expected_owner_uid=expected_owner_uid,
    )
    contract = load_contract(
        root,
        config_path,
        expected_config_sha256=str(anchor["config_sha256"]),
        expected_manifest_sha256=str(anchor["manifest_sha256"]),
    )
    if not contract.enabled:
        raise ContractViolation("deployment_anchor_contract_not_enabled")
    if contract.source_closure_sha256 != anchor["source_closure_sha256"]:
        raise ContractViolation("deployment_anchor_source_closure_mismatch")
    require_operator_ack(contract, str(anchor["acknowledgement"]))
    return contract, anchor


def require_operator_ack(contract: SignalShadowContract, acknowledgement: str | None) -> None:
    if contract.enabled and acknowledgement != contract.operator_ack:
        if acknowledgement is None:
            raise ContractViolation("operator_ack_required")
        raise ContractViolation("operator_ack_mismatch")


def validate_public_endpoint(url: str) -> str:
    value = str(url or "")
    if value != PUBLIC_KLINE_ENDPOINT:
        raise ContractViolation("unapproved_public_endpoint")
    return value


def _safe_runtime_path(root: Path, relative: str, field: str) -> Path:
    root = Path(os.path.abspath(os.fspath(root)))
    root_fd = _open_nofollow(root, directory=True, violation=f"symlink_runtime_root:{field}")
    os.close(root_fd)
    candidate = root / _relative(relative, field)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ContractViolation(f"unsafe_path:{field}") from exc
    current = root
    for part in candidate.relative_to(root).parts:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise ContractViolation(f"unsafe_path:{field}") from exc
        if stat.S_ISLNK(info.st_mode):
            raise ContractViolation(f"symlink_runtime_path:{field}")
    return candidate


def resolve_runtime_paths(root: Path, contract: SignalShadowContract, *, override: Mapping[str, str] | None = None) -> dict[str, Path]:
    values = dict(contract.runtime_paths)
    if override:
        for key, value in override.items():
            if key not in values:
                raise ContractViolation(f"unknown_runtime_path:{key}")
            values[key] = value
    return {key: _safe_runtime_path(root, value, f"runtime_paths:{key}") for key, value in values.items()}


def preflight(
    root: Path,
    config_path: Path | str,
    *,
    expected_config_sha256: str,
    expected_manifest_sha256: str,
) -> dict[str, object]:
    contract = load_contract(
        root,
        config_path,
        expected_config_sha256=expected_config_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    return {
        "schema_id": MANIFEST_SCHEMA_ID,
        "ok": True,
        "status": "RESEARCH_ONLY_DISABLED" if not contract.enabled else "OPT_IN_CONFIG_PRESENT",
        "authority": AUTHORITY,
        "money_authority": False,
        "orders_allowed": False,
        "private_api_allowed": False,
        "release_or_promotion_authority": False,
        "sealed_data_allowed": False,
        "public_base_url": PUBLIC_BASE_URL,
        "source_closure_sha256": contract.source_closure_sha256,
        "config_sha256": expected_config_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "evidence_universe_sha256": FIXED51_UNIVERSE_SHA256,
    }


__all__ = [
    "ACK", "ATT1_SOURCE_PATHS", "AUTHORITY", "CONFIG_SCHEMA_ID", "ContractViolation",
    "DEPLOYMENT_ANCHOR_PATH", "DEPLOYMENT_ANCHOR_SCHEMA_ID",
    "ETS2S_SOURCE_PATHS", "FIXED51_UNIVERSE", "FIXED51_UNIVERSE_SHA256", "MANIFEST_SCHEMA_ID",
    "PROFILE_CONFIG_HASHES", "PROFILE_FIXED51_CONFIG_HASHES", "PROFILE_SOURCE_HASHES", "SOURCE_PATHS",
    "PRIVILEGED_LAUNCHER_SOURCE_PATH",
    "PRIVILEGED_LAUNCHER_INSTALL_PATH",
    "PUBLIC_BASE_URL", "PUBLIC_KLINE_ENDPOINT", "SignalShadowContract", "load_contract",
    "load_contract_from_deployment_anchor", "load_contract_from_deployment_anchor_fd",
    "load_deployment_anchor", "load_deployment_anchor_fd",
    "TRUSTED_CONFIG_PATH", "TRUSTED_MANIFEST_PATH", "preflight", "require_operator_ack",
    "resolve_runtime_paths", "validate_public_endpoint",
]
