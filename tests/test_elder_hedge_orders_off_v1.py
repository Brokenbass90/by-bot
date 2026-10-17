import copy
import json
from pathlib import Path
from decimal import Decimal

import pytest

from bot.kity_m3_orders_off import digest
from research_lab import elder_hedge_orders_off_v1 as elder

H=3600000


def source():
    row=dict(ts=H,sym='BTCUSDT',side='short',zapisano=2*H,
        decision_geometry=dict(ref_close='100',e_ref='100',raw_sl='102',raw_tps=['96','90'],f1='0.55',available_ms=2*H))
    return json.dumps(row).encode()


def context(regime='BEAR_TREND'):
    return dict(signal_bar_open_ms=H,observed_ms=2*H,available_ms=2*H,
                rezhim_v1=regime,source_sha256='c'*64)


def risk():
    return dict(portfolio_risk_budget_usdt='180',sleeve_risk_budget_usdt='60',
        used_sleeve_risk_usdt='0',open_symbols=[],available_ms=2*H,valid_until_ms=9*H,source_sha256='d'*64)


def instrument():
    return dict(symbol='BTCUSDT',tickSize='.01',qtyStep='.001',minOrderQty='.001',
                minNotionalValue='5',maxOrderQty='100',source_sha256='e'*64)


def compile_(raw=None,ctx=None,budget=None,now=2*H):
    return elder.compile_intent(raw or source(),source_ref='fixture/ten_ETS2S.jsonl:1',
        context=ctx or context(),risk=budget or risk(),instrument=instrument(),now_ms=now)


def test_frozen_short_geometry_budget_and_no_transport():
    x=compile_();assert x['status']=='ELDER_HEDGE_INTENT_ORDERS_OFF'
    assert Decimal(x['limit_price'])==Decimal('100.20') and Decimal(x['stop_price'])==108
    assert Decimal(x['risk_usdt'])<=10 and len(x['targets'])==2
    assert not x['orders_allowed'] and x['mode']=='SHADOW'
    assert x['native_guard']['reduceOnly'] is True
    assert x['source_sha256']==elder.sha(source())
    assert x['opportunity']['execution_owner_id']=='UNKNOWN'
    assert not hasattr(elder,'post') and not hasattr(elder,'load_credentials')


@pytest.mark.parametrize('regime,expected',[('BULL_TREND','HEDGE_OFF_BULL'),('UNKNOWN','ELDER_HEDGE_INTENT_ORDERS_OFF'),
    ('NEUTRAL','ELDER_HEDGE_INTENT_ORDERS_OFF'),('BEAR_TREND','ELDER_HEDGE_INTENT_ORDERS_OFF')])
def test_frozen_regime_gate(regime,expected):assert compile_(ctx=context(regime))['status']==expected


def test_actual_first_row_without_geometry_blocks_never_uses_terminal_fields():
    row=dict(ts=H,sym='BTCUSDT',side='short',zapisano=2*H,zhdyot=True,vovremya=True)
    x=compile_(raw=json.dumps(row).encode());assert x['status']=='BLOCKED_SOURCE_DECISION_GEOMETRY'
    row.update(R=1.2,stop_dolya=.08,rr1=.5,rr2=1.25)
    assert compile_(raw=json.dumps(row).encode())['status']=='BLOCKED_SOURCE_DECISION_GEOMETRY'


@pytest.mark.parametrize('change',[{'side':'long'},{'zapisano':8*H},{'ts':True}])
def test_noncausal_long_or_invalid_source_rejected(change):
    row=json.loads(source());row.update(change)
    with pytest.raises(ValueError):compile_(raw=json.dumps(row).encode())


def test_risk_engine_snapshot_no_eviction_and_sleeve_cap():
    for update in ({'sleeve_risk_budget_usdt':'60.0001'},{'used_sleeve_risk_usdt':'55'},
        {'open_symbols':['BTCUSDT']},{'open_symbols':['A','B','C','D','E','F']}):
        x=compile_(budget=dict(risk(),**update));assert x['status'].startswith('BLOCKED_RISK')


def test_durable_claim_no_second_intent_after_restart(tmp_path):
    x=compile_();p=tmp_path/'hedge.sqlite';book=elder.HedgeBook(p)
    assert book.record(x);book.close();book=elder.HedgeBook(p)
    assert not book.record(x) and book.count()==1
    conflict=copy.deepcopy(x);conflict['stop_price']='109'
    with pytest.raises(ValueError,match='CONFLICT'):book.record(conflict)
    book.close()


