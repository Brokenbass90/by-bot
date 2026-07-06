import json
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
