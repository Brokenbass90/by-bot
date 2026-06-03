#!/usr/bin/env python3
"""Regime mirror diagnostic.

heartbeat.regime is sourced from ``os.getenv("ORCH_REGIME", "unknown")`` in the
bot process. When the bot still shows ``regime=unknown`` but the orchestrator
state file holds a real regime, one of the four hops in the mirror chain is
broken:

    orchestrator_state.json  →  regime_orchestrator_latest.env  →  bot env load  →  heartbeat.regime

This script inspects all four hops and writes a single classified report so
the operator (or AI context) can see exactly which hop is stale.

It does **not** modify any env, kill processes, or restart anything. Detection
only. If ``--apply-overlay-refresh`` is passed and the orchestrator file is
fresh while the overlay file is stale, it rewrites the overlay env file from
``strategy_overrides`` of the orchestrator state — that is a flat, idempotent
copy and is the only "fix" allowed here.

Cron suggestion: every 5 minutes, dry-run; alert if classification != "ok".

Usage::

    python3 scripts/regime_mirror_diag.py
    python3 scripts/regime_mirror_diag.py --apply-overlay-refresh

Author: Claude Opus, 2026-06-02. Observability + safe overlay refresh.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ORCH_STATE = ROOT / "runtime" / "regime" / "orchestrator_state.json"
LAST_SEEN = ROOT / "runtime" / "regime" / "last_seen_regime.txt"
OVERLAY_ENV = ROOT / "configs" / "regime_orchestrator_latest.env"
HEARTBEAT = ROOT / "runtime" / "bot_heartbeat.json"
MIRROR_HEARTBEAT = ROOT / "runtime" / "live_mirror" / "bot_heartbeat.json"
REPORT_OUT = ROOT / "runtime" / "regime_mirror_report.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _file_age_sec(p: Path) -> float | None:
    if not p.exists():
        return None
    try:
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        return (_utc_now() - mtime).total_seconds()
    except Exception:
        return None


def _load_json_safe(p: Path) -> dict[str, Any] | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_env_file(p: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not p.exists():
        return out
    for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _write_overlay(state: dict[str, Any], target: Path) -> None:
    overrides = state.get("strategy_overrides") or {}
    if not isinstance(overrides, dict) or not overrides:
        raise RuntimeError("orchestrator_state.strategy_overrides empty/invalid")
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Auto-refreshed from runtime/regime/orchestrator_state.json by",
        "# scripts/regime_mirror_diag.py --apply-overlay-refresh",
        f"# generated_at: {_utc_now().isoformat()}",
        "",
    ]
    for k, v in sorted(overrides.items()):
        lines.append(f"{k}={v}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Regime mirror chain diagnostic")
    ap.add_argument("--max-orch-age-sec", type=int, default=3900,
                    help="orchestrator_state.json older than this counts as stale (default 65m)")
    ap.add_argument("--max-overlay-age-sec", type=int, default=3900,
                    help="overlay env file older than this counts as stale")
    ap.add_argument("--max-heartbeat-age-sec", type=int, default=300,
                    help="bot heartbeat older than this counts as stale")
    ap.add_argument("--apply-overlay-refresh", action="store_true",
                    help="Rewrite overlay env from orchestrator state if overlay is stale")
    args = ap.parse_args()

    report: dict[str, Any] = {
        "generated_at_utc": _utc_now().isoformat(),
        "thresholds": {
            "max_orch_age_sec": args.max_orch_age_sec,
            "max_overlay_age_sec": args.max_overlay_age_sec,
            "max_heartbeat_age_sec": args.max_heartbeat_age_sec,
        },
        "hops": {},
    }

    # 1. orchestrator state
    orch = _load_json_safe(ORCH_STATE)
    orch_age = _file_age_sec(ORCH_STATE)
    orch_regime = (orch or {}).get("regime") if orch else None
    report["hops"]["orchestrator_state"] = {
        "path": str(ORCH_STATE),
        "exists": ORCH_STATE.exists(),
        "age_sec": orch_age,
        "regime": orch_regime,
        "stale": (orch_age is None) or (orch_age > args.max_orch_age_sec),
    }

    # 2. last_seen_regime.txt
    last_seen_text = LAST_SEEN.read_text(encoding="utf-8").strip() if LAST_SEEN.exists() else None
    report["hops"]["last_seen_regime"] = {
        "path": str(LAST_SEEN),
        "exists": LAST_SEEN.exists(),
        "age_sec": _file_age_sec(LAST_SEEN),
        "value": last_seen_text,
    }

    # 3. overlay env file
    overlay_env = _read_env_file(OVERLAY_ENV)
    overlay_age = _file_age_sec(OVERLAY_ENV)
    overlay_regime = overlay_env.get("ORCH_REGIME")
    report["hops"]["overlay_env"] = {
        "path": str(OVERLAY_ENV),
        "exists": OVERLAY_ENV.exists(),
        "age_sec": overlay_age,
        "orch_regime_value": overlay_regime,
        "key_count": len(overlay_env),
        "stale": (overlay_age is None) or (overlay_age > args.max_overlay_age_sec),
    }

    # 4. bot heartbeat
    heartbeat_path = HEARTBEAT if HEARTBEAT.exists() else MIRROR_HEARTBEAT
    hb = _load_json_safe(heartbeat_path)
    hb_age = _file_age_sec(heartbeat_path)
    hb_regime = (hb or {}).get("regime")
    report["hops"]["heartbeat"] = {
        "path": str(heartbeat_path),
        "exists": heartbeat_path.exists(),
        "age_sec": hb_age,
        "regime": hb_regime,
        "stale": (hb_age is None) or (hb_age > args.max_heartbeat_age_sec),
    }

    # Classification
    issues: list[str] = []
    hops = report["hops"]
    if hops["orchestrator_state"]["stale"]:
        issues.append("orchestrator_cron_dead_or_slow")
    if hops["overlay_env"]["stale"] and not hops["orchestrator_state"]["stale"]:
        issues.append("overlay_writer_dead_orch_fresh")
    if (
        not hops["overlay_env"]["stale"]
        and not hops["heartbeat"]["stale"]
        and hops["overlay_env"]["orch_regime_value"]
        and hb_regime in (None, "", "unknown")
    ):
        issues.append("bot_not_reloading_overlay_env")
    if (
        hb_regime
        and orch_regime
        and hb_regime != "unknown"
        and orch_regime != "unknown"
        and hb_regime != orch_regime
    ):
        issues.append(f"divergence_hb={hb_regime}_orch={orch_regime}")

    report["issues"] = issues
    report["classification"] = "ok" if not issues else issues[0]

    # Optional repair: overlay refresh
    if args.apply_overlay_refresh:
        if hops["overlay_env"]["stale"] and not hops["orchestrator_state"]["stale"] and orch:
            try:
                _write_overlay(orch, OVERLAY_ENV)
                report["overlay_refresh_applied"] = True
            except Exception as exc:
                report["overlay_refresh_error"] = str(exc)[:200]
        else:
            report["overlay_refresh_applied"] = False
            report["overlay_refresh_reason"] = "preconditions_not_met"

    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({
        "classification": report["classification"],
        "issues": issues,
        "orchestrator_regime": orch_regime,
        "overlay_regime": overlay_regime,
        "heartbeat_regime": hb_regime,
        "orch_age_sec": orch_age,
        "overlay_age_sec": overlay_age,
        "heartbeat_age_sec": hb_age,
        "report_path": str(REPORT_OUT),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
