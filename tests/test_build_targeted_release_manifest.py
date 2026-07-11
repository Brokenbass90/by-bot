from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.build_targeted_release_manifest import (
    ManifestError,
    build_targeted_release_manifest,
    main,
)


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def _git_commit_all(root: Path) -> None:
    subprocess.run(["git", "add", "--all"], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Manifest Test",
            "-c",
            "user.email=manifest@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=root,
        check=True,
    )


def _build(root: Path, files: list[str], output: str = "release/manifest.json") -> dict:
    return build_targeted_release_manifest(
        root,
        output_path=output,
        release_id="release-20260711",
        git_head="abc1234",
        file_paths=files,
    )


def test_manifest_hashes_only_explicit_files_and_records_dirty_boolean(tmp_path: Path) -> None:
    _git_init(tmp_path)
    selected = tmp_path / "bot" / "selected.py"
    selected.parent.mkdir()
    selected.write_bytes(b"print('selected')\n")
    selected.chmod(0o755)
    secret = tmp_path / "backup-env-secret.env"
    secret.write_text("TOKEN=do-not-serialize\n", encoding="utf-8")

    manifest = _build(tmp_path, ["bot/selected.py"])
    stored = json.loads((tmp_path / "release" / "manifest.json").read_text(encoding="utf-8"))

    expected_hash = hashlib.sha256(selected.read_bytes()).hexdigest()
    assert manifest == stored
    assert manifest["metadata"]["git_dirty"] is True
    assert manifest["metadata"]["explicit_files_only"] is True
    assert manifest["metadata"]["file_count"] == 1
    assert manifest["files"] == [
        {
            "path": "bot/selected.py",
            "sha256": expected_hash,
            "size_bytes": selected.stat().st_size,
            "mode": "0755",
        }
    ]
    serialized = json.dumps(manifest)
    assert "backup-env-secret.env" not in serialized
    assert "do-not-serialize" not in serialized


def test_manifest_bytes_are_reproducible_and_input_order_is_canonical(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "a.txt").write_text("a\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b\n", encoding="utf-8")
    _git_commit_all(tmp_path)

    first_manifest = _build(tmp_path, ["b.txt", "a.txt"])
    first = (tmp_path / "release" / "manifest.json").read_bytes()
    second_manifest = _build(tmp_path, ["a.txt", "b.txt"])
    second = (tmp_path / "release" / "manifest.json").read_bytes()

    assert first == second
    assert first_manifest["metadata"]["git_dirty"] is False
    assert second_manifest["metadata"]["git_dirty"] is False
    assert [row["path"] for row in json.loads(second)["files"]] == ["a.txt", "b.txt"]
    assert not list((tmp_path / "release").glob(".manifest.json.tmp.*"))


@pytest.mark.parametrize(
    "bad_path",
    [
        "/etc/passwd",
        "C:/Windows/system.ini",
        "../outside.txt",
        "inside/../../outside.txt",
        "./file.txt",
        "inside//file.txt",
        "inside\\..\\outside.txt",
        ".git/config",
    ],
)
def test_rejects_absolute_traversal_and_ambiguous_file_paths(
    tmp_path: Path, bad_path: str
) -> None:
    _git_init(tmp_path)
    (tmp_path / "file.txt").write_text("ok\n", encoding="utf-8")

    with pytest.raises(ManifestError):
        _build(tmp_path, [bad_path])


def test_rejects_missing_directory_and_duplicate_inputs(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "file.txt").write_text("ok\n", encoding="utf-8")
    (tmp_path / "directory").mkdir()

    with pytest.raises(ManifestError):
        _build(tmp_path, ["missing.txt"])
    with pytest.raises(ManifestError):
        _build(tmp_path, ["directory"])
    with pytest.raises(ManifestError):
        _build(tmp_path, ["file.txt", "file.txt"])


def test_rejects_symlink_file_and_symlink_directory_component(tmp_path: Path) -> None:
    _git_init(tmp_path)
    real = tmp_path / "real.txt"
    real.write_text("real\n", encoding="utf-8")
    (tmp_path / "linked.txt").symlink_to(real)
    real_dir = tmp_path / "real-dir"
    real_dir.mkdir()
    (real_dir / "nested.txt").write_text("nested\n", encoding="utf-8")
    (tmp_path / "linked-dir").symlink_to(real_dir, target_is_directory=True)

    with pytest.raises(ManifestError):
        _build(tmp_path, ["linked.txt"])
    with pytest.raises(ManifestError):
        _build(tmp_path, ["linked-dir/nested.txt"])


@pytest.mark.parametrize(
    "output",
    [
        "/tmp/manifest.json",
        "C:/Temp/manifest.json",
        "../manifest.json",
        ".git/manifest.json",
        "manifest.txt",
    ],
)
def test_output_must_be_safe_repo_relative_json(tmp_path: Path, output: str) -> None:
    _git_init(tmp_path)
    (tmp_path / "file.txt").write_text("ok\n", encoding="utf-8")

    with pytest.raises(ManifestError):
        _build(tmp_path, ["file.txt"], output=output)


def test_rejects_output_symlink_and_input_output_collision(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "file.txt").write_text("ok\n", encoding="utf-8")
    (tmp_path / "source.json").write_text("{}\n", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.json"
    outside.write_text("outside\n", encoding="utf-8")
    (tmp_path / "manifest.json").symlink_to(outside)
    real_output_dir = tmp_path / "real-output"
    real_output_dir.mkdir()
    (tmp_path / "linked-output").symlink_to(real_output_dir, target_is_directory=True)

    with pytest.raises(ManifestError):
        _build(tmp_path, ["file.txt"], output="manifest.json")
    with pytest.raises(ManifestError):
        _build(tmp_path, ["source.json"], output="source.json")
    with pytest.raises(ManifestError):
        _build(tmp_path, ["file.txt"], output="linked-output/manifest.json")

    assert outside.read_text(encoding="utf-8") == "outside\n"


def test_cli_requires_explicit_files_and_writes_no_runtime_side_effects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _git_init(tmp_path)
    (tmp_path / "safe.txt").write_text("safe\n", encoding="utf-8")

    rc = main(
        [
            "--repo-root",
            str(tmp_path),
            "--output",
            "manifests/release.json",
            "--release-id",
            "r1",
            "--git-head",
            "deadbeef",
            "--file",
            "safe.txt",
        ]
    )

    assert rc == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt == {
        "file_count": 1,
        "git_dirty": True,
        "git_head": "deadbeef",
        "output": "manifests/release.json",
        "release_id": "r1",
    }
    assert not (tmp_path / "runtime").exists()
    assert not (tmp_path / "logs").exists()
    assert not (tmp_path / "deploy").exists()


def test_empty_files_release_id_and_git_head_are_rejected(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "safe.txt").write_text("safe\n", encoding="utf-8")

    with pytest.raises(ManifestError):
        build_targeted_release_manifest(
            tmp_path,
            output_path="manifest.json",
            release_id="r1",
            git_head="deadbeef",
            file_paths=[],
        )
    with pytest.raises(ManifestError):
        build_targeted_release_manifest(
            tmp_path,
            output_path="manifest.json",
            release_id=" ",
            git_head="deadbeef",
            file_paths=["safe.txt"],
        )
    with pytest.raises(ManifestError):
        build_targeted_release_manifest(
            tmp_path,
            output_path="manifest.json",
            release_id="r1",
            git_head="\n",
            file_paths=["safe.txt"],
        )
