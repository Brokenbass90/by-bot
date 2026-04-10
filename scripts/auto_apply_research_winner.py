#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_apply_research_winner.py — Self-optimization module (Phase 3.1)

Scans autoresearch ranked_results.csv files, finds runs that passed
all constraints and have a score above the threshold, and automatically
applies their parameters to the live config override file.

Flow:
  1. Scan one or more research roots for all ranked_results.csv
  2. Find passed=True rows with score >= AUTOAPPLY_MIN_SCORE
  3. Group by strategy family (ARF1, IVB1, BREAKDOWN, etc.)
  4. For each family: if best winner is better than current live params
     → patch configs/auto_apply_params.env
     → log to runtime/auto_apply_log.jsonl
     → notify Telegram

Usage:
  python3 scripts/auto_apply_research_winner.py
  python3 scripts/auto_apply_research_winner.py --dry-run
  python3 scripts/auto_apply_research_winner.py --strategy ARF1
  python3 scripts/auto_apply_research_winner.py --force   (skip cooldown)

Env vars:
  AUTOAPPLY_MIN_SCORE=5.0       # Minimum score to consider a winner
  AUTOAPPLY_MAX_NEG_MONTHS=3    # Max negative months allowed
  AUTOAPPLY_MAX_NEG_STREAK=2    # Max negative month streak allowed
  AUTOAPPLY_MIN_TRADES=8        # Min trades for credibility
  AUTOAPPLY_MIN_PF=1.15         # Min profit factor
  AUTOAPPLY_COOLDOWN_H=20       # Hours between applying same strategy
  AUTOAPPLY_LOOKBACK_DAYS=14    # How far back to search for runs (days)
  AUTOAPPLY_SCAN_ROOTS=...      # Optional comma-separated roots to scan
  TG_TOKEN                      # Telegram bot token
  TG_CHAT                       # Telegram chat ID
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
import urllib.parse

ROOT = Path(__file__).resolve().parent.parent
AUTO_APPLY_ENV     = ROOT / "configs" / "auto_apply_params.env"
LOG_PATH           = ROOT / "runtime" / "auto_apply_log.jsonl"
CURRENT_PARAMS_LOG = ROOT / "runtime" / "auto_apply_current_params.json"

# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default).strip()

def _env_float(name: str, default: float) -> float:
    try: return float(_env(name, str(default)))
    except: return default

def _env_int(name: str, default: int) -> int:
    try: return int(_env(name, str(default)))
    except: return default

def _env_bool(name: str, default: bool = False) -> bool:
    return _env(name, "1" if default else "0").lower() in ("1","true","yes","y","on")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MIN_SCORE        = _env_float("AUTOAPPLY_MIN_SCORE", 5.0)
MAX_NEG_MONTHS   = _env_int("AUTOAPPLY_MAX_NEG_MONTHS", 3)
MAX_NEG_STREAK   = _env_int("AUTOAPPLY_MAX_NEG_STREAK", 2)
MIN_TRADES       = _env_int("AUTOAPPLY_MIN_TRADES", 8)
MIN_PF           = _env_float("AUTOAPPLY_MIN_PF", 1.15)
COOLDOWN_H       = _env_float("AUTOAPPLY_COOLDOWN_H", 20.0)
LOOKBACK_DAYS    = _env_int("AUTOAPPLY_LOOKBACK_DAYS", 14)
TG_TOKEN         = _env("TG_TOKEN")
TG_CHAT          = _env("TG_CHAT") or _env("TG_CHAT_ID")


def _scan_roots() -> List[Path]:
    raw = _env("AUTOAPPLY_SCAN_ROOTS", "")
    roots: List[Path] = []
    if raw:
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            p = Path(part)
            if not p.is_absolute():
                p = ROOT / part
            roots.append(p)
    if not roots:
        roots = [
            ROOT / "backtest_runs",
            ROOT / "runtime" / "research_import",
        ]
    seen = set()
    ordered: List[Path] = []
    for root in roots:
        key = str(root.resolve()) if root.exists() else str(root)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(root)
    return ordered


SCAN_ROOTS = _scan_roots()

# Strategy families: which env keys belong to which family
STRATEGY_FAMILIES: Dict[str, List[str]] = {
    "ARF1":      ["ARF1_"],
    "IVB1":      ["IVB1_"],
    "BREAKDOWN": ["BREAKDOWN_"],
    "ETS2":      ["ETS2_"],
    "ARS1":      ["ARS1_"],
    "ASB1":      ["ASB1_"],
    "ASC1":      ["ASC1_"],
}

