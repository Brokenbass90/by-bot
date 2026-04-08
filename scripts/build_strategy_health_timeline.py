#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.strategy_health_timeline import build_strategy_health_timeline  # noqa: E402


OUT_PATH = ROOT / "runtime" / "control_plane" / "strategy_health_timeline.json"
OUT_HISTORY = ROOT / "runtime" / "control_plane" / "strategy_health_timeline.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser(description="Build historical strategy health timeline from a trusted portfolio run.")
    ap.add_argument("--run-dir", default="", help="Specific run dir to analyze. Default uses trusted latest run.")
    ap.add_argument("--step-days", type=int, default=15, help="Checkpoint spacing in days.")
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--out-history", default=str(OUT_HISTORY))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    run_dir = None
    if args.run_dir:
        run_dir = Path(args.run_dir).expanduser()
        if not run_dir.is_absolute():
            run_dir = ROOT / run_dir

    out_path = Path(args.out).expanduser()
    out_history = Path(args.out_history).expanduser()
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    if not out_history.is_absolute():
        out_history = ROOT / out_history

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_history.parent.mkdir(parents=True, exist_ok=True)
    try:
        timeline = build_strategy_health_timeline(run_dir, step_days=int(args.step_days))
    except FileNotFoundError:
        if out_path.exists():
            if not args.quiet:
                print(f"kept_existing={out_path}")
            return 0
        raise

    text = json.dumps(timeline, ensure_ascii=True, indent=2) + "\n"
    out_path.write_text(text, encoding="utf-8")

    with out_history.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "generated_at_utc": timeline.get("generated_at_utc"),
                    "run_dir": timeline.get("run_dir"),
                    "step_days": timeline.get("step_days"),
                    "snapshot_count": len(timeline.get("snapshots") or []),
                    "first_checkpoint_date_utc": ((timeline.get("snapshots") or [{}])[0]).get("checkpoint_date_utc", ""),
                    "last_checkpoint_date_utc": ((timeline.get("snapshots") or [{}])[-1]).get("checkpoint_date_utc", ""),
                },
                ensure_ascii=True,
            )
            + "\n"
        )

    if not args.quiet:
        print(f"saved={out_path}")
        print(f"run_dir={timeline.get('run_dir')}")
        print(f"step_days={timeline.get('step_days')}")
        print(f"snapshots={len(timeline.get('snapshots') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
