#!/usr/bin/env python3
"""Build a first-pass forensic report for live/backtest crypto trades.

The report answers the practical post-trade questions we keep asking:
- did the trade ever move in our favor before exit (MFE)?
- how far did it move against us (MAE)?
- after a stop, did price quickly reverse, or did the idea keep failing?
- after a take-profit/trail, did price keep going, meaning exits may be too tight?

It intentionally uses only local files: backtest trades.csv, live_trade_events.jsonl
and cached Bybit klines under .cache/klines.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import re
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


@dataclass
class Trade:
    source: str
    strategy: str
    symbol: str
    side: str
    entry_ts_ms: int
    exit_ts_ms: int
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    fees: float
    outcome: str
    reason: str
    sl_price: float | None = None
    tp_price: float | None = None


@dataclass
class Forensic:
    source: str
    strategy: str
    symbol: str
    side: str
    entry_utc: str
    exit_utc: str
    hold_min: float
    pnl: float
    outcome: str
    reason: str
    entry_to_exit_pct: float
    mfe_pct: float | None
    mae_pct: float | None
    mfe_r: float | None
    mae_r: float | None
    post_exit_6bar_pct: float | None
    candles: int
    post_candles: int
    verdict: str


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return None
        return out
    except Exception:
        return None


def _first_pipe_float(value: Any) -> float | None:
    raw = str(value or "").split("|", 1)[0].strip()
    return _optional_float(raw)


def _ts_ms(value: Any) -> int:
    try:
        raw = int(float(value))
    except Exception:
        return 0
    return raw * 1000 if raw and raw < 10_000_000_000 else raw


def _utc(ms: int) -> str:
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _signed_side(side: str) -> int:
    s = str(side or "").strip().lower()
    return -1 if s in {"short", "sell"} else 1


def _norm_side(side: str) -> str:
    return "short" if _signed_side(side) < 0 else "long"


def _load_backtest_csv(path: Path) -> list[Trade]:
    out: list[Trade] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out.append(
                Trade(
                    source=f"backtest:{path.parent.name}",
                    strategy=(row.get("strategy") or "").strip(),
                    symbol=(row.get("symbol") or "").strip().upper(),
                    side=_norm_side(row.get("side") or ""),
                    entry_ts_ms=_ts_ms(row.get("entry_ts")),
                    exit_ts_ms=_ts_ms(row.get("exit_ts")),
                    entry_price=_float(row.get("entry_price")),
                    exit_price=_float(row.get("exit_price")),
                    qty=_float(row.get("qty")),
                    pnl=_float(row.get("pnl")),
                    fees=_float(row.get("fees")),
                    outcome=(row.get("outcome") or "").strip().lower(),
                    reason=(row.get("reason") or "").strip(),
                    sl_price=_optional_float(row.get("sl_price") or row.get("initial_sl")),
                    tp_price=(
                        _optional_float(row.get("tp_price"))
                        or _first_pipe_float(row.get("tp_prices"))
                    ),
                )
            )
    return [t for t in out if t.symbol and t.entry_ts_ms and t.exit_ts_ms and t.entry_price > 0]


def _load_live_events(path: Path, days: int) -> list[Trade]:
    if not path.exists():
        return []
    cutoff_ms = int((time.time() - days * 86400) * 1000) if days > 0 else 0
    rows: list[dict[str, Any]] = []
    fills_by_order: dict[str, dict[str, Any]] = {}
    submits_by_order: dict[str, dict[str, Any]] = {}
    recent_entries: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            rows.append(row)
            event = str(row.get("event") or "").strip().lower()
            order_id = str(row.get("entry_order_id") or "").strip()
            if order_id and event == "entry_filled":
                fills_by_order[order_id] = row
            elif order_id and event == "order_submitted":
                submits_by_order[order_id] = row
            if event in {"entry_filled", "order_submitted"}:
                key = (
                    str(row.get("symbol") or "").strip().upper(),
                    _norm_side(row.get("side") or ""),
                    str(row.get("strategy") or "").strip(),
                )
                recent_entries[key].append(row)

    def _entry_for_close(close: dict[str, Any]) -> dict[str, Any] | None:
        order_id = str(close.get("entry_order_id") or "").strip()
        if order_id:
            return fills_by_order.get(order_id) or submits_by_order.get(order_id)
        key = (
            str(close.get("symbol") or "").strip().upper(),
            _norm_side(close.get("side") or ""),
            str(close.get("strategy") or "").strip(),
        )
        close_ts = _ts_ms(close.get("ts"))
        candidates = [
            row for row in recent_entries.get(key, [])
            if 0 < _ts_ms(row.get("ts")) <= close_ts
        ]
        return max(candidates, key=lambda row: _ts_ms(row.get("ts")), default=None)

    out: list[Trade] = []
    for row in rows:
        if str(row.get("event") or "").strip().lower() != "close":
            continue
        ts = _ts_ms(row.get("ts"))
        if cutoff_ms and ts < cutoff_ms:
            continue
        entry_row = _entry_for_close(row) or {}
        submit_row = submits_by_order.get(str(row.get("entry_order_id") or "").strip(), {})
        entry = _float(
            entry_row.get("fill_price")
            or entry_row.get("entry_price")
            or row.get("entry_price")
        )
        exit_price = _float(row.get("exit_price") or row.get("fill_price"))
        entry_ts = _ts_ms(entry_row.get("ts"))
        reason = str(
            row.get("signal_reason")
            or entry_row.get("signal_reason")
            or submit_row.get("signal_reason")
            or ""
        ).strip()
        out.append(
            Trade(
                source=f"live:{path.name}",
                strategy=(row.get("strategy") or "").strip(),
                symbol=(row.get("symbol") or "").strip().upper(),
                side=_norm_side(row.get("side") or ""),
                entry_ts_ms=entry_ts,
                exit_ts_ms=ts,
                entry_price=entry,
                exit_price=exit_price,
                qty=_float(row.get("qty") or entry_row.get("qty")),
                pnl=_float(row.get("pnl")),
                fees=_float(row.get("fees")),
                outcome=(row.get("close_reason") or "").strip().lower(),
                reason=reason,
                sl_price=_optional_float(row.get("sl_price") or entry_row.get("sl_price")),
                tp_price=_optional_float(row.get("tp_price") or entry_row.get("tp_price")),
            )
        )
    # Legacy close-only journals do not carry entry timestamps. Keep the old
    # conservative window only as an explicit fallback for those records.
    for t in out:
        if not t.entry_ts_ms and t.exit_ts_ms:
            t.entry_ts_ms = t.exit_ts_ms - 6 * 60 * 60 * 1000
    return [t for t in out if t.symbol and t.exit_ts_ms and t.entry_price > 0 and t.exit_price > 0]


_CANDLE_MEMO: dict[tuple[str, str, str, int, int], list[list[float]]] = {}
_CACHE_FILE_MEMO: dict[str, tuple[list[int], list[list[float]]]] = {}


def _row_ts(row: Any) -> int:
    if isinstance(row, dict):
        for key in ("ts", "start_ms", "startTime", "start_time", "t"):
            if key in row:
                return _ts_ms(row.get(key))
        return 0
    if isinstance(row, (list, tuple)) and row:
        return _ts_ms(row[0])
    return 0


def _norm_candle(row: Any) -> list[float] | None:
    if isinstance(row, dict):
        ts = _row_ts(row)
        o = _optional_float(row.get("o", row.get("open")))
        h = _optional_float(row.get("h", row.get("high")))
        l = _optional_float(row.get("l", row.get("low")))
        c = _optional_float(row.get("c", row.get("close")))
        v = _float(row.get("v", row.get("volume")), 0.0)
    elif isinstance(row, (list, tuple)) and len(row) >= 5:
        ts = _row_ts(row)
        o = _optional_float(row[1])
        h = _optional_float(row[2])
        l = _optional_float(row[3])
        c = _optional_float(row[4])
        v = _float(row[5], 0.0) if len(row) > 5 else 0.0
    else:
        return None
    if not ts or o is None or h is None or l is None or c is None:
        return None
    return [float(ts), o, h, l, c, v]


def _cache_file_overlaps(path: Path, symbol: str, interval: str, start_ms: int, end_ms: int) -> bool:
    rng = _cache_file_range(path, symbol, interval)
    if rng is None:
        return True
    file_start, file_end = rng
    return max(file_start, start_ms) <= min(file_end, end_ms)


def _cache_file_range(path: Path, symbol: str, interval: str) -> tuple[int, int] | None:
    stem = path.stem
    prefix = f"{symbol}_{interval}_"
    if not stem.startswith(prefix):
        return None
    parts = stem[len(prefix) :].split("_")
    if len(parts) < 2:
        return None
    try:
        file_start = int(float(parts[0]))
        file_end = int(float(parts[1]))
    except Exception:
        return None
    # backtest.bybit_data uses compact UTC dates in cache names, while older
    # research caches use epoch milliseconds. Normalize both conventions.
    if len(parts[0]) == 8 and len(parts[1]) == 8:
        try:
            file_start = int(datetime.strptime(parts[0], "%Y%m%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
            # The compact end token records only the UTC date even when the
            # requested range ended later that day. Treat it as inclusive and
            # let the actual candle timestamps perform the precise filtering.
            file_end = int(datetime.strptime(parts[1], "%Y%m%d").replace(tzinfo=timezone.utc).timestamp() * 1000) + 86_400_000
        except Exception:
            return None
    return file_start, file_end


def _best_cache_paths(cache_dir: Path, symbol: str, interval: str, start_ms: int, end_ms: int) -> list[Path]:
    candidates: list[tuple[int, int, int, int, Path]] = []
    unknown: list[Path] = []
    for path in sorted(cache_dir.glob(f"{symbol}_{interval}_*.json")):
        rng = _cache_file_range(path, symbol, interval)
        if rng is None:
            unknown.append(path)
            continue
        file_start, file_end = rng
        overlap = max(0, min(file_end, end_ms) - max(file_start, start_ms))
        if overlap <= 0:
            continue
        contains = int(file_start <= start_ms and file_end >= end_ms)
        span = max(1, file_end - file_start)
        size = path.stat().st_size
        # Prefer one file that fully contains the bucket, and among those the
        # narrowest/smallest slice. This avoids parsing duplicate multi-year
        # cache files for every trade.
        candidates.append((-contains, -overlap, span, size, path))
    if candidates:
        candidates.sort()
        return [candidates[0][-1]]
    return [p for p in unknown if _cache_file_overlaps(p, symbol, interval, start_ms, end_ms)]


def _load_symbol_candles(cache_dir: Path, symbol: str, interval: str, start_ms: int, end_ms: int) -> list[list[float]]:
    # Bucket the memo to one-day windows so nearby trades reuse parsed candles
    # without accidentally loading a full multi-year cache for every symbol.
    day_ms = 86_400_000
    bucket_start = (start_ms // day_ms) * day_ms
    bucket_end = ((end_ms // day_ms) + 1) * day_ms
    key = (str(cache_dir.resolve()), symbol, interval, bucket_start, bucket_end)
    if key in _CANDLE_MEMO:
        return _CANDLE_MEMO[key]
    rows_by_ts: dict[int, list[float]] = {}
    for path in _best_cache_paths(cache_dir, symbol, interval, bucket_start, bucket_end):
        cache_key = str(path)
        if cache_key not in _CACHE_FILE_MEMO:
            file_rows: list[list[float]] = []
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                raw = []
            if isinstance(raw, list):
                for item in raw:
                    candle = _norm_candle(item)
                    if candle:
                        file_rows.append(candle)
            file_rows.sort(key=lambda r: int(r[0]))
            _CACHE_FILE_MEMO[cache_key] = ([int(r[0]) for r in file_rows], file_rows)
        file_times, file_rows = _CACHE_FILE_MEMO[cache_key]
        left = bisect.bisect_left(file_times, bucket_start)
        right = bisect.bisect_right(file_times, bucket_end)
        for candle in file_rows[left:right]:
            rows_by_ts[int(candle[0])] = candle
    rows = [rows_by_ts[k] for k in sorted(rows_by_ts) if bucket_start <= k <= bucket_end]
    _CANDLE_MEMO[key] = rows
    return rows


def _window(rows: Iterable[list[float]], start_ms: int, end_ms: int) -> list[list[float]]:
    return [r for r in rows if start_ms <= int(r[0]) <= end_ms]


def _signed_pct(side: str, entry: float, price: float) -> float:
    if entry <= 0 or price <= 0:
        return 0.0
    return _signed_side(side) * (price - entry) / entry * 100.0


def _risk_pct(trade: Trade) -> float | None:
    if trade.sl_price is None or trade.entry_price <= 0:
        return None
    raw = abs(trade.entry_price - trade.sl_price) / trade.entry_price * 100.0
    return raw if raw > 0 else None


def _classify(
    trade: Trade,
    mfe_pct: float | None,
    mae_pct: float | None,
    post_pct: float | None,
    candles: int,
    risk_pct: float | None = None,
) -> str:
    outcome = (trade.outcome or trade.reason or "").lower()
    if candles <= 0:
        return "missing_candles"
    mfe_r = mfe_pct / risk_pct if risk_pct and mfe_pct is not None else None
    mae_r = mae_pct / risk_pct if risk_pct and mae_pct is not None else None
    post_r = post_pct / risk_pct if risk_pct and post_pct is not None else None
    explicit_stop = outcome in {"sl", "stop", "stop_loss"} or outcome.startswith("bounce_sl")
    explicit_take = outcome in {"tp", "take_profit"} or outcome.startswith("bounce_tp")
    if explicit_stop or trade.pnl < 0:
        if post_r is not None and post_r > 0.45:
            return "stop_then_reversed"
        if mae_r is not None and mae_r < -1.25 and (mfe_r is None or mfe_r < 0.35):
            return "entry_failed_fast"
        if mfe_r is not None and mfe_r > 0.75:
            return "gave_back_profit"
        return "stopped_no_reversal_yet"
    if explicit_take or trade.pnl > 0:
        if post_r is not None and post_r > 0.75:
            return "tp_then_continued"
        if mfe_r is not None and mfe_r < 0.35:
            return "thin_win"
        return "clean_win"
    if mfe_r is not None and mfe_r < 0.25 and mae_r is not None and mae_r < -0.75:
        return "no_followthrough"
    return "neutral"


def analyze_trade(trade: Trade, cache_dir: Path, interval: str, post_bars: int) -> Forensic:
    fetch_start_ms = max(0, trade.entry_ts_ms - 30 * 60 * 1000)
    exit_ms = trade.exit_ts_ms
    post_ms = exit_ms + post_bars * int(interval) * 60 * 1000
    rows = _load_symbol_candles(cache_dir, trade.symbol, interval, fetch_start_ms, post_ms)
    trade_rows = _window(rows, trade.entry_ts_ms, exit_ms)
    post_rows = _window(rows, exit_ms, post_ms)

    mfe_pct = None
    mae_pct = None
    if trade_rows:
        highs = [r[2] for r in trade_rows]
        lows = [r[3] for r in trade_rows]
        if _signed_side(trade.side) > 0:
            mfe_pct = _signed_pct(trade.side, trade.entry_price, max(highs))
            mae_pct = _signed_pct(trade.side, trade.entry_price, min(lows))
        else:
            mfe_pct = _signed_pct(trade.side, trade.entry_price, min(lows))
            mae_pct = _signed_pct(trade.side, trade.entry_price, max(highs))

    post_pct = None
    if post_rows:
        closes = [r[4] for r in post_rows]
        if _signed_side(trade.side) > 0:
            post_pct = _signed_pct(trade.side, trade.exit_price, max(closes))
        else:
            post_pct = _signed_pct(trade.side, trade.exit_price, min(closes))

    risk = _risk_pct(trade)
    mfe_r = (mfe_pct / risk) if (risk and mfe_pct is not None) else None
    mae_r = (mae_pct / risk) if (risk and mae_pct is not None) else None
    verdict = _classify(trade, mfe_pct, mae_pct, post_pct, len(trade_rows), risk)
    return Forensic(
        source=trade.source,
        strategy=trade.strategy,
        symbol=trade.symbol,
        side=trade.side,
        entry_utc=_utc(trade.entry_ts_ms),
        exit_utc=_utc(trade.exit_ts_ms),
        hold_min=max(0.0, (trade.exit_ts_ms - trade.entry_ts_ms) / 60000.0),
        pnl=trade.pnl,
        outcome=trade.outcome,
        reason=trade.reason,
        entry_to_exit_pct=_signed_pct(trade.side, trade.entry_price, trade.exit_price),
        mfe_pct=mfe_pct,
        mae_pct=mae_pct,
        mfe_r=mfe_r,
        mae_r=mae_r,
        post_exit_6bar_pct=post_pct,
        candles=len(trade_rows),
        post_candles=len(post_rows),
        verdict=verdict,
    )


def _avg(values: list[float | None]) -> float | None:
    xs = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return statistics.mean(xs) if xs else None


def _fmt(value: float | None, digits: int = 2) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{value:.{digits}f}"


def _profit_factor(pnls: list[float]) -> float:
    gp = sum(p for p in pnls if p > 0)
    gl = -sum(p for p in pnls if p < 0)
    if gl == 0:
        return float("inf") if gp > 0 else 0.0
    return gp / gl


def _safe_slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_") or "trade_forensics"


def write_outputs(items: list[Forensic], out_dir: Path, tag: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = f"trade_forensics_{ts}_{_safe_slug(tag)}"
    jsonl_path = out_dir / f"{base}.jsonl"
    md_path = out_dir / f"{base}.md"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(asdict(item), ensure_ascii=False, sort_keys=True) + "\n")

    by_strategy: dict[str, list[Forensic]] = defaultdict(list)
    for item in items:
        by_strategy[item.strategy or "unknown"].append(item)

    lines: list[str] = []
    lines.append(f"# Trade Forensics - {tag}\n")
    lines.append(f"Generated UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"Trades analyzed: **{len(items)}**\n")
    if items:
        pnls = [x.pnl for x in items]
        lines.append(
            f"Net PnL: **{sum(pnls):.4f}** | PF: **{_fmt(_profit_factor(pnls), 3)}** | "
            f"WR: **{100 * sum(1 for p in pnls if p > 0) / len(pnls):.1f}%**\n"
        )
    lines.append("## Strategy Summary\n")
    lines.append("| Strategy | Trades | Net | PF | WR | Avg MFE % | Avg MAE % | Main Verdicts |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for strategy, rows in sorted(by_strategy.items(), key=lambda kv: sum(x.pnl for x in kv[1])):
        pnls = [x.pnl for x in rows]
        verdicts = Counter(x.verdict for x in rows).most_common(3)
        verdict_txt = ", ".join(f"{k}:{v}" for k, v in verdicts)
        lines.append(
            f"| {strategy} | {len(rows)} | {sum(pnls):.4f} | {_fmt(_profit_factor(pnls), 3)} | "
            f"{100 * sum(1 for p in pnls if p > 0) / len(pnls):.1f}% | "
            f"{_fmt(_avg([x.mfe_pct for x in rows]))} | {_fmt(_avg([x.mae_pct for x in rows]))} | {verdict_txt} |"
        )
    lines.append("\n## Worst Trades\n")
    lines.append("| Exit UTC | Strategy | Symbol | Side | PnL | MFE % | MAE % | Post 6 bars % | Verdict | Reason |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---|---|")
    for item in sorted(items, key=lambda x: x.pnl)[:20]:
        reason = (item.reason or item.outcome or "").replace("|", "/")[:90]
        lines.append(
            f"| {item.exit_utc} | {item.strategy} | {item.symbol} | {item.side} | {item.pnl:.4f} | "
            f"{_fmt(item.mfe_pct)} | {_fmt(item.mae_pct)} | {_fmt(item.post_exit_6bar_pct)} | "
            f"{item.verdict} | {reason} |"
        )
    lines.append("\n## AI Follow-Up Prompts\n")
    lines.append("- If many losses are `stop_then_reversed`, test wider SL or delayed confirmation.")
    lines.append("- If many losses are `entry_failed_fast`, test stricter entry filters or regime/symbol gating.")
    lines.append("- If wins are often `tp_then_continued`, test wider TP/trailing logic.")
    lines.append("- If `missing_candles` appears often, refresh the cache before trusting this report.")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, jsonl_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate MFE/MAE trade forensics for backtest and live trades.")
    ap.add_argument("--trades-csv", action="append", default=[], help="Backtest trades.csv path. Can be repeated.")
    ap.add_argument("--live-events", default="", help="runtime/live_trade_events.jsonl path.")
    ap.add_argument("--live-days", type=int, default=90)
    ap.add_argument("--cache-dir", default=".cache/klines")
    ap.add_argument("--interval", default="5", help="Candle interval to read from cache. Default: 5.")
    ap.add_argument("--post-bars", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out-dir", default="reports/trade_forensics")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    trades: list[Trade] = []
    for raw_path in args.trades_csv:
        path = Path(raw_path).expanduser()
        trades.extend(_load_backtest_csv(path))
    if args.live_events:
        trades.extend(_load_live_events(Path(args.live_events).expanduser(), args.live_days))
    if args.limit and args.limit > 0:
        trades = trades[-args.limit :]
    if not trades:
        raise SystemExit("No trades loaded. Pass --trades-csv and/or --live-events.")

    cache_dir = Path(args.cache_dir).expanduser()
    items = [analyze_trade(t, cache_dir, str(args.interval), args.post_bars) for t in trades]
    if args.tag:
        tag = args.tag
    elif args.trades_csv:
        tag = Path(args.trades_csv[-1]).parent.name
    else:
        tag = "live"
    md_path, jsonl_path = write_outputs(items, Path(args.out_dir).expanduser(), tag)
    print(f"wrote_md={md_path}")
    print(f"wrote_jsonl={jsonl_path}")
    missing = sum(1 for x in items if x.verdict == "missing_candles")
    print(f"trades={len(items)} missing_candles={missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
