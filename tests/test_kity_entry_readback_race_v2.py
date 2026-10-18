"""Measured 18Oct ordering: terminal orders precede nine execution readbacks."""
import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from research_lab.kity_batch_ws_v1 import BatchJournal
from research_lab.kity_micro_account_readbacks_v2 import AccountCycleSources, AccountReadBridge
from research_lab.kity_micro_transport_v1 import BybitReadTransport, SourceError


FIXTURE = Path(__file__).parents[1] / 'reports/evidence/kity_20261018/entry_readback_race.json'


class Reader:
    result = staticmethod(BybitReadTransport.result)

    def __init__(self, data, *, fault=None):
        self.data, self.fault, self.calls = copy.deepcopy(data), fault, []
        self.late = False

    def get(self, path, params):
        return self.pages(path, params)['pages'][0]

    def pages(self, path, params):
        self.calls.append((path, dict(params)))
        rows = []
        if path == '/v5/position/list':
            rows = copy.deepcopy(self.data['positions'])
            if self.fault == 'foreign_quantity':
                rows[0]['size'] = str(Decimal(rows[0]['size']) + 1)
        elif path == '/v5/order/history':
            rows = self.data['late_history'] + self.data['native_orders']
        elif path == '/v5/order/realtime':
            rows = copy.deepcopy(self.data['native_orders'])
            if self.fault == 'foreign_order':
                rows.append(dict(rows[0], orderId='foreign-order', orderLinkId='foreign'))
        elif path == '/v5/execution/list' and self.late and self.fault != 'missing_executions':
            rows = copy.deepcopy(self.data['late_executions'])
            if self.fault == 'wrong_execution_identity':
                for row in rows:
                    row['orderId'], row['orderLinkId'] = 'foreign', 'foreign'
        cap = dict(method='GET', endpoint=path, params=dict(params), http_status=200,
                   body=dict(retCode=0, result=dict(category='linear', list=rows)))
        return dict(complete=not (self.late and self.fault == 'incomplete'), pages=[cap])


class Owner:
    def __init__(self, plan):
        self.plan = plan

    def assert_exclusive(self, plan):
        assert plan == self.plan

    def post_once(self, *args):
        pytest.fail('Readback reconciliation must never send a broker mutation')


def setup_trace(tmp_path, fault=None):
    data = json.loads(FIXTURE.read_text())
    journal = BatchJournal(tmp_path / 'race.sqlite', data['plan'])
    for event in data['before_snapshot_events']:
        journal.append(event)
    reader = Reader(data, fault=fault)
    stale_view = AccountCycleSources(reader, journal.snapshot())
    reader.late = True  # Only a NEW physical read can now see the late executions.
    bridge = AccountReadBridge(journal, stale_view, owner=Owner(data['plan']),
                               clock=lambda: data['clock_ms'])
    return data, journal, reader, bridge


def test_measured_entry_race_catches_up_exact_executions_before_position_custody(tmp_path):
    data, journal, reader, bridge = setup_trace(tmp_path)
    before = journal.snapshot()
    assert sum(Decimal(q) > 0 for q in before['held'].values()) == 1
    assert all(o['terminal'] for o in before['entries'].values())
    state = bridge.reconcile_positions()
    assert not state['entry_blocked'] and not state['ownership_conflict']
    assert all(o['filled'] == o['terminal_quantity'] == o['protected']
               for o in state['entries'].values())
    assert len(state['fills']) == len(data['late_executions'])
    # One initial account execution capture, then exactly one fresh barrier;
    # neither an unbounded poll nor a per-order resend/retry.
    reads = [(path, p) for path, p in reader.calls if path == '/v5/execution/list']
    assert len(reads) == 2 and all('symbol' not in p for _, p in reads)
    journal.close()
    recovered = BatchJournal(tmp_path / 'race.sqlite', data['plan'])
    assert not recovered.snapshot()['entry_blocked']
    assert len(recovered.snapshot()['fills']) == len(data['late_executions'])
    recovered.close()


