from __future__ import annotations

import hashlib
import json

import pytest

from bot.live_native_manifest import ManifestViolation, load_and_verify_manifest


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest(data_sha: str, source_sha: str) -> dict:
    return {
        "schema_id": "att1_sbr1_live_native_parity_manifest_v1",
        "authority": "research_only_no_live_no_broker_no_promotion",
        "default_off": True,
        "enabled": False,
        "money_authority": False,
        "live_or_broker_calls": False,
        "window": {"start_utc": "2024-03-01T00:00:00Z", "end_utc_exclusive": "2025-10-01T00:00:00Z"},
        "sealed_holdout_guard": {"start_utc": "2025-10-01T00:00:00Z", "end_utc_exclusive": "2026-07-01T00:00:00Z", "must_not_read": True},
        "universe": ["BTCUSDT"],
        "data_files": [{"symbol": "BTCUSDT", "path": "data.json", "bytes": 4, "sha256": data_sha}],
        "source_files": [{"path": "source.py", "bytes": 6, "sha256": source_sha}],
        "exchange_filters": {"BTCUSDT": {"tick_size": "0.1", "qty_step": "0.001", "min_notional": "5"}},
        "profiles": {"ATT1": {}, "SBR1": {}},
        "regime_contract": {"timeframe": "60", "ema_period": 200},
        "cost_contracts": {
            "base": {"fee_bps_per_side": "6", "slippage_bps_per_side": "2", "adverse_funding_bps_per_8h": "0"},
            "stress": {"fee_bps_per_side": "6", "slippage_bps_per_side": "5", "adverse_funding_bps_per_8h": "1"},
        },
    }


def test_manifest_binds_data_source_universe_filters_and_costs(tmp_path) -> None:
    (tmp_path / "data.json").write_bytes(b"data")
    (tmp_path / "source.py").write_bytes(b"source")
    payload = _manifest(_sha(b"data"), _sha(b"source"))
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    verified = load_and_verify_manifest(tmp_path, path)
    assert verified.universe == ("BTCUSDT",)
    assert len(verified.manifest_sha256) == 64


def test_manifest_rejects_source_drift_and_authority_escalation(tmp_path) -> None:
    (tmp_path / "data.json").write_bytes(b"data")
    (tmp_path / "source.py").write_bytes(b"source")
    payload = _manifest(_sha(b"data"), _sha(b"source"))
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "source.py").write_bytes(b"changed")
    with pytest.raises(ManifestViolation, match="byte_mismatch|sha_mismatch"):
        load_and_verify_manifest(tmp_path, path)

    (tmp_path / "source.py").write_bytes(b"source")
    payload["money_authority"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ManifestViolation, match="claims_authority"):
        load_and_verify_manifest(tmp_path, path)
