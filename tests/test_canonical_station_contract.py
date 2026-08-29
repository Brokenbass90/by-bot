import json
from pathlib import Path

import pytest

from research_lab.canonical_station import (
    AUTHORITY,
    MANIFEST_SCHEMA_ID,
    MigrationError,
    load_manifest,
)


def _manifest() -> dict:
    return {
        "schema_id": MANIFEST_SCHEMA_ID,
        "authority": AUTHORITY,
        "promotion_authority": False,
        "network_authority": False,
        "private_api_authority": False,
        "order_authority": False,
        "live_write_authority": False,
        "canonical_runtime_root": "runtime/local_research_station",
        "jobs": [
            {
                "name": "fixture",
                "process_kind": "deterministic_decision_loop",
                "screen_session": "canonical_fixture",
                "launcher": ["scripts/fixture.sh"],
                "evidence_paths": ["runtime/fixture/decision.json"],
                "source_paths": [],
                "config_paths": [],
                "input_paths": [],
            }
        ],
    }


def _write_launcher(root: Path) -> None:
    (root / "scripts").mkdir(exist_ok=True)
    (root / "scripts/fixture.sh").write_text("#!/bin/sh\n", encoding="utf-8")


def _write_manifest(root: Path, payload: dict, name: str = "station.json") -> Path:
    path = root / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_manifest_requires_all_exact_authority_fields(tmp_path: Path) -> None:
    _write_launcher(tmp_path)
    path = _write_manifest(tmp_path, _manifest())
    assert load_manifest(path, project_root=tmp_path)["authority"] == AUTHORITY

    broken = _manifest()
    del broken["live_write_authority"]
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(MigrationError, match="live_write_authority"):
        load_manifest(path, project_root=tmp_path)


@pytest.mark.parametrize(
    "field", ("promotion_authority", "network_authority", "private_api_authority", "order_authority", "live_write_authority")
)
def test_manifest_rejects_every_unsafe_authority(field: str, tmp_path: Path) -> None:
    _write_launcher(tmp_path)
    broken = _manifest()
    broken[field] = True
    with pytest.raises(MigrationError, match=field):
        load_manifest(_write_manifest(tmp_path, broken), project_root=tmp_path)


@pytest.mark.parametrize("value", ("runtime/*.json", "/tmp/unsafe.json", "runtime/[ab].json"))
def test_manifest_rejects_globs_and_absolute_job_paths(value: str, tmp_path: Path) -> None:
    _write_launcher(tmp_path)
    broken = _manifest()
    broken["jobs"][0]["evidence_paths"] = [value]
    with pytest.raises(MigrationError, match="explicit relative paths"):
        load_manifest(_write_manifest(tmp_path, broken), project_root=tmp_path)


def test_manifest_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    _write_launcher(tmp_path)
    raw = json.dumps(_manifest())
    raw = raw.replace('"authority": "research_only_no_live_or_promotion",', '"authority": "wrong", "authority": "research_only_no_live_or_promotion",')
    path = tmp_path / "duplicate.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(MigrationError, match="duplicate JSON key"):
        load_manifest(path, project_root=tmp_path)


@pytest.mark.parametrize("fragment", ("--live", "--place-order", "--private-api", "API_KEY=secret"))
def test_manifest_rejects_forbidden_launcher_fragments(fragment: str, tmp_path: Path) -> None:
    _write_launcher(tmp_path)
    broken = _manifest()
    broken["jobs"][0]["launcher"].append(fragment)
    with pytest.raises(MigrationError, match="forbidden launcher argument"):
        load_manifest(_write_manifest(tmp_path, broken), project_root=tmp_path)


def test_manifest_rejects_duplicate_jobs_and_unknown_process_kind(tmp_path: Path) -> None:
    _write_launcher(tmp_path)
    duplicate = _manifest()
    duplicate["jobs"].append(dict(duplicate["jobs"][0]))
    with pytest.raises(MigrationError, match="duplicate job name"):
        load_manifest(_write_manifest(tmp_path, duplicate, "duplicate-job.json"), project_root=tmp_path)

    unknown = _manifest()
    unknown["jobs"][0]["process_kind"] = "ai_money_router"
    with pytest.raises(MigrationError, match="process_kind"):
        load_manifest(_write_manifest(tmp_path, unknown, "unknown-kind.json"), project_root=tmp_path)
