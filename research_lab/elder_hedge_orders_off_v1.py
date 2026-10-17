"""Frozen ELDER_CRASH_HEDGE_V1 source adapter. No broker or money authority.

Decision-time geometry is required from the original warm ETS2S producer.
Terminal R/rr/stop fields are never used to reconstruct an earlier decision.
Standalone Elder remains KILL. All outputs are SHADOW preparation evidence.
"""
import copy
import hashlib
import json
import re
import sqlite3
import os
from decimal import Decimal as D, ROUND_FLOOR, ROUND_CEILING
from pathlib import Path

from bot.kity_m3_orders_off import digest
from research_lab.elder_hedge_frozen_fill_v1 import ispolnenie

H = 3600000
STRATEGY = 'ELDER_CRASH_HEDGE_V1'
MAX_LEV = D('100')
CONTRACT_SHA256='a25e4af2239cfba738b1f9c88f522060fdca810efd97cbff856f85af3fea3a28'
HEX = re.compile(r'[0-9a-f]{64}\Z')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, D)):
        raise ValueError('INVALID_DECISION_NUMBER')
    v = D(str(value))
    if not v.is_finite():
        raise ValueError('INVALID_DECISION_NUMBER')
    return v


def number(value, zero=False):
    v=finite(value)
    if v<0 or (not zero and not v):raise ValueError('INVALID_DECISION_NUMBER')
    return v


def stamp(value):
    if type(value) is not int or value <= 0:
        raise ValueError('INVALID_CAUSAL_CLOCK')
    return value


def pin(value):
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise ValueError('SOURCE_PIN_REQUIRED')
    return value


def text(v):
    return format(v, 'f')


def control_geometry(row):
    """V1.1 first-record geom; rounded diagnostics never replace raw geometry."""
    g=row.get('geom')
    required={'v','ref_close','e_ref','raw_sl','raw_tps','stop_x','sl_w','stop_dolya',
              'rr1','rr2','f1','max_lev','bar_ts_signal','bar_ts_eref'}
    if not isinstance(g,dict) or not required<=set(g):return None
    if (type(g['v']) is not int or g['v']!=1 or stamp(g['bar_ts_signal'])!=row['ts']
            or stamp(g['bar_ts_eref'])!=row['ts']+H or g['bar_ts_eref']>row['zapisano']):
        raise ValueError('FIRST_RECORD_GEOMETRY_CLOCK_OR_VERSION')
    if row.get('vovremya') is not True:raise ValueError('FIRST_RECORD_NOT_OPERATIONALLY_TIMELY')
    ref,anchor,raw_stop=(number(g[k]) for k in ('ref_close','e_ref','raw_sl'))
    if number(g['stop_x'])!=4 or number(g['max_lev'])!=MAX_LEV or number(g['f1'])!=D('.55'):
        raise ValueError('FROZEN_CONTROL_GEOMETRY_PARAMETERS')
    if not isinstance(g['raw_tps'],list):raise ValueError('GEOMETRY_TARGETS_SCHEMA')
    tps=[number(v) for v in g['raw_tps']]
    distance=abs(raw_stop-anchor)*4
    if not distance:raise ValueError('GEOMETRY_ZERO_RISK')
    sp=distance/anchor
    k=[abs(tps[i]-anchor)/distance if i<len(tps) else D('999') for i in range(2)]
    if (abs(finite(g['sl_w'])-(anchor+(raw_stop-anchor)*4))>D('1e-9')
            or abs(number(g['stop_dolya'])-sp)>D('.000000500001')
            or any(abs(number(g['rr'+str(i+1)],zero=True)-k[i])>D('.000500001') for i in range(2))):
        raise ValueError('FIRST_RECORD_GEOMETRY_DIAGNOSTIC_CONFLICT')
    return ref,anchor,sp,k


def control_levels(fill,sp,k,tick):
    risk=fill*sp
    stop=((fill+risk)/tick).to_integral_value(rounding=ROUND_FLOOR)*tick
    if stop<=fill:raise ValueError('INSTRUMENT_TICK_CANNOT_PROTECT_CONTROL_STOP')
    targets=[((fill-r* risk)/tick).to_integral_value(rounding=ROUND_FLOOR)*tick for r in k]
    return stop,[text(v) if v>0 else None for v in targets],fill+risk


