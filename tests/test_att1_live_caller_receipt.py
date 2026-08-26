from __future__ import annotations

import ast
import hashlib
import json
import stat
from pathlib import Path

from bot.att1_live_caller_receipt import (
    ATT1_CALLER_RECEIPTS_ENABLED_BY_DEFAULT,
    append_att1_decision_receipt,
    build_att1_decision_receipt,
    load_att1_source_inputs,
    receipt_jsonl_bytes,
)
from bot.att1_runtime_contract import build_att1_runtime_contract
from bot.live_native_decision_contract import H1_MS
from bot.persisted_btc_h1_regime import bootstrap_btc_h1_regime
from research_lab.att1_live_caller_receipt_replay import build_att1_replay_receipt
from strategies.signals import TradeSignal


ROOT = Path(__file__).resolve().parents[1]
CLOSED_H1_TS_MS = 1_800_000_000_000
OBSERVED_AT_MS = CLOSED_H1_TS_MS + 1
ATT1_SOURCE_PATHS = (
    "strategies/alt_trendline_touch_v1.py",
    "strategies/att1_live.py",
    "strategies/live_kline_utils.py",
    "strategies/signals.py",
)


def _closed_rows(count: int = 121) -> list[list[object]]:
    latest_start = CLOSED_H1_TS_MS - H1_MS
    first = latest_start - (count - 1) * H1_MS
    return [
        [first + index * H1_MS, "100", "102", "98", "100", "1000"]
        for index in range(count)
    ]


def _source_bundle() -> tuple[dict[str, bytes], dict[str, str]]:
    files = {path: (ROOT / path).read_bytes() for path in ATT1_SOURCE_PATHS}
    hashes = {path: hashlib.sha256(data).hexdigest() for path, data in files.items()}
    return files, hashes


def _effective_contract(monkeypatch):
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


def _signal() -> TradeSignal:
    return TradeSignal(
        strategy="alt_trendline_touch_v1",
        symbol="BTCUSDT",
        side="short",
        entry=100.0,
        sl=110.0,
        tp=75.0,
        tps=[88.0, 75.0],
        tp_fracs=[0.55, 0.45],
        be_trigger_rr=0.0,
        trailing_atr_mult=0.0,
        time_stop_bars=4032,
        reason="att1_short_trendline tf=60",
    )


def _caller_context(*, exposure_enforced: bool = True, symbol: str = "BTCUSDT") -> dict:
    return {
        "schema_id": "live_native_caller_context_v1",
        "exchange_filter": {
            "symbol": symbol,
            "tick_size": "0.1",
            "qty_step": "0.001",
            "min_notional": "5",
        },
        "intended_fill": {
            "entry_order": "market",
            "fill_source": "terminal_order_plus_complete_executions",
            "max_fill_age_ms": 300_000,
            "max_finalize_delay_ms": 60_000,
            "max_adverse_risk_expansion": "0.20",
        },
        "portfolio": {
            "slot_allowed": True,
            "open_positions": 0,
            "max_positions": 3,
            "exposure_gate_required": True,
            "exposure_gate_enforced": exposure_enforced,
            "exposure_allowed": True if exposure_enforced else None,
            "drop_reason": "",
        },
    }


def _regime_receipt(*, last_closed_h1_ts_ms: int = CLOSED_H1_TS_MS):
    latest_start = last_closed_h1_ts_ms - H1_MS
    first = latest_start - 499 * H1_MS
    rows: list[list[object]] = []
    for index in range(500):
        close = "99" if index == 499 else "100"
        rows.append(
            [first + index * H1_MS, "100", "102", "98", close, "1000"]
        )
    data_hash = hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
    return bootstrap_btc_h1_regime(
        rows,
        observed_at_ms=last_closed_h1_ts_ms + 1,
        max_age_ms=300_000,
        source_provenance={
            "provider": "bybit-public",
            "endpoint": "/v5/market/kline",
            "source_sha256": "a" * 64,
        },
        data_provenance={
            "symbol": "BTCUSDT",
            "interval": "60",
            "data_sha256": data_hash,
            "provenance": "pytest-causal-closed-h1",
        },
    )


def _build(monkeypatch, **updates):
    files, hashes = _source_bundle()
    values = {
        "symbol": "BTCUSDT",
        "observed_at_ms": OBSERVED_AT_MS,
        "consumed_closed_rows": _closed_rows(),
        "signal": None,
        "no_signal_reason": "touch_miss",
        "runtime_contract": _effective_contract(monkeypatch),
        "source_files": files,
        "expected_source_hashes": hashes,
        "source_manifest_sha256": "b" * 64,
        "regime_required": False,
        "persisted_regime_receipt": None,
        "max_decision_age_ms": 300_000,
        "caller_context": _caller_context(),
        "evaluation_error": None,
        "error_stage": "strategy",
    }
    values.update(updates)
    return build_att1_decision_receipt(**values)


