"""PUMP4-only sequential rehearsal over the unchanged V1 owner/lifecycle.

Deliberately accepts only the fictional test account and ORDERS_OFF. There is
no GO loader, signed sender, actual fee-finality producer, or LIVE activation.
Model settlement reserves explicitly declared hypothetical pending expenses;
it is never broker cost finality or permission to release a real pilot.
"""
import copy
import hashlib
import os
from datetime import datetime, timezone
from decimal import Decimal as D

from research_lab.alpaca_dynamic_v1 import digest
from research_lab.att1_lifecycle_journal import LifecycleJournal, SCHEMA
from research_lab.kity_micro_physical_owner_v1 import publish
from research_lab.kity_oct15_deadline_v1 import decode, stable_bytes
from research_lab.pump4_account_adapter_v1 import frozen_plan
from research_lab.pump4_account_owner_v1 import Pump4AccountOwner, safe
from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle

FIXTURE_KEY = 'NONFINANCIAL_PUMP4_ACCOUNT_FIXTURE_KEY'
FIXTURE_FP = hashlib.sha256(FIXTURE_KEY.encode()).hexdigest()
DOMAIN = 'PUMP4_SERIAL_ORDERS_OFF_V1'


def need(ok, reason):
    if not ok:
        raise ValueError('PUMP4_SERIAL_' + reason)


def decimal(value, *, zero=True):
    need(isinstance(value, str), 'DECIMAL_STRING_REQUIRED')
    n = D(value)
    need(n.is_finite() and (n >= 0 if zero else n > 0), 'INVALID_NONNEGATIVE_AMOUNT')
    return n


def no_wire(*args, **kwargs):
    raise ValueError('PUMP4_SERIAL_NO_WIRE_ORDERS_OFF')


