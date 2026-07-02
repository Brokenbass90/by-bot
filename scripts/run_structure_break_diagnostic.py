#!/usr/bin/env python3
"""BOS/CHoCH diagnostic runner for crypto/FX cached OHLCV.

Research-only. It uses bot.structure_break as the signal source, then applies a
simple fixed-R exit on subsequent bars. This is a cheap way to answer whether the
frequent BOS/CHoCH event has raw edge before building a full live sleeve.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.engine import Candle, aggregate_candles_to_interval
from bot.market_context import atr, CLOSE, HIGH, LOW, TS
from bot.preflight_check import preflight
from bot.structure_break import structure_break


def _csv(raw: str) -> List[str]:
    return [x.strip().upper() for x in str(raw or "").split(",") if x.strip()]


def _row_to_candle(r: Any) -> Candle:
    if isinstance(r, dict):
        ts = int(r.get("ts") or r.get("start") or r.get("startTime") or r.get("start_time"))
        return Candle(
            ts,
            float(r.get("open") if r.get("open") is not None else r.get("o")),
            float(r.get("high") if r.get("high") is not None else r.get("h")),
            float(r.get("low") if r.get("low") is not None else r.get("l")),
            float(r.get("close") if r.get("close") is not None else r.get("c")),
            float(r.get("volume") if r.get("volume") is not None else (r.get("v") or 0.0)),
        )
    return Candle(int(float(r[0])), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]) if len(r) > 5 else 0.0)


def _latest_crypto_cache(cache: Path, symbol: str) -> Optional[Path]:
    files = sorted(cache.glob(f"{symbol}_5_*.json"), key=lambda p: p.stat().st_size, reverse=True)
    return files[0] if files else None


def _load_crypto_rows(cache: Path, symbol: str, days: int, interval_min: int) -> Optional[List[List[float]]]:
    path = _latest_crypto_cache(cache, symbol)
    if path is None:
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    candles = sorted((_row_to_candle(r) for r in raw), key=lambda c: c.ts)
    if days > 0 and candles:
        cutoff = candles[-1].ts - days * 24 * 60 * 60 * 1000
        candles = [c for c in candles if c.ts >= cutoff]
    candles = aggregate_candles_to_interval(candles, interval_min)
    return [[c.ts, c.o, c.h, c.l, c.c, c.v] for c in candles]


def _load_fx_rows(data_dir: Path, symbol: str, tail_rows: int, interval_min: int) -> Optional[List[List[float]]]:
    path = data_dir / f"{symbol}_M5.csv"
    if not path.exists():
        return None
    candles: List[Candle] = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                candles.append(Candle(
                    int(float(r["ts"]) * 1000), float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]), float(r.get("v") or 0.0)
                ))
            except Exception:
                continue
    if tail_rows > 0:
        candles = candles[-tail_rows:]
    candles = aggregate_candles_to_interval(candles, interval_min)
    return [[c.ts, c.o, c.h, c.l, c.c, c.v] for c in candles]


def _f(row: Sequence[float], idx: int) -> float:
    try:
        return float(row[idx])
    except Exception:
        return float("nan")


def _pf(rs: Sequence[float]) -> float:
    gains = sum(x for x in rs if x > 0)
    losses = -sum(x for x in rs if x < 0)
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _simulate(rows: Sequence[Sequence[float]], i: int, side: str, *, sl_atr: float, tp_rr: float, max_hold: int, fee_bps: float, slippage_bps: float) -> Optional[Dict[str, Any]]:
    a = atr(rows[: i + 1])
    if not (a == a and a > 0):
        return None
    entry = _f(rows[i], CLOSE)
    if side == "long":
        stop = entry - sl_atr * a
        risk = entry - stop
        tp = entry + tp_rr * risk
    elif side == "short":
        stop = entry + sl_atr * a
        risk = stop - entry
        tp = entry - tp_rr * risk
    else:
        return None
    if not (risk > 0 and entry > 0):
        return None
    end = min(len(rows) - 1, i + max_hold)
    gross_r: Optional[float] = None
    exit_i = end
    for j in range(i + 1, end + 1):
        hi, lo = _f(rows[j], HIGH), _f(rows[j], LOW)
        if side == "long":
            if lo <= stop:
                gross_r = -1.0; exit_i = j; break
            if hi >= tp:
                gross_r = tp_rr; exit_i = j; break
        else:
            if hi >= stop:
                gross_r = -1.0; exit_i = j; break
            if lo <= tp:
                gross_r = tp_rr; exit_i = j; break
    if gross_r is None:
        c = _f(rows[exit_i], CLOSE)
        gross_r = ((c - entry) if side == "long" else (entry - c)) / risk
    fee_r = (2.0 * (fee_bps + slippage_bps) / 1e4) / max(1e-9, risk / entry)
    return {"r": round(gross_r - fee_r, 4), "entry": entry, "stop": stop, "tp": tp, "exit_i": exit_i}


def _run_one(symbol: str, rows: List[List[float]], *, event_filter: str, side_filter: str, sl_atr: float, tp_rr: float, max_hold: int, buffer_atr: float, left: int, right: int, fee_bps: float, slippage_bps: float, warmup: int) -> List[Dict[str, Any]]:
    trades: List[Dict[str, Any]] = []
    i = max(warmup, 4 * (left + right) + 10)
    while i < len(rows) - max_hold - 2:
        sb = structure_break(rows[: i + 1], left=left, right=right, buffer_atr=buffer_atr)
        if sb.event == "none" or not sb.ok:
            i += 1
            continue
        if event_filter != "all" and sb.event != event_filter:
            i += 1
            continue
        if side_filter != "both" and sb.side != side_filter:
            i += 1
            continue
        sim = _simulate(rows, i, sb.side, sl_atr=sl_atr, tp_rr=tp_rr, max_hold=max_hold, fee_bps=fee_bps, slippage_bps=slippage_bps)
        if sim is None:
            i += 1
            continue
        trades.append({
            "symbol": symbol,
            "ts": int(_f(rows[i], TS)),
            "event": sb.event,
            "direction": sb.direction,
            "trend": sb.trend,
            "side": sb.side,
            "level": sb.level,
            "r": sim["r"],
            "entry": sim["entry"],
            "stop": sim["stop"],
            "tp": sim["tp"],
            "exit_ts": int(_f(rows[sim["exit_i"]], TS)),
        })
        i = int(sim["exit_i"]) + 1
    return trades


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["crypto", "fx"], default="crypto")
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,DOGEUSDT,XRPUSDT,ONDOUSDT,SUIUSDT")
    ap.add_argument("--crypto-cache", default=".cache/klines")
    ap.add_argument("--fx-data-dir", default="data_cache/forex")
    ap.add_argument("--days", type=int, default=360)
    ap.add_argument("--tail-rows", type=int, default=0)
    ap.add_argument("--interval-min", type=int, default=60)
    ap.add_argument("--events", default="bos,choch")
    ap.add_argument("--sides", default="long,short")
    ap.add_argument("--tp-rr", default="1.5,2.0")
    ap.add_argument("--sl-atr", default="0.8,1.0,1.3")
    ap.add_argument("--max-hold", default="12,24")
    ap.add_argument("--buffer-atr", default="0.05,0.10,0.20")
    ap.add_argument("--left", type=int, default=2)
    ap.add_argument("--right", type=int, default=2)
    ap.add_argument("--fee-bps", type=float, default=6.0)
    ap.add_argument("--slippage-bps", type=float, default=2.0)
    ap.add_argument("--outdir", default="")
    args = ap.parse_args()

    run_id = datetime.now(timezone.utc).strftime(f"structure_break_{args.market}_%Y%m%d_%H%M%S")
    outdir = Path(args.outdir or f"reports/research/{run_id}")
    outdir.mkdir(parents=True, exist_ok=True)

    all_rows: List[Dict[str, Any]] = []
    summaries: List[Dict[str, Any]] = []
    row_cache: Dict[str, List[List[float]]] = {}
    for sym in _csv(args.symbols):
        if args.market == "crypto":
            rows = _load_crypto_rows(Path(args.crypto_cache), sym, args.days, args.interval_min)
        else:
            rows = _load_fx_rows(Path(args.fx_data_dir), sym, args.tail_rows, args.interval_min)
        if not rows or len(rows) < 200:
            print(f"[skip] {sym} rows={0 if not rows else len(rows)}", flush=True)
            continue
        row_cache[sym] = rows
        print(f"[load] {sym} rows={len(rows)}", flush=True)

    for event in [x.strip().lower() for x in args.events.split(",") if x.strip()]:
        for side in [x.strip().lower() for x in args.sides.split(",") if x.strip()]:
            for tp_rr in [float(x) for x in args.tp_rr.split(",") if x.strip()]:
                for sl_atr in [float(x) for x in args.sl_atr.split(",") if x.strip()]:
                    for max_hold in [int(x) for x in args.max_hold.split(",") if x.strip()]:
                        for buffer_atr in [float(x) for x in args.buffer_atr.split(",") if x.strip()]:
                            trades: List[Dict[str, Any]] = []
                            for sym, rows in row_cache.items():
                                trades.extend(_run_one(
                                    sym, rows,
                                    event_filter=event,
                                    side_filter=side,
                                    sl_atr=sl_atr,
                                    tp_rr=tp_rr,
                                    max_hold=max_hold,
                                    buffer_atr=buffer_atr,
                                    left=args.left,
                                    right=args.right,
                                    fee_bps=args.fee_bps,
                                    slippage_bps=args.slippage_bps,
                                    warmup=80,
                                ))
                            rs = [float(t["r"]) for t in trades]
                            pf_report = preflight(trades, min_trades_total=40, min_trades_per_fold=8, min_symbols=3)
                            row = {
                                "market": args.market,
                                "event": event,
                                "side": side,
                                "tp_rr": tp_rr,
                                "sl_atr": sl_atr,
                                "max_hold": max_hold,
                                "buffer_atr": buffer_atr,
                                "trades": len(rs),
                                "net_r": round(sum(rs), 4),
                                "pf": _pf(rs),
                                "win_rate": round(sum(1 for x in rs if x > 0) / len(rs), 4) if rs else 0.0,
                                "symbols": len({t["symbol"] for t in trades}),
                                "preflight_go": pf_report.go,
                                "preflight_reasons": ";".join(pf_report.reasons),
                            }
                            summaries.append(row)
                            tag = f"{event}_{side}_rr{tp_rr}_sl{sl_atr}_h{max_hold}_b{buffer_atr}"
                            for t in trades:
                                t.update({"tag": tag, **{k: row[k] for k in ("event", "side", "tp_rr", "sl_atr", "max_hold", "buffer_atr")}})
                            all_rows.extend(trades)
                            print(f"[run] {tag} trades={row['trades']} netR={row['net_r']} pf={row['pf']:.3f} preflight={row['preflight_go']}", flush=True)

    if summaries:
        with (outdir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(summaries[0].keys()))
            w.writeheader(); w.writerows(summaries)
    if all_rows:
        keys: List[str] = []
        for r in all_rows:
            for k in r:
                if k not in keys:
                    keys.append(k)
        with (outdir / "trades.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader(); w.writerows(all_rows)

    top = sorted(summaries, key=lambda r: (bool(r["preflight_go"]), float(r["net_r"]), float(r["pf"])), reverse=True)[:30]
    lines = [
        "# Structure break diagnostic",
        "",
        f"- market: `{args.market}`",
        f"- interval_min: `{args.interval_min}`",
        f"- rows: {len(summaries)}",
        "",
        "| event | side | rr | sl_atr | hold | buffer | trades | netR | PF | WR | symbols | preflight |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in top:
        pf = float(r["pf"])
        pf_s = "inf" if math.isinf(pf) else f"{pf:.3f}"
        lines.append(
            f"| {r['event']} | {r['side']} | {r['tp_rr']} | {r['sl_atr']} | {r['max_hold']} | {r['buffer_atr']} | "
            f"{r['trades']} | {r['net_r']:.3f} | {pf_s} | {r['win_rate']:.3f} | {r['symbols']} | {r['preflight_go']} |"
        )
    lines += ["", "## Outputs", "", f"- `{outdir / 'summary.csv'}`", f"- `{outdir / 'trades.csv'}`"]
    (outdir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[done] {outdir}", flush=True)
    return 0 if summaries else 1


if __name__ == "__main__":
    raise SystemExit(main())
