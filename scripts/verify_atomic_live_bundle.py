#!/usr/bin/env python3
"""Verify an extracted atomic live bundle against its non-secret manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


def verify_bundle(*, root: Path, manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_id") != "atomic_live_dependency_bundle_v1":
        raise ValueError("unsupported bundle manifest")

    verified = []
    for row in manifest.get("files") or []:
        raw = str(row.get("path") or "")
        relative = PurePosixPath(raw)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError(f"unsafe manifest path: {raw!r}")
        path = root.joinpath(*relative.parts)
        data = path.read_bytes()
        actual_sha = hashlib.sha256(data).hexdigest()
        if actual_sha != row.get("sha256"):
            raise ValueError(f"sha256 mismatch: {raw}")
        if len(data) != int(row.get("size_bytes") or -1):
            raise ValueError(f"size mismatch: {raw}")
        verified.append(raw)

    if len(verified) != len(manifest.get("files") or []):
        raise ValueError("manifest verification count mismatch")
    return {
        "schema_id": "atomic_live_dependency_bundle_verification_v1",
        "revision": manifest.get("revision"),
        "verified_files": verified,
        "verified_count": len(verified),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_bundle(root=args.root, manifest_path=args.manifest), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
