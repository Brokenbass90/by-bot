"""Frozen A5/A6 historical comparison mechanics, strictly orders-OFF.

DD_ENV uses future frozen R only as the owner's historical diagnostic proxy.
It never supplies ranking, sizing or admission. Realized equity changes only
on A3 release; A4 funding UNKNOWN releases risk and excludes the whole cashflow.
"""
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from decimal import Decimal, Context, localcontext
import hashlib
import math
from collections import Counter
from copy import deepcopy

from research_lab.brain_v2_frozen_primitives import (
    ARMS, HOUR, BrainBlocked, _require, _number, _time, REGIMES, VOLS,
)
from research_lab.brain_v2_a1 import BAR_MS, _decimal, _first_reject
from research_lab.brain_v2_a3 import TICK, terminal_cash
from research_lab.os2_shadow_journal import strict_json

START=1_688_169_600_000  # 2023-07-01UTC
END=1_759_276_800_000    # 2025-10-01UTC
BOUNDARIES=(START,1_704_067_200_000,1_719_792_000_000,1_735_689_600_000,END)
FOLDS=tuple(zip(BOUNDARIES,BOUNDARIES[1:]))
DATES=('2023-07-01','2024-01-01','2024-07-01','2025-01-01')
A5_PIN='c07cf7964f4013b98c696633ac2b46bdc55cdfce0756f51b33a26cd0ada6e84a'
A6_PIN='19a177e2a4b9e096e049552642b9ea49f51f8a5ce70630403dcc298f766e4441'


def text_decimal(value):
    return format(value,'f').rstrip('0').rstrip('.') if '.' in format(value,'f') else format(value,'f')


def fold_at(at_ms):
    _require(_time(at_ms) and START<=at_ms<END,'test_fold_boundary')
    return bisect_right(BOUNDARIES,at_ms)-1


class FoldTable:
    def __init__(self,raw,*,expected_pin,cutoff):
        _require(type(raw) is bytes and hashlib.sha256(raw).hexdigest()==expected_pin,'table_pin')
        d=strict_json(raw)
        _require(d.get('versiya')=='MU_SIGMA_V1_A2' and d.get('cutoff')==cutoff
                 and cutoff in DATES and d.get('kappa0')==300 and d.get('kappa1')==150
                 and isinstance(d.get('nogi'),dict) and set(d['nogi'])<=set(BAR_MS),'table_contract')
        for row in d['nogi'].values():
            _require(type(row['n']) is int and row['n']>=0 and _number(row['mean'])
                     and (row['n']<2 or (_number(row['sigma']) and row['sigma']>=0)), 'table_stats')
            if row['n']<2 or row['sigma']==0:
                continue  # A6: cells deliberately not scored in cold start.
            _require(type(row['n_unknown']) is int and row['n_unknown']>=0,'table_population')
            mu=row['n']*row['mean']/(row['n']+300)
            _require(math.isclose(mu,row['mu'],rel_tol=1e-12,abs_tol=1e-15),'table_mu')
            count=row['n_unknown']
            for name,cell in row['cells'].items():
                r,v=name.split('|')
                _require(r in ('BULL_TREND','BEAR_TREND','NEUTRAL') and v in VOLS
                         and type(cell['n']) is int and cell['n']>0 and _number(cell['mean']),
                         'table_cell')
                expect=(cell['n']*cell['mean']+150*mu)/(cell['n']+150)
                _require(math.isclose(expect,cell['mu'],rel_tol=1e-12,abs_tol=1e-15),'table_cell_mu')
                count+=cell['n']
            _require(count==row['n'],'table_population')
        self.raw,self.source_hash,self.cutoff=raw,expected_pin,cutoff
        self._data=d
        self.cutoff_ms=BOUNDARIES[DATES.index(cutoff)]

    def score(self,sleeve,regime,vol,*,at_ms):
        _require(sleeve in BAR_MS and regime in (*REGIMES,'UNKNOWN')
                 and vol in (*VOLS,'UNKNOWN'),'score_identity')
        _require(at_ms>=self.cutoff_ms,'table_cutoff_after_decision')
        row=self._data['nogi'].get(sleeve)
        if row is None or row['n']<2 or row['sigma']==0:
            return dict(z=0.0,multiplier=1.0,cold_start=True,status='A6_COLD_START',
                        table_sha256=self.source_hash)
        mu_s=row['n']*row['mean']/(row['n']+300)
        if 'UNKNOWN' in (regime,vol):
            mu,status=mu_s,'UNKNOWN_SLEEVE_FALLBACK'
        else:
            name={'BULL':'BULL_TREND','BEAR':'BEAR_TREND','NEUTRAL':'NEUTRAL'}[regime]+'|'+vol
            cell=row['cells'].get(name,{'n':0,'mean':0})
            mu=(cell['n']*cell['mean']+150*mu_s)/(cell['n']+150)
            status='KNOWN_CONTEXT' if cell['n'] else 'PINNED_ZERO_POPULATION_CELL'
        z=mu/row['sigma']
        _require(math.isfinite(z),'score_nonfinite')
        return dict(z=z,multiplier=min(1.5,max(.5,1+4*z)),cold_start=False,status=status,
                    table_sha256=self.source_hash)


