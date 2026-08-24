"""Fail-closed ATT1 fixed-51 public raw-decision boundary.

This module is intentionally a configuration/provenance boundary only.  It
does not import a broker, account, order client, trading monolith, or release
control.  The separate runner may consume public candles and call the real
default-off ATT1 live wrapper, but the evidence universe can never become the
major-8 money universe.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


AUTHORITY = "zero_risk_public_att1_fixed51_evidence_no_orders_no_money_no_promotion"
SCHEMA_ID = "att1_fixed51_zero_risk_shadow_config_v1"
MANIFEST_SCHEMA_ID = "att1_fixed51_public_shadow_manifest_v1"
ACK = "ATT1_FIXED51_ZERO_RISK_SHADOW"
MAX_DECISION_AGE_MS = 300_000
MIN_REPLAY_BARS = 121
EXPECTED_UNAVAILABLE_SYMBOLS = ("HFTUSDT",)
MANIFEST_SOURCE_PATHS = frozenset(
    {
        "strategies/alt_trendline_touch_v1.py",
        "strategies/att1_live.py",
        "strategies/live_kline_utils.py",
        "strategies/signals.py",
        "bot/live_native_regime_gate.py",
        "bot/live_native_decision_contract.py",
        "bot/att1_runtime_contract.py",
        "bot/att1_fixed51_shadow.py",
        "scripts/run_att1_fixed51_zero_risk_shadow.py",
        "deploy/systemd/att1-fixed51-raw-shadow.service",
        "deploy/systemd/att1-fixed51-raw-shadow.timer",
    }
)

ATT1_MONEY_UNIVERSE = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "DOTUSDT", "SUIUSDT",
)
ATT1_FIXED51_UNIVERSE = (
    "1000BONKUSDT", "1000PEPEUSDT", "1000RATSUSDT", "AAVEUSDT", "ACEUSDT", "ADAUSDT", "ALGOUSDT",
    "APTUSDT", "ARBUSDT", "ATOMUSDT", "AVAXUSDT", "BCHUSDT", "BICOUSDT", "BNBUSDT", "BTCUSDT",
    "C98USDT", "COTIUSDT", "CRVUSDT", "DOGEUSDT", "ETCUSDT", "ETHUSDT", "FILUSDT", "GALAUSDT",
    "HBARUSDT", "HFTUSDT", "ICPUSDT", "INJUSDT", "JTOUSDT", "LDOUSDT", "MNTUSDT", "ONDOUSDT",
    "OPUSDT", "ORDIUSDT", "PAXGUSDT", "PEOPLEUSDT", "SEIUSDT", "SHIB1000USDT", "SOLUSDT", "STRKUSDT",
    "SUIUSDT", "TAOUSDT", "TIAUSDT", "TRXUSDT", "UNIUSDT", "USDCUSDT", "WIFUSDT", "WLDUSDT",
    "XLMUSDT", "XMRUSDT", "XRPUSDT", "ZECUSDT",
)
_SHA = re.compile(r"[0-9a-f]{64}")


class ShadowViolation(ValueError):
    """Stable fail-closed error for evidence configuration/provenance drift."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ShadowViolation("noncanonical_shadow_payload") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> tuple[int, str]:
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def _sha_field(value: object, field: str) -> str:
    result = str(value or "").strip()
    if _SHA.fullmatch(result) is None:
        raise ShadowViolation(f"invalid_sha256:{field}")
    return result


def _relative(value: object, field: str) -> str:
    result = str(value or "").strip().replace("\\", "/")
    if not result or result.startswith("/") or result.startswith("../") or "/../" in result:
        raise ShadowViolation(f"unsafe_path:{field}")
    return result


