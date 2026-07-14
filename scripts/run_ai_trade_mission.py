#!/usr/bin/env python3
"""Local CLI for the research-only one-shot AI shadow mission controller.

No command can select ``live`` mode or call a broker.  Candidate cards come
from a strict JSON file, while the AI authority is limited to the mutually
exclusive ``--select CARD_ID`` and ``--abstain`` flags.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.ai_trade_mission import (  # noqa: E402
    AIDecision,
    AITradeMissionController,
    MissionBook,
    MissionError,
    MissionPersistenceError,
    MissionRecord,
    candidate_from_input,
    mission_book_to_dict,
    mission_record_to_dict,
)


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _at(value: int | None) -> int:
    return _now_ms() if value is None else value


def _read_cards(path: Path) -> list[Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MissionError(f"cannot read candidate JSON: {exc}") from exc
    if not isinstance(raw, list):
        raise MissionError("candidate JSON root must be an array")
    return [candidate_from_input(item) for item in raw]


def _emit(value: MissionBook | MissionRecord) -> None:
    payload = (
        mission_book_to_dict(value)
        if isinstance(value, MissionBook)
        else mission_record_to_dict(value)
    )
    print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Research-only one-shot AI trade mission (shadow mode is immutable)."
    )
    parser.add_argument("--state", required=True, type=Path, help="Atomic local JSON state file.")
    sub = parser.add_subparsers(dest="command", required=True)

    request = sub.add_parser("request", help="Request one shadow mission.")
    request.add_argument("--mission-id", default="", help="Replay identity; defaults to UUID4.")
    request.add_argument("--at-ms", type=int)
    request.add_argument("--allow-symbol", action="append", required=True)
    request.add_argument("--freshness-ms", type=int, default=900_000)
    request.add_argument("--min-rr", type=float, default=1.5)
    request.add_argument("--execution-interval-ms", type=int, default=300_000)
    request.add_argument("--fee-bps-per-side", type=float, default=6.0)
    request.add_argument("--slippage-bps-per-side", type=float, default=2.0)

    freeze = sub.add_parser("freeze", help="Freeze deterministic screener cards.")
    freeze.add_argument("--cards-json", required=True, type=Path)
    freeze.add_argument("--at-ms", type=int)

    propose = sub.add_parser("propose", help="Record the complete AI decision surface.")
    choice = propose.add_mutually_exclusive_group(required=True)
    choice.add_argument("--select", metavar="CARD_ID")
    choice.add_argument("--abstain", action="store_true")
    propose.add_argument("--at-ms", type=int)

    validate = sub.add_parser("validate", help="Apply allowlist/freshness/RR gates.")
    validate.add_argument("--at-ms", type=int)

    opened = sub.add_parser("open", help="Simulate only the exact next-grid open.")
    opened.add_argument("--at-ms", type=int, required=True)
    opened.add_argument("--price", type=float, required=True)

    close = sub.add_parser("close", help="Close shadow position and freeze receipt.")
    close.add_argument("--at-ms", type=int, required=True)
    close.add_argument("--price", type=float, required=True)
    close.add_argument("--reason", required=True)

    cancel = sub.add_parser("cancel", help="Cancel a not-yet-open mission.")
    cancel.add_argument("--at-ms", type=int)
    cancel.add_argument("--reason", default="OPERATOR_CANCEL")

    kill = sub.add_parser("kill", help="Latch kill switch; pre-open mission is cancelled.")
    kill.add_argument("--at-ms", type=int)

    unkill = sub.add_parser("unkill", help="Explicitly clear the kill latch.")
    unkill.add_argument("--at-ms", type=int)

    sub.add_parser("show", help="Print durable state.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    controller = AITradeMissionController(args.state)
    try:
        if args.command == "request":
            result = controller.request(
                mission_id=args.mission_id or uuid.uuid4().hex,
                requested_at_ms=_at(args.at_ms),
                allowlist=args.allow_symbol,
                freshness_ms=args.freshness_ms,
                min_rr=args.min_rr,
                execution_interval_ms=args.execution_interval_ms,
                fee_bps_per_side=args.fee_bps_per_side,
                slippage_bps_per_side=args.slippage_bps_per_side,
            )
        elif args.command == "freeze":
            result = controller.freeze_snapshot(
                _read_cards(args.cards_json), frozen_at_ms=_at(args.at_ms)
            )
        elif args.command == "propose":
            decision = AIDecision.select(args.select) if args.select else AIDecision.abstain()
            result = controller.propose(decision, proposed_at_ms=_at(args.at_ms))
        elif args.command == "validate":
            result = controller.validate(validated_at_ms=_at(args.at_ms))
        elif args.command == "open":
            result = controller.open_shadow(opened_at_ms=args.at_ms, raw_open=args.price)
        elif args.command == "close":
            result = controller.close_shadow(
                closed_at_ms=args.at_ms, raw_close=args.price, reason=args.reason
            )
        elif args.command == "cancel":
            result = controller.cancel(cancelled_at_ms=_at(args.at_ms), reason=args.reason)
        elif args.command == "kill":
            result = controller.set_kill_switch(enabled=True, changed_at_ms=_at(args.at_ms))
        elif args.command == "unkill":
            result = controller.set_kill_switch(enabled=False, changed_at_ms=_at(args.at_ms))
        else:
            result = controller.state()
        _emit(result)
        return 0
    except (MissionError, MissionPersistenceError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
