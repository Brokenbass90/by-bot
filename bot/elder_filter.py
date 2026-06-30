"""Elder-style directional confluence FILTER (not a standalone strategy).

Elder's triple screen works best as a *confluence gate* on top of other legs:
screen-1 (the "tide": higher-timeframe trend via EMA fast/slow + MACD histogram)
tells you which side is allowed; screen-2 (the "wave": Force Index / RSI) confirms
timing. ETS as a standalone crypto strategy underperformed (see elder_crypto_v1
notes) -> here it only ANDs with a leg's own signal.

Used so legs stay one-directional and trade *with* (or at least not against) the
tide:
  * a LONG-only bounce fires only when `allow_long`  (tide not bearish);
  * a SHORT-only fade fires only when `allow_short`  (tide not bullish);
  * `require_with_tide=True` is stricter: allow only WITH the tide.

Row format: [ts, open, high, low, close, volume]. Pure stdlib.
Pass `htf_rows` (higher timeframe) for screen-1; else screen-1 uses `rows`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

TS, OPEN, HIGH, LOW, CLOSE, VOL = 0, 1, 2, 3, 4, 5


def _col(rows: Sequence[Sequence[float]], i: int) -> List[float]:
    out = []
    for r in rows:
        try:
            out.append(float(r[i]))
        except (IndexError, TypeError, ValueError):
            out.append(float("nan"))
    return out


def _ema_series(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(v * k + ema[-1] * (1.0 - k))
    return ema


def _macd_hist(closes: List[float], fast: int, slow: int, signal: int) -> float:
    if len(closes) < slow + signal:
        return float("nan")
    ef = _ema_series(closes, fast)
    es = _ema_series(closes, slow)
    macd_line = [a - b for a, b in zip(ef, es)]
    sig = _ema_series(macd_line, signal)
    return macd_line[-1] - sig[-1]


def _force_index(closes: List[float], vols: List[float], period: int = 13) -> float:
    if len(closes) < period + 2:
        return float("nan")
    fi = [(closes[i] - closes[i - 1]) * vols[i] for i in range(1, len(closes))]
    return _ema_series(fi, period)[-1]


def _rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return float("nan")
    gains = losses = 0.0
    for i in range(len(closes) - period, len(closes)):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - 100.0 / (1.0 + rs)


@dataclass
class ElderBias:
    ok: bool
    tide: str                # "up" | "down" | "flat"
    wave: str                # "up" | "down" | "flat"
    bias: str                # "long" | "short" | "neutral"
    allow_long: bool
    allow_short: bool
    ema_fast: float
    ema_slow: float
    macd_hist: float
    force_index: float
    rsi: float
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def elder_bias(
    rows: Sequence[Sequence[float]],
    *,
    htf_rows: Optional[Sequence[Sequence[float]]] = None,
    ema_fast: int = 50,
    ema_slow: int = 200,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    force_period: int = 13,
    rsi_period: int = 14,
    require_with_tide: bool = False,
    min_tide_sep_frac: float = 0.0005,   # |EMA_fast-EMA_slow|/price >= this to count as a tide
) -> ElderBias:
    """Compute Elder tide+wave confluence and long/short permission gates."""
    blank = ElderBias(
        ok=False, tide="flat", wave="flat", bias="neutral",
        allow_long=True, allow_short=True, ema_fast=float("nan"), ema_slow=float("nan"),
        macd_hist=float("nan"), force_index=float("nan"), rsi=float("nan"),
        reason="insufficient_data",
    )
    s1 = htf_rows if htf_rows is not None else rows
    closes1 = _col(s1, CLOSE)
    # need enough for the slow EMA + macd; degrade gracefully with a shorter slow
    eff_slow = ema_slow if len(closes1) >= ema_slow else max(ema_fast + 1, len(closes1) // 2)
    if len(closes1) < max(ema_fast + 1, macd_slow + macd_signal):
        return blank

    ef_series = _ema_series(closes1, ema_fast)
    es_series = _ema_series(closes1, eff_slow)
    ef, es = ef_series[-1], es_series[-1]
    mh = _macd_hist(closes1, macd_fast, macd_slow, macd_signal)
    price1 = closes1[-1]

    # screen 1: tide (require a MEANINGFUL EMA separation; float-safe vs ~equal EMAs)
    sep = (ef - es) / price1 if price1 else 0.0
    if sep >= min_tide_sep_frac and (mh != mh or mh >= 0) and price1 >= ef:
        tide = "up"
    elif sep <= -min_tide_sep_frac and (mh != mh or mh <= 0) and price1 <= ef:
        tide = "down"
    else:
        tide = "flat"

    # screen 2: wave (on the trading timeframe)
    closes2 = _col(rows, CLOSE)
    vols2 = _col(rows, VOL)
    fi = _force_index(closes2, vols2, force_period)
    rsi = _rsi(closes2, rsi_period)
    if fi == fi and fi > 0:
        wave = "up"
    elif fi == fi and fi < 0:
        wave = "down"
    else:
        wave = "flat"

    # bias = tide, confirmed by wave when they agree
    if tide == "up":
        bias = "long"
    elif tide == "down":
        bias = "short"
    else:
        bias = "neutral"

    if require_with_tide:
        allow_long = (tide == "up")
        allow_short = (tide == "down")
    else:
        allow_long = (tide != "down")     # block longs only against a clear downtide
        allow_short = (tide != "up")      # block shorts only against a clear uptide

    reason = f"tide_{tide}_wave_{wave}"
    return ElderBias(
        ok=True, tide=tide, wave=wave, bias=bias, allow_long=bool(allow_long),
        allow_short=bool(allow_short), ema_fast=ef, ema_slow=es, macd_hist=mh,
        force_index=fi, rsi=rsi, reason=reason,
        extra={"require_with_tide": require_with_tide, "eff_slow": eff_slow},
    )
