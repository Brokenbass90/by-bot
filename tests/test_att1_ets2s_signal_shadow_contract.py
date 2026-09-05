from __future__ import annotations

import json
import hashlib
import os
import shutil
from pathlib import Path

import pytest

from bot.att1_ets2s_signal_shadow_contract import (
    ACK,
    AUTHORITY,
    CONFIG_SCHEMA_ID,
    DEPLOYMENT_ANCHOR_SCHEMA_ID,
    FIXED51_UNIVERSE,
    FIXED51_UNIVERSE_SHA256,
    MANIFEST_SCHEMA_ID,
    PUBLIC_BASE_URL,
    SOURCE_PATHS,
    TRUSTED_CONFIG_PATH,
    TRUSTED_MANIFEST_PATH,
    ContractViolation,
    load_deployment_anchor,
    load_deployment_anchor_fd,
    load_contract,
    preflight,
    resolve_runtime_paths,
    require_operator_ack,
    validate_public_endpoint,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs/att1_ets2s_signal_shadow_v1.json"


def _raw_config() -> dict[str, object]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _write_config(tmp_path: Path, **changes: object) -> Path:
    raw = _raw_config()
    raw.update(changes)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _rewrite_trusted_config(isolated: Path, **changes: object) -> Path:
    path = isolated / "configs/att1_ets2s_signal_shadow_v1.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.update(changes)
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _anchors(repo: Path) -> dict[str, str]:
    return {
        "expected_config_sha256": hashlib.sha256((repo / TRUSTED_CONFIG_PATH).read_bytes()).hexdigest(),
        "expected_manifest_sha256": hashlib.sha256((repo / TRUSTED_MANIFEST_PATH).read_bytes()).hexdigest(),
    }


def _load(repo: Path, config: Path | None = None, *, anchors: dict[str, str] | None = None):
    return load_contract(
        repo,
        config or repo / TRUSTED_CONFIG_PATH,
        **(anchors or _anchors(repo)),
    )


def _rebind_manifest(repo: Path) -> dict[str, str]:
    path = repo / TRUSTED_MANIFEST_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for relative in sorted(SOURCE_PATHS):
        data = (repo / relative).read_bytes()
        rows.append({"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    raw["source_files"] = rows
    raw["source_closure_sha256"] = hashlib.sha256(
        json.dumps(
            {"files": rows, "schema_id": "att1_ets2s_source_closure_v1"},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
    ).hexdigest()
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return _anchors(repo)


def _isolated_repo(tmp_path: Path) -> Path:
    isolated = tmp_path / "repo"
    for relative in sorted(set(SOURCE_PATHS) | {TRUSTED_MANIFEST_PATH}):
        destination = isolated / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    return isolated


def test_repository_contract_is_default_off_and_binds_att1_ets2s_fixed51() -> None:
    contract = _load(ROOT)

    assert contract.schema_id == CONFIG_SCHEMA_ID
    assert contract.authority == AUTHORITY
    assert contract.enabled is False
    assert contract.evidence_universe == FIXED51_UNIVERSE
    assert contract.evidence_universe_sha256 == FIXED51_UNIVERSE_SHA256
    assert set(contract.profiles) == {"ATT1", "ETS2S"}
    assert contract.store_contract_id == "canonical_closed_utc_buckets_v1"
    assert contract.public_base_url == PUBLIC_BASE_URL
    assert contract.allowed_public_endpoints == ("https://api.bybit.com/v5/market/kline",)
    assert contract.data_policy["min_bootstrap_h1_bars"] == 2160
    assert contract.data_policy["max_cache_h1_bars"] == 2880
    assert contract.data_policy["min_runtime_free_bytes"] == 536870912
    assert contract.expected_unavailable_symbols == ("HFTUSDT",)
    assert set(contract.runtime_paths) == {"cache", "journal", "heartbeat", "state"}

    receipt = preflight(ROOT, CONFIG_PATH, **_anchors(ROOT))
    assert receipt["schema_id"] == MANIFEST_SCHEMA_ID
    assert receipt["ok"] is True
    assert receipt["money_authority"] is False
    assert receipt["orders_allowed"] is False
    assert receipt["private_api_allowed"] is False
    assert receipt["release_or_promotion_authority"] is False
    assert receipt["sealed_data_allowed"] is False


def test_deployment_anchor_requires_exact_schema_owner_and_mode(tmp_path: Path) -> None:
    anchor = tmp_path / "anchor.json"
    payload = {
        "schema_id": DEPLOYMENT_ANCHOR_SCHEMA_ID,
        "git_commit_sha": "1" * 40,
        "config_path": TRUSTED_CONFIG_PATH,
        "config_sha256": "2" * 64,
        "manifest_path": TRUSTED_MANIFEST_PATH,
        "manifest_sha256": "3" * 64,
        "source_closure_sha256": "4" * 64,
        "privileged_launcher_sha256": "5" * 64,
        "acknowledgement": ACK,
        "enabled": True,
        "money_authority": False,
        "orders_allowed": False,
        "private_api_allowed": False,
    }
    anchor.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(anchor, 0o600)
    assert load_deployment_anchor(anchor, expected_owner_uid=os.geteuid()) == payload
    fd = os.open(anchor, os.O_RDONLY)
    try:
        assert load_deployment_anchor_fd(fd, expected_owner_uid=os.geteuid()) == payload
    finally:
        os.close(fd)

    os.chmod(anchor, 0o640)
    with pytest.raises(ContractViolation, match="deployment_anchor_mode"):
        load_deployment_anchor(anchor, expected_owner_uid=os.geteuid())


def test_enabled_execution_requires_literal_operator_ack(tmp_path: Path) -> None:
    isolated = _isolated_repo(tmp_path)
    config = _rewrite_trusted_config(isolated, enabled=True)
    contract = _load(isolated, config, anchors=_rebind_manifest(isolated))

    with pytest.raises(ContractViolation, match="operator_ack_required"):
        require_operator_ack(contract, None)
    with pytest.raises(ContractViolation, match="operator_ack_mismatch"):
        require_operator_ack(contract, "ATT1_FIXED51_ZERO_RISK_SHADOW")

    require_operator_ack(contract, ACK)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("money_authority", True, "unsafe_authority:money_authority"),
        ("orders_allowed", True, "unsafe_authority:orders_allowed"),
        ("private_api_allowed", True, "unsafe_authority:private_api_allowed"),
        ("release_or_promotion_authority", True, "unsafe_authority:release_or_promotion_authority"),
        ("sealed_data_allowed", True, "unsafe_authority:sealed_data_allowed"),
        ("public_base_url", "https://api.bybit.com.evil.example", "unapproved_public_base_url"),
        ("evidence_universe_sha256", "0" * 64, "fixed51_universe_hash_mismatch"),
        ("expected_unavailable_symbols", ["HFTUSDT", "BADUSDT"], "expected_unavailable_symbols_mismatch"),
    ],
)
def test_contract_rejects_authority_endpoint_and_universe_drift(
    tmp_path: Path, field: str, value: object, error: str
) -> None:
    isolated = _isolated_repo(tmp_path)
    with pytest.raises(ContractViolation, match=error):
        _load(isolated, _rewrite_trusted_config(isolated, **{field: value}))


def test_manifest_rejects_profile_or_source_hash_drift(tmp_path: Path) -> None:
    with pytest.raises(ContractViolation, match="profile_(source_)?hash_mismatch"):
        raw = _raw_config()
        raw["profiles"]["ETS2S"]["source_hash"] = "0" * 64
        from bot.att1_ets2s_signal_shadow_contract import SignalShadowContract

        SignalShadowContract.from_mapping(raw)


def test_runtime_paths_are_beneath_caller_root_and_reject_escape_and_symlink(
    tmp_path: Path,
) -> None:
    contract = _load(ROOT)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()

    paths = resolve_runtime_paths(runtime_root, contract)
    assert all(path == path.absolute() for path in paths.values())
    assert all(runtime_root in path.parents for path in paths.values())

    with pytest.raises(ContractViolation, match="unsafe_path"):
        resolve_runtime_paths(runtime_root, contract, override={"journal": "../escape.jsonl"})
    with pytest.raises(ContractViolation, match="unsafe_path"):
        resolve_runtime_paths(runtime_root, contract, override={"journal": "/tmp/escape.jsonl"})

    symlink = runtime_root / "journal.jsonl"
    symlink.symlink_to(tmp_path / "outside.jsonl")
    with pytest.raises(ContractViolation, match="symlink"):
        resolve_runtime_paths(runtime_root, contract, override={"journal": "journal.jsonl"})


def test_manifest_source_closure_is_hash_bound_to_config_and_required_paths() -> None:
    contract = _load(ROOT)
    assert contract.source_closure_sha256
    assert {
        "research_lab/research_ohlcv_store.py",
        "strategies/att1_live.py",
        "strategies/elder_live.py",
        "scripts/run_att1_ets2s_signal_shadow.py",
        "deploy/systemd/att1-ets2s-signal-shadow.service",
        "deploy/systemd/att1-ets2s-signal-shadow.timer",
    }.issubset(set(contract.source_paths))


def test_load_contract_rejects_external_or_symlinked_config_and_root(tmp_path: Path) -> None:
    isolated = _isolated_repo(tmp_path)
    config = isolated / "configs/att1_ets2s_signal_shadow_v1.json"
    with pytest.raises(ContractViolation, match="trusted_config_path"):
        _load(ROOT, _write_config(tmp_path, enabled=False))

    symlink_config = isolated / "configs/att1_ets2s_signal_shadow_v1.json.link"
    symlink_config.symlink_to(config)
    with pytest.raises(ContractViolation, match="trusted_config_path"):
        _load(isolated, symlink_config)

    symlink_root = tmp_path / "root-link"
    symlink_root.symlink_to(isolated, target_is_directory=True)
    with pytest.raises(ContractViolation, match="symlink_trusted_root"):
        load_contract(
            symlink_root,
            symlink_root / TRUSTED_CONFIG_PATH,
            **_anchors(isolated),
        )


def test_config_bytes_require_an_external_anchor_before_loading(tmp_path: Path) -> None:
    isolated = _isolated_repo(tmp_path)
    anchors = _anchors(isolated)
    _rewrite_trusted_config(isolated, enabled=True)
    with pytest.raises(ContractViolation, match="config_hash_mismatch"):
        _load(isolated, anchors=anchors)


def test_manifest_requires_exact_fields_and_anchor_matches_actual_bytes(tmp_path: Path) -> None:
    isolated = _isolated_repo(tmp_path)
    original_anchors = _anchors(isolated)
    manifest_path = isolated / "configs/research/att1_ets2s_signal_shadow_manifest_v1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["unexpected"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ContractViolation, match="manifest_hash_mismatch"):
        _load(isolated, anchors=original_anchors)

    anchors = _anchors(isolated)
    with pytest.raises(ContractViolation, match="manifest_fields_mismatch"):
        _load(isolated, anchors=anchors)


def test_manifest_and_source_mutations_are_rejected_in_isolated_repo(tmp_path: Path) -> None:
    isolated = _isolated_repo(tmp_path)
    original_anchors = _anchors(isolated)
    manifest_path = isolated / "configs/research/att1_ets2s_signal_shadow_manifest_v1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["operator_ack"] = "WRONG"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ContractViolation, match="manifest_hash_mismatch"):
        _load(isolated, anchors=original_anchors)

    anchors = _anchors(isolated)
    with pytest.raises(ContractViolation, match="operator_ack"):
        _load(isolated, anchors=anchors)

    isolated = _isolated_repo(tmp_path / "source")
    source = isolated / "strategies/elder_live.py"
    source.write_text(source.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
    with pytest.raises(ContractViolation, match="source_hash_drift|profile_source_hash_mismatch"):
        _load(isolated)


def test_source_ancestor_symlinks_are_rejected(tmp_path: Path) -> None:
    isolated = _isolated_repo(tmp_path)
    source_dir = isolated / "strategies"
    moved = tmp_path / "strategies-real"
    source_dir.rename(moved)
    source_dir.symlink_to(moved, target_is_directory=True)
    with pytest.raises(ContractViolation, match="symlink_source"):
        _load(isolated)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.bybit.com",
        "https://api.bybit.com/v5/market/kline?category=linear",
        "https://api.bybit.com/v5/market/tickers",
        "http://api.bybit.com/v5/market/kline",
        "https://user:pass@api.bybit.com/v5/market/kline",
        "https://api.bybit.com:443/v5/market/kline",
        "https://api.bybit.com/v5/market/kline#fragment",
    ],
)
def test_endpoint_validator_accepts_only_exact_public_kline_endpoint(url: str) -> None:
    with pytest.raises(ContractViolation, match="unapproved_public_endpoint"):
        validate_public_endpoint(url)


def test_endpoint_validator_accepts_the_exact_public_kline_endpoint() -> None:
    url = "https://api.bybit.com/v5/market/kline"
    assert validate_public_endpoint(url) == url
