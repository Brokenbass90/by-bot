"""Mock-network collector acceptance, synthetic prices and real capture files."""
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from research_lab.ibit_btc_collector_v1 import Collector, GetOnlyHTTP, SourceError, build_request, validate_request

NY=ZoneInfo('America/New_York'); UTC=dt.timezone.utc

def moment(day='2026-10-19',hour=16,minute=20):
    return dt.datetime.combine(dt.date.fromisoformat(day),dt.time(hour,minute),NY).astimezone(UTC)


def profile(tmp_path):
    p=tmp_path/'profile.json'; p.write_text(json.dumps({'alpaca_key_id':'fake-id','alpaca_secret_key':'fake-secret','massive_api_key':'fake-massive'})); p.chmod(0o600)
    return p


class FakeHTTP:
    def __init__(self,now,half=False,empty=False): self.now=now; self.half=half; self.empty=empty; self.calls=[]
    def get(self,request):
        validate_request(request); self.calls.append(request)
        day=request.session; end=moment(day,16,0); start=int((end-dt.timedelta(hours=1)).timestamp()*1000)
        if request.source=='calendar': raw=[{'date':day,'open':'09:30','close':'13:00' if self.half else '16:00'}]
        elif request.source=='alpaca_sip': raw={'bars':{'IBIT':[] if self.empty else [{'t':moment(day,0,0).isoformat(),'c':50.0}]},'next_page_token':None}
        elif request.source=='binance': raw=[] if self.empty else [[start,'1','1','1','100000','1',start+3599999]]
        elif request.source=='bybit': raw={'retCode':0,'result':{'category':'linear','symbol':'BTCUSDT','list':[] if self.empty else [[str(start),'1','1','1','100000','1','1']]}}
        else: raw={'status':'OK','results':[{'T':'IBIT','o':49,'h':51,'l':48,'c':50}]}
        return 200,json.dumps(raw).encode(),self.now


def test_default_no_network_or_credential_discovery(tmp_path):
    fake=FakeHTTP(moment())
    c=Collector(tmp_path/'not-created',credentials=tmp_path/'missing',http=fake)
    assert c.collect('2026-10-19')['status']=='NO_NETWORK'
    assert not fake.calls and not (tmp_path/'not-created').exists()


def test_fixed_request_whitelist_and_spot_venue():
    keys={'alpaca_key_id':'id','alpaca_secret_key':'secret','massive_api_key':'m'}
    for source in ('calendar','alpaca_sip','binance','bybit','massive'):
        req=build_request(source,'2026-10-19',keys); validate_request(req)
        assert req.method=='GET' and 'secret' not in repr(req)
        if source=='binance': assert (req.host,req.path)==('api.binance.com','/api/v3/klines')
        if source=='alpaca_sip': assert req.params['timeframe']=='1Day' and req.params['feed']=='sip'
        from dataclasses import replace
        for bad in (replace(req,method='POST'),replace(req,host='evil.test'),replace(req,path='/v2/orders'),replace(req,params={**req.params,'apiKey':'leak'})):
            with pytest.raises(ValueError): validate_request(bad)


def test_capture_before_decision_and_restart_first_receipt(tmp_path):
    p=profile(tmp_path); store=tmp_path/'store'; first=moment(); fake=FakeHTTP(first)
    c=Collector(store,credentials=p,http=fake,enabled=True,clock=lambda:first)
    result=c.collect('2026-10-19')
    assert result['decision']['freshness']=='FRESH' and result['decision']['received_at_ms']==int(first.timestamp()*1000)
    assert result['warmup']['valid_sessions']==1 and result['warmup']['full_window_prior_sessions']==80
    for source in ('calendar','alpaca_sip','binance','bybit'):
        assert list((store/'captures'/'2026-10-19'/source).glob('*.body'))
    later=first+dt.timedelta(hours=1); again=FakeHTTP(later)
    result2=Collector(store,credentials=p,http=again,enabled=True,clock=lambda:later).collect('2026-10-19')
    assert result2['decision']==result['decision'] and not again.calls


