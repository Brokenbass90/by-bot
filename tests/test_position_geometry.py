from __future__ import annotations

import json

from bot.position_geometry import (
    SCHEMA_VERSION,
    build_position_geometry,
    parse_signal_geometry,
    write_position_geometry,
)


def test_parse_att1_signal_geometry() -> None:
    parsed = parse_signal_geometry(
        "short touch tl=184.25 slope=-1.70%/d rsi=63.4 r2=0.91 "
        "pivots=4 age=9 entrydist=0.21 touchdist=0.08 reject=0.72 "
        "body=0.44 atrpct=1.20"
    )

    assert parsed["available"] is True
    assert parsed["primary_role"] == "trendline"
    assert parsed["primary_level"] == 184.25
    assert parsed["sloped_lines"][0]["slope_pct_per_day"] == -1.7
    assert parsed["sloped_lines"][0]["exact_projection"] is True
    assert parsed["sloped_lines"][0]["exact_pivots"] is False
    assert parsed["metrics"] == {
        "rsi": 63.4,
        "r2": 0.91,
        "pivots": 4,
        "age_bars": 9.0,
        "entry_distance_atr": 0.21,
        "touch_distance_atr": 0.08,
        "reject_depth_atr": 0.72,
        "body_atr": 0.44,
        "atr_pct": 1.2,
    }


def test_parse_horizontal_level_aliases() -> None:
    parsed = parse_signal_geometry("breakout upper=102.5 lower=98.25 quality=7.5")

    assert parsed["primary_level"] == 102.5
    assert parsed["primary_role"] == "upper"
    assert [row["role"] for row in parsed["horizontal_levels"]] == ["upper", "lower"]
    assert parsed["metrics"]["quality"] == 7.5


def test_build_and_atomically_write_snapshot(tmp_path) -> None:
    payload = build_position_geometry(
        symbol="ethusdt",
        strategy="att1_trendline_touch",
        side="Sell",
        entry_ts=123,
        entry_price=2500.0,
        sl_price=2525.0,
        tp_prices=[2475.0, 2450.0],
        signal_reason="tl=2501.5 slope=-0.8%/d r2=0.88 pivots=3",
        order_id="abc/123",
    )
    path = write_position_geometry(tmp_path, "abc/123", payload)
    stored = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == SCHEMA_VERSION
    assert path.name == "abc_123.json"
    assert stored == payload
    assert list(tmp_path.glob(".*")) == []


def test_missing_geometry_is_reported_honestly() -> None:
    parsed = parse_signal_geometry("momentum continuation rsi=58.0")
    assert parsed["available"] is False
    assert parsed["primary_level"] is None
    assert parsed["metrics"]["rsi"] == 58.0
