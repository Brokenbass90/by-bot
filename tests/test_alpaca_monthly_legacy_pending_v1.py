"""Source replay separates legacy cash obligations from Monthly admission PnL."""
import copy
import hashlib
import json
import time
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path

import pytest
from research_lab import alpaca_monthly_cost_source_v1 as costs
from test_alpaca_monthly_cost_source_v1 import case,ms
from test_alpaca_monthly_legacy_cost_transition_v1 import legacy_case
from test_alpaca_monthly_pending_fees_v1 import producer_fixture
from test_alpaca_monthly_native_binding_v1 import setup,ticket
from test_alpaca_monthly_account_transport_v1 import connect_wire
from test_alpaca_monthly_standing_v1 import standing,resign
from test_alpaca_monthly_production_runner_v1 import runner


def pending_legacy(case,tmp_path,*,first=False):
    c,seal=legacy_case(case)
    c['fees']=[r for r in c['fees'] if r['id']!='legacy-reg']
    c['cash']='61.97';c['observed']=ms('2026-10-03T06:00:01Z')
    if first:
        c['fills']=c['fills'][:1];c['positions']=[];c['exits']=[];c['fees']=[]
        c['cash']='100';c['pending']='.02'
    native,paths,source=producer_fixture(c,tmp_path)
    path=tmp_path/'legacy-seal.json';path.write_text(json.dumps(seal))
    pin=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    native.liability=Decimal('.04')
    return c,native,paths,source,pin


def produce(native,paths,pin,now):
    native.pending_fee_sources=costs.produce_cost_sources(native,**paths,
        legacy_transition=pin,now_ms=now,allow_pending=True)


def test_legacy_pending_penny_stays_outside_monthly_loss(case,tmp_path):
    c,native,paths,source,pin=pending_legacy(case,tmp_path)
    produce(native,paths,pin,c['observed'])
    lower,proof=native._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])
    assert lower==Decimal('1.97')
    assert proof['unposted_account_fees_usd']=='0.01'
    assert proof['monthly_unposted_fee_upper_bound_usd']=='0'
    assert proof['legacy_unposted_fee_upper_bound_usd']=='0.01'
    native._check_standing_loss({'max_cumulative_net_loss_usd':'8'},lower,
        [dict(qty='1',avg_entry_price='20',current_price='10.04')])
    with pytest.raises(ValueError,match='LOSS_ADMISSION_STOP'):
        native._check_standing_loss({'max_cumulative_net_loss_usd':'8'},lower,
            [dict(qty='1',avg_entry_price='20',current_price='10.03')])


def test_posted_fee_on_open_monthly_position_counts_once_at_loss_boundary(case,tmp_path):
    c,native,paths,source,pin=pending_legacy(case,tmp_path)
    produce(native,paths,pin,c['observed'])
    lower,proof=native._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])
    assert native._accounting_net(pending={'buy-a':'1.98'})==Decimal('1.98')
    assert proof['posted_open_monthly_fees_usd']=='0.01' and lower==Decimal('1.97')
    with pytest.raises(ValueError,match='LOSS_ADMISSION_STOP'):
        native._check_standing_loss({'max_cumulative_net_loss_usd':'8'},lower,
            [dict(qty='2',avg_entry_price='20',current_price='15.015')])


def test_live_legacy_owner_scope_cannot_accept_owned_only_estimate(case,tmp_path):
    from test_alpaca_monthly_pending_fees_v1 import pending_inputs
    c=pending_inputs(case);native,paths,source=producer_fixture(c,tmp_path)
    native.pending_fee_sources=costs.produce_cost_sources(native,**paths,
        now_ms=c['observed'],allow_pending=True)
    native.base_url='https://api.alpaca.markets'
    native._live_custody=lambda:dict(legacy_cost_transition={'path':'absent','sha256':'f'*64},
        pending_fee_protocol_sha256=hashlib.sha256(Path(paths['protocol_path']).read_bytes()).hexdigest())
    with pytest.raises(ValueError,match='ACCOUNT_CONTEXT_REQUIRED'):
        native._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])


