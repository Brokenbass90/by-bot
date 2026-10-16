"""HUMAN-ONLY: restore existing NET maintenance, with no new-entry authority.
Accept one personally restored exact stop, or the exact expired original with
no active order. The existing manager owns re-arm/unwind; this installer never
submits a broker order. Agents may invoke only default or --read-only modes.
"""
import argparse, copy, hashlib, importlib.util, json, os, sqlite3, subprocess, sys, time
from decimal import Decimal
from pathlib import Path
ROOT = Path('/opt/bybot-research/alpaca-dynamic-live-20261013/repairs/oct16-entry-identity-v2')
MANIFEST = '3104af118e3e41b560efce60188c58a8d62e7dfd216b77db5b46b8b2c5015d1f'

def require(condition, reason):
    if not condition:
        raise ValueError(reason)

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def propose_adoption(entry, current, positions, orders, record):
    from research_lab.alpaca_live_readiness_v1 import execution_identity_v1
    from research_lab.alpaca_dynamic_v1 import positive, dec

    def need(condition, reason):
        if not condition:
            raise ValueError(reason)
    need(entry['id'] == '705a1b5b-1d45-4ba1-97cf-9c646033d78d', 'ORIGINAL_ENTRY_SCOPE')
    proof = execution_identity_v1(entry, current)
    need(len(positions) == len(orders) == 1, 'EXACTLY_ONE_RESTORED_STOP_REQUIRED')
    position = positions[0]
    stop = orders[0]
    need(position['symbol'] == 'NET' and position['side'] == 'long' and (positive(position['qty']) == Decimal('0.325167779')), 'POSITION_CHANGED')
    need(positive(position['avg_entry_price']) == Decimal('311.222'), 'ENTRY_CHANGED')
    need((stop['symbol'], stop['side'], stop['type'], stop['status'], stop['time_in_force']) == ('NET', 'sell', 'stop', 'new', 'day'), 'RESTORED_STOP_CONTRACT')
    need(positive(stop['qty']) == positive(position['qty']) and dec(stop.get('filled_qty', '0')) == 0 and (positive(stop['stop_price']) == Decimal('277.69')), 'RESTORED_STOP_SIZE_FLOOR')
    need(stop.get('replaced_by') is None, 'RESTORED_STOP_REPLACED')
    need(positive(record['accepted_stop_floor']) == Decimal('277.69'), 'FLOOR_CHANGED')
    proposal = copy.deepcopy(record)
    proposal.update(accepted_order_id=stop['id'], accepted_order_tif=stop['time_in_force'])
    return (proposal, proof)

def propose_recovery(entry,current,positions,orders,record,previous):
    if orders:
        return propose_adoption(entry,current,positions,orders,record)
    require(previous['id']==record['accepted_order_id'],'ORIGINAL_STOP_IDENTITY')
    require(previous['status']=='expired','ORIGINAL_STOP_NOT_EXPIRED')
    # Validate precisely the original floor/size/ownership, with status changed
    # only in RAM to reuse the same strict scope validator. No order is sent.
    hypothetical={**previous,'status':'new'}
    _,proof=propose_adoption(entry,current,positions,[hypothetical],record)
    return copy.deepcopy(record),proof

