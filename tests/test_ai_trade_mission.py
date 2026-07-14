from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

import bot.ai_trade_mission as mod
from bot.ai_trade_mission import (
    AIDecision,
    AITradeMissionController,
    CandidateCard,
    MissionError,
    MissionPersistenceError,
    MissionStatus,
    candidate_from_input,
)
from scripts.run_ai_trade_mission import main as cli_main


CLOSED = 600_000
REQUESTED = 700_000
FROZEN = 800_000
PROPOSED = 800_001
VALIDATED = 800_002
NEXT_OPEN = 900_000
SNAPSHOT = "a" * 64


def _card(*, side: str = "long", symbol: str = "BTCUSDT", rr: float = 2.0):
    if side == "long":
        entry, sl, tp = 100.0, 98.0, 100.0 + 2.0 * rr
    else:
        entry, sl, tp = 100.0, 102.0, 100.0 - 2.0 * rr
    return CandidateCard.build(
        symbol=symbol,
        side=side,
        closed_at_ms=CLOSED,
        entry=entry,
        sl=sl,
        tp=tp,
        snapshot_hash=SNAPSHOT,
    )


def _request(controller, *, mission_id="mission-1", allowlist=("BTCUSDT",), **kwargs):
    return controller.request(
        mission_id=mission_id,
        requested_at_ms=REQUESTED,
        allowlist=allowlist,
        freshness_ms=kwargs.pop("freshness_ms", 900_000),
        min_rr=kwargs.pop("min_rr", 1.5),
        execution_interval_ms=kwargs.pop("execution_interval_ms", 300_000),
        fee_bps_per_side=kwargs.pop("fee_bps_per_side", 6.0),
        slippage_bps_per_side=kwargs.pop("slippage_bps_per_side", 2.0),
        **kwargs,
    )


def _validated(controller, *, card=None, **request_kwargs):
    card = card or _card()
    _request(controller, **request_kwargs)
    controller.freeze_snapshot([card], frozen_at_ms=FROZEN)
    controller.propose(AIDecision.select(card.card_id), proposed_at_ms=PROPOSED)
    return card, controller.validate(validated_at_ms=VALIDATED)


def test_candidate_card_is_deterministic_and_ai_cannot_edit_geometry() -> None:
    first = _card()
    second = _card()
    assert first == second
    assert first.card_id == second.card_id
    assert first.reward_risk == pytest.approx(2.0)

    with pytest.raises(MissionError, match="geometry"):
        CandidateCard.build(
            symbol="BTCUSDT",
            side="long",
            closed_at_ms=CLOSED,
            entry=100,
            sl=101,
            tp=104,
            snapshot_hash=SNAPSHOT,
        )
    with pytest.raises(MissionError, match="finite"):
        CandidateCard.build(
            symbol="BTCUSDT",
            side="long",
            closed_at_ms=CLOSED,
            entry=float("nan"),
            sl=98,
            tp=104,
            snapshot_hash=SNAPSHOT,
        )
    with pytest.raises(MissionError, match="keys mismatch"):
        candidate_from_input({**first.payload(), "ai_entry": 99.0})


def test_long_happy_path_is_shadow_only_atomic_and_restart_safe(tmp_path: Path) -> None:
    path = tmp_path / "ai-mission.json"
    controller = AITradeMissionController(path)
    card, validated = _validated(controller)
    assert validated.status == MissionStatus.VALIDATED
    assert validated.plan_sha256 and validated.plan_token
    assert validated.mode == "shadow"

    opened = controller.open_shadow(opened_at_ms=NEXT_OPEN, raw_open=100.0)
    assert opened.status == MissionStatus.SHADOW_OPEN
    assert opened.shadow_open.fill_price == pytest.approx(100.02)

    closed = controller.close_shadow(
        closed_at_ms=1_200_000, raw_close=104.0, reason="TP"
    )
    assert closed.status == MissionStatus.SHADOW_CLOSED
    assert closed.receipt is not None
    assert closed.receipt.card_id == card.card_id
    assert closed.receipt.broker_calls is False
    assert closed.receipt.mode == "shadow"
    assert closed.receipt.net_return < closed.receipt.gross_return

    restarted = AITradeMissionController(path).state()
    assert restarted.active is None
    assert restarted.history == (closed,)
    assert restarted.used_plan_tokens == (validated.plan_token,)
    assert restarted.receipt_sha256s == (closed.receipt.receipt_sha256,)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_short_fill_and_receipt_apply_adverse_slippage_and_fees(tmp_path: Path) -> None:
    controller = AITradeMissionController(tmp_path / "state.json")
    card, _ = _validated(controller, card=_card(side="short"))
    opened = controller.open_shadow(opened_at_ms=NEXT_OPEN, raw_open=100.0)
    assert opened.shadow_open.fill_price == pytest.approx(99.98)

    closed = controller.close_shadow(
        closed_at_ms=1_200_000, raw_close=96.0, reason="TARGET"
    )
    receipt = closed.receipt
    assert receipt is not None
    assert receipt.exit_fill == pytest.approx(96.0192)
    assert receipt.symbol == card.symbol and receipt.side == "short"
    assert receipt.net_return == pytest.approx(
        receipt.gross_return - 2 * 6.0 / 10_000.0
    )
    assert receipt.receipt_sha256 == mod._sha256(mod._receipt_payload(receipt))


