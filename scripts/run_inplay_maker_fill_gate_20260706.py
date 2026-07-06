#!/usr/bin/env python3
"""Honest maker-fill gate for inplay breakout r061.

This runner intentionally does not use the portfolio engine pending-limit fill:
the point of this gate is to answer the narrower question added in
``bot.maker_fill``: after an r061 signal, does a resting maker limit get filled
often enough, and does the filled subset still survive stress costs?

Research-only. PASS can justify shadow/risk=0.0, not live money.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.engine import Candle, KlineStore  # noqa: E402
from bot.geometry_cache import load_rows  # noqa: E402
from bot.maker_fill import simulate_maker_trade  # noqa: E402
from bot.market_context import atr as rows_atr  # noqa: E402
from scripts.run_inplay_breakout_retest_strict_gate_20260706 import (  # noqa: E402
    INPLAY_R061_ENV,
    SYMBOLS,
)
from strategies.inplay_breakout import InPlayBreakoutWrapper  # noqa: E402


@dataclass(frozen=True)
class SignalRec:
    symbol: str
    i: int
    ts: int
    side: str
    entry: float
    sl: float
    atr: float


@dataclass
class CaseMetrics:
    case: str
    symbols: str
    days: int
    end: str
    offset_atr: float
    validity_bars: int
    maker_fee_bps: float
    taker_fee_bps: float
    exit_slippage_bps: float
    generated_signals: int
    placed_signals: int
    unfilled: int
    trades: int
    unfilled_rate: float
    net_r: float
    profit_factor: float
    winrate: float
    max_drawdown_r: float
    gross_profit_r: float
    gross_loss_r: float


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _parse_date(raw: str) -> datetime:
    return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _candle_rows(candles: Sequence[Candle]) -> List[List[float]]:
    return [[int(c.ts), float(c.o), float(c.h), float(c.l), float(c.c), float(c.v)] for c in candles]


def _max_drawdown(values: Sequence[float]) -> float:
    peak = 0.0
    max_dd = 0.0
    cur = 0.0
    for v in values:
        cur += float(v)
        peak = max(peak, cur)
        max_dd = max(max_dd, peak - cur)
    return max_dd


def _metrics(rs: Sequence[float]) -> Tuple[float, float, float, float, float, float]:
    gross_profit = sum(x for x in rs if x > 0)
    gross_loss = -sum(x for x in rs if x < 0)
    pf = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    wr = (sum(1 for x in rs if x > 0) / len(rs)) if rs else 0.0
    return sum(rs), pf, wr, _max_drawdown(rs), gross_profit, gross_loss


def _load_store(symbol: str, *, days: int, end: str, cache_dir: Path) -> KlineStore:
    end_ms = int(_parse_date(end).timestamp() * 1000)
    start_ms = int((_parse_date(end) - timedelta(days=int(days))).timestamp() * 1000)
    raw_rows = [
        r for r in load_rows(symbol, "5", data_cache_dir=cache_dir)
        if int(float(r[0])) >= start_ms and int(float(r[0])) < end_ms
    ]
    candles = [
        Candle(ts=int(float(r[0])), o=float(r[1]), h=float(r[2]), l=float(r[3]), c=float(r[4]), v=float(r[5] if len(r) > 5 else 0.0))
        for r in raw_rows
    ]
    if len(candles) < 500:
        raise RuntimeError(f"too few candles for {symbol}: {len(candles)}")
    return KlineStore(symbol, candles, base_interval_min=5)


def _generate_signals(symbol: str, *, days: int, end: str, cache_dir: Path) -> Tuple[List[SignalRec], List[List[float]]]:
    store = _load_store(symbol, days=days, end=end, cache_dir=cache_dir)
    rows = _candle_rows(store.exec_candles)
    wrapper = InPlayBreakoutWrapper()
    out: List[SignalRec] = []

    # Leave room after the signal for validity + max hold. Signals too close to
    # the end would be forced into artificial EOP outcomes.
    max_hold = int(float(INPLAY_R061_ENV.get("BREAKOUT_TIME_STOP_BARS", "288") or 288))
    last_i = max(0, len(store.exec_candles) - max_hold - 2)
    seen_ts: set[int] = set()
    for i in range(300, last_i):
        store.set_index(i)
        bar = store.exec_candles[i]
        signal_ts = int(bar.ts) + 5 * 60_000
        sig = wrapper.signal(store, signal_ts, float(bar.c))
        if sig is None:
            continue
        side = str(getattr(sig, "side", "") or "").lower()
        if side not in {"long", "short"}:
            continue
        entry = float(getattr(sig, "entry", 0.0) or 0.0)
        sl = float(getattr(sig, "sl", 0.0) or 0.0)
        a = rows_atr(rows[: i + 1], 14)
        if not (entry > 0 and sl > 0 and a > 0 and a == a):
            continue
        if side == "long" and sl >= entry:
            continue
        if side == "short" and sl <= entry:
            continue
        key = int(bar.ts)
        if key in seen_ts:
            continue
        seen_ts.add(key)
        out.append(SignalRec(symbol=symbol, i=i, ts=int(bar.ts), side=side, entry=entry, sl=sl, atr=float(a)))
    return out, rows


def _simulate_case(
    *,
    case: str,
    symbols: Sequence[str],
    days: int,
    end: str,
    offset_atr: float,
    validity_bars: int,
    maker_fee_bps: float,
    taker_fee_bps: float,
    exit_slippage_bps: float,
    cache_dir: Path,
    max_positions: int = 3,
) -> Tuple[CaseMetrics, Dict[str, List[float]]]:
    generated: List[SignalRec] = []
    rows_by_symbol: Dict[str, List[List[float]]] = {}
    for sym in symbols:
        sigs, rows = _generate_signals(sym, days=days, end=end, cache_dir=cache_dir)
        generated.extend(sigs)
        rows_by_symbol[sym] = rows
    generated.sort(key=lambda s: (s.ts, s.symbol))

    ts_to_i = {sym: {int(row[0]): i for i, row in enumerate(rows)} for sym, rows in rows_by_symbol.items()}
    open_until: List[int] = []
    busy_until_by_symbol: Dict[str, int] = {}
    placed = 0
    unfilled = 0
    rs: List[float] = []
    rs_by_symbol: Dict[str, List[float]] = {sym: [] for sym in symbols}
    max_hold = int(float(INPLAY_R061_ENV.get("BREAKOUT_TIME_STOP_BARS", "288") or 288))

    for sig in generated:
        open_until = [x for x in open_until if x > sig.i]
        if busy_until_by_symbol.get(sig.symbol, -1) > sig.i:
            continue
        if len(open_until) >= int(max_positions):
            continue
        rows = rows_by_symbol[sig.symbol]
        if sig.side == "long":
            limit = sig.entry - float(offset_atr) * sig.atr
            sl_atr = (limit - sig.sl) / sig.atr
        else:
            limit = sig.entry + float(offset_atr) * sig.atr
            sl_atr = (sig.sl - limit) / sig.atr
        if not (limit > 0 and sl_atr > 0):
            continue
        placed += 1
        trade = simulate_maker_trade(
            rows,
            sig.i,
            sig.side,
            limit,
            sl_atr=float(sl_atr),
            tp_rr=1.5,
            validity_bars=int(validity_bars),
            through_atr=0.05,
            max_hold=max_hold,
            maker_fee_bps=float(maker_fee_bps),
            taker_fee_bps=float(taker_fee_bps),
            exit_slippage_bps=float(exit_slippage_bps),
            atr_period=14,
        )
        if trade is None:
            unfilled += 1
            continue
        r = float(trade.get("r", 0.0) or 0.0)
        rs.append(r)
        rs_by_symbol[sig.symbol].append(r)
        exit_i = ts_to_i.get(sig.symbol, {}).get(int(trade.get("exit_ts", 0) or 0), sig.i + max_hold)
        open_until.append(int(exit_i))
        busy_until_by_symbol[sig.symbol] = int(exit_i)

    net, pf, wr, dd, gp, gl = _metrics(rs)
    metrics = CaseMetrics(
        case=case,
        symbols=";".join(symbols),
        days=int(days),
        end=end,
        offset_atr=float(offset_atr),
        validity_bars=int(validity_bars),
        maker_fee_bps=float(maker_fee_bps),
        taker_fee_bps=float(taker_fee_bps),
        exit_slippage_bps=float(exit_slippage_bps),
        generated_signals=len(generated),
        placed_signals=placed,
        unfilled=unfilled,
        trades=len(rs),
        unfilled_rate=(unfilled / placed) if placed else 1.0,
        net_r=net,
        profit_factor=pf,
        winrate=wr,
        max_drawdown_r=dd,
        gross_profit_r=gp,
        gross_loss_r=gl,
    )
    return metrics, rs_by_symbol


def _dict_rows(rows: Iterable[CaseMetrics]) -> List[Dict[str, object]]:
    return [r.__dict__.copy() for r in rows]


def _write_csv(path: Path, rows: Iterable[CaseMetrics]) -> None:
    data = _dict_rows(rows)
    fields = list(CaseMetrics.__dataclass_fields__.keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(data)


def _gate(rows: Sequence[CaseMetrics], rs_by_symbol: Dict[str, List[float]]) -> Dict[str, object]:
    by_case = {r.case: r for r in rows}
    stress = by_case.get("stress_360")
    folds = [r for r in rows if r.case.startswith("fold_stress_")]
    fold_pos = sum(1 for r in folds if r.net_r > 0 and r.profit_factor >= 1.0 and r.trades > 0)
    gp_by_symbol = {sym: sum(max(0.0, r) for r in vals) for sym, vals in rs_by_symbol.items()}
    total_gp = sum(gp_by_symbol.values())
    concentration = (max(gp_by_symbol.values() or [0.0]) / total_gp) if total_gp > 0 else 1.0
    reasons: List[str] = []
    if stress is None or stress.profit_factor < 1.20 or stress.net_r <= 0 or stress.trades < 30:
        reasons.append("stress_weak")
    if stress is None or stress.unfilled_rate >= 0.50:
        reasons.append("unfilled_high")
    if fold_pos < 3:
        reasons.append(f"time_folds_weak_{fold_pos}/4")
    if concentration >= 0.35:
        reasons.append(f"concentration_{concentration:.3f}")
    return {
        "passed": not reasons,
        "reasons": ";".join(reasons) if reasons else "maker_fill_gate_pass",
        "stress_pf": None if stress is None else round(stress.profit_factor, 6),
        "stress_net_r": None if stress is None else round(stress.net_r, 6),
        "stress_trades": 0 if stress is None else stress.trades,
        "stress_unfilled_rate": None if stress is None else round(stress.unfilled_rate, 6),
        "folds_positive": fold_pos,
        "symbol_concentration": round(concentration, 6),
        "gross_profit_by_symbol": {k: round(v, 6) for k, v in gp_by_symbol.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", default="2026-07-05")
    ap.add_argument("--cache", default="data_cache")
    ap.add_argument("--tag-prefix", default="inplay_maker_fill_gate_20260706")
    ap.add_argument("--offsets", default="0.1,0.25,0.4")
    ap.add_argument("--validities", default="6,12,24")
    ap.add_argument("--maker-fee-bps", type=float, default=1.0)
    ap.add_argument("--taker-fee-bps", type=float, default=6.0)
    ap.add_argument("--exit-slippage-bps", type=float, default=2.0)
    ap.add_argument("--stress-maker-fee-bps", type=float, default=2.0)
    ap.add_argument("--stress-taker-fee-bps", type=float, default=10.0)
    ap.add_argument("--stress-exit-slippage-bps", type=float, default=5.0)
    ap.add_argument("--smoke-days", type=int, default=0)
    args = ap.parse_args()

    os.environ.update(INPLAY_R061_ENV)
    os.environ["BACKTEST_CACHE_ONLY"] = "1"
    os.environ["CACHE_ONLY"] = "1"

    cache_dir = ROOT / args.cache
    offsets = [float(x.strip()) for x in str(args.offsets).split(",") if x.strip()]
    validities = [int(x.strip()) for x in str(args.validities).split(",") if x.strip()]
    stamp = _stamp()
    out_dir = ROOT / "reports" / "research" / f"{args.tag_prefix}_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    best: Optional[Tuple[Dict[str, object], List[CaseMetrics], Dict[str, List[float]]]] = None
    scan_rows: List[Dict[str, object]] = []
    end_dt = _parse_date(args.end)

    for offset in offsets:
        for validity in validities:
            days = int(args.smoke_days or 360)
            base, _ = _simulate_case(
                case="base_360",
                symbols=SYMBOLS,
                days=days,
                end=args.end,
                offset_atr=offset,
                validity_bars=validity,
                maker_fee_bps=args.maker_fee_bps,
                taker_fee_bps=args.taker_fee_bps,
                exit_slippage_bps=args.exit_slippage_bps,
                cache_dir=cache_dir,
            )
            stress, rs_by_symbol = _simulate_case(
                case="stress_360",
                symbols=SYMBOLS,
                days=days,
                end=args.end,
                offset_atr=offset,
                validity_bars=validity,
                maker_fee_bps=args.stress_maker_fee_bps,
                taker_fee_bps=args.stress_taker_fee_bps,
                exit_slippage_bps=args.stress_exit_slippage_bps,
                cache_dir=cache_dir,
            )
            rows = [base, stress]
            if not args.smoke_days:
                for idx in range(4):
                    fold_end = end_dt - timedelta(days=(3 - idx) * 90)
                    fold, _fold_sym = _simulate_case(
                        case=f"fold_stress_{idx + 1}",
                        symbols=SYMBOLS,
                        days=90,
                        end=_fmt(fold_end),
                        offset_atr=offset,
                        validity_bars=validity,
                        maker_fee_bps=args.stress_maker_fee_bps,
                        taker_fee_bps=args.stress_taker_fee_bps,
                        exit_slippage_bps=args.stress_exit_slippage_bps,
                        cache_dir=cache_dir,
                    )
                    rows.append(fold)
            verdict = _gate(rows, rs_by_symbol)
            row = {
                "offset_atr": offset,
                "validity_bars": validity,
                **{f"base_{k}": v for k, v in base.__dict__.items() if k not in {"case", "symbols", "days", "end", "offset_atr", "validity_bars"}},
                **{f"stress_{k}": v for k, v in stress.__dict__.items() if k not in {"case", "symbols", "days", "end", "offset_atr", "validity_bars"}},
                **{f"gate_{k}": v for k, v in verdict.items() if k != "gross_profit_by_symbol"},
            }
            scan_rows.append(row)
            score = (
                (1.0 if verdict["passed"] else 0.0) * 1_000_000
                + float(stress.net_r) * 100
                + float(stress.profit_factor if not math.isinf(stress.profit_factor) else 10.0) * 10
                - float(stress.unfilled_rate) * 50
            )
            if best is None or score > float(best[0]["score"]):
                best = ({"score": score, "offset_atr": offset, "validity_bars": validity, "verdict": verdict}, rows, rs_by_symbol)
            print(
                f"offset={offset} validity={validity} "
                f"stress_trades={stress.trades} stress_netR={stress.net_r:.2f} "
                f"stress_pf={stress.profit_factor:.3f} unfilled={stress.unfilled_rate:.2%} "
                f"gate={'PASS' if verdict['passed'] else 'FAIL'} {verdict['reasons']}",
                flush=True,
            )

    scan_path = out_dir / "scan.csv"
    if scan_rows:
        fields = sorted({k for row in scan_rows for k in row})
        with scan_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(scan_rows)

    if best is not None:
        _write_csv(out_dir / "best_strict_cases.csv", best[1])
        (out_dir / "best_symbol_rs.json").write_text(json.dumps(best[2], indent=2, sort_keys=True) + "\n", encoding="utf-8")
        verdict = dict(best[0]["verdict"])
    else:
        verdict = {"passed": False, "reasons": "no_rows"}
    (out_dir / "verdict.json").write_text(json.dumps({"best": best[0] if best else None, "verdict": verdict}, indent=2) + "\n", encoding="utf-8")
    (out_dir / "summary.md").write_text(
        "\n".join(
            [
                "# Inplay Maker-Fill Gate 2026-07-06",
                "",
                f"- output: `{out_dir}`",
                f"- scan_csv: `{scan_path}`",
                f"- best: `{best[0] if best else None}`",
                f"- verdict: `{'PASS' if verdict.get('passed') else 'FAIL'}`",
                f"- reasons: `{verdict.get('reasons')}`",
                "",
                "Pre-registered thresholds: stress PF >= 1.2, 3/4 stress folds positive, unfilled < 50%, symbol concentration < 0.35.",
                "Research-only. PASS can justify shadow/risk=0.0, not automatic live money.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(out_dir, flush=True)
    print("verdict=" + json.dumps(verdict, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
