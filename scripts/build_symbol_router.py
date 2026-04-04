#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_symbol_router.py — regime-aware dynamic symbol router

Builds per-strategy symbol lists from:
  1. current market scan
  2. optional per-symbol backtest gate
  3. current regime from the orchestrator state
  4. strategy profile registry

Outputs:
  - runtime/router/symbol_router_state.json
  - configs/dynamic_allowlist_latest.env

Fail-safe behavior:
  - if live scan fails, keep the last-known-good allowlists when possible
  - if a profile selects zero symbols, fall back to the previous overlay
  - if there is still no fallback, use fixed symbols or anchor symbols

The router does not change core strategy parameters in live.
It only chooses symbol baskets and profile variants.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.dynamic_allowlist import (  # noqa: E402
    _DEFAULT_PROFILES,
    _load_backtest_perf,
    run_scan,
    select_for_profile,
    StrategyProfile,
)

STATE_PATH = ROOT / "runtime" / "regime" / "orchestrator_state.json"
ROUTER_STATE_PATH = ROOT / "runtime" / "router" / "symbol_router_state.json"
OUT_ENV_PATH = ROOT / "configs" / "dynamic_allowlist_latest.env"
REGISTRY_PATH = ROOT / "configs" / "strategy_profile_registry.json"
CONTROL_PLANE_DIR = ROOT / "runtime" / "control_plane"
HISTORY_PATH = CONTROL_PLANE_DIR / "symbol_router_history.jsonl"
STATE_VERSION = "1"


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _append_history(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _parse_env_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        if not path.exists():
            return out
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    except Exception:
        return {}
    return out


def _csv_symbols(raw: str) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in str(raw or "").replace(";", ",").split(","):
        sym = item.strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def _dedupe_keep_order(values: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for value in values:
        sym = str(value or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def _default_profile_map() -> Dict[str, StrategyProfile]:
    return {p.env_key: copy.deepcopy(p) for p in _DEFAULT_PROFILES}


def _pick_profiles(regime: str, registry: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in registry.get("profiles", []):
        env_key = str(item.get("env_key") or "").strip()
        if not env_key:
            continue
        grouped.setdefault(env_key, []).append(item)

    out: Dict[str, Dict[str, Any]] = {}
    for env_key, entries in grouped.items():
        chosen = None
        for item in entries:
            active = [str(x).strip() for x in (item.get("active_regimes") or [])]
            if regime in active or "*" in active:
                chosen = item
                break
        if chosen is None:
            for item in entries:
                if bool(item.get("default", False)):
                    chosen = item
                    break
        if chosen is None and entries:
            chosen = entries[0]
        if chosen is not None:
            out[env_key] = chosen
    return out


def _build_profile(entry: Dict[str, Any], defaults: Dict[str, StrategyProfile]) -> StrategyProfile:
    env_key = str(entry.get("env_key") or "").strip()
    base = copy.deepcopy(
        defaults.get(env_key)
        or StrategyProfile(
            name=str(entry.get("profile_id") or env_key),
            env_key=env_key,
            strategy_tags=list(entry.get("strategy_tags") or []),
        )
    )

    field_names = {
        "name",
        "strategy_tags",
        "min_turnover",
        "min_atr_pct",
        "max_atr_pct",
        "min_listing_days",
        "top_n",
        "bt_min_trades",
        "bt_min_net",
        "bt_min_pf",
        "anchor_symbols",
    }
    for key in field_names:
        if key in entry:
            setattr(base, key, entry[key])
    return base


def _profile_excludes(entry: Dict[str, Any]) -> List[str]:
    return _dedupe_keep_order([str(x).upper() for x in entry.get("exclude_symbols", []) if str(x).strip()])


def _profile_suffix(env_key: str) -> str:
    return env_key.replace("_SYMBOL_ALLOWLIST", "").replace("_SYMBOLS", "")


def _router_state_entry(
    *,
    env_key: str,
    profile_id: str,
    regime: str,
    symbols: List[str],
    fixed_symbols: bool,
    source: str,
    notes: List[str],
) -> Dict[str, Any]:
    return {
        "env_key": env_key,
        "profile_id": profile_id,
        "regime": regime,
        "symbols": symbols,
        "count": len(symbols),
        "fixed_symbols": fixed_symbols,
        "source": source,
        "notes": notes,
    }


def _fallback_symbols(
    *,
    env_key: str,
    profile: StrategyProfile,
    previous_overlay: Dict[str, str],
    fixed_symbols: List[str],
) -> tuple[List[str], str, List[str]]:
    notes: List[str] = []

    if fixed_symbols:
        notes.append("used fixed_symbols from profile registry")
        return _dedupe_keep_order(fixed_symbols), "fixed_profile", notes

    previous = _csv_symbols(previous_overlay.get(env_key, ""))
    if previous:
        notes.append("used last-known-good symbols from existing overlay")
        return previous, "fallback_existing_env", notes

    anchors = _dedupe_keep_order(list(profile.anchor_symbols or []))
    if anchors:
        notes.append("used anchor symbols because scan selection was unavailable")
        return anchors, "anchor_fallback", notes

    notes.append("no symbols available")
    return [], "empty", notes


def main() -> int:
    ap = argparse.ArgumentParser(description="Build regime-aware dynamic symbol router output.")
    ap.add_argument("--state-path", default=str(STATE_PATH), help="Path to orchestrator JSON state.")
    ap.add_argument("--registry-path", default=str(REGISTRY_PATH), help="Path to strategy profile registry JSON.")
    ap.add_argument("--trades-csv", default="", help="Optional trades.csv for per-symbol backtest gate.")
    ap.add_argument("--out-env", default=str(OUT_ENV_PATH), help="Output env overlay path.")
    ap.add_argument("--out-json", default=str(ROUTER_STATE_PATH), help="Output router state JSON path.")
    ap.add_argument("--bybit-base", default="https://api.bybit.com", help="Bybit API base.")
    ap.add_argument("--atr-lookback-days", type=int, default=14)
    ap.add_argument("--max-scan-symbols", type=int, default=60)
    ap.add_argument("--polite-sleep-sec", type=float, default=0.25)
    ap.add_argument("--http-timeout-sec", type=float, default=8.0)
    ap.add_argument("--kline-max-retries", type=int, default=3)
    ap.add_argument("--kline-backoff-max-sec", type=float, default=5.0)
    ap.add_argument("--regime-override", default="", help="Force regime instead of reading orchestrator state.")
    ap.add_argument("--strict", action="store_true", help="Fail instead of falling back to previous overlay.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    state_path = Path(args.state_path).expanduser()
    if not state_path.is_absolute():
        state_path = ROOT / state_path
    registry_path = Path(args.registry_path).expanduser()
    if not registry_path.is_absolute():
        registry_path = ROOT / registry_path
    out_env = Path(args.out_env).expanduser()
    if not out_env.is_absolute():
        out_env = ROOT / out_env
    out_json = Path(args.out_json).expanduser()
    if not out_json.is_absolute():
        out_json = ROOT / out_json

    state = _load_json(state_path, {})
    raw_regime = str(state.get("raw_regime") or "").strip()
    pending_regime = str(state.get("pending_regime") or "").strip()
    regime = str(args.regime_override or state.get("regime") or "unknown").strip()
    confidence = state.get("confidence")
    registry = _load_json(registry_path, {"profiles": []})
    profile_version = str(registry.get("profile_version") or registry.get("version") or "unknown")
    selected_profiles = _pick_profiles(regime, registry)
    default_profiles = _default_profile_map()
    previous_overlay = _parse_env_file(out_env)

    backtest: Dict[Tuple[str, str], Any] = {}
    backtest_path: str = ""
    if args.trades_csv:
        trades_path = Path(args.trades_csv).expanduser()
        if not trades_path.is_absolute():
            trades_path = ROOT / trades_path
        if not trades_path.exists():
            print(f"ERROR: trades.csv not found: {trades_path}", file=sys.stderr)
            return 1
        backtest = _load_backtest_perf(trades_path)
        backtest_path = str(trades_path)

    scan: Dict[str, Any] = {}
    scan_ok = False
    scan_error = ""
    try:
        scan = run_scan(
        bybit_base=args.bybit_base,
        max_scan_symbols=args.max_scan_symbols,
        atr_lookback_days=args.atr_lookback_days,
        polite_sleep_sec=args.polite_sleep_sec,
        http_timeout_sec=args.http_timeout_sec,
        kline_max_retries=args.kline_max_retries,
        kline_backoff_max_sec=args.kline_backoff_max_sec,
        quiet=args.quiet,
    )
        scan_ok = bool(scan)
        if not scan_ok:
            scan_error = "market scan returned zero candidates"
    except Exception as e:
        scan_error = str(e)
        scan_ok = False
        if args.strict:
            print(f"ERROR: market scan failed: {scan_error}", file=sys.stderr)
            return 1

    results: Dict[str, List[str]] = {}
    router_profiles: Dict[str, Dict[str, Any]] = {}
    fallback_reasons: List[str] = []
    degraded = False

    for env_key, entry in selected_profiles.items():
        profile_id = str(entry.get("profile_id") or env_key)
        fixed_symbols = _dedupe_keep_order([str(x).upper() for x in entry.get("fixed_symbols", []) if str(x).strip()])

        symbols: List[str] = []
        source = "fixed_profile" if fixed_symbols else "scan_profile"
        notes: List[str] = []
        fixed = bool(fixed_symbols)

        if fixed_symbols:
            symbols = fixed_symbols
            notes.append("used fixed_symbols from registry")
        else:
            profile = _build_profile(entry, default_profiles)
            if scan_ok:
                try:
                    symbols = select_for_profile(profile, scan, backtest, quiet=args.quiet)
                except Exception as e:
                    scan_ok = False
                    scan_error = f"profile selection failed for {env_key}: {e}"
                    if args.strict:
                        print(f"ERROR: {scan_error}", file=sys.stderr)
                        return 1
            if not scan_ok or not symbols:
                symbols, source, notes = _fallback_symbols(
                    env_key=env_key,
                    profile=profile,
                    previous_overlay=previous_overlay,
                    fixed_symbols=fixed_symbols,
                )
                degraded = True
                reason = f"{env_key}:{source}"
                if scan_error:
                    reason += f" ({scan_error})"
                fallback_reasons.append(reason)

            excludes = _profile_excludes(entry)
            if excludes:
                exclude_set = set(excludes)
                before = len(symbols)
                symbols = [sym for sym in symbols if sym not in exclude_set]
                if len(symbols) != before:
                    notes.append(f"excluded symbols via registry: {','.join(excludes)}")
                if not symbols:
                    symbols, source, fallback_notes = _fallback_symbols(
                        env_key=env_key,
                        profile=profile,
                        previous_overlay=previous_overlay,
                        fixed_symbols=fixed_symbols,
                    )
                    notes.extend(fallback_notes)
                    degraded = True
                    fallback_reasons.append(f"{env_key}:post_exclude_empty")

        symbols = _dedupe_keep_order(symbols)
        results[env_key] = symbols
        router_profiles[env_key] = _router_state_entry(
            env_key=env_key,
            profile_id=profile_id,
            regime=regime,
            symbols=symbols,
            fixed_symbols=fixed,
            source=source,
            notes=notes,
        )

    now_utc = datetime.now(timezone.utc)
    generated_at = now_utc.isoformat()
    router_status = "degraded_fallback" if degraded else "ok"

    lines = [
        "# Auto-generated by build_symbol_router.py — do not edit manually",
        f"# Generated: {generated_at}",
        f"ROUTER_STATE_VERSION={STATE_VERSION}",
        f"ROUTER_PROFILE_VERSION={profile_version}",
        f"ROUTER_STATUS={router_status}",
        f"ROUTER_REGIME={regime}",
        f"ROUTER_RAW_REGIME={raw_regime}",
        f"ROUTER_PENDING_REGIME={pending_regime}",
        f"ROUTER_GENERATED_AT_UTC={generated_at}",
        f"ROUTER_SCAN_OK={int(scan_ok)}",
        f"ROUTER_STATE_PATH={out_json}",
        f"ROUTER_HISTORY_PATH={HISTORY_PATH}",
        f"ALLOWLIST_WATCHER_FILE={out_env}",
    ]
    if confidence is not None:
        lines.append(f"ROUTER_CONFIDENCE={confidence}")
    if scan_error:
        lines.append(f"ROUTER_SCAN_ERROR={json.dumps(scan_error)}")
    lines.append("")

    for env_key, info in router_profiles.items():
        suffix = _profile_suffix(env_key)
        lines.append(f"ROUTER_PROFILE_{suffix}={info['profile_id']}")
        lines.append(f"ROUTER_SOURCE_{suffix}={info['source']}")
        lines.append(f"ROUTER_COUNT_{suffix}={info['count']}")
        lines.append(f"{env_key}={','.join(info['symbols'])}")
        lines.append("")

    env_text = "\n".join(lines)
    state_obj = {
        "version": STATE_VERSION,
        "profile_version": profile_version,
        "timestamp_utc": generated_at,
        "status": router_status,
        "degraded": degraded,
        "regime": regime,
        "raw_regime": raw_regime,
        "pending_regime": pending_regime,
        "confidence": confidence,
        "scan_ok": scan_ok,
        "scan_error": scan_error,
        "fallback_reasons": fallback_reasons,
        "source_state_path": str(state_path),
        "registry_path": str(registry_path),
        "backtest_path": backtest_path,
        "env_path": str(out_env),
        "state_path": str(out_json),
        "history_path": str(HISTORY_PATH),
        "profiles": router_profiles,
    }

    if args.dry_run:
        print(json.dumps(state_obj, indent=2))
        print("\n" + env_text)
        return 0

    _write_text_atomic(out_env, env_text + "\n")
    _write_text_atomic(out_json, json.dumps(state_obj, indent=2) + "\n")
    _append_history(HISTORY_PATH, state_obj)

    if not args.quiet:
        print(f"Written env:   {out_env}")
        print(f"Written state: {out_json}")
        print(f"History path:  {HISTORY_PATH}")
        print(f"Router status: {router_status} | regime={regime} | scan_ok={int(scan_ok)}")
        if fallback_reasons:
            print("Fallbacks:")
            for reason in fallback_reasons:
                print(f"  - {reason}")
        for env_key, info in router_profiles.items():
            print(
                f"{env_key}: {info['count']} [{info['profile_id']}] "
                f"source={info['source']} -> {','.join(info['symbols'])}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
