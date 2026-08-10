#!/usr/bin/env python3
"""Run the preregistered H4 FX leads on two fixed annual windows."""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read_one(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise RuntimeError(f"expected one summary row in {path}, got {len(rows)}")
    return dict(rows[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/research/fx_h4_annual_reproduction_20260810.json",
    )
    parser.add_argument(
        "--outdir",
        default="reports/research/fx_h4_annual_reproduction_20260810",
    )
    args = parser.parse_args()

    config_path = (ROOT / args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not config.get("research_only") or config.get("live_order_authority"):
        raise RuntimeError("annual FX reproduction must be research-only without order authority")
    if not config.get("promotion_forbidden"):
        raise RuntimeError("diagnostic annual reuse must explicitly forbid promotion")

    outdir = (ROOT / args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    fixed = dict(config["fixed_parameters"])
    costs = dict(config["cost_contract"])
    combined: list[dict[str, str]] = []

    for window in config["windows"]:
        window_id = str(window["id"])
        for item in config["fixed_setups"]:
            pair, setup = str(item).split(":", 1)
            case_dir = outdir / window_id / f"{pair}_{setup}"
            command = [
                sys.executable,
                str(ROOT / "scripts/run_fx_native_harness.py"),
                "--data-dir", str(ROOT / "data_cache/forex"),
                "--pairs", pair,
                "--setups", setup,
                "--outdir", str(case_dir),
                "--tp-rr", str(fixed["tp_rr"]),
                "--sl-atr", str(fixed["sl_atr"]),
                "--max-hold", str(fixed["max_hold_bars"]),
                "--fee-bps", str(costs["fee_bps_per_side"]),
                "--slippage-bps", str(costs["slippage_bps_per_side"]),
                "--interval-min", str(fixed["interval_min"]),
                "--min-coverage", str(fixed["min_coverage"]),
                "--max-gap-bars", str(fixed["max_gap_bars"]),
                "--max-fee-r", str(fixed["max_fee_r"]),
                "--start-utc", str(window["start_utc"]),
                "--end-utc", str(window["end_utc_exclusive"]),
            ]
            subprocess.run(command, cwd=ROOT, check=True)
            row = _read_one(case_dir / "summary.csv")
            row = {
                "window": window_id,
                "start_utc": str(window["start_utc"]),
                "end_utc_exclusive": str(window["end_utc_exclusive"]),
                **row,
            }
            combined.append(row)

    fields: list[str] = []
    for row in combined:
        for key in row:
            if key not in fields:
                fields.append(key)
    with (outdir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(combined)

    lines = [
        "# FX H4 annual reproduction",
        "",
        "Research-only; promotion forbidden; swap and broker bid/ask are not yet included.",
        "",
        "| window | symbol | setup | trades | netR | PF | folds+ | preflight |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for row in combined:
        lines.append(
            f"| {row['window']} | {row['symbol']} | {row['setup']} | {row['trades']} | "
            f"{row['net_r']} | {row['pf']} | {row['folds_positive']}/4 | {row['preflight_go']} |"
        )
    lines.extend(
        [
            "",
            f"- preregistration: `{config_path.relative_to(ROOT)}`",
            "- binding caveat: no broker-calibrated bid/ask, swap or news exclusions",
        ]
    )
    (outdir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(outdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
