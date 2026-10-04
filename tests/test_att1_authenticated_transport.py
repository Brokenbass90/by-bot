"""Contract tests for the deliberately GET-only ATT1 Bybit evidence client."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "live_bybit_evidence_20260706.py"
SPEC = importlib.util.spec_from_file_location("live_bybit_evidence_20260706", SCRIPT)
assert SPEC and SPEC.loader
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)

NOW_MS = 1_700_000_000_000
CONFIG = {"key": "selected-api-key", "secret": "selected-api-secret", "base": "https://api.bybit.com"}


class _Response:
    def __init__(self, payload, url):
        self._raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self._url = url

    def read(self, size=-1):
        return self._raw if size < 0 else self._raw[:size]

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False


class _Opener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        payload, url = self.responses.pop(0)
        return _Response(payload, url)


def _envelope(result, *, time_ms=NOW_MS, code=0):
    return {"retCode": code, "retMsg": "OK", "time": time_ms, "result": result}


def _client(*responses):
    opener = _Opener(responses)
    return evidence.StrictAtt1ReadClient(CONFIG, opener=opener, clock_ms=lambda: NOW_MS), opener


def test_get_is_signed_get_only_redacted_and_pins_the_production_endpoint():
    url = "https://api.bybit.com/v5/position/list?category=linear&symbol=ETHUSDT"
    client, opener = _client((_envelope({"category": "linear", "list": [], "nextPageCursor": ""}), url))

    envelope = client.get("/v5/position/list", {"category": "linear", "symbol": "ETHUSDT"})

    request, timeout = opener.requests[0]
    assert envelope["retCode"] == 0
    assert request.get_method() == "GET"
    assert timeout == client.timeout_seconds
    assert request.full_url == url
    assert set(request.headers) >= {"X-bapi-api-key", "X-bapi-sign", "X-bapi-timestamp", "X-bapi-recv-window"}
    assert client.config == {"key": CONFIG["key"], "base": CONFIG["base"]}
    assert CONFIG["secret"] not in repr(client)
    assert client.last_received_ms == NOW_MS


def test_selected_unified_usdt_wallet_is_get_only_and_retains_raw_balance():
    url = 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED&coin=USDT'
    result = {'list':[{'accountType':'UNIFIED','coin':[{'coin':'USDT','walletBalance':'12.34'}]}]}
    client, opener = _client((_envelope(result), url))
    out = client.get('/v5/account/wallet-balance', {'accountType':'UNIFIED','coin':'USDT'})
    assert out['result']==result and opener.requests[0][0].get_method()=='GET'


@pytest.mark.parametrize('params', [{'accountType':'CONTRACT','coin':'USDT'},
                                  {'accountType':'UNIFIED','coin':'BTC'},
                                  {'accountType':'UNIFIED','coin':'USDT','category':'linear'}])
def test_wallet_collection_rejects_other_accounts_coins_and_extra_params(params):
    client, opener = _client()
    with pytest.raises(ValueError):client.get('/v5/account/wallet-balance',params)
    assert opener.requests==[]


def test_wallet_collection_rejects_foreign_response_before_consumption():
    url = 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED&coin=USDT'
    result = {'list':[{'accountType':'CONTRACT','coin':[{'coin':'USDT'}]}]}
    client, _ = _client((_envelope(result),url))
    with pytest.raises(ValueError):client.get('/v5/account/wallet-balance',{'accountType':'UNIFIED','coin':'USDT'})


@pytest.mark.parametrize(
    "config",
    [
        {"key": "k", "secret": "s", "base": "https://api-testnet.bybit.com"},
        {"key": "k", "secret": "s", "base": "http://api.bybit.com"},
        {"key": "k", "secret": "s", "base": "https://api.bybit.com/proxy"},
        {"key": "k", "secret": "s", "base": "https://api.bybit.com", "accounts": []},
    ],
)
def test_constructor_requires_one_explicit_pinned_account_config(config):
    with pytest.raises(ValueError):
        evidence.StrictAtt1ReadClient(config, opener=_Opener([]), clock_ms=lambda: NOW_MS)


@pytest.mark.parametrize(
    "path,params",
    [
        ("/v5/order/create", {"category": "linear"}),
        ("/v5/position/list", {"category": "spot"}),
        ("/v5/position/list", {"symbol": "ETHUSDT"}),
        ("/v5/user/query-api", {"category": "linear"}),
        ("/v5/position/list", {"category": "linear", "unsafe": "1"}),
    ],
)
def test_transport_rejects_nonallowlisted_or_malformed_requests_before_network(path, params):
    client, opener = _client()

    with pytest.raises(ValueError):
        client.get(path, params)

    assert opener.requests == []


@pytest.mark.parametrize(
    "payload",
    [
        {"retCode": "0", "time": NOW_MS, "result": {}},
        _envelope({}, code=10001),
        _envelope({}, time_ms=NOW_MS + 1),
        _envelope({}, time_ms=NOW_MS - 60_001),
        {"retCode": 0, "time": NOW_MS, "result": []},
    ],
    ids=["retcode-type", "retcode-error", "future", "stale", "result-type"],
)
def test_get_fails_closed_on_malformed_or_unfresh_bybit_envelopes(payload):
    url = "https://api.bybit.com/v5/user/query-api"
    client, _ = _client((payload, url))

    with pytest.raises(ValueError):
        client.get("/v5/user/query-api", {})


def test_get_rejects_a_category_mismatch_before_callers_consume_the_envelope():
    url = "https://api.bybit.com/v5/position/list?category=linear"
    client, _ = _client((_envelope({"category": "spot", "list": [], "nextPageCursor": ""}), url))

    with pytest.raises(ValueError, match="category"):
        client.get("/v5/position/list", {"category": "linear"})


def test_get_rejects_redirects_and_does_not_follow_a_response_to_another_host():
    requested = "https://api.bybit.com/v5/user/query-api"
    client, _ = _client((_envelope({}), "https://attacker.example/v5/user/query-api"))

    with pytest.raises(ValueError, match="redirect"):
        client.get("/v5/user/query-api", {})

    assert requested


def test_pages_collects_complete_cursor_chain_and_binds_each_received_clock():
    first_url = "https://api.bybit.com/v5/order/realtime?category=linear&limit=2&settleCoin=USDT"
    second_url = "https://api.bybit.com/v5/order/realtime?category=linear&cursor=next&limit=2&settleCoin=USDT"
    client, opener = _client(
        (_envelope({"category": "linear", "list": [{"orderId": "a"}], "nextPageCursor": "next"}), first_url),
        (_envelope({"category": "linear", "list": [], "nextPageCursor": ""}), second_url),
    )

    pages = client.pages("/v5/order/realtime", {"category": "linear", "settleCoin": "USDT", "limit": "2"})

    assert [page["result"]["nextPageCursor"] for page in pages] == ["next", ""]
    assert client.last_received_ms == NOW_MS
    assert [parse_qs(urlparse(req.full_url).query).get("cursor") for req, _ in opener.requests] == [None, ["next"]]


@pytest.mark.parametrize(
    "pages",
    [
        [_envelope({"category": "linear", "list": [], "nextPageCursor": "same"}), _envelope({"category": "linear", "list": [], "nextPageCursor": "same"})],
        [_envelope({"category": "linear", "list": [], "nextPageCursor": "next"})] * 17,
        [_envelope({"category": "spot", "list": [], "nextPageCursor": ""})],
    ],
    ids=["cursor-cycle", "page-cap", "wrong-category"],
)
def test_pages_rejects_cycles_bounds_and_wrong_categories(pages):
    urls = ["https://api.bybit.com/v5/order/history?category=linear&limit=2"] * len(pages)
    client, _ = _client(*zip(pages, urls))

    with pytest.raises(ValueError):
        client.pages("/v5/order/history", {"category": "linear", "limit": 2})


def test_identity_uses_the_adapter_validator_and_never_exposes_the_secret():
    url = "https://api.bybit.com/v5/user/query-api"
    payload = _envelope({"apiKey": CONFIG["key"], "userID": "12345"})
    client, _ = _client((payload, url))

    identity = client.identity()

    assert identity.account.startswith("uid:")
    assert identity.endpoint == CONFIG["base"]
    assert identity.observed_at_ms == NOW_MS
    assert CONFIG["secret"] not in repr(identity)


def test_client_has_no_mutating_broker_surface():
    client, _ = _client()

    assert not any(hasattr(client, name) for name in ("post", "submit", "cancel", "set_leverage", "transfer"))


def test_transaction_log_pages_accepts_linear_row_categories_without_a_result_category():
    url = "https://api.bybit.com/v5/account/transaction-log?category=linear&limit=50"
    client, _ = _client((
        _envelope({"list": [{"id": "cash-1", "category": "linear"}], "nextPageCursor": ""}),
        url,
    ))

    pages = client.pages("/v5/account/transaction-log", {"category": "linear", "limit": 50})

    assert pages[0]["result"]["list"][0]["id"] == "cash-1"


def test_transaction_log_rejects_wrong_row_category_and_invalid_window_or_limit_before_use():
    url = "https://api.bybit.com/v5/account/transaction-log?category=linear&limit=50"
    client, _ = _client((
        _envelope({"list": [{"id": "cash-1", "category": "spot"}], "nextPageCursor": ""}),
        url,
    ))

    with pytest.raises(ValueError, match="category"):
        client.pages("/v5/account/transaction-log", {"category": "linear", "limit": 50})
    with pytest.raises(ValueError):
        client.pages("/v5/account/transaction-log", {"category": "linear", "limit": 51})
    with pytest.raises(ValueError):
        client.pages(
            "/v5/account/transaction-log",
            {"category": "linear", "startTime": 1, "endTime": 604_800_002},
        )


def test_public_funding_history_is_allowlisted_as_bounded_get_but_not_pagination():
    url = "https://api.bybit.com/v5/market/funding/history?category=linear&limit=200&symbol=BTCUSDT"
    client, _ = _client((_envelope({"category": "linear", "list": []}), url))

    envelope = client.get(
        "/v5/market/funding/history",
        {"category": "linear", "symbol": "BTCUSDT", "limit": 200},
    )

    assert envelope["result"]["list"] == []
    with pytest.raises(ValueError, match="pagination"):
        client.pages("/v5/market/funding/history", {"category": "linear", "symbol": "BTCUSDT"})


@pytest.mark.parametrize(
    "raw",
    [
        b'{"retCode":0,"retCode":0,"time":1700000000000,"result":{}}',
        b'{"retCode":0,"time":1700000000000,"result":{"value":NaN}}',
        b'{"retCode":0,"time":1700000000000,"result":{"value":Infinity}}',
    ],
    ids=["duplicate-key", "nan", "infinity"],
)
def test_strict_json_rejects_duplicate_keys_and_nonfinite_literals(raw):
    url = "https://api.bybit.com/v5/user/query-api"
    client, _ = _client((raw, url))

    with pytest.raises(ValueError, match="JSON"):
        client.get("/v5/user/query-api", {})


def test_observed_empty_transaction_page_with_explicit_null_cursor():
    url='https://api.bybit.com/v5/account/transaction-log?category=linear'
    raw=_envelope({'list':[],'nextPageCursor':None})
    client,_=_client((raw,url))
    pages=client.pages('/v5/account/transaction-log',{'category':'linear'})
    assert pages==[raw]  # Preserve broker bytes/shape; normalize only pagination control.


def test_missing_cursor_still_rejected_on_empty_cash_page():
    url='https://api.bybit.com/v5/account/transaction-log?category=linear'
    client,_=_client((_envelope({'list':[]}),url))
    with pytest.raises(ValueError,match='page'):
        client.pages('/v5/account/transaction-log',{'category':'linear'})


@pytest.mark.parametrize('path', ['/v5/account/fee-rate', '/v5/market/instruments-info'])
def test_symbol_input_gets_are_pinned_signed_and_symbol_scoped(path):
    url = 'https://api.bybit.com'+path+'?category=linear&symbol=LINKUSDT'
    result = {'list': []}
    if path == '/v5/market/instruments-info': result['category'] = 'linear'
    client, opener = _client((_envelope(result), url))
    assert client.get(path, {'category': 'linear', 'symbol': 'LINKUSDT'})['retCode'] == 0
    assert opener.requests[0][0].get_method() == 'GET'
    with pytest.raises(ValueError): client.get(path, {'category': 'linear'})
    with pytest.raises(ValueError): client.get(path, {'category': 'linear', 'symbol': 'linkusdt'})
    with pytest.raises(ValueError): client.get(path, {'category': 'linear', 'symbol': 'BTCUSDC'})
    assert len(opener.requests) == 1
