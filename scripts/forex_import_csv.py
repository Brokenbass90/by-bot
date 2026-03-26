#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


def _norm(s: str) -> str:
    return "".join(ch for ch in str(s).strip().lower() if ch.isalnum())


def _choose_col(cols: Dict[str, int], names: Iterable[str]) -> Optional[int]:
    for n in names:
        key = _norm(n)
        if key in cols:
            return cols[key]
    return None


def _parse_ts_from_text(text: str, tz_offset_hours: float) -> Optional[int]:
    s = str(text or "").strip()
    if not s:
        return None

    # Numeric unix timestamp (sec/ms)
    try:
        x = float(s)
        if x > 1e12:
            return int(x // 1000)
        if x > 1e9:
            return int(x)
    except Exception:
        pass

    fmts = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    )
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            dt_utc = dt - timedelta(hours=float(tz_offset_hours))
            return int(dt_utc.replace(tzinfo=timezone.utc).timestamp())
        except Exception:
            continue
    return None


def _to_float(x: str) -> Optional[float]:
    s = str(x or "").strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert broker CSV (MT5/other) to ts,o,h,l,c,v format.")
    ap.add_argument("--input", required=True, help="Path to source CSV")
    ap.add_argument("--output", required=True, help="Path to output CSV (ts,o,h,l,c,v)")
    ap.add_argument("--symbol", default="", help="Optional symbol label for logs")
    ap.add_argument(
        "--tz_offset_hours",
        type=float,
        default=0.0,
        help="Source timezone offset vs UTC (e.g. 2 means source is UTC+2).",
    )
    args = ap.parse_args()

    src = Path(args.input)
    out = Path(args.output)
    if not src.exists():
        raise SystemExit(f"Input file not found: {src}")

    with src.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        raise SystemExit("Input CSV is empty")

    header = rows[0]
    data_rows = rows[1:]
    cols = {_norm(h): i for i, h in enumerate(header)}

    # Timestamp may be provided directly.
    i_ts = _choose_col(cols, ("ts", "timestamp", "unixtime", "timeunix"))
    i_datetime = _choose_col(cols, ("datetime", "gmttime", "time", "dateandtime"))
    i_date = _choose_col(cols, ("date", "<date>", "tradedate"))
    i_time = _choose_col(cols, ("clock", "<time>", "timeofday"))

    i_open = _choose_col(cols, ("open", "<open>", "o"))
    i_high = _choose_col(cols, ("high", "<high>", "h"))
    i_low = _choose_col(cols, ("low", "<low>", "l"))
    i_close = _choose_col(cols, ("close", "<close>", "c"))
    i_vol = _choose_col(cols, ("volume", "tickvolume", "tickvol", "<tickvol>", "<volume>", "v"))

    missing = []
    for name, idx in (("open", i_open), ("high", i_high), ("low", i_low), ("close", i_close)):
        if idx is None:
            missing.append(name)
    if missing:
        raise SystemExit(f"Missing required OHLC columns: {', '.join(missing)}")

    out_rows: List[Tuple[int, float, float, float, float, float]] = []
    for r in data_rows:
        if not r:
            continue

        ts: Optional[int] = None
        if i_ts is not None and i_ts < len(r):
            ts = _parse_ts_from_text(r[i_ts], args.tz_offset_hours)
        if ts is None and i_datetime is not None and i_datetime < len(r):
            ts = _parse_ts_from_text(r[i_datetime], args.tz_offset_hours)
        if ts is None and i_date is not None and i_time is not None and i_date < len(r) and i_time < len(r):
            ts = _parse_ts_from_text(f"{r[i_date]} {r[i_time]}", args.tz_offset_hours)
        if ts is None:
            continue

        o = _to_float(r[i_open]) if i_open < len(r) else None
        h = _to_float(r[i_high]) if i_high < len(r) else None
        l = _to_float(r[i_low]) if i_low < len(r) else None
        c = _to_float(r[i_close]) if i_close < len(r) else None
        v = _to_float(r[i_vol]) if (i_vol is not None and i_vol < len(r)) else 0.0
        if None in (o, h, l, c):
            continue
        out_rows.append((int(ts), float(o), float(h), float(l), float(c), float(v or 0.0)))

    if not out_rows:
        raise SystemExit("No valid rows parsed from source CSV")

    # Deduplicate by timestamp and sort.
    by_ts: Dict[int, Tuple[int, float, float, float, float, float]] = {}
    for row in out_rows:
        by_ts[row[0]] = row
    out_rows = [by_ts[k] for k in sorted(by_ts.keys())]

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ts", "o", "h", "l", "c", "v"])
        for ts, o, h, l, c, v in out_rows:
            w.writerow([ts, f"{o:.10f}", f"{h:.10f}", f"{l:.10f}", f"{c:.10f}", f"{v:.2f}"])

    steps = [out_rows[i][0] - out_rows[i - 1][0] for i in range(1, len(out_rows))]
    med_step = int(statistics.median(steps)) if steps else 0
    span_days = (out_rows[-1][0] - out_rows[0][0]) / 86400.0 if len(out_rows) > 1 else 0.0
    sym = args.symbol or src.stem
    print(f"symbol={sym}")
    print(f"saved={out}")
    print(f"rows={len(out_rows)} span_days={span_days:.2f} median_step_sec={med_step}")
    if med_step not in (0, 300):
        print("warning=median_step_is_not_300sec (data may be non-M5)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

