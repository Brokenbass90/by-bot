"""DST-aware sessions and schedule-aware candle quality for FX/CFD V2."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Sequence
from zoneinfo import ZoneInfo


UTC = timezone.utc
NY = ZoneInfo("America/New_York")
LONDON = ZoneInfo("Europe/London")


def _seconds(ts: float) -> int:
    value = int(float(ts))
    return value // 1000 if value > 10_000_000_000 else value


def session_labels(ts: float) -> tuple[str, ...]:
    """Liquid-session labels using local exchange clocks, including DST."""
    dt_utc = datetime.fromtimestamp(_seconds(ts), UTC)
    ld = dt_utc.astimezone(LONDON)
    ny = dt_utc.astimezone(NY)
    london_open = ld.weekday() < 5 and 8 <= ld.hour < 17
    newyork_open = ny.weekday() < 5 and 8 <= ny.hour < 17
    if london_open and newyork_open:
        return ("london_ny_overlap", "london", "newyork")
    if london_open:
        return ("london",)
    if newyork_open:
        return ("newyork",)
    return ("off_session",)


def market_is_open(ts: float, schedule: str) -> bool:
    """Approximate target-market schedule, expressed in DST-aware New York time.

    FX: Sunday 17:00 through Friday 17:00 New York.
    XAU CFD: the same weekly window with a conservative 17:00-18:00 daily
    maintenance break.  Broker-specific holidays remain a promotion blocker.
    """
    ny = datetime.fromtimestamp(_seconds(ts), UTC).astimezone(NY)
    wd, hour = ny.weekday(), ny.hour
    # Universal full-day closures.  Other holidays remain visible as holes
    # until an explicit broker calendar is supplied; we never infer a holiday
    # merely from a large gap.
    if (ny.month, ny.day) in {(1, 1), (12, 25)}:
        return False
    if wd == 5:  # Saturday
        return False
    if wd == 6 and hour < 17:
        return False
    if wd == 4 and hour >= 17:
        return False
    if schedule == "xau_23x5" and wd < 5 and hour == 17:
        return False
    return schedule in {"fx_24x5", "xau_23x5"}


@dataclass
class FxCoverageReport:
    symbol: str
    schedule: str
    interval_sec: int
    expected_bars: int
    actual_expected_bars: int
    coverage: float
    duplicate_bars: int
    off_schedule_bars: int
    invalid_ohlc_bars: int
    missing_runs: int
    max_missing_run: int
    span_days: float
    first_ts: int
    last_ts: int
    ok: bool
    reasons: List[str] = field(default_factory=list)
    largest_missing_runs: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def assess_schedule_coverage(
    rows: Sequence[Sequence[float]],
    *,
    symbol: str,
    schedule: str,
    interval_sec: int = 3600,
    min_coverage: float = 0.985,
    max_missing_run: int = 3,
    min_bars: int = 1000,
    min_span_days: float = 180.0,
    max_off_schedule_bars: int = 0,
    window_start_ts: int | None = None,
    window_end_ts_exclusive: int | None = None,
) -> FxCoverageReport:
    """Validate uniqueness/OHLC and holes only during expected market hours.

    Unlike the legacy ``market_closure_gap_bars`` shortcut, an arbitrary
    multi-week gap is never reclassified as a weekend merely because it is big.
    """
    clean: List[tuple[int, Sequence[float]]] = []
    duplicates = 0
    invalid = 0
    seen: set[int] = set()
    for row in rows:
        try:
            ts = _seconds(float(row[0]))
            o, h, l, c = map(float, row[1:5])
            volume = float(row[5]) if len(row) > 5 else 0.0
        except (TypeError, ValueError, IndexError, OverflowError):
            invalid += 1
            continue
        if ts in seen:
            duplicates += 1
            continue
        seen.add(ts)
        if not (
            all(math.isfinite(value) for value in (o, h, l, c, volume))
            and 0 < l <= min(o, c) <= max(o, c) <= h
            and volume >= 0
        ):
            invalid += 1
            continue
        clean.append((ts, row))
    clean.sort(key=lambda item: item[0])
    if not clean:
        return FxCoverageReport(
            symbol, schedule, interval_sec, 0, 0, 0.0, duplicates, 0, invalid,
            0, 0, 0.0, 0, 0, False, ["no_valid_bars"], [],
        )

    first_ts, last_ts = clean[0][0], clean[-1][0]
    expected_start = _seconds(window_start_ts) if window_start_ts is not None else first_ts
    expected_end = (
        _seconds(window_end_ts_exclusive)
        if window_end_ts_exclusive is not None
        else last_ts + interval_sec
    )
    if expected_end <= expected_start:
        raise ValueError("coverage window end must be after start")
    expected: List[int] = []
    ts = expected_start
    while ts < expected_end:
        if market_is_open(ts, schedule):
            expected.append(ts)
        ts += interval_sec
    actual_set = {
        ts for ts, _ in clean
        if expected_start <= ts < expected_end
    }
    actual_expected = sum(1 for ts in actual_set if market_is_open(ts, schedule))
    off_schedule = len(actual_set) - actual_expected
    missing = [ts for ts in expected if ts not in actual_set]

    runs: List[Dict[str, Any]] = []
    if missing:
        start = prev = missing[0]
        length = 1
        for cur in missing[1:]:
            if cur == prev + interval_sec:
                length += 1
            else:
                runs.append({"start_ts": start, "end_ts": prev, "bars": length})
                start, length = cur, 1
            prev = cur
        runs.append({"start_ts": start, "end_ts": prev, "bars": length})
    largest = sorted(runs, key=lambda r: int(r["bars"]), reverse=True)[:10]
    max_run = max((int(r["bars"]) for r in runs), default=0)
    coverage = actual_expected / len(expected) if expected else 0.0
    span_days = (expected_end - expected_start) / 86400.0
    reasons: List[str] = []
    if len(clean) < min_bars:
        reasons.append(f"too_few_bars_{len(clean)}<{min_bars}")
    if span_days < min_span_days:
        reasons.append(f"span_days_{span_days:.1f}<{min_span_days}")
    if coverage < min_coverage:
        reasons.append(f"coverage_{coverage:.4f}<{min_coverage}")
    if max_run > max_missing_run:
        reasons.append(f"missing_run_{max_run}>{max_missing_run}")
    if duplicates:
        reasons.append(f"duplicate_bars_{duplicates}")
    if invalid:
        reasons.append(f"invalid_ohlc_{invalid}")
    if off_schedule > int(max_off_schedule_bars):
        reasons.append(f"off_schedule_bars_{off_schedule}>{int(max_off_schedule_bars)}")
    return FxCoverageReport(
        symbol=str(symbol).upper(), schedule=schedule, interval_sec=interval_sec,
        expected_bars=len(expected), actual_expected_bars=actual_expected,
        coverage=round(min(1.0, coverage), 6), duplicate_bars=duplicates,
        off_schedule_bars=off_schedule, invalid_ohlc_bars=invalid,
        missing_runs=len(runs), max_missing_run=max_run, span_days=round(span_days, 2),
        first_ts=first_ts, last_ts=last_ts, ok=not reasons, reasons=reasons,
        largest_missing_runs=largest,
    )
