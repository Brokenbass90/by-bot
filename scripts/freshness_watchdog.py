#!/usr/bin/env python3
"""Freshness watchdog — never silently trade stale control-plane state (Opus 2026-06-08).

Root problem found 2026-06-08: the symbol router's fail-safe ("keep last-known-good
allowlist if the scan fails") silently MASKS a chronic failure — the coin universe
froze (~1 month old) with no error, so the bot kept trading an outdated basket and
slowly degraded. This watchdog makes staleness LOUD: it checks the age of every
critical state file and flags anything older than its threshold, so cron/TG can alert
and the dynamic selection is actually kept fresh.

Read-only, pure-stdlib, unit-tested. Run on cron (e.g. every 30 min); exit code 1 if
anything is stale so the caller can alert.

Usage:
    python3 scripts/freshness_watchdog.py
    python3 scripts/freshness_watchdog.py --json runtime/freshness_report.json --telegram
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

# name -> (relative path, max age in hours). Tunable.
CRITICAL: List[Dict[str, Any]] = [
    {"name": "dynamic_allowlist", "path": "configs/dynamic_allowlist_latest.env", "max_age_h": 8.0},
    {"name": "symbol_router_state", "path": "runtime/router/symbol_router_state.json", "max_age_h": 8.0},
    {"name": "regime_state", "path": "runtime/regime/orchestrator_state.json", "max_age_h": 2.0},
    {"name": "bot_heartbeat", "path": "runtime/bot_heartbeat.json", "max_age_h": 0.5},
]


def evaluate_freshness(items: List[Dict[str, Any]], now_ts: float) -> Dict[str, Any]:
    """Pure: items = [{name, age_sec, max_age_sec, present}]. Returns verdict + stale list."""
    stale, missing, ok = [], [], []
    for it in items:
        if not it.get("present", True):
            missing.append(it["name"])
            continue
        if it["age_sec"] > it["max_age_sec"]:
            stale.append({"name": it["name"], "age_h": round(it["age_sec"] / 3600.0, 2),
                          "max_age_h": round(it["max_age_sec"] / 3600.0, 2)})
        else:
            ok.append(it["name"])
    verdict = "ok" if not stale and not missing else "stale"
    return {"verdict": verdict, "stale": stale, "missing": missing, "ok": ok}


def _file_age_sec(path: Path, now_ts: float) -> Optional[float]:
    if not path.exists():
        return None
    return now_ts - path.stat().st_mtime


def build_report(now_ts: Optional[float] = None) -> Dict[str, Any]:
    now_ts = now_ts if now_ts is not None else time.time()
    items = []
    for spec in CRITICAL:
        p = ROOT / spec["path"]
        age = _file_age_sec(p, now_ts)
        items.append({
            "name": spec["name"],
            "present": age is not None,
            "age_sec": age if age is not None else 0.0,
            "max_age_sec": spec["max_age_h"] * 3600.0,
            "path": spec["path"],
        })
    rep = evaluate_freshness(items, now_ts)
    rep["details"] = [{"name": i["name"], "present": i["present"],
                       "age_h": round(i["age_sec"] / 3600.0, 2), "path": i["path"]} for i in items]
    return rep


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
    ap.add_argument("--json", type=str, default="")
    ap.add_argument("--telegram", action="store_true")
    args = ap.parse_args()
    rep = build_report()
    if args.json:
        Path(args.json).write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(f"freshness: {rep['verdict'].upper()}")
    for d in rep["details"]:
        mark = "ok" if d["name"] in rep["ok"] else ("MISSING" if not d["present"] else "STALE")
        print(f"  [{mark:7}] {d['name']:22} age={d['age_h']}h  ({d['path']})")
    if rep["stale"]:
        print("\n⚠ STALE — dynamic selection / state not refreshing. Check cron + scan logs.")
    if args.telegram and rep["verdict"] != "ok":
        bad = ", ".join([s["name"] for s in rep["stale"]] + list(rep["missing"]))
        _send_tg(f"🚨 freshness watchdog: stale control-plane state: {bad}")
    return 1 if rep["verdict"] != "ok" else 0


if __name__ == "__main__":
    raise SystemExit(main())
