#!/usr/bin/env python3
"""Run one public-data, risk-zero XSEC V3 shadow rebalance cycle.

The universe is frozen on the first run from Claude's survivor-only research
universe intersected with currently tradable Bybit USDT perpetuals.  That keeps
signal parity while the separate robustness audit and price-PIT work continue.

This script never reads credentials and has no order endpoint.  It records
target positions, public top-of-book spread, estimated taker friction, and the
markout of the phase being replaced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, time as datetime_time, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab.xsec_v3_reference import leverage, target_weights


BYBIT_BASE = "https://api.bybit.com"
DEFAULT_RUNTIME = ROOT / "runtime" / "xsec_v3_shadow"


class ShadowCycleError(RuntimeError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _public_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{BYBIT_BASE}{path}?{query}",
        headers={"User-Agent": "xsec-risk-zero-shadow/1.0"},
    )
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=25.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if int(payload.get("retCode", -1)) != 0:
                raise ShadowCycleError(
                    f"Bybit retCode={payload.get('retCode')} "
                    f"retMsg={payload.get('retMsg')}"
                )
            return payload
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(0.5 * (2**attempt))
    raise ShadowCycleError(f"public GET retries exhausted: {last_error}")


def _freeze_universe(
    runtime_dir: Path,
    *,
    daily_path: Path,
    instruments_path: Path,
) -> dict[str, Any]:
    output = runtime_dir / "universe.json"
    if output.exists():
        return json.loads(output.read_text(encoding="utf-8"))

    daily = json.loads(daily_path.read_text(encoding="utf-8"))
    instruments = json.loads(instruments_path.read_text(encoding="utf-8"))
    current = {
        str(row.get("symbol") or "").upper()
        for row in instruments.get("records", [])
        if row.get("status") == "Trading"
        and row.get("contractType") == "LinearPerpetual"
        and row.get("quoteCoin") == "USDT"
    }
    symbols = sorted(
        symbol for symbol, values in daily.items()
        if len(values) >= 390 and symbol in current
    )
    if len(symbols) < 14:
        raise ShadowCycleError(
            f"frozen XSEC universe too small: {len(symbols)}"
        )
    value = {
        "schema_id": "xsec_v3_shadow_universe_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "survivor_only": True,
        "capital_authorized": False,
        "symbols": symbols,
        "symbol_count": len(symbols),
        "source_daily": str(daily_path.relative_to(ROOT)),
        "source_daily_sha256": hashlib.sha256(daily_path.read_bytes()).hexdigest(),
        "source_instruments": str(instruments_path.relative_to(ROOT)),
        "source_instruments_payload_sha256": instruments.get("payload_sha256"),
    }
    value["universe_sha256"] = _sha256(value["symbols"])
    _atomic_json(output, value)
    return value


def _daily_history(symbol: str, limit: int = 60) -> list[float]:
    payload = _public_get(
        "/v5/market/kline",
        {
            "category": "linear",
            "symbol": symbol,
            "interval": "D",
            "limit": limit,
        },
    )
    rows = (payload.get("result") or {}).get("list") or []
    today_start_ms = int(
        datetime.combine(
            datetime.now(timezone.utc).date(),
            datetime_time.min,
            tzinfo=timezone.utc,
        ).timestamp() * 1000
    )
    values: dict[int, float] = {}
    for row in rows:
        try:
            timestamp = int(row[0])
            close = float(row[4])
        except (IndexError, TypeError, ValueError):
            continue
        if timestamp < today_start_ms and close > 0 and math.isfinite(close):
            values[timestamp] = close
    return [values[key] for key in sorted(values)]


def _tickers() -> dict[str, dict[str, float]]:
    payload = _public_get("/v5/market/tickers", {"category": "linear"})
    rows = (payload.get("result") or {}).get("list") or []
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        try:
            bid = float(row.get("bid1Price") or 0.0)
            ask = float(row.get("ask1Price") or 0.0)
            last = float(row.get("lastPrice") or 0.0)
        except (TypeError, ValueError):
            continue
        if symbol and bid > 0 and ask >= bid and last > 0:
            out[symbol] = {"bid": bid, "ask": ask, "last": last}
    return out


def _markout(previous: dict[str, Any], tickers: dict[str, dict[str, float]]) -> dict:
    targets = previous.get("target_usd") or {}
    entry_prices = previous.get("entry_prices") or {}
    pnl = 0.0
    covered = 0
    for symbol, notional in targets.items():
        ticker = tickers.get(symbol)
        entry = float(entry_prices.get(symbol) or 0.0)
        if ticker is None or entry <= 0:
            continue
        pnl += float(notional) * (ticker["last"] / entry - 1.0)
        covered += 1
    capital = float(previous.get("phase_capital_usd") or 0.0)
    return {
        "covered_symbols": covered,
        "symbols": len(targets),
        "gross_pnl_usd": round(pnl, 6),
        "gross_return": round(pnl / capital, 8) if capital > 0 else None,
        "previous_estimated_entry_cost_usd": previous.get(
            "estimated_entry_cost_usd"
        ),
    }


def _order_plan(
    old_target: dict[str, float],
    new_target: dict[str, float],
    tickers: dict[str, dict[str, float]],
    *,
    taker_fee_bps: float,
) -> tuple[list[dict[str, Any]], float]:
    orders: list[dict[str, Any]] = []
    estimated_cost = 0.0
    for symbol in sorted(set(old_target) | set(new_target)):
        delta = float(new_target.get(symbol, 0.0)) - float(
            old_target.get(symbol, 0.0)
        )
        if abs(delta) < 0.01:
            continue
        ticker = tickers.get(symbol)
        if ticker is None:
            continue
        mid = (ticker["bid"] + ticker["ask"]) / 2.0
        half_spread_bps = (
            (ticker["ask"] - ticker["bid"]) / mid * 5_000.0
            if mid > 0 else 0.0
        )
        cost_bps = taker_fee_bps + half_spread_bps
        cost_usd = abs(delta) * cost_bps / 10_000.0
        estimated_cost += cost_usd
        orders.append({
            "symbol": symbol,
            "side": "Buy" if delta > 0 else "Sell",
            "delta_notional_usd": round(delta, 4),
            "reference_price": ticker["ask"] if delta > 0 else ticker["bid"],
            "half_spread_bps": round(half_spread_bps, 4),
            "taker_fee_bps": taker_fee_bps,
            "estimated_cost_usd": round(cost_usd, 6),
        })
    return orders, estimated_cost


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME))
    parser.add_argument("--capital-usd", type=float, default=1000.0)
    parser.add_argument("--taker-fee-bps", type=float, default=5.5)
    parser.add_argument(
        "--daily-source",
        default="research_lab/data/daily_338.json",
    )
    parser.add_argument(
        "--instruments-source",
        default="research_lab/data/bybit_instruments_linear.json",
    )
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir)
    if not runtime_dir.is_absolute():
        runtime_dir = ROOT / runtime_dir
    universe = _freeze_universe(
        runtime_dir,
        daily_path=ROOT / args.daily_source,
        instruments_path=ROOT / args.instruments_source,
    )
    state_path = runtime_dir / "state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        state = {
            "schema_id": "xsec_v3_shadow_state_v1",
            "shadow_start_date": date.today().isoformat(),
            "phases": {"0": {}, "1": {}, "2": {}},
        }

    today = datetime.now(timezone.utc).date()
    start = date.fromisoformat(state["shadow_start_date"])
    day_index = (today - start).days
    phase_id = str(day_index % 3)
    previous = state["phases"].get(phase_id) or {}
    if previous.get("rebalance_date") == today.isoformat():
        latest = json.loads(
            (runtime_dir / "decision_latest.json").read_text(encoding="utf-8")
        )
        print(
            f"xsec shadow already completed for {today} phase={phase_id} "
            f"decision={latest.get('decision_id')}"
        )
        return 0

    histories: dict[str, list[float]] = {}
    failures: dict[str, str] = {}
    for symbol in universe["symbols"]:
        try:
            values = _daily_history(symbol)
            if len(values) >= 46:
                histories[symbol] = values
            else:
                failures[symbol] = f"only_{len(values)}_completed_daily_bars"
        except Exception as exc:
            failures[symbol] = str(exc)
    if len(histories) < 14:
        raise ShadowCycleError(
            f"only {len(histories)} symbols with usable public daily history"
        )

    quotes = _tickers()
    raw_weights = target_weights(histories)
    if not raw_weights:
        raise ShadowCycleError("XSEC target_weights returned no portfolio")
    past_returns = list(previous.get("past_rebalance_returns") or [])
    markout = _markout(previous, quotes) if previous else None
    if markout and markout.get("gross_return") is not None:
        past_returns.append(float(markout["gross_return"]))
    past_returns = past_returns[-20:]
    leverage_value = leverage(past_returns)
    phase_capital = float(args.capital_usd) / 3.0
    target_usd = {
        symbol: round(weight * leverage_value * phase_capital, 6)
        for symbol, weight in raw_weights.items()
        if symbol in quotes
    }
    previous_target = {
        symbol: float(value)
        for symbol, value in (previous.get("target_usd") or {}).items()
    }
    orders, estimated_cost = _order_plan(
        previous_target,
        target_usd,
        quotes,
        taker_fee_bps=float(args.taker_fee_bps),
    )
    entry_prices = {
        symbol: quotes[symbol]["last"]
        for symbol in target_usd
        if symbol in quotes
    }
    now = datetime.now(timezone.utc)
    decision_core = {
        "schema_id": "xsec_v3_risk_zero_shadow_decision_v1",
        "created_at": now.isoformat(),
        "rebalance_date": today.isoformat(),
        "phase": int(phase_id),
        "day_index": day_index,
        "risk": 0,
        "orders_sent": False,
        "credentials_read": False,
        "capital_authorized": False,
        "universe_sha256": universe["universe_sha256"],
        "frozen_universe_symbols": universe["symbol_count"],
        "usable_symbols": len(histories),
        "data_failures": failures,
        "leverage": round(leverage_value, 6),
        "phase_capital_usd": phase_capital,
        "raw_weights": raw_weights,
        "target_usd": target_usd,
        "gross_target_usd": round(sum(abs(value) for value in target_usd.values()), 4),
        "net_target_usd": round(sum(target_usd.values()), 4),
        "planned_orders": orders,
        "turnover_usd": round(
            sum(abs(order["delta_notional_usd"]) for order in orders), 4
        ),
        "estimated_entry_cost_usd": round(estimated_cost, 6),
        "previous_phase_markout": markout,
    }
    decision_core["decision_id"] = _sha256(decision_core)
    _atomic_json(runtime_dir / "decision_latest.json", decision_core)
    _append_jsonl(runtime_dir / "ledger.jsonl", decision_core)

    state["updated_at"] = now.isoformat()
    state["phases"][phase_id] = {
        "rebalance_date": today.isoformat(),
        "decision_id": decision_core["decision_id"],
        "phase_capital_usd": phase_capital,
        "target_usd": target_usd,
        "entry_prices": entry_prices,
        "estimated_entry_cost_usd": round(estimated_cost, 6),
        "past_rebalance_returns": past_returns,
    }
    _atomic_json(state_path, state)
    print(
        f"xsec risk-zero phase={phase_id} usable={len(histories)} "
        f"orders={len(orders)} gross=${decision_core['gross_target_usd']} "
        f"turnover=${decision_core['turnover_usd']} "
        f"cost≈${decision_core['estimated_entry_cost_usd']} "
        f"decision={decision_core['decision_id'][:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
