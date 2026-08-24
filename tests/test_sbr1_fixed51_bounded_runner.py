from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from bot.live_native_decision_contract import LiveNativeDecisionPlan
from bot.sbr1_zero_risk_shadow import (
    AUTHORITY,
    CausalEmaRegimeState,
    ShadowViolation,
    ZeroRiskShadowConfig,
)
from scripts import run_sbr1_zero_risk_shadow as runner
from strategies.signals import TradeSignal


H1_MS = 3_600_000


def _sha(value: object) -> str:
    data = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(data).hexdigest()


def _closure(root: Path) -> dict[str, str]:
    paths = (
        "strategies/sloped_break_retest_v1.py",
        "strategies/sbr1_live.py",
        "strategies/live_kline_utils.py",
        "strategies/signals.py",
        "bot/live_native_decision_contract.py",
        "bot/live_native_fill_adapter.py",
        "bot/live_native_regime_gate.py",
        "bot/live_native_manifest.py",
        "bot/live_native_signal_adapters.py",
        "bot/sbr1_zero_risk_shadow.py",
        "bot/sbr1_universe.py",
        "bot/sbr1_shadow_random_control.py",
        "scripts/run_sbr1_zero_risk_shadow.py",
        "deploy/systemd/sbr1-zero-risk-shadow.service",
        "deploy/systemd/sbr1-zero-risk-shadow.timer",
    )
    return {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths}


def _split_config(root: Path, journal_path: str = "runtime/test/events.jsonl"):
    evidence = ["BTCUSDT", "ETHUSDT", "HFTUSDT"]
    money = ["BTCUSDT", "LINKUSDT"]
    raw = {
        "schema_id": "sbr1_zero_risk_shadow_config_v1",
        "enabled": True,
        "authority": AUTHORITY,
        "money_authority": False,
        "orders_allowed": False,
        "private_api_allowed": False,
        "release_or_promotion_authority": False,
        "sealed_data_allowed": False,
        "public_base": "https://api.bybit.com",
        "evidence_universe": evidence,
        "money_universe": money,
        "evidence_universe_manifest_path": "configs/research/test.json",
        "expected_evidence_universe_manifest_sha256": "a" * 64,
        "evidence_universe_sha256": _sha(evidence),
        "money_universe_sha256": _sha(money),
        "parity_manifest_path": "configs/research/test-parity.json",
        "expected_parity_manifest_sha256": "b" * 64,
        "expected_preregistration_sha256": "c" * 64,
        "journal_path": journal_path,
        "max_decision_age_ms": 300_000,
        "max_regime_age_ms": 300_000,
        "h1_history_limit": 260,
        "max_m5_pages": 4,
        "request_timeout_seconds": "15",
        "entry_slippage_bps": "2",
        "exit_slippage_bps": "2",
        "fee_bps_per_side": "6",
        "regime_bootstrap_bars": 900,
        "max_open_slots_total": 12,
        "max_open_slots_sbr1": 6,
        "max_open_slots_per_cluster": 2,
        "shadow_risk_fraction_per_slot": "0.02",
        "max_cluster_risk_fraction": "0.04",
        "symbol_clusters": {
            "BTCUSDT": "major8",
            "LINKUSDT": "major8",
            "ETHUSDT": "fixed51_raw",
            "HFTUSDT": "fixed51_raw",
        },
        "source_closure": _closure(Path(__file__).resolve().parents[1]),
    }
    return ZeroRiskShadowConfig.from_mapping(raw)


def _rows(closed_h1_ts_ms: int, count: int = 260):
    first = closed_h1_ts_ms - count * H1_MS
    return [
        [
            str(first + index * H1_MS),
            "100",
            "101",
            "99",
            "100",
            "10",
        ]
        for index in range(count)
    ]


def _snapshot(symbol: str, closed_h1_ts_ms: int):
    observed = closed_h1_ts_ms + 20_000
    return runner.PublicKlineSnapshot(
        symbol=symbol,
        interval="60",
        rows=tuple(tuple(row) for row in _rows(closed_h1_ts_ms)),
        observed_at_ms=observed,
        response_sha256=_sha({"symbol": symbol, "closed_h1_ts_ms": closed_h1_ts_ms}),
    )


