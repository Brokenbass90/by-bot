#!/usr/bin/env python3
"""Persistent, no-order crypto research queue for the 2026-08-10 handoff.

The process is intended to live inside ``screen``. It resumes completed cases,
keeps an append-only ledger, refuses private/live authority and never reads the
reserved 2025-10..2026-06 holdout. Results are discovery evidence only because
the downloaded universe contains current survivors.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import glob
import json
import math
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs/research/six_day_crypto_pipeline_20260810.json"
OUT = ROOT / "reports/research/six_day_crypto_pipeline_20260810"
CORE_ORDER = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT",
    "ADAUSDT", "LINKUSDT", "AVAXUSDT", "DOTUSDT", "LTCUSDT", "BCHUSDT",
    "ETCUSDT", "ATOMUSDT", "NEARUSDT", "FILUSDT", "TRXUSDT", "APTUSDT",
    "ARBUSDT", "OPUSDT", "INJUSDT", "SUIUSDT", "TONUSDT", "WIFUSDT",
]
SAFE_ENV = {
    "DRY_RUN": "1",
    "TRADE_ON": "0",
    "ENABLE_BYBIT": "0",
    "ENABLE_BINANCE": "0",
    "ENABLE_MEXC": "0",
    "BACKTEST_CACHE_ONLY": "1",
    "BACKTEST_CACHE_FALLBACK_ENABLE": "0",
    "BACKTEST_MIN_COVERAGE_FRAC": "0.98",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_day(raw: str) -> datetime:
    return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(pending, path)


def append_ledger(payload: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "ledger.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts_utc": utc_now(), **payload}, sort_keys=True) + "\n")


def set_status(stage: str, **extra) -> None:
    atomic_json(
        OUT / "status.json",
        {
            "schema_id": "six_day_crypto_pipeline_status_v1",
            "updated_at_utc": utc_now(),
            "stage": stage,
            "research_only": True,
            "live_order_authority": False,
            **extra,
        },
    )


def downloader_complete(path: Path) -> bool:
    if not path.exists():
        return False
    tail = path.read_text(encoding="utf-8", errors="ignore")[-12000:]
    return "готово: сохранено" in tail


def downloader_running() -> bool:
    result = subprocess.run(
        ["pgrep", "-f", "scripts/fetch_bybit_universe.py.*--top.*150"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def ensure_download(config: dict, deadline: datetime) -> None:
    log_path = ROOT / config["data_contract"]["downloader_log"]
    while not downloader_complete(log_path):
        if datetime.now(timezone.utc) >= deadline:
            raise TimeoutError("deadline reached while waiting for Bybit history")
        if not downloader_running():
            append_ledger({"event": "downloader_restart", "log": str(log_path.relative_to(ROOT))})
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as log:
                result = subprocess.run(
                    [
                        "nice", "-n", "10", sys.executable,
                        "scripts/fetch_bybit_universe.py", "--top", "150",
                        "--since", "2023-01-01", "--resume",
                    ],
                    cwd=ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            append_ledger({"event": "downloader_exit", "returncode": result.returncode})
            if result.returncode != 0:
                time.sleep(300)
                continue
        set_status("waiting_for_history", downloader_running=downloader_running())
        time.sleep(300)
    append_ledger({"event": "downloader_complete"})


def symbols_with_filename_coverage(cache_dir: Path, start_ms: int, end_ms: int) -> list[str]:
    covered: set[str] = set()
    for raw in glob.glob(str(cache_dir / "*_5_*.json")):
        path = Path(raw)
        parts = path.stem.rsplit("_", 3)
        if len(parts) != 4 or parts[1] != "5":
            continue
        try:
            file_start, file_end = int(parts[2]), int(parts[3])
        except ValueError:
            continue
        if file_start <= start_ms and file_end >= end_ms:
            covered.add(parts[0].upper())
    return [s for s in CORE_ORDER if s in covered] + sorted(covered - set(CORE_ORDER))


def coverage_preflight(config: dict, window: dict) -> list[str]:
    contract = config["data_contract"]
    cache_dir = ROOT / contract["cache_dir"]
    start = parse_day(window["start_utc"])
    end = parse_day(window["end_utc_exclusive"])
    days = (end - start).days
    preselected = symbols_with_filename_coverage(
        cache_dir, int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    )[: int(contract["max_symbols"])]
    if not preselected:
        raise RuntimeError(f"no filename-level cache coverage for {window['id']}")
    receipt = OUT / "coverage" / f"{window['id']}.csv"
    command = [
        sys.executable, "scripts/preflight_cache_coverage.py",
        "--asset-class", "crypto", "--cache-dir", str(cache_dir),
        "--symbols", ",".join(preselected), "--days", str(days),
        "--end", window["end_utc_exclusive"], "--interval-min", "5",
        "--min-coverage", str(contract["min_coverage"]),
        "--max-gap-bars", str(contract["max_gap_bars"]), "--out", str(receipt),
    ]
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode not in (0, 2):
        raise RuntimeError(f"coverage preflight failed rc={result.returncode}")
    with receipt.open(newline="", encoding="utf-8") as handle:
        passed = [row["symbol"] for row in csv.DictReader(handle) if row["passed"] == "True"]
    if len(passed) < 8:
        raise RuntimeError(f"only {len(passed)} symbols passed coverage for {window['id']}")
    return passed


def experiment_preflight() -> dict:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from research_lab.experiment_preflight import (
        assert_handle_differentiates,
        assert_param_handle_differentiates,
    )

    checks = {
        "att1_slope": assert_handle_differentiates(
            "alt_trendline_touch_v1", "ATT1_MAX_SLOPE_PCT", "max_slope_pct", [0.7, 4.0], quiet=True
        ),
        "hzbo_longs": assert_handle_differentiates(
            "alt_horizontal_break_v1", "HZBO1_ALLOW_LONGS", "allow_longs", [0, 1], quiet=True
        ),
        "hzbo_shorts": assert_handle_differentiates(
            "alt_horizontal_break_v1", "HZBO1_ALLOW_SHORTS", "allow_shorts", [0, 1], quiet=True
        ),
        "support_rsi": assert_handle_differentiates(
            "alt_support_reclaim_v1", "ASR1_MAX_RSI", "max_rsi", [50, 60], quiet=True
        ),
        "squeeze_longs": assert_param_handle_differentiates(
            "alt_squeeze_breakout_v1", "SQB1_ALLOW_LONGS", "ALLOW_LONGS", [0, 1], quiet=True
        ),
        "squeeze_shorts": assert_param_handle_differentiates(
            "alt_squeeze_breakout_v1", "SQB1_ALLOW_SHORTS", "ALLOW_SHORTS", [0, 1], quiet=True
        ),
    }
    atomic_json(
        OUT / "experiment_preflight_receipt.json",
        {"schema_id": "six_day_experiment_preflight_v1", "status": "pass", "checks": checks},
    )
    return checks


def find_completed_run(tag: str) -> Path | None:
    candidates = sorted(ROOT.glob(f"backtest_runs/*_{tag}"), key=lambda p: p.stat().st_mtime)
    for path in reversed(candidates):
        if (path / "summary.csv").exists() and (path / "trades.csv").exists():
            return path
    return None


def metrics(run_dir: Path) -> dict:
    with (run_dir / "trades.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rs = []
    for row in rows:
        try:
            risk = float(row.get("initial_risk_usd") or 0)
            if risk > 0:
                rs.append(float(row.get("pnl") or 0) / risk)
        except (TypeError, ValueError):
            continue
    wins = sum(value for value in rs if value > 0)
    losses = -sum(value for value in rs if value < 0)
    mean = statistics.mean(rs) if rs else 0.0
    sd = statistics.stdev(rs) if len(rs) > 1 else 0.0
    t_stat = mean / (sd / math.sqrt(len(rs))) if sd > 0 else 0.0
    return {
        "trades": len(rs), "net_r": sum(rs), "mean_r": mean, "t_stat": t_stat,
        "profit_factor_r": wins / losses if losses > 0 else (math.inf if wins > 0 else 0.0),
    }


def run_case(config: dict, window: dict, family: dict, costs: dict, symbols: list[str]) -> dict:
    tag = f"sixday-{window['id']}-{family['id']}-{costs['id']}"
    existing = find_completed_run(tag)
    if existing is None:
        days = (parse_day(window["end_utc_exclusive"]) - parse_day(window["start_utc"])).days
        env = {**os.environ, **SAFE_ENV, **{k: str(v) for k, v in family.get("env", {}).items()}}
        env["BACKTEST_MIN_COVERAGE_FRAC"] = str(config["data_contract"]["min_coverage"])
        if family["strategy"] == "alt_support_reclaim_v1":
            env["ASR1_SYMBOL_ALLOWLIST"] = ",".join(symbols)
        if family["strategy"] == "alt_squeeze_breakout_v1":
            env["SQB1_SYMBOL_ALLOWLIST"] = ",".join(symbols)
        command = [
            sys.executable, "backtest/run_portfolio.py", "--symbols", ",".join(symbols),
            "--strategies", family["strategy"], "--days", str(days),
            "--end", window["end_utc_exclusive"], "--cache", config["data_contract"]["cache_dir"],
            "--tag", tag, "--starting_equity", "1000", "--risk_pct", "0.005",
            "--cap_notional", "1000000", "--leverage", "1", "--max_positions", "3",
            "--fee_bps", str(costs["fee_bps"]), "--slippage_bps", str(costs["slippage_bps"]),
            "--entry-on-next-open",
        ]
        logs = OUT / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        with (logs / f"{tag}.log").open("a", encoding="utf-8") as log:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"case {tag} failed rc={result.returncode}")
        existing = find_completed_run(tag)
        if existing is None:
            raise RuntimeError(f"case {tag} returned without a complete run")
    audit = subprocess.run(
        [sys.executable, "scripts/audit_backtest_run.py", str(existing)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, check=False,
    )
    return {
        "tag": tag, "window": window["id"], "family": family["id"],
        "cost_scenario": costs["id"], "symbols": len(symbols),
        "run_dir": str(existing.relative_to(ROOT)), "audit_rc": audit.returncode,
        **metrics(existing),
    }


def write_summary(rows: list[dict]) -> None:
    fields = [
        "window", "family", "cost_scenario", "symbols", "trades", "net_r",
        "mean_r", "t_stat", "profit_factor_r", "audit_rc", "run_dir", "tag",
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in fields} for row in rows])
    lines = [
        "# Six-day crypto research queue", "",
        "Research-only. No live-order authority. Current-survivor universe; promotion forbidden.", "",
        "| window | family | cost | n | netR | R/trade | t | PF(R) | audit |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['window']} | {row['family']} | {row['cost_scenario']} | {row['trades']} | "
            f"{row['net_r']:.3f} | {row['mean_r']:.4f} | {row['t_stat']:.2f} | "
            f"{row['profit_factor_r']:.3f} | {row['audit_rc']} |"
        )
    lines += ["", "Reserved holdout 2025-10..2026-07 was not read."]
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def terminal_stage(
    *,
    completed_cases: int,
    expected_cases: int,
    failed_cases: list[str],
    invalid_cases: list[str] | None = None,
) -> str:
    """Never label a partial or independently-invalid matrix complete."""

    if failed_cases:
        return "incomplete_case_failures"
    if invalid_cases:
        return "incomplete_validation_failures"
    if completed_cases == expected_cases:
        return "complete"
    return "incomplete_case_failures"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if not config.get("research_only") or config.get("live_order_authority"):
        raise RuntimeError("pipeline requires research_only=true and live_order_authority=false")
    if not config.get("promotion_forbidden") or not config.get("reserved_holdout", {}).get("must_not_be_read"):
        raise RuntimeError("promotion and holdout guards are mandatory")
    holdout_start = parse_day(config["reserved_holdout"]["start_utc"])
    if any(parse_day(window["end_utc_exclusive"]) > holdout_start for window in config["windows"]):
        raise RuntimeError("a research window overlaps the reserved holdout boundary")
    deadline = datetime.fromisoformat(config["deadline_utc"].replace("Z", "+00:00"))

    OUT.mkdir(parents=True, exist_ok=True)
    lock_handle = (OUT / "pipeline.lock").open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("six-day pipeline already running")
        return 0

    set_status("starting", deadline_utc=config["deadline_utc"])
    experiment_preflight()
    ensure_download(config, deadline)
    rows: list[dict] = []
    failed_cases: list[str] = []
    for window in config["windows"]:
        symbols = coverage_preflight(config, window)
        append_ledger({"event": "window_ready", "window": window["id"], "symbols": symbols})
        for family in config["families"]:
            for costs in config["cost_scenarios"]:
                if datetime.now(timezone.utc) >= deadline:
                    set_status("deadline_reached", completed_cases=len(rows))
                    write_summary(rows)
                    return 0
                case_id = f"{window['id']}:{family['id']}:{costs['id']}"
                set_status("running_case", case=case_id, completed_cases=len(rows))
                try:
                    row = run_case(config, window, family, costs, symbols)
                except Exception as exc:
                    append_ledger({"event": "case_failed", "case": case_id, "error": repr(exc)})
                    set_status("case_failed_continuing", case=case_id, error=repr(exc))
                    failed_cases.append(case_id)
                    continue
                rows.append(row)
                append_ledger({"event": "case_complete", **row})
                write_summary(rows)
    expected_cases = len(config["windows"]) * len(config["families"]) * len(config["cost_scenarios"])
    invalid_cases = [
        f"{row['window']}:{row['family']}:{row['cost_scenario']}"
        for row in rows
        if int(row.get("audit_rc") or 0) != 0
    ]
    set_status(
        terminal_stage(
            completed_cases=len(rows),
            expected_cases=expected_cases,
            failed_cases=failed_cases,
            invalid_cases=invalid_cases,
        ),
        completed_cases=len(rows),
        expected_cases=expected_cases,
        failed_cases=failed_cases,
        invalid_cases=invalid_cases,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
