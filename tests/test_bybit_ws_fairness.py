"""Buffered production receive loop must leave time for heartbeat/management."""
import ast
import asyncio
from collections import deque
import json
from pathlib import Path
from types import SimpleNamespace


def test_buffered_trade_messages_preserve_processing_and_allow_heartbeat():
    tree = ast.parse(Path('smart_pump_reversal_bot.py').read_text())
    outer = next(n for n in tree.body if getattr(n, 'name', '') == 'bybit_ws')
    worker = next(n for n in ast.walk(outer) if isinstance(n, ast.AsyncFunctionDef) and n.name == 'run_one')
    processed, heartbeats = [], []

    class EndTape(BaseException):
        pass

    class Socket:
        def __init__(self):
            self.i = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def send(self, _):
            pass

        async def recv(self):
            # Like websockets with buffered messages: await does not suspend.
            if self.i == 40:
                raise EndTape()
            self.i += 1
            return json.dumps({'topic': 'publicTrade.ETHUSDT', 'data': [
                {'T': self.i * 1000, 'p': str(self.i), 'v': '1', 'S': 'Buy'}]})

    state = SimpleNamespace(**{k: deque() for k in ('trades', 'prices', 'closes', 'highs', 'lows', 'ctx5m')}, ema_fast=0, ema_slow=0)
    ns = dict(asyncio=asyncio, List=list, random=SimpleNamespace(uniform=lambda *_: 0),
              websockets=SimpleNamespace(connect=lambda *_a, **_kw: Socket()),
              url="fixture://offline", WS_RECONNECT_MIN=1, WS_RECONNECT_MAX=2, WS_RECONNECT_JITTER=0,
              START_STAGGER=0, WS_PING_INTERVAL=20, WS_PING_TIMEOUT=60,
              WS_OPEN_TIMEOUT=60, WS_CLOSE_TIMEOUT=10, BATCH_SIZE=6, BATCH_DELAY=0,
              MSG_COUNTER={}, json=json, _bybit_sym_re=__import__('re').compile(r'publicTrade\.(.+)'),
              S=lambda *_: state, now_s=lambda: 123, EMA_FAST=2, EMA_SLOW=3,
              ema_val=lambda _old, p, _period: p, trim=lambda *_: None,
              detect=lambda exch, sym, st, ts: processed.append((sym, st.closes[-1], ts)),
              _diag_inc=lambda *_: None, log_error=lambda *_: None,
              InvalidStatus=type('InvalidStatus', (Exception,), {}),
              ConnectionClosedError=type('ConnectionClosedError', (Exception,), {}),
              ConnectionClosedOK=type('ConnectionClosedOK', (Exception,), {}))
    exec(compile(ast.Module(body=[worker], type_ignores=[]), '<production-receive-loop>', 'exec'), ns)

    async def run():
        async def heartbeat():
            while True:
                heartbeats.append(len(processed))
                await asyncio.sleep(0)
        hb = asyncio.create_task(heartbeat())
        try:
            await ns['run_one'](['publicTrade.ETHUSDT'], 0)
        except EndTape:
            pass
        finally:
            hb.cancel()
            await asyncio.gather(hb, return_exceptions=True)

    asyncio.run(run())
    assert processed == [('ETHUSDT', float(i), 123) for i in range(1, 41)]
    assert any(0 < n < 40 for n in heartbeats), 'buffered receive starved heartbeat until tape ended'
