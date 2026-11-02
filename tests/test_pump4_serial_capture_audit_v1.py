"""File replay proves source contracts; never fabricates a traded lifecycle."""
import copy,hashlib,json
from pathlib import Path
import pytest
from research_lab import pump4_serial_source_supervisor_v1 as M
from test_pump4_account_owner_v1 import inputs,FP
from test_pump4_bybit_sources_v1 import NOW
from test_pump4_serial_cost_release_v1 import closed_groups
from scripts.rehearse_pump4_bybit_v1 import MemoryBybit


def capture(tmp_path):
    b,_=inputs(MemoryBybit(tmp_path/'memory.json','normal'),now=NOW+4000)
    x=dict(schema='PUMP4_SERIAL_READ_ONLY_CAPTURE_V1',source_observed_ms=NOW+4000,
        account_fingerprint=FP,bundle=b,closed_pnl_sources=closed_groups(b,[]),registry=[],
        selected_packet_sha256='a'*64,collector_sha256='b'*64)
    p=tmp_path/'capture.json';p.write_text(json.dumps(x))
    return p,hashlib.sha256(p.read_bytes()).hexdigest(),x


def audit(*a,**k):
    assert callable(getattr(M,'audit_capture',None)), 'Missing explicit file-only cost-source replay'
    return M.audit_capture(*a,**k)


def test_pinned_flat_capture_replays_at_original_clock_without_owner_or_network(tmp_path,monkeypatch):
    p,pin,x=capture(tmp_path)
    monkeypatch.setattr(M,'selected_owner',lambda *a,**k:pytest.fail('No financial owner during audit'))
    out=tmp_path/'receipt.json';got=audit(p,pin,out,clock=lambda:NOW+86400000)
    assert got['status']=='FLAT_SOURCE_REPLAY_PASS_NO_LIFECYCLE'
    assert got['source_observed_ms']==NOW+4000 and got['replayed_ms']==NOW+86400000
    assert got['orders_allowed'] is False and got['money_authority'] is False
    assert got['cost_finality_proven'] is False and got['nonempty_cost_contract_qualified'] is False
    assert json.loads(out.read_bytes())==got
    before=out.read_bytes()
    with pytest.raises(FileExistsError):audit(p,pin,out,clock=lambda:NOW+86400000)
    assert out.read_bytes()==before


@pytest.mark.parametrize('fault',['pin','body','registry','foreign','closed_partial'])
def test_bad_or_nonempty_capture_is_rejected_before_output(tmp_path,fault):
    p,pin,x=capture(tmp_path)
    if fault=='body':x['bundle']['captures']['wallet']['pages' if 'pages' in x['bundle']['captures']['wallet'] else 'body']={}
    if fault=='registry':x['registry']=[{}]
    if fault=='foreign':x['closed_pnl_sources'][0]['group']['pages'][0]['body']['result']['list']=[dict(orderId='foreign')]
    if fault=='closed_partial':x['closed_pnl_sources'][0]['group']['complete']=False
    if fault!='pin':p.write_text(json.dumps(x));pin=hashlib.sha256(p.read_bytes()).hexdigest()
    else:pin='0'*64
    with pytest.raises((ValueError,KeyError,TypeError)):audit(p,pin,tmp_path/'out.json',clock=lambda:NOW+9000)
    assert not (tmp_path/'out.json').exists()


def test_cli_audit_needs_explicit_off_and_ignores_no_missing_pin(tmp_path,capsys):
    from scripts.run_pump4_serial_source_off_v1 import main
    p,pin,_=capture(tmp_path);out=tmp_path/'cli.json'
    assert main(['--audit-capture',str(p),'--audit-sha256',pin,'--audit-output',str(out)])==0
    assert not out.exists() and json.loads(capsys.readouterr().out)['status']=='ORDERS_OFF_NO_REQUESTS'
    assert main(['--orders-off','--audit-capture',str(p),'--audit-sha256',pin,'--audit-output',str(out)])==0
    assert out.exists() and json.loads(capsys.readouterr().out)['broker_writes']==0
