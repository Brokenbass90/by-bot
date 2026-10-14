#!/usr/bin/env python3
"""Separate Bybit public source V2. Only sends subscribe and public ping.

No credentials/environment files/order transport. Never writes the V1 directory.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bot.bybit_liquidation_collector_v2 import CaptureStopped, ENDPOINT, Journal, MAX_WIRE_BYTES

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "SUIUSDT", "DOGEUSDT", "LINKUSDT",
           "LTCUSDT", "ADAUSDT", "BNBUSDT", "AVAXUSDT", "XRPUSDT", "NEARUSDT")


def now(): return time.time_ns() // 1000000


def notify(value):
    """Notify systemd after the durable heartbeat; no trade/runtime authority."""
    address = os.environ.get("NOTIFY_SOCKET")
    if not address: return
    if address.startswith("@"): address = "\0" + address[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(address); sock.sendall(value.encode())
    except OSError:
        # A broken watchdog channel is observable by systemd's missed deadline.
        pass


def source_pins():
    files = ("bot/__init__.py", "bot/bybit_liquidation_source_v2.py",
             "bot/bybit_liquidation_collector_v2.py", "scripts/collect_bybit_liquidations_v2.py",
             "deploy/bybit-liquidation-source-v2.service")
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}


async def run(root, symbols, pins, *, connector=None, duration_sec=0, tick_sec=5,
              min_free_bytes=1024**3, max_capture_bytes=4 * 1024**3):
    if not math.isfinite(duration_sec) or duration_sec < 0 or not 0 < tick_sec <= 5:
        raise CaptureStopped("INVALID_TIME_CONFIGURATION")
    if connector is None:
        import websockets
        connector = websockets.connect
    stop = asyncio.Event(); loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    deadline = time.monotonic() + duration_sec if duration_sec else None
    def ended(): return stop.is_set() or (deadline is not None and time.monotonic() >= deadline)
    try:
        with Journal(root, symbols, pins, min_free_bytes=min_free_bytes,
                     max_capture_bytes=max_capture_bytes) as journal:
            notify("READY=1\nSTATUS=Public liquidation V2 source journal ready")
            def beat(status=None):
                journal.check_storage(); journal.heartbeat(now(), status)
                notify("WATCHDOG=1")
            async def backoff(seconds):
                until = time.monotonic() + seconds
                while not ended() and time.monotonic() < until:
                    beat()
                    await asyncio.sleep(min(tick_sec, max(0, until - time.monotonic())))
            connection_number = 0
            try:
                while not ended():
                    beat("CONNECTING")
                    try:
                        async with connector(ENDPOINT, open_timeout=10, close_timeout=5,
                                             ping_interval=None, max_size=MAX_WIRE_BYTES,
                                             max_queue=16) as ws:
                            connection_number += 1
                            connection_id = f"{journal.run_id}:{connection_number}"
                            request_id = "liq-v2-" + str(connection_number)
                            journal.connected(connection_id, request_id, now())
                            await ws.send(json.dumps(dict(op="subscribe", req_id=request_id,
                                args=["allLiquidation." + symbol for symbol in symbols])))
                            connected = last_ping = time.monotonic()
                            while not ended():
                                beat()
                                clock = time.monotonic()
                                if not journal.subscription_confirmed and clock - connected > 15:
                                    raise TimeoutError("subscription_ack_timeout")
                                if journal.subscription_rejected and not journal.subscription_confirmed:
                                    raise ConnectionError("subscription_rejected")
                                if clock - last_ping >= 20:
                                    await ws.send(json.dumps(dict(op="ping", req_id="liq-v2-ping")))
                                    last_ping = clock
                                if clock - connected > 65 and (
                                    journal.last_pong_ms is None or now() - journal.last_pong_ms > 45000):
                                    raise TimeoutError("public_pong_timeout")
                                try:
                                    wire = await asyncio.wait_for(ws.recv(), timeout=tick_sec)
                                except asyncio.TimeoutError:
                                    continue
                                journal.receive(wire, recv_ms=now(), connection_id=connection_id)
                    except CaptureStopped:
                        raise
                    except (OSError, TimeoutError, ConnectionError, EOFError) as exc:
                        journal.disconnected(type(exc).__name__, now()); beat()
                        await backoff(5)
                    except Exception as exc:
                        # websockets exceptions are transport-specific; retain the type, no secret text.
                        journal.disconnected(type(exc).__name__, now()); beat()
                        await backoff(5)
                journal.heartbeat(now(), "STOPPED")
                notify("STOPPING=1\nSTATUS=Public source stopped")
            except (CaptureStopped, OSError) as exc:
                try: journal.heartbeat(now(), "BLOCKED_SOURCE_" + type(exc).__name__)
                except (OSError, CaptureStopped): pass
                raise
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM): loop.remove_signal_handler(sig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path,
        default=Path("/opt/bybot-research/liquidation-source-v2-20261014/runtime"))
    parser.add_argument("--symbols", default=",".join(SYMBOLS))
    parser.add_argument("--duration-sec", type=float, default=0)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        pins = source_pins()
        if args.verify_only:
            print(json.dumps(dict(status="PUBLIC_SOURCE_CODE_VERIFIED_NOT_STARTED",
                                  source_files=pins, orders_allowed=False))); return 0
        symbols = tuple(args.symbols.split(","))
        asyncio.run(run(args.root, symbols, pins, duration_sec=args.duration_sec))
        return 0
    except CaptureStopped as exc:
        print(json.dumps(dict(status="BLOCKED_SOURCE", reason=str(exc), orders_allowed=False)), file=sys.stderr)
        return 73 if str(exc) == "ALREADY_RUNNING" else 78
    except (OSError, ValueError, RecursionError) as exc:
        print(json.dumps(dict(status="BLOCKED_SOURCE", reason=type(exc).__name__, orders_allowed=False)), file=sys.stderr)
        return 78


if __name__ == "__main__": raise SystemExit(main())