@pytest.mark.parametrize('fault',['none','missing','after','protocol','calendar','assets'])
def test_production_runner_requires_same_legacy_source_policy(runner,fault):
    from scripts import run_alpaca_monthly_cycle_v1 as cli
    spec,manager,client,writes,now,native,scope=runner
    pin=dict(path=str(manager.root/'terminal-seal.json'),sha256='f'*64)
    spec['costs']['legacy_transition']=pin;scope['legacy_cost_transition']=pin
    scope['legacy_pending_cost_inputs']={k:copy.deepcopy(spec['costs'][k])
        for k in ('after','protocol','calendar','assets')}
    if fault=='missing':scope.pop('legacy_pending_cost_inputs')
    elif fault=='after':scope['legacy_pending_cost_inputs']['after']='2026-09-30T00:00:00Z'
    elif fault!='none':scope['legacy_pending_cost_inputs'][fault]['sha256']='e'*64
    scope['runner_config_sha256']=cli.runner_config_sha256(spec);resign(native,scope)
    spec['authority']['scope_sha256']=native.live_scope_sha256
    if fault=='none':assert cli.runner_authority(spec)==scope
    else:
        with pytest.raises(ValueError,match='LEGACY_PENDING_SOURCE_POLICY_CONFLICT'):cli.runner_authority(spec)
    assert writes==[]


@pytest.mark.parametrize('drift',['unchanged','content','new_dependency','new_import','removed','symlink'])
def test_ast_cache_never_caches_source_hashes_or_dependency_existence(tmp_path,monkeypatch,drift):
    from research_lab import alpaca_monthly_native_binding_v1 as mod
    mod._source_imports.cache_clear()
    monkeypatch.setattr(mod,'ROOT',tmp_path)
    monkeypatch.setattr(mod.baseline,'source_pins',lambda:{'seed.py':'unused'})
    names=['seed.py','research_lab/alpaca_monthly_native_binding_v1.py',
        'research_lab/alpaca_monthly_cycle_v1.py','research_lab/alpaca_monthly_notifications_v1.py',
        'research_lab/alpaca_monthly_source_ops_v1.py','scripts/run_alpaca_monthly_cycle_v1.py',
        'scripts/fetch_equities_yfinance.py']
    for name in names:
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('import missing_dependency\n')
    before=mod.standing_source_pins();info=mod._source_imports.cache_info()
    if drift=='content':(tmp_path/'seed.py').write_text('import missing_dependency\n# changed bytes\n')
    elif drift=='new_dependency':(tmp_path/'missing_dependency.py').write_text('')
    elif drift=='new_import':
        (tmp_path/'seed.py').write_text('import another_dependency\n')
        (tmp_path/'another_dependency.py').write_text('')
    elif drift=='removed':(tmp_path/'seed.py').unlink()
    elif drift=='symlink':
        (tmp_path/'seed.py').unlink();(tmp_path/'target.py').write_text('')
        (tmp_path/'seed.py').symlink_to(tmp_path/'target.py')
    if drift in {'removed','symlink'}:
        with pytest.raises((ValueError,FileNotFoundError)):mod.standing_source_pins()
    else:
        after=mod.standing_source_pins()
        if drift=='unchanged':
            assert after==before and mod._source_imports.cache_info().misses==info.misses
        elif drift=='content':assert after['seed.py']!=before['seed.py']
        elif drift=='new_dependency':assert 'missing_dependency.py' in after and 'missing_dependency.py' not in before
        else:assert 'another_dependency.py' in after


