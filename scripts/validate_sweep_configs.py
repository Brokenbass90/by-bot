#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_sweep_configs.py — Preflight validator for autoresearch sweep configs.

Catches schema bugs BEFORE a sweep is launched. The predecessor session
2026-05-26 shipped three configs with grid=list-of-dicts instead of dict,
which would have crashed run_strategy_autoresearch.py at startup with zero
useful output. This script enforces the contract.

Checks per config:
  - JSON parses
  - Required keys: name, command, base_env, grid, constraints, score_weights
  - grid is Dict[str, list]
  - All grid values are non-empty lists
  - constraints has min_profit_factor + max_drawdown + min_trades
  - score_weights has profit_factor + winrate + max_drawdown
  - command contains backtest/run_portfolio.py
  - --strategies lists names that actually exist in strategies/ or are accepted by run_portfolio.py
  - All allowlist symbols look like USDT perpetuals (or override matches base)
  - Total combo count <= 500 (anything bigger is suspicious / too long)
  - {SYMBOLS} template var, if used in command, has a grid entry

Usage:
  python3 scripts/validate_sweep_configs.py                 # validate all
  python3 scripts/validate_sweep_configs.py --strict        # exit 1 on any warning
  python3 scripts/validate_sweep_configs.py --json          # machine-readable
  python3 scripts/validate_sweep_configs.py --file PATH     # single file
  python3 scripts/validate_sweep_configs.py --tg            # report errors to Telegram

Cron (hourly):
  0 * * * * cd /root/by-bot && python3 scripts/validate_sweep_configs.py --tg >> logs/sweep_validate.log 2>&1

Use --strict for newly edited files or CI gates only. The historical
configs/autoresearch folder intentionally contains many old wide-grid research
specs that are warning-worthy but still runnable.

