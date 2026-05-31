#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Explain current portfolio allocator state in a compact, operator-friendly way."""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List


ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "runtime" / "control_plane" / "portfolio_allocator_state.json"
DECISIONS_PATH = ROOT / "runtime" / "allocator_decisions.jsonl"
HEARTBEAT_PATHS = [
    ROOT / "runtime" / "heartbeat.json",
    ROOT / "runtime" / "bot_heartbeat.json",
]
RUNTIME_DIAG_PATHS = [
    ROOT / "runtime" / "runtime_diagnostics.json",
    ROOT / "runtime" / "runtime_diag.json",
]


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _load_first_json(paths: Iterable[Path], default: Any) -> Any:
    for path in paths:
        item = _load_json(path, None)
        if item is not None:
            return item
    return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _read_recent_jsonl(path: Path, since_ts: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    try:
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines()[-20000:]:
            raw = raw.strip()
            if not raw:
                continue
            item = json.loads(raw)
            ts = int(float(item.get("ts", item.get("timestamp", 0)) or 0))
            if ts >= since_ts:
                rows.append(item)
    except Exception:
        return rows
    return rows


def _decision_summary(decisions: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    total = approved = blocked = 0
    by_reason: Counter[str] = Counter()
    by_sleeve: Dict[str, Counter[str]] = defaultdict(Counter)
    for item in decisions:
        total += 1
        sleeve = str(item.get("sleeve") or item.get("strategy") or "?")
        result = str(item.get("result") or "").lower()
        approved_flag = item.get("approved")
        if approved_flag is True or result == "approved":
            approved += 1
            by_sleeve[sleeve]["approved"] += 1
        else:
            blocked += 1
            reason = str(item.get("block_reason") or item.get("reason") or "unknown")
            by_reason[reason] += 1
            by_sleeve[sleeve][reason] += 1
    return {
        "total": total,
        "approved": approved,
        "blocked": blocked,
        "top_reasons": by_reason.most_common(8),
        "by_sleeve": by_sleeve,
    }


def _fmt_bool(value: Any) -> str:
    return "yes" if bool(value) else "no"


def _short_list(values: Any, limit: int = 5) -> str:
    if not isinstance(values, list):
        return "-"
    items = [str(x) for x in values if str(x)]
    suffix = "" if len(items) <= limit else f" +{len(items) - limit}"
    return ",".join(items[:limit]) + suffix if items else "-"


def main() -> int:
    ap = argparse.ArgumentParser(description="Diagnose portfolio allocator live state.")
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--state", default=str(STATE_PATH))
    ap.add_argument("--decisions", default=str(DECISIONS_PATH))
    args = ap.parse_args()

    state_path = Path(args.state).expanduser()
    decisions_path = Path(args.decisions).expanduser()
    state = _load_json(state_path, {})
    heartbeat = _load_first_json(HEARTBEAT_PATHS, {})
    runtime_diag = _load_first_json(RUNTIME_DIAG_PATHS, {})
    now_ts = int(time.time())
    decisions = _read_recent_jsonl(decisions_path, now_ts - int(args.hours * 3600))
    summary = _decision_summary(decisions)

    print("Allocator diagnostic")
    print(f"state_path: {state_path}")
    print(f"state_exists: {_fmt_bool(bool(state))}")
    if not state:
        print("verdict: missing allocator state; control-plane builder is not running or path is wrong")
        return 2

    mode = state.get("allocator_mode", "?")
    effective = state.get("allocator_effective_mode", "?")
    strength = state.get("haircut_strength", "?")
    equity = state.get("effective_equity_usd")
    print(
        "summary: "
        f"status={state.get('status')} safe={int(bool(state.get('safe_mode')))} "
        f"hard_block={int(bool(state.get('hard_block_new_entries')))} "
        f"mode={mode}->{effective} haircut_strength={strength} "
        f"equity={equity} source={state.get('equity_source', '-')}"
    )
    print(
        "risk: "
        f"global={_safe_float(state.get('allocator_global_risk_mult'), 0.0):.4f} "
        f"base={_safe_float(state.get('base_global_risk_mult'), 0.0):.4f} "
        f"overlap={_safe_float(state.get('portfolio_overlap_ratio'), 0.0):.4f} "
        f"overlap_mult={_safe_float(state.get('portfolio_overlap_mult'), 1.0):.4f} "
        f"raw={_safe_float(state.get('raw_portfolio_overlap_mult'), 1.0):.4f}"
    )
    print(
        "heartbeat: "
        f"status={heartbeat.get('status', '-')} open={heartbeat.get('open_trades', '-')} "
        f"dry_run={heartbeat.get('dry_run', '-')} equity={heartbeat.get('effective_equity', '-')}"
    )
    print(f"safe_reasons: {';'.join(state.get('safe_mode_reasons') or []) or '-'}")
    print(f"degraded_reasons: {';'.join(state.get('degraded_reasons') or []) or '-'}")

    sleeves = dict(state.get("sleeves") or {})
    print("\nSleeves")
    print(f"{'name':<16} {'en':<3} {'risk':>7} {'base':>7} {'health':<6} {'count':>5} {'ovlp':>6} {'raw':>6} symbols")
    for name, item in sorted(
        sleeves.items(),
        key=lambda kv: -_safe_float(kv[1].get("final_risk_mult"), 0.0),
    ):
        print(
            f"{name:<16} {int(bool(item.get('enabled'))):<3} "
            f"{_safe_float(item.get('final_risk_mult'), 0.0):>7.3f} "
            f"{_safe_float(item.get('base_risk_mult'), 0.0):>7.3f} "
            f"{str(item.get('health_status') or '-'):<6} "
            f"{int(item.get('symbol_count') or 0):>5} "
            f"{_safe_float(item.get('overlap_mult'), 1.0):>6.3f} "
            f"{_safe_float(item.get('raw_overlap_mult'), 1.0):>6.3f} "
            f"{_short_list(item.get('symbols'))}"
        )
        notes = [str(x) for x in (item.get("notes") or []) if str(x)]
        if notes:
            print(f"{'':<16} notes: {'; '.join(notes[:4])}")

    print(f"\nDecisions last {args.hours:g}h: total={summary['total']} approved={summary['approved']} blocked={summary['blocked']}")
    if summary["top_reasons"]:
        print("Top block reasons:")
        for reason, count in summary["top_reasons"]:
            print(f"  {reason}: {count}")
    else:
        print("Top block reasons: no decision trace available yet")

    counters = None
    if isinstance(runtime_diag, dict):
        counters = runtime_diag.get("runtime_counters") or runtime_diag.get("counters")
    if isinstance(counters, dict):
        interesting = {
            key: counters.get(key)
            for key in sorted(counters)
            if (
                key.endswith("_try")
                or key.endswith("_no_signal")
                or key.endswith("_skip_cooldown")
                or key.endswith("_skip_disabled")
            )
            and counters.get(key)
        }
        if interesting:
            print("\nRuntime strategy counters")
            for key, value in list(interesting.items())[:80]:
                print(f"  {key}: {value}")

    verdict = "ok"
    if state.get("safe_mode") or state.get("hard_block_new_entries"):
        verdict = "hard_blocked_by_safe_mode"
    elif summary["total"] > 0 and summary["approved"] == 0:
        verdict = "allocator_or_strategy_gate_blocks_all_decisions"
    elif summary["total"] == 0:
        verdict = "no_decision_trace_yet"
    elif summary["approved"] > 0:
        verdict = "allocator_allows_entries_no_hard_block"
    print(f"verdict: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
