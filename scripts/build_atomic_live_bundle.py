#!/usr/bin/env python3
"""Build a deterministic, non-secret live patch bundle from a Git revision.

The builder deliberately reads committed blobs with ``git show`` instead of the
working tree. This prevents unrelated Claude/Codex/user edits from leaking into
a targeted live deployment.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path, PurePosixPath
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ANCESTOR = "f290463"
DEFAULT_PATHS = (
    "smart_pump_reversal_bot.py",
    "bot/maker_execution.py",
    "bot/att1_challenger.py",
    "bot/health_truth.py",
    "bot/portfolio_equity_guard.py",
    "bot/strategy_regime_gate.py",
    "bot/strategy_shadow_ledger.py",
)


def _git(*args: str, cwd: Path = ROOT) -> bytes:
    return subprocess.check_output(["git", *args], cwd=cwd)


def _safe_repo_path(raw: str) -> str:
    path = PurePosixPath(str(raw))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"unsafe bundle path: {raw!r}")
    return path.as_posix()


def _normalized_tar_info(name: str, size: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=name)
    info.size = int(size)
    info.mode = 0o644
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    return info


def build_bundle(
    *,
    repo: Path,
    revision: str,
    output_dir: Path,
    paths: Iterable[str] = DEFAULT_PATHS,
) -> tuple[Path, Path, dict]:
    resolved_revision = _git("rev-parse", f"{revision}^{{commit}}", cwd=repo).decode().strip()
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", REQUIRED_ANCESTOR, resolved_revision],
        cwd=repo,
        check=True,
    )

    safe_paths = tuple(_safe_repo_path(path) for path in paths)
    if len(set(safe_paths)) != len(safe_paths):
        raise ValueError("duplicate paths in bundle")

    blobs: dict[str, bytes] = {}
    rows: list[dict] = []
    for path in safe_paths:
        data = _git("show", f"{resolved_revision}:{path}", cwd=repo)
        blobs[path] = data
        rows.append(
            {
                "path": path,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
        )

    manifest = {
        "schema_id": "atomic_live_dependency_bundle_v1",
        "revision": resolved_revision,
        "required_ancestor": REQUIRED_ANCESTOR,
        "files": rows,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()

    output_dir.mkdir(parents=True, exist_ok=False)
    short = resolved_revision[:12]
    archive_path = output_dir / f"live_bundle_{short}.tar"
    manifest_path = output_dir / f"live_bundle_{short}.manifest.json"

    with tarfile.open(archive_path, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(blobs):
            data = blobs[path]
            archive.addfile(_normalized_tar_info(path, len(data)), io.BytesIO(data))
        archive.addfile(
            _normalized_tar_info("bundle_manifest.json", len(manifest_bytes)),
            io.BytesIO(manifest_bytes),
        )

    manifest_path.write_bytes(manifest_bytes)
    return archive_path, manifest_path, manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    archive, manifest, payload = build_bundle(
        repo=ROOT,
        revision=args.revision,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "archive": str(archive),
                "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "manifest": str(manifest),
                "revision": payload["revision"],
                "file_count": len(payload["files"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
