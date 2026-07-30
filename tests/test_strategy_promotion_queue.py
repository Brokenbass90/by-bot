from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.validate_strategy_promotion_queue import validate_queue


ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / "configs" / "research" / "strategy_promotion_queue_20260730.json"


def _payload() -> dict:
    return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))


def test_canonical_queue_passes() -> None:
    validate_queue(_payload())


def test_queue_cannot_authorize_capital() -> None:
    payload = _payload()
    payload["capital_authorized"] = True
    with pytest.raises(ValueError, match="cannot authorize capital"):
        validate_queue(payload)


def test_queue_fails_when_active_wip_exceeds_limit() -> None:
    payload = _payload()
    payload["wip"]["active"].append("sixth_job")
    with pytest.raises(ValueError, match="exceeds WIP"):
        validate_queue(payload)


def test_queue_rejects_duplicate_strategy_identity() -> None:
    payload = _payload()
    duplicate = copy.deepcopy(payload["crypto_queue"][0])
    duplicate["rank"] = 99
    payload["crypto_queue"].append(duplicate)
    with pytest.raises(ValueError, match="duplicate strategy id"):
        validate_queue(payload)


def test_launch_order_must_reference_a_known_candidate() -> None:
    payload = _payload()
    payload["next_launch_order"][0]["launch"] = "does_not_exist"
    with pytest.raises(ValueError, match="unknown launch id"):
        validate_queue(payload)
