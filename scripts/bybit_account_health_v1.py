#!/usr/bin/env python3
"""Observe the actual Bybit account owner. Never restart, trade or repair.

During a scoped handoff, a dead old heartbeat is expected. The new service,
heartbeat PID, source errors, clock and account-lock inode are checked instead.
After a complete rollback, legacy health is observed without restart authority.
"""
import argparse
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request


def assess(v, now_ms, max_age_ms=90_000):
    result = dict(schema='BYBIT_ACCOUNT_HEALTH_V1', observed_ms=now_ms,
                  status='UNHEALTHY', restart_allowed=False, orders_allowed=False)
    def fail(reason):
        return dict(result, reason=reason)
    try:
        if v['marker'] is not True or v['inhibitors'] is not True:
            return fail('HANDOFF_CUSTODY_CONFLICT')
        if any(pid != 0 for pid in v['old_pids']):
            return fail('COMPETING_OLD_OWNER')
        s, h = v['owner'], v['heartbeat']
        if s['ActiveState'] != 'active' or int(s['MainPID']) <= 0:
            return fail('OWNER_NOT_RUNNING')
        if h['schema'] != 'kity_micro_owner_heartbeat_v1':
            return fail('OWNER_HEARTBEAT_SCHEMA')
        if type(h['pid']) is not int or h['pid'] != int(s['MainPID']):
            return fail('OWNER_PID_CONFLICT')
        if type(h['at_ms']) is not int or not 0 <= now_ms-h['at_ms'] <= max_age_ms:
            return fail('OWNER_HEARTBEAT_STALE_OR_FUTURE')
        if h['error'] is not None:
            return fail('OWNER_REPORTED_ERROR')
        if h['mode'] not in ('ORDERS_OFF', 'EXACT_GO_SCOPED_MANAGEMENT'):
            return fail('OWNER_MODE_UNKNOWN')
        if type(h['account_lock_inode']) is not int or h['account_lock_inode'] != v['lock_inode']:
            return fail('OWNER_LOCK_INODE_CONFLICT')
        if h['mode'] == 'EXACT_GO_SCOPED_MANAGEMENT' or h.get('state') is not None:
            # A running process does not prove custody or native protection.
            # Report the observed uncertainty through the existing alert path;
            # do not invent a grace period, repair state, restart or trade.
            state = h.get('state')
            if not isinstance(state, dict) or type(state.get('ownership_conflict')) is not bool:
                return fail('OWNER_EXPOSURE_SOURCE_INCOMPLETE')
            if state['ownership_conflict']:
                return fail('OWNER_CUSTODY_CONFLICT')
            held, entries = state.get('held'), state.get('entries')
            if not isinstance(held, dict) or not isinstance(entries, dict):
                return fail('OWNER_EXPOSURE_SOURCE_INCOMPLETE')
            for symbol, raw_qty in held.items():
                if not isinstance(raw_qty, str):
                    return fail('OWNER_EXPOSURE_SOURCE_INCOMPLETE')
                try:
                    qty = Decimal(raw_qty)
                except InvalidOperation:
                    return fail('OWNER_EXPOSURE_SOURCE_INCOMPLETE')
                if not qty.is_finite() or qty < 0:
                    return fail('OWNER_EXPOSURE_SOURCE_INCOMPLETE')
                if qty:
                    if h['mode'] == 'ORDERS_OFF':
                        return fail('OWNER_ORDERS_OFF_WITH_EXPOSURE')
                    entry = entries.get(symbol)
                    try:
                        raw_protected = entry.get('protected') if isinstance(entry, dict) else None
                        protected = Decimal(raw_protected) if isinstance(raw_protected, str) else None
                    except (KeyError, TypeError, ValueError, InvalidOperation):
                        protected = None
                    if (protected is None or not protected.is_finite() or protected != qty
                            or not isinstance(entry.get('stop_id'), str) or not entry['stop_id']):
                        return fail('OWNER_NATIVE_PROTECTION_UNCONFIRMED')
            for group in (entries, state.get('exits', {})):
                if not isinstance(group, dict):
                    return fail('OWNER_EXPOSURE_SOURCE_INCOMPLETE')
                for order in group.values():
                    if not isinstance(order, dict):
                        return fail('OWNER_EXPOSURE_SOURCE_INCOMPLETE')
                    if order.get('terminal') is True:
                        quantities = []
                        for key in ('terminal_quantity', 'filled'):
                            raw = order.get(key)
                            try:
                                q = Decimal(raw) if isinstance(raw, str) else None
                            except InvalidOperation:
                                q = None
                            if q is None or not q.is_finite() or q < 0:
                                return fail('OWNER_EXPOSURE_SOURCE_INCOMPLETE')
                            quantities.append(q)
                        if quantities[0] != quantities[1]:
                            return fail('OWNER_EXECUTIONS_UNCONFIRMED')
        return dict(result, status='HEALTHY', reason='CURRENT_OWNER_HEALTHY',
                    owner='KITY_MICRO', pid=h['pid'], age_ms=now_ms-h['at_ms'])
    except (KeyError, TypeError, ValueError, OverflowError):
        return fail('OWNER_HEALTH_SOURCE_INCOMPLETE')