# Params that are OK to auto-apply (whitelist — safety guard)
# Anything NOT in this list will never be auto-applied
SAFE_PARAMS = {
    # ARF1
    "ARF1_SIGNAL_LOOKBACK", "ARF1_MIN_RSI", "ARF1_MAX_RSI",
    "ARF1_MIN_RANGE_PCT", "ARF1_REGIME_MAX_GAP_PCT", "ARF1_REGIME_MAX_SLOPE_PCT",
    "ARF1_COOLDOWN_BARS_5M", "ARF1_SYMBOL_ALLOWLIST",
    # IVB1
    "IVB1_MIN_VOL_MULT", "IVB1_RETRACE_MAX_FRAC", "IVB1_BREAKOUT_BUFFER_ATR",
    "IVB1_RR", "IVB1_SYMBOL_ALLOWLIST",
    # BREAKDOWN
    "BREAKDOWN_RSI_MAX", "BREAKDOWN_LOOKBACK_H", "BREAKDOWN_BUFFER_ATR",
    "BREAKDOWN_SL_ATR", "BREAKDOWN_RR", "BREAKDOWN_COOLDOWN_BARS_5M",
    "BREAKDOWN_SYMBOL_ALLOWLIST",
    # ETS2 (Elder)
    "ETS2_OSC_OB", "ETS2_OSC_OS", "ETS2_WAVE_LOOKBACK",
    "ETS2_ENTRY_RETEST_BARS", "ETS2_TP_ATR_MULT", "ETS2_SYMBOL_ALLOWLIST",
    # ARS1
    "ARS1_BB_STD", "ARS1_RSI_SHORT_MIN", "ARS1_RSI_LONG_MAX",
    "ARS1_MIN_BAND_WIDTH_PCT", "ARS1_SYMBOL_ALLOWLIST",
}