def bind_actual_fill(intent,*,fill,filled_quantity):
    """Pure post-fill level/risk receipt, no replace/send or risk expansion."""
    fill,qty=number(fill),number(filled_quantity)
    if (intent.get('source_contract')!='ELDER_CRASH_HEDGE_V1_1'
            or fill<number(intent['limit_price']) or qty>number(intent['quantity'])):
        raise ValueError('ACTUAL_SHORT_FILL_IDENTITY_OR_QUANTITY')
    stop,targets,unrounded=control_levels(fill,number(intent['stop_fraction']),
        [number(intent['source_k1'],zero=True),number(intent['source_k2'],zero=True)],number(intent['tick_size']))
    risk=qty*(stop-fill)
    return dict(status='ELDER_ACTUAL_FILL_LEVELS_ORDERS_OFF',intent_sha256=intent['intent_sha256'],
        actual_fill=text(fill),filled_quantity=text(qty),stop_price=text(stop),targets=targets,
        control_stop_unrounded=text(unrounded),risk_usdt=text(risk),orders_allowed=False,
        risk_bound_status='WITHIN_BOUND' if risk<=number(intent['per_trade_risk_budget_usdt'])
                          else 'FILL_RISK_REQUIRES_SCOPED_REDUCTION')


def compile_intent(raw, *, source_ref, context, risk, instrument, now_ms):
    stamp(now_ms)
    if not isinstance(raw, bytes) or not raw or len(raw) > 131072 or not source_ref:
        raise ValueError('EXACT_FIRST_RAW_RECORD_REQUIRED')
    row = json.loads(raw)
    ts, available = stamp(row['ts']), stamp(row['zapisano'])
    if (ts % H or row['side'] != 'short' or not ts + H <= available <= now_ms
            or now_ms - ts > 6 * H or available - ts > 6 * H):
        raise ValueError('NONCAUSAL_OR_NONSHORT_ELDER_SOURCE')
    symbol = row['sym']
    if not isinstance(symbol, str) or not re.fullmatch(r'[A-Z0-9]+USDT', symbol):
        raise ValueError('ELDER_SYMBOL_SCHEMA')
    if (context.get('signal_bar_open_ms') != ts
            or not stamp(context['observed_ms']) <= ts + H
            or not context['observed_ms'] <= stamp(context['available_ms']) <= now_ms):
        raise ValueError('REGIME_ASOF_OR_AVAILABILITY_CONFLICT')
    pin(context['source_sha256'])
    regime = context.get('rezhim_v1')
    if regime not in {'BULL_TREND', 'BEAR_TREND', 'NEUTRAL', 'UNKNOWN'}:
        raise ValueError('EXPLICIT_REGIME_OR_UNKNOWN_REQUIRED')
    opp_id = hashlib.sha256(f'{STRATEGY}|crash_hedge|V1|{symbol}|-1|{ts}'.encode()).hexdigest()[:32]
    opportunity = dict(schema='OpportunityRecord V2', opp_id=opp_id, source_ref=str(source_ref),
        source_sha256=sha(raw), t_observation_ms=ts + H, t_available_ms=available,
        t_decision_ms=now_ms, sleeve=STRATEGY, mechanism='crash_hedge', version='V1',
        symbol=symbol, side=-1, horizon_ms=336 * H, context=copy.deepcopy(context), features={},
        exp_gross_bps='UNKNOWN', cost_fee_bps='UNKNOWN', cost_spread_bps='UNKNOWN',
        cost_slip_bps='UNKNOWN', cost_funding_bps='UNKNOWN', exp_net_bps='UNKNOWN',
        uncertainty_bps='UNKNOWN', prior_ref='ELDER_CRASH_HEDGE_V1_KONTRAKT_2026_10_16.md',
        prior_status='DEV_PASS_NOT_MONEY_GO', execution_owner_id='UNKNOWN')
    result = dict(schema='ELDER_HEDGE_ORDERS_OFF_V1', opportunity_id=opp_id, opportunity=opportunity,
        source_sha256=sha(raw), signal_bar_open_ms=ts, signal_available_ms=available,
        decided_ms=now_ms, detection_delay_ms=now_ms-ts, detection_clock_basis='ETS2S_SIGNAL_BAR_OPEN',
        expires_ms=ts+7*H, max_hold_ms=336*H, symbol=symbol, side='Sell', mode='SHADOW',
        orders_allowed=False, owner_money_go=False, execution_owner_id='UNKNOWN',
        strategy=STRATEGY, research_evidence_eligible=False, counts_toward_C1_C2_C3=False)
    if regime == 'BULL_TREND':
        return dict(result, status='HEDGE_OFF_BULL', reason='NO_NEW_ENTRY_EXISTING_MANAGEMENT_UNCHANGED')
    geometry=control_geometry(row)
    if geometry is None:
        return dict(result, status='BLOCKED_SOURCE_DECISION_GEOMETRY',
                    reason='FIRST_RECORD_LACKS_CAUSAL_STOP_TARGETS_NO_TERMINAL_BACKFILL')
    ref,anchor,sp,k=geometry
    if instrument.get('symbol') != symbol:
        raise ValueError('INSTRUMENT_SYMBOL_CONFLICT')
    pin(instrument['source_sha256'])
    tick, step = number(instrument['tickSize']), number(instrument['qtyStep'])
    limit = (ref * D('1.002') / tick).to_integral_value(rounding=ROUND_CEILING) * tick
    stop,targets,control_stop=control_levels(limit,sp,k,tick)
    distance = stop-limit
    leverage = 1/sp
    if leverage > MAX_LEV:
        return dict(result, status='BLOCKED_RISK_INFEASIBLE_STOP_LEV')
    pin(risk['source_sha256'])
    if not stamp(risk['available_ms']) <= now_ms < stamp(risk['valid_until_ms']):
        raise ValueError('RISK_SNAPSHOT_AVAILABILITY_CONFLICT')
    portfolio, budget, used = (number(risk[k], zero=True) for k in (
        'portfolio_risk_budget_usdt', 'sleeve_risk_budget_usdt', 'used_sleeve_risk_usdt'))
    symbols = risk['open_symbols']
    if not isinstance(symbols, list) or len(symbols) != len(set(symbols)):
        raise ValueError('RISK_SYMBOL_SNAPSHOT_CONFLICT')
    if budget > portfolio/3:
        return dict(result, status='BLOCKED_RISK_SLEEVE_CAP')
    per_trade = budget/6
    if symbol in symbols or len(symbols) >= 6 or per_trade <= 0 or used+per_trade > budget:
        return dict(result, status='BLOCKED_RISK_CAPACITY_NO_EVICTION')
    qty = (per_trade/distance/step).to_integral_value(rounding=ROUND_FLOOR)*step
    if (qty < number(instrument['minOrderQty']) or qty > number(instrument['maxOrderQty'])
            or qty*limit < number(instrument['minNotionalValue'])):
        return dict(result, status='BLOCKED_RISK_MINIMUM_LOT')
    # Reference levels use the proposed limit. Actual fills MUST be rebound
    # with bind_actual_fill; better Sell fills can increase monetary stop risk.
    result.update(status='ELDER_HEDGE_INTENT_ORDERS_OFF', limit_price=text(limit), stop_price=text(stop),
        quantity=text(qty), risk_usdt=text(qty*distance), per_trade_risk_budget_usdt=text(per_trade),
        sleeve_risk_budget_usdt=text(budget), risk_source_sha256=risk['source_sha256'],
        instrument_sha256=instrument['source_sha256'], targets=targets, target_fraction_1='0.55',
        source_k1=text(k[0]), source_k2=text(k[1]), leverage=text(leverage),
        native_guard=dict(side='Buy', stopLoss=text(stop), qty=text(qty), reduceOnly=True,
            slOrderType='Market', slTriggerBy='LastPrice', tpslMode='Full'),
        entry_template=dict(category='linear',symbol=symbol,side='Sell',orderType='Limit',
            timeInForce='GTC',price=text(limit),qty=text(qty),positionIdx=0,reduceOnly=False,
            orderLinkId='EHG1-'+opp_id[:20]+'-E',stopLoss=text(stop),
            slOrderType='Market',slTriggerBy='LastPrice',tpslMode='Full'),
        control_reference_stop=text(control_stop),stop_fraction=text(sp),tick_size=text(tick),
        source_contract='ELDER_CRASH_HEDGE_V1_1',contract_sha256=CONTRACT_SHA256,fill_binding_required=True,
        control_stop_anchor_reconciled=True,native_stop_rounding='FLOOR_NOT_FARTHER',
        money_readiness='ORDERS_OFF_PROSPECTIVE_GATES_AND_OWNER_GO_REQUIRED',
        control_source_ref_close=text(ref))
    result['intent_sha256'] = digest(result)
    return result


