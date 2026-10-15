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
    assert assess(v, 110_000)['status'] == 'HEALTHY'


def test_missing_new_owner_never_invokes_old_owner():
    v = observation(); v['owner']['ActiveState'] = 'inactive'
    assert assess(v, 110_000)['reason'] == 'OWNER_NOT_RUNNING'
