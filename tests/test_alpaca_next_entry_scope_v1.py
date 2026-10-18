"""The next original-policy entry remains bounded and personally activated."""
import copy
import importlib
from pathlib import Path
import pytest
from tests.test_alpaca_dynamic_portfolio_admission_v1 import next_setup
from tests.test_alpaca_dynamic_live_runtime_v1 import setup,case
from research_lab.alpaca_dynamic_v1 import digest


def fixture(s,tmp_path):
    m,b,intake,p,binding,permit,now=next_setup(s,tmp_path,session='2026-10-19')
    scope=dict(schema='ALPACA_DYNAMIC_NEXT_SESSION_SCOPE_V1',policy_sha256=digest(p),
        static_binding_sha256=digest({k:v for k,v in binding.items() if k!='intake_sha256'}),
        symbol=intake['plan']['symbol'],session=intake['plan']['session'],ranking_sha256=intake['plan']['ranking_sha256'],
        slot_entry_order_id=intake['plan']['slot_entry_order_id'],reference_risk_distance='4',
        max_notional_usd=intake['plan']['notional_limit_usd'],max_risk_usd='3',
        attempts_allowed=1,auto_repeat=False,carry_to_other_session=False,
        owner_approval_text='Сделай так что бы альпака в понедельник вклбчилась а по китти даю добро go')
    scope['scope_sha256']=digest(scope)
    return scope,dict(status='NEXT_ENTRY_PREVIEW_ONLY',intake=intake,binding=binding),p,b,now


def test_bound_next_entry_compiles_without_minting_go(setup,tmp_path):
    scope,preview,p,b,now=fixture(setup,tmp_path);before=list(b.writes)
    result=importlib.import_module('research_lab.alpaca_next_entry_scope_v1').check_preview(scope,preview,p)
    assert result==scope['scope_sha256'] and b.writes==before


@pytest.mark.parametrize('bad',['notional','risk','ranking','symbol','slot','session','binding','repeat','text','distance'])
def test_no_scope_expansion_from_a_real_prepared_intake(setup,tmp_path,bad):
    scope,preview,p,b,now=fixture(setup,tmp_path)
    if bad=='notional':scope['max_notional_usd']='100000'
    if bad=='risk':scope['max_risk_usd']='10000'
    if bad in ['ranking','symbol','slot','session']:scope[{'ranking':'ranking_sha256','slot':'slot_entry_order_id'}.get(bad,bad)]='foreign'
    if bad=='binding':scope['static_binding_sha256']='f'*64
    if bad=='repeat':scope['auto_repeat']=True
    if bad=='text':scope['owner_approval_text']='synthetic permission'
    if bad=='distance':scope['reference_risk_distance']='5'
    scope['scope_sha256']=digest({k:v for k,v in scope.items() if k!='scope_sha256'})
    before=list(b.writes)
    with pytest.raises(ValueError):importlib.import_module('research_lab.alpaca_next_entry_scope_v1').check_preview(scope,preview,p)
    assert b.writes==before


def test_ordinary_scope_file_is_not_personal_activation(setup,tmp_path):
    scope,preview,p,b,now=fixture(setup,tmp_path)
    module=importlib.import_module('research_lab.alpaca_next_entry_scope_v1')
    with pytest.raises(ValueError):module.validate_personal_arm(scope,scope)
