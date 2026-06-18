import csv
import json
from pathlib import Path

from scripts.alpaca_adaptive_paper import build_bridge_env
from scripts.alpaca_adaptive_shadow import write_bridge_picks_csv


def _report(**overrides):
    report = {
        "generated_at_utc": "2026-06-18T12:00:00+00:00",
        "max_positions": 4,
        "exposure": 1.0,
        "reason": "ok",
        "picks": [
            {
                "symbol": "AAPL",
                "score": 1.25,
                "weight": 0.28,
                "vol": 0.02,
                "mom_fast": 0.05,
                "mom_slow": 0.12,
                "latest_close": 200.0,
            }
        ],
    }
    report.update(overrides)
    return report


def test_adaptive_csv_preserves_risk_parity_weight_as_bridge_score(tmp_path: Path):
    path = tmp_path / "picks.csv"
    write_bridge_picks_csv(_report(), path)
    with path.open(newline="", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    assert row["month"] == "2026-06"
    assert row["ticker"] == "AAPL"
    assert float(row["score"]) == 0.28
    assert float(row["base_score"]) == 1.25


def test_bridge_env_scales_allocation_by_regime_exposure(tmp_path: Path):
    env = build_bridge_env(
        _report(exposure=0.4),
        picks_csv=tmp_path / "picks.csv",
        capital=1000.0,
        target_alloc_pct=70.0,
        send_orders=False,
    )
    assert float(env["ALPACA_TARGET_ALLOC_PCT"]) == 0.28
    assert env["ALPACA_SEND_ORDERS"] == "0"
    assert env["ALPACA_BROKER_PROTECTION_REQUIRED"] == "1"
    assert env["MONTHLY_ATR_SIZING"] == "0"


def test_empty_cash_is_allowed_only_for_explicit_bear_regime(tmp_path: Path):
    bear = build_bridge_env(
        _report(picks=[], exposure=0.0, reason="market_below_regime_sma_cash"),
        picks_csv=tmp_path / "picks.csv",
        capital=1000.0,
        target_alloc_pct=70.0,
        send_orders=True,
    )
    filtered = build_bridge_env(
        _report(picks=[], exposure=0.0, reason="no_qualifying_names"),
        picks_csv=tmp_path / "picks.csv",
        capital=1000.0,
        target_alloc_pct=70.0,
        send_orders=True,
    )
    assert bear["ALPACA_ALLOW_EMPTY_PICKS_FOR_CASH"] == "1"
    assert filtered["ALPACA_ALLOW_EMPTY_PICKS_FOR_CASH"] == "0"


def test_reusable_selection_files_are_stable_contract(tmp_path: Path):
    report = _report()
    report_path = tmp_path / "latest_selection.json"
    picks_path = tmp_path / "current_cycle_picks.csv"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    write_bridge_picks_csv(report, picks_path)

    loaded = json.loads(report_path.read_text(encoding="utf-8"))
    with picks_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert loaded["picks"][0]["symbol"] == "AAPL"
    assert rows[0]["ticker"] == "AAPL"
