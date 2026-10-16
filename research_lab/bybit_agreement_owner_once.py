"""Owner-run legal acceptance only. Agents must never invoke --owner-execute.

Default invocation has no network/credential access. No order/transfer endpoint
is implemented. The owner, personally, runs the explicit execution command.
"""
import argparse
import base64
import hashlib
import hmac
import inspect
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

BODY = b'{"categoryV2":1,"agree":true}'
BASE = 'https://api.bybit.com'
ENDPOINT = '/v5/user/agreement'
AGREEMENT = 'https://www.bybit.com/en/legal/service-specific-terms/Derivative-Contract-Terms-TradFi-Perps'


def _write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as f:
        if f.write(data) != len(data):
            raise OSError('INCOMPLETE_WRITE')
        f.flush()
        os.fsync(f.fileno())
    parent = os.open(Path(path).parent, os.O_RDONLY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('REDIRECT_FORBIDDEN')


def http_request(method, path, headers, body):
    if (method, path) not in {('GET', '/v5/user/query-api'), ('POST', ENDPOINT)}:
        raise ValueError('ENDPOINT_SCOPE')
    if (method == 'GET' and body is not None) or (method == 'POST' and body != BODY):
        raise ValueError('BODY_SCOPE')
    req = urllib.request.Request(BASE + path, headers=headers, data=body, method=method)
    try:
        with urllib.request.build_opener(_NoRedirect()).open(req, timeout=12) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError('RESPONSE_BOUND')
            return response.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(2_000_001)


def execute_once(key, secret, expected_uid, proposal_sha, root, *, wire=http_request, clock=None):
    """Executed by the owner only; wire injection is the external HTTP boundary."""
    clock = clock or (lambda: time.time_ns() // 1_000_000)
    root = Path(root)
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    claim, rawfile, resultfile = (root / n for n in ('claim.json', 'response.raw', 'receipt.json'))
    if any(p.is_symlink() for p in (root, claim, rawfile, resultfile)):
        raise ValueError('SOURCE_SYMLINK')
    if resultfile.exists():
        try:
            previous = json.loads(resultfile.read_bytes())
            assert previous['proposal_sha256'] == proposal_sha and previous['master_uid'] == expected_uid
            if previous.get('raw_sha256'):
                raw = rawfile.read_bytes()
                assert hashlib.sha256(raw).hexdigest() == previous['raw_sha256']
                assert json.loads(raw)['retCode'] == previous['ret_code']
                if previous['status'] == 'AGREEMENT_ACCEPTED':
                    assert previous['http_status'] == 200 and type(previous['ret_code']) is int and previous['ret_code'] == 0
            elif previous['status'] != 'AGREEMENT_RESPONSE_UNKNOWN':
                raise ValueError('MISSING_RAW')
        except Exception:
            raise ValueError('RECEIPT_SOURCE_CONFLICT') from None
        return previous
    if claim.exists():
        return dict(status='ALREADY_ATTEMPTED_UNKNOWN', proposal_sha256=proposal_sha,
                    automatic_retry_allowed=False, additional_posts=0)

    def signed(method, path, body=None):
        stamp = str(clock())
        message = stamp + key + '10000' + (body.decode() if body else '')
        headers = {'X-BAPI-API-KEY': key, 'X-BAPI-TIMESTAMP': stamp,
                   'X-BAPI-RECV-WINDOW': '10000', 'Content-Type': 'application/json',
                   'X-BAPI-SIGN': hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()}
        return wire(method, path, headers, body)

    code, raw = signed('GET', '/v5/user/query-api')
    response = json.loads(raw)
    identity = response.get('result', {})
    wallet = identity.get('permissions', {}).get('Wallet', [])
    if (code != 200 or type(response.get('retCode')) is not int or response['retCode'] != 0
        or identity.get('isMaster') is not True or str(identity.get('parentUid')) != '0'
        or str(identity.get('userID')) != expected_uid or type(identity.get('readOnly')) is not int
        or identity['readOnly'] != 0 or not isinstance(wallet, list)
        or not any(p in wallet for p in ('AccountTransfer', 'SubMemberTransfer'))):
        raise ValueError('MASTER_OR_PERMISSION_CONFLICT')
    metadata = dict(schema='BYBIT_PERSONAL_AGREEMENT_EXECUTION_V1', master_uid=expected_uid,
                    proposal_sha256=proposal_sha, method='POST', path=ENDPOINT,
                    body_sha256=hashlib.sha256(BODY).hexdigest(), at_ms=clock(),
                    identity_raw_sha256=hashlib.sha256(raw).hexdigest(), orders=0, transfers=0)
    try:
        _write(claim, json.dumps(metadata, sort_keys=True).encode())
    except FileExistsError:
        return dict(status='ALREADY_ATTEMPTED_UNKNOWN', additional_posts=0)
    result = dict(metadata, completed_ms=None, automatic_retry_allowed=False)
    try:
        code, raw = signed('POST', ENDPOINT, BODY)
        _write(rawfile, raw)
        result.update(http_status=code, raw_sha256=hashlib.sha256(raw).hexdigest())
        response = json.loads(raw)
        ret = response.get('retCode')
        if type(ret) is not int:
            raise ValueError('INVALID_RESPONSE_SCHEMA')
        result.update(ret_code=ret, status='AGREEMENT_ACCEPTED' if code == 200 and ret == 0 else 'AGREEMENT_REFUSED')
    except Exception as exc:
        result.update(status='AGREEMENT_RESPONSE_UNKNOWN', error_type=type(exc).__name__)
    result['completed_ms'] = clock()
    _write(resultfile, json.dumps(result, sort_keys=True).encode())
    return result


def operator_execute():
    """Called personally by owner, never by an agent, service, timer or monitor."""
    project = Path(__file__).resolve().parents[1]
    private = project / '.private/kity_master_agreement_20261016'
    existing = private / 'owner_execution_receipt.json'
    if existing.exists():
        result = json.loads(existing.read_bytes())
        print(json.dumps({k: result.get(k) for k in ('status', 'ret_code', 'http_status')}))
        return 0 if result.get('status') == 'AGREEMENT_ACCEPTED' else 2
    proposal = json.loads((private / 'agreement-proposal-v1.json').read_bytes())
    pin = proposal.pop('proposal_sha256')
    if hashlib.sha256(json.dumps(proposal, sort_keys=True, separators=(',', ':')).encode()).hexdigest() != pin:
        raise ValueError('PROPOSAL_PIN_CONFLICT')
    if (proposal['method'], proposal['origin'], proposal['path'], proposal['body']) != ('POST', BASE, ENDPOINT, {'categoryV2': 1, 'agree': True}):
        raise ValueError('PROPOSAL_SCOPE_CONFLICT')
    path = project / '.private/kity_master_agreement_20261015/master-signing.env'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != proposal['credential_source_sha256']:
        raise ValueError('CREDENTIAL_SOURCE_CHANGED_REVERIFY_ONLY')
    env = {}
    for line in raw.decode().splitlines():
        k, sep, v = line.partition('=')
        if sep and not k.lstrip().startswith('#'):
            env[k.strip()] = v.strip().strip('"').strip("'")
    key, secret = env['BYBIT_MASTER_API_KEY'], env['BYBIT_MASTER_API_SECRET']
    if env['BYBIT_BASE'] != BASE or hashlib.sha256(key.encode()).hexdigest() != proposal['credential_key_sha256']:
        raise ValueError('CREDENTIAL_BINDING_CONFLICT')
    approval = json.loads((private / 'owner-legal-consent-v1.json').read_bytes())
    if approval.get('proposal_sha256') != pin or approval.get('consent_received') is not True:
        raise ValueError('OWNER_CONSENT_NOT_BOUND')
    definitions = '\n'.join(inspect.getsource(f) for f in (_write, _NoRedirect, http_request, execute_once))
    source = ('import hashlib,hmac,json,os,time,urllib.request,urllib.error\nfrom pathlib import Path\n'
              + 'BODY=' + repr(BODY) + '\nBASE=' + repr(BASE) + '\nENDPOINT=' + repr(ENDPOINT) + '\n' + definitions
              + '\nr=execute_once(' + repr(key) + ',' + repr(secret) + ',' + repr(proposal['signing_master_uid'])
              + ',' + repr(pin) + ",Path('/opt/bybot-research/bybit-agreement-owner-20261016'))\n"
              + "print(json.dumps(r))\n")
    # Secrets are supplied only over encrypted stdin, never argv or remote files.
    call = subprocess.run(['ssh', '-i', '/Users/nikolay.bulgakov/.ssh/by-bot', '-o', 'BatchMode=yes',
                           '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
                           'root@64.226.73.119', '/root/by-bot/.venv/bin/python', '-B', '-'],
                          input=source, text=True, capture_output=True, timeout=50)
    if call.returncode:
        result = dict(status='OWNER_SSH_RESULT_UNKNOWN', automatic_retry_allowed=False,
                      stderr_sha256=hashlib.sha256(call.stderr.encode()).hexdigest())
    else:
        result = json.loads(call.stdout)
    _write(existing, json.dumps(result, sort_keys=True).encode())
    print(json.dumps({k: result.get(k) for k in ('status', 'ret_code', 'http_status')}))
    return 0 if result.get('status') == 'AGREEMENT_ACCEPTED' else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner-execute', action='store_true', help='Owner personally submits the sole legal request')
    args = parser.parse_args(argv)
    if args.owner_execute:
        return operator_execute()
    print(json.dumps(dict(status='OWNER_COMMAND_PREPARED_NO_NETWORK', method='POST', path=ENDPOINT,
                         body=json.loads(BODY), agreement=AGREEMENT, orders_allowed=False)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
