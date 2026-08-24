from __future__ import annotations

import ast
from datetime import datetime, timezone

from scripts.alpaca_health_auditor import (
    _status_exit_code,
    build_operations_from_manifest,
    build_receipt,
    evaluate_health,
)


NOW = datetime(2026, 8, 24, 14, 0, tzinfo=timezone.utc)


def _broker_truth(*, stop_price: str = "108.20", stop_qty: str = "0.5", tif: str = "day"):
    return {
        "schema_id": "alpaca_broker_truth_readonly_v1",
        "authority": "read_only_get_no_order_mutation",
        "broker_mode": "LIVE",
        "generated_at_utc": "2026-08-24T13:59:00+00:00",
        "account": {"status": "ACTIVE"},
        "position_count": 1,
        "open_order_count": 1,
        "positions": [
            {
                "symbol": "SCHW",
                "side": "long",
                "qty": 0.5,
                "avg_entry_price": "101.552",
            }
        ],
        "open_orders": [
            {
                "symbol": "SCHW",
                "side": "sell",
                "type": "stop",
                "status": "new",
                "qty": stop_qty,
                "filled_qty": "0",
                "stop_price": stop_price,
                "time_in_force": tif,
            }
        ],
    }


def _floor_state():
    return {
        "SCHW": {
            "entry_price": 101.552,
            "qty": 0.5,
            "accepted_stop_floor": 108.20,
            "lifecycle_first_seen_at_utc": "2026-08-10T13:30:00+00:00",
        }
    }


def _operations():
    return {
        "authority": "calculated_local_files_and_logs",
        "broker_truth_max_age_minutes": 5,
        "safe_hold_expected": True,
        "send_orders": True,
        "allow_new_entries": False,
        "schedule_expected_active": True,
        "protection_last_success_at_utc": "2026-08-24T13:50:00+00:00",
        "protection_max_age_minutes": 30,
        "bridge_last_success_at_utc": "2026-08-24T13:40:00+00:00",
        "bridge_max_age_minutes": 45,
        "candidate_asof_utc": "2026-08-01T00:00:00+00:00",
        "candidate_max_age_days": 45,
        "source_hashes": {
            "bridge": {"expected": "abc", "observed": "abc"},
            "manager": {"expected": "def", "observed": "def"},
        },
    }


def test_healthy_fractional_day_stop_is_covered_but_explicitly_warned():
    result = evaluate_health(_broker_truth(), _floor_state(), _operations(), now_utc=NOW)

    assert result["status"] == "WARN"
    assert result["coverage"][0]["fully_covered"] is True
    assert result["coverage"][0]["floor_preserved"] is True
    assert {row["code"] for row in result["issues"]} == {
        "fractional_day_stop_not_persistent_across_sessions"
    }
    assert _status_exit_code(result["status"]) == 2


def test_missing_coverage_lowered_floor_and_stale_or_mismatched_ops_are_critical():
    ops = _operations()
    ops["allow_new_entries"] = True
    ops["protection_last_success_at_utc"] = "2026-08-24T12:00:00+00:00"
    ops["candidate_asof_utc"] = "2026-06-01T00:00:00+00:00"
    ops["source_hashes"]["manager"]["observed"] = "wrong"

    result = evaluate_health(
        _broker_truth(stop_price="103.00", stop_qty="0.25"),
        _floor_state(),
        ops,
        now_utc=NOW,
    )

    assert result["status"] == "CRITICAL"
    codes = {row["code"] for row in result["issues"]}
    assert "position_not_fully_protected" in codes
    assert "broker_stop_below_accepted_floor" in codes
    assert "protective_manager_stale" in codes
    assert "candidate_snapshot_stale" in codes
    assert "source_hash_mismatch" in codes
    assert "safe_hold_new_entries_enabled" in codes


def test_missing_or_wrong_lifecycle_floor_fails_closed():
    missing = evaluate_health(_broker_truth(), {}, _operations(), now_utc=NOW)
    wrong = _floor_state()
    wrong["SCHW"]["entry_price"] = 99.0
    mismatched = evaluate_health(_broker_truth(), wrong, _operations(), now_utc=NOW)

    assert missing["status"] == "CRITICAL"
    assert "accepted_floor_missing" in {row["code"] for row in missing["issues"]}
    assert mismatched["status"] == "CRITICAL"
    assert "accepted_floor_lifecycle_mismatch" in {
        row["code"] for row in mismatched["issues"]
    }


def test_missing_lifecycle_timestamp_fails_closed():
    floor = _floor_state()
    del floor["SCHW"]["lifecycle_first_seen_at_utc"]

    result = evaluate_health(_broker_truth(), floor, _operations(), now_utc=NOW)

    assert result["status"] == "CRITICAL"
    assert "accepted_floor_lifecycle_mismatch" in {
        row["code"] for row in result["issues"]
    }


def test_invalid_fixed_stop_price_and_short_position_fail_closed():
    missing_stop = _broker_truth(stop_price="")
    missing_result = evaluate_health(
        missing_stop, _floor_state(), _operations(), now_utc=NOW
    )
    short = _broker_truth()
    short["positions"][0]["side"] = "short"
    short_result = evaluate_health(short, _floor_state(), _operations(), now_utc=NOW)

    assert "protective_stop_price_invalid" in {
        row["code"] for row in missing_result["issues"]
    }
    assert "unsupported_non_long_position" in {
        row["code"] for row in short_result["issues"]
    }


