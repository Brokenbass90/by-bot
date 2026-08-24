from __future__ import annotations

import pytest

from strategies.att1_live import ATT1LiveEngine
from strategies.sbr1_live import (
    SBR1_LIVE_WRAPPER_ENABLED_BY_DEFAULT,
    SBR1LiveEngine,
)


class _RaisingStrategy:
    def maybe_signal(self, *_args, **_kwargs):
        raise RuntimeError("visible-boundary-failure")


def test_att1_wrapper_does_not_swallow_strategy_exceptions() -> None:
    engine = ATT1LiveEngine(lambda *_args: [])
    engine._strategies["BTCUSDT"] = _RaisingStrategy()
    with pytest.raises(RuntimeError, match="visible-boundary-failure"):
        engine.signal("BTCUSDT", 1, 1, 1, 1, 1)


def test_sbr1_wrapper_is_default_off_and_does_not_swallow_exceptions() -> None:
    assert SBR1_LIVE_WRAPPER_ENABLED_BY_DEFAULT is False
    engine = SBR1LiveEngine(lambda *_args: [])
    engine._strategies["BTCUSDT"] = _RaisingStrategy()
    with pytest.raises(RuntimeError, match="visible-boundary-failure"):
        engine.signal("BTCUSDT", 1, 1, 1, 1, 1)


def test_wrappers_expose_the_rows_consumed_by_the_strategy() -> None:
    rows = [[1_700_000_000_000, "1", "2", "0.5", "1.5", "10"]]

    class _NoSignal:
        _last_no_signal_reason = "no_setup"

        def maybe_signal(self, store, *_args, **_kwargs):
            store.fetch_klines(store.symbol, "60", 1)
            return None

    att1 = ATT1LiveEngine(lambda *_args: rows)
    att1._strategies["BTCUSDT"] = _NoSignal()
    assert att1.signal("BTCUSDT", 1, 1, 2, 0.5, 1.5) is None
    assert att1.last_closed_rows("BTCUSDT") == rows

    sbr1 = SBR1LiveEngine(lambda *_args: rows)
    sbr1._strategies["BTCUSDT"] = _NoSignal()
    assert sbr1.signal("BTCUSDT", 1, 1, 2, 0.5, 1.5) is None
    assert sbr1.last_closed_rows("BTCUSDT") == rows
