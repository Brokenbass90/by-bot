#!/usr/bin/env python3
"""Default-disabled public Bitget cash-carry normalization adapter.

Preflight and fixture normalization make no network calls and write no files.
``collect-once`` needs two explicit public-research opt-ins and performs HTTPS
GET requests only to seven frozen Bitget V2 market-data paths.  No credentials,
private/account endpoint, order, transfer, withdrawal, live, or demo authority
exists.  Output is a normalization receipt, not a station journal or trade.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.bitget_cashcarry_public_v1 import (  # noqa: E402
    BITGET_ADAPTER_ID,
    BITGET_EXCHANGE_ID,
    BITGET_SOURCE_ID,
    BITGET_STATION_COMPATIBILITY,
    BitgetPublicCashCarrySnapshotV1,
    normalize_public_payloads,
    normalization_receipt,
)
from bot.bybit_cashcarry_shadow_v1 import CashCarryShadowError  # noqa: E402


DEFAULT_SPEC = ROOT / "configs/preregistered/bitget_cashcarry_public_v1_20260716.json"
DEFAULT_FIXTURE = ROOT / "tests/fixtures/bitget_cashcarry_public_v1_responses.json"
PUBLIC_HOST = "api.bitget.com"
PUBLIC_PATHS = (
    "/api/v2/spot/public/symbols",
    "/api/v2/spot/market/orderbook",
    "/api/v2/mix/market/contracts",
    "/api/v2/mix/market/merge-depth",
    "/api/v2/mix/market/current-fund-rate",
    "/api/v2/mix/market/history-fund-rate",
    "/api/v2/public/time",
)
PUBLIC_QUERY_KEYS = {
    "/api/v2/spot/public/symbols": {"symbol"},
    "/api/v2/spot/market/orderbook": {"symbol", "type", "limit"},
    "/api/v2/mix/market/contracts": {"symbol", "productType"},
    "/api/v2/mix/market/merge-depth": {"symbol", "productType", "precision", "limit"},
    "/api/v2/mix/market/current-fund-rate": {"symbol", "productType"},
    "/api/v2/mix/market/history-fund-rate": {"symbol", "productType", "pageSize", "pageNo"},
    "/api/v2/public/time": set(),
}
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _get_json(url: str, *, timeout: float = 15.0) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != PUBLIC_HOST
        or parsed.path not in PUBLIC_PATHS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise CashCarryShadowError("adapter permits frozen public Bitget V2 paths only")
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    if set(query) - PUBLIC_QUERY_KEYS[parsed.path] or any(len(values) != 1 for values in query.values()):
        raise CashCarryShadowError("adapter rejects unknown or duplicate Bitget query keys")
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "by-bot-public-bitget-cashcarry-v1/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise CashCarryShadowError("Bitget public response exceeds the frozen byte cap")
        return json.loads(raw.decode("utf-8"))


def _query(path: str, **values: Any) -> str:
    query = urllib.parse.urlencode(values)
    suffix = f"?{query}" if query else ""
    return f"https://{PUBLIC_HOST}{path}{suffix}"


def fetch_public_payloads(
    symbol: str,
    *,
    timeout: float = 15.0,
    book_limit: int = 50,
    get_json: Callable[..., dict[str, Any]] = _get_json,
) -> dict[str, Mapping[str, Any]]:
    symbol = str(symbol).strip().upper()
    if (
        not symbol.endswith("USDT")
        or not symbol[:-4].isalnum()
        or len(symbol) > 32
    ):
        raise CashCarryShadowError("Bitget adapter requires explicit USDT symbol")
    timeout = float(timeout)
    if not 0 < timeout <= 60:
        raise CashCarryShadowError("Bitget public timeout must be in (0, 60]")
    if book_limit not in {1, 5, 15, 50}:
        raise CashCarryShadowError("Bitget common spot/perp book limit must be 1, 5, 15, or 50")
    product = "usdt-futures"
    calls = {
        "spot_instrument": _query("/api/v2/spot/public/symbols", symbol=symbol),
        "spot_book": _query(
            "/api/v2/spot/market/orderbook",
            symbol=symbol,
            type="step0",
            limit=book_limit,
        ),
        "perp_instrument": _query(
            "/api/v2/mix/market/contracts",
            symbol=symbol,
            productType=product,
        ),
        "perp_book": _query(
            "/api/v2/mix/market/merge-depth",
            symbol=symbol,
            productType=product,
            precision="scale0",
            limit=book_limit,
        ),
        "current_funding": _query(
            "/api/v2/mix/market/current-fund-rate",
            symbol=symbol,
            productType=product,
        ),
        "funding_history": _query(
            "/api/v2/mix/market/history-fund-rate",
            symbol=symbol,
            productType=product,
            pageSize=10,
            pageNo=1,
        ),
    }
    payloads = {name: get_json(url, timeout=timeout) for name, url in calls.items()}
    # Fetch final server time last so book/request timestamps must be causal.
    payloads["server_time"] = get_json(_query("/api/v2/public/time"), timeout=timeout)
    return payloads


def fetch_public_snapshot(
    symbol: str,
    *,
    timeout: float = 15.0,
    book_limit: int = 50,
    get_json: Callable[..., dict[str, Any]] = _get_json,
) -> BitgetPublicCashCarrySnapshotV1:
    return normalize_public_payloads(
        fetch_public_payloads(
            symbol,
            timeout=timeout,
            book_limit=book_limit,
            get_json=get_json,
        ),
        symbol=symbol,
    )


def _load_spec(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("adapter_id") != BITGET_ADAPTER_ID:
        raise CashCarryShadowError("Bitget public adapter spec identity mismatch")
    if payload.get("source_id") != BITGET_SOURCE_ID:
        raise CashCarryShadowError("Bitget public adapter spec source mismatch")
    if payload.get("live_permission") != "FORBIDDEN":
        raise CashCarryShadowError("Bitget public adapter live permission must be forbidden")
    return payload


def _preflight(spec_path: Path) -> dict[str, Any]:
    spec = _load_spec(spec_path)
    return {
        "schema_id": "bitget_cashcarry_public_preflight_v1",
        "ok": True,
        "status": spec.get("status"),
        "adapter_id": BITGET_ADAPTER_ID,
        "exchange_id": BITGET_EXCHANGE_ID,
        "source_id": BITGET_SOURCE_ID,
        "default_enabled": False,
        "network_calls": False,
        "filesystem_writes": False,
        "daemon_started": False,
        "public_method": "GET_ONLY",
        "public_host": PUBLIC_HOST,
        "public_paths": list(PUBLIC_PATHS),
        "api_keys_or_environment_reads": False,
        "private_api_calls": False,
        "broker_calls": False,
        "orders_transfers_withdrawals": False,
        "executable": False,
        "performance_claims": False,
        "station_compatibility": BITGET_STATION_COMPATIBILITY,
        "blocked_from_bybit_journal": True,
        "spec": str(spec_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("preflight", help="No-network/no-write preflight (default).")

    fixture = sub.add_parser("normalize-fixture", help="Offline fixture normalization receipt.")
    fixture.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)

    collect = sub.add_parser("collect-once", help="One public normalization receipt; no journal.")
    collect.add_argument("--symbol", required=True)
    collect.add_argument("--timeout", type=float, default=15.0)
    collect.add_argument("--book-limit", type=int, default=50)
    collect.add_argument("--allow-public-network", action="store_true")
    collect.add_argument("--acknowledge-normalization-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "preflight"
    try:
        _load_spec(args.spec)
        if command == "preflight":
            print(json.dumps(_preflight(args.spec), indent=2, sort_keys=True))
            return 0
        if command == "normalize-fixture":
            fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
            snapshot = normalize_public_payloads(fixture["responses"], symbol=fixture["symbol"])
        else:
            if not args.allow_public_network or not args.acknowledge_normalization_only:
                raise CashCarryShadowError(
                    "collect-once requires --allow-public-network and "
                    "--acknowledge-normalization-only"
                )
            snapshot = fetch_public_snapshot(
                args.symbol,
                timeout=args.timeout,
                book_limit=args.book_limit,
            )
        print(json.dumps(normalization_receipt(snapshot), indent=2, sort_keys=True))
        return 0
    except (CashCarryShadowError, KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, sort_keys=True),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
