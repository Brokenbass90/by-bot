from __future__ import annotations

import pytest

from bot import deepseek_action_executor as executor


def test_env_mutations_are_physically_quarantined() -> None:
    with pytest.raises(PermissionError, match="quarantined"):
        executor.patch_env_file([{"env_key": "ATT1_RISK_MULT", "new_value": "1.0"}])


def test_approved_proposal_cannot_mutate_or_change_queue_status() -> None:
    queue = [
        {
            "id": 7,
            "status": "approved",
            "payload": {"changes": [{"env_key": "ATT1_RISK_MULT", "new_value": "1.0"}]},
        }
    ]

    result = executor.execute_proposal(7, queue, deploy=False)

    assert "not executed" in result
    assert queue[0]["status"] == "approved"


def test_quarantined_diff_never_echoes_env_values() -> None:
    pending = [
        {
            "id": 1,
            "payload": {
                "changes": [
                    {"env_key": "DEEPSEEK_API_KEY", "new_value": "super-secret-value"},
                    {"env_key": "ATT1_RISK_MULT", "new_value": "0.9"},
                ]
            },
        }
    ]

    result = executor.diff_pending_changes(pending)

    assert "quarantined" in result
    assert "super-secret-value" not in result
    assert "0.9" not in result


def test_rollback_is_quarantined() -> None:
    assert "Rollback command quarantined" in executor.rollback_env()
