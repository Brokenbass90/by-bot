#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
basis_arb_backtest.py — same-exchange spot↔perp basis arbitrage backtest.

Симулирует strategies/basis_arb_v1.py на исторических данных Bybit:
  - Тянет 1h spot ohlc для каждого символа (USDT pair)
  - Тянет 1h perp ohlc для того же символа
  - Тянет funding rate history
  - На каждом часовом баре пересчитывает basis = (perp - spot) / spot * 100
  - При basis > entry_threshold вход (spot+perp одновременно)
  - Exit: convergence < exit_threshold OR funding boundary OR max_hold OR SL

Output (совместим с run_strategy_autoresearch.py + auto_apply):
  - backtest_runs/basis_arb_<tag>/summary.csv     (общая статистика)
  - backtest_runs/basis_arb_<tag>/trades.csv      (все сделки)
  - backtest_runs/basis_arb_<tag>/monthly.csv     (помесячная разбивка)

Usage:
  python3 scripts/basis_arb_backtest.py \
      --symbols BTCUSDT,ETHUSDT,SOLUSDT \
      --days 365 \
      --end 2026-04-30 \
      --per_leg_usd 100 \
      --entry_threshold_pct 0.15 \
      --exit_converge_pct 0.03 \
      --fee_bps 10 \
      --slippage_bps 2 \
      --tag basis_v1_365d_majors

Acceptance gate:
  PF >= 1.5 AND DD <= 3% AND trades >= 50 AND positive_months >= 10/12
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.basis_arb_v1 import BasisArbV1Config, BasisArbV1Strategy, BasisArbSignal


BYBIT_BASE = "https://api.bybit.com"
KLINE_LIMIT_PER_REQ = 1000


def _get_json(url: str, params: Dict, timeout: float = 30.0, retries: int = 5) -> Dict:
    qs = urllib.parse.urlencode(params)
    full = f"{url}?{qs}"
    for i in range(retries):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": "by-bot/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)
    raise RuntimeError("unreachable")


def _fetch_klines(category: str, symbol: str, interval: str, start_ms: int, end_ms: int) -> List[List]:
    """Fetch all klines in window. Returns sorted oldest→newest."""
    out: List[List] = []
    cur_end = end_ms
    while True:
        data = _get_json(
            f"{BYBIT_BASE}/v5/market/kline",
            {"category": category, "symbol": symbol, "interval": interval,
             "start": start_ms, "end": cur_end, "limit": KLINE_LIMIT_PER_REQ},
        )
        if str(data.get("retCode")) != "0":
            raise RuntimeError(f"kline err {category}/{symbol}: {data.get('retMsg')}")
        rows = (data.get("result") or {}).get("list") or []
        if not rows:
            break
        # Bybit returns newest→oldest
        out.extend(rows)
        oldest_ts = int(rows[-1][0])
        if oldest_ts <= start_ms:
            break
        cur_end = oldest_ts - 1
        time.sleep(0.1)
    # Deduplicate + sort oldest→newest
    seen = {}
    for r in out:
        seen[int(r[0])] = r
    return sorted(seen.values(), key=lambda r: int(r[0]))


def _fetch_funding(symbol: str, start_ms: int, end_ms: int) -> List[Dict[str, Any]]:
    """Fetch funding rate history."""
    out = []
    cur_end = end_ms
    while True:
        data = _get_json(
            f"{BYBIT_BASE}/v5/market/funding/history",
            {"category": "linear", "symbol": symbol,
             "startTime": start_ms, "endTime": cur_end, "limit": 200},
        )
        if str(data.get("retCode")) != "0":
            break
        rows = (data.get("result") or {}).get("list") or []
        if not rows:
            break
        for r in rows:
            out.append({
                "ts": int(r.get("fundingRateTimestamp", 0)),
                "rate": float(r.get("fundingRate", 0)),
            })
        oldest = min(int(r.get("fundingRateTimestamp", 0)) for r in rows)
        if oldest <= start_ms:
            break
        cur_end = oldest - 1
        time.sleep(0.1)
    return sorted(out, key=lambda x: x["ts"])


@dataclass
class Trade:
    symbol: str
    side: str
    entry_ts: int
    exit_ts: int
    entry_spot: float
    entry_perp: float
    exit_spot: float
    exit_perp: float
    entry_basis_pct: float
    exit_basis_pct: float
    per_leg_usd: float
    spot_pnl_pct: float
    perp_pnl_pct: float
    funding_pnl_usd: float
    fees_usd: float
    net_pnl_usd: float
    exit_reason: str
    bars_held: int


