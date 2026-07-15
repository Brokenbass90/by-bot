from __future__ import annotations

import dataclasses
import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from bot.bybit_cashcarry_shadow_v1 import CashCarryShadowError, FundingSettlement, ShadowConfig
from bot.bybit_cashcarry_shadow_v2 import (
    BookLevel,
    DurableCashCarryJournalV2,
    DurableCollectorConfigV2,
    InstrumentLegRules,
    InstrumentRulesV2,
    PublicMarketSnapshotV2,
    break_even_gate,
    build_quantized_execution_plan,
    snapshots_from_json,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/bybit_cashcarry_shadow_v2_replay.json"
RUNNER = ROOT / "scripts/run_bybit_cashcarry_shadow_v2.py"


def _fixture_snapshots() -> list[PublicMarketSnapshotV2]:
    return snapshots_from_json(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _load_runner():
    spec = importlib.util.spec_from_file_location("run_bybit_cashcarry_shadow_v2", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_collector_is_disabled_and_does_not_create_files(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    journal = DurableCashCarryJournalV2(journal_path)
    result = journal.ingest(_fixture_snapshots()[0])
    assert result["action"] == "disabled_noop"
    assert result["appended"] is False
    assert not journal_path.exists()
    assert not journal.lock_path.exists()


def test_common_quantity_quantization_and_multilevel_walk_are_deterministic() -> None:
    snapshot = _fixture_snapshots()[0]
    first = build_quantized_execution_plan(
        snapshot,
        target_notional_usd=100.0,
        slippage_bps_per_fill=2.0,
    )
    second = build_quantized_execution_plan(
        snapshot,
        target_notional_usd=100.0,
        slippage_bps_per_fill=2.0,
    )
    assert first == second
    assert first.quantity == "0.998"
    assert first.common_qty_step == "0.001"
    assert first.spot.levels_consumed == 2
    assert first.linear_perp.levels_consumed == 2
    assert sum(float(item.quantity) for item in first.spot.slices) == pytest.approx(0.998)
    assert float(first.spot.adverse_fill_price) > float(first.spot.raw_vwap)
    assert float(first.linear_perp.adverse_fill_price) < float(first.linear_perp.raw_vwap)
    assert float(first.spot.limit_guard_price) >= float(first.spot.slices[-1].price)
    assert float(first.linear_perp.limit_guard_price) <= float(first.linear_perp.slices[-1].price)
    assert first.full_fill_only is True
    assert first.partial_fill_recovery == "REFUSE_BEFORE_STATE_MUTATION"


def test_thin_second_level_refuses_entire_two_leg_plan_without_partial_fill(tmp_path: Path) -> None:
    snapshot = _fixture_snapshots()[0]
    thin = dataclasses.replace(
        snapshot,
        perp_bids=(BookLevel("100.15", "0.1"), BookLevel("100.10", "0.1")),
    )
    with pytest.raises(CashCarryShadowError, match="partial fills are forbidden"):
        build_quantized_execution_plan(
            thin,
            target_notional_usd=100.0,
            slippage_bps_per_fill=2.0,
        )
    journal = DurableCashCarryJournalV2(
        tmp_path / "thin.jsonl",
        collector_config=DurableCollectorConfigV2(enabled=True, shadow_enabled=True),
    )
    refused = journal.ingest(thin)
    assert refused["action"] == "refuse"
    assert "partial_fill_forbidden" in refused["reason"]
    assert refused["position_open"] is False
    assert "partial fills are forbidden" in refused["execution_plan_refusal"]


def test_off_tick_public_level_and_below_minimum_are_refused() -> None:
    snapshot = _fixture_snapshots()[0]
    with pytest.raises(CashCarryShadowError, match="tick-size aligned"):
        dataclasses.replace(
            snapshot,
            spot_bids=(BookLevel("99.955", "1"),),
        )

    high_minimum = InstrumentRulesV2(
        symbol="BTCUSDT",
        funding_interval_minutes=480,
        spot=InstrumentLegRules("spot", "0.01", "0.001", "0.001", "500"),
        linear_perp=InstrumentLegRules("linear_perp", "0.01", "0.001", "0.001", "500"),
    )
    with pytest.raises(CashCarryShadowError, match="below minimum"):
        build_quantized_execution_plan(
            dataclasses.replace(snapshot, instruments=high_minimum),
            target_notional_usd=100.0,
            slippage_bps_per_fill=2.0,
        )


def test_break_even_gate_blocks_current_like_positive_funding_that_cannot_cover_costs() -> None:
    snapshot = _fixture_snapshots()[2]
    weak_rate = 0.000076
    weak = dataclasses.replace(
        snapshot,
        projected_funding_rate=weak_rate,
        funding_settlements=tuple(
            FundingSettlement(item.settled_at_ms, weak_rate, item.perp_mark_price)
            for item in snapshot.funding_settlements
        ),
    )
    shadow = ShadowConfig(enabled=True)
    collector = DurableCollectorConfigV2(enabled=True, shadow_enabled=True)
    plan = build_quantized_execution_plan(
        weak,
        target_notional_usd=shadow.target_notional_usd,
        slippage_bps_per_fill=shadow.slippage_bps_per_fill,
    )
    gate = break_even_gate(weak, plan, shadow, collector)
    assert gate.passed is False
    assert gate.reason == "expected_carry_does_not_cover_four_fills_and_basis_stress"
    assert gate.expected_settlements_before_max_hold == 42
    assert gate.expected_carry_bps == pytest.approx(31.92)
    assert gate.required_carry_bps > gate.expected_carry_bps
    assert gate.four_fill_fee_bps == pytest.approx(31.0)


def test_weak_economics_is_durably_observed_but_cannot_open_shadow(tmp_path: Path) -> None:
    weak_rate = 0.000076
    snapshots = [
        dataclasses.replace(
            snapshot,
            projected_funding_rate=weak_rate,
            funding_settlements=tuple(
                FundingSettlement(item.settled_at_ms, weak_rate, item.perp_mark_price)
                for item in snapshot.funding_settlements
            ),
        )
        for snapshot in _fixture_snapshots()[:3]
    ]
    journal = DurableCashCarryJournalV2(
        tmp_path / "weak.jsonl",
        shadow_config=ShadowConfig(),
        collector_config=DurableCollectorConfigV2(enabled=True, shadow_enabled=True),
    )
    results = [journal.ingest(snapshot) for snapshot in snapshots]
    assert [row["action"] for row in results] == ["observe", "observe", "observe"]
    assert results[-1]["break_even_gate"]["passed"] is False
    assert results[-1]["position_open"] is False
    recovered = journal.recover()
    assert recovered["record_count"] == 3
    assert recovered["position_open"] is False


def test_append_only_restart_recovery_and_duplicate_are_idempotent(tmp_path: Path) -> None:
    snapshots = _fixture_snapshots()
    path = tmp_path / "durable.jsonl"
    collector = DurableCollectorConfigV2(enabled=True, shadow_enabled=True)
    journal = DurableCashCarryJournalV2(path, collector_config=collector)
    first_three = [journal.ingest(snapshot) for snapshot in snapshots[:3]]
    assert [row["action"] for row in first_three] == ["observe", "observe", "open_shadow"]
    assert first_three[-1]["position_open"] is True
    assert first_three[-1]["active_quantized_plan"]["quantity"] == "0.998"
    assert path.stat().st_mode & 0o777 == 0o600

    restarted = DurableCashCarryJournalV2(path, collector_config=collector)
    state = restarted.recover()
    assert state["record_count"] == 3
    assert state["position_open"] is True
    assert state["active_quantized_plan"]["quantity"] == "0.998"
    before = path.read_bytes()
    duplicate = restarted.ingest(snapshots[2])
    assert duplicate["action"] == "duplicate_noop"
    assert duplicate["appended"] is False
    assert path.read_bytes() == before

    closed = restarted.ingest(snapshots[3])
    assert closed["action"] == "close_shadow"
    assert closed["position_open"] is False
    final_state = DurableCashCarryJournalV2(path, collector_config=collector).recover()
    assert final_state["record_count"] == 4
    assert final_state["position_open"] is False
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[2]["state_after"]["quantized_open_plan"]["quantity"] == "0.998"
    assert rows[3]["state_after"]["quantized_open_plan"] is None
    assert rows[3]["legacy_v1_step"]["receipt"]["performance_claims"] is False


def test_torn_or_tampered_journal_fails_closed(tmp_path: Path) -> None:
    collector = DurableCollectorConfigV2(enabled=True, shadow_enabled=False)
    torn_path = tmp_path / "torn.jsonl"
    journal = DurableCashCarryJournalV2(torn_path, collector_config=collector)
    journal.ingest(_fixture_snapshots()[0])
    torn_path.write_bytes(torn_path.read_bytes()[:-1])
    with pytest.raises(CashCarryShadowError, match="torn journal tail"):
        journal.recover()

    changed_path = tmp_path / "changed.jsonl"
    changed = DurableCashCarryJournalV2(changed_path, collector_config=collector)
    changed.ingest(_fixture_snapshots()[0])
    raw = changed_path.read_text(encoding="utf-8")
    changed_path.write_text(raw.replace('"projected_funding_rate":0.0003', '"projected_funding_rate":0.0004'), encoding="utf-8")
    with pytest.raises(CashCarryShadowError, match="checksum mismatch"):
        changed.recover()


def test_public_adapter_parses_instruments_and_uses_only_allowlisted_get_paths() -> None:
    runner = _load_runner()
    calls: list[str] = []
    now = 1_700_100_000_000

    def fake_get(url: str, *, timeout: float) -> dict:
        del timeout
        calls.append(url)
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        category = query.get("category", [""])[0]
        base = {"retCode": 0, "time": now}
        if parsed.path == "/v5/market/instruments-info":
            is_spot = category == "spot"
            base["result"] = {"list": [{
                "symbol": "BTCUSDT",
                "fundingInterval": "480" if not is_spot else None,
                "priceFilter": {"tickSize": "0.01"},
                "lotSizeFilter": {
                    **({"basePrecision": "0.001"} if is_spot else {"qtyStep": "0.001"}),
                    "minOrderQty": "0.001",
                    **({"minOrderAmt": "5"} if is_spot else {"minNotionalValue": "5"}),
                },
            }]}
            return base
        if parsed.path == "/v5/market/orderbook":
            is_spot = category == "spot"
            base["result"] = {
                "ts": now - (400 if is_spot else 200),
                "b": [["99.95" if is_spot else "100.15", "0.4"], ["99.90" if is_spot else "100.10", "1"]],
                "a": [["100.05" if is_spot else "100.25", "0.4"], ["100.10" if is_spot else "100.30", "1"]],
            }
            return base
        if parsed.path == "/v5/market/tickers":
            base["result"] = {"list": [{
                "symbol": "BTCUSDT",
                "fundingRate": "0.0001",
                "nextFundingTime": str(now + 28_800_000),
            }]}
            return base
        assert parsed.path == "/v5/market/funding/history"
        base["result"] = {"list": [{
            "fundingRateTimestamp": str(now - 60_000),
            "fundingRate": "0.0001",
        }]}
        return base

    snapshot = runner.fetch_public_snapshot("BTCUSDT", get_json=fake_get)
    assert snapshot.instruments.funding_interval_minutes == 480
    assert snapshot.instruments.common_qty_step == snapshot.instruments.spot.qty_step_decimal
    assert len(snapshot.spot_asks) == 2 and len(snapshot.perp_bids) == 2
    assert snapshot.funding_settlements[0].perp_mark_price == pytest.approx(100.2)
    assert {urlparse(url).path for url in calls} == set(runner.PUBLIC_PATHS)
    assert len(calls) == 6
    assert all("api_key" not in url.lower() and "/v5/order" not in url for url in calls)


def test_preflight_is_no_network_no_write_no_daemon_and_no_execution_authority() -> None:
    runner = _load_runner()
    receipt = runner._preflight(runner.DEFAULT_SPEC)
    assert receipt["status"] == "RESEARCH_ONLY_DISABLED"
    assert receipt["default_collector_enabled"] is False
    assert receipt["default_shadow_enabled"] is False
    assert receipt["network_calls"] is False
    assert receipt["daemon_started"] is False
    assert receipt["key_or_environment_reads"] is False
    assert receipt["private_api_calls"] is False
    assert receipt["broker_calls"] is False
    assert receipt["executable"] is False
    with pytest.raises(CashCarryShadowError, match="frozen public Bybit"):
        runner._get_json("https://example.com/v5/market/tickers?category=linear")


def test_runner_source_has_no_environment_key_or_order_adapter() -> None:
    runner_source = RUNNER.read_text(encoding="utf-8")
    module_source = (ROOT / "bot/bybit_cashcarry_shadow_v2.py").read_text(encoding="utf-8")
    forbidden = ("os.getenv", "os.environ", "/v5/order/", "/v5/position/", "/v5/account/", "api-secret")
    for token in forbidden:
        assert token not in runner_source
        assert token not in module_source
