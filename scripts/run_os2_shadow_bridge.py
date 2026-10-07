#!/usr/bin/env python3
"""One bounded local observer assessment. No credentials, service or order path."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import stat
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from research_lab.os2_shadow_bridge import BridgeBlocked, MAX_BYTES, canonical, identity
from research_lab.os2_shadow_journal import ShadowJournal, strict_json

NAMESPACE = REPO / "runtime/os2_shadow_bridge_v1"
FIXTURE_AREA = REPO / ".private/os2_shadow_bridge_v1"


def confined(path, roots, kind):
    value = Path(os.path.abspath(path))
    if not any(value.is_relative_to(root) and value != root for root in roots):
        raise BridgeBlocked("BLOCKED_DATA" if kind == "input" else "BLOCKED_IMPLEMENTATION", kind + "_path_refused")
    for component in (value, *value.parents):
        if component.is_symlink():
            raise BridgeBlocked("BLOCKED_DATA", kind + "_symlink_refused")
    return value


def read_bundle(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise BridgeBlocked("BLOCKED_DATA", "unsafe_input_file")
        if info.st_size > MAX_BYTES: raise BridgeBlocked("BLOCKED_DATA", "input_byte_bound")
        raw = os.read(fd, MAX_BYTES + 1)
        after = os.fstat(fd)
        if len(raw) != info.st_size or (info.st_size, info.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise BridgeBlocked("BLOCKED_DATA", "input_changed_or_oversize")
        value = strict_json(raw)
        if not isinstance(value, dict) or not identity(value.get("request_id")):
            raise BridgeBlocked("BLOCKED_DATA", "invalid_request_identity")
        return value
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--runtime-dir", default=str(NAMESPACE / "store"))
    args = parser.parse_args(argv)
    started = time.monotonic()
    def deadline(*_):
        raise BridgeBlocked("BLOCKED_IMPLEMENTATION", "observer_deadline_30s")
    previous = signal.signal(signal.SIGALRM, deadline)
    signal.setitimer(signal.ITIMER_REAL, 30)
    try:
        path = confined(args.input, (NAMESPACE / "inbox", FIXTURE_AREA), "input")
        root = confined(args.runtime_dir, (NAMESPACE, FIXTURE_AREA), "runtime")
        # Runtime cannot overlap source directories or use a source file as state.
        if root == path or path.is_relative_to(root) or root.is_relative_to(NAMESPACE / "inbox"):
            raise BridgeBlocked("BLOCKED_IMPLEMENTATION", "source_runtime_overlap")
        value = read_bundle(path)
        root.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with ShadowJournal(root) as journal:
            result = journal.process(value)
        if time.monotonic() - started > 30: deadline()
        print(canonical(result).decode())
        return {"SHADOW_WIRING_PASS": 0, "BLOCKED_DATA": 2, "BLOCKED_IMPLEMENTATION": 3}[result["status"]]
    except BridgeBlocked as error:
        print(canonical({"status": error.status, "reason": error.reason, "money_authorized": False}).decode())
        return 2 if error.status == "BLOCKED_DATA" else 3
    except (OSError, ValueError, TypeError, RecursionError):
        print(canonical({"status": "BLOCKED_DATA", "reason": "invalid_or_unavailable_input", "money_authorized": False}).decode())
        return 2
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


if __name__ == "__main__":
    raise SystemExit(main())
