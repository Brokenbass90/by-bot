"""Prepare immutable private closure inputs, without remote or broker calls.

The kit is additional orders-OFF control tooling, outside the frozen app.
Historical captures keep their original bytes/times. No monetary permit exists.
"""
import base64
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.alpaca_dynamic_v1 import canonical,digest,dec
from research_lab.alpaca_live_readiness_v1 import initial_evidence,write_new,BASE,POLICY,COMMISSION_PROTOCOL_SHA

KIT=BASE+'/control/fee-to-live-v1'
PRIVATE=ROOT/'.private/alpaca_live_readiness_20261013'


def build():
    files={}
    def raw(name,value):
        files[name]=dict(sha256=hashlib.sha256(value).hexdigest(),content_b64=base64.b64encode(value).decode())
        return dict(path=KIT+'/'+name,sha256=files[name]['sha256'])
    def obj(name,value):return raw(name,canonical(value))
    def copy(name,path):return raw(name,(ROOT/path).read_bytes())
    policy=json.loads((ROOT/POLICY).read_bytes())
    handoff=json.loads((PRIVATE/'orders_off_install_handoff_v2_capture.json').read_bytes())['response']
    authority=json.loads((PRIVATE/'post_reboot_authority_oct13.json').read_bytes())['response']
    reboot=json.loads((PRIVATE/'post_reboot_finality_oct13.json').read_bytes())['response']
    basis=json.loads((PRIVATE/'actual_source_basis.json').read_bytes())
    old=json.loads((ROOT/'.private/alpaca_net_arm_20261011/prearm_source.json').read_bytes())['response']
    old_closure=json.loads((ROOT/'reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_opening_receipt.json').read_bytes())
    assert handoff['status']=='ORDERS_OFF_DEPLOYMENT_HANDOFF_VERIFIED_FINALITY_PENDING'
    assert handoff['no_old_manager_inflight'] and handoff['other_cron_lines_byte_preserved']
    assert handoff['service_activations']==handoff['broker_writes']==0 and handoff['orders_allowed'] is False
    assert not any(p['send_orders'] or p['apply'] for p in authority['processes'])
    account=reboot['live_broker']['account']['payload']
    assert account['id']==policy['account_id']==authority['original_live_binding']['account_id']
    assert reboot['live_halt']['halted'] and not reboot['live_broker']['positions']['payload'] and not reboot['live_broker']['open_orders']['payload']
    assert dec(account['pending_reg_taf_fees'])==dec(account['accrued_fees'])==0
    assert old_closure['status']=='KNOWN_OLD_CASH_FINALITY_RECONCILED' and old_closure['cent_rounded_net_matches']
    assert old_closure['pending_reg_taf_fees']=='0'
    slot=sorted(policy['inherited_slots'],key=lambda r:r['entry_order_id'])[0]
    order_rows=json.loads(old['closed_order_source']['raw'])
    entry=next(o for o in order_rows if o['id']==slot['entry_order_id'])
    leg=next(o for o in old_closure['legs'] if o['entry_order_id']==slot['entry_order_id'])
    exit=next(o for o in order_rows if o['id']==leg['exit_order_id'])
    assert entry['status']==exit['status']=='filled' and entry['side']=='buy' and exit['side']=='sell'
    assert entry['symbol']==exit['symbol']==slot['symbol'] and dec(entry['filled_qty'])==dec(exit['filled_qty'])==dec(slot['qty'])
    proof=[copy('handoff-capture.json',PRIVATE.relative_to(ROOT)/'orders_off_install_handoff_v2_capture.json'),
        copy('authority-capture.json',PRIVATE.relative_to(ROOT)/'post_reboot_authority_oct13.json'),
        copy('live-cash-capture.json',PRIVATE.relative_to(ROOT)/'post_reboot_finality_oct13.json'),
        copy('old-orders-capture.json','.private/alpaca_net_arm_20261011/prearm_source.json'),
        copy('old-cash-finality.json','reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_opening_receipt.json')]
    ledger='/root/by-bot/runtime/alpaca_live_v38/protective_exit_hwm.json'
    lock=authority['original_live_lock']
    halt=str(Path(lock).with_suffix('.paper-kill')/'.paper-entry-halt.json')
    authority_source=obj('authority-source.json',dict(account_id=policy['account_id'],endpoint='https://api.alpaca.markets',
        lock_path=lock,ledger_path=ledger,single_entry_owner_verified=True,single_manager_verified=True,
        old_monthly_entries_off=True,active_dynamic_managers=0,manager_state='DESIGNATED_DISABLED',
        observed_ms=authority['observed_ms'],source_files=proof,orders_allowed=False))
    old_source=obj('old-terminal-source.json',dict(status='TERMINAL_FINAL',evidence_kind='BROKER_LIVE',
        account_id=policy['account_id'],entry_order_id=slot['entry_order_id'],qty=slot['qty'],
        exit_order_id=exit['id'],actual_exit=exit,old_account_day_finality=old_closure,
        source_files=proof[3:],orders_allowed=False))
    protocol_pin=copy('commission-protocol.json','reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_protocol_contract.json')
    assert protocol_pin['sha256']==COMMISSION_PROTOCOL_SHA
    protocol=json.loads((ROOT/'reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_protocol_contract.json').read_bytes())
    # Same account/day CAT ceiling, bounded by the inherited quantity. No fee waiver.
    from decimal import Decimal,ROUND_CEILING
    reserve=(dec(slot['qty'])*dec(protocol['regulatory_model']['cat_nms_executed_share_rate'])/Decimal('.01')).to_integral_value(rounding=ROUND_CEILING)*Decimal('.01')
    assert reserve>0
    cost_source=obj('cost-source.json',dict(source_status='SOURCE_BOUND',account_id=policy['account_id'],
        endpoint='https://api.alpaca.markets',commission_rate=protocol['commission_rate'],
        buy_regulatory_reserve_usd=str(reserve),unresolved_liability_usd='0',
        observed_ms=reboot['observed_ms'],source_files=[protocol_pin,proof[2]],
        future_pending_fee_nonzero='fresh source publisher must reject',orders_allowed=False))
    binding=dict(schema='ALPACA_DYNAMIC_LIVE_RUNTIME_V1',endpoint='https://api.alpaca.markets',
        account_id=policy['account_id'],policy_sha256=digest(policy),broker_root='/root/by-bot',
        runtime=str(Path(ledger).parent),ledger_path=ledger,lock_path=lock,halt_path=halt,
        source_book=BASE+'/sources/live_source_book.sqlite',
        native_bridge_sha256=hashlib.sha256((ROOT/'scripts/equities_alpaca_paper_bridge.py').read_bytes()).hexdigest(),
        sources=dict(authority=authority_source,old_terminal=old_source,cost=cost_source))
    original_initial=ROOT/'.private/alpaca_net_paper_20261012/post_window_1335.json'
    initial_public=ROOT/'reports/evidence/alpaca_net_paper_20261012/post_attempt_receipt.json'
    roles={
        'cash_before':copy('cash-before.json','.private/alpaca_net_arm_20261011/postarm_source.json'),
        'initial':raw('initial-capture.json',original_initial.read_bytes()),
        'rearm':copy('rearm-capture.json','.private/alpaca_net_paper_20261012/rearm_oct13_1332.json'),
        'protocol':protocol_pin,
        'arm':copy('arm-receipt.json','reports/evidence/alpaca_net_arm_20261011/arming_receipt.json'),
        'initial_evidence':obj('initial-evidence.json',initial_evidence(initial_public,original_initial)),
        'deployment':obj('deployment.json',handoff['deployment']),
        'binding_template':obj('binding-template.json',binding),
        'policy':dict(path=BASE+'/app/'+POLICY,sha256=hashlib.sha256((ROOT/POLICY).read_bytes()).hexdigest()),
        'fixed_intent':obj('fixed-intent.json',dict(ticker=basis['ticker'],session='2026-10-14',
            ranking_sha256=basis['ranking_sha256'],slot_entry_order_id=slot['entry_order_id'],
            risk_distance=basis['original_frozen_risk_distance'],max_qty=slot['qty'],
            max_notional_usd=slot['notional_cap'],max_risk_usd=slot['risk_cap']))}
    proposal=json.loads((ROOT/'.private/alpaca_net_arm_20261011/install_proposal.json').read_bytes())
    for name in ('template.json','protocol.json','source_binding.json'):
        raw('publisher-'+name,base64.b64decode(proposal['session_files'][name],validate=True))
    obj('publisher-session.json',dict(session='2026-10-14',ticker='NET'))
    copy('closure.py','research_lab/alpaca_fee_to_live_closure_v1.py')
    copy('observe-close-once.py','reports/evidence/alpaca_live_readiness_20261013/observe_fee_closure_v1.py')
    # Save the original compiled GET-only readers verbatim for a later ONE observation.
    import importlib.util
    def reader(filename,attr):
        spec=importlib.util.spec_from_file_location(filename,ROOT/'reports/evidence/alpaca_live_readiness_20261013'/filename)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        return getattr(mod,attr)
    raw('finality-query.py',reader('capture_oct13_finality_v2.py','query')().encode())
    raw('authority-query.py',reader('capture_authority_read_only.py','REMOTE').encode())
    pins=[dict(path=KIT+'/closure.py',sha256=files['closure.py']['sha256'])]
    for rel in ('research_lab/alpaca_live_readiness_v1.py','research_lab/alpaca_dynamic_first_intent_v1.py'):
        pins.append(dict(path=BASE+'/app/'+rel,sha256=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()))
    pins.append(dict(path=BASE+'/control/orders_off_helper_v2.py',sha256=hashlib.sha256((ROOT/'research_lab/alpaca_orders_off_handoff_v2.py').read_bytes()).hexdigest()))
    manifest=dict(schema='ALPACA_FEE_TO_LIVE_CLOSURE_MANIFEST_V1',inputs=roles,code_files=pins,
        output_dir=KIT+'/oct14-closure',orders_allowed=False,live_orders_allowed=False,
        automatic_retry=False,polling=False)
    manifest['manifest_sha256']=digest(manifest);obj('manifest.json',manifest)
    # A second outer pin covers supplemental raw-source files/readers as well.
    file_pins=[dict(path=KIT+'/'+name,sha256=row['sha256']) for name,row in sorted(files.items())]
    kit=dict(schema='ALPACA_FEE_TO_LIVE_STATIC_KIT_V1',base=KIT,files=file_pins,
        manifest_sha256=files['manifest.json']['sha256'],package_sha256=handoff['deployment']['package_sha256'],
        session='2026-10-14',orders_allowed=False,broker_writes=0,service_activations=0)
    kit['kit_sha256']=digest(kit);obj('kit.json',kit)
    out=dict(schema='ALPACA_FEE_TO_LIVE_STAGE_PAYLOAD_V1',base=KIT,files=files,kit_sha256=kit['kit_sha256'])
    payload_path=PRIVATE/('fee_to_live_stage_payload_'+kit['kit_sha256'][:12]+'.json')
    write_new(payload_path,canonical(out))
    print(json.dumps(dict(status='FEE_TO_LIVE_KIT_PREPARED_NOT_STAGED',kit_sha256=kit['kit_sha256'],
        manifest_file_sha256=kit['manifest_sha256'],payload_file=payload_path.name,files=len(files),broker_queries=0,orders_allowed=False)))


if __name__=='__main__':build()
