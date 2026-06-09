#!/usr/bin/env python3
"""Stop-integrity watchdog — auto-verdict for the P0 bug (Opus 2026-06-08).

The P0 bug: at fill time the bot overwrote the strategy's stop with a tiny global
0.30% stop, so trades were knifed by noise. The fix preserves the strategy stop.
This watchdog turns the manual "did the fix work?" check into an automatic guard:
for every entry it joins order_submitted.request_sl with the actual post-fill
sl_price and flags COMPRESSION (actual stop much tighter than requested) — i.e. the
bug returned or appeared on another code path.

Reads runtime/live_trade_events.jsonl, falling back to the web mirror if needed.
Read-only, pure-stdlib, tested. Exit code 1 if any recent entry shows stop
compression or cannot be verified because its order_submitted event is missing.

Usage:
    python3 scripts/stop_integrity_watchdog.py
    python3 scripts/stop_integrity_watchdog.py --json runtime/stop_integrity_report.json --telegram
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "runtime" / "live_trade_events.jsonl"
MIRROR_EVENTS = ROOT / "runtime" / "live_mirror" / "live_trade_events.jsonl"


def _dist_pct(level: Optional[float], ref: Optional[float]) -> Optional[float]:
    try:
        level = float(level); ref = float(ref)
    except (TypeError, ValueError):
        return None
    if ref <= 0 or level <= 0:
        return None
    return abs(level - ref) / ref * 100.0


def analyze_orders(events: List[Dict[str, Any]], compression_ratio: float = 0.6,
                   min_requested_pct: float = 0.5) -> Dict[str, Any]:
    """Join events by entry_order_id; flag stop compression.

    A trade is COMPRESSED if the actual post-fill stop distance is materially
    tighter than the requested (strategy) stop distance:
        actual_stop_dist < compression_ratio * requested_stop_dist
    (only checked when the requested stop was meaningfully wide, > min_requested_pct).
    """
    by_oid: Dict[str, Dict[str, Any]] = {}
    for e in events:
        oid = str(e.get("entry_order_id") or "").strip()
        if not oid:
            continue
        rec = by_oid.setdefault(oid, {})
        ev = e.get("event")
        if ev == "order_submitted":
            rec["request_sl"] = e.get("request_sl")
            rec["request_price"] = e.get("request_price") or e.get("entry_price")
            rec["strategy"] = e.get("strategy")
            rec["symbol"] = e.get("symbol")
        elif ev in ("entry_filled", "close"):
            rec.setdefault("strategy", e.get("strategy"))
            rec.setdefault("symbol", e.get("symbol"))
            if e.get("sl_price") is not None:
                rec["sl_price"] = e.get("sl_price")
            if e.get("fill_price") is not None:
                rec["fill_price"] = e.get("fill_price")
            elif e.get("entry_price") is not None and "fill_price" not in rec:
                rec["fill_price"] = e.get("entry_price")

    flagged: List[Dict[str, Any]] = []
    missing_request: List[Dict[str, Any]] = []
    checked = 0
    for oid, r in by_oid.items():
        req = _dist_pct(r.get("request_sl"), r.get("request_price"))
        act = _dist_pct(r.get("sl_price"), r.get("fill_price"))
        if req is None and act is not None:
            missing_request.append({
                "order_id": oid, "symbol": r.get("symbol"), "strategy": r.get("strategy"),
                "actual_stop_pct": round(act, 3),
            })
            continue
        if req is None or act is None:
            continue
        if req < min_requested_pct:
            continue
        checked += 1
        if act < compression_ratio * req:
            flagged.append({
                "order_id": oid, "symbol": r.get("symbol"), "strategy": r.get("strategy"),
                "requested_stop_pct": round(req, 3), "actual_stop_pct": round(act, 3),
            })
    if flagged:
        verdict = "compression_detected"
    elif missing_request:
        verdict = "missing_request"
    else:
        verdict = "ok" if checked else "no_data"
    return {
        "checked": checked, "flagged_count": len(flagged), "flagged": flagged,
        "missing_request_count": len(missing_request), "missing_request": missing_request,
        "verdict": verdict,
    }


def _filter_recent(events: List[Dict[str, Any]], lookback_hours: float) -> List[Dict[str, Any]]:
    if lookback_hours <= 0:
        return events
    cutoff = time.time() - lookback_hours * 3600.0
    recent = []
    for event in events:
        try:
            ts = float(event.get("ts") or 0.0)
        except (TypeError, ValueError):
            ts = 0.0
        if ts <= 0 or ts >= cutoff:
            recent.append(event)
    return recent


def _send_tg(text: str) -> None:
    token = (os.getenv("TG_TOKEN") or "").strip()
    chat = (os.getenv("TG_CHAT_ID") or os.getenv("TG_CHAT") or "").strip()
    if not token or not chat:
        return
    data = urlencode({"chat_id": chat, "text": text[:3900]}).encode("utf-8")
    try:
        urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=10).read()
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default=str(EVENTS))
    ap.add_argument("--json", default="")
    ap.add_argument("--compression-ratio", type=float, default=0.6)
    ap.add_argument("--lookback-hours", type=float, default=24.0)
    ap.add_argument("--telegram", action="store_true")
    args = ap.parse_args()
    p = Path(args.events)
    if not p.exists() and Path(args.events) == EVENTS and MIRROR_EVENTS.exists():
        p = MIRROR_EVENTS
    events = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try: events.append(json.loads(line))
                except Exception: pass
    events = _filter_recent(events, args.lookback_hours)
    rep = analyze_orders(events, compression_ratio=args.compression_ratio)
    if args.json:
        Path(args.json).write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(
        f"stop-integrity: {rep['verdict'].upper()} "
        f"(checked={rep['checked']}, flagged={rep['flagged_count']}, "
        f"missing_request={rep['missing_request_count']})"
    )
    for f in rep["flagged"]:
        print(f"  ⚠ {f['symbol']} {f['strategy']}: requested {f['requested_stop_pct']}% -> actual {f['actual_stop_pct']}% (COMPRESSED)")
    for f in rep["missing_request"]:
        print(f"  ⚠ {f['symbol']} {f['strategy']}: missing order_submitted; actual stop {f['actual_stop_pct']}% cannot be verified")
    if args.telegram and rep["verdict"] not in ("ok", "no_data"):
        _send_tg(
            "🚨 stop-integrity watchdog: "
            f"{rep['verdict']} checked={rep['checked']} "
            f"flagged={rep['flagged_count']} missing_request={rep['missing_request_count']}"
        )
    return 1 if rep["verdict"] not in ("ok", "no_data") else 0


if __name__ == "__main__":
    raise SystemExit(main())
