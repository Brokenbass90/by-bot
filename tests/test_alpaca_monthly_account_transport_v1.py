"""Actual restricted transport and native serializer; all HTTP is in memory."""
import copy
import json
import hashlib
from pathlib import Path
from urllib.parse import urlsplit,parse_qs

import pytest

from research_lab.alpaca_dynamic_live_runtime_v1 import DynamicLiveClient, LIVE
from research_lab.alpaca_monthly_binding_v1 import CONTRACT
from research_lab.alpaca_dynamic_v1 import digest,canonical
from test_alpaca_monthly_native_binding_v1 import setup, ticket
from scripts.equities_alpaca_paper_bridge import AlpacaAPIError


def test_existing_transport_can_explicitly_select_monthly_wire_without_relaxing_default():
    client = DynamicLiveClient('fixture', 'fixture', writes_enabled=True,
                               order_contract=CONTRACT['schema'])
    sent = []
    client._http = lambda url, method, payload=None: sent.append((method, url, payload)) or payload
    payload = dict(symbol='NET', notional='100.000000000', side='buy', type='market',
                   time_in_force='day', client_order_id='abm-'+'a'*32)
    with pytest.raises(ValueError):
        client.submit_market_buy('NET', 100., client_order_id=payload['client_order_id'], notional_precision=9)
    client.permit_write('POST', '/v2/orders', payload)
    client.submit_market_buy('NET', 100., client_order_id=payload['client_order_id'], notional_precision=9)
    assert sent == [('POST', LIVE+'/v2/orders', payload)]
    with pytest.raises(ValueError):
        client.submit_market_buy('NET', 100., client_order_id=payload['client_order_id'], notional_precision=9)
    legacy = DynamicLiveClient('fixture', 'fixture', writes_enabled=True)
    legacy._http = lambda *args: pytest.fail('Monthly must not widen legacy Dynamic')
    legacy.permit_write('POST', '/v2/orders', payload)
    with pytest.raises(ValueError, match='LIVE_QUANTITY_OWNED_ROUTE_REQUIRED'):
        legacy._request('POST', '/v2/orders', payload)


@pytest.mark.parametrize('kind', ['foreign_position', 'foreign_order', 'blocked', 'low_cash',
                                  'wrong_account', 'closed', 'stale_clock', 'gross', 'stale_quote'])
def test_new_monthly_buy_requires_fresh_full_account_admission(setup, kind):
    book, selection, adapter, io, now = setup
    prepared = ticket(setup)
    account = dict(id='fixture', cash='487.42', non_marginable_buying_power='487.42',
                   equity='487.42', trading_blocked=False, account_blocked=False)
    clock = dict(is_open=True, timestamp='2026-11-02T14:30:00Z')
    io.get_account = lambda: copy.deepcopy(account)
    io.get_clock = lambda: copy.deepcopy(clock)
    io.get_asset = lambda symbol: dict(symbol=symbol, status='active', tradable=True, fractionable=True)
    io.latest_quote = lambda symbol: dict(ap='311', t='2026-11-02T14:30:00Z')
    if kind == 'foreign_position':
        io.positions = [dict(symbol='OLD_NET', side='long', qty='1', avg_entry_price='10', market_value='10')]
    if kind == 'foreign_order':
        io.orders['foreign'] = dict(id='foreign', symbol='OLD_NET', status='new')
    if kind == 'blocked': account['trading_blocked'] = True
    if kind == 'low_cash': account['non_marginable_buying_power'] = '1'
    if kind == 'wrong_account': account['id'] = 'other'
    if kind == 'closed': clock['is_open'] = False
    if kind == 'stale_clock': clock['timestamp'] = '2026-11-02T14:29:00Z'
    if kind == 'gross': account['equity'] = '100'
    if kind == 'stale_quote': io.latest_quote = lambda symbol: dict(ap='311', t='2026-11-02T14:00:00Z')
    with pytest.raises(ValueError):
        adapter.enter(prepared, now_ms=now, apply=True)
    assert io.sent == [] and not adapter.reentry.exists() and not book.rows('positions')