def read_json(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size > 2_000_000:
        raise ValueError('HEALTH_SOURCE_PATH_OR_SIZE')
    return json.loads(p.read_bytes())


def service(name):
    value = subprocess.run(['systemctl', 'show', name, '--property=ActiveState,MainPID'],
                           capture_output=True, text=True, check=True, timeout=3)
    return dict(line.split('=', 1) for line in value.stdout.splitlines() if '=' in line)


def observe(spec):
    marker = Path(spec['inhibit_marker']).is_file()
    guards = [Path(p).is_file() for p in spec['inhibitor_paths']]
    owner = service(spec['owner_unit'])
    old = [service(n) for n in spec['old_units']]
    now = time.time_ns()//1_000_000
    if not marker and not any(guards) and owner['ActiveState'] != 'active' and int(owner['MainPID']) == 0:
        h = read_json(spec['legacy_heartbeat'])
        stamp = h.get('ts')
        healthy = (old[0]['ActiveState'] == 'active' and int(old[0]['MainPID']) > 0
                   and type(stamp) in (int, float) and 0 <= now-stamp*1000 <= spec['max_age_ms'])
        return dict(schema='BYBIT_ACCOUNT_HEALTH_V1', observed_ms=now, owner='LEGACY',
                    status='HEALTHY' if healthy else 'UNHEALTHY',
                    reason='LEGACY_HEALTHY' if healthy else 'LEGACY_NOT_RUNNING_OR_STALE',
                    restart_allowed=False, orders_allowed=False)
    return assess(dict(marker=marker, inhibitors=bool(guards) and all(guards),
                       old_pids=[int(s['MainPID']) for s in old], owner=owner,
                       heartbeat=read_json(spec['owner_heartbeat']),
                       lock_inode=Path(spec['account_lock']).stat().st_ino),
                  time.time_ns()//1_000_000, spec['max_age_ms'])


def save_state(path, value):
    p = Path(path)
    if p.is_symlink():
        raise ValueError('ALERT_STATE_SYMLINK')
    fd, temporary = tempfile.mkstemp(prefix='.health-', dir=p.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, allow_nan=False); f.flush(); os.fsync(f.fileno())
        os.replace(temporary, p)
        d = os.open(p.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(d)
        finally: os.close(d)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def notify(spec, result):
    state = Path(spec['alert_state'])
    prior = read_json(state) if state.exists() else {}
    now = result['observed_ms']
    last = prior.get('last_alert_ms', 0)
    if type(last) is not int or now < last:
        raise ValueError('ALERT_STATE_TIME_UNKNOWN')
    if now-last < spec['alert_cooldown_ms']:
        return 'COOLDOWN'
    from dotenv import dotenv_values
    env = dotenv_values(spec['notification_profile'], interpolate=False)
    token = env.get('TG_TOKEN'); chat = env.get('TG_CHAT_ID') or env.get('TG_CHAT')
    if not token or not chat:
        return 'NOT_CONFIGURED'
    payload = json.dumps(dict(chat_id=chat,
        text='Bybit account owner health: '+result['reason']+'. No watchdog restart or order was attempted.')).encode()
    # Persist the notification attempt before HTTP: uncertainty must not spam.
    save_state(state, dict(last_alert_ms=now, reason=result['reason']))
    request = urllib.request.Request('https://api.telegram.org/bot'+token+'/sendMessage',
                                    data=payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=10) as response:
        if not json.loads(response.read(1_000_000)).get('ok'):
            return 'DELIVERY_UNKNOWN'
    return 'DELIVERED'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--spec', required=True); ap.add_argument('--spec-sha256', required=True)
    ap.add_argument('--no-notify', action='store_true'); args = ap.parse_args(argv)
    raw = Path(args.spec).read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.spec_sha256:
        raise ValueError('HEALTH_CONFIG_PIN_CONFLICT')
    spec = read_json(args.spec)
    with open(spec['observer_lock'], 'a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return 0
        try: result = observe(spec)
        except Exception as exc:
            result = dict(schema='BYBIT_ACCOUNT_HEALTH_V1', observed_ms=time.time_ns()//1_000_000,
                          status='UNHEALTHY', reason='HEALTH_OBSERVATION_FAILED:'+type(exc).__name__,
                          orders_allowed=False, restart_allowed=False)
        if result['status'] != 'HEALTHY' and not args.no_notify:
            try: result['notification'] = notify(spec, result)
            except Exception as exc: result['notification'] = 'UNKNOWN:'+type(exc).__name__
        print(json.dumps(result, allow_nan=False))
        return 0 if result['status'] == 'HEALTHY' else 2


if __name__ == '__main__':
    raise SystemExit(main())
