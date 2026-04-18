#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
BACKTEST_RUNS = ROOT / "backtest_runs"
DEFAULT_CONFIG = ROOT / "configs" / "crypto_rehab_multiyear_queue.json"
RUNTIME_DIR = ROOT / "runtime" / "research_queue"
LOG_DIR = ROOT / "logs" / "research"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_python() -> str:
    venv_python = ROOT / ".venv" / "bin" / "python3"
    if venv_python.exists() and os.access(venv_python, os.X_OK):
        return str(venv_python)
    return sys.executable


def _slug(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_")


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _days_inclusive(start_s: str, end_s: str) -> int:
    start_d = date.fromisoformat(start_s)
    end_d = date.fromisoformat(end_s)
    return (end_d - start_d).days + 1


def _latest_summary_for_tag(tag: str) -> Path | None:
    matches = sorted(BACKTEST_RUNS.glob(f"portfolio_*_{tag}/summary.csv"), key=lambda p: p.parent.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _latest_autoresearch_dir(spec_path: Path) -> Path | None:
    slug = _slug(spec_path.stem)
    matches = sorted(BACKTEST_RUNS.glob(f"autoresearch_*_{slug}"), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _read_summary(path: Path) -> Dict[str, Any]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return {}
    row = dict(rows[0])
    for key in ("starting_equity", "ending_equity", "trades", "net_pnl", "profit_factor", "winrate", "max_drawdown"):
        if key in row and row[key] not in (None, ""):
            try:
                row[key] = float(row[key])
            except Exception:
                pass
    return row


def _ensure_results_csv(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "ts",
                "task",
                "kind",
                "window",
                "tag",
                "strategy",
                "symbols",
                "start",
                "end",
                "days",
                "trades",
                "ending_equity",
                "net_pnl",
                "profit_factor",
                "winrate",
                "max_drawdown",
                "run_dir",
                "summary_csv",
                "status",
                "notes",
            ],
        )
        w.writeheader()


def _append_result(path: Path, row: Dict[str, Any]) -> None:
    _ensure_results_csv(path)
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "ts", "task", "kind", "window", "tag", "strategy", "symbols", "start", "end", "days",
            "trades", "ending_equity", "net_pnl", "profit_factor", "winrate", "max_drawdown",
            "run_dir", "summary_csv", "status", "notes",
        ])
        w.writerow(row)


