from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pyotp")

from web.routes import data_routes


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _scanner_sources(runtime: Path) -> dict[Path, dict]:
    return {
        runtime / "geometry" / "geometry_state.json": {
            "generated_at_utc": "2026-07-18T00:00:00+00:00",
            "symbols_analyzed": 1,
            "snapshots_built": 1,
            "intervals": ["60"],
            "symbols": {
                "BTCUSDT": {
                    "60": {
                        "status": "ok",
                        "current_price": 100.0,
                        "atr": 2.0,
                        "flags": {"trend_label": "range_or_transition"},
                        "channel": {
                            "position": 0.8,
                            "r2": 0.5,
                            "slope_per_bar": -0.1,
                            "slope_pct_per_bar": -0.1,
                            "mid": 100.0,
                            "upper": 102.0,
                            "lower": 98.0,
                        },
                        "compression": {"is_compressed": False},
                        "nearest_levels": {
                            "above": [{"price": 101.0, "touches": 3, "side_bias": "resistance"}],
                            "below": [],
                        },
                    }
                }
            },
        },
        runtime / "router" / "symbol_router_state.json": {
            "status": "ok",
            "regime": "flat",
            "confidence": 0.8,
            "profiles": {},
        },
        runtime / "control_plane" / "portfolio_allocator_state.json": {
            "status": "ok",
            "safe_mode": False,
            "sleeves": {
                "flat": {
                    "enabled": True,
                    "final_risk_mult": 0.2,
                    "health_status": "ok",
                }
            },
        },
    }


def _write_scanner_sources(runtime: Path) -> None:
    for path, payload in _scanner_sources(runtime).items():
        _write_json(path, payload)


def test_setup_scanner_marks_fresh_rank_output_authoritative(monkeypatch, tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    _write_scanner_sources(runtime)
    max_ages = {
        "geometry_state.json": data_routes.SETUP_SCANNER_GEOMETRY_MAX_AGE_SEC,
        "symbol_router_state.json": data_routes.SETUP_SCANNER_ROUTER_MAX_AGE_SEC,
        "portfolio_allocator_state.json": data_routes.SETUP_SCANNER_ALLOCATOR_MAX_AGE_SEC,
    }
    monkeypatch.setattr(data_routes, "_RUNTIME_ROOT", runtime)
    monkeypatch.setattr(data_routes, "_file_age_sec", lambda path: max_ages[path.name])

    payload = asyncio.run(data_routes.get_setup_scanner(_="tester"))

    assert payload["authoritative"] is True
    assert payload["blockers"] == []
    assert payload["score_semantics"] == "heuristic_rank_not_probability"
    assert payload["freshness_max_age_sec"]["allocator"] == 10_800
    assert payload["cards"]
    assert payload["active_sleeves"]
    assert payload["cards"][0]["geometry"]["channel"] is None
    assert payload["cards"][0]["geometry"]["channel_status"] == "not_relevant_to_horizontal_setup"


def test_scanner_maps_bounce_and_trend_pullback_to_real_runtime_sleeves() -> None:
    geometry = _scanner_sources(Path("/tmp/runtime"))[Path("/tmp/runtime/geometry/geometry_state.json")]
    snapshot = geometry["symbols"]["BTCUSDT"]["60"]
    snapshot["current_price"] = 100.0
    snapshot["nearest_levels"] = {
        "above": [],
        "below": [{"price": 99.5, "touches": 3, "side_bias": "support"}],
    }
    snapshot["flags"] = {"trend_label": "trend_up", "level_context": "near_support"}
    snapshot["channel"]["position"] = 0.2
    cards = data_routes._build_setup_cards(geometry, {"profiles": {}}, {"sleeves": {}})

    by_type = {card["setup_type"]: card for card in cards}
    assert by_type["support bounce"]["strategy"] == "bounce1"
    assert by_type["trend pullback"]["strategy"] == "midterm"
    assert all(card["strategy"] != "att1" for card in cards if card["side"] == "LONG")


def test_horizontal_cards_do_not_present_close_regression_as_strategy_trendline() -> None:
    geometry = _scanner_sources(Path("/tmp/runtime"))[Path("/tmp/runtime/geometry/geometry_state.json")]
    cards = data_routes._build_setup_cards(geometry, {"profiles": {}}, {"sleeves": {}})
    resistance = next(card for card in cards if card["setup_type"] == "resistance fade")

    assert resistance["geometry"]["channel"] is None
    assert resistance["geometry"]["channel_status"] == "not_relevant_to_horizontal_setup"


def test_low_r2_channel_is_suppressed_even_for_sloped_context_card() -> None:
    geometry = _scanner_sources(Path("/tmp/runtime"))[Path("/tmp/runtime/geometry/geometry_state.json")]
    snapshot = geometry["symbols"]["BTCUSDT"]["60"]
    snapshot["flags"] = {"trend_label": "trend_down", "level_context": "near_resistance"}
    snapshot["channel"]["position"] = 0.8
    snapshot["channel"]["r2"] = 0.17
    cards = data_routes._build_setup_cards(geometry, {"profiles": {}}, {"sleeves": {}})
    continuation = next(card for card in cards if card["setup_type"] == "bear continuation")

    assert continuation["geometry"]["channel"] is None
    assert continuation["geometry"]["channel_status"] == "suppressed_low_r2"


@pytest.mark.parametrize(
    ("stale_name", "expected_blocker"),
    [
        ("geometry_state.json", "geometry_missing_or_stale"),
        ("symbol_router_state.json", "router_missing_or_stale"),
        ("portfolio_allocator_state.json", "allocator_missing_or_stale"),
    ],
)
def test_setup_scanner_fails_closed_when_any_source_is_stale(
    monkeypatch,
    tmp_path: Path,
    stale_name: str,
    expected_blocker: str,
) -> None:
    runtime = tmp_path / "runtime"
    _write_scanner_sources(runtime)
    max_ages = {
        "geometry_state.json": data_routes.SETUP_SCANNER_GEOMETRY_MAX_AGE_SEC,
        "symbol_router_state.json": data_routes.SETUP_SCANNER_ROUTER_MAX_AGE_SEC,
        "portfolio_allocator_state.json": data_routes.SETUP_SCANNER_ALLOCATOR_MAX_AGE_SEC,
    }
    monkeypatch.setattr(data_routes, "_RUNTIME_ROOT", runtime)
    monkeypatch.setattr(
        data_routes,
        "_file_age_sec",
        lambda path: max_ages[path.name] + (1 if path.name == stale_name else 0),
    )

    payload = asyncio.run(data_routes.get_setup_scanner(_="tester"))

    assert payload["authoritative"] is False
    assert expected_blocker in payload["blockers"]
    assert payload["cards"] == []
    assert payload["active_sleeves"] == []
    assert payload["regime"] is None
    assert payload["allocator_status"] is None
    assert payload["safe_mode"] is None
