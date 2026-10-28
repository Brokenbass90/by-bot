"""Bind the accepted PUMP account owner to the existing physical verifier.

Component only: no installer, supervisor loop, authority writer or credential
search. Actual selection requires a separately approved physical handoff from
KITY. ORDERS_OFF uses an unconditional rejecting wire, even with a stray GO.
"""
from contextlib import contextmanager
import hashlib,json,os,stat,time
from pathlib import Path
from research_lab.alpaca_dynamic_v1 import digest
from research_lab.kity_micro_physical_owner_v1 import AccountLease,platform_verifier,load_bound_credentials,wire_post
from research_lab.kity_oct15_deadline_v1 import stable_bytes,decode
from research_lab.pump4_account_owner_v1 import Pump4AccountOwner,safe
from research_lab.pump4_bybit_sources_v1 import closed_h1
from research_lab.pump4_execution_plan_v1 import build_plan,HOUR_MS
from strategies.signals import TradeSignal

ROOT=Path(__file__).resolve().parents[1]
SOURCE_FILES=('backtest/__init__.py', 'backtest/alpaca_bakeoff_v2_contract.py', 'backtest/alpaca_exact_parity_contract.py', 'backtest/alpaca_honest_portfolio.py', 'bot/__init__.py', 'bot/kity_m3_orders_off.py', 'configs/preregistered/pump4_v1_universe_20261020.json', 'forex/__init__.py', 'forex/data.py', 'research_lab/alpaca_completed_session_source_v1.py', 'research_lab/alpaca_day_monitor_v1.py', 'research_lab/alpaca_day_protection_v1.py', 'research_lab/alpaca_dynamic_first_intent_v1.py', 'research_lab/alpaca_dynamic_live_intake_v1.py', 'research_lab/alpaca_dynamic_live_runtime_v1.py', 'research_lab/alpaca_dynamic_paper.py', 'research_lab/alpaca_dynamic_paper_maintenance.py', 'research_lab/alpaca_dynamic_portfolio_admission_v1.py', 'research_lab/alpaca_dynamic_v1.py', 'research_lab/alpaca_fee_to_live_closure_v1.py', 'research_lab/alpaca_live_readiness_v1.py', 'research_lab/alpaca_monthly_binding_v1.py', 'research_lab/alpaca_monthly_cost_source_v1.py', 'research_lab/alpaca_monthly_handoff_v1.py', 'research_lab/alpaca_monthly_native_binding_v1.py', 'research_lab/alpaca_monthly_source_ops_v1.py', 'research_lab/alpaca_orders_off_handoff_v2.py', 'research_lab/alpaca_strategy_parity_v1.py', 'research_lab/att1_lifecycle_journal.py', 'research_lab/kity_execution_micro_bybit_v1.py', 'research_lab/kity_execution_micro_runtime_v1.py', 'research_lab/kity_execution_micro_v1.py', 'research_lab/kity_fresh_eligibility_watch_v1.py', 'research_lab/kity_micro_account_bridge_v1.py', 'research_lab/kity_micro_bounded_owner_v2.py', 'research_lab/kity_micro_handoff_v1.py', 'research_lab/kity_micro_low_latency_v1.py', 'research_lab/kity_micro_physical_owner_v1.py', 'research_lab/kity_micro_post_go_pricing_v1.py', 'research_lab/kity_micro_preflight_v1.py', 'research_lab/kity_micro_pricing_intent_v2.py', 'research_lab/kity_micro_supervisor_v1.py', 'research_lab/kity_micro_transport_v1.py', 'research_lab/kity_oct15_deadline_v1.py', 'research_lab/pump4_account_adapter_v1.py', 'research_lab/pump4_account_owner_v1.py', 'research_lab/pump4_bybit_sources_v1.py', 'research_lab/pump4_closed_bar_intake_v1.py', 'research_lab/pump4_execution_lifecycle_v1.py', 'research_lab/pump4_execution_plan_v1.py', 'research_lab/pump4_execution_supervisor_v1.py', 'research_lab/pump4_runtime_sources_v1.py', 'research_lab/pump4_selected_runner_v1.py', 'research_lab/pump4_server_cycle_v1.py', 'research_lab/pump4_supervisor_v1.py', 'scripts/alpaca_adaptive_paper.py', 'scripts/alpaca_adaptive_shadow.py', 'scripts/alpaca_protective_exit_manager.py', 'scripts/alpaca_v3_event_backtest.py', 'scripts/build_equities_monthly_live_cycle.py', 'scripts/capture_pump4_sources_v1.py', 'scripts/equities_alpaca_paper_bridge.py', 'scripts/equities_earnings_filter.py', 'scripts/run_alpaca_dynamic_v1_orders_off.py', 'scripts/run_pump4_execution_supervisor_v1.py', 'scripts/run_pump4_supervisor_v1.py', 'strategies/__init__.py', 'strategies/alpaca_adaptive_v1.py', 'strategies/alpaca_dynamic_v3_event.py', 'strategies/alpaca_dynamic_v4_event.py', 'strategies/pump_fade_v4r.py', 'strategies/signals.py') + ('research_lab/pump4_warm_reducer_v1.py', 'research_lab/pump4_stream_intake_v1.py', 'research_lab/pump4_source_probe_v1.py', 'scripts/run_pump4_stream_v1.py')


SOURCE_FILES += ('research_lab/pump4_native_stop_v1.py',)
SOURCE_FILES += ('research_lab/pump4_entry_binding_v1.py',)
SOURCE_FILES += ('research_lab/pump4_public_retry_v1.py',)


