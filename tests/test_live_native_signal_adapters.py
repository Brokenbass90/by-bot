from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from bot.att1_runtime_contract import build_att1_runtime_contract
from bot.live_native_decision_contract import ContractViolation, H1_MS
from bot.live_native_signal_adapters import (
    LIVE_NATIVE_SIGNAL_ADAPTERS_ENABLED_BY_DEFAULT,
    adapt_att1_live_signal_to_plan,
    adapt_att1_research_signal_to_plan,
    adapt_sbr1_live_signal_to_plan,
    adapt_sbr1_research_signal_to_plan,
    closed_h1_evidence_from_row,
)
from strategies.signals import TradeSignal
from strategies.sloped_break_retest_v1 import SlopedBreakRetestV1Config


ROOT = Path(__file__).resolve().parents[1]
CLOSED_H1_TS_MS = 1_800_000_000_000
BAR_START_MS = CLOSED_H1_TS_MS - H1_MS


def _row(close: str = "100") -> list[str]:
    return [str(BAR_START_MS), "100", "102", "98", close, "1000"]


def _evidence(*, close: str = "100", observed_offset_ms: int = 60_000):
    row = _row(close)
    row_bytes = json.dumps(row, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return closed_h1_evidence_from_row(
        row,
        row_bytes=row_bytes,
        observed_at_ms=CLOSED_H1_TS_MS + observed_offset_ms,
        max_decision_age_ms=300_000,
    )


def _source_bundle(*paths: str):
    files = {path: (ROOT / path).read_bytes() for path in paths}
    hashes = {path: hashlib.sha256(data).hexdigest() for path, data in files.items()}
    return files, hashes


def _att1_source_bundle():
    return _source_bundle(
        "strategies/alt_trendline_touch_v1.py",
        "strategies/att1_live.py",
        "strategies/live_kline_utils.py",
        "strategies/signals.py",
    )


def _sbr1_source_bundle():
    return _source_bundle(
        "strategies/sloped_break_retest_v1.py",
        "strategies/sbr1_live.py",
        "strategies/live_kline_utils.py",
        "strategies/signals.py",
    )


def _target_att1_contract(monkeypatch):
    for key, value in {
        "ATT1_ALLOW_LONGS": "0",
        "ATT1_ALLOW_SHORTS": "1",
        "ATT1_SIGNAL_TF": "60",
        "ATT1_SL_ATR_MULT": "6.60",
        "ATT1_MAX_STOP_PCT": "0.25",
        "ATT1_TP1_RR": "1.20",
        "ATT1_TP2_RR": "2.50",
        "ATT1_TP1_FRAC": "0.55",
        "ATT1_BE_TRIGGER_RR": "0",
        "ATT1_TRAIL_ATR_MULT": "0",
        "ATT1_TIME_STOP_BARS_5M": "4032",
    }.items():
        monkeypatch.setenv(key, value)
    return build_att1_runtime_contract(risk_mult=0.0)


def _att1_signal(**updates: object) -> TradeSignal:
    values: dict[str, object] = {
        "strategy": "alt_trendline_touch_v1",
        "symbol": "BTCUSDT",
        "side": "short",
        "entry": 100.0,
        "sl": 110.0,
        "tp": 75.0,
        "tps": [88.0, 75.0],
        "tp_fracs": [0.55, 0.45],
        "be_trigger_rr": 0.0,
        "trailing_atr_mult": 0.0,
        "time_stop_bars": 4032,
        "reason": "att1_short_trendline tf=60",
    }
    values.update(updates)
    return TradeSignal(**values)  # type: ignore[arg-type]


def _sbr1_config(**updates: object) -> SlopedBreakRetestV1Config:
    values: dict[str, object] = {
        "signal_tf": "60",
        "allow_longs": True,
        "allow_shorts": False,
        "sl_atr_mult": 4.60,
        "tp1_rr": 1.10,
        "tp2_rr": 2.60,
        "tp1_frac": 0.50,
        "tp2_frac": 0.30,
        "be_trigger_rr": 0.0,
        "trail_atr_mult": 0.0,
        "time_stop_bars_5m": 2016,
        "cooldown_tf_bars": 6,
    }
    values.update(updates)
    return SlopedBreakRetestV1Config(**values)  # type: ignore[arg-type]


def _sbr1_signal(**updates: object) -> TradeSignal:
    values: dict[str, object] = {
        "strategy": "sloped_break_retest_v1",
        "symbol": "ETHUSDT",
        "side": "long",
        "entry": 100.0,
        "sl": 90.0,
        "tp": 126.0,
        "tps": [111.0, 126.0],
        "tp_fracs": [0.50, 0.30],
        "be_trigger_rr": 0.0,
        "trailing_atr_mult": 0.0,
        "time_stop_bars": 2016,
        "reason": "sbr1_long_channel_break_retest",
    }
    values.update(updates)
    return TradeSignal(**values)  # type: ignore[arg-type]


def test_att1_real_signal_runtime_source_and_h1_bytes_build_exact_plan(monkeypatch) -> None:
    contract = _target_att1_contract(monkeypatch)
    files, hashes = _att1_source_bundle()
    evidence = _evidence()

    plan = adapt_att1_live_signal_to_plan(
        _att1_signal(),
        evidence,
        contract,
        source_files=files,
        expected_source_hashes=hashes,
    )

    assert LIVE_NATIVE_SIGNAL_ADAPTERS_ENABLED_BY_DEFAULT is False
    assert plan.sleeve_id == "ATT1"
    assert plan.side == "short"
    assert plan.closed_h1_ts_ms == CLOSED_H1_TS_MS
    assert plan.config_hash == contract["sha256"]
    assert plan.data_hash == hashlib.sha256(evidence.row_bytes).hexdigest()
    assert plan.time_stop_hours == 336
    assert [str(value) for value in plan.tp_fractions] == ["0.55", "0.45"]

    research = adapt_att1_research_signal_to_plan(
        _att1_signal(),
        evidence,
        contract,
        source_files=files,
        expected_source_hashes=hashes,
    )
    assert research == plan


@pytest.mark.parametrize(
    ("observed_offset", "code"),
    [(-1, "h1_bar_not_closed"), (300_001, "closed_h1_decision_too_old")],
)
def test_closed_h1_evidence_rejects_open_or_stale_bar(observed_offset: int, code: str) -> None:
    row = _row()
    raw = json.dumps(row, separators=(",", ":")).encode("ascii")
    with pytest.raises(ContractViolation, match=code):
        closed_h1_evidence_from_row(
            row,
            row_bytes=raw,
            observed_at_ms=CLOSED_H1_TS_MS + observed_offset,
            max_decision_age_ms=300_000,
        )


def test_closed_h1_evidence_rejects_bytes_that_do_not_decode_to_the_row() -> None:
    with pytest.raises(ContractViolation, match="closed_h1_row_bytes_mismatch"):
        closed_h1_evidence_from_row(
            _row(),
            row_bytes=json.dumps(_row("101")).encode("ascii"),
            observed_at_ms=CLOSED_H1_TS_MS + 1,
            max_decision_age_ms=300_000,
        )


def test_hand_constructed_evidence_cannot_bypass_age_or_hash_gates(monkeypatch) -> None:
    contract = _target_att1_contract(monkeypatch)
    files, hashes = _att1_source_bundle()
    forged = replace(_evidence(), age_ms=0, data_hash="f" * 64)
    with pytest.raises(ContractViolation, match="inconsistent_closed_h1_evidence"):
        adapt_att1_live_signal_to_plan(
            _att1_signal(), forged, contract,
            source_files=files, expected_source_hashes=hashes,
        )


def test_att1_adapter_rejects_tampered_runtime_contract_hash(monkeypatch) -> None:
    contract = copy.deepcopy(_target_att1_contract(monkeypatch))
    contract["params"]["tp1_rr"] = 9.0
    files, hashes = _att1_source_bundle()
    with pytest.raises(ContractViolation, match="att1_runtime_contract_hash_mismatch"):
        adapt_att1_live_signal_to_plan(
            _att1_signal(), _evidence(), contract,
            source_files=files, expected_source_hashes=hashes,
        )


def test_att1_adapter_rejects_self_consistent_but_wrong_selected_config(monkeypatch) -> None:
    monkeypatch.setenv("ATT1_BE_TRIGGER_RR", "1.0")
    contract = _target_att1_contract(monkeypatch)
    # Override after helper so the contract is self-consistent but not selected.
    monkeypatch.setenv("ATT1_BE_TRIGGER_RR", "1.0")
    contract = build_att1_runtime_contract(risk_mult=0.0)
    files, hashes = _att1_source_bundle()
    with pytest.raises(ContractViolation, match="selected_config_mismatch: be_trigger_rr"):
        adapt_att1_live_signal_to_plan(
            _att1_signal(), _evidence(), contract,
            source_files=files, expected_source_hashes=hashes,
        )


def test_att1_adapter_rejects_changed_source_bytes(monkeypatch) -> None:
    contract = _target_att1_contract(monkeypatch)
    files, hashes = _att1_source_bundle()
    files["strategies/att1_live.py"] += b"\n# changed after manifest\n"
    with pytest.raises(ContractViolation, match="source_hash_mismatch"):
        adapt_att1_live_signal_to_plan(
            _att1_signal(), _evidence(), contract,
            source_files=files, expected_source_hashes=hashes,
        )


@pytest.mark.parametrize(
    ("signal", "code"),
    [
        ({"side": "short"}, "invalid_trade_signal_type"),
        (_att1_signal(entry=99.0), "signal_entry_not_closed_h1_close"),
        (_att1_signal(reason="fixture"), "att1_signal_reason_mismatch"),
        (_att1_signal(time_stop_bars=2016), "wrong_strategy_time_stop"),
        (_att1_signal(tp_fracs=[0.50, 0.50]), "wrong_strategy_tp_fractions"),
    ],
)
def test_att1_adapter_refuses_fixture_shape_or_profile_drift(monkeypatch, signal, code) -> None:
    contract = _target_att1_contract(monkeypatch)
    files, hashes = _att1_source_bundle()
    with pytest.raises(ContractViolation, match=code):
        adapt_att1_live_signal_to_plan(  # type: ignore[arg-type]
            signal, _evidence(), contract,
            source_files=files, expected_source_hashes=hashes,
        )


def test_sbr1_real_research_signal_and_config_build_research_only_plan() -> None:
    files, hashes = _sbr1_source_bundle()
    plan = adapt_sbr1_research_signal_to_plan(
        _sbr1_signal(),
        _evidence(),
        _sbr1_config(),
        source_files=files,
        expected_source_hashes=hashes,
    )

    assert plan.sleeve_id == "SBR1"
    assert plan.side == "long"
    assert plan.time_stop_hours == 168
    assert [str(value) for value in plan.tp_fractions] == ["0.5", "0.3"]
    assert plan.residual_fraction == Decimal("0.20")


@pytest.mark.parametrize(
    "config",
    [
        SlopedBreakRetestV1Config(),
        _sbr1_config(allow_shorts=True),
        _sbr1_config(time_stop_bars_5m=288),
        _sbr1_config(trail_atr_mult=1.7),
    ],
)
def test_sbr1_research_adapter_rejects_nonselected_config(config) -> None:
    files, hashes = _sbr1_source_bundle()
    with pytest.raises(ContractViolation, match="selected_config_mismatch"):
        adapt_sbr1_research_signal_to_plan(
            _sbr1_signal(), _evidence(), config,
            source_files=files, expected_source_hashes=hashes,
        )


def test_sbr1_live_boundary_builds_same_frozen_plan_as_research_boundary() -> None:
    files, hashes = _sbr1_source_bundle()
    research = adapt_sbr1_research_signal_to_plan(
        _sbr1_signal(),
        _evidence(),
        _sbr1_config(),
        source_files=files,
        expected_source_hashes=hashes,
    )
    live = adapt_sbr1_live_signal_to_plan(
        _sbr1_signal(),
        _evidence(),
        _sbr1_config(),
        source_files=files,
        expected_source_hashes=hashes,
    )
    assert live == research
