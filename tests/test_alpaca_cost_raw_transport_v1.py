"""GET-only raw evidence on the existing exact-host client; fake opener only."""
import io
from urllib.error import HTTPError
import pytest
from research_lab.alpaca_dynamic_live_runtime_v1 import DynamicLiveClient


class Response(io.BytesIO):
    status=200


def test_cost_get_keeps_exact_raw_body_timestamps_and_does_not_enable_orders():
    client=DynamicLiveClient('fixture','fixture');calls=[]
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            return Response(b'[ {"id": "raw-not-reserialized"} ]')
    client.opener=Opener()
    result=client.cost_get('/v2/account/activities',dict(after='2026-10-01T00:00:00Z',until='2026-10-03T00:00:00Z',direction='asc',page_size=100))
    assert result['raw']=='[ {"id": "raw-not-reserialized"} ]'
    assert result['started_ms']<=result['received_ms']
    assert calls[0].method=='GET' and calls[0].full_url.startswith('https://api.alpaca.markets/v2/account/activities?')
    assert client.writes_enabled is False and client.write_permit is None


@pytest.mark.parametrize('route,params', [('/v2/orders',{}),('/v2/account/activities',{'activity_types':'FILL'}),
    ('https://example.com/v2/account',{}),('/v2/account',{'secret':'fixture'}),('/v2/account/activities',{'page_size':1000})])
def test_raw_cost_reader_has_no_arbitrary_route_or_filter(route,params):
    client=DynamicLiveClient('fixture','fixture')
    class Refused:
        def open(self,*a,**k):pytest.fail('unsupported cost read reached network')
    client.opener=Refused()
    with pytest.raises(ValueError):client.cost_get(route,params)


def test_raw_cost_http_failure_retains_response_body_without_retry():
    client=DynamicLiveClient('fixture','fixture');calls=[]
    class Opener:
        def open(self,request,timeout):
            calls.append(request)
            raise HTTPError(request.full_url,503,'fixture',{},io.BytesIO(b'{"message":"later"}'))
    client.opener=Opener()
    result=client.cost_get('/v2/account',{})
    assert result['http_status']==503 and result['raw']=='{"message":"later"}' and len(calls)==1


def test_non_utf8_error_body_is_kept_losslessly_before_fail_closed():
    import base64,hashlib
    client=DynamicLiveClient('fixture','fixture');raw=b'\xff\xfe upstream failure'
    class Opener:
        def open(self,request,timeout):
            raise HTTPError(request.full_url,503,'fixture',{},io.BytesIO(raw))
    client.opener=Opener();result=client.cost_get('/v2/account',{})
    assert result['http_status']==503 and result['raw'] is None
    assert base64.b64decode(result['raw_base64'])==raw
    assert result['sha256']==hashlib.sha256(raw).hexdigest()
    from research_lab.alpaca_fee_to_live_closure_v1 import collect_account_cost_source, CostSourceCaptureError
    with pytest.raises(CostSourceCaptureError) as failure:
        collect_account_cost_source(lambda *a:result,account_id='fixture',after='2026-10-01T00:00:00Z',until='2026-10-03T00:00:00Z')
    assert base64.b64decode(failure.value.captures[0]['raw_base64'])==raw