def test_ai_can_only_select_a_frozen_card_or_abstain(tmp_path: Path) -> None:
    controller = AITradeMissionController(tmp_path / "state.json")
    _request(controller)
    controller.freeze_snapshot([_card()], frozen_at_ms=FROZEN)
    before = controller.state()
    with pytest.raises(MissionError, match="only select a frozen"):
        controller.propose(AIDecision.select("b" * 32), proposed_at_ms=PROPOSED)
    assert controller.state() == before

    proposed = controller.propose(AIDecision.abstain(), proposed_at_ms=PROPOSED)
    assert proposed.status == MissionStatus.AI_PROPOSED
    terminal = controller.validate(validated_at_ms=VALIDATED)
    assert terminal.status == MissionStatus.ABSTAIN
    assert controller.state().active is None
    assert controller.state().history[-1].terminal_reason == "AI_ABSTAIN"


@pytest.mark.parametrize(
    ("card", "allowlist", "freshness_ms", "min_rr", "validated_at", "message"),
    [
        (_card(symbol="ETHUSDT"), ("BTCUSDT",), 900_000, 1.5, VALIDATED, "allowlist"),
        (_card(), ("BTCUSDT",), 100_000, 1.5, VALIDATED, "freshness"),
        (_card(rr=1.2), ("BTCUSDT",), 900_000, 1.5, VALIDATED, "reward/risk"),
    ],
)
def test_validation_gates_fail_closed_without_mutating_state(
    tmp_path: Path, card, allowlist, freshness_ms, min_rr, validated_at, message
) -> None:
    controller = AITradeMissionController(tmp_path / f"{message}.json")
    _request(
        controller,
        allowlist=allowlist,
        freshness_ms=freshness_ms,
        min_rr=min_rr,
    )
    controller.freeze_snapshot([card], frozen_at_ms=FROZEN)
    controller.propose(AIDecision.select(card.card_id), proposed_at_ms=PROPOSED)
    before = controller.state()
    with pytest.raises(MissionError, match=message):
        controller.validate(validated_at_ms=validated_at)
    assert controller.state() == before


def test_one_active_duplicate_mission_and_plan_replay_are_rejected(tmp_path: Path) -> None:
    controller = AITradeMissionController(tmp_path / "state.json")
    _request(controller)
    before = controller.state()
    with pytest.raises(MissionError, match="at most one"):
        _request(controller, mission_id="mission-2")
    assert controller.state() == before

    controller.cancel(cancelled_at_ms=FROZEN)
    with pytest.raises(MissionError, match="replay/duplicate"):
        _request(controller, mission_id="mission-1")

    _request(controller, mission_id="mission-2")
    card = _card()
    controller.freeze_snapshot([card], frozen_at_ms=FROZEN)
    controller.propose(AIDecision.select(card.card_id), proposed_at_ms=PROPOSED)
    controller.validate(validated_at_ms=VALIDATED)
    controller.open_shadow(opened_at_ms=NEXT_OPEN, raw_open=100)
    opened = controller.state()
    with pytest.raises(MissionError, match="expected VALIDATED"):
        controller.open_shadow(opened_at_ms=NEXT_OPEN, raw_open=100)
    assert controller.state() == opened


def test_next_open_is_exact_and_no_retroactive_fill_is_allowed(tmp_path: Path) -> None:
    controller = AITradeMissionController(tmp_path / "state.json")
    _validated(controller)
    before = controller.state()
    with pytest.raises(MissionError, match="exact next grid open 900000"):
        controller.open_shadow(opened_at_ms=1_200_000, raw_open=100)
    with pytest.raises(MissionError, match="exact next grid open 900000"):
        controller.open_shadow(opened_at_ms=600_000, raw_open=100)
    assert controller.state() == before


