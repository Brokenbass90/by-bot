"""Isolated ORDERS_OFF serial source/owner integration, not a LIVE activator.

Uses the existing selected_owner for physical verification, credentials and the
original account lease. Child V1 owners share that lease and have an unconditional
rejecting wire. No installed unit, current LIVE selection, GO or risk is changed.

Complete source accounting is implemented; a real cost-release policy is NOT.
Closing a child therefore records COSTS_PENDING and cannot release a second
real-account entry. This deliberate blocker cannot be bypassed by a caller's
``costs_complete`` flag, fixture settlement or an empty transaction log.
"""
import copy
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import threading
import uuid

from research_lab.alpaca_dynamic_v1 import digest
from research_lab.att1_lifecycle_journal import LifecycleJournal, SCHEMA
from research_lab.kity_micro_physical_owner_v1 import publish
from research_lab.kity_oct15_deadline_v1 import stable_bytes, decode
from research_lab.pump4_account_owner_v1 import Pump4AccountOwner, safe
from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle, DOMAIN as FLOW_DOMAIN
from research_lab.pump4_execution_supervisor_v1 import trusted_sources
from research_lab.pump4_selected_runner_v1 import selected_owner, pinned, config_sha, causal_plan
from research_lab.pump4_account_adapter_v1 import frozen_plan
from research_lab.pump4_supervisor_v1 import selected_tick
from research_lab.pump4_serial_accounting_v1 import SeriesAccounting, source_view

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = 'PUMP4_SERIAL_SOURCE_OFF_V1'
FILES = ('research_lab/pump4_serial_accounting_v1.py',
         'research_lab/pump4_serial_source_supervisor_v1.py',
         'scripts/run_pump4_serial_source_off_v1.py')


def source_pins():
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}


def need(ok, reason):
    if not ok:
        raise ValueError('PUMP4_SERIAL_SUPERVISOR_' + reason)


def no_wire(*args, **kwargs):
    raise ValueError('PUMP4_SERIAL_SUPERVISOR_ORDERS_OFF_WIRE_FORBIDDEN')


def read_events(path):
    return LifecycleJournal(path).read()


