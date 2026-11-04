#!/usr/bin/env python3
"""Pinned ORDERS_OFF cycle hook. GET only; no wallet, keys, .env or order transport."""
from pathlib import Path
import hashlib,json,runpy,sys
BUNDLE=Path('/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/.private/poly_signal_cycle_20261104/runtime-4e276ab0474dbcfc')
PIN='4e276ab0474dbcfcf80912add06fc6410bf88271cc268c4ffb6d871761509b8e'
if sys.argv[1:]!=['--cycle-once']:
    print(json.dumps(dict(status='NO_NETWORK_ORDERS_OFF',order_posts=0)));raise SystemExit(0)
raw=(BUNDLE/'manifest.json').read_bytes()
if hashlib.sha256(raw).hexdigest()!=PIN:raise RuntimeError('RUNTIME_MANIFEST_DRIFT')
for name,pin in json.loads(raw)['files'].items():
    rel=Path(name)
    if rel.is_absolute() or '..' in rel.parts:raise RuntimeError('RUNTIME_PATH')
    p=BUNDLE/rel
    if any(x.is_symlink() for x in (p,*p.parents)) or hashlib.sha256(p.read_bytes()).hexdigest()!=pin:raise RuntimeError('RUNTIME_SOURCE_DRIFT')
sys.path.insert(0,str(BUNDLE))
entry=BUNDLE/'scripts/measure_polymarket_snapshot_v1.py'
sys.argv=[str(entry),'--cycle-once','--research-root','/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/research_lab','--signal-epoch','E2_20261104','--state-root','/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/.private/poly_signal_cycle_20261104/runtime-state']
runpy.run_path(str(entry),run_name='__main__')
