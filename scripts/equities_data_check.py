#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path


def _read_ts(path: Path) -> list[int]:
    ts_list: list[int] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            ts_raw = (row.get("ts") or row.get("timestamp") or "").strip()
            if not ts_raw:
                continue
            try:
                ts = int(float(ts_raw))
            except Exception:
                continue
            if ts > 10_000_000_000:
                ts //= 1000
            ts_list.append(ts)
    return ts_list


def _median_step(ts: list[int]) -> float:
    if len(ts) < 2:
        return 0.0
    d = []
    for i in range(1, len(ts)):
        x = ts[i] - ts[i - 1]
        if x > 0:
            d.append(x)
    if not d:
        return 0.0
    return float(statistics.median(d))


def main() -> int:
    ap = argparse.ArgumentParser(description="Check equities CSV readiness")
    ap.add_argument("--tickers", default="AAPL,MSFT,NVDA,AMZN,META,TSLA,GOOGL,AMD,JPM,XOM")
    ap.add_argument("--data-dir", default="data_cache/equities")
    ap.add_argument("--out", default="docs/equities_data_status.csv")
    args = ap.parse_args()

    root = Path.cwd()
    data_dir = (root / args.data_dir).resolve()
    out_path = (root / args.out).resolve()
    tickers = [x.strip().upper() for x in args.tickers.split(",") if x.strip()]

    rows: list[dict[str, str]] = []
    for t in tickers:
        fpath = data_dir / f"{t}_M5.csv"
        if not fpath.exists():
            rows.append(
                {
                    "ticker": t,
                    "path": str(fpath.relative_to(root)),
                    "exists": "0",
                    "rows": "0",
                    "first_ts": "",
                    "last_ts": "",
                    "span_days": "",
                    "median_step_sec": "",
                    "looks_like_m5": "0",
                }
            )
            continue

        ts = _read_ts(fpath)
        if not ts:
            rows.append(
                {
                    "ticker": t,
                    "path": str(fpath.relative_to(root)),
                    "exists": "1",
                    "rows": "0",
                    "first_ts": "",
                    "last_ts": "",
                    "span_days": "",
                    "median_step_sec": "",
                    "looks_like_m5": "0",
                }
            )
            continue

        ts_sorted = sorted(ts)
        first_ts = ts_sorted[0]
        last_ts = ts_sorted[-1]
        span_days = max(0.0, (last_ts - first_ts) / 86400.0)
        med_step = _median_step(ts_sorted)
        m5_ok = 270.0 <= med_step <= 330.0
        rows.append(
            {
                "ticker": t,
                "path": str(fpath.relative_to(root)),
                "exists": "1",
                "rows": str(len(ts_sorted)),
                "first_ts": str(first_ts),
                "last_ts": str(last_ts),
                "span_days": f"{span_days:.2f}",
                "median_step_sec": f"{med_step:.1f}",
                "looks_like_m5": "1" if m5_ok else "0",
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "ticker",
                "path",
                "exists",
                "rows",
                "first_ts",
                "last_ts",
                "span_days",
                "median_step_sec",
                "looks_like_m5",
            ],
        )
        w.writeheader()
        w.writerows(rows)

    ready = sum(1 for x in rows if x["exists"] == "1" and x["looks_like_m5"] == "1")
    print(f"saved={out_path}")
    print(f"tickers={len(rows)} ready={ready}")
    for x in rows:
        print(
            f"{x['ticker']}: exists={x['exists']} rows={x['rows']} "
            f"span_days={x['span_days'] or 'n/a'} median_step_sec={x['median_step_sec'] or 'n/a'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