class SerialSourceOwner:
    def __init__(self, carrier, spec):
        carrier._exclusive()
        need(carrier.scope['mode'] == 'ORDERS_OFF', 'ORDERS_OFF_CARRIER_REQUIRED')
        self.carrier, self.spec = carrier, copy.deepcopy(spec)
        s = self.spec
        need(s['schema'] == 'PUMP4_SERIAL_SOURCE_OFF_SPEC_V1' and s['mode'] == 'ORDERS_OFF'
             and type(s['max_entries']) is int and 1 <= s['max_entries'] <= 10
             and type(s['history_start_ms']) is int and type(s['valid_until_ms']) is int
             and carrier.scope['valid_from_ms'] <= s['history_start_ms'] < s['valid_until_ms']
             <= carrier.scope['valid_until_ms'], 'SERIAL_SPEC')
        self.root = safe(carrier.root/'serial-source')
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.binding = dict(schema='PUMP4_SERIAL_SOURCE_OFF_BINDING_V1', spec=s,
                            carrier_scope_sha256=carrier.scope_sha256)
        self.pin = digest(self.binding)
        target = self.root/'series-binding.json'
        try:
            publish(target, self.binding)
        except FileExistsError:
            need(decode(stable_bytes(target)) == self.binding, 'BINDING_DRIFT_NO_RESET')
        self.events = LifecycleJournal(self.root/'series.jsonl')
        risk = {k: carrier.scope['policy'][k] for k in ('day_loss_usdt', 'week_loss_usdt', 'drawdown_usdt')}
        risk['lifetime_loss_usdt'] = s['lifetime_loss_usdt']
        self.ledger = SeriesAccounting(self.root/'accounting', carrier.scope['account_fingerprint'], risk)
        self._state()

    def _check(self):
        self.carrier._exclusive()
        need(digest(self.binding) == self.pin and self.binding['spec'] == self.spec
             and decode(stable_bytes(self.root/'series-binding.json')) == self.binding, 'BINDING_DRIFT')
        need(not os.path.lexists(self.root/'owner-go.json'), 'NO_SERIAL_FINANCIAL_GO')

    def _state(self):
        self._check()
        rows = self.events.read()
        admissions, closes, active, signals, cursor = [], {}, None, set(), 0
        for i, row in enumerate(rows):
            need(row['schema_id'] == SCHEMA and row['domain'] == DOMAIN and row['binding_sha256'] == self.pin
                 and row['event_id'] == 'serial-source-' + str(i), 'EVENT_BINDING')
            if row['kind'] == 'RESERVATION':
                frozen_plan(row['plan'])
                key = (row['plan']['symbol'], row['plan']['side'], row['plan']['signal_bar_open_ms'])
                need(active is None and row['ordinal'] == len(admissions)+1 and key not in signals
                     and row['plan']['entry_bar_open_ms'] > cursor, 'RESERVATION_HISTORY')
                admissions.append(row)
                active = row
                signals.add(key)
                cursor = row['plan']['entry_bar_open_ms']
            else:
                need(row['kind'] == 'CLOSED_COSTS_PENDING' and active is not None
                     and active['ordinal'] == row['ordinal'] and row['closed_ms'] >= active['observed_ms'], 'CLOSE_HISTORY')
                closes[row['ordinal']] = row['closed_ms']
                active = None
        return dict(rows=rows, admissions=admissions, closes=closes, active=active, signals=signals, cursor=cursor)

    def _append(self, state, kind, **fields):
        self._check()
        event = dict(schema_id=SCHEMA, domain=DOMAIN, binding_sha256=self.pin,
            event_id='serial-source-'+str(len(state['rows'])), observed_ms=self.carrier.clock(), kind=kind, **fields)
        self.events.append(event)
        return event

    def _child(self, admission, *, create=False):
        scope = copy.deepcopy(self.carrier.scope)
        scope.update(root=str(safe(self.root/'slots'/str(admission['ordinal']))),
                     serial_binding_sha256=self.pin, serial_ordinal=admission['ordinal'])
        if not create:
            need(Path(scope['root']).is_dir(), 'AMBIGUOUS_RESERVED_SLOT_NO_RETRY')
        return Pump4AccountOwner(scope, lease=self.carrier.lease,
            key=self.carrier.key, secret=self.carrier.secret, wire=no_wire,
            platform_check=self.carrier._exclusive, clock=self.carrier.clock)

    def _flow(self, child, admission):
        identity = decode(stable_bytes(safe(child.root/'admitted-lifecycle.json')))
        flow_root = safe(child.flows/admission['plan']['plan_sha256'])
        need(identity['flow_root'] == str(flow_root), 'CHILD_FLOW_PATH')
        flow = Pump4Lifecycle.resume(flow_root)
        need(flow.config['plan'] == admission['plan'] and identity == dict(
            scope_sha256=child.scope_sha256, plan_sha256=admission['plan']['plan_sha256'],
            flow_root=str(flow_root), execution_config_sha256=digest(flow.config)), 'CHILD_ADMISSION_BINDING')
        child._flow(flow)
        return flow

    def registry(self, state):
        slots = []
        for admission in state['admissions']:
            child = self._child(admission)
            flow = self._flow(child, admission)
            actions = flow._events()
            need(bool(actions), 'AMBIGUOUS_RESERVATION_WITHOUT_REQUEST_NO_RETRY')
            ids = set()
            for row in flow.observations.read():
                o = row['observation']
                need(row['schema_id'] == SCHEMA and row['domain'] == FLOW_DOMAIN
                     and row['config_sha256'] == digest(flow.config) and row['kind'] == 'OBSERVATION'
                     and row['event_id'] == 'pump4-observation-'+digest(o), 'NATIVE_WITNESS_BINDING')
                oid = row['verified_native_stop_id']
                if oid:
                    native = o['native_stop']
                    need(native['orderId'] == oid and native['positionIdx'] == 0
                         and native['side'] == ('Buy' if admission['plan']['side'] == 'short' else 'Sell')
                         and native['orderStatus'] == 'Untriggered'
                         and Decimal(native['qty']) == Decimal(o['held_qty']) > 0
                         and native['stopOrderType'] == 'StopLoss', 'NATIVE_WITNESS')
                    ids.add(oid)
            slots.append(dict(ordinal=admission['ordinal'], symbol=admission['plan']['symbol'],
                side=admission['plan']['side'], first_send_ms=min(e['observed_ms'] for e in actions),
                closed_ms=state['closes'].get(admission['ordinal']),
                requests=flow.requests(), verified_native_ids=sorted(ids)))
        return slots

    def tick(self, sources, *, epoch_started_ms, max_delay_ms):
        state = self._state()
        view = None
        try:
            # Reuse the already selected provider, credentials and transport;
            # capture ALL earlier slots, not only the newest signal window.
            bundle, _ = sources._capture(None, self.spec['history_start_ms'], custody=True)
            view = source_view(bundle, self.registry(state),
                expected_fingerprint=self.carrier.scope['account_fingerprint'], now_ms=self.carrier.clock())
            self.ledger.record(view)
            accounting = dict(self.ledger.summary(), status='SOURCE_ACCOUNTING_RECORDED')
        except (ValueError, KeyError, TypeError, OSError, ArithmeticError) as exc:
            # Rejected or non-durable accounting is unusable for BOTH entry
            # and closure. Independent child custody below still reconciles.
            view = None
            accounting = dict(status='SOURCE_RISK_UNKNOWN', cost_finality_proven=False,
                              error_type=type(exc).__name__, release_next_entry_allowed=False)
        if state['active'] is not None:
            child = self._child(state['active'])
            # No recreating a lost first reservation after a crash; ambiguity
            # stays blocked. An existing child's custody gets its own fresh GET
            # even if the root accounting query/journal is currently unavailable.
            flow = self._flow(child, state['active'])
            need(bool(flow.requests()), 'AMBIGUOUS_RESERVATION_WITHOUT_REQUEST_NO_RETRY')
            result = selected_tick(child, sources.account, lambda: None,
                epoch_started_ms=epoch_started_ms, max_delay_ms=max_delay_ms, apply=False)
            if (result['status'] == 'FLAT_COSTS_PENDING' and view is not None
                    and view['entry_inputs_complete'] and view['account_open_orders_empty']
                    and all(Decimal(s['signed_inventory']) == 0 for s in view['slots'])):
                self._append(state, 'CLOSED_COSTS_PENDING', ordinal=state['active']['ordinal'],
                             closed_ms=self.carrier.clock(), source_view_sha256=view['view_sha256'])
            return result, accounting
        if view is None or not view['entry_inputs_complete'] or self.ledger.summary()['entry_loss_latched']:
            return dict(status='BLOCKED_SOURCE_ACCOUNTING'), accounting
        if state['admissions']:
            return dict(status='BLOCKED_COST_RELEASE_POLICY_NOT_APPROVED',
                        pending_costs='UNKNOWN', finality_proven=False), accounting
        need(len(state['admissions']) < self.spec['max_entries'], 'SERIAL_ENTRY_LIMIT')
        now = self.carrier.clock()
        need(self.spec['history_start_ms'] <= now <= self.spec['valid_until_ms'], 'SERIAL_ENTRY_WINDOW')
        candidate = sources.candidate()
        if candidate is None:
            return dict(status='NO_NEW_SIGNAL'), accounting
        plan = causal_plan(**candidate, epoch_started_ms=epoch_started_ms,
                           max_delay_ms=max_delay_ms, now_ms=now)
        admission = self._append(state, 'RESERVATION', ordinal=len(state['admissions'])+1, plan=plan)
        child = self._child(admission, create=True)
        child_bundle, public = sources.account(plan, custody=False)
        self._check()
        need(self.carrier.clock() <= self.spec['valid_until_ms'], 'SERIAL_ENTRY_WINDOW')
        need(causal_plan(**candidate, epoch_started_ms=epoch_started_ms, max_delay_ms=max_delay_ms,
                        now_ms=self.carrier.clock()) == plan, 'CAUSAL_PLAN_CHANGED')
        need(self.carrier.clock()-view['observed_ms'] <= 5000, 'ROOT_SOURCE_EXPIRED')
        flow = child.prepare(plan, child_bundle, public)
        return child.cycle(flow, child_bundle, public, apply=False), accounting


