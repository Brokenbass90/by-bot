"""Hash-bound SBR1 evidence and money universe boundaries.

The fixed-51 list is copied from the frozen pre-first-admitted-decision
preregistration.  This module never selects symbols or grants execution
authority; it only verifies immutable identity and provenance.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class UniverseViolation(ValueError):
    """Fail-closed fixed-universe validation error."""


MAJOR8_MONEY_UNIVERSE = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "ADAUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "DOTUSDT",
    "SUIUSDT",
)

FIXED51_UNIVERSE = tuple(
    f"{symbol}USDT"
    for symbol in (
        "1000BONK",
        "1000PEPE",
        "1000RATS",
        "AAVE",
        "ACE",
        "ADA",
        "ALGO",
        "APT",
        "ARB",
        "ATOM",
        "AVAX",
        "BCH",
        "BICO",
        "BNB",
        "BTC",
        "C98",
        "COTI",
        "CRV",
        "DOGE",
        "ETC",
        "ETH",
        "FIL",
        "GALA",
        "HBAR",
        "HFT",
        "ICP",
        "INJ",
        "JTO",
        "LDO",
        "MNT",
        "ONDO",
        "OP",
        "ORDI",
        "PAXG",
        "PEOPLE",
        "SEI",
        "SHIB1000",
        "SOL",
        "STRK",
        "SUI",
        "TAO",
        "TIA",
        "TRX",
        "UNI",
        "USDC",
        "WIF",
        "WLD",
        "XLM",
        "XMR",
        "XRP",
        "ZEC",
    )
)


def canonical_universe_sha256(universe: tuple[str, ...]) -> str:
    payload = json.dumps(
        list(universe), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


FIXED51_UNIVERSE_SHA256 = "fa5c61703cac5c72218022f15d92ee46d6fa577df84c9cfcbf8cc005893bfe19"
MAJOR8_MONEY_UNIVERSE_SHA256 = canonical_universe_sha256(MAJOR8_MONEY_UNIVERSE)
PREREGISTRATION_RELATIVE_PATH = (
    "research_lab/prereg/PREREG_SBR1_SHADOW_RANDOM_CONTROL_2026_08_24.md"
)
PREREGISTRATION_SHA256 = (
    "dffa60b17b785b9182560b1bace7105eef9d715488866dd665df77825cac7b68"
)
EXPECTED_STRUCTURALLY_UNAVAILABLE = {
    "HFTUSDT": "bybit_linear_status_closed_observed_2026-08-24",
}


@dataclass(frozen=True)
class Fixed51Manifest:
    universe: tuple[str, ...]
    universe_sha256: str
    source_preregistration_path: str
    source_preregistration_sha256: str
    money_universe: tuple[str, ...]
    money_universe_sha256: str
    authority: str
    expected_structurally_unavailable: Mapping[str, str]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_symbols(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise UniverseViolation(f"invalid_{field}")
    symbols = tuple(str(item or "").strip().upper() for item in value)
    if any(re.fullmatch(r"[A-Z0-9]{2,20}USDT", symbol) is None for symbol in symbols):
        raise UniverseViolation(f"invalid_{field}")
    if len(set(symbols)) != len(symbols):
        raise UniverseViolation(f"unstable_{field}")
    return symbols


def load_fixed51_manifest(path: Path) -> Fixed51Manifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UniverseViolation("fixed51_manifest_unreadable") from exc
    if not isinstance(raw, Mapping) or raw.get("schema_id") != "sbr1_fixed51_evidence_manifest_v1":
        raise UniverseViolation("fixed51_manifest_schema")
    universe = _validate_symbols(raw.get("universe"), "evidence_universe")
    money_universe = _validate_symbols(raw.get("money_universe"), "money_universe")
    if universe != FIXED51_UNIVERSE:
        raise UniverseViolation("fixed51_universe_identity_mismatch")
    if money_universe != MAJOR8_MONEY_UNIVERSE:
        raise UniverseViolation("money_universe_identity_mismatch")
    if raw.get("universe_sha256") != FIXED51_UNIVERSE_SHA256:
        raise UniverseViolation("fixed51_universe_hash_mismatch")
    if raw.get("money_universe_sha256") != MAJOR8_MONEY_UNIVERSE_SHA256:
        raise UniverseViolation("money_universe_hash_mismatch")
    if raw.get("source_preregistration_path") != PREREGISTRATION_RELATIVE_PATH:
        raise UniverseViolation("fixed51_preregistration_path_mismatch")
    if raw.get("source_preregistration_sha256") != PREREGISTRATION_SHA256:
        raise UniverseViolation("fixed51_preregistration_hash_mismatch")
    if raw.get("authority") != "research_only_no_orders_no_private_api_no_money_no_promotion":
        raise UniverseViolation("fixed51_unsafe_authority")
    unavailable = raw.get("expected_structurally_unavailable")
    if unavailable != EXPECTED_STRUCTURALLY_UNAVAILABLE:
        raise UniverseViolation("fixed51_expected_unavailable_mismatch")
    return Fixed51Manifest(
        universe=universe,
        universe_sha256=str(raw["universe_sha256"]),
        source_preregistration_path=str(raw["source_preregistration_path"]),
        source_preregistration_sha256=str(raw["source_preregistration_sha256"]),
        money_universe=money_universe,
        money_universe_sha256=str(raw["money_universe_sha256"]),
        authority=str(raw["authority"]),
        expected_structurally_unavailable=dict(EXPECTED_STRUCTURALLY_UNAVAILABLE),
    )


def verify_fixed51_manifest(root: Path, manifest: Fixed51Manifest) -> None:
    prereg = root / manifest.source_preregistration_path
    try:
        prereg_bytes = prereg.read_bytes()
    except OSError as exc:
        raise UniverseViolation("fixed51_preregistration_unreadable") from exc
    actual = _sha256_bytes(prereg_bytes)
    if actual != manifest.source_preregistration_sha256:
        raise UniverseViolation("fixed51_preregistration_hash_mismatch")
    text = prereg_bytes.decode("utf-8")
    match = re.search(r"```text\s*\n([^`]+?)\n```", text)
    if not match:
        raise UniverseViolation("fixed51_preregistration_universe_missing")
    source_symbols = tuple(
        f"{item.strip().upper()}USDT"
        for item in match.group(1).replace("\n", "").split(",")
        if item.strip()
    )
    if source_symbols != manifest.universe:
        raise UniverseViolation("fixed51_preregistration_universe_mismatch")


__all__ = [
    "FIXED51_UNIVERSE",
    "FIXED51_UNIVERSE_SHA256",
    "EXPECTED_STRUCTURALLY_UNAVAILABLE",
    "MAJOR8_MONEY_UNIVERSE",
    "MAJOR8_MONEY_UNIVERSE_SHA256",
    "PREREGISTRATION_RELATIVE_PATH",
    "PREREGISTRATION_SHA256",
    "Fixed51Manifest",
    "UniverseViolation",
    "canonical_universe_sha256",
    "load_fixed51_manifest",
    "verify_fixed51_manifest",
]
