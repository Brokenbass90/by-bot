#!/usr/bin/env python3
"""Build an explicit, reproducible targeted-release manifest.

This tool has deliberately narrow authority.  It reads only the files named by
repeated ``--file`` arguments, reads a boolean Git dirty state, and atomically
writes one JSON manifest below the repository root.  It never deploys, copies,
cleans, deletes, restarts, or changes trading/runtime configuration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
import subprocess
from pathlib import Path, PureWindowsPath
from typing import Any, Sequence


SCHEMA_VERSION = 1
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
_DIR_FLAGS = _READ_FLAGS | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_FILE_FLAGS = _READ_FLAGS | getattr(os, "O_NOFOLLOW", 0)


class ManifestError(ValueError):
    """A fail-closed validation or filesystem error."""


def _clean_label(value: str, *, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ManifestError(f"{name} must not be empty")
    if any(ord(ch) < 32 for ch in text):
        raise ManifestError(f"{name} must not contain control characters")
    return text


def _relative_parts(raw_path: str, *, name: str) -> tuple[str, ...]:
    """Return strict repo-relative path components without normalizing danger."""
    raw = str(raw_path or "")
    if not raw:
        raise ManifestError(f"{name} must not be empty")
    if "\x00" in raw:
        raise ManifestError(f"{name} contains a NUL byte")
    if "\\" in raw:
        raise ManifestError(f"{name} must use '/' separators")
    if Path(raw).is_absolute() or PureWindowsPath(raw).is_absolute() or raw.startswith("/"):
        raise ManifestError(f"{name} must be repo-relative, not absolute: {raw!r}")

    parts = tuple(raw.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise ManifestError(f"{name} contains empty, dot, or traversal components: {raw!r}")
    if ".git" in parts:
        raise ManifestError(f"{name} must not address repository metadata: {raw!r}")
    return parts


def _repo_root(path: Path | str) -> Path:
    raw = Path(path).expanduser()
    if raw.is_symlink():
        raise ManifestError("repo root must not itself be a symlink")
    try:
        root = raw.resolve(strict=True)
    except OSError as exc:
        raise ManifestError(f"repo root does not exist: {raw}") from exc
    if not root.is_dir():
        raise ManifestError(f"repo root is not a directory: {root}")
    return root


def _open_dir_chain(root: Path, parts: Sequence[str], *, create: bool) -> int:
    """Open a directory below root without following any child symlink."""
    try:
        current_fd = os.open(root, _DIR_FLAGS)
    except OSError as exc:
        raise ManifestError(f"cannot securely open repo root: {root}") from exc

    try:
        for part in parts:
            if create:
                try:
                    os.mkdir(part, mode=0o755, dir_fd=current_fd)
                except FileExistsError:
                    pass
                except OSError as exc:
                    raise ManifestError(f"cannot create output directory component: {part!r}") from exc
            try:
                next_fd = os.open(part, _DIR_FLAGS, dir_fd=current_fd)
            except OSError as exc:
                raise ManifestError(
                    f"directory component is missing, not a directory, or a symlink: {part!r}"
                ) from exc
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except Exception:
        os.close(current_fd)
        raise


def _hash_explicit_file(root: Path, parts: Sequence[str]) -> dict[str, Any]:
    parent_fd = _open_dir_chain(root, parts[:-1], create=False)
    file_fd = -1
    try:
        try:
            file_fd = os.open(parts[-1], _FILE_FLAGS, dir_fd=parent_fd)
        except OSError as exc:
            raise ManifestError(
                f"explicit file is missing, inaccessible, or a symlink: {'/'.join(parts)!r}"
            ) from exc

        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode):
            raise ManifestError(f"explicit path is not a regular file: {'/'.join(parts)!r}")

        digest = hashlib.sha256()
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)

        after = os.fstat(file_fd)
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or stat.S_IMODE(before.st_mode) != stat.S_IMODE(after.st_mode)
        ):
            raise ManifestError(f"explicit file changed while it was hashed: {'/'.join(parts)!r}")

        return {
            "path": "/".join(parts),
            "sha256": digest.hexdigest(),
            "size_bytes": int(after.st_size),
            "mode": f"{stat.S_IMODE(after.st_mode):04o}",
        }
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        os.close(parent_fd)


def _status_paths(root: Path) -> list[tuple[str, str]]:
    proc = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise ManifestError(f"cannot read Git dirty state: {detail or 'git status failed'}")

    fields = proc.stdout.split(b"\0")
    records: list[tuple[str, str]] = []
    index = 0
    while index < len(fields):
        field = fields[index]
        if not field:
            index += 1
            continue
        row = field.decode("utf-8", errors="surrogateescape")
        status_code = row[:2]
        path = row[3:] if len(row) >= 4 else ""
        records.append((status_code, path))
        # Porcelain v1 -z emits a second path for rename/copy records.  A rename
        # is always dirty, so the old path need not be retained.
        index += 2 if any(code in status_code for code in "RC") else 1
    return records


def _git_dirty(root: Path, *, ignored_output: str) -> bool:
    """Return only a boolean; never serialize unlisted dirty path names."""
    for status_code, path in _status_paths(root):
        if status_code == "??" and path == ignored_output:
            # The generated manifest must not make a clean repo non-reproducible
            # merely because the same output file now exists as an artifact.
            continue
        return True
    return False


def _atomic_write_json(root: Path, output_parts: Sequence[str], payload: bytes) -> None:
    parent_fd = _open_dir_chain(root, output_parts[:-1], create=True)
    leaf = output_parts[-1]
    temp_name = ""
    temp_fd = -1
    try:
        try:
            current = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        except OSError as exc:
            raise ManifestError(f"cannot inspect output path: {'/'.join(output_parts)!r}") from exc
        if current is not None and not stat.S_ISREG(current.st_mode):
            raise ManifestError(
                f"output path exists but is not a regular file: {'/'.join(output_parts)!r}"
            )

        for _ in range(20):
            candidate = f".{leaf}.tmp.{os.getpid()}.{secrets.token_hex(6)}"
            try:
                temp_fd = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                    dir_fd=parent_fd,
                )
                temp_name = candidate
                break
            except FileExistsError:
                continue
        if temp_fd < 0:
            raise ManifestError("could not allocate an atomic output temp file")

        view = memoryview(payload)
        while view:
            written = os.write(temp_fd, view)
            view = view[written:]
        os.fchmod(temp_fd, 0o644)
        os.fsync(temp_fd)
        os.close(temp_fd)
        temp_fd = -1

        os.replace(temp_name, leaf, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temp_name = ""
        os.fsync(parent_fd)
    except ManifestError:
        raise
    except OSError as exc:
        raise ManifestError(f"atomic manifest write failed: {'/'.join(output_parts)!r}") from exc
    finally:
        if temp_fd >= 0:
            os.close(temp_fd)
        if temp_name:
            try:
                os.unlink(temp_name, dir_fd=parent_fd)
            except OSError:
                pass
        os.close(parent_fd)


def build_targeted_release_manifest(
    repo_root: Path | str,
    *,
    output_path: str,
    release_id: str,
    git_head: str,
    file_paths: Sequence[str],
) -> dict[str, Any]:
    """Validate, hash, and atomically write one explicit release manifest."""
    root = _repo_root(repo_root)
    release = _clean_label(release_id, name="release id")
    head = _clean_label(git_head, name="git head")
    output_parts = _relative_parts(output_path, name="output path")
    output_rel = "/".join(output_parts)
    if Path(output_rel).suffix.lower() != ".json":
        raise ManifestError("output path must end in .json")
    if not file_paths:
        raise ManifestError("at least one explicit --file path is required")

    normalized: list[tuple[str, ...]] = []
    seen: set[str] = set()
    for raw in file_paths:
        parts = _relative_parts(raw, name="file path")
        rel = "/".join(parts)
        if rel == output_rel:
            raise ManifestError("output path cannot also be an explicit input file")
        if rel in seen:
            raise ManifestError(f"duplicate explicit file path: {rel!r}")
        seen.add(rel)
        normalized.append(parts)

    files = [_hash_explicit_file(root, parts) for parts in sorted(normalized)]
    dirty = _git_dirty(root, ignored_output=output_rel)
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "release_id": release,
        "git_head": head,
        "metadata": {
            "git_dirty": dirty,
            "explicit_files_only": True,
            "file_count": len(files),
            "reproducible": True,
            "operations": ["read_explicit_files", "read_git_dirty_flag", "write_manifest"],
        },
        "files": files,
    }
    payload = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    _atomic_write_json(root, output_parts, payload)
    return manifest


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", "--root", dest="repo_root", required=True,
        help="repository root; may be absolute",
    )
    parser.add_argument(
        "--output", "--out", dest="output", required=True,
        help="repo-relative JSON output path",
    )
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--git-head", required=True)
    parser.add_argument(
        "--file",
        dest="file_paths",
        action="append",
        required=True,
        help="explicit repo-relative regular file; repeat for every release file",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        manifest = build_targeted_release_manifest(
            args.repo_root,
            output_path=args.output,
            release_id=args.release_id,
            git_head=args.git_head,
            file_paths=args.file_paths,
        )
    except ManifestError as exc:
        raise SystemExit(f"targeted release manifest refused: {exc}") from exc

    print(
        json.dumps(
            {
                "release_id": manifest["release_id"],
                "git_head": manifest["git_head"],
                "git_dirty": manifest["metadata"]["git_dirty"],
                "file_count": manifest["metadata"]["file_count"],
                "output": args.output,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
