#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_research_queue_worker.py — consumer for the dynamic research queue.

regime_change_reopt.py appends sweep jobs to runtime/research_queue.jsonl when
the market regime changes. This worker drains that queue:

  1. Read runtime/research_queue.jsonl
  2. Skip if a sweep is already running (CPU-heavy — one at a time)
  3. Pick the oldest pending entry
  4. Launch scripts/run_strategy_autoresearch.py --spec <spec_path>
  5. Mark entry running → completed (rc=0) / failed (rc!=0)
  6. Rewrite the queue atomically with updated statuses
  7. On completion, optionally trigger auto_apply_research_winner.py --dry-run
     so a fresh winner proposal lands in Telegram

This closes the self-improvement loop:
  regime change → reopt queue → THIS WORKER → sweep → ranked_results.csv
  → auto_apply proposal (dry-run) → operator review → manual apply.

Design choices:
  - One sweep at a time (max_active=1) — backtests are CPU-bound
  - Lock file runtime/research_queue.lock prevents overlapping workers
  - Stale-lock detection: lock older than LOCK_STALE_SEC is reclaimed
  - Each launch logged to logs/research_queue/<tag>.log

Usage:
  python3 scripts/run_research_queue_worker.py            # process one job
  python3 scripts/run_research_queue_worker.py --dry-run  # show next job, don't run
  python3 scripts/run_research_queue_worker.py --status    # print queue state
  python3 scripts/run_research_queue_worker.py --no-auto-apply  # skip proposal step

Cron (every 30 min — long enough for a sweep to make progress):
  */30 * * * * cd /root/by-bot && python3 scripts/run_research_queue_worker.py --tg >> logs/research_queue_worker.log 2>&1

Env:
  QUEUE_LOCK_STALE_SEC   int, default 21600 (6h) — reclaim lock older than this
  QUEUE_ROW_TIMEOUT_SEC  int, default 14400 (4h) — kill a sweep that runs longer
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = ROOT / "runtime" / "research_queue.jsonl"
LOCK_PATH = ROOT / "runtime" / "research_queue.lock"
LOG_DIR = ROOT / "logs" / "research_queue"
RUNNER = ROOT / "scripts" / "run_strategy_autoresearch.py"
AUTO_APPLY = ROOT / "scripts" / "auto_apply_research_winner.py"

LOCK_STALE_SEC = int(os.getenv("QUEUE_LOCK_STALE_SEC", str(6 * 3600)))
ROW_TIMEOUT_SEC = int(os.getenv("QUEUE_ROW_TIMEOUT_SEC", str(4 * 3600)))


def _repo_python() -> str:
    venv = ROOT / ".venv" / "bin" / "python3"
    if venv.exists() and os.access(venv, os.X_OK):
        return str(venv)
    return sys.executable


def _read_queue() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not QUEUE_PATH.exists():
        return items
    for line in QUEUE_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items


