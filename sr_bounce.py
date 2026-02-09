# sr_bounce.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict
import time
import requests

from sr_levels import LevelsService, Level
from indicators import atr_pct_from_ohlc

# --- kline cache (sr_bounce) ---
_KLINE_CACHE: Dict[tuple, tuple] = {}  # key=(symbol, interval_min, limit) -> (ts, (o,h,l,c,vol,to,t))
PUBLIC_RL_UNTIL = 0
PUBLIC_RL_BACKOFF_SEC = 25

def _fetch_kline_tf_cached(base_url, symbol, interval_min=5, limit=120, ttl_sec=20):
    global PUBLIC_RL_UNTIL

    key = (symbol, int(interval_min), int(limit))
    now = time.time()

    # 1) если мы в backoff-окне после rate limit — не дергаем сеть
    if int(time.time()) < int(PUBLIC_RL_UNTIL or 0):
        hit = _KLINE_CACHE.get(key)
        if hit:
            return hit[1]
        return None

    hit = _KLINE_CACHE.get(key)
    if hit:
        ts, data = hit
        if data is not None and (now - ts) < float(ttl_sec):
            return data

    try:
        data = _fetch_kline_tf(base_url, symbol, interval_min=interval_min, limit=limit)
        _KLINE_CACHE[key] = (now, data)
        return data

    except Exception as e:
        txt = str(e).lower()

        # 2) rate limit -> ставим backoff и возвращаем кэш (даже если "протух")
        if ("10006" in txt) or ("too many visits" in txt) or ("rate limit" in txt):
            PUBLIC_RL_UNTIL = int(time.time()) + int(PUBLIC_RL_BACKOFF_SEC)
            if hit:
                return hit[1]
            return None

        raise


@dataclass
class BounceSignal:
    symbol: str
    side: str              # "Buy" | "Sell"
    level: Level
    entry_price: float
    tp_price: float
    sl_price: float
    potential_pct: float
    breakout_risk: float
    note: str

    # --- diagnostics (for bounce_debug.csv) ---
    ob_pressure: float = 0.0
    atr_5m: float = 0.0
    volume_factor: float = 0.0
    false_breakout: bool = False
    micro_trend_ok: bool = True
    mtf_ok: bool = True


