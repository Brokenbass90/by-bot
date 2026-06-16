#!/usr/bin/env python3
"""Refresh the generated snapshot block in PROJECT_MAP.md.

The project map should remain a human-readable architecture document, but its
"current state" should not rot. This script updates one bounded block with
facts that can be safely derived from the local repository and latest reports.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

START = "<!-- AUTO_SNAPSHOT_START -->"
END = "<!-- AUTO_SNAPSHOT_END -->"


def _count_files(root: Path, pattern: str) -> int:
    return sum(1 for p in root.glob(pattern) if p.is_file())


def _git_short_sha(root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:
        return "unknown"


def _latest_report(root: Path, pattern: str) -> Optional[Path]:
    reports = sorted((root / "reports").glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return reports[0] if reports else None


def _gate_verdict(path: Path) -> str:
    if not path.exists():
        return "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"unreadable:{exc}"
    status = "GO" if data.get("go") else "NO-GO"
    net = data.get("net_usd")
    ann = data.get("annual_pct")
    return f"{status}, net=${net}, annual={ann}%"


def build_snapshot(root: Path, *, now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    ai_tools = root / "bot" / "ai_tools.py"
    ai_has_project_map = ai_tools.exists() and "get_project_map" in ai_tools.read_text(encoding="utf-8", errors="ignore")
    collector_exists = (root / "scripts" / "collect_bybit_liquidations.py").exists()
    morning = _latest_report(root, "CODEX_MORNING_PROGRESS_*.md")
    funding_gate = root / "reports" / "FUNDING_CARRY_GATE_180D_HEDGEABLE_latest.json"

    lines = [
        START,
        "## Авто-снимок",
        f"- generated_utc: `{now.strftime('%Y-%m-%dT%H:%M:%SZ')}`",
        f"- git_head: `{_git_short_sha(root)}`",
        f"- tests: `{_count_files(root, 'tests/test_*.py')}` test files",
        f"- strategies: `{_count_files(root, 'strategies/*.py')}` strategy modules",
        f"- backtest modules: `{_count_files(root, 'backtest/*.py')}`",
        f"- onboard AI project-map tool: `{'yes' if ai_has_project_map else 'no'}`",
        f"- liquidation collector: `{'yes' if collector_exists else 'no'}`",
        f"- funding carry 180d hedgeable gate: `{_gate_verdict(funding_gate)}`",
        f"- latest progress note: `{morning.name if morning else 'missing'}`",
        END,
    ]
    return "\n".join(lines)


def update_text(text: str, snapshot: str) -> str:
    if START in text and END in text:
        before = text.split(START, 1)[0].rstrip()
        after = text.split(END, 1)[1].lstrip()
        return f"{before}\n\n{snapshot}\n\n{after}"
    marker = "## Ключевые документы"
    if marker in text:
        before, after = text.split(marker, 1)
        return f"{before.rstrip()}\n\n{snapshot}\n\n{marker}{after}"
    return f"{text.rstrip()}\n\n{snapshot}\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Update PROJECT_MAP.md generated snapshot block")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--check", action="store_true", help="Exit non-zero if PROJECT_MAP.md is stale")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    path = root / "PROJECT_MAP.md"
    old = path.read_text(encoding="utf-8")
    new = update_text(old, build_snapshot(root))
    if args.check:
        if old != new:
            print("PROJECT_MAP.md auto snapshot is stale")
            return 1
        return 0
    path.write_text(new, encoding="utf-8")
    print(f"updated {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