def shadow_entry(intent, bars, *, now_ms):
    stamp(now_ms)
    if intent.get('status') != 'ELDER_HEDGE_INTENT_ORDERS_OFF':
        raise ValueError('ELDER_INTENT_REQUIRED')
    ts = intent['signal_bar_open_ms']
    closed = []
    for n, bar in enumerate(bars[:7]):
        if len(bar) != 6 or type(bar[0]) is not int or bar[0] != ts+n*H:
            raise ValueError('CANONICAL_CONTIGUOUS_H1_REQUIRED')
        o,h,l,c = (number(v) for v in bar[1:5])
        if not l <= min(o,c) <= max(o,c) <= h:
            raise ValueError('H1_OHLC_CONFLICT')
        if bar[0]+H <= now_ms:
            closed.append(bar)
    if not closed:
        return dict(status='PENDING_CLOSED_BARS', orders_allowed=False)
    if number(closed[0][4]) != number(intent['control_source_ref_close']):
        raise ValueError('H1_SIGNAL_REFERENCE_CONFLICT')
    execution = ispolnenie(closed,0,True,.002,6)
    if execution is None:
        return dict(status='PENDING_CLOSED_BARS', orders_allowed=False)
    if execution[0] == 'net':
        return dict(status='NO_FILL', reference_only=True, broker_fill_proven=False, orders_allowed=False)
    _, index, price = execution
    return dict(status='SHADOW_FILLED', bar_open_ms=closed[index][0], price=price,
        pre_intent_bar_ambiguity=closed[index][0]<intent['decided_ms'], reference_only=True,
        broker_fill_proven=False, orders_allowed=False)


