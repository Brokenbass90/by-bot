import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from bot.kity_m3_orders_off import digest
from research_lab.kity_micro_account_bridge_v1 import MicroAccountBridge
from research_lab.kity_micro_bounded_owner_v2 import BoundedSupervisor
from research_lab.kity_micro_bounded_owner_v2 import bound_config_pin
from research_lab.kity_micro_physical_owner_v1 import AccountLease, PhysicalOwner, publish
from research_lab.kity_micro_transport_v1 import SourceError, BybitReadTransport
from test_kity_micro_account_bridge_v1 import Owner, journal
from test_kity_micro_native_protection_v1 import protected_journal
from test_kity_micro_runtime_v1 import event


class PositionReader:
    result = staticmethod(BybitReadTransport.result)
    def __init__(self, symbol, size='1', idx=0, side='Buy'):
        self.position = dict(symbol=symbol, size=size, positionIdx=idx, side=side)
        self.calls = []

    def pages(self, path, params):
        self.calls.append((path, params))
        active = [] if self.position['size'] == '0' else [self.position]
        # Actual Bybit symbol-cursor sequence: live row then an empty placeholder.
        rows = active if 'settleCoin' in params else [self.position, dict(self.position, size='0', side='')]
        return dict(complete=True, pages=[dict(http_status=200, body=dict(retCode=0, result=dict(list=rows)))])

    def get(self, path, params):
        return dict(http_status=200, body=dict(retCode=0, result=dict(list=[self.position])))


def test_exit_uses_complete_nonzero_account_positions_not_symbol_cursor_placeholder(tmp_path):
    j, symbol = protected_journal(tmp_path)
    reader = PositionReader(symbol)
    lease = AccountLease(tmp_path/'account.lock')
    owner = PhysicalOwner(j, reader, lease, tmp_path/'owner', platform_check=lambda: None, post=None, clock=lambda: 2200)
    owner.validate_preflight(j.plan, dict(symbol=symbol, qty='1', reduceOnly=True), 'EXIT')
    assert reader.calls[0][1] == dict(category='linear', settleCoin='USDT', limit='200')
    lease.close()


@pytest.mark.parametrize('size,idx,side', [('2',0,'Buy'), ('1',1,'Buy'), ('1',False,'Buy'), ('1',0,'Sell')])
def test_exit_still_blocks_foreign_size_mode_and_side(tmp_path,size,idx,side):
    j, symbol = protected_journal(tmp_path); lease=AccountLease(tmp_path/'lock')
    owner=PhysicalOwner(j,PositionReader(symbol,size,idx,side),lease,tmp_path,platform_check=lambda:None,post=None)
    with pytest.raises(SourceError):
        owner.validate_preflight(j.plan,dict(symbol=symbol,qty='1',reduceOnly=True),'EXIT')
    lease.close()


@pytest.mark.parametrize('code', [110123,110125])
def test_official_terms_rejection_is_terminal_zero_fill_not_unknown(tmp_path,code):
    j=journal(tmp_path); owner=Owner(j)
    owner.post_once=lambda *args:dict(retCode=code,retMsg='You must agree to the Trading Terms',result={})
    bridge=MicroAccountBridge(j,None,owner=owner,clock=lambda:2100)
    result=bridge.dispatch_next('GO KITY_EXECUTION_MICRO_LIVE '+j.plan['plan_id'])
    assert result['status']=='DEFINITE_REJECTION'
    order=j.snapshot()['entries'][j.plan['legs'][0]['symbol']]
    assert order['terminal'] and order['terminal_quantity']=='0' and order['order_id'] is None
    assert j.snapshot()['entry_blocked']


class EmptyReader:
    result = staticmethod(BybitReadTransport.result)
    def __init__(self, rows=None): self.rows=rows or []; self.calls=[]
    def pages(self,path,params):
        self.calls.append((path,params))
        return dict(complete=True,pages=[dict(http_status=200,body=dict(retCode=0,result=dict(list=self.rows)))])