def _backtest_symbol(
    symbol: str,
    spot_bars: List[List],
    perp_bars: List[List],
    funding_history: List[Dict[str, Any]],
    cfg: BasisArbV1Config,
    per_leg_usd: float,
    fee_bps: float,
    slippage_bps: float,
) -> List[Trade]:
    """Backtest single symbol. Returns trade list."""
    if not spot_bars or not perp_bars:
        return []

    # Build perp_by_ts and funding_by_ts for fast lookup
    perp_by_ts = {int(b[0]): b for b in perp_bars}
    funding_ts = sorted([f["ts"] for f in funding_history])
    funding_lookup = {f["ts"]: f["rate"] for f in funding_history}

    strategy = BasisArbV1Strategy(cfg)
    trades: List[Trade] = []
    open_pos: Optional[BasisArbSignal] = None
    pos_entry_ts: int = 0
    pos_bars_held: int = 0
    funding_accumulated: float = 0.0
    paid_funding_ts: set[int] = set()

    fee_per_leg = (fee_bps + slippage_bps) / 10000.0  # 1 leg, in absolute fraction

    for spot_bar in spot_bars:
        ts = int(spot_bar[0])
        spot_close = float(spot_bar[4])
        if ts not in perp_by_ts:
            continue
        perp_bar = perp_by_ts[ts]
        perp_close = float(perp_bar[4])

        if open_pos is None:
            # Check entry
            sig = strategy.signal(
                symbol,
                spot_price=spot_close,
                perp_price=perp_close,
                funding_rate_8h=None,  # backtest entry doesn't time funding directly
                seconds_to_funding=None,
            )
            if sig:
                open_pos = sig
                pos_entry_ts = ts
                pos_bars_held = 0
                funding_accumulated = 0.0
                paid_funding_ts = set()
        else:
            pos_bars_held += 1
            # Check if we crossed a funding boundary
            funding_paid_this_bar = 0.0
            for f in funding_history:
                f_ts = int(f["ts"])
                if pos_entry_ts < f_ts <= ts and f_ts not in paid_funding_ts:
                    # Add funding payment based on side
                    if open_pos.side == "perp_short_spot_long":
                        # We are short perp; if rate > 0 we receive, < 0 we pay
                        funding_paid_this_bar += f["rate"] * open_pos.per_leg_usd
                    else:
                        # Long perp; if rate > 0 we pay, < 0 we receive
                        funding_paid_this_bar -= f["rate"] * open_pos.per_leg_usd
                    paid_funding_ts.add(f_ts)

            funding_accumulated += funding_paid_this_bar
            passed_boundary = funding_paid_this_bar != 0

            should_exit, reason = strategy.should_exit(
                open_pos,
                current_spot=spot_close,
                current_perp=perp_close,
                bars_held=pos_bars_held,
                passed_funding_boundary=passed_boundary,
            )

            if should_exit:
                exit_basis_pct = (perp_close - spot_close) / spot_close * 100.0
                if open_pos.side == "perp_short_spot_long":
                    spot_pnl_pct = (spot_close - open_pos.spot_price) / open_pos.spot_price
                    perp_pnl_pct = (open_pos.perp_price - perp_close) / open_pos.perp_price
                else:
                    spot_pnl_pct = (open_pos.spot_price - spot_close) / open_pos.spot_price
                    perp_pnl_pct = (perp_close - open_pos.perp_price) / open_pos.perp_price

                # Convert to $ on per_leg_usd
                spot_pnl_usd = spot_pnl_pct * open_pos.per_leg_usd
                perp_pnl_usd = perp_pnl_pct * open_pos.per_leg_usd
                fees_usd = fee_per_leg * open_pos.per_leg_usd * 4  # entry+exit on 2 legs
                net_pnl = spot_pnl_usd + perp_pnl_usd + funding_accumulated - fees_usd

                trades.append(Trade(
                    symbol=symbol,
                    side=open_pos.side,
                    entry_ts=pos_entry_ts,
                    exit_ts=ts,
                    entry_spot=open_pos.spot_price,
                    entry_perp=open_pos.perp_price,
                    exit_spot=spot_close,
                    exit_perp=perp_close,
                    entry_basis_pct=open_pos.basis_pct,
                    exit_basis_pct=exit_basis_pct,
                    per_leg_usd=open_pos.per_leg_usd,
                    spot_pnl_pct=round(spot_pnl_pct * 100, 4),
                    perp_pnl_pct=round(perp_pnl_pct * 100, 4),
                    funding_pnl_usd=round(funding_accumulated, 4),
                    fees_usd=round(fees_usd, 4),
                    net_pnl_usd=round(net_pnl, 4),
                    exit_reason=reason,
                    bars_held=pos_bars_held,
                ))
                open_pos = None

    return trades


