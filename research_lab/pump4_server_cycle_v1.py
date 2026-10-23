"""One server DATA-only cycle; reuse the existing financial owner's cycle API.

No alternate lease, credentials, default POST or authority creation. Actual source
bootstrap/restart is evidence only. A busy physical owner is reported, never
stopped, replaced or bypassed. owner_cycle is called only by an already selected
owner; its exact GO, original lease and platform verification remain mandatory.
"""
import hashlib,json
from pathlib import Path
from research_lab.pump4_bybit_sources_v1 import closed_h1,flat_account,universe
from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
from research_lab.pump4_execution_plan_v1 import build_plan
from research_lab.pump4_account_owner_v1 import source_sizing,safe
from research_lab.kity_micro_physical_owner_v1 import publish
from strategies.signals import TradeSignal


def owner_cycle(owner,plan,bundle,public,*,apply=False):
    owner._exclusive()
    return owner.cycle(owner.prepare(plan,bundle,public),bundle,public,apply=apply)


def analyze(root,archive,bundle,public,policy,*,fingerprint,now_ms,physical,read_symbol=None,diagnostics=True):
    root=safe(root);archive=safe(archive)
    seal=json.loads((archive/'receipt.json').read_bytes())
    for name,pin in seal['source_capture_files'].items():
        path=safe(archive/name)
        if not path.is_relative_to(archive) or hashlib.sha256(path.read_bytes()).hexdigest()!=pin:
            raise ValueError('PUMP4_SERVER_ARCHIVE_HASH')
    view=flat_account(bundle,expected_fingerprint=fingerprint,now_ms=now_ms)
    root.mkdir(parents=True,exist_ok=True,mode=0o700);rows=[];duplicates=0;pass_count=0
    for symbol in universe():
        p=archive/'symbols'/(symbol+'.json');name=str(p.relative_to(archive))
        if name not in seal['source_capture_files']:raise ValueError('PUMP4_SERVER_ARCHIVE_COVERAGE')
        row=json.loads(p.read_bytes())
        if row['symbol']!=symbol:raise ValueError('PUMP4_SERVER_SYMBOL_IDENTITY')
        if row['status']!='READY_H1_BOOTSTRAP_NOT_ENTRY':
            rows.append(dict(symbol=symbol,status=row['status']));continue
        s=closed_h1(row['captures'],symbol,next_open_ms=seal['source_hour_open_ms'],observed_ms=row['source']['observed_ms'])
        if s!=row['source']:raise ValueError('PUMP4_SERVER_SOURCE_REPLAY')
        intake=Pump4Intake(root/(symbol+'.jsonl'),symbol)
        events=intake.journal.read()
        if not events:intake.seed(s['seed'],available_ms=s['available_ms'],observed_ms=s['observed_ms'])
        else:
            known={b[0]:b for b in events[0]['bars']}
            known.update({e['bar'][0]:e['bar'] for e in events[1:]})
            if any(b[0] in known and b!=known[b[0]] for b in s['seed']):
                raise ValueError('PUMP4_SERVER_SOURCE_HISTORY_CONFLICT')
        # Existing accept rejects gaps/changed duplicates. Never reseed an
        # existing cursor or silently skip missing hours after downtime.
        result=intake.accept(s['signal_bar'],available_ms=s['available_ms'],observed_ms=s['observed_ms'])
        duplicates+=not result['new'];decision=result['decision'];pass_count+=1
        out=dict(symbol=symbol,status='CLOSED_H1_INTAKE_PASS',decision_id=decision['decision_id'],signal_present=decision['signal'] is not None)
        if decision['signal'] and diagnostics:
            plan=build_plan(TradeSignal(**decision['signal']),signal_bar_open_ms=decision['bar_open_ms'],next_open_ms=s['next_open_ms'],next_open=s['next_open'])
            validation_bundle=bundle;validation_now=now_ms
            if read_symbol is not None:
                import copy
                cap,validation_now=read_symbol(symbol);validation_bundle=copy.deepcopy(bundle)
                validation_bundle['captures']['symbol_position']=cap
                validation_bundle['completed_ms']=validation_now
            elif symbol in bundle.get('symbol_positions',{}):
                import copy
                validation_bundle=copy.deepcopy(bundle);validation_bundle['captures']['symbol_position']=bundle['symbol_positions'][symbol]
            try:out['sizing']=dict(status='FEASIBLE_PROPOSAL_ONLY',**source_sizing(plan,validation_bundle,public,policy,fingerprint=fingerprint,now_ms=validation_now))
            except (ValueError,KeyError,TypeError) as exc:out['sizing']=dict(status='BLOCKED',reason=str(exc))
        rows.append(out)
    busy=physical.get('owner_active') is True or physical.get('lock_held') is True
    receipt=dict(schema='PUMP4_SERVER_ACTUAL_ORDERS_OFF_CYCLE_V1',status='DATA_COMPONENT_PASS_FINANCIAL_NOT_SELECTED',
        census=len(rows),source_intake_pass=pass_count,duplicate_decisions=duplicates,rows=rows,
        source_archive_sha256=hashlib.sha256((archive/'receipt.json').read_bytes()).hexdigest(),account_source_sha256=hashlib.sha256(json.dumps(bundle,sort_keys=True).encode()).hexdigest(),
        account_flat=view['positions_flat'],physical_owner_status='EXISTING_OWNER_BUSY_NO_SECOND_WRITER' if busy else 'OWNER_SELECTION_NOT_PROVEN',physical=physical,
        financial_owner_constructed=False,original_lock_not_replaced=True,bootstrap_or_replay_only=True,prospective_decisions_credited=0,
        broker_writes=0,orders_allowed=False,money_authority=False,tiny_ready=False)
    publish(root/('receipt-'+str(__import__('time').time_ns())+'.json'),receipt)
    return receipt
