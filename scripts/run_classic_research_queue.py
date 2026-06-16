#!/usr/bin/env python3
"""Sequential classic-strategy autoresearch queue with reports.

The queue is intentionally boring: one spec after another, bounded parallelism
inside each spec, and a monthly/stack report after every completed sweep.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.classic_research_report import _md, build_report


DEFAULT_SPECS = [
    "configs/autoresearch/range_scalp_v1_annual_focus_v2.json",
    "configs/autoresearch/package_elder_modes_exact_probe_v1.json",
    "configs/autoresearch/package_sc1_modes_exact_probe_v1.json",
    "configs/autoresearch/package_asb1_slope_break_v1.json",
    "configs/autoresearch/pump_fade_v5_bear_window_v1.json",
    "configs/autoresearch/breakdown_v1_current90_focus_v1.json",
    "configs/autoresearch/inplay_first_touch_bounce_v1.json",
]


def _slug(text: str) -> str:
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in {"-", "_"}:
            out.append(ch)
        else:
            out.append("_")
    return "".join(out).strip("_")


def _load_name(spec_path: Path) -> str:
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    return _slug(str(payload.get("name") or spec_path.stem))


def _repo_python() -> str:
    venv = ROOT / ".venv" / "bin" / "python"
    return str(venv if venv.exists() else sys.executable)


def _latest_autoresearch_dir(name: str) -> Path | None:
    dirs = sorted(
        (ROOT / "backtest_runs").glob(f"autoresearch_*_{name}"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return dirs[0] if dirs else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Run classic crypto research queue")
    ap.add_argument("--spec", action="append", default=[], help="Spec path. Repeatable.")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0, help="Debug cap passed to each spec.")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--max-concurrent", type=int, default=3)
    ap.add_argument("--bear-months", default="2025-10,2025-11,2025-12,2026-01,2026-02,2026-03,2026-04")
    args = ap.parse_args()

    specs = args.spec or DEFAULT_SPECS
    bear_months = {x.strip() for x in args.bear_months.split(",") if x.strip()}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    queue_report = ROOT / "reports" / f"CLASSIC_RESEARCH_QUEUE_{stamp}.md"
    queue_report.parent.mkdir(parents=True, exist_ok=True)
    queue_lines = [
        "# Classic Research Queue",
        "",
        f"- generated_at_utc: `{datetime.now(timezone.utc).isoformat()}`",
        f"- jobs: `{args.jobs}`",
        f"- specs: `{len(specs)}`",
        "",
    ]

    for raw_spec in specs:
        spec_path = Path(raw_spec)
        if not spec_path.is_absolute():
            spec_path = ROOT / spec_path
        name = _load_name(spec_path)
        print(f"=== RUN {name} spec={spec_path} ===", flush=True)

        cmd = [
            _repo_python(),
            "scripts/run_strategy_autoresearch.py",
            "--spec",
            str(spec_path),
            "--jobs",
            str(max(1, args.jobs)),
        ]
        if args.limit:
            cmd.extend(["--limit", str(args.limit)])
        rc = subprocess.run(cmd, cwd=ROOT).returncode

        latest = _latest_autoresearch_dir(name)
        queue_lines.append(f"## {name}")
        queue_lines.append("")
        queue_lines.append(f"- spec: `{spec_path}`")
        queue_lines.append(f"- autoresearch_rc: `{rc}`")
        queue_lines.append(f"- latest_dir: `{latest or '-'}`")

        if latest is not None and (latest / "ranked_results.csv").exists():
            report = build_report(
                latest,
                top=args.top,
                max_concurrent=args.max_concurrent,
                bear_months=bear_months,
            )
            out_json = ROOT / "reports" / f"CLASSIC_RESEARCH_{name}_{stamp}.json"
            out_md = ROOT / "reports" / f"CLASSIC_RESEARCH_{name}_{stamp}.md"
            out_json.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
            out_md.write_text(_md(report), encoding="utf-8")
            queue_lines.append(f"- report_md: `{out_md}`")
            queue_lines.append(f"- candidates: `{len(report['candidates'])}`")
            if report["candidates"]:
                c = report["candidates"][0]
                summary = c["summary"]
                mv = c["monthly_verdict"]
                queue_lines.append(
                    "- top: "
                    f"`{summary.get('tag')}` net `{summary.get('net_pnl')}` "
                    f"PF `{summary.get('profit_factor')}` monthly `{mv['verdict']}`"
                )
        queue_lines.append("")
        queue_report.write_text("\n".join(queue_lines).rstrip() + "\n", encoding="utf-8")

    print(f"queue_report={queue_report}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