def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--owner-bind-and-activate', action='store_true')
    p.add_argument('--read-only', action='store_true')
    a = p.parse_args(argv)
    if not a.owner_bind_and_activate and (not a.read_only):
        print(json.dumps(dict(status='ORDERS_OFF_OWNER_EXECUTION_REQUIRED', broker_requests=0)))
        return 0
    require(sha(ROOT / 'manifest.json') == MANIFEST, 'REPAIR_MANIFEST_DRIFT')
    manifest = json.loads((ROOT / 'manifest.json').read_bytes())
    for name, pin in manifest['files'].items():
        require(sha(ROOT / name) == pin, 'REPAIR_SOURCE_DRIFT:' + name)
    original_unit = Path('/etc/systemd/system/alpaca-oct15-owned-manager.service')
    require(sha(original_unit) == manifest['old_unit_sha256'], 'MANAGER_UNIT_ALREADY_CHANGED_NO_REPLAY')
    require(sha(manifest['old_spec']) == manifest['old_spec_sha256'], 'ORIGINAL_SPEC_DRIFT')
    s = importlib.util.spec_from_file_location('repair_control', ROOT / 'control-v1.py')
    control = importlib.util.module_from_spec(s)
    s.loader.exec_module(control)
    spec = control.load_spec(ROOT / 'spec.json')
    from research_lab import alpaca_dynamic_live_runtime_v1 as runtime
    from scripts.run_alpaca_dynamic_live_v1 import load_client
    b = runtime.read_json(str(Path(spec['session_dir']) / 'binding.json'))
    client = load_client(spec['live_profile'], b, apply=False)
    from contextlib import nullcontext
    with runtime.account_lock(b) if a.owner_bind_and_activate else nullcontext():
        halt = Path(b['halt_path'])
        require(halt.is_file(), 'ENTRY_HALT_REQUIRED')
        ledger = Path(b['ledger_path'])
        before = ledger.read_bytes()
        state = json.loads(before)
        require(set(state) == {'NET'}, 'UNEXPECTED_NATIVE_OWNERSHIP')
        record = state['NET']
        require(Decimal(str(record['accepted_stop_floor'])) == Decimal('277.69'), 'FLOOR_CHANGED')
        with sqlite3.connect((Path(b['runtime']) / 'live.sqlite').as_uri() + '?mode=ro', uri=True) as db:
            items = [json.loads(r[0]) for r in db.execute('SELECT payload FROM intents')]
        require(len(items) == 1 and items[0]['phase'] == 'PROTECTED', 'OWNED_INTENT_CONFLICT')
        item = items[0]
        entry = client.get_order(item['entry']['id'])
        positions = client.list_positions()
        orders = client.list_orders(status='open', limit=500)
        previous=client.get_order(record['accepted_order_id'])
        proposal, proof = propose_recovery(item['entry'], entry, positions, orders, record,previous)
        stop = orders[0] if orders else previous
        copied = copy.deepcopy(item)
        runtime.owned_snapshot(client, copied, proposal, observation_ms=lambda: time.time_ns() // 1000000)
        if a.read_only:
            print(json.dumps(dict(status='OWNED_STOP_RECOVERY_READONLY_READY', recovery='BIND_PERSONALLY_RESTORED_STOP' if orders else 'ORIGINAL_EXPIRED_STOP_REARM', stop_order_id=stop['id'], stop_price=stop['stop_price'], qty=stop['qty'], broker_writes=0, service_changes=0, native_writes=0)))
            return 0
        claim = ROOT / 'owner-activation-claim.json'
        fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 384)
        with os.fdopen(fd, 'w') as f:
            json.dump(dict(claimed_ms=time.time_ns() // 1000000, owner_only=True, stop_order_id=stop['id']), f)
            f.flush()
            os.fsync(f.fileno())
        stamp = time.time_ns() // 1000000
        receipt = dict(schema='OWNER_RESTORED_NET_STOP_BINDING_V1', at_ms=stamp, entry_order_id=entry['id'], stop=stop, entry_identity=proof, old_ledger_sha256=hashlib.sha256(before).hexdigest(), new_unit_sha256=manifest['new_unit_sha256'], stop_floor_unchanged=True, quantity_unchanged=True, new_entry_authority=False)
        receipt_path = ROOT / ('owner-restored-stop-' + str(stamp) + '.json')
        raw = (json.dumps(receipt, sort_keys=True) + '\n').encode()
        fd = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 384)
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        require(ledger.read_bytes() == before, 'LEDGER_CHANGED_DURING_BIND')
        if orders:
            proposal['owner_restored_stop_receipt_sha256'] = hashlib.sha256(raw).hexdigest()
            runtime.native._atomic_write_json(ledger, {**state, 'NET': proposal})
        require(sha(original_unit) == manifest['old_unit_sha256'], 'MANAGER_UNIT_RACE')
        unit = (ROOT / 'manager.service.proposed').read_bytes()
        require(hashlib.sha256(unit).hexdigest() == manifest['new_unit_sha256'], 'REPAIR_SOURCE_CONFLICT')
        temp = original_unit.with_name(original_unit.name + '.owner-repair.tmp')
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 420)
        with os.fdopen(fd, 'wb') as f:
            f.write(unit)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, original_unit)
        fd = os.open(original_unit.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'start', 'alpaca-oct15-owned-manager.service'], check=True)
    positions=client.list_positions();orders=client.list_orders(status='open',limit=500)
    if len(positions)==len(orders)==1:
        current_state=runtime.read_json(str(ledger))
        propose_adoption(item['entry'],client.get_order(item['entry']['id']),positions,orders,current_state['NET'])
        require(orders[0]['id']==current_state['NET']['accepted_order_id'],'FINAL_NATIVE_STOP_BINDING')
        print(json.dumps(dict(status='OWNER_REPAIR_LIVE_PROTECTED',stop_order_id=orders[0]['id'],stop_price=orders[0]['stop_price'],qty=orders[0]['qty'],receipt=str(receipt_path),entry_halt_preserved=halt.is_file())))
        return 0
    print(json.dumps(dict(status='OWNER_REPAIR_NEEDS_INDEPENDENT_READBACK',positions=len(positions),open_orders=len(orders),receipt=str(receipt_path),entry_halt_preserved=halt.is_file())))
    return 2
if __name__ == '__main__':
    raise SystemExit(main())
