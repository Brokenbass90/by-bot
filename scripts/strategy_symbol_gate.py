#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_THIS_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from strategies.funding_hold_v1 import FundingHoldV1Config, FundingHoldV1Strategy

MODE_SET = {"base", "stress"}


def _f(x: str, default: float = 0.0) -> float:
    try:
        return float(str(x).strip())
    except Exception:
        return default


def _i(x: str, default: int = 0) -> int:
    try:
        return int(float(str(x).strip()))
    except Exception:
        return default


@dataclass
class TradeRow:
    symbol: str
    mode: str
    status: str
    run_dir: str
    net: float
    pf: float
    trades: int
    winrate: float
    max_dd: float


def _extract_symbol_from_run_dir(run_dir: str) -> Optional[str]:
    # e.g. ..._AXSUSDT_base_180d
    m = re.search(r"_([A-Z0-9]+USDT)_(?:base|stress)_", run_dir or "")
    return m.group(1) if m else None


def _normalize_scan_row(raw: List[str], header: List[str]) -> Optional[TradeRow]:
    # Normal format by header
    row = {header[i]: (raw[i] if i < len(raw) else "") for i in range(len(header))}

    symbol = (row.get("symbol") or "").strip().upper()
    mode = (row.get("mode") or "").strip().lower()
    status = (row.get("status") or "").strip().lower()
    run_dir = (row.get("run_dir") or "").strip()
    net = row.get("net", "")
    pf = row.get("pf", "")
    trades = row.get("trades", "")
    winrate = row.get("winrate", "")
    max_dd = row.get("max_dd", "")

    # Broken/shifted case from old script, sample:
    # ,XSUSDT,base,ok,backtest_runs/...,-2.56,0.49,41,0.29,3.57
    # -> shift right by one and recover symbol via run_dir when possible.
    if mode not in MODE_SET and status in MODE_SET and run_dir == "ok":
        mode = status
        status = run_dir
        run_dir = net
        net, pf, trades, winrate, max_dd = pf, trades, winrate, max_dd, (raw[10] if len(raw) > 10 else "")
        # rebuild symbol from second column and run_dir
        cand = (row.get("mode") or "").strip().upper()
        if cand and cand.endswith("USDT"):
            symbol = cand
        # fix truncated `XSUSDT` style from malformed line using run_dir tag
        from_rd = _extract_symbol_from_run_dir(run_dir)
        if from_rd:
            symbol = from_rd

    # If symbol still missing, try run_dir parse.
    if not symbol or not symbol.endswith("USDT"):
        from_rd = _extract_symbol_from_run_dir(run_dir)
        if from_rd:
            symbol = from_rd

    if not symbol or mode not in MODE_SET:
        return None

    return TradeRow(
        symbol=symbol,
        mode=mode,
        status=status,
        run_dir=run_dir,
        net=_f(net),
        pf=_f(pf),
        trades=_i(trades),
        winrate=_f(winrate),
        max_dd=_f(max_dd),
    )