# Params that are NEVER auto-applied (risk controls — require human review)
FORBIDDEN_PARAMS = {
    "RISK_PER_TRADE_PCT", "BYBIT_LEVERAGE", "ORCH_GLOBAL_RISK_MULT",
    "BREAKDOWN_RISK_MULT", "FLAT_RISK_MULT", "IVB1_RISK_MULT",
    "ENABLE_BREAKDOWN_TRADING", "ENABLE_FLAT_TRADING", "ENABLE_IVB1_TRADING",
    "ENABLE_ELDER_TRADING", "BYBIT_ACCOUNTS_JSON", "DRY_RUN",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tg(msg: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        payload = json.dumps({
            "chat_id": TG_CHAT,
            "text": msg,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        print(f"[auto_apply] TG failed: {exc}")


def _log(entry: Dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _safe_float(v: Any, default: float = 0.0) -> float:
    try: return float(v)
    except: return default


def _safe_int(v: Any, default: int = 0) -> int:
    try: return int(float(v))
    except: return default


# ---------------------------------------------------------------------------
# Step 1: Find autoresearch runs newer than LOOKBACK_DAYS
# ---------------------------------------------------------------------------

def find_recent_autoresearch_runs(lookback_days: int) -> List[Path]:
    """Return paths to ranked_results.csv for autoresearch runs within lookback window."""
    cutoff = time.time() - lookback_days * 86400
    results = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for d in root.iterdir():
            if not d.is_dir() or not d.name.startswith("autoresearch_"):
                continue
            ranked = d / "ranked_results.csv"
            if not ranked.exists():
                continue
            if ranked.stat().st_mtime >= cutoff:
                results.append(ranked)
    results.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return results


# ---------------------------------------------------------------------------
# Step 2: Parse ranked_results.csv → find best winner per strategy family
# ---------------------------------------------------------------------------

def _get_strategy_family(overrides: Dict[str, str]) -> Optional[str]:
    """Identify the strategy family from the params being overridden."""
    for family, prefixes in STRATEGY_FAMILIES.items():
        for key in overrides:
            for prefix in prefixes:
                if key.startswith(prefix):
                    return family
    return None


def find_best_winners(
    ranked_csv: Path,
    strategy_filter: Optional[str],
) -> List[Dict[str, Any]]:
    """Parse ranked_results.csv and return all rows that pass quality gates."""
    winners = []
    try:
        with ranked_csv.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if str(row.get("passed", "")).strip().lower() != "true":
                    continue
                score        = _safe_float(row.get("score", 0))
                trades       = _safe_int(row.get("trades", 0))
                pf           = _safe_float(row.get("profit_factor", 0))
                neg_months   = _safe_int(row.get("negative_months", 99))
                neg_streak   = _safe_int(row.get("max_negative_streak", 99))

                if score < MIN_SCORE:       continue
                if trades < MIN_TRADES:     continue
                if pf < MIN_PF:             continue
                if neg_months > MAX_NEG_MONTHS: continue
                if neg_streak > MAX_NEG_STREAK: continue

                try:
                    overrides = json.loads(row.get("overrides_json") or "{}")
                except Exception:
                    overrides = {}

                # Filter by strategy family
                family = _get_strategy_family(overrides)
                if strategy_filter and family != strategy_filter.upper():
                    continue

                winners.append({
                    "run_id":     row.get("run_id", ""),
                    "tag":        row.get("tag", ""),
                    "score":      score,
                    "trades":     trades,
                    "profit_factor": pf,
                    "winrate":    _safe_float(row.get("winrate", 0)),
                    "net_pnl":    _safe_float(row.get("net_pnl", 0)),
                    "max_drawdown": _safe_float(row.get("max_drawdown", 0)),
                    "neg_months": neg_months,
                    "neg_streak": neg_streak,
                    "overrides":  overrides,
                    "family":     family,
                    "source_csv": str(ranked_csv),
                })
    except Exception as exc:
        print(f"[auto_apply] Error reading {ranked_csv}: {exc}")
    return winners


# ---------------------------------------------------------------------------
# Step 3: Check cooldown
# ---------------------------------------------------------------------------

def _is_on_cooldown(family: str, cooldown_h: float) -> bool:
    history = _load_json(LOG_PATH, None)
    if history is None:
        return False
    # Read last N lines efficiently
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    except Exception:
        return False
    cutoff = time.time() - cooldown_h * 3600
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if entry.get("family") == family and entry.get("action") == "applied":
            if float(entry.get("ts", 0)) >= cutoff:
                return True
    return False


# ---------------------------------------------------------------------------
# Step 4: Filter params to safe-only, remove forbidden
# ---------------------------------------------------------------------------

def _filter_safe_params(overrides: Dict[str, str]) -> Dict[str, str]:
    safe = {}
    for k, v in overrides.items():
        if k in FORBIDDEN_PARAMS:
            continue
        if k in SAFE_PARAMS:
            safe[k] = v
        else:
            # Unknown param: apply if it starts with a known strategy prefix
            family = _get_strategy_family({k: v})
            if family:
                safe[k] = v
    return safe


# ---------------------------------------------------------------------------
# Step 5: Apply — write to auto_apply_params.env
# ---------------------------------------------------------------------------

def _read_current_auto_apply_env() -> Dict[str, str]:
    current: Dict[str, str] = {}
    if not AUTO_APPLY_ENV.exists():
        return current
    for line in AUTO_APPLY_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            current[k.strip()] = v.strip()
    return current


def _write_auto_apply_env(params: Dict[str, str], source_info: str) -> None:
    AUTO_APPLY_ENV.parent.mkdir(parents=True, exist_ok=True)
    ts_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"# auto_apply_params.env — auto-generated by auto_apply_research_winner.py",
        f"# Last update: {ts_str}",
        f"# Source: {source_info}",
        f"# DO NOT EDIT MANUALLY — will be overwritten by the auto-apply module",
        "",
    ]
    # Group by strategy family
    by_family: Dict[str, Dict[str, str]] = {}
    for k, v in sorted(params.items()):
        fam = _get_strategy_family({k: v}) or "OTHER"
        by_family.setdefault(fam, {})[k] = v

    for fam in sorted(by_family):
        lines.append(f"# ── {fam} ──")
        for k, v in sorted(by_family[fam].items()):
            lines.append(f"{k}={v}")
        lines.append("")

    AUTO_APPLY_ENV.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Auto-apply best autoresearch winners to live config.")
    ap.add_argument("--dry-run", action="store_true", help="Analyse only, do not write anything.")
    ap.add_argument("--force",   action="store_true", help="Skip cooldown check.")
    ap.add_argument("--strategy", default="", help="Only process this strategy family (e.g. ARF1).")
    ap.add_argument("--lookback-days", type=int, default=LOOKBACK_DAYS)
    ap.add_argument("--min-score",     type=float, default=MIN_SCORE)
    ap.add_argument("--quiet",         action="store_true")
    args = ap.parse_args()

    dry_run  = args.dry_run
    strategy = args.strategy.strip().upper() or None

    roots_str = ", ".join(str(p) for p in SCAN_ROOTS)
    print(f"[auto_apply] Starting — dry_run={dry_run}, lookback={args.lookback_days}d, min_score={args.min_score}")
    print(f"[auto_apply] Scan roots: {roots_str}")

    # Step 1: Find recent autoresearch runs
    runs = find_recent_autoresearch_runs(args.lookback_days)
    if not runs:
        print(f"[auto_apply] No autoresearch runs found in last {args.lookback_days} days.")
        return 0
    print(f"[auto_apply] Found {len(runs)} autoresearch run(s) to check.")

    # Step 2: Collect all winners across runs
    all_winners: List[Dict[str, Any]] = []
    for ranked_csv in runs:
        w = find_best_winners(ranked_csv, strategy)
        all_winners.extend(w)

    if not all_winners:
        print(f"[auto_apply] No winners found passing all gates (score>={args.min_score}, trades>={MIN_TRADES}, PF>={MIN_PF}).")
        return 0

    # Step 3: Best winner per strategy family (highest score)
    best_by_family: Dict[str, Dict[str, Any]] = {}
    for w in all_winners:
        fam = w.get("family") or "UNKNOWN"
        if fam == "UNKNOWN":
            continue
        if fam not in best_by_family or w["score"] > best_by_family[fam]["score"]:
            best_by_family[fam] = w

    print(f"[auto_apply] Best winners: {list(best_by_family.keys())}")

    # Step 4: Read current params state
    current_env = _read_current_auto_apply_env()
    new_env = dict(current_env)  # start from current, will merge updates
    applied_changes: List[Dict[str, Any]] = []
    skipped: List[str] = []

    for family, winner in sorted(best_by_family.items()):
        # Cooldown check
        if not args.force and _is_on_cooldown(family, COOLDOWN_H):
            print(f"[auto_apply] {family}: on cooldown ({COOLDOWN_H:.0f}h). Skipping.")
            skipped.append(f"{family} (cooldown)")
            continue

        # Filter to safe params only
        safe_params = _filter_safe_params(winner["overrides"])
        if not safe_params:
            print(f"[auto_apply] {family}: winner has no safe-applicable params. Skipping.")
            skipped.append(f"{family} (no safe params)")
            continue

        # Check if anything actually changed vs current
        changed = {}
        for k, v in safe_params.items():
            if current_env.get(k) != v:
                changed[k] = {"from": current_env.get(k, "<not set>"), "to": v}

        if not changed:
            print(f"[auto_apply] {family}: params already match current. Nothing to do.")
            skipped.append(f"{family} (no change)")
            continue

        print(f"\n[auto_apply] {family} WINNER — score={winner['score']:.2f} "
              f"PF={winner['profit_factor']:.2f} trades={winner['trades']} "
              f"WR={winner['winrate']:.1%}")
        for k, delta in changed.items():
            print(f"  {k}: {delta['from']} → {delta['to']}")

        if not dry_run:
            new_env.update(safe_params)
            applied_changes.append({
                "family":   family,
                "winner":   winner,
                "changed":  changed,
            })

    # Step 5: Write and notify
    if not dry_run and applied_changes:
        source_info = " | ".join(
            f"{c['family']}: score={c['winner']['score']:.1f} PF={c['winner']['profit_factor']:.2f}"
            for c in applied_changes
        )
        _write_auto_apply_env(new_env, source_info)
        print(f"\n[auto_apply] Written → {AUTO_APPLY_ENV}")

        ts_now = int(time.time())
        ts_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        for change in applied_changes:
            fam = change["family"]
            w   = change["winner"]
            chg = change["changed"]

            # Log entry
            _log({
                "ts":      ts_now,
                "ts_str":  ts_str,
                "action":  "applied",
                "family":  fam,
                "score":   w["score"],
                "pf":      w["profit_factor"],
                "trades":  w["trades"],
                "tag":     w["tag"],
                "changed": chg,
            })

            # TG message
            lines_changed = "\n".join(
                f"  <code>{k}</code>: {v['from']} → <b>{v['to']}</b>"
                for k, v in chg.items()
            )
            msg = (
                f"🔧 <b>AutoApply: {fam}</b>\n"
                f"Score={w['score']:.1f} PF={w['profit_factor']:.2f} "
                f"WR={w['winrate']:.1%} trades={w['trades']}\n"
                f"Изменения:\n{lines_changed}\n"
                f"📄 {Path(w['source_csv']).parent.name}\n"
                f"⏰ {ts_str}"
            )
            _tg(msg)
            print(f"[auto_apply] TG notification sent for {fam}.")

        # Save current params snapshot
        _save_json(CURRENT_PARAMS_LOG, {
            "ts_str": datetime.now(timezone.utc).isoformat(),
            "params": new_env,
        })

        print(f"\n[auto_apply] Done. Applied {len(applied_changes)} update(s).")
        print(f"[auto_apply] ⚠️  IMPORTANT: Run 'systemctl reload bybit-bot' or touch the")
        print(f"[auto_apply]    allowlist watcher file to hot-reload these params in the bot.")
        print(f"[auto_apply]    File: {AUTO_APPLY_ENV}")

    elif dry_run:
        if applied_changes:
            print(f"\n[auto_apply] DRY RUN — would apply {len(applied_changes)} change(s). "
                  f"Run without --dry-run to apply.")
        else:
            print(f"\n[auto_apply] DRY RUN — nothing to apply.")
    else:
        print(f"\n[auto_apply] Nothing applied ({len(skipped)} skipped).")

    if skipped:
        print(f"[auto_apply] Skipped: {', '.join(skipped)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
