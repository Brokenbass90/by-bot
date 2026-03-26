#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
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


def _f(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _latest_per_symbol_csv() -> Path | None:
    root = Path(__file__).resolve().parent.parent
    runs = sorted(root.glob("backtest_runs/funding_*/funding_per_symbol.csv"))
    return runs[-1] if runs else None


def _get_json(url: str, *, timeout_sec: float = 20.0, retries: int = 6) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "by-bot/1.0"})
    for i in range(max(1, int(retries))):
        try:
            with urllib.request.urlopen(req, timeout=float(timeout_sec)) as r:
                return json.loads(r.read().decode("utf-8"))
        except (TimeoutError, socket.timeout, urllib.error.URLError, ConnectionError, OSError):
            if i >= retries - 1:
                raise
            time.sleep(min(15.0, (1.5 ** i) + random.uniform(0.05, 0.25)))
    raise RuntimeError("unreachable")


def _fetch_live_tickers(base: str) -> list[dict]:
    q = urllib.parse.urlencode({"category": "linear"})
    url = f"{base.rstrip('/')}/v5/market/tickers?{q}"
    js = _get_json(url)
    return (((js or {}).get("result") or {}).get("list") or [])


def _load_hist_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for row in rows:
        sym = str(row.get("symbol") or "").strip().upper()
        if not sym:
            continue
        out.append(
            {
                **row,
                "symbol": sym,
                "net_usd_f": _f(row.get("net_usd")),
                "events_i": int(_f(row.get("funding_events"))),
                "mean_funding_rate_f": _f(row.get("mean_funding_rate")),
                "requires_spot_borrow_i": int(_f(row.get("requires_spot_borrow"))),
            }
        )
    return out


