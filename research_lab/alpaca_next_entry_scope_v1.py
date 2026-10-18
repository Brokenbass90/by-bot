"""One-session bounds for the direct owner's existing Dynamic Monday request.

Preparation and checking grant no authority. Actual arming is a separate HUMAN
personal action. The original exact-intake runtime GO is only a derived machine
compatibility record; the actual human text is retained as its separate source.
"""
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from research_lab.alpaca_dynamic_v1 import digest,positive,policy_check
from research_lab.alpaca_dynamic_first_intent_v1 import static_binding_sha256

APPROVAL_SHA256='f76de24aa713fad07083c89f23c7a2fbf76cfe983113c7d08c3ae89bdf18379d'
POLICY_SHA256='fe72557bd7c7437eda328047e81980ee762ec794ac240494ec47d3de4f6f400d'


def check_scope(scope,policy):
    policy_check(policy)
    if (scope['schema']!='ALPACA_DYNAMIC_NEXT_SESSION_SCOPE_V1'
        or scope['scope_sha256']!=digest({k:v for k,v in scope.items() if k!='scope_sha256'})
        or digest(policy)!=POLICY_SHA256 or scope['policy_sha256']!=POLICY_SHA256
        or hashlib.sha256(scope['owner_approval_text'].encode()).hexdigest()!=APPROVAL_SHA256
        or scope['session']!='2026-10-19' or scope['attempts_allowed']!=1
        or scope['auto_repeat'] is not False or scope['carry_to_other_session'] is not False):
        raise ValueError('NEXT_SESSION_OWNER_SCOPE_CONFLICT')
    slot=next((s for s in policy['inherited_slots'] if s['entry_order_id']==scope['slot_entry_order_id']),None)
    if (slot is None or scope['symbol'] not in policy['universe'] or scope['symbol']=='SPY'
        or positive(scope['max_notional_usd'])>positive(slot['notional_cap'])
        or positive(scope['max_risk_usd'])>positive(slot['risk_cap'])):
        raise ValueError('NEXT_SESSION_FROZEN_SLOT_CAP')
    positive(scope['reference_risk_distance'])
    return scope['scope_sha256']


def check_preview(scope,preview,policy):
    check_scope(scope,policy)
    if preview['status']!='NEXT_ENTRY_PREVIEW_ONLY':raise ValueError('NEXT_ENTRY_PREVIEW_NOT_READY')
    intake=preview['intake'];plan=intake['plan'];binding=preview['binding']
    if (static_binding_sha256(binding)!=scope['static_binding_sha256']
        or plan['session']!=scope['session'] or plan['symbol']!=scope['symbol']
        or plan['ranking_sha256']!=scope['ranking_sha256']
        or plan['slot_entry_order_id']!=scope['slot_entry_order_id']):
        raise ValueError('NEXT_ENTRY_BOUND_IDENTITY')
    reference=positive(plan['reference_ask'])
    expected=(reference-positive(scope['reference_risk_distance'])).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    if (positive(plan['stop_price'])!=expected or positive(plan['risk_distance'])!=reference-expected
        or positive(plan['notional_limit_usd'])>positive(scope['max_notional_usd'])
        or positive(plan['qty'])*reference>positive(scope['max_notional_usd'])
        or positive(plan['qty'])*positive(plan['risk_distance'])>positive(scope['max_risk_usd'])):
        raise ValueError('NEXT_ENTRY_BOUND_CAP_OR_NATIVE_DISTANCE')
    return scope['scope_sha256']


def validate_personal_arm(scope,arm):
    expected=dict(schema='ALPACA_DYNAMIC_PERSONAL_SESSION_ARM_V1',scope_sha256=scope['scope_sha256'],
        owner_approval_text_sha256=APPROVAL_SHA256,personal_owner_start=True,
        session=scope['session'],attempts_allowed=1,auto_repeat=False)
    if arm!=expected:raise ValueError('HUMAN_PERSONAL_SESSION_ARM_REQUIRED')
    return digest(arm)


def compatibility_go(scope,preview,policy,arm):
    check_preview(scope,preview,policy);validate_personal_arm(scope,arm)
    intake=preview['intake'];binding=preview['binding']
    # Do not represent this generated token as a verbatim human instruction.
    return dict(schema='ALPACA_DYNAMIC_EXACT_OWNER_GO_V1',account_id=policy['account_id'],
        endpoint=binding['endpoint'],intake_sha256=intake['intake_sha256'],binding_sha256=digest(binding),
        owner_go_text='GO ALPACA_DYNAMIC_V1 '+intake['intake_sha256'],session=scope['session'])
