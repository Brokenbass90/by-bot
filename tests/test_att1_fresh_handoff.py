"""Cold migration is explicit preparation evidence, never recovered OLD state."""
from copy import deepcopy
import sqlite3

import pytest

from bot import att1_canary_preparation as p
from bot import att1_coordinator_adapter as a
from test_att1_canary_preparation import handoff_inputs
from test_att1_exclusive_reservation import ledger, canary_budget, T, H1, ACCOUNT

M5 = 300_000
NOW = T + 9 * H1 + 40
SHA = 'a' * 64


def api(name, module=p):
    assert hasattr(module, name), 'missing fresh-handoff interface: ' + name
    return getattr(module, name)


def fresh_inputs(now=NOW):
    old = handoff_inputs(now)
    common = {'account': ACCOUNT, 'observed_ms': now, 'source_sha256': SHA}
    return {
        'declaration': {'schema_id': 'att1_fresh_epoch_v1',
            'policy_id': 'COLD_96_CLOSED_M5_V1', 'account': ACCOUNT,
            'base_profile_sha256': p.BASE_PROFILE_SHA,
            'implementation_sha256': p.preparation_implementation_hash(),
            'policy_approval_sha256': SHA, 'legacy_state': 'UNKNOWN',
            'retired_at_ms': T + 20, 'fence_h1_ms': T + H1},
        'retirement_snapshot': {**common, 'retired_at_ms': T + 20,
            'entry_guard_disabled': True, 'config_reload_verified': True,
            'restart_entry_denied': True, 'management_preserved': True},
        'pause_snapshot': old['pause_snapshot'],
        'broker_snapshot': old['broker_snapshot'],
        'old_intent_inventory': old['old_intent_inventory'],
        'closed_bars': {**common, 'complete': True, 'fence_available_ms': T + H1,
            'bars': [{'close_ms': T + H1 + i * M5, 'source_sha256': SHA}
                     for i in range(1, (now - T - H1) // M5 + 1)]},
        'now_ms': now,
    }


def fresh_budget(now=NOW, values=None):
    v = canary_budget(now=now)
    base = p.validate_canary_budget_inputs(v['binding'], v['old_budget_evidence'],
                                         v['cash_evidence'], now_ms=now)
    return api('bind_canary_fresh_handoff')(base, **(values or fresh_inputs(now)))


def ready(con, values=None):
    a.pause_att1_route(con, ACCOUNT, T + 10)
    return api('prepare_att1_fresh_cutover', a)(con, ACCOUNT, **(values or fresh_inputs()))


def prepare(con, now=NOW, values=None):
    v = canary_budget(now=now)
    attach = v['command_binding']
    return p.prepare_new_att1_entry(con, ACCOUNT, profile=attach['profile'],
        intent=attach['intent'], validated_budget=fresh_budget(now, values), now_ms=now)


def test_fresh_path_preserves_unknown_state_and_prepares_orders_off(ledger):
    con, _ = ledger
    route = ready(con)
    assert route['latest_h1_ms'] is None
    assert route['cutover_ms'] == T + 9 * H1
    result = prepare(con)
    assert result['status'] == 'PREPARED_ORDERS_OFF'
    assert result['orders_allowed'] is False
    assert result['commands'][0]['positionIdx'] == 0
    assert result['broker_order_id'] is None


@pytest.mark.parametrize('section,field,value', [
    ('declaration', 'legacy_state', 'RECOVERED'),
    ('declaration', 'policy_approval_sha256', ''),
    ('declaration', 'base_profile_sha256', 'b' * 64),
    ('declaration', 'implementation_sha256', 'b' * 64),
    ('declaration', 'fence_h1_ms', T),
    ('declaration', 'account', 'foreign'),
    ('retirement_snapshot', 'entry_guard_disabled', False),
    ('retirement_snapshot', 'config_reload_verified', False),
    ('retirement_snapshot', 'restart_entry_denied', False),
    ('retirement_snapshot', 'management_preserved', False),
    ('retirement_snapshot', 'retired_at_ms', T + 21),
    ('pause_snapshot', 'observed_ms', NOW - 60_001),
    ('broker_snapshot', 'position_count', 1),
    ('broker_snapshot', 'order_count', 1),
    ('old_intent_inventory', 'unresolved', ['late-fill']),
    ('old_intent_inventory', 'costs_complete', False),
    ('closed_bars', 'complete', False),
    ('closed_bars', 'fence_available_ms', T + H1 - 1),
])
def test_unverified_retirement_identity_cash_or_fence_denies(section, field, value):
    values = fresh_inputs(); values[section][field] = value
    with pytest.raises(a.AdapterViolation):
        api('validate_canary_fresh_handoff')(**values)


def test_damaged_pause_denies_even_with_disabled_entry_guard():
    values = fresh_inputs()
    values['pause_snapshot']['control']['read_error'] = 'damaged'
    with pytest.raises(a.AdapterViolation):
        api('validate_canary_fresh_handoff')(**values)


@pytest.mark.parametrize('change', ['95', 'missing', 'duplicate', 'future', 'stale'])
def test_quarantine_does_not_count_wall_clock_gaps_duplicates_or_future_bars(change):
    values = fresh_inputs(); bars = values['closed_bars']['bars']
    if change == '95': bars.pop(0)
    elif change == 'missing': bars.pop(48)
    elif change == 'duplicate': bars[48] = deepcopy(bars[47])
    elif change == 'future': bars[-1]['close_ms'] += M5
    else: values['now_ms'] += M5
    with pytest.raises(a.AdapterViolation):
        api('validate_canary_fresh_handoff')(**values)


def test_missing_bar_extends_quarantine_until_a_new_complete_run():
    now = NOW + 5 * H1
    values = fresh_inputs(now); values['closed_bars']['bars'].pop(48)
    result = api('validate_canary_fresh_handoff')(**values)
    assert result['minimum_cutover_ms'] == T + 14 * H1
    assert result['quarantine_complete_ms'] == T + 13 * H1 + M5


def test_failed_transition_is_atomic_and_cannot_rewrite_live_or_occupied_route(ledger):
    con, _ = ledger
    values = fresh_inputs(); values['broker_snapshot']['order_count'] = 1
    a.pause_att1_route(con, ACCOUNT, T + 10)
    before = a.read_att1_route(con, ACCOUNT)
    with pytest.raises(a.AdapterViolation):
        api('prepare_att1_fresh_cutover', a)(con, ACCOUNT, **values)
    assert a.read_att1_route(con, ACCOUNT) == before
    con.execute("INSERT INTO att1_decisions(account,family,symbol,side,h1_close_ms,owner,order_link_id,reserved_at_ms) VALUES(?,?,?,?,?,?,?,?)",
                (ACCOUNT,'ATT1','BTCUSDT','SELL',T,'OLD','old-entry',T))
    con.commit()
    with pytest.raises(a.AdapterViolation):
        api('prepare_att1_fresh_cutover', a)(con, ACCOUNT, **fresh_inputs())
    assert a.read_att1_route(con, ACCOUNT) == before


def test_epoch_restart_preserves_declaration_and_crash_recovery(ledger):
    con, path = ledger
    ready(con); first = prepare(con); route = a.read_att1_route(con, ACCOUNT); con.close()
    with sqlite3.connect(path) as restored:
        assert a.read_att1_route(restored, ACCOUNT) == route
        again = prepare(restored)
        assert again['status'] == 'RECOVERY_REQUIRED_LOOKUP_ONLY'
        assert again['commands'] == []
        assert again['order_link_id'] == first['reservation']['order_link_id']


def test_new_epoch_cannot_resume_old_or_accept_changed_epoch(ledger):
    con, _ = ledger; ready(con)
    with pytest.raises(a.AdapterViolation): a.pause_att1_route(con, ACCOUNT, NOW)
    changed = fresh_inputs(); changed['declaration']['policy_approval_sha256'] = 'b' * 64
    with pytest.raises(a.AdapterViolation): prepare(con, values=changed)
    assert con.execute('SELECT COUNT(*) FROM att1_decisions').fetchone()[0] == 0


def test_fresh_route_cannot_bypass_cash_handoff_through_generic_reservation(ledger):
    con, _ = ledger; ready(con)
    with pytest.raises(a.AdapterViolation):
        a.reserve_att1_decision(con, ACCOUNT, owner='NEW', symbol='BTCUSDT',
                               side='Sell', h1_close_ms=T+9*H1, now_ms=NOW)
    assert con.execute('SELECT COUNT(*) FROM att1_decisions').fetchone()[0] == 0


def test_cold_transition_does_not_replace_legacy_missing_watermark_denial():
    values = handoff_inputs(NOW); values['old_watermarks']['complete'] = False
    with pytest.raises(a.AdapterViolation): p.validate_canary_handoff(**values)


def test_epoch_maturity_does_not_move_forward_on_fresh_observation(ledger):
    con, _ = ledger; ready(con)
    result = prepare(con, now=NOW+H1)
    assert result['status'] == 'PREPARED_ORDERS_OFF'


def test_missing_durable_declaration_cannot_downgrade_to_legacy(ledger):
    con, _ = ledger; ready(con); prepare(con)
    con.execute('UPDATE att1_route SET fresh_epoch_json=NULL WHERE account=?', (ACCOUNT,))
    con.commit()
    with pytest.raises(a.AdapterViolation): a.read_att1_route(con, ACCOUNT)


def test_later_old_drain_invalidates_the_sealed_epoch(ledger):
    con, _ = ledger; ready(con)
    values = fresh_inputs(); values['old_intent_inventory']['drained_at_ms'] += 1
    with pytest.raises(a.AdapterViolation): prepare(con, values=values)