@pytest.mark.parametrize('fault', ['missing_executions', 'foreign_quantity', 'foreign_order',
                                  'wrong_execution_identity', 'incomplete'])
def test_fresh_barrier_does_not_adopt_unknown_positions_orders_or_executions(tmp_path, fault):
    _, journal, reader, bridge = setup_trace(tmp_path, fault)
    try:
        state = bridge.reconcile_positions()
    except SourceError:
        # Supervisor converts a source failure into its existing owned unwind.
        assert fault == 'incomplete'
        assert journal.snapshot()['entry_blocked']
    else:
        assert state['entry_blocked'] and state['ownership_conflict']
        if fault in ('missing_executions', 'wrong_execution_identity'):
            assert sum(Decimal(q) > 0 for q in state['held'].values()) == 1
    assert len([p for path, p in reader.calls if path == '/v5/execution/list']) <= 2
    journal.close()


def test_catchup_cannot_extend_the_original_hold_deadline(tmp_path):
    _, journal, reader, bridge = setup_trace(tmp_path)
    bridge.clock = lambda: journal.snapshot()['deadline_ms'] + 1
    state = bridge.reconcile_positions()
    assert state['entry_blocked'] and state['phase'] == 'UNWINDING'
    assert len([p for path, p in reader.calls if path == '/v5/execution/list']) == 1
    journal.close()


def test_existing_entry_block_is_never_cleared_by_catchup(tmp_path):
    _, journal, reader, bridge = setup_trace(tmp_path)
    from bot.kity_m3_orders_off import digest
    journal.append(dict(kind='UNWIND', reason='EXISTING_OWNER_KILL', at_ms=bridge.clock(),
                        source_sha256=digest('owner-kill'), event_id='existing-unwind'))
    state = bridge.reconcile_positions()
    assert state['entry_blocked']
    assert len([p for path, p in reader.calls if path == '/v5/execution/list']) == 1
    journal.close()


@pytest.mark.parametrize('fault', ['missing_executions', 'incomplete'])
def test_supervisor_preserves_owned_fallback_when_complete_barrier_cannot_prove_exposure(tmp_path, monkeypatch, fault):
    from types import SimpleNamespace
    from research_lab import kity_micro_supervisor_v1 as supervisor
    data, journal, reader, bridge = setup_trace(tmp_path, fault)
    deadline = journal.snapshot()['deadline_ms']
    # Exercise the production supervisor's error/fallback boundary without any
    # controller constructor, credential loader or dispatch-capable object.
    s = supervisor.Supervisor.__new__(supervisor.Supervisor)
    s.journal, s.reader, s.owner = journal, reader, Owner(journal.plan)
    s.owner._authorized = False
    dispatched = []
    def inspect_action(*args, **kwargs):
        dispatched.append(journal.actions(data['clock_ms']))
        return dict(status='ORDERS_OFF_INSPECTED')
    s.bridge = SimpleNamespace(reader=reader, reconcile_orders=lambda: None,
        bind_native_protection=lambda: None, reconcile_positions=bridge.reconcile_positions,
        dispatch_next=inspect_action)
    s.funding_and_risk = lambda: None
    monkeypatch.setattr(supervisor, 'WarmReader', lambda raw, state: raw)
    monkeypatch.setattr(supervisor, 'now_ms', lambda: data['clock_ms'])
    errors = s.cycle()
    state = journal.snapshot()
    assert state['entry_blocked']
    assert state['deadline_ms'] == deadline
    assert dispatched
    assert all(a['kind'] != 'ENTRY' for a in dispatched[0])
    if fault == 'incomplete':
        assert errors == ['POSITION_READBACK:SourceError']
        assert state['phase'] == 'UNWINDING'
        assert any(a['kind'] == 'EXIT' for a in dispatched[0])
    else:
        # Complete rows which still conflict with the owned execution journal
        # cannot license a position-based invented fill or a blind exit.
        assert state['ownership_conflict']
        assert [a['kind'] for a in dispatched[0]] == ['OWNERSHIP_CONFLICT']
    assert len([p for path, p in reader.calls if path == '/v5/execution/list']) == 2
    journal.close()