class FundingA6:
    """A6 calendar from exact archive, without assumed venue settlement cadence."""
    def __init__(self,raw,*,source_hash,symbol):
        self.source_hash,self.symbol=source_hash,symbol
        self._times,self._rates=[],[]
        self.missing=raw is None
        if self.missing:
            _require(source_hash is None,'missing_funding_pin');return
        _require(hashlib.sha256(raw).hexdigest()==source_hash,'funding_pin')
        d=strict_json(raw)
        _require(isinstance(d,dict) and d.get('symbol')==symbol
                 and isinstance(d.get('funding'),list),'funding_schema')
        for row in d['funding']:
            _require(isinstance(row,list) and len(row)==2 and _time(row[0])
                     and (not self._times or row[0]>self._times[-1]),'funding_timestamp_duplicate_order')
            self._times.append(row[0]);self._rates.append(row[1])

    def summary(self,*,start_ms,end_ms):
        _require(_time(start_ms) and _time(end_ms) and start_ms<end_ms,'funding_window')
        base=dict(status='FUNDING_UNKNOWN',rate_sum=None,source_hash=self.source_hash,
                  calendar_model_sha256=A6_PIN,symbol=self.symbol,start_ms=start_ms,end_ms=end_ms,
                  reason=None,settlement_count=0,baseline_gap_ms=None)
        if self.missing:return {**base,'reason':'missing_file'}
        a=bisect_right(self._times,start_ms)-1;b=bisect_left(self._times,end_ms)
        if a<0 or b>=len(self._times):return {**base,'reason':'outside_archive'}
        if a<10:return {**base,'reason':'insufficient_history'}
        intervals=sorted(self._times[i]-self._times[i-1] for i in range(a-9,a+1))
        median=Decimal(intervals[4]+intervals[5])/2
        base['baseline_gap_ms']=int(median) if median==int(median) else str(median)
        if any(self._times[i]-self._times[i-1]>median for i in range(a+1,b+1)):
            return {**base,'reason':'calendar_gap'}
        rates=self._rates[a+1:bisect_right(self._times,end_ms)]
        if not all(_number(r) for r in rates):return {**base,'reason':'nonfinite_rate'}
        with localcontext(Context(prec=50)):
            total=sum((Decimal(str(r)) for r in rates),Decimal(0))
        return {**base,'status':'KNOWN','reason':'A6_COVERED','rate_sum':text_decimal(total),
                'settlement_count':len(rates)}


@dataclass(frozen=True)
class Outcome:
    hours: int
    R: float
    funding: dict


