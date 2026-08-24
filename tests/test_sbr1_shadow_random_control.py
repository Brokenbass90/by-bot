from __future__ import annotations

import ast
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bot.sbr1_shadow_random_control import (
    CONTROL_AUTHORITY,
    H1_MS,
    build_control_assignments,
    calendar_month_bounds,
    preregistration_sha256,
    persist_control_assignments,
    persist_controlled_admission,
)
from bot.sbr1_zero_risk_shadow import AppendOnlyShadowJournal, ShadowViolation


ROOT = Path(__file__).resolve().parents[1]


def test_calendar_bounds_are_true_utc_months_including_leap_february():
    feb = int(datetime(2028, 2, 29, 23, 15, tzinfo=timezone.utc).timestamp() * 1000)
    start, end = calendar_month_bounds(feb)
    assert datetime.fromtimestamp(start / 1000, timezone.utc).isoformat() == "2028-02-01T00:00:00+00:00"
    assert datetime.fromtimestamp(end / 1000, timezone.utc).isoformat() == "2028-03-01T00:00:00+00:00"
    assert end - start == 29 * 24 * H1_MS


def test_assignments_are_deterministic_unique_and_exclude_main_hour():
    main_ts = int(datetime(2026, 8, 24, 12, tzinfo=timezone.utc).timestamp() * 1000)
    rows = build_control_assignments(
        prereg_sha256="a" * 64,
        main_decision_id="decision-1",
        main_decision_ts_ms=main_ts,
        now_ms=main_ts,
        eligible_hour=lambda _hour: True,
        main_context={
            "symbol": "BTCUSDT",
            "side": "long",
            "geometry_sha256": "e" * 64,
            "source_sha256": "1" * 64,
            "data_sha256": "2" * 64,
            "config_sha256": "3" * 64,
            "cost_contract_sha256": "4" * 64,
        },
    )
    again = build_control_assignments(
        prereg_sha256="a" * 64,
        main_decision_id="decision-1",
        main_decision_ts_ms=main_ts,
        now_ms=main_ts,
        eligible_hour=lambda _hour: True,
        main_context={
            "symbol": "BTCUSDT",
            "side": "long",
            "geometry_sha256": "e" * 64,
            "source_sha256": "1" * 64,
            "data_sha256": "2" * 64,
            "config_sha256": "3" * 64,
            "cost_contract_sha256": "4" * 64,
        },
    )
    assert rows == again
    assert len(rows) == 20
    sampled = [row["sampled_hour_start_ms"] for row in rows]
    assert len(set(sampled)) == 20
    assert (main_ts // H1_MS) * H1_MS not in sampled
    assert all(row["authority"] == CONTROL_AUTHORITY for row in rows)
    assert all(row["main_symbol"] == "BTCUSDT" for row in rows)
    assert all(row["main_side"] == "long" for row in rows)
    assert all(row["main_source_sha256"] == "1" * 64 for row in rows)
    assert all(row["main_data_sha256"] == "2" * 64 for row in rows)
    assert all(row["main_config_sha256"] == "3" * 64 for row in rows)
    assert all(row["cost_contract_sha256"] == "4" * 64 for row in rows)


def test_future_hours_are_pending_and_rejected_hours_do_not_break_determinism():
    main_ts = int(datetime(2026, 2, 24, 12, tzinfo=timezone.utc).timestamp() * 1000)
    past_cutoff = main_ts - 12 * H1_MS
    calls: list[int] = []

    def eligible(hour: int) -> bool:
        calls.append(hour)
        return hour % (3 * H1_MS) != 0

    rows = build_control_assignments(
        prereg_sha256="b" * 64,
        main_decision_id="decision-2",
        main_decision_ts_ms=main_ts,
        now_ms=past_cutoff,
        eligible_hour=eligible,
    )
    assert len(rows) == 20
    assert any(row["lifecycle"] == "pending" for row in rows)
    assert all(row["causal_regime_status"] == "pending" for row in rows)
    assert calls
    assert all(hour + H1_MS <= past_cutoff for hour in calls)


def test_insufficient_eligible_hours_fails_closed():
    main_ts = int(datetime(2026, 8, 24, 12, tzinfo=timezone.utc).timestamp() * 1000)
    with pytest.raises(ShadowViolation, match="insufficient_regime_eligible_hours"):
        build_control_assignments(
            prereg_sha256="c" * 64,
            main_decision_id="decision-3",
            main_decision_ts_ms=main_ts,
            now_ms=int(
                datetime(2026, 9, 1, 0, tzinfo=timezone.utc).timestamp() * 1000
            ),
            eligible_hour=lambda _hour: False,
        )


def test_separate_control_journal_is_idempotent_and_corruption_closed(tmp_path: Path):
    main_ts = int(datetime(2026, 8, 24, 12, tzinfo=timezone.utc).timestamp() * 1000)
    rows = build_control_assignments(
        prereg_sha256="d" * 64,
        main_decision_id="decision-4",
        main_decision_ts_ms=main_ts,
        eligible_hour=lambda _hour: True,
    )
    path = tmp_path / "random_control_events.jsonl"
    journal = AppendOnlyShadowJournal(path)
    assert persist_control_assignments(journal, rows) == 20
    assert persist_control_assignments(journal, rows) == 0
    events = journal.read()
    assert len(events) == 20
    assert events[0]["payload"]["prereg_sha256"] == "d" * 64
    assert events[1]["previous_event_hash"] == events[0]["event_hash"]
    lines = path.read_text(encoding="ascii").splitlines()
    lines[-1] = lines[-1][:-2] + "x\"}"
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    with pytest.raises(ShadowViolation):
        journal.read()


def test_control_precommit_failure_cannot_publish_admitted_main(tmp_path: Path):
    main_ts = int(datetime(2026, 8, 24, 12, tzinfo=timezone.utc).timestamp() * 1000)
    rows = build_control_assignments(
        prereg_sha256="f" * 64,
        main_decision_id="decision-atomic",
        main_decision_ts_ms=main_ts,
        now_ms=main_ts,
    )
    main = AppendOnlyShadowJournal(tmp_path / "main.jsonl")

    class FailingJournal:
        def append(self, *_args, **_kwargs):
            raise ShadowViolation("injected_control_failure")

    with pytest.raises(ShadowViolation, match="injected_control_failure"):
        persist_controlled_admission(
            main_journal=main,
            main_claim="evaluation:SBR1:BTCUSDT:1",
            main_payload={"admitted": True, "decision_id": "decision-atomic"},
            control_journal=FailingJournal(),  # type: ignore[arg-type]
            assignments=rows,
        )
    assert main.read() == []


def test_control_precommit_is_idempotent_before_main_visibility(tmp_path: Path):
    main_ts = int(datetime(2026, 8, 24, 12, tzinfo=timezone.utc).timestamp() * 1000)
    rows = build_control_assignments(
        prereg_sha256="e" * 64,
        main_decision_id="decision-replay",
        main_decision_ts_ms=main_ts,
        now_ms=main_ts,
    )
    main = AppendOnlyShadowJournal(tmp_path / "main.jsonl")
    controls = AppendOnlyShadowJournal(tmp_path / "controls.jsonl")
    payload = {"admitted": True, "decision_id": "decision-replay"}

    assert persist_controlled_admission(
        main_journal=main,
        main_claim="evaluation:SBR1:BTCUSDT:1",
        main_payload=payload,
        control_journal=controls,
        assignments=rows,
    ) == (True, 20)
    assert persist_controlled_admission(
        main_journal=main,
        main_claim="evaluation:SBR1:BTCUSDT:1",
        main_payload=payload,
        control_journal=controls,
        assignments=rows,
    ) == (False, 0)


def test_prereg_hash_and_module_have_no_private_or_order_surface():
    prereg = ROOT / "research_lab/prereg/PREREG_SBR1_SHADOW_RANDOM_CONTROL_2026_08_24.md"
    assert preregistration_sha256(prereg) == hashlib.sha256(prereg.read_bytes()).hexdigest()
    tree = ast.parse((ROOT / "bot/sbr1_shadow_random_control.py").read_text(encoding="utf-8"))
    forbidden = {"private", "order", "broker", "account", "position", "execution"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0].lower() not in forbidden for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0].lower() not in forbidden
            assert all(alias.name.lower() not in forbidden for alias in node.names)
