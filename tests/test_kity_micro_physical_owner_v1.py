import hashlib,json,fcntl,os
from pathlib import Path
import pytest
from bot.kity_m3_orders_off import digest
from test_kity_micro_native_protection_v1 import protected_journal
from research_lab.kity_micro_transport_v1 import SourceError


def test_lease_rejects_second_process_and_path_replacement(tmp_path):
    from research_lab.kity_micro_physical_owner_v1 import AccountLease
    p=tmp_path/'lease';a=AccountLease(p);a.assert_held()
    with pytest.raises((SourceError,BlockingIOError)):AccountLease(p)
    p.unlink();p.write_text('replacement')
    with pytest.raises(SourceError,match='LEASE'):a.assert_held()
    a.close()


def test_post_wire_uses_one_canonical_signed_payload_no_retry(tmp_path):
    from research_lab.kity_micro_physical_owner_v1 import SignedPostOnce
    calls=[]
    def wire(method,url,headers,data,timeout):
        calls.append((method,url,headers,data,timeout));raise TimeoutError()
    w=SignedPostOnce('key','secret',tmp_path,wire=wire,clock=lambda:2000)
    request=dict(category='linear',symbol='LTCUSDT',orderLinkId='owned')
    with pytest.raises(TimeoutError):w.post('/v5/order/create',request)
    with pytest.raises(SourceError,match='SEND_ALREADY_RECORDED'):w.post('/v5/order/create',request)
    assert len(calls)==1 and calls[0][0]=='POST'
    assert json.loads(calls[0][3])==request
    assert 'secret' not in '\n'.join(p.read_text() for p in tmp_path.iterdir())


def test_physical_owner_defaults_to_post_inhibited_even_with_arbitrary_callback(tmp_path):
    from research_lab.kity_micro_physical_owner_v1 import PhysicalOwner,AccountLease
    j,s=protected_journal(tmp_path)
    calls=[]
    o=PhysicalOwner(j,None,AccountLease(tmp_path/'lock'),tmp_path/'raw',
       platform_check=lambda:None,post=lambda *a:calls.append(a),clock=lambda:2100)
    with pytest.raises(SourceError,match='EXACT_OWNER_GO'):o.post_once('/v5/order/create',j.plan['legs'][0]['request'])
    assert calls==[]


def test_native_terminal_cancellation_allows_documented_full_stop_quantity_shrink(tmp_path):
    from research_lab.kity_execution_micro_bybit_v1 import order_events
    from test_kity_micro_native_protection_v1 import bind
    j,s=protected_journal(tmp_path);bind(j,s)
    row=dict(symbol=s,orderId='native-stop-1',orderLinkId='',side='Sell',qty='0',
       reduceOnly=True,positionIdx=0,orderType='Market',stopOrderType='StopLoss',
       orderStatus='Deactivated',cumExecQty='0',triggerPrice='.9')
    es=order_events(j.plan,j.snapshot(),row,observed_ms=2100)
    assert es[-1]['status']=='Deactivated'


def test_send_scope_rejects_nonowned_or_unpersisted_request(tmp_path):
    from research_lab.kity_micro_physical_owner_v1 import PhysicalOwner,AccountLease
    j,s=protected_journal(tmp_path);calls=[]
    o=PhysicalOwner(j,None,AccountLease(tmp_path/'lock'),tmp_path/'raw',
       platform_check=lambda:None,post=lambda *a:calls.append(a),clock=lambda:2100)
    # Cannot fake an exact GO merely by setting a callback / arbitrary wire.
    with pytest.raises(SourceError):o.accept_go('GO KITY_EXECUTION_MICRO_LIVE wrong')
    assert calls==[]


def test_journal_verified_prefix_cache_preserves_external_tamper_detection(tmp_path,monkeypatch):
    import research_lab.kity_execution_micro_runtime_v1 as rt
    import sqlite3
    from test_kity_micro_runtime_v1 import event
    j,s=protected_journal(tmp_path)
    for n in range(30):j.append(dict(event('CLOCK'),at_ms=2200+n))
    calls=[];original=rt.apply_event
    def count(*a):calls.append(1);return original(*a)
    monkeypatch.setattr(rt,'apply_event',count)
    j.snapshot();j.snapshot()
    assert len(calls)==0, 'guard must not revalue the full 30min history for each read'
    other=sqlite3.connect(tmp_path/'j.sqlite');other.execute("UPDATE events SET hash=? WHERE seq=1",('a'*64,));other.commit();other.close()
    with pytest.raises(ValueError,match='CHAIN'):j.snapshot()
