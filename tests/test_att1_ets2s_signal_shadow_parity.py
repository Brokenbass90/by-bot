from __future__ import annotations

from pathlib import Path

import pytest

from research_lab.att1_ets2s_signal_shadow_parity import (
    DEFAULT_FIXTURE_ROOT,
    compare_records,
    run_fixture_parity,
)
from strategies.elder_live import (
    ETS2S_LIVE_WRAPPER_ENABLED_BY_DEFAULT,
    ElderShadowEngine,
)
from strategies.signals import TradeSignal


class _RaisingStrategy:
    def maybe_signal(self, *_args, **_kwargs):
        raise RuntimeError("visible-elder-boundary-failure")


def test_elder_shadow_wrapper_is_broker_free_and_does_not_swallow_exceptions() -> None:
    assert ETS2S_LIVE_WRAPPER_ENABLED_BY_DEFAULT is False
    engine = ElderShadowEngine(lambda *_args: [])
    engine._strategies["BTCUSDT"] = _RaisingStrategy()

    with pytest.raises(RuntimeError, match="visible-elder-boundary-failure"):
        engine.signal("BTCUSDT", 1, 1, 1, 1, 1)


def test_elder_shadow_wrapper_applies_frozen_effective_geometry() -> None:
    raw = TradeSignal(
        strategy="elder_triple_screen_v2",
        symbol="BTCUSDT",
        side="short",
        entry=100.0,
        sl=102.0,
        tp=94.0,
        tps=[97.0, 94.0],
        tp_fracs=[0.5, 0.5],
        time_stop_bars=288,
    )

    class _FixedStrategy:
        last_no_signal_reason = ""

        def maybe_signal(self, *_args, **_kwargs):
            return raw

    engine = ElderShadowEngine(lambda *_args: [])
    engine._strategies["BTCUSDT"] = _FixedStrategy()
    signal = engine.signal("BTCUSDT", 1, 1, 1, 1, 1)

    assert signal is not None
    assert signal.sl == 108.0
    assert signal.tps == [97.0, 94.0]
    assert signal.time_stop_bars == 4032


def test_comparator_treats_silence_and_exceptions_as_decisions() -> None:
    base = {
        "schema_id": "att1_ets2s_signal_shadow_parity_v1",
        "sleeve_id": "ATT1",
        "symbol": "BTCUSDT",
        "bar_ts": 1,
        "side": None,
        "entry": None,
        "sl": None,
        "tps": None,
        "tp_fracs": None,
        "time_stop_hours": 336,
        "entry_type": "market",
        "entry_offset": 0.0,
        "entry_wait_bars": 0,
        "stop_transform_id": "native_strategy_geometry_v1",
        "config_hash": "a" * 64,
        "source_hash": "b" * 64,
        "data_hash": "c" * 64,
        "exception": None,
    }

    assert compare_records([base], [dict(base)])["verdict"] == "PASS"
    broken = dict(base, exception="RuntimeError: broken")
    result = compare_records([base], [broken])
    assert result["verdict"] == "FAIL"
    assert result["mismatches_by_field"] == {"exception": 1}

    signalled = dict(base, side="short", entry=100.0, sl=106.0, tps=[95.0])
    shifted_stop = dict(signalled, sl=106.01)
    result = compare_records([signalled], [shifted_stop])
    assert result["verdict"] == "FAIL"
    assert result["mismatches_by_field"] == {"sl": 1}


@pytest.mark.slow
def test_frozen_fixture_has_automatic_att1_and_ets2s_parity() -> None:
    assert Path(DEFAULT_FIXTURE_ROOT).is_dir()
    result = run_fixture_parity(Path(DEFAULT_FIXTURE_ROOT), decision_bars=300)

    assert result["overall_verdict"] == "PASS"
    assert result["sleeves"]["ATT1"]["verdict"] == "PASS"
    assert result["sleeves"]["ETS2S"]["verdict"] == "PASS"
    assert result["sleeves"]["ATT1"]["decision_rows"] == 600
    assert result["sleeves"]["ETS2S"]["decision_rows"] == 600
    assert result["sleeves"]["ATT1"]["signals"] > 0
    assert result["sleeves"]["ETS2S"]["signals"] > 0
