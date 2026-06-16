#!/usr/bin/env python3
"""Run a bounded pair-stat-arb matrix and write a ranked report.

This is an R&D helper for the market-neutral sleeve: it reuses the existing
honest walk-forward pair arb simulator and tests several pair/config pockets.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_pair_arb import run_walkforward
from strategies.pair_stat_arb_v1 import PairConfig


def _csv_floats(raw: str) -> list[float]:
    return [float(x.strip()) for x in str(raw or "").replace(";", ",").split(",") if x.strip()]


def _csv_ints(raw: str) -> list[int]:
    return [int(float(x.strip())) for x in str(raw or "").replace(";", ",").split(",") if x.strip()]


def _pairs(raw: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for token in str(raw or "").replace(";", ",").split(","):
        token = token.strip().upper()
        if not token:
            continue
        sep = "/" if "/" in token else ":"
        if sep not in token:
            continue
        a, b = [x.strip().upper() for x in token.split(sep, 1)]
        if a and b and a != b:
            out.append((a, b))
    return out


def _metric(result: dict[str, Any], key: str, default: float = 0.0) -> float:
    agg = result.get("oos_aggregate") or {}
    for source in (agg, result):
        value = source.get(key)
        try:
            v = float(value)
        except Exception:
            continue
        if math.isfinite(v):
            return v
    return default


def _score(row: dict[str, Any]) -> float:
    pf = float(row.get("profit_factor") or 0.0)
    ret = float(row.get("return_pct") or 0.0)
    dd = abs(float(row.get("max_drawdown") or 0.0))
    trades = min(float(row.get("trades") or 0.0), 120.0)
    return ret + 4.0 * pf + 0.05 * trades - 1.5 * dd


def _md(rows: list[dict[str, Any]], generated_at: str) -> str:
    lines = [
        "# Pair Arb Matrix",
        "",
        f"- generated_at_utc: `{generated_at}`",
        f"- rows: `{len(rows)}`",
        "",
        "| rank | pair | lookback | z in/out/stop | ret% | PF | WR | DD% | trades | verdict |",
        "|---:|---|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    for i, row in enumerate(rows[:30], 1):
        lines.append(
            "| {rank} | `{pair}` | {lookback} | {entry_z}/{exit_z}/{stop_z} | "
            "{return_pct:.2f} | {profit_factor:.2f} | {win_rate:.2f} | "
            "{max_drawdown:.2f} | {trades} | {verdict} |".format(rank=i, **row)
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Bounded pair stat-arb matrix")
    ap.add_argument("--pairs", default="ETHUSDT/BTCUSDT,SOLUSDT/ETHUSDT,LINKUSDT/ETHUSDT,DOGEUSDT/BTCUSDT,ADAUSDT/ETHUSDT")
    ap.add_argument("--lookbacks", default="96,168,336")
    ap.add_argument("--entry-z", default="1.6,2.0,2.4")
    ap.add_argument("--exit-z", default="0.3,0.5")
    ap.add_argument("--stop-z", default="3.0,3.5")
    ap.add_argument("--fee-bps", type=float, default=6.0)
    ap.add_argument("--funding-bps-per-8h", type=float, default=0.0)
    ap.add_argument("--oos-days", type=int, default=30)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    combos = list(
        itertools.product(
            _pairs(args.pairs),
            _csv_ints(args.lookbacks),
            _csv_floats(args.entry_z),
            _csv_floats(args.exit_z),
            _csv_floats(args.stop_z),
        )
    )
    if args.limit > 0:
        combos = combos[: int(args.limit)]

    generated_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for idx, ((a, b), lookback, entry_z, exit_z, stop_z) in enumerate(combos, 1):
        cfg = PairConfig(lookback=int(lookback), entry_z=float(entry_z), exit_z=float(exit_z), stop_z=float(stop_z))
        result = run_walkforward(
            a,
            b,
            cfg,
            fee_bps=float(args.fee_bps),
            oos_days=int(args.oos_days),
            funding_bps_per_8h=float(args.funding_bps_per_8h),
        )
        if "error" in result:
            row = {
                "pair": f"{a}/{b}",
                "lookback": int(lookback),
                "entry_z": float(entry_z),
                "exit_z": float(exit_z),
                "stop_z": float(stop_z),
                "return_pct": 0.0,
                "profit_factor": 0.0,
                "win_rate": 0.0,
                "max_drawdown": 0.0,
                "trades": 0,
                "verdict": str(result.get("error")),
                "score": -1_000_000.0,
            }
        else:
            trades = int(result.get("total_oos_trades") or _metric(result, "trades", 0.0))
            row = {
                "pair": str(result.get("pair") or f"{a}/{b}"),
                "lookback": int(lookback),
                "entry_z": float(entry_z),
                "exit_z": float(exit_z),
                "stop_z": float(stop_z),
                "return_pct": _metric(result, "return_pct"),
                "profit_factor": _metric(result, "profit_factor"),
                "win_rate": _metric(result, "win_rate"),
                "max_drawdown": _metric(result, "max_drawdown"),
                "trades": trades,
                "verdict": "PASS" if trades >= 20 and _metric(result, "profit_factor") > 1.10 and _metric(result, "return_pct") > 0 else "FAIL",
                "raw": result,
            }
            row["score"] = _score(row)
        rows.append(row)
        print(f"[{idx}/{len(combos)}] {row['pair']} lb={lookback} z={entry_z}/{exit_z}/{stop_z} {row['verdict']} ret={row['return_pct']:.2f} pf={row['profit_factor']:.2f}", flush=True)

    rows.sort(key=lambda r: float(r.get("score") or -1_000_000.0), reverse=True)
    out_dir = ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"PAIR_ARB_MATRIX_{stamp}.json"
    md_path = out_dir / f"PAIR_ARB_MATRIX_{stamp}.md"
    payload = {
        "generated_at_utc": generated_at,
        "args": vars(args),
        "rows": rows,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_md(rows, generated_at), encoding="utf-8")
    print(f"json={json_path}")
    print(f"md={md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