def test_next_open_gap_must_preserve_geometry_and_minimum_rr(tmp_path: Path) -> None:
    geometry = AITradeMissionController(tmp_path / "geometry.json")
    _validated(geometry)
    before_geometry = geometry.state()
    with pytest.raises(MissionError, match="invalidated.*geometry"):
        geometry.open_shadow(opened_at_ms=NEXT_OPEN, raw_open=105)
    assert geometry.state() == before_geometry

    rr = AITradeMissionController(tmp_path / "rr.json")
    _validated(rr)
    before_rr = rr.state()
    with pytest.raises(MissionError, match="minimum reward/risk"):
        rr.open_shadow(opened_at_ms=NEXT_OPEN, raw_open=101)
    assert rr.state() == before_rr


def test_kill_switch_cancels_preopen_blocks_requests_and_preserves_open_receipt(tmp_path: Path) -> None:
    controller = AITradeMissionController(tmp_path / "state.json")
    _request(controller)
    killed = controller.set_kill_switch(enabled=True, changed_at_ms=FROZEN)
    assert killed.kill_switch is True and killed.active is None
    assert killed.history[-1].status == MissionStatus.CANCELLED
    assert killed.history[-1].terminal_reason == "KILL_SWITCH"
    with pytest.raises(MissionError, match="kill switch"):
        _request(controller, mission_id="mission-2")

    controller.set_kill_switch(enabled=False, changed_at_ms=NEXT_OPEN)
    card, _ = _validated(controller, mission_id="mission-2")
    controller.open_shadow(opened_at_ms=NEXT_OPEN, raw_open=100)
    killed_open = controller.set_kill_switch(enabled=True, changed_at_ms=1_000_000)
    assert killed_open.active is not None
    assert killed_open.active.status == MissionStatus.SHADOW_OPEN
    with pytest.raises(MissionError, match="must close"):
        controller.cancel(cancelled_at_ms=1_100_000)
    closed = controller.close_shadow(
        closed_at_ms=1_200_000, raw_close=card.sl, reason="KILL_SWITCH"
    )
    assert closed.receipt is not None
    assert closed.terminal_reason == "KILL_SWITCH"


def test_corruption_symlink_and_insecure_mode_are_never_silently_reset(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    controller = AITradeMissionController(path)
    _request(controller)
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["payload"]["revision"] += 1
    path.write_text(json.dumps(envelope), encoding="utf-8")
    tampered = path.read_bytes()
    with pytest.raises(MissionPersistenceError, match="checksum"):
        controller.state()
    assert path.read_bytes() == tampered

    real = tmp_path / "real.json"
    real.write_text("do not touch", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(real)
    with pytest.raises(MissionPersistenceError, match="regular non-symlink"):
        AITradeMissionController(link).state()
    assert real.read_text(encoding="utf-8") == "do not touch"

    clean = tmp_path / "clean.json"
    clean_controller = AITradeMissionController(clean)
    _request(clean_controller, mission_id="clean")
    clean.chmod(0o640)
    with pytest.raises(MissionPersistenceError, match="exactly 0600"):
        clean_controller.state()


def test_cli_exposes_shadow_fsm_without_a_live_mode(tmp_path: Path, capsys) -> None:
    path = tmp_path / "cli.json"
    cards = tmp_path / "cards.json"
    cards.write_text(json.dumps([_card().payload()]), encoding="utf-8")
    base = ["--state", str(path)]
    assert cli_main(
        base
        + [
            "request",
            "--mission-id",
            "cli-1",
            "--at-ms",
            str(REQUESTED),
            "--allow-symbol",
            "BTCUSDT",
        ]
    ) == 0
    assert cli_main(base + ["freeze", "--cards-json", str(cards), "--at-ms", str(FROZEN)]) == 0
    card_id = AITradeMissionController(path).state().active.cards[0].card_id
    assert cli_main(base + ["propose", "--select", card_id, "--at-ms", str(PROPOSED)]) == 0
    assert cli_main(base + ["validate", "--at-ms", str(VALIDATED)]) == 0
    assert cli_main(base + ["open", "--at-ms", str(NEXT_OPEN), "--price", "100"]) == 0
    assert cli_main(
        base + ["close", "--at-ms", "1200000", "--price", "104", "--reason", "TP"]
    ) == 0
    output = capsys.readouterr().out
    assert '"mode": "shadow"' in output
    assert '"broker_calls": false' in output
    assert AITradeMissionController(path).state().history[-1].status == MissionStatus.SHADOW_CLOSED
