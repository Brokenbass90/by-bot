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


def test_extra_owned_closed_row_without_matching_fills_cannot_release(tmp_path):
    b,s=case(tmp_path)
    req=copy.deepcopy(s[0]['requests'][-1]);req['orderLinkId']='cancelled-extra-close'
    s[0]['requests'].append(req)
    order=copy.deepcopy(rows(b,'history')[1]);order.update(orderId='cancelled-extra-order',
        orderLinkId=req['orderLinkId'],orderStatus='Cancelled',cumExecQty='0')
    rows(b,'history').append(order);sync(b)
    groups=closed_groups(b,s)
    extra=copy.deepcopy(groups[0]['group']['pages'][0]['body']['result']['list'][0])
    extra.update(orderId=order['orderId'],closedPnl='-10')
    groups[0]['group']['pages'][0]['body']['result']['list'].append(extra);fix(groups)
    v=release(b,s,groups)
    assert v['cost_release']['status']=='UNKNOWN'
    l=ledger(tmp_path);l.record(v);assert not l.can_reserve_entry('1')['allowed']


def test_provisional_closed_quantities_can_converge_before_certification(tmp_path):
    b,s=case(tmp_path);s=s[:1]
    for key in ('history','executions'):
        rr=rows(b,key);rr[:]=[r for r in rr if r['orderLinkId'].startswith('serial-1-')]
    sync(b);closed=s[0]['closed_ms'];s[0]['closed_ms']=None
    full=closed_groups(b,s);partial=copy.deepcopy(full)
    row=partial[0]['group']['pages'][0]['body']['result']['list'][0]
    for key in ('closedSize','cumEntryValue','cumExitValue','openFee','closeFee','closedPnl'):
        row[key]=str(D(row[key])/2)
    fix(partial);v=release(b,s,partial);l=ledger(tmp_path);l.record(v)
    assert not l.can_reserve_entry('1')['allowed']
    s[0]['closed_ms']=closed
    qualified=release(b,s,full);assert qualified['cost_release']['status']=='BOUNDED_UNDER_SOURCE_POLICY'
    l.record(qualified)
    assert ledger(tmp_path).can_reserve_entry('1')['allowed']


def test_opposing_closing_order_arithmetic_errors_cannot_cancel(tmp_path):
    b,s=case(tmp_path);slot=s[0];slot['requests'][-1]['qty']='.1'
    oldorder=rows(b,'history')[1];oldorder.update(qty='.1',cumExecQty='.1')
    oldfill=rows(b,'executions')[1];oldfill.update(execQty='.1',execFee='.005')
    req=copy.deepcopy(slot['requests'][-1]);req['orderLinkId']='serial-1-3';slot['requests'].append(req)
    order=copy.deepcopy(oldorder);order.update(orderId='order-1-3',orderLinkId=req['orderLinkId']);rows(b,'history').append(order)
    fill=copy.deepcopy(oldfill);fill.update(orderId=order['orderId'],orderLinkId=req['orderLinkId'],execId='exec-serial-1-3',execTime=str(int(oldfill['execTime'])+10));rows(b,'executions').append(fill)
    sync(b);groups=closed_groups(b,s);rr=groups[0]['group']['pages'][0]['body']['result']['list']
    first=[r for r in rr if r['orderId'].startswith('order-1-')]
    for r in first:r.update(cumEntryValue='10',openFee='.005',closedPnl='.19')
    first[0]['cumExitValue']='8.8';first[1]['cumExitValue']='10.8';fix(groups)
    v=release(b,s,groups)
    assert v['cost_release']['status']=='UNKNOWN'
    l=ledger(tmp_path);l.record(v);assert not l.can_reserve_entry('1')['allowed']