def need(ok,reason):
    if not ok:raise ValueError('PUMP4_RUNNER_'+reason)


def source_pins():return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def config_sha(config):return digest({k:v for k,v in config.items() if k not in {'authority','_config_path','_config_sha256'}})


def pinned(row):
    path=safe(row['path']);raw=stable_bytes(path)
    need(hashlib.sha256(raw).hexdigest()==row['sha256'],'INPUT_PIN')
    return decode(raw)


@contextmanager
def selected_owner(path,pin,*,dispatch=False,clock=None):
    need(type(dispatch) is bool,'EXPLICIT_MODE')
    path=safe(path);config=pinned(dict(path=str(path),sha256=pin))
    need(config['schema']=='PUMP4_SELECTED_ACCOUNT_RUNNER_V1'
        and config['unit']=='pump4-execution-owner.service','SEPARATE_SELECTED_OWNER')
    need(config['app_root']==str(ROOT) and config['source_files']==source_pins(),'SOURCE_CLOSURE')
    original=pinned(config['original_owner'])
    need(original['unit']=='kity-execution-micro-owner.service'
        and original['unit'] in config['inhibitors'],'LEGACY_OWNER_RETIREMENT_REQUIRED')
    need(all(config[k]==original[k] for k in ('credential_source','credential_source_sha256','account_fingerprint')),'ORIGINAL_ACCOUNT_BINDING')
    scope=pinned(config['authority'])
    need(scope['runner_config_sha256']==config_sha(config)
        and scope['account_fingerprint']==original['account_fingerprint']
        and scope['root']==config['custody_runtime_root'],'SEPARATE_CONFIG_AUTHORITY')
    need(scope['mode']==('OWNER_TINY_LIVE' if dispatch else 'ORDERS_OFF'),'ISOLATED_MODE')
    lock=safe(scope['account_lock_path']);need(lock==Path(original['custody_runtime_root'])/'account.lock','ORIGINAL_LOCK_PATH')
    st=lock.stat();need(stat.S_ISREG(st.st_mode) and st.st_nlink==1
        and st.st_ino==scope['account_lock_inode']==original['account_lock_inode'],'ORIGINAL_LOCK_IDENTITY')
    if dispatch:
        go=safe(Path(scope['root'])/'owner-go.json')
        need(go.is_file(),'EXACT_OWNER_GO_REQUIRED');gst=go.stat()
        need(gst.st_uid==os.geteuid() and gst.st_nlink==1 and stat.S_IMODE(gst.st_mode)==0o600,'EXACT_OWNER_GO_CUSTODY')
        need(decode(stable_bytes(go))==dict(schema='PUMP4_EXACT_ACCOUNT_OWNER_GO_V1',scope_sha256=digest(scope),owner_go_text='GO PUMP4_TINY '+digest(scope)),'EXACT_OWNER_GO_REQUIRED')
    config.update(_config_path=str(path),_config_sha256=pin)
    verify=platform_verifier(config);verify()  # before loading credentials or claiming the original lock
    key,secret=load_bound_credentials(original)
    def no_wire(*a,**k):raise ValueError('PUMP4_RUNNER_ORDERS_OFF_WIRE_FORBIDDEN')
    lease=AccountLease(lock)
    try:
        need(lease.inode==st.st_ino and lock.stat().st_dev==st.st_dev,'LOCK_CHANGED_DURING_HANDOFF')
        verify()
        yield Pump4AccountOwner(scope,lease=lease,key=key,secret=secret,wire=wire_post if dispatch else no_wire,
            platform_check=verify,clock=clock or (lambda:time.time_ns()//1000000))
    finally:lease.close()


def causal_plan(intake,decision_id,captures,*,epoch_started_ms,max_delay_ms,now_ms):
    """Recompute from the exact journal and closed HTTPS bars, never a ready flag.

    Raw hashes prove integrity, not a broker signature. A selected trusted source
    process must own this input. Bootstrap and missed entry windows fail closed.
    Delay is an execution-policy proposal bound by future runner authority.
    """
    need(type(max_delay_ms) is int and 0<max_delay_ms<=60000,'DELAY_POLICY')
    events=intake.journal.read();snapshot=intake.snapshot()
    matches=[d for d in snapshot['decisions'] if d['decision_id']==decision_id]
    need(len(matches)==1,'DECISION_IDENTITY');decision=matches[0]
    entry=decision['bar_open_ms']+HOUR_MS
    need(events[0]['observed_ms']<epoch_started_ms<=entry
        and epoch_started_ms<=decision['first_observed_ms']<=now_ms,'PROSPECTIVE_EPOCH')
    need(0<=now_ms-entry<=max_delay_ms and snapshot['cursor_ms']==decision['bar_open_ms'],'ENTRY_WINDOW_OR_OLD_DECISION')
    need(decision['signal'] is not None,'NO_SIGNAL')
    source=closed_h1(captures,intake.symbol,next_open_ms=entry,observed_ms=now_ms)
    need(0<=now_ms-source['source_ms']<=5000 and 0<=now_ms-source['available_ms']<=5000,'ENTRY_SOURCE_STALE')
    known={b[0]:b for b in events[0]['bars']};known.update({e['bar'][0]:e['bar'] for e in events[1:]})
    need(all(known.get(b[0])==b for b in [*source['seed'],source['signal_bar']]),'SOURCE_JOURNAL_CONFLICT')
    return build_plan(TradeSignal(**decision['signal']),signal_bar_open_ms=decision['bar_open_ms'],next_open_ms=entry,next_open=source['next_open'])
