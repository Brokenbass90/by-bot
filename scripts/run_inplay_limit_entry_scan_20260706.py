#!/usr/bin/env python3
"""Scan true pending-limit entry settings for the inplay breakout candidate.

Research-only. This is the bridge between the optimistic maker-cost repair and
the strict promotion gate: it checks whether limit orders would actually fill
often enough under portfolio_engine's pending limit fill/expiry model.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_inplay_breakout_retest_strict_gate_20260706 import (  # noqa: E402
    INPLAY_R061_ENV,
    SYMBOLS,
)


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _read_summary(run_dir: Path) -> Dict[str, str]:
    with (run_dir / "summary.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return dict(rows[0]) if rows else {}


def _latest_run_dir(tag: str) -> Path:
    matches = sorted(ROOT.glob(f"backtest_runs/portfolio_*_{tag}"), key=lambda p: p.stat().st_mtime)
    if not matches:
        raise RuntimeError(f"missing run dir for tag={tag}")
    return matches[-1]


def _to_float(raw: object) -> float:
    s = str(raw or "").strip().lower()
    if s == "inf":
        return float("inf")
    if s in {"", "nan"}:
        return 0.0
    return float(s)


def _grid(offsets: str, validities: str) -> Iterable[tuple[str, str]]:
    offs = [x.strip() for x in offsets.split(",") if x.strip()]
    vals = [x.strip() for x in validities.split(",") if x.strip()]
    return itertools.product(offs, vals)


def _run_case(
    *,
    py: str,
    tag: str,
    env_extra: Dict[str, str],
    fee_bps: float,
    slippage_bps: float,
    log_dir: Path,
) -> Dict[str, object]:
    env = os.environ.copy()
    env.update(INPLAY_R061_ENV)
    env.update(env_extra)
    env["PYTHONPATH"] = str(ROOT)

    cmd = [
        py,
        "backtest/run_portfolio.py",
        "--cache",
        "data_cache",
        "--symbols",
        ",".join(SYMBOLS),
        "--strategies",
        "inplay_breakout",
        "--days",
        "360",
        "--end",
        "2026-07-05",
        "--tag",
        tag,
        "--starting_equity",
        "100",
        "--risk_pct",
        "0.005",
        "--leverage",
        "1",
        "--max_positions",
        "3",
        "--fee_bps",
        f"{fee_bps:.4f}",
        "--slippage_bps",
        f"{slippage_bps:.4f}",
        "--entry-on-next-open",
    ]
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{tag}.log"
    with log_path.open("w", encoding="utf-8", errors="ignore") as f:
        f.write("cmd=" + " ".join(cmd) + "\n")
        f.write("env_extra=" + json.dumps(env_extra, sort_keys=True) + "\n\n")
        subprocess.run(cmd, cwd=ROOT, env=env, check=True, stdout=f, stderr=subprocess.STDOUT)

    run_dir = _latest_run_dir(tag)
    s = _read_summary(run_dir)
    return {
        "tag": tag,
        "run_dir": str(run_dir),
        "trades": int(_to_float(s.get("trades"))),
        "net_pnl": _to_float(s.get("net_pnl")),
        "profit_factor": _to_float(s.get("profit_factor")),
        "winrate": _to_float(s.get("winrate")),
        "max_drawdown": abs(_to_float(s.get("max_drawdown"))),
        "negative_months": int(_to_float(s.get("negative_months"))),
        "worst_month_pnl": _to_float(s.get("worst_month_pnl")),
    }


def _score(row: Dict[str, object]) -> float:
    trades = int(row.get("base_trades", 0) or 0)
    net = float(row.get("stress_net_pnl", 0.0) or 0.0)
    pf = float(row.get("stress_profit_factor", 0.0) or 0.0)
    dd = float(row.get("stress_max_drawdown", 0.0) or 0.0)
    if trades < 60 or net <= 0 or pf < 1.10:
        return -1e9 + trades
    return net * 3.0 + pf * 2.0 + min(trades, 180) * 0.03 - dd * 1.5


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--py", default=".venv/bin/python3")
    ap.add_argument("--tag-prefix", default="inplay_br_limit_scan_20260706")
    ap.add_argument("--offsets", default="0,0.05,0.10,0.20,0.35")
    ap.add_argument("--validities", default="6,12,24,48")
    ap.add_argument("--base-fee-bps", type=float, default=1.0)
    ap.add_argument("--base-slippage-bps", type=float, default=0.0)
    ap.add_argument("--stress-fee-bps", type=float, default=2.0)
    ap.add_argument("--stress-slippage-bps", type=float, default=0.5)
    args = ap.parse_args()

    py = args.py
    if py.startswith(".venv/") and not (ROOT / py).exists():
        py = sys.executable

    stamp = _stamp()
    out_dir = ROOT / "reports" / "research" / f"{args.tag_prefix}_{stamp}"
    log_dir = out_dir / "subprocess_logs"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, object]] = []
    for idx, (offset, validity) in enumerate(_grid(args.offsets, args.validities), start=1):
        env_extra = {
            "BREAKOUT_USE_LIMIT_ENTRY": "1",
            "BREAKOUT_LIMIT_ENTRY_OFFSET_ATR": str(offset),
            "BREAKOUT_LIMIT_ENTRY_VALIDITY_BARS": str(validity),
        }
        base_tag = f"{args.tag_prefix}_c{idx:03d}_base_{stamp}"
        stress_tag = f"{args.tag_prefix}_c{idx:03d}_stress_{stamp}"
        base = _run_case(
            py=py,
            tag=base_tag,
            env_extra=env_extra,
            fee_bps=float(args.base_fee_bps),
            slippage_bps=float(args.base_slippage_bps),
            log_dir=log_dir,
        )
        stress = _run_case(
            py=py,
            tag=stress_tag,
            env_extra=env_extra,
            fee_bps=float(args.stress_fee_bps),
            slippage_bps=float(args.stress_slippage_bps),
            log_dir=log_dir,
        )
        row: Dict[str, object] = {
            "combo": idx,
            "offset_atr": offset,
            "validity_bars": validity,
        }
        for prefix, data in (("base", base), ("stress", stress)):
            for key, value in data.items():
                row[f"{prefix}_{key}"] = value
        row["score"] = _score(row)
        rows.append(row)
        print(
            f"combo={idx} offset={offset} validity={validity} "
            f"base_trades={row['base_trades']} base_net={float(row['base_net_pnl']):.2f} "
            f"stress_trades={row['stress_trades']} stress_net={float(row['stress_net_pnl']):.2f} "
            f"stress_pf={float(row['stress_profit_factor']):.3f}",
            flush=True,
        )

    fields = sorted({k for row in rows for k in row})
    csv_path = out_dir / "scan.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    ranked = sorted(rows, key=lambda r: float(r.get("score", -1e18)), reverse=True)
    best = ranked[0] if ranked else {}
    md = [
        "# Inplay Breakout Limit-Entry Scan 2026-07-06",
        "",
        f"- output: `{out_dir}`",
        f"- scan_csv: `{csv_path}`",
        f"- symbols: `{','.join(SYMBOLS)}`",
        f"- combos: `{len(rows)}`",
        "",
        "## Best",
        "",
        (
            f"- offset_atr `{best.get('offset_atr')}`, validity `{best.get('validity_bars')}`, "
            f"base trades `{best.get('base_trades')}`, base net `{best.get('base_net_pnl')}`, "
            f"stress trades `{best.get('stress_trades')}`, stress net `{best.get('stress_net_pnl')}`, "
            f"stress PF `{best.get('stress_profit_factor')}`"
            if best
            else "- none"
        ),
        "",
        "Research-only. A good scan row still requires the full strict gate with time folds, symbol checks, and shadow.",
        "",
    ]
    (out_dir / "summary.md").write_text("\n".join(md), encoding="utf-8")
    print(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
