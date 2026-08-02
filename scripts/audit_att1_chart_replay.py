#!/usr/bin/env python3
"""Causal chart-level replay for ATT1 trades.

Aggregate PnL cannot prove that the level shown on a chart caused the entry.
This audit freezes the exact information available at signal time, rebuilds
the setup geometry, measures the later path in R, and emits both machine
evidence and a human-reviewable HTML atlas.

New backtest ledgers contain the immutable entry plan.  Older ledgers remain
auditable, but reconstructed timestamps/stops are explicitly marked as such
and can never qualify as exact-plan evidence.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.att1_geometry_v2 import evaluate_att1_short_geometry_v2
from bot.chart_geometry import _atr_from_rows
from bot.geometry_cache import aggregate_rows, load_cache_rows
from bot.position_geometry import parse_signal_geometry
from bot.sloped_level_snapshot_v1 import (
    SlopedLevelConfigV1,
    build_sloped_level_snapshot_v1,
)


HOUR_MS = 3_600_000
FIVE_MIN_MS = 300_000


def _f(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float(default)
    return result if math.isfinite(result) else float(default)


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _closed_prefix(rows: Sequence[Sequence[float]], as_of_ms: int, interval_ms: int) -> list[list[float]]:
    return [list(row) for row in rows if int(row[0]) + interval_ms <= int(as_of_ms)]


def _load_audit_rows(symbol: str, interval: str, cache_dir: Path) -> list[list[float]]:
    """Load the broadest local coverage instead of accepting a partial direct TF.

    ``geometry_cache.load_rows`` intentionally prefers direct higher-timeframe
    files.  That is fast for current charts but unsafe for a historical atlas:
    one recent H1 shard can hide older 5m coverage.  Merge both sources by
    timestamp and prefer direct rows where they overlap.
    """
    direct = load_cache_rows(symbol, interval, data_cache_dir=cache_dir)
    if interval == "5":
        return direct
    target_minutes = {"60": 60, "240": 240}.get(str(interval))
    if target_minutes is None:
        return direct
    base = load_cache_rows(symbol, "5", data_cache_dir=cache_dir)
    derived = aggregate_rows(base, target_minutes) if base else []
    merged = {int(row[0]): list(row) for row in derived}
    merged.update({int(row[0]): list(row) for row in direct})
    return [merged[ts] for ts in sorted(merged)]


def _window(rows: Sequence[Sequence[float]], start_ms: int, end_ms: int) -> list[list[float]]:
    return [list(row) for row in rows if int(start_ms) <= int(row[0]) < int(end_ms)]


def _grid_quality(rows: Sequence[Sequence[float]], interval_ms: int) -> dict[str, Any]:
    timestamps = [int(row[0]) for row in rows]
    duplicate_count = len(timestamps) - len(set(timestamps))
    gaps = [
        timestamps[index] - timestamps[index - 1]
        for index in range(1, len(timestamps))
        if timestamps[index] - timestamps[index - 1] != interval_ms
    ]
    return {
        "rows": len(rows),
        "duplicate_timestamps": duplicate_count,
        "gap_count": len(gaps),
        "max_gap_ms": max(gaps, default=0),
        "contiguous": bool(rows) and duplicate_count == 0 and not gaps,
    }


def _risk_plan(trade: dict[str, str], prefix_h1: Sequence[Sequence[float]]) -> tuple[float, str, bool]:
    exact_sl = _f(trade.get("initial_sl"))
    if exact_sl > 0:
        return exact_sl, "ledger_initial_sl", True
    parsed = parse_signal_geometry(trade.get("signal_reason") or trade.get("reason") or "")
    trendline = _f(parsed.get("primary_level"))
    atr = _atr_from_rows(list(prefix_h1), 14) if prefix_h1 else 0.0
    side = str(trade.get("side") or "").lower()
    if trendline > 0 and atr > 0:
        reconstructed = trendline - 1.10 * atr if side == "long" else trendline + 1.10 * atr
        return reconstructed, "reconstructed_att1_default_1.10atr", False
    return 0.0, "missing", False


def _forward_path(
    rows: Sequence[Sequence[float]],
    *,
    entry_ts: int,
    entry: float,
    sl: float,
    side: str,
    forward_hours: int,
) -> dict[str, Any]:
    risk = (entry - sl) if side == "long" else (sl - entry)
    future = _window(rows, entry_ts, entry_ts + int(forward_hours) * HOUR_MS)
    quality = _grid_quality(future, FIVE_MIN_MS)
    expected = max(1, int(forward_hours) * 12)
    coverage = min(1.0, len(future) / expected)
    if risk <= 0 or not future:
        return {
            "risk_per_unit": risk,
            "mfe_r": None,
            "mae_r": None,
            "first_hit": "invalid_or_missing_path",
            "bars": len(future),
            "coverage": coverage,
            **quality,
        }

    if side == "long":
        mfe_r = max((float(row[2]) - entry) / risk for row in future)
        mae_r = max((entry - float(row[3])) / risk for row in future)
    else:
        mfe_r = max((entry - float(row[3])) / risk for row in future)
        mae_r = max((float(row[2]) - entry) / risk for row in future)

    first_hit = "neither"
    first_half_r_bar = None
    first_one_r_bar = None
    first_stop_bar = None
    for index, row in enumerate(future):
        high, low = float(row[2]), float(row[3])
        favorable_half = high >= entry + 0.5 * risk if side == "long" else low <= entry - 0.5 * risk
        favorable_one = high >= entry + risk if side == "long" else low <= entry - risk
        stop_hit = low <= sl if side == "long" else high >= sl
        if favorable_half and first_half_r_bar is None:
            first_half_r_bar = index
        if favorable_one and first_one_r_bar is None:
            first_one_r_bar = index
        if stop_hit and first_stop_bar is None:
            first_stop_bar = index
        if favorable_one or stop_hit:
            if favorable_one and stop_hit:
                first_hit = "ambiguous_stop_first"
            elif favorable_one:
                first_hit = "+1R"
            else:
                first_hit = "stop"
            break
    return {
        "risk_per_unit": risk,
        "mfe_r": mfe_r,
        "mae_r": mae_r,
        "first_hit": first_hit,
        "first_half_r_bar": first_half_r_bar,
        "first_one_r_bar": first_one_r_bar,
        "first_stop_bar": first_stop_bar,
        "bars": len(future),
        "coverage": coverage,
        **quality,
    }


def _research_class(parsed: dict[str, Any], g2: dict[str, Any]) -> str:
    slope = None
    lines = list(parsed.get("sloped_lines") or [])
    if lines:
        slope = lines[0].get("slope_pct_per_day")
    if slope is not None and _f(slope) > 0:
        return "rising_resistance_separate_family"
    if g2.get("classification") == "horizontal_resistance_rejection":
        return "horizontal_resistance_reaction"
    if g2.get("allowed"):
        return "valid_full_descending_trendline"
    line_quality_blockers = {
        "no_resistance_trendline",
        "insufficient_confirmed_pivots",
        "resistance_not_descending",
        "pivot_fit_too_weak",
        "invalid_or_short_geometry_input",
    }
    blockers = set(g2.get("blockers") or [])
    if not blockers.intersection(line_quality_blockers):
        return "descending_line_pass_execution_or_room_fail"
    return "line_quality_rejected"


def _pf(rows: Iterable[dict[str, Any]]) -> float | str | None:
    pnls = [_f(row.get("pnl")) for row in rows]
    gains = sum(value for value in pnls if value > 0)
    losses = -sum(value for value in pnls if value < 0)
    if losses <= 0:
        return None if gains <= 0 else "inf"
    return gains / losses


def _summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["research_class"])].append(row)
    output = []
    for name, group in sorted(groups.items()):
        mfes = [_f(row["forward"].get("mfe_r"), float("nan")) for row in group]
        maes = [_f(row["forward"].get("mae_r"), float("nan")) for row in group]
        mfes = [value for value in mfes if math.isfinite(value)]
        maes = [value for value in maes if math.isfinite(value)]
        output.append(
            {
                "research_class": name,
                "trades": len(group),
                "net_pnl": sum(_f(row.get("pnl")) for row in group),
                "profit_factor": _pf(group),
                "win_rate": sum(_f(row.get("pnl")) > 0 for row in group) / len(group),
                "median_mfe_r": statistics.median(mfes) if mfes else None,
                "median_mae_r": statistics.median(maes) if maes else None,
                "first_hit_counts": dict(Counter(row["forward"].get("first_hit") for row in group)),
            }
        )
    return output


def _line_price(parsed: dict[str, Any], ts_ms: int, signal_ts: int) -> float | None:
    lines = list(parsed.get("sloped_lines") or [])
    if not lines:
        return None
    projection = _f(lines[0].get("projection_at_signal"))
    slope_pct_day = lines[0].get("slope_pct_per_day")
    if projection <= 0 or slope_pct_day is None:
        return projection or None
    return projection + (int(ts_ms) - int(signal_ts)) / 86_400_000 * projection * _f(slope_pct_day) / 100.0


def _svg_chart(audit: dict[str, Any], h1_rows: Sequence[Sequence[float]]) -> str:
    signal_ts = int(audit["signal_ts"])
    chart_rows = _window(h1_rows, signal_ts - 72 * HOUR_MS, signal_ts + 24 * HOUR_MS)
    if not chart_rows:
        return "<p>OHLC coverage missing.</p>"
    width, height = 920, 360
    left, right, top, bottom = 52, 18, 18, 34
    values = [float(value) for row in chart_rows for value in (row[2], row[3])]
    for key in ("entry_price", "initial_sl"):
        value = _f(audit.get(key))
        if value > 0:
            values.append(value)
    parsed = audit["parsed_geometry"]
    for item in parsed.get("horizontal_levels") or []:
        values.append(_f(item.get("price")))
    for key in ("horizontal_origin", "nearest_support"):
        value = _f(audit["geometry_v2"].get(key))
        if value > 0:
            values.append(value)
    lo, hi = min(values), max(values)
    pad = max((hi - lo) * 0.07, abs(hi) * 0.001)
    lo, hi = lo - pad, hi + pad
    plot_w, plot_h = width - left - right, height - top - bottom
    x0, x1 = int(chart_rows[0][0]), int(chart_rows[-1][0]) + HOUR_MS

    def x(ts: int) -> float:
        return left + (int(ts) - x0) / max(1, x1 - x0) * plot_w

    def y(price: float) -> float:
        return top + (hi - float(price)) / max(1e-12, hi - lo) * plot_h

    pieces = [f'<svg viewBox="0 0 {width} {height}" role="img">']
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        yy = top + plot_h * fraction
        price = hi - (hi - lo) * fraction
        pieces.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{width-right}" y2="{yy:.1f}" class="grid"/>')
        pieces.append(f'<text x="4" y="{yy+4:.1f}" class="axis">{price:.6g}</text>')
    candle_w = max(2.0, plot_w / max(1, len(chart_rows)) * 0.55)
    for row in chart_rows:
        ts, open_, high_, low_, close = int(row[0]), *map(float, row[1:5])
        xx = x(ts + HOUR_MS // 2)
        color = "up" if close >= open_ else "down"
        pieces.append(f'<line x1="{xx:.1f}" y1="{y(high_):.1f}" x2="{xx:.1f}" y2="{y(low_):.1f}" class="{color}"/>')
        yy = min(y(open_), y(close))
        hh = max(1.0, abs(y(open_) - y(close)))
        pieces.append(f'<rect x="{xx-candle_w/2:.1f}" y="{yy:.1f}" width="{candle_w:.1f}" height="{hh:.1f}" class="{color}"/>')
    sx = x(signal_ts)
    pieces.append(f'<line x1="{sx:.1f}" y1="{top}" x2="{sx:.1f}" y2="{top+plot_h}" class="signal"/>')
    for price, klass, label in (
        (_f(audit.get("entry_price")), "entry", "ENTRY"),
        (_f(audit.get("initial_sl")), "stop", "SL"),
        (_f(audit["geometry_v2"].get("horizontal_origin")), "origin", "ORIGIN"),
        (_f(audit["geometry_v2"].get("nearest_support")), "support", "SUPPORT"),
    ):
        if price > 0:
            yy = y(price)
            pieces.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{width-right}" y2="{yy:.1f}" class="{klass}"/>')
            pieces.append(f'<text x="{width-right-72}" y="{yy-4:.1f}" class="label {klass}">{label}</text>')
    line_start = _line_price(parsed, x0, signal_ts)
    line_end = _line_price(parsed, x1, signal_ts)
    if line_start and line_end:
        pieces.append(f'<line x1="{x(x0):.1f}" y1="{y(line_start):.1f}" x2="{x(x1):.1f}" y2="{y(line_end):.1f}" class="trend"/>')
    pieces.append("</svg>")
    return "".join(pieces)


def _html_atlas(audits: list[dict[str, Any]], h1_by_symbol: dict[str, list[list[float]]]) -> str:
    cards = []
    for audit in audits:
        blockers = ", ".join(audit["geometry_v2"].get("blockers") or []) or "none"
        forward = audit["forward"]
        exact = "exact" if audit["exact_plan"] else "reconstructed"
        cards.append(
            "<article>"
            f"<h2>{html.escape(audit['symbol'])} {html.escape(audit['side'])} · {html.escape(audit['research_class'])}</h2>"
            f"<p><b>plan:</b> {exact} · <b>PnL:</b> {audit['pnl']:+.4f} · "
            f"<b>MFE:</b> {forward.get('mfe_r')}R · <b>MAE:</b> {forward.get('mae_r')}R · "
            f"<b>first:</b> {html.escape(str(forward.get('first_hit')))}</p>"
            f"<p><b>geometry blockers:</b> {html.escape(blockers)} · "
            f"<b>path coverage:</b> {forward.get('coverage', 0):.1%}</p>"
            + _svg_chart(audit, h1_by_symbol.get(audit["symbol"], []))
            + "</article>"
        )
    return """<!doctype html><html><head><meta charset="utf-8"><title>ATT1 causal chart replay</title>
