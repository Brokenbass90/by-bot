#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
promote_wf22_winner.py — WF-22 gate → auto_apply_params.env bridge
===================================================================
Called by Codex / nightly queue after a WF-22 walkforward run completes.
Validates the WF result against the promotion gate and, if passing, writes
params directly to configs/auto_apply_params.env.

This is the FINAL promotion step — it only fires on confirmed WF-22 passes.

Usage (by Codex after WF-22):
  python3 scripts/promote_wf22_winner.py \\
    --strategy    alt_inplay_breakdown_v1 \\
    --wf-result   backtest_runs/walkforward_XXXX/walkforward_latest.json \\
    --params      BREAKDOWN_LOOKBACK_H=36 BREAKDOWN_SL_ATR=1.4 BREAKDOWN_RR=2.0 \\
    --description "breakdown v1 WF-22 winner 2026-04-20" \\
    --dry-run

On success:
  - Writes params to configs/auto_apply_params.env (override=True in bot)
  - Logs to runtime/auto_apply_log.jsonl
  - Sends Telegram: "🚀 Auto-promoted: <strategy>"
  - Exits 0

On failure (gate not passed):
  - Prints reason
  - Logs rejection
  - Exits 1

Gate (same as auto_apply_research_winner.py):
  AUTOAPPLY_MIN_PASS_RATIO  default 0.55   (12+ of 22 windows pass)
  AUTOAPPLY_MIN_AVG_PF      default 1.20
  AUTOAPPLY_MAX_AVG_DD      default 8.0
  AUTOAPPLY_QUIET_START_UTC default 2      (quiet window: no apply 02-04 UTC)
  AUTOAPPLY_QUIET_END_UTC   default 4
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import ssl
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
AUTO_APPLY_ENV = ROOT / "configs" / "auto_apply_params.env"
LOG_JSONL      = ROOT / "runtime" / "auto_apply_log.jsonl"

MIN_PASS_RATIO     = float(os.getenv("AUTOAPPLY_MIN_PASS_RATIO", "0.55"))
MIN_AVG_PF         = float(os.getenv("AUTOAPPLY_MIN_AVG_PF", "1.20"))
MAX_AVG_DD         = float(os.getenv("AUTOAPPLY_MAX_AVG_DD", "8.0"))
QUIET_START_UTC    = int(os.getenv("AUTOAPPLY_QUIET_START_UTC", "2"))
QUIET_END_UTC      = int(os.getenv("AUTOAPPLY_QUIET_END_UTC", "4"))
TG_TOKEN           = os.getenv("TG_TOKEN", "")
TG_CHAT_ID         = os.getenv("TG_CHAT_ID", os.getenv("TG_CHAT", ""))


