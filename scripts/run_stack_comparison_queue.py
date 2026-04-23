#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKTEST_RUNS = ROOT / "backtest_runs"
DEFAULT_CONFIG = ROOT / "configs" / "stack_comparison_queue_20260423.json"
DEFAULT_POLICY = ROOT / "configs" / "portfolio_allocator_policy.json"
DEFAULT_BASE_ENV = ROOT / "configs" / "server_clean.env"


def _repo_python() -> str:
    for candidate in (ROOT / ".venv" / "bin" / "python3", ROOT / ".venv" / "bin" / "python"):
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return sys.executable


def _resolve(raw: str | Path) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "label",
        "strategy_only_net",
        "strategy_only_pf",
        "strategy_only_wr",
        "strategy_only_dd",
        "strategy_only_trades",
        "strategy_only_neg_months",
        "full_stack_net",
        "full_stack_return_pct",
        "full_stack_pf",
        "full_stack_wr",
        "full_stack_dd",
        "full_stack_trades",
        "full_stack_neg_months",
        "trade_retention_pct",
        "net_retention_pct",
        "diagnosis",
        "full_stack_run_dir",
        "strategy_only_run_dir",
        "fail_reasons",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _slug(text: str) -> str:
    out: list[str] = []
    for ch in str(text).lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in {"-", "_"}:
            out.append(ch)
        else:
            out.append("_")
    return "".join(out).strip("_")


