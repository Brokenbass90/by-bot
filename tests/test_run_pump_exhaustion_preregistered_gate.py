from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.preflight_pump_exhaustion_prereg import (
    actual_source_hashes,
    compute_state_source_fingerprint,
)
from scripts.run_pump_exhaustion_preregistered_gate import (
    DAY_MS,
    ResearchGateError,
    apply_costs,
    apply_portfolio_occupancy,
    build_gate_report,
    build_preflight_evidence,
    execute_short_plan,
    fixed_development_folds,
    holdout_trades,
    period_rows,
    simulate_equity,
    verify_preflight_evidence,
)
from strategies.pump_exhaustion_unwind_short_v1 import PumpUnwindShortPlan


REPO = Path(__file__).resolve().parents[1]
FROZEN_CONFIG = REPO / "configs/preregistered/pump_exhaustion_unwind_short_v1_20260711.json"
INTERVAL = 300_000


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _preflight_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    root = tmp_path / "repo"
    for relative, content in {
        "strategies/pump_exhaustion_unwind_short_v1.py": "strategy-v1\n",
        "bot/pump_exhaustion_state_store.py": "state-v1\n",
        "scripts/preflight_pump_exhaustion_prereg.py": "preflight-v1\n",
        "scripts/run_pump_exhaustion_preregistered_gate.py": "runner-v1\n",
        "bot/inplay_volume_universe.py": "volume-v1\n",
        "bot/market_context.py": "context-v1\n",
        "bot/pump_exhaustion.py": "exhaustion-v1\n",
        "bot/retest_quality.py": "retest-v1\n",
        "bot/structure_break.py": "structure-v1\n",
        "strategies/signals.py": "signals-v1\n",
    }.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    cfg = json.loads(FROZEN_CONFIG.read_text(encoding="utf-8"))
    cfg["name"] = "unit_pump_prereg"
    cfg["data"].update(
        {
            "window_start_ts": 1_700_000_000_000,
            "window_end_ts_exclusive": 1_700_000_000_000 + 4 * INTERVAL,
            "window_start_utc": "unit",
            "window_end_utc_exclusive": "unit",
            "min_coverage": 1.0,
            "max_internal_gap_bars": 0,
            "symbols": ["AAAUSDT", "BBBUSDT", "CCCUSDT"],
            "input_snapshots": {},
        }
    )
    cfg["source_code"] = actual_source_hashes(root)
    cfg["state_source_fingerprint"] = compute_state_source_fingerprint(
        cfg, cfg["source_code"]
    )
    config_path = root / "configs/preregistered/unit.json"
    _write_json(config_path, cfg)

    pins: dict[str, dict[str, str]] = {}
    details: dict[str, dict[str, object]] = {}
    for number, symbol in enumerate(cfg["data"]["symbols"], start=1):
        rows = [
            {
                "ts": cfg["data"]["window_start_ts"] + index * INTERVAL,
                "o": 100.0 + number,
                "h": 101.0 + number,
                "l": 99.0 + number,
                "c": 100.5 + number,
                "v": 1000.0,
            }
            for index in range(4)
        ]
        snapshot = root / f"data_cache/immutable/unit/{symbol}.json"
        _write_json(snapshot, rows)
        relative = snapshot.relative_to(root).as_posix()
        pins[symbol] = {"path": relative, "sha256": _sha(snapshot)}
        details[symbol] = {
            **pins[symbol],
            "quality_pass": True,
            "coverage": 1.0,
            "max_internal_gap_bars": 0,
        }

    manifest = {
        "schema_version": 1,
        "kind": "pump_exhaustion_immutable_snapshot_manifest",
        "experiment": cfg["name"],
        "side_identity": "short_only",
        "network_calls": False,
        "live_state_changed": False,
        "config_edited": False,
        "performance_computed": False,
        "config": config_path.relative_to(root).as_posix(),
        "config_sha256": _sha(config_path),
        "interval_ms": INTERVAL,
        "quality_gate": {"min_coverage": 1.0, "max_internal_gap_bars": 0},
        "input_snapshots": pins,
        "snapshots": details,
    }
    manifest_path = root / "data_cache/immutable/unit/manifest.json"
    _write_json(manifest_path, manifest)
    runner_path = root / "scripts/run_pump_exhaustion_preregistered_gate.py"
    return root, config_path, manifest_path, runner_path