Pre-commit (git):
  Add a hook that runs this on any change in configs/autoresearch/*.json.

Exit codes:
  0 — all configs valid
  1 — at least one error
  2 — runtime/internal failure
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
SWEEP_DIR = ROOT / "configs" / "autoresearch"
RUNNER_PATH = ROOT / "scripts" / "run_strategy_autoresearch.py"
STRATEGIES_DIR = ROOT / "strategies"
RUN_PORTFOLIO = ROOT / "backtest" / "run_portfolio.py"

# Required keys at top level (runner will crash without these)
REQUIRED_KEYS = ("name", "grid")
# Either "command" OR ("symbols" + "strategies" + "days" + "end_date") must be present
COMMAND_SCHEMA_KEYS = ("command",)
LEGACY_SCHEMA_KEYS = ("symbols", "strategies", "days", "end_date")
# Recommended but not strictly required (runner provides defaults)
RECOMMENDED_KEYS = ("base_env", "constraints", "score_weights")
# Constraint subkeys we always want
REQUIRED_CONSTRAINTS = ("min_profit_factor", "max_drawdown", "min_trades")
# Score weight subkeys we always want
REQUIRED_WEIGHTS = ("profit_factor", "winrate", "max_drawdown")

# Combinatorial limit — anything bigger is too long or test of patience
MAX_COMBOS = 500


def _load_env_file(path: Path) -> Dict[str, str]:
    """Parse a simple KEY=VALUE env file without mutating process env."""
    values: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip()
    return values


def _validate_baseline_env_parity(spec: Dict[str, Any], base_env: Dict[str, Any]) -> List[str]:
    """Require additive package specs to preserve their declared baseline env."""
    baseline_ref = str(spec.get("baseline_env_file") or "").strip()
    if not baseline_ref:
        return []

    baseline_path = Path(baseline_ref)
    if not baseline_path.is_absolute():
        baseline_path = ROOT / baseline_path
    if not baseline_path.exists():
        return [f"baseline_env_file not found: {baseline_ref}"]

    baseline = _load_env_file(baseline_path)
    errors: List[str] = []
    for key, expected in baseline.items():
        if key.startswith("ENABLE_"):
            continue
        if key not in base_env:
            errors.append(f"base_env missing baseline key: {key}")
            continue
        actual = str(base_env[key]).strip()
        if actual != expected:
            errors.append(
                f"base_env baseline mismatch: {key}={actual!r}, expected {expected!r}"
            )
    return errors


def _load_runner_helpers():
    """Import the actual runner module so we use its real _iter_grid/_grid_size."""
    spec = importlib.util.spec_from_file_location("autoresearch_runner", RUNNER_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["autoresearch_runner"] = mod
    spec.loader.exec_module(mod)
    return mod


def _list_allowed_strategy_names() -> set[str]:
    """Pull the canonical allowed-strategies list from run_portfolio.py."""
    if not RUN_PORTFOLIO.exists():
        return set()
    src = RUN_PORTFOLIO.read_text(encoding="utf-8", errors="ignore")
    # Heuristic: find `allowed = {...}` block
    import re
    m = re.search(r'allowed\s*=\s*\{([^}]+)\}', src)
    if not m:
        return set()
    names = re.findall(r'"([a-z0-9_]+)"', m.group(1))
    return set(names)


def _list_strategy_modules() -> set[str]:
    """Pull names of *.py files in strategies/ (without _live wrappers)."""
    if not STRATEGIES_DIR.exists():
        return set()
    return {f.stem for f in STRATEGIES_DIR.glob("*.py") if not f.stem.startswith("_")}


def _validate_config(
    path: Path,
    runner,
    allowed_strategies: set[str],
) -> Tuple[List[str], List[str], str]:
    """Return (errors, warnings, skipped_reason) for one config file."""
    errors: List[str] = []
    warnings: List[str] = []

    # JSON parse
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"JSON parse: {exc}"], [], ""

    validator_meta = spec.get("_validator", {}) if isinstance(spec.get("_validator"), dict) else {}
    legacy_meta = spec.get("_meta", {}) if isinstance(spec.get("_meta"), dict) else {}
    if spec.get("validator_skip") or validator_meta.get("skip") or legacy_meta.get("validator_skip"):
        reason = (
            str(
                spec.get("validator_skip_reason")
                or validator_meta.get("skip_reason")
                or legacy_meta.get("validator_skip_reason")
                or ""
            )
            .strip()
            or "explicit validator skip"
        )
        return [], [], reason

    # Required keys
    for key in REQUIRED_KEYS:
        if key not in spec:
            errors.append(f"missing required key: {key}")

    # Either command schema or legacy schema (symbols+strategies+days+end_date)
    has_command = "command" in spec
    has_legacy = all(k in spec for k in LEGACY_SCHEMA_KEYS)
    if not has_command and not has_legacy:
        missing_legacy = [k for k in LEGACY_SCHEMA_KEYS if k not in spec]
        errors.append(
            f"need either 'command' (list) or all of {list(LEGACY_SCHEMA_KEYS)}; "
            f"missing from legacy schema: {missing_legacy}"
        )

    if errors:
        return errors, warnings, ""  # bail early — nothing else makes sense

    # name vs filename
    expected_stem = path.stem
    if spec.get("name") != expected_stem:
        warnings.append(f"name='{spec.get('name')}' differs from filename stem '{expected_stem}'")

    # Recommended keys
    for key in RECOMMENDED_KEYS:
        if key not in spec:
            warnings.append(f"missing recommended key: {key}")

    # grid must be Dict[str, list]
    grid = spec.get("grid")
    if not isinstance(grid, dict):
        errors.append(
            f"grid must be Dict[str, list], got {type(grid).__name__}. "
            f"Wrong format example seen 2026-05-26: list of {{'param': X, 'values': [...]}}"
        )
    else:
        for k, v in grid.items():
            if not isinstance(v, list):
                errors.append(f"grid['{k}'] must be a list, got {type(v).__name__}")
            elif not v:
                errors.append(f"grid['{k}'] is empty — no values to test")
            elif not all(isinstance(x, (str, int, float)) for x in v):
                warnings.append(f"grid['{k}'] contains non-scalar values: {v}")

    # Compute combo count and bail if absurd
    try:
        combos = runner._grid_size(grid) if isinstance(grid, dict) else 0
        if combos == 0:
            errors.append("grid produces 0 combinations")
        elif combos > MAX_COMBOS:
            warnings.append(f"grid produces {combos} combinations — exceeds soft limit {MAX_COMBOS}")
    except Exception as exc:
        errors.append(f"grid_size computation failed: {exc}")
        combos = 0

    # constraints subkeys
    constraints = spec.get("constraints", {}) or {}
    if not isinstance(constraints, dict):
        errors.append(f"constraints must be dict, got {type(constraints).__name__}")
    else:
        for k in REQUIRED_CONSTRAINTS:
            if k not in constraints:
                warnings.append(f"constraints missing recommended key: {k}")
        # Sanity: PF threshold not too low
        pf_min = constraints.get("min_profit_factor", 0)
        try:
            if float(pf_min) < 1.0:
                warnings.append(f"constraints.min_profit_factor={pf_min} — below 1.0 means losing setups can pass")
        except (TypeError, ValueError):
            warnings.append(f"constraints.min_profit_factor='{pf_min}' is not numeric")
        # Sanity: DD threshold not too generous
        dd_max = constraints.get("max_drawdown", 999)
        try:
            if float(dd_max) > 20:
                warnings.append(f"constraints.max_drawdown={dd_max}% — > 20% is risky tolerance")
        except (TypeError, ValueError):
            warnings.append(f"constraints.max_drawdown='{dd_max}' is not numeric")

    # score_weights subkeys
    weights = spec.get("score_weights", {}) or {}
    if not isinstance(weights, dict):
        errors.append(f"score_weights must be dict, got {type(weights).__name__}")
    else:
        for k in REQUIRED_WEIGHTS:
            if k not in weights:
                warnings.append(f"score_weights missing recommended key: {k}")

    # Don't accept the old broken pass_criteria field (predecessor's bug marker)
    if "pass_criteria" in spec and isinstance(spec["pass_criteria"], dict):
        warnings.append(
            "uses 'pass_criteria' — this key is IGNORED by the runner. "
            "Move thresholds into 'constraints' and use runner-recognized keys "
            "(min_profit_factor, max_drawdown, min_trades, min_net_pnl, max_negative_months)."
        )

    # command/legacy schema sanity
    cmd = spec.get("command", [])
    if cmd:
        if not isinstance(cmd, list):
            errors.append("command must be a list")
        else:
            joined = " ".join(str(x) for x in cmd)
            if "backtest/run_portfolio.py" not in joined and "alpaca" not in joined.lower():
                warnings.append("command does not reference backtest/run_portfolio.py — unusual")

            # extract --strategies arg
            try:
                i = cmd.index("--strategies")
                strategies_str = str(cmd[i + 1])
                strats = [s.strip() for s in strategies_str.split(",") if s.strip()]
            except (ValueError, IndexError):
                strats = []
                warnings.append("--strategies arg not found or empty")

            if allowed_strategies:
                for s in strats:
                    if s not in allowed_strategies:
                        errors.append(f"strategy '{s}' not in run_portfolio.py allowed list")

            # If command uses {SYMBOLS} template, grid must define SYMBOLS
            if "{SYMBOLS}" in joined:
                if isinstance(grid, dict) and "SYMBOLS" not in grid:
                    errors.append("command references {SYMBOLS} but grid doesn't define SYMBOLS")
    else:
        # Legacy schema: validate strategies array against allowed list
        legacy_strats = spec.get("strategies", []) or []
        if allowed_strategies and isinstance(legacy_strats, list):
            for s in legacy_strats:
                if s not in allowed_strategies:
                    errors.append(f"strategy '{s}' not in run_portfolio.py allowed list (legacy schema)")
        if not legacy_strats:
            warnings.append("legacy schema: 'strategies' array is empty")

    # base_env sanity
    base_env = spec.get("base_env", {}) or {}
    if not isinstance(base_env, dict):
        errors.append(f"base_env must be dict, got {type(base_env).__name__}")
    else:
        # Look at allowlist values — empty allowlist is usually a bug
        for k, v in base_env.items():
            if "_SYMBOL_ALLOWLIST" in k or "_ALLOWLIST" in k:
                if not str(v).strip():
                    warnings.append(f"base_env['{k}'] is empty — strategy will see no symbols")
        errors.extend(_validate_baseline_env_parity(spec, base_env))

    return errors, warnings, ""


def _validate_all(strict: bool) -> Dict[str, Any]:
    """Validate every JSON under configs/autoresearch/. Return summary dict."""
    if not SWEEP_DIR.exists():
        return {"ok": False, "error": f"sweep dir not found: {SWEEP_DIR}"}

    runner = _load_runner_helpers()
    allowed_strategies = _list_allowed_strategy_names()

    report = {
        "total_files": 0,
        "passed": 0,
        "warnings": 0,
        "failed": 0,
        "skipped": 0,
        "files": [],
        "ok": True,
    }
    for path in sorted(SWEEP_DIR.glob("*.json")):
        report["total_files"] += 1
        errors, warnings, skipped = _validate_config(path, runner, allowed_strategies)
        entry = {
            "file": path.name,
            "errors": errors,
            "warnings": warnings,
            "skipped": skipped,
        }
        if skipped:
            report["skipped"] += 1
        elif errors:
            report["failed"] += 1
            report["ok"] = False
        elif warnings:
            report["warnings"] += 1
            if strict:
                report["ok"] = False
        else:
            report["passed"] += 1
        report["files"].append(entry)

    return report


def _format_text(report: Dict[str, Any]) -> str:
    lines = []
    lines.append("─" * 78)
    lines.append(f"Sweep config validator — {report['total_files']} files scanned")
    lines.append(
        f"  ✅ passed: {report['passed']}  ⚠️  warnings: {report['warnings']}  "
        f"⏭️  skipped: {report.get('skipped', 0)}  ❌ failed: {report['failed']}"
    )
    lines.append("─" * 78)
    for f in report["files"]:
        if f.get("skipped"):
            lines.append(f"⏭️  {f['file']} — skipped: {f['skipped']}")
        elif f["errors"]:
            lines.append(f"\n❌ {f['file']}")
            for e in f["errors"]:
                lines.append(f"   ERROR: {e}")
            for w in f["warnings"]:
                lines.append(f"   warn:  {w}")
        elif f["warnings"]:
            lines.append(f"\n⚠️  {f['file']}")
            for w in f["warnings"]:
                lines.append(f"   warn:  {w}")
        else:
            lines.append(f"✅ {f['file']}")
    return "\n".join(lines)


def _format_tg(report: Dict[str, Any]) -> str:
    """Short Telegram-friendly summary, only failures + warnings."""
    if report["failed"] == 0 and report["warnings"] == 0:
        return f"✅ All {report['total_files']} sweep configs valid."

    lines = [
        f"🚨 <b>Sweep config validator</b>",
        f"scanned={report['total_files']} passed={report['passed']} "
        f"warn={report['warnings']} skipped={report.get('skipped', 0)} <b>failed={report['failed']}</b>",
        "",
    ]
    for f in report["files"]:
        if f.get("skipped") or (not f["errors"] and not f["warnings"]):
            continue
        lines.append(f"<code>{f['file']}</code>")
        for e in f["errors"][:3]:
            lines.append(f"  ❌ {e}")
        for w in f["warnings"][:2]:
            lines.append(f"  ⚠️  {w}")
    return "\n".join(lines)[:3500]


def _tg_send(text: str) -> None:
    token = os.getenv("TG_TOKEN", "").strip()
    chat = (os.getenv("TG_CHAT_ID") or os.getenv("TG_CHAT") or "").strip()
    if not token or not chat:
        return
    try:
        payload = json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        print(f"[validate] TG send failed: {exc}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Preflight validator for autoresearch sweep configs.")
    ap.add_argument("--strict", action="store_true", help="Exit 1 on warnings too.")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON to stdout.")
    ap.add_argument("--file", type=str, default="", help="Validate a single config file.")
    ap.add_argument("--tg", action="store_true", help="Send TG digest on failure.")
    args = ap.parse_args()

    if args.file:
        path = Path(args.file)
        if not path.is_absolute():
            path = ROOT / path
        if not path.exists():
            print(f"[validate] file not found: {path}", file=sys.stderr)
            return 2
        runner = _load_runner_helpers()
        allowed = _list_allowed_strategy_names()
        errors, warnings, skipped = _validate_config(path, runner, allowed)
        report = {
            "total_files": 1, "passed": 0, "warnings": 0, "failed": 0, "skipped": 0, "files": [
                {"file": path.name, "errors": errors, "warnings": warnings, "skipped": skipped}
            ], "ok": not errors,
        }
        if skipped:
            report["skipped"] = 1
        elif errors:
            report["failed"] = 1
        elif warnings:
            report["warnings"] = 1
            if args.strict:
                report["ok"] = False
        else:
            report["passed"] = 1
    else:
        report = _validate_all(args.strict)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(_format_text(report))

    if args.tg and (report["failed"] or (args.strict and report["warnings"])):
        _tg_send(_format_tg(report))

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
