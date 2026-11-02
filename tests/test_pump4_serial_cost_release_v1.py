"""Source-bound cost release is hypothetical ORDERS_OFF, never broker finality."""
import copy
import hashlib
import json
from decimal import Decimal as D

import pytest

from research_lab import pump4_serial_accounting_v1 as S
from test_pump4_serial_accounting_v1 import case, rows, sync, view
from test_pump4_account_owner_v1 import FP
from test_pump4_bybit_sources_v1 import NOW

POLICY=dict(day_loss_usdt='2',week_loss_usdt='3',drawdown_usdt='6',lifetime_loss_usdt='3')


def closed_groups(bundle,slots,*,first_funding='0'):
    result=[]
    for window in bundle['history_windows']:
        cap=copy.deepcopy(window['groups']['history']['pages'][0])
        cap['endpoint']='/v5/position/closed-pnl'
        cap['params']=dict(category='linear',startTime=str(window['start_ms']),endTime=str(window['end_ms']),limit='100')
        data=[]
        for slot in slots:
            fills=[r for r in rows(bundle,'executions') if r['orderLinkId'].startswith('serial-'+str(slot['ordinal'])+'-')]
            entry=[r for r in fills if r['side']=='Sell'];exits=[r for r in fills if r['side']=='Buy']
            for fill in exits:
                qty=D(fill['execQty']);entry_value=sum(D(x['execQty'])*D(x['execPrice']) for x in entry)
                exit_value=qty*D(fill['execPrice']);fund=D(first_funding) if slot['ordinal']==1 else D(0)
                data.append(dict(symbol=slot['symbol'],orderId=fill['orderId'],side='Buy',qty=str(qty),closedSize=str(qty),
                    cumEntryValue=str(entry_value),cumExitValue=str(exit_value),openFee='.01',closeFee=fill['execFee'],
                    closedPnl=str(entry_value-exit_value-D('.01')-D(fill['execFee'])+fund),
                    execType='Trade',createdTime=fill['execTime'],updatedTime=fill['execTime']))
        cap['body']['result'].update(category='linear',list=data,nextPageCursor='')
        cap['raw']=json.dumps(cap['body']);cap['raw_sha256']=hashlib.sha256(cap['raw'].encode()).hexdigest()
        result.append(dict(start_ms=window['start_ms'],end_ms=window['end_ms'],group=dict(complete=True,pages=[cap])))
    return result


def fix(groups):
    for w in groups:
        for c in w['group']['pages']:
            c['raw']=json.dumps(c['body']);c['raw_sha256']=hashlib.sha256(c['raw'].encode()).hexdigest()
    return groups


def release(bundle,slots,groups=None):
    assert callable(getattr(S,'with_cost_release',None)), 'Missing source-backed closed-cost release policy'
    return S.with_cost_release(view(bundle,slots),closed_groups(bundle,slots) if groups is None else groups)


def ledger(tmp_path,policy=None):
    return S.SeriesAccounting(tmp_path/'ledger',FP,policy or POLICY,cost_policy_sha256=S.COST_RELEASE_POLICY_SHA)


def test_matched_closed_rows_release_only_hypothetical_off_and_keep_finality_false(tmp_path):
    b,s=case(tmp_path);v=release(b,s)
    assert v['cost_release']['status']=='BOUNDED_UNDER_SOURCE_POLICY'
    assert D(v['pending_cost_reserve_usdt'])==D('.000002')
    assert D(v['conservative_net_usdt'])==D('.459998')
    assert v['cost_finality_proven'] is False and v['release_next_entry_allowed'] is False
    assert v['orders_allowed'] is False and v['money_authority'] is False
    l=ledger(tmp_path);l.record(v)
    assert l.can_reserve_entry('1')['allowed'] is True


def test_late_debit_is_reserved_from_closed_pnl_before_account_posting_then_charged_once(tmp_path):
    b,s=case(tmp_path);g=closed_groups(b,s,first_funding='-.05');v=release(b,s,g)
    assert D(v['pending_cost_reserve_usdt'])==D('.050002')
    assert D(v['conservative_net_usdt'])==D('.409998')
    l=ledger(tmp_path);l.record(v)
    rows(b,'transactions').append(dict(id='fund-1',symbol='ZROUSDT',type='SETTLEMENT',category='linear',currency='USDT',transactionTime=str(NOW+1150),funding='-.05'))
    after=release(sync(b),s,g);row=l.record(after)
    assert D(after['pending_cost_reserve_usdt'])==D('.000002')
    assert D(after['conservative_net_usdt'])==D('.409998')
    assert not row['entry_loss_latched']


