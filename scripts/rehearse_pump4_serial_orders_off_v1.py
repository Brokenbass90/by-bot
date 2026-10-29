#!/usr/bin/env python3
"""Local fictional-account acceptance only; never installs or selects a runner."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tests'))

from test_pump4_serial_orders_off_v1 import setup_case, full_model_cycle
from test_pump4_bybit_sources_v1 import NOW, H
from research_lab.pump4_serial_orders_off_v1 import Pump4SerialOrdersOff
from research_lab.kity_micro_physical_owner_v1 import publish


def run(destination):
    owner_pin = 'f47b8471017d38c40e88476c757f97da89594eb3034aeb0c9a9b1663c8128baf'
    if hashlib.sha256((ROOT/'research_lab/pump4_account_owner_v1.py').read_bytes()).hexdigest() != owner_pin:
        raise ValueError('V1_OWNER_SOURCE_DRIFT')
    destination = Path(destination).absolute()
    if destination.exists():
        raise ValueError('CREATE_EXCLUSIVE_REHEARSAL_DESTINATION_REQUIRED')
    if any(p.is_symlink() for p in (destination, *destination.parents)):
        raise ValueError('REHEARSAL_SYMLINK_FORBIDDEN')
    destination.mkdir(parents=True, mode=0o700)
    o, exchange, clock, lease, scope = setup_case(destination)
    try:
        first = full_model_cycle((o, exchange, clock, lease, scope), NOW)
        o = Pump4SerialOrdersOff(scope, lease=lease, clock=lambda: clock[0])
        second = full_model_cycle((o, exchange, clock, lease, scope), NOW+H)
        requests = list(exchange.state['submitted_links'])
        assert len(requests) == len(set(requests)) == 6
        assert first['completed_model_cycles'] == 1 and second['completed_model_cycles'] == 2
        assert second['active_ordinal'] is None and second['cost_finality_proven'] is False
        sources = ['research_lab/pump4_serial_orders_off_v1.py',
                   'research_lab/pump4_account_owner_v1.py',
                   'research_lab/pump4_execution_lifecycle_v1.py',
                   'tests/test_pump4_serial_orders_off_v1.py',
                   'tests/test_pump4_account_owner_v1.py',
                   'scripts/rehearse_pump4_serial_orders_off_v1.py',
                   'scripts/rehearse_pump4_bybit_v1.py']
        receipt = dict(schema='PUMP4_SERIAL_REHEARSAL_RECEIPT_V1',
            status='TWO_MODEL_LIFECYCLES_PASS_NOT_LIVE_READY',
            scope_sha256=o.scope_sha256, completed_model_cycles=2,
            unique_model_requests=6, shared_fictional_exchange=True,
            original_fictional_lease_inode=lease.inode,
            coordinator_restarted_between_cycles=True,
            current_v1_code_modified=False, real_broker_requests=0,
            real_broker_writes=0, actual_execution_proven=False,
            actual_source_acceptance=False, live_entry_ready=False,
            model_fee_reserve_usdt=second['pending_fee_reserve_usdt'],
            cost_finality_proven=False, orders_allowed=False, money_authority=False,
            source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources})
        publish(destination/'receipt.json', receipt)
        return receipt
    finally:
        lease.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.destination), sort_keys=True))


if __name__ == '__main__':
    main()