def _regime(closed_h1_ts_ms: int):
    return CausalEmaRegimeState(
        seed_bar_start_ts_ms=closed_h1_ts_ms - 900 * H1_MS,
        seed_close=Decimal("100"),
        bar_start_ts_ms=closed_h1_ts_ms - H1_MS,
        closed_h1_ts_ms=closed_h1_ts_ms,
        close=Decimal("100.5"),
        ema200=Decimal("100"),
        observation_count=900,
        history_hash="d" * 64,
    )


def _signal(symbol: str):
    return TradeSignal(
        strategy="sloped_break_retest_v1",
        symbol=symbol,
        side="long",
        entry=100,
        sl=90,
        tp=111,
        tps=[111, 126],
        tp_fracs=[0.5, 0.3],
        time_stop_bars=2016,
        reason="test",
    )


def _plan(symbol: str, closed_h1_ts_ms: int):
    return LiveNativeDecisionPlan(
        spec_id="sbr1-live-native-v2",
        sleeve_id="SBR1",
        symbol=symbol,
        side="long",
        closed_h1_ts_ms=closed_h1_ts_ms,
        planned_entry=Decimal("100"),
        frozen_sl=Decimal("90"),
        planned_tps=(Decimal("111"), Decimal("126")),
        tp_fractions=(Decimal("0.5"), Decimal("0.3")),
        residual_fraction=Decimal("0.2"),
        time_stop_hours=168,
        config_hash="1" * 64,
        source_hash="2" * 64,
        data_hash="3" * 64,
    )


def _install_cycle_mocks(monkeypatch, tmp_path: Path, *, signals=(), errors=()):
    repo_root = Path(__file__).resolve().parents[1]
    config = _split_config(repo_root)
    close = 1_800_000_000_000
    btc = _snapshot("BTCUSDT", close)
    snapshots = {
        symbol: _snapshot(symbol, close)
        for symbol in config.evaluation_universe
        if symbol != "HFTUSDT" and symbol not in errors
    }
    monkeypatch.setattr(runner, "_preflight", lambda *_args, **_kwargs: {
        "source_closure_sha256": "e" * 64,
        "expected_structurally_unavailable": {
            "HFTUSDT": "bybit_linear_status_closed_observed_2026-08-24"
        },
    })
    monkeypatch.setattr(runner, "load_config", lambda _path: config)
    monkeypatch.setattr(
        runner,
        "load_and_verify_manifest",
        lambda *_args, **_kwargs: SimpleNamespace(
            manifest_sha256="b" * 64,
            universe=config.money_universe,
            payload={
                "exchange_filters": {
                    symbol: {
                        "tick_size": "0.1",
                        "qty_step": "0.001",
                        "min_notional": "5",
                    }
                    for symbol in config.money_universe
                }
            },
        ),
    )
    monkeypatch.setattr(runner, "_manifest_source_bundle", lambda *_args: ({}, {}))
    monkeypatch.setattr(runner, "fetch_public_klines", lambda *_args, **_kwargs: btc)
    monkeypatch.setattr(runner, "_advance_regime", lambda *_args, **_kwargs: _regime(close))

    def fetch_all(_config, _btc, *, get_bytes, symbols=None):
        del get_bytes
        selected = tuple(symbols or ())
        assert "HFTUSDT" not in selected
        return (
            {symbol: snapshots[symbol] for symbol in selected if symbol in snapshots},
            {symbol: "ShadowViolation:test_gap" for symbol in selected if symbol in errors},
        )

    monkeypatch.setattr(runner, "_fetch_h1_decision_snapshots", fetch_all)
    monkeypatch.setattr(
        runner,
        "replay_latest_signal",
        lambda symbol, rows: (
            _signal(symbol) if symbol in signals else None,
            SimpleNamespace(),
            rows,
        ),
    )
    return config, close


