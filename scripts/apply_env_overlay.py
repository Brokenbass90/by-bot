#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path


def _read_overlay(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply env overlay file while preserving unrelated keys/comments.")
    ap.add_argument("--target", required=True, help="Target .env-like file")
    ap.add_argument("--overlay", required=True, help="Overlay env file")
    ap.add_argument("--backup-dir", default="state/env_backups")
    args = ap.parse_args()

    target = Path(args.target).resolve()
    overlay = Path(args.overlay).resolve()
    if not target.exists():
        raise SystemExit(f"target not found: {target}")
    if not overlay.exists():
        raise SystemExit(f"overlay not found: {overlay}")

    target_lines = target.read_text(encoding="utf-8").splitlines()
    overlay_map = _read_overlay(overlay)
    if not overlay_map:
        raise SystemExit(f"overlay has no key=value entries: {overlay}")

    backup_dir = Path(args.backup_dir).resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{target.name}.{stamp}.bak"
    backup_path.write_text("\n".join(target_lines) + "\n", encoding="utf-8")

    touched: set[str] = set()
    out_lines: list[str] = []
    for raw in target_lines:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in raw:
            key = raw.split("=", 1)[0].strip()
            if key in overlay_map:
                out_lines.append(f"{key}={overlay_map[key]}")
                touched.add(key)
                continue
        out_lines.append(raw)

    missing = [k for k in overlay_map.keys() if k not in touched]
    if missing:
        if out_lines and out_lines[-1].strip():
            out_lines.append("")
        out_lines.append(f"# overlay from {overlay.name}")
        for key in missing:
            out_lines.append(f"{key}={overlay_map[key]}")

    target.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"backup={backup_path}")
    print(f"target={target}")
    print(f"overlay={overlay}")
    print(f"updated_keys={','.join(overlay_map.keys())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
