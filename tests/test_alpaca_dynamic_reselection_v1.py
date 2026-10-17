"""Versioned event reselection remains local ORDERS_OFF; original contracts fixed."""
import copy
from pathlib import Path
import pytest
from test_alpaca_dynamic_v1 import policy,calendar,snapshot
from research_lab import alpaca_dynamic_reselection_v1 as event
from research_lab import alpaca_dynamic_v1 as base

TUESDAY=1791466201000

@pytest.fixture
def scenario(policy,calendar,snapshot,tmp_path,monkeypatch):
    snapshot=copy.deepcopy(snapshot);snapshot['observed_ms']=TUESDAY;snapshot['quotes']['NET']['received_ms']=TUESDAY
    def selector(*a,**kw):
        return {'gate_ok':True,'picks':[dict(symbol='NET',signal_close=100,stop_price=96,atr20=2,rawscore=.5)],
                'selector_source_hashes':policy['selector_source_hashes']}
    monkeypatch.setattr('scripts.alpaca_adaptive_paper.prepare_intended_report',selector)
    history={s:[] for s in policy['universe']}
    book=event.EventReselectionBook(tmp_path/'candidate.sqlite',policy)
    return book,snapshot,history,calendar,policy


def run(s,**overrides):
    b,snap,h,c,p=s
    args=dict(snapshot=snap,history=h,calendar=c,source_sha256='b'*64,source_available_ms=TUESDAY-1000,now_ms=TUESDAY)
    args.update(overrides);return b.reselect(**args)


def test_after_terminal_exit_tuesday_fresh_ranking_reserves_without_waiting_monday(scenario):
    r=run(scenario)
    assert r['status']=='RESERVED_ORDERS_OFF' and r['proposal']['symbol']=='NET'
    assert r['ranking_signal_session']=='2026-10-07'
    assert r['contract_status']=='CANDIDATE_RESEARCH_UNAPPROVED'
    assert not r['orders_allowed'] and not r['money_authority']
    assert scenario[0].intent_count()==1


@pytest.mark.parametrize('bad',['partial','future_exit','cash_unknown','ownership_unknown','wrongaccount','samewindow_exit','noexit','gap_history','future_source','outside_window'])
def test_no_reselection_from_unconfirmed_or_noncausal_event(scenario,bad):
    b,s,h,c,p=scenario;kw={}
    if bad=='partial':s['exits'][0]['orders'][0]['filled_qty']='.01'
    if bad=='future_exit':s['exits'][0]['orders'][0]['filled_ms']=TUESDAY+1000
    if bad=='cash_unknown':s['cash_finality_verified']=False
    if bad=='ownership_unknown':s['single_owner_verified']=False
    if bad=='wrongaccount':s['account_id']='other'
    if bad=='samewindow_exit':s['exits'][0]['orders'][0]['filled_ms']=TUESDAY-500
    if bad=='noexit':s['exits']=[]
    if bad=='gap_history':h.pop('XYZ')
    if bad=='future_source':kw['source_available_ms']=TUESDAY+1
    if bad=='outside_window':kw['now_ms']=TUESDAY+300001
    r=run(scenario,**kw)
    assert r['status']!='RESERVED_ORDERS_OFF' and b.intent_count()==0


def test_cooldown_and_held_names_are_removed_before_selector(scenario,monkeypatch):
    b,s,h,c,p=scenario;seen=[]
    def selector(history,**kw):
        seen.append(set(history));return {'gate_ok':False,'picks':[],'selector_source_hashes':p['selector_source_hashes']}
    monkeypatch.setattr('scripts.alpaca_adaptive_paper.prepare_intended_report',selector)
    r=run(scenario)
    assert not {'AMD','CRWD','META'}&seen[0] and 'SPY' in seen[0]
    assert r['status']=='NO_ELIGIBLE_CANDIDATE' and b.intent_count()==0


def test_restart_keeps_exact_reservation_and_base_live_kind_refuses_candidate(scenario):
    b,s,h,c,p=scenario;one=run(scenario);s['quotes']['NET']['ask']='110'
    reopened=event.EventReselectionBook(b.path,p)
    result=reopened.reselect(snapshot=s,history=h,calendar=c,source_sha256='c'*64,source_available_ms=TUESDAY,now_ms=TUESDAY+1000)
    assert result['proposal']==one['proposal'] and reopened.intent_count()==1
    with b.db() as db:assert db.execute("SELECT value FROM meta WHERE key='runtime_kind'").fetchone()[0]=='EVENT_RESELECTION_RESEARCH_ORDERS_OFF'


def test_candidate_refuses_existing_original_book_without_touching_bytes(tmp_path,policy):
    p=tmp_path/'original.sqlite';base.DynamicBook(p,policy);old=p.read_bytes()
    with pytest.raises(ValueError,match='CANDIDATE_BOOK_REQUIRED'):event.EventReselectionBook(p,policy)
    assert p.read_bytes()==old


def test_default_cli_has_no_book_or_network_side_effect(monkeypatch,capsys):
    from scripts import run_alpaca_dynamic_reselection_v1 as cli
    def forbidden(*a,**k):pytest.fail('default constructed a book')
    monkeypatch.setattr(cli,'EventReselectionBook',forbidden)
    assert cli.main([])==0 and 'NO_NETWORK_ORDERS_OFF' in capsys.readouterr().out


def test_event_candidate_cannot_bypass_parent_cash_or_position_limits(scenario):
    b,s,h,c,p=scenario;s['cash_usd']='0';s['liability_reserve_usd']='0'
    out=run(scenario)
    assert out['status']=='NO_ELIGIBLE_CANDIDATE' and b.intent_count()==0