def test_closed_bars_pending_no_fill_and_no_synthetic_last_bar_close():
    x=compile_();bars=[[H,100,101,99,100,1]]
    assert elder.shadow_entry(x,bars,now_ms=2*H)['status']=='PENDING_CLOSED_BARS'
    bars += [[H*(i+2),100,100.1,99,100,1] for i in range(6)]
    assert elder.shadow_entry(x,bars,now_ms=8*H)['status']=='NO_FILL'
    bars[1][2]=101
    filled=elder.shadow_entry(x,bars,now_ms=8*H)
    assert filled['status']=='SHADOW_FILLED' and filled['price']==100.2
    assert filled['reference_only'] and not filled['broker_fill_proven']


def test_unclosed_gap_or_reordered_h1_never_counts_as_no_fill():
    x=compile_();bars=[[H,100,101,99,100,1],[3*H,100,101,99,100,1]]
    with pytest.raises(ValueError,match='H1'):elder.shadow_entry(x,bars,now_ms=4*H)


def test_signal_decision_and_context_have_actual_availability():
    with pytest.raises(ValueError):compile_(ctx=dict(context(),available_ms=3*H))
    with pytest.raises(ValueError):compile_(now=H)
    with pytest.raises(ValueError):compile_(budget=dict(risk(),valid_until_ms=H))


def test_later_geometry_cannot_be_backdated_into_first_record():
    row=json.loads(source());row['decision_geometry']['available_ms']+=1
    with pytest.raises(ValueError,match='FIRST_RECORD'):compile_(raw=json.dumps(row).encode())


def test_control_anchor_discrepancy_is_explicit_not_silently_repaired():
    x=compile_()
    assert Decimal(x['stop_price'])==108 and Decimal(x['control_reference_stop'])==Decimal('108.216')
    assert not x['control_stop_anchor_reconciled']
    assert x['money_readiness']=='BLOCKED_CONTROL_STOP_ANCHOR_RECONCILIATION_REQUIRED'


def test_report_schema_has_no_invented_tax_or_money_fields():
    e=elder.report_event(compile_())
    assert e['type']=='NO_SEND' and e['mode']=='SHADOW' and e['evidence_id']
    assert e['tax_a']['fees']=='UNKNOWN' and not e['tax_a']['financial_event']


def test_copied_reference_function_is_identical_to_original_pinned_source():
    import ast,hashlib
    from research_lab import elder_hedge_frozen_fill_v1 as frozen
    s=Path(frozen.__file__).read_text();tree=ast.parse(s)
    n=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='ispolnenie')
    assert hashlib.sha256((ast.get_source_segment(s,n)+'\n').encode()).hexdigest()=='54a962ba22d4a9bf2490bf23874706dfefa3feacecff3b351d110c476d474946'


def test_saved_input_cli_never_overwrites_or_claims_fresh_broker_state(tmp_path):
    from scripts.elder_hedge_orders_off_v1 import main
    value=dict(raw_first_record=source().decode(),source_ref='fixture:first',context=context(),risk=risk(),
               instrument=instrument(),observed_ms=2*H)
    raw=json.dumps(value).encode();p=tmp_path/'input.json';p.write_bytes(raw);out=tmp_path/'receipt.json'
    args=['--bundle',str(p),'--bundle-sha256',elder.sha(raw),'--output',str(out)]
    assert main(args)==0
    receipt=json.loads(out.read_bytes());assert receipt['source_use']=='EXPLICIT_SAVED_INPUT_NOT_FRESH_BROKER_STATE'
    saved=out.read_bytes()
    with pytest.raises(FileExistsError):main(args)
    assert out.read_bytes()==saved


def test_shadow_book_will_not_add_tables_to_foreign_sqlite(tmp_path):
    import sqlite3
    path=tmp_path/'foreign.sqlite';db=sqlite3.connect(path);db.execute('CREATE TABLE foreign_data(value)');db.close()
    raw=path.read_bytes()
    with pytest.raises(ValueError,match='IDENTITY'):elder.HedgeBook(path)
    assert path.read_bytes()==raw
