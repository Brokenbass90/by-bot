import copy,importlib,json
import pytest
from research_lab.pump4_bybit_sources_v1 import H
from test_pump4_bybit_sources_v1 import capture,NOW
from test_pump4_stream_intake_v1 import fixture,metadata

def module():
 try:return importlib.import_module('scripts.run_pump4_stream_v1')
 except ImportError:pytest.fail('Resident public stream transport missing')

def test_default_cli_never_constructs_source_or_creates_root(tmp_path,capsys):
 m=module();assert m.main(['--root',str(tmp_path/'unused')])==0
 assert not (tmp_path/'unused').exists();assert json.loads(capsys.readouterr().out)['status']=='ORDERS_OFF_NO_REQUESTS'

def test_missing_bar_recovery_is_immutable_and_not_current(tmp_path):
 m=module();s,t,bar,expected=fixture(tmp_path);t[0]=NOW+200;calls=[]
 def get(path,params):
  calls.append((path,params));return capture(path,params,dict(category='linear',symbol='ZROUSDT',list=[[str(bar[0]),*map(str,bar[1:]),'0']]),at=NOW+100)
 with s._writer():r=m.recover(s,NOW,metadata(),get=get)
 assert r['recovered']==1 and len(calls)==1
 obs=json.loads((s.root/'observations'/(expected['decision_id']+'.json')).read_text());assert obs['mode']=='CATCHUP_REPLAY' and obs['decision']['first_observed_ms']==NOW+200
 before=(s.root/'intake/ZROUSDT.jsonl').read_bytes()
 with s._writer():m.recover(s,NOW,metadata(),get=lambda *a:pytest.fail('No repeat once cursor current'))
 assert before==(s.root/'intake/ZROUSDT.jsonl').read_bytes()


def test_invalid_recovery_retains_capture_without_advancing(tmp_path):
 m=module();s,t,bar,_=fixture(tmp_path);t[0]=NOW+200;before=(s.root/'intake/ZROUSDT.jsonl').read_bytes()
 def get(path,params):
  return capture(path,params,dict(category='linear',symbol='ZROUSDT',list=[]),at=NOW+100)
 with s._writer():
  r=m.recover(s,NOW,metadata(),get=get)
 assert r['blocked'] and (s.root/'intake/ZROUSDT.jsonl').read_bytes()==before
 assert list((s.root/'ws-recovery'/str(NOW)).glob('*.capture.json'))


def test_monotonic_discontinuity_fails_before_entry():
 m=module()
 with pytest.raises(ValueError):m.clock_guard(1000,0,3001,1000000000)


def test_dependency_manifest_wrong_pin_rejected_before_import(tmp_path):
 m=module();p=tmp_path/'dependency.json';p.write_text('{}')
 with pytest.raises(ValueError):m.verify_dependencies(p,'0'*64)


def test_recovery_refuses_missing_epoch_before_network_or_append(tmp_path):
 m=module();s,t,bar,_=fixture(tmp_path);t[0]=NOW+200;(s.root/'epochs/ZROUSDT.json').unlink();before=(s.root/'intake/ZROUSDT.jsonl').read_bytes()
 with s._writer():r=m.recover(s,NOW,metadata(),get=lambda *a:pytest.fail('Epoch must precede capture'))
 assert r['blocked'] and (s.root/'intake/ZROUSDT.jsonl').read_bytes()==before


def test_restart_skips_existing_setup_and_hour_without_rewrite(tmp_path):
 m=module();target=NOW+H
 assert m.unspent_target(tmp_path,NOW+1)==target
 (tmp_path/'ws-setup'/str(target)).mkdir(parents=True)
 assert m.unspent_target(tmp_path,NOW+1) is None
 assert m.unspent_target(tmp_path,target+1)==target+H


def test_setup_attempt_is_durable_before_first_metadata_request(tmp_path,monkeypatch):
 m=module();s,t,_,_=fixture(tmp_path);monkeypatch.setattr(m,'ROOT',tmp_path)
 monkeypatch.setattr(m,'now',lambda:NOW+1);monkeypatch.setattr(m,'StreamIntake',lambda *a,**kw:s)
 monkeypatch.setattr(m,'verify_dependencies',lambda *a,**kw:{})
 def failed(folder):
  assert (folder/'attempt.json').is_file(),'FIRST_REQUEST_MUST_HAVE_DURABLE_ATTEMPT'
  raise OSError('first metadata request failed')
 monkeypatch.setattr(m,'metadata',failed)
 with pytest.raises(OSError,match='first metadata'):
  m.main(['--run','--once','--root',str(tmp_path/'.private/state'),'--dependencies',str(tmp_path/'dep.json'),'--dependencies-sha256','0'*64])
 assert m.unspent_target(s.root,NOW+1) is None