def gate_trade_scan(args: argparse.Namespace) -> int:
    src = Path(args.scan_csv)
    if not src.exists():
        raise SystemExit(f"scan_csv not found: {src}")

    rows: List[TradeRow] = []
    with src.open("r", encoding="utf-8", newline="") as f:
        r = csv.reader(f)
        header = next(r, [])
        if not header:
            raise SystemExit("empty csv")
        for raw in r:
            if not raw:
                continue
            tr = _normalize_scan_row(raw, header)
            if tr:
                rows.append(tr)

    by_sym: Dict[str, Dict[str, TradeRow]] = {}
    for tr in rows:
        by_sym.setdefault(tr.symbol, {})[tr.mode] = tr

    selected: List[Tuple[float, str, TradeRow, TradeRow]] = []
    for sym, d in sorted(by_sym.items()):
        b = d.get("base")
        s = d.get("stress")
        if not b or not s:
            continue
        if b.status != "ok" or s.status != "ok":
            continue
        if b.net < args.min_net_base:
            continue
        if s.net < args.min_net_stress:
            continue
        if b.pf < args.min_pf_base:
            continue
        if s.pf < args.min_pf_stress:
            continue
        if b.trades < args.min_trades_base:
            continue
        if s.trades < args.min_trades_stress:
            continue
        if abs(s.max_dd) > args.max_dd_stress:
            continue
        score = 0.55 * s.net + 0.45 * b.net
        selected.append((score, sym, b, s))

    selected.sort(reverse=True, key=lambda x: x[0])

    out = Path(args.out_csv) if args.out_csv else src.with_name(src.stem + "_gated.csv")
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "score", "base_net", "base_pf", "base_trades", "stress_net", "stress_pf", "stress_trades", "stress_max_dd"])
        for score, sym, b, s in selected:
            w.writerow([sym, f"{score:.4f}", f"{b.net:.4f}", f"{b.pf:.3f}", b.trades, f"{s.net:.4f}", f"{s.pf:.3f}", s.trades, f"{s.max_dd:.4f}"])

    print(f"scan={src}")
    print(f"parsed_rows={len(rows)} symbols={len(by_sym)}")
    print(f"selected={len(selected)}")
    print(f"out={out}")
    if selected:
        syms = ",".join(x[1] for x in selected)
        print(f"symbols_csv={syms}")
    else:
        print("symbols_csv=")
    return 0


def gate_funding(args: argparse.Namespace) -> int:
    src = Path(args.per_symbol_csv)
    if not src.exists():
        raise SystemExit(f"per_symbol_csv not found: {src}")

    candidates: List[Dict[str, float]] = []
    with src.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            candidates.append(
                {
                    "symbol": str(row.get("symbol", "")).strip().upper(),
                    "net_usd": _f(row.get("net_usd", 0.0)),
                    "funding_events": _i(row.get("funding_events", 0)),
                }
            )

    # prefilter by events
    candidates = [x for x in candidates if int(x.get("funding_events", 0)) >= int(args.min_events)]

    selector = FundingHoldV1Strategy(
        FundingHoldV1Config(
            max_top_symbol_share=float(args.max_top_symbol_share),
            min_symbol_net_usd=float(args.min_symbol_net_usd),
            top_n=int(args.top_n),
        )
    )
    selected = selector.select(candidates)
    selected.sort(key=lambda x: float(x.get("net_usd", 0.0)), reverse=True)

    out = Path(args.out_csv) if args.out_csv else src.with_name(src.stem + "_gated.csv")
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "net_usd", "funding_events"])
        for x in selected:
            w.writerow([x.get("symbol", ""), f"{float(x.get('net_usd', 0.0)):.6f}", int(x.get("funding_events", 0))])

    print(f"scan={src}")
    print(f"candidates={len(candidates)} selected={len(selected)}")
    print(f"out={out}")
    print("symbols_csv=" + ",".join(str(x.get("symbol", "")) for x in selected))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Universal symbol gate for trade/funding strategies")
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("trade", help="Gate symbols from per-symbol base/stress scan CSV")
    t.add_argument("--scan_csv", required=True)
    t.add_argument("--min_net_base", type=float, default=0.0)
    t.add_argument("--min_net_stress", type=float, default=0.0)
    t.add_argument("--min_pf_base", type=float, default=1.0)
    t.add_argument("--min_pf_stress", type=float, default=1.0)
    t.add_argument("--min_trades_base", type=int, default=10)
    t.add_argument("--min_trades_stress", type=int, default=10)
    t.add_argument("--max_dd_stress", type=float, default=12.0)
    t.add_argument("--out_csv", default="")

    f = sub.add_parser("funding", help="Gate funding symbols from per_symbol CSV")
    f.add_argument("--per_symbol_csv", required=True)
    f.add_argument("--top_n", type=int, default=8)
    f.add_argument("--min_events", type=int, default=120)
    f.add_argument("--max_top_symbol_share", type=float, default=0.45)
    f.add_argument("--min_symbol_net_usd", type=float, default=-0.10)
    f.add_argument("--out_csv", default="")

    args = ap.parse_args()
    if args.cmd == "trade":
        return gate_trade_scan(args)
    return gate_funding(args)


if __name__ == "__main__":
    raise SystemExit(main())
