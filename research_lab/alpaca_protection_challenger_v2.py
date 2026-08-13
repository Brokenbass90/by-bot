#!/usr/bin/env python3
"""Frozen three-arm Alpaca stop/gap contract diagnostic on clean-962 data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_PATH = Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

from backtest.alpaca_honest_portfolio import (
    LiveProtectionDailyProxy,
    MonthlyDecision,
    select_v38_successor,
    simulate_live_protection_daily_proxy,
)
from research_lab.alpaca_clean_v38_proxy_v1 import (
    CLUSTER_CONFIG,
    DATA,
    ROOT,
    SECTOR_MAP,
    _annualized,
    _load_bars,
)
from research_lab.run_passport import AUTHORITY, build_passport, write_passport


V1_ROOT = ROOT / "research_lab/results/alpaca_clean_v38_proxy_v1_20260813"
PREREG = ROOT / "research_lab/prereg/PREREG_ALPACA_PROTECTION_CHALLENGER_V2_2026_08_13.md"
DEFAULT_OUT = ROOT / "research_lab/results/alpaca_protection_challenger_v2_20260813"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_once(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)


def run(out: Path) -> dict[str, Any]:
    manifest_path = V1_ROOT / "input_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in manifest["symbols"]:
        path = DATA / "bars" / f"{row['symbol']}.json"
        if _sha(path) != row["sha256"]:
            raise RuntimeError(f"input drift: {row['symbol']}")
    symbols = [str(row["symbol"]) for row in manifest["symbols"]]
    data = {symbol: _load_bars(DATA / "bars" / f"{symbol}.json") for symbol in symbols}
    reference_symbol = max(data, key=lambda symbol: len(data[symbol]))
    sessions = [row.session_date for row in data[reference_symbol]]
    month_last: dict[str, int] = {}
    for index, session in enumerate(sessions):
        month_last[session.strftime("%Y-%m")] = index
    frozen = json.loads(CLUSTER_CONFIG.read_text(encoding="utf-8"))
    clusters = [{str(symbol) for symbol in group} for group in frozen.get("clusters") or []]
    decisions: list[MonthlyDecision] = []
    for index in (month_last[key] for key in sorted(month_last)):
        if index + 1 >= len(sessions):
            continue
        signal, entry = sessions[index], sessions[index + 1]
        history = {
            symbol: [bar for bar in rows if bar.session_date <= signal]
            for symbol, rows in data.items()
        }
        history = {symbol: rows for symbol, rows in history.items() if rows and rows[-1].session_date == signal}
        picks = select_v38_successor(history, sectors=SECTOR_MAP, clusters=clusters)
        decisions.append(MonthlyDecision(signal, entry, picks, "ok" if picks else "no_qualifying_names"))

    request = {
        "schema_id": "research_run_passport_request_v1",
        "authority": AUTHORITY,
        "promotion_authority": False,
        "live_or_broker_calls": False,
        "experiment_id": "alpaca_protection_challenger_v2_20260813",
        "code_paths": [
            "research_lab/alpaca_protection_challenger_v2.py",
            "backtest/alpaca_honest_portfolio.py",
            "backtest/alpaca_exact_parity_contract.py",
            str(PREREG.relative_to(ROOT)),
        ],
        "inputs": [{
            "path": str(manifest_path.relative_to(ROOT)),
            "role": "hashed clean-962 manifest",
            "temporal_data": True,
            "contains_sealed_holdout": False,
            "data_window": manifest["window"],
        }],
        "measurement_contract": {
            "engine": "alpaca_clean962_three_arm_daily_proxy_v2",
            "timeframe": "completed monthly signal to next observed daily open",
            "costs": {"base_bps_per_side": 5.0, "stress_bps_per_side": 10.0},
            "label_contract": "cash-aware portfolio, broker-like stops, next-close ratchet",
            "split_contract": "fixed full window plus monthly returns; no selection",
            "universe": symbols,
            "window": manifest["window"],
        },
        "search_contract": {"variant_count": 3, "random_seed": 20260813, "pre_registered": True},
        "sealed_holdouts": [],
    }
    passport = build_passport(request, project_root=ROOT)
    write_passport(out / "run_passport.json", passport)
    policies = {
        "current_contract": LiveProtectionDailyProxy(),
        "entry_relative_stop": LiveProtectionDailyProxy(initial_stop_anchor="entry_fill"),
        "entry_stop_gap2": LiveProtectionDailyProxy(
            initial_stop_anchor="entry_fill", maximum_positive_entry_gap_pct=2.0
        ),
    }
    results: dict[str, Any] = {}
    for arm, policy in policies.items():
        results[arm] = {}
        for cost_name, cost in (("base", 5.0), ("stress", 10.0)):
            replay = simulate_live_protection_daily_proxy(
                data, sessions, decisions, initial_capital=1_000.0,
                target_gross_exposure=0.70, cost_bps_per_side=cost, policy=policy,
            )
            replay["annualized_return_pct"] = _annualized(
                float(replay["return_pct"]), str(sessions[0]), str(sessions[-1])
            )
            results[arm][cost_name] = replay
    baseline = results["current_contract"]
    gates: dict[str, bool] = {}
    for arm in ("entry_relative_stop", "entry_stop_gap2"):
        gates[arm] = all(
            results[arm][case]["daily_max_drawdown_pct"] < baseline[case]["daily_max_drawdown_pct"]
            and results[arm][case]["annualized_return_pct"] >= baseline[case]["annualized_return_pct"]
            and results[arm][case]["profit_factor_realized"] >= baseline[case]["profit_factor_realized"]
            and results[arm][case]["realized_trades"] >= 30
            for case in ("base", "stress")
        )
    result = {
        "schema_id": "alpaca_protection_challenger_v2_result",
        "authority": AUTHORITY,
        "capital_authorized": False,
        "exact_live_contract": False,
        "passport_sha256": passport["passport_sha256"],
        "results": results,
        "diagnostic_gates": gates,
        "verdict": "CHALLENGER_SURVIVES" if any(gates.values()) else "NO_CHALLENGER_SURVIVES",
        "blockers": [
            "full-market PIT membership", "sector completeness", "corporate actions",
            "authoritative XNYS calendar", "15-minute protective-manager parity",
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
        arm: {
            case: {key: row[key] for key in (
                "annualized_return_pct", "daily_max_drawdown_pct",
                "profit_factor_realized", "realized_trades", "red_months",
            )}
            for case, row in cases.items()
        }
        for arm, cases in result["results"].items()
    }
    print(json.dumps({"verdict": result["verdict"], "gates": result["diagnostic_gates"], "results": compact}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
