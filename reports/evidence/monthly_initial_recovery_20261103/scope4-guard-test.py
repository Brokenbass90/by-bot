import copy
from test_alpaca_monthly_initial_recovery_v1 import setup,prepared
from test_alpaca_monthly_standing_v1 import resign
from research_lab.alpaca_dynamic_v1 import digest
from research_lab.alpaca_monthly_binding_v1 import entry_cid
import pytest

def test_initial_exception_remains_one_identity_under_original_four_entry_future_grant(setup,monkeypatch):
 b,s,a,io,p,t,at,saved,writes,r,scope=prepared(setup,monkeypatch,True)
 scope['max_new_entries_per_session']=4;resign(a,scope)
 assert a.enter(saved,now_ms=at,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
 assert a.enter(saved,now_ms=at+1000,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
 assert len(writes)==2 and len(b.rows('positions'))==1
 # A different selection/CID cannot borrow the exception, even when the future
 # standing grant retains four entries per normal monthly session.
 foreign={**copy.deepcopy(r),'selection_id':'f'*64}
 with b.db() as db:b._save(db,'selections',foreign['selection_id'],foreign)
 other={**copy.deepcopy(saved),'selection_id':foreign['selection_id'],'client_order_id':entry_cid(foreign,saved['symbol'])}
 other['ticket_sha256']=digest({k:v for k,v in other.items() if k!='ticket_sha256'})
 with pytest.raises(ValueError,match='MONTHLY_RECOVERY_ENTRY_SCOPE_CONFLICT'):a._entry_authority(other,at+1000)
 with pytest.raises(ValueError,match='MONTHLY_NOT_ADMITTED'):a.enter(other,now_ms=at+1000,apply=True)
 assert len(writes)==2 and len(b.rows('positions'))==1
