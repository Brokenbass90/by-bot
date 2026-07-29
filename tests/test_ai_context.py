import json
import os
import time
from pathlib import Path

from bot.ai_context import append_ai_context_lines, compact_ai_full_context


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_compact_ai_context_includes_open_positions(tmp_path):
    root = tmp_path
    _write_json(
        root / "runtime" / "ai_context" / "full_context.json",
        {
            "generated_at_utc": "2026-06-11T12:00:00Z",
            "sources_used": {"heartbeat": "runtime/bot_heartbeat.json", "live_positions": "runtime/live_positions.json"},
            "heartbeat": {"open_trades": 1, "trade_on": True, "dry_run": False, "regime": "bear_chop"},
            "git_revision": {"head": "abc123"},
            "ai_context_brief": "HOUSE RULES",
            "technology_registry": {
                "schema_id": "technology_inventory_v2",
                "authority": "static_inventory_not_promotion_evidence",
                "totals": {"modules": 3},
            },
            "att1_edge_health": {"status": "watch", "n": 4},
            "pnl_by_sleeve_usd": {
                "lookback_days": 45,
                "rows": [{"strategy": "att1_trendline_touch", "trades": 4, "pnl_usd": -1.23}],
            },
            "alpaca_account_state": {
                "api_snapshot": {"account": {"equity": "494.90"}, "open_orders": []},
            },
            "errors_tail": {"path": "runtime/live.out", "lines": ["ok"]},
            "open_positions": {
                "count": 1,
                "dry_run": False,
                "trade_on": True,
                "ts": 1781190000,
                "positions": [
                    {
                        "symbol": "LTCUSDT",
                        "side": "Sell",
                        "strategy": "att1_trendline_touch",
                        "entry": 42.57,
                        "current": 42.07,
                        "qty": 0.6,
                        "sl": 42.58,
                        "tp": None,
                        "tp_model": "runner_ladder",
                        "exchange_tp": None,
                        "runner": {
                            "enabled": True,
                            "targets": [
                                {"index": 1, "price": 41.9, "frac": 0.6, "status": "pending"},
                                {"index": 2, "price": 41.2, "frac": 0.4, "status": "pending"},
                            ],
                            "trailing": {"enabled": False},
                            "breakeven": {"enabled": False},
                            "time_stop_sec": 172800,
                        },
                        "upnl_usd": 0.3,
                    }
                ],
            },
            "setups_scanner": {"card_count": 0, "cards_top": []},
        },
    )

    compact = compact_ai_full_context(root)

    assert compact["heartbeat"]["open_trades"] == 1
    assert compact["open_positions"]["count"] == 1
    assert compact["open_positions"]["positions"][0]["symbol"] == "LTCUSDT"
    assert compact["open_positions"]["positions"][0]["sl"] == 42.58
    assert compact["open_positions"]["positions"][0]["tp_model"] == "runner_ladder"
    assert compact["open_positions"]["positions"][0]["runner"]["targets"][0]["price"] == 41.9
    assert compact["git_revision"]["head"] == "abc123"
    assert compact["ai_context_brief"] == "HOUSE RULES"
    assert compact["technology_registry"]["totals"]["modules"] == 3
    assert compact["att1_edge_health"]["status"] == "watch"
    assert compact["pnl_by_sleeve_usd"]["rows"][0]["strategy"] == "att1_trendline_touch"
    assert compact["alpaca_account_state"]["api_snapshot"]["account"]["equity"] == "494.90"
    assert compact["errors_tail"]["lines"] == ["ok"]


def test_append_ai_context_lines_mentions_position(tmp_path):
    root = tmp_path
    _write_json(
        root / "runtime" / "ai_context" / "full_context.json",
        {
            "generated_at_utc": "2026-06-11T12:00:00Z",
            "sources_used": {},
            "heartbeat": {"open_trades": 1, "trade_on": True, "dry_run": False, "regime": "bear_chop"},
            "open_positions": {
                "count": 1,
                "ts": 1781190000,
                "positions": [{
                    "symbol": "DOTUSDT",
                    "side": "Sell",
                    "entry": 0.9479,
                    "sl": 0.964,
                    "tp_model": "runner_ladder",
                    "exchange_tp": None,
                    "runner": {
                        "targets": [{"index": 1, "price": 0.93, "frac": 0.6, "status": "pending"}],
                        "trailing": {"enabled": False},
                        "breakeven": {"enabled": False},
                        "time_stop_sec": 86400,
                    },
                }],
            },
            "setups_scanner": {"card_count": 0, "cards_top": []},
        },
    )
    parts = []

    append_ai_context_lines(parts, root)
    text = "".join(parts)

    assert "UNIFIED AI CONTEXT" in text
    assert "OPEN POSITION: DOTUSDT Sell" in text
    assert "sl=0.964" in text
    assert "tp_model=runner_ladder" in text
    assert "runner_targets=[TP1=0.93 frac=0.6 pending]" in text


def test_stale_full_context_is_reduced_to_fail_closed_marker(tmp_path):
    path = tmp_path / "runtime" / "ai_context" / "full_context.json"
    _write_json(
        path,
        {
            "generated_at_utc": "2026-07-10T00:00:00Z",
            "heartbeat": {"open_trades": 0, "regime": "bull_chop"},
            "setups_scanner": {"card_count": 80, "cards_top": [{"symbol": "AVAXUSDT"}]},
        },
    )
    old = time.time() - 10_000
    os.utime(path, (old, old))
    _write_json(
        tmp_path / "configs" / "project_capability_registry_v1.json",
        {
            "schema_version": 1,
            "as_of_utc": "2026-07-15T00:00:00Z",
            "components": [
                {
                    "component_id": "crypto_att1_short_r001",
                    "market": "crypto_perpetual",
                    "physical_side": "short_only",
                    "stage": "live_tiny_canary",
                    "execution_authority": "tiny_money",
                    "promotion_authorized": False,
                    "known_gaps": ["edge unproven"],
                    "next_gate": "review",
                }
            ],
        },
    )

    compact = compact_ai_full_context(tmp_path)

    assert compact["critical_truth_assessment"]["control_recommendations_allowed"] is False
    assert compact["heartbeat"] == {}
    assert compact["setup_cards_top"] == []
    assert "ai_full_context_stale" in compact["critical_truth_assessment"]["blockers"][0]
    assert compact["project_capability_registry"]["component_count"] == 1
    assert compact["project_capability_registry"]["components"][0]["execution_authority"] == "tiny_money"
