#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import lzma
import math
import struct
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


PAIR_PRICE_SCALE: Dict[str, int] = {
    "USDJPY": 1000,
    "EURJPY": 1000,
    "GBPJPY": 1000,
    "AUDJPY": 1000,
    "CADJPY": 1000,
}

FIVE_MIN = 300
TICK_RECORD_BYTES = 20


def _iter_hours(start: dt.datetime, end: dt.datetime) -> Iterable[dt.datetime]:
    cur = start
    while cur < end:
        yield cur
        cur += dt.timedelta(hours=1)


def _pair_scale(pair: str) -> int:
    return int(PAIR_PRICE_SCALE.get(pair.upper(), 100000))


def _dukascopy_url(pair: str, dth: dt.datetime) -> str:
    # Dukascopy uses 0-based month index in path.
    return (
        "https://datafeed.dukascopy.com/datafeed/"
        f"{pair.upper()}/{dth.year}/{dth.month - 1:02d}/{dth.day:02d}/{dth.hour:02d}h_ticks.bi5"
    )


def _decode_bi5(raw: bytes) -> bytes:
    try:
        return lzma.decompress(raw, format=lzma.FORMAT_AUTO)
    except Exception:
        pass
    try:
        return lzma.decompress(raw, format=lzma.FORMAT_ALONE)
    except Exception:
        pass
    # Common fallback for Dukascopy BI5 files.
    return lzma.decompress(
        raw,
        format=lzma.FORMAT_RAW,
        filters=[
            {
                "id": lzma.FILTER_LZMA1,
                "dict_size": 2**23,
                "lc": 3,
                "lp": 0,
                "pb": 2,
            }
        ],
    )


def _bucket_ts(ts_sec: int) -> int:
    return ts_sec - (ts_sec % FIVE_MIN)


def _append_tick(
    buckets: Dict[int, List[float]],
    ts_sec: int,
    price: float,
    volume: float,
) -> None:
    key = _bucket_ts(ts_sec)
    if key not in buckets:
        buckets[key] = [price, price, price, price, max(0.0, volume)]
        return
    row = buckets[key]
    row[1] = max(row[1], price)  # high
    row[2] = min(row[2], price)  # low
    row[3] = price               # close
    row[4] += max(0.0, volume)


def _fetch_hour(url: str, timeout_sec: float) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "by-bot-forex-research/1.0",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return resp.read()


