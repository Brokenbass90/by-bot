from __future__ import annotations

import ast
import hashlib
import inspect
import json
import time
from pathlib import Path

import pytest

from bot.ai_trade_mission import AIDecision, CandidateCard, MissionError
from bot.ai_trade_mission_replay import (
    M5_MS,
    ReplayEvidenceError,
    load_hash_pinned_m5_feed,
    run_feed_bound_replay,
    snapshot_sha256,
    write_replay_receipt,
)


BASE = 1_700_000_100_000
SNAPSHOT_CLOSE = BASE + 3 * M5_MS
ENTRY_INDEX = 4  # controller opens strictly after the causal close boundary


def _rows(*, side: str = "long", ambiguous: bool = False, horizon: bool = False):
    rows = []
    for index in range(7):
        opening = 100.0
        high = 101.0
        low = 99.0
        close = 100.0 + index * 0.05
        if index == ENTRY_INDEX + 1 and not horizon:
            if ambiguous:
                high, low, close = 105.0, 97.0, 100.0
            elif side == "long":
                high, low, close = 104.5, 99.0, 103.5
            else:
                high, low, close = 101.0, 95.5, 96.5
        rows.append(
            {
                "open_ts": BASE + index * M5_MS,
                "open": opening,
                "high": high,
                "low": low,
                "close": close,
            }
        )
    return rows