def connect_wire(setup,monkeypatch):
    """Replace only HTTP: actual native methods, serializer and permit guard run."""
    book, selection, adapter, io, now = setup
    client=DynamicLiveClient('fixture','fixture',writes_enabled=True,order_contract=CONTRACT['schema'])
    writes=[];lose={'stop':False}
    def http(url,method,payload=None):
        parsed=urlsplit(url);route=parsed.path
        if method=='GET':
            if route=='/v2/account':return io.get_account()
            if route=='/v2/clock':return io.get_clock()
            if route=='/v2/positions':return io.list_positions()
            if route.startswith('/v2/assets/'):return io.get_asset(route.rsplit('/',1)[1])
            if route.endswith('/quotes/latest'):return {'quote':io.latest_quote('NET')}
            if route=='/v2/orders':return io.list_orders(**{k:v[0] for k,v in parse_qs(parsed.query).items()})
            if route=='/v2/orders:by_client_order_id':
                found=io.get_order_by_client_id(parse_qs(parsed.query)['client_order_id'][0])
                if found is None:raise AlpacaAPIError(404,'fixture absent')
                return found
            return io.get_order(route.rsplit('/',1)[1])
        writes.append((method,copy.deepcopy(payload)))
        if method=='PATCH':
            previous=io.orders[route.rsplit('/',1)[1]];previous['status']='replaced'
            new={**previous,**payload,'id':'replacement','replaces':previous['id'],'status':'new'}
            io.orders[new['id']]=new;return copy.deepcopy(new)
        if method=='DELETE':
            io.orders[route.rsplit('/',1)[1]]['status']='canceled';return {}
        assert method=='POST' and route=='/v2/orders'
        journal=json.loads(adapter.reentry.read_text())['entry_intents']
        if payload['side']=='buy':
            assert journal[payload['client_order_id']]['status']=='reserved'
            out=io.submit_market_buy(payload['symbol'],float(payload['notional']),
                client_order_id=payload['client_order_id'],notional_precision=9)
            io.positions[0].update(current_price='311.222',market_value='93.3666')
            return out
        assert next(iter(journal.values()))['baseline_stop_dispatch_started'] is True
        out=io.submit_stop_sell(payload['symbol'],qty=float(payload['qty']),stop_price=float(payload['stop_price']),
            time_in_force=payload['time_in_force'],client_order_id=payload['client_order_id'])
        io.orders[out['id']]['submitted_at']=io.get_clock()['timestamp']
        if lose['stop']:
            lose['stop']=False;raise TimeoutError('fixture accepted stop; response lost')
        return out
    client._http=http;adapter.client=client;adapter.base_url=LIVE
    # Test-only files exercise both existing native LIVE acknowledgement and
    # the distinct Monthly owner/source/lock grant. No gate is monkeypatched.
    from research_lab import alpaca_monthly_native_binding_v1 as mod
    from research_lab.alpaca_monthly_binding_v1 import strategy_identity
    from research_lab import alpaca_dynamic_live_runtime_v1 as lifecycle
    adapter.lock_path.touch()
    st=adapter.lock_path.stat()
    scope=dict(schema='ALPACA_MONTHLY_OWNER_SCOPE_V1',endpoint=LIVE,account_id='fixture',
        contract_sha256=digest(CONTRACT),strategy_identity=strategy_identity(),capital_usd='487.42',
        liability_reserve_usd='0',book=str(book.path),runtime=str(adapter.runtime),
        lock_path=str(adapter.lock_path),entry_halt_path=str(adapter.halt),legacy_NET_adoption=False,
        legacy_entry_authority=False,original_lock_identity=[st.st_dev,st.st_ino],
        max_new_entries_per_session=1,max_entry_notional_usd='204.7164',symbol='NET',
        selection_id=selection['selection_id'],source_files=[
            dict(path=str(Path(m.__file__).resolve()),sha256=hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest())
            for m in (mod,lifecycle,mod.native)])
    root=book.path.parent;scope_path=root/'monthly-scope.json';scope_path.write_bytes(canonical(scope))
    adapter.live_scope_path=scope_path;adapter.live_scope_sha256=hashlib.sha256(scope_path.read_bytes()).hexdigest()
    go=root/'monthly-owner-go.json';go.write_bytes(canonical(dict(schema='ALPACA_MONTHLY_EXACT_OWNER_GO_V1',
        scope_sha256=adapter.live_scope_sha256,owner_go_text='GO ALPACA_MONTHLY '+adapter.live_scope_sha256)))
    adapter.owner_go_path=str(go)
    live=root/'legacy-native-binding.json';live.write_bytes(canonical(dict(schema_version=1,endpoint=LIVE,
        strategy_id=mod.native._INTENDED_PAPER_STRATEGY_ID,account_id='fixture',enabled=True,
        capital_usd=487.42,max_positions=4,gross_exposure=.70,maximum_weight=.60)))
    for key,value in dict(ALPACA_INTENDED_PAPER='0',ALPACA_INTENDED_LIVE='1',
        ALPACA_INTENDED_LIVE_BINDING_PATH=str(live),ALPACA_INTENDED_LIVE_ACK='INTENDED_LIVE_CANARY',
        ALPACA_LIVE_ACCOUNT_ROLE='monthly_v38',ALPACA_LIVE_CONFIRM='MONTHLY_V38_LIVE',
        ALPACA_LIVE_MAX_CAPITAL_USD='487.42').items():monkeypatch.setenv(key,value)
    return client,writes,lose