def _tg(text: str) -> None:
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    try:
        payload = json.dumps({"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=10)
    except Exception as e:
        print(f"[promote_wf22] TG error: {e}", file=sys.stderr)


def _log(event: str, **kw: Any) -> None:
    LOG_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with LOG_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": int(time.time()), "event": event, **kw}) + "\n")


def _in_quiet() -> bool:
    h = datetime.now(timezone.utc).hour
    return QUIET_START_UTC <= h < QUIET_END_UTC


def _load_wf(path: str) -> Optional[Dict[str, Any]]:
    p = Path(path) if Path(path).is_absolute() else ROOT / path
    if not p.exists() and (p.parent / "walkforward_latest.json").exists():
        p = p.parent / "walkforward_latest.json"
    if not p.exists():
        return None
    try:
        text = p.read_text().replace(": Infinity", ": 9999").replace(":Infinity", ":9999")
        return json.loads(text)
    except Exception:
        return None


def _passes(wf: Dict[str, Any]) -> tuple[bool, str]:
    windows = int(wf.get("windows") or 0)
    passed  = int(wf.get("passed") or 0)
    avg_pf  = float(wf.get("avg_pf") or 0.0)
    avg_dd  = float(wf.get("avg_max_drawdown") or 999.0)
    if avg_pf > 900:
        avg_pf = 1.0
    if windows < 8:
        return False, f"only {windows} windows (need ≥ 8)"
    ratio = passed / windows
    if ratio < MIN_PASS_RATIO:
        return False, f"pass_ratio {ratio:.2f} < {MIN_PASS_RATIO} ({passed}/{windows})"
    if avg_pf < MIN_AVG_PF:
        return False, f"avg_pf {avg_pf:.3f} < {MIN_AVG_PF}"
    if avg_dd > MAX_AVG_DD:
        return False, f"avg_dd {avg_dd:.2f}% > {MAX_AVG_DD}%"
    return True, f"{passed}/{windows} windows pass | avg_pf={avg_pf:.3f} | avg_dd={avg_dd:.2f}%"


def _merge_env(params: Dict[str, str]) -> None:
    """Merge params into auto_apply_params.env, preserving existing keys."""
    current: Dict[str, str] = {}
    if AUTO_APPLY_ENV.exists():
        for line in AUTO_APPLY_ENV.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                current[k.strip()] = v.strip()
    current.update(params)
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Auto-generated by promote_wf22_winner.py — do not edit manually",
        f"# Updated: {now}", ""
    ] + [f"{k}={v}" for k, v in sorted(current.items())] + [""]
    AUTO_APPLY_ENV.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(AUTO_APPLY_ENV) + ".tmp"
    open(tmp, "w").write("\n".join(lines))
    os.replace(tmp, str(AUTO_APPLY_ENV))


def main() -> int:
    ap = argparse.ArgumentParser(description="WF-22 winner → auto_apply_params.env")
    ap.add_argument("--strategy",    required=True, help="Strategy name")
    ap.add_argument("--wf-result",   required=True, help="Path to walkforward_latest.json")
    ap.add_argument("--params",      nargs="+", default=[], help="KEY=VALUE pairs")
    ap.add_argument("--description", default="", help="Human-readable description")
    ap.add_argument("--dry-run",     action="store_true")
    ap.add_argument("--force",       action="store_true", help="Skip quiet-window check")
    args = ap.parse_args()

    strategy = args.strategy
    desc     = args.description or f"WF-22 winner: {strategy}"
    params   = {}
    for p in args.params:
        if "=" in p:
            k, _, v = p.partition("=")
            params[k.strip()] = v.strip()

    print(f"[promote_wf22] strategy={strategy}")
    print(f"[promote_wf22] wf_result={args.wf_result}")
    print(f"[promote_wf22] params={params}")

    if not args.force and _in_quiet():
        print(f"[promote_wf22] In quiet window ({QUIET_START_UTC}:00-{QUIET_END_UTC}:00 UTC). Use --force to override.")
        return 0

    wf = _load_wf(args.wf_result)
    if wf is None:
        print(f"[promote_wf22] ERROR: WF result not found: {args.wf_result}")
        return 1

    ok, reason = _passes(wf)
    print(f"[promote_wf22] Gate: {'✅ PASS' if ok else '❌ FAIL'} — {reason}")

    if not ok:
        if not args.dry_run:
            _log("wf22_rejected", strategy=strategy, reason=reason,
                 avg_pf=wf.get("avg_pf"), avg_dd=wf.get("avg_max_drawdown"),
                 windows=wf.get("windows"), passed=wf.get("passed"))
            _tg(f"❌ <b>WF-22 rejected</b>: {strategy}\nReason: {reason}")
        return 1

    if not params:
        print("[promote_wf22] No --params provided — nothing to apply")
        return 1

    if args.dry_run:
        print("[DRY RUN] Would apply:")
        for k, v in params.items():
            print(f"  {k}={v}")
        return 0

    _merge_env(params)
    _log("wf22_promoted", strategy=strategy, params=params,
         reason=reason, description=desc,
         avg_pf=wf.get("avg_pf"), avg_dd=wf.get("avg_max_drawdown"),
         windows=wf.get("windows"), passed=wf.get("passed"))
    _tg(
        f"🚀 <b>WF-22 auto-promoted</b>: {strategy}\n"
        f"Gate: {reason}\n"
        f"Params: {', '.join(f'{k}={v}' for k, v in params.items())}\n"
        f"⚡ Active on next bot reload (~5 min)"
    )
    print(f"[promote_wf22] ✅ Applied → {AUTO_APPLY_ENV}")
    for k, v in params.items():
        print(f"  {k}={v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
