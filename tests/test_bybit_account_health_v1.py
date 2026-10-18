import pytest
from scripts.bybit_account_health_v1 import assess


def observation():
    return dict(marker=True, inhibitors=True, old_pids=[0, 0],
                owner=dict(ActiveState='active', MainPID='44'),
                heartbeat=dict(schema='kity_micro_owner_heartbeat_v1', pid=44,
                               at_ms=100_000, error=None, mode='ORDERS_OFF',
                               account_lock_inode=123), lock_inode=123)


def test_intentionally_stopped_old_owner_is_not_unresponsive():
    assert assess(observation(), 110_000)['status'] == 'HEALTHY'


def test_stale_new_owner_is_reported_without_restart_authority():
    out = assess(observation(), 200_001)
    assert out['reason'] == 'OWNER_HEARTBEAT_STALE_OR_FUTURE'
    assert out['restart_allowed'] is False


def test_wrong_pid_cannot_make_new_owner_healthy():
    v = observation(); v['heartbeat']['pid'] = 45
    assert assess(v, 110_000)['reason'] == 'OWNER_PID_CONFLICT'


def test_missing_handoff_marker_does_not_fall_back_to_old_restart():
    v = observation(); v['marker'] = False
    assert assess(v, 110_000)['reason'] == 'HANDOFF_CUSTODY_CONFLICT'


def test_competing_old_writer_is_an_actual_failure():
    v = observation(); v['old_pids'] = [51, 0]
    assert assess(v, 110_000)['reason'] == 'COMPETING_OLD_OWNER'


def test_unknown_or_corrupt_new_heartbeat_is_not_zero_or_healthy():
    for field, value in [('at_ms', True), ('at_ms', 110_001), ('pid', True),
                         ('mode', 'UNKNOWN'), ('error', 'SOURCE_DRIFT'),
                         ('account_lock_inode', 124)]:
        v = observation(); v['heartbeat'][field] = value
        assert assess(v, 110_000)['status'] == 'UNHEALTHY'


def test_active_micro_management_has_same_health_rules():
    v = observation(); v['heartbeat']['mode'] = 'EXACT_GO_SCOPED_MANAGEMENT'
    v['heartbeat']['state'] = dict(ownership_conflict=False, held={}, entries={})
    assert assess(v, 110_000)['status'] == 'HEALTHY'


def test_missing_new_owner_never_invokes_old_owner():
    v = observation(); v['owner']['ActiveState'] = 'inactive'
    assert assess(v, 110_000)['reason'] == 'OWNER_NOT_RUNNING'


def active_observation():
    v = observation(); v['heartbeat']['mode'] = 'EXACT_GO_SCOPED_MANAGEMENT'
    v['heartbeat']['state'] = dict(ownership_conflict=False, held={'BTWUSDT': '10'},
        entries={'BTWUSDT': dict(protected='10', stop_id='owned-native')})
    return v


def test_active_owned_native_protection_can_be_healthy():
    assert assess(active_observation(), 110_000)['status'] == 'HEALTHY'


def test_actual_incident_conflict_is_not_hidden_by_a_fresh_process_heartbeat():
    v = active_observation(); v['heartbeat']['state']['ownership_conflict'] = True
    out = assess(v, 110_000)
    assert out['status'] == 'UNHEALTHY' and out['reason'] == 'OWNER_CUSTODY_CONFLICT'
    assert out['orders_allowed'] is False and out['restart_allowed'] is False


@pytest.mark.parametrize('entry', [dict(protected='0', stop_id=None),
    dict(protected='9', stop_id='owned-native'), dict(protected='10', stop_id=None), None])
def test_unconfirmed_native_guard_uses_existing_alert_path_without_money_actions(entry):
    v = active_observation(); v['heartbeat']['state']['entries']['BTWUSDT'] = entry
    out = assess(v, 110_000)
    assert out['reason'] == 'OWNER_NATIVE_PROTECTION_UNCONFIRMED'
    assert out['status'] == 'UNHEALTHY'
    assert not out['orders_allowed'] and not out['restart_allowed']


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-1', True, None])
def test_unknown_or_invalid_active_quantity_is_not_flat_or_healthy(value):
    v = active_observation(); v['heartbeat']['state']['held']['BTWUSDT'] = value
    assert assess(v, 110_000)['reason'] == 'OWNER_EXPOSURE_SOURCE_INCOMPLETE'


def test_active_missing_lifecycle_is_unknown_instead_of_healthy():
    v = observation(); v['heartbeat']['mode'] = 'EXACT_GO_SCOPED_MANAGEMENT'
    assert assess(v, 110_000)['reason'] == 'OWNER_EXPOSURE_SOURCE_INCOMPLETE'


def test_orders_off_with_observed_exposure_is_not_healthy():
    v = active_observation(); v['heartbeat']['mode'] = 'ORDERS_OFF'
    out = assess(v, 110_000)
    assert out['reason'] == 'OWNER_ORDERS_OFF_WITH_EXPOSURE'
    assert not out['orders_allowed'] and not out['restart_allowed']


@pytest.mark.parametrize('mode', ['ORDERS_OFF', 'EXACT_GO_SCOPED_MANAGEMENT'])
@pytest.mark.parametrize('kind', ['entries', 'exits'])
def test_terminal_quantity_without_all_execution_rows_is_unknown_even_if_held_zero(mode, kind):
    v = observation(); v['heartbeat']['mode'] = mode
    v['heartbeat']['state'] = dict(ownership_conflict=False, held={'BTWUSDT': '0'},
        entries={}, exits={})
    v['heartbeat']['state'][kind]['BTWUSDT'] = dict(terminal=True,
        terminal_quantity='10', filled='1', protected='1', stop_id='owned-native')
    assert assess(v, 110_000)['reason'] == 'OWNER_EXECUTIONS_UNCONFIRMED'


@pytest.mark.parametrize('value', ['NaN', None, True, '-1'])
def test_terminal_unknown_execution_quantity_fails_closed(value):
    v = active_observation()
    v['heartbeat']['state']['entries']['BTWUSDT'].update(terminal=True,
        terminal_quantity='10', filled=value)
    assert assess(v, 110_000)['reason'] == 'OWNER_EXPOSURE_SOURCE_INCOMPLETE'


def test_off_terminal_fully_reconciled_flat_history_is_healthy():
    v = observation(); v['heartbeat']['state'] = dict(ownership_conflict=False,
        held={'BTWUSDT': '0'},entries={'BTWUSDT': dict(terminal=True,
        terminal_quantity='10', filled='10')},exits={'BTWUSDT': dict(terminal=True,
        terminal_quantity='10', filled='10')})
    assert assess(v, 110_000)['status'] == 'HEALTHY'