def _latest_autoresearch_dir(spec_path: Path) -> Path:
    spec = _load_json(spec_path)
    name = _slug(str(spec.get("name") or spec_path.stem))
    matches = sorted(
        BACKTEST_RUNS.glob(f"autoresearch_*_{name}"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not matches:
        raise FileNotFoundError(f"No autoresearch run found for {spec_path}")
    return matches[0]


def _best_strategy_only_row(spec_path: Path) -> dict[str, Any]:
    run_dir = _latest_autoresearch_dir(spec_path)
    ranked = run_dir / "ranked_results.csv"
    rows = _read_csv(ranked)
    if not rows:
        raise RuntimeError(f"Empty ranked results: {ranked}")
    row = dict(rows[0])
    row["_autoresearch_dir"] = str(run_dir)
    return row


def _parse_overrides(row: dict[str, Any]) -> dict[str, str]:
    raw = str(row.get("overrides_json") or "{}")
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}
    return {str(k): str(v) for k, v in dict(payload).items()}


def _parse_command_option(command: list[Any], option: str, default: str = "") -> str:
    items = [str(x) for x in command]
    try:
        idx = items.index(option)
    except ValueError:
        return default
    if idx + 1 >= len(items):
        return default
    return str(items[idx + 1])


def _all_policy_strategies(policy: dict[str, Any]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for sleeve in list(policy.get("sleeves") or []):
        for raw in list(sleeve.get("strategy_names") or []):
            name = str(raw or "").strip()
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return names


def _candidate_health(policy: dict[str, Any], candidate: dict[str, Any], strategy_row: dict[str, Any]) -> dict[str, Any]:
    ok_strategies = {str(x) for x in list(candidate.get("strategies") or [])}
    health: dict[str, Any] = {}
    for strategy in _all_policy_strategies(policy):
        is_ok = strategy in ok_strategies
        health[strategy] = {
            "status": "OK" if is_ok else "PAUSE",
            "total_pnl": float(strategy_row.get("net_pnl") or 0.0) if is_ok else 0.0,
            "rolling_30d_pnl": 0.0,
            "rolling_60d_pnl": 0.0,
            "curve_vs_ma20": 0.0,
            "trades_total": int(float(strategy_row.get("trades") or 0)) if is_ok else 0,
            "trades_30d": 0,
            "winrate_total": float(strategy_row.get("winrate") or 0.0) if is_ok else 0.0,
            "winrate_30d": 0.0,
            "pf_30d": 0.0,
            "notes": (
                f"Stack comparison candidate {candidate.get('id')}: explicitly enabled for paired full-stack audit."
                if is_ok
                else "Paused by stack comparison harness so only the target candidate is tested."
            ),
        }
    return {
        "overall_health": "OK",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_dir": "stack_comparison_candidate_gate",
        "strategies": health,
    }


def _numeric(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default) or default)
    except Exception:
        return default


def _int(row: dict[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(float(row.get(key, default) or default))
    except Exception:
        return default


def _dynamic_summary(path: Path) -> dict[str, Any]:
    return _load_json(path / "summary.json")


def _diagnosis(strategy_trades: int, full_trades: int, strategy_net: float, full_net: float, full_dd: float, strategy_dd: float) -> str:
    trade_ret = (full_trades / strategy_trades) if strategy_trades > 0 else 0.0
    net_ret = (full_net / strategy_net) if abs(strategy_net) > 1e-9 else 0.0
    if full_trades == 0:
        return "blocked_by_stack"
    if trade_ret < 0.35 and full_dd <= strategy_dd:
        return "frequency_cut_too_hard"
    if strategy_net > 0 and full_net <= 0:
        return "edge_destroyed_by_stack"
    if trade_ret < 0.55 or net_ret < 0.45:
        return "stack_needs_relaxation"
    if full_dd < strategy_dd * 0.75 and full_net > 0:
        return "stack_helped_risk"
    return "stack_preserved_edge"


def _run_full_stack(
    *,
    candidate: dict[str, Any],
    spec: dict[str, Any],
    strategy_row: dict[str, Any],
    health_path: Path,
    timeline_path: Path,
    output_root: Path,
    config: dict[str, Any],
) -> Path:
    command = list(spec.get("command") or [])
    overrides = dict(spec.get("base_env") or {})
    overrides.update(_parse_overrides(strategy_row))

    # Autoresearch specs sometimes put sweep placeholders into command options.
    if "MAX_POSITIONS" in overrides:
        max_positions = str(overrides["MAX_POSITIONS"])
    else:
        max_positions = _parse_command_option(command, "--max_positions", "3")

    env = os.environ.copy()
    env.update({str(k): str(v) for k, v in overrides.items()})
    env["BACKTEST_CACHE_ONLY"] = str(spec.get("cache_only", True)).lower()
    env["BACKTEST_CACHE_FALLBACK_ENABLE"] = "1"

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tag = f"stackcmp_{candidate['id']}_{stamp}"
    out_dir = output_root / f"full_stack_{candidate['id']}"

    end = str(config.get("end") or _parse_command_option(command, "--end", "2026-04-01"))
    total_days = str(config.get("total_days") or _parse_command_option(command, "--days", "360"))
    window_days = str(config.get("window_days") or 30)
    step_days = str(config.get("step_days") or window_days)
    starting_equity = _parse_command_option(command, "--starting_equity", "100")
    risk_pct = _parse_command_option(command, "--risk_pct", "0.01")
    leverage = _parse_command_option(command, "--leverage", "1")
    fee_bps = _parse_command_option(command, "--fee_bps", "6")
    slippage_bps = _parse_command_option(command, "--slippage_bps", "2")

    cmd = [
        _repo_python(),
        "scripts/run_dynamic_crypto_annual.py",
        "--end",
        end,
        "--total_days",
        total_days,
        "--window_days",
        window_days,
        "--step_days",
        step_days,
        "--health",
        str(health_path),
        "--health-timeline",
        str(timeline_path),
        "--max-scan-symbols",
        str(config.get("max_scan_symbols") or 80),
        "--starting_equity",
        starting_equity,
        "--base_risk_pct",
        risk_pct,
        "--leverage",
        leverage,
        "--max_positions",
        max_positions,
        "--fee_bps",
        fee_bps,
        "--slippage_bps",
        slippage_bps,
        "--tag",
        tag,
        "--out-dir",
        str(out_dir),
    ]
    log_path = output_root / f"{candidate['id']}.log"
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    if proc.returncode != 0:
        raise RuntimeError(f"full-stack replay failed for {candidate['id']} rc={proc.returncode}; see {log_path}")
    return out_dir


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare strategy-only research results with full-stack dynamic replay.")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--only", default="", help="Comma-separated candidate ids to run.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    config_path = _resolve(args.config)
    config = _load_json(config_path)
    policy = _load_json(DEFAULT_POLICY)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_root = BACKTEST_RUNS / f"stack_comparison_{stamp}_{_slug(config.get('name') or config_path.stem)}"
    output_root.mkdir(parents=True, exist_ok=True)

    empty_timeline = output_root / "empty_strategy_health_timeline.json"
    _write_json(empty_timeline, {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "snapshots": []})

    requested = {item.strip() for item in str(args.only or "").split(",") if item.strip()}
    rows: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []

    for candidate in list(config.get("candidates") or []):
        candidate_id = str(candidate.get("id") or "").strip()
        if not candidate_id:
            continue
        if requested and candidate_id not in requested:
            continue

        spec_path = _resolve(candidate["spec"])
        spec = _load_json(spec_path)
        strategy_row = _best_strategy_only_row(spec_path)
        health_path = output_root / f"health_{candidate_id}.json"
        _write_json(health_path, _candidate_health(policy, candidate, strategy_row))

        if args.dry_run:
            full_summary = {}
            full_dir = Path("")
        else:
            full_dir = _run_full_stack(
                candidate=candidate,
                spec=spec,
                strategy_row=strategy_row,
                health_path=health_path,
                timeline_path=empty_timeline,
                output_root=output_root,
                config=config,
            )
            full_summary = _dynamic_summary(full_dir)

        strategy_net = _numeric(strategy_row, "net_pnl")
        strategy_trades = _int(strategy_row, "trades")
        strategy_dd = _numeric(strategy_row, "max_drawdown")
        full_net = float(full_summary.get("net_pnl") or 0.0)
        full_trades = int(full_summary.get("trades") or 0)
        full_dd = float(full_summary.get("max_drawdown") or 0.0)
        trade_ret = (full_trades / strategy_trades * 100.0) if strategy_trades > 0 else 0.0
        net_ret = (full_net / strategy_net * 100.0) if abs(strategy_net) > 1e-9 else 0.0
        diagnosis = _diagnosis(strategy_trades, full_trades, strategy_net, full_net, full_dd, strategy_dd)

        row = {
            "id": candidate_id,
            "label": candidate.get("label") or candidate_id,
            "strategy_only_net": round(strategy_net, 4),
            "strategy_only_pf": _numeric(strategy_row, "profit_factor"),
            "strategy_only_wr": _numeric(strategy_row, "winrate"),
            "strategy_only_dd": strategy_dd,
            "strategy_only_trades": strategy_trades,
            "strategy_only_neg_months": _int(strategy_row, "negative_months"),
            "full_stack_net": round(full_net, 4),
            "full_stack_return_pct": round(float(full_summary.get("return_pct") or 0.0), 4),
            "full_stack_pf": full_summary.get("profit_factor", 0.0),
            "full_stack_wr": full_summary.get("winrate", 0.0),
            "full_stack_dd": full_dd,
            "full_stack_trades": full_trades,
            "full_stack_neg_months": full_summary.get("negative_months", 0),
            "trade_retention_pct": round(trade_ret, 2),
            "net_retention_pct": round(net_ret, 2),
            "diagnosis": diagnosis,
            "full_stack_run_dir": str(full_dir),
            "strategy_only_run_dir": str(strategy_row.get("run_dir") or ""),
            "fail_reasons": str(strategy_row.get("fail_reasons") or ""),
        }
        rows.append(row)
        details.append(
            {
                "candidate": candidate,
                "spec": str(spec_path),
                "strategy_only": strategy_row,
                "full_stack": full_summary,
                "row": row,
            }
        )
        _write_csv(output_root / "summary.csv", rows)
        _write_json(output_root / "summary.json", {"rows": rows, "details": details})
        print(
            f"[stackcmp] {candidate_id}: strategy_only net={strategy_net:+.2f} trades={strategy_trades} "
            f"-> full_stack net={full_net:+.2f} trades={full_trades} diagnosis={diagnosis}",
            flush=True,
        )

    report = output_root / "report.md"
    lines = [
        f"# Stack Comparison Queue: {config.get('name') or config_path.stem}",
        "",
        "Rule: every candidate is compared as strategy-only research vs full-stack dynamic replay.",
        "",
        "| Candidate | Strategy-only | Full-stack | Retention | Diagnosis |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['label']} | net {row['strategy_only_net']:+.2f}, PF {row['strategy_only_pf']}, "
            f"{row['strategy_only_trades']} trades | net {row['full_stack_net']:+.2f}, PF {row['full_stack_pf']}, "
            f"{row['full_stack_trades']} trades | trades {row['trade_retention_pct']}%, net {row['net_retention_pct']}% | "
            f"{row['diagnosis']} |"
        )
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"summary_csv={output_root / 'summary.csv'}")
    print(f"summary_json={output_root / 'summary.json'}")
    print(f"report={report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
