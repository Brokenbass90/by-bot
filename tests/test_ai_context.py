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
                "positions": [{"symbol": "DOTUSDT", "side": "Sell", "entry": 0.9479, "sl": 0.964}],
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
