#!/usr/bin/env python3
"""Clean-subset Alpaca v38 daily structural proxy; never promotion evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.alpaca_exact_parity_contract import DailyBar
from backtest.alpaca_honest_portfolio import (
    MonthlyDecision,
    select_v38_successor,
    simulate_live_protection_daily_proxy,
)
from research_lab.run_passport import AUTHORITY, build_passport, write_passport
from strategies.alpaca_dynamic_v4_event import SECTOR_MAP

DATA = ROOT / "research_lab/data/alpaca_pit_daily_v1"
VALIDATION = ROOT / "reports/evidence/ALPACA_PIT_DAILY_VALIDATION_20260812.json"
CLUSTER_CONFIG = ROOT / "configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json"
PREREG = ROOT / "research_lab/prereg/PREREG_ALPACA_CLEAN_V38_PROXY_V1_2026_08_13.md"
DEFAULT_OUT = ROOT / "research_lab/results/alpaca_clean_v38_proxy_v1_20260813"


class ProxyError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_once(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ProxyError(f"write-once output exists: {path}") from exc
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _load_bars(path: Path) -> list[DailyBar]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = list(payload.get("records") or [])
    out = [
        DailyBar(
            session_date=datetime.fromtimestamp(int(row["t"]) / 1000, timezone.utc).date(),
            open=float(row["o"]), high=float(row["h"]),
            low=float(row["l"]), close=float(row["c"]),
        )
        for row in rows
    ]
    dates = [row.session_date for row in out]
    if not out or dates != sorted(set(dates)):
        raise ProxyError(f"invalid daily bars: {path}")
    return out


def _annualized(total_pct: float, first_session: str, last_session: str) -> float:
    start = datetime.fromisoformat(first_session).date()
    end = datetime.fromisoformat(last_session).date()
    years = max((end - start).days / 365.25, 1 / 12)
    multiple = 1.0 + total_pct / 100.0
    return (multiple ** (1.0 / years) - 1.0) * 100.0 if multiple > 0 else -100.0


def run(out: Path) -> dict[str, Any]:
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
    if validation.get("clean_subset_integrity_pass") is not True:
        raise ProxyError("clean subset integrity is not proven")
    quarantined = {str(row["symbol"]) for row in validation.get("quarantined_symbols") or []}
    files = sorted(path for path in (DATA / "bars").glob("*.json") if path.stem not in quarantined)
    if len(files) != int(validation.get("clean_subset_symbols") or -1):
        raise ProxyError("clean subset count differs from validation receipt")
    manifest = {
        "schema_id": "alpaca_clean_v38_proxy_input_manifest_v1",
        "window": {"start_utc": "2024-08-12T00:00:00Z", "end_utc_exclusive": "2026-08-12T00:00:00Z"},
        "validation_sha256": _sha(VALIDATION),
        "symbols": [{"symbol": path.stem, "sha256": _sha(path), "bytes": path.stat().st_size} for path in files],
        "clean_symbols": len(files),
        "quarantined_symbols": sorted(quarantined),
    }
    manifest_path = out / "input_manifest.json"
    _write_once(manifest_path, manifest)
    symbols = [path.stem for path in files]
    request = {
        "schema_id": "research_run_passport_request_v1",
        "authority": AUTHORITY,
        "promotion_authority": False,
        "live_or_broker_calls": False,
        "experiment_id": "alpaca_clean_v38_proxy_v1_20260813",
        "code_paths": [
            "research_lab/alpaca_clean_v38_proxy_v1.py",
            "backtest/alpaca_honest_portfolio.py",
            "backtest/alpaca_exact_parity_contract.py",
            str(PREREG.relative_to(ROOT)),
        ],
        "inputs": [{
            "path": str(manifest_path.relative_to(ROOT)),
            "role": "hashed clean-subset daily manifest",
            "temporal_data": True,
            "contains_sealed_holdout": False,
            "data_window": manifest["window"],
        }],
        "measurement_contract": {
            "engine": "alpaca_v38_cash_aware_live_protection_daily_proxy_v1",
            "timeframe": "adjusted daily observed XNYS-like sessions",
            "costs": {"base_bps_per_side": 5.0, "stress_bps_per_side": 10.0},
            "label_contract": "completed_month_close_to_next_observed_session_open",
            "split_contract": "full_window_plus_monthly_returns",
            "universe": symbols,
            "window": manifest["window"],
        },
        "search_contract": {"variant_count": 1, "random_seed": 20260813, "pre_registered": True},
        "sealed_holdouts": [],
    }
    passport = build_passport(request, project_root=ROOT)
    write_passport(out / "run_passport.json", passport)

    data = {path.stem: _load_bars(path) for path in files}
    reference_symbol = max(data, key=lambda symbol: len(data[symbol]))
    sessions = [row.session_date for row in data[reference_symbol]]
    month_last: dict[str, int] = {}
    for index, session in enumerate(sessions):
        month_last[session.strftime("%Y-%m")] = index
    frozen = json.loads(CLUSTER_CONFIG.read_text(encoding="utf-8"))
    clusters = [{str(symbol) for symbol in group} for group in frozen.get("clusters") or []]
    decisions = []
    selected_rows = []
    for _month, index in sorted(month_last.items()):
        if index + 1 >= len(sessions):
            continue
        signal, entry = sessions[index], sessions[index + 1]
        history = {
            symbol: [bar for bar in rows if bar.session_date <= signal]
            for symbol, rows in data.items()
        }
        history = {
            symbol: rows for symbol, rows in history.items()
            if rows and rows[-1].session_date == signal
        }
        picks = select_v38_successor(history, sectors=SECTOR_MAP, clusters=clusters)
        decisions.append(MonthlyDecision(signal, entry, picks, "ok" if picks else "no_qualifying_names"))
        selected_rows.append({
            "signal_session": signal.isoformat(),
            "entry_session": entry.isoformat(),
            "symbols": [pick.symbol for pick in picks],
            "unknown_sector_symbols": [pick.symbol for pick in picks if pick.symbol not in SECTOR_MAP],
        })

    results = {}
    for name, cost in (("base_5bps_side", 5.0), ("stress_10bps_side", 10.0)):
        replay = simulate_live_protection_daily_proxy(
            data, sessions, decisions,
            initial_capital=1_000.0,
            target_gross_exposure=0.70,
            cost_bps_per_side=cost,
        )
        replay["annualized_return_pct"] = _annualized(
            float(replay["return_pct"]), str(sessions[0]), str(sessions[-1])
        )
        results[name] = replay
    positive = all(float(row["return_pct"]) > 0 for row in results.values())
    result = {
        "schema_id": "alpaca_clean_v38_proxy_result_v1",
        "authority": AUTHORITY,
        "capital_authorized": False,
        "promotion_authorized": False,
        "passport_sha256": passport["passport_sha256"],
        "clean_symbols": len(symbols),
        "reference_calendar_symbol": reference_symbol,
        "observed_sessions": len(sessions),
        "decisions": selected_rows,
        "results": results,
        "verdict": "DIAGNOSTIC_POSITIVE_BOTH" if positive else "DIAGNOSTIC_NOT_POSITIVE_BOTH",
        "exact_live_contract": False,
        "blockers": [
            "full-market point-in-time membership unresolved",
            "complete sector classification absent for expanded universe",
            "authoritative XNYS session ledger absent",
            "delisting/corporate-action cashflows unresolved",
            "daily proxy cannot reproduce 15-minute live protective-stop sampling",
        ],
    }
    _write_once(out / "result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    result = run(args.out.resolve())
    compact = {
        "verdict": result["verdict"],
        "clean_symbols": result["clean_symbols"],
        "observed_sessions": result["observed_sessions"],
        "results": {
            name: {key: row[key] for key in (
                "return_pct", "annualized_return_pct", "daily_max_drawdown_pct",
                "profit_factor_realized", "realized_trades", "red_months", "months",
                "average_gross_exposure_pct",
            )}
            for name, row in result["results"].items()
        },
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
