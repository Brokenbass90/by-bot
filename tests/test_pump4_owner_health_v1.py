import copy
import pytest
from scripts.pump4_owner_health_v1 import assess

def good():return dict(unit=dict(ActiveState='active',MainPID='123'),old_inhibited=True,lock_held=True,go_present=False,scope_digest='scope',config_sha256='config',receipt=dict(schema='PUMP4_EXECUTION_SUPERVISOR_RECEIPT_V1',mode='ORDERS_OFF',broker_writes=0,pid=123,scope_sha256='scope',runner_config_sha256='config',observed_ms=1000,result=dict(status='NO_NEW_SIGNAL')))
def test_off_is_observed_without_claiming_trading_or_protection():
 r=assess(good(),1001);assert r['status']=='HEALTHY' and r['orders_allowed'] is r['restart_allowed'] is r['financial_trading_proven'] is False
@pytest.mark.parametrize('field,value',[('old_inhibited',False),('lock_held',False),('go_present',True)])
def test_physical_conflict_fails(field,value):
 v=good();v[field]=value;assert assess(v,1001)['status']=='UNHEALTHY'
@pytest.mark.parametrize('field,value',[('pid',456),('observed_ms',1002),('observed_ms',0),('mode','OWNER_TINY_LIVE'),('broker_writes',1),('scope_sha256','wrong'),('runner_config_sha256','wrong'),('result',dict(status='BLOCKED_OBSERVATION'))])
def test_bad_or_stale_receipt_fails(field,value):
 v=good();v['receipt'][field]=value;assert assess(v,100000 if field=='observed_ms' and value==0 else 1001)['status']=='UNHEALTHY'
