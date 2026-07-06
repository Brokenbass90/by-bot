#!/usr/bin/env python3
"""Causal dynamic symbol selector for inplay maker-fill.

The strict maker-fill gate showed a near-miss: fill rate was acceptable, but
stress PF and time folds were weak. This runner tests the next honest question:
can we pick the right inplay symbols using only a prior window, then trade the
future window with the same maker-fill execution?

Research-only. PASS can justify shadow/risk=0.0, not live money.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_inplay_maker_fill_gate_20260706 import _simulate_case  # noqa: E402


DEFAULT_SYMBOLS = (
    "BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,LINKUSDT,LTCUSDT,DOTUSDT,SUIUSDT,"
    "DOGEUSDT,XRPUSDT,AVAXUSDT,ATOMUSDT,BNBUSDT,BCHUSDT,XLMUSDT,"
    "1000PEPEUSDT,HYPEUSDT,TAOUSDT,ONDOUSDT,NEARUSDT"
)


@dataclass(frozen=True)
class SymbolTrain:
    symbol: str
    trades: int
    net_r: float
    profit_factor: float
    winrate: float
    max_drawdown_r: float
    unfilled_rate: float
    score: float
    error: str = ""


@dataclass(frozen=True)
class FoldRow:
    policy: str
    fold: int
    train_start: str
    train_end: str
    oos_start: str
    oos_end: str
    selected_symbols: str
    selected_count: int
    oos_trades: int
    oos_net_r: float
    oos_profit_factor: float
    oos_winrate: float
    oos_max_drawdown_r: float
    oos_unfilled_rate: float
    oos_gross_profit_r: float
    oos_gross_loss_r: float
    error: str = ""


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _parse_date(raw: str) -> datetime:
    return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _pf(gp: float, gl: float) -> float:
    if gl > 0:
        return gp / gl
    if gp > 0:
        return float("inf")
    return 0.0


def _pf_score(value: float) -> float:
    if math.isinf(value):
        return 3.0
    if math.isnan(value):
        return 0.0
    return min(max(0.0, value), 3.0)


def _score_train(m) -> float:
    if m.trades <= 0:
        return -1e9
    return (
        float(m.net_r) * 2.0
        + max(0.0, _pf_score(float(m.profit_factor)) - 1.0) * 7.0
        + max(0.0, float(m.winrate) - 0.45) * 4.0
        + min(float(m.trades), 30.0) * 0.05
        - float(m.max_drawdown_r) * 0.45
        - float(m.unfilled_rate) * 2.0
    )


def _write_csv(path: Path, rows: Iterable[object], fields: Sequence[str]) -> None:
    data = [r.__dict__ if hasattr(r, "__dict__") else dict(r) for r in rows]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(fields))
        w.writeheader()
        w.writerows(data)


def _train_symbol(
    *,
    symbol: str,
    train_days: int,
    train_end: str,
    offset_atr: float,
    validity_bars: int,
    cache_dir: Path,
) -> SymbolTrain:
    try:
        m, _ = _simulate_case(
            case="train",
            symbols=[symbol],
            days=int(train_days),
            end=train_end,
            offset_atr=float(offset_atr),
            validity_bars=int(validity_bars),
            maker_fee_bps=2.0,
            taker_fee_bps=10.0,
            exit_slippage_bps=5.0,
            cache_dir=cache_dir,
            max_positions=1,
        )
        return SymbolTrain(
            symbol=symbol,
            trades=int(m.trades),
            net_r=float(m.net_r),
            profit_factor=float(m.profit_factor),
            winrate=float(m.winrate),
            max_drawdown_r=float(m.max_drawdown_r),
            unfilled_rate=float(m.unfilled_rate),
            score=_score_train(m),
        )
    except Exception as exc:
        return SymbolTrain(symbol=symbol, trades=0, net_r=0.0, profit_factor=0.0, winrate=0.0, max_drawdown_r=0.0, unfilled_rate=1.0, score=-1e9, error=str(exc)[:240])


def _run_oos(
    *,
    symbols: Sequence[str],
    test_days: int,
    test_end: str,
    offset_atr: float,
    validity_bars: int,
    cache_dir: Path,
    max_positions: int,
) -> tuple[object | None, str]:
    if not symbols:
        return None, "no_symbols_selected"
    try:
        m, _ = _simulate_case(
            case="oos",
            symbols=symbols,
            days=int(test_days),
            end=test_end,
            offset_atr=float(offset_atr),
            validity_bars=int(validity_bars),
            maker_fee_bps=2.0,
            taker_fee_bps=10.0,
            exit_slippage_bps=5.0,
            cache_dir=cache_dir,
            max_positions=max_positions,
        )
        return m, ""
    except Exception as exc:
        return None, str(exc)[:240]


def _policy_id(*, train_days: int, test_days: int, top_n: int, min_trades: int, offset_atr: float, validity_bars: int) -> str:
    return f"train{train_days}_test{test_days}_top{top_n}_min{min_trades}_off{offset_atr:g}_valid{validity_bars}"


def _gate(rows: Sequence[FoldRow], *, min_folds: int) -> Dict[str, object]:
    valid = [r for r in rows if not r.error and r.selected_count > 0]
    gp = sum(float(r.oos_gross_profit_r) for r in valid)
    gl = sum(float(r.oos_gross_loss_r) for r in valid)
    net = sum(float(r.oos_net_r) for r in valid)
    trades = sum(int(r.oos_trades) for r in valid)
    folds_pos = sum(1 for r in valid if r.oos_net_r > 0 and r.oos_profit_factor >= 1.0 and r.oos_trades > 0)
    avg_unfilled = sum(float(r.oos_unfilled_rate) for r in valid) / max(1, len(valid))
    pf = _pf(gp, gl)
    selected_counts: Dict[str, int] = {}
    for r in valid:
        for s in str(r.selected_symbols or "").split(";"):
            if s:
                selected_counts[s] = selected_counts.get(s, 0) + 1
    reasons: List[str] = []
    if len(valid) < int(min_folds):
        reasons.append(f"valid_folds_{len(valid)}<{min_folds}")
    if trades < 20:
        reasons.append(f"trades_{trades}<20")
    if net <= 0:
        reasons.append("net_nonpositive")
    if pf < 1.20:
        reasons.append(f"pf_{pf:.3f}<1.20")
    if folds_pos < 3:
        reasons.append(f"folds_pos_{folds_pos}<3")
    if avg_unfilled >= 0.50:
        reasons.append(f"unfilled_{avg_unfilled:.3f}>=0.50")
    return {
        "passed": not reasons,
        "reasons": ";".join(reasons) if reasons else "dynamic_selector_pass",
        "valid_folds": len(valid),
        "folds_positive": folds_pos,
        "trades": trades,
        "net_r": round(net, 6),
        "profit_factor": round(pf, 6) if not math.isinf(pf) else "inf",
        "avg_unfilled_rate": round(avg_unfilled, 6),
        "selected_counts": selected_counts,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", default="2026-07-05")
    ap.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    ap.add_argument("--cache", default="data_cache")
    ap.add_argument("--tag-prefix", default="inplay_maker_dynsel_20260706")
    ap.add_argument("--train-days", default="90,120,180")
    ap.add_argument("--test-days", default="45")
    ap.add_argument("--top-ns", default="2,3,5")
    ap.add_argument("--min-train-trades", default="3,5,8")
    ap.add_argument("--offsets", default="0.25,0.4,0.55")
    ap.add_argument("--validities", default="12,24,36")
    ap.add_argument("--folds", type=int, default=4)
    args = ap.parse_args()

    cache_dir = ROOT / args.cache
    symbols = [s.strip().upper() for s in str(args.symbols).split(",") if s.strip()]
    train_days_grid = [int(x) for x in str(args.train_days).split(",") if x.strip()]
    test_days_grid = [int(x) for x in str(args.test_days).split(",") if x.strip()]
    top_ns = [int(x) for x in str(args.top_ns).split(",") if x.strip()]
    min_trades_grid = [int(x) for x in str(args.min_train_trades).split(",") if x.strip()]
    offsets = [float(x) for x in str(args.offsets).split(",") if x.strip()]
    validities = [int(x) for x in str(args.validities).split(",") if x.strip()]
    end_dt = _parse_date(args.end)
    out_dir = ROOT / "reports" / "research" / f"{args.tag_prefix}_{_stamp()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    train_rows: List[SymbolTrain] = []
    fold_rows: List[FoldRow] = []
    policy_rows: List[Dict[str, object]] = []
    best: Optional[Dict[str, object]] = None

    for train_days in train_days_grid:
        for test_days in test_days_grid:
            for top_n in top_ns:
                for min_trades in min_trades_grid:
                    for offset_atr in offsets:
                        for validity_bars in validities:
                            policy = _policy_id(
                                train_days=train_days,
                                test_days=test_days,
                                top_n=top_n,
                                min_trades=min_trades,
                                offset_atr=offset_atr,
                                validity_bars=validity_bars,
                            )
                            this_policy: List[FoldRow] = []
                            for fold in range(1, int(args.folds) + 1):
                                oos_end = end_dt - timedelta(days=(int(args.folds) - fold) * test_days)
                                oos_start = oos_end - timedelta(days=test_days)
                                train_end = oos_start
                                train_start = train_end - timedelta(days=train_days)
                                scored = [
                                    _train_symbol(
                                        symbol=sym,
                                        train_days=train_days,
                                        train_end=_fmt(train_end),
                                        offset_atr=offset_atr,
                                        validity_bars=validity_bars,
                                        cache_dir=cache_dir,
                                    )
                                    for sym in symbols
                                ]
                                train_rows.extend(scored)
                                eligible = [
                                    r for r in scored
                                    if not r.error and r.trades >= min_trades and r.net_r > 0 and r.profit_factor >= 1.0
                                ]
                                eligible.sort(key=lambda r: r.score, reverse=True)
                                selected = [r.symbol for r in eligible[:top_n]]
                                oos, err = _run_oos(
                                    symbols=selected,
                                    test_days=test_days,
                                    test_end=_fmt(oos_end),
                                    offset_atr=offset_atr,
                                    validity_bars=validity_bars,
                                    cache_dir=cache_dir,
                                    max_positions=min(3, max(1, top_n)),
                                )
                                if oos is None:
                                    row = FoldRow(policy, fold, _fmt(train_start), _fmt(train_end), _fmt(oos_start), _fmt(oos_end), ";".join(selected), len(selected), 0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, err)
                                else:
                                    row = FoldRow(policy, fold, _fmt(train_start), _fmt(train_end), _fmt(oos_start), _fmt(oos_end), ";".join(selected), len(selected), int(oos.trades), float(oos.net_r), float(oos.profit_factor), float(oos.winrate), float(oos.max_drawdown_r), float(oos.unfilled_rate), float(oos.gross_profit_r), float(oos.gross_loss_r), "")
                                fold_rows.append(row)
                                this_policy.append(row)
                            verdict = _gate(this_policy, min_folds=int(args.folds))
                            rec = {
                                "policy": policy,
                                "train_days": train_days,
                                "test_days": test_days,
                                "top_n": top_n,
                                "min_train_trades": min_trades,
                                "offset_atr": offset_atr,
                                "validity_bars": validity_bars,
                                **{f"gate_{k}": v for k, v in verdict.items() if k != "selected_counts"},
                                "selected_counts": json.dumps(verdict.get("selected_counts", {}), sort_keys=True),
                            }
                            policy_rows.append(rec)
                            score = (1_000_000 if verdict["passed"] else 0) + float(verdict["net_r"]) * 100 + float(verdict["trades"]) + float(verdict["folds_positive"]) * 20
                            if best is None or score > float(best["score"]):
                                best = {"score": score, **rec, "verdict": verdict}
                            print(
                                f"{policy} trades={verdict['trades']} netR={verdict['net_r']} "
                                f"pf={verdict['profit_factor']} folds={verdict['folds_positive']}/{args.folds} "
                                f"gate={'PASS' if verdict['passed'] else 'FAIL'} {verdict['reasons']}",
                                flush=True,
                            )

    _write_csv(out_dir / "train_symbol_rows.csv", train_rows, list(SymbolTrain.__dataclass_fields__.keys()))
    _write_csv(out_dir / "fold_rows.csv", fold_rows, list(FoldRow.__dataclass_fields__.keys()))
    if policy_rows:
        fields = sorted({k for r in policy_rows for k in r})
        with (out_dir / "policy_rows.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(policy_rows)
    verdict = best.get("verdict") if best else {"passed": False, "reasons": "no_policy_rows"}
    (out_dir / "verdict.json").write_text(json.dumps({"best": best, "verdict": verdict}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "summary.md").write_text(
        "\n".join(
            [
                "# Inplay Maker Dynamic Selector 2026-07-06",
                "",
                f"- output: `{out_dir}`",
                f"- verdict: `{'PASS' if verdict.get('passed') else 'FAIL'}`",
                f"- reasons: `{verdict.get('reasons')}`",
                f"- best: `{best}`",
                "",
                "Causal design: train symbols on the prior window, select top-N, test only the future window.",
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