def _summarize(trades: List[Trade], per_leg_usd: float) -> Dict[str, Any]:
    if not trades:
        return {
            "trades": 0, "net_pnl": 0.0, "profit_factor": 0.0,
            "winrate": 0.0, "max_drawdown": 0.0, "avg_pnl_per_trade": 0.0,
            "negative_months": 0, "positive_months": 0,
        }
    total_pnl = sum(t.net_pnl_usd for t in trades)
    gross_win = sum(t.net_pnl_usd for t in trades if t.net_pnl_usd > 0)
    gross_loss = abs(sum(t.net_pnl_usd for t in trades if t.net_pnl_usd < 0))
    pf = gross_win / gross_loss if gross_loss > 0 else 99.0
    winrate = sum(1 for t in trades if t.net_pnl_usd > 0) / len(trades)

    # Build equity curve for drawdown
    equity = per_leg_usd * 2  # initial 2 legs
    peak = equity
    max_dd = 0.0
    for t in sorted(trades, key=lambda x: x.exit_ts):
        equity += t.net_pnl_usd
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Monthly buckets
    monthly: Dict[str, float] = defaultdict(float)
    for t in trades:
        month = datetime.fromtimestamp(t.exit_ts / 1000, tz=timezone.utc).strftime("%Y-%m")
        monthly[month] += t.net_pnl_usd
    neg_months = sum(1 for v in monthly.values() if v < 0)
    pos_months = sum(1 for v in monthly.values() if v > 0)

    return {
        "trades":          len(trades),
        "net_pnl":         round(total_pnl, 2),
        "net_pnl_pct":     round(total_pnl / (per_leg_usd * 2) * 100, 2),
        "profit_factor":   round(pf, 3),
        "winrate":         round(winrate, 3),
        "max_drawdown":    round(max_dd, 3),
        "avg_pnl_per_trade": round(total_pnl / len(trades), 4),
        "negative_months": neg_months,
        "positive_months": pos_months,
        "monthly_pnl":     {k: round(v, 2) for k, v in sorted(monthly.items())},
    }


