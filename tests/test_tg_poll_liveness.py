"""Extract only the command coroutine: never import/start the trading monolith."""
import ast
import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).parents[1] / 'smart_pump_reversal_bot.py'


def load_loop(get, sleep, handler=lambda _: None):
    tree = ast.parse(SOURCE.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'tg_cmd_loop')
    ns = {'asyncio': SimpleNamespace(to_thread=asyncio.to_thread, sleep=sleep),
          'requests': SimpleNamespace(get=get), 'TG_TOKEN': 'fixture', 'TG_CHAT': '7',
          'TG_COMMANDS_ENABLE': True, 'TG_ADMIN_USER_ID': '9', 'BUTTON_MAP': {},
          '_handle_tg_command': handler, '_handle_tg_photo_message': lambda _: None,
          'log_error': lambda _: None}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), ns)
    return ns['tg_cmd_loop']


def test_poll_preserves_serial_offsets_filters_and_main_thread_handlers():
    calls, handled, sleeps = [], [], []
    main = threading.get_ident()
    def update(id, chat, admin, text):
        return {'update_id': id, 'message': {'chat': {'id': chat}, 'from': {'id': admin}, 'text': text}}
    def get(url, **kw):
        assert threading.get_ident() != main
        assert kw['timeout'] == 25 and url.endswith('/getUpdates')
        calls.append(dict(kw['params']))
        rows = [update(1,'7','9','/ok'),update(2,'8','9','/foreign'),update(3,'7','8','/unauthorized')] if len(calls)==1 else []
        return SimpleNamespace(json=lambda: {'result': rows})
    def handle(text):
        assert threading.get_ident() == main
        handled.append(text)
    async def sleep(seconds):
        assert seconds == 1
        sleeps.append(seconds)
        if len(sleeps)==2: raise asyncio.CancelledError
        await asyncio.sleep(0)
    async def run():
        try: await load_loop(get, sleep, handle)()
        except asyncio.CancelledError: pass
    asyncio.run(run())
    assert calls == [{'timeout':20}, {'timeout':20,'offset':4}]
    assert handled == ['/ok']


def test_heartbeat_runs_while_long_poll_is_still_blocked():
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    def get(*args, **kwargs):
        started.set()
        release.wait(timeout=1)
        finished.set()
        return SimpleNamespace(json=lambda: {'result': []})
    async def run():
        task = asyncio.create_task(load_loop(get, asyncio.sleep)())
        try:
            for _ in range(100):
                await asyncio.sleep(.001)
                if started.is_set(): break
            assert started.is_set()
            # A heartbeat can run before network completion, not just after it.
            assert not finished.is_set(), 'long poll blocked the event loop'
        finally:
            release.set()
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
    asyncio.run(run())
    assert finished.is_set()
