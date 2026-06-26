from strategies.inplay_breakout import InPlayBreakoutWrapper


class _Store:
    symbol = "TESTUSDT"

    def fetch_klines(self, symbol, interval, limit):
        _ = (symbol, interval, limit)
        return []


def test_wrapper_rebuilds_cached_engine_when_config_changes():
    wrapper = InPlayBreakoutWrapper(env_prefix="TESTBREAKOUT")
    store = _Store()

    wrapper._ensure_impl(store)
    first = wrapper.impl
    assert first is not None

    wrapper.cfg.rr = float(wrapper.cfg.rr) + 0.5
    wrapper._ensure_impl(store)

    assert wrapper.impl is not None
    assert wrapper.impl is not first


def test_wrapper_refreshes_env_config_before_engine_creation(monkeypatch):
    wrapper = InPlayBreakoutWrapper(env_prefix="TESTBREAKOUTENV")
    store = _Store()

    monkeypatch.setenv("TESTBREAKOUTENV_RR", "2.7")
    wrapper._ensure_impl(store)

    assert wrapper.cfg.rr == 2.7