def _fetch_kline_tf(
    base_url: str,
    symbol: str,
    interval_min: int,
    limit: int = 200
) -> Tuple[List[float], List[float], List[float], List[float], List[float], List[float], List[int]]:
    """
    Bybit v5 /market/kline
    interval_min: 1,5,15,60,240...
    returns: o,h,l,c,vol,turnover,t (t in seconds, chronological)

    Bybit list row usually:
    [startTime, open, high, low, close, volume, turnover]
    """
    r = requests.get(
        f"{base_url.rstrip('/')}/v5/market/kline",
        params={"category": "linear", "symbol": symbol, "interval": str(int(interval_min)), "limit": int(limit)},
        timeout=10,
    )
    r.raise_for_status()
    j = r.json()
    if str(j.get("retCode")) != "0":
        raise RuntimeError(f"kline({interval_min}m) error: {j}")

    rows = (j.get("result") or {}).get("list") or []
    rows.reverse()  # chronological

    t = [int(int(x[0]) // 1000) for x in rows]
    o = [float(x[1]) for x in rows]
    h = [float(x[2]) for x in rows]
    l = [float(x[3]) for x in rows]
    c = [float(x[4]) for x in rows]

    vol: List[float] = []
    to: List[float] = []
    for x in rows:
        vol.append(float(x[5]) if len(x) > 5 and x[5] not in (None, "") else 0.0)
        to.append(float(x[6]) if len(x) > 6 and x[6] not in (None, "") else 0.0)

    return o, h, l, c, vol, to, t


def _pick_last_closed_bar(o, h, l, c, t, tf_sec: int):
    """
    На Bybit последняя свеча иногда ещё формируется.
    Берём последнюю "закрытую" по времени. Если не уверены — берём предпоследнюю.
    """
    if not t:
        return None

    now = int(time.time())
    if len(t) >= 1 and (t[-1] + tf_sec <= now + 2):
        idx = -1
    else:
        idx = -2 if len(t) >= 2 else -1

    return (o[idx], h[idx], l[idx], c[idx], t[idx])


def _atr_pct_from_ohlc(h: List[float], l: List[float], c: List[float], period: int = 14) -> float:
    """
    Обёртка над indicators.atr_pct_from_ohlc для совместимости со старым кодом.
    """
    return atr_pct_from_ohlc(h, l, c, period=period, fallback=0.8)


def _candle_stats(o: float, h: float, l: float, c: float) -> Dict[str, float]:
    rng = max(1e-9, h - l)
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    up = 1.0 if c > o else 0.0
    return {
        "range": rng,
        "body": body,
        "body_pct": (body / rng) * 100.0,
        "upper": upper,
        "lower": lower,
        "up": up,
    }


def _breakout_risk(
    o: List[float],
    h: List[float],
    l: List[float],
    c: List[float],
    *,
    level: float,
    kind: str,
    tol_pct: float
) -> float:
    """
    0..1: риск пробоя (на signal TF, обычно 5m).
    Эвристика:
    - много касаний уровня
    - поджатие (higher lows под R / lower highs над S)
    - импульс последних баров в сторону пробоя
    """
    if len(c) < 40:
        return 0.25

    look = min(30, len(c) - 1)

    touches = 0
    for i in range(-look, 0):
        near_hi = abs(h[i] - level) / max(1e-9, level) * 100.0 <= tol_pct
        near_lo = abs(l[i] - level) / max(1e-9, level) * 100.0 <= tol_pct
        if near_hi or near_lo:
            touches += 1
    touch_factor = min(1.0, touches / 8.0)

    squeeze = 0.0
    if kind == "resistance":
        lows = l[-11:-1]
        if lows and lows[-1] > lows[0]:
            squeeze = 1.0
    else:
        highs = h[-11:-1]
        if highs and highs[-1] < highs[0]:
            squeeze = 1.0

    mom = 0.0
    diffs = [c[i] - c[i - 1] for i in range(len(c) - 6, len(c))]
    up_n = sum(1 for d in diffs if d > 0)
    dn_n = sum(1 for d in diffs if d < 0)
    if kind == "resistance" and up_n >= 5:
        mom = 1.0
    if kind == "support" and dn_n >= 5:
        mom = 1.0

    risk = 0.12 + 0.42 * squeeze + 0.33 * touch_factor + 0.23 * mom
    return max(0.0, min(1.0, risk))


def _ema(series: List[float], length: int) -> float:
    if not series:
        return 0.0
    alpha = 2.0 / (length + 1.0)
    ema = series[0]
    for x in series[1:]:
        ema = alpha * x + (1.0 - alpha) * ema
    return ema


def _check_micro_trend(c: List[float], kind: str) -> bool:
    """
    kind: "support" or "resistance"
    """
    if len(c) < 30:
        return True
    fast = _ema(c[-30:], 10)
    slow = _ema(c[-30:], 20)
    return (fast > slow) if kind == "support" else (fast < slow)


def _volume_factor(turnover: List[float], recent_n: int, avg_n: int) -> float:
    if not turnover or len(turnover) < max(recent_n, avg_n) + 5:
        return 0.0
    recent = sum(turnover[-recent_n:]) / float(recent_n)
    avg = sum(turnover[-avg_n:]) / float(avg_n)
    if avg <= 0:
        return 0.0
    return recent / avg


def _check_false_breakout(
    h: List[float],
    l: List[float],
    c: List[float],
    *,
    level: float,
    kind: str,
    tol_pct: float,
    lookback: int = 6
) -> bool:
    if len(c) < lookback + 2:
        return False

    pierce_pct = max(0.08, min(0.35, tol_pct * 0.8))  # 0.08%..0.35%

    if kind == "support":
        for i in range(-lookback, -1):
            if l[i] < level * (1.0 - pierce_pct / 100.0) and c[i] > level:
                return True
    else:
        for i in range(-lookback, -1):
            if h[i] > level * (1.0 + pierce_pct / 100.0) and c[i] < level:
                return True

    return False


def _mtf_alignment(base_url: str, symbol: str, kind: str) -> bool:
    """
    Простая MTF проверка на 15m:
    - support bounce: не должно быть сильного слива
    - resistance bounce: не должно быть сильного роста
    """
    try:
        bars = _fetch_kline_tf_cached(
            base_url,
            symbol,
            interval_min=15,
            limit=60,
            ttl_sec=30
        )
        if not bars:
            return True
        _o, _h, _l, c15, _v, _to, _t = bars


        if len(c15) < 25:
            return True
        recent = c15[-20:]
        if kind == "support":
            return recent[-1] > recent[0] * 0.985
        else:
            return recent[-1] < recent[0] * 1.015
    except Exception:
        return True


class BounceStrategy:
    def __init__(self, base_url: str, levels: LevelsService):
        self.base_url = base_url.rstrip("/")
        self.levels = levels

        # === параметры ===
        self.signal_tf_min = 5

        self.check_cooldown_sec = 30
        self.near_level_tol_mul = 1.5

        self.touch_tol_pct = 0.12
        self.confirm_pct = 0.06
        self.max_level_dist_pct = 1.2
        self.cooldown_bars = 6

        self.approach_lookback = 60
        self.approach_min_dist_pct = 0.15

        # ВАЖНО: body_pct уже в процентах 0..100
        self.min_body_pct = 12.0
        self.wick_mul = 0.9

        self.breakout_risk_max = 0.70
        self.min_potential_pct = 1.5

        self.sl_pct = 1.0
        self.rr = 2.0

        self.max_hold_sec = 3 * 3600

        # === runtime state ===
        self._last_check_ts: Dict[str, int] = {}
        self._level_cooldown: Dict[tuple, int] = {}

        # --- feature flags ---
        self.use_micro_trend = False
        self.use_false_breakout_bonus = True
        self.use_volume_filter = False
        self.use_mtf_alignment = False

        # volume filter params (по turnover)
        self.min_volume_factor = 0.30
        self.volume_avg_bars = 50
        self.volume_recent_bars = 10

    def try_signal(self, symbol: str, price: float, orderbook_pressure: Optional[float] = None) -> Optional[BounceSignal]:
        now = int(time.time())
        last = self._last_check_ts.get(symbol, 0)
        if now - last < self.check_cooldown_sec:
            return None
        self._last_check_ts[symbol] = now

        levels, meta = self.levels.get(symbol)

        tol1 = float(meta.get("tol_1h_pct", 0.35))
        tol4 = float(meta.get("tol_4h_pct", 0.35))
        tol = min(tol1, tol4) * self.near_level_tol_mul

        lv = self.levels.best_near(levels, price, tol_pct=tol, tf_prefer="4h")
        if not lv:
            return None

        dist_pct = abs(price - lv.price) / max(1e-9, lv.price) * 100.0
        if dist_pct > self.max_level_dist_pct:
            return None

        tf_sec = int(self.signal_tf_min * 60)
        need_bars = max(120, self.approach_lookback + 30)
        bars = _fetch_kline_tf_cached(
            self.base_url,
            symbol,
            interval_min=self.signal_tf_min,
            limit=need_bars,
            ttl_sec=15
        )
        if not bars:
            return None
        o, h, l, c, vol, to, t = bars



        bar = _pick_last_closed_bar(o, h, l, c, t, tf_sec=tf_sec)
        if not bar:
            return None
        last_o, last_h, last_l, last_c, last_ts = bar

        key = (symbol, lv.kind, round(lv.price, 6))
        prev_ts = self._level_cooldown.get(key, 0)
        if prev_ts and (last_ts - prev_ts) < int(self.cooldown_bars * tf_sec):
            return None

        # diagnostics
        atr_5m = float(_atr_pct_from_ohlc(h, l, c, 14))
        ob = float(orderbook_pressure) if orderbook_pressure is not None else 0.5

        vol_factor = 0.0
        if self.use_volume_filter:
            vol_factor = float(_volume_factor(to, self.volume_recent_bars, self.volume_avg_bars))
            if vol_factor > 0 and vol_factor < self.min_volume_factor:
                return None

        micro_ok = True
        if self.use_micro_trend:
            micro_ok = bool(_check_micro_trend(c, lv.kind))
            if not micro_ok:
                return None

        mtf_ok = True
        if self.use_mtf_alignment:
            mtf_ok = bool(_mtf_alignment(self.base_url, symbol, lv.kind))
            if not mtf_ok:
                return None

        # breakout risk + стакан
        risk = float(_breakout_risk(o, h, l, c, level=lv.price, kind=lv.kind, tol_pct=tol))
        if lv.kind == "support" and ob > 0.55:
            risk *= 1.25
        elif lv.kind == "resistance" and ob < 0.45:
            risk *= 1.25
        risk = max(0.0, min(1.0, risk))
        if risk >= self.breakout_risk_max:
            return None

        # approach filter
        look = min(self.approach_lookback, len(c) - 5)
        if look >= 10:
            closes = c[-(look + 1):-1]
            if lv.kind == "support":
                came_from_far = (max(closes) >= lv.price * (1.0 + self.approach_min_dist_pct / 100.0))
            else:
                came_from_far = (min(closes) <= lv.price * (1.0 - self.approach_min_dist_pct / 100.0))
            if not came_from_far:
                return None

        # last candle reaction
        st = _candle_stats(last_o, last_h, last_l, last_c)
        if st["body_pct"] < self.min_body_pct:
            return None

        # false breakout bonus
        false_br = False
        if self.use_false_breakout_bonus:
            false_br = bool(_check_false_breakout(h, l, c, level=lv.price, kind=lv.kind, tol_pct=tol, lookback=6))
            if false_br:
                risk = max(0.0, min(1.0, risk * 0.70))

        if lv.kind == "support":
            touched = last_l <= lv.price * (1.0 + self.touch_tol_pct / 100.0)
            bullish = last_c > last_o
            confirm = last_c >= lv.price * (1.0 + self.confirm_pct / 100.0)
            wick_ok = st["lower"] >= self.wick_mul * st["body"]
            if not (touched and bullish and confirm and wick_ok):
                return None

            nxt = self.levels.nearest_above(levels, price, kind_filter="resistance")
            if not nxt:
                return None
            potential_pct = (nxt.price - price) / max(1e-9, price) * 100.0

            tp_pct = float(self.sl_pct * self.rr)
            if potential_pct < max(self.min_potential_pct, 0.90 * tp_pct):
                return None

            sl = price * (1.0 - self.sl_pct / 100.0)
            tp = price * (1.0 + tp_pct / 100.0)

            self._level_cooldown[key] = last_ts
            return BounceSignal(
                symbol=symbol,
                side="Buy",
                level=lv,
                entry_price=price,
                tp_price=tp,
                sl_price=sl,
                potential_pct=potential_pct,
                breakout_risk=risk,
                note=f"bounce SUPPORT ({lv.tf}); next R≈{nxt.price:.6f}; max_hold={self.max_hold_sec}s",
                ob_pressure=ob,
                atr_5m=atr_5m,
                volume_factor=vol_factor,
                false_breakout=false_br,
                micro_trend_ok=micro_ok,
                mtf_ok=mtf_ok,
            )

        else:  # resistance
            touched = last_h >= lv.price * (1.0 - self.touch_tol_pct / 100.0)
            bearish = last_c < last_o
            confirm = last_c <= lv.price * (1.0 - self.confirm_pct / 100.0)
            wick_ok = st["upper"] >= self.wick_mul * st["body"]
            if not (touched and bearish and confirm and wick_ok):
                return None

            nxt = self.levels.nearest_below(levels, price, kind_filter="support")
            if not nxt:
                return None
            potential_pct = (price - nxt.price) / max(1e-9, price) * 100.0

            tp_pct = float(self.sl_pct * self.rr)
            if potential_pct < max(self.min_potential_pct, 0.90 * tp_pct):
                return None

            sl = price * (1.0 + self.sl_pct / 100.0)
            tp = price * (1.0 - tp_pct / 100.0)

            self._level_cooldown[key] = last_ts
            return BounceSignal(
                symbol=symbol,
                side="Sell",
                level=lv,
                entry_price=price,
                tp_price=tp,
                sl_price=sl,
                potential_pct=potential_pct,
                breakout_risk=risk,
                note=f"bounce RESIST ({lv.tf}); next S≈{nxt.price:.6f}; max_hold={self.max_hold_sec}s",
                ob_pressure=ob,
                atr_5m=atr_5m,
                volume_factor=vol_factor,
                false_breakout=false_br,
                micro_trend_ok=micro_ok,
                mtf_ok=mtf_ok,
            )
