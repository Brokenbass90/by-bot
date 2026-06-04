from strategies.gs1_live import GS1LiveEngine
from strategies.pfs1_live import PFS1LiveEngine


class _RaisingStrategy:
    last_no_signal_reason = ""

    def maybe_signal(self, *args, **kwargs):
        raise RuntimeError("boom")


class _NoSignalStrategy:
    last_no_signal_reason = "quality_gate"

    def maybe_signal(self, *args, **kwargs):
        return None


def _assert_exception_is_visible(engine):
    symbol = "BTCUSDT"
    engine._strategies[symbol] = _RaisingStrategy()

    assert engine.signal(symbol, 1, 1.0, 1.0, 1.0, 1.0) is None
    assert engine.last_no_signal_reason(symbol) == "engine_error:RuntimeError"
    assert engine.last_error(symbol) == "engine_error:RuntimeError"

    engine._strategies[symbol] = _NoSignalStrategy()
    assert engine.signal(symbol, 2, 1.0, 1.0, 1.0, 1.0) is None
    assert engine.last_no_signal_reason(symbol) == "quality_gate"
    assert engine.last_error(symbol) == ""


def test_pfs1_live_wrapper_exposes_engine_errors():
    _assert_exception_is_visible(PFS1LiveEngine(lambda *args, **kwargs: []))


def test_gs1_live_wrapper_exposes_engine_errors():
    _assert_exception_is_visible(GS1LiveEngine(lambda *args, **kwargs: []))
