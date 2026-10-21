"""PUMP4 V1 frozen signal -> reference execution geometry, always ORDERS_OFF.

Contract b138735; no research evaluator, outcome, broker or money authority.
This is a plan component, not an execution admission or quantity calculator.
"""
import hashlib
import math
import os
from pathlib import Path

from research_lab.alpaca_dynamic_v1 import digest

HOUR_MS=3600000
SOURCE_PINS={
    'strategies/pump_fade_v4r.py':'cea7a2cc9151d22ddaf620428dc6b7734f6aa4051819145821a76cda2381792a',
    'strategies/signals.py':'5f9408f203f303853360dd79e31fe0893b6db95329abbd758401a89f3258755c',
}


def frozen_sources():
    root=Path(__file__).resolve().parents[1]
    if any(key.startswith('PF_') for key in os.environ):raise ValueError('PUMP4_AMBIENT_PF_CONFIG')
    if any(hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha for name,sha in SOURCE_PINS.items()):
        raise ValueError('PUMP4_FROZEN_SOURCE_DRIFT')
    return dict(SOURCE_PINS)


def build_plan(signal,*,signal_bar_open_ms,next_open_ms,next_open):
    """Use actual next open, never signal close as a replacement entry price.

    Floating arithmetic deliberately matches the frozen research producer.
    Instrument rounding, actual fills, costs and risk limits are later gates.
    Inputs must come from the causal closed-bar intake; this function cannot
    prove that intake or turn a historical plan into an executable instruction.
    """
    pins=frozen_sources()
    def require(ok,reason):
        if not ok:raise ValueError('PUMP4_PLAN_'+reason)
    def price(value):
        require(type(value) in (int,float) and math.isfinite(value) and value>0,'PRICE')
        return float(value)
    require(type(signal_bar_open_ms) is int and signal_bar_open_ms>0
        and signal_bar_open_ms%HOUR_MS==0 and type(next_open_ms) is int
        and next_open_ms==signal_bar_open_ms+HOUR_MS,'NEXT_OPEN_TIME')
    require(signal.strategy=='pump_fade' and signal.side in ('long','short')
        and isinstance(signal.symbol,str) and bool(signal.symbol),'SIGNAL_IDENTITY')
    require(isinstance(signal.tps,list) and len(signal.tps)>=2
        and isinstance(signal.tp_fracs,list) and bool(signal.tp_fracs)
        and type(signal.tp_fracs[0]) in (int,float) and signal.tp_fracs[0]==.4,'FROZEN_TARGET_FRACTION')
    entry=price(next_open);raw_stop=price(signal.sl)
    # Do not carry signal BE/trail/time_stop/tp3 fields into V1.
    stop=price(entry+(raw_stop-entry)*4.0);targets=[price(v) for v in signal.tps[:2]]
    short=signal.side=='short'
    require((targets[1]<targets[0]<entry<stop) if short else (stop<entry<targets[0]<targets[1]),'GEOMETRY')
    risk=(stop-entry) if short else (entry-stop)
    leverage=entry/risk;require(leverage<=100,'GEOMETRIC_LEVERAGE')
    plan=dict(schema='PUMP4_V1_REFERENCE_EXECUTION_PLAN_V1',contract_commit='b1387354e5b64de205e7f933b0537a2f6f37c123',
        source_pins=pins,symbol=signal.symbol,side=signal.side,
        signal_bar_open_ms=signal_bar_open_ms,entry_bar_open_ms=next_open_ms,
        entry=entry,stop=stop,targets=targets,fractions=[.4,.6],hold_bars=168,
        stop_checked_first=True,geometric_leverage=leverage,model_fee_rate_per_side=.0006,
        funding_cost='UNKNOWN',universe_validation='NOT_PERFORMED',
        instrument_rounding='NOT_PERFORMED',execution_admission='NOT_PERFORMED',
        money_authority=False,orders_allowed=False)
    return dict(plan,plan_sha256=digest(plan))