def _write_outputs(out_dir: Path, summary: Dict, trades: List[Trade]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # summary.csv (compatible with run_strategy_autoresearch _extract_metrics)
    with (out_dir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["trades", "net_pnl", "profit_factor", "winrate", "max_drawdown"])
        w.writerow([
            summary["trades"],
            summary["net_pnl"],
            summary["profit_factor"],
            summary["winrate"],
            summary["max_drawdown"],
        ])

    # trades.csv
    with (out_dir / "trades.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "symbol", "side", "entry_ts", "exit_ts",
            "entry_spot", "entry_perp", "exit_spot", "exit_perp",
            "entry_basis_pct", "exit_basis_pct",
            "spot_pnl_pct", "perp_pnl_pct", "funding_pnl_usd",
            "fees_usd", "net_pnl_usd", "exit_reason", "bars_held",
            "per_leg_usd",
        ])
        w.writeheader()
        for t in trades:
            w.writerow({
                "symbol": t.symbol, "side": t.side,
                "entry_ts": t.entry_ts, "exit_ts": t.exit_ts,
                "entry_spot": t.entry_spot, "entry_perp": t.entry_perp,
                "exit_spot": t.exit_spot, "exit_perp": t.exit_perp,
                "entry_basis_pct": t.entry_basis_pct,
                "exit_basis_pct": t.exit_basis_pct,
                "spot_pnl_pct": t.spot_pnl_pct,
                "perp_pnl_pct": t.perp_pnl_pct,
                "funding_pnl_usd": t.funding_pnl_usd,
                "fees_usd": t.fees_usd,
                "net_pnl_usd": t.net_pnl_usd,
                "exit_reason": t.exit_reason,
                "bars_held": t.bars_held,
                "per_leg_usd": t.per_leg_usd,
            })

    # monthly.csv
    with (out_dir / "monthly.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["month", "net_pnl"])
        for month, pnl in summary.get("monthly_pnl", {}).items():
            w.writerow([month, pnl])

    # summary.json (richer)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Basis arbitrage backtest.")
    ap.add_argument("--symbols", required=True, help="Comma-separated USDT symbols.")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--end", default="", help="End date YYYY-MM-DD; default=today UTC.")
    ap.add_argument("--per_leg_usd", type=float, default=100.0)
    ap.add_argument("--entry_threshold_pct", type=float, default=0.15)
    ap.add_argument("--exit_converge_pct", type=float, default=0.03)
    ap.add_argument("--max_hold_bars_5m", type=int, default=24)  # 24h on 1h bars
    ap.add_argument("--fee_bps", type=float, default=10.0)
    ap.add_argument("--slippage_bps", type=float, default=2.0)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out_root", default="backtest_runs")
    args = ap.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if args.end:
        end_dt = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=args.days)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    print(f"[basis_arb] backtest {args.tag}")
    print(f"  symbols: {symbols}")
    print(f"  window:  {start_dt.isoformat()} → {end_dt.isoformat()} ({args.days}d)")
    print(f"  per_leg: ${args.per_leg_usd}  entry≥{args.entry_threshold_pct}%  exit≤{args.exit_converge_pct}%")

    # Strategy config with backtest params
    cfg = BasisArbV1Config(
        per_leg_usd=args.per_leg_usd,
        symbol_allowlist=symbols,
        entry_threshold_pct=args.entry_threshold_pct,
        exit_converge_pct=args.exit_converge_pct,
        max_hold_bars_5m=args.max_hold_bars_5m,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
    )

    all_trades: List[Trade] = []
    for sym in symbols:
        print(f"[basis_arb] {sym}: fetching klines...")
        try:
            spot_bars = _fetch_klines("spot", sym, "60", start_ms, end_ms)
            perp_bars = _fetch_klines("linear", sym, "60", start_ms, end_ms)
            funding = _fetch_funding(sym, start_ms, end_ms)
            print(f"  spot={len(spot_bars)}  perp={len(perp_bars)}  funding={len(funding)}")
            if not spot_bars or not perp_bars:
                print(f"  ⚠️  missing data, skip")
                continue
            trades = _backtest_symbol(
                sym, spot_bars, perp_bars, funding, cfg,
                args.per_leg_usd, args.fee_bps, args.slippage_bps,
            )
            print(f"  trades={len(trades)}")
            all_trades.extend(trades)
        except Exception as exc:
            print(f"  ❌ {type(exc).__name__}: {exc}")

    summary = _summarize(all_trades, args.per_leg_usd * len(symbols))
    print()
    print(f"[basis_arb] SUMMARY")
    print(f"  trades:       {summary['trades']}")
    print(f"  net_pnl:      ${summary['net_pnl']}")
    print(f"  net_pnl_pct:  {summary.get('net_pnl_pct', 0)}%")
    print(f"  profit_factor: {summary['profit_factor']}")
    print(f"  winrate:      {summary['winrate'] * 100:.1f}%")
    print(f"  max_drawdown: {summary['max_drawdown']}%")
    print(f"  pos_months/neg_months: {summary['positive_months']}/{summary['negative_months']}")

    # Write outputs (compatible with run_strategy_autoresearch + auto_apply)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / args.out_root / f"basis_arb_{stamp}_{args.tag}"
    _write_outputs(out_dir, summary, all_trades)
    print(f"[basis_arb] written → {out_dir}")

    # Acceptance gate hint
    print()
    if summary["profit_factor"] >= 1.5 and summary["max_drawdown"] <= 3.0 and summary["trades"] >= 50:
        print("✅ Acceptance gate: PASS (PF≥1.5, DD≤3%, trades≥50)")
    else:
        reasons = []
        if summary["profit_factor"] < 1.5:
            reasons.append(f"PF={summary['profit_factor']}<1.5")
        if summary["max_drawdown"] > 3.0:
            reasons.append(f"DD={summary['max_drawdown']}%>3")
        if summary["trades"] < 50:
            reasons.append(f"trades={summary['trades']}<50")
        print(f"❌ Acceptance gate: FAIL ({', '.join(reasons)})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
