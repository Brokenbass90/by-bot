from __future__ import annotations

from pathlib import Path

from scripts.score_event_universe_v1 import (
    build_summaries,
    load_scorer_spec,
    score_episode_outcomes,
    select_episodes,
    write_receipt,
)


BASE = 1_800_000_000_000
M5 = 300_000


def _score(symbol: str, direction: str, candidate: str) -> dict:
    return {
        "ok": True,
        "reason": "event_ok",
        "symbol": symbol,
        "direction": direction,
        "listing_tier": "normal",
        "candidate_id": candidate * 64,
        "input_sha256": "f" * 64,
        "heuristic_rank": 70.0,
        "inflow_mult": 3.0,
        "recent_return_pct": 4.0 if direction == "long" else -4.0,
        "range_expansion_atr": 2.5,
        "latest_body_fraction": 0.5,
    }


def _snapshot(sequence: int, as_of_ms: int, scores: list[dict]) -> dict:
    return {
        "sequence": sequence,
        "as_of_ms": as_of_ms,
        "snapshot_sha256": f"{sequence:064x}",
        "scores": scores,
    }


def test_episode_selection_is_first_then_24h_cooldown_and_side_split():
    snapshots = [
        _snapshot(1, BASE, [_score("AKEUSDT", "long", "a")]),
        _snapshot(2, BASE + M5, [_score("AKEUSDT", "long", "b")]),
        _snapshot(3, BASE + 2 * M5, [_score("AKEUSDT", "short", "c")]),
        _snapshot(4, BASE + 86_400_000, [_score("AKEUSDT", "long", "d")]),
    ]
    tails = {
        1: {"AKEUSDT": BASE - M5},
        2: {"AKEUSDT": BASE},
        3: {"AKEUSDT": BASE + M5},
        4: {"AKEUSDT": BASE + 86_400_000 - M5},
    }
    episodes = select_episodes(snapshots, tails)
    assert [(item["signal_sequence"], item["direction"]) for item in episodes] == [
        (1, "long"),
        (3, "short"),
        (4, "long"),
    ]
    assert episodes[0]["signal_tail_end_ms"] == BASE - M5


def _episode(direction: str = "long") -> dict:
    return {
        "episode_index": 1,
        "symbol": "AKEUSDT",
        "direction": direction,
        "listing_tier": "normal",
        "signal_sequence": 1,
        "signal_as_of_ms": BASE,
        "signal_snapshot_sha256": "1" * 64,
        "signal_tail_end_ms": BASE - M5,
        "candidate_id": "2" * 64,
        "input_sha256": "3" * 64,
        "features": {
            "heuristic_rank": 70.0,
            "inflow_mult": 3.0,
            "abs_recent_return_pct": 4.0,
            "range_expansion_atr": 2.5,
            "latest_body_fraction": 0.5,
        },
    }


def _bar(start: int, open_: float, high: float, low: float, close: float) -> list:
    return [start, open_, high, low, close, 1.0, 1000.0]


def test_outcome_uses_exact_next_open_closed_window_and_directional_cost():
    bars = {
        "AKEUSDT": {
            BASE: _bar(BASE, 100.0, 103.0, 99.0, 102.0),
            BASE + M5: _bar(BASE + M5, 102.0, 105.0, 101.0, 104.0),
        }
    }
    long = score_episode_outcomes(
        _episode("long"),
        bars,
        chain_head_as_of_ms=BASE + 2 * M5,
        horizons=[{"id": "10m", "bars": 2}],
        roundtrip_cost_bps=16.0,
    )["outcomes"]["10m"]
    short = score_episode_outcomes(
        _episode("short"),
        bars,
        chain_head_as_of_ms=BASE + 2 * M5,
        horizons=[{"id": "10m", "bars": 2}],
        roundtrip_cost_bps=16.0,
    )["outcomes"]["10m"]
    assert long["entry_start_ms"] == BASE
    assert long["entry_open"] == 100.0
    assert long["gross_return_bps"] == 400.0
    assert long["net_return_bps"] == 384.0
    assert long["mfe_bps"] == 500.0
    assert long["mae_bps"] == 100.0
    assert short["gross_return_bps"] == -400.0
    assert short["net_return_bps"] == -416.0


def test_incomplete_future_is_pending_but_observable_gap_fails_closed():
    bars = {"AKEUSDT": {BASE: _bar(BASE, 100.0, 101.0, 99.0, 100.0)}}
    pending = score_episode_outcomes(
        _episode(),
        bars,
        chain_head_as_of_ms=BASE + M5,
        horizons=[{"id": "10m", "bars": 2}],
        roundtrip_cost_bps=16.0,
    )["outcomes"]["10m"]
    missing = score_episode_outcomes(
        _episode(),
        bars,
        chain_head_as_of_ms=BASE + 2 * M5,
        horizons=[{"id": "10m", "bars": 2}],
        roundtrip_cost_bps=16.0,
    )["outcomes"]["10m"]
    assert pending["status"] == "pending"
    assert missing["status"] == "unscorable_missing_future_bars"
    assert missing["first_missing_start_ms"] == BASE + M5


def test_preregistered_spec_loads_and_summaries_keep_side_split():
    root = Path(__file__).resolve().parents[1]
    spec, _collector_spec, _config = load_scorer_spec(
        root / "configs/preregistered/event_universe_label_scorer_v1_20260721.json"
    )
    bars = {"AKEUSDT": {BASE: _bar(BASE, 100.0, 101.0, 99.0, 101.0)}}
    scored = [
        score_episode_outcomes(
            _episode(side),
            bars,
            chain_head_as_of_ms=BASE + M5,
            horizons=[{"id": "5m", "bars": 1}],
            roundtrip_cost_bps=16.0,
        )
        for side in ("long", "short")
    ]
    summaries = build_summaries(
        scored,
        horizons=[{"id": "5m", "bars": 1}],
        feature_buckets=spec["feature_buckets"],
    )
    side_keys = {
        item["key"]
        for item in summaries
        if item["group_type"] == "direction"
    }
    assert side_keys == {"long", "short"}


def test_receipt_write_is_byte_idempotent(tmp_path):
    receipt = {
        "source_identity": {"snapshot_count": 1, "last_snapshot_sha256": "a" * 64},
        "receipt_sha256": "b" * 64,
        "research_only": True,
    }
    first = write_receipt(tmp_path, receipt)
    original = first.read_bytes()
    second = write_receipt(tmp_path, receipt)
    assert second == first
    assert second.read_bytes() == original
