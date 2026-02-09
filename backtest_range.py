#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import math
import argparse
import datetime as dt
import csv
import asyncio
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Any, Dict

import requests
from collections import deque, defaultdict

import random
import requests
from requests.exceptions import RequestException

from sr_range import Candle, normalize_klines
from sr_range_strategy import RangeStrategy, RangeSignal

# После частичного TP1 поднимаем SL выше BE на долю пути до TP1 (фиксируем прибыль)
POST_TP1_LOCK_FRAC = 0.25  # 0.25 = 25% пути от entry до TP1

# ------------------------- models -------------------------

@dataclass
class SimTrade:
    symbol: str
    side: str
    entry_ts: int
    entry: float
    sl: float
    tp: float
    reason: str
    qty: float
    notional_entry: float

    init_sl: float = 0.0
    init_tp: float = 0.0
    moved_to_be: bool = False

    exit_ts: Optional[int] = None
    exit: Optional[float] = None
    notional_exit: Optional[float] = None
    pnl: Optional[float] = None
    fee_paid: Optional[float] = None
    funding_cost: Optional[float] = None
    exit_reason: Optional[str] = None

    qty_init: float = 0.0
    fee_accum: float = 0.0
    realized_gross: float = 0.0
    partial_taken: bool = False
    tp1: float = 0.0  # TP1 price (mid), 0 = disabled
    # analytics
    init_r_usdt: float = 0.0
    r_mult: float = 0.0
    range_width_pct: float = 0.0
    range_er: float = 0.0
    range_atr: float = 0.0
    pos_entry: float = 0.0
    tp_policy: str = ""   # "mid" | "opp"




# ------------------------- time helpers -------------------------

def parse_date_ms(s: str) -> int:
    d = dt.datetime.strptime(s, "%Y-%m-%d")
    return int(d.replace(tzinfo=dt.timezone.utc).timestamp() * 1000)

def ms_to_iso(ms: int) -> str:
    return dt.datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
def fmt_px(x: float) -> str:
    x = float(x)
    if x >= 1000:
        return f"{x:.2f}"
    if x >= 1:
        return f"{x:.4f}"
    return f"{x:.6f}"
def ensure_ts_ms(candles: List[Candle]) -> List[Candle]:
    if not candles:
        return candles
    if candles[0].ts < 100_000_000_000:
        return [Candle(ts=c.ts * 1000, o=c.o, h=c.h, l=c.l, c=c.c, v=c.v) for c in candles]
    return candles

def http_get_json(url: str, params: dict, *, timeout: int = 30,
                  retries: int = 7, backoff: float = 0.6, backoff_max: float = 8.0) -> dict:
    """
    Надёжный GET с ретраями и экспоненциальным backoff.
    Лечит ConnectionResetError/ProtocolError/временные проблемы сети/429/5xx.
    """
    delay = float(backoff)
    last_err: Optional[Exception] = None

    for attempt in range(int(retries)):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            data = r.json()

            # Bybit иногда возвращает retCode != 0 даже при HTTP 200
            rc = data.get("retCode", 0)
            if isinstance(rc, str):
                try:
                    rc = int(rc)
                except Exception:
                    rc = 0

            if rc not in (0, None):
                raise RuntimeError(f"Bybit retCode={rc} retMsg={data.get('retMsg')}")

            return data

        except Exception as e:
            last_err = e
            if attempt >= int(retries) - 1:
                break

            # jitter + backoff
            jitter = delay * (0.15 + 0.25 * random.random())
            time.sleep(delay + jitter)
            delay = min(float(backoff_max), delay * 2.0)

    raise RuntimeError(f"HTTP GET failed after {retries} retries: {last_err}")


# ------------------------- bybit downloader -------------------------

def bybit_kline_public(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    base: str,
    *,
    limit: int = 1000,
    sleep_sec: float = 0.08,
) -> List[Candle]:
    base = base.rstrip("/")
    interval = str(interval)
    step_ms = int(interval) * 60_000

    out: List[Candle] = []
    seen: set[int] = set()

    cursor = start_ms
    req = 0

    while cursor < end_ms:
        req += 1
        window_end = min(end_ms, cursor + step_ms * limit)

        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "start": cursor,
            "end": window_end,
            "limit": limit,
        }
        data = http_get_json(base + "/v5/market/kline", params, timeout=30)

        rows = (data.get("result") or {}).get("list") or []
        candles = ensure_ts_ms(normalize_klines(rows))
        if not candles:
            cursor = window_end
            time.sleep(sleep_sec)
            continue

        candles.sort(key=lambda c: c.ts)

        added = 0
        for c in candles:
            if c.ts in seen:
                continue
            if start_ms <= c.ts < end_ms:
                out.append(c)
                seen.add(c.ts)
                added += 1

        last_ts = candles[-1].ts
        next_cursor = last_ts + step_ms
        if next_cursor <= cursor:
            raise RuntimeError(f"Cursor not advancing: cursor={cursor} next={next_cursor}")
        cursor = next_cursor

        time.sleep(sleep_sec)
        if len(candles) < 2:
            cursor = window_end

    out.sort(key=lambda c: c.ts)
    return out

def bybit_top_symbols_by_turnover(base: str, top_n: int, *, min_turnover24h: float = 0.0) -> List[str]:
    base = base.rstrip("/")
    params = {"category": "linear"}
    data = http_get_json(base + "/v5/market/tickers", params, timeout=30)

    rows = (data.get("result") or {}).get("list") or []
    items = []

    for x in rows:
        sym = x.get("symbol")
        if not sym or not sym.endswith("USDT"):
            continue

        try:
            tov = float(x.get("turnover24h") or 0.0)
        except Exception:
            tov = 0.0

        # фильтр ликвидности — ВНУТРИ цикла
        if tov < float(min_turnover24h):
            continue

        items.append((tov, sym))

    items.sort(reverse=True, key=lambda t: t[0])
    return [sym for _, sym in items[:top_n]]

# ------------------------- aggregation -------------------------

