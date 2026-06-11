"""Tests for bot/confidence_risk.py (Claude 2026-06-10)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.confidence_risk import (
    RISK_MULT_MAX, RISK_MULT_MIN, LEV_CAP_MAX, LEV_CAP_MIN,
    advise, compute_confidence, score_regime_align, score_rr,
    score_strategy_pf, score_vol_sanity,
)


def test_no_factors_is_neutral():
    a = advise()
    assert a.confidence == 0.5
    assert RISK_MULT_MIN < a.risk_mult < RISK_MULT_MAX
    assert LEV_CAP_MIN < a.leverage_cap < LEV_CAP_MAX


def test_high_confidence_raises_risk_and_leverage():
    a = advise(rr=3.0, side="long", regime="bull_trend",
               strategy_pf=1.6, strategy_trades=30, level_quality=0.9, atr_pct=2.0)
    assert a.confidence > 0.9
    assert a.risk_mult > 1.4
    assert a.leverage_cap > 2.8


def test_low_confidence_cuts_risk():
    a = advise(rr=1.05, side="long", regime="bear_trend",
               strategy_pf=0.7, strategy_trades=30, atr_pct=12.0)
    assert a.confidence < 0.2
    assert a.risk_mult < 0.7
    assert a.leverage_cap < 1.5


def test_bounds_never_exceeded():
    hi = advise(rr=10, side="short", regime="bear_trend",
                strategy_pf=9, strategy_trades=100, level_quality=1.0, atr_pct=2.0)
    lo = advise(rr=0.1, side="short", regime="bull_trend",
                strategy_pf=0.1, strategy_trades=100, level_quality=0.0, atr_pct=50.0)
    assert RISK_MULT_MIN <= lo.risk_mult <= hi.risk_mult <= RISK_MULT_MAX
    assert LEV_CAP_MIN <= lo.leverage_cap <= hi.leverage_cap <= LEV_CAP_MAX


def test_score_rr():
    assert score_rr(None) is None
    assert score_rr(1.0) == 0.0
    assert abs(score_rr(2.0) - 0.5) < 1e-9
    assert score_rr(5.0) == 1.0


def test_regime_alignment():
    assert score_regime_align("long", "bull_trend") == 1.0
    assert score_regime_align("short", "bull_trend") == 0.0
    assert score_regime_align("short", "bear_chop") == 0.75
    assert score_regime_align("long", "bear_chop") == 0.25
    assert score_regime_align(None, "bull_trend") is None


def test_strategy_pf_needs_min_trades():
    assert score_strategy_pf(2.0, trades=3) is None      # мало данных → нейтрально
    assert score_strategy_pf(0.8, trades=20) == 0.0
    assert abs(score_strategy_pf(1.0, trades=20) - 0.4) < 1e-9
    assert score_strategy_pf(1.5, trades=20) == 1.0


def test_vol_sanity_band():
    assert score_vol_sanity(2.0) == 1.0          # здоровая волатильность
    assert score_vol_sanity(0.1) < 0.5           # мёртвый рынок
    assert score_vol_sanity(20.0) < 0.5          # хаос
    assert score_vol_sanity(None) is None


def test_unknown_factors_do_not_penalize():
    # только rr известен и он хорош — уверенность не размазывается неизвестными
    a = advise(rr=3.0)
    assert a.confidence == 1.0
