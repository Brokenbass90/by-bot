#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
regime_change_reopt.py — Phase B2: re-queue strategy sweeps on regime change.

When the orchestrator transitions to a new regime (e.g. bull_chop → bear_chop),
the strategies that were optimal for the previous regime may no longer be.
This script:

  1. Reads the current applied regime from runtime/regime/orchestrator_state.json
  2. Reads the previous applied regime from runtime/regime/last_seen_regime.txt
  3. If they differ → consults a regime→packages mapping and appends sweep specs
     to runtime/research_queue.jsonl for the autoresearch worker to pick up
  4. Updates last_seen_regime.txt so we don't double-queue

Idempotent: re-running with the same regime does nothing.

Mapping (built-in, override via configs/regime_reopt_mapping.json):
  bull_trend → att1_rsi_relax, asc1_longs, elder_ema   (longs-oriented)
  bull_chop  → att1_rsi_relax, arf1_flat_touch         (range + trend touch)
  bear_trend → brc1, asb1, breakdown_rsi               (shorts-oriented)
  bear_chop  → arf1_flat_touch, breakdown_rsi          (shorts + flat)
  neutral    → att1_rsi_relax, arf1_flat_touch         (balanced)

Usage:
  python3 scripts/regime_change_reopt.py            # check and queue
  python3 scripts/regime_change_reopt.py --dry-run  # show what would be queued
  python3 scripts/regime_change_reopt.py --force    # ignore last_seen_regime
  python3 scripts/regime_change_reopt.py --print-mapping  # show config

Cron (every 15 min — fast enough to react, slow enough to not spam):
  */15 * * * * cd /root/by-bot && python3 scripts/regime_change_reopt.py >> logs/regime_reopt.log 2>&1

Env vars:
  REOPT_THROTTLE_HOURS  int, default 24 — min hours between queues per package
  REOPT_MAX_QUEUE_DEPTH int, default 10 — refuse to add if queue already this deep
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
REGIME_STATE = ROOT / "runtime" / "regime" / "orchestrator_state.json"
LAST_SEEN_PATH = ROOT / "runtime" / "regime" / "last_seen_regime.txt"
RESEARCH_QUEUE = ROOT / "runtime" / "research_queue.jsonl"
MAPPING_PATH = ROOT / "configs" / "regime_reopt_mapping.json"
SWEEP_DIR = ROOT / "configs" / "autoresearch"

THROTTLE_HOURS = int(os.getenv("REOPT_THROTTLE_HOURS", "24"))
MAX_QUEUE_DEPTH = int(os.getenv("REOPT_MAX_QUEUE_DEPTH", "10"))

# Defaults; user can override via configs/regime_reopt_mapping.json
DEFAULT_MAPPING: Dict[str, List[str]] = {
    "bull_trend": [
        "package_att1_rsi_relax_v1",
        "package_bull_asc1_longs_v1",
        "package_elder_ema_v1",
    ],
    "bull_chop": [
        "package_att1_rsi_relax_v1",
        "package_arf1_flat_touch_v1",
    ],
    "bear_trend": [
        "package_bear_brc1_v1",
        "package_asb1_slope_break_v1",
        "package_breakdown_rsi_v1",
    ],
    "bear_chop": [
        "package_arf1_flat_touch_v1",
        "package_breakdown_rsi_v1",
    ],
    "neutral": [
        "package_att1_rsi_relax_v1",
        "package_arf1_flat_touch_v1",
    ],
}


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _load_mapping() -> Dict[str, List[str]]:
    custom = _read_json(MAPPING_PATH)
    if isinstance(custom, dict):
        merged = dict(DEFAULT_MAPPING)
        merged.update(custom)
        return merged
    return DEFAULT_MAPPING


def _read_last_seen() -> str:
    try:
        if LAST_SEEN_PATH.exists():
            return LAST_SEEN_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""


def _write_last_seen(regime: str) -> None:
    LAST_SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LAST_SEEN_PATH.with_suffix(".tmp")
    tmp.write_text(regime, encoding="utf-8")
    tmp.replace(LAST_SEEN_PATH)


def _read_queue() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not RESEARCH_QUEUE.exists():
        return items
    for line in RESEARCH_QUEUE.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items


