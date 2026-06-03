#!/usr/bin/env python3
"""Runner TP fallback watchdog (Bybit linear perpetuals).

After commit ``981aea1 Allow runner entries without fixed TP`` the bot can
submit entries with ``request_tp=null`` — the per-trade *runner* state machine
then chooses the exit. That is fine while the runner thread is healthy, but if
it hangs (deploy race, network blip, exception in the trailing loop) the
position can sit on broker with **no take-profit** until the protective stop
triggers. This script is the safety-net: it scans recent OPEN entries with
``request_tp=null``, checks whether the broker-side ``takeProfit`` is still
empty after a grace window, and (optionally) sets a conservative fallback TP.

The watchdog is read-only by default. The ``--apply`` flag is required to
actually call ``/v5/position/trading-stop``. SL is **never** modified.

Usage (server)::

    python3 scripts/runner_tp_watchdog.py                 # dry-run, prints summary
    python3 scripts/runner_tp_watchdog.py --apply         # actually set TPs
    python3 scripts/runner_tp_watchdog.py --apply --grace-min 10 --rr 1.5

Cron suggestion (every minute, dry-run first day, then add ``--apply``)::

    * * * * * /usr/bin/python3 /root/by-bot/scripts/runner_tp_watchdog.py >> /root/by-bot/runtime/runner_tp_watchdog.log 2>&1

Decisions are journaled to ``runtime/runner_tp_watchdog.jsonl``.

Author: Claude Opus, 2026-06-02. Safety-net, not tuning.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Reuse signing + env helpers from emergency-SL script
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from set_bybit_emergency_sl import (  # type: ignore
        _request,
        _load_env,
        _first_bybit_account,
    )
except Exception as exc:  # pragma: no cover
    print(json.dumps({"ok": False, "error": f"helper_import_failed: {exc}"}))
    sys.exit(2)


ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "runtime" / "live_trade_events.jsonl"
MIRROR_EVENTS = ROOT / "runtime" / "live_mirror" / "live_trade_events.jsonl"
JOURNAL = ROOT / "runtime" / "runner_tp_watchdog.jsonl"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tail_events(path: Path, n: int = 2000) -> list[dict[str, Any]]:
    """Return last `n` JSON events from the live trade events file."""
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()[-n:]
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for raw in lines:
        try:
            out.append(json.loads(raw))
        except Exception:
            continue
    return out


def _open_runner_positions(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Rebuild current open positions that were submitted with request_tp=null.

    Returns mapping symbol -> last entry_filled event for runner-only entries
    that have not been closed yet.
    """
    state: dict[str, dict[str, Any]] = {}
    for ev in events:
        sym = str(ev.get("symbol") or "").upper()
        if not sym:
            continue
        kind = str(ev.get("event") or "")
        if kind == "order_submitted":
            req_tp = ev.get("request_tp")
            if req_tp is None:
                state[sym] = {"submitted": ev, "filled": None, "closed": False}
            else:
                # explicit TP — not our concern, drop any prior runner state
                state.pop(sym, None)
        elif kind == "entry_filled":
            cur = state.get(sym)
            if cur is not None:
                cur["filled"] = ev
        elif kind == "close":
            state.pop(sym, None)
    return {s: v for s, v in state.items() if v.get("filled") is not None}


def _compute_fallback_tp(side: str, entry: float, sl: float, rr: float) -> float | None:
    """Conservative fallback: TP at entry +/- rr * |entry-sl|.

    Side 'Sell' (short): TP below entry. Side 'Buy' (long): TP above entry.
    """
    if entry <= 0 or sl <= 0 or rr <= 0:
        return None
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    if side.lower() == "sell":
        return entry - risk * rr
    if side.lower() == "buy":
        return entry + risk * rr
    return None


def _format_price(symbol: str, price: float) -> str:
    """Crude tick-size formatter. Bybit accepts strings; better safe than sorry."""
    if symbol == "BTCUSDT":
        return f"{price:.1f}"
    if symbol == "ETHUSDT":
        return f"{price:.2f}"
    return f"{price:.6f}".rstrip("0").rstrip(".") or "0"


