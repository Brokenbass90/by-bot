#!/usr/bin/env python3
"""Opt-in durable public-data runner for cash-carry shadow v2.

The default command is a no-network/no-write preflight.  Network collection is
single-shot only and requires two explicit opt-ins.  The adapter admits HTTPS
GET requests solely to four public Bybit market-data paths; it has no key,
private-account, order, transfer, or withdrawal code path.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.bybit_cashcarry_shadow_v1 import (  # noqa: E402
    CashCarryShadowError,
    FundingSettlement,
    ShadowConfig,
)
from bot.bybit_cashcarry_shadow_v2 import (  # noqa: E402
    BookLevel,
    DurableCashCarryJournalV2,
    DurableCollectorConfigV2,
    InstrumentLegRules,
    InstrumentRulesV2,
    PublicMarketSnapshotV2,
    snapshots_from_json,
)


DEFAULT_SPEC = ROOT / "configs/preregistered/bybit_cashcarry_shadow_v2_20260715.json"
PUBLIC_PATHS = (
    "/v5/market/instruments-info",
    "/v5/market/orderbook",
    "/v5/market/tickers",
    "/v5/market/funding/history",
)
PUBLIC_HOSTS = {"api.bybit.com", "api-testnet.bybit.com"}


def _get_json(url: str, *, timeout: float = 15.0) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in PUBLIC_HOSTS
        or parsed.path not in PUBLIC_PATHS
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise CashCarryShadowError("adapter permits frozen public Bybit market paths only")
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "by-bot-public-cashcarry-v2/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _query(base: str, path: str, **values: Any) -> str:
    return f"{base.rstrip('/')}{path}?{urllib.parse.urlencode(values)}"


def _result(payload: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    if int(payload.get("retCode", -1)) != 0:
        raise CashCarryShadowError(f"{label} public response retCode is not zero")
    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise CashCarryShadowError(f"{label} public response is missing result")
    return result


def _one_row(result: Mapping[str, Any], symbol: str, label: str) -> Mapping[str, Any]:
    rows = result.get("list")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], Mapping):
        raise CashCarryShadowError(f"{label} must return exactly one instrument")
    if str(rows[0].get("symbol") or "").upper() != symbol:
        raise CashCarryShadowError(f"{label} symbol mismatch")
    return rows[0]


def _levels(result: Mapping[str, Any], side: str, label: str) -> tuple[BookLevel, ...]:
    rows = result.get(side)
    if not isinstance(rows, list) or not rows:
        raise CashCarryShadowError(f"{label} is missing book side {side}")
    return tuple(BookLevel.from_sequence(row) for row in rows)


def _rules(symbol: str, spot_row: Mapping[str, Any], perp_row: Mapping[str, Any]) -> InstrumentRulesV2:
    spot_price = spot_row.get("priceFilter") or {}
    spot_lot = spot_row.get("lotSizeFilter") or {}
    perp_price = perp_row.get("priceFilter") or {}
    perp_lot = perp_row.get("lotSizeFilter") or {}
    return InstrumentRulesV2(
        symbol=symbol,
        funding_interval_minutes=int(perp_row.get("fundingInterval") or 0),
        spot=InstrumentLegRules(
            market="spot",
            tick_size=str(spot_price.get("tickSize") or ""),
            # Bybit spot exposes the executable base-quantity increment as
            # basePrecision, while linear instruments use qtyStep.
            qty_step=str(spot_lot.get("qtyStep") or spot_lot.get("basePrecision") or ""),
            min_order_qty=str(spot_lot.get("minOrderQty") or ""),
            min_notional_usd=str(spot_lot.get("minOrderAmt") or ""),
        ),
        linear_perp=InstrumentLegRules(
            market="linear_perp",
            tick_size=str(perp_price.get("tickSize") or ""),
            qty_step=str(perp_lot.get("qtyStep") or ""),
            min_order_qty=str(perp_lot.get("minOrderQty") or ""),
            min_notional_usd=str(perp_lot.get("minNotionalValue") or ""),
        ),
    )


def fetch_public_snapshot(
    symbol: str,
    *,
    base: str = "https://api.bybit.com",
    timeout: float = 15.0,
    book_limit: int = 50,
    funding_price_proxy_max_lag_ms: int = 120_000,
    get_json: Callable[..., dict[str, Any]] = _get_json,
) -> PublicMarketSnapshotV2:
    """Fetch one timestamp-preserving, non-atomic public REST snapshot."""

    symbol = str(symbol).strip().upper()
    if book_limit < 2 or book_limit > 200:
        raise CashCarryShadowError("book limit must be between 2 and 200")
    calls = {
        "spot_instrument": ("/v5/market/instruments-info", {"category": "spot", "symbol": symbol}),
        "perp_instrument": ("/v5/market/instruments-info", {"category": "linear", "symbol": symbol}),
        "spot_book": ("/v5/market/orderbook", {"category": "spot", "symbol": symbol, "limit": book_limit}),
        "perp_book": ("/v5/market/orderbook", {"category": "linear", "symbol": symbol, "limit": book_limit}),
        "ticker": ("/v5/market/tickers", {"category": "linear", "symbol": symbol}),
        "funding": ("/v5/market/funding/history", {"category": "linear", "symbol": symbol, "limit": 10}),
    }
    payloads = {
        name: get_json(_query(base, path, **query), timeout=timeout)
        for name, (path, query) in calls.items()
    }
    results = {name: _result(payload, name) for name, payload in payloads.items()}
    spot_row = _one_row(results["spot_instrument"], symbol, "spot instrument")
    perp_row = _one_row(results["perp_instrument"], symbol, "perp instrument")
    ticker_row = _one_row(results["ticker"], symbol, "linear ticker")
    instruments = _rules(symbol, spot_row, perp_row)
    server_times = [int(payload.get("time") or 0) for payload in payloads.values()]
    if any(timestamp <= 0 for timestamp in server_times):
        raise CashCarryShadowError("public response is missing exchange server time")
    observed_at_ms = max(server_times)
    spot_book = results["spot_book"]
    perp_book = results["perp_book"]
    spot_ts = int(spot_book.get("ts") or payloads["spot_book"].get("time") or 0)
    perp_ts = int(perp_book.get("ts") or payloads["perp_book"].get("time") or 0)
    perp_bids = _levels(perp_book, "b", "perp book")
    perp_asks = _levels(perp_book, "a", "perp book")
    perp_mid = (float(perp_bids[0].price) + float(perp_asks[0].price)) / 2.0
    settlements: list[FundingSettlement] = []
    for row in results["funding"].get("list") or []:
        settled_at_ms = int(row.get("fundingRateTimestamp") or 0)
        if settled_at_ms <= 0 or settled_at_ms > observed_at_ms:
            continue
        proxy = (
            perp_mid
            if observed_at_ms - settled_at_ms <= int(funding_price_proxy_max_lag_ms)
            else None
        )
        settlements.append(
            FundingSettlement(
                settled_at_ms=settled_at_ms,
                rate=float(row.get("fundingRate")),
                perp_mark_price=proxy,
            )
        )
    settlements.sort(key=lambda item: item.settled_at_ms)
    return PublicMarketSnapshotV2(
        symbol=symbol,
        observed_at_ms=observed_at_ms,
        spot_book_ts_ms=spot_ts,
        perp_book_ts_ms=perp_ts,
        spot_bids=_levels(spot_book, "b", "spot book"),
        spot_asks=_levels(spot_book, "a", "spot book"),
        perp_bids=perp_bids,
        perp_asks=perp_asks,
        projected_funding_rate=float(ticker_row.get("fundingRate")),
        next_funding_time_ms=int(ticker_row.get("nextFundingTime") or 0),
        funding_settlements=tuple(settlements),
        instruments=instruments,
    )


def _load_spec(path: Path) -> tuple[Mapping[str, Any], ShadowConfig, DurableCollectorConfigV2]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mechanics = payload.get("v1_mechanics")
    durable = payload.get("durable_collector")
    if not isinstance(mechanics, Mapping) or not isinstance(durable, Mapping):
        raise CashCarryShadowError("v2 preregistered spec is incomplete")
    shadow = ShadowConfig.from_mapping(mechanics, enabled=False)
    allowed = {field.name for field in dataclasses.fields(DurableCollectorConfigV2)}
    collector = DurableCollectorConfigV2(
        **{key: value for key, value in durable.items() if key in allowed},
    )
    # A modified spec cannot opt in to collection or shadow mutation.
    collector = dataclasses.replace(collector, enabled=False, shadow_enabled=False)
    return payload, shadow, collector


def _preflight(spec_path: Path) -> dict[str, Any]:
    spec, shadow, collector = _load_spec(spec_path)
    return {
        "schema_id": "bybit_cashcarry_durable_preflight_v2",
        "ok": True,
        "status": "RESEARCH_ONLY_DISABLED",
        "default_collector_enabled": collector.enabled,
        "default_shadow_enabled": collector.shadow_enabled,
        "research_only": True,
        "executable": False,
        "broker_calls": False,
        "private_api_calls": False,
        "key_or_environment_reads": False,
        "network_calls": False,
        "daemon_started": False,
        "allowed_opt_in_public_paths": list(PUBLIC_PATHS),
        "public_method": "GET",
        "spec": str(spec_path),
        "spec_status": spec.get("status"),
        "shadow_config_sha256": shadow.config_sha256,
        "collector_config_sha256": collector.config_sha256,
        "performance_claims": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("preflight", help="No-network/no-write safety receipt (default).")

    replay = sub.add_parser("replay", help="Offline durable replay of normalized snapshots.")
    replay.add_argument("--input", type=Path, required=True)
    replay.add_argument("--journal", type=Path, required=True)
    replay.add_argument("--enable-durable-collector", action="store_true")
    replay.add_argument("--enable-research-shadow", action="store_true")

    collect = sub.add_parser("collect-once", help="Fetch and durably append one public snapshot.")
    collect.add_argument("--symbol", required=True)
    collect.add_argument("--journal", type=Path, required=True)
    collect.add_argument("--base", default="https://api.bybit.com")
    collect.add_argument("--timeout", type=float, default=15.0)
    collect.add_argument("--book-limit", type=int, default=50)
    collect.add_argument("--allow-public-network", action="store_true")
    collect.add_argument("--enable-durable-collector", action="store_true")
    collect.add_argument("--enable-research-shadow", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "preflight"
    try:
        if command == "preflight":
            print(json.dumps(_preflight(args.spec), indent=2, sort_keys=True))
            return 0
        _, frozen_shadow, _ = _load_spec(args.spec)
        collector_enabled = bool(args.enable_durable_collector)
        shadow_enabled = bool(args.enable_research_shadow)
        if shadow_enabled and not collector_enabled:
            raise CashCarryShadowError("research shadow requires durable collector opt-in")
        spec_payload = json.loads(args.spec.read_text(encoding="utf-8"))
        durable = spec_payload["durable_collector"]
        config = DurableCollectorConfigV2(
            enabled=collector_enabled,
            shadow_enabled=shadow_enabled,
            basis_stress_bps=durable["basis_stress_bps"],
            minimum_expected_edge_bps=durable["minimum_expected_edge_bps"],
        )
        journal = DurableCashCarryJournalV2(
            args.journal,
            shadow_config=frozen_shadow,
            collector_config=config,
        )
        if command == "collect-once":
            if not args.allow_public_network or not collector_enabled:
                raise CashCarryShadowError(
                    "collect-once requires --allow-public-network and --enable-durable-collector"
                )
            snapshots = [
                fetch_public_snapshot(
                    args.symbol,
                    base=args.base,
                    timeout=args.timeout,
                    book_limit=args.book_limit,
                )
            ]
        else:
            payload = json.loads(args.input.read_text(encoding="utf-8"))
            snapshots = snapshots_from_json(payload)
        results = [journal.ingest(snapshot) for snapshot in snapshots]
        output = {
            "schema_id": "bybit_cashcarry_durable_run_v2",
            "research_only": True,
            "executable": False,
            "broker_calls": False,
            "private_api_calls": False,
            "performance_claims": False,
            "collector_enabled": collector_enabled,
            "shadow_enabled": shadow_enabled,
            "snapshot_count": len(snapshots),
            "appended_count": sum(bool(row.get("appended")) for row in results),
            "results": results,
            "recovered": journal.recover(),
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    except (CashCarryShadowError, KeyError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(
            json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, sort_keys=True),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