<style>body{background:#08101b;color:#dce7f5;font-family:system-ui;margin:24px}article{background:#101a28;border:1px solid #2a3a4d;border-radius:12px;padding:16px;margin:18px 0}h2{font-size:18px}p{color:#aebdd0}.grid{stroke:#243449;stroke-width:1}.axis,.label{fill:#8fa2b8;font-size:11px}.up{fill:#30c77b;stroke:#30c77b}.down{fill:#f05b5b;stroke:#f05b5b}.signal{stroke:#70c8ff;stroke-dasharray:5 4}.entry{stroke:#39bff8}.stop{stroke:#f24f65}.origin{stroke:#ffa928;stroke-dasharray:7 4}.support{stroke:#48d17e;stroke-dasharray:7 4}.trend{stroke:#ffd02e;stroke-width:3}svg{background:#0b1420;border-radius:8px;width:100%;height:auto}</style></head><body><h1>ATT1 causal chart replay</h1>""" + "".join(cards) + "</body></html>"


def audit_trade(
    trade: dict[str, str],
    *,
    h1_rows: list[list[float]],
    m5_rows: list[list[float]],
    forward_hours: int,
) -> dict[str, Any]:
    entry_ts = _i(trade.get("entry_ts"))
    exact_signal_ts = _i(trade.get("signal_ts"))
    signal_ts = exact_signal_ts or max(0, entry_ts - FIVE_MIN_MS)
    prefix = _closed_prefix(h1_rows, signal_ts, HOUR_MS)[-120:]
    entry = _f(trade.get("entry_price"))
    sl, risk_source, exact_sl = _risk_plan(trade, prefix)
    signal_reason = trade.get("signal_reason") or trade.get("reason") or ""
    parsed = parse_signal_geometry(signal_reason)
    if str(trade.get("side") or "").lower() == "short" and entry > 0 and sl > entry:
        g2_obj = evaluate_att1_short_geometry_v2(prefix, entry=entry, sl=sl)
        g2 = g2_obj.as_dict()
    else:
        g2 = {
            "allowed": False,
            "classification": "unsupported_side_or_invalid_plan",
            "blockers": ["unsupported_side_or_invalid_plan"],
        }
    strict = build_sloped_level_snapshot_v1(
        str(trade.get("symbol") or "").upper(),
        "resistance",
        HOUR_MS,
        h1_rows,
        as_of_ms=signal_ts,
        cfg=SlopedLevelConfigV1(
            lookback_bars=120,
            pivot_left=3,
            pivot_right=3,
            min_confirmed_pivots=3,
            min_r_squared=0.80,
        ),
    )
    strict_payload = {
        "status": strict.status,
        "reason": strict.reason,
        "closed_bars": strict.closed_bars,
        "confirmed_pivots": strict.confirmed_pivots,
        "input_sha256": strict.input_sha256,
        "snapshot": asdict(strict.snapshot) if strict.snapshot is not None else None,
    }
    forward = _forward_path(
        m5_rows,
        entry_ts=entry_ts,
        entry=entry,
        sl=sl,
        side=str(trade.get("side") or "").lower(),
        forward_hours=forward_hours,
    )
    exact_plan = bool(exact_signal_ts > 0 and exact_sl)
    audit = {
        "strategy": trade.get("strategy") or "",
        "symbol": str(trade.get("symbol") or "").upper(),
        "side": str(trade.get("side") or "").lower(),
        "signal_ts": signal_ts,
        "entry_ts": entry_ts,
        "exit_ts": _i(trade.get("exit_ts")),
        "entry_price": entry,
        "initial_sl": sl,
        "risk_source": risk_source,
        "exact_plan": exact_plan,
        "pnl": _f(trade.get("pnl")),
        "outcome": trade.get("outcome") or "",
        "signal_reason": signal_reason,
        "parsed_geometry": parsed,
        "geometry_v2": g2,
        "strict_snapshot": strict_payload,
        "prefix_quality": _grid_quality(prefix, HOUR_MS),
        "forward": forward,
    }
    audit["research_class"] = _research_class(parsed, g2)
    audit["usable_for_exact_plan_claim"] = bool(
        exact_plan
        and audit["prefix_quality"]["contiguous"]
        and forward.get("coverage", 0.0) >= 0.95
        and forward.get("duplicate_timestamps", 0) == 0
        and forward.get("gap_count", 0) == 0
    )
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades-csv", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--cache-dir", default="data_cache")
    parser.add_argument("--forward-hours", type=int, default=24)
    parser.add_argument("--strategy-contains", default="trendline_touch")
    args = parser.parse_args()

    trades_path = Path(args.trades_csv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with trades_path.open(encoding="utf-8", newline="") as handle:
        raw_trades = list(csv.DictReader(handle))
    needle = str(args.strategy_contains or "").lower()
    trades = [row for row in raw_trades if needle in str(row.get("strategy") or "").lower()]
    if not trades:
        raise SystemExit("no matching trades")

    keys = [(row.get("strategy"), row.get("symbol"), row.get("side"), row.get("entry_ts")) for row in trades]
    duplicate_trade_keys = len(keys) - len(set(keys))
    symbols = sorted({str(row.get("symbol") or "").upper() for row in trades})
    cache_dir = Path(args.cache_dir)
    h1_by_symbol = {symbol: _load_audit_rows(symbol, "60", cache_dir) for symbol in symbols}
    m5_by_symbol = {symbol: _load_audit_rows(symbol, "5", cache_dir) for symbol in symbols}
    audits = [
        audit_trade(
            trade,
            h1_rows=h1_by_symbol.get(str(trade.get("symbol") or "").upper(), []),
            m5_rows=m5_by_symbol.get(str(trade.get("symbol") or "").upper(), []),
            forward_hours=max(1, int(args.forward_hours)),
        )
        for trade in trades
    ]
    summaries = _summaries(audits)
    exact_count = sum(bool(row["usable_for_exact_plan_claim"]) for row in audits)
    quality = {
        "source_trades": len(trades),
        "duplicate_trade_keys": duplicate_trade_keys,
        "symbols": symbols,
        "exact_plan_rows": sum(bool(row["exact_plan"]) for row in audits),
        "usable_for_exact_plan_claim": exact_count,
        "reconstructed_rows": sum(not bool(row["exact_plan"]) for row in audits),
        "minimum_forward_coverage": min((_f(row["forward"].get("coverage")) for row in audits), default=0.0),
        "verdict": "PASS_EXACT" if exact_count == len(audits) and duplicate_trade_keys == 0 else "DIAGNOSTIC_ONLY",
    }
    payload = {
        "schema": "att1_causal_chart_replay_v1",
        "source": str(trades_path),
        "forward_hours": max(1, int(args.forward_hours)),
        "data_quality": quality,
        "summaries": summaries,
        "trades": audits,
    }
    (out_dir / "audit.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with (out_dir / "audit.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = [
            "symbol", "side", "signal_ts", "entry_ts", "entry_price", "initial_sl", "risk_source",
            "exact_plan", "usable_for_exact_plan_claim", "research_class", "pnl", "outcome", "g2_allowed",
            "g2_classification", "g2_blockers", "strict_status", "strict_reason", "mfe_r", "mae_r",
            "first_hit", "forward_coverage",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in audits:
            writer.writerow(
                {
                    "symbol": row["symbol"], "side": row["side"], "signal_ts": row["signal_ts"],
                    "entry_ts": row["entry_ts"], "entry_price": row["entry_price"], "initial_sl": row["initial_sl"],
                    "risk_source": row["risk_source"], "exact_plan": row["exact_plan"],
                    "usable_for_exact_plan_claim": row["usable_for_exact_plan_claim"],
                    "research_class": row["research_class"], "pnl": row["pnl"], "outcome": row["outcome"],
                    "g2_allowed": row["geometry_v2"].get("allowed"),
                    "g2_classification": row["geometry_v2"].get("classification"),
                    "g2_blockers": "|".join(row["geometry_v2"].get("blockers") or []),
                    "strict_status": row["strict_snapshot"]["status"],
                    "strict_reason": row["strict_snapshot"]["reason"],
                    "mfe_r": row["forward"].get("mfe_r"), "mae_r": row["forward"].get("mae_r"),
                    "first_hit": row["forward"].get("first_hit"),
                    "forward_coverage": row["forward"].get("coverage"),
                }
            )
    md = [
        "# ATT1 causal chart replay",
        "",
        f"- Source trades: **{len(trades)}**",
        f"- Data verdict: **{quality['verdict']}**",
        f"- Exact-plan rows: **{quality['exact_plan_rows']}**",
        f"- Reconstructed legacy rows: **{quality['reconstructed_rows']}**",
        f"- Exact rows usable for claims: **{quality['usable_for_exact_plan_claim']}**",
        "",
        "Legacy reconstructed rows are visual diagnostics only. They cannot promote a strategy.",
        "",
        "| class | trades | net | PF | win rate | median MFE R | median MAE R |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for summary in summaries:
        pf = summary["profit_factor"]
        pf_text = "inf" if pf == "inf" else ("-" if pf is None else f"{pf:.3f}")
        md.append(
            f"| {summary['research_class']} | {summary['trades']} | {summary['net_pnl']:+.4f} | {pf_text} | "
            f"{summary['win_rate']:.1%} | {summary['median_mfe_r'] if summary['median_mfe_r'] is not None else '-'} | "
            f"{summary['median_mae_r'] if summary['median_mae_r'] is not None else '-'} |"
        )
    (out_dir / "README.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (out_dir / "atlas.html").write_text(_html_atlas(audits, h1_by_symbol), encoding="utf-8")
    print(json.dumps({"out_dir": str(out_dir), "data_quality": quality, "summaries": summaries}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