def run(config_path=None, config_sha256=None, *, orders_off=False, once=False,
        max_ticks=None, poll_seconds=5, source_factory=None, clock=None, stop=None):
    if not orders_off:
        return [dict(status='ORDERS_OFF_NO_REQUESTS', broker_writes=0)]
    need(type(orders_off) is bool and type(once) is bool and type(poll_seconds) is int
         and 5 <= poll_seconds <= 30 and (max_ticks is None or type(max_ticks) is int and max_ticks > 0), 'EXPLICIT_MODE')
    config = pinned(dict(path=str(config_path), sha256=config_sha256))
    need(config.get('mode') == 'ORDERS_OFF' and config['serial_orders_off']['mode'] == 'ORDERS_OFF', 'ORDERS_OFF_ONLY')
    need(config['serial_source_files'] == source_pins(), 'SOURCE_CLOSURE')
    stop = stop or threading.Event()
    receipts, run_id, ticks = [], uuid.uuid4().hex, 0
    with selected_owner(config_path, config_sha256, dispatch=False, clock=clock) as carrier:
        need(carrier.scope['runner_config_sha256'] == config_sha(config), 'CONFIG_BINDING')
        serial = SerialSourceOwner(carrier, config['serial_orders_off'])
        sources = (source_factory or trusted_sources)(config, carrier)
        while not stop.is_set():
            ticks += 1
            try:
                result, accounting = serial.tick(sources, epoch_started_ms=config['epoch_started_ms'],
                                                max_delay_ms=config['entry_max_delay_ms'])
            except (ValueError, KeyError, TypeError, OSError, ArithmeticError) as exc:
                result = dict(status='BLOCKED_SERIAL_OBSERVATION', error_type=type(exc).__name__)
                accounting = dict(status='SOURCE_RISK_UNKNOWN', release_next_entry_allowed=False)
            receipt = dict(schema='PUMP4_SERIAL_SOURCE_OFF_RECEIPT_V1', result=result,
                source_accounting=accounting, observed_ms=carrier.clock(), run_id=run_id,
                tick=ticks, mode='ORDERS_OFF', broker_writes=0, carrier_scope_sha256=carrier.scope_sha256,
                serial_binding_sha256=serial.pin, cost_release_policy='NOT_IMPLEMENTED_NOT_APPROVED')
            publish(serial.root/'receipts'/(run_id+'-'+str(ticks)+'.json'), receipt)
            if once or max_ticks is not None:
                receipts.append(receipt)
            else:
                receipts[:] = [receipt]
            if once or max_ticks is not None and ticks >= max_ticks or stop.wait(poll_seconds):
                break
    return receipts
