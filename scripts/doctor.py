#!/usr/bin/env python3
import os, sys, platform
import asyncio
import inspect

def main():
    print('Python:', sys.version)
    print('Executable:', sys.executable)
    print('CWD:', os.getcwd())
    print('Platform:', platform.platform())
    try:
        import backtest
        import backtest.run_month
        import backtest.engine
        print('backtest.__file__:', backtest.__file__)
        print('run_month.__file__:', backtest.run_month.__file__)
        print('engine.__file__:', backtest.engine.__file__)
        print('OK: imports resolved')

        # ------------------
        # Lightweight smoke tests
        # ------------------
        # The goal is to catch common wiring errors (wrong constructor args,
        # missing methods, wrong store integration) before you run a full
        # month backtest.
        import asyncio
        import random
        from backtest.engine import Candle, KlineStore
        from strategies.bounce_bt import BounceBTConfig, BounceBTStrategy
        from strategies.pump_fade import PumpFadeConfig, PumpFadeStrategy
        from strategies.range_wrapper import RangeWrapperConfig, RangeBacktestStrategy
        from strategies.inplay_wrapper import InPlayWrapper, InPlayWrapperConfig

        def _make_dummy_store(symbol: str = 'TESTUSDT', n_5m: int = 1000) -> KlineStore:
            # 1000x 5m candles ~ 83 hours, enough for 1h resampling and ATR.
            ts0 = 1700000000000
            price = 100.0
            candles = []
            for i in range(n_5m):
                # small random walk
                price *= (1.0 + random.uniform(-0.001, 0.001))
                o = price
                h = o * (1.0 + random.uniform(0.0, 0.001))
                l = o * (1.0 - random.uniform(0.0, 0.001))
                c = price * (1.0 + random.uniform(-0.0005, 0.0005))
                v = random.uniform(10.0, 100.0)
                candles.append(Candle(ts=ts0 + i * 5 * 60 * 1000, o=o, h=h, l=l, c=c, v=v))
                price = c
            return KlineStore(symbol=symbol, candles_5m=candles)

        store = _make_dummy_store()
        store.set_index(len(store.c5) - 1)
        last_bar = store.c5[-1]

        def _call_maybe(fn, *args, **kwargs):
            """Run a maybe_signal that can be sync or async."""
            if inspect.iscoroutinefunction(fn):
                return asyncio.run(fn(*args, **kwargs))
            out = fn(*args, **kwargs)
            # In case a sync wrapper returns a coroutine.
            if inspect.iscoroutine(out):
                return asyncio.run(out)
            return out

        # Bounce (store-driven) should run without exceptions.
        bounce = BounceBTStrategy(BounceBTConfig())
        _call_maybe(bounce.maybe_signal, store, last_bar.ts, last_bar.c)

        # Pump-fade should run without exceptions.
        pf = PumpFadeStrategy(PumpFadeConfig())
        _call_maybe(
            pf.maybe_signal,
            "TESTUSDT",
            last_bar.ts,
            last_bar.o,
            last_bar.h,
            last_bar.l,
            last_bar.c,
            last_bar.v,
        )

        # Range strategy: verify it can call through using store.fetch_klines.
        r = RangeBacktestStrategy(RangeWrapperConfig())
        _call_maybe(r.maybe_signal, store, last_bar.ts, last_bar.c)

        # In-play wrapper: constructor + cheap call smoke (should not raise).
        ip = InPlayWrapper(InPlayWrapperConfig())
        assert hasattr(ip, "_coerce_price"), "InPlayWrapper missing _coerce_price"
        assert hasattr(ip, "_coerce_ts"), "InPlayWrapper missing _coerce_ts"
        _call_maybe(ip.maybe_signal, store, last_bar.ts, last_bar.c)

        print('OK: smoke tests passed')
    except Exception as e:
        print('IMPORT ERROR:', repr(e))
        raise

if __name__ == '__main__':
    main()
