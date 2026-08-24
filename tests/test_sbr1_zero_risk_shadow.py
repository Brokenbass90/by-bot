from __future__ import annotations

import ast
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from bot.live_native_decision_contract import FillRebasePolicy, LiveNativeDecisionPlan
from bot.live_native_manifest import load_and_verify_manifest
from bot.sbr1_zero_risk_shadow import (
    AUTHORITY,
    AppendOnlyShadowJournal,
    CausalEmaRegimeState,
    SHADOW_ENABLED_BY_DEFAULT,
    ShadowViolation,
    TickNativeShadowExecution,
    ZeroRiskShadowConfig,
    advance_causal_ema,
    bootstrap_causal_ema,
    evaluate_prospective_outcome,
    load_config,
    shadow_slot_gate,
    tick_native_shadow_execution,
    verify_source_closure,
)
from scripts.run_sbr1_zero_risk_shadow import (
    _public_get_bytes,
    fetch_public_filters,
    fetch_public_klines,
    verify_public_filters,
)


ROOT = Path(__file__).resolve().parents[1]
H1 = 3_600_000
M5 = 300_000


def _closure() -> dict[str, str]:
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
        "scripts/run_sbr1_zero_risk_shadow.py",
        "deploy/systemd/sbr1-zero-risk-shadow.service",
        "deploy/systemd/sbr1-zero-risk-shadow.timer",
    )
    return {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths
    }


def _config(**updates: object) -> ZeroRiskShadowConfig:
    raw: dict[str, object] = {
        "schema_id": "sbr1_zero_risk_shadow_config_v1",
        "enabled": False,
        "authority": AUTHORITY,
        "money_authority": False,
        "orders_allowed": False,
        "private_api_allowed": False,
        "release_or_promotion_authority": False,
        "sealed_data_allowed": False,
        "public_base": "https://api.bybit.com",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "parity_manifest_path": "configs/research/att1_sbr1_live_native_parity_v1.json",
        "expected_parity_manifest_sha256": "a" * 64,
        "journal_path": "runtime/sbr1_zero_risk_shadow/events.jsonl",
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
        "symbol_clusters": {
            "BTCUSDT": "btc",
            "ETHUSDT": "eth",
            "SOLUSDT": "alt",
        },
        "source_closure": _closure(),
        "shadow_risk_fraction_per_slot": "0.02",
        "max_cluster_risk_fraction": "0.04",
    }
    raw.update(updates)
    return ZeroRiskShadowConfig.from_mapping(raw)


def _plan() -> LiveNativeDecisionPlan:
    return LiveNativeDecisionPlan(
        spec_id="sbr1-live-native-v2",
        sleeve_id="SBR1",
        symbol="BTCUSDT",
        side="long",
        closed_h1_ts_ms=1_800_000_000_000,
        planned_entry=Decimal("100"),
        frozen_sl=Decimal("90"),
        planned_tps=(Decimal("111"), Decimal("126")),
        tp_fractions=(Decimal("0.5"), Decimal("0.3")),
        residual_fraction=Decimal("0.2"),
        time_stop_hours=168,
        config_hash="a" * 64,
        source_hash="b" * 64,
        data_hash="c" * 64,
    )


def _policy(plan: LiveNativeDecisionPlan) -> FillRebasePolicy:
    return FillRebasePolicy(
        spec_id=plan.spec_id,
        profile_hash=plan.profile_hash,
        tick_size=Decimal("0.5"),
        max_adverse_risk_expansion=Decimal("0.2"),
        max_fill_age_ms=300_000,
        max_finalize_delay_ms=60_000,
    )


def _h1_rows(count: int = 900, start: int = 1_700_000_400_000):
    start -= start % H1
    rows = []
    for index in range(count):
        price = Decimal("100") + Decimal(index) / Decimal("100")
        rows.append(
            [
                str(start + index * H1),
                str(price),
                str(price + 1),
                str(price - 1),
                str(price),
                "10",
            ]
        )
    return rows


def test_default_off_and_authority_are_fail_closed():
    assert SHADOW_ENABLED_BY_DEFAULT is False
    config = _config()
    assert config.enabled is False
    assert config.authority == AUTHORITY
    with pytest.raises(ShadowViolation, match="unsafe_authority:orders_allowed"):
        _config(orders_allowed=True)
    with pytest.raises(ShadowViolation, match="source_closure_mismatch"):
        _config(source_closure={})


