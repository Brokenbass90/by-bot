"""Descriptive sums of already-closed V1.1 records; no simulation or judge."""
from collections import defaultdict
from decimal import Decimal, localcontext
import gzip
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
RUN = BASE / 'run_v1_1'


def summarize():
    artifacts = json.loads((RUN / 'ARTIFACTS.json').read_bytes())
    result = {}
    with localcontext() as ctx:
        ctx.prec = 50
        for arm in ('RAW_SAFE', 'FOUNDATION', 'BRAIN_DET'):
            def empty():
                return dict(accepted=0, known=0, funding_unknown=0, slot_hours=0,
                            risk_usd_hours=Decimal(0), net_usd_known=Decimal(0))
            groups = {key: defaultdict(empty) for key in ('sleeve', 'symbol', 'side')}
            total = empty()
            info = artifacts['closed_' + arm]; path = RUN / info['path']
            assert hashlib.sha256(path.read_bytes()).hexdigest() == info['compressed_sha256']
            with gzip.open(path, 'rb') as stream:
                for raw in stream:
                    row = json.loads(raw)['data']
                    for group in [total, *(groups[key][row[key]] for key in groups)]:
                        group['accepted'] += 1
                        group['known' if row['status'] == 'KNOWN' else 'funding_unknown'] += 1
                        group['slot_hours'] += row['hours']
                        group['risk_usd_hours'] += Decimal(row['risk_usd']) * row['hours']
                        if row['status'] == 'KNOWN': group['net_usd_known'] += Decimal(row['net_usd'])
            assert total['accepted'] == info['records']
            native = json.loads((RUN / 'TERMINAL.json').read_bytes())['arms'][arm]
            assert abs(total['net_usd_known'] - Decimal(native['net_usd'])) < Decimal('1e-40')
            result[arm] = dict(total=total, by_sleeve=dict(groups['sleeve']),
                              by_symbol=dict(groups['symbol']), by_direction=dict(groups['side']))
    return dict(scope='RECORDED_TERMINALS_DESCRIPTIVE_ONLY', arms=result,
        slot_hours_basis='A3 scheduled release, not broker-measured holding',
        concentration_basis='count, slot-hours and stop-risk-dollar-hours distribution; no new gate',
        bootstrap_interval=None, bootstrap_reason='NO_FROZEN_RESAMPLING_UNIT_BLOCK_SEED_OR_INTERVAL_RULE',
        idle_cash_usd=None, idle_cash_reason='NO_FROZEN_EXECUTION_MARGIN_MODEL',
        additional_evaluator_runs=0, new_decisions=0, orders_allowed=False, money_authority=False,
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


if __name__ == '__main__':
    result = summarize()
    with (BASE / 'RECORDED_TRADE_DIAGNOSTICS.json').open('xb') as file:
        file.write(json.dumps(result, sort_keys=True, indent=2, default=str).encode() + b'\n')
    print(json.dumps({arm: dict(closed=r['total']['accepted'], slot_hours=r['total']['slot_hours'])
        for arm, r in result['arms'].items()}))
