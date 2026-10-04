"""Closed exchange bars, never elapsed wall time, advance cold quarantine."""
from copy import deepcopy
import json

import pytest

from scripts.collect_att1_fresh_epoch import analyze_quarantine, funding_stress
from research_lab.att1_lifecycle_profile import BROKER_ADMISSION_SYMBOLS

M5 = 300_000
FENCE = 360_000_000


def captures(count, *, gap=None, now=None):
    now = now or FENCE + (count + 1) * M5 + 1000
    out = {}
    for symbol in BROKER_ADMISSION_SYMBOLS:
        rows = [[str(FENCE + n * M5), '10', '11', '9', '10', '1', '10']
                for n in range(count)]
        if gap is not None and symbol == 'LINKUSDT':
            rows.pop(gap)
        # Include a still-open candle; it must never count.
        rows.append([str(now // M5 * M5), '10', '11', '9', '10', '1', '10'])
        out[symbol] = {'retCode': 0, 'time': now,
                       'result': {'category': 'linear', 'symbol': symbol,
                                  'list': list(reversed(rows))}}
    return out, now


def test_95_closed_bars_cannot_mature_by_waiting():
    pages, now = captures(95)
    out = analyze_quarantine(pages, fence_ms=FENCE, observed_ms=now)
    assert out['consecutive_closed_m5'] == 95
    assert out['quarantine_complete_ms'] is None
    assert out['orders_allowed'] is False


def test_96_actual_common_closes_establish_only_quarantine():
    pages, now = captures(96, now=FENCE + 96 * M5 + 1000)
    out = analyze_quarantine(pages, fence_ms=FENCE, observed_ms=now)
    assert out['quarantine_complete_ms'] == FENCE + 96 * M5
    assert len(out['common_bars']) == 96
    assert out['orders_allowed'] is False


def test_one_symbol_gap_restarts_common_count():
    pages, now = captures(100, gap=50, now=FENCE + 100 * M5 + 1000)
    out = analyze_quarantine(pages, fence_ms=FENCE, observed_ms=now)
    assert out['consecutive_closed_m5'] == 49
    assert out['quarantine_complete_ms'] is None


def test_stale_bars_do_not_claim_current_maturity():
    pages, now = captures(96)
    assert analyze_quarantine(pages, fence_ms=FENCE, observed_ms=now)['current'] is False


@pytest.mark.parametrize('fault', ['missing_symbol', 'wrong_symbol', 'duplicate', 'future_server', 'bad_price'])
def test_conflicting_or_incomplete_capture_denies(fault):
    pages, now = captures(96)
    pages = deepcopy(pages)
    if fault == 'missing_symbol': pages.pop('LINKUSDT')
    if fault == 'wrong_symbol': pages['LINKUSDT']['result']['symbol'] = 'BTCUSDT'
    if fault == 'duplicate': pages['LINKUSDT']['result']['list'].append(pages['LINKUSDT']['result']['list'][-1])
    if fault == 'future_server': pages['LINKUSDT']['time'] = now + 1
    if fault == 'bad_price': pages['LINKUSDT']['result']['list'][-1][4] = 'NaN'
    with pytest.raises(ValueError):
        analyze_quarantine(pages, fence_ms=FENCE, observed_ms=now)


def test_funding_is_side_bound_and_includes_phase_event():
    row = {'symbol': 'BTCUSDT', 'fundingInterval': 480,
           'lowerFundingRate': '-0.0075', 'upperFundingRate': '0.0075'}
    out = funding_stress(row, side='SHORT', notional_usdt='5')
    assert out['events_with_phase_reserve'] == 43
    assert out['funding_usdt'] == '129/80'
    assert out['future_ceiling_proven'] is False
    assert out['policy_approved'] is False


@pytest.mark.parametrize('field,value', [('fundingInterval', 0), ('lowerFundingRate', 'NaN'), ('upperFundingRate', '-1')])
def test_invalid_funding_bounds_are_not_zero(field, value):
    row = {'symbol': 'BTCUSDT', 'fundingInterval': 480,
           'lowerFundingRate': '-0.0075', 'upperFundingRate': '0.0075', field: value}
    with pytest.raises(ValueError): funding_stress(row, side='SHORT', notional_usdt='5')


def test_collector_persists_sources_without_route_or_money_authority(tmp_path, monkeypatch):
    import scripts.collect_att1_fresh_epoch as collector
    pages, now = captures(96, now=FENCE + 96 * M5 + 1000)
    # Source-backed availability of the H1 fence, independently of future bars.
    for page in pages.values():
        page['result']['list'].append([str(FENCE - M5), '10', '11', '9', '10', '1', '10'])
    retirement = {'schema_id':'att1_old_retirement_receipt_v1','retirement_verified':True,
                  'retired_at_ms':FENCE-1000,'fence_h1_ms':FENCE,
                  'initial_process_retirement_flag':'1','orders_allowed':False}
    path = tmp_path/'retired.json';path.write_text(json.dumps(retirement))
    monkeypatch.setattr(collector.time, 'time', lambda: now/1000)
    calls = []
    monkeypatch.setattr(collector, 'request_m5', lambda symbol: (calls.append('/v5/market/kline') or pages[symbol]))
    def public(symbol):
        calls.append('/v5/market/instruments-info')
        return {'result':{'list':[{'symbol':symbol,'status':'Trading','fundingInterval':480,
                                  'lowerFundingRate':'-0.0075','upperFundingRate':'0.0075'}]}}
    monkeypatch.setattr(collector, 'request_instrument', public)
    result = collector.collect(path, tmp_path/'observations')
    assert result['status'] == 'QUARANTINE_OBSERVED'
    assert result['actual_handoff_ready'] is False
    assert result['orders_allowed'] is False
    assert result['private_api_calls'] == 0
    assert len(calls) == 16
    assert (tmp_path/'observations'/'observation.json').exists()
    assert len(list((tmp_path/'observations').glob('capture_*.json'))) == 1
    # A different declaration never silently resets the counter or source pin.
    retirement['retired_at_ms'] -= 1;path.write_text(json.dumps(retirement))
    with pytest.raises(ValueError, match='source changed'):
        collector.collect(path, tmp_path/'observations')


def test_m5_transport_is_get_only_and_does_not_weaken_h1_transport(monkeypatch):
    import scripts.collect_att1_fresh_epoch as collector
    from scripts.run_att1_lifecycle_zero_risk import validate_public_request, RunnerViolation
    from urllib.parse import urlparse, parse_qs
    captured = []
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            assert limit == 5_000_001
            if '/instruments-info?' in captured[-1].full_url:
                return b'{"retCode":0,"result":{"category":"linear","list":[{"symbol":"BTCUSDT"}]}}'
            return b'{"retCode":0,"result":{"category":"linear","symbol":"BTCUSDT","list":[]}}'
    class Opener:
        def open(self, request, timeout):
            captured.append(request)
            assert timeout == 10
            return Response()
    monkeypatch.setattr(collector, 'build_opener', lambda *args: Opener(), raising=False)
    collector.request_m5('BTCUSDT')
    request = captured[0]
    url = urlparse(request.full_url)
    assert request.get_method() == 'GET'
    assert url.scheme == 'https' and url.netloc == 'api.bybit.com' and url.path == '/v5/market/kline'
    assert parse_qs(url.query) == {'category':['linear'],'symbol':['BTCUSDT'],'interval':['5'],'limit':['1000']}
    assert not any('bapi' in k.lower() or 'authorization' in k.lower() for k in request.headers)
    with pytest.raises(ValueError): collector.request_m5('HFTUSDT')
    collector.request_instrument('BTCUSDT')
    assert urlparse(captured[-1].full_url).path == '/v5/market/instruments-info'
    assert captured[-1].get_method() == 'GET'
    with pytest.raises(ValueError): collector.request_instrument('HFTUSDT')
    with pytest.raises(RunnerViolation):
        validate_public_request('/v5/market/kline', {'category':'linear','symbol':'BTCUSDT','interval':'5','limit':1000})
