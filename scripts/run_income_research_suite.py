#!/usr/bin/env python3
"""Run the next income-focused crypto research suite sequentially.

The suite waits for already-running heavy research jobs, then runs bounded
autoresearch sweeps and writes monthly/stack reports after each sweep.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


SUITE = [
    {
        "name": "ivb1_impulse_retrace_v2_relaxed_mirror",
        "label": "impulse breakout with pullback v2 / mirrored",
        "spec": "configs/autoresearch/ivb1_impulse_retrace_v2_relaxed_mirror.json",
        "limit": 1536,
    },
    {
        "name": "inplay_breakout_retest_htf_runner_v2",
        "label": "breakout-retest HTF runner v2",
        "spec": "configs/autoresearch/inplay_breakout_retest_htf_runner_v2.json",
        "limit": 1152,
    },
    {
        "name": "range_scalp_v1_annual_repair_v3",
        "label": "range boundary scalp repair v3",
        "spec": "configs/autoresearch/range_scalp_v1_annual_repair_v3.json",
        "limit": 2000,
    },
    {
        "name": "vwap_mean_reversion_v1_annual_repair_v2",
        "label": "VWAP mean reversion repair v2",
        "spec": "configs/autoresearch/vwap_mean_reversion_v1_annual_repair_v2.json",
        "limit": 120,
    },
]


ACTIVE_PATTERNS = [
    "ivb1_live_canary_annual_focus_v1",
    "range_scalp_v1_annual_focus_v2",
    "run_classic_research_queue.py",
]


def _repo_python() -> str:
    for name in ("python", "python3"):
        p = ROOT / ".venv" / "bin" / name
        if p.exists():
            return str(p)
    return sys.executable


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


def _latest_autoresearch_dir(name: str) -> Path | None:
    dirs = sorted(
        (ROOT / "backtest_runs").glob(f"autoresearch_*_{name}"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return dirs[0] if dirs else None


def _pattern_running(pattern: str) -> bool:
    rc = subprocess.run(["pgrep", "-f", pattern], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    return rc == 0


def _wait_for_existing(poll_sec: int) -> None:
    while True:
        active = [p for p in ACTIVE_PATTERNS if _pattern_running(p)]
        if not active:
            return
        print(f"waiting_for_existing={','.join(active)} poll_sec={poll_sec}", flush=True)
        time.sleep(max(30, int(poll_sec)))


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> int:
    print("cmd=" + " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT, env=env).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="Run income-focused research suite")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--poll-sec", type=int, default=600)
    ap.add_argument("--skip-wait", action="store_true")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--max-concurrent", type=int, default=3)
    ap.add_argument("--bear-months", default="2025-10,2025-11,2025-12,2026-01,2026-02,2026-03,2026-04")
    ap.add_argument("--skip-pair-arb", action="store_true")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    master = ROOT / "reports" / f"INCOME_RESEARCH_SUITE_{stamp}.md"
    master.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Income Research Suite",
        "",
        f"- generated_at_utc: `{datetime.now(timezone.utc).isoformat()}`",
        f"- jobs: `{args.jobs}`",
        "",
    ]
    master.write_text("\n".join(lines), encoding="utf-8")

    if not args.skip_wait:
        _wait_for_existing(args.poll_sec)

    py = _repo_python()
    for item in SUITE:
        spec_path = ROOT / item["spec"]
        name = _load_name(spec_path)
        limit = int(item["limit"])
        lines.extend([f"## {item['label']}", "", f"- spec: `{spec_path}`", f"- limit: `{limit}`"])
        master.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

        rc = _run([
            py,
            "scripts/run_strategy_autoresearch.py",
            "--spec",
            str(spec_path),
            "--jobs",
            str(max(1, int(args.jobs))),
            "--limit",
            str(limit),
        ])
        latest = _latest_autoresearch_dir(name)
        lines.append(f"- autoresearch_rc: `{rc}`")
        lines.append(f"- latest_dir: `{latest or '-'}`")

        if latest is not None:
            out_md = ROOT / "reports" / f"INCOME_RESEARCH_{name}_{stamp}.md"
            out_json = ROOT / "reports" / f"INCOME_RESEARCH_{name}_{stamp}.json"
            report_rc = _run([
                py,
                "scripts/classic_research_report.py",
                str(latest),
                "--top",
                str(max(1, int(args.top))),
                "--max-concurrent",
                str(max(0, int(args.max_concurrent))),
                "--bear-months",
                str(args.bear_months),
                "--out-md",
                str(out_md),
                "--out-json",
                str(out_json),
            ])
            lines.append(f"- report_rc: `{report_rc}`")
            lines.append(f"- report_md: `{out_md}`")
        lines.append("")
        master.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    if not args.skip_pair_arb:
        lines.extend(["## pair stat-arb matrix", ""])
        pair_rc = _run([
            py,
            "scripts/run_pair_arb_matrix.py",
            "--limit",
            "180",
        ])
        lines.append(f"- pair_arb_rc: `{pair_rc}`")
        lines.append("")
        master.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    print(f"master_report={master}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