def test_nonmajor_fixed51_signal_is_raw_only_and_cannot_reach_downstream(
    monkeypatch, tmp_path: Path
):
    config, _ = _install_cycle_mocks(monkeypatch, tmp_path, signals={"ETHUSDT"})
    monkeypatch.setattr(
        runner,
        "fetch_public_filters",
        lambda *_args, **_kwargs: pytest.fail("raw symbol reached public filter"),
    )
    monkeypatch.setattr(
        runner,
        "adapt_sbr1_live_signal_to_plan",
        lambda *_args, **_kwargs: pytest.fail("raw symbol reached adapter"),
    )
    monkeypatch.setattr(
        runner,
        "shadow_slot_gate",
        lambda *_args, **_kwargs: pytest.fail("raw symbol reached slot gate"),
    )
    monkeypatch.setattr(
        runner,
        "build_control_assignments",
        lambda *_args, **_kwargs: pytest.fail("raw symbol reached control"),
    )

    receipt = runner.run_once(
        tmp_path,
        tmp_path / "config.json",
        acknowledgement=runner.ACK,
        get_bytes=lambda *_args, **_kwargs: b"",
    )

    events = runner.AppendOnlyShadowJournal(tmp_path / config.journal_path).read()
    raw = next(event["payload"] for event in events if event["payload"].get("symbol") == "ETHUSDT")
    assert raw["admitted"] is False
    assert raw["evidence_role"] == "preparity_raw_not_final_n"
    assert raw["promotion_eligible"] is False
    assert "decision_plan" not in raw
    assert "decision_id" not in raw
    assert receipt["fixed51_final_n_eligible"] is False
    assert receipt["promotion_eligible"] is False


def test_major8_golden_path_still_reaches_adapter_gate_control_and_lifecycle(
    monkeypatch, tmp_path: Path
):
    config, close = _install_cycle_mocks(monkeypatch, tmp_path, signals={"BTCUSDT"})
    calls: list[str] = []
    monkeypatch.setattr(
        runner,
        "fetch_public_filters",
        lambda _base, symbol, **_kwargs: (
            calls.append(f"filter:{symbol}")
            or runner.PublicFilterSnapshot(symbol, "0.1", "0.001", "5", close + 20_000, "4" * 64)
        ),
    )
    monkeypatch.setattr(
        runner,
        "adapt_sbr1_live_signal_to_plan",
        lambda signal, *_args, **_kwargs: (
            calls.append(f"adapter:{signal.symbol}") or _plan(signal.symbol, close)
        ),
    )
    monkeypatch.setattr(
        runner,
        "build_control_assignments",
        lambda **_kwargs: calls.append("control") or (),
    )

    def persist(*, main_journal, main_claim, main_payload, **_kwargs):
        calls.append("persist")
        return main_journal.append("evaluation", main_claim, main_payload), 0

    monkeypatch.setattr(runner, "persist_controlled_admission", persist)
    monkeypatch.setattr(runner, "preregistration_sha256", lambda _path: config.expected_preregistration_sha256)

    receipt = runner.run_once(
        tmp_path,
        tmp_path / "config.json",
        acknowledgement=runner.ACK,
        get_bytes=lambda *_args, **_kwargs: b"",
    )

    events = runner.AppendOnlyShadowJournal(tmp_path / config.journal_path).read()
    main = next(event["payload"] for event in events if event["payload"].get("symbol") == "BTCUSDT")
    assert main["admitted"] is True
    assert main["decision_plan"]["symbol"] == "BTCUSDT"
    assert calls == ["filter:BTCUSDT", "adapter:BTCUSDT", "control", "persist"]
    assert receipt["decisions_admitted"] == 1


