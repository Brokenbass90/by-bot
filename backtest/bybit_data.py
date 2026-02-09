#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Bybit public market data helpers with local caching.

Only public endpoints are used, so no API keys are required.

Backtests may request 30+ days of 5-minute klines across many symbols.
To avoid repeated downloads, responses are cached under ./data_cache.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple



DEFAULT_BYBIT_BASE = os.getenv("BYBIT_BASE", "https://api.bybit.com")
CACHE_DIR = os.getenv("BYBIT_DATA_CACHE_DIR", "data_cache")
DEFAULT_POLITE_SLEEP_SEC = float(os.getenv("BYBIT_DATA_POLITE_SLEEP_SEC", "0.60"))


@dataclass(frozen=True)
class Kline:
    ts: int  # ms
    o: float
    h: float
    l: float
    c: float
    v: float


def _dt_utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y%m%d")


def _cache_path(symbol: str, interval: str, start_ms: int, end_ms: int) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    s = _dt_utc(start_ms)
    e = _dt_utc(end_ms)
    return os.path.join(CACHE_DIR, f"{symbol}_{interval}_{s}_{e}.json")


def _req_json(url: str, params: Dict[str, Any], timeout: int = 20) -> Dict[str, Any]:
    try:
        import requests  # lazy import to avoid dependency when using local cache only
    except Exception as e:
        raise RuntimeError("Fetching Bybit data requires the 'requests' package") from e
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_klines_public(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    *,
    base: str = DEFAULT_BYBIT_BASE,
    category: str = "linear",
    limit: int = 1000,
    cache: bool = True,
    polite_sleep_sec: float = DEFAULT_POLITE_SLEEP_SEC,
) -> List[Kline]:
    """Fetch klines from Bybit v5 and return *oldest-first* list of Kline.

    interval examples: "1", "3", "5", "15", "60", "240" (minutes)

    We chunk the request in a loop because the endpoint has a per-call limit.
    """

    if end_ms <= start_ms:
        return []

    cache_path = _cache_path(symbol, interval, start_ms, end_ms)
    if cache and os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [Kline(**x) for x in raw]

    url = f"{base.rstrip('/')}/v5/market/kline"

    out: List[Kline] = []
    cursor_end = end_ms

    # Bybit returns newest-first. We iterate backwards (end -> start)
    # and then reverse at the end.
    while cursor_end > start_ms:
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "end": cursor_end,
            "limit": limit,
        }
        # Fetch with basic rate-limit backoff (retCode 10006 = Too many visits)
        backoff = max(0.6, float(polite_sleep_sec))
        js = None
        for attempt in range(10):
            try:
                js = _req_json(url, params)
            except Exception as e:
                # network hiccup / transient Bybit edge
                time.sleep(min(15.0, backoff))
                backoff = min(15.0, backoff * 1.7)
                continue

            rc = js.get("retCode")
            if rc == 0 or rc == "0":
                break

            try:
                rc_i = int(rc)
            except Exception:
                rc_i = -1

            if rc_i == 10006:
                time.sleep(min(15.0, backoff))
                backoff = min(15.0, backoff * 1.7)
                continue

            raise RuntimeError(f"Bybit error {rc}: {js.get('retMsg')}")

        else:
            raise RuntimeError(f"Bybit error 10006: Too many visits (rate limit) after retries")

        lst = (((js.get("result") or {}).get("list")) or [])
        if not lst:
            break

        # list format: [startTime, open, high, low, close, volume, turnover]
        for row in lst:
            try:
                ts = int(row[0])
                if ts < start_ms or ts >= end_ms:
                    continue
                out.append(
                    Kline(
                        ts=ts,
                        o=float(row[1]),
                        h=float(row[2]),
                        l=float(row[3]),
                        c=float(row[4]),
                        v=float(row[5]),
                    )
                )
            except Exception:
                continue

        # move cursor earlier than the earliest returned candle
        earliest_ts = int(lst[-1][0])
        if earliest_ts == cursor_end:
            break
        cursor_end = earliest_ts - 1

        if polite_sleep_sec > 0:
            time.sleep(polite_sleep_sec)

    out.sort(key=lambda x: x.ts)

    if cache:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump([x.__dict__ for x in out], f, ensure_ascii=False)

    return out


def to_bybit_raw(klines: List[Kline]) -> List[List[Any]]:
    """Convert to a Bybit-like raw format that sr_* modules can normalize."""
    return [[k.ts, str(k.o), str(k.h), str(k.l), str(k.c), str(k.v), "0"] for k in klines]


def aggregate_klines(src: List[Kline], minutes: int) -> List[Kline]:
    """Aggregate lower TF klines into higher TF by simple bucket grouping.

    Assumes src is continuous and ordered. If gaps exist, aggregation remains
    best-effort.
    """
    if not src:
        return []

    base_minutes = 5  # backtests use 5m as base
    step = max(1, int(minutes / base_minutes))

    out: List[Kline] = []
    i = 0
    n = len(src)
    while i < n:
        chunk = src[i : i + step]
        if not chunk:
            break
        ts0 = chunk[0].ts
        o = chunk[0].o
        h = max(x.h for x in chunk)
        l = min(x.l for x in chunk)
        c = chunk[-1].c
        v = sum(x.v for x in chunk)
        out.append(Kline(ts=ts0, o=o, h=h, l=l, c=c, v=v))
        i += step
    return out
