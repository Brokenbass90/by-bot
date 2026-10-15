from decimal import Decimal as D
import pytest
from test_kity_micro_native_protection_v1 import protected_journal
from test_kity_micro_runtime_v1 import fill,terminal,send,event


def test_funding_calendar_uses_actual_owned_holding_not_nominal_30min(tmp_path):
    from research_lab.kity_micro_supervisor_v1 import funding_calendar
    j,s=protected_journal(tmp_path)
    spec={s:dict(next_funding_ms='2500',funding_interval_minutes=1)}
    # Actual fill helper has no source timestamp; unknown is an error, not zero.
    with pytest.raises(ValueError,match='FUNDING_FILL_CLOCK'):funding_calendar(j.snapshot(),spec)


def test_restart_inhibits_new_entries_without_resetting_deadline(tmp_path):
    from research_lab.kity_micro_supervisor_v1 import recover_without_reentry
    j,s=protected_journal(tmp_path);before=j.snapshot()['deadline_ms']
    recover_without_reentry(j,2200)
    assert j.snapshot()['entry_blocked'] and j.snapshot()['deadline_ms']==before
    assert j.actions(2200)[0]['kind']=='EXIT'


def test_restart_with_spent_go_but_no_send_is_inert(tmp_path):
    from research_lab.kity_micro_supervisor_v1 import recover_without_reentry
    from research_lab.kity_execution_micro_runtime_v1 import MicroJournal,prepare_micro_plan
    from test_kity_micro_runtime_v1 import dossier
    from test_kity_micro_integration_v3 import V3
    j=MicroJournal(tmp_path/'empty.sqlite',prepare_micro_plan(dossier(),V3))
    recover_without_reentry(j,2200)
    assert j.snapshot()['entry_blocked'] and not j.snapshot()['entries']


def test_control_rejects_go_on_wrong_prepared_plan_and_unknown_commands(tmp_path):
    from research_lab.kity_micro_supervisor_v1 import validate_control
    with pytest.raises(ValueError):validate_control(dict(kind='GO',plan_id='a'*64,exact_go='wrong'))
    with pytest.raises(ValueError):validate_control(dict(kind='SEND',plan_id='a'*64))
    assert validate_control(dict(kind='PREPARE'))['kind']=='PREPARE'


def test_empty_restart_or_fresh_rejection_can_finish_without_inventing_send(tmp_path):
    from research_lab.kity_execution_micro_runtime_v1 import MicroJournal,prepare_micro_plan
    from research_lab.kity_micro_account_bridge_v1 import MicroAccountBridge
    from test_kity_micro_runtime_v1 import dossier
    from test_kity_micro_integration_v3 import V3
    from test_kity_micro_account_bridge_v1 import AccountReader,Owner
    j=MicroJournal(tmp_path/'empty.sqlite',prepare_micro_plan(dossier(),V3))
    from research_lab.kity_micro_supervisor_v1 import recover_without_reentry
    recover_without_reentry(j,2200)
    b=MicroAccountBridge(j,AccountReader(),owner=Owner(j),clock=lambda:2300)
    s=b.finalize_accounting({})
    assert s['phase']=='TERMINAL' and s['execution_verdict']=='NO_SEND_NOT_LIFECYCLE_PASS'
    assert not s['entries'] and s['first_send_ms'] is None


def test_funding_repeated_same_actual_row_is_idempotent_at_later_observation(tmp_path):
    from research_lab.kity_execution_micro_runtime_v1 import record_funding_cash
    j,s=protected_journal(tmp_path)
    row=dict(id='settle1',symbol=s,transactionTime='2100',funding='-.01',change='-.01')
    record_funding_cash(j,row,2200);record_funding_cash(j,row,2300)
    assert j.snapshot()['funding_cash_usdt']=='-0.01'
    row['funding']=row['change']='-.02'
    with pytest.raises(ValueError):record_funding_cash(j,row,2400)


def test_calendar_excludes_settlement_preceding_actual_first_fill():
    from research_lab.kity_micro_supervisor_v1 import funding_calendar
    state=dict(entries={'LTCUSDT':{'filled':'1'}},held={'LTCUSDT':'0'},fills={
        'e':dict(kind='ENTRY_FILL',symbol='LTCUSDT',quantity='1',source_execution_ms=2001),
        'x':dict(kind='EXIT_FILL',symbol='LTCUSDT',quantity='1',source_execution_ms=2500)})
    assert funding_calendar(state,{'LTCUSDT':dict(next_funding_ms='2000',funding_interval_minutes=60)})=={'LTCUSDT':[]}


def test_active_plan_with_missing_journal_never_silently_creates_empty_history(tmp_path):
    from research_lab.kity_micro_supervisor_v1 import Supervisor
    from research_lab.kity_execution_micro_runtime_v1 import prepare_micro_plan
    from test_kity_micro_runtime_v1 import dossier
    from test_kity_micro_integration_v3 import V3
    s=Supervisor.__new__(Supervisor);s.root=tmp_path
    from types import SimpleNamespace
    s.reader=None;s.lease=None;s.check=lambda:None;s.writer=SimpleNamespace(post=None)
    d=dict(instruments=[],plan=prepare_micro_plan(dossier(),V3))
    with pytest.raises(ValueError,match='RECOVERY_JOURNAL_MISSING'):s.bind(d)
    assert not (tmp_path/'lifecycle.sqlite').exists()
