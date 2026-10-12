"""Versioned A1 allocator/context with owner-supplied A2 table and time mapping.

Research only. No market client, credentials, broker adapter or order path.
V1 literal-denominator primitives and earlier receipts remain unchanged.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from copy import deepcopy
from decimal import Decimal, InvalidOperation, Context, localcontext
import hashlib
import math
from pathlib import Path
from types import MappingProxyType

from research_lab.brain_v2_frozen_primitives import (
    HOUR, ARMS, REGIMES, VOLS, SPEC_PIN, PARAMS_PIN, Opportunity, RegimeBar,
    Score, BrainBlocked, canonical, digest, _require, _number, _pin, _time,
    regime_context,
)
from research_lab.os2_shadow_journal import strict_json, ShadowJournal
from research_lab.os2_shadow_bridge import BridgeBlocked

VERSION = 'BRAIN_V2_A1_A2_ORDERS_OFF'
A1_PIN = '11577585273fec71c499634e121df879bec1f861a8d3b265f65638ef5f3db999'
A2_PIN = '4e599ff09da9b0354ef95e1ec45c053b4a7c9b0f2bcac40b42fb2eaf79131a10'
TABLE_PIN = '35fa0e0809b0df2f63ef29d5c1483158573d35d6fb25212e79c1cfe500557020'
CUTOFF_MS = 1_759_276_800_000
BAR_MS = {'ATT1': HOUR, 'SBR1': HOUR, 'ASR1': HOUR, 'BOUNCE1': HOUR,
          'ETS2': HOUR//4, 'SF3': HOUR//4}
COST_MODEL = 'BRAIN_V2_V1_6BP_2BP_ACTUAL_FUNDING'
TABLE_PATH = Path(__file__).resolve().parents[1]/'reports/evidence/brain_v2_a2_20261012/frozen/research_lab/brain_v2/MU_SIGMA_V1.json'
PINS = MappingProxyType({'spec_sha256':SPEC_PIN,'params_sha256':PARAMS_PIN,
        'addendum_a1_sha256':A1_PIN,'addendum_a2_sha256':A2_PIN,'table_sha256':TABLE_PIN})


@dataclass(frozen=True)
class FrozenTable:
    raw: bytes

    @property
    def source_hash(self):
        return hashlib.sha256(self.raw).hexdigest()


def load_table(raw: bytes) -> FrozenTable:
    _require(type(raw) is bytes and hashlib.sha256(raw).hexdigest() == TABLE_PIN, 'table_pin')
    data = strict_json(raw)
    _require(data['versiya'] == 'MU_SIGMA_V1_A2' and data['cutoff'] == '2025-10-01'
             and data['kappa0'] == 300 and data['kappa1'] == 150, 'table_contract')
    _require(set(data['nogi']) == set(BAR_MS), 'table_population')
    for row in data['nogi'].values():
        _require(type(row['n']) is int and row['n'] > 1 and _number(row['mean'])
                 and _number(row['sigma']) and row['sigma'] > 0
                 and type(row['n_unknown']) is int and row['n_unknown'] >= 0, 'table_statistics')
        mu_s = row['n']*row['mean']/(row['n']+300)
        _require(math.isclose(mu_s, row['mu'], rel_tol=1e-12, abs_tol=1e-15), 'table_shrinkage')
        population = row['n_unknown']
        for name, cell in row['cells'].items():
            r, v = name.split('|')
            _require(r in ('BULL_TREND','BEAR_TREND','NEUTRAL') and v in VOLS,
                     'table_cell_label')
            _require(type(cell['n']) is int and cell['n'] > 0 and _number(cell['mean']), 'table_cell_count')
            mu = (cell['n']*cell['mean']+150*mu_s)/(cell['n']+150)
            _require(math.isclose(mu, cell['mu'], rel_tol=1e-12, abs_tol=1e-15), 'table_cell_shrinkage')
            population += cell['n']
        _require(population == row['n'], 'table_population_accounting')
    return FrozenTable(raw)


def score_a1(op: Opportunity, table: FrozenTable, regime: str, vol: str) -> Score:
    _require(isinstance(table, FrozenTable), 'statistics_table_unknown')
    data = strict_json(load_table(table.raw).raw)
    _require(op.sleeve in data['nogi'], 'statistics_sleeve')
    _require(op.t_available >= CUTOFF_MS, 'statistics_cutoff_after_decision')
    _require(regime in (*REGIMES,'UNKNOWN') and vol in (*VOLS,'UNKNOWN'), 'context_labels')
    row = data['nogi'][op.sleeve]
    mu_s = row['n']*row['mean']/(row['n']+300)
    if 'UNKNOWN' in (regime, vol):
        mu, status = mu_s, 'UNKNOWN_SLEEVE_FALLBACK'
    else:
        r = {'BULL':'BULL_TREND','BEAR':'BEAR_TREND','NEUTRAL':'NEUTRAL'}[regime]
        # Omitted cells are zero only after exhaustive pinned population validation.
        cell = row['cells'].get(f'{r}|{vol}', {'n':0,'mean':0})
        mu = (cell['n']*cell['mean']+150*mu_s)/(cell['n']+150)
        status = 'KNOWN_CONTEXT' if cell['n'] else 'PINNED_ZERO_POPULATION_CELL'
    z = mu/row['sigma']
    return Score(mu_s,mu,z,min(1.5,max(.5,1+4*z)),status,table.source_hash)


def vol_context(bars, *, hour_ms, source_hash):
    """Closed h−1 H1, Wilder seed14, last2160 NATR, exact midrank A1/A2."""
    base = {'vol':'UNKNOWN', 'hour_ms':hour_ms, 'source_hash':source_hash,
            'method_sha256':A1_PIN, 'orders_allowed':False}
    if not _time(hour_ms) or hour_ms % HOUR or not _pin(source_hash):
        return {**base,'reason':'vol_source_or_time_unknown'}
    if not isinstance(bars,(list,tuple)) or len(bars) < 2173:
        return {**base,'reason':'vol_warmup_or_window_missing'}
    xs = list(bars)
    for i,b in enumerate(xs):
        if (not isinstance(b,RegimeBar) or not _time(b.open_ms) or b.open_ms % HOUR
                or not _time(b.available_ms) or not b.open_ms+HOUR <= b.available_ms <= hour_ms
                or not all(_number(x) for x in (b.o,b.h,b.l,b.c,b.v))
                or min(b.o,b.h,b.l,b.c) <= 0 or b.v < 0
                or not b.l <= min(b.o,b.c) <= max(b.o,b.c) <= b.h
                or (i and xs[i-1].open_ms >= b.open_ms)):
            return {**base,'reason':'vol_invalid_or_unavailable_bar'}
    if xs[-1].open_ms != hour_ms-HOUR:
        return {**base,'reason':'vol_expected_last_bar_missing'}
    if any(b.open_ms-a.open_ms != HOUR for a,b in zip(xs[-2160:],xs[-2159:])):
        return {**base,'reason':'vol_window_not_contiguous'}
    tr = [xs[0].h-xs[0].l]
    tr.extend(max(b.h-b.l,abs(b.h-a.c),abs(b.l-a.c)) for a,b in zip(xs,xs[1:]))
    atr = sum(tr[:14])/14
    natrs = [atr/xs[13].c]
    for i in range(14,len(xs)):
        atr = (13*atr+tr[i])/14
        natrs.append(atr/xs[i].c)
    window = natrs[-2160:]
    if len(window)!=2160 or not all(math.isfinite(x) for x in window):
        return {**base,'reason':'vol_nonfinite_or_short_window'}
    x = window[-1]
    p = 100*(sum(w<x for w in window)+.5*sum(w==x for w in window))/2160
    return {**base,'vol':'LOW' if p<33 else 'HIGH' if p>67 else 'MID',
            'reason':'A1_CLOSED_H1_WILDER_MIDRANK', 'percentile':p,
            'natr':x, 'window_count':2160, 'closed_cutoff_ms':hour_ms}


def signal_available_ms(sleeve, signal_open_ms):
    _require(sleeve in BAR_MS and _time(signal_open_ms)
             and signal_open_ms % BAR_MS[sleeve] == 0, 'signal_bar_identity')
    return signal_open_ms+BAR_MS[sleeve]


def build_contexts(opportunities, *, hour_ms, btc_h4, symbol_h1):
    """Pure source adapter; caller retains raw bars and their source manifest.

    A missing context falls back to the sleeve estimate, never to NEUTRAL.
    This is not a collector and cannot establish real feed completeness.
    """
    if btc_h4 is None:
        regime={'regime':'UNKNOWN','reason':'source_absent','as_of_ms':hour_ms,'orders_allowed':False}
    else:
        regime=regime_context(btc_h4['bars'],hour_ms,btc_h4['source_hash'])
    results={}
    for op in opportunities:
        raw=symbol_h1.get(op.symbol)
        vol=(vol_context(raw['bars'],hour_ms=hour_ms,source_hash=raw['source_hash']) if raw
             else {'vol':'UNKNOWN','reason':'source_absent','hour_ms':hour_ms,'orders_allowed':False})
        envelope={'schema':'BRAIN_V2_A1_CONTEXT','hour_ms':hour_ms,'known_at_ms':hour_ms,
                  'opportunity_id':op.id,'regime':regime,'vol':vol,'pins':dict(PINS)}
        if btc_h4 is not None:
            try: envelope['btc_bars_sha256']=digest([asdict(b) for b in btc_h4['bars']])
            except (TypeError,ValueError): envelope['btc_bars_sha256']=None
        if raw is not None:
            # Invalid/nonfinite data is already UNKNOWN and cannot become a hashable known value.
            try: envelope['symbol_bars_sha256']=digest([asdict(b) for b in raw['bars']])
            except (TypeError,ValueError): envelope['symbol_bars_sha256']=None
        results[op.id]={**envelope,'sha256':digest(envelope)}
    return results


def _decimal(value, reason):
    _require(type(value) in (str,int,float) and type(value) is not bool, reason)
    try: number=Decimal(str(value))
    except InvalidOperation as error: raise BrainBlocked(reason) from error
    _require(number.is_finite(),reason)
    return number


def _seal_state(state):
    state={k:v for k,v in state.items() if k!='state_sha256'}
    return {**state,'state_sha256':digest(state)}


def empty_brain_state():
    return _seal_state({'schema':'BRAIN_V2_A1_STATE','version':VERSION,'pins':dict(PINS),
                        'epoch_start_ms':None,'last_hour_ms':None,'arms':{},
                        'opportunities':{},'terminals':{},'orders_allowed':False})


def _realized_equity(arm_state):
    # Stable summation order survives canonical JSON key sorting on restart.
    return sum((_decimal(arm_state['closed'][key]['net_usd'],'state_terminal_cash')
                for key in sorted(arm_state['closed'])),
               _decimal(arm_state['initial_equity_usd'],'state_initial_capital'))


def _validate_state(state):
    _require(isinstance(state,dict) and state.get('schema')=='BRAIN_V2_A1_STATE'
             and state.get('version')==VERSION and state.get('pins')==PINS
             and state.get('orders_allowed') is False, 'state_identity')
    _require(_seal_state(state)['state_sha256']==state.get('state_sha256'),'state_hash')
    if state['epoch_start_ms'] is None:
        _require(state==empty_brain_state(),'state_uninitialized')
        return
    _require(set(state['arms'])==set(ARMS),'state_arms')
    for a in state['arms'].values():
        initial=_decimal(a['initial_equity_usd'],'state_initial_capital')
        equity=_decimal(a['realized_equity_usd'],'state_capital')
        _require(initial>0 and _realized_equity(a)==equity,'state_cash_identity')
        _require(set(a['positions']).isdisjoint(a['closed']),'state_position_finality_conflict')
        symbols=set()
        for key,p in a['positions'].items():
            _require(key in state['opportunities'] and p['opportunity_id']==key
                     and p['symbol'] not in symbols and p['side'] in ('long','short')
                     and p['sleeve'] in BAR_MS and _decimal(p['risk_usd'],'state_risk')>0
                     and _decimal(p['notional_usd'],'state_notional')>0,'state_position_identity')
            symbols.add(p['symbol'])


def _context_labels(context, op, hour_ms):
    _require(isinstance(context,dict) and context.get('schema')=='BRAIN_V2_A1_CONTEXT'
             and context.get('pins')==PINS and context.get('hour_ms')==hour_ms
             and context.get('known_at_ms')==hour_ms and context.get('opportunity_id')==op.id,
             'context_identity_or_time')
    _require(digest({k:v for k,v in context.items() if k!='sha256'})==context.get('sha256'), 'context_hash')
    r,v=context['regime'],context['vol']
    _require(r.get('as_of_ms')==hour_ms and v.get('hour_ms')==hour_ms,'context_hour')
    _require(r.get('regime') in (*REGIMES,'UNKNOWN') and v.get('vol') in (*VOLS,'UNKNOWN'), 'context_labels')
    _require(r.get('orders_allowed') is False and v.get('orders_allowed') is False,'context_authority')
    if r['regime']!='UNKNOWN':
        _require(_pin(r.get('source_hash')) and _pin(context.get('btc_bars_sha256')),'context_regime_source')
    if v['vol']!='UNKNOWN':
        _require(_pin(v.get('source_hash')) and _pin(context.get('symbol_bars_sha256'))
                 and v.get('method_sha256')==A1_PIN and v.get('closed_cutoff_ms')==hour_ms,'context_vol_source')
    return r['regime'],v['vol']


def _first_reject(positions, candidate, equity, arm):
    existing=list(positions.values()); budget=Decimal('.06')*equity
    risk=_decimal(candidate['risk_usd'],'risk')
    if len(existing)>=12: return 'slots_full'
    if any(p['symbol']==candidate['symbol'] for p in existing): return 'symbol_overlap'
    if sum((_decimal(p['risk_usd'],'risk') for p in existing),risk)>budget: return 'risk_budget'
    if arm!='RAW_SAFE':
        sleeve=sum((_decimal(p['risk_usd'],'risk') for p in existing if p['sleeve']==candidate['sleeve']),risk)
        if sleeve>Decimal('.40')*budget: return 'sleeve_cap'
        net=sum((_decimal(p['risk_usd'],'risk')*(1 if p['side']=='long' else -1) for p in existing),
                risk*(1 if candidate['side']=='long' else -1))
        if abs(net)>Decimal('.60')*budget: return 'direction_cap'
    return None


def _close_terminals(events, state, hour_ms, sealed_at_ms):
    _require(isinstance(events,list),'terminal_population_unknown')
    seen=set()
    for event in sorted(events,key=lambda e:(e['actual_exit_ms'],e['opportunity_id'])):
        key=event['opportunity_id']
        _require(key not in seen and key not in state['terminals'],'duplicate_terminal')
        seen.add(key)
        _require(key in state['opportunities'],'terminal_opportunity_unknown')
        op=Opportunity(**state['opportunities'][key])
        _require(_time(event['actual_exit_ms']) and _time(event['available_ms'])
                 and hour_ms<=event['actual_exit_ms']<hour_ms+HOUR
                 and op.t_available<=event['actual_exit_ms']<=event['available_ms']<=sealed_at_ms,
                 'terminal_late_future_or_exit_time')
        _require(event.get('finality')=='FINAL' and _pin(event.get('source_hash'))
                 and event.get('cost_model_id')==COST_MODEL,'terminal_finality_cost_source_unknown')
        gross=_decimal(event.get('gross_return_frac'),'terminal_gross_unknown')
        exit_ratio=_decimal(event.get('exit_notional_ratio'),'terminal_exit_notional_unknown')
        funding=_decimal(event.get('funding_cost_frac'),'terminal_funding_unknown')
        _require(exit_ratio>0,'terminal_exit_notional_nonpositive')
        for arm,a in state['arms'].items():
            if key not in a['positions']: continue  # independently rejected arm has no trade
            p=a['positions'].pop(key); notional=_decimal(p['notional_usd'],'notional')
            gross_usd=notional*gross
            fees=notional*(1+exit_ratio)*Decimal('.0006')
            slippage=notional*(1+exit_ratio)*Decimal('.0002')
            funding_usd=notional*funding
            net=gross_usd-fees-slippage-funding_usd
            closed={'opportunity_id':key,'actual_exit_ms':event['actual_exit_ms'],
                    'available_ms':event['available_ms'],'event_sha256':digest(event),
                    'gross_usd':str(gross_usd),'fees_usd':str(fees),'slippage_usd':str(slippage),
                    'funding_usd':str(funding_usd),'net_usd':str(net),'arm':arm}
            a['closed'][key]=closed
            a['realized_equity_usd']=str(_realized_equity(a))
        state['terminals'][key]=digest(event)


def _assess_request(request, state):
    """One sealed, complete research hour; pure transaction, never a dispatch.

    Exits from this hour are known by its seal and release before the hour's
    opportunity batch per A1. This convention cannot authorize intrahour orders.
    Supplied source envelopes are evidence inputs, not authenticated broker truth.
    """
    _validate_state(state)
    _require(isinstance(request,dict) and _pin(request.get('source_hash')),'request_source_unknown')
    _require(request.get('positions_known') is True and request.get('protection_known') is True,
             'positions_or_protection_unknown')
    result_state=deepcopy(state)
    decisions={}; closed={}
    if request.get('kind')=='INIT':
        _require(state['epoch_start_ms'] is None,'epoch_already_initialized')
        equity=_decimal(request.get('initial_equity_usd'),'initial_capital_unknown')
        start=request.get('epoch_start_ms')
        _require(request.get('capital_known') is True and equity>0 and _time(start)
                 and start%HOUR==0 and start>=CUTOFF_MS,'initial_capital_or_epoch_unknown')
        result_state['epoch_start_ms']=start
        result_state['arms']={arm:{'initial_equity_usd':str(equity),'realized_equity_usd':str(equity),
                                 'positions':{},'closed':{}} for arm in ARMS}
        status='EPOCH_INITIALIZED_ORDERS_OFF'
    else:
        _require(request.get('kind')=='HOUR' and state['epoch_start_ms'] is not None,'request_kind_or_epoch')
        hour=request.get('hour_ms'); sealed=request.get('sealed_at_ms')
        expected=(state['epoch_start_ms'] if state['last_hour_ms'] is None else state['last_hour_ms']+HOUR)
        _require(_time(hour) and hour==expected and hour%HOUR==0,'hour_sequence')
        _require(_time(sealed) and sealed>=hour+HOUR and request.get('coverage_end_ms')==hour+HOUR
                 and request.get('costs_known') is True,'batch_unsealed_or_costs_unknown')
        raw=request.get('opportunities')
        _require(isinstance(raw,list) and len(raw)<=1000,'opportunity_population_unknown_or_bound')
        try: xs=[Opportunity(**o) for o in raw]
        except (TypeError,KeyError) as error: raise BrainBlocked('opportunity_schema') from error
        _require(len({op.id for op in xs})==len(xs)
                 and not any(op.id in state['opportunities'] for op in xs),'duplicate_opportunity')
        for op in xs:
            _require(op.batch_hour==hour//HOUR and op.cost_model_id==COST_MODEL
                     and signal_available_ms(op.sleeve,op.t_signal)==op.t_available,'opportunity_frozen_time_cost')
        contexts=request.get('contexts')
        _require(isinstance(contexts,dict) and set(contexts)=={op.id for op in xs},'context_population')
        table=load_table(TABLE_PATH.read_bytes())
        scores={op.id:score_a1(op,table,*_context_labels(contexts[op.id],op,hour)) for op in xs}
        before_closed={arm:set(a['closed']) for arm,a in result_state['arms'].items()}
        _close_terminals(request.get('terminals'),result_state,hour,sealed)
        for arm in ARMS:
            a=result_state['arms'][arm]
            equity=_decimal(a['realized_equity_usd'],'capital_unknown')
            _require(equity>0,'realized_capital_nonpositive')
            ordered=sorted(xs,key=(lambda op:(-scores[op.id].z,op.t_available,op.id)) if arm=='BRAIN_DET'
                           else (lambda op:(op.t_available,op.id)))
            decisions[arm]=[]
            for op in ordered:
                s=scores[op.id]; multiplier=s.multiplier if arm=='BRAIN_DET' else 1
                risk=Decimal('.005')*equity*_decimal(multiplier,'multiplier')
                notional=risk/_decimal(op.stop_distance_frac,'stop_distance')
                candidate={'opportunity_id':op.id,'symbol':op.symbol,'sleeve':op.sleeve,
                           'side':op.side,'risk_usd':str(risk),'notional_usd':str(notional),
                           'source_hash':op.source_hash,'t_available':op.t_available}
                reason=_first_reject(a['positions'],candidate,equity,arm)
                decision={**candidate,'arm':arm,'accepted':reason is None,'reason':reason or 'accepted',
                          'multiplier':multiplier,'z':s.z,'mu_s':s.mu_s,'mu_context':s.mu_context,
                          'context_status':s.context_status,'context_sha256':contexts[op.id]['sha256'],
                          'equity_at_batch_usd':str(equity),'budget_usd':str(Decimal('.06')*equity)}
                decisions[arm].append(decision)
                if reason is None: a['positions'][op.id]=candidate
            closed[arm]={key:a['closed'][key] for key in sorted(set(a['closed'])-before_closed[arm])}
        result_state['opportunities'].update({op.id:asdict(op) for op in xs})
        result_state['last_hour_ms']=hour
        status='HOUR_RECORDED_ORDERS_OFF'
    result_state=_seal_state(result_state)
    _validate_state(result_state)
    return {'status':status,'pins':dict(PINS),'version':VERSION,'orders_allowed':False,
            'money_authority':False,'state_after':result_state,'decisions':decisions,
            'closed':closed,'request':deepcopy(request),
            'scope':'RESEARCH_HOUR_BATCH_SUPPLIED_SOURCES_NOT_BROKER_AUTHORITY'}


def assess_request(request,state):
    # Process-global decimal settings cannot change research receipts. This
    # internal 50-digit representation is not venue rounding or a money policy.
    try:
        with localcontext(Context(prec=50)):
            return _assess_request(request,state)
    except BrainBlocked:
        raise
    except (KeyError,TypeError,ValueError,ArithmeticError,OSError) as error:
        raise BrainBlocked(f'malformed_or_unavailable_input:{type(error).__name__}') from error


class BrainJournal(ShadowJournal):
    """Same bounded OS2 single writer; three independent ledgers per transaction.

    Reload verifies both the chain and deterministic semantic replay. No cache,
    truncation, resume override or poisoned-instance retry is permitted.
    """
    receipt_schema='BRAIN_V2_A1_RECEIPT'
    state_schema='BRAIN_V2_A1_STATE'

    def initial_state(self):
        return empty_brain_state()

    @staticmethod
    def evaluate(request,state):
        try:
            return assess_request(request,state)
        except BrainBlocked as error:
            return {'status':'BLOCKED_DATA','reason':str(error),'pins':dict(PINS),'version':VERSION,
                    'orders_allowed':False,'money_authority':False,'state_after':deepcopy(state),
                    'decisions':{},'closed':{},'request':deepcopy(request),
                    'scope':'RESEARCH_HOUR_BATCH_SUPPLIED_SOURCES_NOT_BROKER_AUTHORITY'}

    def assess(self,bundle):
        return self.evaluate(bundle,self.state)

    def _load(self):
        super()._load()
        state=empty_brain_state()
        for receipt in self.receipts.values():
            try:
                request=receipt['request']
                expected=self.evaluate(request,state)
                valid=(request['request_id']==receipt['request_id']
                       and digest(request)==receipt['input_sha256']
                       and all(receipt[k]==v for k,v in expected.items())
                       and set(receipt)==set(expected)|{'schema','sequence','request_id','input_sha256',
                                                        'previous_sha256','sha256'})
                if not valid: raise ValueError('semantic replay mismatch')
                state=expected['state_after']
            except (ValueError,KeyError,TypeError) as error:
                raise BridgeBlocked('BLOCKED_DATA','brain_journal_semantic_replay_mismatch') from error
        self.state=state
