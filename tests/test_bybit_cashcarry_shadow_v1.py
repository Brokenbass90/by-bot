from __future__ import annotations

import dataclasses
import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from bot import bybit_cashcarry_shadow_v1 as mod
from bot.bybit_cashcarry_shadow_v1 import (
    CashCarryShadowEngine,
    CashCarryShadowError,
    FundingSettlement,
    PublicQuoteObservation,
    ShadowConfig,
    append_cycle_receipt,
    observations_from_json,
    replay_observations,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/bybit_cashcarry_shadow_v1_replay.json"
RUNNER = ROOT / "scripts/run_bybit_cashcarry_shadow_v1.py"


def _obs(
    ts: int,
    *,
    funding: tuple[FundingSettlement, ...] = (),
    projected: float = 0.0001,
    spot_bid: float = 99.95,
    spot_ask: float = 100.05,
    perp_bid: float = 100.15,
    perp_ask: float = 100.25,
    depth: float = 50.0,
    complete: bool = True,
    spot_ts: int | None = None,
    perp_ts: int | None = None,
) -> PublicQuoteObservation:
    return PublicQuoteObservation(
        symbol="BTCUSDT",
        observed_at_ms=ts,
        spot_quote_ts_ms=ts if spot_ts is None else spot_ts,
        perp_quote_ts_ms=ts if perp_ts is None else perp_ts,
        spot_bid=spot_bid,
        spot_ask=spot_ask,
        spot_bid_qty=depth,
        spot_ask_qty=depth,
        perp_bid=perp_bid,
        perp_ask=perp_ask,
        perp_bid_qty=depth,
        perp_ask_qty=depth,
        projected_funding_rate=projected,
        next_funding_time_ms=ts + 8 * 60 * 60 * 1000,
        funding_settlements=funding,
        complete=complete,
    )


def _settlement(ts: int, rate: float = 0.0001, price: float | None = 100.2) -> FundingSettlement:
    return FundingSettlement(settled_at_ms=ts, rate=rate, perp_mark_price=price)


def _load_runner():
    spec = importlib.util.spec_from_file_location("run_bybit_cashcarry_shadow_v1", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_is_disabled_and_cannot_open_after_three_settlements() -> None:
    engine = CashCarryShadowEngine()
    assert engine.config.enabled is False
    actions = []
    for index in range(3):
        ts = 1_700_000_000_000 + index * 28_800_000
        actions.append(engine.step(_obs(ts, funding=(_settlement(ts),))).action)
    assert actions == ["disabled_noop", "disabled_noop", "disabled_noop"]
    assert engine.position_open is False
    assert engine.positive_funding_count == 3


def test_entry_requires_three_distinct_completed_positive_funding_observations() -> None:
    engine = CashCarryShadowEngine(ShadowConfig(enabled=True))
    base = 1_700_000_000_000
    first = engine.step(_obs(base, funding=(_settlement(base),)))
    second_ts = base + 28_800_000
    second = engine.step(_obs(second_ts, funding=(_settlement(second_ts),)))
    third_ts = second_ts + 28_800_000
    third = engine.step(_obs(third_ts, funding=(_settlement(third_ts),)))
    assert [first.action, second.action, third.action] == ["observe", "observe", "open_shadow"]
    assert third.completed_positive_funding_count == 3
    assert engine.position_open is True
    assert engine.step(_obs(third_ts, funding=(_settlement(third_ts),))).action == "duplicate_noop"


def test_fixture_models_four_adverse_fills_fees_settlement_timing_and_flip_exit() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    observations = observations_from_json(payload)
    steps, receipts = replay_observations(observations, ShadowConfig(enabled=True))
    assert [step.action for step in steps] == [
        "observe", "observe", "open_shadow", "hold_shadow", "close_shadow"
    ]
    assert len(receipts) == 1
    receipt = receipts[0]
    receipt.verify()
    assert receipt.close_reason == "funding_flip"
    assert len(receipt.fills) == 4
    spot_open, perp_open, spot_close, perp_close = receipt.fills
    assert spot_open.fill_price > spot_open.reference_price
    assert perp_open.fill_price < perp_open.reference_price
    assert spot_close.fill_price < spot_close.reference_price
    assert perp_close.fill_price > perp_close.reference_price
    assert spot_open.notional_usd == pytest.approx(100.0)
    assert perp_open.notional_usd == pytest.approx(100.0)
    # The three settlements used for persistence occurred no later than entry
    # and are not miscredited.  Only one later positive and the flip are booked.
    assert len(receipt.funding_cashflows) == 2
    assert all(flow.settled_at_ms > receipt.opened_at_ms for flow in receipt.funding_cashflows)
    assert receipt.funding_cashflows[0].cashflow_usd > 0
    assert receipt.funding_cashflows[1].cashflow_usd < 0
    assert receipt.total_fee_usd == pytest.approx(sum(fill.fee_usd for fill in receipt.fills))
    assert receipt.net_pnl_usd == pytest.approx(
        receipt.spot_leg_pnl_usd
        + receipt.perp_leg_pnl_usd
        + receipt.funding_cashflow_usd
        - receipt.total_fee_usd
    )
    assert receipt.performance_claims is False
    assert receipt.executable is False and receipt.broker_calls is False


def _opened_engine(**overrides: object) -> tuple[CashCarryShadowEngine, int]:
    config = ShadowConfig(enabled=True, **overrides)
    engine = CashCarryShadowEngine(config)
    base = 1_700_000_000_000
    for index in range(3):
        ts = base + index * 28_800_000
        result = engine.step(_obs(ts, funding=(_settlement(ts),)))
    assert result.action == "open_shadow"
    return engine, ts


def test_adverse_basis_guard_closes_without_waiting_for_funding_flip() -> None:
    engine, opened = _opened_engine(max_adverse_basis_widen_bps=40.0)
    later = opened + 60_000
    result = engine.step(
        _obs(
            later,
            spot_bid=99.95,
            spot_ask=100.05,
            perp_bid=100.85,
            perp_ask=100.95,
        )
    )
    assert result.action == "close_shadow"
    assert result.reason == "adverse_basis_widen_guard"
    assert result.receipt is not None and result.receipt.adverse_basis_widen_bps > 40.0


def test_missing_funding_price_proxy_refuses_without_fabricating_cashflow() -> None:
    engine, opened = _opened_engine()
    later = opened + 28_800_000
    missing = engine.step(_obs(later, funding=(_settlement(later, price=None),)))
    assert missing.action == "refuse"
    assert missing.reason == "missing_funding_settlement_price_proxy"
    assert engine.position_open is True

    # The same exchange settlement remains unprocessed and can be ingested from
    # a complete retry carrying a near-time public valuation proxy.
    valid = engine.step(
        _obs(
            later + 1_000,
            funding=(_settlement(later, price=100.2),),
            spot_ts=later + 1_000,
            perp_ts=later + 1_000,
        )
    )
    assert valid.action == "hold_shadow"


def test_completed_funding_flip_exits_even_if_projected_rate_has_recovered() -> None:
    engine, opened = _opened_engine()
    later = opened + 28_800_000
    result = engine.step(
        _obs(
            later,
            funding=(_settlement(later, rate=-0.00001, price=100.2),),
            projected=0.0001,
        )
    )
    assert result.action == "close_shadow"
    assert result.reason == "funding_flip"
    assert result.receipt is not None
    assert result.receipt.funding_cashflows[-1].cashflow_usd < 0


def test_stale_incomplete_and_thin_books_refuse_without_partial_fills() -> None:
    config = ShadowConfig(enabled=True)
    stale_engine = CashCarryShadowEngine(config)
    ts = 1_700_000_000_000
    stale = stale_engine.step(_obs(ts, spot_ts=ts - config.max_quote_age_ms - 1))
    assert stale.action == "refuse" and stale.reason == "stale_spot_quote"
    assert stale_engine.positive_funding_count == 0

    incomplete_engine = CashCarryShadowEngine(config)
    incomplete = incomplete_engine.step(_obs(ts, complete=False))
    assert incomplete.action == "refuse" and incomplete.reason == "incomplete_public_snapshot"

    thin_engine = CashCarryShadowEngine(config)
    for index in range(2):
        cur = ts + index * 28_800_000
        thin_engine.step(_obs(cur, funding=(_settlement(cur),)))
    cur = ts + 2 * 28_800_000
    thin = thin_engine.step(_obs(cur, funding=(_settlement(cur),), depth=0.5))
    assert thin.action == "refuse"
    assert "partial_fill_forbidden" in thin.reason
    assert thin_engine.position_open is False


def test_delta_drift_is_measured_and_guarded() -> None:
    engine, opened = _opened_engine(max_delta_drift_bps=20.0)
    later = opened + 60_000
    # A large spot/perp relative move creates material residual delta for the
    # independently equal-notional entry quantities.
    result = engine.step(
        _obs(
            later,
            spot_bid=999.95,
            spot_ask=1000.05,
            perp_bid=999.95,
            perp_ask=1000.05,
        )
    )
    assert result.action == "close_shadow"
    assert result.reason == "delta_drift_guard"
    assert result.delta_drift_bps is not None


def test_append_only_receipt_is_idempotent_and_collision_fails_closed(tmp_path: Path) -> None:
    observations = observations_from_json(json.loads(FIXTURE.read_text(encoding="utf-8")))
    _, receipts = replay_observations(observations, ShadowConfig(enabled=True))
    receipt = receipts[0]
    ledger = tmp_path / "cycles.jsonl"
    assert append_cycle_receipt(ledger, receipt) is True
    assert append_cycle_receipt(ledger, receipt) is False
    assert ledger.stat().st_mode & 0o777 == 0o600
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 1

    altered_probe = dataclasses.replace(receipt, close_reason="max_hold_guard", receipt_sha256="")
    altered = dataclasses.replace(
        altered_probe,
        receipt_sha256=mod._sha256(mod._receipt_payload(altered_probe)),
    )
    altered.verify()
    with pytest.raises(CashCarryShadowError, match="cycle-id collision"):
        append_cycle_receipt(ledger, altered)


def test_public_adapter_uses_only_public_paths_and_preserves_timestamps() -> None:
    runner = _load_runner()
    calls: list[str] = []
    now = 1_700_000_000_000

    def fake_get(url: str, *, timeout: float) -> dict:
        del timeout
        calls.append(url)
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if parsed.path == "/v5/market/orderbook":
            is_spot = query["category"] == ["spot"]
            return {
                "retCode": 0,
                "time": now - (500 if is_spot else 200),
                "result": {
                    "ts": now - (500 if is_spot else 200),
                    "b": [["99.9" if is_spot else "100.1", "5"]],
                    "a": [["100.0" if is_spot else "100.2", "5"]],
                },
            }
        if parsed.path == "/v5/market/tickers":
            return {
                "retCode": 0,
                "time": now,
                "result": {"list": [{
                    "symbol": "BTCUSDT",
                    "fundingRate": "0.0001",
                    "nextFundingTime": str(now + 28_800_000),
                }]},
            }
        assert parsed.path == "/v5/market/funding/history"
        return {
            "retCode": 0,
            "time": now,
            "result": {"list": [{
                "fundingRateTimestamp": str(now - 60_000),
                "fundingRate": "0.0001",
            }]},
        }

    observation = runner.fetch_public_observation("BTCUSDT", get_json=fake_get)
    assert observation.source == "bybit_public_v5"
    assert observation.observed_at_ms == now
    assert observation.funding_settlements[0].perp_mark_price == pytest.approx(100.15)
    assert {urlparse(url).path for url in calls} == set(runner.PUBLIC_PATHS)
    assert all("api_key" not in url.lower() and "/v5/order" not in url for url in calls)


def test_preflight_is_no_network_disabled_and_has_no_execution_authority() -> None:
    runner = _load_runner()
    receipt = runner._preflight(runner.DEFAULT_SPEC)
    assert receipt["ok"] is True
    assert receipt["status"] == "RESEARCH_ONLY_DISABLED"
    assert receipt["default_enabled"] is False
    assert receipt["network_calls"] is False
    assert receipt["key_or_environment_reads"] is False
    assert receipt["private_api_calls"] is False
    assert receipt["broker_calls"] is False and receipt["executable"] is False
    with pytest.raises(CashCarryShadowError, match="frozen public Bybit"):
        runner._get_json("https://example.com/v5/market/tickers?category=linear")


def test_observation_contract_rejects_future_funding_and_crossed_books() -> None:
    ts = 1_700_000_000_000
    with pytest.raises(CashCarryShadowError, match="future funding"):
        _obs(ts, funding=(_settlement(ts + 1),))
    with pytest.raises(CashCarryShadowError, match="crossed"):
        _obs(ts, spot_bid=100.1, spot_ask=100.0)


def test_conflicting_rate_for_same_exchange_settlement_fails_closed() -> None:
    engine = CashCarryShadowEngine(ShadowConfig(enabled=True))
    ts = 1_700_000_000_000
    assert engine.step(_obs(ts, funding=(_settlement(ts, rate=0.0001),))).action == "observe"
    conflicting = engine.step(
        _obs(
            ts + 1_000,
            funding=(FundingSettlement(ts, 0.0002, 100.2),),
            spot_ts=ts + 1_000,
            perp_ts=ts + 1_000,
        )
    )
    assert conflicting.action == "refuse"
    assert conflicting.reason == "funding_settlement_conflict"
    assert engine.positive_funding_count == 1


def test_three_positive_settlements_must_be_recent_and_not_sparse() -> None:
    engine = CashCarryShadowEngine(
        ShadowConfig(enabled=True, max_funding_persistence_span_ms=3 * 28_800_000)
    )
    base = 1_700_000_000_000
    result = None
    for index in range(3):
        ts = base + index * 2 * 28_800_000
        result = engine.step(_obs(ts, funding=(_settlement(ts),)))
    assert result is not None
    assert result.action == "observe"
    assert result.reason == "completed_funding_persistence_is_too_sparse"
    assert engine.position_open is False
