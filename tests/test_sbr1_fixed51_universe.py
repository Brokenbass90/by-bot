from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bot.sbr1_universe import (
    FIXED51_UNIVERSE,
    FIXED51_UNIVERSE_SHA256,
    MAJOR8_MONEY_UNIVERSE,
    load_fixed51_manifest,
    verify_fixed51_manifest,
)
from bot.sbr1_zero_risk_shadow import AUTHORITY, ShadowViolation, load_config
from scripts.run_sbr1_zero_risk_shadow import _preflight


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs/sbr1_zero_risk_shadow_v1.json"
FIXED51_MANIFEST = ROOT / "configs/research/sbr1_fixed51_evidence_manifest_v1.json"


def test_fixed51_identity_is_exact_stable_and_hash_bound() -> None:
    assert len(FIXED51_UNIVERSE) == 51
    assert len(set(FIXED51_UNIVERSE)) == 51
    assert FIXED51_UNIVERSE == tuple(sorted(FIXED51_UNIVERSE))
    assert all(symbol.endswith("USDT") for symbol in FIXED51_UNIVERSE)
    canonical = json.dumps(
        list(FIXED51_UNIVERSE), sort_keys=True, separators=(",", ":")
    ).encode("ascii")
    assert hashlib.sha256(canonical).hexdigest() == FIXED51_UNIVERSE_SHA256


def test_fixed51_manifest_provenance_is_the_frozen_preregistration() -> None:
    manifest = load_fixed51_manifest(FIXED51_MANIFEST)
    assert manifest.universe == FIXED51_UNIVERSE
    assert manifest.universe_sha256 == FIXED51_UNIVERSE_SHA256
    assert manifest.source_preregistration_path == (
        "research_lab/prereg/PREREG_SBR1_SHADOW_RANDOM_CONTROL_2026_08_24.md"
    )
    assert manifest.source_preregistration_sha256 == (
        "dffa60b17b785b9182560b1bace7105eef9d715488866dd665df77825cac7b68"
    )
    assert manifest.expected_structurally_unavailable == {
        "HFTUSDT": "bybit_linear_status_closed_observed_2026-08-24"
    }
    verify_fixed51_manifest(ROOT, manifest)


def test_evidence_and_money_universes_are_separate_in_shadow_config() -> None:
    config = load_config(CONFIG_PATH)
    assert config.authority == AUTHORITY
    assert config.evidence_universe == FIXED51_UNIVERSE
    assert config.money_universe == MAJOR8_MONEY_UNIVERSE
    assert config.evidence_universe != config.money_universe
    assert len(config.evaluation_universe) == 54
    assert len(config.raw_evidence_universe) == 46
    assert set(config.evaluation_universe) == set(config.evidence_universe) | set(
        config.money_universe
    )
    assert all(config.symbol_clusters[symbol] == "major8" for symbol in config.money_universe)
    assert config.money_universe == (
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "ADAUSDT",
        "LINKUSDT",
        "LTCUSDT",
        "DOTUSDT",
        "SUIUSDT",
    )


def test_preflight_rejects_fixed51_identity_or_provenance_drift(tmp_path: Path) -> None:
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    raw["evidence_universe_manifest_path"] = str(
        FIXED51_MANIFEST.relative_to(ROOT)
    )
    raw["expected_evidence_universe_manifest_sha256"] = "0" * 64
    drifted = tmp_path / "sbr1.json"
    drifted.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ShadowViolation, match="fixed51_manifest_hash_mismatch"):
        _preflight(ROOT, drifted)


def test_fixed51_shadow_config_cannot_gain_money_or_private_authority() -> None:
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for field in (
        "money_authority",
        "orders_allowed",
        "private_api_allowed",
        "release_or_promotion_authority",
        "sealed_data_allowed",
    ):
        raw[field] = True
        with pytest.raises(ShadowViolation, match=f"unsafe_authority:{field}"):
            load_config_from_mapping(raw)
        raw[field] = False


def test_fixed51_config_rejects_major8_cluster_drift() -> None:
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    raw["symbol_clusters"]["DOTUSDT"] = "fixed51_dot"
    with pytest.raises(ShadowViolation, match="money_universe_cluster_mismatch"):
        load_config_from_mapping(raw)


def load_config_from_mapping(raw: dict[str, object]):
    from bot.sbr1_zero_risk_shadow import ZeroRiskShadowConfig

    return ZeroRiskShadowConfig.from_mapping(raw)