def test_stale_or_incomplete_broker_truth_fails_closed():
    stale = _broker_truth()
    stale["generated_at_utc"] = "2026-08-24T13:30:00+00:00"
    stale_result = evaluate_health(stale, _floor_state(), _operations(), now_utc=NOW)

    incomplete = _broker_truth()
    del incomplete["open_orders"]
    incomplete_result = evaluate_health(
        incomplete, _floor_state(), _operations(), now_utc=NOW
    )

    assert "broker_truth_stale" in {row["code"] for row in stale_result["issues"]}
    assert "broker_truth_incomplete" in {
        row["code"] for row in incomplete_result["issues"]
    }


def test_missing_safe_hold_switch_evidence_fails_closed():
    operations = _operations()
    operations["allow_new_entries"] = None

    result = evaluate_health(_broker_truth(), _floor_state(), operations, now_utc=NOW)

    assert "safe_hold_state_unknown" in {row["code"] for row in result["issues"]}


def test_future_operational_timestamps_fail_closed():
    operations = _operations()
    operations["protection_last_success_at_utc"] = "2026-08-24T15:00:00+00:00"
    operations["bridge_last_success_at_utc"] = "2026-08-24T15:00:00+00:00"
    operations["candidate_asof_utc"] = "2026-08-25T00:00:00+00:00"

    result = evaluate_health(_broker_truth(), _floor_state(), operations, now_utc=NOW)
    codes = {row["code"] for row in result["issues"]}

    assert "protective_manager_stale" in codes
    assert "alpaca_bridge_stale" in codes
    assert "candidate_snapshot_from_future" in codes


def test_cli_has_no_operations_json_bypass():
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "alpaca_health_auditor.py").read_text(encoding="utf-8")

    assert 'parser.add_argument("--operations-json"' not in text


def test_manifest_collector_calculates_source_hashes_logs_and_safe_hold(tmp_path):
    bridge = tmp_path / "bridge.py"
    manager = tmp_path / "manager.py"
    bridge.write_text("bridge\n", encoding="utf-8")
    manager.write_text("manager\n", encoding="utf-8")
    bridge_log = tmp_path / "bridge.log"
    protection_log = tmp_path / "protection.log"
    bridge_log.write_text(
        '{"generated_at_utc":"2026-08-24T13:40:00+00:00","latest_entry_day":"2026-07-31"}\n',
        encoding="utf-8",
    )
    protection_log.write_text(
        '{"generated_at_utc":"2026-08-24T13:50:00+00:00"}\n',
        encoding="utf-8",
    )
    safe_hold = tmp_path / "safe_hold.env"
    safe_hold.write_text("ALPACA_ALLOW_NEW_ENTRIES=0\n", encoding="utf-8")
    manifest = {
        "schema_id": "alpaca_health_auditor_manifest_v1",
        "expected_broker_mode": "LIVE",
        "safe_hold_expected": True,
        "send_orders": True,
        "broker_truth_max_age_minutes": 5,
        "candidate_max_age_days": 45,
        "bridge_max_age_minutes": 90,
        "protection_max_age_minutes": 30,
        "schedule": {
            "weekdays_utc": [0, 1, 2, 3, 4],
            "start_utc": "13:30",
            "end_utc": "22:00",
        },
        "env_files": ["safe_hold.env"],
        "bridge_log_path": "bridge.log",
        "protection_log_path": "protection.log",
        "source_files": {
            "bridge": {
                "path": "bridge.py",
                "expected_sha256": __import__("hashlib").sha256(b"bridge\n").hexdigest(),
            },
            "manager": {
                "path": "manager.py",
                "expected_sha256": __import__("hashlib").sha256(b"manager\n").hexdigest(),
            },
        },
    }

    operations = build_operations_from_manifest(manifest, root=tmp_path, now_utc=NOW)

    assert operations["authority"] == "calculated_local_files_and_logs"
    assert operations["allow_new_entries"] is False
    assert operations["schedule_expected_active"] is True
    assert operations["candidate_asof_utc"].startswith("2026-07-31")
    assert all(
        row["expected"] == row["observed"]
        for row in operations["source_hashes"].values()
    )


def test_hash_bound_receipt_is_stable_and_sensitive_to_evidence():
    result = evaluate_health(_broker_truth(), _floor_state(), _operations(), now_utc=NOW)
    first = build_receipt(result)
    second = build_receipt(result)

    assert first == second
    assert len(first["evidence_sha256"]) == 64

    changed = evaluate_health(
        _broker_truth(stop_price="108.21"),
        _floor_state(),
        _operations(),
        now_utc=NOW,
    )
    assert build_receipt(changed)["evidence_sha256"] != first["evidence_sha256"]


def test_non_live_broker_truth_cannot_be_reported_as_live_health():
    broker = _broker_truth()
    broker["broker_mode"] = "PAPER"
    result = evaluate_health(broker, _floor_state(), _operations(), now_utc=NOW)

    assert result["status"] == "CRITICAL"
    assert "unexpected_broker_mode" in {row["code"] for row in result["issues"]}


def test_auditor_has_no_broker_mutation_call_path():
    tree = ast.parse(
        open(__import__("scripts.alpaca_health_auditor", fromlist=["x"]).__file__, encoding="utf-8").read()
    )
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not called_attributes.intersection(
        {
            "cancel_order",
            "close_position",
            "replace_order",
            "submit_bracket_order",
            "submit_market_buy",
            "submit_market_buy_qty",
            "submit_stop_sell",
            "submit_trailing_stop_sell",
        }
    )


def test_launcher_is_read_only_and_uses_explicit_live_inputs():
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "run_alpaca_health_auditor.sh").read_text(
        encoding="utf-8"
    )

    assert "configs/alpaca_live_v38.env" in text
    assert "configs/alpaca_health_auditor_v1.json" in text
    assert "runtime/alpaca_live_v38/protective_exit_hwm.json" in text
    assert "--telegram-alert" not in text
    assert "--send-orders" not in text
