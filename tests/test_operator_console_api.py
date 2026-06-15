from __future__ import annotations

import json
from pathlib import Path

from web.routes import data_routes


def test_operator_pnl_payload_filters_period_and_aggregates(monkeypatch, tmp_path: Path) -> None:
    events = tmp_path / "live_trade_events.jsonl"
    events.write_text(
        "\n".join(
            [
                json.dumps({"event": "close", "strategy": "flat", "pnl": 1.25, "fees": 0.05, "ts": 1781510000}),
                json.dumps({"event": "close", "strategy": "att1", "pnl": -0.50, "fees": 0.02, "ts": 1781510100}),
                json.dumps({"event": "order_submitted", "strategy": "flat", "pnl": 99.0, "fees": 9.0, "ts": 1781510200}),
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(data_routes, "_live_events_path", lambda: events)
    monkeypatch.setattr(data_routes, "_period_start", lambda period: None)

    payload = data_routes._operator_pnl_payload("all")

    assert payload["total"] == {"pnl": 0.75, "fees": 0.07, "trades": 2}
    by_sleeve = {row["sleeve"]: row for row in payload["rows"]}
    assert by_sleeve["flat"]["win"] == 1
    assert by_sleeve["att1"]["loss"] == 1


def test_ai_code_read_endpoint_uses_secret_safe_refusal() -> None:
    import asyncio

    result = asyncio.run(data_routes.ai_code_read(path=".env", _="tester"))

    assert result["content"].startswith("refused:")
