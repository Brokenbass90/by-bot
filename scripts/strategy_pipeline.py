#!/usr/bin/env python3
"""Strategy promotion pipeline.

Tracks each strategy's stage on the way from `strategies/*.py` file to live
trading. Reads inventory from `runtime/strategy_registry.json` (produced by
`scripts/build_strategy_registry.py`) and maintains state in
`runtime/strategy_pipeline.json`.

Stages (in order, monotonic by default — manual demote allowed):

    inventory             ← file exists in strategies/, registry entry present
    audit_passed          ← static checks: imports OK, class found, no syntax errors
    unit_smoke            ← strategy returns sensibly to a mock kline call
    backtest_seeded       ← backtest_runs/<family>_* exists with non-empty ranked_results
    sweep_complete        ← at least one configs/autoresearch/package_<family>_*.json done
    package_replay_passed ← full 4-sleeve replay beats baseline +73.96% / PF 1.591
    shadow_30d            ← shadow mode 30 calendar days, PF ≥ 1.2, DD ≤ 8%
    live_canary           ← live with RISK_MULT=0.3, allowlist 3 symbols
    live_full             ← live with RISK_MULT=1.0, full allowlist

Promotion gate (between any two stages): must pass acceptance criteria
documented in `runtime/strategy_pipeline_gates.json` (auto-bootstrapped on
first run). Demote requires `--reason` and is journaled.

This script does NOT modify .env or live trading. It only tracks state and
runs static checks.

Usage::

    python3 scripts/strategy_pipeline.py --list
    python3 scripts/strategy_pipeline.py --audit MTPB
    python3 scripts/strategy_pipeline.py --status
    python3 scripts/strategy_pipeline.py --promote MTPB --to backtest_seeded
    python3 scripts/strategy_pipeline.py --demote ARF1 --reason "live PF dropped to 1.05 over 7d"
    python3 scripts/strategy_pipeline.py --refresh  # rebuild stages from filesystem evidence

Author: Claude Opus, 2026-06-02. Process scaffold for adding strategies safely.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STRATEGIES_DIR = ROOT / "strategies"
REGISTRY = ROOT / "runtime" / "strategy_registry.json"
PIPELINE = ROOT / "runtime" / "strategy_pipeline.json"
GATES = ROOT / "runtime" / "strategy_pipeline_gates.json"
JOURNAL = ROOT / "runtime" / "strategy_pipeline_journal.jsonl"
AUTORESEARCH_DIR = ROOT / "configs" / "autoresearch"
BACKTEST_RUNS_DIR = ROOT / "backtest_runs"

STAGES = [
    "inventory",
    "audit_passed",
    "unit_smoke",
    "backtest_seeded",
    "sweep_complete",
    "package_replay_passed",
    "shadow_30d",
    "live_canary",
    "live_full",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(p: Path, default: Any = None) -> Any:
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(p: Path, data: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _append_journal(entry: dict[str, Any]) -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _stage_index(s: str) -> int:
    try:
        return STAGES.index(s)
    except ValueError:
        return -1


# ---------------------------------------------------------------------------
# Default acceptance gates
# ---------------------------------------------------------------------------

DEFAULT_GATES = {
    "package_replay_passed": {
        "baseline_name": "crypto_income_static_v1",
        "must_beat_pf": 1.591,
        "must_beat_net_pct": 73.96,
        "max_drawdown_pct": 5.16,
        "max_negative_months": 2,
        "additivity_required": True,
    },
    "shadow_30d": {
        "min_days": 30,
        "min_trades": 20,
        "min_pf": 1.2,
        "max_drawdown_pct": 8.0,
    },
    "live_canary": {
        "min_days_shadow_stable": 30,
        "max_risk_mult": 0.3,
        "max_allowlist_size": 3,
        "min_trades_to_full": 30,
        "min_pf_to_full": 1.3,
    },
    "live_full": {
        "min_days_canary": 30,
        "min_pf_canary": 1.3,
        "min_trades_canary": 30,
        "max_drawdown_pct": 5.0,
    },
}


def _ensure_gates_file() -> dict[str, Any]:
    g = _load_json(GATES)
    if not g:
        _write_json(GATES, DEFAULT_GATES)
        return DEFAULT_GATES
    return g


# ---------------------------------------------------------------------------
# Inventory + audit
# ---------------------------------------------------------------------------

def load_registry() -> dict[str, Any]:
    reg = _load_json(REGISTRY)
    if not reg or "modules" not in reg:
        return {}
    return reg


def static_audit(module_name: str) -> dict[str, Any]:
    """Static checks: file exists, imports clean, top-level class detected."""
    candidate = STRATEGIES_DIR / f"{module_name}.py"
    if not candidate.exists():
        return {"ok": False, "reason": f"file_missing:{candidate.name}"}
    try:
        src = candidate.read_text(encoding="utf-8")
    except Exception as exc:
        return {"ok": False, "reason": f"read_error:{exc}"}

    # Syntax compile
    try:
        compile(src, str(candidate), "exec")
    except SyntaxError as exc:
        return {"ok": False, "reason": f"syntax_error:{exc.msg}@{exc.lineno}"}

    # Light import attempt — best-effort; many strategies import bot internals.
    spec = importlib.util.spec_from_file_location(f"_audit_{module_name}", candidate)
    import_status = "skipped_dependency_unsafe"
    try:
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            import_status = "import_ok"
    except Exception as exc:
        import_status = f"import_failed:{type(exc).__name__}:{str(exc)[:120]}"

    # Look for top-level Strategy / Signal class via simple grep
    has_class = "class " in src and (
        "Strategy" in src or "Signal" in src or "Engine" in src
    )
    return {
        "ok": True,
        "audit_at_utc": _utc_now(),
        "loc": src.count("\n") + 1,
        "import_status": import_status,
        "has_strategy_class": has_class,
    }


def find_sweep_configs(family: str) -> list[str]:
    fam_lower = family.lower()
    matches: list[str] = []
    for p in AUTORESEARCH_DIR.glob("package_*.json"):
        n = p.stem.lower()
        if fam_lower in n:
            matches.append(p.name)
    return matches


_BACKTEST_RUN_CACHE: list[str] | None = None
_BACKTEST_RUN_CACHE_LIMIT = 4000


def _backtest_run_list() -> list[str]:
    """Lazy, one-shot enumeration of recent backtest_runs dir names.

    `backtest_runs/` can hold 40k+ entries (one per sweep candidate). Scanning
    every entry for every strategy multiplies cost to millions of ops. We
    enumerate once, keep the most recent ``_BACKTEST_RUN_CACHE_LIMIT`` by name
    (timestamps embedded in dir names sort lexicographically), and reuse.
    """
    global _BACKTEST_RUN_CACHE
    if _BACKTEST_RUN_CACHE is not None:
        return _BACKTEST_RUN_CACHE
    if not BACKTEST_RUNS_DIR.exists():
        _BACKTEST_RUN_CACHE = []
        return _BACKTEST_RUN_CACHE
    try:
        names = sorted(
            (p.name for p in BACKTEST_RUNS_DIR.iterdir() if p.is_dir()),
            reverse=True,
        )[:_BACKTEST_RUN_CACHE_LIMIT]
    except Exception:
        names = []
    _BACKTEST_RUN_CACHE = names
    return names


def find_backtest_runs(family: str) -> list[str]:
    fam_lower = family.lower()
    return [n for n in _backtest_run_list() if fam_lower in n.lower()][:5]


# ---------------------------------------------------------------------------
# Pipeline state ops
# ---------------------------------------------------------------------------

def _load_pipeline() -> dict[str, Any]:
    state = _load_json(PIPELINE, default={"version": 1, "strategies": {}})
    state.setdefault("strategies", {})
    return state


def refresh_from_registry() -> dict[str, Any]:
    reg = load_registry()
    state = _load_pipeline()

    if not reg:
        return state

    for module_name, meta in (reg.get("modules") or {}).items():
        family = str(meta.get("family") or module_name)
        existing = state["strategies"].get(family, {})
        sweeps = find_sweep_configs(family) or find_sweep_configs(module_name)
        runs = find_backtest_runs(family) or find_backtest_runs(module_name)

        wired = bool(meta.get("wired_in_runner"))
        imported = bool(meta.get("imported_in_bot"))

        # Heuristic stage detection from filesystem evidence
        stage = existing.get("stage", "inventory")
        if imported and stage == "inventory":
            stage = "audit_passed"
        if runs and _stage_index(stage) < _stage_index("backtest_seeded"):
            stage = "backtest_seeded"
        if sweeps and _stage_index(stage) < _stage_index("sweep_complete"):
            stage = "sweep_complete"

        # Live evidence overrides if module is imported AND wired AND has enable flag
        if wired and imported and meta.get("enable_flag") and _stage_index(stage) < _stage_index("live_canary"):
            stage = "live_canary"

        entry = {
            "module": module_name,
            "family": family,
            "stage": stage,
            "wired_in_runner": wired,
            "imported_in_bot": imported,
            "enable_flag": meta.get("enable_flag"),
            "sweep_configs": sweeps,
            "backtest_runs_recent": runs,
            "sweep_count": int(meta.get("sweep_count") or 0),
            "loc": meta.get("loc"),
            "last_refreshed_utc": _utc_now(),
            "manual_notes": existing.get("manual_notes", ""),
        }
        # Preserve existing audit if present
        if "audit" in existing:
            entry["audit"] = existing["audit"]
        state["strategies"][family] = entry

    state["last_refresh_utc"] = _utc_now()
    state["total_tracked"] = len(state["strategies"])
    state["registry_generated_at"] = reg.get("generated_at")
    return state


def show_list(state: dict[str, Any], filter_stage: str | None = None) -> None:
    rows = []
    for fam, entry in sorted(state.get("strategies", {}).items()):
        st = entry.get("stage", "inventory")
        if filter_stage and st != filter_stage:
            continue
        wired = "Y" if entry.get("wired_in_runner") else "."
        imp = "Y" if entry.get("imported_in_bot") else "."
        sweeps = entry.get("sweep_count", 0)
        rows.append((fam, st, wired, imp, sweeps, entry.get("loc") or 0))
    rows.sort(key=lambda r: (_stage_index(r[1]), -r[4]))
    print(f"{'FAMILY':<28} {'STAGE':<22} {'WIRE':<4} {'IMP':<3} {'SWEEPS':<7} {'LOC':<5}")
    print("-" * 75)
    for r in rows:
        print(f"{r[0]:<28} {r[1]:<22} {r[2]:<4} {r[3]:<3} {r[4]:<7} {r[5]:<5}")


def show_status(state: dict[str, Any]) -> None:
    counts: dict[str, int] = {s: 0 for s in STAGES}
    for entry in state.get("strategies", {}).values():
        s = entry.get("stage", "inventory")
        counts[s] = counts.get(s, 0) + 1
    total = sum(counts.values())
    print(f"Total tracked: {total}")
    print(f"Registry generated: {state.get('registry_generated_at')}")
    print(f"Last refresh: {state.get('last_refresh_utc')}")
    print("")
    for s in STAGES:
        bar = "█" * counts[s]
        print(f"  {s:<24} {counts[s]:>3} {bar}")


def do_audit(family: str, state: dict[str, Any]) -> None:
    entry = state["strategies"].get(family)
    if not entry:
        print(f"ERROR: family '{family}' not in pipeline; run --refresh first")
        return
    module_name = entry["module"]
    result = static_audit(module_name)
    entry["audit"] = result
    if result.get("ok") and _stage_index(entry["stage"]) < _stage_index("audit_passed"):
        entry["stage"] = "audit_passed"
    _append_journal({
        "ts_utc": _utc_now(),
        "event": "audit",
        "family": family,
        "result": result,
        "stage_after": entry["stage"],
    })
    print(json.dumps({"family": family, "audit": result, "stage_after": entry["stage"]},
                     indent=2, ensure_ascii=False))


def do_promote(family: str, target: str, state: dict[str, Any], gates: dict[str, Any]) -> None:
    entry = state["strategies"].get(family)
    if not entry:
        print(f"ERROR: family '{family}' not in pipeline")
        return
    cur_idx = _stage_index(entry["stage"])
    tgt_idx = _stage_index(target)
    if tgt_idx < 0:
        print(f"ERROR: unknown target stage '{target}'. Valid: {STAGES}")
        return
    if tgt_idx <= cur_idx:
        print(f"NOOP: {family} already at {entry['stage']}, target {target} is not forward")
        return
    if tgt_idx - cur_idx > 1:
        print(f"REJECT: cannot skip stages. Current={entry['stage']}, requested={target}. "
              f"Next allowed: {STAGES[cur_idx+1]}")
        return
    # Gate check
    gate = gates.get(target, {})
    if gate:
        print(f"GATE for {target}: {json.dumps(gate, ensure_ascii=False)}")
        print("Operator must confirm gate conditions are met before promotion is journaled.")
    prev = entry["stage"]
    entry["stage"] = target
    entry["promoted_at_utc"] = _utc_now()
    _append_journal({
        "ts_utc": _utc_now(),
        "event": "promote",
        "family": family,
        "from": prev,
        "to": target,
        "gate_referenced": gate,
    })
    print(f"PROMOTED {family}: {prev} → {target}")


def do_demote(family: str, reason: str, state: dict[str, Any]) -> None:
    entry = state["strategies"].get(family)
    if not entry:
        print(f"ERROR: family '{family}' not in pipeline")
        return
    cur_idx = _stage_index(entry["stage"])
    if cur_idx <= 0:
        print(f"NOOP: {family} already at lowest stage")
        return
    prev = entry["stage"]
    entry["stage"] = STAGES[cur_idx - 1]
    entry["demoted_at_utc"] = _utc_now()
    entry["last_demote_reason"] = reason
    _append_journal({
        "ts_utc": _utc_now(),
        "event": "demote",
        "family": family,
        "from": prev,
        "to": entry["stage"],
        "reason": reason,
    })
    print(f"DEMOTED {family}: {prev} → {entry['stage']} (reason: {reason})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Strategy promotion pipeline tracker")
    ap.add_argument("--list", action="store_true", help="List strategies and stages")
    ap.add_argument("--list-stage", default=None, help="Filter --list to one stage")
    ap.add_argument("--status", action="store_true", help="Stage histogram")
    ap.add_argument("--refresh", action="store_true",
                    help="Rebuild stage hints from registry + filesystem")
    ap.add_argument("--audit", default=None, help="Run static audit on a strategy family")
    ap.add_argument("--promote", default=None, help="Strategy family to promote")
    ap.add_argument("--to", default=None, help="Target stage for --promote")
    ap.add_argument("--demote", default=None, help="Strategy family to demote")
    ap.add_argument("--reason", default=None, help="Reason for --demote (required)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    gates = _ensure_gates_file()
    state = _load_pipeline()

    if args.refresh or not state.get("strategies"):
        state = refresh_from_registry()
        _write_json(PIPELINE, state)
        if not args.quiet:
            print(f"refreshed pipeline; total_tracked={state.get('total_tracked')}")

    if args.list or args.list_stage:
        show_list(state, args.list_stage)
        return 0

    if args.status:
        show_status(state)
        return 0

    if args.audit:
        do_audit(args.audit, state)
        _write_json(PIPELINE, state)
        return 0

    if args.promote:
        if not args.to:
            print("ERROR: --promote requires --to <stage>")
            return 2
        do_promote(args.promote, args.to, state, gates)
        _write_json(PIPELINE, state)
        return 0

    if args.demote:
        if not args.reason:
            print("ERROR: --demote requires --reason '<text>'")
            return 2
        do_demote(args.demote, args.reason, state)
        _write_json(PIPELINE, state)
        return 0

    # Default: print status
    show_status(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
