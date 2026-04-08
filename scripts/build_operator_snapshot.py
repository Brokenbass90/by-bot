#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.operator_snapshot import build_operator_snapshot, format_operator_snapshot_text  # noqa: E402


OUT_JSON = ROOT / "runtime" / "operator" / "operator_snapshot.json"
OUT_TXT = ROOT / "runtime" / "operator" / "operator_snapshot.txt"


def main() -> int:
    ap = argparse.ArgumentParser(description="Build compact operator snapshot from live/runtime artifacts.")
    ap.add_argument("--out-json", default=str(OUT_JSON))
    ap.add_argument("--out-txt", default=str(OUT_TXT))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    out_json = Path(args.out_json).expanduser()
    out_txt = Path(args.out_txt).expanduser()
    if not out_json.is_absolute():
        out_json = ROOT / out_json
    if not out_txt.is_absolute():
        out_txt = ROOT / out_txt

    snapshot = build_operator_snapshot(ROOT)
    text = format_operator_snapshot_text(snapshot)

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(snapshot, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    out_txt.write_text(text + "\n", encoding="utf-8")

    if not args.quiet:
        print(text)
        print("")
        print(f"saved_json={out_json}")
        print(f"saved_txt={out_txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
