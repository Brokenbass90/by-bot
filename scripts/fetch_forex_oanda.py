#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List


PAIR_TO_OANDA: Dict[str, str] = {
    "EURUSD": "EUR_USD",
    "GBPUSD": "GBP_USD",
    "USDJPY": "USD_JPY",
    "AUDUSD": "AUD_USD",
    "USDCAD": "USD_CAD",
    "USDCHF": "USD_CHF",
    "NZDUSD": "NZD_USD",
    "EURGBP": "EUR_GBP",
    "EURJPY": "EUR_JPY",
    "GBPJPY": "GBP_JPY",
    "AUDJPY": "AUD_JPY",
    "CADJPY": "CAD_JPY",
}


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_oanda_ts(ts: str) -> int:
    # OANDA timestamps are often nanosecond precision, e.g. 2026-03-04T10:25:00.000000000Z
    t = ts.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    if "." in t:
        base, frac_tz = t.split(".", 1)
        if "+" in frac_tz:
            frac, tz = frac_tz.split("+", 1)
            frac = (frac + "000000")[:6]
            t = f"{base}.{frac}+{tz}"
        elif "-" in frac_tz:
            frac, tz = frac_tz.split("-", 1)
            frac = (frac + "000000")[:6]
            t = f"{base}.{frac}-{tz}"
        else:
            frac = (frac_tz + "000000")[:6]
            t = f"{base}.{frac}"
    dt = datetime.fromisoformat(t)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _fetch_chunk(base_url: str, token: str, instrument: str, frm: datetime, granularity: str, count: int):
    params = {
        "price": "M",
        "granularity": granularity,
        "count": str(count),
        "from": _utc_iso(frm),
    }
    url = f"{base_url.rstrip('/')}/v3/instruments/{instrument}/candles?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch M5 Forex data from OANDA REST v20 into ts,o,h,l,c,v CSV.")
    ap.add_argument("--pairs", default="EURUSD,GBPUSD,USDJPY")
    ap.add_argument("--days", type=int, default=365, help="History depth in days")
    ap.add_argument("--granularity", default="M5")
    ap.add_argument("--count-per-request", type=int, default=5000)
    ap.add_argument("--sleep-sec", type=float, default=0.12)
    ap.add_argument("--out-dir", default="data_cache/forex")
    ap.add_argument("--base-url", default=os.getenv("OANDA_API_URL", "https://api-fxpractice.oanda.com"))
    ap.add_argument("--token", default=os.getenv("OANDA_API_TOKEN", ""))
    args = ap.parse_args()

    token = args.token.strip()
    if not token:
        raise SystemExit("Missing OANDA token. Set OANDA_API_TOKEN or pass --token.")
    token_u = token.upper()
    if token_u in {"YOUR_TOKEN", "YOUR_OANDA_TOKEN", "TOKEN", "API_TOKEN"} or "YOUR_" in token_u:
        raise SystemExit(
            "OANDA token looks like a placeholder. "
            "Use a real personal access token from OANDA: My Account -> My Services -> Manage API Access."
        )

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=max(1, int(args.days)))
    pairs = [p.strip().upper() for p in args.pairs.split(",") if p.strip()]

    print(f"oanda fetch start: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"pairs={','.join(pairs)} days={args.days} granularity={args.granularity} out_dir={out_dir}")
    print(f"base_url={args.base_url}")

    ok = 0
    step = timedelta(minutes=5) if args.granularity.upper() == "M5" else timedelta(minutes=1)
    for pair in pairs:
        instr = PAIR_TO_OANDA.get(pair, "")
        if not instr:
            print(f"\n>>> {pair}\nskip: no OANDA mapping")
            continue

        print(f"\n>>> {pair} ({instr})")
        cursor = start_dt
        rows: List[tuple[int, float, float, float, float, float]] = []
        seen = set()
        loops = 0
        while cursor < end_dt:
            loops += 1
            try:
                js = _fetch_chunk(
                    base_url=args.base_url,
                    token=token,
                    instrument=instr,
                    frm=cursor,
                    granularity=args.granularity.upper(),
                    count=int(args.count_per_request),
                )
            except Exception as e:
                print(f"fail chunk from={_utc_iso(cursor)} err={e}")
                break

            candles = js.get("candles") or []
            if not candles:
                break

            last_ts = None
            added = 0
            for c in candles:
                if not c.get("complete", False):
                    continue
                mid = c.get("mid") or {}
                if not all(k in mid for k in ("o", "h", "l", "c")):
                    continue
                ts = _parse_oanda_ts(str(c.get("time") or ""))
                if ts in seen:
                    continue
                seen.add(ts)
                o = float(mid["o"])
                h = float(mid["h"])
                l = float(mid["l"])
                cl = float(mid["c"])
                v = float(c.get("volume") or 0.0)
                if min(o, h, l, cl) <= 0:
                    continue
                rows.append((ts, o, h, l, cl, v))
                added += 1
                last_ts = ts

            if added == 0 or last_ts is None:
                break
            cursor = datetime.fromtimestamp(last_ts, tz=timezone.utc) + step
            if cursor >= end_dt:
                break
            time.sleep(max(0.0, float(args.sleep_sec)))
            if loops > 5000:
                break

        if not rows:
            print("fail: no rows collected")
            continue

        rows.sort(key=lambda x: x[0])
        out = out_dir / f"{pair}_{args.granularity.upper()}.csv"
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ts", "o", "h", "l", "c", "v"])
            for ts, o, h, l, c, v in rows:
                w.writerow([ts, f"{o:.10f}", f"{h:.10f}", f"{l:.10f}", f"{c:.10f}", f"{v:.2f}"])
        span_days = (rows[-1][0] - rows[0][0]) / 86400.0 if len(rows) > 1 else 0.0
        print(f"saved={out}")
        print(f"rows={len(rows)} span_days={span_days:.2f}")
        ok += 1

    print(f"\noanda fetch done: ok={ok}/{len(pairs)}")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
