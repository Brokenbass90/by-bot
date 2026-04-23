#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]
BACKTEST_RUNS = ROOT / "backtest_runs"
AUTORESEARCH_RUNNER = ROOT / "scripts" / "run_strategy_autoresearch.py"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python3"


def _repo_python() -> str:
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    return sys.executable


def _resolve_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


def _slug(text: str) -> str:
    out: List[str] = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in {"-", "_"}:
            out.append(ch)
        else:
            out.append("_")
    return "".join(out).strip("_")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_csv_rows(path: Path) -> List[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@dataclass
class LogicBatteryRow:
    entry_id: str
    label: str
    spec: str
    why: str
    run_dir: str
    passed: bool
    score: float
    trades: int
    net_pnl: float
    profit_factor: float
    winrate: float
    max_drawdown: float
    negative_months: int
    max_negative_streak: int
    worst_month_pnl: float
    tag: str
    fail_reasons: str


def _run_autoresearch(spec_path: Path, limit: int, log_path: Path) -> tuple[Optional[Path], Optional[Path]]:
    cmd = [_repo_python(), str(AUTORESEARCH_RUNNER), "--spec", str(spec_path)]
    if limit > 0:
        cmd += ["--limit", str(limit)]

    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    log_text = []
    if proc.stdout:
        log_text.append(proc.stdout)
    if proc.stderr:
        log_text.append(proc.stderr)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(log_text), encoding="utf-8")

    results_csv: Optional[Path] = None
    ranked_csv: Optional[Path] = None
    for line in (proc.stdout or "").splitlines():
        if line.startswith("results_csv="):
            results_csv = _resolve_path(line.split("=", 1)[1].strip())
        elif line.startswith("ranked_csv="):
            ranked_csv = _resolve_path(line.split("=", 1)[1].strip())

    if proc.returncode != 0:
        raise RuntimeError(f"autoresearch failed for {spec_path.name}: rc={proc.returncode}")
    return results_csv, ranked_csv


def _best_row_from_ranked(path: Path) -> dict:
    rows = _load_csv_rows(path)
    if not rows:
        raise RuntimeError(f"Empty ranked results: {path}")
    return rows[0]


def _battery_fields() -> List[str]:
    return [
        "entry_id",
        "label",
        "spec",
        "why",
        "run_dir",
        "passed",
        "score",
        "trades",
        "net_pnl",
        "profit_factor",
        "winrate",
        "max_drawdown",
        "negative_months",
        "max_negative_streak",
        "worst_month_pnl",
        "tag",
        "fail_reasons",
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a battery of distinct strategy logic hypotheses and rank the best lane.")
    ap.add_argument("--battery", required=True, help="Path to logic battery JSON.")
    ap.add_argument("--limit-per-spec", type=int, default=0, help="Optional cap passed to each autoresearch spec.")
    args = ap.parse_args()

    battery_path = _resolve_path(args.battery)
    battery = _load_json(battery_path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = BACKTEST_RUNS / f"logic_battery_{stamp}_{_slug(battery.get('name', battery_path.stem))}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "battery.json").write_text(json.dumps(battery, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    results: List[LogicBatteryRow] = []
    entries = list(battery.get("entries") or [])
    total = len(entries)
    for idx, entry in enumerate(entries, start=1):
        entry_id = str(entry.get("id") or f"entry_{idx:02d}")
        label = str(entry.get("label") or entry_id)
        why = str(entry.get("why") or "")
        spec_path = _resolve_path(str(entry["spec"]))
        log_path = out_dir / "logs" / f"{entry_id}.log"
        print(f"[{idx}/{total}] {entry_id} start label={label} spec={spec_path}", flush=True)
        try:
            _, ranked_csv = _run_autoresearch(spec_path, args.limit_per_spec, log_path)
            if ranked_csv is None or not ranked_csv.exists():
                raise RuntimeError(f"Missing ranked_csv for {entry_id}")
            top = _best_row_from_ranked(ranked_csv)
            row = LogicBatteryRow(
                entry_id=entry_id,
                label=label,
                spec=str(spec_path),
                why=why,
                run_dir=str(Path(top.get("run_dir", "")).resolve()) if top.get("run_dir") else "",
                passed=str(top.get("passed", "")).strip().lower() in {"1", "true", "yes"},
                score=float(top.get("score") or 0.0),
                trades=int(float(top.get("trades") or 0)),
                net_pnl=float(top.get("net_pnl") or 0.0),
                profit_factor=float(top.get("profit_factor") or 0.0),
                winrate=float(top.get("winrate") or 0.0),
                max_drawdown=float(top.get("max_drawdown") or 0.0),
                negative_months=int(float(top.get("negative_months") or 0)),
                max_negative_streak=int(float(top.get("max_negative_streak") or 0)),
                worst_month_pnl=float(top.get("worst_month_pnl") or 0.0),
                tag=str(top.get("tag") or ""),
                fail_reasons=str(top.get("fail_reasons") or ""),
            )
            print(
                f"[{idx}/{total}] {entry_id} best passed={row.passed} net={row.net_pnl:.2f} "
                f"pf={row.profit_factor:.3f} dd={row.max_drawdown:.3f} trades={row.trades}",
                flush=True,
            )
        except Exception as exc:
            row = LogicBatteryRow(
                entry_id=entry_id,
                label=label,
                spec=str(spec_path),
                why=why,
                run_dir="",
                passed=False,
                score=-1_000_000.0,
                trades=0,
                net_pnl=0.0,
                profit_factor=0.0,
                winrate=0.0,
                max_drawdown=0.0,
                negative_months=0,
                max_negative_streak=0,
                worst_month_pnl=0.0,
                tag="",
                fail_reasons=f"battery:{type(exc).__name__}:{exc}",
            )
            print(f"[{idx}/{total}] {entry_id} CRASH {row.fail_reasons}", flush=True)
        results.append(row)

    ranked = sorted(
        results,
        key=lambda r: (not r.passed, -r.score, -r.net_pnl, r.max_drawdown),
    )

    results_csv = out_dir / "results.csv"
    with results_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_battery_fields())
        w.writeheader()
        for row in ranked:
            w.writerow(row.__dict__)

    summary = {
        "battery": str(battery_path),
        "out_dir": str(out_dir),
        "entries": len(entries),
        "best_entry": ranked[0].__dict__ if ranked else None,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    print(f"battery={battery_path}")
    print(f"results_csv={results_csv}")
    print(f"summary_json={out_dir / 'summary.json'}")
    if ranked:
        top = ranked[0]
        print(
            f"best_logic={top.entry_id} passed={top.passed} net={top.net_pnl:.2f} "
            f"pf={top.profit_factor:.3f} dd={top.max_drawdown:.3f} trades={top.trades}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