def aggregate_candles(c_base: List[Candle], tf_minutes: int) -> List[Candle]:
    out: List[Candle] = []
    if not c_base:
        return out

    tf_minutes = int(tf_minutes)
    if tf_minutes <= 0:
        return out

    tf_ms = tf_minutes * 60 * 1000

    def bucket(ts_ms: int) -> int:
        return (int(ts_ms) // tf_ms) * tf_ms

    cur: Optional[Candle] = None
    cur_bucket: Optional[int] = None

    for c in c_base:
        b = bucket(c.ts)
        if cur_bucket is None or b != cur_bucket:
            if cur is not None:
                out.append(cur)
            cur_bucket = b
            cur = Candle(ts=b, o=c.o, h=c.h, l=c.l, c=c.c, v=c.v)
        else:
            cur.h = max(cur.h, c.h)
            cur.l = min(cur.l, c.l)
            cur.c = c.c
            cur.v += c.v

    if cur is not None:
        out.append(cur)

    out.sort(key=lambda x: x.ts)
    return out

# ------------------------- indicators for scanning -------------------------

def atr_from_candles(c: List[Candle], period: int) -> float:
    if not c or len(c) < period + 2:
        return 0.0
    trs = []
    for i in range(1, len(c)):
        h, l = float(c[i].h), float(c[i].l)
        pc = float(c[i - 1].c)
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    last = trs[-period:]
    return sum(last) / max(1, len(last))

def efficiency_ratio(closes: List[float], period: int) -> float:
    if len(closes) < period + 1:
        return 1.0
    start = closes[-period - 1]
    end = closes[-1]
    net = abs(end - start)
    den = 0.0
    for i in range(len(closes) - period, len(closes)):
        den += abs(closes[i] - closes[i - 1])
    return net / max(1e-12, den)

def percentile(sorted_vals: List[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    p = max(0.0, min(1.0, p))
    idx = int(p * (len(sorted_vals) - 1))
    return sorted_vals[idx]

def range_score_1h(
    candles: List[Candle],
    *,
    bar_minutes: int,
    range_bars: int,
    min_range_bars: int,
    min_width_pct: float,
    max_width_pct: float,
    atr_period: int,
    er_period: int,
    er_max: float,
) -> Tuple[float, Dict[str, float]]:
    """
    Скоринг боковика на любом TF.
    range_bars/min_range_bars — количество баров (уже пересчитанное из часов).
    """
    if len(candles) < int(min_range_bars):
        return (0.0, {"ok": 0})

    window = candles[-int(range_bars):]
    if len(window) < int(min_range_bars):
        return (0.0, {"ok": 0})

    lows = sorted([float(x.l) for x in window])
    highs = sorted([float(x.h) for x in window])

    q = 0.10 if len(window) < 40 else 0.05
    support = percentile(lows, q)
    resistance = percentile(highs, 1.0 - q)
    mid = (support + resistance) / 2.0
    width = resistance - support
    width_pct = width / max(1e-12, mid)

    if not (width > 0 and float(min_width_pct) <= width_pct <= float(max_width_pct)):
        return (0.0, {"ok": 0, "width_pct": width_pct})

    closes = [float(x.c) for x in window]
    er = efficiency_ratio(closes, int(er_period))

    drift = abs(closes[-1] - closes[0])
    if drift > 0.35 * width:
        return (0.0, {"ok": 0, "width_pct": width_pct, "er": er, "drift": drift})

    if er > float(er_max):
        return (0.0, {"ok": 0, "width_pct": width_pct, "er": er})

    atr = atr_from_candles(window, int(atr_period))
    band = max(0.05 * width, 0.50 * atr)

    touch_s = sum(1 for x in window if float(x.l) <= support + band)
    touch_r = sum(1 for x in window if float(x.h) >= resistance - band)

    # Требование касаний масштабируем под TF:
    # 1H -> 6, 2H -> 3, 4H -> 3 (минимум 3, иначе слишком либерально)
    touch_req = max(4, int(math.ceil(8.0 * (60.0 / max(1.0, float(bar_minutes))))))


    if touch_s < touch_req or touch_r < touch_req:
        return (0.0, {"ok": 0, "width_pct": width_pct, "er": er, "touch_s": float(touch_s), "touch_r": float(touch_r)})

    mn = max(1, min(touch_s, touch_r))
    mx = max(touch_s, touch_r)
    if mx / mn > 3.0:
        return (0.0, {"ok": 0, "width_pct": width_pct, "er": er, "touch_s": float(touch_s), "touch_r": float(touch_r)})

    # бонус за возвраты к mid (mean reversion)
    mid_band = max(0.10 * width, 0.75 * atr)
    reverts = sum(1 for x in window if abs(float(x.c) - mid) <= mid_band)

    score = 40.0
    score += min(touch_s, touch_req * 2) * 6.0
    score += min(touch_r, touch_req * 2) * 6.0
    score += min(reverts / max(1, len(window)) * 100.0, 20.0)
    score -= 20.0 * (width_pct / max(1e-12, float(max_width_pct)))
    score = max(0.0, score)

    meta = {
        "ok": 1,
        "score": score,
        "support": support,
        "resistance": resistance,
        "mid": mid,
        "width_pct": width_pct,
        "atr": atr,
        "er": er,
        "touch_s": float(touch_s),
        "touch_r": float(touch_r),
        "touch_req": float(touch_req),
        "reverts": float(reverts),
        "q": float(q),
    }
    return (score, meta)

# ------------------------- execution model -------------------------

def apply_exit_slippage(side: str, px: float, slippage: float, reason: str) -> float:
    """
    Всегда "в худшую сторону" (консервативно).
    TP — мягче, SL/BE/TIME/EOD — жёстче.
    """
    base = float(slippage)
    slip = base * (0.60 if reason == "TP" else 1.20)
    if side == "Buy":
        return float(px) * (1.0 - slip)  # закрытие лонга продажей -> ниже
    return float(px) * (1.0 + slip)      # закрытие шорта покупкой -> выше


def _csv_open_append(path: str, fieldnames: List[str]):
    if not path:
        return None, None
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    f = open(path, "a", newline="")
    w = csv.DictWriter(f, fieldnames=fieldnames)
    if not exists:
        w.writeheader()
    return f, w


def candle_hits_sl_tp(
    c: Candle,
    side: str,
    sl: float,
    tp: float,
    intrabar_fill: str = "pessimistic",
) -> Optional[Tuple[str, float]]:
    o = float(getattr(c, "o", 0.0))
    h = float(c.h)
    l = float(c.l)
    cl = float(getattr(c, "c", 0.0))

    def tie_break(sl_px: float, tp_px: float) -> Tuple[str, float]:
        mode = str(intrabar_fill)
        if mode == "pessimistic":
            return ("SL", sl_px)
        if mode == "optimistic":
            return ("TP", tp_px)
        if mode == "random":
            return ("TP", tp_px) if random.random() < 0.5 else ("SL", sl_px)

        # heuristic (your current model)
        if side == "Buy":
            # bullish => open->low->high->close => SL first
            return ("SL", sl_px) if cl >= o else ("TP", tp_px)
        else:
            # Sell: bullish => open->low->high => TP first
            return ("TP", tp_px) if cl >= o else ("SL", sl_px)

    if side == "Buy":
        hit_sl = l <= sl
        hit_tp = h >= tp
        if hit_sl and hit_tp:
            return tie_break(sl, tp)
        if hit_sl:
            return ("SL", sl)
        if hit_tp:
            return ("TP", tp)
    else:
        hit_sl = h >= sl
        hit_tp = l <= tp
        if hit_sl and hit_tp:
            return tie_break(sl, tp)
        if hit_sl:
            return ("SL", sl)
        if hit_tp:
            return ("TP", tp)

    return None

def calc_position_size_usdt(
    equity: float,
    risk_pct: float,
    entry: float,
    sl: float,
    cap_notional: float,
    min_notional: float,
) -> Tuple[float, float]:
    """
    Исправленная версия.
    cap_notional теперь является МЯГКИМ лимитом, а не жёстким обрезчиком размера.
    """
    stop_dist = abs(entry - sl)
    if entry <= 0 or stop_dist <= 0:
        return (0.0, 0.0)

    risk_usdt = max(0.0, equity * risk_pct)
    stop_dist_pct = stop_dist / entry
    if stop_dist_pct <= 0:
        return (0.0, 0.0)

    # 1. Рассчитываем ИДЕАЛЬНЫЙ номинал по риску
    notional_target = risk_usdt / stop_dist_pct

    # 2. Применяем МЯГКИЙ лимит (cap_notional). Если целевой номинал больше лимита,
    #    мы не обрезаем его, а ПРЕДУПРЕЖДАЕМ, что риск будет меньше запланированного.
    if cap_notional > 0 and notional_target > cap_notional:
        # Вместо обрезки до cap_notional, мы просто используем cap_notional,
        # что уменьшит ФАКТИЧЕСКИЙ риск (risk_usdt_final).
        # Это лучше, чем вообще не входить.
        notional = cap_notional
        # Для прозрачности можно залогировать:
        # print(f"WARN: Target notional {notional_target:.2f} > cap {cap_notional}. Using {notional:.2f}.")
    else:
        notional = notional_target

    # 3. Проверяем АБСОЛЮТНЫЙ минимум. Если рынок слишком мал для нашего минимального номинала - пропускаем.
    if notional < min_notional:
        return (0.0, 0.0)

    qty = notional / entry
    return (qty, notional)


# ------------------------- minimal range registry -------------------------

class SimpleRangeInfo:
    def __init__(
        self,
        support: float,
        resistance: float,
        *,
        width_pct: float = 0.0,
        er: float = 1.0,
        atr: float = 0.0,
        active: bool = True,
        bad_streak: int = 0,
        last_good_ts: int = 0,
    ):
        self.support = float(support)
        self.resistance = float(resistance)
        self.mid = (self.support + self.resistance) / 2.0
        self.width = self.resistance - self.support

        self.width_pct = float(width_pct)
        self.er = float(er)
        self.atr = float(atr)
        self.active = bool(active)

        # hysteresis
        self.bad_streak = int(bad_streak)
        self.last_good_ts = int(last_good_ts)


class SimpleRangeRegistry:
    def __init__(self):
        self._m: Dict[str, SimpleRangeInfo] = {}

    def get(self, symbol: str):
        return self._m.get(symbol)

    def set(self, symbol: str, info: SimpleRangeInfo):
        self._m[symbol] = info

    def disable(self, symbol: str) -> None:
        info = self._m.get(symbol)
        if info:
            info.active = False

    def is_allowed(self, symbol: str) -> bool:
        info = self._m.get(symbol)
        return bool(info and info.active)



# ------------------------- feed for RangeStrategy.fetch_klines -------------------------

class HistoryFeed:
    def __init__(self, candles_5m: List[Candle]):
        self.c5 = candles_5m
        self.i = 0

    def set_index(self, i: int) -> None:
        self.i = i

    def fetch_klines(self, symbol: str, tf: str, limit: int) -> Any:
        tf = str(tf)
        limit = int(limit)
        if tf != "5":
            return []
        start = max(0, self.i - limit + 1)
        subset = self.c5[start:self.i + 1]
        return [
            {"startTime": int(c.ts), "open": c.o, "high": c.h, "low": c.l, "close": c.c, "volume": c.v}
            for c in subset
        ]


# ------------------------- stats helpers -------------------------
class OnlineQualityFilter:
    """
    Soft OQ:
    - не баним рынок по каждому шуму
    - считаем PF и winrate по окну
    - даём risk multiplier 1.0 / 0.7 / 0.4
    - hard-ban только если совсем плохо (ниже 70% порогов)
    """
    def __init__(self, window_trades: int, min_trades: int,
                 pf_min: float, winrate_min: float,
                 ban_hours: int):
        self.window_trades = int(window_trades)
        self.min_trades = int(min_trades)
        self.pf_min = float(pf_min)
        self.winrate_min = float(winrate_min)
        self.ban_hours = int(ban_hours)

        self.r_window = deque(maxlen=self.window_trades)

        self.ban_until_ms = 0

    def allowed(self, ts_ms: int) -> bool:
        return int(ts_ms) >= int(self.ban_until_ms)

    def _stats(self) -> Tuple[float, float]:
        if len(self.r_window) < max(1, self.min_trades):
            return (float("inf"), 1.0)
        gp = sum(x for x in self.r_window if x > 0)
        gl = -sum(x for x in self.r_window if x < 0)
        pf = (gp / gl) if gl > 0 else float("inf")
        winrate = sum(1 for x in self.r_window if x > 0) / max(1, len(self.r_window))
        return pf, winrate


    def risk_multiplier(self) -> float:
        """
        Возвращает коэффициент риска:
        - 1.0 если качество >= порогов
        - 0.7 если около порогов
        - 0.4 если заметно ниже
        """
        if len(self.r_window) < max(1, self.min_trades):
            return 1.0
        pf, wr = self._stats()

        if pf >= self.pf_min and wr >= self.winrate_min:
            return 1.0

        if pf >= self.pf_min * 0.90 and wr >= self.winrate_min * 0.90:
            return 0.7

        return 0.4

    def update_on_close(self, r_mult: float, ts_ms: int) -> None:
        self.r_window.append(float(r_mult))
        if len(self.r_window) < max(1, self.min_trades):
            return

        pf, wr = self._stats()

        # hard-ban только если совсем плохо (ниже 70% от порогов)
        if pf < self.pf_min * 0.70 and wr < self.winrate_min * 0.70:
            self.ban_until_ms = max(self.ban_until_ms, int(ts_ms) + self.ban_hours * 3600_000)

def calc_max_drawdown(equity_curve: List[Tuple[int, float]]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0][1]
    max_dd = 0.0
    for _, eq in equity_curve:
        if eq > peak:
            peak = eq
        max_dd = max(max_dd, peak - eq)
    return max_dd


# ------------------------- single-symbol backtest -------------------------
async def maybe_signal_compat(strat, symbol: str, price: float, ts_ms: int):
    # New API: maybe_signal(symbol, price=..., ts_ms=...)
    try:
        return await strat.maybe_signal(symbol, price=price, ts_ms=ts_ms)
    except TypeError:
        # Old API: maybe_signal(symbol, price=...)
        return await strat.maybe_signal(symbol, price=price)

async def backtest_one_symbol(
    symbol: str,
    *,
    start_ms: int,
    end_ms: int,
    download_start_ms: int,
    base: str,
    warmup_hours: int,
    fee: float,
    slippage: float,
    funding_rate: float,
    range_hours: int,
    min_range_hours: int,
    min_width_pct: float,
    max_width_pct: float,
    range_update_hours: int,
    range_tf_minutes: int,
    range_er_period: int,

    equity: float,
    risk_pct: float,
    cap_notional: float,
    min_notional: float,

    # strategy params
    confirm_limit: int,
    atr_period: int,
    entry_zone_frac: float,
    sweep_frac: float,
    reclaim_frac: float,
    wick_frac_min: float,
    tp_mode: str,
    min_rr: float,
    sl_width_frac: float,
    sl_atr_mult: float,
    cooldown_minutes: int,
    sl_ban_hours: int,
    trade_er_max: float,

    max_hold_hours: float,
    be_trigger_r: float,
    net_rr_min_mult: float,

    tp_auto: int,
    tp_opp_min_width_pct: float,
    tp_buffer_width_frac: float,
    tp1_frac: float,
    
    

    oq_window_trades: int,
    oq_min_trades: int,
    oq_pf_min: float,
    oq_winrate_min: float,
    oq_ban_hours: int,

    trades_csv: str,
    sl_side_strikes: int,
    sl_side_window_hours: int,
    sl_side_ban_hours: int,

    intrabar_fill: str,
    break_exit: int,
    break_buf_atr_mult: float,
    break_buf_width_frac: float,


        ) -> Dict[str, Any]:
    try:
        c5_all = bybit_kline_public(symbol, "5", download_start_ms, end_ms, base)
    except Exception as e:
        return {"symbol": symbol, "ok": False, "reason": f"download_failed: {type(e).__name__}: {e}"}

    c5_all = [c for c in c5_all if download_start_ms <= c.ts < end_ms]
    if len(c5_all) < 600:
        return {"symbol": symbol, "ok": False, "reason": "too few 5m candles"}

    bar_minutes = int(range_tf_minutes)
    bar_hours = float(bar_minutes) / 60.0
    range_bars = max(1, int(math.ceil(float(range_hours) / max(1e-9, bar_hours))))
    min_range_bars = max(1, int(math.ceil(float(min_range_hours) / max(1e-9, bar_hours))))

    touch_req = max(4, int(math.ceil(8.0 * (60.0 / max(1.0, float(bar_minutes))))))
    drift_bars = max(1, int(math.ceil(12.0 / max(1e-9, bar_hours))))

    # ----- incremental TF aggregation (NO look-ahead) -----
    tf_minutes = int(range_tf_minutes)
    tf_ms = tf_minutes * 60_000

    def _bucket_tf(ts_ms: int) -> int:
        return (int(ts_ms) // tf_ms) * tf_ms

    window_1h: List[Candle] = []        # тут лежат ТОЛЬКО закрытые TF-свечи
    cur_tf_bucket: Optional[int] = None
    cur_tf: Optional[Candle] = None
    # -----------------------------------------------


    registry = SimpleRangeRegistry()
    feed = HistoryFeed(c5_all)

    confirm_limit = max(int(confirm_limit), int(atr_period) + 2)
    strat = RangeStrategy(
        fetch_klines=feed.fetch_klines,
        registry=registry,
        confirm_tf="5",
        confirm_limit=confirm_limit,
        atr_period=int(atr_period),
        entry_zone_frac=float(entry_zone_frac),
        sweep_frac=float(sweep_frac),
        reclaim_frac=float(reclaim_frac),
        wick_frac_min=float(wick_frac_min),
        tp_mode=str(tp_mode),
        min_rr=float(min_rr),
        sl_width_frac=float(sl_width_frac),
        sl_atr_mult=float(sl_atr_mult),
        confirm_cache_ttl_sec=0,
    )

    current_equity = float(equity)
    equity_curve: List[Tuple[int, float]] = [(start_ms, current_equity)]
    trades: List[SimTrade] = []
    open_trade: Optional[SimTrade] = None
    signals = 0
    entered = 0
    # --- TP1 stats ---
    tp1_armed = 0          # сколько сделок открыто с tp1 > 0
    tp1_hits = 0           # сколько раз TP1 реально сработал
    tp1_closed_qty = 0.0   # суммарно закрыто qty по TP1
    tp1_gross = 0.0        # суммарный gross по TP1
    tp1_fee = 0.0          # суммарная комиссия по TP1




    last_range_update_ms = 0
    upd_ms = int(range_update_hours) * 3600_000
    cooldown_ms = int(cooldown_minutes) * 60_000
    last_entry_ts: int = -10**18
    sl_ban_until_ms: int = 0
    # await_mid_reset / await_mid_reset_band initialized near rej[]


    oq = OnlineQualityFilter(
        window_trades=int(oq_window_trades),
        min_trades=int(oq_min_trades),
        pf_min=float(oq_pf_min),
        winrate_min=float(oq_winrate_min),
        ban_hours=int(oq_ban_hours),
    )

    rej = defaultdict(int)
    # CSV (optional)
    csv_fields = [
        "symbol","side","entry_ts","entry","sl","tp","tp1","exit_ts","exit","exit_reason",
        "pnl","r_mult","fee_paid","funding_cost",
        "range_width_pct","range_er","range_atr","pos_entry","tp_policy",
        "partial_taken","moved_to_be","reason"
    ]
    csv_f, csv_w = _csv_open_append(str(trades_csv or ""), csv_fields)

    # side-ban after SL streaks (per symbol)
    side_ban_until = {"Buy": 0, "Sell": 0}
    side_strikes = {"Buy": deque(), "Sell": deque()}
    side_win_ms = int(sl_side_window_hours) * 3600_000

    # mid-reset after trade: require touching mid-band before next entry
    await_mid_reset = False
    await_mid_reset_band = 0.0

    def finalize_trade(tr: SimTrade, exit_ts: int, exit_px: float, reason: str) -> float:
        tr.exit_ts = int(exit_ts)
        tr.exit = float(exit_px)
        tr.exit_reason = str(reason)
        tr.notional_exit = tr.qty * float(exit_px)

        # gross for remaining position
        if tr.side == "Buy":
            gross_final = (float(exit_px) - tr.entry) * tr.qty
        else:
            gross_final = (tr.entry - float(exit_px)) * tr.qty

        # exit fee for remaining qty
        exit_fee = float(fee) * (tr.qty * float(exit_px))

        hold_hours = (int(exit_ts) - tr.entry_ts) / 3600_000
        funding_cost = (hold_hours // 8) * float(funding_rate) * tr.notional_entry

        fee_paid = float(tr.fee_accum) + float(exit_fee)
        pnl = float(tr.realized_gross) + float(gross_final) - fee_paid - float(funding_cost)

        tr.fee_paid = fee_paid
        tr.funding_cost = funding_cost
        tr.pnl = pnl

        # R multiple (use INITIAL risk)
        risk_usdt = float(tr.init_r_usdt) if float(tr.init_r_usdt) > 0 else (
            abs(tr.entry - float(tr.init_sl)) * float(tr.qty_init)
        )
        tr.r_mult = (pnl / risk_usdt) if risk_usdt > 0 else 0.0

        print(
            f"[EXIT ] {tr.symbol} {tr.side} ts={ms_to_iso(tr.exit_ts)} "
            f"exit={fmt_px(tr.exit)} reason={tr.exit_reason} pnl={tr.pnl:+.3f} "
            f"R={tr.r_mult:+.2f} tp1_taken={tr.partial_taken}"
        )

        # CSV row
        if csv_w is not None:
            csv_w.writerow({
                "symbol": tr.symbol,
                "side": tr.side,
                "entry_ts": ms_to_iso(tr.entry_ts),
                "entry": tr.entry,
                "sl": tr.init_sl,
                "tp": tr.init_tp,
                "tp1": tr.tp1,
                "exit_ts": ms_to_iso(tr.exit_ts),
                "exit": tr.exit,
                "exit_reason": tr.exit_reason,
                "pnl": tr.pnl,
                "r_mult": tr.r_mult,
                "fee_paid": tr.fee_paid,
                "funding_cost": tr.funding_cost,
                "range_width_pct": tr.range_width_pct,
                "range_er": tr.range_er,
                "range_atr": tr.range_atr,
                "pos_entry": tr.pos_entry,
                "tp_policy": tr.tp_policy,
                "partial_taken": int(bool(tr.partial_taken)),
                "moved_to_be": int(bool(tr.moved_to_be)),
                "reason": tr.reason,
            })

        return pnl


    for i, c in enumerate(c5_all):
        feed.set_index(i)
        # ----- build/update TF candle incrementally (closed-only in window_1h) -----
        b = _bucket_tf(int(c.ts))

        if cur_tf_bucket is None:
            cur_tf_bucket = b
            cur_tf = Candle(ts=b, o=c.o, h=c.h, l=c.l, c=c.c, v=c.v)

        elif b != cur_tf_bucket:
            # TF-бар сменился => предыдущий cur_tf считается ЗАКРЫТЫМ
            if cur_tf is not None:
                window_1h.append(cur_tf)
                if len(window_1h) > int(range_bars):
                    window_1h.pop(0)

            cur_tf_bucket = b
            cur_tf = Candle(ts=b, o=c.o, h=c.h, l=c.l, c=c.c, v=c.v)

        else:
            # текущий TF-бар еще не закрыт — просто обновляем его
            if cur_tf is not None:
                cur_tf.h = max(cur_tf.h, c.h)
                cur_tf.l = min(cur_tf.l, c.l)
                cur_tf.c = c.c
                cur_tf.v += c.v
        # -------------------------------------------------------------------------

        # обновляем диапазон не чаще чем раз в upd_ms
        if (c.ts - last_range_update_ms) >= upd_ms:
            last_range_update_ms = c.ts

            # hysteresis: выключаем range только после N плохих апдейтов подряд
            MAX_BAD_UPDATES = 3

            if len(window_1h) >= int(min_range_bars):
                lows = sorted([float(x.l) for x in window_1h])
                highs = sorted([float(x.h) for x in window_1h])

                q = 0.10 if len(window_1h) < 40 else 0.05
                support = percentile(lows, q)
                resistance = percentile(highs, 1.0 - q)

                width = resistance - support
                mid = (support + resistance) / 2.0
                width_pct = width / max(1e-12, mid)

                closes = [float(x.c) for x in window_1h]
                er_period_local = min(int(range_er_period), len(closes) - 1)
                er = efficiency_ratio(closes, er_period_local) if er_period_local >= 2 else 1.0

                atr = atr_from_candles(window_1h, int(atr_period))

                # базовые условия “это диапазон”
                range_good = True

                if not (width > 0 and (float(min_width_pct) <= width_pct <= float(max_width_pct))):
                    range_good = False

                # drift-filter
                drift = abs(float(window_1h[-1].c) - float(window_1h[0].c))
                if drift > 0.35 * width:
                    range_good = False

                # ER filter
                if er > float(trade_er_max):
                    range_good = False

                # touch/balance filter (согласуем со сканером)
                if width > 0:
                    touch_band = max(0.05 * width, 0.50 * atr)
                    touch_s = sum(1 for x in window_1h if float(x.l) <= support + touch_band)
                    touch_r = sum(1 for x in window_1h if float(x.h) >= resistance - touch_band)

                    if touch_s < int(touch_req) or touch_r < int(touch_req):
                        range_good = False

                    # баланс касаний (чтобы не было 30/3)
                    mn = max(1, min(touch_s, touch_r))
                    mx = max(touch_s, touch_r)
                    if mx / mn > 3.0:
                        range_good = False

                prev = registry.get(symbol)

                if range_good:
                    registry.set(
                        symbol,
                        SimpleRangeInfo(
                            support, resistance,
                            width_pct=width_pct,
                            er=er,
                            atr=atr,
                            active=True,
                            bad_streak=0,
                            last_good_ts=int(c.ts),
                        ),
                    )
                else:
                    # если раньше был валидный диапазон — сохраняем его ещё немного
                    if prev is not None:
                        prev.bad_streak = int(getattr(prev, "bad_streak", 0)) + 1
                        if prev.bad_streak >= MAX_BAD_UPDATES:
                            prev.active = False
                    else:
                        # если валидного диапазона ещё не было — просто ничего не делаем
                        pass


        # equity curve (floating)
        if open_trade is not None and c.ts >= start_ms:
            if open_trade.side == "Buy":
                floating_pnl = (float(c.c) - open_trade.entry) * open_trade.qty
            else:
                floating_pnl = (open_trade.entry - float(c.c)) * open_trade.qty
            equity_curve.append((c.ts, current_equity + floating_pnl))
        # exits
        if open_trade is not None:
            # --- PARTIAL TP1 at mid (if enabled) ---
            if float(open_trade.tp1) > 0 and (not open_trade.partial_taken):
                tp1 = float(open_trade.tp1)
                close_frac = max(0.0, min(1.0, float(tp1_frac)))

                if close_frac > 0 and open_trade.qty > 0:
                    o_ = float(getattr(c, "o", c.c))
                    cl_ = float(getattr(c, "c", c.c))
                    h_ = float(c.h)
                    l_ = float(c.l)

                    # detect if TP1 and SL are both reachable in this candle
                    if open_trade.side == "Buy":
                        hit_sl = l_ <= float(open_trade.sl)
                        hit_tp1 = h_ >= tp1
                        # if both hit: decide order
                        if hit_sl and hit_tp1:
                            mode = str(intrabar_fill)
                            if mode == "pessimistic":
                                hit_tp1 = False
                            elif mode == "optimistic":
                                hit_tp1 = True
                            elif mode == "random":
                                hit_tp1 = (random.random() < 0.5)
                            else:
                                # heuristic: bullish => low-first => SL first
                                hit_tp1 = (cl_ < o_)  # high-first => TP1 first

                        if hit_tp1:
                            qty_close = open_trade.qty * close_frac
                            gross_part = (tp1 - open_trade.entry) * qty_close
                            fee_part = float(fee) * (qty_close * tp1)

                            open_trade.realized_gross += gross_part
                            open_trade.fee_accum += fee_part
                            open_trade.qty -= qty_close
                            open_trade.partial_taken = True

                            tp1_hits += 1
                            tp1_closed_qty += qty_close
                            tp1_gross += gross_part
                            tp1_fee += fee_part

                            # profit-lock (not just BE)
                            fee_buf = open_trade.entry * (2.2 * float(fee) + 2.0 * float(slippage))
                            lock = max(fee_buf, float(POST_TP1_LOCK_FRAC) * (tp1 - open_trade.entry))
                            new_sl = open_trade.entry + lock
                            if new_sl > open_trade.sl:
                                open_trade.sl = new_sl
                                open_trade.moved_to_be = True

                    else:  # Sell
                        hit_sl = h_ >= float(open_trade.sl)
                        hit_tp1 = l_ <= tp1
                        if hit_sl and hit_tp1:
                            mode = str(intrabar_fill)
                            if mode == "pessimistic":
                                hit_tp1 = False
                            elif mode == "optimistic":
                                hit_tp1 = True
                            elif mode == "random":
                                hit_tp1 = (random.random() < 0.5)
                            else:
                                # heuristic: bullish => low-first => TP1 first for Sell
                                hit_tp1 = (cl_ >= o_)

                        if hit_tp1:
                            qty_close = open_trade.qty * close_frac
                            gross_part = (open_trade.entry - tp1) * qty_close
                            fee_part = float(fee) * (qty_close * tp1)

                            open_trade.realized_gross += gross_part
                            open_trade.fee_accum += fee_part
                            open_trade.qty -= qty_close
                            open_trade.partial_taken = True

                            tp1_hits += 1
                            tp1_closed_qty += qty_close
                            tp1_gross += gross_part
                            tp1_fee += fee_part

                            fee_buf = open_trade.entry * (2.2 * float(fee) + 2.0 * float(slippage))
                            lock = max(fee_buf, float(POST_TP1_LOCK_FRAC) * (open_trade.entry - tp1))
                            new_sl = open_trade.entry - lock
                            if new_sl < open_trade.sl:
                                open_trade.sl = new_sl
                                open_trade.moved_to_be = True
            # --- END PARTIAL ---

            # --- BREAK exit: range invalidation ---
            if open_trade is not None and int(break_exit) == 1:
                info_now = registry.get(symbol)
                if (not info_now) or (not registry.is_allowed(symbol)):
                    # range switched off => exit at market close with slippage
                    mpx = float(c.c) * (1 - float(slippage)) if open_trade.side == "Buy" else float(c.c) * (1 + float(slippage))
                    pnl = finalize_trade(open_trade, int(c.ts), float(mpx), "RANGE_OFF")
                    if c.ts >= start_ms:
                        current_equity += pnl
                        equity_curve.append((c.ts, current_equity))
                        trades.append(open_trade)
                        oq.update_on_close(float(open_trade.r_mult), int(c.ts))

                    open_trade = None
                else:
                    buf = max(
                        float(break_buf_width_frac) * float(info_now.width),
                        float(break_buf_atr_mult) * float(getattr(info_now, "atr", 0.0)),
                    )
                    px = float(c.c)
                    if (px > float(info_now.resistance) + buf) or (px < float(info_now.support) - buf):
                        mpx = px * (1 - float(slippage)) if open_trade.side == "Buy" else px * (1 + float(slippage))
                        pnl = finalize_trade(open_trade, int(c.ts), float(mpx), "BREAK")
                        if c.ts >= start_ms:
                            current_equity += pnl
                            equity_curve.append((c.ts, current_equity))
                            trades.append(open_trade)
                            oq.update_on_close(float(open_trade.r_mult), int(c.ts))

                        open_trade = None



            
            if open_trade is None:


            
                continue


            
            hit = candle_hits_sl_tp(c, open_trade.side, open_trade.sl, open_trade.tp, intrabar_fill=str(intrabar_fill))
            if hit:
                reason, px = hit
                ban_on_sl = (reason == "SL" and (not open_trade.moved_to_be))

                # если SL сработал после перевода в BE -> считаем как BE
                if reason == "SL" and open_trade.moved_to_be:
                    reason = "BE"

                exit_px = apply_exit_slippage(open_trade.side, float(px), float(slippage), reason)
                pnl = finalize_trade(open_trade, int(c.ts), exit_px, reason)

                if ban_on_sl:
                    sl_ban_until_ms = int(c.ts) + int(sl_ban_hours) * 3600_000

                    # side-ban strikes
                    dq = side_strikes.get(open_trade.side)
                    if dq is not None:
                        dq.append(int(c.ts))
                        while dq and dq[0] < int(c.ts) - side_win_ms:
                            dq.popleft()
                        if len(dq) >= int(sl_side_strikes):
                            side_ban_until[open_trade.side] = max(
                                int(side_ban_until.get(open_trade.side, 0)),
                                int(c.ts) + int(sl_side_ban_hours) * 3600_000
                            )



                if c.ts >= start_ms:
                    current_equity += pnl
                    equity_curve.append((c.ts, current_equity))
                    trades.append(open_trade)
                    oq.update_on_close(float(open_trade.r_mult), int(c.ts))

                 

                open_trade = None

            # --- BE / time-stop management ---
            if open_trade is not None:
                init_r = abs(open_trade.entry - float(open_trade.init_sl or open_trade.sl))
                if init_r > 0 and (not open_trade.moved_to_be):

                    # профит в "ценовых единицах"
                    if open_trade.side == "Buy":
                        unreal = float(c.c) - open_trade.entry
                    else:
                        unreal = open_trade.entry - float(c.c)

                    r_mult = unreal / init_r  # сколько R прошли

                    # BE разрешаем только после TP1 (если TP1 вообще активен)
                    # tp1_active = (float(getattr(open_trade, "tp1", 0.0)) > 0.0)
                    # if tp1_active and (not open_trade.partial_taken):
                    #     be_allowed = False
                    # else:
                    #     be_allowed = True
                    tp1_active = (float(getattr(open_trade, "tp1", 0.0)) > 0.0)
                    be_allowed = bool(tp1_active and open_trade.partial_taken)

                    if be_allowed and (r_mult >= float(be_trigger_r)):
                        # буфер на комиссии/проскальзывание (минимальный, чтобы BE был реально BE)
                        fee_buf = open_trade.entry * (2.2 * float(fee) + 2.0 * float(slippage))

                        if open_trade.side == "Buy":
                            new_sl = open_trade.entry + fee_buf
                            if new_sl > open_trade.sl:
                                open_trade.sl = new_sl
                                open_trade.moved_to_be = True
                        else:
                            new_sl = open_trade.entry - fee_buf
                            if new_sl < open_trade.sl:
                                open_trade.sl = new_sl
                                open_trade.moved_to_be = True


                # time-stop
                hold_hours = (int(c.ts) - int(open_trade.entry_ts)) / 3600_000
                if hold_hours >= float(max_hold_hours):
                    px = float(c.c)
                    exit_px = px * (1 - float(slippage)) if open_trade.side == "Buy" else px * (1 + float(slippage))
                    pnl = finalize_trade(open_trade, int(c.ts), float(exit_px), "TIME")



                    if c.ts >= start_ms:
                        current_equity += pnl
                        equity_curve.append((c.ts, current_equity))
                        trades.append(open_trade)
                        oq.update_on_close(float(open_trade.r_mult), int(c.ts))

                      

                    open_trade = None


        # entries
        if open_trade is None and c.ts >= start_ms:
            # OQ ban — блокируем только новые входы
            if not oq.allowed(int(c.ts)):
                rej["rej_oq_ban"] += 1
                continue

            # ban after SL (per-symbol)
            if int(sl_ban_hours) > 0 and int(c.ts) < int(sl_ban_until_ms):
                rej["rej_sl_ban"] += 1
                continue

            # cooldown
            if int(c.ts) - last_entry_ts < cooldown_ms:
                rej["rej_cooldown"] += 1
                continue

            info = registry.get(symbol)
            if not info or not registry.is_allowed(symbol):
                rej["rej_no_range"] += 1
                continue

            # mid-reset: после сделки ждём касания mid-band перед следующей сделкой
            if await_mid_reset:
                if abs(float(c.c) - float(info.mid)) > float(await_mid_reset_band):
                    rej["rej_mid_reset"] += 1
                    continue
                await_mid_reset = False


            # anti hidden trend на последних ~12h (масштабируем под TF)
            if len(window_1h) >= int(drift_bars):
                drift_recent = abs(float(window_1h[-1].c) - float(window_1h[-int(drift_bars)].c))
                if drift_recent > 0.25 * info.width:
                    rej["rej_drift_recent"] += 1
                    continue

            sig: Optional[RangeSignal] = await maybe_signal_compat(
                strat, symbol, price=float(c.c), ts_ms=int(c.ts)
            )
            if not sig:
                rej["rej_no_signal"] += 1
                continue
            signals += 1
            # SIDE-BAN (после серии SL на этой стороне)
            if int(c.ts) < int(side_ban_until.get(str(sig.side), 0)):
                rej["rej_side_ban"] += 1
                continue


            # slippage -> entry
            if sig.side == "Buy":
                entry = float(c.c) * (1 + float(slippage))
            else:
                entry = float(c.c) * (1 - float(slippage))

            # --- anti-micro-trade (fee-aware) ---
            rt_cost = 2.0 * float(fee) + 2.0 * float(slippage)
            min_tp_pct = max(0.0045, rt_cost * 1.8 + 0.0010)   # ~0.45%+
            min_sl_pct = max(0.0030, rt_cost * 1.2 + 0.0005)   # ~0.30%+

            # --- sl/tp shift из-за slippage ---
            raw = float(c.c)
            delta = entry - raw
            sl_raw = float(sig.sl)
            tp_raw = float(sig.tp)

            tp_use_opp = None
            tp_mid_raw = float(info.mid)

            if int(tp_auto) == 1:
                width_pct_local = float(getattr(info, "width_pct", 0.0))
                atr1h_local = float(getattr(info, "atr", 0.0))
                buf = max(float(tp_buffer_width_frac) * float(info.width), 0.25 * atr1h_local)

                use_opp = (width_pct_local >= float(tp_opp_min_width_pct))
                tp_use_opp = bool(use_opp)

                if sig.side == "Buy":
                    tp_opp_raw = float(info.resistance) - buf
                    tp_raw = tp_opp_raw if use_opp else tp_mid_raw
                else:
                    tp_opp_raw = float(info.support) + buf
                    tp_raw = tp_opp_raw if use_opp else tp_mid_raw

            sl_adj = sl_raw + delta
            tp_adj = tp_raw + delta

            tp1_raw = 0.0
            if int(tp_auto) == 1 and bool(tp_use_opp) and float(tp1_frac) > 0:
                tp1_raw = float(tp_mid_raw)
            tp1_adj = (tp1_raw + delta) if tp1_raw > 0 else 0.0

            # sanity: TP/SL по правильную сторону
            if sig.side == "Buy":
                if not (sl_adj < entry < tp_adj):
                    rej["rej_sanity"] += 1
                    continue
            else:
                if not (tp_adj < entry < sl_adj):
                    rej["rej_sanity"] += 1
                    continue

            dist_sl_pct = abs(entry - sl_adj) / max(1e-12, entry)
            dist_tp_pct = abs(tp_adj - entry) / max(1e-12, entry)

            if dist_sl_pct < min_sl_pct or dist_tp_pct < min_tp_pct:
                rej["rej_micro"] += 1
                continue

            # sizing
            qty, notional = calc_position_size_usdt(
                equity=current_equity,
                risk_pct=float(risk_pct) * float(oq.risk_multiplier()),
                entry=entry,
                sl=float(sl_adj),
                cap_notional=float(cap_notional),
                min_notional=float(min_notional),
            )
            if qty <= 0:
                rej["rej_size"] += 1
                continue

            # fee-aware net RR filter
            tp_px = float(tp_adj)
            sl_px = float(sl_adj)

            if sig.side == "Buy":
                gross_tp = (tp_px - entry) * qty
                gross_sl = (entry - sl_px) * qty
            else:
                gross_tp = (entry - tp_px) * qty
                gross_sl = (sl_px - entry) * qty

            fee_est = float(fee) * (float(notional) + float(qty) * float(tp_px))
            net_tp = gross_tp - fee_est
            net_sl = gross_sl + fee_est

            if net_tp <= 0 or net_sl <= 0:
                rej["rej_net_rr"] += 1
                continue

            net_rr = net_tp / max(1e-12, net_sl)
            min_net_rr = float(min_rr) * float(net_rr_min_mult)

            if net_rr < min_net_rr:
                rej["rej_net_rr"] += 1
                continue

            # tp policy counts
            if int(tp_auto) == 1 and tp_use_opp is not None:
                if tp_use_opp:
                    rej["tp_policy_opp"] += 1
                else:
                    rej["tp_policy_mid"] += 1

            entry_fee = float(fee) * float(notional)
            pos_entry = (float(c.c) - float(info.support)) / max(1e-12, float(info.width))
            tp_policy = "mid"
            if int(tp_auto) == 1 and tp_use_opp is not None:
                tp_policy = "opp" if tp_use_opp else "mid"

            open_trade = SimTrade(
                symbol=symbol,
                side=str(sig.side),
                entry_ts=int(c.ts),
                entry=float(entry),
                sl=float(sl_adj),
                tp=float(tp_adj),
                reason=str(sig.reason),
                qty=float(qty),
                notional_entry=float(notional),

                init_sl=float(sl_adj),
                init_tp=float(tp_adj),
                moved_to_be=False,

                qty_init=float(qty),
                fee_accum=float(entry_fee),
                realized_gross=0.0,
                partial_taken=False,
                tp1=float(tp1_adj),

                init_r_usdt=abs(float(entry) - float(sl_adj)) * float(qty),
                range_width_pct=float(getattr(info, "width_pct", 0.0)),
                range_er=float(getattr(info, "er", 1.0)),
                range_atr=float(getattr(info, "atr", 0.0)),
                pos_entry=float(pos_entry),
                tp_policy=str(tp_policy),

            )
            entered += 1

            print(
                f"[ENTER] {symbol} {open_trade.side} ts={ms_to_iso(open_trade.entry_ts)} "
                f"entry={fmt_px(open_trade.entry)} sl={fmt_px(open_trade.sl)} "
                f"tp={fmt_px(open_trade.tp)} tp1={fmt_px(open_trade.tp1)} qty={open_trade.qty:.4f}"
            )

            if float(open_trade.tp1) > 0:
                tp1_armed += 1

            last_entry_ts = int(c.ts)
            await_mid_reset = True
            await_mid_reset_band = max(0.10 * float(info.width), 0.75 * float(getattr(info, "atr", 0.0)))


    # EOD close
    if open_trade is not None and open_trade.entry_ts >= start_ms:

        last = c5_all[-1]
        px = float(last.c)
        exit_px = px * (1 - float(slippage)) if open_trade.side == "Buy" else px * (1 + float(slippage))
        pnl = finalize_trade(open_trade, int(last.ts), float(exit_px), "EOD")


        current_equity += pnl
        equity_curve.append((int(last.ts), current_equity))
        trades.append(open_trade)
        oq.update_on_close(float(open_trade.r_mult), int(last.ts))
        open_trade = None


    n = len(trades)
    wins = sum(1 for t in trades if (t.pnl or 0.0) > 0.0)
    total_pnl = sum((t.pnl or 0.0) for t in trades)
    max_dd = calc_max_drawdown(equity_curve)
    gross_profit = sum((t.pnl or 0.0) for t in trades if (t.pnl or 0.0) > 0.0)
    gross_loss = -sum((t.pnl or 0.0) for t in trades if (t.pnl or 0.0) < 0.0)
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    exit_counts = defaultdict(int)
    for t in trades:
        exit_counts[str(t.exit_reason)] += 1

    top_rej = sorted(rej.items(), key=lambda x: x[1], reverse=True)[:12]
    if top_rej:
        print(f"[REJ ] {symbol} top_rejects={top_rej}")
        
    if csv_f is not None:
        csv_f.close()

    return {
        "symbol": symbol,
        "ok": True,
        "trades": trades,
        "n": n,
        "wins": wins,
        "winrate": (wins / n * 100.0) if n else 0.0,
        "start_equity": float(equity),
        "end_equity": float(current_equity),
        "total_pnl": float(total_pnl),
        "max_dd": float(max_dd),
        "profit_factor": float(profit_factor),
        "signals": int(signals),
        "entered": int(entered),
        "rejects": dict(rej),
        "gross_profit": float(gross_profit),
        "gross_loss": float(gross_loss),
        "exit_counts": dict(exit_counts),
        "tp1_armed": int(tp1_armed),
        "tp1_hits": int(tp1_hits),
        "tp1_closed_qty": float(tp1_closed_qty),
        "tp1_gross": float(tp1_gross),
        "tp1_fee": float(tp1_fee),

    }


# ------------------------- main -------------------------

async def run() -> None:
    ap = argparse.ArgumentParser()

    # period
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument(
        "--wf_step_days", "--step_days",
        dest="wf_step_days",
        type=int, default=7,
        help="walk-forward step in days (0 = disable, run single pass)"
    )
    ap.add_argument(
        "--wf_lookback_days", "--lookback_days",
        dest="wf_lookback_days",
        type=int, default=21,
        help="how many days to look back for scanning ranges at each step"
    )



    # universe
    ap.add_argument("--symbols", default="", help="comma-separated, e.g. BTCUSDT,ETHUSDT,SOLUSDT (optional)")
    ap.add_argument("--universe_top_n", type=int, default=60, help="if --symbols empty: take top N by turnover24h")
    ap.add_argument("--select_top_k", type=int, default=8, help="pick best K range candidates to backtest")
    ap.add_argument("--exclude_symbols", default="", help="comma-separated, e.g. BTCUSDT,ETHUSDT")
    ap.add_argument("--min_turnover24h", type=float, default=20_000_000,
        help="min turnover24h (USDT) to include symbol in universe")

    ap.add_argument("--base", default=os.getenv("BYBIT_BASE", "https://api.bybit.com"))

    # costs
    ap.add_argument("--fee", type=float, default=0.0006)
    ap.add_argument("--slippage", type=float, default=0.0005)
    ap.add_argument("--funding_rate", type=float, default=0.0001)

    # backtest realism
    ap.add_argument(
        "--intrabar_fill",
        type=str,
        default="pessimistic",
        choices=["pessimistic", "heuristic", "optimistic", "random"],
        help="When SL and TP are both touched inside the same candle."
    )

    ap.add_argument("--break_exit", type=int, default=1, choices=[0, 1],
        help="Exit position when range breaks (close outside support/resistance + buffer).")
    ap.add_argument("--break_buf_atr_mult", type=float, default=0.50,
        help="Break buffer as ATR multiple.")
    ap.add_argument("--break_buf_width_frac", type=float, default=0.02,
        help="Break buffer as fraction of range width.")

    ap.add_argument("--min_width_fee_mult", type=float, default=2.2,
        help="Auto-min range width based on costs: min_width_fee = (2*fee+2*slippage)*mult")
    ap.add_argument("--min_width_fee_floor", type=float, default=0.0,
        help="Optional hard floor for min_width_fee.")


    # warmup (download before start)
    ap.add_argument("--warmup_hours", type=int, default=240)

    # range build (1h)
    ap.add_argument("--range_hours", type=int, default=72)
    ap.add_argument("--min_range_hours", type=int, default=48)
    ap.add_argument("--min_width_pct", type=float, default=0.003)
    ap.add_argument("--max_width_pct", type=float, default=0.08)
    ap.add_argument("--range_update_hours", type=int, default=1)


    # sizing
    ap.add_argument("--equity", type=float, default=100.0)
    ap.add_argument("--equity_mode", type=str, default="split", choices=["split", "full"],
        help="split: equity/K per symbol; full: each symbol uses full equity (не реалистично)")
    ap.add_argument(
        "--max_concurrent",
        type=int,
        default=4,
        help="Для equity_mode=split: делим equity не на top_k, а на min(top_k, max_concurrent). "
            "Это приближение реального числа одновременных позиций."
    )

    ap.add_argument("--trades_csv", default="", help="append all closed trades to CSV (single file)")

    ap.add_argument("--sl_side_strikes", type=int, default=2, help="how many SL (no-BE) to trigger side-ban")
    ap.add_argument("--sl_side_window_hours", type=int, default=12, help="window for counting SL strikes")
    ap.add_argument("--sl_side_ban_hours", type=int, default=12, help="ban duration for that side after strikes")


    ap.add_argument("--risk_pct", type=float, default=0.01)
    ap.add_argument("--cap_notional", type=float, default=50.0)
    ap.add_argument("--min_notional", type=float, default=5.0)

    # strategy params
    ap.add_argument("--confirm_limit", type=int, default=60)
    ap.add_argument("--atr_period", type=int, default=14)
    ap.add_argument("--entry_zone_frac", type=float, default=0.10)
    ap.add_argument("--sweep_frac", type=float, default=0.02)
    ap.add_argument("--reclaim_frac", type=float, default=0.01)
    ap.add_argument("--wick_frac_min", type=float, default=0.35)
    ap.add_argument("--tp_mode", type=str, default="mid", choices=["mid", "opposite"])
    ap.add_argument("--min_rr", type=float, default=1.6)
    ap.add_argument("--tp_auto", type=int, default=0, choices=[0,1],
        help="1: TP выбирается автоматически: для широких диапазонов цель opposite, иначе mid.")
    ap.add_argument("--tp_opp_min_width_pct", type=float, default=0.02,
        help="Если width_pct >= порога, TP ставим на opposite (с буфером). Пример 0.02 = 2%%.")
    ap.add_argument("--tp_buffer_width_frac", type=float, default=0.02,
        help="Буфер от границы диапазона как доля width, чтобы TP чаще исполнялся. Пример 0.02 = 2%% ширины.")
    
    ap.add_argument(
        "--tp1_frac",
        type=float,
        default=0.0,
        help="Partial take-profit fraction at mid (0..1). Работает только когда tp_auto=1 и выбран opposite TP. 0 = отключено."
    )


    ap.add_argument("--sl_width_frac", type=float, default=0.10)
    ap.add_argument("--sl_atr_mult", type=float, default=1.0)
    ap.add_argument("--max_hold_hours", type=float, default=10.0, help="time-stop: max holding hours")
    ap.add_argument("--be_trigger_r", type=float, default=0.6, help="move SL to breakeven after +X*R")
    ap.add_argument("--net_rr_min_mult", type=float, default=0.90,
        help="fee-aware filter: require net_RR >= min_rr * this_mult (after fees). Typical: 0.85-0.95")

    ap.add_argument("--cooldown_minutes", type=int, default=60, help="cooldown between entries per symbol")
    ap.add_argument("--sl_ban_hours", type=int, default=24,
        help="ban new entries for this symbol after SL for N hours")


    ap.add_argument("--oq_window_trades", type=int, default=20)
    ap.add_argument("--oq_min_trades", type=int, default=8)
    ap.add_argument("--oq_pf_min", type=float, default=0.9)
    ap.add_argument("--oq_winrate_min", type=float, default=0.35)
    ap.add_argument("--oq_ban_hours", type=int, default=48)


    # scan filters
    ap.add_argument("--scan_atr_period", type=int, default=14)
    ap.add_argument("--scan_er_period", type=int, default=24)
    ap.add_argument("--scan_er_max", type=float, default=0.28)
    ap.add_argument("--trade_er_max", type=float, default=None,
        help="ER max for trading (if None, uses scan_er_max)")
    
    ap.add_argument("--scan_tf_minutes", type=int, default=60,
        help="TF for scanning ranges (minutes). 60=1H, 240=4H.")
    ap.add_argument("--range_tf_minutes", type=int, default=60,
        help="TF used to build/update range levels during trading (minutes). Usually match scan_tf_minutes.")
    ap.add_argument("--range_er_period", type=int, default=24,
        help="ER period (bars of range_tf) used when validating range in registry updates.")
    
    ap.add_argument("--scan_debug", action="store_true",
        help="Print scan rejection stats when no picks in a segment")


    
    args = ap.parse_args()

    rt_cost = 2.0 * float(args.fee) + 2.0 * float(args.slippage)
    min_width_fee = max(float(args.min_width_fee_floor), rt_cost * float(args.min_width_fee_mult))
    min_width_eff = max(float(args.min_width_pct), float(min_width_fee))

    print(f"DEBUG scan_er_max={args.scan_er_max}  universe_top_n={args.universe_top_n}  select_top_k={args.select_top_k}")

    trade_er_max = float(args.trade_er_max) if args.trade_er_max is not None else float(args.scan_er_max)

    start_ms = parse_date_ms(args.start)
    end_ms = parse_date_ms(args.end)

    trade_er_max = float(args.trade_er_max) if args.trade_er_max is not None else float(args.scan_er_max)

    download_start_ms = start_ms - int(args.warmup_hours) * 3600_000
    if download_start_ms < 0:
        download_start_ms = 0

    # --- build symbol universe ---
    if args.symbols.strip():
        universe = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        universe = bybit_top_symbols_by_turnover(
            args.base,
            int(args.universe_top_n),
            min_turnover24h=float(args.min_turnover24h),
        )


    # apply excludes
    if args.exclude_symbols.strip():
        excl = {s.strip().upper() for s in args.exclude_symbols.split(",") if s.strip()}
        universe = [s for s in universe if s not in excl]

    
    print(f"Universe size: {len(universe)}")
    
    def scan_picks(scan_end_ms: int) -> List[Tuple[float, str, Dict[str, float]]]:
        lookback_ms = int(args.wf_lookback_days) * 24 * 3600_000
        scan_start_local = max(0, int(scan_end_ms) - int(lookback_ms))

        bar_minutes = int(args.scan_tf_minutes)
        bar_hours = float(bar_minutes) / 60.0

        range_bars = max(1, int(math.ceil(float(args.range_hours) / max(1e-9, bar_hours))))
        min_range_bars = max(1, int(math.ceil(float(args.min_range_hours) / max(1e-9, bar_hours))))

        scored_local = []

        # ---- DEBUG stats ----
        stats = defaultdict(int)
        err_sample = None

        for sym in universe:
            try:
                c_tf = bybit_kline_public(sym, str(bar_minutes), scan_start_local, scan_end_ms, args.base)
                c_tf = [c for c in c_tf if scan_start_local <= c.ts < scan_end_ms]

                # ВОТ СЮДА ставится проверка too_few (сразу после фильтрации)
                if len(c_tf) < int(min_range_bars):
                    stats["too_few"] += 1
                    continue

                score, meta = range_score_1h(
                    c_tf,
                    bar_minutes=bar_minutes,
                    range_bars=range_bars,
                    min_range_bars=min_range_bars,
                    min_width_pct=float(min_width_eff),
                    max_width_pct=float(args.max_width_pct),
                    atr_period=int(args.scan_atr_period),
                    er_period=int(args.scan_er_period),
                    er_max=float(args.scan_er_max),
                )

                if meta.get("ok") == 1:
                    stats["ok"] += 1
                    scored_local.append((score, sym, meta))
                else:
                    stats["fail"] += 1
                    wp = meta.get("width_pct", None)
                    er = meta.get("er", None)

                    if wp is not None and not (float(args.min_width_pct) <= float(wp) <= float(args.max_width_pct)):
                        stats["fail_width"] += 1
                    elif er is not None and float(er) > float(args.scan_er_max):
                        stats["fail_er"] += 1
                    elif ("touch_s" in meta) or ("touch_r" in meta):
                        stats["fail_touch"] += 1
                    elif "drift" in meta:
                        stats["fail_drift"] += 1
                    else:
                        stats["fail_other"] += 1

            except Exception as e:
                stats["err"] += 1
                if err_sample is None:
                    err_sample = f"{sym}: {type(e).__name__}: {e}"
                continue

        scored_local.sort(reverse=True, key=lambda x: x[0])
        top_k_local = min(int(args.select_top_k), len(scored_local))

        if bool(args.scan_debug) and not scored_local:
            print(
                f"[SCAN] end={ms_to_iso(scan_end_ms)} tf={bar_minutes}m "
                f"bars={range_bars}/{min_range_bars} universe={len(universe)} "
                f"ok={stats.get('ok',0)} too_few={stats.get('too_few',0)} "
                f"fail_width={stats.get('fail_width',0)} fail_er={stats.get('fail_er',0)} "
                f"fail_touch={stats.get('fail_touch',0)} fail_drift={stats.get('fail_drift',0)} "
                f"errors={stats.get('err',0)}"
            )
            if err_sample:
                print("[SCAN] sample_error:", err_sample)

        return scored_local[:top_k_local]

    # --- walk-forward or single-pass ---
    if int(args.wf_step_days) <= 0:
        # один scan на start_ms и один backtest на весь период
        picks = scan_picks(start_ms)
        if not picks:
            print("No range candidates found by scan filters. Try loosening scan_er_max or width bounds.")
            return

        top_k = len(picks)
        print("\n=== RANGE SCAN (top candidates) ===")
        for score, sym, meta in picks[:min(10, top_k)]:
            print(f"{sym:<12} score={score:5.1f} width_pct={meta['width_pct']*100:5.2f}% ER={meta['er']:.3f}")

        alloc_k = min(top_k, int(args.max_concurrent)) if args.equity_mode == "split" else 1
        equity_per = float(args.equity) / float(alloc_k) if args.equity_mode == "split" else float(args.equity)


        total_pnl_sum = 0.0
        dd_sum = 0.0
        results = 0

        for _, sym, _ in picks:
            res = await backtest_one_symbol(
                sym,
                start_ms=start_ms,
                end_ms=end_ms,
                download_start_ms=max(0, start_ms - int(args.warmup_hours) * 3600_000),
                base=args.base,
                warmup_hours=int(args.warmup_hours),
                fee=float(args.fee),
                slippage=float(args.slippage),
                funding_rate=float(args.funding_rate),
                range_hours=int(args.range_hours),
                min_range_hours=int(args.min_range_hours),
                min_width_pct=float(min_width_eff),
                max_width_pct=float(args.max_width_pct),
                range_update_hours=int(args.range_update_hours),
                range_tf_minutes=int(args.range_tf_minutes),
                range_er_period=int(args.range_er_period),
                equity=float(equity_per),
                risk_pct=float(args.risk_pct),
                cap_notional=float(args.cap_notional),
                min_notional=float(args.min_notional),
                confirm_limit=int(args.confirm_limit),
                atr_period=int(args.atr_period),
                entry_zone_frac=float(args.entry_zone_frac),
                sweep_frac=float(args.sweep_frac),
                reclaim_frac=float(args.reclaim_frac),
                wick_frac_min=float(args.wick_frac_min),
                tp_mode=str(args.tp_mode),
                min_rr=float(args.min_rr),
                sl_width_frac=float(args.sl_width_frac),
                sl_atr_mult=float(args.sl_atr_mult),
                cooldown_minutes=int(args.cooldown_minutes),
                trade_er_max=trade_er_max,
                max_hold_hours=float(args.max_hold_hours),
                be_trigger_r=float(args.be_trigger_r),
                net_rr_min_mult=float(args.net_rr_min_mult),

                oq_window_trades=int(args.oq_window_trades),
                oq_min_trades=int(args.oq_min_trades),
                oq_pf_min=float(args.oq_pf_min),
                oq_winrate_min=float(args.oq_winrate_min),
                oq_ban_hours=int(args.oq_ban_hours),

                tp_auto=int(args.tp_auto),
                tp_opp_min_width_pct=float(args.tp_opp_min_width_pct),
                tp_buffer_width_frac=float(args.tp_buffer_width_frac),
                tp1_frac=float(args.tp1_frac),
                sl_ban_hours=int(args.sl_ban_hours),

                trades_csv=str(args.trades_csv),
                sl_side_strikes=int(args.sl_side_strikes),
                sl_side_window_hours=int(args.sl_side_window_hours),
                sl_side_ban_hours=int(args.sl_side_ban_hours),

                intrabar_fill=str(args.intrabar_fill),
                break_exit=int(args.break_exit),
                break_buf_atr_mult=float(args.break_buf_atr_mult),
                break_buf_width_frac=float(args.break_buf_width_frac),


            )
            if not res.get("ok"):
                continue

            results += 1
            total_pnl_sum += float(res["total_pnl"])
            dd_sum += float(res["max_dd"])

        print("\n=== PORTFOLIO SUMMARY ===")
        print(f"Period: {args.start}..{args.end}")
        print(f"Selected symbols: {results}/{len(picks)}  Equity mode: {args.equity_mode}")
        print(f"Total PnL (sum): {total_pnl_sum:+.2f} USDT")
        print(f"Sum MaxDD (naive sum): {dd_sum:.2f} USDT")
        return

    # walk-forward: перескан каждые wf_step_days и торговля на следующий сегмент
    step_ms = int(args.wf_step_days) * 24 * 3600_000
    seg_start = start_ms

    wf_tp_opp = 0
    wf_tp_mid = 0

    # TP1 aggregate (WF)
    wf_tp1_armed = 0
    wf_tp1_hits = 0
    wf_tp1_closed_qty = 0.0
    wf_tp1_gross = 0.0
    wf_tp1_fee = 0.0

    # WF run stats
    wf_runs = 0
    wf_dd_max = 0.0

    wf_total_pnl = 0.0
    wf_dd_sum = 0.0
    wf_trades = 0
    wf_wins = 0
    wf_gross_profit = 0.0
    wf_gross_loss = 0.0
    wf_exit_counts = defaultdict(int)



    print("\n=== WALK-FORWARD MODE ===")
    print(f"Step: {args.wf_step_days} days  Lookback: {args.wf_lookback_days} days")

    while seg_start < end_ms:
        seg_end = min(end_ms, seg_start + step_ms)

        picks = scan_picks(seg_start)
        if not picks:
            print(f"\n[{ms_to_iso(seg_start)}] No picks. Skip {ms_to_iso(seg_start)}..{ms_to_iso(seg_end)}")
            seg_start = seg_end
            continue

        top_k = len(picks)
        alloc_k = min(top_k, int(args.max_concurrent)) if args.equity_mode == "split" else 1
        equity_per = float(args.equity) / float(alloc_k) if args.equity_mode == "split" else float(args.equity)


        print(f"\n--- SEGMENT {ms_to_iso(seg_start)}..{ms_to_iso(seg_end)}  picks={top_k}  equity_per={equity_per:.2f} ---")

        for _, sym, _ in picks:
            res = await backtest_one_symbol(
                sym,
                start_ms=seg_start,
                end_ms=seg_end,
                download_start_ms=max(0, seg_start - int(args.warmup_hours) * 3600_000),
                base=args.base,
                warmup_hours=int(args.warmup_hours),
                fee=float(args.fee),
                slippage=float(args.slippage),
                funding_rate=float(args.funding_rate),
                range_hours=int(args.range_hours),
                min_range_hours=int(args.min_range_hours),
                min_width_pct=float(min_width_eff),
                max_width_pct=float(args.max_width_pct),
                range_update_hours=int(args.range_update_hours),
                range_tf_minutes=int(args.range_tf_minutes),
                range_er_period=int(args.range_er_period),
                equity=float(equity_per),
                risk_pct=float(args.risk_pct),
                cap_notional=float(args.cap_notional),
                min_notional=float(args.min_notional),
                confirm_limit=int(args.confirm_limit),
                atr_period=int(args.atr_period),
                entry_zone_frac=float(args.entry_zone_frac),
                sweep_frac=float(args.sweep_frac),
                reclaim_frac=float(args.reclaim_frac),
                wick_frac_min=float(args.wick_frac_min),
                tp_mode=str(args.tp_mode),
                min_rr=float(args.min_rr),
                sl_width_frac=float(args.sl_width_frac),
                sl_atr_mult=float(args.sl_atr_mult),
                cooldown_minutes=int(args.cooldown_minutes),
                trade_er_max=trade_er_max,
                max_hold_hours=float(args.max_hold_hours),
                be_trigger_r=float(args.be_trigger_r),
                net_rr_min_mult=float(args.net_rr_min_mult),

                oq_window_trades=int(args.oq_window_trades),
                oq_min_trades=int(args.oq_min_trades),
                oq_pf_min=float(args.oq_pf_min),
                oq_winrate_min=float(args.oq_winrate_min),
                oq_ban_hours=int(args.oq_ban_hours),

                tp_auto=int(args.tp_auto),
                tp_opp_min_width_pct=float(args.tp_opp_min_width_pct),
                tp_buffer_width_frac=float(args.tp_buffer_width_frac),
                tp1_frac=float(args.tp1_frac),

                sl_ban_hours=int(args.sl_ban_hours),

                trades_csv=str(args.trades_csv),
                sl_side_strikes=int(args.sl_side_strikes),
                sl_side_window_hours=int(args.sl_side_window_hours),
                sl_side_ban_hours=int(args.sl_side_ban_hours),

                intrabar_fill=str(args.intrabar_fill),
                break_exit=int(args.break_exit),
                break_buf_atr_mult=float(args.break_buf_atr_mult),
                break_buf_width_frac=float(args.break_buf_width_frac),


            )

            if not res.get("ok"):
                continue

            # run counters
            wf_runs += 1
            wf_dd_max = max(wf_dd_max, float(res.get("max_dd", 0.0)))

            # portfolio sums
            wf_total_pnl += float(res.get("total_pnl", 0.0))
            wf_dd_sum += float(res.get("max_dd", 0.0))
            wf_trades += int(res.get("n", 0))
            wf_wins += int(res.get("wins", 0))
            wf_gross_profit += float(res.get("gross_profit", 0.0))
            wf_gross_loss += float(res.get("gross_loss", 0.0))

            # TP policy counts (лежит в rejects)
            rj = res.get("rejects") or {}
            wf_tp_opp += int(rj.get("tp_policy_opp", 0))
            wf_tp_mid += int(rj.get("tp_policy_mid", 0))

            # TP1 aggregates
            wf_tp1_armed += int(res.get("tp1_armed", 0))
            wf_tp1_hits += int(res.get("tp1_hits", 0))
            wf_tp1_closed_qty += float(res.get("tp1_closed_qty", 0.0))
            wf_tp1_gross += float(res.get("tp1_gross", 0.0))
            wf_tp1_fee += float(res.get("tp1_fee", 0.0))

            # exit reasons
            xc = res.get("exit_counts") or {}
            for k, v in xc.items():
                wf_exit_counts[str(k)] += int(v)

        seg_start = seg_end

    winrate = (wf_wins / max(1, wf_trades)) * 100.0
    print("\n=== WALK-FORWARD SUMMARY ===")
    wf_pf = (wf_gross_profit / wf_gross_loss) if wf_gross_loss > 0 else float("inf")

    print(f"Period: {args.start}..{args.end}")
    print(f"Trades: {wf_trades}  Wins: {wf_wins}  Winrate: {winrate:.1f}%")
    print(f"Total PnL (sum): {wf_total_pnl:+.2f} USDT")
    print(f"Sum MaxDD (naive sum): {wf_dd_sum:.2f} USDT")
    print(f"Profit Factor (portfolio, fee-aware): {wf_pf:.3f}")
    print(f"TP policy counts: opp={wf_tp_opp}  mid={wf_tp_mid}")
    tp1_hr = (wf_tp1_hits / wf_tp1_armed * 100.0) if wf_tp1_armed else 0.0
    dd_avg = (wf_dd_sum / wf_runs) if wf_runs else 0.0  
    print(f"TP1 armed: {wf_tp1_armed}  hits: {wf_tp1_hits}  hit-rate: {tp1_hr:.1f}%")
    print(f"TP1 closed_qty: {wf_tp1_closed_qty:.4f}  gross: {wf_tp1_gross:+.2f}  fee: {wf_tp1_fee:.2f}")
    print(f"MaxDD (max single-run): {wf_dd_max:.2f}  Avg MaxDD (per run): {dd_avg:.2f}  Sum MaxDD (naive): {wf_dd_sum:.2f}")



    print("Exit reasons:", ", ".join(
        f"{k}={v}" for k, v in sorted(wf_exit_counts.items(), key=lambda x: x[1], reverse=True)
    ))

   

def main() -> None:
    asyncio.run(run())

if __name__ == "__main__":
    main()

