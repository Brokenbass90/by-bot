import pytest
from research_lab.research_tiny_intake_v1 import assess_kity, IntakeBlocked


def packet():
    legs = [{'s': 'L'+str(i)} for i in range(5)]
    shorts = [{'s': 'S'+str(i)} for i in range(5)]
    signal = {'d':'2026-10-22', 'long':legs,'short':shorts,'monet_s_priznakom':50}
    c2 = {'schema':'KITY_C2_ACTUAL_SIGNAL_MATCH_V1','d':'2026-10-22',
          'status':'C2_PASS_MATCH_ONLY', 'long':[v['s'] for v in legs],
          'short':[v['s'] for v in shorts], 'features':50}
    positions = [{'s':v['s'], 'side':side,'kolichestvo':10,'cena_vhoda':10,'lot_ok':True}
                 for side, group in [(1,legs),(-1,shorts)] for v in group]
    return signal, c2, {'d':'2026-10-22','pozicii':positions}


def test_parity_not_economic_or_money_pass():
    report = assess_kity(*packet(), dossier_legs=8, active_owner='PUMP4')
    assert report['ready_for_tiny'] is False
    assert report['signal_parity'] == 'C2_PASS_MATCH_ONLY'
    assert 'DOSSIER_LEG_COUNT_DRIFT_8_VS_10' in report['blockers']
    assert 'BYBIT_SINGLE_OWNER_CONFLICT_PUMP4' in report['blockers']
    assert 'BYBIT_ECONOMIC_ADMISSION_CONTRACT_UNRESOLVED' in report['blockers']
    assert report['research_gross_usdt'] == '1000'
    assert report['orders_allowed'] is False


def test_unknown_fee_funding_never_assumed_zero():
    report = assess_kity(*packet(), dossier_legs=10, active_owner='UNKNOWN')
    assert report['costs'] == 'UNKNOWN_FRESH_FEES_FUNDING_SLIPPAGE_REQUIRED'
    assert report['ready_for_tiny'] is False


@pytest.mark.parametrize('bad', ['side', 'duplicate', 'quantity', 'symbols', 'day'])
def test_mismatch_fail_closed(bad):
    signal, c2, entry = packet()
    if bad == 'side': entry['pozicii'][0]['side'] = -1
    if bad == 'duplicate': entry['pozicii'][1] = entry['pozicii'][0]
    if bad == 'quantity': entry['pozicii'][0]['kolichestvo'] = -1
    if bad == 'symbols': c2['long'][0] = 'OTHER'
    if bad == 'day': entry['d'] = '2026-10-15'
    with pytest.raises(IntakeBlocked): assess_kity(signal,c2,entry,dossier_legs=8,active_owner='PUMP4')


def test_metadata_rounding_check_does_not_trust_lot_ok():
    signal,c2,entry=packet()
    signal['instrumenty']={x['s']:{'step':1,'min_qty':1,'min_notional':5} for x in entry['pozicii']}
    entry['pozicii'][0]['kolichestvo']=10.5
    result=assess_kity(signal,c2,entry,dossier_legs=10,active_owner='PUMP4')
    assert 'RESEARCH_STEP_MINIMUM_NOT_PASS' in result['blockers']
    assert result['legs'][0]['metadata_lot_check'] is False
