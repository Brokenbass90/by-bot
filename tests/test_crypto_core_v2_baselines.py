from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import strategies.event_expansion_retest_long_v1 as event_mod
from strategies.alt_support_bounce_v1 import AltSupportBounceV1Strategy
from research_lab.crypto_core_v2_baselines import (
    BASELINE_SOURCE_PINS,
    CryptoCoreV2Adapter,
    adapt_alt_support_bounce,
    adapt_event_expansion_retest,
    CostAssumptions,
)


def test_source_pins_match_frozen_research_ref_blobs() -> None:
    assert BASELINE_SOURCE_PINS == {
        "event_expansion_retest_long_v1": "e50c4f1a0610c03e6ed79a9bc06023f14a12dcfa",
        "alt_support_bounce_v1": "b8fcdca3974161ddc1804384fd1dd5bb28168857",
    }


def test_local_baseline_sources_have_git_blob_parity() -> None:
    root = Path(__file__).parents[1]
    for relative, expected in (
        ("strategies/event_expansion_retest_long_v1.py", BASELINE_SOURCE_PINS["event_expansion_retest_long_v1"]),
        ("strategies/alt_support_bounce_v1.py", BASELINE_SOURCE_PINS["alt_support_bounce_v1"]),
    ):
        payload = (root / relative).read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()
        assert actual == expected


def test_event_adapter_preserves_native_rejection_and_closed_availability() -> None:
    cfg = event_mod.ExpansionRetestLongConfig()
    rows = [[i * cfg.interval_ms, 100.0, 101.0, 99.0, 100.0, 100.0] for i in range(4)]
    expected = event_mod.EventExpansionRetestLongV1Research(cfg).process_closed_rows(
        "TESTUSDT", rows, []
    )
    record = adapt_event_expansion_retest(
        "TESTUSDT", rows, [], cfg=cfg, as_of_ms=rows[-1][0] + cfg.interval_ms
    )
    assert record.decision == "rejected"
    assert record.side == "long"
    assert json.loads(record.data)["reason"] == expected.reason
    assert record.native_sha256
    assert record.reason == expected.reason == "no_expansion_event"
    assert record.availability.status == "CLOSED_BAR_CONFIRMED"
    assert record.costs.status == "UNKNOWN_BLOCKED"


def test_event_adapter_blocks_future_or_incomplete_input_without_reinterpreting_it() -> None:
    cfg = event_mod.ExpansionRetestLongConfig()
    rows = [[i * cfg.interval_ms, 100.0, 101.0, 99.0, 100.0, 100.0] for i in range(4)]
    record = adapt_event_expansion_retest(
        "TESTUSDT", rows, [], cfg=cfg, as_of_ms=rows[-1][0] + cfg.interval_ms - 1
    )
    assert record.decision == "blocked"
    assert record.side == "long"
    assert record.data == "null"
    assert record.reason == "BLOCKED_DATA:closed_bar_availability_unknown"
    assert record.availability.status == "BLOCKED_DATA"


def test_event_adapter_reuses_original_state_for_full_lifecycle_and_duplicate() -> None:
    fixture = __import__("tests.test_event_expansion_retest_long_v1", fromlist=["_advance_to_plan"])
    cfg, rows, expected_state, expected_plan, expected_reason = fixture._advance_to_plan()
    runner = event_mod.EventExpansionRetestLongV1Research(cfg)
    snapshots = [fixture._snapshot()]
    observed = []
    for index in range(50, len(rows) + 1):
        record = adapt_event_expansion_retest(
            "TESTUSDT", rows[:index], snapshots, cfg=cfg,
            as_of_ms=rows[index - 1][0] + cfg.interval_ms, research=runner,
        )
        observed.append(record)
    assert observed[-1].decision == "accepted"
    final_payload = json.loads(observed[-1].data)
    assert final_payload["plan"]["side"] == expected_plan.side
    assert final_payload["state"]["active"]["stage"] == expected_state.stage.value
    assert final_payload["state"]["active"]["last_processed_ts"] == expected_state.last_processed_ts
    duplicate = adapt_event_expansion_retest(
        "TESTUSDT", rows, snapshots, cfg=cfg,
        as_of_ms=rows[-1][0] + cfg.interval_ms, research=runner,
    )
    assert duplicate.decision == "rejected"
    assert duplicate.reason == "terminal:plan_emitted"
    assert duplicate.config_sha256 == observed[-1].config_sha256


@dataclass
class _Store:
    symbol: str = "TESTUSDT"

    def fetch_klines(self, symbol: str, timeframe: str, limit: int):
        return []


def test_bounce_adapter_preserves_native_rejection_and_side() -> None:
    strategy = AltSupportBounceV1Strategy()
    store = _Store()
    expected = strategy.maybe_signal(store, 123, 100.0, 101.0, 99.0, 100.0, 10.0)
    record = adapt_alt_support_bounce(
        strategy, store, 123, 100.0, 101.0, 99.0, 100.0, 10.0,
        as_of_ms=14_400_123,
        source_rows={"1h": [[0, 1, 2, 0.5, 1, 1]], "4h": [[0, 1, 2, 0.5, 1, 1]]},
    )
    assert record.decision == "rejected"
    assert record.side == "long"
    assert record.data == "null"
    assert record.reason == "regime_not_bullish"
    assert record.availability.status == "CLOSED_BAR_CONFIRMED"