def test_first_entry_classifies_legacy_liability_without_monthly_exits(case,tmp_path):
    c,native,paths,source,pin=pending_legacy(case,tmp_path,first=True)
    produce(native,paths,pin,c['observed'])
    assert native.pending_fee_sources=={}
    lower,proof=native._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])
    assert lower==0 and proof['unposted_account_fees_usd']=='0.02'
    assert proof['monthly_unposted_fee_upper_bound_usd']=='0'
    assert proof['legacy_unposted_fee_upper_bound_usd']=='0.02'
    assert proof['terminal_cost_finality_proven'] is False
    assert not (native.runtime/'standing-loss-stop.json').exists()


def test_zero_api_liabilities_do_not_prove_zero_missing_fees(case,tmp_path):
    c,native,paths,source,pin=pending_legacy(case,tmp_path,first=True)
    # Rebuild a raw capture whose liability fields are zero, not a patched proof.
    c['pending']='0'
    from test_alpaca_monthly_pending_fees_v1 import inputs
    source=inputs(c)['source'];Path(paths['source_path']).write_text(json.dumps(source))
    produce(native,paths,pin,c['observed'])
    lower,proof=native._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])
    assert lower==0 and proof['unposted_account_fees_usd']=='0.02'
    native.liability=Decimal('.01')
    with pytest.raises(ValueError,match='RESERVE_EXCEEDED'):
        native._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])


@pytest.mark.parametrize('fault',['none','protocol','calendar','assets','after','legacy'])
def test_live_context_requires_exact_owner_source_policy(case,tmp_path,fault):
    c,native,paths,source,pin=pending_legacy(case,tmp_path,first=True)
    produce(native,paths,pin,c['observed']);native.base_url='https://api.alpaca.markets'
    rows={k:dict(path=paths[k+'_path'],sha256=hashlib.sha256(Path(paths[k+'_path']).read_bytes()).hexdigest())
        for k in ('protocol','calendar','assets')}
    scope=dict(pending_fee_protocol_sha256=rows['protocol']['sha256'],legacy_cost_transition=pin,
        legacy_pending_cost_inputs=dict(after=source['coverage']['after'],**rows))
    if fault in rows:scope['legacy_pending_cost_inputs'][fault]=dict(rows[fault],sha256='f'*64)
    elif fault=='after':scope['legacy_pending_cost_inputs']['after']='2026-09-30T00:00:00Z'
    elif fault=='legacy':scope['legacy_cost_transition']=dict(pin,sha256='f'*64)
    call=lambda:costs.pending_admission_net(native,account=source['account_after'],now_ms=c['observed'],owner_scope=scope)
    if fault=='none':assert call()[0]==0
    else:
        with pytest.raises(ValueError,match='SCOPE|POLICY'):call()


def test_capture_first_entry_and_restart_late_fee_keep_old_evidence(case,tmp_path):
    c,native,paths,source,pin=pending_legacy(case,tmp_path,first=True)
    current=[source];calls=[]
    def get(route,query):
        calls.append(route)
        if route=='/v2/clock':body=dict(timestamp=current[0]['coverage']['until'])
        elif route=='/v2/account':body=current[0]['account_after']
        else:
            assert route=='/v2/account/activities';body=current[0]['activities']
        return dict(http_status=200,started_ms=c['observed']-100,received_ms=c['observed']-100,
            raw=json.dumps(body))
    native.client.cost_get=get
    kwargs={k:v for k,v in paths.items() if k!='source_path'}
    def capture():return costs.capture_and_produce_cost_sources(native,after=source['coverage']['after'],
        **kwargs,legacy_transition=pin,allow_pending=True,now_ms=c['observed'])
    assert capture()=={} and '/v2/account/activities' in calls
    old=Path(native.pending_account_fee_source);before=old.read_bytes();stamp=old.stat().st_mtime_ns
    native.pending_account_fee_source=None  # new manager instance has no cached context
    assert capture()=={} and Path(native.pending_account_fee_source)==old
    assert old.read_bytes()==before and old.stat().st_mtime_ns==stamp
    c['fees']=[dict(id='late-cat',activity_type='FEE',activity_sub_type='CAT',date='2026-10-01',
        created_at='2026-10-02T00:16:00Z',status='executed',currency='USD',net_amount='-.01'),
        dict(id='late-reg',activity_type='FEE',activity_sub_type='REG',date='2026-10-01',
        created_at='2026-10-02T00:17:00Z',status='executed',currency='USD',net_amount='-.01')]
    c['pending']='0';c['cash']='99.98';c['observed']+=2000
    from test_alpaca_monthly_pending_fees_v1 import inputs
    current[0]=inputs(c)['source'];assert capture()=={}
    lower,proof=native._accounting_for_admission(account=current[0]['account_after'],now_ms=c['observed'])
    assert lower==0 and Decimal(proof['unposted_account_fees_usd'])==0
    assert Path(native.pending_account_fee_source)!=old
    assert old.read_bytes()==before and old.stat().st_mtime_ns==stamp


