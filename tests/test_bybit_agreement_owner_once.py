import hashlib
import hmac
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_lab import bybit_agreement_owner_once as a


KEY = 'fixture-key'
SECRET = 'fixture-secret'
PIN = 'a' * 64


class Venue:
    def __init__(self, *, master=True, wallet=None, code=0, timeout=False):
        self.master = master
        self.wallet = ['AccountTransfer'] if wallet is None else wallet
        self.code = code
        self.timeout = timeout
        self.posts = 0

    def __call__(self, method, path, headers, body):
        signed = str(headers['X-BAPI-TIMESTAMP']) + KEY + '10000' + (body.decode() if body else '')
        assert headers['X-BAPI-SIGN'] == hmac.new(SECRET.encode(), signed.encode(), hashlib.sha256).hexdigest()
        if method == 'GET':
            assert path == '/v5/user/query-api' and body is None
            return 200, json.dumps({'retCode': 0, 'result': {
                'isMaster': self.master, 'parentUid': '0', 'userID': 123,
                'readOnly': 0, 'permissions': {'Wallet': self.wallet},
            }}).encode()
        assert method == 'POST' and path == '/v5/user/agreement'
        assert body == b'{"categoryV2":1,"agree":true}'
        self.posts += 1
        if self.timeout:
            raise TimeoutError()
        return 200, json.dumps({'retCode': self.code, 'result': {}, 'time': 123456}).encode()


def run(root, venue):
    return a.execute_once(KEY, SECRET, '123', PIN, root, wire=venue, clock=lambda: 123000)


def test_success_retains_raw_hash_and_second_call_never_sends_again(tmp_path):
    venue = Venue()
    receipt = run(tmp_path, venue)
    assert receipt['status'] == 'AGREEMENT_ACCEPTED' and venue.posts == 1
    raw = (tmp_path / 'response.raw').read_bytes()
    assert receipt['raw_sha256'] == hashlib.sha256(raw).hexdigest()
    assert json.loads(raw)['retCode'] == 0
    assert run(tmp_path, venue)['status'] == 'AGREEMENT_ACCEPTED' and venue.posts == 1


@pytest.mark.parametrize('master,wallet', [(False, ['AccountTransfer']), (True, [])])
def test_bad_role_or_permission_never_claims_or_sends(tmp_path, master, wallet):
    venue = Venue(master=master, wallet=wallet)
    with pytest.raises(ValueError, match='MASTER_OR_PERMISSION'):
        run(tmp_path, venue)
    assert venue.posts == 0 and not (tmp_path / 'claim.json').exists()


def test_unknown_send_stays_spent_and_never_retries(tmp_path):
    venue = Venue(timeout=True)
    assert run(tmp_path, venue)['status'] == 'AGREEMENT_RESPONSE_UNKNOWN'
    assert run(tmp_path, venue)['status'] == 'AGREEMENT_RESPONSE_UNKNOWN'
    assert venue.posts == 1


def test_api_refusal_is_retained_without_retry(tmp_path):
    venue = Venue(code=10005)
    assert run(tmp_path, venue)['status'] == 'AGREEMENT_REFUSED'
    assert run(tmp_path, venue)['ret_code'] == 10005
    assert venue.posts == 1


def test_crash_after_durable_claim_never_repeats_dispatch(tmp_path):
    (tmp_path / 'claim.json').write_text('{}')
    venue = Venue()
    assert run(tmp_path, venue)['status'] == 'ALREADY_ATTEMPTED_UNKNOWN'
    assert venue.posts == 0


def test_tampered_raw_cannot_recover_as_accepted(tmp_path):
    venue = Venue()
    run(tmp_path, venue)
    (tmp_path / 'response.raw').write_text('{}')
    with pytest.raises(ValueError, match='RECEIPT_SOURCE_CONFLICT'):
        run(tmp_path, venue)
    assert venue.posts == 1


def test_default_cli_has_no_network_or_credential_access(monkeypatch, capsys):
    monkeypatch.setattr(a, 'operator_execute', lambda: pytest.fail('unexpected operator execution'))
    assert a.main([]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'OWNER_COMMAND_PREPARED_NO_NETWORK'


def operator_files(tmp_path, monkeypatch):
    project = tmp_path / 'project'
    private = project / '.private/kity_master_agreement_20261016'
    private.mkdir(parents=True)
    credential = project / '.private/kity_master_agreement_20261015/master-signing.env'
    credential.parent.mkdir()
    credential.write_text('BYBIT_BASE=https://api.bybit.com\nBYBIT_MASTER_API_KEY=fixture-key\nBYBIT_MASTER_API_SECRET=fixture-secret\n')
    proposal = dict(method='POST', origin='https://api.bybit.com', path='/v5/user/agreement',
                    body={'categoryV2': 1, 'agree': True}, signing_master_uid='123',
                    credential_source_sha256=hashlib.sha256(credential.read_bytes()).hexdigest(),
                    credential_key_sha256=hashlib.sha256(KEY.encode()).hexdigest())
    pin = hashlib.sha256(json.dumps(proposal, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    (private / 'agreement-proposal-v1.json').write_text(json.dumps(dict(proposal, proposal_sha256=pin)))
    (private / 'owner-legal-consent-v1.json').write_text(json.dumps(dict(proposal_sha256=pin, consent_received=True)))
    monkeypatch.setattr(a, '__file__', str(project / 'research_lab/bybit_agreement_owner_once.py'))
    return credential, private


def test_owner_frontend_builds_valid_remote_source_without_secrets_in_argv(tmp_path, monkeypatch, capsys):
    _, private = operator_files(tmp_path, monkeypatch)
    calls = []

    def ssh(argv, **kwargs):
        assert KEY not in repr(argv) and SECRET not in repr(argv)
        compile(kwargs['input'], 'operator-remote', 'exec')
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout='{"status":"AGREEMENT_ACCEPTED","ret_code":0,"http_status":200}', stderr='')

    monkeypatch.setattr(a.subprocess, 'run', ssh)
    assert a.operator_execute() == 0
    assert (private / 'owner_execution_receipt.json').stat().st_mode & 0o777 == 0o600
    assert a.operator_execute() == 0 and len(calls) == 1
    capsys.readouterr()


def test_changed_credential_file_stops_before_any_ssh(tmp_path, monkeypatch):
    credential, _ = operator_files(tmp_path, monkeypatch)
    credential.write_text('changed')
    monkeypatch.setattr(a.subprocess, 'run', lambda *args, **kwargs: pytest.fail('unexpected SSH'))
    with pytest.raises(ValueError, match='CREDENTIAL_SOURCE_CHANGED'):
        a.operator_execute()
