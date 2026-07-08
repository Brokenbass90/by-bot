#!/usr/bin/env python3
"""Strict pre-registered OOS for level-memory sweep/reclaim.

Research-only. No network and no live orders.

This freezes the pocket found by the 2026-07-07 exploration:
respect_min=0.65, lookback=48, rr in {1.2, 1.6}.  The point is not to find a
new best row, but to answer whether the pocket survives time folds, causal
selection, symbol holdout, fee stress, and regime splits.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.candle_coverage import assess_coverage
from bot.geometry_cache import load_cache_rows
from scripts.run_crypto_level_memory_sweep_reclaim_20260707 import (
    Bar,
    Trade,
    _folds,
    _load_symbol_h1,
    _max_dd,
    _pf,
    _simulate_symbol,
    _utc_compact,
)

MS_DAY = 86_400_000

BASE_SYMBOLS = [
    "ETHUSDT",
    "BTCUSDT",
    "LINKUSDT",
    "SUIUSDT",
    "SOLUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "LTCUSDT",
    "TAOUSDT",
    "HYPEUSDT",
    "1000PEPEUSDT",
    "DOTUSDT",
    "ATOMUSDT",
    "XRPUSDT",
    "AVAXUSDT",
    "ONDOUSDT",
    "BCHUSDT",
    "XLMUSDT",
    "BNBUSDT",
]

HOLDOUT_SYMBOLS = [
    "NEARUSDT",
    "INJUSDT",
    "TIAUSDT",
    "SEIUSDT",
    "ARBUSDT",
    "OPUSDT",
    "APTUSDT",
    "RUNEUSDT",
]


def _summarize(trades: Sequence[Trade]) -> Dict[str, Any]:
    vals = [float(t.net_r) for t in sorted(trades, key=lambda t: t.entry_ts)]
    return {
        "trades": len(vals),
        "net_r": round(sum(vals), 4),
        "pf": round(_pf(vals), 4) if vals else 0.0,
        "wr": round(sum(1 for v in vals if v > 0) / len(vals), 4) if vals else 0.0,
        "dd_r": round(_max_dd(vals), 4),
        "folds_pos": sum(1 for f in _folds(trades, 4) if f["net_r"] > 0),
    }


def _coverage_row(cache_dir: Path, symbol: str) -> Dict[str, Any]:
    rows = load_cache_rows(symbol, "5", data_cache_dir=cache_dir)
    cov = assess_coverage(rows, symbol=symbol, interval_min=5, min_bars=500)
    return {
        "symbol": symbol,
        "rows_5m": len(rows),
        "coverage": round(float(cov.coverage), 6),
        "n_gaps": int(cov.n_gaps),
        "max_gap_bars": int(cov.max_gap_bars),
        "ok": bool(cov.ok),
        "reasons": ";".join(cov.reasons[:4]),
    }


def _simulate_many(
    data: Dict[str, Sequence[Bar]],
    *,
    rr: float,
    fee_bps_entry: float,
    fee_bps_exit: float,
) -> List[Trade]:
    trades: List[Trade] = []
    for sym, bars in data.items():
        trades.extend(
            _simulate_symbol(
                sym,
                bars,
                lookback=48,
                respect_min=0.65,
                min_touches=3,
                rr=rr,
                atr_period=14,
                min_sweep_atr=0.15,
                reclaim_atr=0.03,
                sl_pad_atr=0.08,
                max_hold_bars=36,
                fee_bps_entry=fee_bps_entry,
                fee_bps_exit=fee_bps_exit,
                allow_longs=True,
                allow_shorts=True,
            )
        )
    return sorted(trades, key=lambda t: t.entry_ts)


def _concentration(trades: Sequence[Trade]) -> Dict[str, Any]:
    by_sym: Dict[str, float] = {}
    for t in trades:
        by_sym[t.symbol] = by_sym.get(t.symbol, 0.0) + float(t.net_r)
    positive = {s: max(0.0, r) for s, r in by_sym.items()}
    total_pos = sum(positive.values())
    top = sorted(positive.items(), key=lambda kv: kv[1], reverse=True)
    largest_trades = sorted([max(0.0, float(t.net_r)) for t in trades], reverse=True)[:3]
    return {
        "top_symbol": top[0][0] if top else "",
        "top_symbol_share": round((top[0][1] / total_pos), 4) if total_pos > 0 and top else 0.0,
        "top2_share": round((sum(v for _, v in top[:2]) / total_pos), 4) if total_pos > 0 else 0.0,
        "top3_share": round((sum(v for _, v in top[:3]) / total_pos), 4) if total_pos > 0 else 0.0,
        "top3_trade_pnl_share": round((sum(largest_trades) / total_pos), 4) if total_pos > 0 else 0.0,
        "symbol_net_r": {s: round(r, 4) for s, r in sorted(by_sym.items(), key=lambda kv: -kv[1])},
    }


def _oos_selector(trades_by_rr: Dict[float, Sequence[Trade]], *, train_days: int = 40, test_days: int = 8) -> Dict[str, Any]:
    all_ts = [t.entry_ts for trades in trades_by_rr.values() for t in trades]
    if not all_ts:
        return {"windows": [], "summary": {"pass": False, "reason": "no_trades"}}
    start = min(all_ts)
    end = max(all_ts)
    windows: List[Dict[str, Any]] = []
    step = test_days * MS_DAY
    width = (train_days + test_days) * MS_DAY
    cur = start
    while cur + width <= end + 1:
        train_lo = cur
        train_hi = cur + train_days * MS_DAY
        test_hi = train_hi + test_days * MS_DAY
        scored: List[tuple[float, float, int]] = []
        for rr, trades in trades_by_rr.items():
            train_vals = [float(t.net_r) for t in trades if train_lo <= t.entry_ts < train_hi]
            scored.append((sum(train_vals), rr, len(train_vals)))
        scored.sort(reverse=True)
        train_net, selected_rr, train_n = scored[0]
        selected = trades_by_rr[selected_rr]
        test_vals = [float(t.net_r) for t in selected if train_hi <= t.entry_ts < test_hi]
        windows.append({
            "start_utc": datetime.fromtimestamp(train_lo / 1e3, timezone.utc).isoformat(),
            "selected_rr": selected_rr,
            "train_trades": train_n,
            "train_net_r": round(train_net, 4),
            "test_trades": len(test_vals),
            "test_net_r": round(sum(test_vals), 4),
            "test_pf": round(_pf(test_vals), 4) if test_vals else 0.0,
        })
        cur += step
    test_vals_all = [float(w["test_net_r"]) for w in windows]
    total_trades = sum(int(w["test_trades"]) for w in windows)
    summary = {
        "windows": len(windows),
        "test_trades": total_trades,
        "test_net_r": round(sum(test_vals_all), 4),
        "positive_windows": sum(1 for v in test_vals_all if v > 0),
        "pass": bool(windows and total_trades >= 20 and sum(test_vals_all) > 0 and sum(1 for v in test_vals_all if v > 0) >= math.ceil(len(windows) * 0.5)),
    }
    return {"windows": windows, "summary": summary}


def _btc_regime_labels(btc_bars: Sequence[Bar]) -> List[tuple[int, str]]:
    labels: List[tuple[int, str]] = []
    for i, b in enumerate(btc_bars):
        if i < 168:
            labels.append((b.ts, "unknown"))
            continue
        ret = (b.c / btc_bars[i - 168].c) - 1.0 if btc_bars[i - 168].c > 0 else 0.0
        if ret >= 0.02:
            labels.append((b.ts, "bull"))
        elif ret <= -0.02:
            labels.append((b.ts, "bear"))
        else:
            labels.append((b.ts, "chop"))
    return labels


def _regime_for(ts: int, labels: Sequence[tuple[int, str]]) -> str:
    if not labels:
        return "unknown"
    lo, hi = 0, len(labels) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if labels[mid][0] <= ts:
            lo = mid + 1
        else:
            hi = mid - 1
    return labels[max(0, hi)][1]


def _period_stats(trades: Sequence[Trade], btc_bars: Sequence[Bar]) -> List[Dict[str, Any]]:
    labels = _btc_regime_labels(btc_bars)
    rows: List[Dict[str, Any]] = []
    for regime in ("bull", "bear", "chop", "unknown"):
        vals = [float(t.net_r) for t in trades if _regime_for(t.entry_ts, labels) == regime]
        rows.append({
            "regime": regime,
            "trades": len(vals),
            "net_r": round(sum(vals), 4),
            "pf": round(_pf(vals), 4) if vals else 0.0,
            "wr": round(sum(1 for v in vals if v > 0) / len(vals), 4) if vals else 0.0,
        })
    return rows


def _write_csv(path: Path, rows: Sequence[Dict[str, Any]], fields: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        if not fields:
            fields = list(rows[0].keys()) if rows else ["empty"]
        w = csv.DictWriter(f, fieldnames=list(fields), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default=str(ROOT / "data_cache"))
    ap.add_argument("--days", type=int, default=360)
    ap.add_argument("--out", default="")
    ap.add_argument("--symbols", default=",".join(BASE_SYMBOLS))
    ap.add_argument("--holdout-symbols", default=",".join(HOLDOUT_SYMBOLS))
    args = ap.parse_args(list(argv) if argv is not None else None)

    cache_dir = Path(args.cache_dir)
    out_dir = Path(args.out) if args.out else ROOT / "reports" / "research" / f"level_memory_oos_prereg_20260708_{_utc_compact()}"
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    holdouts = [s.strip().upper() for s in args.holdout_symbols.split(",") if s.strip()]

    coverage = [_coverage_row(cache_dir, s) for s in symbols + holdouts]
    _write_csv(out_dir / "coverage.csv", coverage)
    print(json.dumps({"event": "coverage_done", "out": str(out_dir), "rows": len(coverage)}, ensure_ascii=False), flush=True)

    base_data = {s: _load_symbol_h1(cache_dir, s, args.days) for s in symbols}
    base_data = {s: b for s, b in base_data.items() if len(b) >= 300}
    print(json.dumps({"event": "base_data_loaded", "symbols": sorted(base_data)}, ensure_ascii=False), flush=True)
    trades_by_rr: Dict[float, List[Trade]] = {}
    stress_by_rr: Dict[float, List[Trade]] = {}
    for rr in (1.2, 1.6):
        print(json.dumps({"event": "simulate_base_start", "rr": rr}, ensure_ascii=False), flush=True)
        trades_by_rr[rr] = _simulate_many(base_data, rr=rr, fee_bps_entry=6.0, fee_bps_exit=2.0)
        print(json.dumps({"event": "simulate_base_done", "rr": rr, "trades": len(trades_by_rr[rr])}, ensure_ascii=False), flush=True)
        print(json.dumps({"event": "simulate_stress_start", "rr": rr}, ensure_ascii=False), flush=True)
        stress_by_rr[rr] = _simulate_many(base_data, rr=rr, fee_bps_entry=10.0, fee_bps_exit=5.0)
        print(json.dumps({"event": "simulate_stress_done", "rr": rr, "trades": len(stress_by_rr[rr])}, ensure_ascii=False), flush=True)

    grid_rows: List[Dict[str, Any]] = []
    for rr, trades in trades_by_rr.items():
        stress = _summarize(stress_by_rr[rr])
        conc = _concentration(trades)
        stats = _summarize(trades)
        fold_rows = _folds(trades, 4)
        grid_rows.append({
            "respect_min": 0.65,
            "lookback": 48,
            "rr": rr,
            **stats,
            "stress_net_r": stress["net_r"],
            "stress_pf": stress["pf"],
            "top_symbol_share": conc["top_symbol_share"],
            "top2_share": conc["top2_share"],
            "top3_trade_pnl_share": conc["top3_trade_pnl_share"],
            "folds": json.dumps(fold_rows, ensure_ascii=False),
            "step1_pass": int(stats["trades"] >= 40 and conc["top_symbol_share"] < 0.35),
            "step2_pass": int(stats["folds_pos"] >= 3 and stats["pf"] >= 1.20),
        })
        _write_csv(out_dir / f"trades_rr{rr}.csv", [asdict(t) for t in trades])
        (out_dir / f"concentration_rr{rr}.json").write_text(json.dumps(conc, ensure_ascii=False, indent=2), encoding="utf-8")

    oos = _oos_selector(trades_by_rr)
    _write_csv(out_dir / "oos_windows.csv", oos["windows"])

    holdout_data = {s: _load_symbol_h1(cache_dir, s, args.days) for s in holdouts}
    holdout_rows: List[Dict[str, Any]] = []
    holdout_passes: List[bool] = []
    for rr in (1.2, 1.6):
        print(json.dumps({"event": "simulate_holdout_start", "rr": rr}, ensure_ascii=False), flush=True)
        trades = _simulate_many({s: b for s, b in holdout_data.items() if len(b) >= 300}, rr=rr, fee_bps_entry=6.0, fee_bps_exit=2.0)
        print(json.dumps({"event": "simulate_holdout_done", "rr": rr, "trades": len(trades)}, ensure_ascii=False), flush=True)
        stats = _summarize(trades)
        present = sorted({t.symbol for t in trades} | {s for s, b in holdout_data.items() if len(b) >= 300})
        missing = [s for s in holdouts if s not in present]
        passed = bool(not missing and stats["pf"] >= 1.15 and stats["net_r"] > 0)
        holdout_passes.append(passed)
        holdout_rows.append({
            "rr": rr,
            **stats,
            "symbols_present": ",".join(present),
            "symbols_missing_or_no_cache": ",".join(missing),
            "pass": int(passed),
        })
    _write_csv(out_dir / "holdout.csv", holdout_rows)

    btc = base_data.get("BTCUSDT", [])
    period_rows: List[Dict[str, Any]] = []
    for rr, trades in trades_by_rr.items():
        for row in _period_stats(trades, btc):
            period_rows.append({"rr": rr, **row})
    _write_csv(out_dir / "period_regime.csv", period_rows)

    best = max(grid_rows, key=lambda r: (int(r["step1_pass"]) + int(r["step2_pass"]), float(r["net_r"])), default={})
    promotion = bool(
        best
        and best.get("step1_pass")
        and best.get("step2_pass")
        and oos["summary"].get("pass")
        and any(holdout_passes)
        and any(r["trades"] > 0 and r["net_r"] > 0 for r in period_rows)
    )
    verdict = {
        "out": str(out_dir),
        "base_symbols_used": sorted(base_data),
        "best": best,
        "oos_selector": oos["summary"],
        "holdout": holdout_rows,
        "promotion_to_shadow": promotion,
        "blocked_by_data": any(r.get("symbols_missing_or_no_cache") for r in holdout_rows),
    }
    (out_dir / "verdict.json").write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Level-Memory OOS Pre-Registration Result",
        "",
        f"- output: `{out_dir}`",
        f"- base symbols used: `{','.join(sorted(base_data))}`",
        f"- best frozen row: `{best}`",
        f"- OOS selector: `{oos['summary']}`",
        f"- holdout: `{holdout_rows}`",
        f"- verdict: `{'PROMOTE_TO_SHADOW' if promotion else 'NO_PROMOTION'}`",
        "",
        "This is strict follow-up for the 2026-07-07 exploration pulse. No live money is enabled by this script.",
    ]
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