def test_same_h1_is_idempotent_and_receipt_preserves_fixed51_coverage(
    monkeypatch, tmp_path: Path
):
    config, _ = _install_cycle_mocks(monkeypatch, tmp_path)
    first = runner.run_once(
        tmp_path,
        tmp_path / "config.json",
        acknowledgement=runner.ACK,
        get_bytes=lambda *_args, **_kwargs: b"",
    )
    before = runner.AppendOnlyShadowJournal(tmp_path / config.journal_path).read()
    second = runner.run_once(
        tmp_path,
        tmp_path / "config.json",
        acknowledgement=runner.ACK,
        get_bytes=lambda *_args, **_kwargs: b"",
    )
    after = runner.AppendOnlyShadowJournal(tmp_path / config.journal_path).read()
    assert len(after) == len(before)
    assert first["coverage"] == second["coverage"]
    assert second["coverage"]["expected_count"] == 3
    assert second["coverage"]["observed_symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert second["coverage"]["structurally_unavailable_symbols"] == ["HFTUSDT"]
    assert second["status"] == "ZERO_RISK_SHADOW_OK_EXPECTED_STRUCTURAL_GAP"
    assert runner._cycle_exit_code(second) == 0


@pytest.mark.parametrize(
    ("errors", "expected_observed"),
    [({"ETHUSDT"}, ["BTCUSDT"]), ({"BTCUSDT", "ETHUSDT"}, [])],
)
def test_partial_or_zero_fixed51_coverage_is_degraded_and_nonzero(
    monkeypatch, tmp_path: Path, errors: set[str], expected_observed: list[str]
):
    _, _ = _install_cycle_mocks(monkeypatch, tmp_path, errors=errors)
    receipt = runner.run_once(
        tmp_path,
        tmp_path / "config.json",
        acknowledgement=runner.ACK,
        get_bytes=lambda *_args, **_kwargs: b"",
    )
    assert receipt["coverage"]["observed_symbols"] == expected_observed
    assert receipt["coverage"]["error_symbols"] == sorted(errors)
    assert receipt["status"] == "ZERO_RISK_SHADOW_DEGRADED_PUBLIC_DATA"
    assert runner._cycle_exit_code(receipt) != 0


def test_hft_is_frozen_expected_structural_gap_without_substitution(monkeypatch, tmp_path: Path):
    config, _ = _install_cycle_mocks(monkeypatch, tmp_path)
    receipt = runner.run_once(
        tmp_path,
        tmp_path / "config.json",
        acknowledgement=runner.ACK,
        get_bytes=lambda *_args, **_kwargs: b"",
    )
    events = runner.AppendOnlyShadowJournal(tmp_path / config.journal_path).read()
    unavailable = [event for event in events if event["event_type"] == "evaluation_unavailable"]
    assert len(unavailable) == 1
    assert unavailable[0]["payload"]["symbol"] == "HFTUSDT"
    assert unavailable[0]["payload"]["availability"] == "structurally_unavailable"
    assert unavailable[0]["payload"]["expected_gap"] is True
    assert receipt["coverage"]["missing_symbols"] == []


def test_lifecycle_rejects_admitted_nonmoney_symbol():
    events = [
        {
            "event_type": "evaluation",
            "claim_key": "evaluation:SBR1:ETHUSDT:1800000000000",
            "payload": {
                "admitted": True,
                "decision_id": "a" * 64,
                "symbol": "ETHUSDT",
            },
        }
    ]
    with pytest.raises(ShadowViolation, match="admitted_non_money_symbol"):
        runner._journal_index(events, money_universe=("BTCUSDT", "LINKUSDT"))


def test_durable_missed_window_never_becomes_observed_coverage() -> None:
    close = 1_800_000_000_000
    events = [
        {
            "event_type": "evaluation",
            "payload": {
                "symbol": "BTCUSDT",
                "closed_h1_ts_ms": close,
                "status": "missed_decision_window",
                "reason": "production_or_regime_decision_clock_missed",
            },
        }
    ]
    coverage = runner._coverage_for_close(
        events,
        expected_symbols=("BTCUSDT",),
        expected_close=close,
    )
    assert coverage["observed_symbols"] == []
    assert coverage["error_symbols"] == ["BTCUSDT"]


def test_oneshot_start_timeout_finishes_before_three_minute_retry() -> None:
    root = Path(__file__).resolve().parents[1]
    service = (root / "deploy/systemd/sbr1-zero-risk-shadow.service").read_text(
        encoding="utf-8"
    )
    values = [
        int(line.split("=", 1)[1])
        for line in service.splitlines()
        if line.startswith("TimeoutStartSec=")
    ]
    assert values == [120]
    assert "RuntimeMaxSec=" not in service
