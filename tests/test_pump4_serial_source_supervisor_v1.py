"""Physical selection is simulated; original AccountLease and V1 owner are real."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from research_lab.alpaca_dynamic_v1 import digest
from research_lab.kity_micro_physical_owner_v1 import AccountLease
from test_pump4_execution_supervisor_v1 import setup, provider
from test_pump4_supervisor_v1 import fixture_candidate
from test_pump4_account_owner_v1 import inputs


def module():
    from research_lab import pump4_serial_source_supervisor_v1
    return pump4_serial_source_supervisor_v1


def configured(tmp_path, monkeypatch):
    runner, state, path, pin, config, scope, called = setup(tmp_path, monkeypatch)
    spec = dict(schema='PUMP4_SERIAL_SOURCE_OFF_SPEC_V1', mode='ORDERS_OFF',
        history_start_ms=scope['valid_from_ms'], valid_until_ms=scope['valid_until_ms'],
        max_entries=10, lifetime_loss_usdt='3')
    config['serial_orders_off'] = spec
    config['serial_source_files'] = module().source_pins()
    scope['runner_config_sha256'] = runner.config_sha(config)
    target = Path(config['authority']['path'])
    target.write_text(json.dumps(scope))
    config['authority']['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
    path.write_text(json.dumps(config))
    return state, path, hashlib.sha256(path.read_bytes()).hexdigest(), config, scope, called


def sources(state, candidate, *, root_failure=False):
    Base = provider(state, candidate)
    class Sources(Base):
        def _capture(self, symbol, begin, *, custody):
            if root_failure:
                raise TimeoutError('root history unavailable')
            assert symbol is None and custody is True and begin == state[0].scope['valid_from_ms']
            return inputs(state[1], now=state[2][0])
    return Sources


def test_cli_default_has_no_selection_or_file_access(tmp_path, capsys):
    from scripts.run_pump4_serial_source_off_v1 import main
    assert main(['--config', str(tmp_path/'absent')]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'ORDERS_OFF_NO_REQUESTS'
    assert not list(tmp_path.iterdir())


def test_selected_original_lease_source_ledger_and_one_reserved_child(tmp_path, monkeypatch):
    state, path, pin, config, scope, called = configured(tmp_path, monkeypatch)
    out = module().run(path, pin, orders_off=True, once=True,
        source_factory=sources(state, fixture_candidate(tmp_path)), clock=lambda: state[2][0])
    assert out[0]['result']['status'] == 'ACTION_RESERVED_ORDERS_OFF'
    assert out[0]['source_accounting']['source_observations'] == 1
    assert state[1].state['calls'] == 0 and out[0]['broker_writes'] == 0
    root = Path(scope['root'])/'serial-source'
    assert len(list((root/'slots').glob('*/admitted-lifecycle.json'))) == 1
    AccountLease(state[-1].path).close()
    assert called[0] == 'physical' and called.count('credentials') == 1


def test_restart_keeps_uncertain_slot_no_second_entry_or_send(tmp_path, monkeypatch):
    state, path, pin, config, scope, called = configured(tmp_path, monkeypatch)
    candidate = fixture_candidate(tmp_path)
    Factory = sources(state, candidate)
    first = module().run(path, pin, orders_off=True, once=True, source_factory=Factory, clock=lambda: state[2][0])
    second = module().run(path, pin, orders_off=True, once=True, source_factory=Factory, clock=lambda: state[2][0])
    assert first[0]['result']['role'] == 'ENTRY'
    assert second[0]['result']['status'] == 'RECONCILE_ONLY'
    assert second[0]['source_accounting']['status'] == 'SOURCE_RISK_UNKNOWN'
    rows = module().read_events(Path(scope['root'])/'serial-source/series.jsonl')
    assert len(rows) == 1 and rows[0]['kind'] == 'RESERVATION'
    assert state[1].state['calls'] == 0


def test_root_source_failure_blocks_entry_before_reservation(tmp_path, monkeypatch):
    state, path, pin, config, scope, called = configured(tmp_path, monkeypatch)
    out = module().run(path, pin, orders_off=True, once=True,
        source_factory=sources(state, fixture_candidate(tmp_path), root_failure=True), clock=lambda: state[2][0])
    assert out[0]['result']['status'] == 'BLOCKED_SOURCE_ACCOUNTING'
    assert not (Path(scope['root'])/'serial-source/slots').exists()
    assert state[1].state['calls'] == 0


def test_source_failure_does_not_abandon_existing_child_reconciliation(tmp_path, monkeypatch):
    state, path, pin, config, scope, called = configured(tmp_path, monkeypatch)
    candidate = fixture_candidate(tmp_path)
    module().run(path, pin, orders_off=True, once=True,
        source_factory=sources(state, candidate), clock=lambda: state[2][0])
    out = module().run(path, pin, orders_off=True, once=True,
        source_factory=sources(state, candidate, root_failure=True), clock=lambda: state[2][0])
    assert out[0]['result']['status'] == 'RECONCILE_ONLY'
    assert out[0]['source_accounting']['status'] == 'SOURCE_RISK_UNKNOWN'


def test_live_carrier_config_refused_before_credentials(tmp_path, monkeypatch):
    state, path, pin, config, scope, called = configured(tmp_path, monkeypatch)
    config['mode'] = 'OWNER_TINY_LIVE'
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match='ORDERS_OFF'):
        module().run(path, hashlib.sha256(path.read_bytes()).hexdigest(), orders_off=True, once=True)
    assert called == [] and not Path(scope['root']).exists()


def test_physical_owner_conflict_never_loads_credentials_or_creates_root(tmp_path, monkeypatch):
    from research_lab import pump4_selected_runner_v1 as runner
    state, path, pin, config, scope, called = configured(tmp_path, monkeypatch)
    def conflict():
        raise ValueError('ACTIVE_EXISTING_OWNER')
    monkeypatch.setattr(runner, 'platform_verifier', lambda config: conflict)
    with pytest.raises(ValueError, match='ACTIVE_EXISTING_OWNER'):
        module().run(path, pin, orders_off=True, once=True)
    assert called == [] and not Path(scope['root']).exists()


def test_source_pin_drift_blocks_before_selection(tmp_path, monkeypatch):
    state, path, pin, config, scope, called = configured(tmp_path, monkeypatch)
    config['serial_source_files'][next(iter(config['serial_source_files']))] = '0'*64
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match='SOURCE_CLOSURE'):
        module().run(path, hashlib.sha256(path.read_bytes()).hexdigest(), orders_off=True, once=True)
    assert called == []

def test_failed_root_risk_append_never_reserves_first_child(tmp_path, monkeypatch):
    state, path, pin, config, scope, called = configured(tmp_path, monkeypatch)
    def failed(*args):
        raise OSError('source risk fsync failed')
    monkeypatch.setattr(module().SeriesAccounting, 'record', failed)
    out = module().run(path, pin, orders_off=True, once=True,
        source_factory=sources(state, fixture_candidate(tmp_path)), clock=lambda: state[2][0])
    assert out[0]['source_accounting']['status'] == 'SOURCE_RISK_UNKNOWN'
    assert out[0]['result']['status'] == 'BLOCKED_SOURCE_ACCOUNTING'
    assert not (Path(scope['root'])/'serial-source/slots').exists()
    assert state[1].state['calls'] == 0

def test_rejected_cumulative_history_keeps_active_child_for_reconcile(tmp_path, monkeypatch):
    state, path, pin, config, scope, called = configured(tmp_path, monkeypatch)
    candidate = fixture_candidate(tmp_path)
    Factory = sources(state, candidate)
    module().run(path, pin, orders_off=True, once=True, source_factory=Factory, clock=lambda: state[2][0])
    # Reach exactly the closure guard: source reducer and child terminal result
    # are stubbed; the cumulative journal still explicitly rejects the source.
    monkeypatch.setattr(module().SerialSourceOwner, 'registry', lambda *_: [])
    def rejected(*args):
        raise ValueError('SOURCE_HISTORY_SHRANK')
    reconciled = []
    def terminal(*args, **kwargs):
        reconciled.append(True)
        return dict(status='FLAT_COSTS_PENDING')
    monkeypatch.setattr(module().SeriesAccounting, 'record', rejected)
    monkeypatch.setattr(module(), 'selected_tick', terminal)
    out = module().run(path, pin, orders_off=True, once=True, source_factory=Factory, clock=lambda: state[2][0])
    assert reconciled and out[0]['source_accounting']['status'] == 'SOURCE_RISK_UNKNOWN'
    rows = module().read_events(Path(scope['root'])/'serial-source/series.jsonl')
    assert [row['kind'] for row in rows] == ['RESERVATION']

def test_full_memory_source_cycle_closes_but_never_releases_unknown_costs(tmp_path, monkeypatch):
    from decimal import Decimal
    from test_pump4_serial_accounting_v1 import sync
    state, path, pin, config, scope, called = configured(tmp_path, monkeypatch)
    candidate = fixture_candidate(tmp_path)
    plan = __import__('research_lab.pump4_selected_runner_v1', fromlist=['causal_plan']).causal_plan(
        **candidate, epoch_started_ms=config['epoch_started_ms'],
        max_delay_ms=config['entry_max_delay_ms'], now_ms=state[2][0])
    Base = provider(state, candidate)
    price = ['100']
    execution_times = {}
    class Sources(Base):
        def fixed(self, bundle):
            quote = bundle['captures']['quote']['body']['result']['list'][0]
            quote.update(lastPrice=price[0], bid1Price=price[0], ask1Price=price[0])
            for window in bundle['history_windows']:
                for page in window['groups']['executions']['pages']:
                    for fill in page['body']['result']['list']:
                        fill['execTime'] = str(execution_times[fill['orderLinkId']])
            return sync(bundle)
        def _capture(self, symbol, begin, *, custody):
            bundle, public = inputs(state[1], now=state[2][0])
            return self.fixed(bundle), public
        def account(self, plan, *, custody):
            bundle, public = super().account(plan, custody=custody)
            return self.fixed(bundle), public
    results = []
    for target in ['100', str(plan['targets'][0]-.01), str(plan['targets'][1]-.01), str(plan['targets'][1]-.01)]:
        price[0] = target
        out = module().run(path, pin, orders_off=True, once=True, source_factory=Sources, clock=lambda: state[2][0])
        results.append(out[0])
        if out[0]['result'].get('request'):
            request = out[0]['result']['request']
            execution_times[request['orderLinkId']] = state[2][0]+1
            # Explicit test-exchange step outside the OFF controller; fake only.
            state[1].state['fixture_exit_price'] = target
            state[1].wire('POST','https://api.bybit.com/v5/order/create',{},json.dumps(request).encode(),1)
        state[2][0] += 1000
    assert [row['result'].get('role') for row in results[:3]] == ['ENTRY','TP1','TP2']
    assert results[-1]['result']['status'] == 'FLAT_COSTS_PENDING'
    assert results[-1]['source_accounting']['status'] == 'SOURCE_ACCOUNTING_RECORDED'
    rows = module().read_events(Path(scope['root'])/'serial-source/series.jsonl')
    assert [row['kind'] for row in rows] == ['RESERVATION','CLOSED_COSTS_PENDING']
    final = module().run(path, pin, orders_off=True, once=True, source_factory=Sources, clock=lambda: state[2][0])
    assert final[0]['result']['status'] == 'BLOCKED_COST_RELEASE_POLICY_NOT_APPROVED'
    assert state[1].state['calls'] == 3 and Decimal(state[1].state['held']) == 0