def _write_queue(items: List[Dict[str, Any]]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = QUEUE_PATH.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(QUEUE_PATH)


def _acquire_lock() -> bool:
    """Return True if we got the lock. Reclaim stale locks."""
    now = time.time()
    if LOCK_PATH.exists():
        try:
            age = now - LOCK_PATH.stat().st_mtime
        except Exception:
            age = 0
        if age < LOCK_STALE_SEC:
            return False
        # stale — reclaim
        print(f"[queue] reclaiming stale lock (age={age:.0f}s)")
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(f"{os.getpid()} {datetime.now(timezone.utc).isoformat()}\n", encoding="utf-8")
    return True


def _release_lock() -> None:
    try:
        if LOCK_PATH.exists():
            LOCK_PATH.unlink()
    except Exception:
        pass


def _tg_send(text: str) -> None:
    token = os.getenv("TG_TOKEN", "").strip()
    chat = (os.getenv("TG_CHAT_ID") or os.getenv("TG_CHAT") or "").strip()
    if not token or not chat:
        return
    try:
        payload = json.dumps({"chat_id": chat, "text": text[:3500], "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload, headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        print(f"[queue] TG send failed: {exc}", file=sys.stderr)


def _print_status(items: List[Dict[str, Any]]) -> None:
    by_status: Dict[str, int] = {}
    for it in items:
        by_status[it.get("status", "?")] = by_status.get(it.get("status", "?"), 0) + 1
    print(f"[queue] {QUEUE_PATH} — {len(items)} entries")
    for st, n in sorted(by_status.items()):
        print(f"  {st}: {n}")
    pend = [it for it in items if it.get("status") == "pending"]
    if pend:
        print("  next pending:")
        for it in pend[:5]:
            print(f"    - {it.get('package')} (from {it.get('from_regime')}→{it.get('to_regime')}, queued {it.get('queued_at','')[:19]})")


def _run_sweep(spec_path: Path, tag: str) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{tag}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.log"
    cmd = [_repo_python(), str(RUNNER), "--spec", str(spec_path)]
    print(f"[queue] launching: {' '.join(cmd)}")
    print(f"[queue] log → {log_path}")
    with log_path.open("w", encoding="utf-8", errors="ignore") as log_f:
        log_f.write(f"cmd={' '.join(cmd)}\nstarted={datetime.now(timezone.utc).isoformat()}\n\n")
        try:
            subprocess.run(
                cmd, cwd=ROOT, check=True,
                stdout=log_f, stderr=subprocess.STDOUT,
                timeout=ROW_TIMEOUT_SEC,
            )
            return 0
        except subprocess.CalledProcessError as exc:
            log_f.write(f"\nFAILED rc={exc.returncode}\n")
            return exc.returncode or 1
        except subprocess.TimeoutExpired:
            log_f.write(f"\nTIMEOUT after {ROW_TIMEOUT_SEC}s\n")
            return 124


def _trigger_auto_apply_proposal() -> None:
    """Run auto_apply in dry-run so a fresh proposal lands in TG."""
    if not AUTO_APPLY.exists():
        return
    try:
        subprocess.run(
            [_repo_python(), str(AUTO_APPLY), "--dry-run"],
            cwd=ROOT, timeout=300,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        print(f"[queue] auto_apply proposal trigger failed: {exc}")


def _main() -> int:
    ap = argparse.ArgumentParser(description="Drain the dynamic research queue (one sweep per run).")
    ap.add_argument("--dry-run", action="store_true", help="Show next job, don't launch.")
    ap.add_argument("--status", action="store_true", help="Print queue state and exit.")
    ap.add_argument("--no-auto-apply", action="store_true", help="Don't trigger auto_apply proposal after sweep.")
    ap.add_argument("--tg", action="store_true", help="Send TG notifications.")
    args = ap.parse_args()

    items = _read_queue()

    if args.status:
        _print_status(items)
        return 0

    pending = [it for it in items if it.get("status") == "pending"]
    if not pending:
        print("[queue] no pending jobs.")
        return 0

    # Lock — one sweep at a time
    if not args.dry_run and not _acquire_lock():
        print("[queue] another worker holds the lock (sweep in progress). Exiting.")
        return 0

    try:
        # Pick oldest pending by queued_at_ts
        pending.sort(key=lambda it: float(it.get("queued_at_ts", 0)))
        job = pending[0]
        pkg = job.get("package", "")
        spec_rel = job.get("spec_path", "")
        spec_path = ROOT / spec_rel if spec_rel else (ROOT / "configs" / "autoresearch" / f"{pkg}.json")

        if not spec_path.exists():
            print(f"[queue] spec missing: {spec_path} — marking failed")
            job["status"] = "failed"
            job["error"] = "spec_missing"
            job["finished_at"] = datetime.now(timezone.utc).isoformat()
            if not args.dry_run:
                _write_queue(items)
            return 1

        if args.dry_run:
            print(f"[queue] DRY RUN — would launch sweep for: {pkg}")
            print(f"  spec: {spec_path}")
            print(f"  trigger: {job.get('trigger')} ({job.get('from_regime')}→{job.get('to_regime')})")
            return 0

        # Mark running
        job["status"] = "running"
        job["started_at"] = datetime.now(timezone.utc).isoformat()
        _write_queue(items)

        if args.tg:
            _tg_send(
                f"⚙️ <b>Research queue</b>: launching sweep\n"
                f"  <code>{pkg}</code>\n"
                f"  trigger: {job.get('trigger')} ({job.get('from_regime')}→{job.get('to_regime')})"
            )

        tag = f"queue_{pkg}"
        rc = _run_sweep(spec_path, tag)

        # Refresh items (queue may have grown during the sweep) and update this job
        items = _read_queue()
        for it in items:
            if it.get("package") == pkg and it.get("status") == "running":
                it["status"] = "completed" if rc == 0 else "failed"
                it["rc"] = rc
                it["finished_at"] = datetime.now(timezone.utc).isoformat()
                break
        _write_queue(items)

        result_word = "completed" if rc == 0 else f"FAILED (rc={rc})"
        print(f"[queue] sweep {pkg} {result_word}")

        if args.tg:
            icon = "✅" if rc == 0 else "❌"
            _tg_send(
                f"{icon} <b>Research queue</b>: {pkg} {result_word}\n"
                f"  Check ranked_results.csv; run auto_apply for proposal."
            )

        # Trigger proposal
        if rc == 0 and not args.no_auto_apply:
            _trigger_auto_apply_proposal()

        return 0 if rc == 0 else 1

    finally:
        if not args.dry_run:
            _release_lock()


if __name__ == "__main__":
    raise SystemExit(_main())
