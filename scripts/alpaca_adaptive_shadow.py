#!/usr/bin/env python3
"""Run alpaca_adaptive_v1 as a shadow paper advisor.

No orders are submitted. This lets the adaptive strategy accumulate an honest
"would trade" history next to the currently active v38 paper bridge without
making the two managers fight for the same Alpaca paper positions.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.alpaca_v3_event_backtest import DEFAULT_UNIVERSE, _fetch
from strategies.alpaca_adaptive_v1 import AdaptiveConfig, select
from strategies.alpaca_dynamic_v4_event import SECTOR_MAP


def _latest_close(df: Any) -> float:
    try:
        return float(df["Close"].dropna().iloc[-1])
    except Exception:
        return 0.0


def _close_series(df: Any) -> list[float]:
    try:
        return [float(x) for x in df["Close"].dropna().tolist() if float(x) > 0]
    except Exception:
        return []


def run_shadow(
    *,
    symbols: list[str],
    start: str,
    end: str,
    capital: float,
    max_positions: int,
    cache_dir: Path,
    target_alloc_pct: float,
) -> dict[str, Any]:
    fetch_symbols = sorted(set([s.upper() for s in symbols] + ["SPY"]))
    data = _fetch(fetch_symbols, start, end, cache_dir)
    closes = {sym: _close_series(df) for sym, df in data.items()}
    prices = {sym: _latest_close(df) for sym, df in data.items()}

    cfg = AdaptiveConfig(max_positions=max_positions)
    selected = select(
        {sym: xs for sym, xs in closes.items() if sym != "SPY"},
        closes.get("SPY", []),
        sectors=SECTOR_MAP,
        cfg=cfg,
    )

    target_alloc = max(0.0, min(1.0, target_alloc_pct / 100.0))
    picks = []
    for pick in selected.get("picks") or []:
        symbol = str(pick["symbol"])
        weight = float(pick.get("weight") or 0.0)
        price = float(prices.get(symbol) or 0.0)
        notional = capital * target_alloc * weight
        fractional_qty = notional / price if price > 0 else 0.0
        whole_qty = int(fractional_qty)
        min_capital_for_one_share = price / max(1e-12, target_alloc * weight) if price > 0 and weight > 0 else 0.0
        picks.append(
            {
                **pick,
                "latest_close": round(price, 4),
                "target_notional": round(notional, 2),
                "fractional_qty": round(fractional_qty, 6),
                "whole_qty_at_capital": whole_qty,
                "native_trailing_possible_at_capital": whole_qty >= 1,
                "min_capital_for_one_share": round(min_capital_for_one_share, 2),
            }
        )

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "shadow_no_orders",
        "strategy": "alpaca_adaptive_v1",
        "capital": capital,
        "target_alloc_pct": target_alloc_pct,
        "max_positions": max_positions,
        "start": start,
        "end": end,
        "regime_ok": bool(selected.get("regime_ok")),
        "reason": selected.get("reason"),
        "cash_frac": selected.get("cash_frac", 1.0),
        "picks": picks,
        "native_trailing_min_capital_for_all_picks": (
            round(max((float(p.get("min_capital_for_one_share") or 0.0) for p in picks), default=0.0), 2)
        ),
        "symbols_loaded": sorted(data),
    }


def _md(report: dict[str, Any]) -> str:
    lines = [
        "# Alpaca Adaptive V1 Shadow",
        "",
        f"- generated_at_utc: `{report['generated_at_utc']}`",
        f"- mode: `{report['mode']}`",
        f"- capital: `${report['capital']:.2f}`",
        f"- target_alloc_pct: `{report['target_alloc_pct']}`",
        f"- regime_ok: `{report['regime_ok']}` reason: `{report['reason']}`",
        f"- cash_frac: `{report['cash_frac']}`",
        f"- native_trailing_min_capital_for_all_picks: `${report['native_trailing_min_capital_for_all_picks']:.2f}`",
        "",
        "| symbol | sector | weight | close | notional | frac_qty | whole_qty | native trail? | min capital/share |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for p in report["picks"]:
        lines.append(
            "| {symbol} | {sector} | {weight:.3f} | {latest_close:.2f} | {target_notional:.2f} | "
            "{fractional_qty:.4f} | {whole_qty_at_capital} | {native_trailing_possible_at_capital} | "
            "{min_capital_for_one_share:.2f} |".format(**p)
        )
    if not report["picks"]:
        lines.append("| cash | - | 0 | 0 | 0 | 0 | 0 | False | 0 |")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="alpaca_adaptive_v1 shadow advisor")
    ap.add_argument("--symbols", default=",".join(DEFAULT_UNIVERSE))
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--target-alloc-pct", type=float, default=70.0)
    ap.add_argument("--max-positions", type=int, default=4)
    ap.add_argument("--cache-dir", default="runtime/equities_yf_cache")
    ap.add_argument("--out-json", default="runtime/alpaca_adaptive_v1_shadow_latest.json")
    ap.add_argument("--out-md", default="runtime/alpaca_adaptive_v1_shadow_latest.md")
    args = ap.parse_args()

    end = args.end or (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    cache_dir = Path(args.cache_dir)
    if not cache_dir.is_absolute():
        cache_dir = ROOT / cache_dir
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    report = run_shadow(
        symbols=symbols,
        start=args.start,
        end=end,
        capital=float(args.capital),
        max_positions=int(args.max_positions),
        cache_dir=cache_dir,
        target_alloc_pct=float(args.target_alloc_pct),
    )

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not out_json.is_absolute():
        out_json = ROOT / out_json
    if not out_md.is_absolute():
        out_md = ROOT / out_md
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    out_md.write_text(_md(report), encoding="utf-8")
    print(f"json={out_json}")
    print(f"md={out_md}")
    print(f"regime_ok={report['regime_ok']} picks={','.join(p['symbol'] for p in report['picks']) or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