def _build_rows_for_pair(
    pair: str,
    start_utc: dt.datetime,
    end_utc: dt.datetime,
    timeout_sec: float,
    sleep_sec: float,
    retries: int,
    max_hours: int,
) -> Tuple[List[Tuple[int, float, float, float, float, float]], Dict[str, int], str]:
    scale = float(_pair_scale(pair))
    buckets: Dict[int, List[float]] = {}
    stats = {
        "hours_total": 0,
        "hours_ok": 0,
        "hours_404": 0,
        "hours_empty": 0,
        "hours_fail": 0,
        "ticks": 0,
    }
    last_error = ""

    for idx, hour in enumerate(_iter_hours(start_utc, end_utc)):
        if max_hours > 0 and idx >= max_hours:
            break
        stats["hours_total"] += 1
        url = _dukascopy_url(pair, hour)

        payload: bytes | None = None
        for attempt in range(max(1, retries + 1)):
            try:
                payload = _fetch_hour(url, timeout_sec=timeout_sec)
                break
            except urllib.error.HTTPError as e:
                if int(e.code) == 404:
                    stats["hours_404"] += 1
                    payload = None
                    break
                last_error = f"HTTP {e.code} on {url}"
                if attempt >= retries:
                    stats["hours_fail"] += 1
                else:
                    time.sleep(min(2.0, 0.25 * (attempt + 1)))
            except Exception as e:
                last_error = f"request error on {url}: {e}"
                if attempt >= retries:
                    stats["hours_fail"] += 1
                else:
                    time.sleep(min(2.0, 0.25 * (attempt + 1)))

        if payload is None:
            time.sleep(max(0.0, sleep_sec))
            continue
        if len(payload) == 0:
            stats["hours_empty"] += 1
            time.sleep(max(0.0, sleep_sec))
            continue

        try:
            decoded = _decode_bi5(payload)
        except Exception as e:
            last_error = f"decode error on {url}: {e}"
            stats["hours_fail"] += 1
            time.sleep(max(0.0, sleep_sec))
            continue

        if len(decoded) < TICK_RECORD_BYTES:
            time.sleep(max(0.0, sleep_sec))
            continue

        hour_epoch = int(hour.timestamp())
        records = len(decoded) // TICK_RECORD_BYTES
        stats["hours_ok"] += 1
        stats["ticks"] += records

        for pos in range(0, records * TICK_RECORD_BYTES, TICK_RECORD_BYTES):
            ms_offset, ask_i, bid_i, ask_v, bid_v = struct.unpack(">IIIff", decoded[pos : pos + TICK_RECORD_BYTES])
            ts_sec = hour_epoch + int(ms_offset // 1000)
            if ts_sec < int(start_utc.timestamp()) or ts_sec >= int(end_utc.timestamp()):
                continue
            if ask_i <= 0 or bid_i <= 0:
                continue
            mid_price = ((float(ask_i) + float(bid_i)) * 0.5) / scale
            if not math.isfinite(mid_price) or mid_price <= 0.0:
                continue
            vol = max(0.0, float(ask_v)) + max(0.0, float(bid_v))
            _append_tick(buckets, ts_sec=ts_sec, price=mid_price, volume=vol)

        time.sleep(max(0.0, sleep_sec))

    rows: List[Tuple[int, float, float, float, float, float]] = []
    for ts in sorted(buckets.keys()):
        o, h, l, c, v = buckets[ts]
        rows.append((ts, o, h, l, c, v))
    return rows, stats, last_error


def _write_rows(path: Path, rows: List[Tuple[int, float, float, float, float, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ts", "o", "h", "l", "c", "v"])
        for ts, o, h, l, c, v in rows:
            w.writerow([ts, f"{o:.10f}", f"{h:.10f}", f"{l:.10f}", f"{c:.10f}", f"{v:.2f}"])


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch free Dukascopy tick data and aggregate to M5 OHLCV CSV.")
    ap.add_argument("--pairs", default="EURUSD,GBPUSD,USDJPY")
    ap.add_argument("--days", type=int, default=120, help="Lookback in days from now UTC.")
    ap.add_argument("--from-utc", default="", help="Optional start UTC (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).")
    ap.add_argument("--to-utc", default="", help="Optional end UTC (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).")
    ap.add_argument("--out-dir", default="data_cache/forex")
    ap.add_argument("--sleep-sec", type=float, default=0.02)
    ap.add_argument("--timeout-sec", type=float, default=12.0)
    ap.add_argument("--retries", type=int, default=1)
    ap.add_argument("--max-hours", type=int, default=0, help="Debug cap per pair; 0 = no cap.")
    args = ap.parse_args()

    pairs = [p.strip().upper() for p in args.pairs.split(",") if p.strip()]
    if not pairs:
        raise SystemExit("No pairs provided.")

    now = dt.datetime.now(dt.UTC).replace(minute=0, second=0, microsecond=0)

    def parse_utc(s: str) -> dt.datetime:
        txt = s.strip()
        if not txt:
            raise ValueError("empty datetime string")
        if len(txt) == 10:
            txt = txt + "T00:00:00"
        parsed = dt.datetime.fromisoformat(txt.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.UTC)
        return parsed.astimezone(dt.UTC)

    if args.from_utc.strip():
        start_utc = parse_utc(args.from_utc).replace(minute=0, second=0, microsecond=0)
    else:
        start_utc = now - dt.timedelta(days=max(1, int(args.days)))
    if args.to_utc.strip():
        end_utc = parse_utc(args.to_utc).replace(minute=0, second=0, microsecond=0)
    else:
        end_utc = now
    if end_utc <= start_utc:
        raise SystemExit("Invalid range: to-utc must be > from-utc.")

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"dukascopy fetch start: {dt.datetime.now(dt.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"pairs={','.join(pairs)}")
    print(f"range={start_utc.strftime('%Y-%m-%d %H:%M')}..{end_utc.strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"out_dir={out_dir}")

    ok = 0
    for pair in pairs:
        print(f"\n>>> {pair}")
        rows, stats, last_error = _build_rows_for_pair(
            pair=pair,
            start_utc=start_utc,
            end_utc=end_utc,
            timeout_sec=float(args.timeout_sec),
            sleep_sec=float(args.sleep_sec),
            retries=max(0, int(args.retries)),
            max_hours=max(0, int(args.max_hours)),
        )
        if not rows:
            print(
                "fail: no rows"
                f" hours_total={stats['hours_total']} ok={stats['hours_ok']} 404={stats['hours_404']} empty={stats['hours_empty']} fail={stats['hours_fail']}"
            )
            if last_error:
                print(f"last_error={last_error}")
            continue
        out_path = out_dir / f"{pair}_M5.csv"
        _write_rows(out_path, rows)
        span_days = (rows[-1][0] - rows[0][0]) / 86400.0 if len(rows) > 1 else 0.0
        print(f"saved={out_path}")
        print(
            f"rows={len(rows)} span_days={span_days:.2f}"
            f" hours_total={stats['hours_total']} ok={stats['hours_ok']} 404={stats['hours_404']} empty={stats['hours_empty']} fail={stats['hours_fail']}"
        )
        ok += 1

    print(f"\ndukascopy fetch done: ok={ok}/{len(pairs)}")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
