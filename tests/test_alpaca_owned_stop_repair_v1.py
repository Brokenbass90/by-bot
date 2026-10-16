"""No financial I/O: exact owner-restored-stop binding and default refusal."""
import copy
import importlib
import pytest


def sample():
    entry=dict(id='705a1b5b-1d45-4ba1-97cf-9c646033d78d',symbol='NET',side='buy',type='limit',
        qty='0.325167779',filled_qty='0.325167779',filled_avg_price='311.222',status='filled',
        filled_at='2026-10-15T13:30:06.234131481Z',source=None)
    current={**entry,'filled_at':'2026-10-15T13:30:06.234131Z','source':'access_key'}
    position=dict(symbol='NET',side='long',qty='0.325167779',avg_entry_price='311.222')
    stop=dict(id='personally-restored',symbol='NET',side='sell',type='stop',status='new',time_in_force='day',
        qty='0.325167779',filled_qty='0',stop_price='277.69',replaced_by=None)
    record=dict(accepted_order_id='expired-original',accepted_stop_floor=277.69,qty=.325167779,hwm=315.505)
    return entry,current,[position],[stop],record


def test_default_owner_helper_has_no_network_or_file_access(capsys):
    m=importlib.import_module('research_lab.alpaca_owned_stop_repair_v1')
    assert m.main([])==0
    assert 'ORDERS_OFF_OWNER_EXECUTION_REQUIRED' in capsys.readouterr().out


def test_exact_adoption_is_a_pure_proposal_with_raw_identity_hashes():
    m=importlib.import_module('research_lab.alpaca_owned_stop_repair_v1');args=sample();before=copy.deepcopy(args)
    record,proof=m.propose_adoption(*args)
    assert args==before
    assert record['accepted_order_id']=='personally-restored'
    assert record['accepted_stop_floor']==277.69 and record['hwm']==315.505
    assert proof['status']=='EXECUTION_IDENTITY_MATCH'


@pytest.mark.parametrize('target,field,value',[
    (1,'filled_qty','.1'),(1,'filled_avg_price','311.223'),(1,'source','foreign'),
    (2,'symbol','META'),(2,'qty','.325167778'),(2,'avg_entry_price','311.223'),
    (3,'symbol','META'),(3,'side','buy'),(3,'type','limit'),(3,'status','partially_filled'),
    (3,'time_in_force','gtc'),(3,'qty','.325167778'),(3,'filled_qty','.000000001'),
    (3,'stop_price','277.68'),(3,'stop_price','277.70'),(3,'replaced_by','unknown'),
    (4,'accepted_stop_floor',270),
])
def test_material_change_blocks_before_any_mutation(target,field,value):
    m=importlib.import_module('research_lab.alpaca_owned_stop_repair_v1');args=list(sample())
    row=args[target][0] if target in (2,3) else args[target];row[field]=value;before=copy.deepcopy(args)
    with pytest.raises(ValueError):m.propose_adoption(*args)
    assert args==before


@pytest.mark.parametrize('index',[2,3])
def test_ambiguous_or_missing_current_position_stop_never_adopted(index):
    m=importlib.import_module('research_lab.alpaca_owned_stop_repair_v1');args=list(sample())
    args[index]=[]
    with pytest.raises(ValueError):m.propose_adoption(*args)
    args=list(sample());args[index].append(copy.deepcopy(args[index][0]))
    with pytest.raises(ValueError):m.propose_adoption(*args)


def test_missing_stop_only_permits_rearm_of_exact_expired_original():
    m=importlib.import_module('research_lab.alpaca_owned_stop_repair_v1')
    entry,current,positions,orders,record=sample();previous={**orders[0],'id':record['accepted_order_id'],'status':'expired'}
    proposal,proof=m.propose_recovery(entry,current,positions,[],record,previous)
    assert proposal==record and proposal is not record
    assert proof['status']=='EXECUTION_IDENTITY_MATCH'


@pytest.mark.parametrize('field,value',[
    ('id','foreign'),('status','new'),('status','partially_filled'),
    ('filled_qty','.000000001'),('qty','.1'),('stop_price','277.68'),
    ('symbol','META'),('type','market'),('side','buy'),
])
def test_missing_stop_never_adopts_an_unknown_or_executing_original(field,value):
    m=importlib.import_module('research_lab.alpaca_owned_stop_repair_v1')
    entry,current,positions,orders,record=sample();previous={**orders[0],'id':record['accepted_order_id'],'status':'expired'}
    previous[field]=value
    with pytest.raises(ValueError):m.propose_recovery(entry,current,positions,[],record,previous)
