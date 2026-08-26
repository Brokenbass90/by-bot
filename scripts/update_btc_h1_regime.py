#!/usr/bin/env python3
"""Operate the explicit public BTC H1 regime updater/restart gate.

No flag means no network or filesystem mutation.  ``--enable`` is required to
fetch public data and update state; ``--check-restart`` only verifies an
already persisted fresh receipt.  Neither path can place orders or grant
money/promotion authority.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.btc_h1_regime_updater import (  # noqa: E402
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_STATE_PATH,
    BTCRegimeUpdaterError,
    UPDATER_AUTHORITY,
    update_btc_h1_regime,
    verify_btc_h1_regime_restart,
)
from bot.persisted_btc_h1_regime import BTCRegimeContractError  # noqa: E402


def _now_ms() -> int:
    return int(time.time() * 1000)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--enable",
        action="store_true",
        help="explicitly enable public fetch and state update (default: off)",
    )
    modes.add_argument(
        "--check-restart",
        action="store_true",
        help="verify existing persisted state and freshness only",
    )
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--max-age-ms", type=int, default=300_000)
    parser.add_argument("--history-limit", type=int, default=DEFAULT_HISTORY_LIMIT)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--observed-at-ms", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.check_restart:
            proof = verify_btc_h1_regime_restart(
                args.state_path,
                observed_at_ms=args.observed_at_ms or _now_ms(),
                max_age_ms=args.max_age_ms,
            )
            payload = {
                "status": "PASS",
                "gate": "btc_h1_regime_restart",
                "receipt_sha256": proof.receipt_sha256,
                "state_sha256": proof.state_sha256,
                "last_closed_h1_ts_ms": proof.last_closed_h1_ts_ms,
                "observed_at_ms": proof.observed_at_ms,
                "regime_value": proof.regime_value,
                "research_only": proof.research_only,
                "money_authority": proof.money_authority,
                "orders_allowed": proof.orders_allowed,
            }
        else:
            result = update_btc_h1_regime(
                args.state_path,
                enabled=args.enable,
                limit=args.history_limit,
                timeout=args.timeout,
                max_age_ms=args.max_age_ms,
                observed_at_ms=args.observed_at_ms,
            )
            payload = {
                "status": "PASS",
                "gate": "btc_h1_regime_updater",
                "authority": UPDATER_AUTHORITY,
                "action": result.action,
                "applied_bars": result.applied_bars,
                "receipt_sha256": result.receipt.receipt_sha256,
                "state_sha256": result.receipt.state.state_sha256,
                "observed_at_ms": result.observed_at_ms,
                "research_only": result.research_only,
                "money_authority": result.money_authority,
                "orders_allowed": result.orders_allowed,
            }
        print(json.dumps(payload, sort_keys=True))
        return 0
    except (BTCRegimeUpdaterError, BTCRegimeContractError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL_CLOSED",
                    "gate": "btc_h1_regime",
                    "error_code": getattr(exc, "code", type(exc).__name__),
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
