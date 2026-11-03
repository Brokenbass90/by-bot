"""Explicit operator date exception, isolated fake wire; never a live grant."""
import copy,json,hashlib
from pathlib import Path
import pytest
from research_lab import alpaca_monthly_binding_v1 as bookmod
from research_lab import alpaca_monthly_native_binding_v1 as mod
from research_lab.alpaca_dynamic_v1 import canonical,digest
from test_alpaca_monthly_native_binding_v1 import setup,ticket,ms
from test_alpaca_monthly_account_transport_v1 import connect_wire
from test_alpaca_monthly_standing_v1 import standing,resign


def recovery(setup):
 b,s,a,io,now=setup;t=ticket(setup);at=ms('2026-11-03T14:30:00')
 frozen=a.runtime.parent/'frozen-history.json';frozen.write_bytes(canonical(dict(schema='MONTHLY_INITIAL_RECOVERY_FROZEN_HISTORY_V1',original_selection_sha256=digest(s),source_sha256=s['source_sha256'],source_available_ms=s['source_available_ms'],history={})))
 policy=dict(frozen_history=dict(path=str(frozen),sha256=hashlib.sha256(frozen.read_bytes()).hexdigest()),schema='ALPACA_MONTHLY_INITIAL_ENTRY_RECOVERY_V1',original_selection_id=s['selection_id'],
  original_selection_sha256=digest(s),original_ticket_sha256=t['ticket_sha256'],
  entry_session='2026-11-03',open_ms=at,close_ms=at+300000,symbol=t['symbol'],
  max_notional_usd=str(t['notional']),max_entries=1,created_ms=at-3600000)
 return policy,t,at


def test_original_missed_window_stays_closed(setup):
 b,s,a,io,now=setup;p,t,at=recovery(setup)
 assert b.monthly_actions(s['selection_id'],now_ms=at)['status']=='NO_SEND'
 with pytest.raises(ValueError,match='STALE_SIGNAL'):
  b.seal_selection({},s['calendar'],signal_session=s['signal_session'],entry_session=p['entry_session'],source_available_ms=s['source_available_ms'],source_sha256=s['source_sha256'],now_ms=at)


def test_recovery_is_new_append_only_selection_actual_entry_day_and_idempotent(setup):
 b,s,a,io,now=setup;p,t,at=recovery(setup);before=copy.deepcopy(b.rows('selections'))
 r=b.seal_initial_recovery(p,t,now_ms=at-1000)
 assert r['selection_id']!=s['selection_id'] and r['entry_session']=='2026-11-03'
 assert r['picks']==s['picks'] and r['source_available_ms']==s['source_available_ms']
 assert next(v for v in b.rows('selections') if v['selection_id']==s['selection_id'])==before[0]
 assert b.seal_initial_recovery(p,t,now_ms=at)==r
 assert len(b.rows('selections'))==2 and b.rows('positions')==[] and io.sent==[]


@pytest.mark.parametrize('fault',['day','start','end','symbol','size','original','ticket','entries','extra','history_pin'])
def test_recovery_policy_cannot_widen_date_size_or_identity(setup,fault):
 b,s,a,io,now=setup;p,t,at=recovery(setup)
 if fault=='day':p['entry_session']='2026-11-04'
 elif fault=='start':p['open_ms']+=1
 elif fault=='end':p['close_ms']+=1
 elif fault=='symbol':p['symbol']='OTHER'
 elif fault=='size':p['max_notional_usd']=str(float(p['max_notional_usd'])+1)
 elif fault=='original':p['original_selection_sha256']='0'*64
 elif fault=='ticket':p['original_ticket_sha256']='0'*64
 elif fault=='entries':p['max_entries']=2
 elif fault=='history_pin':p['frozen_history']['sha256']='f'*64
 else:p['automatic_retry']=True
 with pytest.raises(ValueError):b.seal_initial_recovery(p,t,now_ms=at-1000)
 assert len(b.rows('selections'))==1 and io.sent==[]


def test_expired_recovery_never_moves_to_later_day(setup):
 b,s,a,io,now=setup;p,t,at=recovery(setup)
 with pytest.raises(ValueError,match='RECOVERY_WINDOW'):b.seal_initial_recovery(p,t,now_ms=at+300000)
 assert len(b.rows('selections'))==1