def test_partial_halfday_retains_early_sip_receipt(tmp_path):
    p=profile(tmp_path); store=tmp_path/'store'; day='2026-11-27'; early=moment(day,13,20)
    fake=FakeHTTP(early,half=True)
    r=Collector(store,credentials=p,http=fake,enabled=True,clock=lambda:early).collect(day)
    assert r['status']=='NOT_READY' and [x.source for x in fake.calls]==['calendar','alpaca_sip']
    later=moment(day,16,20); fake2=FakeHTTP(later,half=True)
    r=Collector(store,credentials=p,http=fake2,enabled=True,clock=lambda:later).collect(day)
    assert r['decision']['sokrashchennyy'] and r['decision']['execution']=='NO_SEND'
    assert r['decision']['received_at_ms']==int(early.timestamp()*1000)
    assert 'alpaca_sip' not in [x.source for x in fake2.calls]


def test_missing_not_finalized_prematurely_then_terminal(tmp_path):
    p=profile(tmp_path); store=tmp_path/'store'; first=moment(); fake=FakeHTTP(first,empty=True)
    r=Collector(store,credentials=p,http=fake,enabled=True,clock=lambda:first).collect('2026-10-19')
    assert r['status']=='NOT_READY'
    later=moment(hour=22,minute=1); fake2=FakeHTTP(later,empty=True)
    r=Collector(store,credentials=p,http=fake2,enabled=True,clock=lambda:later).collect('2026-10-19')
    assert r['decision']['freshness']=='MISSING' and r['decision']['z'] is None


def test_late_and_delayed_massive_qa_no_row_rewrite(tmp_path):
    p=profile(tmp_path); store=tmp_path/'store'; late=moment(hour=17)
    fake=FakeHTTP(late)
    c=Collector(store,credentials=p,http=fake,enabled=True,clock=lambda:late)
    r=c.collect('2026-10-19'); decision=r['decision']; assert decision['freshness']=='LATE'
    after=moment('2026-10-21'); qahttp=FakeHTTP(after)
    r=Collector(store,credentials=p,http=qahttp,enabled=True,clock=lambda:after).collect('2026-10-19',massive_qa=True,qa_only=True)
    assert r['qa']['status']=='SVERKA_PASS' and r['decision']==decision
    assert [q.source for q in qahttp.calls]==['massive']


def test_errors_sanitized_and_capture_before_rejection(tmp_path):
    class Broken(FakeHTTP):
        def get(self,req):
            if req.source=='calendar': return super().get(req)
            self.calls.append(req)
            return 401,b'{"message":"secret-token?apiKey=fake-secret"}',self.now
    p=profile(tmp_path); now=moment(); store=tmp_path/'store'; fake=Broken(now)
    r=Collector(store,credentials=p,http=fake,enabled=True,clock=lambda:now).collect('2026-10-19')
    assert r['status']=='NOT_READY' and r['errors']
    assert 'fake-secret' not in json.dumps(r) and 'apiKey' not in json.dumps(r)
    assert list((store/'captures'/'2026-10-19'/'alpaca_sip').glob('*.body'))


def test_transport_no_redirect_and_bounded_read(monkeypatch):
    import research_lab.ibit_btc_collector_v1 as module
    calls=[]
    class Response:
        status=302
        def read1(self,n): calls.append(('read',n)); return b''
    class Connection:
        sock=None
        def __init__(self,host,timeout,context): calls.append(('host',host))
        def request(self,method,path,headers): calls.append((method,path))
        def getresponse(self): return Response()
        def close(self): pass
    monkeypatch.setattr(module.http.client,'HTTPSConnection',Connection)
    request=build_request('binance','2026-10-19',{})
    status,body,received=GetOnlyHTTP().get(request)
    assert status==302 and type(received) is dt.datetime
    assert [c[0] for c in calls].count('GET')==1
    assert all(n<=65536 for kind,n in calls if kind=='read')


@pytest.mark.parametrize('kind',['foreign','symlink','credentials_inside','old_session'])
def test_unsafe_inputs_fail_before_network(tmp_path,kind):
    p=profile(tmp_path); now=moment(); fake=FakeHTTP(now); root=tmp_path/'store'; day='2026-10-19'
    if kind=='foreign': root.mkdir(); (root/'foreign').write_bytes(b'keep')
    elif kind=='symlink': root.symlink_to(tmp_path,target_is_directory=True)
    elif kind=='credentials_inside': root.mkdir(); p=root/'key.json'; p.write_text('{}')
    else: day='2025-01-01'
    with pytest.raises((ValueError,SourceError)):
        Collector(root,credentials=p,http=fake,enabled=True,clock=lambda:now).collect(day)
    assert not fake.calls



