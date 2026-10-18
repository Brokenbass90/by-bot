import json
from pathlib import Path
import pytest

from research_lab import elder_hedge_event_intake_v1 as intake
from test_elder_hedge_orders_off_v1 import source, context, risk, instrument, H


def files(tmp_path, raw=None):
    producer=tmp_path/'ten.py';producer.write_bytes(b'pinned producer')
    journal=tmp_path/'ten.jsonl';journal.write_bytes((raw or source())+b'\n')
    return producer,journal


def run(tmp_path, *, now=2*H, contexts=None):
    producer=tmp_path/'ten.py';return intake.receive(tmp_path/'ten.jsonl',
        producer=producer,producer_sha256=intake.sha(producer.read_bytes()),
        book=tmp_path/'intake.sqlite',contexts=contexts or {},now_ms=now)


def test_decision_prefix_stops_before_outcome_values_and_keeps_raw_geom():
    # Deliberately invalid terminal value must never be decoded as an outcome.
    raw=source()[:-1]+b', "R": SEALED_OUTCOME_NEVER_DECODE}'
    fields,prefix=intake.decision_prefix(raw)
    assert fields==json.loads(source()) and prefix==source()[:-1]


def test_first_geometry_free_record_cannot_be_replaced_by_later_geometry(tmp_path):
    old=json.loads(source());del old['geom']
    files(tmp_path,json.dumps(old).encode())
    with (tmp_path/'ten.jsonl').open('ab') as f:f.write(source()+b'\n')
    out=run(tmp_path)
    assert out['new_first_short_records']==1 and out['source_rows']==2
    assert out['blockers']=={'FIRST_RECORD_GEOMETRY_MISSING':1}
    assert out['prospective_events_credited']==0


def test_restart_reuses_original_intake_time_and_does_not_duplicate(tmp_path):
    files(tmp_path)
    a=run(tmp_path);b=run(tmp_path,now=3*H)
    assert a['new_first_short_records']==1 and b['new_first_short_records']==0
    assert b['already_recorded']==1 and b['first_short_records']==1


@pytest.mark.parametrize('change', ['truncate','mutate','partial'])
def test_source_prefix_conflict_or_partial_tail_blocks_without_repair(tmp_path,change):
    files(tmp_path);run(tmp_path);p=tmp_path/'ten.jsonl';raw=p.read_bytes()
    p.write_bytes(raw[:10] if change=='truncate' else
        raw.replace(b'BTCUSDT',b'ETHUSDT') if change=='mutate' else raw+b'{')
    with pytest.raises(ValueError,match='PREFIX|TAIL'):run(tmp_path,now=3*H)
    assert p.read_bytes()!=(raw if change!='partial' else b'')


def test_bound_context_is_recorded_but_missing_risk_never_becomes_zero(tmp_path):
    files(tmp_path);out=run(tmp_path,contexts={'BTCUSDT:3600000':context()})
    assert out['context_joined']==1
    assert out['blockers']=={'RISK_AND_INSTRUMENT_SNAPSHOT_REQUIRED':1}
    assert not out['orders_allowed'] and out['broker_requests']==0


def test_producer_mismatch_is_not_silently_repinned(tmp_path):
    p,j=files(tmp_path)
    with pytest.raises(ValueError,match='PRODUCER_PIN'):
        intake.receive(j,producer=p,producer_sha256='0'*64,
            book=tmp_path/'intake.sqlite',contexts={},now_ms=2*H)


def test_cli_relative_receipt_path_and_restart_after_committed_import(tmp_path, monkeypatch):
    from scripts import receive_elder_hedge_events_v1 as cli
    producer,journal=files(tmp_path);monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli,'PRODUCER_SHA256',intake.sha(producer.read_bytes()))
    monkeypatch.setattr(cli,'contexts_from_brain',lambda *a,**kw:{})
    args=['--source',str(journal),'--producer',str(producer),'--book','intake.sqlite',
        '--brain-opportunities','unused','--output','receipt.json']
    assert cli.main(args)==0
    assert json.loads((tmp_path/'receipt.json').read_bytes())['new_first_short_records']==1
    args[-1]='restart.json';assert cli.main(args)==0
    assert json.loads((tmp_path/'restart.json').read_bytes())['already_recorded']==1


def test_context_join_uses_actual_record_availability_not_backdated_decision(monkeypatch):
    from research_lab import brain_shadow_readonly_bridge_v1 as bridge
    row=dict(sleeve='ELDER',side=-1,symbol='BTCUSDT',source_ref='data/ten_ETS2S.jsonl#BTCUSDT:3600000',
        t_observation_ms=2*H,t_decision_ms=2*H,t_recorded_ms=4*H,record_hash='a'*64,
        source_sha256='b'*64,context=dict(bar_ts=H,rezhim_v1='BEAR_TREND'))
    monkeypatch.setattr(bridge,'_read_chain',lambda *a:[row])
    assert not intake.contexts_from_brain('unused',now_ms=3*H)
    ctx=intake.contexts_from_brain('unused',now_ms=5*H)['BTCUSDT:3600000']
    assert ctx['available_ms']==4*H and ctx['observed_ms']==2*H


def test_context_first_decision_hash_conflict_does_not_compile_a_signal(tmp_path):
    files(tmp_path);ctx=dict(context(),brain_decision_source_sha256='f'*64)
    out=run(tmp_path,contexts={'BTCUSDT:3600000':ctx})
    assert out['blockers']=={'CAUSAL_CONTEXT_CONFLICT':1}
    assert out['prospective_events_credited']==0


def test_actual_timely_ets2s_half_fraction_cannot_pass_frozen_point55_contract():
    from research_lab.elder_hedge_orders_off_v1 import compile_intent
    p=Path(__file__).parents[1]/'reports/evidence/elder_event_intake_20261018/actual_f1_conflict.json'
    f=json.loads(p.read_bytes())['decision_fields'];ts=f['ts'];available=f['zapisano']
    assert f['vovremya'] is True and f['geom']['f1']==.5
    ctx=dict(signal_bar_open_ms=ts,observed_ms=ts+H,available_ms=available,
        source_sha256='a'*64,rezhim_v1='BEAR_TREND')
    with pytest.raises(ValueError,match='FROZEN_CONTROL_GEOMETRY_PARAMETERS'):
        compile_intent(json.dumps(f).encode(),source_ref='ACTUAL_DECISION_FIELDS_FIXTURE',
            context=ctx,risk={},instrument={},now_ms=available)