class HedgeBook:
    """Own durable shadow book; never opens a money journal/lock or a sender."""
    def __init__(self,path):
        p=Path(path)
        if p.is_symlink() or any(x.is_symlink() for x in p.absolute().parents):
            raise ValueError('ELDER_JOURNAL_SYMLINK')
        try:
            fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            os.close(fd);created=True
        except FileExistsError:created=False
        self.db=sqlite3.connect(p,isolation_level=None)
        if not created and self.db.execute('PRAGMA application_id').fetchone()[0]!=0x45484731:
            self.db.close();raise ValueError('ELDER_JOURNAL_IDENTITY_CONFLICT')
        if created:self.db.execute('PRAGMA application_id=1162364721')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS elder_intents(id TEXT PRIMARY KEY,body TEXT,pin TEXT)')
        for _,body,pin_ in self.db.execute('SELECT * FROM elder_intents'):
            if sha(body.encode())!=pin_:raise ValueError('ELDER_JOURNAL_CONFLICT')

    def record(self,intent):
        if intent.get('orders_allowed') is not False or intent.get('mode')!='SHADOW':
            raise ValueError('ELDER_ORDERS_OFF_ONLY')
        key=intent['opportunity_id'];body=json.dumps(intent,sort_keys=True,separators=(',',':'),allow_nan=False)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old=self.db.execute('SELECT body FROM elder_intents WHERE id=?',(key,)).fetchone()
            if old:
                if old[0]!=body:raise ValueError('ELDER_INTENT_CONFLICT')
                self.db.commit();return False
            self.db.execute('INSERT INTO elder_intents VALUES(?,?,?)',(key,body,sha(body.encode())))
            self.db.commit();return True
        except Exception:
            self.db.rollback();raise

    def count(self):return self.db.execute('SELECT count(*) FROM elder_intents').fetchone()[0]
    def close(self):self.db.close()


def report_event(intent):
    return dict(schema='ReportEvent v1',type='NO_SEND',ts_ms=intent['decided_ms'],sleeve='ELDER_HEDGE',
        venue='Bybit',strategy=STRATEGY,evidence_id=intent.get('intent_sha256',digest(intent)),mode='SHADOW',
        symbol=intent['symbol'],side='short',reason=intent['status'],execution_owner_id='UNKNOWN',
        tax_a=dict(broker_order_id='UNKNOWN',execution_id='UNKNOWN',fees='UNKNOWN',funding='UNKNOWN',
                   realized_pnl='UNKNOWN',ccy='USDT',financial_event=False))
