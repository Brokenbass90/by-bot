#!/usr/bin/env python3
"""Fail-closed health check for the local project audit pipeline.

This does not inspect trading performance and cannot mutate live state.  It
answers a narrower question: did the auditor complete, are its artifacts
internally consistent, and does its own deterministic scanner still catch a
known seeded defect?
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
import time
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab.static_defect_scan import scan_file

OUT_DIR = ROOT / "runtime" / "project_audit"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _parse_iso(value: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        # A sandbox may forbid signalling a live sibling process.  EPERM is
        # evidence that the PID exists, not evidence that it is dead.
        return True
    except (ProcessLookupError, OSError):
        return False


def _scanner_canary() -> tuple[bool, str]:
    source = """
def broken(tf_ts, window, tf_seconds):
    return tf_ts + window * tf_seconds
"""
    with tempfile.TemporaryDirectory(prefix="audit_canary_") as tmp:
        path = Path(tmp) / "seeded_ms_seconds_bug.py"
        path.write_text(source, encoding="utf-8")
        hits = scan_file(path)
    codes = [code for _, code, _ in hits]
    return ("E1" in codes, f"expected=E1 observed={codes}")


def build_health(root: Path = ROOT, *, now_epoch: float | None = None) -> dict[str, Any]:
    now = float(time.time() if now_epoch is None else now_epoch)
    audit_dir = root / "runtime" / "project_audit"
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, severity: str = "high") -> None:
        checks.append({"name": name, "ok": bool(ok), "severity": severity, "detail": detail})

    status = _read_json(audit_dir / "supervisor_status.json")
    last_success = _parse_iso(status.get("last_success_utc"))
    age_hours = None if last_success is None else max(0.0, (now - last_success) / 3600.0)
    add(
        "supervisor_fresh",
        age_hours is not None and age_hours <= 7.0,
        "missing" if age_hours is None else f"age_hours={age_hours:.2f}",
    )

    lock_pid_path = audit_dir / "run.lock" / "pid"
    if lock_pid_path.exists():
        try:
            lock_pid = int(lock_pid_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            lock_pid = 0
        add("audit_lock_owner_alive", _pid_alive(lock_pid), f"pid={lock_pid}")
    else:
        add("audit_lock_clear", True, "no lock", severity="info")

    registry = _read_json(audit_dir / "registry.json")
    findings = list(registry.get("findings") or []) if registry else []
    summary = registry.get("summary") if isinstance(registry.get("summary"), dict) else {}
    add("registry_json_valid", bool(registry), f"findings={len(findings)}")
    add(
        "registry_total_consistent",
        int(summary.get("total") or -1) == len(findings),
        f"summary_total={summary.get('total')} rows={len(findings)}",
    )

    csv_path = audit_dir / "registry.csv"
    try:
        with csv_path.open(encoding="utf-8", newline="") as handle:
            csv_rows = sum(1 for _ in csv.DictReader(handle))
    except OSError:
        csv_rows = -1
    add("registry_csv_consistent", csv_rows == len(findings), f"csv_rows={csv_rows} json_rows={len(findings)}")
    markdown_path = audit_dir / "registry.md"
    add(
        "registry_markdown_present",
        markdown_path.exists() and markdown_path.stat().st_size > 0,
        "registry.md",
        severity="medium",
    )

    live_path = root / "runtime" / "liveness_table.txt"
    try:
        live_text = live_path.read_text(encoding="utf-8")
    except OSError:
        live_text = ""
    add(
        "liveness_complete",
        "LIVENESS_SWEEP_COMPLETE " in live_text,
        "completion marker present" if "LIVENESS_SWEEP_COMPLETE " in live_text else "partial or missing table",
    )

    canary_ok, canary_detail = _scanner_canary()
    add("static_scanner_seeded_canary", canary_ok, canary_detail)

    ai_dir = root / "runtime" / "ai_audit"
    ai_files = sorted(ai_dir.glob("*.md"))
    ai_age_hours = None
    if ai_files:
        ai_age_hours = max(0.0, (now - ai_files[-1].stat().st_mtime) / 3600.0)
    add(
        "ai_audit_artifact_fresh",
        ai_age_hours is not None and ai_age_hours <= 7.0,
        "missing" if ai_age_hours is None else f"age_hours={ai_age_hours:.2f}",
        severity="medium",
    )

    negative_path = root / "runtime" / "strategy_diagnostics" / "registry.json"
    negative = _read_json(negative_path)
    negative_generated = _parse_iso(negative.get("generated_at_utc"))
    negative_age_hours = None if negative_generated is None else max(0.0, (now - negative_generated) / 3600.0)
    add(
        "negative_evidence_registry_fresh",
        negative_age_hours is not None and negative_age_hours <= 7.0,
        "missing" if negative_age_hours is None else f"age_hours={negative_age_hours:.2f}",
        severity="high",
    )

    failed = [row for row in checks if not row["ok"] and row["severity"] in {"high", "critical"}]
    return {
        "schema_id": "project_audit_health_v1",
        "generated_at_utc": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds"),
        "healthy": not failed,
        "proposal_only": True,
        "live_mutation": False,
        "checks": checks,
        "failed_high_count": len(failed),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Project audit health",
        "",
        f"Generated: `{payload['generated_at_utc']}`",
        f"Health: **{'HEALTHY' if payload['healthy'] else 'DEGRADED'}**",
        "",
        "| Check | Result | Severity | Detail |",
        "|---|---|---|---|",
    ]
    for row in payload["checks"]:
        detail = str(row["detail"]).replace("|", "/")
        lines.append(f"| {row['name']} | {'PASS' if row['ok'] else 'FAIL'} | {row['severity']} | {detail} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    payload = build_health()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "health.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "health.md").write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps({"healthy": payload["healthy"], "failed_high_count": payload["failed_high_count"]}))
    return 0 if payload["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
