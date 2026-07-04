#!/usr/bin/env python3
"""Run a fixed ARS1 configuration one symbol at a time.

Purpose:
  * distinguish a real range-suitable symbol universe from a cherry-picked
    ARS1 pocket;
  * produce a cheap OOS-symbol evidence table before any live range canary.

This script intentionally does not optimize parameters. It keeps the fixed
ARS1 r170/no-LTC geometry and tests symbol transferability.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[1]


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


def _discover_symbols(cache_dir: Path) -> List[str]:
    symbols = set()
    if not cache_dir.exists():
        return []
    for p in cache_dir.rglob("*USDT*"):
        m = re.search(r"([A-Z0-9]+USDT)", p.name)
        if m:
            symbols.add(m.group(1))
    return sorted(symbols)


def _read_summary(path: Path) -> Dict[str, str]:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"empty summary: {path}")
    return rows[0]


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="", help="Comma-separated symbols. Defaults to symbols discovered in .cache/klines.")
    ap.add_argument("--exclude", default="", help="Comma-separated symbols to exclude.")
    ap.add_argument("--days", type=int, default=360)
    ap.add_argument("--end", default="2026-04-30")
    ap.add_argument("--fee-bps", type=float, default=6.0)
    ap.add_argument("--slippage-bps", type=float, default=2.0)
    ap.add_argument("--tag-prefix", default="ars1_r170_symbol_matrix")
    ap.add_argument("--outdir", default="")
    ap.add_argument("--max-symbols", type=int, default=0)
    args = ap.parse_args()

    if args.symbols.strip():
        symbols = [s.strip().upper() for s in args.symbols.replace(";", ",").split(",") if s.strip()]
    else:
        symbols = _discover_symbols(ROOT / ".cache" / "klines")
    exclude = {s.strip().upper() for s in args.exclude.replace(";", ",").split(",") if s.strip()}
    symbols = [s for s in symbols if s not in exclude]
    if args.max_symbols and args.max_symbols > 0:
        symbols = symbols[: args.max_symbols]
    if not symbols:
        raise SystemExit("no symbols to test")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    outdir = Path(args.outdir) if args.outdir else ROOT / "reports" / "research" / f"{args.tag_prefix}_{ts}"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "params.json").write_text(
        json.dumps({"symbols": symbols, "args": vars(args), "env": ARS1_R170_ENV}, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    rows: List[Dict[str, object]] = []
    for i, sym in enumerate(symbols, 1):
        tag = f"{args.tag_prefix}_{sym}_{ts}"
        env = os.environ.copy()
        env.update(ARS1_R170_ENV)
        env["ARS1_SYMBOL_ALLOWLIST"] = sym
        cmd = [
            sys.executable,
            "backtest/run_portfolio.py",
            "--symbols",
            sym,
            "--strategies",
            "alt_range_scalp_v1",
            "--days",
            str(args.days),
            "--end",
            args.end,
            "--tag",
            tag,
            "--starting_equity",
            "100",
            "--risk_pct",
            "0.005",
            "--leverage",
            "1",
            "--max_positions",
            "1",
            "--fee_bps",
            str(args.fee_bps),
            "--slippage_bps",
            str(args.slippage_bps),
            "--entry-on-next-open",
        ]
        print(f"[{i}/{len(symbols)}] {sym}", flush=True)
        try:
            proc = subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True, timeout=900)
            saved = ""
            for line in (proc.stdout or "").splitlines():
                if line.startswith("Saved portfolio run to:"):
                    saved = line.split(":", 1)[1].strip()
                    break
            if proc.returncode != 0 or not saved:
                rows.append({
                    "symbol": sym,
                    "status": "fail",
                    "trades": 0,
                    "net_pnl": 0.0,
                    "profit_factor": 0.0,
                    "winrate": 0.0,
                    "max_drawdown": 0.0,
                    "run_dir": saved,
                    "error": (proc.stderr or proc.stdout or "")[-500:].replace("\n", " "),
                })
                _write_csv(outdir / "summary.csv", rows)
                continue
            summary = _read_summary(ROOT / saved / "summary.csv")
            rows.append({
                "symbol": sym,
                "status": "ok",
                "trades": int(float(summary.get("trades") or 0)),
                "net_pnl": float(summary.get("net_pnl") or 0.0),
                "profit_factor": float(summary.get("profit_factor") or 0.0),
                "winrate": float(summary.get("winrate") or 0.0),
                "max_drawdown": float(summary.get("max_drawdown") or 0.0),
                "run_dir": saved,
                "error": "",
            })
            rows.sort(key=lambda r: (str(r["status"]) == "ok", float(r["net_pnl"])), reverse=True)
            _write_csv(outdir / "summary.csv", rows)
        except Exception as e:
            rows.append({
                "symbol": sym,
                "status": "exception",
                "trades": 0,
                "net_pnl": 0.0,
                "profit_factor": 0.0,
                "winrate": 0.0,
                "max_drawdown": 0.0,
                "run_dir": "",
                "error": repr(e),
            })
            _write_csv(outdir / "summary.csv", rows)

    ok = [r for r in rows if r["status"] == "ok"]
    positive = [r for r in ok if float(r["net_pnl"]) > 0]
    gross_win = sum(float(r["net_pnl"]) for r in ok if float(r["net_pnl"]) > 0)
    gross_loss = -sum(float(r["net_pnl"]) for r in ok if float(r["net_pnl"]) < 0)
    crude_pf = gross_win / gross_loss if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0)
    verdict = {
        "tested": len(rows),
        "ok": len(ok),
        "positive_symbols": len(positive),
        "positive_frac": (len(positive) / len(ok)) if ok else 0.0,
        "crude_symbol_pf": crude_pf,
        "total_net_pnl": sum(float(r["net_pnl"]) for r in ok),
        "pass_preregistered": bool(ok and len(positive) / len(ok) >= 0.50 and crude_pf > 1.10),
    }
    (outdir / "verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True), encoding="utf-8")
    (outdir / "summary.md").write_text(
        "# ARS1 fixed r170 symbol matrix\n\n"
        f"- tested: `{verdict['tested']}`\n"
        f"- ok: `{verdict['ok']}`\n"
        f"- positive symbols: `{verdict['positive_symbols']}` (`{verdict['positive_frac']:.1%}`)\n"
        f"- crude symbol PF: `{verdict['crude_symbol_pf']:.3f}`\n"
        f"- total net R: `{verdict['total_net_pnl']:.2f}`\n"
        f"- preregistered pass: `{verdict['pass_preregistered']}`\n",
        encoding="utf-8",
    )
    print(f"[done] {outdir}")
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
