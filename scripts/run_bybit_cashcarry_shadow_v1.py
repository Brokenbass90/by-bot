#!/usr/bin/env python3
"""Opt-in runner for the research-only Bybit cash-and-carry shadow.

Default invocation is a no-network preflight.  The only network command is an
explicit public snapshot; it has no authenticated/private/order code path.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.bybit_cashcarry_shadow_v1 import (  # noqa: E402
    CashCarryShadowError,
    FundingSettlement,
    PublicQuoteObservation,
    ShadowConfig,
    append_cycle_receipt,
    observations_from_json,
    replay_observations,
)


DEFAULT_SPEC = ROOT / "configs/preregistered/bybit_cashcarry_shadow_v1_20260715.json"
PUBLIC_PATHS = (
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
        raise CashCarryShadowError("network adapter permits frozen public Bybit market paths only")
    request = urllib.request.Request(url, headers={"User-Agent": "by-bot-public-shadow/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _checked_result(payload: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    if int(payload.get("retCode", -1)) != 0:
        raise CashCarryShadowError(f"{label} public response retCode is not zero")
    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise CashCarryShadowError(f"{label} public response is missing result")
    return result


def _level(result: Mapping[str, Any], side: str, label: str) -> tuple[float, float]:
    rows = result.get(side)
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], list) or len(rows[0]) < 2:
        raise CashCarryShadowError(f"{label} is missing top-of-book {side}")
    try:
        price, quantity = float(rows[0][0]), float(rows[0][1])
    except (TypeError, ValueError) as exc:
        raise CashCarryShadowError(f"{label} contains malformed top-of-book {side}") from exc
    return price, quantity


def _query(base: str, path: str, **values: Any) -> str:
    return f"{base.rstrip('/')}{path}?{urllib.parse.urlencode(values)}"


def fetch_public_observation(
    symbol: str,
    *,
    base: str = "https://api.bybit.com",
    timeout: float = 15.0,
    funding_price_proxy_max_lag_ms: int = 120_000,
    get_json: Callable[..., dict[str, Any]] = _get_json,
) -> PublicQuoteObservation:
    """Fetch one non-atomic public snapshot and preserve all source timestamps.

    The engine will refuse the snapshot when the spot/perp calls are too stale or
    skewed.  This function does not hide that unavoidable REST non-atomicity.
    """

    symbol = str(symbol).strip().upper()
    spot_payload = get_json(
        _query(base, "/v5/market/orderbook", category="spot", symbol=symbol, limit=1),
        timeout=timeout,
    )
    perp_payload = get_json(
        _query(base, "/v5/market/orderbook", category="linear", symbol=symbol, limit=1),
        timeout=timeout,
    )
    ticker_payload = get_json(
        _query(base, "/v5/market/tickers", category="linear", symbol=symbol),
        timeout=timeout,
    )
    funding_payload = get_json(
        _query(base, "/v5/market/funding/history", category="linear", symbol=symbol, limit=10),
        timeout=timeout,
    )

    spot = _checked_result(spot_payload, "spot orderbook")
    perp = _checked_result(perp_payload, "perp orderbook")
    ticker = _checked_result(ticker_payload, "perp ticker")
    funding = _checked_result(funding_payload, "funding history")
    tickers = ticker.get("list")
    if not isinstance(tickers, list) or len(tickers) != 1:
        raise CashCarryShadowError("public ticker must return exactly one symbol")
    ticker_row = tickers[0]
    if str(ticker_row.get("symbol") or "").upper() != symbol:
        raise CashCarryShadowError("ticker symbol mismatch")

    spot_bid, spot_bid_qty = _level(spot, "b", "spot orderbook")
    spot_ask, spot_ask_qty = _level(spot, "a", "spot orderbook")
    perp_bid, perp_bid_qty = _level(perp, "b", "perp orderbook")
    perp_ask, perp_ask_qty = _level(perp, "a", "perp orderbook")
    server_times = [
        int(spot_payload.get("time") or 0),
        int(perp_payload.get("time") or 0),
        int(ticker_payload.get("time") or 0),
        int(funding_payload.get("time") or 0),
    ]
    if any(value <= 0 for value in server_times):
        raise CashCarryShadowError("public response is missing exchange server time")
    observed_at_ms = max(server_times)
    spot_ts_ms = int(spot.get("ts") or spot_payload.get("time") or 0)
    perp_ts_ms = int(perp.get("ts") or perp_payload.get("time") or 0)
    perp_mid = (perp_bid + perp_ask) / 2.0

    settlements: list[FundingSettlement] = []
    for row in funding.get("list") or []:
        settled_at_ms = int(row.get("fundingRateTimestamp") or 0)
        if settled_at_ms <= 0 or settled_at_ms > observed_at_ms:
            continue
        rate = float(row.get("fundingRate"))
        lag = observed_at_ms - settled_at_ms
        proxy = perp_mid if lag <= int(funding_price_proxy_max_lag_ms) else None
        settlements.append(
            FundingSettlement(
                settled_at_ms=settled_at_ms,
                rate=rate,
                perp_mark_price=proxy,
            )
        )
    settlements.sort(key=lambda item: item.settled_at_ms)

    return PublicQuoteObservation(
        symbol=symbol,
        observed_at_ms=observed_at_ms,
        spot_quote_ts_ms=spot_ts_ms,
        perp_quote_ts_ms=perp_ts_ms,
        spot_bid=spot_bid,
        spot_ask=spot_ask,
        spot_bid_qty=spot_bid_qty,
        spot_ask_qty=spot_ask_qty,
        perp_bid=perp_bid,
        perp_ask=perp_ask,
        perp_bid_qty=perp_bid_qty,
        perp_ask_qty=perp_ask_qty,
        projected_funding_rate=float(ticker_row.get("fundingRate")),
        next_funding_time_ms=int(ticker_row.get("nextFundingTime") or 0),
        funding_settlements=tuple(settlements),
        complete=True,
    )


def _load_spec(path: Path) -> tuple[dict[str, Any], ShadowConfig]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mechanics = payload.get("mechanics")
    if not isinstance(mechanics, Mapping):
        raise CashCarryShadowError("preregistered spec is missing mechanics")
    # Even a modified spec cannot opt into execution.  Only the explicit replay
    # flag below can turn the in-memory research simulator on.
    return payload, ShadowConfig.from_mapping(mechanics, enabled=False)


def _preflight(spec_path: Path) -> dict[str, Any]:
    spec, config = _load_spec(spec_path)
    return {
        "schema_id": "bybit_cashcarry_shadow_preflight_v1",
        "ok": True,
        "status": "RESEARCH_ONLY_DISABLED",
        "default_enabled": config.enabled,
        "research_only": True,
        "executable": False,
        "broker_calls": False,
        "private_api_calls": False,
        "key_or_environment_reads": False,
        "network_calls": False,
        "allowed_opt_in_public_paths": list(PUBLIC_PATHS),
        "spec": str(spec_path),
        "spec_status": spec.get("status"),
        "config_sha256": config.config_sha256,
        "performance_claims": False,
    }


def _step_dict(step: Any) -> dict[str, Any]:
    out = dataclasses.asdict(step)
    if step.receipt is not None:
        out["receipt"] = step.receipt.as_dict()
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("preflight", help="No-network safety/config receipt (default).")

    replay = sub.add_parser("replay", help="Replay normalized public observations.")
    replay.add_argument("--input", type=Path, required=True)
    replay.add_argument("--receipt-ledger", type=Path)
    replay.add_argument(
        "--enable-research-shadow",
        action="store_true",
        help="Enable in-memory simulated fills only; still cannot call broker/order APIs.",
    )

    snapshot = sub.add_parser("snapshot", help="Fetch and print one public Bybit snapshot.")
    snapshot.add_argument("--symbol", required=True)
    snapshot.add_argument("--base", default="https://api.bybit.com")
    snapshot.add_argument("--timeout", type=float, default=15.0)
    snapshot.add_argument(
        "--allow-public-network",
        action="store_true",
        help="Required opt-in; uses only the three frozen public market paths.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "preflight"
    try:
        if command == "preflight":
            print(json.dumps(_preflight(args.spec), indent=2, sort_keys=True))
            return 0
        if command == "snapshot":
            if not args.allow_public_network:
                raise CashCarryShadowError("public network is disabled without --allow-public-network")
            observation = fetch_public_observation(
                args.symbol,
                base=args.base,
                timeout=args.timeout,
            )
            print(json.dumps(observation.payload(), indent=2, sort_keys=True))
            return 0

        _, frozen = _load_spec(args.spec)
        enabled = bool(args.enable_research_shadow)
        config = dataclasses.replace(frozen, enabled=enabled)
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        observations = observations_from_json(payload)
        steps, receipts = replay_observations(observations, config)
        appended = 0
        already_present = 0
        if args.receipt_ledger is not None:
            for receipt in receipts:
                if append_cycle_receipt(args.receipt_ledger, receipt):
                    appended += 1
                else:
                    already_present += 1
        result = {
            "schema_id": "bybit_cashcarry_shadow_replay_v1",
            "research_only": True,
            "executable": False,
            "broker_calls": False,
            "private_api_calls": False,
            "performance_claims": False,
            "shadow_enabled": enabled,
            "config_sha256": config.config_sha256,
            "observation_count": len(observations),
            "cycle_count": len(receipts),
            "receipts_appended": appended,
            "receipts_already_present": already_present,
            "steps": [_step_dict(step) for step in steps],
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (CashCarryShadowError, KeyError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
