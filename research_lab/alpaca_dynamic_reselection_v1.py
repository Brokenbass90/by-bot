"""Event-triggered candidate, ORDERS_OFF. No broker, credentials or LIVE runner.

Original Weekly and Monthly policies stay separate. A verified full exit before
this session's open requests a fresh unchanged selector on previous closed bars.
Slots, sizing, cash/fees, cooldown, reservations and restart use DynamicBook.
Inputs are caller evidence. This candidate has no research or money approval.
"""
from datetime import date
import json,sqlite3
from pathlib import Path

from research_lab import alpaca_dynamic_v1 as base
from research_lab.alpaca_dynamic_live_runtime_v1 import safe_path

CONTRACT={'schema':'ALPACA_DYNAMIC_EVENT_RESELECTION_V1_CANDIDATE',
          'status':'CANDIDATE_RESEARCH_UNAPPROVED','trigger':'CONFIRMED_FULL_OWNED_EXIT_BEFORE_OPEN',
          'selection':'FRESH_PREVIOUS_COMPLETED_SESSION_AT_NEXT_RTH_OPEN',
          'window_ms':300000,'reentry_calendar_days':21,'max_new_entries_per_session':1,
          'slot_risk_and_notional':'UNCHANGED_PARENT_DYNAMIC_POLICY','orders_allowed':False,'money_authority':False}
KIND='EVENT_RESELECTION_RESEARCH_ORDERS_OFF'


class EventReselectionBook(base.DynamicBook):
    def __init__(self,path,policy):
        path=safe_path(str(Path(path).absolute()))
        if path.exists():
            try:
                with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
                    values=dict(db.execute('SELECT key,value FROM meta'))
                if values.get('runtime_kind')!=KIND or values.get('event_contract')!=base.digest(CONTRACT):
                    raise ValueError('CANDIDATE_BOOK_REQUIRED')
            except sqlite3.Error as e:raise ValueError('CANDIDATE_BOOK_REQUIRED') from e
        super().__init__(path,policy)
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO meta VALUES ('runtime_kind',?)",(KIND,))
            db.execute("INSERT OR IGNORE INTO meta VALUES ('event_contract',?)",(base.digest(CONTRACT),))
        self._trigger_window=None

    def _refresh_window_allowed(self,window,calendar):
        return self._trigger_window==window

    def _event(self,snapshot,calendar,now):
        current=base.session_at(calendar,now)
        if not current:return None,set(),'NOT_SELECTION_WINDOW'
        p=self.policy;s=snapshot
        if (s['account_id']!=p['account_id'] or s['single_owner_verified'] is not True
            or s['cash_finality_verified'] is not True or not 0<=now-base.instant(s['observed_ms'])<=p['max_snapshot_age_ms']):
            raise ValueError('BROKER_OR_CASH_UNCONFIRMED')
        base.pin(s['source_sha256'])
        held={r['symbol'] for r in s['positions']};open_names={r['symbol'] for r in s['open_orders']}
        with self.db() as db:
            slots={key:json.loads(raw) for key,raw in db.execute('SELECT entry,payload FROM slots')}
            saved=[json.loads(raw) for raw, in db.execute('SELECT payload FROM exits')]
        blocked=held|set(s['blocked_symbols']);triggers=[]
        for exited in [*saved,*s['exits']]:
            slot=slots.get(exited['entry_order_id']);orders=exited['orders']
            if not slot or slot['symbol'] in held|open_names or not orders:continue
            if len({o['id'] for o in orders})!=len(orders):continue
            total=base.dec(0);times=[];valid=True
            for order in orders:
                stamp=base.instant(order['filled_ms']);times.append(stamp)
                valid &= (order['symbol']==slot['symbol'] and order['side']=='sell'
                    and order['status'] in {'filled','canceled','expired'}
                    and slot['entry_ms']<=stamp<=s['observed_ms'] and stamp<current['open_ms'])
                total+=base.positive(order['filled_qty']);base.positive(order['filled_avg_price'])
            if not valid or total!=base.positive(slot['qty']):continue
            triggers.append(exited)
            if now-max(times)<p['reentry_calendar_days']*86400000:blocked.add(slot['symbol'])
        if not triggers:return current,blocked,'NO_CONFIRMED_VACANCY'
        return current,blocked,'EXIT_TRIGGER_CONFIRMED'

    def reselect(self,*,snapshot,history,calendar,source_sha256,source_available_ms,now_ms):
        try:
            now=base.instant(now_ms);base.policy_check(self.policy);base.source_check(self.policy,calendar)
            current,blocked,status=self._event(snapshot,calendar,now)
            if status!='EXIT_TRIGGER_CONFIRMED':return self._result(status)
            old=self.ranking_at(current['open_ms'])
            if not old:
                if set(history)!=set(self.policy['universe']):raise ValueError('UNIVERSE_SOURCE_CONFLICT')
                base.pin(source_sha256);available=base.instant(source_available_ms)
                prior=[r for r in calendar if r['close_ms']<current['open_ms']]
                if not prior or not prior[-1]['close_ms']<=available<=now:raise ValueError('MISSING_OR_FUTURE_SOURCE')
                cutoff=date.fromisoformat(prior[-1]['session'])
                from scripts.alpaca_adaptive_paper import prepare_intended_report
                eligible={s:bars for s,bars in history.items() if s=='SPY' or s not in blocked}
                report=prepare_intended_report(eligible,signal_session=cutoff,entry_session=date.fromisoformat(current['session']))
                ranking={'policy_sha256':self.policy_hash,'window_ms':current['open_ms'],'signal_session':cutoff.isoformat(),
                    'input_sha256':source_sha256,'source_available_ms':available,'gate_ok':report['gate_ok'],
                    'picks':report['picks'],'blocked_symbols':sorted(blocked),'selector_source_hashes':report['selector_source_hashes']}
                self._trigger_window=current['open_ms']
                try:self.seal_ranking(ranking,calendar,now)
                finally:self._trigger_window=None
            proposal=self.propose(snapshot,calendar,now)
            return self._result(proposal['status'],proposal=proposal,ranking_signal_session=(old or ranking)['signal_session'])
        except (ValueError,KeyError,TypeError,ArithmeticError) as e:
            # Only local fixed validation errors are expected. No HTTP is present.
            return self._result('BLOCKED_DATA',reason=type(e).__name__)

    @staticmethod
    def _result(status,**fields):
        return {'schema':CONTRACT['schema'],'status':status,'contract_status':CONTRACT['status'],
                'contract_sha256':base.digest(CONTRACT),'orders_allowed':False,'money_authority':False,
                'broker_truth_authenticated':False,**fields}
