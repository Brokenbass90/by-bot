#!/usr/bin/env python3
"""Build a comparable scoreboard for strategy/backtest runs.

The goal is to stop mixing numbers from different runs without labels. Every
row carries the run path, period, universe, strategy list, costs already baked
into the run, monthly red/green counts, and the worst red streak.

Usage:
    python3 scripts/build_portfolio_scoreboard.py \
      backtest_runs/autoresearch_.../ranked_results.csv \
      --top-ranked 3 \
      --out reports/portfolio_scoreboard_latest.md \
      --json-out runtime/portfolio_scoreboard_latest.json

Inputs can be:
  - a portfolio run directory with summary.csv and trades.csv;
  - a ranked_results.csv from autoresearch; the script follows run_dir values.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8", errors="ignore") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _month_from_ts(raw: Any) -> str | None:
    ts = _safe_float(raw, math.nan)
    if math.isnan(ts) or ts <= 0:
        return None
    if ts > 10_000_000_000:
        ts = ts / 1000.0
    try:
        return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m")
    except Exception:
        return None


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except Exception:
        return str(path)


@dataclass
class ScoreRow:
    tag: str
    run_dir: str
    days: int
    end_date_utc: str
    symbols: str
    strategies: str
    trades: int
    net_pnl: float
    profit_factor: float
    winrate: float
    max_drawdown: float
    positive_months: int
    negative_months: int
    flat_months: int
    max_negative_streak: int
    worst_month_pnl: float
    best_month_pnl: float
    source: str


def monthly_stats(trades_path: Path) -> dict[str, Any]:
    rows = _read_csv_rows(trades_path)
    by_month: dict[str, float] = defaultdict(float)
    for row in rows:
        month = _month_from_ts(row.get("exit_ts") or row.get("ts") or row.get("close_ts"))
        if not month:
            continue
        by_month[month] += _safe_float(row.get("pnl") or row.get("pnl_usd"))

    months = sorted(by_month)
    vals = [by_month[m] for m in months]
    pos = sum(1 for v in vals if v > 1e-12)
    neg = sum(1 for v in vals if v < -1e-12)
    flat = len(vals) - pos - neg
    streak = 0
    max_streak = 0
    for v in vals:
        if v < -1e-12:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return {
        "months": months,
        "monthly_pnl": {m: round(by_month[m], 8) for m in months},
        "positive_months": pos,
        "negative_months": neg,
        "flat_months": flat,
        "max_negative_streak": max_streak,
        "worst_month_pnl": min(vals) if vals else 0.0,
        "best_month_pnl": max(vals) if vals else 0.0,
    }


def score_run(run_dir: Path, *, source: str) -> ScoreRow | None:
    summary_rows = _read_csv_rows(run_dir / "summary.csv")
    if not summary_rows:
        return None
    summary = summary_rows[0]
    months = monthly_stats(run_dir / "trades.csv")
    return ScoreRow(
        tag=str(summary.get("tag") or run_dir.name),
        run_dir=_rel(run_dir),
        days=_safe_int(summary.get("days")),
        end_date_utc=str(summary.get("end_date_utc") or ""),
        symbols=str(summary.get("symbols") or ""),
        strategies=str(summary.get("strategies") or ""),
        trades=_safe_int(summary.get("trades")),
        net_pnl=round(_safe_float(summary.get("net_pnl")), 8),
        profit_factor=round(_safe_float(summary.get("profit_factor")), 6),
        winrate=round(_safe_float(summary.get("winrate")), 6),
        max_drawdown=round(_safe_float(summary.get("max_drawdown")), 8),
        positive_months=int(months["positive_months"]),
        negative_months=int(months["negative_months"]),
        flat_months=int(months["flat_months"]),
        max_negative_streak=int(months["max_negative_streak"]),
        worst_month_pnl=round(float(months["worst_month_pnl"]), 8),
        best_month_pnl=round(float(months["best_month_pnl"]), 8),
        source=source,
    )


def expand_input(path: Path, *, top_ranked: int) -> list[tuple[Path, str]]:
    path = path.expanduser()
    if not path.is_absolute():
        path = ROOT / path
    if path.is_dir():
        return [(path, _rel(path))]
    if path.name == "ranked_results.csv":
        rows = _read_csv_rows(path)
        out: list[tuple[Path, str]] = []
        for row in rows[: max(1, top_ranked)]:
            run_dir = str(row.get("run_dir") or "").strip()
            if not run_dir:
                continue
            rd = Path(run_dir)
            if not rd.is_absolute():
                rd = ROOT / rd
            out.append((rd, _rel(path)))
        return out
    return []


def render_markdown(rows: list[ScoreRow]) -> str:
    generated = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Portfolio Scoreboard",
        "",
        f"Generated: `{generated}`",
        "",
        "This table is for comparable strategy/backtest numbers. Do not quote a P&L/PF number without the row's run path, period, universe, and source.",
        "",
        "| Tag | Days | Strategies | Symbols | Trades | Net | PF | WR | Max DD | Green M | Red M | Red Streak | Worst M | Source |",
        "|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        symbols = r.symbols.replace(";", ",")
        if len(symbols) > 48:
            symbols = symbols[:45] + "..."
        lines.append(
            "| "
            f"`{r.tag}` | {r.days} | `{r.strategies}` | {symbols or '-'} | "
            f"{r.trades} | {r.net_pnl:.4f} | {r.profit_factor:.3f} | {r.winrate:.3f} | "
            f"{r.max_drawdown:.4f} | {r.positive_months} | {r.negative_months} | "
            f"{r.max_negative_streak} | {r.worst_month_pnl:.4f} | `{r.source}` |"
        )
    lines.extend(
        [
            "",
            "## Rules",
            "",
            "- A strategy is not portfolio-ready only because PF > 1.0; red months, red streak, drawdown, and additivity matter.",
            "- Ranked/autoresearch rows are candidate evidence, not live approval.",
            "- Funding, fees, slippage, universe, and IS/OOS split must be stated before comparing runs.",
            "- Portfolio selection should optimize return, drawdown, red months, correlation, and slot collision together.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Run dirs or ranked_results.csv files")
    parser.add_argument("--top-ranked", type=int, default=1, help="Rows to follow from each ranked_results.csv")
    parser.add_argument("--out", default="reports/portfolio_scoreboard_latest.md", help="Markdown output")
    parser.add_argument("--json-out", default="runtime/portfolio_scoreboard_latest.json", help="JSON output")
    args = parser.parse_args()

    run_sources: list[tuple[Path, str]] = []
    for raw in args.paths:
        run_sources.extend(expand_input(Path(raw), top_ranked=args.top_ranked))

    rows: list[ScoreRow] = []
    seen: set[str] = set()
    for run_dir, source in run_sources:
        key = str(run_dir.resolve())
        if key in seen:
            continue
        seen.add(key)
        row = score_run(run_dir, source=source)
        if row:
            rows.append(row)

    rows.sort(key=lambda r: (r.negative_months, r.max_negative_streak, -r.net_pnl, -r.profit_factor))

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(rows), encoding="utf-8")

    js_out = Path(args.json_out)
    if not js_out.is_absolute():
        js_out = ROOT / js_out
    js_out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": [asdict(r) for r in rows],
        "inputs": [str(x) for x in args.paths],
    }
    js_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"rows={len(rows)} markdown={_rel(out)} json={_rel(js_out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
