#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    val = os.getenv(name)
    return str(val).strip() if val is not None else default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on"}


def _latest_per_symbol_csv() -> Path | None:
    root = Path(__file__).resolve().parent.parent
    runs = sorted(root.glob("backtest_runs/funding_*/funding_per_symbol.csv"))
    return runs[-1] if runs else None


def _load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["symbol"] = str(row.get("symbol") or "").strip().upper()
        row["net_usd_f"] = float(row.get("net_usd") or 0.0)
        row["events_i"] = int(float(row.get("funding_events") or 0))
        row["requires_spot_borrow_i"] = int(float(row.get("requires_spot_borrow") or 0))
    rows.sort(key=lambda r: (r["net_usd_f"], r["events_i"]), reverse=True)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Dry-run funding/carry basket planner from latest funding_per_symbol.csv")
    ap.add_argument("--per-symbol-csv", default=_env("FUNDING_PER_SYMBOL_CSV", ""))
    ap.add_argument("--capital-usd", type=float, default=_env_float("FUNDING_BRIDGE_CAPITAL_USD", 500.0))
    ap.add_argument("--max-symbols", type=int, default=_env_int("FUNDING_BRIDGE_MAX_SYMBOLS", 4))
    ap.add_argument("--min-net-usd", type=float, default=_env_float("FUNDING_BRIDGE_MIN_NET_USD", 0.0))
    ap.add_argument("--min-events", type=int, default=_env_int("FUNDING_BRIDGE_MIN_EVENTS", 120))
    ap.add_argument("--positive-carry-only", type=int, default=1 if _env_bool("FUNDING_BRIDGE_POSITIVE_CARRY_ONLY", True) else 0)
    ap.add_argument("--allow-borrow-legs", type=int, default=1 if _env_bool("FUNDING_BRIDGE_ALLOW_BORROW_LEGS", False) else 0)
    args = ap.parse_args()

    per_symbol_csv = Path(args.per_symbol_csv) if args.per_symbol_csv else _latest_per_symbol_csv()
    if per_symbol_csv is None or not per_symbol_csv.exists():
        print("error=no_funding_per_symbol_csv", file=sys.stderr)
        return 2

    rows = _load_rows(per_symbol_csv)
    selected: list[dict] = []
    skipped: list[dict] = []
    for row in rows:
        if len(selected) >= max(1, int(args.max_symbols)):
            break
        if row["net_usd_f"] < float(args.min_net_usd):
            skipped.append({"symbol": row["symbol"], "reason": "net_below_min"})
            continue
        if row["events_i"] < int(args.min_events):
            skipped.append({"symbol": row["symbol"], "reason": "events_below_min"})
            continue
        if int(args.positive_carry_only) == 1 and str(row.get("perp_side") or "") != "short":
            skipped.append({"symbol": row["symbol"], "reason": "not_positive_carry_short_perp"})
            continue
        if int(args.allow_borrow_legs) != 1 and row["requires_spot_borrow_i"] == 1:
            skipped.append({"symbol": row["symbol"], "reason": "requires_spot_borrow"})
            continue
        selected.append(row)

    if not selected:
        print("error=no_selected_symbols", file=sys.stderr)
        return 3

    per_symbol_capital = max(25.0, float(args.capital_usd) / max(1, len(selected)))
    report = {
        "status": "dry_run",
        "per_symbol_csv": str(per_symbol_csv),
        "capital_usd": round(float(args.capital_usd), 2),
        "per_symbol_capital_usd": round(per_symbol_capital, 2),
        "positive_carry_only": bool(int(args.positive_carry_only)),
        "allow_borrow_legs": bool(int(args.allow_borrow_legs)),
        "selected": [
            {
                "symbol": row["symbol"],
                "target_notional_usd": round(per_symbol_capital, 2),
                "perp_side": row.get("perp_side", ""),
                "hedge_leg": row.get("hedge_leg", ""),
                "requires_spot_borrow": bool(row["requires_spot_borrow_i"]),
                "funding_events": row["events_i"],
                "net_usd_hist": round(row["net_usd_f"], 6),
                "mean_funding_rate": float(row.get("mean_funding_rate") or 0.0),
            }
            for row in selected
        ],
        "skipped": skipped[:20],
    }
    print(json.dumps(report, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
