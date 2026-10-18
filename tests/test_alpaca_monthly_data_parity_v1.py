import copy
import json
from datetime import date
from pathlib import Path

import pytest
from test_alpaca_monthly_source_ops_v1 import cache,ms
from research_lab import alpaca_monthly_source_ops_v1 as ops


def real_view():
    import gzip
    return json.loads(gzip.decompress((Path(__file__).parent/'fixtures/alpaca_monthly58_20261016.json.gz').read_bytes()))


def build(cache):
    from research_lab.alpaca_monthly_data_parity_v1 import build_delivery
    p,c,m=cache
    bundle=ops.compile_source(p,m,c,now_ms=ms('2026-10-30T20:21:00Z'))
    return build_delivery(bundle,now_ms=ms('2026-10-30T20:21:00Z'),warmup=200)


def test_export_exact_monthly_universe_and_selector_roundtrip(cache):
    x=build(cache)
    assert len(x['history'])==58 and 'QQQ' not in x['history']
    assert x['parity']['selection_equal'] and x['parity']['ranking_equal']
    assert x['adjustment_policy']['auto_adjust'] is False
    assert x['adjustment_policy']['consumer_price_factor']=='NONE'
    assert x['source_available_ms']==cache[2]['completed_ms']
    assert x['coverage']['fully_checked_sessions']==200


def test_default_260_warmup_cannot_silently_accept_200_sessions(cache):
    from research_lab.alpaca_monthly_data_parity_v1 import build_delivery
    p,c,m=cache;b=ops.compile_source(p,m,c,now_ms=ms('2026-10-30T20:21:00Z'))
    with pytest.raises(ValueError,match='260|WARMUP'):build_delivery(b,now_ms=ms('2026-10-30T20:21:00Z'))


@pytest.mark.parametrize('defect',['QQQ','SIP','adjustment','missing','future','close'])
def test_reader_rejects_contaminated_control_view(defect):
    from research_lab.alpaca_monthly_data_parity_v1 import verify_delivery
    x=real_view()
    if defect=='QQQ':x['history']['QQQ']=x['history']['SPY']
    elif defect=='SIP':x['provider']='ALPACA_SIP'
    elif defect=='adjustment':x['adjustment_policy']['auto_adjust']=True
    elif defect=='missing':x['history']['AAPL'].pop()
    elif defect=='future':x['history']['AAPL'][-1]['session']='2026-11-02'
    else:x['history']['AAPL'][-1]['close']+=.1
    x['data_sha256']=ops.digest({k:v for k,v in x.items() if k!='data_sha256'})
    with pytest.raises(ValueError):verify_delivery(x)


def test_immutable_delivery_replay_and_tampered_seal_fail_closed(tmp_path):
    from research_lab.alpaca_monthly_data_parity_v1 import publish_delivery,verify_files
    x=real_view();root=tmp_path/'delivery'
    a=publish_delivery(root,x);b=publish_delivery(root,x)
    assert not a['already_published'] and b['already_published']
    f=root/(x['session_date']+'.json');f.write_bytes(f.read_bytes()+b' ')
    with pytest.raises(ValueError):verify_files(root,x['session_date'])


def test_diagnostic_has_every_stock_and_no_financial_or_schedule_activation(cache):
    from research_lab.alpaca_monthly_data_parity_v1 import diagnostic
    x=build(cache);d=diagnostic(x)
    assert len(d['stocks'])==57
    assert d['account_cash_gate']=='UNKNOWN_NOT_READ_DATA_ONLY'
    assert not d['orders_allowed'] and d['monthly_calendar_due'] is True
    assert d['hypothetical_weekly']['picks']==d['hypothetical_monthly']['picks']
    assert all(r['reasons'] for r in d['stocks'])


def test_real_snapshot_nonempty_selection_and_flagged_older_warmup_preserve_parity():
    from research_lab.alpaca_monthly_data_parity_v1 import verify_delivery,diagnostic
    x=verify_delivery(real_view());d=diagnostic(x)
    assert [p['symbol'] for p in x['parity']['selection']['picks']]==['SHOP','ABBV','ADSK','MSFT']
    assert x['coverage']['exported_sessions']==260 and x['coverage']['fully_checked_sessions']==257
    assert x['coverage']['core200_complete'] is True
    assert x['coverage']['by_symbol']['AAPL']['incomplete_older_sessions']==['2025-11-28','2025-12-24']
    assert not d['monthly_calendar_due'] and d['hypothetical_weekly']['max_new_entries_per_session']==1