def _write_feed(tmp_path: Path, rows, *, jsonl: bool = False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / ("feed.jsonl" if jsonl else "feed.json")
    if jsonl:
        raw = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
    else:
        raw = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    path.write_text(raw, encoding="utf-8")
    return path, hashlib.sha256(raw.encode()).hexdigest()


def _card(tmp_path: Path, *, side: str, rows, jsonl: bool = False):
    path, digest = _write_feed(tmp_path, rows, jsonl=jsonl)
    feed = load_hash_pinned_m5_feed(path, expected_sha256=digest)
    snap = snapshot_sha256(feed, symbol="BTCUSDT", closed_at_ms=SNAPSHOT_CLOSE)
    if side == "long":
        card = CandidateCard.build(
            symbol="BTCUSDT",
            side="long",
            closed_at_ms=SNAPSHOT_CLOSE,
            entry=100.0,
            sl=98.0,
            tp=104.0,
            snapshot_hash=snap,
        )
    else:
        card = CandidateCard.build(
            symbol="BTCUSDT",
            side="short",
            closed_at_ms=SNAPSHOT_CLOSE,
            entry=100.0,
            sl=102.0,
            tp=96.0,
            snapshot_hash=snap,
        )
    return path, digest, card


def _run(tmp_path: Path, *, side="long", rows=None, jsonl=False, mission="m1"):
    rows = _rows(side=side) if rows is None else rows
    path, digest, card = _card(tmp_path, side=side, rows=rows, jsonl=jsonl)
    envelope = run_feed_bound_replay(
        feed_path=path,
        expected_feed_sha256=digest,
        state_path=tmp_path / "state.json",
        mission_id=mission,
        cards=(card,),
        decision=AIDecision.select(card.card_id),
        max_bars=3,
    )
    return envelope, path, digest, card


def test_happy_long_binds_feed_range_plan_costed_controller_receipt(tmp_path: Path):
    envelope, _, digest, card = _run(tmp_path, side="long")
    receipt = envelope["controller_receipt"]
    hash_payload = dict(envelope)
    envelope_sha = hash_payload.pop("envelope_sha256")
    assert envelope_sha == hashlib.sha256(
        json.dumps(
            hash_payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    assert envelope["feed"]["sha256"] == digest
    assert envelope["mission"]["selected_card"]["card_id"] == card.card_id
    assert envelope["mission"]["plan_sha256"] == receipt["plan_sha256"]
    assert envelope["mission"]["plan_token"] == receipt["plan_token"]
    assert envelope["selected_bar_range"] == {
        "snapshot_closed_at_ms": SNAPSHOT_CLOSE,
        "entry_open_ts": BASE + ENTRY_INDEX * M5_MS,
        "exit_open_ts": BASE + (ENTRY_INDEX + 1) * M5_MS,
        "exit_close_ts": BASE + (ENTRY_INDEX + 2) * M5_MS,
        "evaluated_bars": 2,
        "max_bars": 3,
        "decision_latency_bars": 1,
        "feed_ends_at_preregistered_horizon": True,
    }
    assert receipt["close_reason"] == "TP"
    assert receipt["raw_open"] == 100.0 and receipt["raw_close"] == 104.0
    assert receipt["entry_fill"] > receipt["raw_open"]
    assert receipt["exit_fill"] < receipt["raw_close"]
    assert receipt["net_return"] < receipt["gross_return"]
    assert envelope["performance_authority"] == {
        "enabled": True,
        "scope": "single_mission_replay_only",
    }
    assert envelope["promotion_authority"] is False
    assert envelope["selection_bias_control"]["preregistration_sha256"] is None
    assert envelope["live"] is False and envelope["broker"] is False


def test_happy_short_jsonl_applies_adverse_controller_costs(tmp_path: Path):
    envelope, _, _, _ = _run(tmp_path, side="short", jsonl=True)
    receipt = envelope["controller_receipt"]
    assert envelope["feed"]["format"] == "jsonl"
    assert receipt["side"] == "short" and receipt["close_reason"] == "TP"
    assert receipt["entry_fill"] < receipt["raw_open"]
    assert receipt["exit_fill"] > receipt["raw_close"]
    assert receipt["net_return"] < receipt["gross_return"]


def test_gap_in_m5_grid_is_rejected_before_mission_state_exists(tmp_path: Path):
    rows = _rows()
    del rows[2]
    path, digest = _write_feed(tmp_path, rows)
    with pytest.raises(ReplayEvidenceError, match="gap, duplicate, or reordering"):
        load_hash_pinned_m5_feed(path, expected_sha256=digest)


def test_feed_byte_tamper_is_rejected_by_required_hash_pin(tmp_path: Path):
    path, digest = _write_feed(tmp_path, _rows())
    path.write_text(path.read_text() + " ", encoding="utf-8")
    with pytest.raises(ReplayEvidenceError, match="SHA256 mismatch"):
        load_hash_pinned_m5_feed(path, expected_sha256=digest)


def test_same_bar_tp_and_sl_is_resolved_adversely_sl_first(tmp_path: Path):
    rows = _rows(ambiguous=True)
    envelope, _, _, _ = _run(tmp_path, rows=rows)
    receipt = envelope["controller_receipt"]
    assert receipt["close_reason"] == "AMBIGUOUS_SL_FIRST"
    assert receipt["raw_close"] == 98.0
    assert receipt["net_return"] < 0


def test_no_trigger_closes_at_final_horizon_bar_close(tmp_path: Path):
    rows = _rows(horizon=True)
    rows[-1]["close"] = 101.25
    rows[-1]["high"] = 101.5
    envelope, _, _, _ = _run(tmp_path, rows=rows)
    receipt = envelope["controller_receipt"]
    assert receipt["close_reason"] == "MAX_BARS"
    assert receipt["raw_close"] == 101.25
    assert receipt["closed_at_ms"] == rows[-1]["open_ts"] + M5_MS
    assert envelope["selected_bar_range"]["evaluated_bars"] == 3


def test_abstain_cannot_open_and_has_no_performance_authority(tmp_path: Path):
    path, digest, card = _card(tmp_path, side="long", rows=_rows())
    envelope = run_feed_bound_replay(
        feed_path=path,
        expected_feed_sha256=digest,
        state_path=tmp_path / "state.json",
        mission_id="abstain-1",
        cards=(card,),
        decision=AIDecision.abstain(),
        max_bars=3,
    )
    assert envelope["mission"]["status"] == "ABSTAIN"
    assert envelope["controller_receipt"] is None
    assert envelope["selected_bar_range"]["entry_open_ts"] is None
    assert envelope["performance_authority"] == {"enabled": False, "scope": "none"}


def test_snapshot_is_prefix_only_and_future_or_tail_rows_are_rejected(tmp_path: Path):
    rows = _rows()
    path, digest, card = _card(tmp_path, side="long", rows=rows)
    original_snapshot = card.snapshot_hash
    changed = [dict(row) for row in rows]
    changed[-1]["close"] = 100.9
    changed[-1]["high"] = 101.1
    changed_path, changed_digest = _write_feed(tmp_path / "changed", changed)
    changed_feed = load_hash_pinned_m5_feed(changed_path, expected_sha256=changed_digest)
    assert snapshot_sha256(
        changed_feed, symbol="BTCUSDT", closed_at_ms=SNAPSHOT_CLOSE
    ) == original_snapshot

    tail = rows + [{
        "open_ts": rows[-1]["open_ts"] + M5_MS,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.0,
    }]
    tail_path, tail_digest = _write_feed(tmp_path / "tail", tail)
    with pytest.raises(ReplayEvidenceError, match="post-horizon tail"):
        run_feed_bound_replay(
            feed_path=tail_path,
            expected_feed_sha256=tail_digest,
            state_path=tmp_path / "tail-state.json",
            mission_id="tail",
            cards=(card,),
            decision=AIDecision.select(card.card_id),
            max_bars=3,
        )
    truncated_path, truncated_digest = _write_feed(tmp_path / "truncated", rows[:-1])
    with pytest.raises(ReplayEvidenceError, match="truncated before"):
        run_feed_bound_replay(
            feed_path=truncated_path,
            expected_feed_sha256=truncated_digest,
            state_path=tmp_path / "truncated-state.json",
            mission_id="truncated",
            cards=(card,),
            decision=AIDecision.select(card.card_id),
            max_bars=3,
        )
    future_open = ((time.time_ns() // 1_000_000) // M5_MS + 1) * M5_MS
    future_path, future_digest = _write_feed(tmp_path / "future", [{
        "open_ts": future_open,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.0,
    }])
    with pytest.raises(ReplayEvidenceError, match="future or still-forming"):
        load_hash_pinned_m5_feed(
            future_path,
            expected_sha256=future_digest,
        )


def test_next_open_price_gap_cannot_bypass_frozen_geometry(tmp_path: Path):
    rows = _rows()
    rows[ENTRY_INDEX]["open"] = 105.0
    rows[ENTRY_INDEX]["high"] = 106.0
    rows[ENTRY_INDEX]["low"] = 104.5
    rows[ENTRY_INDEX]["close"] = 105.2
    path, digest, card = _card(tmp_path, side="long", rows=rows)
    with pytest.raises(MissionError, match="gap invalidated"):
        run_feed_bound_replay(
            feed_path=path,
            expected_feed_sha256=digest,
            state_path=tmp_path / "state.json",
            mission_id="price-gap",
            cards=(card,),
            decision=AIDecision.select(card.card_id),
            max_bars=3,
        )


def test_receipt_is_create_only_and_replay_api_has_no_manual_outcome_arguments(tmp_path: Path):
    envelope, _, _, _ = _run(tmp_path)
    receipt = tmp_path / "receipt.json"
    write_replay_receipt(receipt, envelope)
    assert json.loads(receipt.read_text())["envelope_sha256"] == envelope["envelope_sha256"]
    assert receipt.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ReplayEvidenceError, match="overwrite is forbidden"):
        write_replay_receipt(receipt, envelope)
    parameters = set(inspect.signature(run_feed_bound_replay).parameters)
    assert not parameters.intersection(
        {
            "raw_open",
            "raw_close",
            "opened_at_ms",
            "closed_at_ms",
            "close_reason",
            "observed_at_ms",
        }
    )


def test_replay_module_import_graph_contains_no_live_or_network_adapter():
    source_path = Path(__file__).parents[1] / "bot" / "ai_trade_mission_replay.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert roots <= {
        "__future__",
        "dataclasses",
        "hashlib",
        "json",
        "math",
        "os",
        "pathlib",
        "time",
        "typing",
        "uuid",
        "bot",
    }
    lowered = source_path.read_text(encoding="utf-8").lower()
    for forbidden in ("import requests", "import ccxt", "import pybit", "import telegram"):
        assert forbidden not in lowered
