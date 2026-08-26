from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.bootstrap_alpaca_paper_floor import (
    PaperFloorBootstrapError,
    build_historical_floor_state,
    write_bootstrap_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]


def _position(symbol: str, qty: float, entry: float, current: float) -> dict:
    return {
        "symbol": symbol,
        "qty": str(qty),
        "avg_entry_price": str(entry),
        "current_price": str(current),
    }


def _stop(symbol: str, qty: float, stop: float, created: str, status: str = "expired") -> dict:
    return {
        "id": f"{symbol}-{stop}",
        "symbol": symbol,
        "side": "sell",
        "type": "stop",
        "status": status,
        "qty": str(qty),
        "filled_qty": "0",
        "stop_price": str(stop),
        "time_in_force": "day",
        "created_at": created,
    }


def test_build_uses_highest_broker_accepted_exact_qty_floor() -> None:
    positions = [_position("SNOW", 1.18466942, 289.71, 316.83)]
    orders = [
        _stop("SNOW", 1.18466942, 309.06, "2026-08-19T20:30:31+00:00"),
        _stop("SNOW", 1.18466942, 312.47, "2026-08-18T20:30:28+00:00"),
        _stop("SNOW", 2.0, 315.0, "2026-08-20T20:30:00+00:00"),
        _stop("SNOW", 1.18466942, 314.0, "2026-08-20T20:30:00+00:00", "rejected"),
    ]

    state, evidence = build_historical_floor_state(
        positions,
        orders,
        observed_at_utc=datetime(2026, 8, 26, 6, 30, tzinfo=timezone.utc),
    )

    assert state["SNOW"]["accepted_stop_floor"] == 312.47
    assert state["SNOW"]["entry_price"] == 289.71
    assert state["SNOW"]["qty"] == 1.18466942
    assert state["SNOW"]["hwm"] == 316.83
    assert state["SNOW"]["accepted_order_id"] == "SNOW-312.47"
    assert state["SNOW"]["bootstrap_source"] == "historical_broker_fixed_stop_exact_qty"
    assert evidence[0]["candidate_count"] == 2


def test_build_fails_closed_when_any_open_position_has_no_historical_floor() -> None:
    positions = [
        _position("SCHW", 1.84, 111.75, 112.27),
        _position("SNOW", 1.18, 289.71, 316.83),
    ]
    orders = [_stop("SCHW", 1.84, 106.10, "2026-08-19T20:30:30+00:00")]

    with pytest.raises(PaperFloorBootstrapError, match="missing_historical_floor:SNOW"):
        build_historical_floor_state(
            positions,
            orders,
            observed_at_utc=datetime.now(timezone.utc),
        )


def test_artifacts_are_private_and_never_overwrite_existing_state(tmp_path: Path) -> None:
    state_path = tmp_path / "protective_exit_hwm.json"
    receipt_path = tmp_path / "bootstrap_receipt.json"
    state = {
        "SCHW": {
            "entry_price": 111.75,
            "qty": 1.84,
            "hwm": 112.27,
            "lifecycle_first_seen_at_utc": "2026-08-19T20:30:30+00:00",
            "accepted_stop_floor": 106.10,
        }
    }

    write_bootstrap_artifacts(
        state_path,
        receipt_path,
        state=state,
        evidence=[{"symbol": "SCHW"}],
        generated_at_utc="2026-08-26T06:30:00+00:00",
    )
    assert os.stat(state_path).st_mode & 0o777 == 0o600
    assert os.stat(receipt_path).st_mode & 0o777 == 0o600
    assert json.loads(receipt_path.read_text())["state_sha256"]

    with pytest.raises(PaperFloorBootstrapError, match="state_already_exists"):
        write_bootstrap_artifacts(
            state_path,
            receipt_path,
            state=state,
            evidence=[],
            generated_at_utc="2026-08-26T06:31:00+00:00",
        )


def test_direct_cli_without_ack_is_fail_closed_before_network_or_writes() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/bootstrap_alpaca_paper_floor.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload == {
        "live_account_authority": False,
        "network_calls": False,
        "orders_allowed": False,
        "required_ack": "PAPER_HISTORICAL_STOP_FLOOR_BOOTSTRAP",
        "status": "PAPER_FLOOR_BOOTSTRAP_DISABLED",
        "writes": False,
    }


def test_bootstrap_client_surface_is_read_only() -> None:
    source = (ROOT / "scripts/bootstrap_alpaca_paper_floor.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    client_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "client"
    }

    assert client_calls == {"list_orders", "list_positions"}
