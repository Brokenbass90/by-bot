#!/usr/bin/env python3
"""Build a read-only manifest for a dirty local/VPS repository.

The script never reads file contents and never moves/deletes anything.  It
classifies tracked changes and every untracked path so an operator can preserve
manual code, move secrets/backups out of the checkout, and quarantine archives
before a reviewed fast-forward deploy.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CODE_ROOTS = {
    "backtest", "bot", "forex", "research_lab", "scripts", "strategies", "tests", "web"
}
CODE_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".html", ".css", ".sh"}
ARCHIVE_SUFFIXES = {".bak", ".gz", ".tgz", ".tar", ".zip", ".7z", ".old"}
SECRET_MARKERS = (".env", "backup-env", "env_backup", "secret", "credential", "apikey", "api_key")
ARCHIVE_MARKERS = ("backup", "archive", "snapshot", "server_pull", "manual_copy")


def classify_path(path: str, status: str = "??") -> tuple[str, str, bool]:
    """Return category, recommended disposition, and secret-looking flag."""
    norm = str(path or "").replace("\\", "/").lstrip("./")
    low = norm.lower()
    parts = [p for p in low.split("/") if p]
    suffix = Path(low).suffix
    secret_like = any(marker in low for marker in SECRET_MARKERS)

    if status != "??":
        return (
            "tracked_change",
            "review diff; commit intentionally or preserve as a named patch before deploy",
            secret_like,
        )
    if secret_like:
        return (
            "secret_or_env_backup",
            "move to a permissioned directory outside the repo; rotate if exposure is possible",
            True,
        )
    if parts and parts[0] in {"runtime", "logs"}:
        return (
            "runtime_or_log",
            "keep outside version control; retain only the evidence window required by policy",
            False,
        )
    if suffix in ARCHIVE_SUFFIXES or any(marker in low for marker in ARCHIVE_MARKERS):
        return (
            "archive_or_backup",
            "quarantine outside the checkout; delete only after owner-reviewed manifest",
            False,
        )
    if parts and parts[0] in CODE_ROOTS and suffix in CODE_SUFFIXES:
        return (
            "manual_code_candidate",
            "review references/tests; commit if canonical, otherwise preserve as a patch or quarantine",
            False,
        )
    if parts and parts[0] in {"data", "data_cache", "backtest_runs"}:
        return (
            "data_or_research_output",
            "keep reproducibility manifest; store bulk data/artifacts outside the code checkout",
            False,
        )
    if parts and parts[0] == "reports":
        return (
            "report_or_research_output",
            "commit canonical evidence/indexes; archive bulky generated runs by retention policy",
            False,
        )
    if suffix in {".md", ".txt", ".json", ".csv"}:
        return (
            "document_or_metadata",
            "review for canonical value, references and secrets before commit/archive",
            False,
        )
    return ("unknown_review", "manual review; do not delete or deploy over it blindly", False)


def _git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root)


def _git_text(root: Path, *args: str, default: str = "") -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if proc.returncode != 0:
        return default
    return proc.stdout.decode("utf-8", errors="replace").strip()


def _status_records(root: Path) -> list[tuple[str, str]]:
    raw = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    fields = raw.split(b"\0")
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(fields):
        field = fields[i]
        if not field:
            i += 1
            continue
        text = field.decode("utf-8", errors="surrogateescape")
        status = text[:2]
        path = text[3:] if len(text) >= 4 else ""
        out.append((status, path))
        i += 2 if any(ch in status for ch in "RC") else 1
    return out


def build_manifest(root: Path, *, max_entries: int = 10000) -> dict[str, Any]:
    root = root.resolve()
    records = _status_records(root)
    truncated = len(records) > max_entries
    entries: list[dict[str, Any]] = []
    for status, rel in records[:max_entries]:
        category, action, secret_like = classify_path(rel, status)
        path = root / rel
        try:
            st = path.stat()
            size = st.st_size if path.is_file() else None
            mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            size = None
            mtime = None
        entries.append(
            {
                "status": status,
                "path": rel,
                "category": category,
                "secret_like_name": secret_like,
                "size_bytes": size,
                "mtime_utc": mtime,
                "recommended_disposition": action,
            }
        )

    counts = Counter(item["category"] for item in entries)
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "git_head": _git_text(root, "rev-parse", "--short", "HEAD", default="UNBORN"),
        "git_branch": _git_text(root, "branch", "--show-current", default=""),
        "read_only": True,
        "content_scanned": False,
        "record_count": len(records),
        "entries_emitted": len(entries),
        "truncated": truncated,
        "category_counts": dict(sorted(counts.items())),
        "entries": entries,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="")
    ap.add_argument("--max-entries", type=int, default=10000)
    args = ap.parse_args()
    manifest = build_manifest(Path(args.root), max_entries=max(1, args.max_entries))
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        print(f"written={out}")
    print(json.dumps({k: manifest[k] for k in ("git_head", "record_count", "truncated", "category_counts")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
