import json
from datetime import datetime, timezone

from bot.alpaca_truth import build_alpaca_live_truth


def _safe_hold(root):
    cfg = root / "configs"
    cfg.mkdir(parents=True)
    (cfg / "alpaca_live_v38_safe_hold.env").write_text(
        "ALPACA_ALLOW_NEW_ENTRIES=0\nALPACA_CLOSE_STALE_POSITIONS=0\n",
        encoding="utf-8",
    )


def test_prefers_post_action_manager_receipt(tmp_path):
    _safe_hold(tmp_path)
    out = tmp_path / "runtime" / "equities_monthly_v36"
    out.mkdir(parents=True)
    now = datetime.now(timezone.utc).isoformat()
    (out / "latest_manager_receipt.json").write_text(
        json.dumps(
            {
                "generated_at_utc": now,
                "report": {
                    "status": "send_orders",
                    "broker_truth_authoritative": True,
                    "broker_truth_after": {
                        "generated_at_utc": now,
                        "account": {"equity": "485.5"},
                        "positions": [{"symbol": "GE", "qty": "2", "market_value": "720", "avg_entry_price": "357.83"}],
                        "open_stops": [{"symbol": "GE", "type": "stop", "status": "new", "qty": "2", "protected_remaining_qty": 2.0, "stop_price": "338.66"}],
                        "position_symbols": ["GE"],
                        "stop_symbols": ["GE"],
                        "missing_stop_symbols": [],
                        "underprotected_stop_symbols": [],
                        "overprotected_stop_symbols": [],
                        "protection_gap_symbols": [],
                        "position_qty_by_symbol": {"GE": 2.0},
                        "protected_qty_by_symbol": {"GE": 2.0},
                        "stop_coverage_count": 1,
                        "position_count": 1,
                        "stop_coverage_complete": True,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    truth = build_alpaca_live_truth(tmp_path)

    assert truth["source"] == "monthly_manager_post_action_receipt"
    assert truth["mode"] == "SAFE_HOLD"
    assert truth["authoritative"] is True
    assert truth["position_symbols"] == ["GE"]
    assert truth["positions"][0]["entry_price"] == 357.83
    assert truth["positions"][0]["last_price"] == 360.0
    assert truth["positions"][0]["stop_price"] == 338.66
    assert truth["stop_coverage_complete"] is True
    assert truth["research_metrics_are_live_pnl"] is False


def test_account_state_fallback_marks_missing_stop(tmp_path):
    _safe_hold(tmp_path)
    out = tmp_path / "runtime" / "alpaca_live_v38"
    out.mkdir(parents=True)
    (out / "account_state.json").write_text(
        json.dumps(
            {
                "generated_at_utc": "2026-07-14T05:00:00Z",
                "account": {"equity": "485.0"},
                "positions": [{"symbol": "ABBV"}, {"symbol": "GE"}],
                "open_orders": [
                    {"symbol": "ABBV", "side": "sell", "type": "stop", "status": "new"},
                    {"symbol": "GE", "side": "sell", "type": "limit", "status": "new"},
                ],
            }
        ),
        encoding="utf-8",
    )

    truth = build_alpaca_live_truth(tmp_path)

    assert truth["source"] == "alpaca_live_v38_account_state"
    assert truth["stop_symbols"] == ["ABBV"]
    assert truth["missing_stop_symbols"] == ["GE"]
    assert truth["stop_coverage_complete"] is False


def test_empty_live_account_has_complete_zero_over_zero_coverage(tmp_path):
    _safe_hold(tmp_path)
    out = tmp_path / "runtime" / "alpaca_live_v38"
    out.mkdir(parents=True)
    (out / "account_state.json").write_text(
        json.dumps({"generated_at_utc": "2026-07-14T05:00:00Z", "positions": [], "open_orders": []}),
        encoding="utf-8",
    )

    truth = build_alpaca_live_truth(tmp_path)

    assert truth["position_count"] == 0
    assert truth["stop_coverage_count"] == 0
    assert truth["stop_coverage_complete"] is True


def test_fresh_receipt_without_post_action_refresh_is_not_authoritative(tmp_path):
    _safe_hold(tmp_path)
    out = tmp_path / "runtime" / "equities_monthly_v36"
    out.mkdir(parents=True)
    now = datetime.now(timezone.utc).isoformat()
    (out / "latest_manager_receipt.json").write_text(
        json.dumps(
            {
                "generated_at_utc": now,
                "report": {
                    "status": "send_orders",
                    "broker_truth_authoritative": False,
                    "broker_truth_refresh_error": "timeout",
                    "broker_truth_after": {
                        "generated_at_utc": now,
                        "account": {"equity": "485"},
                        "positions": [],
                        "open_stops": [],
                        "position_symbols": [],
                        "stop_symbols": [],
                        "missing_stop_symbols": [],
                        "stop_coverage_count": 0,
                        "position_count": 0,
                        "stop_coverage_complete": True,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    truth = build_alpaca_live_truth(tmp_path)

    assert truth["exists"] is True
    assert truth["is_stale"] is False
    assert truth["authoritative"] is False
