import copy,gzip,hashlib,importlib,json,os
from pathlib import Path
import pytest

INPUT=Path(__file__).resolve().parents[1]/'reports/evidence/polymarket_ws_data_20261102/inputs'
PINS=json.loads((INPUT.parent/'prototype-source-hashes.json').read_bytes())
NOW=1793613600000


def mod():
    try:return importlib.import_module('research_lab.polymarket_ws_data_v1')
    except ImportError:pytest.fail('Missing bounded DATA-only WS collector')


def store(root,**kw):return mod().SegmentStore(root,'sports',epoch='poly-ws-data-20261102',clock=lambda:NOW,min_free=0,max_total=1000000,**kw)


def test_durable_seal_preserves_raw_duplicates_and_distinct_receive_clocks(tmp_path):
    s=store(tmp_path);s.append('RECV','{"timestamp":1}',received_ms=NOW-20,monotonic_ns=55);s.append('RECV','{"timestamp":1}',received_ms=NOW-10,monotonic_ns=66)
    seal=s.seal();s.close();raw=gzip.decompress((tmp_path/seal['file']).read_bytes());rows=[json.loads(x) for x in raw.splitlines()]
    assert len(rows)==2 and [r['received_ms'] for r in rows]==[NOW-20,NOW-10]
    assert rows[0]['payload']==rows[1]['payload'] and rows[1]['monotonic_ns']==66
    assert hashlib.sha256(raw).hexdigest()==seal['raw_sha256'] and seal['closed_ms']==NOW
    assert seal['venue_sequence_coverage']=='UNKNOWN' and seal['orders_allowed'] is False
    assert not list((tmp_path/'sports').glob('*.partial'))


def test_second_writer_refused_and_crash_partial_never_repaired(tmp_path):
    s=store(tmp_path);s.append('RECV','first');before=next((tmp_path/'sports').glob('*.partial'));raw=before.read_bytes()
    with pytest.raises((BlockingIOError,ValueError)):store(tmp_path)
    s.close(seal=False)
    t=store(tmp_path);t.append('RECV','second');seal=t.seal();t.close()
    assert before.read_bytes()==raw and gzip.decompress((tmp_path/seal['file']).read_bytes()).count(b'first')==0


def test_budget_stops_before_unbounded_write_and_preserves_prior_evidence(tmp_path):
    s=store(tmp_path);s.max_total=900
    with pytest.raises(mod().DataStop):s.append('RECV','a'*1000)
    s.close(seal=False)
    assert sum(p.stat().st_size for p in tmp_path.rglob('*') if p.is_file())<1000


def test_free_disk_floor_stops_data_only(tmp_path):
    with pytest.raises(mod().DataStop):mod().SegmentStore(tmp_path,'sports',epoch='poly-ws-data-20261102',min_free=2**80)


def test_frozen_catalogue_and_both_outcomes_keep_existing_selection(tmp_path):
    f=mod().FrozenSelection(INPUT,PINS)
    import datetime as dt
    when=dt.datetime.fromtimestamp(NOW/1000,dt.timezone.utc)
    market=dict(id='m1',question='Alpha vs Beta',endDate=when.isoformat(),volume='50001',outcomes='["Alpha","Beta"]',clobTokenIds='["11","22"]',closed=False)
    calls=[]
    def fetch(url):calls.append(url);return [dict(markets=[market])] if 'offset=0&' in url or url.endswith('offset=0') else []
    selected=f.markets(NOW,fetch)
    assert len(selected)==1 and selected[0]['token']=='11'
    snapshot=dict(markets=[dict(selected[0],tokens=['11','22'])])
    assert f.tokens(snapshot,NOW)==['11','22']
    assert f.tokens(snapshot,NOW+9*3600000)==[]
    bad=dict(PINS);bad['poly_clob_ws_sbor.py']='0'*64
    with pytest.raises(ValueError):mod().FrozenSelection(INPUT,bad)


def test_get_and_ws_sends_cannot_reach_private_or_order_endpoints():
    m=mod()
    assert m.validate_send('sports','pong')=='pong'
    assert m.validate_send('clob','PING')=='PING'
    s=json.dumps(dict(type='market',assets_ids=['11'],custom_feature_enabled=True))
    assert m.validate_send('clob',s)==s
    for payload in (json.dumps(dict(type='user',auth={'apiKey':'x'})),json.dumps(dict(operation='order',assets_ids=['11'])),json.dumps(dict(type='market',assets_ids=['11'],auth='x'))):
        with pytest.raises(ValueError):m.validate_send('clob',payload)
    for url in ('https://clob.polymarket.com/order','http://gamma-api.polymarket.com/events','https://evil.test/events','https://gamma-api.polymarket.com/events?offset=-1'):
        with pytest.raises(ValueError):m.validate_get(url)


def test_stale_or_future_catalogue_is_not_subscription_authority(tmp_path):
    m=mod();root=tmp_path/'catalog';root.mkdir()
    x=dict(generated_ms=NOW-2500000,markets=[]);(root/'current.json').write_text(json.dumps(x))
    with pytest.raises(ValueError):m.load_catalogue(tmp_path,NOW)
    x['generated_ms']=NOW+1;(root/'current.json').write_text(json.dumps(x))
    with pytest.raises(ValueError):m.load_catalogue(tmp_path,NOW)


def test_default_cli_does_not_read_sources_or_connect(tmp_path,capsys):
    try:from scripts.run_polymarket_ws_data_v1 import main
    except ImportError:pytest.fail('Missing explicit DATA-only CLI')
    assert main(['--spec',str(tmp_path/'absent')])==0
    assert json.loads(capsys.readouterr().out)['status']=='DATA_ONLY_NO_REQUESTS'
    assert not list(tmp_path.iterdir())


def test_disconnect_creates_gap_and_reconnect_preserves_each_received_frame(tmp_path,monkeypatch):
    m=mod();calls=[]
    class WS:
        def __enter__(self):return self
        def __exit__(self,*a):return False
        def send(self,x):calls.append(('send',x))
        def recv(self,**kw):
            count=sum(1 for x in calls if x[0]=='recv');calls.append(('recv',count))
            if count==0:return 'ping'
            if count==1:raise OSError('disconnect')
            if count==2:return '{"gameId":1,"ended":false}'
            raise m.DataStop('fixture ends')
    def connect(url,**kw):calls.append(('connect',url));return WS()
    monkeypatch.setattr(m.time,'sleep',lambda _:None)
    with pytest.raises(m.DataStop):m.run_worker(tmp_path,'sports',None,connect=connect)
    rows=[]
    for p in sorted((tmp_path/'sports/sealed').glob('*.gz')):rows.extend(json.loads(x) for x in gzip.decompress(p.read_bytes()).splitlines())
    assert sum(x[0]=='connect' for x in calls)==2
    assert any(r['kind']=='DISCONNECTED' and r['payload']['missing_messages']=='UNKNOWN' for r in rows)
    assert [r['payload']['frame'] for r in rows if r['kind']=='RECV']==['ping','{"gameId":1,"ended":false}']


def test_each_frame_does_not_rescan_the_entire_archive(tmp_path,monkeypatch):
    m=mod();calls=[];original=Path.rglob
    def scan(path,pattern):calls.append(str(path));return original(path,pattern)
    monkeypatch.setattr(Path,'rglob',scan)
    s=store(tmp_path)
    for n in range(10):s.append('RECV',str(n))
    assert len(calls)<=2
    s.close()
