#!/usr/bin/env python3
"""Bybit orderbook DENSITY collector — starts the dataset for the density edge.

Owner vision includes density/liquidity-wall strategies (fade from a large wall,
break of an eaten wall). We have NO orderbook data — this collector closes that
gap the same way collect_bybit_liquidations.py did for liquidations: run it on
the server for weeks, then research on our OWN dataset nobody else has aligned
with our liq/funding/OI stream.

Storage is a compact JSONL of DENSITIES (anomalously large levels), not full
books: {ts_ms, symbol, side, price, size_usd, dist_pct, mult_vs_median}.
A wall is recorded when its size >= min_mult * median level size of that side.
Snapshot cadence per symbol: --emit-every-sec (default 30s) -> ~3k lines/day
for 10 symbols at top50 depth. Pure functions are unit-tested offline.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import websockets  # type: ignore
except Exception:  # pragma: no cover - collector runs on server, tests are offline
    websockets = None


# ── pure, unit-tested core ───────────────────────────────────────────────────

def apply_orderbook_message(book: Dict[str, Dict[float, float]], msg: Dict[str, Any]) -> Optional[str]:
    """Apply one Bybit v5 orderbook message (snapshot|delta) to {bids, asks}.

    Returns the affected symbol or None if the message is not an orderbook one.
    Sizes of 0 delete a level (per Bybit contract)."""
    topic = str(msg.get("topic") or "")
    if not topic.startswith("orderbook."):
        return None
    data = msg.get("data") or {}
    symbol = str(data.get("s") or topic.split(".")[-1] or "").upper()
    if not symbol:
        return None
    if str(msg.get("type") or "").lower() == "snapshot":
        book["bids"] = {}
        book["asks"] = {}
    for side_key, side_name in (("b", "bids"), ("a", "asks")):
        for lvl in data.get(side_key) or []:
            try:
                price, size = float(lvl[0]), float(lvl[1])
            except (TypeError, ValueError, IndexError):
                continue
            if size <= 0:
                book[side_name].pop(price, None)
            else:
                book[side_name][price] = size
    return symbol


def _median(xs: List[float]) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def extract_densities(
    book: Dict[str, Dict[float, float]],
    *,
    symbol: str,
    ts_ms: int,
    min_mult: float = 4.0,
    max_dist_pct: float = 3.0,
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    """Find anomalously large levels (walls) near the mid.

    A density = level with size >= min_mult * median size of its book side,
    within max_dist_pct of mid. Top-N largest per side, USD-sized."""
    bids, asks = book.get("bids") or {}, book.get("asks") or {}
    if not bids or not asks:
        return []
    best_bid, best_ask = max(bids), min(asks)
    mid = 0.5 * (best_bid + best_ask)
    if not (mid > 0 and best_bid < best_ask):
        return []
    out: List[Dict[str, Any]] = []
    for side_name, levels in (("bid", bids), ("ask", asks)):
        med = _median(list(levels.values()))
        if not (med == med and med > 0):
            continue
        walls = []
        for price, size in levels.items():
            dist_pct = abs(price - mid) / mid * 100.0
            if dist_pct > max_dist_pct:
                continue
            mult = size / med
            if mult >= min_mult:
                walls.append({
                    "ts_ms": int(ts_ms), "symbol": symbol, "side": side_name,
                    "price": price, "size_usd": round(size * price, 2),
                    "dist_pct": round(dist_pct, 4), "mult_vs_median": round(mult, 2),
                })
        walls.sort(key=lambda w: -w["size_usd"])
        out.extend(walls[:top_n])
    return out


def _chunks(items: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


# ── collector loop (server-side; mirrors the liquidation collector) ─────────

async def collect(args: argparse.Namespace) -> None:  # pragma: no cover - network loop
    if websockets is None:
        raise SystemExit("websockets module required on the collector host")
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        raise SystemExit("no symbols")
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    topics = [f"orderbook.{args.depth}.{s}" for s in symbols]
    books: Dict[str, Dict[str, Dict[float, float]]] = {s: {"bids": {}, "asks": {}} for s in symbols}
    last_emit: Dict[str, float] = {s: 0.0 for s in symbols}
    stop_at = time.time() + float(args.duration_sec) if args.duration_sec > 0 else 0.0

    while True:
        if stop_at and time.time() >= stop_at:
            return
        try:
            async with websockets.connect(args.ws_url, ping_interval=args.ping_interval_sec, ping_timeout=20) as ws:
                for chunk in _chunks(topics, max(1, int(args.chunk_size))):
                    await ws.send(json.dumps({"op": "subscribe", "args": chunk}))
                    await asyncio.sleep(0.1)
                print(f"subscribed symbols={len(symbols)} depth={args.depth} out={out_path}", flush=True)
                with out_path.open("a", encoding="utf-8") as f:
                    while True:
                        if stop_at and time.time() >= stop_at:
                            return
                        raw = await asyncio.wait_for(ws.recv(), timeout=args.idle_timeout_sec)
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        sym = None
                        for s in symbols:
                            if str(msg.get("topic") or "").endswith(f".{s}"):
                                sym = s
                                break
                        if sym is None:
                            continue
                        apply_orderbook_message(books[sym], msg)
                        now = time.time()
                        if now - last_emit[sym] >= float(args.emit_every_sec):
                            last_emit[sym] = now
                            dens = extract_densities(
                                books[sym], symbol=sym, ts_ms=int(now * 1000),
                                min_mult=args.min_mult, max_dist_pct=args.max_dist_pct,
                                top_n=args.top_n,
                            )
                            for d in dens:
                                if d["size_usd"] < args.min_usd:
                                    continue
                                f.write(json.dumps(d, separators=(",", ":"), sort_keys=True) + "\n")
                            if dens:
                                f.flush()
        except asyncio.TimeoutError:
            print("idle timeout; reconnecting", flush=True)
        except Exception as exc:
            print(f"collector error: {exc}; reconnecting in {args.reconnect_sleep_sec}s", flush=True)
            await asyncio.sleep(args.reconnect_sleep_sec)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,LINKUSDT,DOGEUSDT,XRPUSDT,SUIUSDT,LTCUSDT,DOTUSDT")
    p.add_argument("--ws-url", default="wss://stream.bybit.com/v5/public/linear")
    p.add_argument("--depth", type=int, default=50, choices=[1, 50, 200])
    p.add_argument("--out", default="runtime/orderbook/bybit_densities.jsonl")
    p.add_argument("--emit-every-sec", type=float, default=30.0)
    p.add_argument("--min-mult", type=float, default=4.0, help="wall >= mult * median level size")
    p.add_argument("--max-dist-pct", type=float, default=3.0, help="only walls within this %% of mid")
    p.add_argument("--top-n", type=int, default=5, help="largest walls per side per emit")
    p.add_argument("--min-usd", type=float, default=10_000.0)
    p.add_argument("--chunk-size", type=int, default=10)
    p.add_argument("--ping-interval-sec", type=float, default=20.0)
    p.add_argument("--idle-timeout-sec", type=float, default=60.0)
    p.add_argument("--reconnect-sleep-sec", type=float, default=5.0)
    p.add_argument("--duration-sec", type=float, default=0.0, help="0 = run forever")
    return p


def main(argv: Optional[List[str]] = None) -> int:  # pragma: no cover
    args = build_parser().parse_args(argv)
    asyncio.run(collect(args))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
