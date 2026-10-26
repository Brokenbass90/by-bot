"""Versioned non-widening native tick mapping, ORDERS_OFF only.

The reference plan and sizing risk basis never change. Source snapshots here
are immutable evidence; only the account adapter authenticates fresh captures.
"""
import copy
from decimal import Decimal as D,ROUND_FLOOR,ROUND_CEILING
from research_lab.alpaca_dynamic_v1 import digest

SCHEMA='PUMP4_NATIVE_STOP_NON_WIDENING_OFF_V1'
def need(ok,why):
    if not ok:raise ValueError('PUMP4_NATIVE_STOP_'+why)
def number(v):
    need(type(v) in (str,int,float),'NUMBER')
    try:n=D(str(v))
    except ArithmeticError as exc:raise ValueError('PUMP4_NATIVE_STOP_NUMBER') from exc
    need(n.is_finite() and n>0,'NUMBER');return n

def native_mapping(plan,instrument,ticker):
    need(plan['plan_sha256']==digest({k:v for k,v in plan.items() if k!='plan_sha256'}),'PLAN_HASH')
    symbol=plan['symbol'];side=plan['side'];need(side in ('short','long'),'SIDE')
    need(instrument['symbol']==ticker['symbol']==symbol and instrument['status']=='Trading'
        and instrument['quoteCoin']=='USDT' and instrument['contractType']=='LinearPerpetual','INSTRUMENT')
    reference=number(plan['stop']);entry=number(plan['entry']);tick=number(instrument['priceFilter']['tickSize'])
    last=number(ticker['lastPrice']);quote=number(ticker['bid1Price'] if side=='short' else ticker['ask1Price'])
    short=side=='short';rule=ROUND_FLOOR if short else ROUND_CEILING
    native=(reference/tick).to_integral_value(rounding=rule)*tick
    need(native>0 and native%tick==0,'INVALID_NATIVE_GEOMETRY')
    need((entry<native<=reference and last<native and quote<native) if short
        else (reference<=native<entry and native<last and native<quote),'INVALID_NATIVE_GEOMETRY')
    limits=instrument['priceFilter']
    if 'minPrice' in limits:need(number(limits['minPrice'])<=native,'MIN_PRICE')
    if 'maxPrice' in limits:need(native<=number(limits['maxPrice']),'MAX_PRICE')
    return dict(schema=SCHEMA,plan_sha256=plan['plan_sha256'],symbol=symbol,side=side,
        reference_stop=str(plan['stop']),reference_entry=str(plan['entry']),tick_size=str(tick),native_stop=str(native),
        rounding='SHORT_FLOOR' if short else 'LONG_CEIL',quantity_basis='UNCHANGED_REFERENCE_RISK_NO_UPSIZE',
        instrument=copy.deepcopy(instrument),instrument_sha256=digest(instrument),
        quote=copy.deepcopy(ticker),quote_sha256=digest(ticker),orders_allowed=False,money_authority=False)

def verify_mapping(plan,tick_size,mapping):
    need(isinstance(mapping,dict) and mapping.get('schema')==SCHEMA,'SCHEMA')
    try:
        need(number(tick_size)==number(mapping['tick_size'])==number(mapping['instrument']['priceFilter']['tickSize']),'TICK_CHANGED')
        need(mapping==native_mapping(plan,mapping['instrument'],mapping['quote']),'MAPPING_CHANGED')
    except (KeyError,TypeError,ArithmeticError) as exc:raise ValueError('PUMP4_NATIVE_STOP_INVALID_MAPPING') from exc
    return mapping
