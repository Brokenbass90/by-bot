#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
BACKTEST_RUNS = ROOT / "backtest_runs"


def _resolve_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


def _load_rows(path: Path) -> List[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _to_float(value: str | None) -> float:
    try:
        return float(str(value or 0).strip())
    except Exception:
        return 0.0


def _latest_dynamic_dir(tag_contains: str) -> Path:
    matches = sorted(
        [
            p
            for p in BACKTEST_RUNS.glob("dynamic_annual_*")
            if p.is_dir() and tag_contains in p.name and (p / "dynamic_windows.csv").exists() and (p / "stitched_trades.csv").exists()
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not matches:
        raise FileNotFoundError(f"No dynamic annual dir matching: {tag_contains}")
    return matches[0]


def main() -> int:
    ap = argparse.ArgumentParser(description="Attribute dynamic replay performance by regime, sleeve, and strategy.")
    ap.add_argument("--run-dir", help="Dynamic annual run dir. If omitted, use --tag-contains.")
    ap.add_argument("--tag-contains", default="", help="Substring to find latest matching dynamic annual run dir.")
    args = ap.parse_args()

    if args.run_dir:
        run_dir = _resolve_path(args.run_dir)
    else:
        if not args.tag_contains:
            raise SystemExit("Provide --run-dir or --tag-contains")
        run_dir = _latest_dynamic_dir(args.tag_contains)

    windows_csv = run_dir / "dynamic_windows.csv"
    trades_csv = run_dir / "stitched_trades.csv"
    summary_json = run_dir / "summary.json"
    if not windows_csv.exists() or not trades_csv.exists():
        raise SystemExit(f"Missing dynamic outputs in {run_dir}")

    windows = _load_rows(windows_csv)
    trades = _load_rows(trades_csv)
    summary = json.loads(summary_json.read_text()) if summary_json.exists() else {}

    regime_stats: Dict[str, dict] = defaultdict(lambda: {"windows": 0, "net_pnl": 0.0, "trades": 0})
    sleeve_stats: Dict[str, dict] = defaultdict(lambda: {"windows": 0, "net_pnl": 0.0})
    strategy_stats: Dict[str, dict] = defaultdict(lambda: {"trades": 0, "net_pnl": 0.0})

    for row in windows:
        regime = str(row.get("regime") or "?")
        net = _to_float(row.get("net_pnl"))
        tr = int(float(row.get("trades") or 0))
        regime_stats[regime]["windows"] += 1
        regime_stats[regime]["net_pnl"] += net
        regime_stats[regime]["trades"] += tr
        for sleeve in str(row.get("enabled_sleeves") or "").split(";"):
            sleeve = sleeve.strip()
            if not sleeve:
                continue
            sleeve_stats[sleeve]["windows"] += 1
            sleeve_stats[sleeve]["net_pnl"] += net

    for row in trades:
        strategy = str(row.get("strategy") or "?")
        strategy_stats[strategy]["trades"] += 1
        strategy_stats[strategy]["net_pnl"] += _to_float(row.get("pnl"))

    worst_windows = sorted(
        windows,
        key=lambda row: _to_float(row.get("net_pnl")),
    )[:8]
    best_windows = sorted(
        windows,
        key=lambda row: _to_float(row.get("net_pnl")),
        reverse=True,
    )[:8]

    payload = {
        "run_dir": str(run_dir),
        "summary": summary,
        "regimes": [
            {
                "regime": k,
                "windows": v["windows"],
                "net_pnl": round(v["net_pnl"], 4),
                "trades": v["trades"],
                "avg_net_per_window": round(v["net_pnl"] / max(1, v["windows"]), 4),
            }
            for k, v in sorted(regime_stats.items(), key=lambda item: item[1]["net_pnl"])
        ],
        "sleeves": [
            {
                "sleeve": k,
                "windows": v["windows"],
                "net_pnl": round(v["net_pnl"], 4),
                "avg_net_per_window": round(v["net_pnl"] / max(1, v["windows"]), 4),
            }
            for k, v in sorted(sleeve_stats.items(), key=lambda item: item[1]["net_pnl"])
        ],
        "strategies": [
            {
                "strategy": k,
                "trades": v["trades"],
                "net_pnl": round(v["net_pnl"], 4),
                "avg_pnl_per_trade": round(v["net_pnl"] / max(1, v["trades"]), 4),
            }
            for k, v in sorted(strategy_stats.items(), key=lambda item: item[1]["net_pnl"])
        ],
        "worst_windows": worst_windows,
        "best_windows": best_windows,
    }

    out = run_dir / "attribution.json"
    out.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(f"run_dir={run_dir}")
    print(f"attribution_json={out}")
    if payload["regimes"]:
        print(f"worst_regime={payload['regimes'][0]}")
    if payload["strategies"]:
        print(f"worst_strategy={payload['strategies'][0]}")
    if payload["worst_windows"]:
        print(f"worst_window={payload['worst_windows'][0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