def test_live_shaped_and_replay_inputs_emit_byte_equal_signal_receipt(monkeypatch) -> None:
    live = _build(
        monkeypatch,
        signal=_signal(),
        no_signal_reason="",
        regime_required=True,
        persisted_regime_receipt=_regime_receipt(),
    )
    files, hashes = _source_bundle()
    replay = build_att1_replay_receipt(
        symbol="BTCUSDT",
        observed_at_ms=OBSERVED_AT_MS,
        consumed_closed_rows=_closed_rows(),
        signal=_signal(),
        no_signal_reason="",
        runtime_contract=_effective_contract(monkeypatch),
        source_files=files,
        expected_source_hashes=hashes,
        source_manifest_sha256="b" * 64,
        regime_required=True,
        persisted_regime_receipt=_regime_receipt(),
        max_decision_age_ms=300_000,
        caller_context=_caller_context(),
    )

    assert ATT1_CALLER_RECEIPTS_ENABLED_BY_DEFAULT is False
    assert live["status"] == "SIGNAL"
    assert live["decision"]["side"] == "short"
    assert live["regime"]["allows_att1"] is True
    assert live["money_authority"] is False
    assert live["orders_allowed"] is False
    assert live["release_or_promotion_authority"] is False
    assert live["consumed_rows_count"] == 121
    assert live["caller_context"] == _caller_context()
    assert receipt_jsonl_bytes(live) == receipt_jsonl_bytes(replay)


def test_no_signal_is_explicit_and_not_an_exception(monkeypatch) -> None:
    receipt = _build(monkeypatch)

    assert receipt["status"] == "NO_SIGNAL"
    assert receipt["effective_config"] == _effective_contract(monkeypatch)["params"]
    assert receipt["decision"] == {
        "kind": "no_signal",
        "no_signal_reason": "touch_miss",
        "plan": None,
    }
    assert receipt["exception"] is None


def test_no_signal_requires_an_explicit_drop_reason(monkeypatch) -> None:
    receipt = _build(monkeypatch, no_signal_reason="")

    assert receipt["status"] == "FAIL_CLOSED"
    assert receipt["exception"]["code"] == "missing_no_signal_reason"


def test_receipt_symbol_must_match_real_signal_symbol(monkeypatch) -> None:
    receipt = _build(
        monkeypatch,
        symbol="ETHUSDT",
        signal=_signal(),
        no_signal_reason="",
        caller_context=_caller_context(symbol="ETHUSDT"),
    )

    assert receipt["status"] == "FAIL_CLOSED"
    assert receipt["exception"]["code"] == "att1_signal_symbol_mismatch"


def test_receipt_preserves_explicit_not_yet_enforced_exposure_gate(monkeypatch) -> None:
    receipt = _build(
        monkeypatch,
        signal=_signal(),
        no_signal_reason="",
        caller_context=_caller_context(exposure_enforced=False),
    )

    assert receipt["status"] == "SIGNAL"
    assert receipt["caller_context"]["portfolio"] == {
        "slot_allowed": True,
        "open_positions": 0,
        "max_positions": 3,
        "exposure_gate_required": True,
        "exposure_gate_enforced": False,
        "exposure_allowed": None,
        "drop_reason": "exposure_gate_not_connected",
    }
    assert receipt["money_authority"] is False


def test_signal_stop_is_rounded_outward_using_consumed_exchange_filter(monkeypatch) -> None:
    signal = _signal()
    risk = 9.96
    signal.sl = 100.0 + risk
    signal.tps = [100.0 - 1.2 * risk, 100.0 - 2.5 * risk]
    signal.tp = signal.tps[-1]

    receipt = _build(
        monkeypatch,
        signal=signal,
        no_signal_reason="",
    )

    assert receipt["status"] == "SIGNAL"
    assert receipt["decision"]["frozen_sl"] == "110"
    assert receipt["decision"]["planned_tps"] == ["88", "75"]


def test_no_signal_still_binds_runtime_contract_to_actual_strategy_source(monkeypatch) -> None:
    contract = json.loads(json.dumps(_effective_contract(monkeypatch)))
    contract["params"]["strategy_source_sha256"] = "c" * 64
    contract["sha256"] = hashlib.sha256(
        json.dumps(
            contract["params"], sort_keys=True, separators=(",", ":")
        ).encode("ascii")
    ).hexdigest()

    receipt = _build(monkeypatch, runtime_contract=contract)

    assert receipt["status"] == "FAIL_CLOSED"
    assert receipt["exception"]["code"] == "att1_runtime_strategy_source_mismatch"


def test_strategy_exception_is_a_fail_closed_receipt_not_no_signal(monkeypatch) -> None:
    receipt = _build(
        monkeypatch,
        no_signal_reason="",
        evaluation_error=RuntimeError("private text must not be journaled"),
        error_stage="strategy_evaluation",
    )

    assert receipt["status"] == "FAIL_CLOSED"
    assert receipt["decision"]["kind"] == "error"
    assert receipt["exception"] == {
        "code": "unexpected_exception",
        "stage": "strategy_evaluation",
        "type": "RuntimeError",
    }
    assert b"private text" not in receipt_jsonl_bytes(receipt)


