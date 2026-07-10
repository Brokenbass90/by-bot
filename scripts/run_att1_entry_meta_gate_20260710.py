#!/usr/bin/env python3
"""Causal ATT1 entry-quality gate over an already frozen backtest cohort.

This runner deliberately does not rerun or tune ATT1.  It reads the four
chronological ``base/all_regimes`` folds produced by
``run_att1_exit_regime_ab_20260710.py``, extracts the entry-time slope and RSI
printed by the strategy, selects one pre-declared filter on folds 1-3, and
checks it once on fold 4.

Research-only: no config, server, risk, or order changes are made here.
The available trade log does not yet contain R2/pivots/touch distance, so a
PASS is only permission to instrument and rerun a richer entry-card gate.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
FEATURE_RE = re.compile(r"slope=(?P<slope>-?[0-9.]+)%/d\s+rsi=(?P<rsi>[0-9.]+)")


@dataclass(frozen=True)
class EntryTrade:
    fold: int
    symbol: str
    entry_ts: int
    pnl: float
    slope_pct_day: float
    rsi: float
    reason: str


def _base(_: EntryTrade) -> bool:
    return True


# Frozen before reading the new cohort.  Keep this list intentionally small;
# it tests causal entry ideas rather than mining a large threshold grid.
FILTERS: dict[str, Callable[[EntryTrade], bool]] = {
    "base": _base,
    "descending_only": lambda t: t.slope_pct_day <= -0.05,
    "moderate_descending": lambda t: -3.25 <= t.slope_pct_day <= -0.25,
    "rsi_50_70": lambda t: 50.0 <= t.rsi <= 70.0,
    "descending_rsi_50_70": lambda t: t.slope_pct_day <= -0.05 and 50.0 <= t.rsi <= 70.0,
    "moderate_descending_rsi_50_70": lambda t: -3.25 <= t.slope_pct_day <= -0.25 and 50.0 <= t.rsi <= 70.0,
}


def _f(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _pf(values: list[float]) -> float:
    gross_profit = sum(v for v in values if v > 0)
    gross_loss = -sum(v for v in values if v < 0)
    if gross_loss <= 1e-12:
        return math.inf if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def _max_dd(values: list[float]) -> float:
    equity = peak = worst = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        worst = max(worst, peak - equity)
    return worst


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _load_trades(source: Path) -> tuple[list[EntryTrade], list[str]]:
    rows = _read_csv(source / "folds.csv")
    selected = [r for r in rows if r.get("variant") == "base" and r.get("regime_mode") == "all_regimes"]
    trades: list[EntryTrade] = []
    skipped: list[str] = []
    for fold_row in selected:
        fold = int(float(fold_row["fold"]))
        trade_path = Path(fold_row["out_dir"]) / "trades.csv"
        if not trade_path.exists():
            skipped.append(f"missing:{trade_path}")
            continue
        for row in _read_csv(trade_path):
            reason = str(row.get("reason") or "")
            match = FEATURE_RE.search(reason)
            if match is None:
                skipped.append(f"unparsed:f{fold}:{row.get('symbol','?')}:{reason}")
                continue
            trades.append(
                EntryTrade(
                    fold=fold,
                    symbol=str(row.get("symbol") or ""),
                    entry_ts=int(float(row.get("entry_ts") or 0)),
                    pnl=_f(row.get("pnl")),
                    slope_pct_day=float(match.group("slope")),
                    rsi=float(match.group("rsi")),
                    reason=reason,
                )
            )
    return trades, skipped


def _metrics(trades: list[EntryTrade]) -> dict[str, object]:
    ordered = sorted(trades, key=lambda t: (t.entry_ts, t.symbol))
    values = [t.pnl for t in ordered]
    positive_symbols = 0
    symbols = sorted({t.symbol for t in ordered})
    for symbol in symbols:
        if sum(t.pnl for t in ordered if t.symbol == symbol) > 0:
            positive_symbols += 1
    return {
        "trades": len(values),
        "net_pnl": round(sum(values), 6),
        "profit_factor": _pf(values),
        "winrate": round(sum(1 for v in values if v > 0) / len(values), 6) if values else 0.0,
        "max_drawdown_pnl": round(_max_dd(values), 6),
        "symbols": len(symbols),
        "positive_symbols": positive_symbols,
    }


def _safe_pf(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="reports/research/att1_entry_baseline_20260710")
    parser.add_argument("--out", default="reports/research/att1_entry_meta_gate_20260710")
    args = parser.parse_args()

    source = Path(args.source)
    out = Path(args.out)
    if not source.is_absolute():
        source = ROOT / source
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)

    trades, skipped = _load_trades(source)
    if not trades:
        raise SystemExit(f"no parseable base/all_regimes trades in {source}")

    fold_rows: list[dict[str, object]] = []
    aggregate_rows: list[dict[str, object]] = []
    for name, predicate in FILTERS.items():
        kept = [t for t in trades if predicate(t)]
        train = [t for t in kept if t.fold <= 3]
        holdout = [t for t in kept if t.fold == 4]
        train_m = _metrics(train)
        holdout_m = _metrics(holdout)
        all_m = _metrics(kept)
        positive_train_folds = 0
        positive_all_folds = 0
        for fold in range(1, 5):
            subset = [t for t in kept if t.fold == fold]
            fm = _metrics(subset)
            fold_rows.append({"filter": name, "fold": fold, **fm})
            positive_all_folds += int(float(fm["net_pnl"]) > 0)
            if fold <= 3:
                positive_train_folds += int(float(fm["net_pnl"]) > 0)
        aggregate_rows.append(
            {
                "filter": name,
                "train_trades": train_m["trades"],
                "train_net_pnl": train_m["net_pnl"],
                "train_pf": train_m["profit_factor"],
                "train_winrate": train_m["winrate"],
                "train_positive_folds": positive_train_folds,
                "holdout_trades": holdout_m["trades"],
                "holdout_net_pnl": holdout_m["net_pnl"],
                "holdout_pf": holdout_m["profit_factor"],
                "holdout_winrate": holdout_m["winrate"],
                "all_trades": all_m["trades"],
                "all_net_pnl": all_m["net_pnl"],
                "all_pf": all_m["profit_factor"],
                "all_winrate": all_m["winrate"],
                "all_positive_folds": positive_all_folds,
                "all_max_drawdown_pnl": all_m["max_drawdown_pnl"],
                "retention": round(len(kept) / len(trades), 6),
            }
        )

    base = next(r for r in aggregate_rows if r["filter"] == "base")
    candidates = [
        r
        for r in aggregate_rows
        if r["filter"] != "base"
        and int(r["train_trades"]) >= 80
        and int(r["train_positive_folds"]) >= 2
        and _safe_pf(r["train_pf"]) >= max(1.10, _safe_pf(base["train_pf"]))
    ]
    selected = max(candidates, key=lambda r: (_safe_pf(r["train_pf"]), float(r["train_net_pnl"])), default=None)
    holdout_pass = bool(
        selected
        and int(selected["holdout_trades"]) >= 20
        and float(selected["holdout_net_pnl"]) > 0
        and _safe_pf(selected["holdout_pf"]) >= 1.15
        and int(selected["all_positive_folds"]) >= 3
        and _safe_pf(selected["all_pf"]) >= _safe_pf(base["all_pf"])
    )

    with (out / "folds.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fold_rows[0]))
        writer.writeheader()
        writer.writerows(fold_rows)
    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(aggregate_rows[0]))
        writer.writeheader()
        writer.writerows(aggregate_rows)

    verdict = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "source": str(source),
        "parsed_trades": len(trades),
        "skipped_rows": len(skipped),
        "selection_folds": [1, 2, 3],
        "untouched_holdout_fold": 4,
        "selected": selected,
        "holdout_pass": holdout_pass,
        "promotion": False,
        "next_if_pass": "instrument R2/pivots/touch-distance/regime cards, then rerun; never direct live promotion",
        "rows": aggregate_rows,
    }
    (out / "verdict.json").write_text(json.dumps(verdict, indent=2, allow_nan=True), encoding="utf-8")
    if skipped:
        (out / "skipped.txt").write_text("\n".join(skipped) + "\n", encoding="utf-8")

    lines = [
        "# ATT1 Entry Meta-Filter Gate",
        "",
        "Research-only. Filters were selected on folds 1-3 and checked once on fold 4.",
        "This cohort exposes only slope and RSI; it is not sufficient for live promotion.",
        "",
        f"- parsed trades: `{len(trades)}`; skipped: `{len(skipped)}`",
        f"- selected on train: `{selected['filter'] if selected else 'NONE'}`",
        f"- untouched holdout: `{'PASS_DIAGNOSTIC' if holdout_pass else 'FAIL'}`",
        "",
        "| filter | train N | train PF | holdout N | holdout PF | all WR | all PF | all folds+ |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in aggregate_rows:
        lines.append(
            f"| {row['filter']} | {row['train_trades']} | {_safe_pf(row['train_pf']):.3f} | "
            f"{row['holdout_trades']} | {_safe_pf(row['holdout_pf']):.3f} | "
            f"{float(row['all_winrate']):.3f} | {_safe_pf(row['all_pf']):.3f} | {row['all_positive_folds']}/4 |"
        )
    lines.extend(["", "Even PASS_DIAGNOSTIC only authorizes richer entry-card instrumentation and a new causal run."])
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "selected": selected, "holdout_pass": holdout_pass}, indent=2, allow_nan=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
