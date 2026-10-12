"""Separate frozen A7 engineering candidate. No client/order/live authority.

Predicate is shared by prospective callers; no existing worker is changed here.
Scoring, allocation, cash, funding, timing and DD_ENV reuse frozen A1-A6 mechanics.
"""
from collections import Counter
from decimal import Decimal
import hashlib
import math
from pathlib import Path

from research_lab.brain_v2_frozen_primitives import ARMS, VOLS, _number, _require
from research_lab.brain_v2_a1 import BAR_MS
from research_lab.brain_v2_develop import (
    FoldTable, DevelopEngine, DATES, BOUNDARIES, END, fold_at, text_decimal,
)
from research_lab.brain_v2_develop_run import execute_once, save_exclusive
from research_lab.os2_shadow_journal import strict_json

MAX_LEV=100
A7_PIN='0b40ce06fffd4afbc916b066021d523fee51b6fe56e01c8e935827c5f49279e1'
FREEZE_PIN='e650a34259ce6749f5fd47842f8228b6553c105054b1e21922663b85f5320b0a'
OWNER_GO='GO_BRAIN_V2_V1_1_A7_ONCE'


def feasibility(entry):
    """Frozen source lev, before scorer/allocator, never clamp or rescale it."""
    _require(_number(entry.lev) and entry.lev>0,'A7_lev_unknown_or_invalid')
    return 'infeasible_stop_lev' if entry.lev>MAX_LEV else None


def partition(entries):
    feasible,rejected=[],[]
    for entry in entries:
        (rejected if feasibility(entry) else feasible).append(entry)
    return feasible,rejected


class A7Table:
    """Authenticate A7 bytes; same statistical validation and score as FoldTable.

    No table regeneration, reinterpretation or projection back into an A2 blob.
    The prospective cutoff is allowed too; its decision-time check is unchanged.
    """
    score=FoldTable.score

    def __init__(self,raw,*,expected_pin,cutoff):
        _require(type(raw) is bytes and hashlib.sha256(raw).hexdigest()==expected_pin,'table_pin')
        d=strict_json(raw)
        _require(d.get('versiya')=='MU_SIGMA_V1_A7' and d.get('cutoff')==cutoff
            and cutoff in (*DATES,'2025-10-01') and d.get('kappa0')==300 and d.get('kappa1')==150
            and isinstance(d.get('nogi'),dict) and set(d['nogi'])<=set(BAR_MS)
            and isinstance(d.get('exec_feasibility'),dict)
            and _number(d['exec_feasibility'].get('max_lev'))
            and d['exec_feasibility']['max_lev']==MAX_LEV,'A7_table_contract')
        for row in d['nogi'].values():
            _require(type(row['n']) is int and row['n']>=0 and _number(row['mean'])
                and (row['n']<2 or (_number(row['sigma']) and row['sigma']>=0)),'table_stats')
            if row['n']<2 or row['sigma']==0:continue
            _require(type(row['n_unknown']) is int and row['n_unknown']>=0,'table_population')
            mu=row['n']*row['mean']/(row['n']+300)
            _require(math.isclose(mu,row['mu'],rel_tol=1e-12,abs_tol=1e-15),'table_mu')
            count=row['n_unknown']
            for name,cell in row['cells'].items():
                regime,vol=name.split('|')
                _require(regime in ('BULL_TREND','BEAR_TREND','NEUTRAL') and vol in VOLS
                    and type(cell['n']) is int and cell['n']>0 and _number(cell['mean']),'table_cell')
                expected=(cell['n']*cell['mean']+150*mu)/(cell['n']+150)
                _require(math.isclose(expected,cell['mu'],rel_tol=1e-12,abs_tol=1e-15),'table_cell_mu')
                count+=cell['n']
            _require(count==row['n'],'table_population')
        self.raw,self.source_hash,self.cutoff=raw,expected_pin,cutoff
        self._data=d
        self.cutoff_ms=END if cutoff=='2025-10-01' else BOUNDARIES[DATES.index(cutoff)]


class DevelopEngineV11(DevelopEngine):
    """A7 admission population before the unchanged three-arm allocator."""
    def __init__(self,tables):
        _require(all(isinstance(t,A7Table) for t in tables),'A7_tables_required')
        super().__init__(tables)
        self.infeasible=Counter()
        self.max_notional_ratio={arm:Decimal(0) for arm in ARMS}
        self.sf3_net={arm:Decimal(0) for arm in ARMS}
        self.sf3_known_closed={arm:0 for arm in ARMS}

    def step(self,at,entries,contexts,outcomes):
        ids=[e.opportunity.id for e in entries]
        _require(len(ids)==len(set(ids)) and not self.seen.intersection(ids),'duplicate_opportunity')
        _require(all(e.opportunity.t_available==at
            and e.opportunity.t_signal==at-BAR_MS[e.opportunity.sleeve]
            for e in entries),'opportunity_tick')
        valid,rejected=partition(entries)
        accepted_ids={e.opportunity.id for e in valid}
        _require(set(contexts)==set(outcomes)==accepted_ids,'A7_feasible_input_completeness')
        result=super().step(at,valid,contexts,outcomes)
        if rejected:
            fold=fold_at(at)
            for e in rejected:
                key=e.opportunity.id;self.infeasible[f'{fold}|{e.opportunity.sleeve}']+=1
                result['decisions'][key]={}
                for arm in ARMS:
                    self.arms[arm]['rejected']['infeasible_stop_lev']+=1
                    result['decisions'][key][arm]=dict(accepted=False,reason='infeasible_stop_lev',
                        rank=None,risk_usd=None,multiplier=None,z=None,table_sha256=None,cold_start=None)
            self.seen.update(e.opportunity.id for e in rejected)
        for arm,a in self.arms.items():
            if a['equity']>0:
                gross=sum((Decimal(p['notional_usd']) for p in a['positions'].values()),Decimal(0))
                self.max_notional_ratio[arm]=max(self.max_notional_ratio[arm],gross/a['equity'])
            for row in result['closed'][arm]:
                if row['sleeve']=='SF3' and row['status']=='KNOWN':
                    self.sf3_net[arm]+=Decimal(row['net_usd']);self.sf3_known_closed[arm]+=1
        return result

    def report(self):
        report=super().report()
        report.update(version='BRAIN_V2_V1_1_A7',development_evidence_only=True,
            independent_holdout=False,exec_feasibility_a7_sha256=A7_PIN,
            infeasible_stop_lev_by_sleeve_fold=dict(self.infeasible),
            max_open_notional_over_equity={k:text_decimal(v) for k,v in self.max_notional_ratio.items()},
            sf3_contribution={arm:dict(net_usd=text_decimal(self.sf3_net[arm]),
                known_closed=self.sf3_known_closed[arm],
                fraction_of_arm_net=(text_decimal(self.sf3_net[arm]/Decimal(report['arms'][arm]['net_usd']))
                    if Decimal(report['arms'][arm]['net_usd'])!=0 else None)) for arm in ARMS})
        return report


def run_once_authorized(output,manifest_pin,owner_go,driver):
    """Only a separately provided direct owner instruction may spend V1.1."""
    _require(owner_go==OWNER_GO,'explicit_owner_go_required')
    output=Path(output)
    _require(output.name=='run_v1_1','separate_version_run_directory_required')
    def guarded(path):
        save_exclusive(path/'OWNER_GO.json',dict(owner_go=owner_go,version='V1.1_A7',
            manifest_sha256=manifest_pin,orders_allowed=False,money_authority=False))
        return driver(path)
    return execute_once(output,manifest_pin,guarded)
