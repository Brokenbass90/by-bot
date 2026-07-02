#!/usr/bin/env python3
"""ARF2 OLD-vs-NEW sequential diagnostic.

This is a cheap research gate before expensive OOS:

* load cached 5m candles;
* run ARF2 variants directly against KlineStore;
* count raw signals, limit fills, simple R outcomes, per-symbol concentration;
* write CSV + markdown summary.

It is intentionally not promotion-grade. It tells us whether a variant deserves
preflight/OOS, and which helper filter kills or improves the signal stream.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.engine import Candle, KlineStore
from strategies.alt_resistance_fade_v2 import AltResistanceFadeV2Config, AltResistanceFadeV2Strategy


DEFAULT_SYMBOLS = (
    "ADAUSDT,DOGEUSDT,SUIUSDT,LINKUSDT,SOLUSDT,DOTUSDT,LTCUSDT,ONDOUSDT,"
    "ATOMUSDT,AVAXUSDT,BNBUSDT,BCHUSDT,XRPUSDT,XLMUSDT,1000PEPEUSDT,HYPEUSDT,TAOUSDT"
)


def _csv(raw: str) -> List[str]:
    return [x.strip().upper() for x in str(raw or "").split(",") if x.strip()]


def _csv_lower(raw: str) -> List[str]:
    return [x.strip().lower() for x in str(raw or "").split(",") if x.strip()]


def _latest_cache(cache_dir: Path, symbol: str) -> Optional[Path]:
    files = sorted(cache_dir.glob(f"{symbol}_5_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _row_to_candle(r: Any) -> Candle:
    if isinstance(r, dict):
        ts = int(r.get("ts") or r.get("start") or r.get("startTime") or r.get("start_time"))
        o = float(r.get("open") if r.get("open") is not None else r.get("o"))
        h = float(r.get("high") if r.get("high") is not None else r.get("h"))
        l = float(r.get("low") if r.get("low") is not None else r.get("l"))
        c = float(r.get("close") if r.get("close") is not None else r.get("c"))
        v = float(r.get("volume") if r.get("volume") is not None else (r.get("v") or 0.0))
        return Candle(ts, o, h, l, c, v)
    return Candle(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]) if len(r) > 5 else 0.0)


def _load_store(cache_dir: Path, symbol: str, days: int) -> Optional[Tuple[KlineStore, str]]:
    path = _latest_cache(cache_dir, symbol)
    if path is None:
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    candles = sorted((_row_to_candle(r) for r in raw), key=lambda c: c.ts)
    if not candles:
        return None
    if days > 0:
        cutoff = candles[-1].ts - int(days) * 24 * 60 * 60 * 1000
        candles = [c for c in candles if c.ts >= cutoff]
    if len(candles) < 500:
        return None
    return KlineStore(symbol, candles), path.name


def _variants(names: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    all_variants: Dict[str, Dict[str, Any]] = {
        "old": {},
        "unified": {"use_unified_levels": True, "min_level_score": 0.20},
        "unified_minrange1": {"use_unified_levels": True, "min_level_score": 0.20, "min_range_pct": 1.0},
        "unified_retest025": {"use_unified_levels": True, "min_level_score": 0.20, "use_retest_quality": True, "retest_min_quality": 0.25},
        "unified_retest035": {"use_unified_levels": True, "min_level_score": 0.20, "use_retest_quality": True, "retest_min_quality": 0.35},
        "unified_retest045": {"use_unified_levels": True, "min_level_score": 0.20, "use_retest_quality": True, "retest_min_quality": 0.45},
        "unified_level_v4": {"use_unified_levels": True, "min_level_score": 0.20, "use_level_entry": True, "level_entry_max_chase_atr": 2.0, "level_entry_validity_bars": 4},
        "unified_level_v12": {"use_unified_levels": True, "min_level_score": 0.20, "use_level_entry": True, "level_entry_max_chase_atr": 2.0, "level_entry_validity_bars": 12},
        "unified_level_v24": {"use_unified_levels": True, "min_level_score": 0.20, "use_level_entry": True, "level_entry_max_chase_atr": 2.0, "level_entry_validity_bars": 24},
        "unified_level_v12_retest025": {"use_unified_levels": True, "min_level_score": 0.20, "use_level_entry": True, "level_entry_max_chase_atr": 2.0, "level_entry_validity_bars": 12, "use_retest_quality": True, "retest_min_quality": 0.25},
        "unified_level_v24_retest025": {"use_unified_levels": True, "min_level_score": 0.20, "use_level_entry": True, "level_entry_max_chase_atr": 2.0, "level_entry_validity_bars": 24, "use_retest_quality": True, "retest_min_quality": 0.25},
        "unified_elder": {"use_unified_levels": True, "min_level_score": 0.20, "use_elder_filter": True},
        "unified_rangefilter": {"use_unified_levels": True, "min_level_score": 0.20, "use_range_filter": True},
        "failed_breakout": {
            "use_failed_breakout": True,
            "failed_breakout_level_lookback": 20,
            "failed_breakout_event_window": 5,
            "failed_breakout_buffer_atr": 0.10,
            "min_reject_vol_mult": 0.0,
            "min_upper_wick_frac": 0.10,
            "resistance_touch_buffer_atr": 0.70,
            "max_pierce_atr": 1.50,
            "min_range_pct": 1.0,
        },
        "failed_breakout_range": {
            "use_failed_breakout": True,
            "use_range_filter": True,
            "failed_breakout_level_lookback": 20,
            "failed_breakout_event_window": 5,
            "failed_breakout_buffer_atr": 0.10,
            "min_reject_vol_mult": 0.0,
            "min_upper_wick_frac": 0.10,
            "resistance_touch_buffer_atr": 0.70,
            "max_pierce_atr": 1.50,
            "min_range_pct": 1.0,
        },
        "failed_breakout_level": {
            "use_failed_breakout": True,
            "use_level_entry": True,
            "level_entry_max_chase_atr": 2.0,
            "level_entry_validity_bars": 12,
            "failed_breakout_level_lookback": 20,
            "failed_breakout_event_window": 5,
            "failed_breakout_buffer_atr": 0.10,
            "min_reject_vol_mult": 0.0,
            "min_upper_wick_frac": 0.10,
            "resistance_touch_buffer_atr": 0.70,
            "max_pierce_atr": 1.50,
            "min_range_pct": 1.0,
        },
        "failed_breakout_volfade": {
            "use_failed_breakout": True,
            "failed_breakout_require_vol_fade": True,
            "failed_breakout_level_lookback": 20,
            "failed_breakout_event_window": 5,
            "failed_breakout_buffer_atr": 0.10,
            "min_reject_vol_mult": 0.0,
            "min_upper_wick_frac": 0.10,
            "resistance_touch_buffer_atr": 0.70,
            "max_pierce_atr": 1.50,
            "min_range_pct": 1.0,
        },
    }
    if not names:
        return all_variants
    return {n: all_variants[n] for n in names if n in all_variants}


def _exit_r(sig: Any, store: KlineStore, signal_i: int, *, max_hold_bars: int, cost_bps_per_side: float) -> Optional[Dict[str, Any]]:
    side = str(getattr(sig, "side", "")).lower()
    if side != "short":
        return None
    entry = float(getattr(sig, "entry"))
    sl = float(getattr(sig, "sl"))
    tp = float(getattr(sig, "tp"))
    if not (tp < entry < sl):
        return None
    fill_i = signal_i + 1
    fill_reason = "next_bar"
    if str(getattr(sig, "entry_order_type", "") or "").lower() == "limit":
        validity = max(1, int(getattr(sig, "limit_validity_bars", 1) or 1))
        fill_i = -1
        for j in range(signal_i + 1, min(len(store.exec_candles), signal_i + 1 + validity)):
            if float(store.exec_candles[j].h) >= entry:
                fill_i = j
                fill_reason = f"limit_fill_{j - signal_i}"
                break
        if fill_i < 0:
            return {"filled": False, "r": None, "outcome": "unfilled", "fill_i": -1, "fill_reason": "limit_unfilled"}
    if fill_i >= len(store.exec_candles):
        return None
    risk = sl - entry
    if risk <= 0:
        return None
    end_i = min(len(store.exec_candles) - 1, fill_i + max(1, int(max_hold_bars)))
    exit_price = float(store.exec_candles[end_i].c)
    outcome = "time"
    exit_i = end_i
    for j in range(fill_i, end_i + 1):
        b = store.exec_candles[j]
        # Conservative SL-first if both reachable.
        if float(b.h) >= sl:
            exit_price = sl
            outcome = "sl"
            exit_i = j
            break
        if float(b.l) <= tp:
            exit_price = tp
            outcome = "tp"
            exit_i = j
            break
    gross_r = (entry - exit_price) / risk
    cost_r = (entry * (cost_bps_per_side * 2.0 / 10000.0)) / risk
    return {
        "filled": True,
        "r": gross_r - cost_r,
        "gross_r": gross_r,
        "cost_r": cost_r,
        "outcome": outcome,
        "fill_i": fill_i,
        "exit_i": exit_i,
        "fill_reason": fill_reason,
    }


def _pf(rs: Sequence[float]) -> float:
    gains = sum(x for x in rs if x > 0)
    losses = -sum(x for x in rs if x < 0)
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _run_variant(name: str, cfg_kwargs: Dict[str, Any], stores: Dict[str, KlineStore], *, step: int, max_hold_bars: int, cost_bps_per_side: float) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    for symbol, store in stores.items():
        strat = AltResistanceFadeV2Strategy(AltResistanceFadeV2Config(**cfg_kwargs))
        for i in range(300, len(store.exec_candles) - max_hold_bars - 2, max(1, int(step))):
            store.set_index(i)
            b = store.current_bar()
            if b is None:
                continue
            sig = strat.maybe_signal(store, b.ts, b.o, b.h, b.l, b.c, b.v)
            if sig is None:
                reason_counts[strat.last_no_signal_reason or "unknown"] += 1
                continue
            sim = _exit_r(sig, store, i, max_hold_bars=max_hold_bars, cost_bps_per_side=cost_bps_per_side)
            rec = {
                "variant": name,
                "symbol": symbol,
                "ts": int(b.ts),
                "date": datetime.fromtimestamp(int(b.ts) / 1000, timezone.utc).date().isoformat(),
                "side": getattr(sig, "side", ""),
                "entry_order_type": getattr(sig, "entry_order_type", "market"),
                "entry": float(getattr(sig, "entry")),
                "sl": float(getattr(sig, "sl")),
                "tp": float(getattr(sig, "tp")),
                "reason": str(getattr(sig, "reason", "")),
            }
            if sim:
                rec.update(sim)
            else:
                rec.update({"filled": False, "r": None, "outcome": "sim_error", "fill_i": -1, "fill_reason": "sim_error"})
            rows.append(rec)
    filled_rs = [float(r["r"]) for r in rows if r.get("filled") and r.get("r") is not None]
    by_symbol = Counter(r["symbol"] for r in rows)
    filled_by_symbol = Counter(r["symbol"] for r in rows if r.get("filled"))
    summary = {
        "variant": name,
        "raw_signals": len(rows),
        "filled_trades": len(filled_rs),
        "fill_rate": (len(filled_rs) / len(rows)) if rows else 0.0,
        "net_r": sum(filled_rs),
        "pf": _pf(filled_rs),
        "winrate": (sum(1 for x in filled_rs if x > 0) / len(filled_rs)) if filled_rs else 0.0,
        "avg_r": statistics.mean(filled_rs) if filled_rs else 0.0,
        "symbols_raw": len(by_symbol),
        "symbols_filled": len(filled_by_symbol),
        "top_raw_symbol": by_symbol.most_common(1)[0][0] if by_symbol else "",
        "top_raw_symbol_frac": (by_symbol.most_common(1)[0][1] / len(rows)) if rows else 0.0,
        "top_reasons": ";".join(f"{k}:{v}" for k, v in reason_counts.most_common(8)),
    }
    return rows, summary


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: List[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    ap.add_argument("--variants", default="", help="CSV variant names; empty = all")
    ap.add_argument("--days", type=int, default=360)
    ap.add_argument("--step", type=int, default=12, help="5m bars between signal checks; 12 = hourly")
    ap.add_argument("--max-hold-bars", type=int, default=432)
    ap.add_argument("--cost-bps-per-side", type=float, default=8.0, help="fee+slip bps per side")
    ap.add_argument("--cache", default=".cache/klines")
    ap.add_argument("--outdir", default="")
    args = ap.parse_args()

    run_id = datetime.now(timezone.utc).strftime("arf2_ab_diag_%Y%m%d_%H%M%S")
    outdir = Path(args.outdir or f"reports/research/{run_id}")
    outdir.mkdir(parents=True, exist_ok=True)

    stores: Dict[str, KlineStore] = {}
    cache_files: Dict[str, str] = {}
    for sym in _csv(args.symbols):
        loaded = _load_store(Path(args.cache), sym, int(args.days))
        if loaded is None:
            continue
        stores[sym], cache_files[sym] = loaded
    if not stores:
        raise SystemExit("No cached stores loaded")

    variants = _variants(_csv_lower(args.variants))
    all_rows: List[Dict[str, Any]] = []
    summaries: List[Dict[str, Any]] = []
    for name, cfg in variants.items():
        print(f"[variant] {name} symbols={len(stores)}", flush=True)
        rows, summary = _run_variant(name, cfg, stores, step=args.step, max_hold_bars=args.max_hold_bars, cost_bps_per_side=args.cost_bps_per_side)
        summaries.append(summary)
        all_rows.extend(rows)
        print(f"  raw={summary['raw_signals']} filled={summary['filled_trades']} netR={summary['net_r']:.2f} pf={summary['pf']}", flush=True)

    _write_csv(outdir / "signals.csv", all_rows)
    _write_csv(outdir / "summary.csv", summaries)
    (outdir / "cache_files.json").write_text(json.dumps(cache_files, indent=2), encoding="utf-8")

    lines = [
        "# ARF2 A/B diagnostic",
        "",
        f"- symbols loaded: {len(stores)}",
        f"- days: {args.days}",
        f"- variants: {len(variants)}",
        "",
        "| variant | raw | filled | fill_rate | netR | PF | WR | symbols_filled | top_raw_symbol_frac |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in sorted(summaries, key=lambda x: (float(x["net_r"]), int(x["filled_trades"])), reverse=True):
        pf = s["pf"]
        pf_s = "inf" if pf == float("inf") else f"{pf:.3f}"
        lines.append(
            f"| {s['variant']} | {s['raw_signals']} | {s['filled_trades']} | {s['fill_rate']:.2%} | "
            f"{s['net_r']:.2f} | {pf_s} | {s['winrate']:.1%} | {s['symbols_filled']} | {s['top_raw_symbol_frac']:.1%} |"
        )
    lines += ["", "## Outputs", "", f"- `{outdir / 'summary.csv'}`", f"- `{outdir / 'signals.csv'}`"]
    (outdir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[done] {outdir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