class Pump4SerialOrdersOff:
    def __init__(self, scope, *, lease, clock):
        self.scope = copy.deepcopy(scope)
        s = self.scope
        need(s['schema'] == 'PUMP4_SERIAL_ORDERS_OFF_SCOPE_V1'
             and s['mode'] == 'ORDERS_OFF' and s['fixture_only'] is True,
             'FICTIONAL_ORDERS_OFF_ONLY')
        need(s['account_fingerprint'] == FIXTURE_FP, 'FICTIONAL_ACCOUNT_ONLY')
        need(type(s['valid_from_ms']) is int and type(s['valid_until_ms']) is int
             and s['valid_from_ms'] < s['valid_until_ms'], 'AUTHORITY_WINDOW')
        p = s['policy']
        need(type(p['max_entries']) is int and 1 <= p['max_entries'] <= 20
             and type(p['max_positions']) is int and p['max_positions'] == 1, 'LIMITS')
        for key in ('allocation_usdt', 'gross_usdt', 'risk_usdt', 'day_loss_usdt',
                    'week_loss_usdt', 'drawdown_usdt', 'lifetime_loss_usdt'):
            decimal(p[key], zero=False)
        need(decimal(p['reserve_usdt']) < decimal(p['allocation_usdt']), 'RESERVE')
        need(decimal(p['slippage_bps']) < 10000, 'SLIPPAGE')
        self.scope_sha256 = digest(s)
        self.root = safe(s['root'])
        self.lease, self.clock = lease, clock
        self._exclusive(check_file=False)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self.root/'serial-scope.json'
        try:
            publish(path, s)
        except FileExistsError:
            need(decode(stable_bytes(path)) == s, 'SCOPE_DRIFT_NO_RESET')
        self.events = LifecycleJournal(self.root/'serial-events.jsonl')
        self._state()

    def _exclusive(self, *, check_file=True):
        need(digest(self.scope) == self.scope_sha256, 'SCOPE_MUTATED')
        self.lease.assert_held()
        need(self.lease.path == safe(self.scope['account_lock_path'])
             and self.lease.inode == self.scope['account_lock_inode'], 'ORIGINAL_LEASE')
        need(type(self.clock()) is int, 'CLOCK')
        if check_file:
            need(decode(stable_bytes(self.root/'serial-scope.json')) == self.scope, 'SCOPE_DRIFT')

    def _state(self):
        self._exclusive()
        rows = self.events.read()
        st = dict(rows=rows, admissions=[], active=None, completed=0,
                  closed_net=D(0), pending=D(0), blocked=False,
                  total=D(0), signals=set(), last=None)
        for i, e in enumerate(rows):
            need(e['schema_id'] == SCHEMA and e['domain'] == DOMAIN
                 and e['scope_sha256'] == self.scope_sha256
                 and e['event_id'] == 'pump4-serial-'+str(i), 'JOURNAL_DOMAIN')
            need(type(e['observed_ms']) is int and
                 (st['last'] is None or e['observed_ms'] >= st['last']['observed_ms']), 'CLOCK_REVERSED')
            kind = e['kind']
            if kind == 'ADMISSION':
                need(st['active'] is None and e['ordinal'] == len(st['admissions'])+1
                     and e['signal_key'] not in st['signals'], 'ADMISSION_HISTORY')
                st['admissions'].append(e); st['active'] = e
                st['signals'].add(e['signal_key'])
            elif kind in ('SNAPSHOT', 'MODEL_SETTLEMENT'):
                need(st['active'] is not None and e['ordinal'] == st['active']['ordinal'], 'ACTIVE_IDENTITY')
                total = D(e['model_total_net_usdt'])
                need(total.is_finite(), 'RISK_VALUE')
                st['total'] = total
                st['blocked'] |= bool(e['loss_reasons'])
                if kind == 'MODEL_SETTLEMENT':
                    st['closed_net'] = total
                    st['pending'] += decimal(e['pending_fee_upper_bound_usdt'])
                    st['completed'] += 1; st['active'] = None
            elif kind == 'BLOCK':
                st['blocked'] = True
            else:
                need(False, 'JOURNAL_KIND')
            st['last'] = e
        return st

    def _append(self, kind, st, **values):
        now = self.clock()
        need(st['last'] is None or now >= st['last']['observed_ms'], 'CLOCK_REVERSED')
        e = dict(schema_id=SCHEMA, domain=DOMAIN, scope_sha256=self.scope_sha256,
                 event_id='pump4-serial-'+str(len(st['rows'])), kind=kind,
                 observed_ms=now, **values)
        self.events.append(e)
        return e

    def _risk(self, st, total):
        stamp = datetime.fromtimestamp(self.clock()/1000, timezone.utc)
        day, week = stamp.date().isoformat(), list(stamp.isocalendar()[:2])
        prior = next((e for e in reversed(st['rows']) if 'model_total_net_usdt' in e), None)
        daybase = D(prior['day_baseline_usdt']) if prior and prior['day'] == day else st['total']
        weekbase = D(prior['week_baseline_usdt']) if prior and prior['week'] == week else st['total']
        high = max(D(0), D(prior['high_water_usdt']) if prior else D(0), total)
        p = self.scope['policy']; reasons = []
        for reason, loss, cap in (
            ('DAY', total-daybase, p['day_loss_usdt']),
            ('WEEK', total-weekbase, p['week_loss_usdt']),
            ('DRAWDOWN', total-high, p['drawdown_usdt']),
            ('LIFETIME', total, p['lifetime_loss_usdt'])):
            if loss <= -decimal(cap, zero=False): reasons.append(reason)
        return dict(model_total_net_usdt=str(total), day=day, week=week,
                    day_baseline_usdt=str(daybase), week_baseline_usdt=str(weekbase),
                    high_water_usdt=str(high), loss_reasons=reasons)

    def _owner(self, admission):
        path = safe(self.root/'slots'/('%04d' % admission['ordinal']))
        scope = decode(stable_bytes(path/'owner-scope.json'))
        need(digest(scope) == admission['child_scope_sha256'] and scope['root'] == str(path)
             and scope['mode'] == 'ORDERS_OFF', 'CHILD_SCOPE')
        need(not os.path.lexists(path/'owner-go.json'), 'GO_FORBIDDEN')
        return Pump4AccountOwner(scope, lease=self.lease, key=FIXTURE_KEY,
            secret='NONFINANCIAL_UNUSED', wire=no_wire, platform_check=lambda:None,
            clock=self.clock)

    def reserve(self, plan, bundle, public):
        st = self._state(); frozen_plan(plan)
        key = digest([plan['symbol'], plan['side'], plan['signal_bar_open_ms']])
        need(key not in st['signals'], 'DUPLICATE_SIGNAL')
        need(st['active'] is None, 'ACTIVE_LIFECYCLE')
        need(not st['blocked'], 'ENTRY_LOSS_LATCHED' if any(e.get('loss_reasons') for e in st['rows']) else 'ENTRY_SAFETY_LATCHED')
        need(len(st['admissions']) < self.scope['policy']['max_entries'], 'ENTRY_LIMIT')
        now = self.clock()
        need(self.scope['valid_from_ms'] <= now < self.scope['valid_until_ms'], 'ENTRY_EXPIRED')
        need(0 <= now-plan['entry_bar_open_ms'] <= 60000, 'ENTRY_CLOCK')
        prior_entries = [e['entry_bar_open_ms'] for e in st['admissions']]
        need(not prior_entries or plan['entry_bar_open_ms'] > max(prior_entries), 'CURSOR_REWIND')
        ordinal = len(st['admissions'])+1
        path = self.root/'slots'/('%04d' % ordinal)
        p = copy.deepcopy(self.scope['policy'])
        # Keep provisional profits outside allocated capital. Every model fee
        # reserve is already deducted in closed_net and remains unavailable.
        p['allocation_usdt'] = str(decimal(p['allocation_usdt'])+min(D(0), st['closed_net']))
        p.pop('lifetime_loss_usdt'); p['max_entries'] = 1
        need(decimal(p['allocation_usdt']) > decimal(p['reserve_usdt']), 'RESERVE_EXHAUSTED')
        child = dict(self.scope, schema='PUMP4_ACCOUNT_OWNER_SCOPE_V1', root=str(path), policy=p)
        child.pop('fixture_only')
        owner = Pump4AccountOwner(child, lease=self.lease, key=FIXTURE_KEY,
            secret='NONFINANCIAL_UNUSED', wire=no_wire, platform_check=lambda:None,
            clock=self.clock)
        flow = owner.prepare(plan, bundle, public)
        self._append('ADMISSION', st, ordinal=ordinal, signal_key=key,
            entry_bar_open_ms=plan['entry_bar_open_ms'], plan_sha256=plan['plan_sha256'],
            child_scope_sha256=owner.scope_sha256, flow_config_sha256=digest(flow.config))
        return self.summary()

    def _flow(self, owner, admission):
        flow = Pump4Lifecycle.resume(owner.flows/admission['plan_sha256'])
        need(digest(flow.config) == admission['flow_config_sha256'], 'FLOW_CONFIG_DRIFT')
        return flow

    def _current_risk(self, owner, flow):
        risk = owner.risk.read()[-1]
        observation = flow.observations.read()[-1]['observation']
        need(risk['observation_sha256'] == digest(observation)
             and risk['observed_ms'] == observation['observed_ms'],
             'RISK_OBSERVATION_BINDING')
        marker = owner.root/'entry-loss-stop.json'
        if marker.exists():
            need(decode(stable_bytes(marker)).get('reason') != 'RISK_UNKNOWN',
                 'RISK_UNKNOWN_LATCHED')
        return risk

    def tick(self, bundle, public):
        st = self._state(); a = st['active']
        need(a is not None, 'ACTIVE_LIFECYCLE_REQUIRED')
        owner = self._owner(a); flow = self._flow(owner, a)
        # Admission is not a grant to send later after expiry or a safety block.
        # Existing requests instead remain in reconcile/custody; never resend.
        if not flow.requests():
            need(not st['blocked'], 'ENTRY_LOSS_LATCHED' if any(e.get('loss_reasons') for e in st['rows']) else 'ENTRY_SAFETY_LATCHED')
            need(self.scope['valid_from_ms'] <= self.clock() < self.scope['valid_until_ms'], 'ENTRY_EXPIRED')
        result = None
        try:
            result = owner.cycle(flow, bundle, public, apply=False)
            risk = self._current_risk(owner, flow)
            total = st['closed_net']+D(risk['total_net_usdt'])
            self._append('SNAPSHOT', st, ordinal=a['ordinal'],
                child_risk_sha256=digest(risk), status=result['status'],
                **self._risk(st, total))
            return result
        except (ValueError, KeyError, OSError, IndexError):
            self._append('BLOCK', st, reason='SOURCE_OR_RISK_UNKNOWN')
            # Account uncertainty must inhibit entry/release without swallowing
            # an already reserved reduce-only custody action in the model.
            if result is not None and result.get('request') is not None and result['request'].get('reduceOnly') is True and result.get('role') != 'ENTRY':
                return dict(result, serial_accounting_status='UNKNOWN', serial_entry_blocked=True)
            raise

    def settle_model(self, *, pending_fee_upper_bound_usdt):
        bound = decimal(pending_fee_upper_bound_usdt)
        st = self._state(); a = st['active']
        need(a is not None, 'ACTIVE_LIFECYCLE_REQUIRED')
        latest = st['last']
        need(latest['kind'] == 'SNAPSHOT' and latest['status'] in
             ('FLAT_COSTS_PENDING', 'FLAT_COSTS_RECONCILED_ORDERS_OFF'), 'TERMINAL_REQUIRED')
        need(0 <= self.clock()-latest['observed_ms'] <= 5000, 'TERMINAL_STALE')
        owner = self._owner(a); flow = self._flow(owner, a)
        risk = self._current_risk(owner, flow)
        need(digest(risk) == latest['child_risk_sha256'], 'TERMINAL_SOURCE_CHANGED')
        observation = flow.observations.read()[-1]['observation']
        need(observation['held_qty'] == '0' and bool(flow.requests()), 'TERMINAL_REQUIRED')
        total = st['closed_net']+D(risk['total_net_usdt'])-bound
        self._append('MODEL_SETTLEMENT', st, ordinal=a['ordinal'],
            pending_fee_upper_bound_usdt=str(bound), child_risk_sha256=digest(risk),
            cost_finality_proven=False, provenance='SYNTHETIC_COST_MODEL_NOT_BROKER_FINALITY',
            **self._risk(st, total))
        return self.summary()

    def summary(self):
        st = self._state()
        return dict(schema='PUMP4_SERIAL_ORDERS_OFF_SUMMARY_V1',
            status='MODEL_ONLY_NOT_LIVE_READY', scope_sha256=self.scope_sha256,
            admitted_model_cycles=len(st['admissions']), completed_model_cycles=st['completed'],
            active_ordinal=st['active']['ordinal'] if st['active'] else None,
            pending_fee_reserve_usdt=str(st['pending']), model_net_usdt=str(st['total']),
            entry_block_latched=st['blocked'],
            entry_loss_latched=any(bool(e.get('loss_reasons')) for e in st['rows']),
            cost_finality_proven=False,
            actual_execution_proven=False, broker_requests=0, broker_writes=0,
            orders_allowed=False, money_authority=False)