def test_native_monthly_roundtrip_through_real_restricted_transport_and_restart(setup,monkeypatch):
    book,selection,adapter,io,now=setup
    client,writes,lose=connect_wire(setup,monkeypatch);lose['stop']=True
    prepared=ticket(setup)
    with pytest.raises(TimeoutError):adapter.enter(prepared,now_ms=now,apply=True)
    assert len(writes)==2
    assert adapter.enter(prepared,now_ms=now+1000,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
    assert len(writes)==2
    io.orders['stop'].update(status='filled',filled_qty='.3',filled_avg_price='277',filled_at='2026-11-02T14:30:59Z')
    io.positions=[];io.get_clock=lambda:dict(is_open=True,timestamp='2026-11-02T14:31:00Z')
    assert adapter.maintain(now_ms=now+60000,apply=True)['status']=='MONTHLY_EXIT_PENDING_ACCOUNTING'
    assert not book.rows('positions') and len(writes)==2
    assert book.rows('exits')[0]['reason']=='protective_stop_intraday'


def test_initial_floor_daily_ratchet_and_day_rearm_use_actual_permitted_wire(setup,monkeypatch):
    book,selection,adapter,io,now=setup
    client,writes,lose=connect_wire(setup,monkeypatch)
    adapter.enter(ticket(setup),now_ms=now,apply=True)
    from test_alpaca_monthly_native_binding_v1 import ms
    end=ms('2026-11-02T21:00:00')
    raw=[dict(symbol='NET',session='2026-11-02',open=311.222,high=380.,low=300.,close=325.)]
    book.observe_close(dict(schema='ALPACA_COMPLETED_SESSION_SOURCE_V1',source='RECORDED_REGULAR_SESSION_OHLC',
        raw=raw,raw_sha256=digest(raw),
        calendar=selection['calendar'],available_ms=end,completed_ms=end),now_ms=end)
    io.orders['stop']['status']='expired';io.positions[0]['current_price']='326'
    io.get_clock=lambda:dict(is_open=True,timestamp='2026-11-03T14:30:00Z')
    assert adapter.maintain(now_ms=ms('2026-11-03T14:30:00'),apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
    assert [w[1]['stop_price'] for w in writes if w[1]['type']=='stop']==['277.67','313.62']
    assert book.rows('positions')[0]['daily_state']['hwm']==325.


def test_legacy_live_approval_cannot_activate_monthly(setup,monkeypatch):
    book,selection,adapter,io,now=setup
    adapter.base_url=LIVE
    monkeypatch.setattr(adapter.__class__,'_admit_new_entry',lambda *a:pytest.fail('owner scope first'))
    with pytest.raises(ValueError,match='MONTHLY_SEPARATE_OWNER_SCOPE_REQUIRED'):
        adapter.enter(ticket(setup),now_ms=now,apply=True)
    assert io.sent==[]


def test_flat_exit_does_not_release_capital_until_existing_accounting_finality(setup,tmp_path,monkeypatch):
    book,selection,adapter,io,now=setup
    client,writes,lose=connect_wire(setup,monkeypatch)
    adapter.enter(ticket(setup),now_ms=now,apply=True)
    io.orders['stop'].update(status='filled',filled_qty='.3',filled_avg_price='277',filled_at='2026-11-02T14:30:59Z')
    io.positions=[];io.get_clock=lambda:dict(is_open=True,timestamp='2026-11-02T14:31:00Z')
    adapter.maintain(now_ms=now+60000,apply=True)
    next_ticket=dict(symbol='NEW',notional=100.,selection_id=selection['selection_id'])
    with pytest.raises(ValueError,match='MONTHLY_ACCOUNTING_PENDING'):
        adapter._admit_new_entry(next_ticket,now+60000)
    source_file=tmp_path/'broker-activity.json';source_file.write_text('{"fixture":"broker activity"}')
    files=[dict(path=str(source_file),sha256=hashlib.sha256(source_file.read_bytes()).hexdigest())]
    orders=[io.orders['stop']];identity=digest(dict(schema=CONTRACT['schema'],entry_id='entry'))
    source=dict(schema='ALPACA_DYNAMIC_BROKER_COST_FINALITY_V1',account_id='fixture',intake_sha256=identity,
        closure_status='ACCOUNT_DAY_FEES_RECONCILED',exit_orders_sha256=digest(orders),gross_before_fees='-10.2666',
        observed_ms=now+60000,source_files=files,source_manifest_sha256=digest(files),coverage_end_ms=now+60000,
        commission_usd='0',regulatory_fees_usd='0',unresolved_liability_usd='0',
        cash_before_entry='487.42',cash_after_exit='477.15',other_cash_net_usd='0')
    path=tmp_path/'finality.json';path.write_bytes(canonical(source))
    io.get_account=lambda:dict(id='fixture',cash='477.15',non_marginable_buying_power='477.15',
        equity='477.15',trading_blocked=False,account_blocked=False)
    out=adapter.finalize_exit('entry',path,now_ms=now+60000)
    assert out['status']=='LIVE_TERMINAL_COST_FINALITY' and out['new_entry_authority'] is False
    assert adapter.finalize_exit('entry',path,now_ms=now+60000)==out
    assert adapter._require_exit_accounting() is None
    with pytest.raises(ValueError,match='MONTHLY_APPROVED_SELECTION_REQUIRED'):
        adapter._admit_new_entry(next_ticket,now+60000)
    source_file.write_text('changed')
    with pytest.raises(ValueError,match='MONTHLY_ACCOUNTING_SOURCE_CHANGED'):
        adapter._require_exit_accounting()
    assert len(writes)==2


@pytest.mark.parametrize('payload', [
    dict(symbol='NET',qty='1',side='buy',type='market',time_in_force='day',client_order_id='abm-'+'a'*32),
    dict(symbol='NET',notional='100.00',side='buy',type='market',time_in_force='day',client_order_id='abm-'+'a'*32),
    dict(symbol='NET',notional='0.000000000',side='buy',type='market',time_in_force='day',client_order_id='abm-'+'a'*32),
    dict(symbol='NET',qty='1',side='sell',type='market',time_in_force='day',client_order_id='foreign'),
    dict(symbol='NET',qty='1',side='sell',type='stop',stop_price='NaN',time_in_force='day',client_order_id='abf-'+'a'*32),
])
def test_monthly_contract_rejects_noncanonical_payload_even_with_exact_permit(payload):
    client=DynamicLiveClient('fixture','fixture',writes_enabled=True,order_contract=CONTRACT['schema'])
    client._http=lambda *a:pytest.fail('invalid payload reached HTTP')
    client.permit_write('POST','/v2/orders',payload)
    with pytest.raises(ValueError):client._request('POST','/v2/orders',payload)
    assert client.write_permit is None


def test_closed_final_dispatch_clock_cannot_send_after_admission(setup):
    book,selection,adapter,io,now=setup;prepared=ticket(setup)
    readings=iter([dict(is_open=True,timestamp='2026-11-02T14:30:00Z'),
                   dict(is_open=False,timestamp='2026-11-02T14:30:00Z')])
    io.get_clock=lambda:next(readings)
    with pytest.raises(ValueError,match='MONTHLY_FINAL_DISPATCH'):
        adapter.enter(prepared,now_ms=now,apply=True)
    assert io.sent==[] and not adapter.reentry.exists()


def test_original_account_lock_prevents_second_writer_before_account_io(setup):
    from research_lab.alpaca_dynamic_live_runtime_v1 import account_lock
    book,selection,adapter,io,now=setup;prepared=ticket(setup)
    io.get_account=lambda:pytest.fail('account IO before original lock')
    with account_lock(dict(lock_path=str(adapter.lock_path))):
        with pytest.raises(BlockingIOError):adapter.enter(prepared,now_ms=now,apply=True)
    assert io.sent==[]


@pytest.mark.parametrize('change',['go','lock','scope','source','endpoint','selection'])
def test_monthly_live_custody_scope_cannot_be_reused_or_changed(setup,monkeypatch,change):
    book,selection,adapter,io,now=setup
    client,writes,lose=connect_wire(setup,monkeypatch);prepared=ticket(setup)
    if change=='go':Path(adapter.owner_go_path).write_text('{}')
    if change=='lock':
        adapter.lock_path.rename(adapter.lock_path.with_suffix('.old'));adapter.lock_path.touch()
    if change=='scope':adapter.live_scope_path.write_text('{}')
    if change=='source':
        scope=json.loads(adapter.live_scope_path.read_text());scope['source_files'][0]['sha256']='f'*64
        adapter.live_scope_path.write_bytes(canonical(scope))
        adapter.live_scope_sha256=hashlib.sha256(adapter.live_scope_path.read_bytes()).hexdigest()
    if change=='endpoint':adapter.base_url='https://paper-api.alpaca.markets'
    if change=='selection':
        prepared['selection_id']='b'*64
        prepared['ticket_sha256']=digest({k:v for k,v in prepared.items() if k!='ticket_sha256'})
    with pytest.raises(ValueError):adapter.enter(prepared,now_ms=now,apply=True)
    assert writes==[] and not adapter.reentry.exists()
