import copy,hashlib
import pytest
from test_alpaca_monthly_source_ops_v1 import cache,ms
from research_lab import alpaca_dynamic_source_ops_v1 as dynamic
from research_lab import alpaca_monthly_source_ops_v1 as monthly


def full(cache):
    p,c,m=cache;m=copy.deepcopy(m);raw=(p/'SPY_M5.csv').read_bytes();(p/'QQQ_M5.csv').write_bytes(raw)
    m['files']['QQQ_M5.csv']=hashlib.sha256(raw).hexdigest();m['schema']=dynamic.CAPTURE_SCHEMA
    return p,c,m


def test_original_dynamic59_is_separate_from_unchanged_monthly58(cache):
    p,c,m=full(cache);out=dynamic.compile_source(p,m,c,now_ms=ms('2026-10-30T20:12:00Z'))
    assert len(out['history'])==59 and 'QQQ' in out['history'] and len(out['history']['QQQ'])==200
    assert out['schema']==dynamic.SCHEMA and not out['money_authority'] and not out['orders_allowed']
    original=copy.deepcopy(m);original['schema']=monthly.CAPTURE_SCHEMA;original['files'].pop('QQQ_M5.csv')
    old=monthly.compile_source(p,original,c,now_ms=ms('2026-10-30T20:12:00Z'))
    assert len(old['history'])==58 and old['schema']==monthly.SCHEMA


@pytest.mark.parametrize('bad',['missing_qqq','partial_qqq','monthly_schema','wrong_hash'])
def test_dynamic59_cannot_silently_degrade_to_monthly58(cache,bad):
    p,c,m=full(cache)
    if bad=='missing_qqq':m['files'].pop('QQQ_M5.csv')
    if bad=='partial_qqq':
        f=p/'QQQ_M5.csv';f.write_text('\n'.join(f.read_text().splitlines()[:-1])+'\n');m['files'][f.name]=hashlib.sha256(f.read_bytes()).hexdigest()
    if bad=='monthly_schema':m['schema']=monthly.CAPTURE_SCHEMA
    if bad=='wrong_hash':m['files']['QQQ_M5.csv']='0'*64
    with pytest.raises(ValueError):dynamic.compile_source(p,m,c,now_ms=ms('2026-10-30T20:12:00Z'))


def test_restart_retains_source_and_refuses_revision_or_foreign_book(cache,tmp_path):
    p,c,m=full(cache);bundle=dynamic.compile_source(p,m,c,now_ms=ms('2026-10-30T20:12:00Z'))
    root=tmp_path/'dynamic';one=dynamic.seal_source(root,bundle);two=dynamic.seal_source(root,bundle)
    assert one['source_id']==two['source_id'] and two['already_sealed'] is True
    bad=copy.deepcopy(bundle);bad['source_available_ms']+=1;bad['source_id']=dynamic.ops.digest({k:v for k,v in bad.items() if k!='source_id'})
    with pytest.raises(ValueError,match='CONFLICT'):dynamic.seal_source(root,bad)
    other=tmp_path/'foreign';other.mkdir();(other/'ledger').write_text('owned elsewhere')
    with pytest.raises(ValueError,match='FOREIGN'):dynamic.seal_source(other,bundle)


def test_cli_default_does_not_fetch(monkeypatch,capsys):
    from scripts import run_alpaca_dynamic_source_ops_v1 as cli
    monkeypatch.setattr(cli.ops,'capture_full',lambda *a,**k:pytest.fail('no default capture'))
    assert cli.main([])==0 and 'NO_NETWORK_ORDERS_OFF' in capsys.readouterr().out


def test_saved_source_cli_seals_own59_book_without_monthly_or_native_calls(cache,tmp_path,monkeypatch,capsys):
    import json
    from scripts import run_alpaca_dynamic_source_ops_v1 as cli
    p,c,m=full(cache);(p/'capture.json').write_text(json.dumps(m))
    raw={'schema':'BROKER_CALENDAR_GET_CAPTURE_V1','method':'GET','endpoint':'/v2/calendar?start=x',
         'started_ms':ms('2026-10-30T20:09:00Z'),'completed_ms':ms('2026-10-30T20:09:01Z'),
         'body':[dict(date=r['session'],open='09:30',close='16:00') for r in c]}
    cp=tmp_path/'calendar.json';cp.write_text(json.dumps(raw))
    monkeypatch.setattr(cli.time,'time_ns',lambda:ms('2026-10-30T20:21:00Z')*1000000)
    monkeypatch.setattr(cli,'calendar_capture',lambda *a:pytest.fail('saved source must not query broker'))
    root=tmp_path/'runtime'
    assert cli.main(['--runtime',str(root),'--calendar-source',str(cp),'--calendar-source-sha256',monthly.sha(cp),'--cache',str(p)])==0
    out=json.loads(capsys.readouterr().out)
    assert out['status']=='DYNAMIC59_SOURCE_SEALED' and out['symbols']==59 and out['broker_writes']==0
    assert (root/'sources/2026-10-30.json').is_file() and not list(root.rglob('*.sqlite'))
