"""Bounded operator probe; stdout is a PRIVATE raw-response archive.

Existing credentials stay on VPS. No credential is returned and no POST/PUT/
DELETE, key/configuration change, order test, transfer or remote write exists.
This is not imported by KITY and grants no order authority.
"""
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
BODY_BOUND = 2 * 1024 * 1024
GET_ALLOWLIST = {
    ('https://fapi.binance.com', '/fapi/v1/time'): set(),
    ('https://fapi.binance.com', '/fapi/v3/account'): set(),
    ('https://fapi.binance.com', '/fapi/v1/accountConfig'): set(),
    ('https://fapi.binance.com', '/fapi/v1/symbolConfig'): {'symbol'},
    ('https://fapi.binance.com', '/fapi/v1/commissionRate'): {'symbol'},
    ('https://fapi.binance.com', '/fapi/v3/positionRisk'): set(),
    ('https://fapi.binance.com', '/fapi/v1/openOrders'): set(),
    ('https://fapi.binance.com', '/fapi/v1/openAlgoOrders'): set(),
    ('https://api.binance.com', '/sapi/v1/account/apiRestrictions'): set(),
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('REDIRECT_REJECTED')


def main():
    started = time.time_ns() // 1_000_000
    env_path = Path('/root/by-bot/.env')
    env = {}
    for line in env_path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    key, secret = env.get('BINANCE_API_KEY'), env.get('BINANCE_API_SECRET')
    if not key or not secret:
        print(json.dumps({'status': 'BLOCKED_DATA', 'reason': 'EXISTING_KEYS_MISSING'}))
        return

    def get(base, path, params, signed=True):
        assert (base, path) in GET_ALLOWLIST
        assert set(params) <= GET_ALLOWLIST[(base, path)]
        if 'symbol' in params:
            assert params['symbol'] in SYMBOLS
        request_ms = time.time_ns() // 1_000_000
        wire_params = dict(params)
        headers = {'Accept': 'application/json', 'User-Agent': 'KITY-account-intake-GET-only/1'}
        if signed:
            wire_params.update(timestamp=request_ms, recvWindow=5000)
            headers['X-MBX-APIKEY'] = key
        query = urllib.parse.urlencode(sorted(wire_params.items()))
        if signed:
            signature = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
            query += '&signature=' + signature
        url = base + path + ('?' + query if query else '')
        capture = {'base': base, 'endpoint': path, 'method': 'GET',
                   'params': params, 'signed': signed, 'request_ms': request_ms}
        try:
            opener = urllib.request.build_opener(NoRedirect())
            with opener.open(urllib.request.Request(url, headers=headers, method='GET'), timeout=12) as response:
                assert response.geturl() == url
                raw = response.read(BODY_BOUND + 1)
                capture['http_status'] = response.status
        except urllib.error.HTTPError as exc:
            capture['http_status'] = exc.code
            raw = exc.read(BODY_BOUND + 1)
        except Exception as exc:
            capture.update(receive_ms=time.time_ns() // 1_000_000,
                           ok=False, error_type=type(exc).__name__)
            return capture
        capture['receive_ms'] = time.time_ns() // 1_000_000
        if len(raw) > BODY_BOUND:
            capture.update(ok=False, error_type='BODY_BOUND')
            return capture
        # Defensively refuse any response containing the credential itself.
        if key.encode() in raw or secret.encode() in raw:
            capture.update(ok=False, error_type='SECRET_ECHO_REJECTED')
            return capture
        capture.update(raw=raw.decode('utf-8'), sha256=hashlib.sha256(raw).hexdigest(),
                       ok=capture['http_status'] == 200)
        return capture

    clocks = [get('https://fapi.binance.com', '/fapi/v1/time', {}, False)]
    jobs = [('https://api.binance.com', '/sapi/v1/account/apiRestrictions', {})]
    jobs += [('https://fapi.binance.com', endpoint, {}) for endpoint in
             ('/fapi/v3/account', '/fapi/v1/accountConfig', '/fapi/v3/positionRisk',
              '/fapi/v1/openOrders', '/fapi/v1/openAlgoOrders')]
    jobs += [('https://fapi.binance.com', endpoint, {'symbol': symbol})
             for endpoint in ('/fapi/v1/symbolConfig', '/fapi/v1/commissionRate')
             for symbol in SYMBOLS]
    assert len(jobs) == 22
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(get, base, endpoint, params) for base, endpoint, params in jobs]
        captures = [future.result() for future in futures]
    clocks.append(get('https://fapi.binance.com', '/fapi/v1/time', {}, False))
    print(json.dumps({'schema': 'KITY_BINANCE_EXISTING_ACCOUNT_GET_ARCHIVE_V1',
        'started_ms': started, 'completed_ms': time.time_ns() // 1_000_000,
        'credential_profile': str(env_path) + ':existing BINANCE named fields',
        'same_in_memory_key_for_all_signed_reads': True,
        'orders_allowed': False, 'order_calls': 0, 'remote_writes': 0,
        'api_requests': len(captures) + len(clocks),
        'symbols': SYMBOLS, 'clock_captures': clocks, 'captures': captures},
        ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
