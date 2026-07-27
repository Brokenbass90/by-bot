#!/usr/bin/env python3
"""Crypto level-memory sweep/reclaim exploration.

Research-only. No network, no live orders.

Hypothesis:
  "Range / saw / bounce" should not fade every range. First ask whether this
  symbol historically respects this level. Then trade only a sweep through the
  level and reclaim back inside.

This is an exploration gate. PASS here can justify a stricter follow-up and
shadow/risk=0.0 only, never live money directly.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

ROOT = Path(__file__).resolve().parent.parent

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.geometry_cache import aggregate_rows, load_cache_rows
from bot.elder_filter import elder_bias
from bot.level_memory import level_respect


@dataclass(frozen=True)
class Bar:
    ts: int
    o: float
    h: float
    l: float
    c: float
    v: float


@dataclass(frozen=True)
class Trade:
    symbol: str
    side: str
    entry_ts: int
    exit_ts: int
    entry: float
    exit: float
    level: float
    respect: float
    touches: int
    net_r: float
    gross_r: float
    fees_r: float
    reason: str


def _utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _f(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def _bars(rows: Sequence[Sequence[float]]) -> List[Bar]:
    out: List[Bar] = []
    for r in rows:
        if len(r) < 5:
            continue
        out.append(Bar(int(_f(r[0])), _f(r[1]), _f(r[2]), _f(r[3]), _f(r[4]), _f(r[5]) if len(r) > 5 else 0.0))
    return sorted(out, key=lambda b: b.ts)


def _rows(bars: Sequence[Bar]) -> List[List[float]]:
    return [[b.ts, b.o, b.h, b.l, b.c, b.v] for b in bars]


def _discover_symbols(cache_dir: Path, min_rows_5m: int, limit: int) -> List[str]:
    counts: Dict[str, int] = {}
    for p in cache_dir.glob("*_5_*.json"):
        sym = p.name.split("_5_", 1)[0]
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        counts[sym] = counts.get(sym, 0) + len(raw if isinstance(raw, list) else [])
    syms = [s for s, n in counts.items() if n >= int(min_rows_5m)]
    syms.sort(key=lambda s: counts.get(s, 0), reverse=True)
    return syms[: max(1, int(limit))]


def _load_symbol_h1(cache_dir: Path, symbol: str, days: int, end_ms: int | None) -> List[Bar]:
    direct = load_cache_rows(symbol, "60", data_cache_dir=cache_dir)
    derived = aggregate_rows(load_cache_rows(symbol, "5", data_cache_dir=cache_dir), 60)
    # Older runs silently preferred a short direct-H1 cache over a complete M5
    # history.  Use the candidate with the larger causal span/row count.
    candidates = [rows for rows in (direct, derived) if rows]
    rows = max(
        candidates,
        key=lambda x: ((int(_f(x[-1][0])) - int(_f(x[0][0]))) if len(x) > 1 else 0, len(x)),
        default=[],
    )
    bars = _bars(rows)
    if not bars:
        return []
    cutoff = int(end_ms) if end_ms is not None else bars[-1].ts + 1
    start = cutoff - int(days) * 86_400_000
    return [b for b in bars if start <= b.ts < cutoff]


def _atr(bars: Sequence[Bar], idx: int, period: int) -> float:
    vals: List[float] = []
    for i in range(max(1, idx - period + 1), idx + 1):
        prev = bars[i - 1].c
        vals.append(max(bars[i].h - bars[i].l, abs(bars[i].h - prev), abs(bars[i].l - prev)))
    return sum(vals) / len(vals) if vals else 0.0


def _pf(vals: Sequence[float]) -> float:
    gp = sum(v for v in vals if v > 0)
    gl = -sum(v for v in vals if v < 0)
    if gl <= 1e-12:
        return float("inf") if gp > 0 else 0.0
    return gp / gl


def _max_dd(vals: Sequence[float]) -> float:
    eq = 0.0
    peak = 0.0
    dd = 0.0
    for v in vals:
        eq += v
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return dd


def _folds(trades: Sequence[Trade], folds: int = 4) -> List[Dict[str, float]]:
    if not trades:
        return []
    t0 = min(t.entry_ts for t in trades)
    t1 = max(t.entry_ts for t in trades)
    span = max(1, t1 - t0 + 1)
    out = []
    for i in range(folds):
        lo = t0 + span * i // folds
        hi = t0 + span * (i + 1) // folds
        vals = [t.net_r for t in trades if lo <= t.entry_ts < hi]
        out.append({"fold": i + 1, "trades": len(vals), "net_r": round(sum(vals), 4), "pf": round(_pf(vals), 4) if vals else 0.0})
    return out


def _resolved_touches(stats) -> int:
    return int(stats.bounces + stats.sweeps + stats.breaks)


def _simulate_symbol(
    symbol: str,
    bars: Sequence[Bar],
    *,
    lookback: int,
    respect_min: float,
    min_touches: int,
    rr: float,
    atr_period: int,
    min_sweep_atr: float,
    reclaim_atr: float,
    sl_pad_atr: float,
    max_hold_bars: int,
    fee_bps_entry: float,
    fee_bps_exit: float,
    allow_longs: bool,
    allow_shorts: bool,
    memory_bars: int,
    elder_mode: str,
) -> List[Trade]:
    trades: List[Trade] = []
    if len(bars) < lookback + atr_period + max_hold_bars + 5:
        return trades
    i = max(lookback, atr_period, memory_bars) + 1
    while i < len(bars) - max_hold_bars - 2:
        b = bars[i]
        a = _atr(bars, i, atr_period)
        if a <= 0 or b.c <= 0:
            i += 1
            continue
        prev = bars[i - lookback : i]
        support = min(x.l for x in prev)
        resistance = max(x.h for x in prev)
        candidates = []
        if allow_longs and b.l < support - min_sweep_atr * a and b.c > support + reclaim_atr * a:
            candidates.append(("long", support, b.l - sl_pad_atr * a))
        if allow_shorts and b.h > resistance + min_sweep_atr * a and b.c < resistance - reclaim_atr * a:
            candidates.append(("short", resistance, b.h + sl_pad_atr * a))
        if not candidates:
            i += 1
            continue

        history = _rows(bars[max(0, i - memory_bars) : i])
        htf_history = aggregate_rows(history, 240) if elder_mode != "off" else []
        picked = None
        for side, level, sl in candidates:
            approach = "from_above" if side == "long" else "from_below"
            st = level_respect(history, level, approach=approach)
            resolved = _resolved_touches(st)
            if not (resolved >= min_touches and st.respect_score == st.respect_score and st.respect_score >= respect_min):
                continue
            if elder_mode != "off":
                eb = elder_bias(
                    history,
                    htf_rows=htf_history,
                    require_with_tide=(elder_mode == "strict"),
                )
                if (side == "long" and not eb.allow_long) or (side == "short" and not eb.allow_short):
                    continue
            if resolved >= min_touches:
                picked = (side, level, sl, st.respect_score, resolved)
                break
        if picked is None:
            i += 1
            continue

        side, level, sl, score, touches = picked
        entry_idx = i + 1
        entry = bars[entry_idx].o
        risk = (entry - sl) if side == "long" else (sl - entry)
        if risk <= 0 or risk > 4.0 * a:
            i += 1
            continue
        tp = entry + rr * risk if side == "long" else entry - rr * risk
        exit_px = bars[min(len(bars) - 1, entry_idx + max_hold_bars)].c
        exit_idx = min(len(bars) - 1, entry_idx + max_hold_bars)
        reason = "time"
        for j in range(entry_idx, min(len(bars), entry_idx + max_hold_bars + 1)):
            bj = bars[j]
            if side == "long":
                if bj.l <= sl:
                    exit_px, exit_idx, reason = sl, j, "sl"
                    break
                if bj.h >= tp:
                    exit_px, exit_idx, reason = tp, j, "tp"
                    break
            else:
                if bj.h >= sl:
                    exit_px, exit_idx, reason = sl, j, "sl"
                    break
                if bj.l <= tp:
                    exit_px, exit_idx, reason = tp, j, "tp"
                    break
        gross = ((exit_px - entry) if side == "long" else (entry - exit_px)) / risk
        fees_r = (entry * ((fee_bps_entry + fee_bps_exit) / 10_000.0)) / risk
        trades.append(Trade(symbol, side, bars[entry_idx].ts, bars[exit_idx].ts, entry, exit_px, level, score, touches, gross - fees_r, gross, fees_r, reason))
        i = exit_idx + 1
    return trades


def _summarize(trades: Sequence[Trade]) -> Dict[str, float]:
    vals = [t.net_r for t in trades]
    return {
        "trades": len(vals),
        "net_r": round(sum(vals), 4),
        "pf": round(_pf(vals), 4) if vals else 0.0,
        "wr": round(sum(1 for v in vals if v > 0) / len(vals), 4) if vals else 0.0,
        "dd_r": round(_max_dd(vals), 4),
        "folds_pos": sum(1 for f in _folds(trades) if f["net_r"] > 0),
    }


def _pick_best(rows: Sequence[dict]) -> dict:
    """Prefer an exploration-pass row, then rank by the frozen score.

    The original exploration selected the largest score even when that row
    missed the minimum-trade gate.  That made ``summary.md`` report FAIL while
    ``grid.csv`` contained passing rows.  Passing the gate is the primary
    ordering; score is only a tie-breaker inside the same gate status.
    """

    if not rows:
        return {"score": -1e9, "pass_exploration": 0}
    return dict(
        max(
            rows,
            key=lambda row: (
                int(row.get("pass_exploration", 0)),
                float(row.get("score", -1e9)),
            ),
        )
    )


def _write_outputs(out_dir: Path, rows: List[dict], best_trades: Sequence[Trade], best: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if rows:
        with (out_dir / "grid.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    with (out_dir / "trades.csv").open("w", newline="", encoding="utf-8") as f:
        fields = list(Trade.__dataclass_fields__.keys())
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for t in best_trades:
            w.writerow({k: getattr(t, k) for k in fields})
    lines = [
        "# Crypto Level-Memory Sweep/Reclaim Exploration",
        "",
        f"- output: `{out_dir}`",
        f"- passing candidates: `{sum(int(row.get('pass_exploration', 0)) for row in rows)}`",
        f"- best: `{best}`",
        f"- verdict: `{'PASS_EXPLORATION' if best.get('pass_exploration') else 'FAIL'}`",
        "",
        "Exploration-only. PASS here means next strict validation/shadow candidate, not live money.",
    ]
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default=str(ROOT / "data_cache"))
    ap.add_argument("--days", type=int, default=360)
    ap.add_argument("--end", default="", help="Exclusive UTC date, YYYY-MM-DD.")
    ap.add_argument("--limit", type=int, default=24)
    ap.add_argument("--min-rows-5m", type=int, default=50_000)
    ap.add_argument("--symbols", default="")
    ap.add_argument("--lookbacks", default="48,96")
    ap.add_argument("--respect", default="0.55,0.65,0.75")
    ap.add_argument("--rr", default="1.2,1.6,2.0")
    ap.add_argument("--min-touches", type=int, default=3)
    ap.add_argument("--side", choices=("long", "short", "both"), default="both")
    ap.add_argument("--memory-bars", type=int, default=960)
    ap.add_argument("--elder-mode", choices=("off", "permissive", "strict"), default="off")
    ap.add_argument(
        "--entry-cost-bps",
        type=float,
        default=8.0,
        help="All-in entry cost in bps (fee plus slippage).",
    )
    ap.add_argument(
        "--exit-cost-bps",
        type=float,
        default=8.0,
        help="All-in exit cost in bps (fee plus slippage).",
    )
    ap.add_argument("--max-wall-sec", type=int, default=0)
    ap.add_argument("--out", default="")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    cache_dir = Path(args.cache_dir)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        symbols = _discover_symbols(cache_dir, args.min_rows_5m, args.limit)
    end_ms = None
    if args.end:
        end_ms = int(datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    data = {s: _load_symbol_h1(cache_dir, s, args.days, end_ms) for s in symbols}
    data = {s: b for s, b in data.items() if len(b) >= 300}

    out_dir = Path(args.out) if args.out else ROOT / "reports" / "research" / f"crypto_level_memory_sweep_reclaim_20260707_{_utc_compact()}"
    grid_rows: List[dict] = []
    trades_by_key: Dict[tuple, List[Trade]] = {}

    lookbacks = [int(x) for x in args.lookbacks.split(",") if x.strip()]
    respect_grid = [float(x) for x in args.respect.split(",") if x.strip()]
    rr_grid = [float(x) for x in args.rr.split(",") if x.strip()]
    total_combos = max(1, len(lookbacks) * len(respect_grid) * len(rr_grid))
    combo_idx = 0
    started = time.monotonic()
    if not args.quiet:
        print(json.dumps({
            "event": "start",
            "out": str(out_dir),
            "symbols": list(data),
            "combos": total_combos,
        }, ensure_ascii=False), flush=True)

    for lookback in lookbacks:
        for respect_min in respect_grid:
            for rr in rr_grid:
                combo_idx += 1
                trades: List[Trade] = []
                for sym, bars in data.items():
                    trades.extend(
                        _simulate_symbol(
                            sym,
                            bars,
                            lookback=lookback,
                            respect_min=respect_min,
                            min_touches=args.min_touches,
                            rr=rr,
                            atr_period=14,
                            min_sweep_atr=0.15,
                            reclaim_atr=0.03,
                            sl_pad_atr=0.08,
                            max_hold_bars=36,
                            fee_bps_entry=max(0.0, float(args.entry_cost_bps)),
                            fee_bps_exit=max(0.0, float(args.exit_cost_bps)),
                            allow_longs=args.side in {"long", "both"},
                            allow_shorts=args.side in {"short", "both"},
                            memory_bars=max(30, int(args.memory_bars)),
                            elder_mode=args.elder_mode,
                        )
                    )
                    if args.max_wall_sec and time.monotonic() - started > args.max_wall_sec:
                        raise TimeoutError(f"max wall time exceeded after {sym}")
                stats = _summarize(sorted(trades, key=lambda t: t.entry_ts))
                pass_exploration = stats["trades"] >= 40 and stats["pf"] >= 1.05 and stats["folds_pos"] >= 2
                score = stats["net_r"] + 20.0 * (stats["pf"] - 1.0) + 5.0 * stats["folds_pos"]
                row = {
                    "lookback": lookback,
                    "respect_min": respect_min,
                    "rr": rr,
                    "side": args.side,
                    "elder_mode": args.elder_mode,
                    "entry_cost_bps": round(max(0.0, float(args.entry_cost_bps)), 4),
                    "exit_cost_bps": round(max(0.0, float(args.exit_cost_bps)), 4),
                    **stats,
                    "pass_exploration": int(pass_exploration),
                    "score": round(score, 4),
                }
                grid_rows.append(row)
                trades_by_key[(lookback, respect_min, rr)] = sorted(
                    trades, key=lambda t: t.entry_ts
                )
                if not args.quiet:
                    print(json.dumps({
                        "event": "combo_done",
                        "combo": combo_idx,
                        "combos": total_combos,
                        **row,
                    }, ensure_ascii=False), flush=True)

    best = _pick_best(grid_rows)
    best_trades = trades_by_key.get(
        (best.get("lookback"), best.get("respect_min"), best.get("rr")),
        [],
    )
    _write_outputs(out_dir, grid_rows, best_trades, best)
    print(json.dumps({"out": str(out_dir), "symbols": list(data), "best": best}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