def _run(cmd: List[str], env: Dict[str, str], log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as logf:
        proc = subprocess.run(cmd, cwd=str(ROOT), env=env, stdout=logf, stderr=subprocess.STDOUT)
        return int(proc.returncode)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a resumable multiyear crypto rehab queue.")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    config_path = Path(args.config).resolve()
    config = _load_json(config_path, {})
    if not config:
        raise SystemExit(f"Could not load config: {config_path}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    name = _slug(str(config.get("name") or "crypto_rehab_multiyear_queue"))
    progress_path = RUNTIME_DIR / f"{name}_progress.json"
    history_path = RUNTIME_DIR / f"{name}_history.jsonl"
    results_path = BACKTEST_RUNS / f"{name}_results.csv"
    state = _load_json(progress_path, {"config": str(config_path), "completed": {}, "started_utc": _utc_now()})
    completed = dict(state.get("completed") or {})

    python = _repo_python()
    windows = list(config.get("windows") or [])
    tasks = list(config.get("tasks") or [])

    if not args.quiet:
        print(f"[queue] config={config_path}")
        print(f"[queue] progress={progress_path}")
        print(f"[queue] results={results_path}")

    for task in tasks:
        task_name = str(task.get("name") or "task")
        kind = str(task.get("kind") or "annual_matrix")

        if kind == "annual_matrix":
            strategy = str(task["strategy"])
            symbols = [str(s).upper() for s in (task.get("symbols") or [])]
            base_env = {str(k): str(v) for k, v in dict(task.get("env") or {}).items()}
            extra_args = [str(x) for x in list(task.get("args") or [])]
            tag_prefix = str(task.get("tag_prefix") or _slug(task_name))

            for window in windows:
                window_name = str(window["name"])
                step_key = f"{task_name}:{window_name}"
                if step_key in completed:
                    continue
                start_s = str(window["start"])
                end_s = str(window["end"])
                days = _days_inclusive(start_s, end_s)
                tag = f"{tag_prefix}_{window_name}"
                log_path = LOG_DIR / f"{tag}_{stamp}.log"
                cmd = [
                    python,
                    "backtest/run_portfolio.py",
                    "--symbols",
                    ",".join(symbols),
                    "--strategies",
                    strategy,
                    "--days",
                    str(days),
                    "--end",
                    end_s,
                    "--tag",
                    tag,
                ] + extra_args
                env = os.environ.copy()
                env.update(base_env)

                _append_jsonl(history_path, {"ts": _utc_now(), "event": "start", "task": task_name, "window": window_name, "tag": tag, "cmd": cmd})
                rc = _run(cmd, env, log_path)
                summary_csv = _latest_summary_for_tag(tag)
                row: Dict[str, Any] = {
                    "ts": _utc_now(),
                    "task": task_name,
                    "kind": kind,
                    "window": window_name,
                    "tag": tag,
                    "strategy": strategy,
                    "symbols": ";".join(symbols),
                    "start": start_s,
                    "end": end_s,
                    "days": days,
                    "trades": "",
                    "ending_equity": "",
                    "net_pnl": "",
                    "profit_factor": "",
                    "winrate": "",
                    "max_drawdown": "",
                    "run_dir": "",
                    "summary_csv": "",
                    "status": "ok" if rc == 0 else f"rc={rc}",
                    "notes": "",
                }
                if summary_csv and summary_csv.exists():
                    summary = _read_summary(summary_csv)
                    row.update({
                        "trades": summary.get("trades", ""),
                        "ending_equity": summary.get("ending_equity", ""),
                        "net_pnl": summary.get("net_pnl", ""),
                        "profit_factor": summary.get("profit_factor", ""),
                        "winrate": summary.get("winrate", ""),
                        "max_drawdown": summary.get("max_drawdown", ""),
                        "run_dir": str(summary_csv.parent),
                        "summary_csv": str(summary_csv),
                    })
                else:
                    row["notes"] = "summary_missing"
                _append_result(results_path, row)
                completed[step_key] = {"finished_utc": _utc_now(), "status": row["status"], "summary_csv": row["summary_csv"]}
                state["completed"] = completed
                state["last_finished"] = {"task": task_name, "window": window_name, "tag": tag, "status": row["status"]}
                _write_json(progress_path, state)
                _append_jsonl(history_path, {"ts": _utc_now(), "event": "finish", "task": task_name, "window": window_name, "tag": tag, "status": row["status"]})

        elif kind == "autoresearch":
            spec_rel = str(task["spec"])
            spec_path = (ROOT / spec_rel).resolve()
            step_key = f"{task_name}:autoresearch"
            if step_key in completed:
                continue
            log_path = LOG_DIR / f"{_slug(task_name)}_{stamp}.log"
            cmd = [python, "scripts/run_strategy_autoresearch.py", "--spec", str(spec_path)]
            _append_jsonl(history_path, {"ts": _utc_now(), "event": "start", "task": task_name, "spec": spec_rel, "cmd": cmd})
            rc = _run(cmd, os.environ.copy(), log_path)
            run_dir = _latest_autoresearch_dir(spec_path)
            row = {
                "ts": _utc_now(),
                "task": task_name,
                "kind": kind,
                "window": "",
                "tag": spec_path.stem,
                "strategy": "",
                "symbols": "",
                "start": "",
                "end": "",
                "days": "",
                "trades": "",
                "ending_equity": "",
                "net_pnl": "",
                "profit_factor": "",
                "winrate": "",
                "max_drawdown": "",
                "run_dir": str(run_dir) if run_dir else "",
                "summary_csv": "",
                "status": "ok" if rc == 0 else f"rc={rc}",
                "notes": spec_rel,
            }
            _append_result(results_path, row)
            completed[step_key] = {"finished_utc": _utc_now(), "status": row["status"], "run_dir": row["run_dir"]}
            state["completed"] = completed
            state["last_finished"] = {"task": task_name, "spec": spec_rel, "status": row["status"]}
            _write_json(progress_path, state)
            _append_jsonl(history_path, {"ts": _utc_now(), "event": "finish", "task": task_name, "spec": spec_rel, "status": row["status"]})
        else:
            raise SystemExit(f"Unsupported task kind: {kind}")

    state["finished_utc"] = _utc_now()
    _write_json(progress_path, state)
    if not args.quiet:
        print(f"[queue] done results={results_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
