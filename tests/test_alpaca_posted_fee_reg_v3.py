import copy,json
import pytest
from research_lab import alpaca_live_readiness_v1 as api
from research_lab.alpaca_dynamic_v1 import canonical
from tests.test_alpaca_live_readiness_v1 import posted_case,lifecycle

# Break caught: treating Alpaca's executed USD FEE/REG as an unknown SEC charge.
def test_documented_reg_closes_same_cash_chain_without_rewriting_raw(posted_case):
    assert hasattr(api,'derive_paper_posted_cost_closure_v3'), 'versioned REG classifier missing'
    paths=posted_case[-1];p=paths['terminal'];r=json.loads(p.read_bytes())
    for row in r['response']['paper_broker']['activities']['payload']:
        if row.get('description','').startswith('SEC fee '):
            row.update(activity_sub_type='REG',status='executed',currency='USD')
            row['description']=row['description'].replace('SEC fee ','REG fee ',1)
    p.write_bytes(canonical(r));before=p.read_bytes()
    fee=api.derive_paper_posted_cost_closure_v3(**{n+'_path':v for n,v in paths.items()},now_ms=1791900300000)
    assert fee['regulatory_fees_usd']=='0.03'
    assert fee['cash_after']=='99405.75'
    assert p.read_bytes()==before
    result=api.verify_paper_lifecycle(*posted_case[:3],r['response'],fee,now_ms=1791900300000)
    assert result['status']=='PAPER_EXECUTION_PASS',result
    assert result['net_usd']=='-4.535524745824'

@pytest.mark.parametrize('fault',['missing_subtype','other_subtype','conflicting_subtypes','wrong_type','unposted','wrong_currency','wrong_amount'])
def test_reg_alias_never_accepts_ambiguous_or_wrong_fee(posted_case,fault):
    paths=posted_case[-1];p=paths['terminal'];r=json.loads(p.read_bytes())
    row=next(x for x in r['response']['paper_broker']['activities']['payload'] if x.get('description','').startswith('SEC fee '))
    row.update(activity_sub_type='REG',status='executed',currency='USD');row['description']=row['description'].replace('SEC fee ','REG fee ',1)
    if fault=='missing_subtype':row.pop('activity_sub_type')
    elif fault=='other_subtype':row['activity_sub_type']='TAF'
    elif fault=='conflicting_subtypes':row['activity_subtype']='CAT'
    elif fault=='wrong_type':row['activity_type']='DIV'
    elif fault=='unposted':row['status']='pending'
    elif fault=='wrong_currency':row['currency']='EUR'
    elif fault=='wrong_amount':row['net_amount']='-0.02'
    p.write_bytes(canonical(r))
    with pytest.raises(ValueError):api.derive_paper_posted_cost_closure_v3(**{n+'_path':v for n,v in paths.items()},now_ms=1791900300000)
