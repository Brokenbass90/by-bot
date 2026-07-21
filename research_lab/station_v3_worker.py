#!/usr/bin/env python3
"""Fail-closed local worker guard for Research Station v3.

This is a pragmatic non-adversarial sandbox: the child receives no credential
environment, cannot open network sockets or subprocesses, cannot read common secret
files, and can mutate files only inside its per-trial work directory.  It is not a
replacement for an OS/container sandbox against intentionally malicious native code.
"""

from __future__ import annotations

import argparse
import builtins
import io
import os
import runpy
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Sequence


class ResearchIsolationError(RuntimeError):
    pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allowed-write-root", required=True)
    parser.add_argument("--runner", required=True)
    parser.add_argument("runner_args", nargs=argparse.REMAINDER)
    return parser


def _install_guards(allowed_write_root: Path) -> None:
    root = allowed_write_root.resolve()

    def resolved(value: Any) -> Path | None:
        if isinstance(value, int):
            return None
        try:
            return Path(value).expanduser().resolve()
        except (TypeError, ValueError):
            return None

    def is_under(path: Path, parent: Path) -> bool:
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False

    def assert_write_path(value: Any) -> None:
        path = resolved(value)
        if path is None:
            raise ResearchIsolationError(f"unverifiable write target is blocked: {value!r}")
        if not is_under(path, root):
            raise ResearchIsolationError(f"write outside per-trial root is blocked: {path}")

    def assert_safe_read(value: Any) -> None:
        path = resolved(value)
        if path is None:
            return
        lowered_parts = {part.lower() for part in path.parts}
        name = path.name.lower()
        if name == ".env" or name.startswith(".env.") or lowered_parts.intersection({".ssh", ".aws", ".gnupg"}):
            raise ResearchIsolationError(f"credential-like file read is blocked: {path}")

    original_open = builtins.open
    original_io_open = io.open
    original_os_open = os.open

    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND

    def reject_dir_fds(kwargs: dict[str, Any]) -> None:
        for key, value in kwargs.items():
            if key.endswith("dir_fd") and value is not None:
                raise ResearchIsolationError(f"{key} path indirection is blocked in Station v3 worker")

    def audit_guard(event: str, args: tuple[Any, ...]) -> None:
        if event == "open" and args:
            path = args[0]
            mode = args[1] if len(args) > 1 else None
            flags = args[2] if len(args) > 2 else 0
            writing = (isinstance(mode, str) and any(flag in mode for flag in ("w", "a", "x", "+"))) or (
                isinstance(flags, int) and bool(flags & write_flags)
            )
            (assert_write_path if writing else assert_safe_read)(path)
        elif event in {
            "os.remove",
            "os.rmdir",
            "os.mkdir",
            "os.chdir",
            "os.chmod",
            "os.chown",
            "os.truncate",
            "os.utime",
        } and args:
            assert_write_path(args[0])
        elif event in {"os.rename", "os.link", "os.symlink"} and len(args) >= 2:
            assert_write_path(args[0])
            assert_write_path(args[1])
        elif event == "sqlite3.connect" and args and args[0] != ":memory:":
            if isinstance(args[0], str) and args[0].startswith("file:"):
                raise ResearchIsolationError("SQLite file: URIs are blocked in Station v3 worker")
            assert_write_path(args[0])
        elif event.startswith("socket."):
            raise ResearchIsolationError(f"{event} is blocked in Station v3 worker")
        elif event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.fork", "os.exec"}:
            raise ResearchIsolationError(f"{event} is blocked in Station v3 worker")

    sys.addaudithook(audit_guard)

    def guarded_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if any(flag in mode for flag in ("w", "a", "x", "+")):
            assert_write_path(file)
        else:
            assert_safe_read(file)
        return original_open(file, mode, *args, **kwargs)

    def guarded_io_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if any(flag in mode for flag in ("w", "a", "x", "+")):
            assert_write_path(file)
        else:
            assert_safe_read(file)
        return original_io_open(file, mode, *args, **kwargs)

    def guarded_os_open(file: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        reject_dir_fds(kwargs)
        if flags & write_flags:
            assert_write_path(file)
        else:
            assert_safe_read(file)
        return original_os_open(file, flags, *args, **kwargs)

    builtins.open = guarded_open
    io.open = guarded_io_open
    os.open = guarded_os_open

    def one_path_mutation(original: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(path: Any, *args: Any, **kwargs: Any) -> Any:
            reject_dir_fds(kwargs)
            assert_write_path(path)
            return original(path, *args, **kwargs)

        return wrapped

    def two_path_mutation(original: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(src: Any, dst: Any, *args: Any, **kwargs: Any) -> Any:
            reject_dir_fds(kwargs)
            assert_write_path(src)
            assert_write_path(dst)
            return original(src, dst, *args, **kwargs)

        return wrapped

    for name in (
        "mkdir",
        "makedirs",
        "remove",
        "unlink",
        "rmdir",
        "removedirs",
        "chmod",
        "chown",
        "lchown",
        "truncate",
        "utime",
        "mkfifo",
        "mknod",
        "chflags",
        "setxattr",
        "removexattr",
    ):
        if hasattr(os, name):
            setattr(os, name, one_path_mutation(getattr(os, name)))
    for name in ("rename", "replace", "link", "symlink"):
        if hasattr(os, name):
            setattr(os, name, two_path_mutation(getattr(os, name)))

    original_chdir = os.chdir

    def guarded_chdir(path: Any) -> None:
        assert_write_path(path)
        original_chdir(path)

    os.chdir = guarded_chdir

    def denied(operation: str) -> Callable[..., Any]:
        def reject(*args: Any, **kwargs: Any) -> Any:
            raise ResearchIsolationError(f"{operation} is blocked in Station v3 worker")

        return reject

    socket.socket = denied("network socket")  # type: ignore[assignment]
    for name in (
        "create_connection",
        "create_server",
        "fromfd",
        "socketpair",
        "getaddrinfo",
        "gethostbyaddr",
        "gethostbyname",
        "gethostbyname_ex",
    ):
        if hasattr(socket, name):
            setattr(socket, name, denied(f"socket.{name}"))
    for name in ("Popen", "run", "call", "check_call", "check_output", "getoutput", "getstatusoutput"):
        if hasattr(subprocess, name):
            setattr(subprocess, name, denied(f"subprocess.{name}"))
    os.system = denied("os.system")
    os.popen = denied("os.popen")
    if hasattr(os, "kill"):
        os.kill = denied("os.kill")
    if hasattr(os, "killpg"):
        os.killpg = denied("os.killpg")
    for name in (
        "fork",
        "forkpty",
        "posix_spawn",
        "posix_spawnp",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "execv",
        "execve",
        "execvp",
        "execvpe",
    ):
        if hasattr(os, name):
            setattr(os, name, denied(f"os.{name}"))
    for name in ("fchmod", "fchown", "ftruncate"):
        if hasattr(os, name):
            setattr(os, name, denied(f"os.{name}"))

    original_sqlite_connect = sqlite3.connect

    def guarded_sqlite_connect(database: Any, *args: Any, **kwargs: Any) -> Any:
        if database != ":memory:":
            if isinstance(database, str) and database.startswith("file:"):
                raise ResearchIsolationError("SQLite file: URIs are blocked in Station v3 worker")
            assert_write_path(database)
        return original_sqlite_connect(database, *args, **kwargs)

    sqlite3.connect = guarded_sqlite_connect


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    runner_args = list(args.runner_args)
    if runner_args and runner_args[0] == "--":
        runner_args = runner_args[1:]
    root = Path(args.allowed_write_root).resolve()
    runner = Path(args.runner).resolve()
    if not root.is_dir() or not runner.is_file():
        raise ResearchIsolationError("worker root/runner is missing")
    _install_guards(root)
    sys.argv = [str(runner), *runner_args]
    runpy.run_path(str(runner), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
