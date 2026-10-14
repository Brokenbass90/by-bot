"""Pre-outcome public census only. No liquidation history, returns or PnL inputs."""
from collections import Counter
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

RULE = dict(version="LIQUIDATION_UNIVERSE_V2_1", count=25,
            eligibility="Trading;LinearPerpetual;USDT quote+settle;not prelisting;not TradFi;source symbol grammar",
            minimum_turnover24h_usdt="10000000",
            order="descending Decimal(turnover24h), ascending symbol",
            refresh="NONE; a changed universe requires a separate epoch",
            selector_inputs="instrument census + ticker snapshot only; no liquidation/outcome inputs")


class UniverseBlocked(ValueError): pass


def encoded(d): return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
def sha(d): return hashlib.sha256(encoded(d)).hexdigest()


def _raw(capture, endpoint):
    if (capture.get("endpoint") != endpoint or capture.get("params", {}).get("category") != "linear"
            or type(capture.get("request_ms")) is not int or type(capture.get("receive_ms")) is not int
            or capture["request_ms"] > capture["receive_ms"]):
        raise UniverseBlocked("CAPTURE_CONTRACT_INVALID")
    text = capture.get("raw_text")
    if not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != capture.get("raw_sha256"):
        raise UniverseBlocked("RAW_HASH_INVALID")
    raw = json.loads(text)
    if raw.get("retCode") != 0 or raw.get("result", {}).get("category") != "linear":
        raise UniverseBlocked("PUBLIC_API_RESPONSE_INVALID")
    result = raw["result"]
    if not isinstance(result.get("list"), list): raise UniverseBlocked("PUBLIC_LIST_INVALID")
    return result


def freeze(pages, ticker, *, prereg_sha256):
    if not re.fullmatch(r"[a-f0-9]{64}", prereg_sha256): raise UniverseBlocked("PREREG_PIN_INVALID")
    if not pages or len(pages) > 10: raise UniverseBlocked("PAGINATION_INVALID")
    instruments = {}; cursor = ""; seen_cursors = set()
    for index, capture in enumerate(pages):
        params = capture.get("params", {})
        if params.get("cursor", "") != cursor: raise UniverseBlocked("CURSOR_CHAIN_INVALID")
        if params.get("status") != "Trading" or params.get("limit") != 1000:
            raise UniverseBlocked("INSTRUMENT_REQUEST_INVALID")
        result = _raw(capture, "/v5/market/instruments-info")
        for item in result["list"]:
            symbol = item.get("symbol")
            if not isinstance(symbol, str) or not symbol: raise UniverseBlocked("INSTRUMENT_SCHEMA_INVALID")
            if symbol in instruments: raise UniverseBlocked("DUPLICATE_INSTRUMENT")
            instruments[symbol] = item
        cursor = result.get("nextPageCursor", "")
        if not isinstance(cursor, str): raise UniverseBlocked("CURSOR_TYPE_INVALID")
        if not cursor and index != len(pages) - 1: raise UniverseBlocked("PAGINATION_EXTRA_PAGE")
        if cursor in seen_cursors: raise UniverseBlocked("CURSOR_LOOP")
        if cursor: seen_cursors.add(cursor)
    if cursor: raise UniverseBlocked("PAGINATION_INCOMPLETE")
    tickers = {}
    for item in _raw(ticker, "/v5/market/tickers")["list"]:
        symbol = item.get("symbol")
        if not isinstance(symbol, str) or symbol in tickers: raise UniverseBlocked("DUPLICATE_OR_INVALID_TICKER")
        tickers[symbol] = item
    excluded = Counter(); ranked = []
    for symbol, item in instruments.items():
        required = ("status", "contractType", "quoteCoin", "settleCoin", "isPreListing")
        if any(k not in item for k in required): raise UniverseBlocked("INSTRUMENT_SCHEMA_INVALID")
        reason = None
        if item["status"] != "Trading": reason = "NOT_TRADING"
        elif item["contractType"] != "LinearPerpetual": reason = "NOT_PERPETUAL"
        elif item["quoteCoin"] != "USDT" or item["settleCoin"] != "USDT": reason = "NOT_USDT"
        elif item["isPreListing"] is not False: reason = "PRELISTING_OR_UNKNOWN"
        elif (item.get("marketRegion") or item.get("underlyingTicker")
              or item.get("symbolType") in ("commodity", "stock", "forex", "index")): reason = "TRADFI"
        elif not re.fullmatch(r"[A-Z0-9]{2,30}USDT", symbol): reason = "SOURCE_SYMBOL_GRAMMAR_UNSUPPORTED"
        if reason: excluded[reason] += 1; continue
        if symbol not in tickers: raise UniverseBlocked("TICKER_MISSING:" + symbol)
        try:
            raw_turnover = tickers[symbol]["turnover24h"]
            if not isinstance(raw_turnover, str): raise TypeError("turnover must be API decimal text")
            turnover = Decimal(raw_turnover)
        except (InvalidOperation, KeyError, TypeError): raise UniverseBlocked("TURNOVER_INVALID:" + symbol)
        if not turnover.is_finite() or turnover < 0: raise UniverseBlocked("TURNOVER_INVALID:" + symbol)
        if turnover < Decimal(RULE["minimum_turnover24h_usdt"]):
            excluded["BELOW_TURNOVER_FLOOR"] += 1; continue
        ranked.append((turnover, symbol))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    if len(ranked) < 25: raise UniverseBlocked("FEWER_THAN_25_ELIGIBLE_LIQUID_SYMBOLS")
    selected = ranked[:25]
    manifest = dict(schema="BYBIT_LIQUIDATION_UNIVERSE_MANIFEST_V2_1", rule=deepcopy(RULE),
                    prereg_sha256=prereg_sha256, symbols=[s for _, s in selected],
                    ranked_selected=[dict(symbol=s, turnover24h_usdt=str(v)) for v, s in selected],
                    eligible_count=len(ranked), census_count=len(instruments), exclusion_counts=dict(excluded),
                    prepared_ms=max(c["receive_ms"] for c in [*pages, ticker]),
                    instrument_captures=deepcopy(pages), ticker_capture=deepcopy(ticker),
                    liquidation_history_reads=0, strategy_runs=0, judge_runs=0, orders_allowed=False)
    manifest["manifest_sha256"] = sha(manifest)
    return manifest


def verify(manifest):
    core = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    if sha(core) != manifest.get("manifest_sha256"): raise UniverseBlocked("MANIFEST_HASH_INVALID")
    reconstructed = freeze(manifest["instrument_captures"], manifest["ticker_capture"],
                           prereg_sha256=manifest["prereg_sha256"])
    if reconstructed != manifest: raise UniverseBlocked("MANIFEST_RECONSTRUCTION_MISMATCH")
    return manifest
