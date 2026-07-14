#!/usr/bin/env python3
"""Run a hash-pinned, feed-bound AI shadow mission replay.

There are deliberately no CLI flags for entry/exit prices, execution times, or
outcome reasons.  Those values are derived from the pinned M5 feed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.ai_trade_mission import AIDecision, MissionError, MissionPersistenceError  # noqa: E402
from bot.ai_trade_mission_replay import (  # noqa: E402
    ReplayEvidenceError,
    read_candidate_cards,
    run_feed_bound_replay,
    write_replay_receipt,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Hash-pinned M5 feed replay for one research-only AI shadow mission."
    )
    parser.add_argument("--feed", required=True, type=Path)
    parser.add_argument("--feed-sha256", required=True)
    parser.add_argument("--cards-json", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--mission-id", required=True)
    parser.add_argument("--max-bars", required=True, type=int)
    parser.add_argument("--min-rr", type=float, default=1.5)
    parser.add_argument("--fee-bps-per-side", type=float, default=6.0)
    parser.add_argument("--slippage-bps-per-side", type=float, default=2.0)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--select", metavar="FROZEN_CARD_ID")
    choice.add_argument("--abstain", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.receipt.exists():
            raise ReplayEvidenceError("receipt already exists; overwrite is forbidden")
        cards = read_candidate_cards(args.cards_json)
        decision = AIDecision.select(args.select) if args.select else AIDecision.abstain()
        envelope = run_feed_bound_replay(
            feed_path=args.feed,
            expected_feed_sha256=args.feed_sha256,
            state_path=args.state,
            mission_id=args.mission_id,
            cards=cards,
            decision=decision,
            max_bars=args.max_bars,
            min_rr=args.min_rr,
            fee_bps_per_side=args.fee_bps_per_side,
            slippage_bps_per_side=args.slippage_bps_per_side,
        )
        write_replay_receipt(args.receipt, envelope)
        print(json.dumps(envelope, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except (MissionError, MissionPersistenceError, ReplayEvidenceError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
