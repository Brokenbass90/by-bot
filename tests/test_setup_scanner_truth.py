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
                        "channel": {"position": 0.8, "r2": 0.5},
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
