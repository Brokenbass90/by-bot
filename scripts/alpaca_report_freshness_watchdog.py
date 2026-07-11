#!/usr/bin/env python3
"""Alert when the recurring Alpaca post-close Telegram report was not delivered.

The report job writes an atomic status file only after attempting delivery.  This
watchdog is intended for 23:00 UTC on weekdays, after the 22:10 UTC report job.
It never treats a dry-run as a successful delivery.
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any
from urllib import request

ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "runtime" / "alpaca_reports" / "alpaca_postclose_status.json"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        rows = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    for row in rows:
        row = row.strip()
        if not row or row.startswith("#") or "=" not in row:
            continue
        key, value = row.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _read_status(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def evaluate_delivery(status: dict[str, Any], now_utc: datetime) -> dict[str, Any]:
    """Pure delivery verdict for the current UTC reporting day."""
    now_utc = now_utc.astimezone(timezone.utc)
    due = now_utc.weekday() < 5 and now_utc.time() >= time(22, 30)
    if not due:
        return {"due": False, "ok": True, "reason": "not_due"}

    if not status:
        return {"due": True, "ok": False, "reason": "status_missing"}
    if not bool(status.get("success")):
        return {"due": True, "ok": False, "reason": "delivery_failed"}
    if bool(status.get("dry_run")):
        return {"due": True, "ok": False, "reason": "dry_run_not_delivery"}
    try:
        sent_at = datetime.fromisoformat(str(status.get("attempted_at_utc") or "").replace("Z", "+00:00"))
        sent_at = sent_at.astimezone(timezone.utc)
    except Exception:
        return {"due": True, "ok": False, "reason": "timestamp_invalid"}
    if sent_at.date() != now_utc.date():
        return {
            "due": True,
            "ok": False,
            "reason": "not_delivered_today",
            "last_attempted_at_utc": sent_at.isoformat(),
        }
    return {
        "due": True,
        "ok": True,
        "reason": "delivered_today",
        "attempted_at_utc": sent_at.isoformat(),
        "broker_mode": status.get("broker_mode"),
    }


def _send_alert(text: str) -> bool:
    token = (os.getenv("TG_TOKEN") or "").strip()
    chat_id = (os.getenv("TG_CHAT_ID") or os.getenv("TG_CHAT") or "").strip()
    if not token or not chat_id:
        print("[alpaca-report-watchdog] Telegram credentials missing", file=sys.stderr)
        return False
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, context=ssl.create_default_context(), timeout=12):
            return True
    except Exception as exc:
        print(f"[alpaca-report-watchdog] Telegram alert failed: {exc}", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", type=Path, default=STATUS_PATH)
    ap.add_argument("--dry-run", action="store_true", help="Print verdict; never send Telegram")
    args = ap.parse_args()

    _load_env_file(ROOT / "configs" / "alpaca_live_v38.env")
    _load_env_file(ROOT / "configs" / "alpaca_paper_local.env")
    now = datetime.now(timezone.utc)
    verdict = evaluate_delivery(_read_status(args.status), now)
    print(json.dumps(verdict, ensure_ascii=False, sort_keys=True))
    if verdict["ok"]:
        return 0

    message = (
        "🚨 Alpaca post-close report missing\n"
        f"UTC date: {now.date().isoformat()}\n"
        f"Reason: {verdict['reason']}\n"
        "Check tg_daily_digest.log / Alpaca API credentials / Telegram delivery."
    )
    if args.dry_run:
        print(message)
        return 1
    _send_alert(message)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
