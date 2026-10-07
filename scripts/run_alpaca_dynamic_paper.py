#!/usr/bin/env python3
"""One isolated broker-PAPER lifecycle. Default GET-only; never a LIVE sender."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib import request, error
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab.alpaca_dynamic_paper import PAPER, CORE, execute_paper, result
from research_lab.alpaca_dynamic_paper_maintenance import maintain_paper, rearm_cid, unwind_cid
from research_lab.alpaca_dynamic_v1 import digest, positive
from scripts.equities_alpaca_paper_bridge import AlpacaClient, AlpacaAPIError


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('PAPER_HTTP_REDIRECT_REFUSED')


class PaperClient(AlpacaClient):
    """Exact host, no redirects/proxies; writes restricted to this receipt's IDs."""
    def __init__(self, key, secret, owned_client_ids=()):
        super().__init__(PAPER, key, secret)
        self.owned_client_ids = frozenset(owned_client_ids)
        self.paper_exit_scope = None
        self.opener = request.build_opener(request.ProxyHandler({}), NoRedirect(), request.HTTPSHandler(context=self._ssl_ctx))

    def _request(self, method, path, payload=None):
        parts = urlsplit(path)
        route = parts.path
        if self.base_url != PAPER or parts.scheme or parts.netloc or parts.fragment or not path.startswith('/v2/'):
            raise ValueError('PAPER_ENDPOINT_OR_PATH')
        allowed_get = route in {'/v2/account', '/v2/clock', '/v2/positions', '/v2/orders', '/v2/orders:by_client_order_id'} or bool(re.fullmatch(r'/v2/orders/[A-Za-z0-9_-]{1,128}', route))
        if method == 'GET':
            if not allowed_get or payload is not None:
                raise ValueError('PAPER_READ_ROUTE')
        elif method == 'POST':
            emergency = isinstance(payload, dict) and (payload.get('side'), payload.get('type')) == ('sell', 'market')
            if (route != '/v2/orders' or parts.query or not isinstance(payload, dict)
                or payload.get('client_order_id') not in self.owned_client_ids
                or ((payload.get('side'), payload.get('type')) not in {('buy', 'limit'), ('sell', 'stop')} and not emergency)):
                raise ValueError('PAPER_WRITE_ROUTE_OR_OWNERSHIP')
            if emergency:
                scope = self.paper_exit_scope
                if (not scope or payload.get('client_order_id') != scope['cid']
                    or payload.get('symbol') != scope['symbol'] or payload.get('time_in_force') != 'day'
                    or not 0 < positive(payload['qty']) <= positive(scope['qty'])):
                    raise ValueError('PAPER_EMERGENCY_PROOF_REQUIRED')
        elif method == 'DELETE':
            if not re.fullmatch(r'/v2/orders/[A-Za-z0-9_-]{1,128}', route) or parts.query:
                raise ValueError('PAPER_CANCEL_ROUTE')
            owned = self._request('GET', path)
            scoped_stop = (self.paper_exit_scope and owned.get('symbol') == self.paper_exit_scope['symbol']
                           and owned.get('side') == 'sell' and owned.get('type') == 'stop'
                           and positive(owned['qty']) <= positive(self.paper_exit_scope['qty']))
            if owned.get('client_order_id') not in self.owned_client_ids or (owned.get('side') != 'buy' and not scoped_stop):
                raise ValueError('PAPER_CANCEL_OWNERSHIP')
        else:
            raise ValueError('PAPER_METHOD_REFUSED')
        body = json.dumps(payload, allow_nan=False).encode() if payload is not None else None
        req = request.Request(PAPER + path, data=body, method=method, headers=self._headers())
        try:
            with self.opener.open(req, timeout=10) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError('PAPER_RESPONSE_TOO_LARGE')
            return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            # Do not log secret-bearing headers or an unrestricted remote body.
            raise AlpacaAPIError(exc.code, f'PAPER_HTTP_{exc.code}') from exc

    def submit_stop_sell(self, symbol, *, qty, stop_price, time_in_force='day', client_order_id=None):
        return self._request('POST', '/v2/orders', {'symbol': symbol, 'side': 'sell', 'type': 'stop',
            'qty': str(positive(qty)), 'stop_price': format(positive(stop_price), '.2f'),
            'time_in_force': time_in_force, 'client_order_id': client_order_id})

    def authorize_owned_unwind(self, proof, cid):
        from scripts.equities_alpaca_paper_bridge import _validated_paper_kill_scope
        if len(proof.get('positions', [])) != 1 or cid not in self.owned_client_ids:
            raise ValueError('PAPER_SINGLE_UNWIND_PROOF_REQUIRED')
        _validated_paper_kill_scope(proof=proof, client=self, base_url=PAPER)
        row = proof['positions'][0]
        self.paper_exit_scope = {**row, 'cid': cid, 'proof': proof}

    def close_position(self, symbol):
        # Never DELETE /positions: submit one quantity-bound owned market exit.
        from scripts.equities_alpaca_paper_bridge import _validated_paper_kill_scope
        scope = self.paper_exit_scope
        if not scope or symbol != scope['symbol']:
            raise ValueError('PAPER_EMERGENCY_PROOF_REQUIRED')
        _validated_paper_kill_scope(proof=scope['proof'], client=self, base_url=PAPER)
        existing = self.get_order_by_client_id(scope['cid'])
        if existing is not None:
            return existing
        rows = [p for p in self.list_positions() if p['symbol'] == symbol]
        if len(rows) != 1 or not 0 < positive(rows[0]['qty']) <= positive(scope['qty']):
            raise ValueError('PAPER_SCOPED_EXIT_QUANTITY_CONFLICT')
        return self.submit_market_sell_qty(symbol, float(positive(rows[0]['qty'])), client_order_id=scope['cid'])