@dataclass(frozen=True)
class Fixed51Config:
    enabled: bool
    authority: str
    money_universe: tuple[str, ...]
    evidence_universe: tuple[str, ...]
    manifest_path: str
    expected_manifest_sha256: str
    expected_preregistration_sha256: str
    evidence_universe_sha256: str
    journal_path: str
    public_base: str
    max_h1_bars: int
    max_decision_age_ms: int
    min_replay_bars: int
    expected_unavailable_symbols: tuple[str, ...]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "Fixed51Config":
        required = {
            "schema_id", "enabled", "authority", "money_authority", "orders_allowed",
            "private_api_allowed", "release_or_promotion_authority", "sealed_data_allowed",
            "money_universe", "evidence_universe", "manifest_path", "expected_manifest_sha256",
            "expected_preregistration_sha256", "evidence_universe_sha256", "journal_path",
            "public_base", "max_h1_bars", "max_decision_age_ms", "min_replay_bars",
            "expected_unavailable_symbols",
        }
        if not isinstance(raw, Mapping) or set(raw) != required:
            raise ShadowViolation("config_fields_mismatch")
        if raw.get("schema_id") != SCHEMA_ID:
            raise ShadowViolation("wrong_config_schema")
        if raw.get("authority") != AUTHORITY:
            raise ShadowViolation("wrong_shadow_authority")
        if raw.get("enabled") is not False and raw.get("enabled") is not True:
            raise ShadowViolation("enabled_not_boolean")
        for field in ("money_authority", "orders_allowed", "private_api_allowed", "release_or_promotion_authority", "sealed_data_allowed"):
            if raw.get(field) is not False:
                raise ShadowViolation(f"unsafe_authority:{field}")
        if raw.get("public_base") != "https://api.bybit.com":
            raise ShadowViolation("unapproved_public_base")
        money = tuple(str(x or "").strip().upper() for x in raw.get("money_universe", []))
        evidence = tuple(str(x or "").strip().upper() for x in raw.get("evidence_universe", []))
        if money != ATT1_MONEY_UNIVERSE:
            raise ShadowViolation("money_universe_mismatch")
        if evidence != ATT1_FIXED51_UNIVERSE:
            raise ShadowViolation("fixed51_universe_mismatch")
        if _sha(list(evidence)) != _sha_field(raw.get("evidence_universe_sha256"), "evidence_universe_sha256"):
            raise ShadowViolation("fixed51_universe_hash_mismatch")
        expected_unavailable = tuple(str(x or "").strip().upper() for x in raw.get("expected_unavailable_symbols", []))
        if expected_unavailable != EXPECTED_UNAVAILABLE_SYMBOLS:
            raise ShadowViolation("expected_unavailable_symbols_mismatch")
        try:
            max_bars = int(raw.get("max_h1_bars"))
            max_age = int(raw.get("max_decision_age_ms"))
            min_replay = int(raw.get("min_replay_bars"))
        except (TypeError, ValueError) as exc:
            raise ShadowViolation("invalid_numeric_boundary") from exc
        if isinstance(raw.get("max_h1_bars"), bool) or not 120 <= max_bars <= 1000:
            raise ShadowViolation("unsafe_max_h1_bars")
        if isinstance(raw.get("max_decision_age_ms"), bool) or max_age != MAX_DECISION_AGE_MS:
            raise ShadowViolation("unsafe_max_decision_age_ms")
        if isinstance(raw.get("min_replay_bars"), bool) or min_replay != MIN_REPLAY_BARS:
            raise ShadowViolation("unsafe_min_replay_bars")
        if max_bars < min_replay or max_bars < 200:
            raise ShadowViolation("history_boundary_too_short")
        return cls(
            enabled=bool(raw["enabled"]), authority=AUTHORITY, money_universe=money, evidence_universe=evidence,
            manifest_path=_relative(raw.get("manifest_path"), "manifest_path"),
            expected_manifest_sha256=_sha_field(raw.get("expected_manifest_sha256"), "expected_manifest_sha256"),
            expected_preregistration_sha256=_sha_field(raw.get("expected_preregistration_sha256"), "expected_preregistration_sha256"),
            evidence_universe_sha256=_sha_field(raw.get("evidence_universe_sha256"), "evidence_universe_sha256"),
            journal_path=_relative(raw.get("journal_path"), "journal_path"), public_base="https://api.bybit.com", max_h1_bars=max_bars,
            max_decision_age_ms=max_age, min_replay_bars=min_replay,
            expected_unavailable_symbols=expected_unavailable,
        )


def load_config(path: Path) -> Fixed51Config:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShadowViolation("config_unreadable") from exc
    return Fixed51Config.from_mapping(raw)


