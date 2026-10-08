"""One bounded existing-account Bitget audit; stdout is a PRIVATE raw archive.

Only allowlisted GET endpoints, no remote file or broker writes. Not imported
by KITY, not an execution adapter. Signing material is never returned.
"""
import base64
import concurrent.futures
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SYMBOLS = ('SANDUSDT', 'BTWUSDT', 'TRXUSDT', 'AEROUSDT',
           'DOGEUSDT', 'TRUMPUSDT', '币安人生USDT', 'FILUSDT')
BASE = 'https://api.bitget.com'
BODY_BOUND = 2 * 1024 * 1024
ALLOWLIST = {
    '/api/v2/public/time': set(),
    '/api/v2/mix/market/contracts': {'productType'},
    '/api/v2/mix/account/accounts': {'productType'},
    '/api/v2/mix/account/account': {'productType', 'symbol', 'marginCoin'},
    '/api/v2/spot/account/info': set(),
    '/api/v2/spot/account/assets': {'coin'},
    '/api/v2/mix/position/all-position': {'productType', 'marginCoin'},
    '/api/v2/mix/order/orders-pending': {'productType', 'limit'},
    '/api/v2/mix/order/orders-plan-pending': {'productType', 'planType', 'limit'},
    '/api/v2/common/trade-rate': {'symbol', 'businessType'},
    '/api/v2/mix/market/merge-depth': {'productType', 'symbol', 'precision', 'limit'},
    '/api/v2/mix/market/current-fund-rate': {'productType', 'symbol'},
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('REDIRECT_REJECTED')


def main():
    started = time.time_ns() // 1_000_000
    env = {}
    needed = {'BITGET_API_KEY', 'BITGET_API_SECRET', 'BITGET_API_PASSPHRASE'}
    for line in Path('/root/by-bot/.env').read_text().splitlines():
        if line.lstrip().startswith('#') or '=' not in line:
            continue
        name, value = line.split('=', 1)
        if name.strip() in needed:
            env[name.strip()] = value.strip().strip('"').strip("'")
    key = env.get('BITGET_API_KEY')
    secret = env.get('BITGET_API_SECRET')
    passphrase = env.get('BITGET_API_PASSPHRASE')
    credentials_present = bool(key and secret and passphrase)

    def get(path, params, signed=False):
        assert path in ALLOWLIST and set(params) <= ALLOWLIST[path]
        if 'symbol' in params:
            assert params['symbol'] in SYMBOLS
        if 'productType' in params:
            assert params['productType'] == 'USDT-FUTURES'
        if 'marginCoin' in params or 'coin' in params:
            assert params.get('marginCoin', params.get('coin')) == 'USDT'
        request_ms = time.time_ns() // 1_000_000
        capture = {'endpoint': path, 'params': params, 'method': 'GET',
                   'signed': signed, 'request_ms': request_ms}
        if signed and not credentials_present:
            return dict(capture, ok=False, error_type='EXISTING_KEYS_MISSING')
        query = urllib.parse.urlencode(sorted(params.items()))
        target = path + ('?' + query if query else '')
        headers = {'Accept': 'application/json', 'User-Agent': 'KITY-Bitget-GET-audit/1'}
        if signed:
            timestamp = str(request_ms)
            digest = hmac.new(secret.encode(),
                (timestamp + 'GET' + target).encode(), hashlib.sha256).digest()
            headers.update({'ACCESS-KEY': key, 'ACCESS-SIGN': base64.b64encode(digest).decode(),
                'ACCESS-TIMESTAMP': timestamp, 'ACCESS-PASSPHRASE': passphrase})
        url = BASE + target
        try:
            opener = urllib.request.build_opener(NoRedirect())
            with opener.open(urllib.request.Request(url, headers=headers, method='GET'), timeout=12) as response:
                assert response.geturl() == url
                raw = response.read(BODY_BOUND + 1)
                capture['http_status'] = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read(BODY_BOUND + 1)
            capture['http_status'] = exc.code
        except Exception as exc:
            return dict(capture, receive_ms=time.time_ns() // 1_000_000,
                        ok=False, error_type=type(exc).__name__)
        capture['receive_ms'] = time.time_ns() // 1_000_000
        if len(raw) > BODY_BOUND:
            return dict(capture, ok=False, error_type='BODY_BOUND')
        if any(value and value.encode() in raw for value in (key, secret, passphrase)):
            return dict(capture, ok=False, error_type='SECRET_ECHO_REJECTED')
        try:
            body = json.loads(raw)
        except Exception:
            return dict(capture, ok=False, error_type='NON_JSON_RESPONSE')
        capture.update(raw=raw.decode('utf-8'), sha256=hashlib.sha256(raw).hexdigest(),
            api_code=body.get('code'), ok=capture['http_status'] == 200 and body.get('code') == '00000')
        return capture

    captures = [get('/api/v2/public/time', {}),
                get('/api/v2/mix/market/contracts', {'productType': 'USDT-FUTURES'})]
    census = captures[1]
    rows = json.loads(census.get('raw', '{}')).get('data', []) if census.get('ok') else []
    counts = {}
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get('symbol'), str):
                counts[row['symbol']] = counts.get(row['symbol'], 0) + 1
    present = [symbol for symbol in SYMBOLS if counts.get(symbol) == 1]
    jobs = [
        ('/api/v2/mix/account/accounts', {'productType': 'USDT-FUTURES'}, True),
        ('/api/v2/spot/account/info', {}, True),
        ('/api/v2/spot/account/assets', {'coin': 'USDT'}, True),
        ('/api/v2/mix/position/all-position', {'productType': 'USDT-FUTURES', 'marginCoin': 'USDT'}, True),
        ('/api/v2/mix/order/orders-pending', {'productType': 'USDT-FUTURES', 'limit': '100'}, True),
    ]
    jobs += [('/api/v2/mix/order/orders-plan-pending',
        {'productType': 'USDT-FUTURES', 'planType': kind, 'limit': '100'}, True)
        for kind in ('normal_plan', 'track_plan', 'profit_loss')]
    for symbol in present:
        jobs += [
            ('/api/v2/mix/account/account', {'productType': 'USDT-FUTURES', 'symbol': symbol, 'marginCoin': 'USDT'}, True),
            ('/api/v2/common/trade-rate', {'symbol': symbol, 'businessType': 'mix'}, True),
            ('/api/v2/mix/market/current-fund-rate', {'productType': 'USDT-FUTURES', 'symbol': symbol}, False),
        ]
    assert len(jobs) <= 32
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        captures.extend(pool.map(lambda args: get(*args), jobs))
    # Read all present books in one bounded phase, retaining each raw clock.
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        captures.extend(pool.map(lambda symbol: get('/api/v2/mix/market/merge-depth',
            {'productType': 'USDT-FUTURES', 'symbol': symbol, 'precision': 'scale0', 'limit': '50'}), present))
    captures.append(get('/api/v2/public/time', {}))
    assert len(captures) <= 43
    print(json.dumps({'schema': 'KITY_BITGET_EXISTING_ACCOUNT_GET_ARCHIVE_V1',
        'started_ms': started, 'completed_ms': time.time_ns() // 1_000_000,
        'credential_profile': '/root/by-bot/.env:existing BITGET named fields',
        'same_in_memory_key_for_all_signed_reads': True,
        'credentials_present': credentials_present,
        'orders_allowed': False, 'order_calls': 0, 'remote_writes': 0,
        'api_requests': len(captures), 'symbols': SYMBOLS,
        'complete_census_required': True, 'exact_symbol_counts': {s: counts.get(s, 0) for s in SYMBOLS},
        'captures': captures}, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
