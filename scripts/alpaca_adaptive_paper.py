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
    report: dict[str, Any], *, picks_csv: Path, capital: float, live: bool = False
) -> dict[str, str]:
    """Frozen endpoint-specific environment; preparation never enables orders."""
    # Do not return inherited credentials; callers can source this generated
    # override file only in a separately approved broker-runtime step.
    env: dict[str, str] = {}
    protective_runtime = picks_csv.parent / "protective_exit"
    env.update({
        "ALPACA_BASE_URL": "https://paper-api.alpaca.markets",
        "ALPACA_INTENDED_PAPER": "1",
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
    if live:
        env.update({"ALPACA_BASE_URL": "https://api.alpaca.markets",
                    "ALPACA_API_BASE_URL": "https://api.alpaca.markets",
                    "ALPACA_INTENDED_PAPER": "0", "ALPACA_INTENDED_LIVE": "1"})
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


def _intended_emergency_exits(client: Any, env: dict[str, str], runtime_dir: Path,
                              account_id: str, *, reason: str = "unprotected_after_reconcile") -> dict[str, Any]:
    from scripts import equities_alpaca_paper_bridge as bridge
    state, error = bridge._load_protective_floor_state(Path(env["ALPACA_PROTECTIVE_EXIT_HWM_PATH"]))
    if error:
        return {"status": "NOT_CONFIRMED", "error": error}
    orders = client.list_orders(status="open", limit=100)
    if len(orders) >= 100:
        return {"status": "NOT_CONFIRMED", "error": "orders_incomplete"}
    scope = []
    for pos in client.list_positions():
        symbol = str(pos.get("symbol") or "")
        record = state.get(symbol)
        if (not isinstance(record, dict) or record.get("account_id") != account_id
            or record.get("strategy_id") != bridge._INTENDED_PAPER_STRATEGY_ID
            or not record.get("entry_order_id")):
            continue
        qty = bridge._intended_finite_positive(pos.get("qty"))
        floor = bridge._intended_finite_positive(record.get("accepted_stop_floor"))
        covered = False
        if qty and floor and not record.get("protection_pending") and reason != "missed_full_session":
            stops = [o for o in orders if o.get("symbol") == symbol and o.get("side") == "sell"]
            if len(stops) == 1:
                try:
                    bridge._confirmed_intended_stop(client, stops[0], symbol=symbol, qty=qty, requested_stop=floor)
                    covered = True
                except Exception:
                    pass
        if not covered:
            scope.append({"symbol": symbol, "entry_order_id": record["entry_order_id"],
                          "qty": record.get("entry_fill_qty", record.get("qty")),
                          "avg_entry_price": record.get("entry_price")})
    if not scope:
        return {"status": "NO_UNPROTECTED_PROVEN_OWNED_POSITION"}
    proof_path = runtime_dir / "emergency_owned_proof.json"
    _atomic_write_private_json(proof_path, {"account_id": account_id, "reason": reason, "positions": scope})
    live = env.get("ALPACA_INTENDED_LIVE") == "1"
    kill_env = {**env, "ALPACA_SEND_ORDERS": "1", "ALPACA_ALLOW_NEW_ENTRIES": "0",
                ("ALPACA_INTENDED_LIVE_KILL_ACK" if live else "ALPACA_PAPER_KILL_ACK"):
                ("INTENDED_OWNED_EXITS_ONLY" if live else "PAPER_OWNED_EXITS_ONLY")}
    result = subprocess.run([sys.executable, str(ROOT / "scripts/equities_alpaca_paper_bridge.py"),
        "--intended-live-kill-owned" if live else "--paper-kill-owned", str(proof_path), "--apply-kill"], cwd=ROOT, env=kill_env,
        check=False, capture_output=True, text=True, timeout=240)
    return {"returncode": result.returncode, "receipt_path": str(runtime_dir / "paper_kill_receipt.json"),
            "scope": [row["symbol"] for row in scope], "stdout": result.stdout, "stderr": result.stderr}


def _intended_missed_session(client: Any, last: datetime, now: datetime) -> bool:
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    if last.astimezone(ny).date() == now.astimezone(ny).date():
        return False
    start = max(last.date(), now.date() - timedelta(days=31))
    rows = client._request("GET", f"/v2/calendar?start={start.isoformat()}&end={now.date().isoformat()}")
    if not isinstance(rows, list):
        raise ValueError("broker_calendar_invalid")
    for row in rows:
        opening = datetime.fromisoformat(f"{row['date']}T{row['open']}").replace(tzinfo=ny)
        closing = datetime.fromisoformat(f"{row['date']}T{row['close']}").replace(tzinfo=ny)
        if last < opening and closing < now:
            return True
    return False


def run_intended_cycle(runtime_dir: Path, *, capital: float, send_orders: bool,
                       client: Any = None, live: bool = False) -> int:
    """Run one bound intended cycle using the existing bridge and ratchet."""
    import fcntl
    from zoneinfo import ZoneInfo
    from scripts import equities_alpaca_paper_bridge as bridge

    runtime_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = runtime_dir / "latest_intended_run.json"
    receipt: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "live_monthly_canary" if live else "paper_operational_acceptance_not_monthly_strategy_evidence",
        "money_authority": False, "paper_orders_enabled": send_orders and not live,
    }
    lock = (runtime_dir / ".runner.lock").open("a")
    account: dict[str, Any] = {}
    clock: dict[str, Any] = {}
    env: dict[str, str] = {}
    try:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 75
        previous = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
        if previous.get("last_regular_success_at_utc"):
            receipt["last_regular_success_at_utc"] = previous["last_regular_success_at_utc"]
        base = os.getenv("ALPACA_BASE_URL", "").rstrip("/")
        binding = None
        if live:
            binding = bridge._load_intended_live_binding(base_url=base, capital=capital, require_enabled=send_orders)
            if binding.get("selector_source_hashes") != _frozen_source_hashes():
                raise ValueError("intended_live_source_hash_mismatch")
        elif base != bridge._PAPER_API_URL:
            raise ValueError("intended_runner_requires_exact_paper")
        report = json.loads((runtime_dir / "latest_selection.json").read_text())
        if (report.get("mode") != "intended_prepare_only"
            or report.get("capital_usd" if live else "paper_capital_usd") != capital
            or report.get("target_gross_exposure") != .70
            or report.get("maximum_weight") != .60 or report.get("max_positions") != 4
            or report.get("selector_source_hashes") != _frozen_source_hashes()):
            raise ValueError("frozen_selection_or_capital_mismatch")
        picks = runtime_dir / "current_cycle_picks.csv"
        expected = {p["symbol"]: p for p in report.get("picks", [])}
        parsed = bridge._load_picks(picks, None)
        if {p.ticker for p in parsed} != set(expected) or len(parsed) != len(expected):
            raise ValueError("frozen_picks_csv_mismatch")
        for pick in parsed:
            row = expected[pick.ticker]
            if (pick.weight != row["weight"] or pick.entry_price != row["signal_close"]
                or pick.stop_price != row["stop_price"] or pick.entry_day != report["entry_session"]):
                raise ValueError("frozen_picks_values_mismatch")
        ownership = json.loads((runtime_dir / "foreign_owners.json").read_text())
        foreign = ownership.get("owners")
        if not isinstance(foreign, dict) or any(not owner for owner in foreign.values()):
            raise ValueError("foreign_ownership_invalid")
        client = client or bridge.AlpacaClient(base, os.environ["ALPACA_API_KEY_ID"], os.environ["ALPACA_API_SECRET_KEY"])
        account = client.get_account()
        if live:
            fresh_binding = bridge._load_intended_live_binding(base_url=base,
                account_id=str(account.get("id") or ""), capital=capital, require_enabled=send_orders)
            if fresh_binding != binding:
                raise ValueError("intended_live_binding_changed")
            receipt["money_authority"] = bool(send_orders)
            receipt["monthly_schedule"] = validate_intended_live_schedule(client, report)
        if account.get("id") != ownership.get("account_id"):
            raise ValueError("paper_account_identity_mismatch")
        if account.get("trading_blocked") or account.get("account_blocked"):
            raise ValueError("paper_account_blocked")
        clock = client.get_clock()
        positions = client.list_positions()
        orders = client.list_orders(status="open", limit=100)
        if len(orders) >= 100:
            raise ValueError("broker_orders_snapshot_incomplete")
        env = os.environ.copy()
        env.update(build_intended_bridge_env(report, picks_csv=picks, capital=capital, live=live))
        state_path = Path(env["ALPACA_PROTECTIVE_EXIT_HWM_PATH"])
        state, error = bridge._load_protective_floor_state(state_path)
        if error not in {"", "state_missing"}:
            raise ValueError("intended_state_corrupt")
        if set(state) & set(foreign):
            raise ValueError("intended_foreign_ownership_overlap")
        unknown = {str(p.get("symbol") or "") for p in positions} - set(state) - set(foreign)
        if unknown:
            raise ValueError("unknown_position:" + ",".join(sorted(unknown)))
        if any(str(o.get("symbol") or "") not in set(state) | set(foreign) for o in orders):
            raise ValueError("unknown_active_order")
        receipt.update({"account_id": account["id"], "market_open": bool(clock.get("is_open")),
                        "foreign_positions": sorted({p["symbol"] for p in positions} & set(foreign)),
                        "owned_positions": sorted({p["symbol"] for p in positions} & set(state)),
                        "next_open": clock.get("next_open"), "entry_session": report["entry_session"]})
        if not send_orders or not clock.get("is_open"):
            receipt["status"] = "WAITING_FOR_REGULAR_SESSION" if send_orders else ("LIVE_READ_ONLY_READY" if live else "PAPER_READ_ONLY_READY")
            _atomic_write_private_json(receipt_path, receipt)
            return 0
        # Explicit one-session broker acceptance launch, never daily strategy reselection.
        session = datetime.fromisoformat(str(clock["timestamp"]).replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York")).date()
        prior_success = receipt.get("last_regular_success_at_utc")
        if state and prior_success:
            last = datetime.fromisoformat(str(prior_success).replace("Z", "+00:00"))
            now = datetime.fromisoformat(str(clock["timestamp"]).replace("Z", "+00:00"))
            if _intended_missed_session(client, last, now):
                receipt["emergency"] = _intended_emergency_exits(client, env, runtime_dir,
                    str(account["id"]), reason="missed_full_session")
                raise RuntimeError("missed_full_regular_session")
        env["ALPACA_SEND_ORDERS"] = "1"
        env["ALPACA_ALLOW_NEW_ENTRIES"] = "1" if session.isoformat() == report["entry_session"] else "0"
        env["ALPACA_ALLOW_EMPTY_PICKS_FOR_CASH"] = "1"
        excluded_path = runtime_dir / "foreign_exclusions.json"
        _atomic_write_private_json(excluded_path, foreign)
        env["ALPACA_INTRADAY_STATE_PATH"] = str(excluded_path)
        env["ALPACA_INTRADAY_ADVISORY_PATH"] = str(runtime_dir / "no_intraday_advisory.json")
        env["ALPACA_PROTECTIVE_EXIT_EXCLUDED_SYMBOLS"] = ",".join(sorted(foreign))
        if error == "state_missing":
            _atomic_write_private_json(state_path, {})
        commands = [
            [sys.executable, str(ROOT / "scripts/equities_alpaca_paper_bridge.py"), "--picks-csv", str(picks)],
            [sys.executable, str(ROOT / "scripts/alpaca_protective_exit_manager.py"), "--apply"],
        ]
        receipt["stages"] = []
        for index, command in enumerate(commands):
            if index == 1:
                env["ALPACA_ALLOW_NEW_ENTRIES"] = "0"
                env["ALPACA_PROTECTIVE_EXIT_ACK"] = "PROTECTIVE_EXITS_ONLY"
            result = subprocess.run(command, cwd=ROOT, env=env, check=False,
                                    capture_output=True, text=True, timeout=240)
            with (runtime_dir / "execution.log").open("a") as log:
                os.chmod(log.name, 0o600)
                log.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(),
                    "stage": index, "returncode": result.returncode,
                    "stdout": result.stdout, "stderr": result.stderr}) + "\n")
            receipt["stages"].append({"stage": "bridge" if index == 0 else "ratchet", "returncode": result.returncode})
            if result.returncode:
                receipt["emergency"] = _intended_emergency_exits(client, env, runtime_dir, str(account["id"]))
                raise RuntimeError(f"intended_stage_failed:{index}:{result.returncode}")
        receipt["status"] = "LIVE_CYCLE_COMPLETE" if live else "PAPER_CYCLE_COMPLETE"
        receipt["last_regular_success_at_utc"] = str(clock["timestamp"])
        _atomic_write_private_json(receipt_path, receipt)
        return 0
    except Exception as exc:
        if send_orders and account.get("id") and (base == bridge._PAPER_API_URL or (live and base == "https://api.alpaca.markets")):
            try:
                bridge._halt_intended_paper_entries(
                    bridge._paper_kill_state_dir(base, os.environ["ALPACA_API_KEY_ID"]),
                    str(account["id"]), str(exc))
                if send_orders and clock.get("is_open") and env and "emergency" not in receipt:
                    receipt["emergency"] = _intended_emergency_exits(client, env, runtime_dir, str(account["id"]))
            except Exception as emergency_error:
                receipt["emergency_error"] = str(emergency_error)
        receipt.update({"status": "HALTED", "error": f"{type(exc).__name__}:{exc}"})
        _atomic_write_private_json(receipt_path, receipt)
        return 9
    finally:
        lock.close()


