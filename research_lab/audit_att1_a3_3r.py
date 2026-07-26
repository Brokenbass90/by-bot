#!/usr/bin/env python3
"""Audit Claude's A3/3R ATT1 proxy on the actual eight-symbol ATT1 universe.

This is deliberately not called an exact ATT1 replay: Claude's prototype uses
an H1 trendline-touch geometry over cached M5 bars, while live ATT1 has its own
entry path.  The audit answers narrower, falsifiable questions:

* does A3 help on the real ATT1 symbols, not a shuffled mover universe?
* does 3R survive explicit maker/mixed/taker round-trip costs?
* does the edge survive when overlapping clone trades are forbidden?
* are both chronological halves and four folds positive?

No network, broker, credentials, or orders are used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYMBOLS = (
    "ADAUSDT",
    "BTCUSDT",
    "DOTUSDT",
    "ETHUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "SOLUSDT",
    "SUIUSDT",
)
COST_BPS = (0.0, 4.0, 7.5, 11.0)


@dataclass(frozen=True)
class Candidate:
    symbol: str
    entry_index: int
    entry_ts: int
    side: str
    a3: bool
    risk_pct: float
    r_2: float
    exit_2: int
    r_3: float
    exit_3: int


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _widest_cache(symbol: str, data_dir: Path) -> Path:
    choices = list(data_dir.glob(f"{symbol}_5_*.json"))
    if not choices:
        raise FileNotFoundError(f"no M5 cache for {symbol} in {data_dir}")
    return max(choices, key=lambda path: path.stat().st_size)


def _load_m5(path: Path) -> list[list[float]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows: list[list[float]] = []
    for value in raw:
        if isinstance(value, dict):
            try:
                rows.append([
                    float(value["ts"]),
                    float(value["o"]),
                    float(value["h"]),
                    float(value["l"]),
                    float(value["c"]),
                ])
            except (KeyError, TypeError, ValueError):
                continue
        elif isinstance(value, list) and len(value) >= 5:
            try:
                rows.append([float(x) for x in value[:5]])
            except (TypeError, ValueError):
                continue
    rows.sort(key=lambda row: row[0])
    deduped: list[list[float]] = []
    for row in rows:
        if deduped and row[0] == deduped[-1][0]:
            deduped[-1] = row
        else:
            deduped.append(row)
    return deduped


def _to_h1(rows: Iterable[list[float]]) -> list[list[float]]:
    out: list[list[float]] = []
    current_bucket: int | None = None
    current: list[float] | None = None
    for row in rows:
        bucket = int(row[0]) // 3_600_000
        if bucket != current_bucket:
            if current is not None:
                out.append(current)
            current_bucket = bucket
            current = list(row)
        elif current is not None:
            current[2] = max(current[2], row[2])
            current[3] = min(current[3], row[3])
            current[4] = row[4]
    if current is not None:
        out.append(current)
    return out


def _all_pivots(rows: list[list[float]], left: int = 2, right: int = 2):
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for i in range(left, len(rows) - right):
        high = rows[i][2]
        if all(high >= rows[j][2] for j in range(i - left, i)) and all(
            high > rows[j][2] for j in range(i + 1, i + right + 1)
        ):
            highs.append((i, high))
        low = rows[i][3]
        if all(low <= rows[j][3] for j in range(i - left, i)) and all(
            low < rows[j][3] for j in range(i + 1, i + right + 1)
        ):
            lows.append((i, low))
    return highs, lows


def _fit(points: list[tuple[int, float]]) -> tuple[float, float] | None:
    n = len(points)
    mean_x = sum(point[0] for point in points) / n
    mean_y = sum(point[1] for point in points) / n
    denominator = sum((point[0] - mean_x) ** 2 for point in points)
    if denominator <= 0:
        return None
    slope = sum(
        (point[0] - mean_x) * (point[1] - mean_y) for point in points
    ) / denominator
    return slope, mean_y - slope * mean_x


def _atr_series(rows: list[list[float]], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(rows)
    queue: list[float] = []
    total = 0.0
    for i in range(1, len(rows)):
        tr = max(
            rows[i][2] - rows[i][3],
            abs(rows[i][2] - rows[i - 1][4]),
            abs(rows[i][3] - rows[i - 1][4]),
        )
        queue.append(tr)
        total += tr
        if len(queue) > period:
            total -= queue.pop(0)
        if len(queue) == period:
            out[i] = total / period
    return out


def _walk(
    rows: list[list[float]],
    entry_index: int,
    side: str,
    entry: float,
    stop: float,
    target_r: float,
    max_hold: int = 48,
) -> tuple[float, int]:
    risk = abs(stop - entry)
    target = entry - target_r * risk if side == "short" else entry + target_r * risk
    final_index = min(entry_index + max_hold, len(rows) - 1)
    for j in range(entry_index + 1, final_index + 1):
        # Conservative same-bar ambiguity: stop is checked before target.
        if side == "short":
            if rows[j][2] >= stop:
                return -1.0, j
            if rows[j][3] <= target:
                return target_r, j
        else:
            if rows[j][3] <= stop:
                return -1.0, j
            if rows[j][2] >= target:
                return target_r, j
    exit_price = rows[final_index][4]
    result = (
        (entry - exit_price) / risk
        if side == "short"
        else (exit_price - entry) / risk
    )
    return result, final_index


def _candidates(symbol: str, rows: list[list[float]]) -> list[Candidate]:
    pivots_high, pivots_low = _all_pivots(rows)
    atr = _atr_series(rows)
    out: list[Candidate] = []
    for i in range(140, len(rows) - 49):
        current_atr = atr[i]
        if current_atr is None or current_atr <= 0:
            continue
        close = rows[i][4]
        open_price = rows[i][1]
        candle_range = rows[i][2] - rows[i][3]
        if candle_range <= 0 or abs(close - open_price) < 0.18 * candle_range:
            continue
        r3 = close / rows[i - 3][4] - 1.0 if rows[i - 3][4] > 0 else 0.0
        for side, pivots in (("short", pivots_high), ("long", pivots_low)):
            if side == "short" and close >= open_price:
                continue
            if side == "long" and close <= open_price:
                continue
            points = [point for point in pivots if point[0] <= i - 3][-2:]
            if len(points) < 2 or i - points[0][0] > 120:
                continue
            fitted = _fit(points)
            if fitted is None:
                continue
            slope, intercept = fitted
            level = slope * i + intercept
            if abs(close - level) > 0.40 * current_atr:
                continue
            if any(
                (side == "short" and rows[k][4] > slope * k + intercept)
                or (side == "long" and rows[k][4] < slope * k + intercept)
                for k in range(points[0][0], i)
            ):
                continue
            stop = level + current_atr if side == "short" else level - current_atr
            risk = abs(stop - close)
            if risk <= 0 or close <= 0:
                continue
            result_2, exit_2 = _walk(rows, i, side, close, stop, 2.0)
            result_3, exit_3 = _walk(rows, i, side, close, stop, 3.0)
            out.append(Candidate(
                symbol=symbol,
                entry_index=i,
                entry_ts=int(rows[i][0]),
                side=side,
                a3=(r3 <= 0 if side == "short" else r3 >= 0),
                risk_pct=risk / close,
                r_2=result_2,
                exit_2=exit_2,
                r_3=result_3,
                exit_3=exit_3,
            ))
    return out


def _non_overlapping(candidates: list[Candidate], target_r: int) -> list[Candidate]:
    kept: list[Candidate] = []
    last_exit: dict[str, int] = {}
    for candidate in sorted(candidates, key=lambda value: (value.entry_ts, value.symbol)):
        if candidate.entry_index <= last_exit.get(candidate.symbol, -1):
            continue
        kept.append(candidate)
        last_exit[candidate.symbol] = (
            candidate.exit_2 if target_r == 2 else candidate.exit_3
        )
    return kept


def _profit_factor(values: list[float]) -> float:
    gains = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    return gains / losses if losses > 0 else math.inf


def _summary(candidates: list[Candidate], target_r: int, cost_bps: float) -> dict:
    gross = [value.r_2 if target_r == 2 else value.r_3 for value in candidates]
    net = [
        result - (cost_bps / 10_000.0) / value.risk_pct
        for value, result in zip(candidates, gross)
    ]
    if not net:
        return {"n": 0}
    half = len(net) // 2
    mean = statistics.mean(net)
    stdev = statistics.stdev(net) if len(net) > 1 else 0.0
    folds = []
    for i in range(4):
        part = net[i * len(net) // 4:(i + 1) * len(net) // 4]
        folds.append(round(statistics.mean(part), 5) if part else None)
    return {
        "n": len(net),
        "expectancy_r": round(mean, 6),
        "t_stat": round(mean / (stdev / math.sqrt(len(net))), 3) if stdev > 0 else None,
        "profit_factor": round(_profit_factor(net), 4),
        "win_rate_pct": round(sum(value > 0 for value in net) / len(net) * 100, 2),
        "median_risk_pct": round(statistics.median(
            value.risk_pct for value in candidates
        ) * 100, 4),
        "half_expectancy_r": [
            round(statistics.mean(net[:half]), 6) if half else None,
            round(statistics.mean(net[half:]), 6) if net[half:] else None,
        ],
        "fold_expectancy_r": folds,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data_cache")
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
    )
    parser.add_argument(
        "--out",
        default="reports/research/att1_a3_3r_actual_universe_audit_20260726.json",
    )
    args = parser.parse_args()

    data_dir = ROOT / args.data_dir
    symbols = tuple(
        value.strip().upper() for value in args.symbols.split(",") if value.strip()
    )
    sources: dict[str, dict] = {}
    h1_by_symbol: dict[str, list[list[float]]] = {}
    for symbol in symbols:
        path = _widest_cache(symbol, data_dir)
        rows = _load_m5(path)
        sources[symbol] = {
            "path": str(path.relative_to(ROOT)),
            "sha256": _sha256(path),
            "m5_rows": len(rows),
            "first_ts": int(rows[0][0]),
            "last_ts": int(rows[-1][0]),
        }
        h1_by_symbol[symbol] = _to_h1(rows)

    common_start = max(rows[0][0] for rows in h1_by_symbol.values())
    common_end = min(rows[-1][0] for rows in h1_by_symbol.values())
    all_candidates: list[Candidate] = []
    for symbol, rows in h1_by_symbol.items():
        aligned = [row for row in rows if common_start <= row[0] <= common_end]
        all_candidates.extend(_candidates(symbol, aligned))

    matrix: list[dict] = []
    for guard in ("none", "A3"):
        for side in ("all", "short", "long"):
            selected = [
                value for value in all_candidates
                if (guard == "none" or value.a3)
                and (side == "all" or value.side == side)
            ]
            for target_r in (2, 3):
                independent = _non_overlapping(selected, target_r)
                for cost_bps in COST_BPS:
                    row = {
                        "guard": guard,
                        "side": side,
                        "target_r": target_r,
                        "round_trip_cost_bps": cost_bps,
                        "overlap_policy": "one_open_position_per_symbol",
                    }
                    row.update(_summary(independent, target_r, cost_bps))
                    matrix.append(row)

    maker_passes = [
        row for row in matrix
        if row["round_trip_cost_bps"] == 4.0
        and row.get("n", 0) >= 60
        and row.get("expectancy_r", 0) > 0
        and all(value is not None and value > 0 for value in row["half_expectancy_r"])
        and sum(value is not None and value > 0 for value in row["fold_expectancy_r"]) >= 3
    ]
    taker_passes = [
        row for row in matrix
        if row["round_trip_cost_bps"] == 11.0
        and row.get("n", 0) >= 60
        and row.get("expectancy_r", 0) > 0
        and all(value is not None and value > 0 for value in row["half_expectancy_r"])
        and sum(value is not None and value > 0 for value in row["fold_expectancy_r"]) >= 3
    ]
    payload = {
        "schema_id": "att1_a3_3r_actual_universe_audit_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "exact_live_att1_replay": False,
        "model": "claude_h1_trendline_geometry_proxy",
        "symbols": list(symbols),
        "common_window": {
            "start_ms": int(common_start),
            "end_ms": int(common_end),
            "start_utc": datetime.fromtimestamp(
                common_start / 1000, timezone.utc
            ).isoformat(),
            "end_utc": datetime.fromtimestamp(
                common_end / 1000, timezone.utc
            ).isoformat(),
        },
        "sources": sources,
        "raw_candidate_count": len(all_candidates),
        "matrix": matrix,
        "gate": {
            "maker_pass_count": len(maker_passes),
            "taker_pass_count": len(taker_passes),
            "maker_passes": maker_passes,
            "taker_passes": taker_passes,
            "promotion": "REPAIR_EXACT_ATT1_REPLAY",
            "binding_reason": (
                "This audit uses Claude's proxy geometry, not the live ATT1 "
                "entry implementation. A passing row can justify an exact "
                "ATT1 challenger replay, never a live parameter change."
            ),
        },
    }
    output = ROOT / args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    print(f"symbols={len(symbols)} candidates={len(all_candidates)}")
    print(
        f"window={payload['common_window']['start_utc']}.."
        f"{payload['common_window']['end_utc']}"
    )
    print(
        f"maker_passes={len(maker_passes)} taker_passes={len(taker_passes)} "
        f"out={output.relative_to(ROOT)}"
    )
    for row in matrix:
        if (
            row["guard"] == "A3"
            and row["side"] in {"all", "short"}
            and row["round_trip_cost_bps"] in {4.0, 11.0}
        ):
            print(
                f"A3 {row['side']:>5} {row['target_r']}R "
                f"cost={row['round_trip_cost_bps']:>4.1f}bps "
                f"n={row.get('n', 0):>4} exp={row.get('expectancy_r')} "
                f"halves={row.get('half_expectancy_r')} "
                f"folds={row.get('fold_expectancy_r')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