def test_repository_config_pins_verified_manifest_and_full_source_closure():
    config = load_config(ROOT / "configs/sbr1_zero_risk_shadow_v1.json")
    assert config.enabled is False
    manifest = load_and_verify_manifest(
        ROOT,
        ROOT / config.parity_manifest_path,
        verify_data_bytes=False,
        verify_source_bytes=True,
    )
    assert manifest.manifest_sha256 == config.expected_parity_manifest_sha256
    assert tuple(manifest.universe) == config.universe
    assert len(verify_source_closure(ROOT, config)) == 64


def test_source_closure_includes_indirect_strategy_dependencies(tmp_path: Path):
    config = _config()
    assert "strategies/signals.py" in config.source_closure
    assert "strategies/live_kline_utils.py" in config.source_closure
    assert len(verify_source_closure(ROOT, config)) == 64
    bad = dict(config.source_closure)
    bad["strategies/signals.py"] = "0" * 64
    with pytest.raises(ShadowViolation, match="source_closure_hash_mismatch"):
        verify_source_closure(ROOT, _config(source_closure=bad))


def test_append_only_journal_is_hash_chained_idempotent_and_conflict_closed(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    journal = AppendOnlyShadowJournal(path)
    assert journal.append("evaluation", "eval:1", {"status": "no_signal"}) is True
    assert journal.append("evaluation", "eval:1", {"status": "no_signal"}) is False
    assert journal.append("fill", "fill:1", {"price": "100"}) is True
    events = journal.read()
    assert len(events) == 2
    assert events[1]["previous_event_hash"] == events[0]["event_hash"]
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ShadowViolation, match="journal_claim_conflict"):
        journal.append("evaluation", "eval:1", {"status": "signal"})
    lines = path.read_text(encoding="ascii").splitlines()
    broken = json.loads(lines[0])
    broken["payload"]["status"] = "tampered"
    lines[0] = json.dumps(broken, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    with pytest.raises(ShadowViolation, match="journal_event_id_mismatch"):
        journal.read()


def test_causal_ema_has_explicit_seed_and_rejects_noncontiguous_update():
    rows = _h1_rows()
    state = bootstrap_causal_ema(rows)
    assert state.seed_bar_start_ts_ms == int(rows[0][0])
    assert state.observation_count == 900
    restored = CausalEmaRegimeState.from_dict(state.to_dict())
    assert restored == state
    next_row = _h1_rows(1, int(rows[-1][0]) + H1)
    updated = advance_causal_ema(state, next_row[0])
    assert updated.observation_count == 901
    assert updated.history_hash != state.history_hash
    with pytest.raises(ShadowViolation, match="noncausal_regime_update"):
        advance_causal_ema(state, rows[-1])


def test_tick_native_fill_stop_targets_and_stop_first_outcome():
    plan = _plan()
    policy = _policy(plan)
    row = [str(plan.closed_h1_ts_ms), "100", "101", "99", "100", "10"]
    row_bytes = json.dumps(
        row, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    execution = tick_native_shadow_execution(
        plan,
        policy,
        row,
        row_bytes=row_bytes,
        adverse_slippage_bps="2",
        qty_step="0.001",
        min_notional="5",
    )
    assert execution.fill.fill_price == Decimal("100.5")
    assert execution.stop == Decimal("90.0")
    assert execution.targets == (Decimal("112.5"), Decimal("128.0"))
    assert execution.fill.cumulative_filled_qty == Decimal("0.050")
    assert all(
        value % Decimal("0.5") == 0
        for value in (execution.fill.fill_price, execution.stop, *execution.targets)
    )
    rows = [
        [str(plan.closed_h1_ts_ms), "100.5", "113", "100", "112", "1"],
        [str(plan.closed_h1_ts_ms + M5), "112", "129", "110", "128", "1"],
        [str(plan.closed_h1_ts_ms + 2 * M5), "100", "110", "89", "90", "1"],
    ]
    outcome = evaluate_prospective_outcome(
        plan,
        execution,
        policy,
        rows,
        fee_bps_per_side="6",
        exit_slippage_bps="2",
    )
    assert outcome.finalized is True
    assert outcome.label == "tp1+tp2+stop"
    assert outcome.net_r is not None


def test_shadow_slot_and_cluster_limits_are_enforced():
    config = _config(max_open_slots_per_cluster=1)
    assert shadow_slot_gate(config, "SOLUSDT", ["BTCUSDT"])[0] is True
    assert shadow_slot_gate(config, "BTCUSDT", ["BTCUSDT"]) == (
        False,
        "symbol_already_open",
    )
    same_cluster = _config(
        max_open_slots_per_cluster=1,
        symbol_clusters={"BTCUSDT": "major", "ETHUSDT": "major", "SOLUSDT": "alt"},
    )
    assert shadow_slot_gate(same_cluster, "ETHUSDT", ["BTCUSDT"]) == (
        False,
        "cluster_slots_full",
    )


def test_public_adapter_rejects_non_bybit_or_private_shape_before_network():
    with pytest.raises(ShadowViolation, match="nonpublic_bybit_request_rejected"):
        _public_get_bytes(
            "https://evil.example/v5/market/kline?category=linear",
            timeout=1,
        )
    with pytest.raises(ShadowViolation, match="nonpublic_bybit_request_rejected"):
        _public_get_bytes(
            "https://api.bybit.com/v5/order/create?category=linear",
            timeout=1,
        )


def test_public_kline_decoder_preserves_exchange_clock_and_sorts_rows():
    payload = {
        "retCode": 0,
        "time": 1_800_000_300_000,
        "result": {
            "list": [
                ["1800000000000", "100", "101", "99", "100", "1"],
                ["1799999700000", "99", "100", "98", "99", "1"],
            ]
        },
    }

    def get_bytes(_url: str, *, timeout: float) -> bytes:
        assert timeout == 2
        return json.dumps(payload).encode("utf-8")

    snapshot = fetch_public_klines(
        "https://api.bybit.com",
        "BTCUSDT",
        "5",
        2,
        timeout=2,
        get_bytes=get_bytes,
    )
    assert snapshot.observed_at_ms == payload["time"]
    assert snapshot.rows[0][0] == "1799999700000"


def test_public_exchange_filters_must_match_frozen_tick_qty_and_notional():
    payload = {
        "retCode": 0,
        "time": 1_800_000_300_000,
        "result": {
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "priceFilter": {"tickSize": "0.10"},
                    "lotSizeFilter": {"qtyStep": "0.001", "minNotionalValue": "5"},
                }
            ]
        },
    }

    def get_bytes(_url: str, *, timeout: float) -> bytes:
        assert timeout == 2
        return json.dumps(payload).encode("utf-8")

    snapshot = fetch_public_filters(
        "https://api.bybit.com", "BTCUSDT", timeout=2, get_bytes=get_bytes
    )
    verify_public_filters(
        snapshot,
        {"tick_size": "0.1", "qty_step": "0.0010", "min_notional": "5.0"},
    )
    with pytest.raises(ShadowViolation, match="exchange_filter_drift"):
        verify_public_filters(
            snapshot,
            {"tick_size": "0.01", "qty_step": "0.001", "min_notional": "5"},
        )


