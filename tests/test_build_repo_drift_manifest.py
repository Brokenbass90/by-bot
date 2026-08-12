import json
import subprocess

from scripts.build_repo_drift_manifest import build_manifest, classify_path


def test_classification_is_conservative_and_secret_aware():
    assert classify_path("configs/backup-env-20260710.env")[0] == "secret_or_env_backup"
    assert classify_path("runtime/live_positions.json")[0] == "runtime_or_log"
    assert classify_path("scripts/manual_fix.py")[0] == "manual_code_candidate"
    assert classify_path("server_pull_20260710.tar.gz")[0] == "archive_or_backup"
    assert classify_path("mystery.bin")[0] == "unknown_review"
    assert classify_path("bot/core.py", " M")[0] == "tracked_change"


def test_manifest_reads_git_metadata_without_reading_contents(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.py"
    tracked.write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.py"], cwd=tmp_path, check=True)
    tracked.write_text("changed\n", encoding="utf-8")
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime" / "state.json").write_text(json.dumps({"ok": True}), encoding="utf-8")

    manifest = build_manifest(tmp_path)

    assert manifest["read_only"] is True
    assert manifest["content_scanned"] is False
    assert manifest["record_count"] == 2
    cats = {item["path"]: item["category"] for item in manifest["entries"]}
    assert cats["tracked.py"] == "tracked_change"
    assert cats["runtime/state.json"] == "runtime_or_log"
