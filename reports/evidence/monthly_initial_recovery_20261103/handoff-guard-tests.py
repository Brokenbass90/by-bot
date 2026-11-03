import importlib.util,sys,time
from pathlib import Path
import pytest
sys.path.insert(0,'/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/tests')
from test_alpaca_monthly_native_binding_v1 import setup,ticket
from test_alpaca_monthly_account_transport_v1 import connect_wire
from test_alpaca_monthly_standing_v1 import standing

def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

@pytest.mark.parametrize('fault',['write','reload','retire','none'])
def test_selection_verified_before_retirement_and_rollback_keeps_old_rights(tmp_path,monkeypatch,fault):
 m=load('handoff','/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/.private/monthly_initial_recovery_20261103/owner-review-initial-recovery-v1/handoff.py');target=tmp_path/'unit';target.write_bytes(b'old');revocation=tmp_path/'revoked';calls=[]
 original_put=m.put
 def put(p,b,*a):
  if fault=='write' and bytes(b)==b'new':raise OSError('write failed')
  return original_put(p,b,*a)
 def ctl(*args):
  calls.append(args)
  if args==('daemon-reload',) and fault=='reload' and target.read_bytes()==b'new':raise OSError('reload failed')
  return 'ExecStart=new\nNeedDaemonReload=no\n'
 def retire():
  assert target.read_bytes()==b'new' and ('daemon-reload',) in calls
  if fault=='retire':raise OSError('retire failed')
  revocation.write_bytes(b'yes')
 monkeypatch.setattr(m,'put',put);monkeypatch.setattr(m,'ctl',ctl)
 if fault=='none':m.select_unit(target,b'old',b'new',revocation,retire)
 else:
  with pytest.raises(OSError):m.select_unit(target,b'old',b'new',revocation,retire)
 assert target.read_bytes()==(b'new' if fault=='none' else b'old')
 assert revocation.exists()==(fault=='none')

def test_real_guard_ast_valid_window_has_globals_and_never_submits(setup,tmp_path,monkeypatch):
 p=load('probe','/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/.private/monthly_initial_recovery_20261103/owner-review-initial-recovery-v1/probe-v2.py');b,s,n,io,now=setup
 connect_wire(setup,monkeypatch);standing(n,now);t=ticket(setup);folder=tmp_path/'anchors';folder.mkdir()
 fn=p.load_final_guard(n,t,next(r for r in s['calendar'] if r['session']==s['entry_session']),folder,now,time.monotonic())
 fn();assert not io.sent and not n.reentry.exists() and not b.rows('positions')


def test_uncertain_retirement_keeps_verified_replacement_and_never_clears_marker(tmp_path,monkeypatch):
 m=load('handoff_partial','/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/.private/monthly_initial_recovery_20261103/owner-review-initial-recovery-v1/handoff.py');target=tmp_path/'unit';target.write_bytes(b'old');revocation=tmp_path/'revoked'
 monkeypatch.setattr(m,'ctl',lambda *args:'NeedDaemonReload=no\n')
 def retire():revocation.write_bytes(b'durable stop marker');raise OSError('publication uncertain')
 with pytest.raises(OSError):m.select_unit(target,b'old',b'new',revocation,retire)
 assert target.read_bytes()==b'new' and revocation.read_bytes()==b'durable stop marker'


@pytest.mark.parametrize('provided',[None,'GO previous_scope'])
def test_new_date_requires_exact_go_before_any_action(monkeypatch,provided):
 m=load('recovery_go_guard','/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/.private/monthly_initial_recovery_20261103/owner-review-initial-recovery-v1/handoff.py')
 calls=[]
 monkeypatch.setattr(m,'raw',lambda *a,**k:b'{"owner_go_text":"GO exact_recovery_scope"}')
 monkeypatch.setattr(m,'put',lambda *a,**k:calls.append('write'))
 monkeypatch.setattr(m,'ctl',lambda *a,**k:calls.append('systemctl'))
 with pytest.raises(ValueError,match='SEPARATE_EXACT_OWNER_GO_REQUIRED'):m.run('apply',provided)
 assert not calls