def saved_rejection(tmp_path, code=110123):
    j=journal(tmp_path); leg=j.plan['legs'][0]; symbol=leg['symbol']
    j.append(event('ENTRY_INTENT',symbol=symbol))
    j.append(event('DISPATCH_UNKNOWN',symbol=symbol,order_link_id=leg['request']['orderLinkId']))
    wire=tmp_path/'wire'; wire.mkdir(); key=digest(dict(path='/v5/order/create',request=leg['request']))
    publish(wire/('send-'+key+'.json'),dict(path='/v5/order/create',request=leg['request'],at_ms=2100,status='INTENT_WIRE_MAY_HAVE_RUN'))
    raw=json.dumps(dict(retCode=code,retMsg='You must agree to the Trading Terms',result={}))
    publish(wire/('response-'+key+'.json'),dict(http_status=200,raw=raw,raw_sha256=hashlib.sha256(raw.encode()).hexdigest(),receive_ms=2200))
    s=BoundedSupervisor.__new__(BoundedSupervisor);s.root=tmp_path;s.journal=j;s.reader=EmptyReader()
    return s,leg,key


def test_recover_exact_saved_terms_rejection_preserves_wire_and_is_idempotent(tmp_path):
    s,leg,key=saved_rejection(tmp_path)
    before={p.name:p.read_bytes() for p in (tmp_path/'wire').iterdir()}
    s.recover_saved_terms_rejections();s.recover_saved_terms_rejections()
    order=s.journal.snapshot()['entries'][leg['symbol']]
    assert order['terminal'] and order['definite_rejection']==110123
    assert len(s.reader.calls)==4
    assert before=={p.name:p.read_bytes() for p in (tmp_path/'wire').iterdir()}


def test_saved_unknown_error_stays_unknown_and_never_uses_empty_reads_as_rejection(tmp_path):
    s,leg,key=saved_rejection(tmp_path,10006)
    s.recover_saved_terms_rejections()
    assert not s.journal.snapshot()['entries'][leg['symbol']]['terminal']
    assert s.reader.calls==[]


def test_saved_terms_rejection_conflicting_broker_order_still_blocks(tmp_path):
    s,leg,key=saved_rejection(tmp_path);s.reader=EmptyReader([{'orderId':'unexpected'}])
    with pytest.raises(SourceError,match='REJECTION_READBACK_CONFLICT'):s.recover_saved_terms_rejections()
    assert not s.journal.snapshot()['entries'][leg['symbol']]['terminal']


def test_saved_terms_rejection_raw_hash_tamper_blocks(tmp_path):
    s,leg,key=saved_rejection(tmp_path);p=tmp_path/'wire'/('response-'+key+'.json')
    x=json.loads(p.read_bytes());x['raw_sha256']='0'*64;p.write_text(json.dumps(x))
    with pytest.raises(SourceError,match='REJECTION_RESPONSE_HASH'):s.recover_saved_terms_rejections()
    assert not s.journal.snapshot()['entries'][leg['symbol']]['terminal']


def test_recovery_binding_preserves_original_intent_and_cannot_create_new_journal(tmp_path):
    original=tmp_path/'original.json';old=dict(runtime_root=str(tmp_path),account_lock_inode=818853)
    original.write_text(json.dumps(old));store=tmp_path/'experiment';store.mkdir()
    (store/'active-plan.json').write_text('{"immutable":true}');(store/'lifecycle.sqlite').touch()
    pin=hashlib.sha256(original.read_bytes()).hexdigest()
    recovery=dict(mode='OWNED_RECOVERY_ONLY',original_config_path=str(original),
        original_config_sha256=pin,intent_id='a'*64,
        active_plan_sha256=hashlib.sha256((store/'active-plan.json').read_bytes()).hexdigest())
    config=dict(old,_config_sha256='b'*64,recovery_binding=recovery)
    dossier=dict(pricing_intent=dict(intent_id='a'*64))
    assert bound_config_pin(config,dossier,store)==pin
    with pytest.raises(SourceError,match='RECOVERY_ONLY_BINDING'):bound_config_pin(config,dossier,store,create=True)
    with pytest.raises(SourceError,match='RECOVERY_ORIGINAL_CUSTODY'):
        bound_config_pin(dict(config,account_lock_inode=818854),dossier,store)
    (store/'active-plan.json').write_text('{"changed":true}')
    with pytest.raises(SourceError,match='RECOVERY_ONLY_BINDING'):bound_config_pin(config,dossier,store)


def test_recovery_config_cannot_prepare_or_select_another_experiment():
    s=BoundedSupervisor.__new__(BoundedSupervisor);s.config={'recovery_binding':{}}
    with pytest.raises(SourceError,match='RECOVERY_ONLY_NO_NEW_SELECTION'):s.before_selection()