def validate_intended_live_schedule(client: Any, report: dict[str, Any]) -> dict[str, Any]:
    """Check the frozen month-end/next-open rule against the broker calendar."""
    import calendar
    signal = date.fromisoformat(str(report["signal_session"]))
    entry = date.fromisoformat(str(report["entry_session"]))
    next_month = (signal.replace(day=28) + timedelta(days=4)).replace(day=1)
    if entry.year != next_month.year or entry.month != next_month.month:
        raise ValueError("intended_live_requires_monthly_schedule")
    start = signal.replace(day=1)
    end = entry.replace(day=calendar.monthrange(entry.year, entry.month)[1])
    rows = client._request("GET", f"/v2/calendar?start={start.isoformat()}&end={end.isoformat()}")
    if not isinstance(rows, list) or not rows:
        raise ValueError("intended_monthly_calendar_missing")
    sessions = [date.fromisoformat(str(row["date"])) for row in rows]
    if len(set(sessions)) != len(sessions) or any(d < start or d > end for d in sessions):
        raise ValueError("intended_monthly_calendar_invalid")
    prior = [d for d in sessions if (d.year, d.month) == (signal.year, signal.month)]
    following = [d for d in sessions if (d.year, d.month) == (entry.year, entry.month)]
    if not prior or not following or signal != max(prior) or entry != min(following):
        raise ValueError("intended_live_requires_monthly_schedule")
    return {"signal_session": signal.isoformat(), "entry_session": entry.isoformat(),
            "calendar_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()}


def preflight_intended_live(runtime_dir: Path, *, client: Any = None) -> int:
    """Validate initial LIVE account binding with GETs only; never dispatch orders."""
    from scripts import equities_alpaca_paper_bridge as bridge
    receipt: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "money_authority": False, "broker_writes": 0, "activation_ready": False,
        "execution_binding_complete": False,
    }
    try:
        base = os.getenv("ALPACA_BASE_URL", "").rstrip("/")
        binding = bridge._load_intended_live_binding(base_url=base)
        if binding.get("selector_source_hashes") != _frozen_source_hashes():
            raise ValueError("intended_live_source_hash_mismatch")
        key = os.environ.get("ALPACA_API_KEY_ID", "")
        secret = os.environ.get("ALPACA_API_SECRET_KEY", "")
        if not key or not secret:
            raise ValueError("intended_live_credentials_missing")
        client = client or bridge.AlpacaClient(base, key, secret)
        account = client.get_account()
        if binding != bridge._load_intended_live_binding(base_url=base, account_id=str(account.get("id") or "")):
            raise ValueError("intended_live_binding_changed_during_preflight")
        if (account.get("status") != "ACTIVE" or account.get("currency") != "USD"
            or account.get("trading_blocked") or account.get("account_blocked")):
            raise ValueError("intended_live_account_not_eligible")
        cash = bridge._intended_finite_positive(account.get("cash"))
        if cash is None:
            raise ValueError("intended_live_cash_not_confirmed")
        if binding["capital_usd"] is not None and float(binding["capital_usd"]) > cash:
            raise ValueError("intended_live_capital_exceeds_cash")
        clock = client.get_clock()
        positions = client.list_positions()
        orders = client.list_orders(status="open", limit=100)
        if not isinstance(positions, list) or not isinstance(orders, list) or len(orders) >= 100:
            raise ValueError("intended_live_truth_incomplete")
        # Initial binding cannot quietly adopt an OLD lifecycle or pending order.
        if positions or orders:
            raise ValueError("intended_live_initial_binding_requires_flat_account")
        binding_bytes = Path(os.environ["ALPACA_INTENDED_LIVE_BINDING_PATH"]).read_bytes()
        if json.loads(binding_bytes) != binding:
            raise ValueError("intended_live_binding_changed_during_preflight")
        receipt.update({
            "status": "LIVE_ACCOUNT_BOUND_READ_ONLY", "endpoint": base,
            "account_id": account["id"], "cash_usd": cash,
            "capital_usd": binding["capital_usd"], "binding_enabled": binding["enabled"],
            "positions_count": len(positions), "open_orders_count": len(orders),
            "market_open": clock.get("is_open"), "next_open": clock.get("next_open"),
            "strategy_id": binding["strategy_id"],
            "selector_source_hashes": binding["selector_source_hashes"],
            "binding_sha256": hashlib.sha256(binding_bytes).hexdigest(),
        })
        _atomic_write_private_json(runtime_dir / "live_binding_preflight.json", receipt)
        return 0
    except Exception as exc:
        receipt.update({"status": "NOT_CONFIRMED", "error": f"{type(exc).__name__}:{exc}"})
        _atomic_write_private_json(runtime_dir / "live_binding_preflight.json", receipt)
        return 9


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
    ap.add_argument("--preserve-only", action="store_true", help="legacy PAPER protection with new entries and stale rotation disabled")
    ap.add_argument("--preflight-intended-live", action="store_true", help="GET-only initial LIVE account binding; cannot submit orders")
    ap.add_argument("--run-intended-live", action="store_true", help="run explicitly account-bound frozen LIVE lifecycle; disabled without binding approval")
    ap.add_argument("--run-intended", action="store_true", help="run frozen one-session PAPER acceptance and ongoing protection")
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

    if args.preflight_intended_live:
        if args.send_orders or args.run_intended or args.run_intended_live or args.prepare_intended or args.preserve_only:
            print(json.dumps({"error": "live_preflight_rejects_order_or_execution_flags"}))
            return 2
        runtime_dir = Path(args.runtime_dir or "runtime/alpaca_intended_live").resolve()
        return preflight_intended_live(runtime_dir)

    if args.run_intended_live and (args.run_intended or args.prepare_intended or args.preserve_only):
        print(json.dumps({"error": "conflicting_intended_execution_modes"}))
        return 2
    if args.run_intended or args.run_intended_live:
        runtime_dir = Path(args.runtime_dir or ("runtime/alpaca_intended_live" if args.run_intended_live else "runtime/alpaca_intended_paper")).resolve()
        result = run_intended_cycle(runtime_dir, capital=float(args.capital), send_orders=bool(args.send_orders), live=bool(args.run_intended_live))
        print(json.dumps({"intended_runner_returncode": result, "receipt": str(runtime_dir / "latest_intended_run.json")}))
        return result

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
        report["paper_capital_usd"] = float(args.capital)
        report["capital_usd"] = float(args.capital)
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
    if args.preserve_only:
        env["ALPACA_ALLOW_NEW_ENTRIES"] = "0"
        env["ALPACA_CLOSE_STALE_POSITIONS"] = "0"
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