@pytest.mark.parametrize('fault',['cash','liability','stale','reserve','foreign_fill','seal'])
def test_unknowns_cannot_be_covered_by_legacy_admission(case,tmp_path,fault):
    c,native,paths,source,pin=pending_legacy(case,tmp_path,first=True)
    if fault=='foreign_fill':
        p=Path(paths['source_path']);v=json.loads(p.read_bytes());v['activities'][0]['order_id']='unknown';p.write_text(json.dumps(v))
    if fault=='seal':Path(pin['path']).write_text('{}')
    account=copy.deepcopy(source['account_after']);now=c['observed']
    if fault=='cash':account['cash']='101'
    if fault=='liability':account['accrued_fees']='1'
    if fault=='stale':now+=5001
    if fault=='reserve':native.liability=Decimal('.01')
    with pytest.raises(ValueError):
        produce(native,paths,pin,c['observed'])
        native._accounting_for_admission(account=account,now_ms=now)


@pytest.mark.parametrize('lose_stop',[False,True])
def test_first_buy_with_legacy_pending_uses_native_wire_and_restart(setup,case,tmp_path,monkeypatch,lose_stop):
    """No Monthly exits or synthetic accounting row is needed for the first BUY."""
    from research_lab.alpaca_fee_to_live_closure_v1 import collect_account_cost_source
    from research_lab.alpaca_dynamic_v1 import canonical
    book,selection,native,io,now=setup
    client,writes,lose=connect_wire(setup,monkeypatch);scope=standing(native,now)
    native.pending_fee_admission=True;native.liability=Decimal('.04')
    now+=2000
    account=dict(id='fixture',currency='USD',cash='487.42',equity='487.42',
        non_marginable_buying_power='487.42',accrued_fees='.02',pending_reg_taf_fees='0',
        trading_blocked=False,account_blocked=False)
    io.get_account=lambda:copy.deepcopy(account)
    clock_started=time.monotonic()
    io.get_clock=lambda:dict(is_open=True,timestamp=datetime.fromtimestamp(
        (now+int((time.monotonic()-clock_started)*1000))/1000,timezone.utc).isoformat())
    _,seal=legacy_case(case)
    seal['exits'][0]['filled_at']='2026-11-02T14:30:00Z'
    seal['sealed_ms']=now-1000
    fill=dict(id='legacy-f1',activity_type='FILL',order_id='legacy-sell',symbol='NET',
        side='sell',qty='1',price='5',transaction_time='2026-11-02T14:30:00Z')
    def get(route,query):
        return dict(http_status=200,started_ms=now,received_ms=now,
            raw=json.dumps(account if route=='/v2/account' else [fill]))
    source=collect_account_cost_source(get,account_id='fixture',after='2026-11-02T00:00:00Z',
        until='2026-11-02T14:30:02Z',now_ms=now)
    paths={}
    for key,value in dict(source=source,protocol=case['protocol'],calendar=selection['calendar'],
            assets=[dict(id='NET',symbol='NET',asset_class='us_equity',exchange='NASDAQ')]).items():
        path=tmp_path/(key+'-first.json');path.write_bytes(canonical(value));paths[key+'_path']=str(path)
    path=tmp_path/'first-terminal-seal.json';path.write_bytes(canonical(seal))
    pin=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    rows={k:dict(path=paths[k+'_path'],sha256=hashlib.sha256(Path(paths[k+'_path']).read_bytes()).hexdigest())
        for k in ('protocol','calendar','assets')}
    from research_lab.alpaca_monthly_native_binding_v1 import PENDING_FEE_POLICY
    scope.update(liability_reserve_usd='0.04',pending_fee_admission=PENDING_FEE_POLICY,
        pending_fee_protocol_sha256=rows['protocol']['sha256'],legacy_cost_transition=pin,
        legacy_pending_cost_inputs=dict(after=source['coverage']['after'],**rows))
    resign(native,scope);produce(native,paths,pin,now)
    assert not book.rows('exits') and not native.pending_fee_sources
    prepared=ticket(setup);lose['stop']=lose_stop
    if lose_stop:
        with pytest.raises(TimeoutError):native.enter(prepared,now_ms=now,apply=True)
    else:assert native.enter(prepared,now_ms=now,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
    # A genuine new native instance has no cached admission source. Custody of
    # the accepted BUY/stop must recover independently of fresh-entry costs.
    restarted=type(native)(book,client=client,base_url=native.base_url,account_id=native.account,
        capital=native.capital,runtime=native.runtime,lock_path=native.lock_path,
        entry_halt_path=native.halt,liability_reserve_usd='.04',pending_fee_admission=True,
        live_scope_path=native.live_scope_path,live_scope_sha256=native.live_scope_sha256,
        owner_go_path=native.owner_go_path)
    assert restarted.pending_account_fee_source is None
    assert restarted.enter(prepared,now_ms=now+1000,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
    assert [row[1]['side'] for row in writes]==['buy','sell']
    assert len(book.rows('positions'))==1 and not book.rows('exits')
    assert not (native.runtime/'standing-loss-stop.json').exists()


@pytest.mark.parametrize('fault',['none','partial','foreign_entry','quantity','side','price'])
def test_complete_legacy_entry_and_exit_source_is_classified_before_first_monthly_buy(case,tmp_path,fault):
    c,seal=legacy_case(case)
    seal['entry']['filled_at']='2026-10-01T13:58:00Z'
    old_exit=copy.deepcopy(c['fills'][0])
    old_entry=dict(id='original-net-buy-fill',activity_type='FILL',order_id=seal['entry']['id'],
        symbol='NET',side='buy',qty='1',price='6',transaction_time=seal['entry']['filled_at'])
    if fault=='foreign_entry':old_entry['order_id']='unowned-net-buy'
    elif fault=='quantity':old_entry['qty']='2'
    elif fault=='side':old_entry['side']='sell'
    elif fault=='price':old_entry['price']='6.01'
    c.update(fills=[old_entry,old_exit],positions=[],exits=[],fees=[],cash='100',pending='.02',
        observed=ms('2026-10-03T06:00:01Z'))
    if fault=='partial':
        c['fills']=[dict(old_entry,id='net-part1',qty='.4',transaction_time='2026-10-01T13:57:00Z'),
            dict(old_entry,id='net-part2',qty='.6'),old_exit]
    native,paths,source=producer_fixture(c,tmp_path)
    kwargs=dict(source=source,protocol=c['protocol'],calendar=c['calendar'],assets=c['assets'],
        positions=[],exits=[],legacy_transition=seal,pending=True)
    if fault not in {'none','partial'}:
        with pytest.raises(ValueError):costs._account_day_context(**kwargs)
    else:
        result=costs._account_day_context(**kwargs)
        assert Decimal(result['classification']['monthly_unposted_fee_upper_bound_usd'])==0
        assert Decimal(result['classification']['legacy_unposted_fee_upper_bound_usd'])==Decimal('.02')