class DevelopEngine:
    """Three isolated virtual ledgers sharing inputs, never sharing equity/state."""
    def __init__(self,tables):
        _require(type(tables) is tuple and tuple(t.cutoff for t in tables)==DATES,'four_fold_tables')
        self.tables=tables;self.last_tick=None;self.seen=set()
        self.arms={arm:dict(equity=Decimal(100000),positions={},fold_net=[Decimal(0)]*4,
            peak_env=Decimal(100000),peak_realized=Decimal(100000),dd_env=Decimal(0),dd_realized=Decimal(0),
            closed_count=0,known_count=0,unknown_count=0,unknown_by_reason=Counter(),unknown_by_symbol=Counter(),
            unknown_risk=Decimal(0),unknown_slot_hours=0,positive_net=Decimal(0),negative_net=Decimal(0),
            slippage=Decimal(0),funding=Decimal(0),commission_in_R_model=Decimal(0),turnover=Decimal(0),
            rejected=Counter(),cold_decisions=Counter(),accepted=0,ticks=0,risk_fraction_sum=Decimal(0))
            for arm in ARMS}

    def step(self,at,entries,contexts,outcomes):
        with localcontext(Context(prec=50)):
            return self._step(at,entries,contexts,outcomes)

    def _step(self,at,entries,contexts,outcomes):
        _require(_time(at) and at==(START if self.last_tick is None else self.last_tick+TICK),
                 'tick_continuity')
        _require(not entries or at<END,'new_entry_after_end')
        ids=[e.opportunity.id for e in entries]
        _require(len(ids)==len(set(ids)) and not self.seen.intersection(ids),'duplicate_opportunity')
        _require(set(contexts)==set(ids) and set(outcomes)==set(ids),'paired_input_completeness')
        for entry in entries:
            op=entry.opportunity;event=outcomes[op.id]
            _require(op.t_available==at and op.t_signal==at-BAR_MS[op.sleeve], 'opportunity_tick')
            _require(type(event.hours) is int and 1<=event.hours<=op.max_hold_h
                     and _number(event.R) and event.funding.get('status') in ('KNOWN','FUNDING_UNKNOWN'),
                     'outcome_contract')
        closed,ticks={},{}
        for arm,a in self.arms.items():
            released=[]
            due=sorted(k for k,p in a['positions'].items() if p['release_ms']<=at)
            for key in due:
                p=a['positions'].pop(key)
                _require(p['release_ms']==at,'release_tick_missed')
                cash=terminal_cash(p['risk_usd'],p['lev'],p['R'],p['side'],p['funding'])
                a['closed_count']+=1
                if cash['status']=='KNOWN':
                    net=Decimal(cash['net_usd']);a['equity']+=net
                    a['fold_net'][p['entry_fold']]+=net;a['known_count']+=1
                    a['positive_net']+=max(Decimal(0),net);a['negative_net']+=min(Decimal(0),net)
                    a['slippage']+=Decimal(cash['slippage_usd']);a['funding']+=Decimal(cash['funding_usd'])
                    a['turnover']+=2*Decimal(p['notional_usd'])
                    a['commission_in_R_model']+=Decimal('.0012')*Decimal(p['notional_usd'])
                else:
                    a['unknown_count']+=1;a['unknown_by_reason'][p['funding']['reason']]+=1
                    a['unknown_by_symbol'][p['symbol']]+=1
                    a['unknown_risk']+=Decimal(p['risk_usd']);a['unknown_slot_hours']+=p['hours']
                released.append({k:v for k,v in p.items() if k!='funding'}|dict(
                    **cash,funding_reason=p['funding']['reason'],funding_source_sha256=p['funding']['source_hash']))
            closed[arm]=released
            # Frozen A5 observation order: after releases, before current entries.
            env=a['equity']+sum((min(Decimal(-1),Decimal(str(p['R'])))*Decimal(p['risk_usd'])
                  for p in a['positions'].values() if p['funding']['status']=='KNOWN'),Decimal(0))
            a['peak_env']=max(a['peak_env'],env)
            a['dd_env']=max(a['dd_env'],(a['peak_env']-env)/a['peak_env'])
            a['peak_realized']=max(a['peak_realized'],a['equity'])
            a['dd_realized']=max(a['dd_realized'],(a['peak_realized']-a['equity'])/a['peak_realized'])
            risk=sum((Decimal(p['risk_usd']) for p in a['positions'].values()),Decimal(0))
            a['ticks']+=1
            if a['equity']>0:a['risk_fraction_sum']+=risk/(Decimal('.06')*a['equity'])
            ticks[arm]=dict(realized_usd=text_decimal(a['equity']),env_usd=text_decimal(env),
                dd_env=text_decimal(a['dd_env']),dd_realized=text_decimal(a['dd_realized']),
                open_positions=len(a['positions']),open_risk_usd=text_decimal(risk))
        paired={key:{} for key in ids}
        if entries:
            fold=fold_at(at);table=self.tables[fold]
            scores={e.opportunity.id:table.score(e.opportunity.sleeve,*contexts[e.opportunity.id],at_ms=at)
                    for e in entries}
            for arm,a in self.arms.items():
                _require(a['equity']>0,'realized_capital_nonpositive')
                ordering=sorted(entries,key=lambda e:(-scores[e.opportunity.id]['z'],e.opportunity.t_available,
                     e.opportunity.id) if arm=='BRAIN_DET' else (e.opportunity.t_available,e.opportunity.id))
                for rank,entry in enumerate(ordering):
                    op=entry.opportunity;key=op.id;score=scores[key]
                    mult=score['multiplier'] if arm=='BRAIN_DET' else 1.0
                    risk=Decimal('.005')*a['equity']*Decimal(str(mult))
                    p=dict(opportunity_id=key,symbol=op.symbol,sleeve=op.sleeve,side=op.side,
                           risk_usd=text_decimal(risk),lev=str(entry.lev),
                           notional_usd=text_decimal(risk*Decimal(str(entry.lev))),entry_ms=at,entry_fold=fold)
                    reason=_first_reject(a['positions'],p,a['equity'],arm)
                    decision=dict(accepted=reason is None,reason=reason,rank=rank,risk_usd=p['risk_usd'],
                        multiplier=mult,z=score['z'] if arm=='BRAIN_DET' else None,table_sha256=table.source_hash,
                        cold_start=score['cold_start'] if arm=='BRAIN_DET' else None)
                    paired[key][arm]=decision
                    if arm=='BRAIN_DET' and score['cold_start']:a['cold_decisions'][(fold,op.sleeve)]+=1
                    if reason:a['rejected'][reason]+=1;continue
                    # Only after admission: source R/hold/funding for diagnostics and releases.
                    event=outcomes[key];a['positions'][key]={**p,'release_ms':at+event.hours*HOUR,
                        'hours':event.hours,'R':event.R,'funding':deepcopy(event.funding)}
                    a['accepted']+=1
        self.seen.update(ids);self.last_tick=at
        return dict(tick_ms=at,decisions=paired,ticks=ticks,closed=closed,orders_allowed=False)

    def report(self):
        with localcontext(Context(prec=50)):
            rows={}
            for arm,a in self.arms.items():
                rows[arm]=dict(final_realized_usd=text_decimal(a['equity']),
                    net_usd=text_decimal(a['equity']-100000),fold_net_usd=list(map(text_decimal,a['fold_net'])),
                    dd_env=text_decimal(a['dd_env']),dd_realized_reference=text_decimal(a['dd_realized']),
                    accepted=a['accepted'],closed=a['closed_count'],known=a['known_count'],
                    funding_unknown=a['unknown_count'],funding_unknown_fraction=a['unknown_count']/a['closed_count'] if a['closed_count'] else None,
                    unknown_by_reason=dict(a['unknown_by_reason']),unknown_by_symbol=dict(a['unknown_by_symbol']),
                    unknown_slot_hours=a['unknown_slot_hours'],unknown_risk_usd=text_decimal(a['unknown_risk']),
                    pf_known=text_decimal(a['positive_net']/abs(a['negative_net'])) if a['negative_net'] else None,
                    expectancy_usd_known=text_decimal((a['positive_net']+a['negative_net'])/a['known_count']) if a['known_count'] else None,
                    slippage_usd_known=text_decimal(a['slippage']),signed_funding_usd_known=text_decimal(a['funding']),
                    commission_already_in_R_model_usd_known=text_decimal(a['commission_in_R_model']),
                    roundtrip_turnover_usd_known=text_decimal(a['turnover']),rejections=dict(a['rejected']),
                    cold_start_decisions={f'{fold}|{s}':n for (fold,s),n in a['cold_decisions'].items()},
                    ticks=a['ticks'],average_open_risk_budget_fraction=text_decimal(a['risk_fraction_sum']/a['ticks']) if a['ticks'] else None,
                    idle_cash_usd=None,idle_cash_reason='NO_FROZEN_EXECUTION_MARGIN_MODEL',open_positions=len(a['positions']))
            brain=self.arms['BRAIN_DET'];foundation=self.arms['FOUNDATION']
            wins=[a>=b for a,b in zip(brain['fold_net'],foundation['fold_net'])]
            dd_ok=brain['dd_env']<=Decimal('1.1')*foundation['dd_env']
            unknown=any(a['unknown_count']*20>a['closed_count'] for a in self.arms.values())
            status='BLOCKED_DATA' if unknown else 'DEVELOPING_FILTER_PASS' if sum(wins)>=3 and dd_ok else 'STOP_V1'
            return dict(status=status,arms=rows,fold_noninferior=wins,fold_noninferior_count=sum(wins),
                        dd_env_gate_pass=dd_ok,metric='A5_DD_ENV_NOT_MTM',initial_usd=100000,
                        filter_runs=1,orders_allowed=False,money_authority=False,
                        standalone_edge_proven=False,source_regime_policy_approved=False)
