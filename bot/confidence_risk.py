"""Confidence-based risk sizing — «умное плечо» (Claude 2026-06-10).

Идея владельца: «если уверен — можно и с плечом». Реализация БЕЗ азарта:
плечо аккаунта не трогаем (3x), а уверенность сигнала масштабирует
риск на сделку и потолок notional. Нерушимые рейлы (дневной −2%,
аварийный стоп) остаются выше этого модуля и режут всё.

confidence ∈ [0..1] из независимых факторов; затем:
    risk_mult     = 0.50 + 1.00 * confidence   (0.5x..1.5x базового риска)
    leverage_cap  = 1.0  + 2.00 * confidence   (1x..3x notional/equity на сделку)

Факторы (каждый 0..1, отсутствующий = нейтральный 0.5):
  rr              — risk:reward сигнала (1R→0, 2R→0.5, 3R+→1)
  regime_align    — направление сигнала совпадает с фазой рынка
  strategy_pf     — скользящий live-PF стратегии (PF 0.8→0, 1.0→0.4, 1.5+→1)
  level_quality   — качество уровня (R² трендлайна / касания уровня), 0..1 от стратегии
  vol_sanity      — ATR% в здоровой полосе (мёртвый или бешеный рынок → 0)

Подключение (Codex): в место расчёта qty в smart_pump_reversal_bot
(risk_usd = equity * RISK_PER_TRADE_PCT) добавить
    risk_usd *= advice.risk_mult
    notional  = min(notional, equity * advice.leverage_cap)
+ env-гейт CONFIDENCE_RISK_ENABLE (по умолчанию OFF, сначала shadow-лог).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

RISK_MULT_MIN = 0.50
RISK_MULT_MAX = 1.50
LEV_CAP_MIN = 1.00
LEV_CAP_MAX = 3.00


@dataclass
class RiskAdvice:
    confidence: float      # 0..1
    risk_mult: float       # множитель к базовому риску на сделку
    leverage_cap: float    # потолок notional/equity для ЭТОЙ сделки
    reasons: str           # человекочитаемое объяснение для лога/веба


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def score_rr(rr: Optional[float]) -> Optional[float]:
    """1R→0, 2R→0.5, 3R и выше→1 (линейно)."""
    if rr is None or rr <= 0:
        return None
    return _clamp((float(rr) - 1.0) / 2.0, 0.0, 1.0)


def score_regime_align(side: Optional[str], regime: Optional[str]) -> Optional[float]:
    """long в bull / short в bear → 1; против фазы → 0; chop → 0.5."""
    if not side or not regime:
        return None
    s = str(side).lower()
    r = str(regime).lower()
    bull = "bull" in r
    bear = "bear" in r
    chop = "chop" in r or "flat" in r or "range" in r
    if chop and not (bull or bear):
        return 0.5
    if (bull and s == "long") or (bear and s == "short"):
        return 1.0 if not chop else 0.75
    if (bull and s == "short") or (bear and s == "long"):
        return 0.0 if not chop else 0.25
    return 0.5


def score_strategy_pf(pf: Optional[float], trades: int = 0, min_trades: int = 10) -> Optional[float]:
    """Скользящий live-PF стратегии. Мало сделок → None (нейтрально).
    PF 0.8→0, 1.0→0.4, 1.5+→1."""
    if pf is None or trades < min_trades:
        return None
    p = float(pf)
    if p <= 0.8:
        return 0.0
    if p <= 1.0:
        return 0.4 * (p - 0.8) / 0.2
    return _clamp(0.4 + 0.6 * (p - 1.0) / 0.5, 0.0, 1.0)


def score_vol_sanity(atr_pct: Optional[float], lo: float = 0.5, hi: float = 6.0) -> Optional[float]:
    """ATR% за бар-час: <lo — рынок мёртв (нечего ловить), >hi — хаос.
    Внутри полосы → 1, на границах спадает до 0."""
    if atr_pct is None or atr_pct <= 0:
        return None
    a = float(atr_pct)
    if a < lo:
        return _clamp(a / lo, 0.0, 1.0) * 0.5  # мёртвый рынок максимум 0.5
    if a > hi:
        return _clamp(1.0 - (a - hi) / hi, 0.0, 1.0) * 0.5
    return 1.0


def compute_confidence(factors: Mapping[str, Optional[float]]) -> float:
    """Среднее по ПРИСУТСТВУЮЩИМ факторам (None = фактор не известен).
    Нет ни одного фактора → нейтральные 0.5."""
    vals = [float(v) for v in factors.values() if v is not None]
    if not vals:
        return 0.5
    return _clamp(sum(vals) / len(vals), 0.0, 1.0)


def advise(
    *,
    rr: Optional[float] = None,
    side: Optional[str] = None,
    regime: Optional[str] = None,
    strategy_pf: Optional[float] = None,
    strategy_trades: int = 0,
    level_quality: Optional[float] = None,
    atr_pct: Optional[float] = None,
) -> RiskAdvice:
    factors = {
        "rr": score_rr(rr),
        "regime": score_regime_align(side, regime),
        "pf": score_strategy_pf(strategy_pf, strategy_trades),
        "level": _clamp(level_quality, 0.0, 1.0) if level_quality is not None else None,
        "vol": score_vol_sanity(atr_pct),
    }
    conf = compute_confidence(factors)
    risk_mult = _clamp(RISK_MULT_MIN + (RISK_MULT_MAX - RISK_MULT_MIN) * conf,
                       RISK_MULT_MIN, RISK_MULT_MAX)
    lev_cap = _clamp(LEV_CAP_MIN + (LEV_CAP_MAX - LEV_CAP_MIN) * conf,
                     LEV_CAP_MIN, LEV_CAP_MAX)
    used = ",".join(f"{k}={v:.2f}" for k, v in factors.items() if v is not None) or "none"
    return RiskAdvice(
        confidence=round(conf, 4),
        risk_mult=round(risk_mult, 4),
        leverage_cap=round(lev_cap, 4),
        reasons=f"conf={conf:.2f} [{used}]",
    )
