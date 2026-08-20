#!/usr/bin/env python3
"""Replay ATT1 entry timestamps against public L2/tape, without order authority."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import zstandard

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.limit_execution import TradePrint, simulate_limit_then_market  # noqa: E402


DEFAULT_EVENTS = ROOT / "runtime" / "live_mirror" / "live_trade_events.jsonl"
DEFAULT_TAPE = ROOT / "runtime" / "tape"
DEFAULT_OUTPUT = ROOT / "runtime" / "att1_limit_execution_paper" / "status.json"


def _iter_lines(path: Path) -> Iterator[str]:
    if path.suffix == ".zst":
        with path.open("rb") as raw:
            with zstandard.ZstdDecompressor().stream_reader(raw) as reader:
                with io.TextIOWrapper(reader, encoding="utf-8") as text:
                    yield from text
        return
    with path.open(encoding="utf-8") as handle:
        yield from handle


def _partition(root: Path, symbol: str, day: str, stream: str) -> Path | None:
    base = root / symbol / f"{day}.{stream}.jsonl"
    if base.exists():
        return base
    compressed = base.with_suffix(base.suffix + ".zst")
    return compressed if compressed.exists() else None


def _updates(row: dict[str, Any], key: str) -> list[list[str]]:
    payload = row.get("payload") or {}
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    aliases = (key, "bids") if key == "b" else (key, "asks")
    for alias in aliases:
        value = data.get(alias) if isinstance(data, dict) else None
        if isinstance(value, list):
            return value
    return []


def _apply(side: dict[float, float], rows: list[list[str]]) -> None:
    for price_raw, qty_raw in rows:
        price, qty = float(price_raw), float(qty_raw)
        if qty <= 0:
            side.pop(price, None)
        else:
            side[price] = qty


def _book_window(path: Path, start_ms: int, deadline_ms: int) -> tuple[dict[str, float] | None, str]:
    bids: dict[float, float] = {}
    asks: dict[float, float] = {}
    valid = False
    initial: dict[str, float] | None = None
    gap_after_start = False
    final: dict[str, float] | None = None
    for raw in _iter_lines(path):
        try:
            row = json.loads(raw)
        except Exception:
            continue
        ts = int(row.get("local_recv_ts_ms") or 0)
        kind = str(row.get("kind") or "")
        if kind == "gap":
            if start_ms <= ts <= deadline_ms:
                gap_after_start = True
            valid = False
            continue
        if kind == "snapshot":
            bids, asks = {}, {}
            _apply(bids, _updates(row, "b"))
            _apply(asks, _updates(row, "a"))
            valid = bool(row.get("replayable", True))
        elif kind == "delta" and valid:
            _apply(bids, _updates(row, "b"))
            _apply(asks, _updates(row, "a"))
        else:
            continue
        if not valid or not bids or not asks:
            continue
        bid, ask = max(bids), min(asks)
        if ask <= bid:
            continue
        if initial is None and ts >= start_ms:
            initial = {
                "ts_ms": float(ts), "bid": bid, "ask": ask,
                "bid_qty": bids[bid], "ask_qty": asks[ask],
            }
        if ts >= deadline_ms:
            final = {"ts_ms": float(ts), "bid": bid, "ask": ask}
            break
    if initial is None or final is None:
        return None, "book_window_incomplete"
    if int(initial["ts_ms"]) - start_ms > 2_000:
        return None, "signal_quote_lag_over_2s"
    if int(final["ts_ms"]) - deadline_ms > 2_000:
        return None, "fallback_quote_lag_over_2s"
    if gap_after_start:
        return None, "book_gap_inside_wait_window"
    return {**initial, "fallback_bid": final["bid"], "fallback_ask": final["ask"]}, ""


def _trade_window(path: Path, start_ms: int, deadline_ms: int) -> tuple[list[TradePrint], str]:
    trades: list[TradePrint] = []
    gap = False
    for raw in _iter_lines(path):
        try:
            row = json.loads(raw)
        except Exception:
            continue
        ts = int(row.get("local_recv_ts_ms") or 0)
        if ts > deadline_ms:
            break
        if ts < start_ms:
            continue
        if row.get("kind") == "gap":
            gap = True
            continue
        if row.get("kind") != "trade":
            continue
        try:
            trades.append(TradePrint(
                ts_ms=ts,
                price=float(row["price"]),
                qty=float(row["size"]),
                aggressor_side=str(row["side"]),
            ))
        except Exception:
            continue
    if gap:
        return [], "trade_gap_inside_wait_window"
    return trades, ""


def _signals(path: Path) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if row.get("event") != "entry_filled":
                continue
            if str(row.get("strategy") or "") != "att1_trendline_touch":
                continue
            key = str(row.get("entry_order_id") or "")
            if key:
                rows[key] = row
    return sorted(rows.values(), key=lambda row: int(row.get("ts") or 0))


def _event_signal_ms(row: dict[str, Any]) -> int:
    geometry = row.get("signal_geometry") if isinstance(row.get("signal_geometry"), dict) else {}
    return int(geometry.get("entry_ts") or row.get("ts") or 0) * 1000


def _key(row: dict[str, Any]) -> str:
    basis = f"{row.get('entry_order_id')}|{row.get('symbol')}|{_event_signal_ms(row)}"
    return hashlib.sha256(basis.encode()).hexdigest()[:24]


def run(events_path: Path, tape_root: Path, output: Path) -> dict[str, Any]:
    previous: dict[str, Any] = {}
    try:
        previous = json.loads(output.read_text(encoding="utf-8"))
    except Exception:
        pass
    observations = {
        str(row.get("paper_key")): row
        for row in list(previous.get("observations") or [])
        if isinstance(row, dict) and row.get("paper_key")
    }
    skipped: list[dict[str, Any]] = []
    for event in _signals(events_path):
        paper_key = _key(event)
        if paper_key in observations:
            continue
        signal_ms = _event_signal_ms(event)
        if signal_ms <= 0:
            continue
        symbol = str(event.get("symbol") or "").upper()
        day = datetime.fromtimestamp(signal_ms / 1000, timezone.utc).strftime("%Y%m%d")
        book_path = _partition(tape_root, symbol, day, "book")
        trade_path = _partition(tape_root, symbol, day, "trades")
        if book_path is None or trade_path is None:
            skipped.append({"paper_key": paper_key, "symbol": symbol, "day": day,
                            "reason": "public_tape_partition_missing"})
            continue
        deadline_ms = signal_ms + 60_000
        book, error = _book_window(book_path, signal_ms, deadline_ms)
        if book is None:
            skipped.append({"paper_key": paper_key, "symbol": symbol, "day": day, "reason": error})
            continue
        trades, trade_error = _trade_window(trade_path, signal_ms, deadline_ms)
        if trade_error:
            skipped.append({"paper_key": paper_key, "symbol": symbol, "day": day,
                            "reason": trade_error})
            continue
        side = str(event.get("side") or "")
        queue = book["bid_qty"] if side.lower() in {"buy", "long"} else book["ask_qty"]
        result = simulate_limit_then_market(
            side=side,
            signal_ts_ms=signal_ms,
            best_bid=book["bid"],
            best_ask=book["ask"],
            queue_ahead_qty=queue,
            order_qty=float(event.get("qty") or 0),
            trades=trades,
            fallback_bid=book["fallback_bid"],
            fallback_ask=book["fallback_ask"],
            wait_seconds=60,
            maker_fee_bps=2.0,
            taker_fee_bps=5.5,
        )
        observations[paper_key] = {
            "paper_key": paper_key,
            "entry_order_id": event.get("entry_order_id"),
            "symbol": symbol,
            "strategy": "att1_trendline_touch",
            "source_book": str(book_path.relative_to(ROOT)),
            "source_trades": str(trade_path.relative_to(ROOT)),
            **result.as_dict(),
        }
    values = list(observations.values())
    savings = [float(row["savings_bps_vs_market"]) for row in values]
    maker_count = sum(row.get("mode") == "maker" for row in values)
    payload = {
        "schema_id": "att1_limit_execution_paper_v1",
        "authority": "paper_only_no_orders_no_promotion",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "contract": {
            "limit": "best_bid_for_buy_best_ask_for_sell",
            "wait_seconds": 60,
            "fallback": "market",
            "maker_fee_bps": 2.0,
            "taker_fee_bps": 5.5,
            "fill_rule": "public_prints_consume_visible_queue_plus_order_qty",
        },
        "summary": {
            "evaluated": len(values),
            "maker_fills": maker_count,
            "maker_fill_pct": maker_count / len(values) * 100.0 if values else None,
            "mean_savings_bps": sum(savings) / len(savings) if savings else None,
            "not_ready_for_live": len(values) < 20,
        },
        "observations": sorted(values, key=lambda row: int(row["signal_ts_ms"])),
        "skipped_latest_run": skipped,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(output)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--tape-root", type=Path, default=DEFAULT_TAPE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = run(args.events, args.tape_root, args.output)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
