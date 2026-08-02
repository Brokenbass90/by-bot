#!/usr/bin/env python3
"""Run the frozen BOUNCE1 candidate on three chronological regimes."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "configs/research/bounce1_exact_three_regime_prereg_20260802.json"
OUTPUT = ROOT / "reports/research/bounce1_exact_three_regime_20260802/result.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prereg", default=str(PREREG))
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()
    prereg_path = Path(args.prereg)
    output_path = Path(args.output)
    spec = json.loads(prereg_path.read_text(encoding="utf-8"))
    source = ROOT / "strategies/alt_support_bounce_v1.py"
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    env = os.environ.copy()
    env.update({str(k): str(v) for k, v in spec["frozen_env"].items()})
    env["BACKTEST_CACHE_ONLY"] = "1"
    rows = []
    for window in spec["windows"]:
        tag = f"bounce1_exact_{window['name']}_20260802"
        command = [
            str(ROOT / ".venv/bin/python"), "backtest/run_portfolio.py",
            "--symbols", ",".join(spec["symbols"]),
            "--strategies", spec["strategy"],
            "--days", str(window["days"]), "--end", window["end"],
            "--starting_equity", "100", "--risk_pct", "0.0075",
            "--leverage", "1", "--max_positions", "3",
            "--fee_bps", "6", "--slippage_bps", "2",
            "--cache", str(ROOT / spec["execution"]["cache"]),
            "--entry-on-next-open", "--tag", tag,
        ]
        subprocess.run(command, cwd=ROOT, env=env, check=True)
        run_dirs = sorted((ROOT / "backtest_runs").glob(f"portfolio_*_{tag}"), key=lambda p: p.stat().st_mtime)
        run_dir = run_dirs[-1]
        with (run_dir / "summary.csv").open(newline="", encoding="utf-8") as handle:
            summary = next(csv.DictReader(handle))
        rows.append({
            "window": window,
            "run_dir": str(run_dir.relative_to(ROOT)),
            "trades": int(summary["trades"]),
            "net_pct": float(summary["net_pnl"]),
            "profit_factor": float(summary["profit_factor"]),
            "winrate": float(summary["winrate"]),
            "max_drawdown_pct": float(summary["max_drawdown"]),
        })
    gate = spec["gate"]
    positive = sum(row["net_pct"] > 0 and row["profit_factor"] >= gate["profit_factor_min_each"] for row in rows)
    total_trades = sum(row["trades"] for row in rows)
    passed = positive >= gate["positive_windows_min"] and total_trades >= gate["trades_min_total"]
    output = {
        "schema_id": "bounce1_exact_three_regime_replay_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "capital_authorized": False,
        "strategy_source_sha256": source_sha,
        "n_trials_planned": 1,
        "n_trials_evaluated": 1,
        "n_trials_effective_independent": None,
        "windows": rows,
        "gate": {"positive_windows": positive, "total_trades": total_trades, "status": "PASS_TO_PROSPECTIVE_RISK_ZERO" if passed else "FAIL_EXACT_REPLAY"},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output["gate"], sort_keys=True))
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