def _journal(entry: dict[str, Any]) -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Runner-only TP fallback watchdog")
    ap.add_argument("--grace-min", type=float, default=5.0,
                    help="Minutes to wait after entry_filled before adding fallback TP")
    ap.add_argument("--rr", type=float, default=1.5,
                    help="Risk-reward multiple for fallback TP (default 1.5)")
    ap.add_argument("--apply", action="store_true",
                    help="Actually call /v5/position/trading-stop (default: dry-run)")
    ap.add_argument("--max-age-hours", type=float, default=24.0,
                    help="Ignore entries older than this many hours")
    args = ap.parse_args()

    events_path = EVENTS if EVENTS.exists() else MIRROR_EVENTS
    events = _tail_events(events_path, n=4000)
    open_runners = _open_runner_positions(events)

    summary: dict[str, Any] = {
        "generated_at_utc": _utc_now_iso(),
        "events_path": str(events_path),
        "grace_min": args.grace_min,
        "rr": args.rr,
        "apply": bool(args.apply),
        "candidates": [],
    }

    if not open_runners:
        summary["note"] = "no_runner_only_open_entries"
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    env = {**os.environ, **_load_env(ROOT / ".env")}
    key, secret, base = _first_bybit_account(env)
    if not key or not secret:
        summary["note"] = "missing_bybit_credentials"
        print(json.dumps(summary, ensure_ascii=False))
        return 2

    now = time.time()
    grace_sec = max(60.0, args.grace_min * 60.0)
    max_age_sec = max(grace_sec, args.max_age_hours * 3600.0)

    for symbol, state in open_runners.items():
        filled = state["filled"]
        ts_filled = int(filled.get("ts") or 0)
        age_sec = max(0.0, now - ts_filled)
        item: dict[str, Any] = {
            "symbol": symbol,
            "strategy": filled.get("strategy"),
            "side": filled.get("side"),
            "entry_price": filled.get("entry_price") or filled.get("fill_price"),
            "sl_price": filled.get("sl_price"),
            "filled_ts_utc": filled.get("ts_utc"),
            "age_sec": int(age_sec),
        }
        if age_sec < grace_sec:
            item["decision"] = "skip_within_grace"
            summary["candidates"].append(item)
            continue
        if age_sec > max_age_sec:
            item["decision"] = "skip_too_old"
            summary["candidates"].append(item)
            continue

        # Fetch live position to check broker-side TP
        try:
            data = _request("GET", base, key, secret, "/v5/position/list",
                            {"category": "linear", "symbol": symbol})
        except Exception as exc:
            item["decision"] = "skip_position_query_failed"
            item["error"] = str(exc)[:120]
            summary["candidates"].append(item)
            continue

        positions = (((data or {}).get("result") or {}).get("list") or [])
        active = next((p for p in positions if abs(float(p.get("size") or 0.0)) > 0), None)
        if active is None:
            item["decision"] = "skip_position_already_closed"
            summary["candidates"].append(item)
            continue

        broker_tp = str(active.get("takeProfit") or "").strip()
        broker_sl = str(active.get("stopLoss") or "").strip()
        item["broker_tp"] = broker_tp
        item["broker_sl"] = broker_sl
        item["avg_price"] = active.get("avgPrice")
        item["size"] = active.get("size")

        if broker_tp and broker_tp not in {"0", "0.0", ""}:
            item["decision"] = "skip_broker_tp_already_set"
            summary["candidates"].append(item)
            continue

        avg = float(active.get("avgPrice") or item["entry_price"] or 0.0)
        sl = float(broker_sl or item["sl_price"] or 0.0)
        side = str(active.get("side") or item["side"] or "")
        fallback_tp = _compute_fallback_tp(side, avg, sl, args.rr)
        if fallback_tp is None or fallback_tp <= 0:
            item["decision"] = "skip_invalid_tp_calc"
            summary["candidates"].append(item)
            continue

        item["fallback_tp"] = round(fallback_tp, 8)

        if not args.apply:
            item["decision"] = "dry_run_would_set_tp"
            summary["candidates"].append(item)
            _journal({"event": "would_set_tp", **item, "generated_at_utc": _utc_now_iso()})
            continue

        # Apply: set broker-side TP only. Do not touch SL.
        body = {
            "category": "linear",
            "symbol": symbol,
            "tpslMode": "Full",
            "tpTriggerBy": "LastPrice",
            "takeProfit": _format_price(symbol, fallback_tp),
        }
        pidx = active.get("positionIdx")
        if pidx not in (None, "", "0", 0):
            try:
                body["positionIdx"] = int(pidx)
            except Exception:
                pass

        try:
            resp = _request("POST", base, key, secret, "/v5/position/trading-stop", body)
        except Exception as exc:
            item["decision"] = "apply_request_failed"
            item["error"] = str(exc)[:200]
            summary["candidates"].append(item)
            _journal({"event": "apply_failed", **item, "generated_at_utc": _utc_now_iso()})
            continue

        item["ret_code"] = resp.get("retCode")
        item["ret_msg"] = resp.get("retMsg")
        if resp.get("retCode") == 0:
            item["decision"] = "applied_tp"
        else:
            item["decision"] = "apply_rejected_by_exchange"
        summary["candidates"].append(item)
        _journal({"event": "tp_apply_attempt", **item, "generated_at_utc": _utc_now_iso()})

    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