def verify_manifest(root: Path, config: Fixed51Config) -> dict[str, object]:
    path = root / config.manifest_path
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShadowViolation("manifest_unreadable") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_id") != MANIFEST_SCHEMA_ID:
        raise ShadowViolation("wrong_manifest_schema")
    if manifest.get("authority") != AUTHORITY or manifest.get("default_off") is not True or manifest.get("enabled") is not False:
        raise ShadowViolation("manifest_claims_authority")
    if manifest.get("money_universe") != list(ATT1_MONEY_UNIVERSE) or manifest.get("evidence_universe") != list(ATT1_FIXED51_UNIVERSE):
        raise ShadowViolation("manifest_universe_mismatch")
    evidence_hash = _sha(manifest["evidence_universe"])
    if evidence_hash != config.evidence_universe_sha256 or evidence_hash != manifest.get("evidence_universe_sha256"):
        raise ShadowViolation("fixed51_universe_hash_mismatch")
    if manifest.get("public_base") != config.public_base or manifest.get("private_api_allowed") is not False or manifest.get("orders_allowed") is not False:
        raise ShadowViolation("manifest_claims_authority")
    if (manifest.get("measurement_authority") != "raw_decision_only"
            or manifest.get("evidence_admitted") is not False
            or manifest.get("performance_authority") is not False
            or manifest.get("final_n_eligible") is not False):
        raise ShadowViolation("manifest_claims_measurement_authority")
    if (manifest.get("max_decision_age_ms") != config.max_decision_age_ms
            or manifest.get("min_replay_bars") != config.min_replay_bars
            or manifest.get("expected_unavailable_symbols") != list(config.expected_unavailable_symbols)):
        raise ShadowViolation("manifest_runtime_boundary_mismatch")
    prereg_path = root / _relative(manifest.get("preregistration_path"), "preregistration_path")
    try:
        prereg_sha = hashlib.sha256(prereg_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ShadowViolation("preregistration_unreadable") from exc
    if prereg_sha != config.expected_preregistration_sha256 or prereg_sha != manifest.get("preregistration_sha256"):
        raise ShadowViolation("preregistration_hash_mismatch")
    rows = manifest.get("source_files")
    if not isinstance(rows, list) or not rows:
        raise ShadowViolation("manifest_source_files_missing")
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            raise ShadowViolation("manifest_source_row_invalid")
        rel = _relative(row.get("path"), "source_path")
        try:
            size, digest = _file_sha(root / rel)
        except OSError as exc:
            raise ShadowViolation(f"source_unreadable:{rel}") from exc
        if size != row.get("bytes") or digest != row.get("sha256"):
            raise ShadowViolation(f"source_drift:{rel}")
        normalized.append({"path": rel, "bytes": size, "sha256": digest})
    if frozenset(row["path"] for row in normalized) != MANIFEST_SOURCE_PATHS:
        raise ShadowViolation("manifest_source_paths_mismatch")
    closure = _sha({"files": sorted(normalized, key=lambda x: x["path"]), "schema_id": "att1_fixed51_source_closure_v1"})
    if closure != manifest.get("source_closure_sha256"):
        raise ShadowViolation("source_closure_hash_mismatch")
    manifest_sha = hashlib.sha256(_canonical(manifest)).hexdigest()
    if manifest_sha != config.expected_manifest_sha256:
        raise ShadowViolation("manifest_hash_mismatch")
    return {"manifest_sha256": manifest_sha, "prereg_sha256": prereg_sha, "source_closure_sha256": closure,
            "evidence_universe_sha256": evidence_hash, "manifest": manifest}


def preflight(root: Path, config_path: Path) -> dict[str, object]:
    config = load_config(config_path)
    manifest = verify_manifest(root, config)
    return {
        "schema_id": "att1_fixed51_zero_risk_shadow_preflight_v1", "ok": True,
        "status": "RESEARCH_ONLY_DISABLED" if not config.enabled else "OPT_IN_CONFIG_PRESENT",
        "authority": AUTHORITY, "network_calls": False, "writes": False,
        "orders_allowed": False, "private_api_allowed": False, "money_authority": False,
        "release_or_promotion_authority": False, "evidence_admitted": False,
        "performance_authority": False, "final_n_eligible": False,
        "measurement_authority": "raw_decision_only", "money_universe": list(config.money_universe),
        "evidence_universe": list(config.evidence_universe), "manifest_sha256": manifest["manifest_sha256"],
        "prereg_sha256": manifest["prereg_sha256"], "source_closure_sha256": manifest["source_closure_sha256"],
        "max_decision_age_ms": config.max_decision_age_ms,
        "min_replay_bars": config.min_replay_bars,
        "expected_unavailable_symbols": list(config.expected_unavailable_symbols),
    }


__all__ = [
    "ACK", "ATT1_FIXED51_UNIVERSE", "ATT1_MONEY_UNIVERSE", "AUTHORITY",
    "EXPECTED_UNAVAILABLE_SYMBOLS", "MANIFEST_SOURCE_PATHS", "MAX_DECISION_AGE_MS", "MIN_REPLAY_BARS",
    "Fixed51Config", "ShadowViolation", "load_config", "preflight", "verify_manifest",
]
