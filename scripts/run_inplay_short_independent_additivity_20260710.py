#!/usr/bin/env python3
"""Fixed, independent-symbol additivity gate for InPlay maker short.

Research-only and cache-only.  This runner deliberately fixes two weaknesses in
the source maker gate without touching production code:

* data coverage is a hard gate before signal generation;
* portfolio occupancy is tracked by UTC timestamps, never by per-symbol row
  indices (row indices become incomparable as soon as any symbol has a gap).

The strategy parameters, symbols, costs, periods, and thresholds are read from a
pre-registered JSON file.  There is no parameter scan or result-dependent
selection.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.geometry_cache import load_rows  # noqa: E402
import scripts.run_inplay_maker_fill_gate_20260706 as source_gate  # noqa: E402


DEFAULT_CONFIG = ROOT / "configs" / "research" / "inplay_short_independent_additivity_20260710.json"
DEFAULT_OUTPUT = ROOT / "reports" / "research" / "inplay_short_independent_additivity_20260710"


def _dt_ms(raw: str) -> int:
    return int(datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def _iso_ms(ts_ms: int) -> str:
    return datetime.fromtimestamp(int(ts_ms) / 1000, timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    data = [dict(row) for row in rows]
    if not data:
        path.write_text("", encoding="utf-8")
        return
    fields: List[str] = []
    for row in data:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)


def _metrics(rs: Sequence[float]) -> Dict[str, float]:
    gross_profit = sum(x for x in rs if x > 0)
    gross_loss = -sum(x for x in rs if x < 0)
    pf = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in rs:
        equity += float(value)
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "net_r": round(sum(rs), 6),
        "profit_factor": pf,
        "winrate": (sum(1 for x in rs if x > 0) / len(rs)) if rs else 0.0,
        "max_drawdown_r": round(max_dd, 6),
        "gross_profit_r": round(gross_profit, 6),
        "gross_loss_r": round(gross_loss, 6),
    }


def _coverage_rows(
    *,
    symbols: Sequence[str],
    cache_dir: Path,
    start_ms: int,
    end_ms: int,
    interval_min: int,
    min_coverage: float,
    max_internal_gap_bars: int,
    max_tail_lag_hours: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, List[List[float]]], bool]:
    interval_ms = int(interval_min) * 60_000
    expected = max(1, (end_ms - start_ms) // interval_ms)
    out: List[Dict[str, Any]] = []
    rows_by_symbol: Dict[str, List[List[float]]] = {}
    timestamp_sets: Dict[str, set[int]] = {}

    for symbol in symbols:
        merged = [
            list(row)
            for row in load_rows(symbol, "5", data_cache_dir=cache_dir)
            if start_ms <= int(float(row[0])) < end_ms
        ]
        merged.sort(key=lambda row: int(float(row[0])))
        timestamps = [int(float(row[0])) for row in merged]
        unique_ts = sorted(set(timestamps))
        duplicate_rows = len(timestamps) - len(unique_ts)
        max_gap = 0
        gap_start = ""
        gap_end = ""
        for prev, cur in zip(unique_ts, unique_ts[1:]):
            missing = max(0, int(math.ceil((cur - prev) / interval_ms)) - 1)
            if missing > max_gap:
                max_gap = missing
                gap_start = _iso_ms(prev)
                gap_end = _iso_ms(cur)
        head_lag_h = ((unique_ts[0] - start_ms) / 3_600_000) if unique_ts else float("inf")
        tail_lag_h = ((end_ms - interval_ms - unique_ts[-1]) / 3_600_000) if unique_ts else float("inf")
        coverage = len(unique_ts) / expected
        passed = (
            coverage >= float(min_coverage)
            and max_gap <= int(max_internal_gap_bars)
            and tail_lag_h <= float(max_tail_lag_hours)
            and duplicate_rows == 0
        )
        out.append(
            {
                "symbol": symbol,
                "passed": passed,
                "coverage": round(coverage, 6),
                "rows": len(unique_ts),
                "expected_rows": expected,
                "duplicate_rows": duplicate_rows,
                "max_internal_gap_bars": max_gap,
                "gap_start": gap_start,
                "gap_end": gap_end,
                "head_lag_hours": round(head_lag_h, 6),
                "tail_lag_hours": round(tail_lag_h, 6),
                "first_ts": _iso_ms(unique_ts[0]) if unique_ts else "",
                "last_ts": _iso_ms(unique_ts[-1]) if unique_ts else "",
            }
        )
        rows_by_symbol[symbol] = merged
        timestamp_sets[symbol] = set(unique_ts)

    reference = timestamp_sets[symbols[0]] if symbols else set()
    identical = all(timestamp_sets[symbol] == reference for symbol in symbols)
    for row in out:
        row["identical_timestamps"] = identical
        if not identical:
            row["passed"] = False
    return out, rows_by_symbol, bool(out) and all(bool(row["passed"]) for row in out)


def _simulate(
    *,
    case: str,
    cost_mode: str,
    symbols: Sequence[str],
    signals: Sequence[Any],
    rows_by_symbol: Mapping[str, List[List[float]]],
    start_ms: int,
    end_ms: int,
    cfg: Mapping[str, Any],
    costs: Mapping[str, Any],
    max_positions: int,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    entry_cfg = cfg["maker_entry"]
    interval_ms = int(cfg["interval_min"]) * 60_000
    validity = int(entry_cfg["validity_bars"])
    max_hold = int(entry_cfg["max_hold_bars"])
    # Every included order has room for its full validity plus full max hold.
    signal_cutoff_ms = end_ms - (validity + max_hold + 2) * interval_ms
    selected = [
        sig
        for sig in signals
        if sig.symbol in symbols and start_ms <= int(sig.ts) < signal_cutoff_ms
    ]
    selected.sort(key=lambda sig: (int(sig.ts), str(sig.symbol)))

    open_until_ms: List[int] = []
    busy_until_by_symbol: Dict[str, int] = {}
    placed = 0
    unfilled = 0
    invalid = 0
    skipped_busy = 0
    skipped_capacity = 0
    trades: List[Dict[str, Any]] = []
    offset_atr = float(entry_cfg["offset_atr"])

    for sig in selected:
        signal_ts = int(sig.ts)
        open_until_ms = [ts for ts in open_until_ms if ts > signal_ts]
        if busy_until_by_symbol.get(sig.symbol, -1) > signal_ts:
            skipped_busy += 1
            continue
        if len(open_until_ms) >= int(max_positions):
            skipped_capacity += 1
            continue

        if sig.side == "long":
            limit = float(sig.entry) - offset_atr * float(sig.atr)
            sl_atr = (limit - float(sig.sl)) / float(sig.atr)
        else:
            limit = float(sig.entry) + offset_atr * float(sig.atr)
            sl_atr = (float(sig.sl) - limit) / float(sig.atr)
        if not (limit > 0 and sl_atr > 0):
            invalid += 1
            continue

        placed += 1
        trade = source_gate.simulate_maker_trade(
            rows_by_symbol[sig.symbol],
            int(sig.i),
            str(sig.side),
            limit,
            sl_atr=float(sl_atr),
            tp_rr=float(entry_cfg["tp_rr"]),
            validity_bars=validity,
            through_atr=float(entry_cfg["through_atr"]),
            max_hold=max_hold,
            maker_fee_bps=float(costs["maker_fee_bps"]),
            taker_fee_bps=float(costs["taker_fee_bps"]),
            exit_slippage_bps=float(costs["exit_slippage_bps"]),
            atr_period=14,
        )
        if trade is None:
            unfilled += 1
            # Do not allow duplicate pending orders for the same symbol while
            # this order would still have been resting.
            busy_until_by_symbol[sig.symbol] = signal_ts + (validity + 1) * interval_ms
            continue

        exit_ts = int(trade.get("exit_ts", signal_ts) or signal_ts)
        occupied_until = exit_ts + interval_ms
        open_until_ms.append(occupied_until)
        busy_until_by_symbol[sig.symbol] = occupied_until
        trades.append(
            {
                "case": case,
                "cost_mode": cost_mode,
                "symbol": sig.symbol,
                "side": sig.side,
                "signal_ts": int(trade.get("signal_ts", signal_ts) or signal_ts),
                "fill_ts": int(trade.get("fill_ts", 0) or 0),
                "exit_ts": exit_ts,
                "signal_utc": _iso_ms(signal_ts),
                "fill_utc": _iso_ms(int(trade.get("fill_ts", 0) or 0)),
                "exit_utc": _iso_ms(exit_ts),
                "entry": float(trade.get("entry", limit) or limit),
                "r": float(trade.get("r", 0.0) or 0.0),
                "wait_bars": int(trade.get("wait_bars", 0) or 0),
            }
        )

    rs = [float(row["r"]) for row in trades]
    metric = {
        "case": case,
        "cost_mode": cost_mode,
        "symbols": ";".join(symbols),
        "start": _iso_ms(start_ms),
        "end": _iso_ms(end_ms),
        "signal_cutoff": _iso_ms(signal_cutoff_ms),
        "generated_signals": len(selected),
        "generated_long_signals": sum(1 for sig in selected if sig.side == "long"),
        "generated_short_signals": sum(1 for sig in selected if sig.side == "short"),
        "placed_signals": placed,
        "skipped_symbol_busy": skipped_busy,
        "skipped_capacity": skipped_capacity,
        "invalid_plans": invalid,
        "unfilled": unfilled,
        "trades": len(trades),
        "unfilled_rate": (unfilled / placed) if placed else 1.0,
        **_metrics(rs),
    }
    return metric, trades


def _finite_json(value: Any) -> Any:
    if isinstance(value, float) and math.isinf(value):
        return "inf" if value > 0 else "-inf"
    if isinstance(value, dict):
        return {key: _finite_json(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_finite_json(val) for val in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing evidence: {output}")
    cfg: Dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
    if not bool(cfg.get("no_tuning")) or cfg.get("direction") != "short":
        raise SystemExit("config must be no_tuning=true and direction=short")

    source_paths = {
        "maker_gate_sha256": ROOT / "scripts" / "run_inplay_maker_fill_gate_20260706.py",
        "strict_gate_sha256": ROOT / "scripts" / "run_inplay_breakout_retest_strict_gate_20260706.py",
        "maker_fill_sha256": ROOT / "bot" / "maker_fill.py",
        "strategy_sha256": ROOT / "strategies" / "inplay_breakout.py",
        "independent_runner_sha256": Path(__file__).resolve(),
    }
    source_mismatches = []
    for config_key, path in source_paths.items():
        expected = str(cfg.get("source_code", {}).get(config_key, ""))
        actual = _sha256(path)
        if not expected or actual != expected:
            source_mismatches.append(
                {"key": config_key, "path": str(path), "expected": expected, "actual": actual}
            )
    if source_mismatches:
        raise SystemExit("source SHA256 gate failed: " + json.dumps(source_mismatches, sort_keys=True))
    output.mkdir(parents=True)

    # Freeze the shared environment dictionary exactly as pre-registered.  This
    # is the same proven mechanism used by the completed short exact launch.
    source_gate.INPLAY_R061_ENV.clear()
    source_gate.INPLAY_R061_ENV.update({str(k): str(v) for k, v in cfg["strategy_env"].items()})
    os.environ.update(source_gate.INPLAY_R061_ENV)
    os.environ["BACKTEST_CACHE_ONLY"] = "1"
    os.environ["CACHE_ONLY"] = "1"

    symbols = [str(x) for x in cfg["independent_symbols"]]
    cache_dir = ROOT / str(cfg["cache"])
    start_ms = _dt_ms(str(cfg["start"]))
    end_ms = _dt_ms(str(cfg["end"]))
    data_gate = cfg["data_gates"]
    coverage, _coverage_rows_by_symbol, data_passed = _coverage_rows(
        symbols=symbols,
        cache_dir=cache_dir,
        start_ms=start_ms,
        end_ms=end_ms,
        interval_min=int(cfg["interval_min"]),
        min_coverage=float(data_gate["min_coverage"]),
        max_internal_gap_bars=int(data_gate["max_internal_gap_bars"]),
        max_tail_lag_hours=float(data_gate["max_tail_lag_hours"]),
    )
    _write_csv(output / "coverage.csv", coverage)
    if bool(data_gate.get("require_identical_timestamps")) and not all(
        bool(row.get("identical_timestamps")) for row in coverage
    ):
        data_passed = False
    if not data_passed:
        verdict = {"passed": False, "status": "INVALID_DATA", "reasons": ["data_gate_failed"]}
        (output / "verdict.json").write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(verdict), flush=True)
        return 2

    if args.preflight_only:
        wrapper = source_gate.InPlayBreakoutWrapper()
        smoke = {
            "passed": bool(wrapper.cfg.allow_shorts and not wrapper.cfg.allow_longs),
            "source_sha256_gate_passed": True,
            "data_gate_passed": True,
            "short_only_config_passed": bool(wrapper.cfg.allow_shorts and not wrapper.cfg.allow_longs),
            "symbols": symbols,
            "max_tail_lag_hours": max(float(row["tail_lag_hours"]) for row in coverage),
        }
        (output / "preflight_smoke.json").write_text(
            json.dumps(smoke, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(smoke, sort_keys=True), flush=True)
        return 0 if smoke["passed"] else 2

    days = (end_ms - start_ms) // 86_400_000
    all_signals: List[Any] = []
    rows_by_symbol: Dict[str, List[List[float]]] = {}
    signal_audit: List[Dict[str, Any]] = []
    for idx, symbol in enumerate(symbols, 1):
        print(f"signals {idx}/{len(symbols)} {symbol} start", flush=True)
        symbol_signals, symbol_rows = source_gate._generate_signals(
            symbol,
            days=int(days),
            end=str(cfg["end"]),
            cache_dir=cache_dir,
        )
        all_signals.extend(symbol_signals)
        rows_by_symbol[symbol] = symbol_rows
        signal_audit.append(
            {
                "symbol": symbol,
                "rows": len(symbol_rows),
                "signals": len(symbol_signals),
                "long_signals": sum(1 for sig in symbol_signals if sig.side == "long"),
                "short_signals": sum(1 for sig in symbol_signals if sig.side == "short"),
                "first_signal": _iso_ms(min(sig.ts for sig in symbol_signals)) if symbol_signals else "",
                "last_signal": _iso_ms(max(sig.ts for sig in symbol_signals)) if symbol_signals else "",
            }
        )
        print(f"signals {idx}/{len(symbols)} {symbol} done n={len(symbol_signals)}", flush=True)
    all_signals.sort(key=lambda sig: (int(sig.ts), str(sig.symbol)))
    _write_csv(output / "signal_audit.csv", signal_audit)

    cases: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []
    max_positions = int(cfg["maker_entry"]["max_positions"])

    def run_case(
        name: str,
        mode: str,
        case_symbols: Sequence[str],
        case_start: int,
        case_end: int,
        case_max_positions: int,
    ) -> None:
        metric, detail = _simulate(
            case=name,
            cost_mode=mode,
            symbols=case_symbols,
            signals=all_signals,
            rows_by_symbol=rows_by_symbol,
            start_ms=case_start,
            end_ms=case_end,
            cfg=cfg,
            costs=cfg["costs"][mode],
            max_positions=case_max_positions,
        )
        cases.append(metric)
        trades.extend(detail)
        print(
            f"{name}: n={metric['trades']} netR={metric['net_r']:.4f} "
            f"pf={metric['profit_factor']} unfilled={metric['unfilled_rate']:.2%}",
            flush=True,
        )

    run_case("base_full_360", "base", symbols, start_ms, end_ms, max_positions)
    run_case("stress_full_360", "stress", symbols, start_ms, end_ms, max_positions)
    folds = [(str(a), str(b)) for a, b in cfg["folds"]]
    for index, (fold_start, fold_end) in enumerate(folds, 1):
        run_case(
            f"stress_fold_{index}",
            "stress",
            symbols,
            _dt_ms(fold_start),
            _dt_ms(fold_end),
            max_positions,
        )
    for symbol in symbols:
        run_case(f"stress_symbol_{symbol}", "stress", [symbol], start_ms, end_ms, 1)

    _write_csv(output / "cases.csv", [_finite_json(row) for row in cases])
    _write_csv(output / "trades.csv", trades)

    by_case = {str(row["case"]): row for row in cases}
    full = by_case["stress_full_360"]
    fold_rows = [by_case[f"stress_fold_{idx}"] for idx in range(1, len(folds) + 1)]
    holdout = by_case[f"stress_fold_{int(cfg['holdout_fold'])}"]
    symbol_rows = [by_case[f"stress_symbol_{symbol}"] for symbol in symbols]
    positive_folds = sum(
        1
        for row in fold_rows
        if int(row["trades"]) > 0 and float(row["net_r"]) > 0 and float(row["profit_factor"]) >= 1.0
    )
    symbols_with_trades = sum(1 for row in symbol_rows if int(row["trades"]) > 0)
    positive_symbols = sum(
        1 for row in symbol_rows if int(row["trades"]) > 0 and float(row["net_r"]) > 0
    )
    full_stress_trades = [row for row in trades if row["case"] == "stress_full_360"]
    gp_by_symbol = {
        symbol: round(sum(max(0.0, float(row["r"])) for row in full_stress_trades if row["symbol"] == symbol), 6)
        for symbol in symbols
    }
    total_gp = sum(gp_by_symbol.values())
    concentration = max(gp_by_symbol.values() or [0.0]) / total_gp if total_gp > 0 else 1.0
    gates = cfg["promotion_gates"]
    reasons: List[str] = []
    if int(full["trades"]) < int(gates["stress_min_trades"]):
        reasons.append(f"stress_trades_{full['trades']}<{gates['stress_min_trades']}")
    if float(full["profit_factor"]) < float(gates["stress_min_profit_factor"]):
        reasons.append(f"stress_pf_{float(full['profit_factor']):.3f}<{gates['stress_min_profit_factor']}")
    if bool(gates["stress_net_r_must_be_positive"]) and float(full["net_r"]) <= 0:
        reasons.append("stress_net_nonpositive")
    if float(full["unfilled_rate"]) >= float(gates["stress_max_unfilled_rate"]):
        reasons.append(f"stress_unfilled_{float(full['unfilled_rate']):.3f}")
    if positive_folds < int(gates["min_positive_chronological_folds"]):
        reasons.append(f"positive_folds_{positive_folds}/{len(fold_rows)}")
    if int(holdout["trades"]) < int(gates["holdout_min_trades"]):
        reasons.append(f"holdout_trades_{holdout['trades']}<{gates['holdout_min_trades']}")
    if float(holdout["profit_factor"]) < float(gates["holdout_min_profit_factor"]):
        reasons.append(f"holdout_pf_{float(holdout['profit_factor']):.3f}<{gates['holdout_min_profit_factor']}")
    if bool(gates["holdout_net_r_must_be_positive"]) and float(holdout["net_r"]) <= 0:
        reasons.append("holdout_net_nonpositive")
    if symbols_with_trades < int(gates["min_symbols_with_trades"]):
        reasons.append(f"symbols_with_trades_{symbols_with_trades}<{gates['min_symbols_with_trades']}")
    if positive_symbols < int(gates["min_positive_symbols"]):
        reasons.append(f"positive_symbols_{positive_symbols}<{gates['min_positive_symbols']}")
    if concentration >= float(gates["max_gross_profit_concentration"]):
        reasons.append(f"gross_profit_concentration_{concentration:.3f}")
    total_long = sum(int(row["long_signals"]) for row in signal_audit)
    if bool(gates["require_zero_long_signals"]) and total_long != 0:
        reasons.append(f"long_signals_{total_long}")

    passed = not reasons
    verdict = {
        "passed": passed,
        "status": "SHADOW_ELIGIBLE_NOT_LIVE" if passed else "NO_PROMOTION",
        "reasons": reasons if reasons else ["all_preregistered_gates_passed"],
        "data_gate_passed": data_passed,
        "direction_short_only_verified": total_long == 0,
        "stress_full": _finite_json(full),
        "positive_folds": positive_folds,
        "folds_total": len(fold_rows),
        "holdout": _finite_json(holdout),
        "symbols_with_trades": symbols_with_trades,
        "positive_symbols": positive_symbols,
        "gross_profit_by_symbol": gp_by_symbol,
        "gross_profit_concentration": round(concentration, 6),
    }
    (output / "verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest = {
        "experiment_id": cfg["experiment_id"],
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": f".venv/bin/python3 scripts/{Path(__file__).name} --config {config_path.relative_to(ROOT)}",
        "config": str(config_path),
        "config_sha256": _sha256(config_path),
        "runner": str(Path(__file__).resolve()),
        "runner_sha256": _sha256(Path(__file__).resolve()),
        "git_head_at_run": _git_head(),
        "cache_only": True,
        "research_only": True,
        "broker_calls": False,
        "network_calls": False,
        "parameter_combinations": 1,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    pf = full["profit_factor"]
    pf_text = "inf" if isinstance(pf, float) and math.isinf(pf) else f"{float(pf):.3f}"
    hold_pf = holdout["profit_factor"]
    hold_pf_text = "inf" if isinstance(hold_pf, float) and math.isinf(hold_pf) else f"{float(hold_pf):.3f}"
    summary = [
        "# InPlay maker short — independent additivity gate (2026-07-10)",
        "",
        f"- Verdict: **{verdict['status']}**.",
        f"- Independent universe: `{','.join(symbols)}`; no overlap with development symbols.",
        f"- Data gate: `{'PASS' if data_passed else 'FAIL'}`; exact shared M5 timeline, cache-only, no internal gaps; max tail lag `{max(float(r['tail_lag_hours']) for r in coverage):.2f}h`.",
        f"- Direction audit: `{sum(int(r['short_signals']) for r in signal_audit)}` short / `{total_long}` long signals.",
        f"- Stress full: N `{full['trades']}`, net `{float(full['net_r']):.4f}R`, PF `{pf_text}`, unfilled `{float(full['unfilled_rate']):.1%}`.",
        f"- Chronological stress folds: `{positive_folds}/{len(fold_rows)}` positive.",
        f"- Final 90d holdout: N `{holdout['trades']}`, net `{float(holdout['net_r']):.4f}R`, PF `{hold_pf_text}`.",
        f"- Symbol breadth: traded `{symbols_with_trades}/{len(symbols)}`, positive `{positive_symbols}/{len(symbols)}`.",
        f"- Gross-profit concentration: `{concentration:.1%}` (gate `< {float(gates['max_gross_profit_concentration']):.0%}`).",
        f"- Failed gates: `{'; '.join(reasons) if reasons else 'none'}`.",
        "",
        "Fixed one-combination test: offset 0.4 ATR, validity 24 bars, short-only, base and adverse costs. No grid or broker/live access.",
        "The final 90-day holdout is evaluated once and is not used for symbol, parameter, or threshold selection.",
        "PASS would permit only a risk=0 shadow/parity stage; it would not authorize money deployment.",
        "",
    ]
    (output / "summary.md").write_text("\n".join(summary), encoding="utf-8")
    print(json.dumps(verdict, sort_keys=True), flush=True)
    print(output, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