def _score_row(hist_net_usd: float, receive_8h_pct: float, basis_pct: float) -> float:
    basis_penalty = max(0.0, abs(basis_pct) - 0.10) * 0.5
    return hist_net_usd + (receive_8h_pct * 15.0) - basis_penalty


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a live-ready funding/carry basket plan from historical per-symbol stats + current Bybit funding/basis.")
    ap.add_argument("--per-symbol-csv", default=_env("FUNDING_PER_SYMBOL_CSV", ""))
    ap.add_argument("--base", default=_env("BYBIT_BASE", "https://api.bybit.com"))
    ap.add_argument("--capital-usd", type=float, default=_env_float("FUNDING_PLAN_CAPITAL_USD", 500.0))
    ap.add_argument("--max-symbols", type=int, default=_env_int("FUNDING_PLAN_MAX_SYMBOLS", 4))
    ap.add_argument("--min-hist-net-usd", type=float, default=_env_float("FUNDING_PLAN_MIN_HIST_NET_USD", 0.0))
    ap.add_argument("--min-events", type=int, default=_env_int("FUNDING_PLAN_MIN_EVENTS", 120))
    ap.add_argument("--positive-carry-only", type=int, default=1 if _env_bool("FUNDING_PLAN_POSITIVE_CARRY_ONLY", True) else 0)
    ap.add_argument("--allow-borrow-legs", type=int, default=1 if _env_bool("FUNDING_PLAN_ALLOW_BORROW_LEGS", False) else 0)
    ap.add_argument("--min-receive-8h-pct", type=float, default=_env_float("FUNDING_PLAN_MIN_RECEIVE_8H_PCT", 0.005))
    ap.add_argument("--max-abs-basis-pct", type=float, default=_env_float("FUNDING_PLAN_MAX_ABS_BASIS_PCT", 0.75))
    ap.add_argument("--min-turnover-usd", type=float, default=_env_float("FUNDING_PLAN_MIN_TURNOVER_USD", 50_000_000.0))
    ap.add_argument("--min-oi-usd", type=float, default=_env_float("FUNDING_PLAN_MIN_OI_USD", 10_000_000.0))
    ap.add_argument("--out-dir", default=_env("FUNDING_PLAN_OUT_DIR", "runtime/funding_carry"))
    args = ap.parse_args()

    per_symbol_csv = Path(args.per_symbol_csv) if args.per_symbol_csv else _latest_per_symbol_csv()
    if per_symbol_csv is None or not per_symbol_csv.exists():
        print("error=no_funding_per_symbol_csv", file=sys.stderr)
        return 2

    hist_rows = _load_hist_rows(per_symbol_csv)
    if not hist_rows:
        print("error=empty_hist_rows", file=sys.stderr)
        return 3

    live_rows = _fetch_live_tickers(args.base)
    live_by_symbol: dict[str, dict] = {}
    raw_live_export: list[dict] = []
    for row in live_rows:
        sym = str(row.get("symbol") or "").strip().upper()
        if not sym.endswith("USDT"):
            continue
        fr = _f(row.get("fundingRate"))
        mark = _f(row.get("markPrice"))
        idx = _f(row.get("indexPrice"))
        basis_pct = ((mark - idx) / idx * 100.0) if mark > 0 and idx > 0 else 0.0
        turnover = _f(row.get("turnover24h"))
        oi = _f(row.get("openInterestValue"))
        live = {
            "symbol": sym,
            "funding_rate_8h_pct": fr * 100.0,
            "funding_annual_pct": fr * 3.0 * 365.0 * 100.0,
            "basis_pct": basis_pct,
            "turnover24h_usd": turnover,
            "oi_usd": oi,
        }
        live_by_symbol[sym] = live
        raw_live_export.append(live)

    selected: list[dict] = []
    skipped: list[dict] = []
    for row in hist_rows:
        sym = row["symbol"]
        live = live_by_symbol.get(sym)
        if live is None:
            skipped.append({"symbol": sym, "reason": "missing_live_ticker"})
            continue
        if row["net_usd_f"] < float(args.min_hist_net_usd):
            skipped.append({"symbol": sym, "reason": "hist_net_below_min"})
            continue
        if row["events_i"] < int(args.min_events):
            skipped.append({"symbol": sym, "reason": "events_below_min"})
            continue
        if int(args.positive_carry_only) == 1 and str(row.get("perp_side") or "") != "short":
            skipped.append({"symbol": sym, "reason": "not_short_perp_profile"})
            continue
        if int(args.allow_borrow_legs) != 1 and row["requires_spot_borrow_i"] == 1:
            skipped.append({"symbol": sym, "reason": "requires_spot_borrow"})
            continue
        if float(live.get("turnover24h_usd") or 0.0) < float(args.min_turnover_usd):
            skipped.append({"symbol": sym, "reason": "turnover_below_min"})
            continue
        if float(live.get("oi_usd") or 0.0) < float(args.min_oi_usd):
            skipped.append({"symbol": sym, "reason": "oi_below_min"})
            continue
        basis_pct = float(live.get("basis_pct") or 0.0)
        if abs(basis_pct) > float(args.max_abs_basis_pct):
            skipped.append({"symbol": sym, "reason": "basis_too_wide"})
            continue
        perp_side = str(row.get("perp_side") or "")
        receive_8h_pct = float(live.get("funding_rate_8h_pct") or 0.0) if perp_side == "short" else -float(live.get("funding_rate_8h_pct") or 0.0)
        if receive_8h_pct < float(args.min_receive_8h_pct):
            skipped.append({"symbol": sym, "reason": "live_receive_below_min"})
            continue
        score = _score_row(row["net_usd_f"], receive_8h_pct, basis_pct)
        selected.append(
            {
                "symbol": sym,
                "hist_net_usd": round(row["net_usd_f"], 6),
                "hist_events": row["events_i"],
                "hist_mean_funding_rate": round(row["mean_funding_rate_f"], 8),
                "perp_side": perp_side,
                "hedge_leg": str(row.get("hedge_leg") or ""),
                "requires_spot_borrow": bool(row["requires_spot_borrow_i"]),
                "live_receive_8h_pct": round(receive_8h_pct, 6),
                "live_funding_annual_pct": round(float(live.get("funding_annual_pct") or 0.0), 3),
                "live_basis_pct": round(basis_pct, 4),
                "turnover24h_usd": round(float(live.get("turnover24h_usd") or 0.0), 2),
                "oi_usd": round(float(live.get("oi_usd") or 0.0), 2),
                "selection_score": round(score, 6),
            }
        )

    selected.sort(key=lambda r: (float(r["selection_score"]), float(r["live_receive_8h_pct"]), float(r["hist_net_usd"])), reverse=True)
    selected = selected[: max(1, int(args.max_symbols))]
    if not selected:
        print("error=no_live_selected_symbols", file=sys.stderr)
        print(json.dumps({"per_symbol_csv": str(per_symbol_csv), "skipped": skipped[:30]}, ensure_ascii=True))
        return 4

    per_symbol_capital = max(25.0, float(args.capital_usd) / max(1, len(selected)))
    for row in selected:
        row["target_notional_usd"] = round(per_symbol_capital, 2)
        row["execution_hint"] = f"{row['perp_side']}_perp + {row['hedge_leg']}"

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    raw_json = out_dir / f"live_scan_{ts}.json"
    plan_json = out_dir / f"plan_{ts}.json"
    plan_csv = out_dir / f"plan_{ts}.csv"
    latest_json = out_dir / "latest_plan.json"
    latest_csv = out_dir / "latest_plan.csv"
    raw_json.write_text(json.dumps(raw_live_export, ensure_ascii=True, indent=2), encoding="utf-8")
    report = {
        "ts_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "per_symbol_csv": str(per_symbol_csv),
        "capital_usd": round(float(args.capital_usd), 2),
        "per_symbol_capital_usd": round(per_symbol_capital, 2),
        "allow_borrow_legs": bool(int(args.allow_borrow_legs)),
        "positive_carry_only": bool(int(args.positive_carry_only)),
        "min_receive_8h_pct": float(args.min_receive_8h_pct),
        "max_abs_basis_pct": float(args.max_abs_basis_pct),
        "selected": selected,
        "skipped": skipped[:30],
    }
    plan_json.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    latest_json.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    with plan_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "symbol",
                "target_notional_usd",
                "perp_side",
                "hedge_leg",
                "requires_spot_borrow",
                "hist_net_usd",
                "hist_events",
                "live_receive_8h_pct",
                "live_funding_annual_pct",
                "live_basis_pct",
                "selection_score",
                "execution_hint",
            ]
        )
        for row in selected:
            w.writerow(
                [
                    row["symbol"],
                    f"{float(row['target_notional_usd']):.2f}",
                    row["perp_side"],
                    row["hedge_leg"],
                    int(bool(row["requires_spot_borrow"])),
                    f"{float(row['hist_net_usd']):.6f}",
                    int(row["hist_events"]),
                    f"{float(row['live_receive_8h_pct']):.6f}",
                    f"{float(row['live_funding_annual_pct']):.3f}",
                    f"{float(row['live_basis_pct']):.4f}",
                    f"{float(row['selection_score']):.6f}",
                    row["execution_hint"],
                ]
            )
    latest_csv.write_text(plan_csv.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"saved_json={plan_json}")
    print(f"saved_csv={plan_csv}")
    print(json.dumps(report, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
