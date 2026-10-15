"""Execution geometry only; no strategy outcomes or credentials."""
from decimal import Decimal as D
import pytest

from research_lab.kity_execution_micro_v1 import (
    numeric, sizing_floor, basket_geometry, first_target_within_rounding,
    common_source_clock,
)


def row(symbol, quantum, minimum='1', price='1'):
    return dict(symbol=symbol, side='Buy', price=D(price), bid=D(price),
                step=D(quantum), minimum=D(minimum), min_notional=D('1'), maximum=D('100000'))


@pytest.mark.parametrize('value', [True, False, None, 'NaN', 'Infinity', '-1', '0'])
def test_invalid_positive_number_rejected(value):
    with pytest.raises(ValueError):
        numeric(value)


def test_common_floor_never_truncates_a_leg_below_minimum():
    rows = [row('coarse', '10', '10', '2'), row('fine', '.1', '.1', '3')]
    target = sizing_floor(rows)
    assert target == D('20')
    legs = basket_geometry(rows, target)
    assert [l['quantity'] for l in legs] == ['10', '6.6']
    assert all(D(l['entry_reference_notional']) >= 1 for l in legs)


def test_string_source_numbers_and_duplicate_symbols():
    r = {k: str(v) for k, v in row('s', '1').items()}
    assert sizing_floor([r]) == 1
    assert basket_geometry([r], '2')[0]['quantity'] == '2'
    with pytest.raises(ValueError, match='DUPLICATE'):
        sizing_floor([r, r])


def test_no_arbitrary_target_or_silent_quantity_increase():
    with pytest.raises(ValueError, match='MINIMUM'):
        basket_geometry([row('coarse', '10', '10', '2')], D('19.99'))


def test_maximum_market_quantity_is_enforced():
    r = row('s', '1'); r['maximum'] = D('5')
    with pytest.raises(ValueError, match='MAXIMUM'):
        basket_geometry([r], D('6'))


@pytest.mark.parametrize('steps', [(2, 3), (7, 10), (3, 11), (5, 8)])
@pytest.mark.parametrize('eps', ['.05', '.1', '.2'])
def test_frontier_matches_exhaustive_discrete_breakpoint_search(steps, eps):
    rows = [row(str(i), str(step), str(step)) for i, step in enumerate(steps)]
    e = D(eps)
    floor = sizing_floor(rows)
    candidates = sorted({D(k * step) for step in steps for k in range(1, 500) if k * step >= floor})
    expected = next(t for t in candidates if all(
        (t - (t // D(step)) * D(step)) <= e * t for step in steps))
    assert first_target_within_rounding(rows, e) == expected


def test_rounding_cannot_be_zero_negative_or_at_least_one():
    for e in [D('0'), D('-1'), D('1'), D('NaN')]:
        with pytest.raises(ValueError):
            first_target_within_rounding([row('s', '1')], e)


def cap(request=900, received=1000, server=960, cts=950):
    return dict(request_ms=request, receive_ms=received,
                body=dict(time=server, result=dict(cts=cts)))


def test_common_clock_uses_engine_cts_and_offset_upper_bound():
    got = common_source_clock([cap()], 1100)
    assert got['server_offset_interval_ms'] == [-40, 60]
    assert got['max_engine_age_upper_ms'] == 210
    assert got['status'] == 'OBSERVED_COMMON_2S_PASS'


def test_missing_engine_cts_is_unknown_not_response_timestamp():
    c = cap(); del c['body']['result']['cts']
    assert common_source_clock([c], 1100)['status'] == 'SOURCE_UNKNOWN'


def test_whole_group_stale_if_one_book_stale():
    assert common_source_clock([cap(), cap(cts=1)], 3000)['status'] == 'COMMON_BASKET_STALE'


def test_future_engine_clock_is_conflict():
    assert common_source_clock([cap(cts=2000)], 1100)['status'] == 'SOURCE_CLOCK_CONFLICT'


def test_clock_observation_cannot_precede_http_completion():
    assert common_source_clock([cap()], 999)['status'] == 'SOURCE_CLOCK_CONFLICT'
