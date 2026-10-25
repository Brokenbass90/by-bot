"""Source/book/manager wiring, with the actual frozen selector and no network."""
import importlib
import json

import pytest
from test_alpaca_monthly_source_ops_v1 import cache,ms
from research_lab import alpaca_monthly_source_ops_v1 as ops
from test_alpaca_monthly_native_binding_v1 import setup


def api():
    return importlib.import_module('research_lab.alpaca_monthly_cycle_v1')


def test_source_and_native_manager_share_one_owned_book(cache,tmp_path):
    p,calendar,capture=cache
    bundle=ops.compile_source(p,capture,calendar,now_ms=ms('2026-10-30T20:21:00Z'))
    m=api().MonthlyManager(tmp_path/'cycle',account_id='fixture',capital='487.42',
        account_lock_path=tmp_path/'original.lock',entry_halt_path=tmp_path/'original-HALT.json')
    result=m.source(bundle,now_ms=ms('2026-10-30T20:21:00Z'))
    assert result['status']=='ORDERS_OFF_OPERATIONAL_PASS'
    assert m.book.path==m.root/'book/monthly-orders-off.sqlite'
    assert m.book.rows('selections')[0]['selection_id']==result['selection_id']
    assert m.source(bundle,now_ms=ms('2026-10-30T20:22:00Z'))['already_bound'] is True
    assert m.preview(now_ms=ms('2026-11-02T14:30:00Z'))['broker_writes']==0
    assert not (tmp_path/'original-HALT.json').exists()


def test_cycle_restart_and_single_writer_preserve_source_seal(cache,tmp_path):
    p,calendar,capture=cache;now=ms('2026-10-30T20:21:00Z')
    bundle=ops.compile_source(p,capture,calendar,now_ms=now)
    args=dict(account_id='fixture',capital='487.42',account_lock_path=tmp_path/'lock',entry_halt_path=tmp_path/'HALT')
    one=api().MonthlyManager(tmp_path/'cycle',**args);one.source(bundle,now_ms=now)
    two=api().MonthlyManager(tmp_path/'cycle',**args)
    assert one.book.rows('selections')==two.book.rows('selections')
    with one.guard():
        with pytest.raises(BlockingIOError):two.preview(now_ms=now)


def test_cycle_never_uses_foreign_book_or_changed_account_identity(tmp_path):
    args=dict(account_id='fixture',capital='487.42',account_lock_path=tmp_path/'lock',entry_halt_path=tmp_path/'HALT')
    api().MonthlyManager(tmp_path/'cycle',**args)
    with pytest.raises(ValueError,match='CYCLE_IDENTITY'):
        api().MonthlyManager(tmp_path/'cycle',**{**args,'account_id':'foreign'})
    with pytest.raises(ValueError):api().MonthlyManager(tmp_path,**args)


def test_broker_mutation_cannot_be_enabled_by_preview_cli(tmp_path):
    from scripts import run_alpaca_monthly_cycle_v1 as cli
    with pytest.raises(SystemExit):cli.main(['--spec','unused','--spec-sha256','a'*64,'--apply'])


@pytest.mark.parametrize('operation,expected_elapsed_ms',[('opening',2000),('tick',6000)])
def test_cycle_receipt_clock_includes_custody_elapsed(setup,tmp_path,monkeypatch,operation,expected_elapsed_ms):
    from test_alpaca_monthly_cycle_custody_v1 import wired
    m,n,selection,io,now=wired(setup,tmp_path)
    elapsed=[0.];custody=m._custody
    monkeypatch.setattr(api().time,'monotonic',lambda:elapsed[0])
    def delayed(native):
        custody(native)
        elapsed[0]+=2.
    monkeypatch.setattr(m,'_custody',delayed)
    if operation=='opening':
        m.opening(n,{},selection['selection_id'],quotes={},symbols=[],now_ms=now,apply=True)
        kind='OPENING'
    else:
        m.tick(n,now_ms=now,apply=True)
        kind='DISPATCH_TICK'
    receipt=next(json.loads(p.read_bytes()) for p in (m.root/'observations').glob('*.json')
        if json.loads(p.read_bytes())['operation']==kind)
    assert receipt['observed_ms']==now+expected_elapsed_ms
    assert io.sent==[]


def test_recovery_clock_includes_custody_before_native_reconciliation(setup,tmp_path,monkeypatch):
    from test_alpaca_monthly_cycle_custody_v1 import wired
    m,n,selection,io,now=wired(setup,tmp_path)
    elapsed=[0.];custody=m._custody;recover=n._recover_rotation_receipts;observed=[]
    monkeypatch.setattr(api().time,'monotonic',lambda:elapsed[0])
    def delayed(native):
        custody(native)
        elapsed[0]+=2.
    def reconcile(*,now_ms,known_only=False):
        observed.append(now_ms)
        return recover(now_ms=now_ms,known_only=known_only)
    monkeypatch.setattr(m,'_custody',delayed)
    monkeypatch.setattr(n,'_recover_rotation_receipts',reconcile)
    assert m.recover(n,now_ms=now,apply=True)==[]
    assert observed==[now+2000]
    assert io.sent==[]
