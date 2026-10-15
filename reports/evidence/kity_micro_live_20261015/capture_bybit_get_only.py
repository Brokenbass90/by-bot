"""Bounded feasibility observation, executed via SSH stdin; no remote writes.

Selected credentials must exactly match the already-running production process.
GET-only allowlist, no redirects/retries. Stdout belongs in a PRIVATE archive.
The key returned by query-api is redacted before serialization, with raw hash.
This is an evidence reader, never a dispatcher or a readiness decision.
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

SYMBOLS = ('BTWUSDT', 'XAUUSDT', 'LTCUSDT', 'VVVUSDT', 'BNBUSDT',
           'XAUTUSDT', 'XPLUSDT', 'XAGUSDT', 'GRASSUSDT', 'SPCXUSDT')
BASE = 'https://api.bybit.com'
PID = 1648585
ALLOW = {
    '/v5/user/query-api': set(),
    '/v5/account/info': set(),
    '/v5/account/wallet-balance': {'accountType'},
    '/v5/account/fee-rate': {'category', 'symbol'},
    '/v5/position/list': {'category', 'symbol', 'settleCoin', 'limit', 'cursor'},
    '/v5/order/realtime': {'category', 'settleCoin', 'limit', 'cursor', 'openOnly'},
    '/v5/market/instruments-info': {'category', 'symbol'},
    '/v5/market/tickers': {'category', 'symbol'},
    '/v5/market/orderbook': {'category', 'symbol', 'limit'},
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('REDIRECT_REJECTED')


def main():
    start = time.time_ns() // 1_000_000
    env = {}
    for line in Path('/root/by-bot/.env').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    active = {}
    for item in (Path('/proc') / str(PID) / 'environ').read_bytes().split(b'\0'):
        k, sep, v = item.partition(b'=')
        if sep:
            active[k.decode()] = v.decode()
    for name in ('BYBIT_ACCOUNTS_JSON', 'TRADE_ACCOUNT_NAME', 'BYBIT_BASE'):
        if env.get(name) != active.get(name):
            raise RuntimeError('ACTIVE_CREDENTIAL_SOURCE_MISMATCH')
    if env['BYBIT_BASE'] != BASE:
        raise RuntimeError('UNAPPROVED_BASE')
    rows = json.loads(env['BYBIT_ACCOUNTS_JSON'])
    selected = [r for r in rows if r.get('name') == env['TRADE_ACCOUNT_NAME']]
    if len(selected) != 1:
        raise RuntimeError('AMBIGUOUS_SELECTED_ACCOUNT')
    key, secret = selected[0]['key'], selected[0]['secret']
    if not key or not secret:
        raise RuntimeError('MISSING_EXISTING_CREDENTIALS')

    def get(path, params, signed=True):
        if path not in ALLOW or not set(params) <= ALLOW[path]:
            raise RuntimeError('GET_ALLOWLIST')
        if 'symbol' in params and params['symbol'] not in SYMBOLS:
            raise RuntimeError('SYMBOL_ALLOWLIST')
        request_ms = time.time_ns() // 1_000_000
        cap = dict(endpoint=path, params=params, method='GET', signed=signed,
                   request_ms=request_ms)
        query = urllib.parse.urlencode(sorted(params.items()))
        url = BASE + path + ('?' + query if query else '')
        headers = {'User-Agent': 'KITY-micro-feasibility-GET-only/1'}
        if signed:
            ts, window = str(request_ms), '10000'
            sig = hmac.new(secret.encode(), (ts + key + window + query).encode(), hashlib.sha256).hexdigest()
            headers.update({'X-BAPI-API-KEY': key, 'X-BAPI-TIMESTAMP': ts,
                            'X-BAPI-RECV-WINDOW': window, 'X-BAPI-SIGN': sig})
        try:
            opener = urllib.request.build_opener(NoRedirect())
            with opener.open(urllib.request.Request(url, headers=headers, method='GET'), timeout=12) as resp:
                raw = resp.read(2_000_001)
                cap['http_status'] = resp.status
        except urllib.error.HTTPError as exc:
            raw = exc.read(2_000_001)
            cap['http_status'] = exc.code
        except Exception as exc:
            return dict(cap, receive_ms=time.time_ns() // 1_000_000, error_type=type(exc).__name__)
        cap['receive_ms'] = time.time_ns() // 1_000_000
        if len(raw) > 2_000_000:
            return dict(cap, error_type='BODY_BOUND')
        cap['raw_sha256'] = hashlib.sha256(raw).hexdigest()
        try:
            body = json.loads(raw)
        except Exception:
            return dict(cap, error_type='NON_JSON_RESPONSE')
        if path == '/v5/user/query-api' and isinstance(body.get('result'), dict):
            # Bybit intentionally returns the API key. Never retain it.
            body['result'].pop('apiKey', None)
            body['result'].pop('ips', None)
            cap['redacted_fields'] = ['result.apiKey', 'result.ips']
        else:
            cap['raw'] = raw.decode()
        encoded = json.dumps(body)
        if any(value in encoded for value in (key, secret)):
            return dict(cap, error_type='SECRET_ECHO_REJECTED')
        cap['body'] = body
        return cap

    def pages(path, params):
        out, cursor, seen = [], '', set()
        for _ in range(10):
            cap = get(path, dict(params, **({'cursor': cursor} if cursor else {})))
            out.append(cap)
            body = cap.get('body', {})
            if body.get('retCode') != 0:
                return dict(pages=out, complete=False, reason='API_OR_TRANSPORT_ERROR')
            cursor = (body.get('result') or {}).get('nextPageCursor', '')
            if not cursor:
                return dict(pages=out, complete=True)
            if cursor in seen:
                return dict(pages=out, complete=False, reason='CURSOR_LOOP')
            seen.add(cursor)
        return dict(pages=out, complete=False, reason='PAGE_BOUND')

    tasks = [('identity', '/v5/user/query-api', {}),
             ('account', '/v5/account/info', {}),
             ('wallet', '/v5/account/wallet-balance', {'accountType': 'UNIFIED'})]
    for symbol in SYMBOLS:
        tasks.extend([(f'instrument:{symbol}', '/v5/market/instruments-info', {'category': 'linear', 'symbol': symbol}),
                      (f'ticker:{symbol}', '/v5/market/tickers', {'category': 'linear', 'symbol': symbol}),
                      (f'fee:{symbol}', '/v5/account/fee-rate', {'category': 'linear', 'symbol': symbol}),
                      (f'position:{symbol}', '/v5/position/list', {'category': 'linear', 'symbol': symbol})])
    result = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        pending = {pool.submit(get, path, params, not path.startswith('/v5/market/')): label for label, path, params in tasks}
        pending[pool.submit(pages, '/v5/position/list', {'category': 'linear', 'settleCoin': 'USDT', 'limit': '200'})] = 'all_positions'
        pending[pool.submit(pages, '/v5/order/realtime', {'category': 'linear', 'settleCoin': 'USDT', 'limit': '50', 'openOnly': '0'})] = 'all_open_orders'
        for future in concurrent.futures.as_completed(pending):
            result[pending[future]] = future.result()
    # Books are one separate concurrent group, never sequentially called fresh.
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        books = {pool.submit(get, '/v5/market/orderbook', {'category': 'linear', 'symbol': s, 'limit': '50'}, False): s for s in SYMBOLS}
        for future in concurrent.futures.as_completed(books):
            result['book:' + books[future]] = future.result()
    print(json.dumps(dict(schema='kity_execution_micro_get_capture_v1',
        purpose='EXECUTION_ONLY_NOT_RESEARCH', started_ms=start,
        completed_ms=time.time_ns() // 1_000_000, base=BASE,
        selected_credential_sha256=hashlib.sha256(key.encode()).hexdigest(),
        credential_source='/root/by-bot/.env:TRADE_ACCOUNT_NAME (matches active process)',
        active_source_pid=PID, symbols=SYMBOLS, captures=result,
        broker_writes=0, remote_writes=0), allow_nan=False))


if __name__ == '__main__':
    main()