def test_strategy_exception_identity_survives_when_engine_consumed_no_rows(monkeypatch) -> None:
    receipt = _build(
        monkeypatch,
        consumed_closed_rows=[],
        no_signal_reason="",
        evaluation_error=RuntimeError("fetch failed before a row was consumed"),
        error_stage="strategy_evaluation",
    )

    assert receipt["status"] == "FAIL_CLOSED"
    assert receipt["consumed_rows_count"] == 0
    assert receipt["exception"] == {
        "code": "unexpected_exception",
        "stage": "strategy_evaluation",
        "type": "RuntimeError",
    }


def test_missing_or_stale_persisted_regime_is_fail_closed(monkeypatch) -> None:
    missing = _build(monkeypatch, regime_required=True)
    stale = _build(
        monkeypatch,
        regime_required=True,
        persisted_regime_receipt=_regime_receipt(
            last_closed_h1_ts_ms=CLOSED_H1_TS_MS - H1_MS
        ),
    )

    assert missing["status"] == "FAIL_CLOSED"
    assert missing["exception"]["code"] == "missing_persisted_btc_regime_receipt"
    assert stale["status"] == "FAIL_CLOSED"
    assert stale["exception"]["code"] == "evidence_too_old"
    assert missing["decision"]["kind"] == stale["decision"]["kind"] == "error"


def test_append_is_locked_durable_jsonl_with_mode_0600(monkeypatch, tmp_path: Path) -> None:
    receipt = _build(monkeypatch)
    journal = tmp_path / "nested" / "att1-decisions.jsonl"

    append_att1_decision_receipt(journal, receipt)
    append_att1_decision_receipt(journal, receipt)

    assert stat.S_IMODE(journal.stat().st_mode) == 0o600
    assert journal.read_bytes() == receipt_jsonl_bytes(receipt) * 2
    assert [json.loads(line) for line in journal.read_text().splitlines()] == [
        receipt,
        receipt,
    ]


def test_production_caller_has_default_off_receipt_calls_for_all_outcomes() -> None:
    source = (ROOT / "smart_pump_reversal_bot.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    caller = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "try_att1_entry_async"
    )
    helper = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_att1_record_caller_receipt"
    )
    calls = [
        node
        for node in ast.walk(caller)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_att1_record_caller_receipt"
    ]
    constants = {
        target.id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
        and target.id
        in {
            "ATT1_CALLER_RECEIPT_ENABLE",
            "ATT1_CALLER_REGIME_RECEIPT_REQUIRED",
        }
    }

    assert len(calls) == 3  # strategy exception, ordinary no-signal, real signal
    assert any(any(keyword.arg == "evaluation_error" for keyword in call.keywords) for call in calls)
    assert any(any(keyword.arg == "no_signal_reason" for keyword in call.keywords) for call in calls)
    assert any(any(keyword.arg == "signal" for keyword in call.keywords) for call in calls)
    assignment = constants["ATT1_CALLER_RECEIPT_ENABLE"]
    assert isinstance(assignment, ast.Call)
    assert isinstance(assignment.func, ast.Name) and assignment.func.id == "_env_bool"
    assert isinstance(assignment.args[1], ast.Constant) and assignment.args[1].value is False
    regime_assignment = constants["ATT1_CALLER_REGIME_RECEIPT_REQUIRED"]
    assert isinstance(regime_assignment, ast.Call)
    assert isinstance(regime_assignment.func, ast.Name)
    assert regime_assignment.func.id == "_env_bool"
    assert isinstance(regime_assignment.args[1], ast.Constant)
    assert regime_assignment.args[1].value is True
    assert isinstance(helper.body[0], ast.Expr)  # docstring
    disabled_guard = helper.body[1]
    assert isinstance(disabled_guard, ast.If)
    assert isinstance(disabled_guard.test, ast.UnaryOp)
    assert isinstance(disabled_guard.test.operand, ast.Name)
    assert disabled_guard.test.operand.id == "ATT1_CALLER_RECEIPT_ENABLE"
    helper_calls = {
        node.func.id
        for node in ast.walk(helper)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "load_btc_h1_regime" in helper_calls
    assert "closed_h1_btc_ema200_regime" not in helper_calls
    assert "bootstrap_btc_h1_regime" not in helper_calls


def test_presealed_replay_calls_the_same_receipt_boundary() -> None:
    source = (
        ROOT / "research_lab" / "att1_live_caller_receipt_replay.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "build_att1_decision_receipt" in called_names
    assert "receipt_jsonl_bytes" in called_names


def test_source_loader_rejects_a_different_manifest_schema(tmp_path: Path) -> None:
    source_files, source_hashes = _source_bundle()
    manifest = tmp_path / "wrong-schema.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_id": "lookalike_manifest_v1",
                "source_files": [
                    {"path": path, "sha256": source_hashes[path]}
                    for path in sorted(source_files)
                ],
            }
        ),
        encoding="utf-8",
    )

    try:
        load_att1_source_inputs(ROOT, manifest)
    except Exception as exc:
        assert getattr(exc, "code", "") == "invalid_att1_source_manifest"
    else:
        raise AssertionError("lookalike source manifest must fail closed")