def test_unposted_credit_is_not_spent_as_real_profit(tmp_path):
    b,s=case(tmp_path);v=release(b,s,closed_groups(b,s,first_funding='.2'))
    assert D(v['conservative_net_usdt'])==D('.459998')
    assert D(v['pending_cost_reserve_usdt'])==D('.000002')


@pytest.mark.parametrize('fault',['empty','missing_row','foreign','quantity','side','fee','value','nonfinite','clock','incomplete','wrong_query','raw_conflict'])
def test_unknown_or_mismatched_closed_cost_source_never_releases(tmp_path,fault):
    b,s=case(tmp_path);g=closed_groups(b,s);cap=g[0]['group']['pages'][0];rr=cap['body']['result']['list']
    if fault=='empty':rr.clear()
    elif fault=='missing_row':rr.pop()
    elif fault=='foreign':rr[0]['orderId']='foreign'
    elif fault=='quantity':rr[0]['closedSize']='.1'
    elif fault=='side':rr[0]['side']='Sell'
    elif fault=='fee':rr[0]['openFee']='.1'
    elif fault=='value':rr[0]['cumEntryValue']='19'
    elif fault=='nonfinite':rr[0]['closedPnl']='NaN'
    elif fault=='clock':rr[0]['updatedTime']=str(NOW+5000)
    elif fault=='incomplete':g[0]['group']['complete']=False
    elif fault=='wrong_query':cap['params']['startTime']='1'
    fix(g)
    if fault=='raw_conflict':cap['body']['result']['list'][0]['closedPnl']='999'
    v=release(b,s,g);assert v['cost_release']['status']=='UNKNOWN'
    l=ledger(tmp_path);l.record(v);assert l.can_reserve_entry('1')['allowed'] is False


def test_closed_report_negative_net_is_included_in_lifetime_latch(tmp_path):
    b,s=case(tmp_path);v=release(b,s,closed_groups(b,s,first_funding='-4'))
    l=ledger(tmp_path);row=l.record(v)
    assert 'LIFETIME' in row['loss_reasons'] and row['entry_loss_latched']
    assert l.can_reserve_entry('1')['allowed'] is False


def test_next_entry_risk_is_reserved_before_reservation(tmp_path):
    b,s=case(tmp_path);v=release(b,s)
    l=ledger(tmp_path,dict(POLICY,lifetime_loss_usdt='.5'));l.record(v)
    assert l.summary()['entry_loss_latched'] is False
    assert l.can_reserve_entry('1')['allowed'] is False
    assert l.can_reserve_entry('.9')['allowed'] is True


def test_revision_beyond_certificate_latches_through_restart_and_unknown_gap(tmp_path):
    b,s=case(tmp_path);v=release(b,s);l=ledger(tmp_path);l.record(v)
    unknown=release(b,s,closed_groups(b,s)[:0])
    with pytest.raises(ValueError):l.record(unknown)
    rows(b,'executions')[0]['execFee']='.06';sync(b)
    g=closed_groups(b,s,first_funding='-.05');g[0]['group']['pages'][0]['body']['result']['list'][0]['openFee']='.06';fix(g)
    revised=release(b,s,g);row=l.record(revised)
    assert 'COST_SOURCE_REVISION' in row['loss_reasons']
    assert ledger(tmp_path).summary()['entry_loss_latched'] is True
    assert ledger(tmp_path).can_reserve_entry('1')['allowed'] is False


def test_policy_binding_and_derived_lower_bound_cannot_be_changed_by_caller(tmp_path):
    b,s=case(tmp_path);v=release(b,s);l=ledger(tmp_path);l.record(v)
    forged=copy.deepcopy(v);forged['conservative_net_usdt']='100';forged['view_sha256']=S.digest({k:x for k,x in forged.items() if k!='view_sha256'})
    with pytest.raises(ValueError):l.record(forged)
    with pytest.raises(ValueError):S.SeriesAccounting(tmp_path/'ledger',FP,POLICY)


def test_initial_proven_unused_series_can_reserve_without_inventing_closed_pnl(tmp_path):
    b,s=case(tmp_path)
    for name in ['history','executions','transactions']:rows(b,name).clear()
    b=sync(b);v=release(b,[],closed_groups(b,[]));l=ledger(tmp_path);l.record(v)
    assert D(v['conservative_net_usdt'])==0 and D(v['pending_cost_reserve_usdt'])==0
    assert l.can_reserve_entry('1')['allowed'] is True
