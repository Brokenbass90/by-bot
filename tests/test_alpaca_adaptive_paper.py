import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from scripts import alpaca_adaptive_paper as adaptive_paper
from scripts.alpaca_adaptive_paper import build_bridge_env
from scripts.alpaca_adaptive_shadow import write_bridge_picks_csv


def _report(**overrides):
    report = {
        "generated_at_utc": "2026-06-18T12:00:00+00:00",
        "max_positions": 4,
        "exposure": 1.0,
        "reason": "ok",
        "picks": [
            {
                "symbol": "AAPL",
                "score": 1.25,
                "weight": 0.28,
                "vol": 0.02,
                "mom_fast": 0.05,
                "mom_slow": 0.12,
                "latest_close": 200.0,
            }
        ],
    }
    report.update(overrides)
    return report


def test_adaptive_csv_preserves_risk_parity_weight_as_bridge_score(tmp_path: Path):
    path = tmp_path / "picks.csv"
    write_bridge_picks_csv(_report(), path)
    with path.open(newline="", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    assert row["month"] == "2026-06"
    assert row["ticker"] == "AAPL"
    assert float(row["score"]) == 0.28
    assert float(row["base_score"]) == 1.25


def test_bridge_env_scales_allocation_by_regime_exposure(tmp_path: Path):
    env = build_bridge_env(
        _report(exposure=0.4),
        picks_csv=tmp_path / "picks.csv",
        capital=1000.0,
        target_alloc_pct=70.0,
        send_orders=False,
    )
    assert float(env["ALPACA_TARGET_ALLOC_PCT"]) == 0.28
    assert env["ALPACA_SEND_ORDERS"] == "0"
    assert env["ALPACA_BROKER_PROTECTION_REQUIRED"] == "1"
    assert env["MONTHLY_ATR_SIZING"] == "0"


def test_empty_cash_is_allowed_only_for_explicit_bear_regime(tmp_path: Path):
    bear = build_bridge_env(
        _report(picks=[], exposure=0.0, reason="market_below_regime_sma_cash"),
        picks_csv=tmp_path / "picks.csv",
        capital=1000.0,
        target_alloc_pct=70.0,
        send_orders=True,
    )
    filtered = build_bridge_env(
        _report(picks=[], exposure=0.0, reason="no_qualifying_names"),
        picks_csv=tmp_path / "picks.csv",
        capital=1000.0,
        target_alloc_pct=70.0,
        send_orders=True,
    )
    assert bear["ALPACA_ALLOW_EMPTY_PICKS_FOR_CASH"] == "1"
    assert filtered["ALPACA_ALLOW_EMPTY_PICKS_FOR_CASH"] == "0"


def test_reusable_selection_files_are_stable_contract(tmp_path: Path):
    report = _report()
    report_path = tmp_path / "latest_selection.json"
    picks_path = tmp_path / "current_cycle_picks.csv"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    write_bridge_picks_csv(report, picks_path)

    loaded = json.loads(report_path.read_text(encoding="utf-8"))
    with picks_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert loaded["picks"][0]["symbol"] == "AAPL"
    assert rows[0]["ticker"] == "AAPL"


def test_bridge_env_scopes_floor_state_to_adaptive_paper_runtime(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(
        "ALPACA_PROTECTIVE_EXIT_RUNTIME_DIR",
        "/root/by-bot/runtime/alpaca_live_v38",
    )
    monkeypatch.setenv(
        "ALPACA_PROTECTIVE_EXIT_HWM_PATH",
        "/root/by-bot/runtime/alpaca_live_v38/protective_exit_hwm.json",
    )
    picks_path = tmp_path / "adaptive-paper" / "current_cycle_picks.csv"

    env = build_bridge_env(
        _report(),
        picks_csv=picks_path,
        capital=1000.0,
        target_alloc_pct=70.0,
        send_orders=False,
    )

    expected_runtime = picks_path.parent / "protective_exit"
    assert env["ALPACA_PROTECTIVE_EXIT_RUNTIME_DIR"] == str(expected_runtime)
    assert env["ALPACA_PROTECTIVE_EXIT_HWM_PATH"] == str(
        expected_runtime / "protective_exit_hwm.json"
    )
    assert "alpaca_live_v38" not in env["ALPACA_PROTECTIVE_EXIT_HWM_PATH"]


def test_refresh_stages_previous_open_candidate_before_overwriting_selection(tmp_path: Path):
    registry_path = tmp_path / "owned_position_lifecycles.json"

    owned = adaptive_paper.stage_adaptive_owned_symbols(
        registry_path,
        previous_cycle_symbols={"TMO", "SCHW"},
        selected_symbols={"BAC", "SCHW"},
    )

    assert owned == {"BAC", "SCHW", "TMO"}
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    assert payload["schema_id"] == "alpaca_adaptive_paper_owned_positions_v1"
    assert payload["owned_symbols"] == ["BAC", "SCHW", "TMO"]
    assert os.stat(registry_path).st_mode & 0o777 == 0o600


def test_fresh_authoritative_receipt_prunes_only_broker_flat_ownership(tmp_path: Path):
    registry_path = tmp_path / "owned_position_lifecycles.json"
    receipt_path = tmp_path / "latest_manager_receipt.json"
    adaptive_paper.stage_adaptive_owned_symbols(
        registry_path,
        previous_cycle_symbols={"TMO", "SCHW"},
        selected_symbols={"BAC"},
    )

    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at_utc": "2026-08-25T14:00:47+00:00",
                "report": {
                    "broker_truth_authoritative": True,
                    "broker_truth_after": {
                        "generated_at_utc": "2026-08-25T14:00:46+00:00",
                        "position_symbols": ["SCHW", "BAC"],
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    assert adaptive_paper.reconcile_adaptive_owned_symbols(
        registry_path,
        receipt_path,
        previous_receipt_identity=None,
        run_started_at_utc=datetime(2026, 8, 25, 14, 0, tzinfo=timezone.utc),
    ) is True
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    assert payload["owned_symbols"] == ["BAC", "SCHW"]


def test_stale_or_non_authoritative_receipt_cannot_drop_ownership(tmp_path: Path):
    registry_path = tmp_path / "owned_position_lifecycles.json"
    receipt_path = tmp_path / "latest_manager_receipt.json"
    adaptive_paper.stage_adaptive_owned_symbols(
        registry_path,
        previous_cycle_symbols={"TMO"},
        selected_symbols={"SCHW"},
    )
    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "report": {
                    "broker_truth_authoritative": False,
                    "broker_truth_after": {
                        "generated_at_utc": "2026-08-25T14:00:00+00:00",
                        "position_symbols": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    current_identity = adaptive_paper.receipt_identity(receipt_path)

    assert adaptive_paper.reconcile_adaptive_owned_symbols(
        registry_path,
        receipt_path,
        previous_receipt_identity=current_identity,
        run_started_at_utc=datetime(2026, 8, 25, 14, 0, tzinfo=timezone.utc),
    ) is False
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    assert payload["owned_symbols"] == ["SCHW", "TMO"]

    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "report": {
                    "broker_truth_authoritative": False,
                    "broker_truth_after": {
                        "generated_at_utc": "2026-08-25T14:00:01+00:00",
                        "position_symbols": [],
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert adaptive_paper.reconcile_adaptive_owned_symbols(
        registry_path,
        receipt_path,
        previous_receipt_identity=current_identity,
        run_started_at_utc=datetime(2026, 8, 25, 14, 0, tzinfo=timezone.utc),
    ) is False
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    assert payload["owned_symbols"] == ["SCHW", "TMO"]


def test_changed_but_old_authoritative_receipt_cannot_prune_ownership(tmp_path: Path):
    registry_path = tmp_path / "owned_position_lifecycles.json"
    receipt_path = tmp_path / "latest_manager_receipt.json"
    adaptive_paper.stage_adaptive_owned_symbols(
        registry_path,
        previous_cycle_symbols={"TMO"},
        selected_symbols={"SCHW"},
    )
    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "report": {
                    "broker_truth_authoritative": True,
                    "broker_truth_after": {
                        "generated_at_utc": "2020-01-01T00:00:00+00:00",
                        "position_symbols": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    assert adaptive_paper.reconcile_adaptive_owned_symbols(
        registry_path,
        receipt_path,
        previous_receipt_identity=None,
        run_started_at_utc=datetime(2026, 8, 25, 14, 0, tzinfo=timezone.utc),
    ) is False
    assert json.loads(registry_path.read_text())["owned_symbols"] == ["SCHW", "TMO"]


def test_existing_malformed_previous_picks_fail_closed(tmp_path: Path):
    picks = tmp_path / "current_cycle_picks.csv"
    picks.write_text("wrong_header\nTMO\n", encoding="utf-8")

    try:
        adaptive_paper._picks_symbols(picks)
    except adaptive_paper.AdaptiveOwnershipError as exc:
        assert str(exc) == "invalid_previous_picks_csv"
    else:
        raise AssertionError("malformed existing picks must fail closed")


def test_main_stages_old_picks_before_refresh_and_uses_fresh_paper_receipt(
    tmp_path: Path, monkeypatch
):
    runtime = tmp_path / "adaptive"
    runtime.mkdir()
    picks = runtime / "current_cycle_picks.csv"
    picks.write_text("month,ticker\n2026-08,TMO\n", encoding="utf-8")
    original_writer = write_bridge_picks_csv
    observations: dict[str, object] = {}
    report = _report(
        picks=[
            {
                "symbol": "BAC",
                "score": 1.0,
                "weight": 1.0,
                "vol": 0.02,
                "mom_fast": 0.05,
                "mom_slow": 0.10,
                "latest_close": 60.0,
            }
        ]
    )

    def fake_writer(value, path):
        registry = json.loads(
            (runtime / "owned_position_lifecycles.json").read_text(encoding="utf-8")
        )
        observations["owned_before_overwrite"] = registry["owned_symbols"]
        return original_writer(value, path)

    def fake_subprocess(_command, *, cwd, env, check):
        assert cwd == tmp_path
        assert check is False
        observations["hwm_path"] = env["ALPACA_PROTECTIVE_EXIT_HWM_PATH"]
        (runtime / "latest_manager_receipt.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "report": {
                        "broker_truth_authoritative": True,
                        "broker_truth_after": {
                            "generated_at_utc": "2099-01-01T00:00:00+00:00",
                            "position_symbols": ["BAC"],
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(adaptive_paper, "ROOT", tmp_path)
    monkeypatch.setattr(adaptive_paper, "run_shadow", lambda **_kwargs: report)
    monkeypatch.setattr(adaptive_paper, "write_bridge_picks_csv", fake_writer)
    monkeypatch.setattr(adaptive_paper.subprocess, "run", fake_subprocess)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "alpaca_adaptive_paper.py",
            "--runtime-dir",
            str(runtime),
            "--cache-dir",
            str(tmp_path / "cache"),
        ],
    )

    assert adaptive_paper.main() == 0
    assert observations["owned_before_overwrite"] == ["BAC", "TMO"]
    assert observations["hwm_path"] == str(
        runtime / "protective_exit" / "protective_exit_hwm.json"
    )
    assert json.loads(
        (runtime / "owned_position_lifecycles.json").read_text(encoding="utf-8")
    )["owned_symbols"] == ["BAC"]
