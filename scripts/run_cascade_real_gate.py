#!/usr/bin/env python3
"""Cascade-reversal gate on REAL collected liquidation data — козырь #1.

The cascade_reversal detector failed on PROXY liq data (PF 0.26 — honest NO-GO).
It has NEVER been tested on the real Bybit allLiquidation stream that
scripts/collect_bybit_liquidations.py has been writing on the server. This
runner closes that gap:

  liq JSONL (collector) ──┐
  5m klines (cache)     ──┼─> aligned 5m series -> cascade_reversal -> fade sim
  funding (REST/CSV)    ──┤   (fixed-R, SL-first, fees) -> per-symbol/side,
  open interest (REST)  ──┘   4 chrono folds, preflight, coverage gate

Pre-registered mini-grid only (16 combos/side) — no free-form fitting.
Research-only; feeds wf_folds/oos_selector if anything shows a pulse.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.engine import Candle, aggregate_candles_to_interval
from bot.candle_coverage import assess_coverage
from bot.cascade_reversal import cascade_reversal
from bot.market_context import atr, CLOSE, HIGH, LOW, TS
from bot.preflight_check import preflight

INTERVAL_MS = 5 * 60_000


# ── data loading / alignment (unit-tested) ───────────────────────────────────

def bucket_liquidations(events: Iterable[Dict[str, Any]], interval_ms: int = INTERVAL_MS) -> Dict[str, Dict[int, float]]:
    """Sum liquidation USD per (symbol, 5m bucket). Event: {ts_ms, symbol, usd}."""
    out: Dict[str, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for e in events:
        try:
            ts = int(e["ts_ms"]); sym = str(e["symbol"]).upper(); usd = float(e["usd"])
        except Exception:
            continue
        if ts <= 0 or usd <= 0 or not sym:
            continue
        out[sym][(ts // interval_ms) * interval_ms] += usd
    return {s: dict(b) for s, b in out.items()}


def load_liq_jsonl(path: Path) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue
    return events


def forward_fill_to_grid(points: Sequence[Tuple[int, float]], grid_ts: Sequence[int]) -> List[float]:
    """Align sparse (ts_ms, value) points to a bar grid: last known value wins.
    Bars before the first point get NaN (detector treats missing honestly)."""
    pts = sorted((int(t), float(v)) for t, v in points)
    out: List[float] = []
    j = -1
    for ts in grid_ts:
        while j + 1 < len(pts) and pts[j + 1][0] <= ts:
            j += 1
        out.append(pts[j][1] if j >= 0 else float("nan"))
    return out


def liq_series_for_grid(buckets: Dict[int, float], grid_ts: Sequence[int]) -> List[float]:
    return [float(buckets.get(int(ts), 0.0)) for ts in grid_ts]


def _row_to_candle(r: Any) -> Candle:
    if isinstance(r, dict):
        ts = int(r.get("ts") or r.get("start") or r.get("startTime") or r.get("start_time"))
        return Candle(ts, float(r.get("open", r.get("o"))), float(r.get("high", r.get("h"))),
                      float(r.get("low", r.get("l"))), float(r.get("close", r.get("c"))),
                      float(r.get("volume", r.get("v")) or 0.0))
    return Candle(int(float(r[0])), float(r[1]), float(r[2]), float(r[3]), float(r[4]),
                  float(r[5]) if len(r) > 5 else 0.0)


def load_price_rows(cache: Path, symbol: str, start_ms: int, end_ms: int) -> List[List[float]]:
    files = sorted(cache.glob(f"{symbol}_5_*.json"))
    if not files:
        return []
    by_ts: Dict[int, Candle] = {}
    for file in files:
        try:
            raw = json.loads(file.read_text(encoding="utf-8"))
        except Exception:
            continue
        for r in raw:
            try:
                c = _row_to_candle(r)
            except Exception:
                continue
            if start_ms <= c.ts <= end_ms:
                by_ts[c.ts] = c
    candles = [by_ts[ts] for ts in sorted(by_ts)]
    candles = aggregate_candles_to_interval(candles, 5)
    return [[c.ts, c.o, c.h, c.l, c.c, c.v] for c in candles]


# ── Bybit public REST (runs on the server; guarded, cursor-paginated) ────────

def _get_json(url: str, timeout: float = 10.0) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosec: public market data
        return json.loads(resp.read().decode("utf-8"))


def fetch_funding_history(symbol: str, start_ms: int, end_ms: int, *, base: str = "https://api.bybit.com") -> List[Tuple[int, float]]:
    out: List[Tuple[int, float]] = []
    cursor_end = end_ms
    for _ in range(40):
        url = (f"{base}/v5/market/funding/history?category=linear&symbol={symbol}"
               f"&startTime={start_ms}&endTime={cursor_end}&limit=200")
        try:
            data = _get_json(url)
        except Exception:
            break
        rows = (data.get("result") or {}).get("list") or []
        if not rows:
            break
        for r in rows:
            out.append((int(r["fundingRateTimestamp"]), float(r["fundingRate"])))
        oldest = min(int(r["fundingRateTimestamp"]) for r in rows)
        if oldest <= start_ms or len(rows) < 200:
            break
        cursor_end = oldest - 1
        time.sleep(0.15)
    return sorted(set(out))


def fetch_oi_history(symbol: str, start_ms: int, end_ms: int, *, base: str = "https://api.bybit.com") -> List[Tuple[int, float]]:
    out: List[Tuple[int, float]] = []
    cursor = ""
    for _ in range(300):
        url = (f"{base}/v5/market/open-interest?category=linear&symbol={symbol}"
               f"&intervalTime=5min&startTime={start_ms}&endTime={end_ms}&limit=200")
        if cursor:
            url += f"&cursor={urllib.request.quote(cursor)}" if hasattr(urllib.request, "quote") else f"&cursor={cursor}"
        try:
            data = _get_json(url)
        except Exception:
            break
        res = data.get("result") or {}
        rows = res.get("list") or []
        for r in rows:
            out.append((int(r["timestamp"]), float(r["openInterest"])))
        cursor = str(res.get("nextPageCursor") or "")
        if not rows or not cursor:
            break
        time.sleep(0.15)
    return sorted(set(out))


def load_points_csv(path: Path) -> List[Tuple[int, float]]:
    """Fallback offline source: CSV with ts_ms,value columns."""
    pts: List[Tuple[int, float]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.reader(f):
            try:
                pts.append((int(float(r[0])), float(r[1])))
            except Exception:
                continue
    return pts


# ── fade simulation (same conservative contract as other runners) ───────────

def simulate_fade(rows: Sequence[Sequence[float]], i: int, side: str, *, sl_atr: float,
                  tp_rr: float, max_hold: int, fee_bps: float, slippage_bps: float) -> Optional[Dict[str, Any]]:
    a = atr(rows[: i + 1])
    if not (a == a and a > 0):
        return None
    entry = float(rows[i][CLOSE])
    if side == "long":
        stop = entry - sl_atr * a; risk = entry - stop; tp = entry + tp_rr * risk
    else:
        stop = entry + sl_atr * a; risk = stop - entry; tp = entry - tp_rr * risk
    if not (risk > 0 and entry > 0):
        return None
    end = min(len(rows) - 1, i + max_hold)
    r_gross = None; exit_i = end
    for j in range(i + 1, end + 1):
        hi, lo = float(rows[j][HIGH]), float(rows[j][LOW])
        if side == "long":
            if lo <= stop: r_gross = -1.0; exit_i = j; break
            if hi >= tp: r_gross = tp_rr; exit_i = j; break
        else:
            if hi >= stop: r_gross = -1.0; exit_i = j; break
            if lo <= tp: r_gross = tp_rr; exit_i = j; break
    if r_gross is None:
        c = float(rows[exit_i][CLOSE])
        r_gross = ((c - entry) if side == "long" else (entry - c)) / risk
    fee_r = (2.0 * (fee_bps + slippage_bps) / 1e4) / max(1e-9, risk / entry)
    return {"r": round(r_gross - fee_r, 4), "exit_i": exit_i}


def run_symbol(rows: List[List[float]], funding: List[float], oi: List[float], liq: List[float], *,
               symbol: str, funding_z_min: float, oi_drop_min_pct: float, liq_pctile_min: float,
               sl_atr: float, tp_rr: float, max_hold: int, cooldown_bars: int,
               fee_bps: float, slippage_bps: float, warmup: int = 300) -> List[Dict[str, Any]]:
    trades: List[Dict[str, Any]] = []
    i = warmup
    n = len(rows)
    while i < n - max_hold - 2:
        st = cascade_reversal(
            rows[: i + 1], funding[: i + 1], oi[: i + 1], liq[: i + 1],
            funding_z_min=funding_z_min, oi_drop_min_pct=oi_drop_min_pct,
            liq_pctile_min=liq_pctile_min,
        )
        if not getattr(st, "ok", False) or getattr(st, "side", "none") not in ("long", "short"):
            i += 1
            continue
        sim = simulate_fade(rows, i, st.side, sl_atr=sl_atr, tp_rr=tp_rr,
                            max_hold=max_hold, fee_bps=fee_bps, slippage_bps=slippage_bps)
        if sim is None:
            i += 1
            continue
        trades.append({"symbol": symbol, "ts": int(rows[i][TS]), "side": st.side,
                       "r": sim["r"], "reason": getattr(st, "reason", "")})
        i = int(sim["exit_i"]) + 1 + max(0, cooldown_bars)
    return trades


def _folds(trades: Sequence[Dict[str, Any]], n: int = 4) -> List[float]:
    ts_sorted = sorted(trades, key=lambda t: t["ts"])
    if not ts_sorted:
        return [0.0] * n
    chunk = max(1, len(ts_sorted) // n)
    sums = []
    for k in range(n):
        part = ts_sorted[k * chunk: (k + 1) * chunk] if k < n - 1 else ts_sorted[(n - 1) * chunk:]
        sums.append(round(sum(float(t["r"]) for t in part), 4))
    return sums


def _pf(rs: Sequence[float]) -> float:
    g = sum(x for x in rs if x > 0); l = -sum(x for x in rs if x < 0)
    return (g / l) if l > 0 else (float("inf") if g > 0 else 0.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--liq-jsonl", default="runtime/liquidations/bybit_liquidations.jsonl")
    ap.add_argument("--crypto-cache", default="data_cache")
    ap.add_argument("--symbols", default="")  # default: all symbols present in liq file
    ap.add_argument("--funding-csv-dir", default="", help="Offline ts_ms,value CSVs per symbol; else Bybit REST")
    ap.add_argument("--oi-csv-dir", default="", help="Offline ts_ms,value CSVs per symbol; else Bybit REST")
    # pre-registered mini-grid — do not widen ad hoc
    ap.add_argument("--funding-z", default="1.5,2.0")
    ap.add_argument("--oi-drop", default="3.0,5.0")
    ap.add_argument("--liq-pctile", default="90,95")
    ap.add_argument("--tp-rr", default="1.5,2.0")
    ap.add_argument("--sl-atr", type=float, default=1.0)
    ap.add_argument("--max-hold", type=int, default=48)
    ap.add_argument("--cooldown-bars", type=int, default=12)
    ap.add_argument("--fee-bps", type=float, default=6.0)
    ap.add_argument("--slippage-bps", type=float, default=2.0)
    ap.add_argument("--outdir", default="")
    args = ap.parse_args()

    liq_path = Path(args.liq_jsonl)
    if not liq_path.exists():
        print(f"[fatal] liq jsonl not found: {liq_path}", flush=True)
        return 2
    events = load_liq_jsonl(liq_path)
    buckets = bucket_liquidations(events)
    print(f"[liq] events={len(events)} symbols={len(buckets)}", flush=True)
    if not buckets:
        return 2

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or \
              sorted(buckets, key=lambda s: -sum(buckets[s].values()))[:20]

    run_id = datetime.now(timezone.utc).strftime("cascade_real_gate_%Y%m%d_%H%M%S")
    outdir = Path(args.outdir or f"reports/research/{run_id}")
    outdir.mkdir(parents=True, exist_ok=True)

    all_ts = [t for b in buckets.values() for t in b]
    start_ms, end_ms = min(all_ts), max(all_ts)
    print(f"[window] {datetime.fromtimestamp(start_ms/1e3, timezone.utc)} .. "
          f"{datetime.fromtimestamp(end_ms/1e3, timezone.utc)}", flush=True)

    coverage_rows: List[Dict[str, Any]] = []
    summaries: List[Dict[str, Any]] = []
    trades_all: List[Dict[str, Any]] = []

    for sym in symbols:
        rows = load_price_rows(Path(args.crypto_cache), sym, start_ms, end_ms)
        cov = assess_coverage(rows, symbol=sym, interval_min=5, min_bars=500)
        coverage_rows.append({"symbol": sym, **{k: cov.to_dict()[k] for k in
                              ("coverage", "n_gaps", "max_gap_bars", "flat_frac", "ok")}})
        print(f"[coverage] {sym} ok={cov.ok} cov={cov.coverage:.3f} reasons={';'.join(cov.reasons[:2])}", flush=True)
        if not cov.ok:
            continue
        grid_ts = [int(r[TS]) for r in rows]
        liq_series = liq_series_for_grid(buckets.get(sym, {}), grid_ts)
        if sum(1 for x in liq_series if x > 0) < 30:
            print(f"[skip] {sym}: too few liq buckets", flush=True)
            continue

        fdir, odir = args.funding_csv_dir, args.oi_csv_dir
        f_pts = load_points_csv(Path(fdir) / f"{sym}.csv") if fdir else fetch_funding_history(sym, start_ms, end_ms)
        o_pts = load_points_csv(Path(odir) / f"{sym}.csv") if odir else fetch_oi_history(sym, start_ms, end_ms)
        if len(f_pts) < 3 or len(o_pts) < 50:
            print(f"[skip] {sym}: funding_pts={len(f_pts)} oi_pts={len(o_pts)} insufficient", flush=True)
            continue
        funding = forward_fill_to_grid(f_pts, grid_ts)
        oi = forward_fill_to_grid(o_pts, grid_ts)

        for fz in [float(x) for x in args.funding_z.split(",")]:
            for od in [float(x) for x in args.oi_drop.split(",")]:
                for lp in [float(x) for x in args.liq_pctile.split(",")]:
                    for rr in [float(x) for x in args.tp_rr.split(",")]:
                        trades = run_symbol(
                            rows, funding, oi, liq_series, symbol=sym,
                            funding_z_min=fz, oi_drop_min_pct=od, liq_pctile_min=lp,
                            sl_atr=args.sl_atr, tp_rr=rr, max_hold=args.max_hold,
                            cooldown_bars=args.cooldown_bars,
                            fee_bps=args.fee_bps, slippage_bps=args.slippage_bps,
                        )
                        for side in ("long", "short"):
                            st = [t for t in trades if t["side"] == side]
                            rs = [float(t["r"]) for t in st]
                            if not rs:
                                continue
                            tag = f"fz{fz}_od{od}_lp{lp}_rr{rr}_{side}"
                            summaries.append({
                                "symbol": sym, "tag": tag, "side": side,
                                "trades": len(rs), "net_r": round(sum(rs), 4),
                                "pf": round(_pf(rs), 4),
                                "win_rate": round(sum(1 for x in rs if x > 0) / len(rs), 4),
                                "folds": _folds(st),
                            })
                            for t in st:
                                trades_all.append({**t, "tag": tag})
                        print(f"[run] {sym} fz={fz} od={od} lp={lp} rr={rr} trades={len(trades)}", flush=True)

    with (outdir / "coverage.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(coverage_rows[0].keys()) if coverage_rows else ["symbol"])
        w.writeheader(); w.writerows(coverage_rows)
    with (outdir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(sorted(summaries, key=lambda r: -r["net_r"]), f, indent=1)
    with (outdir / "trades.csv").open("w", newline="", encoding="utf-8") as f:
        if trades_all:
            w = csv.DictWriter(f, fieldnames=list(trades_all[0].keys()))
            w.writeheader(); w.writerows(trades_all)

    top = sorted(summaries, key=lambda r: -r["net_r"])[:15]
    lines = ["# Cascade real-data gate", "", f"- liq events: {len(events)}",
             f"- window: {datetime.fromtimestamp(start_ms/1e3, timezone.utc)} .. {datetime.fromtimestamp(end_ms/1e3, timezone.utc)}",
             "", "| symbol | tag | trades | netR | PF | WR | folds |", "|---|---|---:|---:|---:|---:|---|"]
    for r in top:
        lines.append(f"| {r['symbol']} | {r['tag']} | {r['trades']} | {r['net_r']} | {r['pf']} | {r['win_rate']} | {r['folds']} |")
    (outdir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[done] outdir={outdir} combos={len(summaries)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
