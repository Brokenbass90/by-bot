#!/usr/bin/env python3
"""Apply a verified live bundle while the service is stopped, with rollback."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

try:
    from scripts.verify_atomic_live_bundle import verify_bundle
except ImportError:  # Direct execution from a staged bundle tools directory.
    from verify_atomic_live_bundle import verify_bundle


def _paths(manifest: dict) -> list[PurePosixPath]:
    paths = []
    for row in manifest.get("files") or []:
        path = PurePosixPath(str(row.get("path") or ""))
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError(f"unsafe manifest path: {path}")
        paths.append(path)
    if not paths or len(set(paths)) != len(paths):
        raise ValueError("empty or duplicate bundle paths")
    return paths


def backup_live_files(*, live_root: Path, backup_root: Path, paths: list[PurePosixPath]) -> list[str]:
    absent = []
    for relative in paths:
        source = live_root.joinpath(*relative.parts)
        if not source.exists():
            absent.append(relative.as_posix())
            continue
        target = backup_root.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return absent


def apply_files(*, live_root: Path, stage_root: Path, paths: list[PurePosixPath], token: str) -> None:
    prepared = []
    for relative in paths:
        source = stage_root.joinpath(*relative.parts)
        target = live_root.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        pending = target.with_name(f".{target.name}.codex-new-{token}")
        shutil.copy2(source, pending)
        prepared.append((pending, target))

    # The service is stopped, so it can observe only the complete old set before
    # this function or the complete verified new set after it.
    for pending, target in prepared:
        os.replace(pending, target)


def rollback_files(
    *,
    live_root: Path,
    backup_root: Path,
    paths: list[PurePosixPath],
    originally_absent: set[str],
) -> None:
    for relative in paths:
        target = live_root.joinpath(*relative.parts)
        if relative.as_posix() in originally_absent:
            if target.exists():
                target.unlink()
            continue
        source = backup_root.joinpath(*relative.parts)
        pending = target.with_name(f".{target.name}.codex-rollback")
        shutil.copy2(source, pending)
        os.replace(pending, target)


def _service_active(service: str) -> bool:
    result = subprocess.run(
        ["systemctl", "is-active", "--quiet", service],
        check=False,
    )
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-root", type=Path, required=True)
    parser.add_argument("--stage-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--service", default="bybot.service")
    parser.add_argument("--receipt-dir", type=Path)
    args = parser.parse_args()

    live_root = args.live_root.resolve()
    stage_root = args.stage_root.resolve()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    paths = _paths(manifest)
    revision = str(manifest.get("revision") or "unknown")
    token = revision[:12]

    if _service_active(args.service):
        raise SystemExit(f"refusing to apply while {args.service} is active")
    verify_bundle(root=stage_root, manifest_path=args.manifest)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = live_root / "backups" / f"atomic_live_{token}_{stamp}"
    backup_root.mkdir(parents=True, exist_ok=False)
    absent = backup_live_files(live_root=live_root, backup_root=backup_root, paths=paths)
    (backup_root / "originally_absent.json").write_text(
        json.dumps(absent, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    status = "UNKNOWN"
    error = ""
    try:
        apply_files(live_root=live_root, stage_root=stage_root, paths=paths, token=token)
        verify_bundle(root=live_root, manifest_path=args.manifest)
        subprocess.run(["systemctl", "start", args.service], check=True)
        time.sleep(5)
        if not _service_active(args.service):
            raise RuntimeError(f"{args.service} did not become active")
        status = "DEPLOYED"
    except Exception as exc:
        error = repr(exc)
        subprocess.run(["systemctl", "stop", args.service], check=False)
        rollback_files(
            live_root=live_root,
            backup_root=backup_root,
            paths=paths,
            originally_absent=set(absent),
        )
        subprocess.run(["systemctl", "start", args.service], check=True)
        time.sleep(5)
        status = "ROLLED_BACK"

    receipt_dir = (args.receipt_dir or (live_root / "runtime" / "deploy_receipts")).resolve()
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema_id": "atomic_live_bundle_deploy_receipt_v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "revision": revision,
        "service": args.service,
        "status": status,
        "backup": str(backup_root),
        "originally_absent": absent,
        "files": [path.as_posix() for path in paths],
        "error": error,
    }
    receipt_path = receipt_dir / f"atomic_live_{token}_{stamp}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({**receipt, "receipt": str(receipt_path)}, sort_keys=True))
    return 0 if status == "DEPLOYED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
