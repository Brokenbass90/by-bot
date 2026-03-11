from __future__ import annotations

import csv
from pathlib import Path
from typing import List

from .types import Candle


def load_m5_csv(path: str) -> List[Candle]:
    """Load M5 candles from CSV.

    Accepted headers:
    - ts,o,h,l,c,v
    - timestamp,open,high,low,close,volume
    ts/timestamp can be epoch seconds or milliseconds.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"CSV not found: {p}")

    rows: List[Candle] = []
    with p.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            ts_raw = row.get("ts") or row.get("timestamp") or ""
            if not ts_raw:
                continue
            ts = int(float(ts_raw))
            if ts > 10_000_000_000:
                ts //= 1000
            o = float(row.get("o") or row.get("open") or 0.0)
            h = float(row.get("h") or row.get("high") or 0.0)
            l = float(row.get("l") or row.get("low") or 0.0)
            c = float(row.get("c") or row.get("close") or 0.0)
            v = float(row.get("v") or row.get("volume") or 0.0)
            if min(o, h, l, c) <= 0:
                continue
            rows.append(Candle(ts=ts, o=o, h=h, l=l, c=c, v=v))
    return rows