def shared_lock_path(paper_env, env, key_id):
    """Use the established broker checkout's lock, never this package's ROOT."""
    broker_root = Path(paper_env).absolute().parent.parent
    if Path(paper_env).absolute().parent.name != 'configs':
        raise ValueError('PAPER_PROFILE_NOT_IN_BROKER_CONFIGS')
    configured = env.get('ALPACA_BRIDGE_LOCK_PATH')
    path = Path(configured) if configured else broker_root/'runtime/locks'/(
        'alpaca_bridge_'+hashlib.sha256((PAPER+'|'+key_id).encode()).hexdigest()[:16]+'.lock')
    if not path.is_absolute() or not path.is_relative_to(broker_root/'runtime') or any(p.is_symlink() for p in [path,*path.parents]):
        raise ValueError('SHARED_ACCOUNT_LOCK_SOURCE_CONFLICT')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, default=ROOT/'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json')
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--plan-store', type=Path, required=True, help='source replacement.sqlite; plan must exist unchanged')
    parser.add_argument('--paper-env', type=Path, required=True, help='exact PAPER profile; no LIVE credential fallback')
    parser.add_argument('--paper-account', required=True)
    parser.add_argument('--runtime', type=Path, default=ROOT/'.private/alpaca_dynamic_paper_20261006/broker_paper')
    parser.add_argument('--paper-submit', action='store_true', help='PAPER-only; default reads only')
    parser.add_argument('--paper-maintain', action='store_true', help='existing owned PAPER lifecycle only; no entries')
    parser.add_argument('--paper-unwind', action='store_true', help='explicit scoped owned PAPER unwind; requires maintenance')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        from dotenv import dotenv_values
        import sqlite3
        plan, policy = json.loads(args.plan.read_text()), json.loads(args.policy.read_text())
        if digest(policy) != 'fe72557bd7c7437eda328047e81980ee762ec794ac240494ec47d3de4f6f400d':
            raise ValueError('SEALED_POLICY_CONFLICT')
        with sqlite3.connect(args.plan_store.absolute().as_uri()+'?mode=ro', uri=True) as db:
            row = db.execute('SELECT payload FROM intents WHERE entry=?', (plan['slot_entry_order_id'],)).fetchone()
        if not row or any(json.loads(row[0]).get(k) != plan.get(k) for k in [*CORE, 'receipt_id', 'client_order_id', 'status', 'money_authority', 'orders_allowed']):
            raise ValueError('PLAN_NOT_IN_SOURCE_BOOK')
        if args.runtime.exists() and any(args.runtime.iterdir()) and not (args.runtime/'paper.sqlite').is_file():
            raise ValueError('PAPER_RUNTIME_NOT_ISOLATED')
        env = dotenv_values(args.paper_env)
        if env.get('ALPACA_BASE_URL') != PAPER:
            raise ValueError('PAPER_PROFILE_REQUIRED')
        identity = digest({'parent': plan['receipt_id'], 'paper_account': args.paper_account})
        if args.paper_unwind and not args.paper_maintain:
            raise ValueError('PAPER_UNWIND_REQUIRES_MAINTENANCE')
        client = PaperClient(env['ALPACA_API_KEY_ID'], env['ALPACA_API_SECRET_KEY'],
                             ['dyp-'+identity[:32], 'dys-'+identity[:32], unwind_cid(plan['receipt_id'], args.paper_account),
                              *[rearm_cid(plan['receipt_id'], args.paper_account, s['session']) for s in policy['calendar_sessions']]])
        lock_path = shared_lock_path(args.paper_env, env, client.key_id)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.paper_maintain:
                receipt = maintain_paper(plan=plan, policy=policy, client=client, expected_paper_id=args.paper_account,
                                         runtime=args.runtime, now_ms=time.time_ns()//1_000_000,
                                         send=args.paper_submit, unwind=args.paper_unwind)
            else:
                receipt = execute_paper(plan, policy, client, args.paper_account, args.runtime,
                                        time.time_ns()//1_000_000, send=args.paper_submit)
    except Exception as exc:
        receipt = result('BLOCKED_DATA', reason=str(exc) or type(exc).__name__)
    raw = json.dumps(receipt, indent=2, allow_nan=False)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as handle:
            handle.write(raw)
    print(raw, end='')
    return 2 if receipt['status'].startswith('BLOCKED') else 0


if __name__ == '__main__':
    raise SystemExit(main())