def _append_queue(entry: Dict[str, Any]) -> None:
    RESEARCH_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with RESEARCH_QUEUE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _recent_queue_for_package(package: str, hours: int) -> bool:
    """Return True if package was queued in the last `hours`."""
    now_ts = datetime.now(timezone.utc).timestamp()
    cutoff = now_ts - hours * 3600
    for entry in _read_queue():
        if entry.get("package") != package:
            continue
        try:
            ts = float(entry.get("queued_at_ts", 0))
        except (TypeError, ValueError):
            continue
        if ts >= cutoff:
            return True
    return False


def _pending_queue_depth() -> int:
    """Count entries with status != 'completed'."""
    return sum(1 for e in _read_queue() if e.get("status") not in ("completed", "failed"))


def _validate_package_exists(package: str) -> bool:
    return (SWEEP_DIR / f"{package}.json").exists()


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
        print(f"[regime_reopt] TG send failed: {exc}", file=sys.stderr)


def _main() -> int:
    ap = argparse.ArgumentParser(description="Regime-triggered re-optimisation queue.")
    ap.add_argument("--dry-run", action="store_true", help="Don't write queue or last_seen.")
    ap.add_argument("--force", action="store_true", help="Ignore last_seen + throttle.")
    ap.add_argument("--print-mapping", action="store_true", help="Print the regime→packages map.")
    ap.add_argument("--tg", action="store_true", help="Send TG notification on queue.")
    args = ap.parse_args()

    mapping = _load_mapping()

    if args.print_mapping:
        print(json.dumps(mapping, indent=2, ensure_ascii=False))
        return 0

    state = _read_json(REGIME_STATE)
    if not state:
        print(f"[regime_reopt] missing regime state: {REGIME_STATE}")
        return 2
    current_regime = str(state.get("regime", "")).strip()
    if not current_regime:
        print("[regime_reopt] regime field empty in orchestrator state")
        return 2

    last_seen = _read_last_seen()
    print(f"[regime_reopt] current={current_regime} last_seen={last_seen or '(none)'}")

    if not args.force and current_regime == last_seen:
        print(f"[regime_reopt] No regime change — nothing to do.")
        return 0

    packages = mapping.get(current_regime, [])
    if not packages:
        print(f"[regime_reopt] No packages mapped for regime '{current_regime}'.")
        if not args.dry_run:
            _write_last_seen(current_regime)
        return 0

    queue_depth = _pending_queue_depth()
    if queue_depth >= MAX_QUEUE_DEPTH:
        print(
            f"[regime_reopt] queue full (pending={queue_depth} >= {MAX_QUEUE_DEPTH}). "
            f"Skipping — operator should drain queue first."
        )
        if args.tg:
            _tg_send(
                f"⏸️  Regime change to <b>{current_regime}</b> detected, "
                f"but research queue is full ({queue_depth} pending). Drain it manually."
            )
        return 0

    queued: List[str] = []
    skipped: List[str] = []

    for pkg in packages:
        if not _validate_package_exists(pkg):
            print(f"[regime_reopt] ⚠️  package '{pkg}' missing on disk — skip")
            skipped.append(f"{pkg} (missing)")
            continue
        if not args.force and _recent_queue_for_package(pkg, THROTTLE_HOURS):
            print(f"[regime_reopt] {pkg} on cooldown ({THROTTLE_HOURS}h) — skip")
            skipped.append(f"{pkg} (cooldown)")
            continue
        entry = {
            "package":      pkg,
            "spec_path":    str((SWEEP_DIR / f"{pkg}.json").relative_to(ROOT)),
            "trigger":      "regime_change",
            "from_regime":  last_seen or "unknown",
            "to_regime":    current_regime,
            "queued_at":    datetime.now(timezone.utc).isoformat(),
            "queued_at_ts": datetime.now(timezone.utc).timestamp(),
            "status":       "pending",
        }
        if not args.dry_run:
            _append_queue(entry)
        queued.append(pkg)
        print(f"[regime_reopt] queued: {pkg}")

    if not args.dry_run:
        _write_last_seen(current_regime)

    summary = (
        f"🔄 <b>Regime change reopt</b>\n"
        f"  {last_seen or '(none)'} → <b>{current_regime}</b>\n"
        f"  queued: {len(queued)} | skipped: {len(skipped)}\n"
    )
    if queued:
        summary += "  ✓ " + ", ".join(queued)
    if skipped:
        summary += "\n  ⏸ " + ", ".join(skipped)

    print()
    print(summary.replace("<b>", "").replace("</b>", ""))

    if args.tg and queued and not args.dry_run:
        _tg_send(summary)

    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
