#!/usr/bin/env python3
"""Archive Bybit public liquidation events for offline edge research.

This is read-only infrastructure for `backtest/liquidation_sweep_research.py`.
It connects to Bybit's public linear WebSocket `allLiquidation.{symbol}` topics
and appends normalized jsonl events:

    {"ts_ms": ..., "symbol": "BTCUSDT", "side": "long", "usd": 12345.67, ...}

Side convention matches the research engine:
  * side="long"  means long positions were liquidated (forced sell)
  * side="short" means short positions were liquidated (forced buy)

No API keys, no orders, no writes outside the requested output file.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import websockets

DEFAULT_WS_URL = "wss://stream.bybit.com/v5/public/linear"
DEFAULT_SYMBOLS = (
    "BTCUSDT,ETHUSDT,SOLUSDT,SUIUSDT,DOGEUSDT,LINKUSDT,LTCUSDT,"
    "ADAUSDT,BNBUSDT,AVAXUSDT,XRPUSDT,NEARUSDT"
)


def _f(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    return x if math.isfinite(x) else default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def normalize_liquidation(raw: Dict[str, Any], *, topic_symbol: str = "", recv_ts_ms: int = 0) -> Optional[Dict[str, Any]]:
    """Normalize one Bybit allLiquidation data item.

    Bybit reports the liquidation order side as `S`: Sell means forced selling
    from long liquidations; Buy means forced buying from short liquidations.
    """
    symbol = str(raw.get("s") or raw.get("symbol") or topic_symbol or "").upper()
    order_side = str(raw.get("S") or raw.get("side") or "").lower()
    qty = _f(raw.get("v", raw.get("qty")))
    price = _f(raw.get("p", raw.get("price")))
    ts_ms = _i(raw.get("T", raw.get("ts_ms")), default=recv_ts_ms)
    if not symbol or order_side not in {"buy", "sell"} or qty <= 0 or price <= 0 or ts_ms <= 0:
        return None
    liquidated_side = "long" if order_side == "sell" else "short"
    return {
        "ts_ms": ts_ms,
        "symbol": symbol,
        "side": liquidated_side,
        "usd": round(qty * price, 8),
        "qty": qty,
        "price": price,
        "order_side": "Sell" if order_side == "sell" else "Buy",
        "recv_ts_ms": recv_ts_ms,
    }


def normalize_ws_message(message: Dict[str, Any], *, recv_ts_ms: Optional[int] = None) -> List[Dict[str, Any]]:
    topic = str(message.get("topic") or "")
    topic_symbol = topic.split(".")[-1].upper() if "." in topic else ""
    recv = int(recv_ts_ms or message.get("ts") or time.time() * 1000)
    data = message.get("data") or []
    if isinstance(data, dict):
        data = [data]
    out: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        ev = normalize_liquidation(item, topic_symbol=topic_symbol, recv_ts_ms=recv)
        if ev is not None:
            out.append(ev)
    return out


def _chunks(items: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


async def collect(args: argparse.Namespace) -> None:
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        raise SystemExit("no symbols")
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    topics = [f"allLiquidation.{s}" for s in symbols]
    stop_at = time.time() + float(args.duration_sec) if args.duration_sec > 0 else 0.0

    while True:
        if stop_at and time.time() >= stop_at:
            return
        try:
            async with websockets.connect(args.ws_url, ping_interval=args.ping_interval_sec, ping_timeout=20) as ws:
                for chunk in _chunks(topics, max(1, int(args.chunk_size))):
                    await ws.send(json.dumps({"op": "subscribe", "args": chunk}))
                    await asyncio.sleep(0.1)
                print(f"subscribed symbols={len(symbols)} out={out_path}", flush=True)
                with out_path.open("a", encoding="utf-8") as f:
                    while True:
                        if stop_at and time.time() >= stop_at:
                            return
                        raw = await asyncio.wait_for(ws.recv(), timeout=args.idle_timeout_sec)
                        recv_ts_ms = int(time.time() * 1000)
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        events = normalize_ws_message(msg, recv_ts_ms=recv_ts_ms)
                        for ev in events:
                            if ev["usd"] < args.min_usd:
                                continue
                            f.write(json.dumps(ev, separators=(",", ":"), sort_keys=True) + "\n")
                        if events:
                            f.flush()
        except asyncio.TimeoutError:
            print("idle timeout; reconnecting", flush=True)
        except Exception as exc:
            print(f"collector error: {exc}; reconnecting in {args.reconnect_sleep_sec}s", flush=True)
            await asyncio.sleep(args.reconnect_sleep_sec)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Archive Bybit public allLiquidation events to jsonl")
    p.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    p.add_argument("--out", default="runtime/liquidations/bybit_liquidations.jsonl")
    p.add_argument("--ws-url", default=DEFAULT_WS_URL)
    p.add_argument("--duration-sec", type=float, default=0.0, help="0 = run forever")
    p.add_argument("--min-usd", type=float, default=0.0)
    p.add_argument("--chunk-size", type=int, default=10)
    p.add_argument("--ping-interval-sec", type=float, default=20.0)
    p.add_argument("--idle-timeout-sec", type=float, default=120.0)
    p.add_argument("--reconnect-sleep-sec", type=float, default=5.0)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    asyncio.run(collect(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