def _plan(*, signal_ts: int = 0, symbol: str = "AAAUSDT") -> PumpUnwindShortPlan:
    return PumpUnwindShortPlan(
        event_id=f"event-{symbol}-{signal_ts}",
        strategy="pump_exhaustion_unwind_short_v1",
        symbol=symbol,
        side="short",
        signal_ts=signal_ts,
        valid_from_ts=signal_ts + INTERVAL,
        entry_type="market_next_open",
        entry_reference=100.0,
        stop=110.0,
        target_1=90.0,
        target_2=80.0,
        risk=10.0,
        choch_level=101.0,
        event_peak=108.0,
        reason="unit",
    )


def _row(ts: int, o: float, h: float, l: float, c: float) -> list[float]:
    return [float(ts), o, h, l, c, 1000.0]


def _closed_candidate(
    symbol: str,
    plan_id: str,
    entry_ts: int,
    exit_ts: int,
    *,
    side: str = "short",
    gross_r: float = 1.0,
) -> dict[str, object]:
    return {
        "status": "filled_closed",
        "plan_id": plan_id,
        "event_id": f"event-{plan_id}",
        "strategy": "pump_exhaustion_unwind_short_v1",
        "symbol": symbol,
        "side": side,
        "signal_ts": entry_ts - INTERVAL,
        "valid_from_ts": entry_ts,
        "entry_ts": entry_ts,
        "exit_ts": exit_ts,
        "entry": 100.0,
        "stop": 110.0,
        "target_1": 90.0,
        "target_2": 80.0,
        "risk": 10.0,
        "risk_fraction": 0.1,
        "bars_held": max(1, (exit_ts - entry_ts) // INTERVAL + 1),
        "gross_r": gross_r,
        "mae_r": min(0.0, gross_r, -0.5),
        "mae_ts": entry_ts,
        "exit_reason": "unit",
        "exit_legs": [{"fraction": 1.0, "price": 90.0, "reason": "unit", "r": gross_r}],
    }


def test_preflight_accepts_external_hash_pins_without_editing_frozen_config(tmp_path: Path) -> None:
    root, config_path, manifest_path, runner_path = _preflight_fixture(tmp_path)
    evidence = build_preflight_evidence(
        root,
        config_path,
        manifest_path,
        runner_path=runner_path,
        expected_config_sha256=None,
    )
    assert evidence["permission"] == "PERFORMANCE_RESEARCH_ALLOWED"
    assert evidence["blockers"] == []
    assert len(evidence["snapshots"]) == 3
    assert all(row["ok"] for row in evidence["snapshots"])
    assert json.loads(config_path.read_text())["data"]["input_snapshots"] == {}


def test_preflight_is_stale_after_runner_or_snapshot_hash_changes(tmp_path: Path) -> None:
    root, config_path, manifest_path, runner_path = _preflight_fixture(tmp_path)
    evidence = build_preflight_evidence(
        root,
        config_path,
        manifest_path,
        runner_path=runner_path,
        expected_config_sha256=None,
    )
    evidence_path = root / "evidence.json"
    _write_json(evidence_path, evidence)

    runner_path.write_text("runner-v2\n", encoding="utf-8")
    fresh = build_preflight_evidence(
        root,
        config_path,
        manifest_path,
        runner_path=runner_path,
        expected_config_sha256=None,
    )
    with pytest.raises(ResearchGateError, match="stale"):
        verify_preflight_evidence(fresh, evidence_path)

    manifest = json.loads(manifest_path.read_text())
    first = next(iter(manifest["input_snapshots"].values()))
    (root / first["path"]).write_text("[]", encoding="utf-8")
    blocked = build_preflight_evidence(
        root,
        config_path,
        manifest_path,
        runner_path=runner_path,
        expected_config_sha256=None,
    )
    assert blocked["permission"] == "BLOCKED_FAIL_CLOSED"
    assert any(item.startswith("snapshot_not_ready:") for item in blocked["blockers"])


def test_preflight_rejects_exit_contract_weakening_even_with_refreshed_file_hashes(
    tmp_path: Path,
) -> None:
    root, config_path, manifest_path, runner_path = _preflight_fixture(tmp_path)
    cfg = json.loads(config_path.read_text())
    cfg["exit_contract"]["max_hold_bars"] = 95
    _write_json(config_path, cfg)
    manifest = json.loads(manifest_path.read_text())
    manifest["config_sha256"] = _sha(config_path)
    _write_json(manifest_path, manifest)

    with pytest.raises(ResearchGateError, match="exit mechanics"):
        build_preflight_evidence(
            root,
            config_path,
            manifest_path,
            runner_path=runner_path,
            expected_config_sha256=None,
        )


def test_next_open_and_stop_first_for_ambiguous_entry_bar() -> None:
    rows = [_row(INTERVAL, 100, 111, 79, 100)]
    result = execute_short_plan(
        _plan(), rows, interval_ms=INTERVAL, max_hold_bars=96
    )
    assert result["status"] == "filled_closed"
    assert result["entry_ts"] == INTERVAL
    assert result["exit_reason"] == "stop"
    assert result["gross_r"] == pytest.approx(-1.0)


def test_tp1_tp2_partial_lifecycle_and_tp1_then_stop() -> None:
    win_rows = [
        _row(INTERVAL, 100, 105, 89, 92),
        _row(2 * INTERVAL, 92, 105, 79, 81),
    ]
    winner = execute_short_plan(
        _plan(), win_rows, interval_ms=INTERVAL, max_hold_bars=96
    )
    assert winner["exit_reason"] == "tp1_tp2"
    assert winner["gross_r"] == pytest.approx(1.5)
    assert [leg["fraction"] for leg in winner["exit_legs"]] == [0.5, 0.5]

    scratch_rows = [
        _row(INTERVAL, 100, 105, 89, 92),
        _row(2 * INTERVAL, 92, 111, 85, 105),
    ]
    scratch = execute_short_plan(
        _plan(), scratch_rows, interval_ms=INTERVAL, max_hold_bars=96
    )
    assert scratch["exit_reason"] == "tp1_then_stop"
    assert scratch["gross_r"] == pytest.approx(0.0)


def test_gap_policies_are_adverse_and_fail_closed() -> None:
    entry_gap = execute_short_plan(
        _plan(),
        [_row(INTERVAL, 111, 112, 105, 108)],
        interval_ms=INTERVAL,
        max_hold_bars=96,
    )
    assert entry_gap["status"] == "invalid_adverse_gap_through_stop"

    stop_gap = execute_short_plan(
        _plan(),
        [
            _row(INTERVAL, 100, 105, 95, 100),
            _row(2 * INTERVAL, 115, 116, 114, 115),
        ],
        interval_ms=INTERVAL,
        max_hold_bars=96,
    )
    assert stop_gap["status"] == "filled_closed"
    assert stop_gap["gross_r"] == pytest.approx(-1.5)

    missing = execute_short_plan(
        _plan(),
        [_row(2 * INTERVAL, 100, 105, 95, 100)],
        interval_ms=INTERVAL,
        max_hold_bars=96,
    )
    assert missing["status"] == "missing_exact_next_open"


def test_maxhold_and_base_stress_costs() -> None:
    result = execute_short_plan(
        _plan(),
        [
            _row(INTERVAL, 100, 105, 95, 100),
            _row(2 * INTERVAL, 100, 104, 94, 95),
        ],
        interval_ms=INTERVAL,
        max_hold_bars=2,
    )
    assert result["exit_reason"] == "max_hold"
    assert result["gross_r"] == pytest.approx(0.5)
    base = apply_costs(result, {"fee": 6, "slippage": 2})
    stress = apply_costs(result, {"fee": 10, "slippage": 5})
    assert 0 < base["cost_r"] < stress["cost_r"]
    assert stress["net_r"] < base["net_r"] < result["gross_r"]


def test_global_timestamp_occupancy_is_deterministic_and_same_symbol_is_busy() -> None:
    candidates = [
        _closed_candidate(f"{letter}USDT", letter, INTERVAL, 3 * INTERVAL)
        for letter in "ABCDE"
    ]
    accepted, rejected, counts = apply_portfolio_occupancy(
        list(reversed(candidates)), max_positions=4
    )
    assert [row["symbol"] for row in accepted] == ["AUSDT", "BUSDT", "CUSDT", "DUSDT"]
    assert rejected[0]["symbol"] == "EUSDT"
    assert rejected[0]["portfolio_status"] == "rejected_capacity"
    assert counts["accepted"] == 4

    same_symbol = [
        _closed_candidate("AAAUSDT", "first", INTERVAL, 2 * INTERVAL),
        _closed_candidate("AAAUSDT", "second", 2 * INTERVAL, 3 * INTERVAL),
    ]
    accepted, rejected, _ = apply_portfolio_occupancy(same_symbol, max_positions=4)
    assert len(accepted) == 1
    assert rejected[0]["portfolio_status"] == "rejected_symbol_busy"


def test_fixed_folds_embargo_purge_and_final_holdout_are_time_frozen() -> None:
    start = 0
    end = 720 * DAY_MS
    holdout_start = 600 * DAY_MS
    fold_span = 150 * DAY_MS
    embargo = 7 * DAY_MS
    data = {
        "window_start_ts": start,
        "window_end_ts_exclusive": end,
        "interval_ms": INTERVAL,
    }
    evaluation = {
        "chronological_folds": 4,
        "embargo_bars": 2016,
        "untouched_holdout_days": 120,
    }
    trades = []
    for index in range(4):
        entry = index * fold_span + embargo
        trade = _closed_candidate("AAAUSDT", f"fold-{index}", entry, entry + INTERVAL)
        trade["net_r"] = 1.0
        trades.append(trade)
    embargoed = _closed_candidate("AAAUSDT", "embargoed", fold_span + INTERVAL, fold_span + 2 * INTERVAL)
    embargoed["net_r"] = 1.0
    crossing = _closed_candidate("AAAUSDT", "crossing", fold_span - INTERVAL, fold_span)
    crossing["net_r"] = 1.0
    hold = _closed_candidate(
        "AAAUSDT", "holdout", holdout_start + embargo, holdout_start + embargo + INTERVAL
    )
    hold["net_r"] = 1.0
    trades.extend((embargoed, crossing, hold))

    folds, diagnostics, actual_holdout_start = fixed_development_folds(
        trades, data, evaluation
    )
    assert actual_holdout_start == holdout_start
    assert [row["trades"] for row in folds] == [1, 1, 1, 1]
    assert diagnostics["embargoed"] == 1
    assert diagnostics["purged_boundary"] == 1
    selected, summary = holdout_trades(trades, data, evaluation)
    assert [row["plan_id"] for row in selected] == ["holdout"]
    assert summary["trades"] == 1


def test_period_outputs_include_zero_trade_calendar_months_and_active_labels() -> None:
    start = 1_704_067_200_000  # 2024-01-01 UTC
    end = 1_711_929_600_000  # 2024-04-01 UTC
    rows = period_rows(
        [],
        period="monthly",
        scenario="stress",
        window_start_ts=start,
        window_end_ts_exclusive=end,
        starting_equity=100.0,
    )
    assert [row["period"] for row in rows] == ["2024-01", "2024-02", "2024-03"]
    assert all(row["trades"] == 0 and row["active"] is False for row in rows)
    assert all(row["red_active"] is False for row in rows)

    feb_exit = 1_708_041_600_000  # 2024-02-15 UTC
    losing_trade = {
        "exit_ts": feb_exit,
        "symbol": "AAAUSDT",
        "plan_id": "feb-loss",
        "net_r": -1.0,
        "pnl_usd": -1.0,
        "equity_before_exit": 100.0,
        "equity_after_exit": 99.0,
    }
    with_trade = period_rows(
        [losing_trade],
        period="monthly",
        scenario="stress",
        window_start_ts=start,
        window_end_ts_exclusive=end,
        starting_equity=100.0,
    )
    assert sum(row["active"] for row in with_trade) == 1
    assert sum(row["red_active"] for row in with_trade) == 1
    assert next(row for row in with_trade if row["period"] == "2024-02")["trades"] == 1


def test_conservative_overlap_mae_drawdown_is_explicit_and_not_below_exit_dd() -> None:
    first = apply_costs(
        _closed_candidate("AAAUSDT", "a", INTERVAL, 4 * INTERVAL, gross_r=1.0),
        {"fee": 6, "slippage": 2},
    )
    second = apply_costs(
        _closed_candidate("BBBUSDT", "b", 2 * INTERVAL, 5 * INTERVAL, gross_r=1.0),
        {"fee": 6, "slippage": 2},
    )
    equity = simulate_equity(
        [first, second],
        {
            "starting_equity": 100.0,
            "simulation_risk_pct": 0.005,
            "cap_notional_usd": 30.0,
        },
    )
    assert equity["max_drawdown_pct"] >= equity["exit_realized_max_drawdown_pct"]
    assert equity["conservative_overlap_mae_max_drawdown_pct"] > 0
    assert "conservative" in equity["drawdown_gate_basis"]


def test_gate_fails_side_impurity_and_duplicate_event_plan_ids_deterministically() -> None:
    cfg = json.loads(FROZEN_CONFIG.read_text(encoding="utf-8"))
    cfg["data"].update(
        {
            "window_start_ts": 0,
            "window_end_ts_exclusive": 720 * DAY_MS,
            "symbols": ["AAAUSDT", "BBBUSDT", "CCCUSDT"],
        }
    )
    cfg["evaluation_contract"].update(
        {"embargo_bars": 1, "untouched_holdout_days": 120, "chronological_folds": 4}
    )
    candidates = [
        _closed_candidate("AAAUSDT", "duplicate", 10 * DAY_MS, 10 * DAY_MS + INTERVAL),
        _closed_candidate("BBBUSDT", "other", 170 * DAY_MS, 170 * DAY_MS + INTERVAL, side="long"),
    ]
    invalid = _closed_candidate(
        "CCCUSDT", "invalid-gap", 320 * DAY_MS, 320 * DAY_MS + INTERVAL
    )
    invalid["status"] = "invalid_adverse_gap_through_stop"
    candidates.append(invalid)
    symbol_results = [
        {
            "symbol": "AAAUSDT",
            "rows": 1,
            "first_ts": 0,
            "last_ts": 0,
            "continuity_resets": 0,
            "event_ids": ["event-dup", "event-dup"],
            "plan_ids": ["duplicate", "duplicate"],
            "duplicate_event_ids": [],
            "duplicate_plan_ids": [],
            "reason_counts": {},
            "candidates": candidates,
        },
        {
            "symbol": "BBBUSDT",
            "rows": 0,
            "first_ts": None,
            "last_ts": None,
            "continuity_resets": 0,
            "event_ids": [],
            "plan_ids": [],
            "duplicate_event_ids": [],
            "duplicate_plan_ids": [],
            "reason_counts": {},
            "candidates": [],
        },
        {
            "symbol": "CCCUSDT",
            "rows": 0,
            "first_ts": None,
            "last_ts": None,
            "continuity_resets": 0,
            "event_ids": [],
            "plan_ids": [],
            "duplicate_event_ids": [],
            "duplicate_plan_ids": [],
            "reason_counts": {},
            "candidates": [],
        },
    ]
    report = build_gate_report(
        cfg,
        symbol_results,
        {"permission": "PERFORMANCE_RESEARCH_ALLOWED", "unit": True},
    )
    assert report["verdict"] == "NO_PROMOTION"
    assert report["gate_checks"]["side_purity"] is False
    assert report["gate_checks"]["event_id_duplicates"] is False
    assert report["gate_checks"]["plan_id_duplicates"] is False
    assert report["gate_checks"]["execution_integrity"] is False
    assert set(
        ("side_purity", "event_id_duplicates", "plan_id_duplicates", "execution_integrity")
    ) <= set(
        report["failed_gates"]
    )
