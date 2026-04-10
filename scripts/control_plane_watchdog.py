#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REGIME_ENV_PATH = ROOT / "configs" / "regime_orchestrator_latest.env"
ROUTER_ENV_PATH = ROOT / "configs" / "dynamic_allowlist_latest.env"
ALLOCATOR_ENV_PATH = ROOT / "configs" / "portfolio_allocator_latest.env"
REGIME_STATE_PATH = ROOT / "runtime" / "regime" / "orchestrator_state.json"
ROUTER_STATE_PATH = ROOT / "runtime" / "router" / "symbol_router_state.json"
ALLOCATOR_STATE_PATH = ROOT / "runtime" / "control_plane" / "portfolio_allocator_state.json"
OUT_STATE_PATH = ROOT / "runtime" / "control_plane" / "control_plane_watchdog_state.json"


DEFAULT_MAX_AGE_SEC = {
    "regime_env": 7_200,
    "regime_state": 7_200,
    "router_env": 28_800,
    "router_state": 28_800,
    "allocator_env": 10_800,
    "allocator_state": 10_800,
}


def _state_age_sec(path: Path, now_ts: int) -> int | None:
    if not path.exists():
        return None
    try:
        return max(0, now_ts - int(path.stat().st_mtime))
    except Exception:
        return None


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _run_step(cmd: List[str]) -> Dict[str, Any]:
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    finished = time.time()
    return {
        "cmd": cmd,
        "ok": proc.returncode == 0,
        "returncode": int(proc.returncode),
        "elapsed_sec": round(max(0.0, finished - started), 3),
        "stdout_tail": "\n".join(proc.stdout.splitlines()[-8:]),
        "stderr_tail": "\n".join(proc.stderr.splitlines()[-8:]),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Freshness/self-heal watchdog for regime/router/allocator.")
    ap.add_argument("--repair", action="store_true", help="Rebuild stale layers in dependency order.")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--regime-max-age-sec", type=int, default=DEFAULT_MAX_AGE_SEC["regime_env"])
    ap.add_argument("--router-max-age-sec", type=int, default=DEFAULT_MAX_AGE_SEC["router_env"])
    ap.add_argument("--allocator-max-age-sec", type=int, default=DEFAULT_MAX_AGE_SEC["allocator_env"])
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    now_ts = int(time.time())
    max_age = {
        "regime_env": max(300, int(args.regime_max_age_sec)),
        "regime_state": max(300, int(args.regime_max_age_sec)),
        "router_env": max(900, int(args.router_max_age_sec)),
        "router_state": max(900, int(args.router_max_age_sec)),
        "allocator_env": max(900, int(args.allocator_max_age_sec)),
        "allocator_state": max(900, int(args.allocator_max_age_sec)),
    }

    files = {
        "regime_env": REGIME_ENV_PATH,
        "regime_state": REGIME_STATE_PATH,
        "router_env": ROUTER_ENV_PATH,
        "router_state": ROUTER_STATE_PATH,
        "allocator_env": ALLOCATOR_ENV_PATH,
        "allocator_state": ALLOCATOR_STATE_PATH,
    }

    # ── Detect router degraded_fallback status ────────────────────────
    # If router is in degraded_fallback, treat as stale regardless of file age.
    # This triggers an immediate rebuild attempt on next --repair run.
    router_degraded = False
    try:
        if ROUTER_STATE_PATH.exists():
            _rs = json.loads(ROUTER_STATE_PATH.read_text(encoding="utf-8"))
            if str(_rs.get("status") or "").strip().lower() == "degraded_fallback":
                router_degraded = True
    except Exception:
        pass

    checks: Dict[str, Dict[str, Any]] = {}
    stale_groups = {"regime": False, "router": False, "allocator": False}
    problems: List[str] = []
    for label, path in files.items():
        age = _state_age_sec(path, now_ts)
        stale = age is None or age > int(max_age[label])
        # Also treat router as stale if it's in degraded_fallback
        if label.startswith("router") and router_degraded:
            stale = True
        checks[label] = {
            "path": str(path),
            "exists": bool(path.exists()),
            "age_sec": age,
            "max_age_sec": int(max_age[label]),
            "stale": stale,
            "degraded": router_degraded if label.startswith("router") else False,
        }
        if stale:
            group = label.split("_", 1)[0]
            stale_groups[group] = True
            reason = "degraded_fallback" if (label.startswith("router") and router_degraded) else f"age={age}"
            problems.append(f"{label}: {reason} max={max_age[label]} path={path}")

    actions: List[Dict[str, Any]] = []
    repaired = False
    if args.repair:
        if stale_groups["regime"]:
            step = _run_step([sys.executable, "scripts/build_regime_state.py"])
            actions.append({"name": "build_regime_state", **step})
            repaired = repaired or bool(step["ok"])
            if not step["ok"]:
                stale_groups["router"] = False
                stale_groups["allocator"] = False
        if stale_groups["router"] or (actions and actions[-1]["name"] == "build_regime_state" and actions[-1]["ok"]):
            step = _run_step([sys.executable, "scripts/build_symbol_router.py", "--quiet"])
            actions.append({"name": "build_symbol_router", **step})
            repaired = repaired or bool(step["ok"])
            if not step["ok"]:
                stale_groups["allocator"] = False
        if stale_groups["allocator"] or any(a["name"] == "build_symbol_router" and a["ok"] for a in actions):
            step = _run_step([sys.executable, "scripts/build_portfolio_allocator.py"])
            actions.append({"name": "build_portfolio_allocator", **step})
            repaired = repaired or bool(step["ok"])

    post_checks: Dict[str, Dict[str, Any]] = {}
    post_problems: List[str] = []
    post_now_ts = int(time.time())
    for label, path in files.items():
        age = _state_age_sec(path, post_now_ts)
        stale = age is None or age > int(max_age[label])
        post_checks[label] = {
            "path": str(path),
            "exists": bool(path.exists()),
            "age_sec": age,
            "max_age_sec": int(max_age[label]),
            "stale": stale,
        }
        if stale:
            post_problems.append(f"{label}: age={age} max={max_age[label]} path={path}")

    status = "ok" if not post_problems else ("repaired_partial" if repaired else "degraded")
    payload = {
        "generated_at_utc": now.isoformat(),
        "repair_enabled": bool(args.repair),
        "status": status,
        "checks_before": checks,
        "checks_after": post_checks,
        "problems_before": problems,
        "problems_after": post_problems,
        "actions": actions,
    }
    _write_json(OUT_STATE_PATH, payload)

    if args.quiet:
        return 0 if not post_problems else 1

    print(f"status={status}")
    if problems:
        print("problems_before=" + json.dumps(problems, ensure_ascii=True))
    if actions:
        print("actions=" + json.dumps(actions, ensure_ascii=True))
    if post_problems:
        print("problems_after=" + json.dumps(post_problems, ensure_ascii=True))
    print(f"state={OUT_STATE_PATH}")
    return 0 if not post_problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
