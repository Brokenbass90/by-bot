#!/usr/bin/env python3
"""Build a resumable, research-only US-equity PIT candidate archive.

Massive supplies active/inactive ticker reference, delisting dates, adjusted
daily bars and corporate actions. Alpaca is used only for GET-only active asset
metadata and batched recent IEX bars so the active side is ranked by liquidity
instead of alphabetically.  The process has no order, cancel, close or risk
path.  The free Massive plan exposes about two years, so this archive is a
two-year causal repair input, not a long-horizon promotion artifact.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
MASSIVE_ROOT = "https://api.massive.com"
ALPACA_DATA_ROOT = "https://data.alpaca.markets"
AUTHORITY = "research_only_get_no_orders_no_risk_mutation"
DEFAULT_OUT = ROOT / "research_lab/data/alpaca_pit_daily_v1"
DEFAULT_MASSIVE_ENV = ROOT / "configs/massive_stocks_local.env"
DEFAULT_ALPACA_ENV = ROOT / "configs/alpaca_paper_local.env"
PRIMARY_EXCHANGES = {"XNYS", "XNAS", "XASE", "ARCX"}


class PitArchiveError(RuntimeError):
    """The archive cannot make safe progress."""


def _load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines() if path.exists() else []:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip("'\"")
    return out


def _canonical_sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _json_get(url: str, headers: dict[str, str], timeout: float = 30.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise PitArchiveError(f"HTTP {exc.code}: {detail}") from exc
    if not isinstance(payload, dict):
        raise PitArchiveError("provider payload is not a JSON object")
    return payload


def _massive_headers(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}", "Accept": "application/json", "User-Agent": "pit-daily-v1/1.0"}


def _alpaca_headers(key: str, secret: str) -> dict[str, str]:
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret, "Accept": "application/json", "User-Agent": "pit-daily-v1/1.0"}


def _provider_pages(
    url: str,
    *,
    headers: dict[str, str],
    throttle_s: float,
    get_json: Callable[[str, dict[str, str]], dict[str, Any]] = _json_get,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    next_url = url
    while next_url:
        payload = get_json(next_url, headers)
        page = payload.get("results") or []
        if not isinstance(page, list):
            raise PitArchiveError("provider results are not a list")
        rows.extend(row for row in page if isinstance(row, dict))
        raw_next = str(payload.get("next_url") or "")
        next_url = raw_next if raw_next.startswith("https://") else ""
        if next_url and throttle_s > 0:
            time.sleep(throttle_s)
    return rows


def fetch_massive_reference(key: str, throttle_s: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for active in ("true", "false"):
        query = urllib.parse.urlencode({"market": "stocks", "type": "CS", "active": active, "limit": 1000, "sort": "ticker"})
        rows.extend(_provider_pages(f"{MASSIVE_ROOT}/v3/reference/tickers?{query}", headers=_massive_headers(key), throttle_s=throttle_s))
        if throttle_s > 0:
            time.sleep(throttle_s)
    dedup = {str(row.get("ticker") or "").upper(): row for row in rows if row.get("ticker")}
    return [dedup[key] for key in sorted(dedup)]


def fetch_alpaca_assets(key: str, secret: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"status": "active", "asset_class": "us_equity"})
    payload = _json_get(f"https://paper-api.alpaca.markets/v2/assets?{query}", _alpaca_headers(key, secret))
    # Alpaca's assets endpoint returns a top-level array.  _json_get is strict
    # for provider safety, so use a direct array reader here.
    return list(payload.get("results") or [])


def _alpaca_asset_array(key: str, secret: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"status": "active", "asset_class": "us_equity"})
    request = urllib.request.Request(
        f"https://paper-api.alpaca.markets/v2/assets?{query}",
        headers=_alpaca_headers(key, secret), method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise PitArchiveError("Alpaca assets payload is not a list")
    return [row for row in payload if isinstance(row, dict)]


def fetch_recent_liquidity(
    symbols: list[str], *, key: str, secret: str, start: str, end: str, batch_size: int = 180
) -> dict[str, float]:
    scores: dict[str, list[float]] = {}
    headers = _alpaca_headers(key, secret)
    for offset in range(0, len(symbols), batch_size):
        batch = symbols[offset: offset + batch_size]
        token = ""
        while True:
            params = {
                "symbols": ",".join(batch), "timeframe": "1Day", "start": start, "end": end,
                "limit": 10000, "adjustment": "raw", "feed": "iex", "sort": "asc",
            }
            if token:
                params["page_token"] = token
            payload = _json_get(f"{ALPACA_DATA_ROOT}/v2/stocks/bars?{urllib.parse.urlencode(params)}", headers)
            for symbol, bars in dict(payload.get("bars") or {}).items():
                for bar in bars or []:
                    try:
                        scores.setdefault(symbol.upper(), []).append(float(bar["c"]) * float(bar["v"]))
                    except (KeyError, TypeError, ValueError):
                        continue
            token = str(payload.get("next_page_token") or "")
            if not token:
                break
    return {symbol: sum(values) / len(values) for symbol, values in scores.items() if values}


def _date_or_none(value: Any) -> dt.date | None:
    text = str(value or "")[:10]
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def select_universe(
    reference: list[dict[str, Any]],
    alpaca_assets: list[dict[str, Any]],
    liquidity: dict[str, float],
    *,
    start: dt.date,
    target_size: int,
    inactive_cap: int,
    force_symbols: list[str],
) -> dict[str, Any]:
    tradable = {
        str(row.get("symbol") or "").upper()
        for row in alpaca_assets
        if row.get("tradable") is True and row.get("status") == "active"
    }
    eligible = [
        row for row in reference
        if str(row.get("primary_exchange") or "") in PRIMARY_EXCHANGES
        and str(row.get("type") or "") == "CS"
    ]
    active = [row for row in eligible if row.get("active") is True and str(row.get("ticker") or "").upper() in tradable]
    inactive = []
    for row in eligible:
        if row.get("active") is not False:
            continue
        delisted = _date_or_none(row.get("delisted_utc"))
        updated = _date_or_none(row.get("last_updated_utc"))
        if (delisted and delisted >= start) or (delisted is None and updated and updated >= start):
            inactive.append(row)
    inactive.sort(key=lambda row: str(row.get("delisted_utc") or row.get("last_updated_utc") or ""), reverse=True)
    inactive = inactive[:max(0, inactive_cap)]
    active.sort(key=lambda row: (float(liquidity.get(str(row.get("ticker") or "").upper(), 0.0)), str(row.get("ticker") or "")), reverse=True)
    chosen: dict[str, dict[str, Any]] = {}
    for row in inactive:
        chosen[str(row["ticker"]).upper()] = row
    for row in active:
        if len(chosen) >= target_size:
            break
        chosen[str(row["ticker"]).upper()] = row
    ref_map = {str(row.get("ticker") or "").upper(): row for row in eligible}
    for symbol in force_symbols:
        if symbol in ref_map:
            chosen[symbol] = ref_map[symbol]
    rows = [chosen[symbol] for symbol in sorted(chosen)]
    return {
        "schema_id": "alpaca_pit_candidate_universe_v1",
        "pit_candidate_pool": True,
        "point_in_time_membership": False,
        "membership_semantics": "daily bar existence through delisted_utc; first adjusted bar defines observed start",
        "selection_limitations": [
            "active candidate pool ranked by current recent IEX liquidity",
            "two-year Massive Basic history",
            "list_date often absent; first observed daily bar is used instead",
            "final PIT membership intervals are materialized only after all selected daily histories validate",
        ],
        "start": start.isoformat(),
        "target_size": target_size,
        "active_selected": sum(row.get("active") is True for row in rows),
        "inactive_selected": sum(row.get("active") is False for row in rows),
        "symbols": [str(row["ticker"]).upper() for row in rows],
        "reference": rows,
    }


def fetch_massive_daily(symbol: str, start: str, end: str, *, key: str) -> list[dict[str, Any]]:
    safe = urllib.parse.quote(symbol, safe="")
    query = urllib.parse.urlencode({"adjusted": "true", "sort": "asc", "limit": 50000})
    payload = _json_get(f"{MASSIVE_ROOT}/v2/aggs/ticker/{safe}/range/1/day/{start}/{end}?{query}", _massive_headers(key))
    rows = payload.get("results") or []
    if not isinstance(rows, list):
        raise PitArchiveError(f"{symbol}: daily results are not a list")
    return rows


def materialize(
    *, out_dir: Path, massive_key: str, alpaca_key: str, alpaca_secret: str,
    start: dt.date, end: dt.date, target_size: int, inactive_cap: int,
    throttle_s: float, min_free_gb: float, max_symbols: int,
) -> dict[str, Any]:
    if shutil.disk_usage(out_dir.parent if out_dir.parent.exists() else ROOT).free < min_free_gb * 1024**3:
        raise PitArchiveError("disk guard active")
    out_dir.mkdir(parents=True, exist_ok=True)
    reference_path = out_dir / "ticker_reference.json"
    if reference_path.exists():
        reference = json.loads(reference_path.read_text(encoding="utf-8"))["records"]
    else:
        reference = fetch_massive_reference(massive_key, throttle_s)
        _atomic_json(reference_path, {"schema_id": "massive_ticker_reference_v1", "records": reference, "payload_sha256": _canonical_sha(reference)})

    assets_path = out_dir / "alpaca_active_assets.json"
    if assets_path.exists():
        assets = json.loads(assets_path.read_text(encoding="utf-8"))["records"]
    else:
        assets = _alpaca_asset_array(alpaca_key, alpaca_secret)
        _atomic_json(assets_path, {"schema_id": "alpaca_active_assets_v1", "records": assets, "payload_sha256": _canonical_sha(assets)})

    active_symbols = sorted({
        str(row.get("ticker") or "").upper() for row in reference
        if row.get("active") is True and str(row.get("primary_exchange") or "") in PRIMARY_EXCHANGES
    })
    liquidity_path = out_dir / "recent_liquidity.json"
    if liquidity_path.exists():
        liquidity = json.loads(liquidity_path.read_text(encoding="utf-8"))["scores"]
    else:
        recent_start = (end - dt.timedelta(days=35)).isoformat()
        liquidity = fetch_recent_liquidity(active_symbols, key=alpaca_key, secret=alpaca_secret, start=recent_start, end=end.isoformat())
        _atomic_json(liquidity_path, {"schema_id": "alpaca_recent_iex_liquidity_v1", "scores": liquidity, "payload_sha256": _canonical_sha(liquidity)})

    force = ["SPY", "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "BAC", "PANW", "SNOW", "CRWD"]
    universe = select_universe(reference, assets, liquidity, start=start, target_size=target_size, inactive_cap=inactive_cap, force_symbols=force)
    _atomic_json(out_dir / "universe.json", universe)
    symbols = list(universe["symbols"])
    bars_dir = out_dir / "bars"
    bars_dir.mkdir(exist_ok=True)
    status: dict[str, Any] = {
        "schema_id": "alpaca_pit_daily_materialization_status_v1", "authority": AUTHORITY,
        "private_order_api_calls": False, "order_or_risk_mutation": False,
        "state": "running", "start": start.isoformat(), "end": end.isoformat(),
        "requested": len(symbols), "completed": [], "skipped": [], "failed": {},
    }
    attempts = 0
    for symbol in symbols:
        if max_symbols and attempts >= max_symbols:
            status["state"] = "budget_complete"
            break
        if shutil.disk_usage(out_dir).free < min_free_gb * 1024**3:
            status["state"] = "stopped_disk_guard"
            _atomic_json(out_dir / "status.json", status)
            raise PitArchiveError("disk guard activated during daily materialization")
        path = bars_dir / f"{symbol}.json"
        if path.exists():
            try:
                old = json.loads(path.read_text(encoding="utf-8"))
                if old.get("payload_sha256") == _canonical_sha(old.get("records") or []) and old.get("end") == end.isoformat():
                    status["skipped"].append(symbol)
                    continue
            except Exception:
                pass
        attempts += 1
        try:
            rows = fetch_massive_daily(symbol, start.isoformat(), end.isoformat(), key=massive_key)
            times = [int(row.get("t") or 0) for row in rows]
            if times != sorted(times) or len(times) != len(set(times)):
                raise PitArchiveError("daily timestamps not unique ascending")
            payload = {
                "schema_id": "massive_adjusted_daily_symbol_v1", "authority": AUTHORITY,
                "symbol": symbol, "start": start.isoformat(), "end": end.isoformat(),
                "adjusted": True, "records": rows, "payload_sha256": _canonical_sha(rows),
                "first_bar_ms": times[0] if times else None, "last_bar_ms": times[-1] if times else None,
            }
            _atomic_json(path, payload)
            status["completed"].append(symbol)
        except Exception as exc:
            status["failed"][symbol] = f"{type(exc).__name__}: {exc}"
        status["updated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        _atomic_json(out_dir / "status.json", status)
        if throttle_s > 0:
            time.sleep(throttle_s)
    else:
        status["state"] = "complete"
    status.update({"completed_count": len(status["completed"]), "skipped_count": len(status["skipped"]), "failed_count": len(status["failed"]), "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat()})
    _atomic_json(out_dir / "status.json", status)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-readonly-network", action="store_true")
    parser.add_argument("--massive-env", type=Path, default=DEFAULT_MASSIVE_ENV)
    parser.add_argument("--alpaca-env", type=Path, default=DEFAULT_ALPACA_ENV)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--start", default="2024-08-12")
    parser.add_argument("--end", default=dt.date.today().isoformat())
    parser.add_argument("--target-size", type=int, default=1000)
    parser.add_argument("--inactive-cap", type=int, default=300)
    parser.add_argument("--throttle-seconds", type=float, default=12.5)
    parser.add_argument("--min-free-gb", type=float, default=50.0)
    parser.add_argument("--max-symbols", type=int, default=0)
    args = parser.parse_args()
    if not args.allow_readonly_network:
        raise PitArchiveError("--allow-readonly-network is required")
    massive = _load_env(args.massive_env)
    alpaca = _load_env(args.alpaca_env)
    massive_key = str(massive.get("MASSIVE_API_KEY") or os.getenv("MASSIVE_API_KEY") or "").strip()
    alpaca_key = str(alpaca.get("ALPACA_API_KEY_ID") or "").strip()
    alpaca_secret = str(alpaca.get("ALPACA_API_SECRET_KEY") or "").strip()
    if not massive_key or not alpaca_key or not alpaca_secret:
        raise PitArchiveError("required provider credentials are missing")
    status = materialize(
        out_dir=args.out_dir, massive_key=massive_key, alpaca_key=alpaca_key, alpaca_secret=alpaca_secret,
        start=dt.date.fromisoformat(args.start), end=dt.date.fromisoformat(args.end),
        target_size=max(1, args.target_size), inactive_cap=max(0, args.inactive_cap),
        throttle_s=max(0.0, args.throttle_seconds), min_free_gb=max(0.0, args.min_free_gb),
        max_symbols=max(0, args.max_symbols),
    )
    print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not status["failed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
