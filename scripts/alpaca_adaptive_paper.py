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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.alpaca_adaptive_shadow import run_shadow, write_bridge_picks_csv
from scripts.alpaca_v3_event_backtest import DEFAULT_UNIVERSE


OWNERSHIP_SCHEMA_ID = "alpaca_adaptive_paper_owned_positions_v1"


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
    ap.add_argument("--symbols", default=",".join(DEFAULT_UNIVERSE))
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--target-alloc-pct", type=float, default=70.0)
    ap.add_argument("--max-positions", type=int, default=4)
    ap.add_argument("--preset", choices=("baseline", "lively"), default="baseline")
    ap.add_argument("--cache-dir", default="runtime/equities_yf_cache")
    ap.add_argument("--runtime-dir", default="runtime/equities_alpaca_adaptive_v1")
    ap.add_argument("--send-orders", action="store_true")
    ap.add_argument(
        "--reuse-selection",
        action="store_true",
        help="manage the last daily selection without recalculating or rotating it",
    )
    args = ap.parse_args()

    end = args.end or (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    cache_dir = Path(args.cache_dir)
    runtime_dir = Path(args.runtime_dir)
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
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        report = run_shadow(
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
        write_bridge_picks_csv(report, picks_csv)
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
