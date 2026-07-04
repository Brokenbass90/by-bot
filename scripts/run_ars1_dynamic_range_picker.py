#!/usr/bin/env python3
"""Causal ARS1 range-picker validation.

Fixed ARS1 r170/no-LTC looked good on selected symbols, then failed the OOS-symbol
gate. This runner tests the only valid rescue hypothesis: can a causal range
scanner pick the right instruments *before* the OOS window?

For each fold:
  1. score every symbol on the prior lookback window only;
  2. pick top tradeable range symbols;
  3. run fixed ARS1 on the next OOS window;
  4. pass fold results through oos_selector.

No ARS1 parameter optimization is done here. The only grid is picker policy.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
DAY_MS = 86_400_000
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.oos_selector import evaluate_candidate
from bot.range_scanner import RangeScore, score_instrument


ARS1_R170_ENV: Dict[str, str] = {
    "BACKTEST_CACHE_ONLY": "1",
    "ARS1_BB_PERIOD": "20",
    "ARS1_BB_STD": "2.0",
    "ARS1_MIN_BAND_WIDTH_PCT": "1.5",
    "ARS1_MAX_BAND_WIDTH_PCT": "24.0",
    "ARS1_RSI_LONG_MAX": "38",
    "ARS1_RSI_SHORT_MIN": "55",
    "ARS1_SL_ATR_MULT": "0.8",
    "ARS1_TP1_FRAC": "0.55",
    "ARS1_MIN_RR": "1.15",
    "ARS1_MIN_STOP_PCT": "0.0015",
    "ARS1_MAX_STOP_PCT": "0.0600",
    "ARS1_TIME_STOP_BARS_5M": "216",
    "ARS1_COOLDOWN_BARS_5M": "12",
    "ARS1_ADX_PERIOD": "14",
    "ARS1_MAX_ADX": "0.0",
    "ARS1_MIN_VOL_MULT": "1.1",
    "ARS1_RECLAIM_ATR": "0.0",
    "ARS1_TRAIL_ATR_MULT": "0.0",
    "ARS1_TRAIL_ACTIVATE_RR": "1.0",
    "ARS1_ALLOW_LONGS": "1",
    "ARS1_ALLOW_SHORTS": "1",
}


def _parse_float_list(raw: str) -> List[float]:
    return [float(x.strip()) for x in raw.replace(";", ",").split(",") if x.strip()]


def _parse_int_list(raw: str) -> List[int]:
    return [int(x.strip()) for x in raw.replace(";", ",").split(",") if x.strip()]


def _date_to_ms(s: str) -> int:
    dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _ms_to_date(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _discover_symbols(cache_dir: Path) -> List[str]:
    symbols = set()
    if not cache_dir.exists():
        return []
    for p in cache_dir.rglob("*USDT*"):
        m = re.search(r"([A-Z0-9]+USDT)", p.name)
        if m:
            symbols.add(m.group(1))
    return sorted(symbols)


def _load_symbol_rows(cache_dir: Path, symbol: str) -> List[list]:
    by_ts: Dict[int, list] = {}
    for p in cache_dir.glob(f"{symbol}_5_*.json"):
        try:
            rows = json.loads(p.read_text())
        except Exception:
            continue
        if not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, list) or len(r) < 6:
                continue
            try:
                ts = int(float(r[0]))
                by_ts[ts] = [
                    ts,
                    float(r[1]),
                    float(r[2]),
                    float(r[3]),
                    float(r[4]),
                    float(r[5]),
                ]
            except Exception:
                continue
    return [by_ts[k] for k in sorted(by_ts)]


def _slice_rows(rows: Sequence[list], start_ms: int, end_ms: int) -> List[list]:
    return [r for r in rows if start_ms <= int(r[0]) < end_ms]


def _write_csv(path: Path, rows: Iterable[Dict[str, object]]) -> None:
    rows = list(rows)
    if not rows:
        return
    keys = list(rows[0].keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def _read_summary(path: Path) -> Dict[str, str]:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"empty summary: {path}")
    return rows[0]


def _score_fold_symbols(
    rows_by_symbol: Dict[str, List[list]],
    *,
    train_start_ms: int,
    train_end_ms: int,
    lookback_bars: int,
    min_score: float,
    min_width_atr: float,
    max_width_atr: float,
) -> List[RangeScore]:
    scores: List[RangeScore] = []
    for symbol, rows in rows_by_symbol.items():
        train_rows = _slice_rows(rows, train_start_ms, train_end_ms)
        if len(train_rows) > lookback_bars:
            train_rows = train_rows[-lookback_bars:]
        scores.append(
            score_instrument(
                symbol,
                train_rows,
                lookback=min(lookback_bars, max(40, len(train_rows))),
                min_width_atr=min_width_atr,
                max_width_atr=max_width_atr,
                min_score=min_score,
            )
        )
    scores.sort(key=lambda r: (r.tradeable, r.score, r.votes), reverse=True)
    return scores


def _run_fold(
    *,
    symbols: List[str],
    fold_days: int,
    fold_end_ms: int,
    tag: str,
    fee_bps: float,
    slippage_bps: float,
    max_positions: int,
) -> Dict[str, object]:
    if not symbols:
        return {
            "status": "no_picks",
            "trades": 0,
            "net_pnl": 0.0,
            "profit_factor": 0.0,
            "winrate": 0.0,
            "max_drawdown": 0.0,
            "run_dir": "",
            "error": "",
        }
    env = os.environ.copy()
    env.update(ARS1_R170_ENV)
    env["ARS1_SYMBOL_ALLOWLIST"] = ",".join(symbols)
    cmd = [
        sys.executable,
        "backtest/run_portfolio.py",
        "--symbols",
        ",".join(symbols),
        "--strategies",
        "alt_range_scalp_v1",
        "--days",
        str(fold_days),
        "--end",
        _ms_to_date(fold_end_ms),
        "--tag",
        tag,
        "--starting_equity",
        "100",
        "--risk_pct",
        "0.005",
        "--leverage",
        "1",
        "--max_positions",
        str(max_positions),
        "--fee_bps",
        str(fee_bps),
        "--slippage_bps",
        str(slippage_bps),
        "--entry-on-next-open",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True, timeout=1200)
    saved = ""
    for line in (proc.stdout or "").splitlines():
        if line.startswith("Saved portfolio run to:"):
            saved = line.split(":", 1)[1].strip()
            break
    if proc.returncode != 0 or not saved:
        return {
            "status": "fail",
            "trades": 0,
            "net_pnl": 0.0,
            "profit_factor": 0.0,
            "winrate": 0.0,
            "max_drawdown": 0.0,
            "run_dir": saved,
            "error": (proc.stderr or proc.stdout or "")[-500:].replace("\n", " "),
        }
    summary = _read_summary(ROOT / saved / "summary.csv")
    return {
        "status": "ok",
        "trades": int(float(summary.get("trades") or 0)),
        "net_pnl": float(summary.get("net_pnl") or 0.0),
        "profit_factor": float(summary.get("profit_factor") or 0.0),
        "winrate": float(summary.get("winrate") or 0.0),
        "max_drawdown": float(summary.get("max_drawdown") or 0.0),
        "run_dir": saved,
        "error": "",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="", help="Comma-separated universe. Defaults to discovered cache symbols.")
    ap.add_argument("--exclude", default="", help="Comma-separated symbols to exclude.")
    ap.add_argument("--end", default="2026-04-30")
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--fold-days", type=int, default=90)
    ap.add_argument("--train-days", default="30,60,120")
    ap.add_argument("--lookback-bars", default="60,120")
    ap.add_argument("--top-ns", default="3,5")
    ap.add_argument("--min-scores", default="0.45,0.55")
    ap.add_argument("--min-width-atrs", default="2.0")
    ap.add_argument("--max-width-atrs", default="12.0")
    ap.add_argument("--fee-bps", type=float, default=6.0)
    ap.add_argument("--slippage-bps", type=float, default=2.0)
    ap.add_argument("--max-positions", type=int, default=3)
    ap.add_argument("--max-symbols", type=int, default=0)
    ap.add_argument("--outdir", default="")
    ap.add_argument("--tag-prefix", default="ars1_dynamic_range_picker")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    cache_dir = ROOT / ".cache" / "klines"
    if args.symbols.strip():
        symbols = [s.strip().upper() for s in args.symbols.replace(";", ",").split(",") if s.strip()]
    else:
        symbols = _discover_symbols(cache_dir)
    exclude = {s.strip().upper() for s in args.exclude.replace(";", ",").split(",") if s.strip()}
    symbols = [s for s in symbols if s not in exclude]
    if args.max_symbols > 0:
        symbols = symbols[: args.max_symbols]
    if not symbols:
        raise SystemExit("no symbols to test")

    rows_by_symbol = {s: _load_symbol_rows(cache_dir, s) for s in symbols}
    rows_by_symbol = {s: r for s, r in rows_by_symbol.items() if r}
    if not rows_by_symbol:
        raise SystemExit("no cached rows loaded")
    symbols = sorted(rows_by_symbol)

    train_days = _parse_int_list(args.train_days)
    lookback_bars = _parse_int_list(args.lookback_bars)
    top_ns = _parse_int_list(args.top_ns)
    min_scores = _parse_float_list(args.min_scores)
    min_width_atrs = _parse_float_list(args.min_width_atrs)
    max_width_atrs = _parse_float_list(args.max_width_atrs)
    combos = list(itertools.product(train_days, lookback_bars, top_ns, min_scores, min_width_atrs, max_width_atrs))
    if args.smoke:
        combos = combos[:1]
        args.folds = min(args.folds, 2)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    outdir = Path(args.outdir) if args.outdir else ROOT / "reports" / "research" / f"{args.tag_prefix}_{ts}"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "params.json").write_text(
        json.dumps({"args": vars(args), "symbols": symbols, "env": ARS1_R170_ENV}, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    end_ms = _date_to_ms(args.end)
    fold_ms = args.fold_days * DAY_MS
    fold_results: List[Dict[str, object]] = []
    candidate_rows: List[Dict[str, object]] = []
    score_rows: List[Dict[str, object]] = []

    for ci, (train_d, lb, top_n, min_score, min_w, max_w) in enumerate(combos, 1):
        cid = f"td{train_d}_lb{lb}_top{top_n}_s{min_score:g}_w{min_w:g}-{max_w:g}"
        print(f"[candidate {ci}/{len(combos)}] {cid}", flush=True)
        folds_for_selector: List[Dict[str, object]] = []
        for fi in range(args.folds):
            fold_start_ms = end_ms - (args.folds - fi) * fold_ms
            fold_end_ms = fold_start_ms + fold_ms
            train_end_ms = fold_start_ms
            train_start_ms = train_end_ms - train_d * DAY_MS
            scores = _score_fold_symbols(
                rows_by_symbol,
                train_start_ms=train_start_ms,
                train_end_ms=train_end_ms,
                lookback_bars=lb,
                min_score=min_score,
                min_width_atr=min_w,
                max_width_atr=max_w,
            )
            picked = [s.symbol for s in scores if s.tradeable][:top_n]
            for rank, s in enumerate(scores[: min(12, len(scores))], 1):
                score_rows.append({
                    "candidate": cid,
                    "fold": fi,
                    "rank": rank,
                    "symbol": s.symbol,
                    "score": s.score,
                    "tradeable": int(s.tradeable),
                    "is_range": int(s.is_range),
                    "votes": s.votes,
                    "regime": s.regime,
                    "range_prob": s.range_prob,
                    "width_atr": s.width_atr,
                    "reason": s.reason,
                })

            tag = f"{args.tag_prefix}_{cid}_f{fi}_{ts}"
            result = _run_fold(
                symbols=picked,
                fold_days=args.fold_days,
                fold_end_ms=fold_end_ms,
                tag=tag,
                fee_bps=args.fee_bps,
                slippage_bps=args.slippage_bps,
                max_positions=args.max_positions,
            )
            fold_row = {
                "candidate": cid,
                "fold": fi,
                "train_start": _ms_to_date(train_start_ms),
                "train_end": _ms_to_date(train_end_ms),
                "oos_start": _ms_to_date(fold_start_ms),
                "oos_end": _ms_to_date(fold_end_ms),
                "picked": ",".join(picked),
                **result,
            }
            fold_results.append(fold_row)
            folds_for_selector.append({"net_r": float(result["net_pnl"]), "trades": int(result["trades"])})
            _write_csv(outdir / "fold_results.csv", fold_results)
            _write_csv(outdir / "scoreboard.csv", score_rows)

        graded = evaluate_candidate(
            {"id": cid, "folds": folds_for_selector, "params": {
                "train_days": train_d,
                "lookback_bars": lb,
                "top_n": top_n,
                "min_score": min_score,
                "min_width_atr": min_w,
                "max_width_atr": max_w,
            }},
            min_folds=args.folds,
            min_frac_positive=0.75,
            min_trades_total=40,
            min_trades_per_fold=5,
            max_peak_ratio=3.0,
        )
        candidate_rows.append({
            "candidate": cid,
            "passes": int(graded.passes),
            "reason": graded.reason,
            "robustness": graded.robustness,
            "folds": graded.folds,
            "folds_positive": graded.folds_positive,
            "frac_positive": graded.frac_positive,
            "median_metric": graded.median_metric,
            "min_metric": graded.min_metric,
            "dispersion": graded.dispersion,
            "peak_ratio": graded.peak_ratio,
            "total_trades": graded.total_trades,
        })
        candidate_rows.sort(key=lambda r: (int(r["passes"]), float(r["frac_positive"]), float(r["robustness"])), reverse=True)
        _write_csv(outdir / "candidates.csv", candidate_rows)

    passing = [r for r in candidate_rows if int(r["passes"]) == 1]
    verdict = {
        "candidates": len(candidate_rows),
        "passing": len(passing),
        "best": candidate_rows[0] if candidate_rows else None,
        "outdir": str(outdir),
    }
    (outdir / "verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True), encoding="utf-8")
    (outdir / "summary.md").write_text(
        "# ARS1 dynamic range-picker validation\n\n"
        f"- candidates: `{verdict['candidates']}`\n"
        f"- passing: `{verdict['passing']}`\n"
        f"- best: `{(verdict['best'] or {}).get('candidate', '')}` / `{(verdict['best'] or {}).get('reason', '')}`\n"
        f"- output: `{outdir}`\n",
        encoding="utf-8",
    )
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