def test_flagged_older_missing_bar_cannot_migrate_into_required_200_sessions():
    from research_lab.alpaca_monthly_data_parity_v1 import verify_delivery,view_proof
    x=real_view();x['coverage']['by_symbol']['AAPL']['incomplete_older_sessions'][0]='2026-10-15'
    x['source_view_proof']=view_proof(x)
    x['data_sha256']=ops.digest({k:v for k,v in x.items() if k!='data_sha256'})
    with pytest.raises(ValueError,match='CORE200'):verify_delivery(x)


def test_data_export_worker_waits_for_19th_capture_and_never_relabels_16th(tmp_path):
    from scripts.export_alpaca_monthly58_daily_v1 import run
    root=tmp_path/'captures';cache=root/'1';cache.mkdir(parents=True)
    cal=dict(schema='BROKER_CALENDAR_GET_CAPTURE_V1',method='GET',endpoint='/v2/calendar?start=2026-10-16',
        started_ms=1,completed_ms=2,body=[dict(date='2026-10-16',open='09:30',close='16:00'),
        dict(date='2026-10-19',open='09:30',close='16:00'),dict(date='2026-10-20',open='09:30',close='16:00')])
    (cache/'calendar.json').write_text(json.dumps(cal));(cache/'capture.json').write_text(json.dumps(dict(completed_ms=ms('2026-10-16T20:21:00Z'))))
    spec=dict(orders_allowed=False,money_authority=False,exports=str(tmp_path/'exports'),source_captures=str(root))
    assert run(spec,now_ms=ms('2026-10-19T17:30:00Z'))['status']=='NOT_DUE_DATA_ONLY'
    assert run(spec,now_ms=ms('2026-10-19T20:25:00Z'))['status']=='WAITING_EXACT_SESSION_CAPTURE'
    assert not (tmp_path/'exports').exists()


def test_cross_python_one_ulp_metrics_preserve_same_selection_not_false_source_conflict():
    from research_lab.alpaca_monthly_data_parity_v1 import verify_delivery
    x=real_view();x['parity']['ranking'][0]['health_score']+=1e-15
    x['parity']['ranking_sha256']=ops.digest(x['parity']['ranking'])
    x['data_sha256']=ops.digest({k:v for k,v in x.items() if k!='data_sha256'})
    assert verify_delivery(x) is x


@pytest.mark.parametrize('defect',['clock','coverage','old_price'])
def test_outer_digest_reseal_does_not_hide_provenance_mutation(defect):
    from research_lab.alpaca_monthly_data_parity_v1 import verify_delivery
    x=real_view()
    if defect=='clock':x['source_started_ms']=x['source_available_ms']+3600000
    elif defect=='coverage':
        for c in x['coverage']['by_symbol'].values():c.update(fully_checked_sessions=260,incomplete_older_sessions=[])
        x['coverage']['fully_checked_sessions']=260
    else:
        for k in ('open','high','low','close'):x['history']['AAPL'][0][k]*=1.01
    x['data_sha256']=ops.digest({k:v for k,v in x.items() if k!='data_sha256'})
    with pytest.raises(ValueError):verify_delivery(x)


def test_old_capture_reconstruction_is_asof_original_completion_not_later_close(cache):
    from scripts.export_alpaca_monthly58_daily_v1 import candidate_bundle
    p,c,m=cache;(p/'capture.json').write_text(json.dumps(m))
    raw=dict(schema='BROKER_CALENDAR_GET_CAPTURE_V1',method='GET',endpoint='/v2/calendar?start=2026-01-01',
        started_ms=m['started_ms']-1000,completed_ms=m['started_ms']-500,
        body=[dict(date=r['session'],open='09:30',close='16:00') for r in c])
    (p/'calendar.json').write_text(json.dumps(raw))
    b=candidate_bundle(p,now_ms=ms('2026-11-02T21:20:00Z'))
    assert b['signal_session']=='2026-10-30' and b['source_available_ms']==m['completed_ms']
    with pytest.raises(ValueError):candidate_bundle(p,now_ms=m['completed_ms']-1)


def test_unfinished_new_directory_does_not_hide_last_completed_capture(tmp_path):
    from scripts.export_alpaca_monthly58_daily_v1 import completed_caches
    root=tmp_path/'captures';(root/'2').mkdir(parents=True);old=root/'1';old.mkdir()
    (old/'capture.json').write_text('{}');(old/'calendar.json').write_text('{}')
    assert completed_caches(root)==[old]