def test_probe_history_captures_without_historical_decision(tmp_path):
    p=profile(tmp_path); now=moment('2026-10-19'); fake=FakeHTTP(now); store=tmp_path/'store'
    r=Collector(store,credentials=p,http=fake,enabled=True,clock=lambda:now).collect('2026-10-16',probe=True,massive_qa=True)
    assert r['status']=='CAPTURE_ONLY' and r['decision'] is None
    assert r['capture_kind']=='HISTORICAL_RETRIEVAL_NOT_PROSPECTIVE'
    assert not (store/'adapter/decisions.jsonl').exists()
    assert {req.source for req in fake.calls}=={'calendar','alpaca_sip','binance','bybit','massive'}


def test_dotenv_explicit_profile_no_interpolation_and_sip_delay_end(tmp_path):
    p=tmp_path/'observer.env'; p.write_text('ALPACA_API_KEY_ID=fake-id\nALPACA_API_SECRET_KEY=${NOT_EXPANDED}\nALPACA_BASE_URL=https://api.alpaca.markets\n'); p.chmod(0o640)
    early=moment(hour=16,minute=10); fake=FakeHTTP(early)
    Collector(tmp_path/'store',credentials=p,http=fake,enabled=True,clock=lambda:early).collect('2026-10-19')
    assert 'alpaca_sip' not in [r.source for r in fake.calls]
    ready=moment(); later=FakeHTTP(ready)
    Collector(tmp_path/'store',credentials=p,http=later,enabled=True,clock=lambda:ready).collect('2026-10-19')
    request=next(r for r in later.calls if r.source=='alpaca_sip')
    assert request.headers['APCA-API-SECRET-KEY']=='${NOT_EXPANDED}'
    assert request.params['end']==dt.datetime.combine(dt.date(2026,10,19),dt.time(16),NY).isoformat()


def test_cli_default_and_probe_opt_in(tmp_path):
    import subprocess
    import sys
    script=Path(__file__).resolve().parents[1]/'scripts/collect_ibit_btc_data_only_v1.py'
    result=subprocess.run([sys.executable,str(script)],capture_output=True,text=True)
    assert result.returncode==0 and json.loads(result.stdout)['status']=='NO_NETWORK'
    result=subprocess.run([sys.executable,str(script),'--network'],capture_output=True,text=True)
    assert result.returncode==2 and 'fake-secret' not in result.stderr


def test_massive_original_payload_qa_link(tmp_path):
    p=profile(tmp_path); now=moment(); store=tmp_path/'store'; fake=FakeHTTP(now)
    r=Collector(store,credentials=p,http=fake,enabled=True,clock=lambda:now).collect('2026-10-19',massive_qa=True)
    links=list((store/'qa_links').glob('*.json'))
    assert len(links)==1
    link=json.loads(links[0].read_text())
    assert link['adapter_qa_sha']==r['qa']['qa_sha'] and link['row_sha']==r['decision']['row_sha']
    assert len(link['provider_canonical_raw_sha'])==64 and len(link['body_sha'])==64


def test_capture_limits_checked_before_request(tmp_path,monkeypatch):
    import research_lab.ibit_btc_collector_v1 as module
    p=profile(tmp_path); now=moment(); fake=FakeHTTP(now); store=tmp_path/'store'
    monkeypatch.setattr(module,'MAX_STORE_BYTES',1)
    with pytest.raises(SourceError):
        Collector(store,credentials=p,http=fake,enabled=True,clock=lambda:now).collect('2026-10-19')
    assert not fake.calls


def test_transport_hard_body_limit_without_clock_or_redirect(monkeypatch):
    import research_lab.ibit_btc_collector_v1 as module
    events=[]
    monkeypatch.setattr(module,'MAX_BODY',100)
    class Response:
        status=200
        def read1(self,n): events.append(('read',n)); return b'x'*n
    class Connection:
        sock=None
        def __init__(self,host,timeout,context): events.append(('host',host))
        def request(self,method,path,headers): events.append((method,path))
        def getresponse(self): return Response()
        def close(self): events.append(('close',None))
    monkeypatch.setattr(module.http.client,'HTTPSConnection',Connection)
    def clock():
        pytest.fail('oversized incomplete body must not become a valid receipt')
    with pytest.raises(SourceError,match='BODY_LIMIT'):
        GetOnlyHTTP(clock).get(build_request('binance','2026-10-19',{}))
    assert [v for k,v in events if k=='read']==[101]
    assert events[-1][0]=='close'
