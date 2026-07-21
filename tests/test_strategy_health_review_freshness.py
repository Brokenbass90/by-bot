import json

import scripts.strategy_health_review as review


def _close(ts, strategy="range"):
    return {"event": "close", "ts": ts, "strategy": strategy, "pnl": 1.0}


def test_event_timestamp_accepts_seconds_and_milliseconds():
    assert review._event_ts_seconds(_close(1_700_000_000)) == 1_700_000_000
    assert review._event_ts_seconds(_close(1_700_000_000_000)) == 1_700_000_000


def test_tail_closes_excludes_historical_sleeve_outside_rolling_window(tmp_path, monkeypatch):
    now = 1_800_000_000.0
    events = tmp_path / "events.jsonl"
    events.write_text(
        "\n".join(
            [
                json.dumps(_close(now - 31 * 86400, "range")),
                json.dumps(_close(now - 2 * 86400, "att1_trendline_touch")),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(review, "LIVE_EVENT_CANDIDATES", (events,))

    rows = review._tail_closes(rolling_days=30, now_ts=now)

    assert [row["strategy"] for row in rows] == ["att1_trendline_touch"]


def test_tail_closes_all_history_keeps_archived_sleeve(tmp_path, monkeypatch):
    events = tmp_path / "events.jsonl"
    events.write_text(json.dumps(_close(1_600_000_000, "range")) + "\n", encoding="utf-8")
    monkeypatch.setattr(review, "LIVE_EVENT_CANDIDATES", (events,))

    rows = review._tail_closes(rolling_days=None, now_ts=1_800_000_000)

    assert [row["strategy"] for row in rows] == ["range"]