def test_bounce_adapter_blocks_unknown_closed_bar_and_keeps_native_strategy_uninvoked() -> None:
    strategy = AltSupportBounceV1Strategy()
    store = _Store()
    record = adapt_alt_support_bounce(
        strategy, store, 123, 100.0, 101.0, 99.0, 100.0, 10.0,
        as_of_ms=123,
        source_rows=None,
    )
    assert record.decision == "blocked"
    assert record.side == "long"
    assert record.data == "null"
    assert record.reason == "BLOCKED_DATA:closed_bar_availability_unknown"


def test_bounce_truthy_legacy_flag_cannot_claim_closed_data() -> None:
    record = adapt_alt_support_bounce(
        AltSupportBounceV1Strategy(), _Store(), 123, 100.0, 101.0, 99.0, 100.0, 10.0,
        closed_bar_available=True, as_of_ms=123, source_rows=None,
    )
    assert record.decision == "blocked"
    assert record.availability.status == "BLOCKED_DATA"


def test_cost_assumptions_validate_explicit_values() -> None:
    assert CostAssumptions(status="CONFIRMED", fee_bps=1.0, slippage_bps=2.0, funding_bps=0.0,
                           unknowns=(), source_sha256="a"*64).status == "CONFIRMED"
    try:
        CostAssumptions(status="CONFIRMED", fee_bps=-1.0)
    except ValueError as exc:
        assert str(exc) == "cost assumptions must be finite and non-negative"
    else:
        raise AssertionError("negative cost was accepted")


def test_adapter_facade_routes_only_the_two_frozen_families() -> None:
    assert isinstance(CryptoCoreV2Adapter("event_expansion_retest_long_v1"), CryptoCoreV2Adapter)
    try:
        CryptoCoreV2Adapter("elder_crypto_v1")
    except ValueError as exc:
        assert str(exc) == "unsupported crypto baseline family"
    else:
        raise AssertionError("unsupported family was accepted")

import pytest

def test_bounce_consumes_only_the_exact_validated_source_rows():
    class EvilStore(_Store):
        def fetch_klines(self,*_):pytest.fail('unvalidated backing source must not be read')
    strategy=AltSupportBounceV1Strategy()
    r=adapt_alt_support_bounce(strategy,EvilStore(),123,100,101,99,100,10,as_of_ms=14_400_123,
           source_rows={'1h':[[0,1,2,.5,1,1]],'4h':[[0,1,2,.5,1,1]]})
    assert r.reason=='regime_not_bullish'
    assert r.availability.as_of_ms==14_400_123 and r.config_sha256

@pytest.mark.parametrize('inputs',[{}, {'fee_bps':1}, {'fee_bps':1,'slippage_bps':2}])
def test_incomplete_costs_cannot_claim_confirmed(inputs):
    with pytest.raises(ValueError):CostAssumptions(status='CONFIRMED',**inputs)

def test_confirmed_costs_need_resolved_unknowns_and_source_pin():
    with pytest.raises(ValueError):CostAssumptions(status='CONFIRMED',fee_bps=1,slippage_bps=2,funding_bps=0)
    r=CostAssumptions(status='CONFIRMED',fee_bps=1,slippage_bps=2,funding_bps=0,unknowns=(),source_sha256='a'*64)
    assert r.status=='CONFIRMED' and r.unknowns==()


def test_bounce_default_baseline_acceptance_and_cooldown_have_exact_native_parity(monkeypatch):
    from dataclasses import asdict
    import os
    for key in list(os.environ):
        if key.startswith(('BOUNCE1_', 'ASB1_')):monkeypatch.delenv(key)
    closes=[105+.2*(i%2) for i in range(58)]+[104,104.4,103.5,103.9,103,103.4,
        102.5,102.9,102,102.4,101.5,101.9,101,100.4,100.8]
    rows=[[(168+i)*3_600_000,c-.2,c+.5,c-.5,c,100] for i,c in enumerate(closes)]
    rows[2][2]=110;rows[10][3]=100;rows[-2][3]=100
    rows[-1]=[240*3_600_000,100.3,101,99.9,100.8,100]
    regime=[[i*14_400_000,100,101,99,100,100] for i in range(60)]
    class Store:
        symbol='TESTUSDT'
        def __init__(self):self.rows=rows[:-1]
        def fetch_klines(self,symbol,timeframe,limit):
            return (regime if timeframe=='240' else self.rows)[-limit:]
    store=Store();native=AltSupportBounceV1Strategy();wrapped=AltSupportBounceV1Strategy()
    for values,expected_reason in [(rows[:-1],'first_signal_bar'),(rows,'signal_emitted'),(rows,'cooldown')]:
        store.rows=values;now=values[-1][0]+3_600_000
        expected=native.maybe_signal(store,values[-1][0],0,0,0,0)
        actual=adapt_alt_support_bounce(wrapped,store,values[-1][0],0,0,0,0,
            as_of_ms=now,source_rows={'1h':values,'4h':regime})
        assert actual.native_copy()==(asdict(expected) if expected else None)
        assert actual.reason==expected_reason and actual.config_sha256
