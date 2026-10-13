"""Owner-approved first-entry envelope; preparation never grants money authority.

Fresh opening plans still use the unchanged planner/compiler/runtime. An exact
separate owner GO binds this complete intent and static custody, not an unknown
future ticker or session. Bounds can reject a fresh plan, never reprice it.
"""
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from pathlib import Path

from research_lab.alpaca_dynamic_v1 import dec, digest, instant, pin, policy_check, positive

SCHEMA = 'ALPACA_DYNAMIC_FIRST_INTENT_V1'


def require(condition, reason):
    if not condition: raise ValueError(reason)


def static_binding_sha256(binding):
    # Only the future exact intake identity varies. All sources, account, book,
    # runtime, native manager, lock, ledger and HALT paths stay owner-pinned.
    return digest({k:v for k,v in binding.items() if k!='intake_sha256'})


def prepare_first_intent(*, policy, binding, ticker, session, ranking_sha256,
        slot_entry_order_id, risk_distance, max_qty, max_notional_usd,
        max_risk_usd, max_limit_price, price_source_sha256, quote_cts_ms, prepared_ms):
    policy_check(policy)
    row = next((r for r in policy['calendar_sessions'] if r['session']==session), None)
    now = instant(prepared_ms); cts = instant(quote_cts_ms)
    require(row is not None and policy['first_window_ms'] <= row['open_ms'] and now < row['open_ms'], 'FIRST_INTENT_SESSION')
    require(0 <= now-cts <= policy['max_snapshot_age_ms'], 'PREPARATION_QUOTE_CTS_REQUIRED')
    require(ticker in policy['universe'] and ticker!='SPY', 'FIRST_INTENT_SYMBOL')
    require(binding['account_id']==policy['account_id'] and binding['endpoint']=='https://api.alpaca.markets'
        and binding['policy_sha256']==digest(policy), 'FIRST_INTENT_ACCOUNT_POLICY')
    slot = next((s for s in policy['inherited_slots'] if s['entry_order_id']==slot_entry_order_id), None)
    require(slot is not None, 'FIRST_INTENT_ACTUAL_OLD_SLOT')
    qty=positive(max_qty); notional=positive(max_notional_usd); risk=positive(max_risk_usd)
    distance=positive(risk_distance); limit=positive(max_limit_price)
    require(qty==qty.quantize(Decimal('.000000001')) and limit==limit.quantize(Decimal('.01'))
        and limit>distance and notional <= min(positive(slot['notional_cap']),
             dec(policy['capital_usd'])*dec(policy['gross'])*Decimal('.60'))
        and risk<=positive(slot['risk_cap']), 'FIRST_INTENT_FROZEN_CAPS')
    # The reference distance is unrounded ranking provenance. Actual stop risk
    # uses the unchanged cent-rounded planner distance, checked below for EVERY
    # fresh plan. Multiplying the maximum quantity by the raw reference here
    # wrongly vetoed NET's admissible quantity; it is not an extra risk limit.
    from scripts import alpaca_protective_exit_manager as manager
    out=dict(schema=SCHEMA,account_id=policy['account_id'],endpoint=binding['endpoint'],
        policy_sha256=digest(policy),static_binding_sha256=static_binding_sha256(binding),
        native_manager_source_sha256=hashlib.sha256(Path(manager.__file__).read_bytes()).hexdigest(),
        symbol=ticker,session=session,open_ms=row['open_ms'],end_ms=row['open_ms']+300000,
        ranking_sha256=pin(ranking_sha256),slot_entry_order_id=slot_entry_order_id,
        reference_risk_distance=str(distance),max_qty=str(qty),max_notional_usd=str(notional),
        max_risk_usd=str(risk),max_limit_price=str(limit),
        limit_rule='unchanged fresh ask-based limit, capped by exact owner-approved price; no upward reprice',
        price_source_sha256=pin(price_source_sha256),quote_cts_ms=cts,prepared_ms=now,
        attempts_allowed=1,carry_to_other_session=False,auto_repeat=False,
        orders_allowed=False,money_authority=False,evidence_kind='INPUT_PROVIDED_PRE_ENTRY_ENVELOPE')
    out['intent_sha256']=digest(out)
    return out


def check_first_intent(intent, binding, intake, policy):
    require(intent['schema']==SCHEMA and intent['intent_sha256']==digest({k:v for k,v in intent.items() if k!='intent_sha256'}),
            'FIRST_INTENT_PIN_CONFLICT')
    rebuilt=prepare_first_intent(policy=policy,binding=binding,ticker=intent['symbol'],session=intent['session'],
        ranking_sha256=intent['ranking_sha256'],slot_entry_order_id=intent['slot_entry_order_id'],
        risk_distance=intent['reference_risk_distance'],max_qty=intent['max_qty'],
        max_notional_usd=intent['max_notional_usd'],max_risk_usd=intent['max_risk_usd'],
        max_limit_price=intent['max_limit_price'],price_source_sha256=intent['price_source_sha256'],
        quote_cts_ms=intent['quote_cts_ms'],prepared_ms=intent['prepared_ms'])
    require(rebuilt==intent, 'FIRST_INTENT_STATIC_BINDING_CONFLICT')
    plan=intake['plan']; payload=intake['entry_payload']
    require(intake['scope']['native_manager_source_sha256']==intent['native_manager_source_sha256'],
            'FIRST_INTENT_NATIVE_MANAGER_CONFLICT')
    require(plan['symbol']==intent['symbol'] and plan['session']==intent['session']
        and plan['ranking_sha256']==intent['ranking_sha256']
        and plan['slot_entry_order_id']==intent['slot_entry_order_id'], 'FIRST_INTENT_PLAN_IDENTITY')
    # Reuse the frozen planner's fill-reference rounding rule, not an early-exit
    # or stop challenger. The actual fill stop still comes from native_handoff.
    expected=(positive(plan['reference_ask'])-positive(intent['reference_risk_distance'])).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    require(expected==positive(plan['stop_price'])
        and positive(plan['risk_distance'])==positive(plan['reference_ask'])-expected,
        'FIRST_INTENT_FROZEN_STOP_DISTANCE')
    q=positive(plan['qty']); limit=positive(payload['limit_price'])
    require(q<=positive(intent['max_qty']) and q*positive(plan['reference_ask'])<=positive(intent['max_notional_usd'])
        and q*positive(plan['risk_distance'])<=positive(intent['max_risk_usd'])
        and limit<=positive(intent['max_limit_price']) and payload['symbol']==intent['symbol']
        and positive(payload['qty'])==q, 'FIRST_INTENT_CAP_EXCEEDED')
    return intent['intent_sha256']


def intent_permit(go, intent, binding, intake, policy):
    check_first_intent(intent,binding,intake,policy)
    expected=dict(schema='ALPACA_DYNAMIC_FIRST_INTENT_OWNER_GO_V1',account_id=intent['account_id'],
        endpoint=intent['endpoint'],intent_sha256=intent['intent_sha256'],
        static_binding_sha256=intent['static_binding_sha256'],session=intent['session'],
        owner_go_text='GO ALPACA_DYNAMIC_FIRST_INTENT_V1 '+intent['intent_sha256'])
    require(go==expected, 'FIRST_INTENT_SEPARATE_EXACT_OWNER_GO_REQUIRED')
    return digest(dict(owner_go=go,intent_sha256=intent['intent_sha256']))
