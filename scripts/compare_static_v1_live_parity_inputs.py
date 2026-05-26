#!/usr/bin/env python3
"""Compare proven crypto_income_static_v1 inputs with current live-effective inputs.

This is read-only. It does not inspect or print secrets; it only reports which
strategy sleeves and symbols differ between the recovery baseline and the
currently effective allocator/router state. Account-level position, leverage,
and risk settings are deliberately outside this report and require a separate
non-secret runtime check.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from run_live_effective_parity import build_live_effective_inputs, load_env_file


STATIC_SLEEVES = {
    "att1": ("ENABLE_ATT1_TRADING", "ATT1_SYMBOL_ALLOWLIST", "alt_trendline_touch_v1"),
    "flat": ("ENABLE_FLAT_TRADING", "ARF1_SYMBOL_ALLOWLIST", "alt_resistance_fade_v1"),
    "breakdown": ("ENABLE_BREAKDOWN_TRADING", "BREAKDOWN_SYMBOL_ALLOWLIST", "alt_inplay_breakdown_v1"),
    "midterm": ("ENABLE_MIDTERM_TRADING", "MIDTERM_SYMBOLS", "btc_eth_midterm_pullback"),
}


def _csv_set(value: str) -> set[str]:
    return {part.strip().upper() for part in str(value or "").split(",") if part.strip()}


def _enabled(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _fmt(items: set[str], limit: int = 12) -> str:
    if not items:
        return "-"
    ordered = sorted(items)
    suffix = "" if len(ordered) <= limit else f",...(+{len(ordered) - limit})"
    return ",".join(ordered[:limit]) + suffix


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--static-env", default="configs/crypto_income_static_v1_candidate.env")
    parser.add_argument("--health-filter", choices=["all", "ok", "ok-watch"], default="all")
    parser.add_argument(
        "--env-path",
        action="append",
        dest="env_paths",
        help="Env overlay path to load for the compared live/test-effective stack.",
    )
    parser.add_argument(
        "--allocator-state",
        default="runtime/control_plane/portfolio_allocator_state.json",
        help="Allocator state JSON to compare against static_v1.",
    )
    parser.add_argument(
        "--allow-extra-live-inputs",
        action="store_true",
        help="Report only missing required inputs; do not fail on extra live sleeves or symbols.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    static_env = load_env_file(root / args.static_env)
    _, _, _, live_rows = build_live_effective_inputs(
        root,
        health_filter=args.health_filter,
        env_paths=args.env_paths,
        allocator_state_path=args.allocator_state,
    )
    live_by_sleeve = {str(row["sleeve"]): row for row in live_rows}

    print("STATIC_V1_VS_LIVE_EFFECTIVE_INPUT_PARITY")
    print(f"static_env={args.static_env}")
    print(f"health_filter={args.health_filter}")
    print("scope=sleeves_and_symbols_only")
    print("not_checked=max_positions,leverage,risk_pct,portfolio_risk_cap")

    total_static_symbols = 0
    total_matched_symbols = 0
    hard_mismatches: list[str] = []
    extra_symbol_mismatches: list[str] = []
    expected_live_sleeves = {
        sleeve
        for sleeve, (enable_key, _, _) in STATIC_SLEEVES.items()
        if _enabled(static_env.get(enable_key, "0"))
    }

    for sleeve, (enable_key, symbols_key, strategy) in STATIC_SLEEVES.items():
        static_enabled = _enabled(static_env.get(enable_key, "0"))
        static_symbols = _csv_set(static_env.get(symbols_key, ""))
        live_row = live_by_sleeve.get(sleeve)
        live_symbols = _csv_set(",".join(live_row.get("symbols") or [])) if live_row else set()
        live_strategy = str(live_row.get("strategy") or "-") if live_row else "-"
        live_active = bool(live_row)

        matched = static_symbols & live_symbols
        missing = static_symbols - live_symbols
        extra = live_symbols - static_symbols
        total_static_symbols += len(static_symbols)
        total_matched_symbols += len(matched)

        status = "OK"
        if static_enabled and not live_active:
            status = "MISSING_SLEEVE"
            hard_mismatches.append(sleeve)
        elif static_enabled and live_strategy != strategy:
            status = "STRATEGY_MISMATCH"
            hard_mismatches.append(sleeve)
        elif static_enabled and missing:
            status = "SYMBOL_MISMATCH"
            hard_mismatches.append(sleeve)
        elif static_enabled and extra and not args.allow_extra_live_inputs:
            status = "EXTRA_SYMBOLS"
            extra_symbol_mismatches.append(sleeve)

        print(
            f"{sleeve}: {status} | static_strategy={strategy} live_strategy={live_strategy} "
            f"| static_symbols={len(static_symbols)} live_symbols={len(live_symbols)} "
            f"matched={len(matched)} missing={_fmt(missing)} extra={_fmt(extra)}"
        )

    extra_live_sleeves = set(live_by_sleeve) - expected_live_sleeves
    if extra_live_sleeves:
        print(f"extra_live_sleeves={_fmt(extra_live_sleeves)}")
    if extra_symbol_mismatches:
        print(f"extra_symbol_sleeves={_fmt(set(extra_symbol_mismatches))}")

    score = (total_matched_symbols / total_static_symbols * 100.0) if total_static_symbols else 0.0
    strict_extras = bool(extra_live_sleeves or extra_symbol_mismatches) and not args.allow_extra_live_inputs
    passed = score >= 80.0 and not hard_mismatches and not strict_extras
    print(f"required_input_coverage_pct={score:.1f}")
    print(f"strict_extra_input_check={'OFF' if args.allow_extra_live_inputs else 'ON'}")
    print("account_limit_parity=NOT_CHECKED")
    print("verdict=" + ("PASS" if passed else "FAIL"))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
