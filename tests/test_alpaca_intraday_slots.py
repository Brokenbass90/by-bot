#!/usr/bin/env python3
from __future__ import annotations

import sys
import csv
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_monthly_positions_do_not_consume_intraday_slots():
    from scripts.equities_alpaca_intraday_bridge import _position_slot_views

    intraday, visible = _position_slot_views(
        state_symbols=[],
        remote_only_symbols=[],
        protected_remote_symbols=["AMD", "GE", "LLY", "SNOW"],
        pending_close_symbols=[],
    )

    assert intraday == []
    assert visible == ["AMD", "GE", "LLY", "SNOW"]


def test_intraday_slots_still_count_intraday_and_unknown_remote_positions():
    from scripts.equities_alpaca_intraday_bridge import _position_slot_views

    intraday, visible = _position_slot_views(
        state_symbols=["TSLA"],
        remote_only_symbols=["JPM"],
        protected_remote_symbols=["AMD"],
        pending_close_symbols=["GOOGL"],
    )

    assert intraday == ["GOOGL", "JPM", "TSLA"]
    assert visible == ["AMD", "GOOGL", "JPM", "TSLA"]


def test_position_not_found_cleanup_error_is_idempotent_only_for_known_alpaca_code():
    from scripts.equities_alpaca_intraday_bridge import AlpacaHttpError, _is_position_not_found_error

    gone = AlpacaHttpError(
        "DELETE",
        "https://paper-api.alpaca.markets/v2/positions/JPM",
        404,
        '{"code":40410000,"message":"position not found: JPM"}',
    )
    unrelated = AlpacaHttpError("GET", "https://example.test/missing", 404, "not found")

    assert _is_position_not_found_error(gone) is True
    assert _is_position_not_found_error(unrelated) is False


def test_monthly_ownership_unions_legacy_and_adaptive_cycles(tmp_path, monkeypatch):
    from scripts import equities_alpaca_intraday_bridge as bridge

    legacy = tmp_path / "runtime" / "equities_monthly_v36" / "current_cycle_picks.csv"
    adaptive = tmp_path / "runtime" / "equities_alpaca_adaptive_v1" / "current_cycle_picks.csv"
    adaptive_ownership = adaptive.parent / "owned_position_lifecycles.json"
    for path, symbols in ((legacy, ["GE", "SNOW"]), (adaptive, ["AAPL", "JPM", "UNH"])):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["ticker"])
            writer.writeheader()
            for symbol in symbols:
                writer.writerow({"ticker": symbol})
    adaptive_ownership.write_text(
        json.dumps(
            {
                "schema_id": "alpaca_adaptive_paper_owned_positions_v1",
                "owned_symbols": ["TMO", "UNH"],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(bridge, "ROOT", tmp_path)
    monkeypatch.setattr(bridge, "MONTHLY_RUNTIME_DIR", legacy.parent)
    monkeypatch.delenv("ALPACA_CURRENT_CYCLE_PICKS_CSV", raising=False)
    monkeypatch.delenv("ALPACA_ADAPTIVE_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("ALPACA_AUTOPILOT_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("EQ_V35_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("EQ_BASELINE_RUNTIME_DIR", raising=False)

    assert bridge._load_monthly_managed_symbols() == {
        "AAPL",
        "GE",
        "JPM",
        "SNOW",
        "TMO",
        "UNH",
    }


def test_malformed_adaptive_ownership_registry_disables_cleanup(tmp_path, monkeypatch):
    from scripts import equities_alpaca_intraday_bridge as bridge

    adaptive_dir = tmp_path / "runtime" / "equities_alpaca_adaptive_v1"
    adaptive_dir.mkdir(parents=True)
    (adaptive_dir / "owned_position_lifecycles.json").write_text(
        '{"schema_id":"wrong","owned_symbols":["TMO"]}',
        encoding="utf-8",
    )

    monkeypatch.setattr(bridge, "ROOT", tmp_path)
    monkeypatch.setattr(
        bridge,
        "MONTHLY_RUNTIME_DIR",
        tmp_path / "runtime" / "equities_monthly_v36",
    )
    monkeypatch.delenv("ALPACA_CURRENT_CYCLE_PICKS_CSV", raising=False)
    monkeypatch.delenv("ALPACA_ADAPTIVE_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("ALPACA_AUTOPILOT_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("EQ_V35_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("EQ_BASELINE_RUNTIME_DIR", raising=False)

    with pytest.raises(bridge.MonthlyOwnershipRegistryError):
        bridge._load_monthly_managed_symbols()