def test_recovery_requires_initial_empty_book(setup):
 b,s,a,io,now=setup;p,t,at=recovery(setup)
 with b.db() as db:b._save(db,'dispatches','old',{'status':'unknown'})
 with pytest.raises(ValueError,match='RECOVERY_NOT_INITIAL'):b.seal_initial_recovery(p,t,now_ms=at-1000)


def prepared(setup,monkeypatch,approved):
 b,s,a,io,now=setup;p,t,at=recovery(setup);client,writes,lose=connect_wire(setup,monkeypatch);scope=standing(a,now,limit=1)
 path=a.runtime.parent/'tickets';path.mkdir(exist_ok=True);(path/(t['client_order_id']+'.json')).write_bytes(canonical(t))
 if approved:scope.update(selection_policy=mod.RECOVERY_SELECTION_POLICY,initial_recovery=p);resign(a,scope)
 r=b.seal_initial_recovery(p,t,now_ms=at-1000)
 io.get_clock=lambda:dict(is_open=True,timestamp='2026-11-03T14:30:00Z')
 io.latest_quote=lambda symbol:dict(ap='311',t='2026-11-03T14:30:00Z')
 # Fake wire returns execution times at the actual newly approved date.
 http=client._http
 def actual_date(url,method,payload=None):
  out=http(url,method,payload)
  def shift(v):
   if isinstance(v,dict):
    for k,x in v.items():
     if isinstance(x,str) and '2026-11-02' in x:v[k]=x.replace('2026-11-02','2026-11-03')
     else:shift(x)
   elif isinstance(v,list):
    for x in v:shift(x)
  shift(out);return out
 client._http=actual_date
 saved=a.prepare_entry({},r['selection_id'],t['symbol'],quote=dict(ask=311.,quote_ts=at,received_ms=at,source='recorded-iex'),now_ms=at,cash=487.42,open_equity=487.42)
 return b,s,a,io,p,t,at,saved,writes,r,scope


def test_old_standing_go_cannot_authorize_recovery(setup,monkeypatch):
 b,s,a,io,p,t,at,saved,writes,r,scope=prepared(setup,monkeypatch,False)
 with pytest.raises(ValueError,match='RECOVERY_SEPARATE_SCOPE'):a.enter(saved,now_ms=at,apply=True)
 assert writes==[] and b.rows('positions')==[]


def test_separate_recovery_full_native_fill_stop_restart_actual_day(setup,monkeypatch):
 b,s,a,io,p,t,at,saved,writes,r,scope=prepared(setup,monkeypatch,True)
 assert saved['entry_gate']['selection_cadence']=='OPERATOR_INITIAL_ENTRY_RECOVERY_V1'
 assert a.enter(saved,now_ms=at,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
 assert b.rows('positions')[0]['daily_state']['entry_session']=='2026-11-03'
 assert b.rows('positions')[0]['daily_state']['last_observed_session'] is None
 assert len(writes)==2 and a.enter(saved,now_ms=at+1000,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
 assert len(writes)==2
 # Window expiry must not remove existing custody.
 assert a._live_custody()['initial_recovery']==p


@pytest.mark.parametrize('fault',['notional','symbol','policy','quote','expired'])
def test_recovery_ticket_and_freshness_enforced_before_wire(setup,monkeypatch,fault):
 b,s,a,io,p,t,at,saved,writes,r,scope=prepared(setup,monkeypatch,True)
 if fault=='notional':saved['notional']+=1
 elif fault=='symbol':saved['symbol']='OTHER'
 elif fault=='policy':saved['entry_gate']['initial_recovery_policy_sha256']='f'*64
 elif fault=='quote':saved['entry_gate']['quote_ts']=at-300001
 else:at+=300000
 saved['entry_gate']['receipt_sha256']=digest({k:v for k,v in saved['entry_gate'].items() if k!='receipt_sha256'})
 saved['ticket_sha256']=digest({k:v for k,v in saved.items() if k!='ticket_sha256'})
 with pytest.raises(ValueError):a.enter(saved,now_ms=at,apply=True)
 assert writes==[]
