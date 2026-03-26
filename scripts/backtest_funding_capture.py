#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
import math
import time
import random
import socket
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from pathlib import Path
from typing import Dict, List

_THIS_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from strategies.funding_hold_v1 import FundingHoldV1Config, FundingHoldV1Strategy


def _get_json(url: str, *, timeout_sec: float = 30.0, retries: int = 8) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "by-bot/1.0"})
    for i in range(max(1, int(retries))):
        try:
            with urllib.request.urlopen(req, timeout=float(timeout_sec)) as r:
                return json.loads(r.read().decode("utf-8"))
        except (TimeoutError, socket.timeout, urllib.error.URLError, ConnectionError, OSError):
            if i >= retries - 1:
                raise
            # Exponential backoff with small jitter.
            delay = min(20.0, (1.6 ** i) + random.uniform(0.05, 0.35))
            time.sleep(delay)
    raise RuntimeError("unreachable")


def _f(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _q(base: str, path: str, params: dict) -> dict:
    qs = urllib.parse.urlencode(params)
    url = f"{base.rstrip('/')}{path}?{qs}"
    js = _get_json(url)
    code = int((js or {}).get("retCode", 0) or 0)
    if code == 10006:
        # Bybit rate limit: retry a few times with backoff.
        for i in range(6):
            time.sleep(min(30.0, 2.0 + (2.0 ** i) + random.uniform(0.0, 0.5)))
            js = _get_json(url)
            code = int((js or {}).get("retCode", 0) or 0)
            if code != 10006:
                break
    return js


def _utc_ms_now() -> int:
    return int(time.time() * 1000)


def _ym_from_ms(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m")


@dataclass
class FundingPoint:
    ts_ms: int
    rate: float


def fetch_tickers_linear(base: str) -> List[dict]:
    js = _q(base, "/v5/market/tickers", {"category": "linear"})
    return (((js or {}).get("result") or {}).get("list") or [])


def fetch_funding_history(base: str, symbol: str, start_ms: int, end_ms: int) -> List[FundingPoint]:
    out: List[FundingPoint] = []
    cursor_end = int(end_ms)

    while cursor_end > start_ms:
        js = _q(
            base,
            "/v5/market/funding/history",
            {
                "category": "linear",
                "symbol": symbol,
                "startTime": int(start_ms),
                "endTime": int(cursor_end),
                "limit": 200,
            },
        )
        rows = (((js or {}).get("result") or {}).get("list") or [])
        if not rows:
            break

        batch: List[FundingPoint] = []
        for r in rows:
            ts = int(_f(r.get("fundingRateTimestamp"), 0.0))
            fr = _f(r.get("fundingRate"), 0.0)
            if ts <= 0:
                continue
            if ts < start_ms or ts > end_ms:
                continue
            batch.append(FundingPoint(ts_ms=ts, rate=fr))

        if not batch:
            break

        out.extend(batch)
        earliest = min(x.ts_ms for x in batch)
        if earliest >= cursor_end:
            break
        cursor_end = earliest - 1
        time.sleep(0.12)

    # de-dup + sort ascending
    uniq: Dict[int, FundingPoint] = {x.ts_ms: x for x in out}
    pts = list(uniq.values())
    pts.sort(key=lambda x: x.ts_ms)
    return pts


def funding_interval_hours(points: List[FundingPoint]) -> float:
    if len(points) < 2:
        return 0.0
    diffs_h = []
    prev = points[0].ts_ms
    for p in points[1:]:
        d_ms = p.ts_ms - prev
        if d_ms > 0:
            diffs_h.append(d_ms / 3_600_000.0)
        prev = p.ts_ms
    if not diffs_h:
        return 0.0
    return float(median(diffs_h))


def auto_select_symbols(
    base: str,
    top_n: int,
    min_turnover_usd: float,
    min_oi_usd: float,
    min_abs_funding_8h_pct: float,
    max_abs_funding_8h_pct: float,
    exclude_symbols: set[str],
) -> List[str]:
    rows = fetch_tickers_linear(base)
    scored: List[tuple[float, str]] = []
    for r in rows:
        sym = str(r.get("symbol") or "")
        if not sym.endswith("USDT"):
            continue
        if sym in exclude_symbols:
            continue
        turn = _f(r.get("turnover24h"))
        oi = _f(r.get("openInterestValue"))
        fr = abs(_f(r.get("fundingRate"))) * 100.0
        if turn < min_turnover_usd:
            continue
        if oi < min_oi_usd:
            continue
        if fr < min_abs_funding_8h_pct:
            continue
        if max_abs_funding_8h_pct > 0 and fr > max_abs_funding_8h_pct:
            continue
        score = fr * math.log10(max(10.0, turn))
        scored.append((score, sym))
    scored.sort(reverse=True)
    return [s for _, s in scored[: max(1, top_n)]]


def main() -> int:
    ap = argparse.ArgumentParser(description="Historical funding-capture prototype (delta-neutral approximation).")
    ap.add_argument("--base", default="https://api.bybit.com")
    ap.add_argument("--symbols", default="", help="Comma-separated symbols; empty => auto select from tickers.")
    ap.add_argument("--top_n", type=int, default=12)
    ap.add_argument("--selection_buffer_mult", type=float, default=3.0, help="When auto-selecting, fetch top_n*mult candidates before historical filters.")
    ap.add_argument("--min_turnover_usd", type=float, default=2_000_000.0)
    ap.add_argument("--min_oi_usd", type=float, default=500_000.0)
    ap.add_argument("--min_abs_funding_8h_pct", type=float, default=0.008)
    ap.add_argument("--max_abs_funding_8h_pct", type=float, default=0.40, help="Exclude extreme outliers by current |funding| in %% (0 disables).")
    ap.add_argument("--exclude_symbols", default="", help="Comma-separated symbols to exclude from selection.")
    ap.add_argument("--min_events_per_symbol", type=int, default=60, help="Min funding prints in period to keep symbol.")
    ap.add_argument("--min_interval_hours", type=float, default=0.0, help="Min median funding interval in hours (0 disables).")
    ap.add_argument("--max_interval_hours", type=float, default=0.0, help="Max median funding interval in hours (0 disables).")
    ap.add_argument("--clip_abs_rate", type=float, default=0.0025, help="Clip |fundingRate| per event (decimal, 0 disables).")
    ap.add_argument("--max_top_symbol_share", type=float, default=0.45, help="Selection cap for top symbol |net| share.")
    ap.add_argument("--min_symbol_net_usd", type=float, default=-0.25, help="Minimum net USD per symbol to include into basket.")
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--end_ms", type=int, default=0, help="UTC ms; 0 = now")
    ap.add_argument("--notional_per_symbol", type=float, default=100.0)
    ap.add_argument("--fee_bps_open_close_perp", type=float, default=6.0, help="Total perp taker open+close fees in bps.")
    ap.add_argument("--fee_bps_open_close_spot", type=float, default=10.0, help="Total spot leg open+close fees in bps.")
    ap.add_argument("--mode", choices=["hold", "flip"], default="hold", help="hold=one side for full period, flip=switch side each funding print.")
    ap.add_argument("--flip_fee_bps", type=float, default=2.0, help="Extra fee bps per notional each time direction flips (used in mode=flip).")
    ap.add_argument("--positive-carry-only", type=int, default=0, help="When mode=hold, keep only short-perp / long-spot profiles.")
    ap.add_argument("--exclude-requires-borrow", type=int, default=0, help="When mode=hold, drop long-perp profiles that require short spot / borrow.")
    ap.add_argument("--tag", default="funding_capture")
    args = ap.parse_args()

    end_ms = int(args.end_ms) if int(args.end_ms) > 0 else _utc_ms_now()
    start_ms = end_ms - int(args.days) * 86400 * 1000

    symbols = [x.strip().upper() for x in str(args.symbols).split(",") if x.strip()]
    auto_selected = not bool(symbols)
    exclude_symbols = {x.strip().upper() for x in str(args.exclude_symbols).replace(";", ",").split(",") if x.strip()}
    if auto_selected:
        buffered_top_n = max(1, int(round(float(args.top_n) * max(1.0, float(args.selection_buffer_mult)))))
        symbols = auto_select_symbols(
            base=args.base,
            top_n=buffered_top_n,
            min_turnover_usd=float(args.min_turnover_usd),
            min_oi_usd=float(args.min_oi_usd),
            min_abs_funding_8h_pct=float(args.min_abs_funding_8h_pct),
            max_abs_funding_8h_pct=float(args.max_abs_funding_8h_pct),
            exclude_symbols=exclude_symbols,
        )
    if not symbols:
        raise SystemExit("No symbols selected (try lower liquidity/funding filters).")

    out_dir = Path("backtest_runs") / f"funding_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{args.tag}"
    out_dir.mkdir(parents=True, exist_ok=True)
    per_symbol_csv = out_dir / "funding_per_symbol.csv"
    monthly_csv = out_dir / "monthly_pnl.csv"
    summary_csv = out_dir / "summary.csv"

    notional = float(args.notional_per_symbol)
    fee_total_bps = float(args.fee_bps_open_close_perp) + float(args.fee_bps_open_close_spot)
    fee_total_usd = notional * (fee_total_bps / 10000.0)
    flip_fee_usd = notional * (float(args.flip_fee_bps) / 10000.0)

    rows_symbol = []
    by_symbol_month: Dict[str, Dict[str, float]] = {}
    total_events = 0
    total_gross = 0.0
    total_net = 0.0
    used_symbols: List[str] = []

    for sym in symbols:
        pts = fetch_funding_history(args.base, sym, start_ms, end_ms)
        if not pts:
            continue
        if len(pts) < int(args.min_events_per_symbol):
            continue
        interval_h = funding_interval_hours(pts)
        if float(args.min_interval_hours) > 0 and interval_h < float(args.min_interval_hours):
            continue
        if float(args.max_interval_hours) > 0 and interval_h > float(args.max_interval_hours):
            continue

        gross = 0.0
        net_after_flips = 0.0
        flips = 0
        receive_events = 0
        pay_events = 0
        pos = 0  # +1 long perp, -1 short perp
        mean_fr_raw = sum(float(x.rate) for x in pts) / max(1, len(pts))
        if args.mode == "hold":
            pos = -1 if mean_fr_raw >= 0 else 1

        prev_pos = pos
        sym_month: Dict[str, float] = {}
        for p in pts:
            fr = float(p.rate)
            if float(args.clip_abs_rate) > 0:
                lim = abs(float(args.clip_abs_rate))
                fr = max(-lim, min(lim, fr))
            if args.mode == "flip":
                pos = -1 if fr >= 0 else 1  # choose side that receives this print
                if prev_pos != 0 and pos != prev_pos:
                    flips += 1
                    net_after_flips -= flip_fee_usd
                prev_pos = pos

            pnl = (-pos) * fr * notional
            gross += pnl
            net_after_flips += pnl
            if pnl >= 0:
                receive_events += 1
            else:
                pay_events += 1
            ym = _ym_from_ms(p.ts_ms)
            sym_month[ym] = sym_month.get(ym, 0.0) + pnl

        net = net_after_flips - fee_total_usd
        if args.mode == "hold":
            perp_side = "short" if pos < 0 else "long"
            hedge_leg = "long_spot" if pos < 0 else "short_spot_or_borrow"
            requires_spot_borrow = 1 if pos > 0 else 0
        else:
            perp_side = "dynamic"
            hedge_leg = "dynamic"
            requires_spot_borrow = 0
        rows_symbol.append(
            {
                "symbol": sym,
                "funding_events": len(pts),
                "median_interval_h": round(interval_h, 3),
                "mean_funding_rate": round(mean_fr_raw, 8),
                "perp_side": perp_side,
                "hedge_leg": hedge_leg,
                "requires_spot_borrow": requires_spot_borrow,
                "receive_events": receive_events,
                "pay_events": pay_events,
                "mode": args.mode,
                "flips": flips,
                "gross_funding_usd": round(gross, 6),
                "flip_fees_usd": round(flips * flip_fee_usd, 6),
                "fees_open_close_usd": round(fee_total_usd, 6),
                "net_usd": round(net, 6),
                "net_pct_on_notional": round((net / notional) * 100.0, 4) if notional > 0 else 0.0,
            }
        )
        by_symbol_month[sym] = sym_month

    if args.mode == "hold":
        filtered_rows_symbol = []
        for r in rows_symbol:
            perp_side = str(r.get("perp_side") or "")
            requires_spot_borrow = int(r.get("requires_spot_borrow") or 0)
            if int(args.positive_carry_only) == 1 and perp_side != "short":
                continue
            if int(args.exclude_requires_borrow) == 1 and requires_spot_borrow == 1:
                continue
            filtered_rows_symbol.append(r)
        rows_symbol = filtered_rows_symbol

    selector = FundingHoldV1Strategy(
        FundingHoldV1Config(
            max_top_symbol_share=float(args.max_top_symbol_share),
            min_symbol_net_usd=float(args.min_symbol_net_usd),
            top_n=int(args.top_n),
        )
    )
    rows_symbol = selector.select(rows_symbol)
    rows_symbol.sort(key=lambda x: float(x.get("net_usd", 0.0)), reverse=True)
    used_symbols = [str(r.get("symbol", "")) for r in rows_symbol]

    by_month_gross: Dict[str, float] = {}
    for r in rows_symbol:
        sym = str(r.get("symbol", ""))
        total_events += int(r.get("funding_events", 0) or 0)
        total_gross += float(r.get("gross_funding_usd", 0.0) or 0.0)
        total_net += float(r.get("net_usd", 0.0) or 0.0)
        for ym, pnl in (by_symbol_month.get(sym) or {}).items():
            by_month_gross[ym] = by_month_gross.get(ym, 0.0) + float(pnl)

    with per_symbol_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "symbol",
                "funding_events",
                "median_interval_h",
                "mean_funding_rate",
                "perp_side",
                "hedge_leg",
                "requires_spot_borrow",
                "receive_events",
                "pay_events",
                "mode",
                "flips",
                "gross_funding_usd",
                "flip_fees_usd",
                "fees_open_close_usd",
                "net_usd",
                "net_pct_on_notional",
            ],
        )
        w.writeheader()
        for r in rows_symbol:
            w.writerow(r)

    with monthly_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["month", "gross_funding_usd"])
        for ym in sorted(by_month_gross.keys()):
            w.writerow([ym, f"{by_month_gross[ym]:.6f}"])

    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "tag",
                "days",
                "symbols",
                "notional_per_symbol",
                "fee_total_bps",
                "mode",
                "flip_fee_bps",
                "clip_abs_rate",
                "min_events_per_symbol",
                "min_interval_hours",
                "max_interval_hours",
                "positive_carry_only",
                "exclude_requires_borrow",
                "max_top_symbol_share",
                "min_symbol_net_usd",
                "funding_events",
                "gross_funding_total_usd",
                "flip_fees_total_usd",
                "fees_total_usd",
                "net_total_usd",
                "top_symbol_share_net",
            ]
        )
        top_share = 0.0
        if rows_symbol:
            total_abs = sum(abs(float(r.get("net_usd", 0.0))) for r in rows_symbol)
            if total_abs > 1e-12:
                top = max(abs(float(r.get("net_usd", 0.0))) for r in rows_symbol)
                top_share = top / total_abs
        w.writerow(
            [
                args.tag,
                int(args.days),
                ";".join(used_symbols),
                f"{notional:.2f}",
                f"{fee_total_bps:.2f}",
                args.mode,
                f"{float(args.flip_fee_bps):.2f}",
                f"{float(args.clip_abs_rate):.6f}",
                int(args.min_events_per_symbol),
                f"{float(args.min_interval_hours):.3f}",
                f"{float(args.max_interval_hours):.3f}",
                int(args.positive_carry_only),
                int(args.exclude_requires_borrow),
                f"{float(args.max_top_symbol_share):.3f}",
                f"{float(args.min_symbol_net_usd):.3f}",
                int(total_events),
                f"{total_gross:.6f}",
                f"{sum(float(r.get('flip_fees_usd', 0.0)) for r in rows_symbol):.6f}",
                f"{(len(rows_symbol) * fee_total_usd):.6f}",
                f"{total_net:.6f}",
                f"{top_share:.4f}",
            ]
        )

    print(f"Saved funding run to: {out_dir}")
    print(f"  summary: {summary_csv}")
    print(f"  per_symbol: {per_symbol_csv}")
    print(f"  monthly: {monthly_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