def test_runner_import_graph_has_no_money_or_monolith_modules():
    forbidden = {
        "smart_pump_reversal_bot",
        "pybit",
        "alpaca",
        "bot.bybit_client",
        "bot.order_manager",
    }
    for relative in (
        "bot/sbr1_zero_risk_shadow.py",
        "scripts/run_sbr1_zero_risk_shadow.py",
    ):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        assert not (imports & forbidden)


def test_systemd_timer_covers_h1_decision_and_next_m5_fill_without_catchup():
    service = (ROOT / "deploy/systemd/sbr1-zero-risk-shadow.service").read_text()
    timer = (ROOT / "deploy/systemd/sbr1-zero-risk-shadow.timer").read_text()
    assert "--once --ack ZERO_RISK_SHADOW_ONLY" in service
    assert "ProtectSystem=strict" in service
    assert "WorkingDirectory=/opt/bybot-research/sbr1-zero-risk-shadow" in service
    assert (
        "ReadWritePaths=/opt/bybot-research/sbr1-zero-risk-shadow/"
        "runtime/sbr1_zero_risk_shadow" in service
    )
    assert "WorkingDirectory=/root/by-bot\n" not in service
    assert "OnCalendar=*-*-* *:0/5:20 UTC" in timer
    assert "Persistent=false" in timer
