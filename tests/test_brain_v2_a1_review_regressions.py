import ast
from copy import deepcopy
from dataclasses import replace
from decimal import localcontext
from pathlib import Path

import numpy as np
import pytest

from research_lab.brain_v2_a1 import (
    assess_request, build_contexts, load_table, signal_available_ms, vol_context, _first_reject,
)
from research_lab.brain_v2_frozen_primitives import BrainBlocked
from tests.test_brain_v2_a1_allocator import NOW, PIN, op, initialized, batch, terminal, HOUR
from tests.test_brain_v2_a1_context import bars

ROOT=Path(__file__).resolve().parents[1]
FROZEN=ROOT/'reports/evidence/brain_v2_a2_20261012/frozen/research_lab/brain_v2'


def test_external_decimal_context_cannot_change_receipt_sizing_or_equity():
    x=replace(op(),stop_distance_frac=.0137)
    state=assess_request(batch([x]),initialized())['state_after']
    req=batch([],hour=NOW+HOUR,exits=[terminal(x,gross=.03779)])
    expected=assess_request(req,state)
    with localcontext() as ctx:
        ctx.prec=6
        assert assess_request(req,state)==expected


def test_nonfinite_btc_source_becomes_unknown_instead_of_crashing_adapter():
    h4=[replace(b,c=float('nan')) for b in bars(60)]
    contexts=build_contexts([op()],hour_ms=NOW,
                            btc_h4={'bars':h4,'source_hash':PIN},symbol_h1={})
    assert contexts[op().id]['regime']['regime']=='UNKNOWN'


def test_malformed_terminal_returns_explicit_blocked_not_keyerror():
    state=assess_request(batch([op()]),initialized())['state_after']
    with pytest.raises(BrainBlocked):
        assess_request(batch([],hour=NOW+HOUR,exits=[{}]),state)


def test_synthetic_context_parity_with_exact_a2_pure_functions_only():
    # AST extracts pure routines only. No imports/main, generator, B3 inputs or outcomes run.
    tree=ast.parse((FROZEN/'mu_sigma.py').read_text())
    pure=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef)
                         and n.name in ('natr_series','vol_bucket','t_available')],type_ignores=[])
    env={'np':np,'WIN':2160,'H':HOUR,
         'BAR_MS':{'ATT1':HOUR,'ETS2':HOUR//4}}
    exec(compile(pure,'frozen_a2_pure_functions','exec'),env)
    assert signal_available_ms('ATT1',NOW)==env['t_available']({'ts':NOW,'leg':'ATT1'})
    assert signal_available_ms('ETS2',NOW)==env['t_available']({'ts':NOW,'leg':'ETS2'})
    xs=list(bars())
    for value in (2.,4.,1.):
        xs[-1]=replace(xs[-1],h=100.+value/2,l=100.-value/2)
        ts=np.array([b.open_ms for b in xs]);ohlc=np.array([[b.o,b.h,b.l,b.c,b.v] for b in xs])
        natr,ok=env['natr_series'](ts,ohlc)
        actual=vol_context(xs,hour_ms=xs[-1].open_ms+HOUR,source_hash=PIN)
        assert actual['vol']==env['vol_bucket'](natr,ok,len(xs)-1)
        assert actual['natr']==pytest.approx(natr[-1],rel=1e-14)


def test_superseded_a1_table_cannot_rank_any_new_opportunity():
    old=ROOT/'reports/evidence/brain_v2_a1_20261012/frozen/research_lab/brain_v2/MU_SIGMA_V1.json'
    with pytest.raises(BrainBlocked,match='table_pin'):load_table(old.read_bytes())


def test_receipt_pins_are_copies_caller_cannot_change_global_frozen_identity():
    request=batch([op()]); state=initialized()
    result=assess_request(request,state)
    result['pins']['table_sha256']='b'*64
    assert assess_request(request,state)['pins']['table_sha256']!='b'*64


def test_full_risk_budget_precedes_sleeve_cap_and_exact_equality_is_allowed():
    from decimal import Decimal
    # Direct analytical fixture, no new table, tuning or outcome consumption.
    p={'symbol':'BTC','sleeve':'ATT1','side':'long','risk_usd':'55'}
    c={'symbol':'ETH','sleeve':'ATT1','side':'short','risk_usd':'6'}
    assert _first_reject({'p':p},c,Decimal(1000),'FOUNDATION')=='risk_budget'
    c['risk_usd']='5'
    assert _first_reject({'p':p},c,Decimal(1000),'RAW_SAFE') is None


def test_duplicate_symbol_precedes_budget_and_same_hour_terminal_stays_blocked():
    from decimal import Decimal
    p={'symbol':'BTC','sleeve':'ATT1','side':'long','risk_usd':'59'}
    c={'symbol':'BTC','sleeve':'ATT1','side':'short','risk_usd':'6'}
    assert _first_reject({'p':p},c,Decimal(1000),'FOUNDATION')=='symbol_overlap'
    # Cannot insert a same-hour outcome into capital before its new opportunity is admitted.
    x=op()
    with pytest.raises(BrainBlocked,match='terminal_opportunity_unknown'):
        assess_request(batch([x],exits=[terminal(x,hour=NOW)]),initialized())
