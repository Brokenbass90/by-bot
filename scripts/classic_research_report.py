#!/usr/bin/env python3
"""Build monthly + stack reports for classic crypto autoresearch runs.

This is deliberately read-only: it consumes completed backtest run directories
or an autoresearch ranked_results.csv and writes a compact Markdown/JSON report.
It answers two operator questions:

1. Which classic strategy variants survive month-by-month?
2. Does a simple control-plane slot cap help or choke the trade stream?
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.monthly_analysis import format_table, monthly_breakdown, verdict
from backtest.stack_comparison import compare


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return default
    return out if math.isfinite(out) else default


def _safe_int_ms(value: Any) -> int:
    raw = _safe_float(value, 0.0)
    if raw <= 0:
        return 0
    if raw < 10_000_000_000:
        raw *= 1000.0
    return int(raw)


def _candidate_rows(path: Path, top: int) -> list[dict[str, Any]]:
    """Return rows with run_dir and ranking metadata."""
    if (path / "ranked_results.csv").exists():
        rows = _read_csv(path / "ranked_results.csv")
        out: list[dict[str, Any]] = []
        for row in rows[: max(1, top)]:
            run_dir = Path(str(row.get("run_dir", "")))
            if not run_dir.is_absolute():
                run_dir = ROOT / run_dir
            out.append({"run_dir": run_dir, "rank_row": row})
        return out

    if (path / "summary.csv").exists() and (path / "trades.csv").exists():
        return [{"run_dir": path, "rank_row": {}}]

    raise FileNotFoundError(f"{path} is neither an autoresearch dir nor a run dir")


def _load_summary(run_dir: Path) -> dict[str, str]:
    rows = _read_csv(run_dir / "summary.csv")
    return rows[0] if rows else {}


def _load_trades(run_dir: Path) -> list[dict[str, Any]]:
    rows = _read_csv(run_dir / "trades.csv")
    trades: list[dict[str, Any]] = []
    for row in rows:
        exit_ts = _safe_int_ms(row.get("exit_ts") or row.get("exit_ts_ms"))
        entry_ts = _safe_int_ms(row.get("entry_ts") or row.get("entry_ts_ms"))
        pnl = _safe_float(row.get("pnl") or row.get("net_pnl") or row.get("R"), 0.0)
        if exit_ts <= 0:
            continue
        trades.append(
            {
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "exit_ts_ms": exit_ts,
                "pnl": pnl,
                # stack_comparison calls this R. For portfolio CSVs we use PnL
                # units; relative help/hurt is still valid for the same stream.
                "R": _safe_float(row.get("R"), pnl),
                "regime": row.get("regime", ""),
                "strategy": row.get("strategy", ""),
                "symbol": row.get("symbol", ""),
                "side": row.get("side", ""),
            }
        )
    return trades


def _compact_summary(summary: dict[str, str]) -> dict[str, Any]:
    keys = [
        "tag",
        "symbols",
        "strategies",
        "trades",
        "net_pnl",
        "profit_factor",
        "winrate",
        "max_drawdown",
        "ending_equity",
    ]
    return {k: summary.get(k, "") for k in keys if k in summary}


def build_report(
    path: Path,
    *,
    top: int,
    max_concurrent: int | None,
    bear_months: set[str],
) -> dict[str, Any]:
    candidates = []
    for item in _candidate_rows(path, top=top):
        run_dir: Path = item["run_dir"]
        if not (run_dir / "summary.csv").exists() or not (run_dir / "trades.csv").exists():
            continue
        summary = _load_summary(run_dir)
        trades = _load_trades(run_dir)
        monthly = monthly_breakdown(trades, bear_months=bear_months)
        monthly_verdict = verdict(monthly)
        stack = compare(trades, max_concurrent=max_concurrent) if trades else compare([])
        candidates.append(
            {
                "run_dir": str(run_dir),
                "rank_row": item.get("rank_row") or {},
                "summary": _compact_summary(summary),
                "monthly": monthly,
                "monthly_verdict": monthly_verdict,
                "stack_comparison": stack,
            }
        )
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(path),
        "top": top,
        "max_concurrent": max_concurrent,
        "bear_months": sorted(bear_months),
        "candidates": candidates,
    }


def _md(report: dict[str, Any]) -> str:
    lines = [
        "# Classic Research Report",
        "",
        f"- generated_at_utc: `{report['generated_at_utc']}`",
        f"- source: `{report['source']}`",
        f"- candidates: `{len(report['candidates'])}`",
        f"- bear_months: `{', '.join(report['bear_months']) or '-'}`",
        f"- max_concurrent_stack_check: `{report['max_concurrent'] or '-'}`",
        "",
    ]
    for idx, c in enumerate(report["candidates"], start=1):
        summary = c["summary"]
        v = c["monthly_verdict"]
        stack = c["stack_comparison"]
        rank = c.get("rank_row") or {}
        lines.extend(
            [
                f"## #{idx} {summary.get('tag') or Path(c['run_dir']).name}",
                "",
                f"- run_dir: `{c['run_dir']}`",
                f"- strategies: `{summary.get('strategies', '')}`",
                f"- symbols: `{summary.get('symbols', '')}`",
                (
                    f"- summary: trades `{summary.get('trades', '')}`, "
                    f"net `{summary.get('net_pnl', '')}`, PF `{summary.get('profit_factor', '')}`, "
                    f"WR `{summary.get('winrate', '')}`, DD `{summary.get('max_drawdown', '')}`"
                ),
                f"- autoresearch_passed: `{rank.get('passed', '')}` fail_reasons: `{rank.get('fail_reasons', '')}`",
                f"- monthly_verdict: `{v['verdict']}` reason: `{v['reason']}`",
                (
                    f"- stack: `{stack['verdict']}` bare={stack['bare']} "
                    f"stacked={stack['stacked']} dropped={stack['dropped']}"
                ),
                "",
                "```text",
                format_table(c["monthly"]),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Classic autoresearch monthly/stack report")
    ap.add_argument("path", help="Autoresearch directory or portfolio run directory")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--max-concurrent", type=int, default=0)
    ap.add_argument("--bear-months", default="")
    ap.add_argument("--out-md", default="")
    ap.add_argument("--out-json", default="")
    args = ap.parse_args()

    source = Path(args.path)
    if not source.is_absolute():
        source = (ROOT / source).resolve()
    bear_months = {x.strip() for x in args.bear_months.split(",") if x.strip()}
    max_concurrent = int(args.max_concurrent) if int(args.max_concurrent or 0) > 0 else None
    report = build_report(source, top=args.top, max_concurrent=max_concurrent, bear_months=bear_months)

    out_md = Path(args.out_md) if args.out_md else ROOT / "reports" / f"CLASSIC_RESEARCH_{source.name}.md"
    out_json = Path(args.out_json) if args.out_json else ROOT / "reports" / f"CLASSIC_RESEARCH_{source.name}.json"
    if not out_md.is_absolute():
        out_md = ROOT / out_md
    if not out_json.is_absolute():
        out_json = ROOT / out_json
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    out_md.write_text(_md(report), encoding="utf-8")
    print(f"md={out_md}")
    print(f"json={out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
