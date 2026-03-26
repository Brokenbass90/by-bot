#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


def _norm(s: str) -> str:
    return "".join(ch for ch in str(s or "").strip().lower() if ch.isalnum())


def _choose_col(cols: dict[str, int], names: Iterable[str]) -> Optional[int]:
    for n in names:
        key = _norm(n)
        if key in cols:
            return cols[key]
    return None


def _parse_ts(text: str) -> Optional[int]:
    s = str(text or "").strip()
    if not s:
        return None
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
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    )
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.astimezone(timezone.utc).timestamp())
        except Exception:
            continue
    return None


def _impact(raw: str) -> str:
    s = str(raw or "").strip().lower()
    if s in {"3", "high", "red", "critical"}:
        return "high"
    if s in {"2", "medium", "orange", "moderate"}:
        return "medium"
    if s in {"1", "low", "yellow", "minor"}:
        return "low"
    return "high" if "high" in s else ("medium" if "med" in s else ("low" if "low" in s else "medium"))


def _default_blackout(impact: str) -> tuple[int, int]:
    if impact == "high":
        return 20, 30
    if impact == "medium":
        return 10, 15
    return 0, 0


def _scope(currency: str, explicit_scope: str, title: str) -> str:
    scope = str(explicit_scope or "").strip().upper()
    if scope:
        return scope
    cur = "".join(ch if ch.isalpha() else "," for ch in str(currency or "").upper())
    parts = [p for p in cur.split(",") if p]
    parts = [p[:3] for p in parts if len(p) >= 3]
    if "XAU" in parts or "GOLD" in str(title or "").upper():
        return "METALS:XAUUSD"
    if len(parts) >= 2:
        return f"FX:{','.join(parts[:2])}"
    if len(parts) == 1:
        return f"FX:{parts[0]}"
    return "ALL"


def _event_id(ts_utc: int, currency: str, title: str, row_no: int) -> str:
    base = f"{ts_utc}|{currency}|{title}|{row_no}"
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
    return f"evt_{digest}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize raw macro/news CSV into runtime/news_filter canonical format.")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", default="runtime/news_filter/events_latest.csv")
    ap.add_argument("--source-name", default="manual_import")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        raise SystemExit(f"Input not found: {src}")
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    with src.open("r", newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        raise SystemExit("Empty input CSV")

    header = rows[0]
    data_rows = rows[1:]
    cols = {_norm(h): i for i, h in enumerate(header)}

    i_ts = _choose_col(cols, ("ts", "tsutc", "timestamp", "unix", "utc", "timeutc"))
    i_datetime = _choose_col(cols, ("datetime", "dateandtime", "gmttime"))
    i_date = _choose_col(cols, ("date", "day"))
    i_time = _choose_col(cols, ("time", "clock"))
    i_country = _choose_col(cols, ("country", "region"))
    i_currency = _choose_col(cols, ("currency", "curr", "currencies", "symbol"))
    i_scope = _choose_col(cols, ("instrumentscope", "scope", "marketscope"))
    i_title = _choose_col(cols, ("title", "event", "name"))
    i_impact = _choose_col(cols, ("impact", "importance", "priority"))
    i_before = _choose_col(cols, ("blackoutbeforemin", "beforemin"))
    i_after = _choose_col(cols, ("blackoutaftermin", "aftermin"))
    i_notes = _choose_col(cols, ("notes", "comment"))
    i_event_id = _choose_col(cols, ("eventid", "id"))

    normalized: list[list[str]] = []
    for row_no, row in enumerate(data_rows, start=2):
        if not row:
            continue
        ts = None
        if i_ts is not None and i_ts < len(row):
            ts = _parse_ts(row[i_ts])
        if ts is None and i_datetime is not None and i_datetime < len(row):
            ts = _parse_ts(row[i_datetime])
        if ts is None and i_date is not None and i_time is not None and i_date < len(row) and i_time < len(row):
            ts = _parse_ts(f"{row[i_date]} {row[i_time]}")
        if ts is None:
            continue

        country = str(row[i_country] if i_country is not None and i_country < len(row) else "").strip().upper()
        currency = str(row[i_currency] if i_currency is not None and i_currency < len(row) else "").strip().upper()
        title = str(row[i_title] if i_title is not None and i_title < len(row) else "").strip()
        impact = _impact(row[i_impact] if i_impact is not None and i_impact < len(row) else "")
        before_default, after_default = _default_blackout(impact)
        before = int(float(row[i_before])) if i_before is not None and i_before < len(row) and str(row[i_before]).strip() else before_default
        after = int(float(row[i_after])) if i_after is not None and i_after < len(row) and str(row[i_after]).strip() else after_default
        notes = str(row[i_notes] if i_notes is not None and i_notes < len(row) else "").strip()
        scope = _scope(
            currency=currency,
            explicit_scope=row[i_scope] if i_scope is not None and i_scope < len(row) else "",
            title=title,
        )
        event_id = str(row[i_event_id] if i_event_id is not None and i_event_id < len(row) else "").strip() or _event_id(ts, currency, title, row_no)
        normalized.append(
            [
                event_id,
                str(int(ts)),
                country,
                currency,
                scope,
                title,
                impact,
                args.source_name,
                str(before),
                str(after),
                notes,
            ]
        )

    if not normalized:
        raise SystemExit("No valid rows parsed")

    normalized.sort(key=lambda r: (int(r[1]), r[2], r[5]))
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "event_id",
                "ts_utc",
                "country",
                "currency",
                "instrument_scope",
                "title",
                "impact",
                "source",
                "blackout_before_min",
                "blackout_after_min",
                "notes",
            ]
        )
        w.writerows(normalized)

    print(f"saved={out}")
    print(f"rows={len(normalized)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
