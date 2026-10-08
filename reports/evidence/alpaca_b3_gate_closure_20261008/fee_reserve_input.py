"""Source-only calculator: no broker/network/order/strategy authority.

Map the reviewed October1 retail fee source into the existing planner's separate
liability reserve. Amounts are conditional account/day reserves, not exact future
fee attribution. Invoke with a fresh pre-plan quantity CEILING under existing caps.
The actual runner/book and broker acceptance are still independently gated.
"""
from decimal import Decimal,ROUND_CEILING
import hashlib,json
from pathlib import Path

def prepare_entry_cost_input(quantity_ceiling,unresolved_liability,contract_path):
    source=Path(contract_path).read_bytes();c=json.loads(source)
    if (c['status']!='APPROVE_WITH_LIMITATIONS' or c['commission_rate']!='0'
        or c['account_id']!='afd9ffea-e99d-4d2a-b64a-f07fb0f295c6'
        or c['regulatory_model']['cat_nms_executed_share_rate']!='0.000003'
        or c['regulatory_model']['fee_schedule_revision']!='2026-10-01'):
        raise ValueError('FEE_SOURCE_NOT_ACCEPTED')
    q=Decimal(str(quantity_ceiling));pending=Decimal(str(unresolved_liability))
    if not q.is_finite() or q<=0 or not pending.is_finite() or pending<0:
        raise ValueError('INVALID_FEE_QUANTITY_OR_LIABILITY')
    cat=(q*Decimal(c['regulatory_model']['cat_nms_executed_share_rate'])).quantize(Decimal('.01'),rounding=ROUND_CEILING)
    return {'fee_rate':'0','liability_reserve_usd':str(pending+cat),
            'unresolved_liability_usd':str(pending),'modeled_entry_cat_reserve_usd':str(cat),
            'entry_qty_ceiling':str(q),'fee_contract_sha256':hashlib.sha256(source).hexdigest(),
            'cash_mapping':'existing DynamicBook uses (cash_usd-liability_reserve_usd)/(1+fee_rate); preserve this deduction in fresh snapshot',
            'fee_assumption':'unchanged retail schedule; one entry execution day; other account fees/liabilities must be separately included, not guessed zero',
            'exit_costs':'separate actual quantity/price/daily aggregation at terminal reconciliation, not zero or a hard future bound',
            'money_authority':False,'orders_allowed':False,'executable_plan':False}
