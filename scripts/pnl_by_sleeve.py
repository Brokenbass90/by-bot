#!/usr/bin/env python3
"""Realized P&L breakdown by sleeve / day / month (Opus 2026-06-08).

Foundation for the web "clickable daily P&L" modal: per-strategy (sleeve),
per-day and per-month realized P&L from the live trade-event log. Pure stdlib,
read-only. Feeds /api/pnl/by-sleeve and the planned P&L modal.

Usage:
    python3 scripts/pnl_by_sleeve.py
    python3 scripts/pnl_by_sleeve.py --json runtime/pnl_breakdown.json
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "runtime" / "live_trade_events.jsonl"
MIRROR_EVENTS = ROOT / "runtime" / "live_mirror" / "live_trade_events.jsonl"


def _acc() -> Dict[str, float]:
    return {"pnl": 0.0, "fees": 0.0, "wins": 0, "losses": 0, "trades": 0}


def _add(d: Dict[str, float], pnl: float, fees: float) -> None:
    d["pnl"] += pnl
    d["fees"] += fees
    d["trades"] += 1
    if pnl >= 0:
        d["wins"] += 1
    else:
        d["losses"] += 1


def build_breakdown(events_path: Path = EVENTS) -> Dict[str, Any]:
    if not events_path.exists() and events_path == EVENTS and MIRROR_EVENTS.exists():
        events_path = MIRROR_EVENTS
    by_sleeve: Dict[str, Dict[str, float]] = defaultdict(_acc)
    by_day: Dict[str, Dict[str, float]] = defaultdict(_acc)
    by_month: Dict[str, Dict[str, float]] = defaultdict(_acc)
    by_sleeve_day: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(lambda: defaultdict(_acc))
    total = _acc()

    if not events_path.exists():
        return {"error": f"no events file: {events_path}", "total": total}

    for line in events_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("event") != "close" or e.get("pnl") is None:
            continue
        pnl = float(e.get("pnl") or 0.0)
        fees = float(e.get("fees") or 0.0)
        sleeve = str(e.get("strategy") or "unknown")
        day = str(e.get("ts_utc") or "")[:10]      # YYYY-MM-DD
        month = day[:7]                            # YYYY-MM
        _add(by_sleeve[sleeve], pnl, fees)
        _add(by_day[day], pnl, fees)
        _add(by_month[month], pnl, fees)
        _add(by_sleeve_day[sleeve][day], pnl, fees)
        _add(total, pnl, fees)

    def _round(d):
        return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in d.items()}

    return {
        "total": _round(total),
        "by_sleeve": {k: _round(v) for k, v in sorted(by_sleeve.items(), key=lambda kv: kv[1]["pnl"])},
        "by_day": {k: _round(v) for k, v in sorted(by_day.items())},
        "by_month": {k: _round(v) for k, v in sorted(by_month.items())},
        "by_sleeve_day": {s: {d: _round(v) for d, v in sorted(days.items())} for s, days in by_sleeve_day.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=str, default="", help="optional output path")
    args = ap.parse_args()
    bd = build_breakdown()
    if args.json:
        Path(args.json).write_text(json.dumps(bd, indent=2), encoding="utf-8")
        print(f"written: {args.json}")
    t = bd.get("total", {})
    print(f"\nTOTAL realized: pnl={t.get('pnl',0):.4f} fees={t.get('fees',0):.4f} "
          f"trades={t.get('trades',0)} W/L={t.get('wins',0)}/{t.get('losses',0)}")
    print("\nBy sleeve (worst→best):")
    for s, v in bd.get("by_sleeve", {}).items():
        print(f"  {s:30} pnl={v['pnl']:+.4f}  trades={v['trades']}  W/L={v['wins']}/{v['losses']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
