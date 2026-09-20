#!/usr/bin/env python3
"""Run adaptive_v1 as the single Alpaca monthly paper order driver."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OWNERSHIP_SCHEMA_ID = "alpaca_adaptive_paper_owned_positions_v1"
FROZEN_INTENDED_CONFIG = ROOT / "configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json"
FROZEN_INTENDED_GROSS = 0.70
FROZEN_INTENDED_WEIGHT_CAP = 0.60
# Compatibility seams for the legacy driver.  They intentionally stay lazy so
# `--prepare-intended` can run from local cache without yfinance installed.
run_shadow = None
write_bridge_picks_csv = None


def _frozen_clusters() -> list[set[str]]:
    """Load the frozen diversification groups without importing research runners."""
    config = json.loads(FROZEN_INTENDED_CONFIG.read_text(encoding="utf-8"))
    return [{str(symbol).upper() for symbol in group} for group in config["clusters"]]


def _frozen_source_hashes() -> dict[str, Any]:
    config = json.loads(FROZEN_INTENDED_CONFIG.read_text(encoding="utf-8"))
    actual_paths = {
        "portfolio_engine": ROOT / "backtest/alpaca_honest_portfolio.py",
        "bakeoff_contract": ROOT / "backtest/alpaca_bakeoff_v2_contract.py",
        "sector_map": ROOT / "strategies/alpaca_dynamic_v4_event.py",
        "hourly_aggregator": ROOT / "scripts/build_equities_monthly_live_cycle.py",
    }
    return {
        "config_sha256": hashlib.sha256(FROZEN_INTENDED_CONFIG.read_bytes()).hexdigest(),
        **{name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in actual_paths.items()},
        "declared_source_pins": {
            str(name): str(item.get("sha256") or "")
            for name, item in dict(config.get("source_pins") or {}).items()
            if isinstance(item, dict)
        },
    }


def _load_intended_hourly_history(cache_dir: Path) -> dict[str, list[Any]]:
    """Aggregate the specified local cache and convert into canonical DailyBar values."""
    # Deliberately local imports: normal legacy mode may use yfinance, while
    # offline intended preparation must not require it.
    from backtest.alpaca_exact_parity_contract import DailyBar
    from scripts.build_equities_monthly_live_cycle import _aggregate_daily

    history: dict[str, list[Any]] = {}
    for path in sorted(cache_dir.glob("*_M5.csv")):
        symbol = path.stem.removesuffix("_M5").upper()
        history[symbol] = [
            DailyBar(date.fromisoformat(bar.day), bar.o, bar.h, bar.l, bar.c)
            for bar in _aggregate_daily(path)
        ]
    if "SPY" not in history:
        raise ValueError("intended_prepare_missing_spy_cache")
    return history


def prepare_intended_report(
    history: dict[str, list[Any]], *, signal_session: date, entry_session: date
) -> dict[str, Any]:
    """Create a frozen, causal v38 intended selection from completed signal bars."""
    if entry_session <= signal_session:
        raise ValueError("entry_session_must_be_later_than_signal_session")
    from backtest.alpaca_bakeoff_v2_contract import spy200_gate
    from backtest.alpaca_honest_portfolio import select_v38_successor
    from strategies.alpaca_dynamic_v4_event import SECTOR_MAP

    cutoff = {
        symbol: [bar for bar in rows if bar.session_date <= signal_session]
        for symbol, rows in history.items()
    }
    # A symbol without a completed bar at the signal cutoff is unavailable;
    # using its earlier bar would silently mix information sets.
    cutoff = {
        symbol: rows for symbol, rows in cutoff.items()
        if rows and rows[-1].session_date == signal_session
    }
    spy = cutoff.get("SPY") or []
    if not spy:
        raise ValueError("intended_prepare_signal_session_missing_from_spy")
    gate_ok = spy200_gate([bar.close for bar in spy])
    picks = ()
    reason = "spy200_gate_cash"
    if gate_ok:
        picks = select_v38_successor(
            cutoff,
            sectors=SECTOR_MAP,
            clusters=_frozen_clusters(),
            top_n=4,
            maximum_weight=FROZEN_INTENDED_WEIGHT_CAP,
        )
        reason = "ok" if picks else "no_qualifying_names"
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "intended_prepare_only",
        "evidence_kind": "frozen_intended_preparation_not_rehearsal_not_prospective",
        "strategy": "select_v38_successor_spy200_gated",
        "frozen_config_at_utc": str(json.loads(FROZEN_INTENDED_CONFIG.read_text(encoding="utf-8")).get("frozen_at_utc") or ""),
        "signal_session": signal_session.isoformat(),
        "entry_session": entry_session.isoformat(),
        "max_positions": 4,
        "target_gross_exposure": FROZEN_INTENDED_GROSS,
        "maximum_weight": FROZEN_INTENDED_WEIGHT_CAP,
        "scenario_cost_bps_per_side": 10.0,
        "scenario_cost_note": "historical accounting assumption; not broker fee evidence",
        "gate_ok": gate_ok,
        "reason": reason,
        "selector_source_hashes": _frozen_source_hashes(),
        "picks": [
            {
                "symbol": candidate.symbol,
                "rawscore": candidate.score,
                "score": candidate.weight,
                "weight": candidate.weight,
                "atr20": candidate.atr_at_signal,
                "atr20_pct": candidate.atr_pct_at_signal,
                "signal_close": candidate.signal_close,
                "stop_price": candidate.signal_close - 2.0 * candidate.atr_at_signal,
            }
            for candidate in picks
        ],
    }


def write_intended_bridge_picks_csv(report: dict[str, Any], path: Path) -> None:
    """Materialize frozen weights and signal-close stops for existing fill shifting."""
    fields = [
        "month", "ticker", "entry_day", "base_score", "overlay_score", "score",
        "atr20_pct", "momentum20_pct", "momentum60_pct", "pullback60_pct",
        "universe_score", "selection_score", "corr_penalty", "max_corr_to_existing",
        "entry_price", "stop_price", "target_price", "weight",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for pick in report.get("picks") or []:
            frozen_weight = float(pick["weight"])
            writer.writerow({
                "month": str(report["entry_session"])[:7], "ticker": pick["symbol"],
                "entry_day": report["entry_session"], "base_score": pick["rawscore"],
                "overlay_score": 0.0, "score": frozen_weight,
                "atr20_pct": pick["atr20_pct"], "momentum20_pct": 0.0,
                "momentum60_pct": 0.0, "pullback60_pct": 0.0,
                "universe_score": pick["rawscore"], "selection_score": pick["rawscore"],
                "corr_penalty": 0.0, "max_corr_to_existing": 0.0,
                "entry_price": pick["signal_close"], "stop_price": pick["stop_price"],
                "target_price": "", "weight": frozen_weight,
            })


def build_intended_bridge_env(
    report: dict[str, Any], *, picks_csv: Path, capital: float
) -> dict[str, str]:
    """Frozen PAPER environment; this preparation mode never enables orders."""
    # Do not return inherited credentials; callers can source this generated
    # override file only in a separately approved broker-runtime step.
    env: dict[str, str] = {}
    protective_runtime = picks_csv.parent / "protective_exit"
    env.update({
        "ALPACA_BASE_URL": "https://paper-api.alpaca.markets",
        "ALPACA_API_BASE_URL": "https://paper-api.alpaca.markets",
        "ALPACA_PICKS_CSV": str(picks_csv), "ALPACA_CURRENT_CYCLE_PICKS_CSV": str(picks_csv),
        "ALPACA_SEND_ORDERS": "0", "ALPACA_ALLOW_NEW_ENTRIES": "0",
        "ALPACA_CLOSE_STALE_POSITIONS": "0", "ALPACA_CAPITAL_OVERRIDE_USD": str(max(0.0, capital)),
        "ALPACA_TARGET_ALLOC_PCT": "0.70000000", "ALPACA_MAX_POSITIONS": "4",
        "ALPACA_MIN_DOLLAR_ORDER": "1",
        "ALPACA_ALLOW_STALE_PICKS": "0", "ALPACA_REFRESH_UTC": str(report.get("generated_at_utc") or ""),
        "MONTHLY_WEIGHTED_SIZING": "1", "MONTHLY_ATR_SIZING": "0",
        "ALPACA_ENTRY_RELATIVE_STOP_ENABLE": "1", "ALPACA_BROKER_PROTECTION_ENABLE": "1",
        "ALPACA_BROKER_PROTECTION_REQUIRED": "1", "ALPACA_BROKER_PROTECTION_ORDER_CLASS": "simple_stop",
        "ALPACA_BROKER_PROTECTION_SIZE_MODE": "qty", "ALPACA_WHOLE_SHARE_ONLY": "0",
        "ALPACA_BROKER_PROTECTION_TIF": "day", "ALPACA_NATIVE_TRAIL_ENABLE": "0",
        "ALPACA_NATIVE_TRAIL_REQUIRED": "0",
        "ALPACA_EARNINGS_FILTER": "0", "MONTHLY_SL_ENABLE": "0", "MONTHLY_TRAIL_ENABLE": "0",
        "MONTHLY_MIDMONTH_ROTATION": "0", "MONTHLY_REENTRY_BLOCK_ENABLE": "1",
        "MONTHLY_TRAIL_REENTRY_BLOCK_DAYS": "21",
        "ALPACA_PROTECTIVE_TRAIL_ACTIVATE_GAIN_PCT": "3.5",
        "ALPACA_PROTECTIVE_TRAIL_PCT": "3.5", "ALPACA_PROTECTIVE_MIN_LOCK_GAIN_PCT": "0.5",
        "ALPACA_PROTECTIVE_EXIT_RUNTIME_DIR": str(protective_runtime),
        "ALPACA_PROTECTIVE_EXIT_HWM_PATH": str(protective_runtime / "protective_exit_hwm.json"),
        "ALPACA_PROTECTIVE_EXIT_RECEIPT_PATH": str(protective_runtime / "protective_exit_latest.json"),
        "MONTHLY_HWM_STATE_PATH": str(picks_csv.parent / "monthly_hwm.json"),
        "MONTHLY_REENTRY_BLOCK_STATE_PATH": str(picks_csv.parent / "monthly_reentry_block.json"),
    })
    return env


class AdaptiveOwnershipError(RuntimeError):
    """The PAPER lifecycle registry is unsafe to consume or replace."""


def _normalized_symbols(values: Any) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, (str, bytes)):
        raise AdaptiveOwnershipError("invalid_owned_symbols")
    result: set[str] = set()
    try:
        for value in values:
            symbol = str(value or "").strip().upper()
            if not symbol or not symbol.replace(".", "").replace("-", "").isalnum():
                raise AdaptiveOwnershipError("invalid_owned_symbol")
            result.add(symbol)
    except TypeError as exc:
        raise AdaptiveOwnershipError("invalid_owned_symbols") from exc
    return result


def _atomic_write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _load_owned_symbols(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AdaptiveOwnershipError("invalid_ownership_registry") from exc
    if not isinstance(raw, dict) or raw.get("schema_id") != OWNERSHIP_SCHEMA_ID:
        raise AdaptiveOwnershipError("invalid_ownership_registry")
    return _normalized_symbols(raw.get("owned_symbols"))


def stage_adaptive_owned_symbols(
    registry_path: Path,
    *,
    previous_cycle_symbols: Any,
    selected_symbols: Any,
) -> set[str]:
    """Fail-safely retain old PAPER ownership across a selection refresh."""

    owned = (
        _load_owned_symbols(registry_path)
        | _normalized_symbols(previous_cycle_symbols)
        | _normalized_symbols(selected_symbols)
    )
    _atomic_write_private_json(
        registry_path,
        {"schema_id": OWNERSHIP_SCHEMA_ID, "owned_symbols": sorted(owned)},
    )
    return owned


def receipt_identity(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(data).hexdigest()


def reconcile_adaptive_owned_symbols(
    registry_path: Path,
    receipt_path: Path,
    *,
    previous_receipt_identity: str | None,
    run_started_at_utc: datetime,
) -> bool:
    """Prune ownership only from a new authoritative post-bridge snapshot."""

    current_identity = receipt_identity(receipt_path)
    if current_identity is None or current_identity == previous_receipt_identity:
        return False
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
        return False
    report = receipt.get("report")
    truth = report.get("broker_truth_after") if isinstance(report, dict) else None
    if report.get("broker_truth_authoritative") is not True or not isinstance(truth, dict):
        return False
    try:
        generated = datetime.fromisoformat(
            str(truth.get("generated_at_utc") or "").replace("Z", "+00:00")
        )
        started = run_started_at_utc
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        if generated.astimezone(timezone.utc) < started.astimezone(timezone.utc):
            return False
    except (TypeError, ValueError):
        return False
    try:
        broker_symbols = _normalized_symbols(truth.get("position_symbols"))
        owned = _load_owned_symbols(registry_path)
    except AdaptiveOwnershipError:
        return False
    _atomic_write_private_json(
        registry_path,
        {
            "schema_id": OWNERSHIP_SCHEMA_ID,
            "owned_symbols": sorted(owned & broker_symbols),
        },
    )
    return True


def _picks_symbols(path: Path) -> set[str]:
    if not path.exists():
        return set()
    result: set[str] = set()
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "ticker" not in reader.fieldnames:
                raise AdaptiveOwnershipError("invalid_previous_picks_csv")
            for row in reader:
                symbol = str(row.get("ticker") or "").strip().upper()
                if not symbol:
                    raise AdaptiveOwnershipError("invalid_previous_picks_csv")
                result |= _normalized_symbols({symbol})
    except (OSError, csv.Error) as exc:
        raise AdaptiveOwnershipError("invalid_previous_picks_csv") from exc
    return result


def build_bridge_env(
    report: dict[str, Any],
    *,
    picks_csv: Path,
    capital: float,
    target_alloc_pct: float,
    send_orders: bool,
) -> dict[str, str]:
    env = os.environ.copy()
    protective_runtime = picks_csv.parent / "protective_exit"
    exposure = max(0.0, min(1.0, float(report.get("exposure") or 0.0)))
    env.update(
        {
            "ALPACA_PICKS_CSV": str(picks_csv),
            "ALPACA_CURRENT_CYCLE_PICKS_CSV": str(picks_csv),
            "ALPACA_SEND_ORDERS": "1" if send_orders else "0",
            "ALPACA_CLOSE_STALE_POSITIONS": "1",
            "ALPACA_CAPITAL_OVERRIDE_USD": str(max(0.0, capital)),
            "ALPACA_TARGET_ALLOC_PCT": f"{max(0.0, min(1.0, target_alloc_pct / 100.0)) * exposure:.8f}",
            "ALPACA_MAX_POSITIONS": str(max(1, int(report.get("max_positions") or 1))),
            "ALPACA_MIN_DOLLAR_ORDER": "10",
            "ALPACA_ALLOW_STALE_PICKS": "0",
            "ALPACA_REFRESH_UTC": str(report.get("generated_at_utc") or ""),
            "MONTHLY_WEIGHTED_SIZING": "1",
            "MONTHLY_ATR_SIZING": "0",
            "MONTHLY_TRAIL_ENABLE": "1",
            "ALPACA_BROKER_PROTECTION_ENABLE": "1",
            "ALPACA_BROKER_PROTECTION_REQUIRED": "1",
            "ALPACA_BROKER_PROTECTION_ORDER_CLASS": "simple_stop",
            "ALPACA_NATIVE_TRAIL_ENABLE": "0",
            "ALPACA_PROTECTIVE_EXIT_RUNTIME_DIR": str(protective_runtime),
            "ALPACA_PROTECTIVE_EXIT_HWM_PATH": str(
                protective_runtime / "protective_exit_hwm.json"
            ),
            "ALPACA_ALLOW_EMPTY_PICKS_FOR_CASH": (
                "1" if report.get("reason") == "market_below_regime_sma_cash" else "0"
            ),
        }
    )
    return env


def main() -> int:
    ap = argparse.ArgumentParser(description="adaptive_v1 Alpaca paper driver")
    ap.add_argument("--symbols", default="")
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--target-alloc-pct", type=float, default=70.0)
    ap.add_argument("--max-positions", type=int, default=4)
    ap.add_argument("--preset", choices=("baseline", "lively"), default="baseline")
    ap.add_argument("--cache-dir", default="runtime/equities_yf_cache")
    ap.add_argument("--runtime-dir", default="")
    ap.add_argument("--send-orders", action="store_true")
    ap.add_argument(
        "--prepare-intended", action="store_true",
        help="offline-only frozen v38 selection from local completed hourly cache",
    )
    ap.add_argument("--signal-session", default="", help="completed causal YYYY-MM-DD signal session")
    ap.add_argument("--entry-session", default="", help="explicit later YYYY-MM-DD entry session")
    ap.add_argument(
        "--reuse-selection",
        action="store_true",
        help="manage the last daily selection without recalculating or rotating it",
    )
    args = ap.parse_args()

    if args.prepare_intended:
        if args.send_orders:
            print(json.dumps({"error": "prepare_intended_rejects_send_orders"}))
            return 2
        if not args.signal_session or not args.entry_session:
            print(json.dumps({"error": "prepare_intended_requires_signal_and_entry_session"}))
            return 2
        try:
            signal_session = date.fromisoformat(args.signal_session)
            entry_session = date.fromisoformat(args.entry_session)
        except ValueError:
            print(json.dumps({"error": "prepare_intended_sessions_must_be_yyyy_mm_dd"}))
            return 2
        if signal_session >= datetime.now(timezone.utc).date():
            print(json.dumps({"error": "prepare_intended_signal_session_must_be_completed_before_today"}))
            return 2
        cache_dir = Path(args.cache_dir)
        runtime_dir = Path(args.runtime_dir or "runtime/alpaca_intended_paper")
        if not cache_dir.is_absolute():
            cache_dir = ROOT / cache_dir
        if not runtime_dir.is_absolute():
            runtime_dir = ROOT / runtime_dir
        try:
            report = prepare_intended_report(
                _load_intended_hourly_history(cache_dir),
                signal_session=signal_session,
                entry_session=entry_session,
            )
        except (OSError, ValueError, KeyError) as exc:
            print(json.dumps({"error": str(exc), "cache_dir": str(cache_dir)}))
            return 3
        runtime_dir.mkdir(parents=True, exist_ok=True)
        picks_csv = runtime_dir / "current_cycle_picks.csv"
        report_path = runtime_dir / "latest_selection.json"
        write_intended_bridge_picks_csv(report, picks_csv)
        report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        frozen_env = build_intended_bridge_env(report, picks_csv=picks_csv, capital=float(args.capital))
        # Keep only the explicit frozen overrides, never inherited credentials.
        env_path = runtime_dir / "frozen_intended_paper.env"
        env_path.write_text(
            "\n".join(f"{key}={value}" for key, value in sorted(frozen_env.items()) if key.startswith(("ALPACA_", "MONTHLY_"))) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "mode": report["mode"], "orders_submitted": False,
            "signal_session": report["signal_session"], "entry_session": report["entry_session"],
            "picks": [pick["symbol"] for pick in report["picks"]],
            "runtime_dir": str(runtime_dir), "picks_csv": str(picks_csv), "env_path": str(env_path),
        }, ensure_ascii=True))
        return 0

    from scripts.alpaca_adaptive_shadow import run_shadow as legacy_run_shadow
    from scripts.alpaca_adaptive_shadow import write_bridge_picks_csv as legacy_write_bridge_picks_csv
    from scripts.alpaca_v3_event_backtest import DEFAULT_UNIVERSE
    shadow_runner = run_shadow or legacy_run_shadow
    bridge_writer = write_bridge_picks_csv or legacy_write_bridge_picks_csv
    end = args.end or (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    cache_dir = Path(args.cache_dir)
    runtime_dir = Path(args.runtime_dir or "runtime/equities_alpaca_adaptive_v1")
    if not cache_dir.is_absolute():
        cache_dir = ROOT / cache_dir
    if not runtime_dir.is_absolute():
        runtime_dir = ROOT / runtime_dir
    report_path = runtime_dir / "latest_selection.json"
    picks_csv = runtime_dir / "current_cycle_picks.csv"
    ownership_path = runtime_dir / "owned_position_lifecycles.json"
    manager_receipt_path = runtime_dir / "latest_manager_receipt.json"
    try:
        previous_cycle_symbols = _picks_symbols(picks_csv)
    except AdaptiveOwnershipError as exc:
        print(json.dumps({"error": str(exc), "picks_csv": str(picks_csv)}))
        return 4
    if args.reuse_selection:
        if not report_path.exists() or not picks_csv.exists():
            print(json.dumps({"error": "adaptive_selection_missing", "runtime_dir": str(runtime_dir)}))
            return 2
        report = json.loads(report_path.read_text(encoding="utf-8"))
    else:
        symbols = [s.strip().upper() for s in (args.symbols or ",".join(DEFAULT_UNIVERSE)).split(",") if s.strip()]
        report = shadow_runner(
            symbols=symbols,
            start=args.start,
            end=end,
            capital=float(args.capital),
            max_positions=int(args.max_positions),
            cache_dir=cache_dir,
            target_alloc_pct=float(args.target_alloc_pct),
            preset=args.preset,
        )

    if not report.get("picks") and report.get("reason") != "market_below_regime_sma_cash":
        print(json.dumps({"error": "adaptive_selector_empty", "reason": report.get("reason")}, ensure_ascii=True))
        return 3

    runtime_dir.mkdir(parents=True, exist_ok=True)
    selected_symbols = {
        str(item.get("symbol") or "").strip().upper()
        for item in (report.get("picks") or [])
        if str(item.get("symbol") or "").strip()
    }
    try:
        stage_adaptive_owned_symbols(
            ownership_path,
            previous_cycle_symbols=previous_cycle_symbols,
            selected_symbols=selected_symbols,
        )
    except AdaptiveOwnershipError as exc:
        print(json.dumps({"error": str(exc), "registry": str(ownership_path)}))
        return 4
    if not args.reuse_selection:
        report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        bridge_writer(report, picks_csv)
    env = build_bridge_env(
        report,
        picks_csv=picks_csv,
        capital=float(args.capital),
        target_alloc_pct=float(args.target_alloc_pct),
        send_orders=bool(args.send_orders),
    )
    command = [sys.executable, str(ROOT / "scripts" / "equities_alpaca_paper_bridge.py"), "--picks-csv", str(picks_csv)]
    print(
        f"preset={report.get('preset', args.preset)} refresh={not args.reuse_selection} "
        f"mode={'send_orders' if args.send_orders else 'dry_run'} "
        f"picks={','.join(p['symbol'] for p in report.get('picks') or []) or 'cash'}"
    )
    previous_receipt_identity = receipt_identity(manager_receipt_path)
    run_started_at_utc = datetime.now(timezone.utc)
    returncode = subprocess.run(command, cwd=ROOT, env=env, check=False).returncode
    if returncode == 0:
        reconcile_adaptive_owned_symbols(
            ownership_path,
            manager_receipt_path,
            previous_receipt_identity=previous_receipt_identity,
            run_started_at_utc=run_started_at_utc,
        )
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
