#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# smart_pump_reversal_bot.py
# ──────────────────────────────────────────────────────────────────────────────
# Refactor status (see docs/REFACTOR_ROADMAP.md):
#   Phase 1 DONE — extracted to bot/ package:
#     bot.env_helpers  → _env_bool, _csv_lower_set, _csv_upper_set, _session_name_utc
#     bot.utils        → now_s, _to_float_safe, _today_ymd, base_from_usdt, dist_pct
#     bot.auth         → AUTH_DISABLED_UNTIL, AUTH_LAST_ERROR, auth_disabled, mark_auth_fail
#     bot.diagnostics  → RUNTIME_COUNTER, MSG_COUNTER, _diag_inc, _diag_get_int, ...
#     bot.symbol_state → SymState, STATE, S, update_5m_bar, trim + indicator wrappers
#   Phase 2 TODO — BybitClient, telegram, db
#   Phase 3 TODO — strategy entries, risk/portfolio
# ──────────────────────────────────────────────────────────────────────────────

import os
import time, json, statistics, asyncio, requests, collections, re, csv, traceback, random, math
import sqlite3
import subprocess
from pathlib import Path
from typing import Dict, Tuple, List, Optional, Any
import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK, InvalidStatus
from dotenv import load_dotenv
import hmac, hashlib
from urllib.parse import urlencode
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from sr_levels import LevelsService
from sr_bounce import BounceStrategy
from trade_state import TradeState
from inplay_live import InPlayLiveEngine
from breakout_live import BreakoutLiveEngine
try:
    from news_filter import load_news_events, load_news_policy, is_news_blocked as _news_is_blocked
    _NEWS_FILTER_AVAILABLE = True
except ImportError:
    _NEWS_FILTER_AVAILABLE = False
    def load_news_events(p): return []      # type: ignore[misc]
    def load_news_policy(p): return {}      # type: ignore[misc]
    def _news_is_blocked(**kw): return False, ""  # type: ignore[misc]
from midterm_live import MidtermLiveEngine
from retest_live import RetestEngine
from strategies.breakdown_live import BreakdownLiveEngine
from strategies.micro_scalper_live import MicroScalperLiveEngine
from strategies.support_reclaim_live import SupportReclaimLiveEngine
from trade_reporting import generate_report, since_days

from sr_range import RangeRegistry, RangeScanner
from sr_range_strategy import RangeStrategy
from indicators import (
    atr_pct_from_ohlc,
    rsi as rsi_calc,
    ema_incremental,
    candle_pattern as candle_pattern_detect,
    engulfing as engulfing_bear,
    trade_quality as calc_trade_quality,
)

# ── Phase 1: bot/ package imports ────────────────────────────────────────────
from bot.env_helpers import _env_bool, _csv_lower_set, _csv_upper_set, _session_name_utc
from bot.utils import now_s, _to_float_safe, _today_ymd, base_from_usdt, dist_pct
from bot.auth import (
    AUTH_DISABLED_UNTIL, AUTH_LAST_ERROR, BOT_START_TS,
    auth_cooldown_remaining,
    # auth_disabled and mark_auth_fail kept in this file:
    #   auth_disabled → references module-level DRY_RUN
    #   mark_auth_fail → calls tg_trade (defined later in this file)
    #   Both use the shared AUTH_DISABLED_UNTIL dict from bot.auth.
)
from bot.diagnostics import (
    RUNTIME_DIAG_ENABLE, RUNTIME_COUNTER, MSG_COUNTER,
    _diag_inc, _diag_get_int, _runtime_diag_snapshot,
    _breakout_no_signal_diag_key,
)
from bot.deepseek_overlay import DeepSeekOverlay
from bot.deepseek_autoresearch_agent import (
    results_report_text,
    tune_strategy,
    trigger_mini_backtest,
    build_research_context,
    audit_bot_full,
    ask_about_file,
)
from bot.deepseek_action_executor import (
    execute_proposal,
    rollback_env,
    check_server_status,
    diff_pending_changes,
)
from bot.symbol_state import (
    SymState, STATE,
    S, update_5m_bar, trim,
    calc_atr_pct, calc_rsi, ema_val, candle_pattern, engulfing, trade_quality,
)
# ─────────────────────────────────────────────────────────────────────────────

# Load .env before any module-level os.getenv(...) settings below are evaluated.
load_dotenv()

# Минимальная доля "желательного" notional (по риск-сайзингу), которую нужно уметь разместить.
# Если меньше — пропускаем сделку (иначе комиссии/проскальзывание убивают ожидание).
MIN_NOTIONAL_FILL_FRAC = float(os.getenv("MIN_NOTIONAL_FILL_FRAC", "0.40"))


# =========================== ГЛОБАЛ ===========================
# _env_bool, _csv_lower_set, _csv_upper_set, _session_name_utc → bot.env_helpers
# now_s, _to_float_safe, _today_ymd, base_from_usdt, dist_pct  → bot.utils
# AUTH_DISABLED_UNTIL, AUTH_LAST_ERROR, BOT_START_TS           → bot.auth
# RUNTIME_COUNTER, MSG_COUNTER, _diag_inc/get, snapshot        → bot.diagnostics
# SymState, STATE, S, update_5m_bar, trim + indicator wrappers → bot.symbol_state
# (all imported at the top of this file)

DEBUG_WINDOWS = True


def _ws_health_from_delta(connect_delta: int, disconnect_delta: int, handshake_delta: int) -> tuple[str, float, float]:
    c = max(0, int(connect_delta))
    d = max(0, int(disconnect_delta))
    h = max(0, int(handshake_delta))
    if c <= 0:
        if d == 0 and h == 0:
            return "NO_ACTIVITY", 0.0, 0.0
        # A single close without reconnect in the same short window is often transient and
        # should not page as critical.
        if d <= WS_HEALTH_NO_CONNECT_DISC_TOL and h <= WS_HEALTH_NO_CONNECT_HS_TOL:
            return "NO_CONNECT_TRANSIENT", float("inf"), float("inf")
        if d > 0 or h > 0:
            return "CRITICAL_NO_CONNECT", float("inf"), float("inf")
        return "NO_ACTIVITY", 0.0, 0.0
    disc_conn_pct = (100.0 * d) / max(1, c)
    hs_conn_pct = (100.0 * h) / max(1, c)
    if disc_conn_pct >= WS_HEALTH_CRIT_DISC_CONN_PCT or hs_conn_pct >= WS_HEALTH_CRIT_HANDSHAKE_CONN_PCT:
        return "CRITICAL", disc_conn_pct, hs_conn_pct
    if disc_conn_pct >= WS_HEALTH_WARN_DISC_CONN_PCT or hs_conn_pct >= WS_HEALTH_WARN_HANDSHAKE_CONN_PCT:
        return "WARN", disc_conn_pct, hs_conn_pct
    return "OK", disc_conn_pct, hs_conn_pct


def _fmt_ratio_or_inf(v: float) -> str:
    if math.isinf(v):
        return "inf"
    try:
        return f"{float(v):.1f}%"
    except Exception:
        return "n/a"


# _breakout_no_signal_diag_key → moved to bot.diagnostics (imported above)

def auth_disabled(name: str) -> bool:
    """Check if auth is disabled for account `name`. Uses module-level DRY_RUN."""
    if DRY_RUN:
        return False
    until = int((AUTH_DISABLED_UNTIL.get(name) or 0))
    return int(time.time()) < until


def mark_auth_fail(name: str, err: Exception, cooldown_sec: int = 600):
    """Record auth failure, disable private calls for cooldown_sec.
    Uses shared AUTH_DISABLED_UNTIL from bot.auth.
    FIX: guard against flood-logging — downstream callers check auth_disabled()
    before each request, so errors.log will stop flooding after first failure.
    """
    AUTH_DISABLED_UNTIL[name] = int(time.time()) + int(cooldown_sec)
    AUTH_LAST_ERROR[name] = str(err)[:300]
    try:
        tg_trade(
            f"🛑 AUTH FAIL [{name}]: {AUTH_LAST_ERROR[name]}\n"
            f"Отключаю приватные вызовы на {cooldown_sec // 60} мин."
        )
    except Exception:
        pass


# — логируем "почти прошёл фильтр", чтобы понимать, что зарезало
NEAR_MISS_LOG = True
def _near(v, thr, tol):
    try:
        return abs(float(v) - float(thr)) <= float(tol)
    except Exception:
        return False


# =========================== ПАРАМЕТРЫ ДЕТЕКТОРА ===========================
WINDOW_SEC = 300
BASE_WINDOWS = 12

DELTA_PCT_THR = 10.0 
VBOOST = 1.03
MIN_WINDOW_QUOTE_USD = 200_000
MIN_24H_TURNOVER = 300_000

ACCEL_K = 1.05
IMBALANCE_THR = 0.50
COOLDOWN_SEC = 1800
PING_INTERVAL = 30

Z_MAD_THR = 4.0
MIN_TRADES = 200

MIN_ATR_MULT = 0.5
REQUIRE_TWO_HITS = False
BODY_RATIO_MIN = 0.40

REV_WINDOW_SEC = 3600
REV_DROP_PCT_NORMAL = 1.5   # обычный кейс: нужен откат 0.80% от пика
REV_DROP_PCT_STRONG = 1.0   # для сильного пампа: хватит 0.60%

VERIFY_SNAPSHOT = False
SNAPSHOT_MAX_DEVIATION_PCT = 1.0
REST_TIMEOUT = 7

EMA_FAST = 20
EMA_SLOW = 60
CTX_5M_SEC = 300
CTX_MIN_MOVE = 0.10

STRONG_RET_THR      = 1.6      # мин. рост окна, %
STRONG_VBOOST       = 2.0      # в x раз к медиане объёма окна
STRONG_ACCEL        = 2.0      # ускорение второй половины окна vs первой
STRONG_ZMAD         = 3.0      # zMAD по объёму
STRONG_MIN_QUOTE    = 60_000   # мин. квоут в окне, USDT
STRONG_CTX_MIN      = 1.2      # мин. +движение за 5м контекст, %

EXPANSION_MIN_PCT = 0.5      
CLOSE_IN_TOP_FRAC = 0.35   

ENABLE_BYBIT = True
ENABLE_BINANCE = False
ENABLE_MEXC = False
TOP_N_BYBIT = int(os.getenv("TOP_N_BYBIT", "120"))
TOP_N_BINANCE = int(os.getenv("TOP_N_BINANCE", "200"))

# ===== INPLAY (live) =====
ENABLE_INPLAY_TRADING = os.getenv("ENABLE_INPLAY_TRADING", "0").strip() == "1"
INPLAY_TRY_EVERY_SEC = int(os.getenv("INPLAY_TRY_EVERY_SEC", "30"))
INPLAY_TOP_N = int(os.getenv("INPLAY_TOP_N", "60"))
INPLAY_SYMBOLS = set()
INPLAY_ENGINE = None

# ===== BREAKOUT (live) =====
ENABLE_BREAKOUT_TRADING = os.getenv("ENABLE_BREAKOUT_TRADING", "0").strip() == "1"
ENABLE_PUMP_FADE_TRADING = os.getenv("ENABLE_PUMP_FADE_TRADING", "0").strip() == "1"
ENABLE_MIDTERM_TRADING = os.getenv("ENABLE_MIDTERM_TRADING", "0").strip() == "1"
BREAKOUT_TRY_EVERY_SEC = int(os.getenv("BREAKOUT_TRY_EVERY_SEC", "30"))
BREAKOUT_TOP_N = int(os.getenv("BREAKOUT_TOP_N", "60"))
BREAKOUT_MAX_SPREAD_PCT = float(os.getenv("BREAKOUT_MAX_SPREAD_PCT", "0.20"))
BREAKOUT_MAX_CHASE_PCT = float(os.getenv("BREAKOUT_MAX_CHASE_PCT", "0.15"))
BREAKOUT_REQUIRE_RETEST_CONFIRM = os.getenv("BREAKOUT_REQUIRE_RETEST_CONFIRM", "1").strip() == "1"
BREAKOUT_RETEST_TOUCH_PCT = float(os.getenv("BREAKOUT_RETEST_TOUCH_PCT", "0.15"))
BREAKOUT_MIN_STOP_ATR_MULT = float(os.getenv("BREAKOUT_MIN_STOP_ATR_MULT", "0.80"))
BREAKOUT_SL_COOLDOWN_SEC = int(os.getenv("BREAKOUT_SL_COOLDOWN_SEC", "2700"))
BREAKOUT_REF_LOOKBACK_BARS = int(os.getenv("BREAKOUT_REF_LOOKBACK_BARS", "20"))
BREAKOUT_MAX_LATE_VS_REF_PCT = float(os.getenv("BREAKOUT_MAX_LATE_VS_REF_PCT", "0.35"))
BREAKOUT_MIN_PULLBACK_FROM_EXTREME_PCT = float(os.getenv("BREAKOUT_MIN_PULLBACK_FROM_EXTREME_PCT", "0.08"))
BREAKOUT_SIZEUP_ENABLE = _env_bool("BREAKOUT_SIZEUP_ENABLE", True)
BREAKOUT_SIZEUP_MAX_MULT = max(1.0, float(os.getenv("BREAKOUT_SIZEUP_MAX_MULT", "1.30")))
BREAKOUT_SIZEUP_MIN_SCORE = min(0.95, max(0.10, float(os.getenv("BREAKOUT_SIZEUP_MIN_SCORE", "0.62"))))
BREAKOUT_QUALITY_MIN_SCORE = max(0.0, min(0.99, float(os.getenv("BREAKOUT_QUALITY_MIN_SCORE", "0.00"))))
BREAKOUT_QUALITY_BOOST_ENABLE = _env_bool("BREAKOUT_QUALITY_BOOST_ENABLE", True)
BREAKOUT_QUALITY_BOOST_SCORE_1 = max(0.0, min(1.0, float(os.getenv("BREAKOUT_QUALITY_BOOST_SCORE_1", "0.78"))))
BREAKOUT_QUALITY_BOOST_MULT_1 = max(1.0, float(os.getenv("BREAKOUT_QUALITY_BOOST_MULT_1", "1.10")))
BREAKOUT_QUALITY_BOOST_SCORE_2 = max(0.0, min(1.0, float(os.getenv("BREAKOUT_QUALITY_BOOST_SCORE_2", "0.88"))))
BREAKOUT_QUALITY_BOOST_MULT_2 = max(1.0, float(os.getenv("BREAKOUT_QUALITY_BOOST_MULT_2", "1.20")))
BREAKOUT_MIN_QUOTE_5M_USD = max(0.0, float(os.getenv("BREAKOUT_MIN_QUOTE_5M_USD", "70000")))
BREAKOUT_SESSION_FILTER_ENABLE = _env_bool("BREAKOUT_SESSION_FILTER_ENABLE", False)
BREAKOUT_SESSION_ALLOWED = _csv_lower_set("BREAKOUT_SESSION_ALLOWED")
BREAKOUT_SYMBOL_ALLOWLIST = _csv_upper_set("BREAKOUT_SYMBOL_ALLOWLIST")
BREAKOUT_SYMBOL_DENYLIST = _csv_upper_set("BREAKOUT_SYMBOL_DENYLIST")
BREAKOUT_SYMBOLS = set()
BREAKOUT_ENGINE = None

# ── News filter (runtime/news_filter/) ───────────────────────────────────────
_NEWS_FILTER_ENABLE = _env_bool("NEWS_FILTER_ENABLE", True)
_NEWS_EVENTS_PATH = os.getenv("NEWS_EVENTS_PATH", "runtime/news_filter/events.csv")
_NEWS_POLICY_PATH = os.getenv("NEWS_POLICY_PATH", "runtime/news_filter/policy.json")
_NEWS_EVENTS: list = []
_NEWS_POLICY: dict = {}
_NEWS_CACHE_TS: int = 0
_NEWS_CACHE_TTL: int = 300   # reload events every 5 minutes

MIDTERM_TRY_EVERY_SEC = int(os.getenv("MIDTERM_TRY_EVERY_SEC", "90"))
MIDTERM_NOTIONAL_MULT = max(0.05, min(1.0, float(os.getenv("MIDTERM_NOTIONAL_MULT", "0.35"))))
MIDTERM_ALLOW_MINQTY_FALLBACK = _env_bool("MIDTERM_ALLOW_MINQTY_FALLBACK", True)
MIDTERM_MINQTY_FALLBACK_MAX_MULT = max(1.0, float(os.getenv("MIDTERM_MINQTY_FALLBACK_MAX_MULT", "1.80")))
MIDTERM_SYMBOLS = {s.strip().upper() for s in str(os.getenv("MIDTERM_SYMBOLS", "BTCUSDT,ETHUSDT")).split(",") if s.strip()}
MIDTERM_ACTIVE_SYMBOLS = set()
MIDTERM_ENGINE = None

# ===== Live allocator (risk mult by regime/strategy) =====
LIVE_ALLOCATOR_ENABLE = _env_bool("LIVE_ALLOCATOR_ENABLE", False)
LIVE_ALLOCATOR_MULT_MIN = max(0.10, float(os.getenv("LIVE_ALLOCATOR_MULT_MIN", "0.60")))
LIVE_ALLOCATOR_MULT_MAX = max(LIVE_ALLOCATOR_MULT_MIN, float(os.getenv("LIVE_ALLOCATOR_MULT_MAX", "1.40")))
LIVE_ALLOCATOR_BREAKOUT_TREND_MULT = max(0.10, float(os.getenv("LIVE_ALLOCATOR_BREAKOUT_TREND_MULT", "1.12")))
LIVE_ALLOCATOR_BREAKOUT_FLAT_MULT = max(0.10, float(os.getenv("LIVE_ALLOCATOR_BREAKOUT_FLAT_MULT", "0.80")))
LIVE_ALLOCATOR_MIDTERM_TREND_MULT = max(0.10, float(os.getenv("LIVE_ALLOCATOR_MIDTERM_TREND_MULT", "0.90")))
LIVE_ALLOCATOR_MIDTERM_FLAT_MULT = max(0.10, float(os.getenv("LIVE_ALLOCATOR_MIDTERM_FLAT_MULT", "1.12")))

# ===== RETEST LEVELS (live) =====
ENABLE_RETEST_TRADING = os.getenv("ENABLE_RETEST_TRADING", "0").strip() == "1"
RETEST_TRY_EVERY_SEC = int(os.getenv("RETEST_TRY_EVERY_SEC", "60"))
RETEST_TOP_N = int(os.getenv("RETEST_TOP_N", "60"))
RETEST_SYMBOLS = set()
RETEST_ENGINE = None

# ===== SLOPED CHANNEL (live) =====
ENABLE_SLOPED_TRADING = os.getenv("ENABLE_SLOPED_TRADING", "0").strip() == "1"
SLOPED_TRY_EVERY_SEC = int(os.getenv("SLOPED_TRY_EVERY_SEC", "60"))
SLOPED_RISK_MULT = max(0.05, float(os.getenv("SLOPED_RISK_MULT", "1.0")))
SLOPED_MAX_OPEN_TRADES = int(os.getenv("SLOPED_MAX_OPEN_TRADES", "1"))
SLOPED_ENGINE = None

# ===== FLAT RESISTANCE FADE (live) =====
ENABLE_FLAT_TRADING = os.getenv("ENABLE_FLAT_TRADING", "0").strip() == "1"
FLAT_TRY_EVERY_SEC = int(os.getenv("FLAT_TRY_EVERY_SEC", "60"))
FLAT_RISK_MULT = max(0.05, float(os.getenv("FLAT_RISK_MULT", "1.0")))
FLAT_MAX_OPEN_TRADES = int(os.getenv("FLAT_MAX_OPEN_TRADES", "1"))
FLAT_ENGINE = None

# ===== BREAKDOWN SHORTS (live) =====
ENABLE_BREAKDOWN_TRADING = os.getenv("ENABLE_BREAKDOWN_TRADING", "0").strip() == "1"
BREAKDOWN_TRY_EVERY_SEC = int(os.getenv("BREAKDOWN_TRY_EVERY_SEC", "60"))
BREAKDOWN_RISK_MULT = max(0.05, float(os.getenv("BREAKDOWN_RISK_MULT", "0.10")))
BREAKDOWN_MAX_OPEN_TRADES = int(os.getenv("BREAKDOWN_MAX_OPEN_TRADES", "1"))
BREAKDOWN_ENGINE = None

# ===== MICRO SCALPER (live) =====
ENABLE_MICRO_SCALPER_TRADING = os.getenv("ENABLE_MICRO_SCALPER_TRADING", "0").strip() == "1"
MICRO_SCALPER_TRY_EVERY_SEC = int(os.getenv("MICRO_SCALPER_TRY_EVERY_SEC", "30"))
MICRO_SCALPER_RISK_MULT = max(0.05, float(os.getenv("MICRO_SCALPER_RISK_MULT", "0.10")))
MICRO_SCALPER_MAX_OPEN_TRADES = int(os.getenv("MICRO_SCALPER_MAX_OPEN_TRADES", "2"))
MICRO_SCALPER_SYMBOL_ALLOWLIST: set[str] = {s.strip().upper() for s in str(os.getenv("MICRO_SCALPER_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT,SOLUSDT")).split(",") if s.strip()}
MICRO_SCALPER_ENGINE = None
_MICRO_SCALPER_LAST_TRY: dict[str, float] = {}

# ===== SUPPORT RECLAIM LONGS (live) =====
ENABLE_SUPPORT_RECLAIM_TRADING = os.getenv("ENABLE_SUPPORT_RECLAIM_TRADING", "0").strip() == "1"
SUPPORT_RECLAIM_TRY_EVERY_SEC = int(os.getenv("SUPPORT_RECLAIM_TRY_EVERY_SEC", "60"))
SUPPORT_RECLAIM_RISK_MULT = max(0.05, float(os.getenv("SUPPORT_RECLAIM_RISK_MULT", "0.10")))
SUPPORT_RECLAIM_MAX_OPEN_TRADES = int(os.getenv("SUPPORT_RECLAIM_MAX_OPEN_TRADES", "1"))
SUPPORT_RECLAIM_SYMBOL_ALLOWLIST: set[str] = {s.strip().upper() for s in str(os.getenv("SUPPORT_RECLAIM_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT")).split(",") if s.strip()}
SUPPORT_RECLAIM_ENGINE = None
_SUPPORT_RECLAIM_LAST_TRY: dict[str, float] = {}

# ===== TRIPLE SCREEN v132 (live) =====
ENABLE_TS132_TRADING = os.getenv("ENABLE_TS132_TRADING", "0").strip() == "1"
TS132_TRY_EVERY_SEC = int(os.getenv("TS132_TRY_EVERY_SEC", "60"))
TS132_SYMBOLS = {s.strip().upper() for s in str(os.getenv("TS132_SYMBOLS", "")).split(",") if s.strip()}
TS132_ENGINE = None

LOG_SIGNALS = True
SIGNALS_CSV = "signals.csv"
ERRORS_LOG = "errors.log"

# =========================== ПАРАМЕТРЫ ТОРГОВЛИ ===========================
TRADE_ON = True
BYBIT_LEVERAGE = 3               
MIN_NOTIONAL_USD = 10.0
BOT_CAPITAL_USD = None

USE_HALF_EQUITY_PER_TRADE = False
MIN_LEG_USD = 5.0              
MAX_LEG_USD = 12.0        
RESERVE_EQUITY_FRAC = 0.05     


LEG1_USD = 5                     
LEG2_USD = 5                     

DCA_ENTRY_UP_PCT = 0.6
DCA_BREAK_PEAK_PCT = 0.20

TP_PCT = 0.50
SL_PCT = 0.30                   
STALL_BOUNCE_PCT = 0.15
STALL_MIN_SELL_IMB = 0.52

# === Risk sizing (1% risk) ===
USE_RISK_SIZING = True
RISK_PER_TRADE_PCT = 1.0
MAX_OPEN_PORTFOLIO_RISK_PCT = float(os.getenv("MAX_OPEN_PORTFOLIO_RISK_PCT", "0") or 0)

# "почти без плеча": максимум notional = equity (а не equity*leverage)
CAP_NOTIONAL_TO_EQUITY = True

# === Exchange TP/SL reliability ===
ALWAYS_SET_TPSL_ON_EXCHANGE = True
TPSL_RETRY_ATTEMPTS = 5
TPSL_RETRY_DELAY_SEC = 0.8
TPSL_ENSURE_EVERY_SEC = 20  

# === Manual TP/SL override (если поменял руками на бирже — бот не перезатирает) ===
RESPECT_MANUAL_TPSL = True          # главный переключатель
MANUAL_TPSL_MIN_AGE_SEC = 12        # не считаем "ручным" изменение в первые N секунд после входа/обновления
MANUAL_TPSL_DETECT_TICKS = 2        # допуск расхождения в "тиках" (tickSize * N), чтобы не ловить шум


# =========================== BOUNCE DEBUG/CONTROL ===========================
BOUNCE_DEBUG = _env_bool("BOUNCE_DEBUG", True)
# Control bounce-related Telegram chatter when bounce is disabled
BOUNCE_TG_LOGS = _env_bool("BOUNCE_TG_LOGS", True)
BOUNCE_LOG_ONLY = _env_bool("BOUNCE_LOG_ONLY", True)
BOUNCE_TG_DEBUG_WHEN_LOG_ONLY = _env_bool("BOUNCE_TG_DEBUG_WHEN_LOG_ONLY", False)
BOUNCE_DEBUG_CSV = "bounce_debug.csv"

BOUNCE_MAX_DIST_PCT = 0.60
BOUNCE_EXECUTE_TRADES = True  # False = только логировать

# --- Bounce extra filters (то, что ты спросил "куда это") ---
BOUNCE_REQUIRE_TREND_MATCH = True       # не торговать bounce против EMA20/EMA60
BOUNCE_MAX_BREAKOUT_RISK   = 0.55       # максимум допустимого breakout_risk
BOUNCE_MIN_POTENTIAL_PCT   = 0.30       # минимум потенциала (в %)
BOUNCE_MIN_GROSS_MOVE_PCT  = float(os.getenv("BOUNCE_MIN_GROSS_MOVE_PCT", "0.35"))
BOUNCE_EST_ROUNDTRIP_COST_PCT = float(os.getenv("BOUNCE_EST_ROUNDTRIP_COST_PCT", "0.25"))
BOUNCE_MIN_NET_MOVE_PCT = float(os.getenv("BOUNCE_MIN_NET_MOVE_PCT", "0.12"))
BOUNCE_MIN_NET_RR = float(os.getenv("BOUNCE_MIN_NET_RR", "0.70"))

# === Bounce universe control ===
BOUNCE_TOP_N = 50                 # bounce только на топ-50 ликвидных инструментов
BOUNCE_SYMBOLS = set()            # заполнится в bybit_ws() после получения syms

ENTRY_CONFIRM_GRACE_SEC = 25   # сколько ждём "позиция появится" прежде чем признать FAIL
ENTRY_TIMEOUT_SEC = 120   
ENTRY_CONFIRM_POLL_SEC  = 0.8

PENDING_PNL_MAX_SEC = 180  # 3 минуты
_KLINE_CACHE = {}  # key=(symbol, interval) -> (ts, data)
PUBLIC_RL_UNTIL = 0
PUBLIC_RL_BACKOFF_SEC = 25


PUMP5_MIN_PCT = float(os.getenv("PUMP5_MIN_PCT", "10.0"))
PUMP5_MIN_QUOTE = float(os.getenv("PUMP5_MIN_QUOTE", "200000"))
PUMP5_COOLDOWN_SEC = int(os.getenv("PUMP5_COOLDOWN_SEC", "3600"))
PUMP5_REV_DROP_PCT = float(os.getenv("PUMP5_REV_DROP_PCT", "1.5"))
PUMP5_STOP_BUFFER_PCT = float(os.getenv("PUMP5_STOP_BUFFER_PCT", "0.3"))
PUMP5_TP_RETRACE_FRAC = float(os.getenv("PUMP5_TP_RETRACE_FRAC", "0.5"))  # 50% retrace


def fetch_kline(symbol: str, interval: str, limit: int = 200, base_url: Optional[str] = None):
    """
    Унифицированный fetch klines для Bybit v5 /market/kline.
    interval: "1","5","15","60","240"...
    Возвращает tuple(o,h,l,c,vol,to,t) как в sr_bounce.py (t в секундах, chronological).
    """
    base = (base_url or (TRADE_CLIENT.base if TRADE_CLIENT else BYBIT_BASE_DEFAULT)).rstrip("/")

    r = requests.get(
        f"{base}/v5/market/kline",
        params={"category": "linear", "symbol": symbol, "interval": str(interval), "limit": int(limit)},
        timeout=10,
    )
    r.raise_for_status()
    j = r.json()
    if str(j.get("retCode")) != "0":
        raise RuntimeError(f"kline({interval}) error: {j}")

    rows = (j.get("result") or {}).get("list") or []
    rows.reverse()  # chronological

    t = [int(int(x[0]) // 1000) for x in rows]
    o = [float(x[1]) for x in rows]
    h = [float(x[2]) for x in rows]
    l = [float(x[3]) for x in rows]
    c = [float(x[4]) for x in rows]

    vol = []
    to = []
    for x in rows:
        vol.append(float(x[5]) if len(x) > 5 and x[5] not in (None, "") else 0.0)
        to.append(float(x[6]) if len(x) > 6 and x[6] not in (None, "") else 0.0)

    return o, h, l, c, vol, to, t


fetch_kline_tuple = fetch_kline      

# --- COMPAT: старые имена, чтобы ничего не падало, если где-то их зовут ---
async def fetch_klines_for_range(symbol: str, interval: str, limit: int):
    """
    sr_range ждёт RAW Bybit v5 klines: [[ts, o, h, l, c, v, turnover], ...]
    Совместимо со старым поведением, но без лишних compat-обёрток.
    """
    return await asyncio.to_thread(fetch_klines, symbol, interval, limit)

_KLINE_RAW_CACHE = {}  # (symbol, interval, limit) -> (saved_time, rows)
KLINE_STALE_GRACE_SEC = int(os.getenv("KLINE_STALE_GRACE_SEC", "90"))
KLINE_STALE_MAX_BARS = float(os.getenv("KLINE_STALE_MAX_BARS", "2.5"))


def _kline_cache_ttl_sec(interval: str) -> float:
    interval_sec = _interval_to_seconds(interval)
    if interval_sec <= 5 * 60:
        return 20.0
    if interval_sec <= 15 * 60:
        return 45.0
    if interval_sec <= 60 * 60:
        return 120.0
    return 300.0


def _interval_to_seconds(interval: str) -> int:
    iv = str(interval).strip().upper()
    if iv.isdigit():
        return max(60, int(iv) * 60)
    mapping = {
        "D": 86400,
        "W": 7 * 86400,
        "M": 30 * 86400,
    }
    return int(mapping.get(iv, 300))


def _latest_kline_age_sec(rows: list) -> Optional[float]:
    if not rows:
        return None
    try:
        ts_raw = int(rows[-1][0])
    except Exception:
        return None
    ts_s = ts_raw / 1000.0 if ts_raw > 10**11 else float(ts_raw)
    return max(0.0, time.time() - ts_s)


def _klines_are_fresh(rows: list, interval: str) -> bool:
    age = _latest_kline_age_sec(rows)
    if age is None:
        return False
    interval_sec = _interval_to_seconds(interval)
    max_age_sec = max(float(KLINE_STALE_GRACE_SEC), float(interval_sec) * float(KLINE_STALE_MAX_BARS))
    return age <= max_age_sec


def fetch_klines(symbol: str, interval: str, limit: int):
    """
    Возвращает список свечей Bybit v5 kline в формате list-of-lists (как приходит от API),
    отсортированный от старых к новым.
    """
    base = (getattr(TRADE_CLIENT, "base", None) or os.getenv("BYBIT_BASE") or "https://api.bybit.com").rstrip("/")
    limit = int(limit)

    key = (symbol, str(interval), limit)
    now = time.time()
    hit = _KLINE_RAW_CACHE.get(key)
    ttl_sec = _kline_cache_ttl_sec(interval)
    if hit and (now - hit[0] < ttl_sec) and _klines_are_fresh(hit[1], interval):
        return hit[1]
    global PUBLIC_RL_UNTIL
    if PUBLIC_RL_UNTIL > now:
        if hit and _klines_are_fresh(hit[1], interval):
            return hit[1]
        raise RuntimeError(f"Bybit public RL backoff active for {max(0.0, PUBLIC_RL_UNTIL - now):.1f}s")

    r = requests.get(
        f"{base}/v5/market/kline",
        params={"category": "linear", "symbol": symbol, "interval": str(interval), "limit": limit},
        timeout=10,
    )
    r.raise_for_status()
    j = r.json()
    if str(j.get("retCode")) != "0":
        if str(j.get("retCode")) == "10006":
            PUBLIC_RL_UNTIL = max(PUBLIC_RL_UNTIL, now + float(PUBLIC_RL_BACKOFF_SEC))
            if hit and _klines_are_fresh(hit[1], interval):
                return hit[1]
        raise RuntimeError(f"Bybit kline error: {j}")

    rows = ((j.get("result") or {}).get("list") or [])
    rows = list(reversed(rows))  # делаем: старые -> новые

    if rows and not _klines_are_fresh(rows, interval):
        age = _latest_kline_age_sec(rows)
        interval_sec = _interval_to_seconds(interval)
        max_age_sec = max(float(KLINE_STALE_GRACE_SEC), float(interval_sec) * float(KLINE_STALE_MAX_BARS))
        raise RuntimeError(
            f"Bybit kline stale: symbol={symbol} interval={interval} "
            f"age={0.0 if age is None else age:.1f}s max={max_age_sec:.1f}s"
        )

    _KLINE_RAW_CACHE[key] = (now, rows)
    return rows

# init inplay live engine after fetch_klines is available
if INPLAY_ENGINE is None:
    INPLAY_ENGINE = InPlayLiveEngine(fetch_klines)
if BREAKOUT_ENGINE is None:
    BREAKOUT_ENGINE = BreakoutLiveEngine(fetch_klines)
if RETEST_ENGINE is None:
    RETEST_ENGINE = RetestEngine(fetch_klines)
if MIDTERM_ENGINE is None:
    MIDTERM_ENGINE = MidtermLiveEngine(fetch_klines)


def _atr_abs_from_klines(rows: list, period: int) -> float:
    if not rows or period <= 0 or len(rows) < period + 2:
        return 0.0
    trs = []
    # rows: [ts, o, h, l, c, v, ...]
    for i in range(1, len(rows)):
        try:
            h = float(rows[i][2]); l = float(rows[i][3]); pc = float(rows[i-1][4])
        except Exception:
            return 0.0
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    tail = trs[-period:]
    if not tail:
        return 0.0
    return float(sum(tail) / len(tail))

def _pos_size_abs(pos: dict) -> float:
    # подстроено под Bybit: size часто строка
    try:
        return abs(float(pos.get("size", 0) or 0))
    except Exception:
        return 0.0

def _pos_avg_price(pos: dict) -> float:
    try:
        return float(pos.get("avgPrice", 0) or 0)
    except Exception:
        return 0.0



def _append_csv(path: str, fieldnames: list, row: dict):
    new_file = not os.path.exists(path)
    try:
        with open(path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if new_file:
                w.writeheader()
            w.writerow(row)
    except Exception as e:
        log_error(f"csv write fail {path}: {e}")

def log_bounce_debug(row: dict):
    if not BOUNCE_DEBUG:
        return

    fields = [
        "ts","symbol","price","level","kind","tf","side",
        "dist_pct","risk","potential_pct","tp","sl",
        "ob_pressure","atr_5m","volume_factor","false_breakout","micro_trend_ok","mtf_ok",
        "stop_pct","dyn_usd","qty_raw","qty_floor","min_qty","qty_step","notional_real","cap_notional",
        "decision","reason","note"
    ]

    _append_csv(BOUNCE_DEBUG_CSV, fields, row)

# dist_pct → bot.utils (imported above)

# =========================== ПОРТФЕЛЬНЫЕ ЛИМИТЫ ===========================
MAX_POSITIONS = 1
DAILY_LOSS_LIMIT_PCT = 2.0      
MAX_DRAWDOWN_PCT = 5.0           # от стартового equity бота
PORTFOLIO_STATE = {
    "start_equity": None,
    "day_equity_start": None,
    "day": None,
    "daily_pnl_usd": 0.0,
    "disabled": False,
}

def tg_trade(msg: str):
    # шлём только важное — вход/выход/ошибки по торговле
    if not (TG_TOKEN and TG_CHAT):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": msg},
            timeout=10
        )
    except Exception:
        pass


_TG_ALERT_THROTTLE_TS: dict[str, int] = {}
BREAKOUT_SKIP_ALERT_COOLDOWN_SEC = int(os.getenv("BREAKOUT_SKIP_ALERT_COOLDOWN_SEC", "14400") or 14400)
BREAKOUT_SKIP_DIGEST_ENABLE = _env_bool("BREAKOUT_SKIP_DIGEST_ENABLE", True)
BREAKOUT_SKIP_DIGEST_EVERY_SEC = max(300, int(os.getenv("BREAKOUT_SKIP_DIGEST_EVERY_SEC", "14400") or 14400))
BREAKOUT_SKIP_DIGEST_TOP_N = max(1, int(os.getenv("BREAKOUT_SKIP_DIGEST_TOP_N", "8") or 8))
BREAKOUT_SKIP_TG_IMMEDIATE = _env_bool("BREAKOUT_SKIP_TG_IMMEDIATE", False)
_BREAKOUT_SKIP_DIGEST_COUNTS: dict[tuple[str, str], int] = {}
_BREAKOUT_SKIP_DIGEST_LAST_SENT_TS = int(time.time())


def tg_trade_throttled(key: str, msg: str, cooldown_sec: int) -> bool:
    if cooldown_sec <= 0:
        tg_trade(msg)
        return True
    now = int(time.time())
    last_ts = int(_TG_ALERT_THROTTLE_TS.get(key, 0) or 0)
    if last_ts > 0 and (now - last_ts) < int(cooldown_sec):
        return False
    _TG_ALERT_THROTTLE_TS[key] = now
    tg_trade(msg)
    return True


def _record_breakout_skip(symbol: str, reason_key: str) -> None:
    key = (str(symbol or "?"), str(reason_key or "other"))
    _BREAKOUT_SKIP_DIGEST_COUNTS[key] = int(_BREAKOUT_SKIP_DIGEST_COUNTS.get(key, 0) or 0) + 1


def _flush_breakout_skip_digest(force: bool = False) -> bool:
    global _BREAKOUT_SKIP_DIGEST_LAST_SENT_TS
    if not BREAKOUT_SKIP_DIGEST_ENABLE:
        return False
    if not _BREAKOUT_SKIP_DIGEST_COUNTS:
        return False
    now = int(time.time())
    if not force and (now - int(_BREAKOUT_SKIP_DIGEST_LAST_SENT_TS or 0)) < int(BREAKOUT_SKIP_DIGEST_EVERY_SEC):
        return False

    reason_totals: dict[str, int] = {}
    symbol_totals: dict[str, int] = {}
    for (sym, reason), cnt in list(_BREAKOUT_SKIP_DIGEST_COUNTS.items()):
        reason_totals[reason] = int(reason_totals.get(reason, 0) or 0) + int(cnt)
        symbol_totals[sym] = int(symbol_totals.get(sym, 0) or 0) + int(cnt)

    total = sum(int(v) for v in _BREAKOUT_SKIP_DIGEST_COUNTS.values())
    if total <= 0:
        _BREAKOUT_SKIP_DIGEST_COUNTS.clear()
        _BREAKOUT_SKIP_DIGEST_LAST_SENT_TS = now
        return False

    def _fmt_top(d: dict[str, int]) -> str:
        items = sorted(d.items(), key=lambda kv: (-int(kv[1]), kv[0]))[: int(BREAKOUT_SKIP_DIGEST_TOP_N)]
        return ", ".join(f"{k}={v}" for k, v in items) if items else "n/a"

    window_min = max(1, int(round((now - int(_BREAKOUT_SKIP_DIGEST_LAST_SENT_TS or now)) / 60.0)))
    msg = (
        f"🧾 BREAKOUT skip digest ({window_min}m)\n"
        f"total={total}\n"
        f"reasons: {_fmt_top(reason_totals)}\n"
        f"symbols: {_fmt_top(symbol_totals)}"
    )
    tg_trade(msg)
    _BREAKOUT_SKIP_DIGEST_COUNTS.clear()
    _BREAKOUT_SKIP_DIGEST_LAST_SENT_TS = now
    return True

# =========================== TELEGRAM UI ===========================
TG_KB = {
    "keyboard": [
        ["📊 /status", "🧾 /status_full"],
        ["✅ /ping"],
        ["⏸ /pause", "▶ /resume"],
        ["ℹ /help", "🤖 /ai"],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": False,
}

BUTTON_MAP = {
    "📊 /status": "/status",
    "🧾 /status_full": "/status_full",
    "✅ /ping": "/ping",
    "⏸ /pause": "/pause",
    "▶ /resume": "/resume",
    "ℹ /help": "/help",
    "🤖 /ai": "/ai",
}

# =========================== .env ===========================
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT  = os.getenv("TG_CHAT")

DRY_RUN = os.getenv("DRY_RUN", "True").strip().lower() in ("1","true","yes","y")
BYBIT_BASE_DEFAULT = os.getenv("BYBIT_BASE", "https://api.bybit.com")

_single_key    = os.getenv("BYBIT_API_KEY") or ""
_single_secret = os.getenv("BYBIT_API_SECRET") or ""
_accounts_json = os.getenv("BYBIT_ACCOUNTS_JSON", "").strip()

try:
    ACCOUNTS = json.loads(_accounts_json) if _accounts_json else (
        [{"name":"main","key":_single_key,"secret":_single_secret,"base":BYBIT_BASE_DEFAULT}] if (_single_key and _single_secret) else []
    )
except Exception:
    ACCOUNTS = []

TRADE_ACCOUNT_NAME = os.getenv("TRADE_ACCOUNT_NAME", "main")
BYBIT_POS_MODE = os.getenv("BYBIT_POSITION_MODE", "oneway").strip().lower()  # "oneway" | "hedge"
POS_IS_ONEWAY = (BYBIT_POS_MODE != "hedge")

ENABLE_RANGE_TRADING = os.getenv("ENABLE_RANGE_TRADING", "0").strip() == "1"
RANGE_RESCAN_SEC = int(os.getenv("RANGE_RESCAN_SEC", "14400"))
RANGE_LOOKBACK_H = int(os.getenv("RANGE_LOOKBACK_H", "72"))
RANGE_SCAN_TF = os.getenv("RANGE_SCAN_TF", "60").strip()
MIN_RANGE_PCT = float(os.getenv("MIN_RANGE_PCT", "3.0"))
MAX_RANGE_PCT = float(os.getenv("MAX_RANGE_PCT", "8.0"))
RANGE_MIN_TOUCHES = int(os.getenv("RANGE_MIN_TOUCHES", "3"))
RANGE_CONFIRM_LIMIT = int(os.getenv("RANGE_CONFIRM_LIMIT", "40"))
RANGE_ATR_PERIOD = int(os.getenv("RANGE_ATR_PERIOD", "14"))
RANGE_CONFIRM_TF = os.getenv("RANGE_CONFIRM_TF", "5").strip()

RANGE_ENTRY_ZONE_FRAC = float(os.getenv("RANGE_ENTRY_ZONE_FRAC", "0.08"))
RANGE_SWEEP_FRAC = float(os.getenv("RANGE_SWEEP_FRAC", "0.02"))
RANGE_RECLAIM_FRAC = float(os.getenv("RANGE_RECLAIM_FRAC", "0.01"))
RANGE_WICK_FRAC_MIN = float(os.getenv("RANGE_WICK_FRAC_MIN", "0.35"))
RANGE_REQUIRE_PREV_SWEEP = os.getenv("RANGE_REQUIRE_PREV_SWEEP", "1").strip() == "1"
RANGE_IMPULSE_BODY_ATR_MAX = float(os.getenv("RANGE_IMPULSE_BODY_ATR_MAX", "0.90"))
RANGE_ADAPTIVE_REGIME = os.getenv("RANGE_ADAPTIVE_REGIME", "0").strip() == "1"
RANGE_REGIME_LOW_ATR_PCT = float(os.getenv("RANGE_REGIME_LOW_ATR_PCT", "0.35"))
RANGE_REGIME_HIGH_ATR_PCT = float(os.getenv("RANGE_REGIME_HIGH_ATR_PCT", "0.90"))
RANGE_IMPULSE_BODY_ATR_MAX_LOW = float(os.getenv("RANGE_IMPULSE_BODY_ATR_MAX_LOW", "0.60"))
RANGE_IMPULSE_BODY_ATR_MAX_HIGH = float(os.getenv("RANGE_IMPULSE_BODY_ATR_MAX_HIGH", "1.10"))
RANGE_MIN_RR_LOW = float(os.getenv("RANGE_MIN_RR_LOW", "2.20"))
RANGE_MIN_RR_HIGH = float(os.getenv("RANGE_MIN_RR_HIGH", "1.50"))
RANGE_ADAPTIVE_TP = os.getenv("RANGE_ADAPTIVE_TP", "0").strip() == "1"
RANGE_TP_FRAC_LOW = float(os.getenv("RANGE_TP_FRAC_LOW", "0.60"))
RANGE_TP_FRAC_HIGH = float(os.getenv("RANGE_TP_FRAC_HIGH", "0.40"))
RANGE_TP_MODE = os.getenv("RANGE_TP_MODE", "mid").strip()
RANGE_TP_FRAC = float(os.getenv("RANGE_TP_FRAC", "0.45"))
RANGE_SL_BUFFER_FRAC = float(os.getenv("RANGE_SL_BUFFER_FRAC", "0.03"))
RANGE_SL_ATR_MULT = float(os.getenv("RANGE_SL_ATR_MULT", "0.8"))
RANGE_SL_WIDTH_FRAC = float(os.getenv("RANGE_SL_WIDTH_FRAC", "0.10"))
RANGE_MIN_RR = float(os.getenv("RANGE_MIN_RR", "3.00"))

RANGE_ALLOW_LONG = os.getenv("RANGE_ALLOW_LONG", "1").strip() == "1"
RANGE_ALLOW_SHORT = os.getenv("RANGE_ALLOW_SHORT", "1").strip() == "1"

# =========================== REGEXP ===========================
_bybit_sym_re = re.compile(r'publicTrade\.([A-Z0-9]+USDT)\b')

# =========================== УТИЛИТЫ ===========================
def tg_send(t: str):
    if not (TG_TOKEN and TG_CHAT):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": t},
            timeout=10
        )
    except Exception:
        pass

def tg_send_kb(t: str):
    if not (TG_TOKEN and TG_CHAT):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": t, "reply_markup": TG_KB},
            timeout=10
        )
    except Exception:
        pass

def tg_send_doc(path: str, caption: str | None = None):
    if not (TG_TOKEN and TG_CHAT) or not path or not os.path.exists(path):
        return
    try:
        with open(path, "rb") as f:
            requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendDocument",
                data={"chat_id": TG_CHAT, "caption": caption or ""},
                files={"document": f},
                timeout=20,
            )
    except Exception:
        pass

def tg_send_photo(path: str, caption: str | None = None):
    if not (TG_TOKEN and TG_CHAT) or not path or not os.path.exists(path):
        return
    try:
        with open(path, "rb") as f:
            requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                data={"chat_id": TG_CHAT, "caption": caption or ""},
                files={"photo": f},
                timeout=20,
            )
    except Exception:
        pass

# =========================== TRADE DB (SQLite) ===========================
TRADE_DB_PATH = os.getenv("TRADE_DB_PATH", "trades.db")

def _db_init():
    try:
        with sqlite3.connect(TRADE_DB_PATH) as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER,
                    event TEXT,
                    exchange TEXT,
                    symbol TEXT,
                    side TEXT,
                    strategy TEXT,
                    qty REAL,
                    entry_price REAL,
                    exit_price REAL,
                    tp_price REAL,
                    sl_price REAL,
                    pnl REAL,
                    fees REAL,
                    reason TEXT
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS ml_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_entry INTEGER,
                    ts_close INTEGER,
                    strategy TEXT,
                    symbol TEXT,
                    side TEXT,
                    entry_price REAL,
                    sl_price REAL,
                    tp_price REAL,
                    stop_pct REAL,
                    notional_usd REAL,
                    leverage REAL,
                    risk_pct REAL,
                    feature_json TEXT,
                    status TEXT,
                    outcome TEXT,
                    pnl REAL,
                    fees REAL,
                    close_reason TEXT
                )
                """
            )
            con.commit()
    except Exception as e:
        log_error(f"db init fail: {e}")

def _db_log_event(event: str, tr, sym: str, *, pnl: float | None = None, fees: float | None = None, exit_px: float | None = None):
    try:
        with sqlite3.connect(TRADE_DB_PATH) as con:
            con.execute(
                """
                INSERT INTO trade_events
                (ts, event, exchange, symbol, side, strategy, qty, entry_price, exit_price, tp_price, sl_price, pnl, fees, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(time.time()),
                    str(event),
                    "Bybit",
                    str(sym),
                    str(getattr(tr, "side", "")),
                    str(getattr(tr, "strategy", "")),
                    float(getattr(tr, "qty", 0) or 0),
                    float(getattr(tr, "entry_price", getattr(tr, "avg", 0) or 0) or 0),
                    float(exit_px) if exit_px is not None else None,
                    float(getattr(tr, "tp_price", 0) or 0) if getattr(tr, "tp_price", None) is not None else None,
                    float(getattr(tr, "sl_price", 0) or 0) if getattr(tr, "sl_price", None) is not None else None,
                    float(pnl) if pnl is not None else None,
                    float(fees) if fees is not None else None,
                    str(getattr(tr, "close_reason", "") or getattr(tr, "reason_close", "") or ""),
                ),
            )
            con.commit()
    except Exception as e:
        log_error(f"db log fail: {e}")


def _db_log_ml_entry(tr, sym: str):
    try:
        f = getattr(tr, "ml_features", None) or {}
        entry_px = float(getattr(tr, "entry_price", getattr(tr, "avg", 0) or 0) or 0)
        sl_px = float(getattr(tr, "sl_price", 0) or 0)
        tp_px = float(getattr(tr, "tp_price", 0) or 0)
        stop_pct = abs((sl_px - entry_px) / max(1e-12, entry_px)) * 100.0 if entry_px > 0 and sl_px > 0 else None
        notional_usd = float(getattr(tr, "entry_notional_usd", 0.0) or 0.0)
        if notional_usd <= 0:
            try:
                notional_usd = float(getattr(tr, "qty", 0.0) or 0.0) * float(entry_px)
            except Exception:
                notional_usd = 0.0

        with sqlite3.connect(TRADE_DB_PATH) as con:
            cur = con.execute(
                """
                INSERT INTO ml_samples
                (ts_entry, ts_close, strategy, symbol, side, entry_price, sl_price, tp_price, stop_pct, notional_usd, leverage, risk_pct, feature_json, status, outcome, pnl, fees, close_reason)
                VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', NULL, NULL, NULL, NULL)
                """,
                (
                    int(time.time()),
                    str(getattr(tr, "strategy", "") or ""),
                    str(sym),
                    str(getattr(tr, "side", "") or ""),
                    entry_px if entry_px > 0 else None,
                    sl_px if sl_px > 0 else None,
                    tp_px if tp_px > 0 else None,
                    float(stop_pct) if stop_pct is not None else None,
                    float(notional_usd) if notional_usd > 0 else None,
                    float(BYBIT_LEVERAGE),
                    float(RISK_PER_TRADE_PCT),
                    json.dumps(f, ensure_ascii=True),
                ),
            )
            tr.ml_sample_id = int(cur.lastrowid or 0)
            con.commit()
    except Exception as e:
        log_error(f"db ml entry fail: {e}")


def _db_log_ml_close(tr, sym: str, *, pnl: float | None = None, fees: float | None = None):
    try:
        sid = int(getattr(tr, "ml_sample_id", 0) or 0)
        if sid <= 0:
            try:
                with sqlite3.connect(TRADE_DB_PATH) as con:
                    cur = con.execute(
                        """
                        SELECT id
                          FROM ml_samples
                         WHERE ts_close IS NULL
                           AND symbol=?
                           AND side=?
                           AND strategy=?
                         ORDER BY ts_entry DESC
                         LIMIT 1
                        """,
                        (
                            str(sym),
                            str(getattr(tr, "side", "") or ""),
                            str(getattr(tr, "strategy", "") or ""),
                        ),
                    )
                    row = cur.fetchone()
                    sid = int(row[0] or 0) if row else 0
                    if sid > 0:
                        tr.ml_sample_id = sid
            except Exception:
                sid = 0
        if sid <= 0:
            return
        ts_close = int(time.time())
        pnl_v = float(pnl or 0.0)
        outcome = "win" if pnl_v > 0 else ("loss" if pnl_v < 0 else "flat")
        entry_ts = int(getattr(tr, "entry_ts", 0) or 0)
        fill_ts = int(getattr(tr, "entry_fill_ts", 0) or 0)
        send_ts = int(getattr(tr, "order_send_ts", 0) or 0)

        close_feats = {
            "close_reason": str(getattr(tr, "close_reason", "") or ""),
            "close_session": str(_session_name_utc(ts_close)),
            "close_hour_utc": int((ts_close // 3600) % 24),
        }
        if entry_ts > 0 and ts_close >= entry_ts:
            close_feats["entry_to_close_sec"] = int(ts_close - entry_ts)
        if fill_ts > 0 and ts_close >= fill_ts:
            close_feats["fill_to_close_sec"] = int(ts_close - fill_ts)
        if send_ts > 0 and fill_ts > 0 and fill_ts >= send_ts:
            close_feats["send_to_fill_sec"] = int(fill_ts - send_ts)

        with sqlite3.connect(TRADE_DB_PATH) as con:
            cur = con.execute("SELECT feature_json FROM ml_samples WHERE id=?", (sid,))
            row = cur.fetchone()
            merged = {}
            if row and row[0]:
                try:
                    parsed = json.loads(row[0]) if isinstance(row[0], str) else {}
                    if isinstance(parsed, dict):
                        merged.update(parsed)
                except Exception:
                    pass
            merged.update(close_feats)
            con.execute(
                """
                UPDATE ml_samples
                   SET ts_close=?, status='CLOSED', outcome=?, pnl=?, fees=?, close_reason=?, feature_json=?
                 WHERE id=?
                """,
                (
                    ts_close,
                    outcome,
                    pnl_v,
                    float(fees or 0.0),
                    str(getattr(tr, "close_reason", "") or ""),
                    json.dumps(merged, ensure_ascii=True),
                    sid,
                ),
            )
            con.commit()
    except Exception as e:
        log_error(f"db ml close fail: {e}")

# =========================== TELEGRAM COMMANDS ===========================
TG_COMMANDS_ENABLE = os.getenv("TG_COMMANDS_ENABLE", "1").strip() == "1"
# Restrict commands to this Telegram user_id (0 = no restriction)
TG_ADMIN_USER_ID = os.getenv("TG_ADMIN_USER_ID", "").strip()
REPORTS_ENABLE = os.getenv("REPORTS_ENABLE", "1").strip() == "1"
REPORTS_SEND_ON_START = os.getenv("REPORTS_SEND_ON_START", "0").strip() == "1"
REPORTS_OUT_DIR = os.getenv("REPORTS_OUT_DIR", "/tmp").strip() or "/tmp"
REPORTS_STATE_PATH = os.getenv("REPORTS_STATE_PATH", "/tmp/bybot_reports_state.json").strip() or "/tmp/bybot_reports_state.json"
REPORT_DAILY_ENABLE = os.getenv("REPORT_DAILY_ENABLE", "1").strip() == "1"
REPORT_WEEKLY_ENABLE = os.getenv("REPORT_WEEKLY_ENABLE", "1").strip() == "1"
REPORT_MONTHLY_ENABLE = os.getenv("REPORT_MONTHLY_ENABLE", "1").strip() == "1"
REPORT_YEARLY_ENABLE = os.getenv("REPORT_YEARLY_ENABLE", "1").strip() == "1"
STRATEGY_STATS_TG_EVERY_SEC = int(os.getenv("STRATEGY_STATS_TG_EVERY_SEC", "3600"))
STRATEGY_STATS_LOOKBACK_H = int(os.getenv("STRATEGY_STATS_LOOKBACK_H", "24"))
WS_HEALTH_ALERT_ENABLE = _env_bool("WS_HEALTH_ALERT_ENABLE", True)
WS_HEALTH_CHECK_SEC = max(60, int(os.getenv("WS_HEALTH_CHECK_SEC", "300")))
WS_HEALTH_ALERT_COOLDOWN_SEC = max(60, int(os.getenv("WS_HEALTH_ALERT_COOLDOWN_SEC", "1800")))
WS_HEALTH_MIN_CONNECT_DELTA = max(1, int(os.getenv("WS_HEALTH_MIN_CONNECT_DELTA", "3")))
WS_HEALTH_NO_CONNECT_STREAK_ALERT = max(1, int(os.getenv("WS_HEALTH_NO_CONNECT_STREAK_ALERT", "2")))
WS_HEALTH_NO_CONNECT_ALERT_COOLDOWN_SEC = max(
    60,
    int(os.getenv("WS_HEALTH_NO_CONNECT_ALERT_COOLDOWN_SEC", str(WS_HEALTH_ALERT_COOLDOWN_SEC))),
)
WS_HEALTH_NO_CONNECT_DISC_TOL = max(0, int(os.getenv("WS_HEALTH_NO_CONNECT_DISC_TOL", "1")))
WS_HEALTH_NO_CONNECT_HS_TOL = max(0, int(os.getenv("WS_HEALTH_NO_CONNECT_HS_TOL", "0")))
WS_HEALTH_NO_CONNECT_MIN_MSG_DELTA = max(0, int(os.getenv("WS_HEALTH_NO_CONNECT_MIN_MSG_DELTA", "1000")))
WS_HEALTH_WARN_DISC_CONN_PCT = max(0.0, float(os.getenv("WS_HEALTH_WARN_DISC_CONN_PCT", "120")))
WS_HEALTH_CRIT_DISC_CONN_PCT = max(0.0, float(os.getenv("WS_HEALTH_CRIT_DISC_CONN_PCT", "250")))
WS_HEALTH_WARN_HANDSHAKE_CONN_PCT = max(0.0, float(os.getenv("WS_HEALTH_WARN_HANDSHAKE_CONN_PCT", "30")))
WS_HEALTH_CRIT_HANDSHAKE_CONN_PCT = max(0.0, float(os.getenv("WS_HEALTH_CRIT_HANDSHAKE_CONN_PCT", "80")))
TRADE_CHARTS_ENABLE = os.getenv("TRADE_CHARTS_ENABLE", "1").strip() == "1"
TRADE_CHARTS_SEND_ON_ENTRY = os.getenv("TRADE_CHARTS_SEND_ON_ENTRY", "1").strip() == "1"
TRADE_CHARTS_SEND_ON_CLOSE = os.getenv("TRADE_CHARTS_SEND_ON_CLOSE", "1").strip() == "1"
TRADE_CHARTS_PAD_BARS = int(os.getenv("TRADE_CHARTS_PAD_BARS", "80"))
TRADE_CHARTS_OUT_DIR = os.getenv("TRADE_CHARTS_OUT_DIR", "/tmp/bybot_trade_charts").strip() or "/tmp/bybot_trade_charts"

# Symbol filters (allow/deny lists)
SYMBOL_FILTERS_PATH = os.getenv("SYMBOL_FILTERS_PATH", "/tmp/bybot_symbol_filters.json").strip()
SYMBOL_FILTERS_PROFILES_PATH = os.getenv("SYMBOL_FILTERS_PROFILES_PATH", "configs/symbol_filters_profiles.json").strip()
SYMBOL_FILTERS_CACHE_DIR = os.getenv("SYMBOL_FILTERS_CACHE_DIR", "").strip()
FILTERS_AUTO_REFRESH_SEC = int(os.getenv("FILTERS_AUTO_REFRESH_SEC", "1800"))
FILTERS_AUTO_BUILD = os.getenv("FILTERS_AUTO_BUILD", "1").strip() == "1"
FILTERS_AUTO_BUILD_SEC = int(os.getenv("FILTERS_AUTO_BUILD_SEC", "1800"))
SYMBOL_ALLOWLIST_ENV = os.getenv("SYMBOL_ALLOWLIST", "").strip()
SYMBOL_DENYLIST_ENV = os.getenv("SYMBOL_DENYLIST", "").strip()

# Recommendation (banlist) loop
RECO_ENABLE = os.getenv("RECO_ENABLE", "1").strip() == "1"
RECO_SEND_ON_START = os.getenv("RECO_SEND_ON_START", "0").strip() == "1"
RECO_PERIOD_SEC = int(os.getenv("RECO_PERIOD_SEC", str(7 * 86400)))
RECO_LOOKBACK_DAYS = int(os.getenv("RECO_LOOKBACK_DAYS", "60"))
RECO_WORST_N = int(os.getenv("RECO_WORST_N", "3"))
RECO_MIN_TRADES = int(os.getenv("RECO_MIN_TRADES", "8"))
RECO_STRATEGIES = os.getenv("RECO_STRATEGIES", "").strip()

KILLER_GUARD_ENABLE = os.getenv("KILLER_GUARD_ENABLE", "1").strip() == "1"
KILLER_GUARD_LOOKBACK_DAYS = int(os.getenv("KILLER_GUARD_LOOKBACK_DAYS", "7"))
KILLER_GUARD_MIN_TRADES = int(os.getenv("KILLER_GUARD_MIN_TRADES", "3"))
KILLER_GUARD_MAX_NET_PNL = float(os.getenv("KILLER_GUARD_MAX_NET_PNL", "-0.8"))
KILLER_GUARD_STRATEGIES = os.getenv("KILLER_GUARD_STRATEGIES", "inplay_breakout").strip()
KILLER_GUARD_REFRESH_SEC = int(os.getenv("KILLER_GUARD_REFRESH_SEC", "600"))
KILLER_GUARD_LOG_EVERY_SEC = int(os.getenv("KILLER_GUARD_LOG_EVERY_SEC", "300"))

LAST_RECO_SYMBOLS: list[str] = []
LAST_FILTER_BUILD_TS = 0
LAST_UNIVERSE_REFRESH_TS = 0
KILLER_GUARD_CACHE_TS = 0
KILLER_GUARD_BANNED: set[str] = set()
DEEPSEEK_OVERLAY = DeepSeekOverlay()

def _parse_symbol_csv(s: str) -> list[str]:
    parts = [p.strip().upper() for p in s.replace(";", ",").split(",") if p.strip()]
    return [p for p in parts if p]

def _load_symbol_filters() -> dict:
    base = {"allowlist": [], "denylist": [], "per_strategy": {}}
    if SYMBOL_FILTERS_PATH and os.path.exists(SYMBOL_FILTERS_PATH):
        try:
            with open(SYMBOL_FILTERS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            base["allowlist"] = [str(x).upper() for x in (data.get("allowlist") or [])]
            base["denylist"] = [str(x).upper() for x in (data.get("denylist") or [])]
            per = data.get("per_strategy") or data.get("strategies") or {}
            norm: dict[str, dict] = {}
            for k, v in (per or {}).items():
                if not isinstance(v, dict):
                    continue
                allow = [str(x).upper() for x in (v.get("allowlist") or [])]
                deny = [str(x).upper() for x in (v.get("denylist") or [])]
                norm[str(k).lower()] = {"allowlist": allow, "denylist": deny}
            base["per_strategy"] = norm
        except Exception:
            pass
    return base

def _save_symbol_filters(data: dict) -> None:
    try:
        if not SYMBOL_FILTERS_PATH:
            return
        with open(SYMBOL_FILTERS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass

def _get_symbol_filters(strategy: str | None = None) -> tuple[set[str], set[str]]:
    allow = set(_parse_symbol_csv(SYMBOL_ALLOWLIST_ENV)) if SYMBOL_ALLOWLIST_ENV else set()
    deny = set(_parse_symbol_csv(SYMBOL_DENYLIST_ENV)) if SYMBOL_DENYLIST_ENV else set()
    data = _load_symbol_filters()
    allow.update(data.get("allowlist") or [])
    deny.update(data.get("denylist") or [])
    if strategy:
        per = (data.get("per_strategy") or {}).get(str(strategy).lower())
        if per:
            per_allow = set(per.get("allowlist") or [])
            per_deny = set(per.get("denylist") or [])
            if per_allow:
                allow = (allow & per_allow) if allow else per_allow
            deny.update(per_deny)
    return allow, deny

def _apply_symbol_filters(symbols: list[str], strategy: str | None = None) -> list[str]:
    allow, deny = _get_symbol_filters(strategy=strategy)
    out = []
    for s in symbols:
        if allow and s not in allow:
            continue
        if s in deny:
            continue
        out.append(s)
    return out

def _symbol_filters_summary() -> str:
    data = _load_symbol_filters()
    allow = [str(x).upper() for x in (data.get("allowlist") or [])]
    deny = [str(x).upper() for x in (data.get("denylist") or [])]
    per = data.get("per_strategy") or {}
    parts = [
        f"Filters file: {SYMBOL_FILTERS_PATH}",
        f"Base allow={len(allow)} | deny={len(deny)}",
    ]
    for k in ("breakout", "inplay", "range", "bounce", "retest"):
        v = per.get(k) or {}
        a = v.get("allowlist") or []
        d = v.get("denylist") or []
        if a or d:
            parts.append(f"{k}: allow={len(a)} deny={len(d)}")
    return "\n".join(parts)

def _build_symbol_filters() -> tuple[bool, str]:
    global LAST_FILTER_BUILD_TS
    script = os.path.join(os.path.dirname(__file__), "scripts", "build_symbol_filters.py")
    cmd = ["python3", script, "--profiles", SYMBOL_FILTERS_PROFILES_PATH, "--out", SYMBOL_FILTERS_PATH]
    if SYMBOL_FILTERS_CACHE_DIR:
        cmd += ["--cache_dir", SYMBOL_FILTERS_CACHE_DIR]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        out = (res.stdout or "").strip()
        err = (res.stderr or "").strip()
        if res.returncode != 0:
            msg = err or out or f"exit={res.returncode}"
            return False, f"build failed: {msg}"
        LAST_FILTER_BUILD_TS = int(time.time())
        return True, out or "filters built"
    except Exception as e:
        return False, f"build failed: {e}"

def _load_filter_profiles() -> dict:
    try:
        if not SYMBOL_FILTERS_PROFILES_PATH:
            return {}
        with open(SYMBOL_FILTERS_PROFILES_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}

def _compute_symbol_health(lookback_days: int = 30, min_trades: int = 2, top_n: int = 5) -> tuple[list[tuple], list[tuple]]:
    if not os.path.exists(TRADE_DB_PATH):
        return [], []
    since_ts = int(time.time()) - int(lookback_days) * 86400
    rows: list[tuple] = []
    try:
        with sqlite3.connect(TRADE_DB_PATH) as con:
            cur = con.execute(
                """
                SELECT symbol,
                       COUNT(*) AS trades,
                       SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
                       SUM(pnl) AS net
                FROM trade_events
                WHERE event='CLOSE' AND pnl IS NOT NULL AND ts>=?
                GROUP BY symbol
                """,
                (since_ts,),
            )
            rows = cur.fetchall()
    except Exception as e:
        log_error(f"health query failed: {e}")
        return [], []

    norm = []
    for sym, trades, wins, net in rows:
        t = int(trades or 0)
        if t < int(min_trades):
            continue
        w = int(wins or 0)
        n = float(net or 0.0)
        wr = (100.0 * w / t) if t > 0 else 0.0
        norm.append((str(sym).upper(), t, w, wr, n))

    killers = sorted(norm, key=lambda x: x[4])[: max(1, int(top_n))]
    winners = sorted(norm, key=lambda x: x[4], reverse=True)[: max(1, int(top_n))]
    return killers, winners

def _health_summary_text(lookback_days: int = 30, min_trades: int = 2, top_n: int = 5) -> str:
    killers, winners = _compute_symbol_health(lookback_days=lookback_days, min_trades=min_trades, top_n=top_n)
    data = _load_symbol_filters()
    profiles = _load_filter_profiles()
    base_cfg = profiles.get("base") or {}
    br_cfg = (profiles.get("per_strategy") or {}).get("breakout") or {}

    lines = [
        f"Health lookback={lookback_days}d, min_trades={min_trades}",
        f"Filters: base_allow={len(data.get('allowlist') or [])}, deny={len(data.get('denylist') or [])}",
        f"Base criteria: turnover>={base_cfg.get('min_turnover', '-')}, atr%>={base_cfg.get('min_atr_pct', '-')}, age>={base_cfg.get('min_listing_days', '-')}, top_n={base_cfg.get('top_n', '-')}",
        f"Breakout criteria: turnover>={br_cfg.get('min_turnover', '-')}, atr%>={br_cfg.get('min_atr_pct', '-')}, top_n={br_cfg.get('top_n', '-')}, spread<={BREAKOUT_MAX_SPREAD_PCT:.2f}%",
        "Killers:",
    ]
    if killers:
        for sym, t, _w, wr, net in killers:
            lines.append(f"{sym}: trades={t}, wr={wr:.1f}%, net={net:.4f}")
    else:
        lines.append("-")
    lines.append("Winners:")
    if winners:
        for sym, t, _w, wr, net in winners:
            lines.append(f"{sym}: trades={t}, wr={wr:.1f}%, net={net:.4f}")
    else:
        lines.append("-")
    return "\n".join(lines)

def _compute_reco_symbols() -> list[str]:
    if not os.path.exists(TRADE_DB_PATH):
        return []
    since_ts = int(time.time()) - int(RECO_LOOKBACK_DAYS) * 86400
    strat_filter = [s.strip() for s in RECO_STRATEGIES.split(",") if s.strip()]
    rows = []
    try:
        with sqlite3.connect(TRADE_DB_PATH) as con:
            if strat_filter:
                placeholders = ",".join(["?"] * len(strat_filter))
                query = (
                    "SELECT symbol, COUNT(*), SUM(pnl) "
                    "FROM trade_events "
                    "WHERE event='CLOSE' AND pnl IS NOT NULL AND ts>=? "
                    f"AND strategy IN ({placeholders}) "
                    "GROUP BY symbol"
                )
                cur = con.execute(query, [since_ts, *strat_filter])
            else:
                query = (
                    "SELECT symbol, COUNT(*), SUM(pnl) "
                    "FROM trade_events "
                    "WHERE event='CLOSE' AND pnl IS NOT NULL AND ts>=? "
                    "GROUP BY symbol"
                )
                cur = con.execute(query, (since_ts,))
            for sym, cnt, pnl in cur.fetchall():
                rows.append((str(sym).upper(), int(cnt), float(pnl or 0.0)))
    except Exception as e:
        log_error(f"reco query failed: {e}")
        return []

    rows = [r for r in rows if r[1] >= int(RECO_MIN_TRADES)]
    rows.sort(key=lambda x: x[2])  # worst first
    return [sym for sym, _, _ in rows[: max(0, int(RECO_WORST_N))]]

def _refresh_killer_guard_cache(force: bool = False) -> set[str]:
    global KILLER_GUARD_CACHE_TS, KILLER_GUARD_BANNED
    if not KILLER_GUARD_ENABLE:
        return set()
    now = int(time.time())
    if (not force) and (now - int(KILLER_GUARD_CACHE_TS or 0) < int(KILLER_GUARD_REFRESH_SEC)):
        return set(KILLER_GUARD_BANNED)
    if not os.path.exists(TRADE_DB_PATH):
        KILLER_GUARD_BANNED = set()
        KILLER_GUARD_CACHE_TS = now
        return set()
    strat_filter = [s.strip() for s in KILLER_GUARD_STRATEGIES.split(",") if s.strip()]
    since_ts = now - int(KILLER_GUARD_LOOKBACK_DAYS) * 86400
    banned: set[str] = set()
    try:
        with sqlite3.connect(TRADE_DB_PATH) as con:
            if strat_filter:
                placeholders = ",".join(["?"] * len(strat_filter))
                query = (
                    "SELECT symbol, COUNT(*), SUM(pnl) "
                    "FROM trade_events "
                    "WHERE event='CLOSE' AND pnl IS NOT NULL AND ts>=? "
                    f"AND strategy IN ({placeholders}) "
                    "GROUP BY symbol"
                )
                params = [since_ts, *strat_filter]
            else:
                query = (
                    "SELECT symbol, COUNT(*), SUM(pnl) "
                    "FROM trade_events "
                    "WHERE event='CLOSE' AND pnl IS NOT NULL AND ts>=? "
                    "GROUP BY symbol"
                )
                params = [since_ts]
            for sym, cnt, net in con.execute(query, params).fetchall():
                c = int(cnt or 0)
                n = float(net or 0.0)
                if c >= int(KILLER_GUARD_MIN_TRADES) and n <= float(KILLER_GUARD_MAX_NET_PNL):
                    banned.add(str(sym).upper())
    except Exception as e:
        log_error(f"killer guard query failed: {e}")
    KILLER_GUARD_BANNED = set(banned)
    KILLER_GUARD_CACHE_TS = now
    return set(KILLER_GUARD_BANNED)

def _tg_reply(msg: str):
    tg_send(msg)


def _deepseek_local_regime_hint() -> dict[str, Any]:
    breakout_try = int(_diag_get_int("breakout_try"))
    breakout_entry = int(_diag_get_int("breakout_entry"))
    breakout_no_signal = int(_diag_get_int("breakout_no_signal"))
    weak = int(_diag_get_int("breakout_ns_impulse_weak"))
    body = int(_diag_get_int("breakout_ns_impulse_body"))
    dist = int(_diag_get_int("breakout_ns_dist"))
    ws_connect = int(_diag_get_int("ws_connect"))
    ws_disconnect = int(_diag_get_int("ws_disconnect"))
    ws_handshake_timeout = int(_diag_get_int("ws_handshake_timeout"))

    if ws_handshake_timeout > 0:
        return {
            "label": "infra_unstable",
            "confidence": 0.95,
            "reason": "websocket handshake timeouts observed",
        }

    if breakout_entry > 0 and breakout_try > 0:
        return {
            "label": "tradable_impulse",
            "confidence": 0.65,
            "reason": "live breakout sleeve is already seeing entries",
        }

    if breakout_no_signal <= 0:
        return {
            "label": "insufficient_data",
            "confidence": 0.2,
            "reason": "not enough recent no-signal evidence",
        }

    weak_ratio = weak / float(max(1, breakout_no_signal))
    body_ratio = body / float(max(1, breakout_no_signal))
    dist_ratio = dist / float(max(1, breakout_no_signal))

    if weak_ratio >= 0.60:
        return {
            "label": "weak_chop",
            "confidence": round(min(0.95, 0.55 + weak_ratio * 0.4), 2),
            "reason": "impulse_weak dominates recent breakout rejections",
        }
    if body_ratio >= 0.28:
        return {
            "label": "messy_body",
            "confidence": round(min(0.9, 0.45 + body_ratio * 0.7), 2),
            "reason": "many setups fail on weak/ugly candle bodies",
        }
    if dist_ratio >= 0.18:
        return {
            "label": "late_extended",
            "confidence": round(min(0.85, 0.4 + dist_ratio * 0.9), 2),
            "reason": "setups often arrive too stretched from acceptable distance",
        }
    if ws_connect > 0 and ws_disconnect > ws_connect:
        return {
            "label": "infra_noisy",
            "confidence": 0.7,
            "reason": "disconnects exceed connects in current live window",
        }
    return {
        "label": "mixed",
        "confidence": 0.45,
        "reason": "no single live rejection pattern dominates right now",
    }


def _deepseek_snapshot() -> dict[str, Any]:
    return {
        "ts_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "trade_on": bool(TRADE_ON),
        "portfolio_disabled": bool(PORTFOLIO_STATE.get("disabled")),
        "effective_equity": round(float(_get_effective_equity() or 0), 4),
        "open_trades": int(len(TRADES)),
        "risk_pct": float(RISK_PER_TRADE_PCT or 0),
        "max_positions": int(MAX_POSITIONS),
        "bot_capital_usd": float(BOT_CAPITAL_USD or 0),
        "bot_capital_effective_usd": round(float(_get_effective_equity() or 0), 4) if not BOT_CAPITAL_USD else float(BOT_CAPITAL_USD or 0),
        "bot_capital_mode": "fixed" if BOT_CAPITAL_USD else "auto_equity",
        "strategies": {
            "breakout": bool(ENABLE_BREAKOUT_TRADING),
            "midterm": bool(ENABLE_MIDTERM_TRADING),
            "sloped": bool(ENABLE_SLOPED_TRADING),
            "flat": bool(ENABLE_FLAT_TRADING),
            "breakdown": bool(ENABLE_BREAKDOWN_TRADING),
            "ts132": bool(ENABLE_TS132_TRADING),
            "pump_fade": bool(ENABLE_PUMP_FADE_TRADING),
            "inplay": bool(ENABLE_INPLAY_TRADING),
            "retest": bool(ENABLE_RETEST_TRADING),
            "range": bool(ENABLE_RANGE_TRADING),
            "micro_scalper": bool(ENABLE_MICRO_SCALPER_TRADING),
            "support_reclaim": bool(ENABLE_SUPPORT_RECLAIM_TRADING),
        },
        "diag": {
            "ws_connect": int(_diag_get_int("ws_connect")),
            "ws_disconnect": int(_diag_get_int("ws_disconnect")),
            "ws_handshake_timeout": int(_diag_get_int("ws_handshake_timeout")),
            "breakout_try": int(_diag_get_int("breakout_try")),
            "breakout_entry": int(_diag_get_int("breakout_entry")),
            "breakout_no_signal": int(_diag_get_int("breakout_no_signal")),
            "breakout_ns_impulse_weak": int(_diag_get_int("breakout_ns_impulse_weak")),
            "breakout_ns_impulse_body": int(_diag_get_int("breakout_ns_impulse_body")),
            "breakout_ns_dist": int(_diag_get_int("breakout_ns_dist")),
            "midterm_try": int(_diag_get_int("midterm_try")),
            "midterm_entry": int(_diag_get_int("midterm_entry")),
            "sloped_try": int(_diag_get_int("sloped_try")),
            "sloped_entry": int(_diag_get_int("sloped_entry")),
            "flat_try": int(_diag_get_int("flat_try")),
            "flat_entry": int(_diag_get_int("flat_entry")),
            "breakdown_try": int(_diag_get_int("breakdown_try")),
            "breakdown_entry": int(_diag_get_int("breakdown_entry")),
            "ts132_try": int(_diag_get_int("ts132_try")),
            "ts132_entry": int(_diag_get_int("ts132_entry")),
        },
        "local_regime_hint": _deepseek_local_regime_hint(),
        "runtime_stats_12h": _strategy_runtime_stats_text(12),
        "health_30d": _health_summary_text(30),
        "filters": _symbol_filters_summary(),
        "research": build_research_context(),
        # Key live params — lets /ai answer questions about current settings
        "live_params": {
            "ASC1_SYMBOL_ALLOWLIST": os.getenv("ASC1_SYMBOL_ALLOWLIST", ""),
            "ASC1_ALLOW_SHORTS": os.getenv("ASC1_ALLOW_SHORTS", ""),
            "ASC1_SHORT_MIN_RSI": os.getenv("ASC1_SHORT_MIN_RSI", ""),
            "ASC1_SHORT_MIN_REJECT_DEPTH_ATR": os.getenv("ASC1_SHORT_MIN_REJECT_DEPTH_ATR", ""),
            "ARF1_SYMBOL_ALLOWLIST": os.getenv("ARF1_SYMBOL_ALLOWLIST", ""),
            "ARF1_REJECT_BELOW_RES_ATR": os.getenv("ARF1_REJECT_BELOW_RES_ATR", ""),
            "ARF1_MIN_RSI": os.getenv("ARF1_MIN_RSI", ""),
            "BREAKOUT_ALLOW_SHORTS": os.getenv("BREAKOUT_ALLOW_SHORTS", ""),
            "BREAKOUT_TOP_N": os.getenv("BREAKOUT_TOP_N", ""),
            "BT_BREAKOUT_QUALITY_MIN_SCORE": os.getenv("BT_BREAKOUT_QUALITY_MIN_SCORE", ""),
            "RISK_PER_TRADE_PCT": os.getenv("RISK_PER_TRADE_PCT", ""),
            "SLOPED_RISK_MULT": os.getenv("SLOPED_RISK_MULT", ""),
            "FLAT_RISK_MULT": os.getenv("FLAT_RISK_MULT", ""),
            "DRY_RUN": os.getenv("DRY_RUN", ""),
            "ENABLE_BREAKDOWN_TRADING": os.getenv("ENABLE_BREAKDOWN_TRADING", "0"),
        },
    }


_BOT_ROOT = Path(__file__).resolve().parent


def _parse_csv_items_keep_case(raw: str) -> list[str]:
    return [p.strip() for p in str(raw or "").replace(";", ",").split(",") if p.strip()]


def _fmt_list_compact(items: list[str], max_items: int = 6) -> str:
    if not items:
        return "-"
    items = [str(x) for x in items if str(x).strip()]
    if not items:
        return "-"
    if len(items) <= max_items:
        return ",".join(items)
    return ",".join(items[:max_items]) + f",+{len(items) - max_items}"


def _display_capital_text() -> str:
    try:
        if BOT_CAPITAL_USD is not None and float(BOT_CAPITAL_USD) > 0:
            return f"{float(BOT_CAPITAL_USD):.2f}"
    except Exception:
        pass
    return f"auto(eq≈{float(_get_effective_equity() or 0.0):.2f})"


def _safe_read_csv_first(path: Path) -> Optional[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return next(csv.DictReader(f), None)
    except Exception:
        return None


def _find_best_equities_summary_patterns(glob_patterns: list[str]) -> tuple[Optional[Path], Optional[dict[str, str]]]:
    best_path: Optional[Path] = None
    best_row: Optional[dict[str, str]] = None
    best_score: Optional[float] = None
    for glob_pattern in glob_patterns:
        for path in _BOT_ROOT.glob(glob_pattern):
            row = _safe_read_csv_first(path)
            if not row:
                continue
            try:
                ret = float(row.get("compounded_return_pct") or 0.0)
                dd = abs(float(row.get("max_monthly_dd_pct") or 0.0))
                pos = float(row.get("positive_months") or 0.0)
                score = ret - dd * 0.25 + pos * 0.2
            except Exception:
                continue
            if best_score is None or score > best_score:
                best_score = score
                best_path = path
                best_row = row
    return best_path, best_row


def _status_full_text() -> str:
    eq = _get_effective_equity()
    lines: list[str] = []

    lines.append("📋 status_full")
    lines.append(
        f"crypto_live: {'ON' if TRADE_ON else 'OFF'} | disabled={PORTFOLIO_STATE.get('disabled')} | "
        f"equity≈{eq:.2f} USDT | open={len(TRADES)}"
    )
    lines.append(
        f"risk={RISK_PER_TRADE_PCT:.2f}% | max_positions={MAX_POSITIONS} | capital={_display_capital_text()}"
    )
    lines.append(
        "strategies: "
        f"breakout={ENABLE_BREAKOUT_TRADING}, midterm={ENABLE_MIDTERM_TRADING}, "
        f"sloped={ENABLE_SLOPED_TRADING}, flat={ENABLE_FLAT_TRADING}, "
        f"breakdown={ENABLE_BREAKDOWN_TRADING}, ts132={ENABLE_TS132_TRADING}"
    )

    if ENABLE_BREAKOUT_TRADING:
        lines.append(f"breakout-universe: {len(BREAKOUT_SYMBOLS)} (top {BREAKOUT_TOP_N})")
    if ENABLE_MIDTERM_TRADING:
        lines.append(f"midterm-universe: {len(MIDTERM_ACTIVE_SYMBOLS)} ({_fmt_list_compact(sorted(MIDTERM_ACTIVE_SYMBOLS), 8)})")
    if ENABLE_SLOPED_TRADING:
        sloped_symbols = sorted(_parse_symbol_csv(os.getenv('ASC1_SYMBOL_ALLOWLIST', '')))
        lines.append(f"sloped-universe: {len(sloped_symbols)} ({_fmt_list_compact(sloped_symbols, 8) if sloped_symbols else 'dynamic'})")
    if ENABLE_FLAT_TRADING:
        flat_symbols = sorted(_parse_symbol_csv(os.getenv('ARF1_SYMBOL_ALLOWLIST', '')))
        lines.append(f"flat-universe: {len(flat_symbols)} ({_fmt_list_compact(flat_symbols, 8) if flat_symbols else 'dynamic'})")
    if ENABLE_BREAKDOWN_TRADING:
        breakdown_symbols = sorted(_parse_symbol_csv(os.getenv('BREAKDOWN_SYMBOL_ALLOWLIST', '')))
        lines.append(f"breakdown-universe: {len(breakdown_symbols)} ({_fmt_list_compact(breakdown_symbols, 8) if breakdown_symbols else 'dynamic'})")

    if LAST_UNIVERSE_REFRESH_TS:
        age_min = max(0, int((time.time() - int(LAST_UNIVERSE_REFRESH_TS)) // 60))
        lines.append(f"universe_refresh_age_min={age_min}")

    regime = _deepseek_local_regime_hint()
    lines.append(
        f"regime_hint: {regime.get('label','n/a')} "
        f"(conf={float(regime.get('confidence', 0.0)):.2f}) — {regime.get('reason','')}"
    )
    lines.append(
        "live_diag: "
        f"ws={int(_diag_get_int('ws_connect'))}/{int(_diag_get_int('ws_disconnect'))} | "
        f"breakout_try={int(_diag_get_int('breakout_try'))} entry={int(_diag_get_int('breakout_entry'))} | "
        f"midterm_try={int(_diag_get_int('midterm_try'))} entry={int(_diag_get_int('midterm_entry'))} | "
        f"sloped_try={int(_diag_get_int('sloped_try'))} | flat_try={int(_diag_get_int('flat_try'))} | "
        f"breakdown_try={int(_diag_get_int('breakdown_try'))}"
    )

    crypto_best_path = _BOT_ROOT / "backtest_runs" / "portfolio_20260325_172613_new_5strat_final" / "summary.csv"
    crypto_best = _safe_read_csv_first(crypto_best_path)
    if crypto_best:
        lines.append(
            "research_crypto_best: "
            f"+{float(crypto_best.get('net_pnl') or 0.0):.2f}% | "
            f"PF={float(crypto_best.get('profit_factor') or 0.0):.3f} | "
            f"trades={int(float(crypto_best.get('trades') or 0.0))} | "
            f"DD={float(crypto_best.get('max_drawdown') or 0.0):.2f}"
        )

    alpaca_path, alpaca_row = _find_best_equities_summary_patterns([
        "backtest_runs/*equities_monthly_v21_red_month_push*/summary.csv",
        "backtest_runs/*equities_monthly_v23_breadth_exit_cluster*/summary.csv",
    ])
    if alpaca_row:
        months = int(float(alpaca_row.get("months") or 0))
        pos_months = int(float(alpaca_row.get("positive_months") or 0))
        neg_months = max(0, months - pos_months)
        lines.append(
            "alpaca_paper: active separate stack | "
            f"best≈+{float(alpaca_row.get('compounded_return_pct') or 0.0):.2f}% | "
            f"trades={int(float(alpaca_row.get('trades') or 0.0))} | "
            f"WR={float(alpaca_row.get('winrate_pct') or 0.0):.1f}% | "
            f"red_months={neg_months} | "
            f"max_month_dd={float(alpaca_row.get('max_monthly_dd_pct') or 0.0):.2f}%"
        )
    else:
        lines.append("alpaca_paper: separate stack | no local summary found")

    forex_env = _BOT_ROOT / "docs" / "forex_live_filter_latest.env"
    if forex_env.exists():
        env_map: dict[str, str] = {}
        try:
            for raw in forex_env.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env_map[k.strip()] = v.strip()
        except Exception:
            env_map = {}
        active_pairs = _parse_csv_items_keep_case(env_map.get("FOREX_ACTIVE_PAIRS", ""))
        canary_pairs = _parse_csv_items_keep_case(env_map.get("FOREX_CANARY_PAIRS", ""))
        active_combos = _parse_csv_items_keep_case(env_map.get("FOREX_ACTIVE_COMBOS", ""))
        lines.append(
            "forex_pilot: "
            f"active_pairs={_fmt_list_compact(active_pairs, 6)} | "
            f"canary_pairs={_fmt_list_compact(canary_pairs, 6)} | "
            f"active_combos={_fmt_list_compact(active_combos, 3)}"
        )
    else:
        lines.append("forex_pilot: no latest filter artifact")

    return "\n".join(lines)

def _parse_float(s: str) -> float | None:
    try:
        return float(s)
    except Exception:
        return None

def _get_last_close_event(symbol: str | None = None) -> dict | None:
    if not os.path.exists(TRADE_DB_PATH):
        return None
    try:
        with sqlite3.connect(TRADE_DB_PATH) as con:
            if symbol:
                cur = con.execute(
                    """
                    SELECT ts, symbol, side, strategy, entry_price, exit_price, tp_price, sl_price, pnl, reason
                    FROM trade_events
                    WHERE event='CLOSE' AND symbol=?
                    ORDER BY ts DESC
                    LIMIT 1
                    """,
                    (str(symbol).upper(),),
                )
            else:
                cur = con.execute(
                    """
                    SELECT ts, symbol, side, strategy, entry_price, exit_price, tp_price, sl_price, pnl, reason
                    FROM trade_events
                    WHERE event='CLOSE'
                    ORDER BY ts DESC
                    LIMIT 1
                    """
                )
            row = cur.fetchone()
            if not row:
                return None
            close_ts, sym, side, strategy, entry_px, exit_px, tp, sl, pnl, reason = row

            entry_ts = None
            try:
                ecur = con.execute(
                    """
                    SELECT ts
                    FROM trade_events
                    WHERE event='ENTRY' AND symbol=? AND side=? AND strategy=? AND ts<=?
                    ORDER BY ts DESC
                    LIMIT 1
                    """,
                    (str(sym).upper(), str(side or ''), str(strategy or ''), int(close_ts or 0)),
                )
                erow = ecur.fetchone()
                if erow:
                    entry_ts = int(erow[0])
            except Exception:
                entry_ts = None

            return {
                "close_ts": int(close_ts or 0),
                "entry_ts": int(entry_ts or 0),
                "symbol": str(sym).upper(),
                "side": str(side or "Buy"),
                "strategy": str(strategy or ""),
                "entry_price": float(entry_px or 0.0),
                "exit_price": float(exit_px or 0.0),
                "tp_price": float(tp) if tp is not None else None,
                "sl_price": float(sl) if sl is not None else None,
                "pnl": float(pnl) if pnl is not None else None,
                "reason": str(reason or ""),
            }
    except Exception as e:
        log_error(f"plotlast query failed: {e}")
        return None

def _get_close_event_by_ts(symbol: str, close_ts: int) -> dict | None:
    if not os.path.exists(TRADE_DB_PATH):
        return None
    try:
        with sqlite3.connect(TRADE_DB_PATH) as con:
            cur = con.execute(
                """
                SELECT ts, symbol, side, strategy, entry_price, exit_price, tp_price, sl_price, pnl, reason
                FROM trade_events
                WHERE event='CLOSE' AND symbol=? AND ts<=?
                ORDER BY ts DESC
                LIMIT 1
                """,
                (str(symbol).upper(), int(close_ts)),
            )
            row = cur.fetchone()
            if not row:
                return None
            close_ts_r, sym, side, strategy, entry_px, exit_px, tp, sl, pnl, reason = row
            entry_ts = None
            try:
                ecur = con.execute(
                    """
                    SELECT ts
                    FROM trade_events
                    WHERE event='ENTRY' AND symbol=? AND side=? AND strategy=? AND ts<=?
                    ORDER BY ts DESC
                    LIMIT 1
                    """,
                    (str(sym).upper(), str(side or ""), str(strategy or ""), int(close_ts_r or 0)),
                )
                erow = ecur.fetchone()
                if erow:
                    entry_ts = int(erow[0])
            except Exception:
                entry_ts = None
            return {
                "close_ts": int(close_ts_r or 0),
                "entry_ts": int(entry_ts or 0),
                "symbol": str(sym).upper(),
                "side": str(side or "Buy"),
                "strategy": str(strategy or ""),
                "entry_price": float(entry_px or 0.0),
                "exit_price": float(exit_px or 0.0),
                "tp_price": float(tp) if tp is not None else None,
                "sl_price": float(sl) if sl is not None else None,
                "pnl": float(pnl) if pnl is not None else None,
                "reason": str(reason or ""),
            }
    except Exception as e:
        log_error(f"plotts query failed: {e}")
        return None


def _get_last_open_entry_event(symbol: str, side: str | None = None) -> dict | None:
    if not os.path.exists(TRADE_DB_PATH):
        return None
    try:
        with sqlite3.connect(TRADE_DB_PATH) as con:
            params: list[Any] = [str(symbol).upper()]
            side_sql = ""
            if side:
                side_sql = " AND side=? "
                params.append(str(side))
            cur = con.execute(
                f"""
                SELECT ts, symbol, side, strategy, qty, entry_price, tp_price, sl_price, reason
                FROM trade_events
                WHERE event='ENTRY' AND symbol=? {side_sql}
                ORDER BY ts DESC
                LIMIT 1
                """,
                params,
            )
            row = cur.fetchone()
            if not row:
                return None
            entry_ts, sym, side_db, strategy, qty, entry_px, tp, sl, reason = row

            close_params: list[Any] = [str(sym).upper(), int(entry_ts or 0)]
            close_side_sql = ""
            if side_db:
                close_side_sql = " AND side=? "
                close_params.insert(1, str(side_db))
            ccur = con.execute(
                f"""
                SELECT ts
                FROM trade_events
                WHERE event='CLOSE' AND symbol=? {close_side_sql} AND ts>=?
                ORDER BY ts DESC
                LIMIT 1
                """,
                close_params,
            )
            crow = ccur.fetchone()
            if crow and int(crow[0] or 0) >= int(entry_ts or 0):
                return None

            return {
                "entry_ts": int(entry_ts or 0),
                "symbol": str(sym).upper(),
                "side": str(side_db or "Buy"),
                "strategy": str(strategy or ""),
                "qty": float(qty or 0.0),
                "entry_price": float(entry_px or 0.0),
                "tp_price": float(tp) if tp is not None else None,
                "sl_price": float(sl) if sl is not None else None,
                "reason": str(reason or ""),
            }
    except Exception as e:
        log_error(f"open entry query failed {symbol}: {e}")
        return None


def _list_unmatched_open_entry_events(limit: int = 50) -> list[dict]:
    if not os.path.exists(TRADE_DB_PATH):
        return []
    out: list[dict] = []
    try:
        with sqlite3.connect(TRADE_DB_PATH) as con:
            cur = con.execute(
                """
                SELECT e.ts, e.symbol, e.side, e.strategy, e.qty, e.entry_price, e.tp_price, e.sl_price, e.reason
                  FROM trade_events e
                 WHERE e.event='ENTRY'
                   AND NOT EXISTS (
                       SELECT 1
                         FROM trade_events c
                        WHERE c.event='CLOSE'
                          AND c.symbol=e.symbol
                          AND c.side=e.side
                          AND c.ts>=e.ts
                   )
                 ORDER BY e.ts DESC
                 LIMIT ?
                """,
                (int(limit),),
            )
            seen: set[tuple[str, str, str]] = set()
            for row in cur.fetchall():
                entry_ts, sym, side, strategy, qty, entry_px, tp, sl, reason = row
                key = (str(sym).upper(), str(side or "Buy"), str(strategy or ""))
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    {
                        "entry_ts": int(entry_ts or 0),
                        "symbol": str(sym).upper(),
                        "side": str(side or "Buy"),
                        "strategy": str(strategy or ""),
                        "qty": float(qty or 0.0),
                        "entry_price": float(entry_px or 0.0),
                        "tp_price": float(tp) if tp is not None else None,
                        "sl_price": float(sl) if sl is not None else None,
                        "reason": str(reason or ""),
                    }
                )
    except Exception as e:
        log_error(f"unmatched open entry query failed: {e}")
    return out


def reconcile_stale_db_entries_with_exchange(open_rows: list[dict]) -> None:
    """
    На старте подбирает незакрытые ENTRY в trades.db, которых уже нет в открытых
    позициях на бирже, и отдаёт их в обычный sync/closed-pnl pipeline.
    Так мы не оставляем stale-open хвосты после рестарта/ручного закрытия.
    """
    if DRY_RUN or TRADE_CLIENT is None:
        return

    live_open: set[tuple[str, str]] = set()
    for row in open_rows or []:
        sym = str(row.get("symbol") or "").upper().strip()
        side = str(row.get("side") or "Buy").strip() or "Buy"
        try:
            qty = abs(float(row.get("size") or 0.0))
        except Exception:
            qty = 0.0
        if sym and qty > 0:
            live_open.add((sym, side))

    staged = 0
    for ev in _list_unmatched_open_entry_events(limit=100):
        sym = str(ev.get("symbol") or "").upper().strip()
        side = str(ev.get("side") or "Buy").strip() or "Buy"
        if not sym or (sym, side) in live_open:
            continue
        key = ("Bybit", sym)
        if key in TRADES:
            continue

        tr = TradeState(symbol=sym, side=side, strategy=str(ev.get("strategy") or "bootstrap"))
        tr.qty = float(ev.get("qty") or 0.0)
        tr.status = "OPEN"
        tr.entry_ts = int(ev.get("entry_ts") or now_s())
        tr.entry_fill_ts = int(ev.get("entry_ts") or tr.entry_ts)
        tr.entry_confirm_sent = True
        tr.avg = float(ev.get("entry_price") or 0.0)
        tr.entry_price = float(ev.get("entry_price") or 0.0)
        tr.entry_price_req = float(ev.get("entry_price") or 0.0)
        tr.tp_price = ev.get("tp_price")
        tr.sl_price = ev.get("sl_price")
        tr.close_reason = "POSITION_GONE(RESTART_RECONCILE)"
        TRADES[key] = tr
        staged += 1

    if staged > 0:
        tg_trade(f"🔁 Startup reconcile: staged_stale_db_entries={staged}")
        try:
            sync_trades_with_exchange()
        except Exception as e:
            log_error(f"startup reconcile sync fail: {e}")

def _handle_tg_command(text: str):
    global TRADE_ON, RISK_PER_TRADE_PCT, BOT_CAPITAL_USD, MAX_POSITIONS

    cmd = text.strip().split()
    if not cmd:
        return
    name = cmd[0].lower()

    if name in ("/help", "/start"):
        tg_send_kb(
            "🤖 *Bybit Bot — Команды*\n\n"
            "📊 *Статус и мониторинг*\n"
            "  /status — баланс, риск, открытые позиции\n"
            "  /status_full — полный свод crypto + research stacks\n"
            "  /ping — время работы бота\n"
            "  /stats 7|30|90|365 — отчёт за период\n"
            "  /health — фильтр символов, killers/winners\n\n"
            "⚙️ *Управление торговлей*\n"
            "  /pause — пауза всех стратегий\n"
            "  /resume — возобновить торговлю\n"
            "  /risk 0.5 — риск на сделку в %\n"
            "  /capital 300 — капитал бота (USDT)\n"
            "  /positions 3 — макс. одновременных позиций\n\n"
            "🔍 *Фильтры и бан-лист*\n"
            "  /filters — текущие фильтры монет\n"
            "  /banlist — бан-лист символов\n"
            "  /ban BTC,ETH — добавить в бан\n"
            "  /unban BTC,ETH — убрать из бана\n\n"
            "📈 *Графики*\n"
            "  /plotlast [SYM] — график последней сделки\n\n"
            "🤖 *AI / DeepSeek*\n"
            "  /ai <вопрос> — задать вопрос AI-партнёру\n"
            "     Примеры:\n"
            "     /ai почему бот не входил сегодня?\n"
            "     /ai запусти autoresearch на breakdown\n"
            "     /ai какие стратегии сейчас активны?\n"
            "  /ai_backtest — быстрый бэктест 90d\n"
            "  /ai_results [strat] — топ autoresearch кандидаты\n"
            "     strat: breakout | flat | asc1 | breakdown | midterm | alpaca | portfolio\n"
            "  /ai_tune [strat] — AI предложит новые параметры\n"
            "     strat: breakout | flat | asc1 | breakdown | midterm | alpaca\n"
            "  /ai_audit — полный аудит бота (код+конфиг)\n"
            "  /ai_code <файл> [вопрос] — AI читает файл\n"
            "  /ai_budget — расход AI токенов\n"
            "  /ai_reset — сбросить историю диалога\n"
            "  /ai_server — статус сервера и процессов\n"
            "  /ai_diff — показать pending изменения от AI\n"
            "  /ai_rollback — откатить последнее изменение env\n"
            "  /ai_shadow — последние AI рекомендации (shadow log)"
        )
        return

    if name == "/status":
        eq = _get_effective_equity()
        _tg_reply(
            f"Status: {'ON' if TRADE_ON else 'OFF'} | disabled={PORTFOLIO_STATE.get('disabled')}\n"
            f"Equity≈{eq:.2f} USDT | open={len(TRADES)}\n"
            f"risk={RISK_PER_TRADE_PCT:.2f}% | max_positions={MAX_POSITIONS} | capital={_display_capital_text()}"
        )
        return

    if name == "/status_full":
        _tg_reply(_status_full_text())
        return

    if name == "/ping":
        up = max(0, int(time.time()) - int(BOT_START_TS))
        h = up // 3600
        m = (up % 3600) // 60
        s = up % 60
        _tg_reply(f"✅ alive | uptime {h:02d}:{m:02d}:{s:02d}")
        return

    if name == "/menu":
        tg_send_kb("Меню управления:")
        return

    if name == "/pause":
        TRADE_ON = False
        PORTFOLIO_STATE["disabled"] = True
        _tg_reply("Trading paused.")
        return

    if name == "/resume":
        TRADE_ON = True
        PORTFOLIO_STATE["disabled"] = False
        _tg_reply("Trading resumed.")
        return

    if name == "/risk" and len(cmd) >= 2:
        v = _parse_float(cmd[1])
        if v is None or v <= 0:
            _tg_reply("Usage: /risk 0.5  (percent)")
            return
        # treat as percent
        RISK_PER_TRADE_PCT = float(v)
        _tg_reply(f"Risk set to {RISK_PER_TRADE_PCT:.2f}%")
        return

    if name == "/capital" and len(cmd) >= 2:
        v = _parse_float(cmd[1])
        if v is None or v <= 0:
            _tg_reply("Usage: /capital 200")
            return
        BOT_CAPITAL_USD = float(v)
        _tg_reply(f"Bot capital set to {BOT_CAPITAL_USD:.2f} USDT")
        return

    if name in ("/positions", "/maxpos") and len(cmd) >= 2:
        v = _parse_float(cmd[1])
        if v is None:
            _tg_reply("Usage: /positions 3")
            return
        v = int(max(1, min(10, v)))
        MAX_POSITIONS = v
        _tg_reply(f"Max positions set to {MAX_POSITIONS}")
        return

    if name == "/banlist":
        allow, deny = _get_symbol_filters()
        _tg_reply(
            f"Allowlist ({len(allow)}): {','.join(sorted(allow)) if allow else '-'}\n"
            f"Denylist ({len(deny)}): {','.join(sorted(deny)) if deny else '-'}"
        )
        return

    if name == "/filters":
        _tg_reply(_symbol_filters_summary())
        return

    if name == "/filters_build":
        ok, msg = _build_symbol_filters()
        if ok:
            _tg_reply("✅ filters rebuilt\n" + _symbol_filters_summary())
        else:
            _tg_reply("❌ " + msg)
        return

    if name in ("/stats", "/report"):
        arg = (cmd[1].strip().lower() if len(cmd) >= 2 else "7")
        alias = {
            "d": 1, "day": 1, "daily": 1, "1d": 1, "1": 1,
            "w": 7, "week": 7, "weekly": 7, "7d": 7, "7": 7,
            "m": 30, "month": 30, "monthly": 30, "30d": 30, "30": 30,
            "q": 90, "90d": 90, "90": 90,
            "y": 365, "year": 365, "yearly": 365, "365d": 365, "365": 365,
        }
        days = alias.get(arg)
        if days is None:
            _tg_reply("Usage: /stats 7  (or 30/90/365)")
            return
        _send_report(f"manual_{days}d", int(days))
        return

    if name == "/health":
        _tg_reply(_health_summary_text())
        return

    if name == "/ai":
        prompt = text.partition(" ")[2].strip()
        if not prompt:
            _tg_reply(
                DEEPSEEK_OVERLAY.status_text()
                + "\n\nUsage: /ai <question>\n"
                + "Example: /ai почему бот сегодня не входил?"
            )
            return
        _tg_reply("🤖 AI думает...")
        # Run entirely in background thread — snapshot + ask + reply
        # IMPORTANT: snapshot is taken inside the thread so any failure
        # is caught by the thread's own try/except and reported to TG.
        import threading
        _ai_prompt = prompt  # capture before thread
        def _run_ai():
            print(f"[AI] thread started, prompt={_ai_prompt[:60]!r}")
            try:
                snap = _deepseek_snapshot()
                answer = DEEPSEEK_OVERLAY.ask(_ai_prompt, snap)
                print(f"[AI] ask() returned {len(answer) if answer else 0} chars")
                if not answer or not answer.strip():
                    answer = "❓ AI вернул пустой ответ. Попробуй ещё раз."
            except Exception as exc:
                print(f"[AI] exception: {exc}")
                answer = f"❌ AI ошибка: {exc}"
            # Split long answers into ≤4000-char chunks (Telegram limit = 4096)
            _CHUNK = 4000
            if len(answer) <= _CHUNK:
                tg_send(answer)
            else:
                parts = [answer[i:i + _CHUNK] for i in range(0, len(answer), _CHUNK)]
                for idx, part in enumerate(parts, 1):
                    tg_send(f"[{idx}/{len(parts)}]\n{part}")
            print(f"[AI] tg_send done")
        threading.Thread(target=_run_ai, daemon=True).start()
        return

    if name == "/ai_reset":
        DEEPSEEK_OVERLAY.reset_history()
        _tg_reply("AI history reset.")
        return

    if name == "/ai_regime":
        rg = _deepseek_local_regime_hint()
        _tg_reply(
            "DeepSeek regime scaffold:\n"
            f"label={rg.get('label')}\n"
            f"confidence={rg.get('confidence')}\n"
            f"reason={rg.get('reason')}"
        )
        return

    if name == "/ai_budget":
        _tg_reply(DEEPSEEK_OVERLAY.budget_status_text())
        return

    if name == "/ai_pending":
        _tg_reply(DEEPSEEK_OVERLAY.pending_actions_text())
        return

    if name == "/ai_shadow":
        _tg_reply(DEEPSEEK_OVERLAY.shadow_status_text())
        return

    if name == "/ai_shadow_reset":
        _tg_reply(DEEPSEEK_OVERLAY.reset_shadow_log())
        return

    if name == "/ai_approve" and len(cmd) >= 2:
        pid = _parse_float(cmd[1])
        if pid is None:
            _tg_reply("Usage: /ai_approve <id>")
            return
        _tg_reply(DEEPSEEK_OVERLAY.decide_proposal(int(pid), approve=True))
        return

    if name == "/ai_reject" and len(cmd) >= 2:
        pid = _parse_float(cmd[1])
        if pid is None:
            _tg_reply("Usage: /ai_reject <id>")
            return
        _tg_reply(DEEPSEEK_OVERLAY.decide_proposal(int(pid), approve=False))
        return

    # ── AI Autoresearch & Action commands ─────────────────────────────────────

    if name == "/ai_results":
        strategy_hint = cmd[1].lower() if len(cmd) >= 2 else None
        _tg_reply(results_report_text(strategy_hint=strategy_hint, top_n=3))
        return

    if name == "/ai_tune":
        strategy_hint = cmd[1].lower() if len(cmd) >= 2 else "breakout"
        _tg_reply("🔍 AI анализирует результаты, жди...")
        msg = tune_strategy(strategy_hint, DEEPSEEK_OVERLAY, _deepseek_snapshot())
        _tg_reply(msg)
        return

    if name == "/ai_audit":
        _tg_reply("🔍 DeepSeek читает код стратегий и конфиг, жди ~30 сек...")
        report = audit_bot_full(_deepseek_snapshot())
        # Split into chunks if too long for TG
        if len(report) > 4000:
            for i in range(0, len(report), 4000):
                _tg_reply(report[i:i+4000])
        else:
            _tg_reply(report)
        return

    if name == "/ai_code":
        # /ai_code strategies/alt_sloped_channel_v1.py [optional question]
        if len(cmd) < 2:
            _tg_reply(
                "Usage: /ai_code <filename> [вопрос]\n"
                "Примеры:\n"
                "  /ai_code strategies/alt_sloped_channel_v1.py\n"
                "  /ai_code bot/deepseek_autoresearch_agent.py как работает аудит?\n"
                "  /ai_code configs/server.env.example что у нас включено в live?"
            )
            return
        filename = cmd[1]
        question = " ".join(cmd[2:]) if len(cmd) > 2 else None
        _tg_reply(f"📄 Читаю {filename}...")
        answer = ask_about_file(filename, question, _deepseek_snapshot())
        if len(answer) > 4000:
            for i in range(0, len(answer), 4000):
                _tg_reply(answer[i:i+4000])
        else:
            _tg_reply(answer)
        return

    if name == "/ai_backtest":
        _tg_reply(trigger_mini_backtest())
        return

    if name == "/ai_diff":
        queue = DEEPSEEK_OVERLAY._load_approval_queue()
        pending = [x for x in queue if str(x.get("status", "")) == "approved"]
        _tg_reply(diff_pending_changes(pending))
        return

    if name == "/ai_deploy" and len(cmd) >= 2:
        pid = _parse_float(cmd[1])
        if pid is None:
            _tg_reply("Usage: /ai_deploy <proposal_id>")
            return
        queue = DEEPSEEK_OVERLAY._load_approval_queue()
        _tg_reply("📡 Применяю и деплою, жди...")
        result = execute_proposal(int(pid), queue, deploy=True)
        DEEPSEEK_OVERLAY._save_approval_queue(queue)
        _tg_reply(result)
        return

    if name == "/ai_rollback":
        result = rollback_env()
        _tg_reply(result)
        return

    if name == "/ai_server":
        _tg_reply(check_server_status())
        return

    if name == "/plotlast":
        req_sym = None
        if len(cmd) >= 2:
            req_sym = str(cmd[1]).upper().strip()
        ev = _get_last_close_event(req_sym)
        if not ev:
            _tg_reply("Нет закрытых сделок для построения графика.")
            return
        tr = TradeState(symbol=ev["symbol"], side=ev["side"], strategy=ev["strategy"])
        tr.entry_ts = int(ev.get("entry_ts") or 0)
        tr.exit_ts = int(ev.get("close_ts") or 0)
        tr.avg = float(ev.get("entry_price") or 0.0)
        tr.entry_price = float(ev.get("entry_price") or 0.0)
        tr.tp_price = ev.get("tp_price")
        tr.sl_price = ev.get("sl_price")
        png = _make_trade_chart(
            ev["symbol"],
            tr,
            stage="close",
            pnl=ev.get("pnl"),
            exit_px=ev.get("exit_price"),
        )
        if not png:
            _tg_reply("Не удалось построить график (недостаточно локальных 5m-баров).")
            return
        close_ts = int(ev.get("close_ts") or 0)
        dt = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(close_ts)) if close_ts > 0 else "-"
        pnl = ev.get("pnl")
        pnl_txt = f"{float(pnl):+.4f}" if pnl is not None else "n/a"
        cap = (
            f"plotlast {ev['symbol']} {ev['side']} [{ev.get('strategy','')}]\n"
            f"close={dt} pnl={pnl_txt} reason={ev.get('reason','')}\n"
            f"lines: cyan=ENTRY green=TP red=SL orange=EXIT"
        )
        tg_send_photo(png, caption=cap)
        return

    if name == "/plotts":
        if len(cmd) < 3:
            _tg_reply("Usage: /plotts SYMBOL CLOSE_TS")
            return
        req_sym = str(cmd[1]).upper().strip()
        try:
            req_ts = int(float(cmd[2]))
        except Exception:
            _tg_reply("Usage: /plotts SYMBOL CLOSE_TS")
            return
        ev = _get_close_event_by_ts(req_sym, req_ts)
        if not ev:
            _tg_reply("Сделка не найдена. Проверь SYMBOL/TS.")
            return
        tr = TradeState(symbol=ev["symbol"], side=ev["side"], strategy=ev["strategy"])
        tr.entry_ts = int(ev.get("entry_ts") or 0)
        tr.exit_ts = int(ev.get("close_ts") or 0)
        tr.avg = float(ev.get("entry_price") or 0.0)
        tr.entry_price = float(ev.get("entry_price") or 0.0)
        tr.tp_price = ev.get("tp_price")
        tr.sl_price = ev.get("sl_price")
        png = _make_trade_chart(
            ev["symbol"],
            tr,
            stage="close",
            pnl=ev.get("pnl"),
            exit_px=ev.get("exit_price"),
        )
        if not png:
            _tg_reply("Не удалось построить график (нет 5m баров).")
            return
        close_ts = int(ev.get("close_ts") or 0)
        dt = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(close_ts)) if close_ts > 0 else "-"
        pnl = ev.get("pnl")
        pnl_txt = f"{float(pnl):+.4f}" if pnl is not None else "n/a"
        cap = (
            f"plotts {ev['symbol']} {ev['side']} [{ev.get('strategy','')}]\n"
            f"close={dt} pnl={pnl_txt} reason={ev.get('reason','')}\n"
            f"lines: cyan=ENTRY green=TP red=SL orange=EXIT"
        )
        tg_send_photo(png, caption=cap)
        return

    if name == "/banreco":
        global LAST_RECO_SYMBOLS
        LAST_RECO_SYMBOLS = _compute_reco_symbols()
        if not LAST_RECO_SYMBOLS:
            _tg_reply("Нет рекомендаций (мало сделок/нет данных).")
            return
        _tg_reply("Рекомендую в бан: " + ",".join(LAST_RECO_SYMBOLS))
        return

    if name == "/banapply":
        if not LAST_RECO_SYMBOLS:
            _tg_reply("Нет сохранённых рекомендаций. Сначала /banreco.")
            return
        data = _load_symbol_filters()
        deny = set([str(x).upper() for x in (data.get("denylist") or [])])
        for s in LAST_RECO_SYMBOLS:
            deny.add(str(s).upper())
        data["denylist"] = sorted(deny)
        _save_symbol_filters(data)
        _tg_reply("Применил бан: " + ",".join(sorted(LAST_RECO_SYMBOLS)))
        return

    if name in ("/ban", "/unban") and len(cmd) >= 2:
        symbols = []
        for part in cmd[1:]:
            symbols.extend([s.strip().upper() for s in part.replace(";", ",").split(",") if s.strip()])
        if not symbols:
            _tg_reply("Usage: /ban SYM1,SYM2 или /unban SYM1,SYM2")
            return
        data = _load_symbol_filters()
        deny = set([str(x).upper() for x in (data.get("denylist") or [])])
        if name == "/ban":
            for s in symbols:
                deny.add(s)
            data["denylist"] = sorted(deny)
            _save_symbol_filters(data)
            _tg_reply("Добавил в бан: " + ",".join(symbols))
        else:
            for s in symbols:
                deny.discard(s)
            data["denylist"] = sorted(deny)
            _save_symbol_filters(data)
            _tg_reply("Убрал из бана: " + ",".join(symbols))
        return

    _tg_reply("Unknown command. /help")

async def tg_cmd_loop():
    if not (TG_TOKEN and TG_CHAT and TG_COMMANDS_ENABLE):
        return
    last_id = 0
    while True:
        try:
            params = {"timeout": 20}
            if last_id:
                params["offset"] = last_id + 1
            r = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates", params=params, timeout=25)
            j = r.json()
            updates = j.get("result", []) if isinstance(j, dict) else []
            for u in updates:
                uid = u.get("update_id") or 0
                if uid > last_id:
                    last_id = uid
                msg = u.get("message") or u.get("edited_message") or {}
                chat_id = str((msg.get("chat") or {}).get("id") or "")
                if chat_id != str(TG_CHAT):
                    continue
                # Extra security: only allow the designated admin user
                from_user_id = str((msg.get("from") or {}).get("id") or "")
                if TG_ADMIN_USER_ID and from_user_id and from_user_id != TG_ADMIN_USER_ID:
                    continue
                text = (msg.get("text") or "").strip()
                if text:
                    mapped = BUTTON_MAP.get(text.lower().strip())
                    if mapped:
                        text = mapped
                if text.startswith("/"):
                    _handle_tg_command(text)
        except Exception as e:
            log_error(f"tg cmd loop error: {e}")
        await asyncio.sleep(1)

def _load_report_state() -> Dict[str, int]:
    try:
        if not os.path.exists(REPORTS_STATE_PATH):
            return {}
        with open(REPORTS_STATE_PATH, "r") as f:
            return json.load(f) or {}
    except Exception:
        return {}

def _save_report_state(state: Dict[str, int]) -> None:
    try:
        with open(REPORTS_STATE_PATH, "w") as f:
            json.dump(state, f)
    except Exception:
        pass


def _strategy_runtime_stats_text(lookback_hours: int = 24) -> str:
    since_ts = int(time.time()) - max(1, int(lookback_hours)) * 3600
    by_strategy: dict[str, dict] = {}
    try:
        with sqlite3.connect(TRADE_DB_PATH) as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT strategy,
                       SUM(CASE WHEN event='ENTRY' THEN 1 ELSE 0 END) AS entries,
                       SUM(CASE WHEN event='CLOSE' THEN 1 ELSE 0 END) AS closes,
                       SUM(CASE WHEN event='CLOSE' THEN COALESCE(pnl, 0.0) ELSE 0.0 END) AS net
                  FROM trade_events
                 WHERE ts >= ?
                 GROUP BY strategy
                """,
                (since_ts,),
            )
            for st, e_cnt, c_cnt, net in cur.fetchall():
                name = str(st or "unknown")
                by_strategy[name] = {
                    "entries": int(e_cnt or 0),
                    "closes": int(c_cnt or 0),
                    "net": float(net or 0.0),
                    "open": 0,
                }
    except Exception as e:
        return f"📊 strategy-stats error: {e}"

    for tr in list(TRADES.values()):
        st_name = str(getattr(tr, "strategy", "") or "unknown")
        slot = by_strategy.setdefault(st_name, {"entries": 0, "closes": 0, "net": 0.0, "open": 0})
        if getattr(tr, "status", "") in ("OPEN", "PENDING_ENTRY"):
            slot["open"] += 1

    enabled = [
        f"breakout={ENABLE_BREAKOUT_TRADING}",
        f"pump_fade={ENABLE_PUMP_FADE_TRADING}",
        f"midterm={ENABLE_MIDTERM_TRADING}",
        f"inplay={ENABLE_INPLAY_TRADING}",
        f"retest={ENABLE_RETEST_TRADING}",
        f"range={ENABLE_RANGE_TRADING}",
        f"sloped={ENABLE_SLOPED_TRADING}",
        f"flat={ENABLE_FLAT_TRADING}",
        f"breakdown={ENABLE_BREAKDOWN_TRADING}",
        f"ts132={ENABLE_TS132_TRADING}",
    ]
    lines = [
        "🧠 strategies: " + " | ".join(enabled),
        f"📊 stats ({max(1, int(lookback_hours))}h):",
        f"🧪 {_runtime_diag_snapshot()}",
    ]
    if not by_strategy:
        lines.append(" - no events")
        return "\n".join(lines)

    def _score(item: tuple[str, dict]) -> tuple[float, int]:
        d = item[1]
        return (float(d.get("net", 0.0)), int(d.get("closes", 0)))

    for st_name, d in sorted(by_strategy.items(), key=_score, reverse=True):
        lines.append(
            f" - {st_name}: entry={d['entries']} close={d['closes']} open={d['open']} net={d['net']:+.4f}"
        )
    return "\n".join(lines)

def _fetch_5m_bars_bybit(sym: str, start_ts: int | None = None, end_ts: int | None = None) -> list[dict]:
    out: list[dict] = []
    try:
        base = (getattr(TRADE_CLIENT, "base", None) or BYBIT_BASE_DEFAULT).rstrip("/")
        url = f"{base}/v5/market/kline"
        params = {
            "category": "linear",
            "symbol": str(sym).upper(),
            "interval": "5",
            "limit": 1000,
        }
        if start_ts is not None:
            params["start"] = int(start_ts * 1000)
        if end_ts is not None:
            params["end"] = int(end_ts * 1000)

        r = requests.get(url, params=params, timeout=15)
        js = r.json() if r is not None else {}
        if int(js.get("retCode", -1)) != 0:
            log_error(f"chart bybit retCode={js.get('retCode')} retMsg={js.get('retMsg')} sym={sym}")
            return []
        rows = (((js or {}).get("result") or {}).get("list") or [])
        for row in rows:
            try:
                ts = int(row[0]) // 1000
                o = float(row[1]); h = float(row[2]); l = float(row[3]); c = float(row[4])
                q = float(row[6]) if len(row) > 6 else 0.0
                out.append({
                    "id": int(ts // 300),
                    "o": o,
                    "h": h,
                    "l": l,
                    "c": c,
                    "quote": q,
                })
            except Exception:
                continue
        out.sort(key=lambda b: int(b.get("id", 0)))
        dedup = {}
        for b in out:
            dedup[int(b.get("id", 0))] = b
        return [dedup[k] for k in sorted(dedup)]
    except Exception as e:
        log_error(f"chart bybit fetch fail {sym}: {e}")
        return []

def _make_trade_chart(sym: str, tr: TradeState, stage: str = "close", pnl: float | None = None, exit_px: float | None = None) -> str | None:
    if not TRADE_CHARTS_ENABLE:
        return None
    try:
        st = S("Bybit", sym)
        bars = list(st.bars5m)
        if st.cur5_id is not None and st.cur5_o is not None:
            bars.append({
                "id": st.cur5_id,
                "o": st.cur5_o,
                "h": st.cur5_h,
                "l": st.cur5_l,
                "c": st.cur5_c,
                "quote": st.cur5_quote,
            })
        if len(bars) < 20:
            entry_ts = int(getattr(tr, "entry_ts", 0) or 0)
            exit_ts = int(getattr(tr, "exit_ts", 0) or int(time.time()))
            pad = max(20, int(TRADE_CHARTS_PAD_BARS))
            win_sec = int((pad + 20) * 300)
            start_ts = max(0, min(entry_ts or exit_ts, exit_ts) - win_sec)
            end_ts = max(entry_ts, exit_ts) + win_sec
            remote = _fetch_5m_bars_bybit(sym, start_ts=start_ts, end_ts=end_ts)
            if not remote:
                # Fallback: latest bars without time range
                remote = _fetch_5m_bars_bybit(sym)
            if remote:
                bars = remote
        if len(bars) < 20:
            return None

        def _nearest_idx(target_id: int) -> int:
            best_i, best_d = 0, 10**18
            for i, b in enumerate(bars):
                d = abs(int(b.get("id", 0)) - target_id)
                if d < best_d:
                    best_i, best_d = i, d
            return best_i

        entry_ts = int(getattr(tr, "entry_ts", 0) or 0)
        exit_ts = int(getattr(tr, "exit_ts", 0) or 0)
        entry_id = max(0, entry_ts // 300) if entry_ts > 0 else int(bars[-1]["id"])
        exit_id = max(0, exit_ts // 300) if exit_ts > 0 else int(bars[-1]["id"])

        i_entry = _nearest_idx(entry_id)
        i_exit = _nearest_idx(exit_id)
        i_mid = i_exit if stage == "close" else i_entry
        pad = max(20, int(TRADE_CHARTS_PAD_BARS))
        i0 = max(0, i_mid - pad)
        i1 = min(len(bars), i_mid + pad)
        seg = bars[i0:i1]
        if len(seg) < 10:
            return None

        xs = list(range(len(seg)))
        opens = [float(b.get("o", 0) or 0) for b in seg]
        closes = [float(b.get("c", 0) or 0) for b in seg]
        highs = [float(b.get("h", 0) or 0) for b in seg]
        lows = [float(b.get("l", 0) or 0) for b in seg]
        quotes = [float(b.get("quote", 0) or 0) for b in seg]

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle

        os.makedirs(TRADE_CHARTS_OUT_DIR, exist_ok=True)
        out = os.path.join(
            TRADE_CHARTS_OUT_DIR,
            f"{sym}_{stage}_{int(time.time())}.png",
        )

        fig, ax = plt.subplots(figsize=(12.5, 6.2))
        fig.patch.set_facecolor("#0b1020")
        ax.set_facecolor("#0f172a")
        ax.grid(True, alpha=0.15, color="#94a3b8", linewidth=0.6)

        # Candlesticks
        candle_w = 0.65
        for i, (o, h, l, c) in enumerate(zip(opens, highs, lows, closes)):
            up = c >= o
            col = "#22c55e" if up else "#ef4444"
            ax.vlines(i, l, h, color=col, linewidth=1.0, alpha=0.95, zorder=2)
            body_low = min(o, c)
            body_h = max(abs(c - o), 1e-9)
            ax.add_patch(Rectangle((i - candle_w / 2.0, body_low), candle_w, body_h, facecolor=col, edgecolor=col, linewidth=0.8, alpha=0.9, zorder=3))

        seg_ids = [int(b.get("id", 0)) for b in seg]

        def _plot_vline(target_id: int, label: str):
            if not seg_ids:
                return
            idx = min(range(len(seg_ids)), key=lambda i: abs(seg_ids[i] - target_id))
            col = "#38bdf8" if label == "entry" else "#f59e0b"
            ax.axvline(idx, linestyle="--", linewidth=1.1, color=col, alpha=0.9, zorder=1)
            y_top = max(highs) if highs else 0.0
            if y_top > 0:
                y_shift = (max(highs) - min(lows)) * (0.01 if label == "entry" else 0.03)
                ax.text(idx + 0.2, y_top - y_shift, label.upper(), color=col, fontsize=8, va="bottom", ha="left")
            return idx

        entry_idx = _plot_vline(entry_id, "entry")
        exit_idx = None
        if stage == "close" and exit_ts > 0:
            exit_idx = _plot_vline(exit_id, "exit")

        entry_px = float(getattr(tr, "avg", 0) or getattr(tr, "entry_price", 0) or 0)
        tp = getattr(tr, "tp_price", None)
        sl = getattr(tr, "sl_price", None)
        x_lbl = len(seg) + 0.6
        if entry_px > 0:
            ax.axhline(entry_px, linestyle="-", linewidth=1.0, color="#38bdf8", alpha=0.75)
            ax.text(x_lbl, entry_px, "ENTRY", color="#38bdf8", fontsize=8, va="center", ha="left")
        if tp is not None:
            tp_v = float(tp)
            ax.axhline(tp_v, linestyle="--", linewidth=1.0, color="#22c55e", alpha=0.8)
            ax.text(x_lbl, tp_v, "TP", color="#22c55e", fontsize=8, va="center", ha="left")
        if sl is not None:
            sl_v = float(sl)
            ax.axhline(sl_v, linestyle="--", linewidth=1.0, color="#ef4444", alpha=0.8)
            ax.text(x_lbl, sl_v, "SL", color="#ef4444", fontsize=8, va="center", ha="left")
        if exit_px is not None:
            ex_v = float(exit_px)
            ax.axhline(ex_v, linestyle="-.", linewidth=1.0, color="#f59e0b", alpha=0.75)
            ax.text(x_lbl, ex_v, "EXIT", color="#f59e0b", fontsize=8, va="center", ha="left")

        # Context levels (simple SR from window)
        sr_hi = max(highs) if highs else None
        sr_lo = min(lows) if lows else None
        if sr_hi is not None and sr_lo is not None:
            span = max(sr_hi - sr_lo, 1e-9)
            lvl1 = sr_lo + span * 0.25
            lvl2 = sr_lo + span * 0.75
            ax.axhline(lvl1, color="#64748b", linewidth=0.8, alpha=0.35)
            ax.axhline(lvl2, color="#64748b", linewidth=0.8, alpha=0.35)

        # Inplay breakout reference level: prior 20-bar extreme before entry.
        # This helps see if entry is taken right into local exhaustion.
        brk_ref = None
        if str(getattr(tr, "strategy", "")) == "inplay_breakout" and entry_idx is not None and entry_idx > 5:
            lb = max(5, entry_idx - 20)
            pre_high = max(highs[lb:entry_idx]) if highs[lb:entry_idx] else None
            pre_low = min(lows[lb:entry_idx]) if lows[lb:entry_idx] else None
            side = str(getattr(tr, "side", "")).lower()
            if side == "buy" and pre_high is not None:
                brk_ref = float(pre_high)
                ax.axhline(pre_high, color="#a78bfa", linestyle=":", linewidth=1.0, alpha=0.9)
                ax.text(len(seg) + 0.6, pre_high, "BRK_REF", color="#a78bfa", fontsize=8, va="center", ha="left")
            if side == "sell" and pre_low is not None:
                brk_ref = float(pre_low)
                ax.axhline(pre_low, color="#a78bfa", linestyle=":", linewidth=1.0, alpha=0.9)
                ax.text(len(seg) + 0.6, pre_low, "BRK_REF", color="#a78bfa", fontsize=8, va="center", ha="left")

        if entry_idx is not None and 0 <= entry_idx < len(closes):
            side = str(getattr(tr, "side", "")).lower()
            m = "^" if side == "buy" else "v"
            y_entry = entry_px if entry_px > 0 else closes[entry_idx]
            ax.scatter([entry_idx], [y_entry], color="#38bdf8", s=80, marker=m, zorder=5, edgecolors="#0f172a", linewidths=0.8)
        if exit_idx is not None and 0 <= exit_idx < len(closes):
            side = str(getattr(tr, "side", "")).lower()
            m = "v" if side == "buy" else "^"
            y_exit = float(exit_px) if exit_px is not None else closes[exit_idx]
            ax.scatter([exit_idx], [y_exit], color="#f59e0b", s=80, marker=m, zorder=5, edgecolors="#0f172a", linewidths=0.8)

        title = f"{sym} {getattr(tr, 'side', '')} [{getattr(tr, 'strategy', '')}] {stage}"
        if pnl is not None:
            title += f" pnl={float(pnl):+.4f}"
        ax.set_title(title, color="#e2e8f0", fontsize=12, fontweight="bold")
        ax.set_xlabel("5m candles", color="#cbd5e1")
        ax.set_ylabel("price", color="#cbd5e1")
        ax.tick_params(colors="#94a3b8")
        for spine in ax.spines.values():
            spine.set_color("#334155")
        ax.set_xlim(-1, len(seg) + 8)
        legend_lines = [
            ("#38bdf8", "ENTRY line"),
            ("#22c55e", "TP line"),
            ("#ef4444", "SL line"),
            ("#f59e0b", "EXIT line"),
        ]
        for col, name in legend_lines:
            ax.plot([], [], color=col, label=name, linewidth=1.4)
        ax.legend(loc="upper right", facecolor="#111827", edgecolor="#334155", framealpha=0.9, fontsize=8, labelcolor="#e2e8f0")

        vol24h = sum(quotes) * 12.0
        mfe_txt = "-"
        mae_txt = "-"
        late_txt = "-"
        if entry_px > 0 and entry_idx is not None and 0 <= entry_idx < len(seg):
            h1 = min(len(seg), entry_idx + 13)  # 1h on 5m bars
            w_high = max(highs[entry_idx:h1]) if entry_idx < h1 else entry_px
            w_low = min(lows[entry_idx:h1]) if entry_idx < h1 else entry_px
            side = str(getattr(tr, "side", "")).lower()
            if side == "sell":
                mfe = (entry_px - w_low) / max(entry_px, 1e-9) * 100.0
                mae = (entry_px - w_high) / max(entry_px, 1e-9) * 100.0
            else:
                mfe = (w_high - entry_px) / max(entry_px, 1e-9) * 100.0
                mae = (w_low - entry_px) / max(entry_px, 1e-9) * 100.0
            mfe_txt = f"{mfe:+.2f}%"
            mae_txt = f"{mae:+.2f}%"
            if brk_ref is not None and brk_ref > 0:
                if side == "sell":
                    late = (brk_ref - entry_px) / brk_ref * 100.0
                else:
                    late = (entry_px - brk_ref) / brk_ref * 100.0
                late_txt = f"{late:+.2f}%"
        info = [
            f"Entry: {entry_px:.6f}" if entry_px > 0 else "Entry: -",
            f"Exit: {float(exit_px):.6f}" if exit_px is not None else "Exit: -",
            f"TP: {float(tp):.6f}" if tp is not None else "TP: -",
            f"SL: {float(sl):.6f}" if sl is not None else "SL: -",
            f"PnL: {float(pnl):+.4f}" if pnl is not None else "PnL: -",
            f"MFE(1h): {mfe_txt}",
            f"MAE(1h): {mae_txt}",
            f"Late vs BRK_REF: {late_txt}",
            f"Vol(24h est): {vol24h:,.0f}",
        ]
        ax.text(
            0.01,
            0.99,
            "\n".join(info),
            transform=ax.transAxes,
            va="top",
            ha="left",
            fontsize=9,
            color="#e2e8f0",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#111827", edgecolor="#334155", alpha=0.9),
        )

        fig.tight_layout()
        fig.savefig(out, dpi=160)
        plt.close(fig)
        return out
    except Exception as e:
        log_error(f"trade chart fail {sym} {stage}: {e}")
        return None

def _send_report(tag: str, days: int) -> None:
    since_ts = since_days(days)
    rep = generate_report(TRADE_DB_PATH, since_ts, REPORTS_OUT_DIR, tag)
    tg_trade(rep.text)
    if rep.csv_path:
        tg_send_doc(rep.csv_path, caption=f"{tag} CSV")
    if rep.png_path:
        tg_send_photo(rep.png_path, caption=f"{tag} chart")

async def reports_loop():
    if not REPORTS_ENABLE:
        return
    schedules = []
    if REPORT_DAILY_ENABLE:
        schedules.append(("daily", 1, 86400))
    if REPORT_WEEKLY_ENABLE:
        schedules.append(("weekly", 7, 7 * 86400))
    if REPORT_MONTHLY_ENABLE:
        schedules.append(("monthly", 30, 30 * 86400))
    if REPORT_YEARLY_ENABLE:
        schedules.append(("yearly", 365, 365 * 86400))
    state = _load_report_state()
    now = int(time.time())
    if REPORTS_SEND_ON_START:
        for tag, days, _ in schedules:
            _send_report(tag, days)
        if RECO_ENABLE:
            syms = _compute_reco_symbols()
            if syms:
                tg_trade("🧹 Рекомендую в бан: " + ",".join(syms))
        for tag, _, _ in schedules:
            state[tag] = now
        if RECO_ENABLE:
            state["reco"] = now
        _save_report_state(state)
    while True:
        now = int(time.time())
        for tag, days, period in schedules:
            last = int(state.get(tag, 0) or 0)
            if last == 0:
                # initialize without spamming
                state[tag] = now
                _save_report_state(state)
                continue
            if now - last >= period:
                _send_report(tag, days)
                state[tag] = now
                _save_report_state(state)
        if RECO_ENABLE:
            last_reco = int(state.get("reco", 0) or 0)
            if last_reco == 0:
                state["reco"] = now
                _save_report_state(state)
            elif now - last_reco >= int(RECO_PERIOD_SEC):
                syms = _compute_reco_symbols()
                if syms:
                    tg_trade("🧹 Рекомендую в бан: " + ",".join(syms))
                    global LAST_RECO_SYMBOLS
                    LAST_RECO_SYMBOLS = list(syms)
                state["reco"] = now
                _save_report_state(state)
        await asyncio.sleep(600)

def log_signal(row: dict):
    if not LOG_SIGNALS:
        return
    new_file = not os.path.exists(SIGNALS_CSV)
    try:
        with open(SIGNALS_CSV, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[
                "ts","exchange","symbol","pair","type","delta_pct","quote_usd",
                "x_to_med","zmad","trades","body","imb2","atr_pct","rsi",
                "ema_fast_gt_slow","ctx5m_pct","pattern"
            ])
            if new_file:
                w.writeheader()
            w.writerow(row)
    except Exception as e:
        log_error(f"signal-log-fail: {e}")

def log_error(msg: str):
    try:
        with open(ERRORS_LOG, "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}] {msg}\n")
    except Exception:
        pass

# base_from_usdt, now_s, _to_float_safe, _today_ymd → bot.utils (imported above)
# SymState, STATE, S, update_5m_bar, trim            → bot.symbol_state (imported above)
# calc_atr_pct, calc_rsi, ema_val, candle_pattern,
# engulfing, trade_quality                           → bot.symbol_state (imported above)

# =========================== BYBIT CLIENT ===========================
class BybitClient:

    def get_open_orders(self, symbol: str) -> list:
        j = self.get("/v5/order/realtime", {
            "category": "linear",
            "symbol": symbol,
            "openOnly": 1,
            "limit": 50,
        }, timeout=10)
        return (((j or {}).get("result") or {}).get("list") or [])

    def get_order(self, symbol: str, order_id: str) -> Optional[dict]:
        j = self.get("/v5/order/realtime", {
            "category": "linear",
            "symbol": symbol,
            "orderId": order_id,
            "limit": 50,
        }, timeout=10)
        lst = (((j or {}).get("result") or {}).get("list") or [])
        return lst[0] if lst else None

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        if DRY_RUN:
            return True
        try:
            self.post("/v5/order/cancel", {
                "category": "linear",
                "symbol": symbol,
                "orderId": order_id,
            }, timeout=10)
            return True
        except Exception as e:
            log_error(f"[{self.name}] cancel_order fail {symbol} {order_id}: {e}")
            return False

    def __init__(self, name: str, key: str, secret: str, base: str):
        self.name = name
        self.key = key
        self.secret = secret
        self.base = base.rstrip("/")
        self._lev_set = set()

    def place_market(self, symbol: str, side: str, qty: float, allow_quote_fallback: bool = True) -> Tuple[str, float]:

        if DRY_RUN:
            return f"DRYRUN-{self.name}-{symbol}-{int(time.time())}", qty

        def _mk_body_base(q):
            body = {
                "category":   "linear",
                "symbol":     symbol,
                "side":       side,
                "orderType":  "Market",
                "qty":        fmt_qty(symbol, q),
                "timeInForce":"IOC",
                "marketUnit": "baseCoin",
            }
            if not POS_IS_ONEWAY:
                body["positionIdx"] = 1 if side == "Buy" else 2
            return body

        def _mk_body_quote(q_usd):
            body = {
                "category":   "linear",
                "symbol":     symbol,
                "side":       side,
                "orderType":  "Market",
                "qty":        fmt_amt(symbol, q_usd),   
                "timeInForce":"IOC",
                "marketUnit": "quoteCoin",
            }
            if not POS_IS_ONEWAY:
                body["positionIdx"] = 1 if side == "Buy" else 2
            return body

        # 1) baseCoin c жёстким округлением
        try:
            q_fixed = strict_round_qty(symbol, qty)
            j = self.post("/v5/order/create", _mk_body_base(q_fixed))
            oid = j["result"]["orderId"]
            return oid, q_fixed
        except Exception as e:
            err_txt = str(e)

            # 2) fallback → quoteCoin (USDT) c мин/шагом
            # 2) fallback → quoteCoin (USDT) c мин/шагом
            if not allow_quote_fallback:
                # для bounce/риск-сайзинга нельзя "поднимать" notional через quoteCoin
                raise

            try:
                # подберём оценку quote USDT
                px = None
                st = None
                try:
                    st = S("Bybit", symbol)
                    if st and st.prices:
                        px = st.prices[-1][1]
                except Exception:
                    px = None
                if not px:
                    r = requests.get(
                        f"{self.base}/v5/market/tickers",
                        params={"category":"linear","symbol":symbol},
                        timeout=7
                    )
                    r.raise_for_status()
                    px = float(r.json()["result"]["list"][0]["lastPrice"])

                approx_usd = max(MIN_NOTIONAL_USD, float(qty) * float(px))

                usdt_q = strict_round_quote_amt(symbol, approx_usd)
                j2 = self.post("/v5/order/create", _mk_body_quote(usdt_q))
                oid2 = j2["result"]["orderId"]

                tg_trade(f"🟠 {self.name}: fallback→quoteCoin {symbol} {usdt_q} USDT")
                base_equiv = float(usdt_q) / max(1e-9, float(px))
                return oid2, base_equiv

            except Exception as e2:
                err_txt += f" | fallback_quote_fail={e2}"
                log_error(f"[{self.name}] create fail {symbol}: {err_txt}")
                tg_trade(
                    f"🛑 {self.name}: не смог открыть {side} {symbol} qty={qty} — {err_txt}\n"
                    f"👉 проверь, что деньги на торговом счёте (UNIFIED)"
                )
                raise


    def get_position(self, symbol: str) -> dict:
        """
        Возвращает dict позиции по символу или {}.
        Должно работать в ONE-WAY.
        """
        j = self.get("/v5/position/list", {
            "category": "linear",
            "symbol": symbol,
        }, timeout=10)
        lst = (((j or {}).get("result") or {}).get("list") or [])
        return lst[0] if lst else {}

    def get_executions(self, symbol: str, order_id: str, limit: int = 50) -> list:
        """
        Возвращает list филлов (execution) по order_id (если Bybit отдает).
        """
        j = self.get("/v5/execution/list", {
            "category": "linear",
            "symbol": symbol,
            "orderId": order_id,
            "limit": int(limit),
        }, timeout=10)
        return (((j or {}).get("result") or {}).get("list") or [])

    # --- общая подпись/хедеры/вызовы
    def _ts(self) -> str:
        return str(int(time.time()*1000))

    def _sign(self, prehash: str) -> str:
        return hmac.new(self.secret.encode(), prehash.encode(), hashlib.sha256).hexdigest()

    def _headers(self, ts: str, recv_window: str, payload: str) -> dict:
        prehash = f"{ts}{self.key}{recv_window}{payload}"
        return {
            "X-BAPI-API-KEY": self.key,
            "X-BAPI-SIGN": self._sign(prehash),
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": recv_window,
            "Content-Type": "application/json",
        }

    def get(self, path: str, params: Optional[dict] = None, timeout: int = 15) -> dict:
        params = params or {}
        if auth_disabled(self.name):
            last = AUTH_LAST_ERROR.get(self.name, "")
            raise RuntimeError(f"[{self.name}] AUTH_DISABLED: {last}")
        qs = urlencode(sorted(params.items()))
        ts = self._ts()
        headers = self._headers(ts, "5000", qs)
        url = f"{self.base}{path}"
        if qs:
            url += f"?{qs}"
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        j = r.json()

        rc = str(j.get("retCode"))

        if rc != "0":
            log_error(f"[{self.name}] GET {path} failed. Params={qs}  Resp={j}")

            # auth/permission errors -> ставим cooldown, чтобы не спамить приватные ручки
            msg = (str(j.get("retMsg") or "")).lower()
            if rc in ("33004", "10002", "10003", "10004", "10005") or ("api key" in msg) or ("expired" in msg) or ("invalid" in msg) or ("sign" in msg):
                err = RuntimeError(f"[{self.name}] Bybit AUTH error: {j}")
                mark_auth_fail(self.name, err, cooldown_sec=600)
                raise err

            raise RuntimeError(f"[{self.name}] Bybit GET error: {j}")

        return j


    def post(self, path: str, body: dict | None = None, timeout: int = 15) -> dict:
        body = body or {}
        if auth_disabled(self.name):
            last = AUTH_LAST_ERROR.get(self.name, "")
            raise RuntimeError(f"[{self.name}] AUTH_DISABLED: {last}")


        js = json.dumps(body, separators=(",", ":"))
        ts = self._ts()
        headers = self._headers(ts, "5000", js)
        url = f"{self.base}{path}"
        r = requests.post(url, headers=headers, data=js, timeout=timeout)
        r.raise_for_status()
        j = r.json()        
        rc = str(j.get("retCode"))

        if rc != "0":
            log_error(f"[{self.name}] POST {path} failed. Body={js}  Resp={j}")

            msg = (str(j.get("retMsg") or "")).lower()
            if rc in ("33004", "10002", "10003", "10004", "10005") or ("api key" in msg) or ("expired" in msg) or ("invalid" in msg) or ("sign" in msg):
                err = RuntimeError(f"[{self.name}] Bybit AUTH error: {j}")
                mark_auth_fail(self.name, err, cooldown_sec=600)
                raise err


            raise RuntimeError(f"[{self.name}] Bybit POST error: {j}")

        return j


    def wallet_balance(self) -> dict:
        return self.get("/v5/account/wallet-balance", {"accountType":"UNIFIED"})

    def ensure_leverage(self, symbol: str, lev: int):
        if DRY_RUN:
            return

        if not hasattr(self, "_lev_set") or self._lev_set is None:
            self._lev_set = set()

        if symbol in self._lev_set:
            return

        try:
            self.post("/v5/position/set-leverage", {
                "category": "linear",
                "symbol": symbol,
                "buyLeverage": str(lev),
                "sellLeverage": str(lev),
            })
            self._lev_set.add(symbol)

        except Exception as e:
            txt = str(e)
            low = txt.lower()

            # Bybit: leverage уже такое же -> это НЕ ошибка
            if ("110043" in txt) or ("leverage not modified" in low):
                self._lev_set.add(symbol)
                return

            log_error(f"[{self.name}] ensure_leverage({symbol}) failed: {e}")


    def close_market(self, symbol: str, side: str, qty: float):
        if DRY_RUN:
            return
        opp = "Sell" if side == "Buy" else "Buy"

        q = floor_qty_no_min(symbol, float(qty))   # <-- ВАЖНО
        if q <= 0:
            log_error(f"[{self.name}] close_market skip {symbol}: qty too small ({qty})")
            return

        body = {
            "category":   "linear",
            "symbol":     symbol,
            "side":       opp,
            "orderType":  "Market",
            "qty":        fmt_qty(symbol, q),
            "reduceOnly": True,
            "timeInForce":"IOC",
            "marketUnit": "baseCoin",
        }
        if not POS_IS_ONEWAY:
            body["positionIdx"] = 2 if side == "Sell" else 1
        self.post("/v5/order/create", body)

    
    def get_position_summary(self, symbol: str) -> tuple[float, Optional[str], int, Optional[float], Optional[float], Optional[float]]:
        j = self.get("/v5/position/list", {"category": "linear", "symbol": symbol}, timeout=10)
        lst = (j.get("result") or {}).get("list") or []
        if not lst:
            return 0.0, None, 0, None, None, None

        best_row = None
        best_size = 0.0
        for row in lst:
            size = abs(float(row.get("size") or 0.0))
            if size > best_size:
                best_size = size
                best_row = row

        if not best_row:
            return 0.0, None, 0, None, None, None

        side = best_row.get("side") or None
        pidx = int(best_row.get("positionIdx") or 0)

        tp = best_row.get("takeProfit")
        sl = best_row.get("stopLoss")
        tp_f = float(tp) if tp not in (None, "", "0") else None
        sl_f = float(sl) if sl not in (None, "", "0") else None

        avgp = best_row.get("avgPrice")
        avg_f = float(avgp) if avgp not in (None, "", "0") else None

        return float(best_size), side, pidx, tp_f, sl_f, avg_f

    def list_open_positions(self) -> list[dict]:
        j = self.get("/v5/position/list", {"category": "linear", "settleCoin": "USDT"}, timeout=10)
        lst = (j.get("result") or {}).get("list") or []
        out = []
        for row in lst:
            try:
                size = abs(float(row.get("size") or 0.0))
            except Exception:
                size = 0.0
            if size <= 0:
                continue
            out.append(row)
        return out

    def set_tp_sl(self, symbol: str, side: str, tp: Optional[float], sl: Optional[float]):
        """
        Ставит TP/SL на БИРЖЕ (position trading-stop).
        side = "Buy" | "Sell" (сторона позиции)
        """
        if DRY_RUN:
            return

        body = {
            "category": "linear",
            "symbol": symbol,
            "tpslMode": "Full",
            "tpTriggerBy": "LastPrice",
            "slTriggerBy": "LastPrice",
        }
        if tp is not None:
            body["takeProfit"] = fmt_price(symbol, float(tp))
        if sl is not None:
            body["stopLoss"] = fmt_price(symbol, float(sl))

        # hedge-mode: обязательно positionIdx
        if not POS_IS_ONEWAY:
            body["positionIdx"] = 1 if side == "Buy" else 2

        self.post("/v5/position/trading-stop", body, timeout=10)
    
    def get_closed_pnl(self, symbol: str, start_time_ms: int, end_time_ms: int | None = None, limit: int = 50) -> list:
        """
        Возвращает список закрытых сделок по символу с realized PnL и комиссиями.
        """
        params = {
            "category": "linear",
            "symbol": symbol,
            "startTime": int(start_time_ms),
            "limit": int(limit),
        }
        if end_time_ms is not None:
            params["endTime"] = int(end_time_ms)

        j = self.get("/v5/position/closed-pnl", params, timeout=10)
        return (((j or {}).get("result") or {}).get("list") or [])
    
def sync_trades_with_exchange():
    if DRY_RUN or TRADE_CLIENT is None:
        return

    now = now_s()

    for (exch, sym), tr in list(TRADES.items()):
        if exch != "Bybit":
            continue

        # --- PENDING_PNL: позиция уже закрыта, ждём запись closed-pnl ---
        if getattr(tr, "status", "") == "PENDING_PNL":
            age = now - int(getattr(tr, "pending_pnl_since", now) or now)

            if age > PENDING_PNL_MAX_SEC:
                tg_trade(f"🟡 PNL TIMEOUT {sym}: closed-pnl not found after {PENDING_PNL_MAX_SEC}s")
                try:
                    del TRADES[(exch, sym)]
                except Exception:
                    pass
                continue

            # пробуем ещё раз добрать pnl/fees
            _finalize_and_report_closed(tr, sym)

            # если добрали — удаляем из активных; если всё ещё pending — оставляем
            if getattr(tr, "status", "") == "CLOSED":
                try:
                    del TRADES[(exch, sym)]
                except Exception:
                    pass
            continue

        # --- обычный sync: читаем позицию ---
        try:
            size, side, pidx, tp_ex, sl_ex, avg_ex = TRADE_CLIENT.get_position_summary(sym)
        except Exception as e:
            log_error(f"sync position fail {sym}: {e}")
            continue

        # --- 1) Если вход ещё не подтверждён ---
        if getattr(tr, "status", "OPEN") == "PENDING_ENTRY":
            age = now - int(tr.entry_ts or now)

            # позиция появилась -> OPEN
            if size > 0:
                tr.status = "OPEN"
                if not getattr(tr, "entry_fill_ts", 0):
                    tr.entry_fill_ts = int(now)

                tr.qty = float(size)
                if side in ("Buy", "Sell"):
                    tr.side = side

                # ✅ реальный avgPrice с биржи
                if avg_ex is not None and float(avg_ex) > 0:
                    tr.avg = float(avg_ex)
                    tr.entry_price = float(avg_ex)

                    # если TP/SL уже были рассчитаны по "примерному" price — пересчитаем от реального avg
                    if getattr(tr, "strategy", "pump") in ("bounce", "range", "inplay", "inplay_breakout", "btc_eth_midterm_pullback"):
                        # bounce tp/sl могли прийти из сигнала — оставляем их как есть,
                        # но гарантируем корректное округление относительно entry
                        tr.tp_price, tr.sl_price = round_tp_sl_prices(sym, tr.side, tr.avg, tr.tp_price, tr.sl_price)
                    else:
                        # pump стратегия: tp/sl пересчитать от avg
                        if tr.side == "Sell":
                            tp_raw = tr.avg * (1.0 - TP_PCT / 100.0)
                            sl_raw = tr.avg * (1.0 + SL_PCT / 100.0)
                        else:
                            tp_raw = tr.avg * (1.0 + TP_PCT / 100.0)
                            sl_raw = tr.avg * (1.0 - SL_PCT / 100.0)
                        tr.tp_price, tr.sl_price = round_tp_sl_prices(sym, tr.side, tr.avg, tp_raw, sl_raw)

                # поставить TP/SL, когда позиция реально появилась
                if not (RESPECT_MANUAL_TPSL and getattr(tr, "tpsl_manual_lock", False)):
                    if tr.tp_price is not None or tr.sl_price is not None:
                        ok = set_tp_sl_retry(sym, tr.side, tr.tp_price, tr.sl_price)
                        tr.tpsl_on_exchange = bool(ok)
                        tr.tpsl_last_set_ts = now_s()
                        if ok:
                            tr.tpsl_manual_lock = False

                if not getattr(tr, "entry_confirm_sent", False):
                    tr.entry_confirm_sent = True
                    lat_parts = []
                    sig_ts = int(getattr(tr, "signal_ts", 0) or 0)
                    send_ts = int(getattr(tr, "order_send_ts", 0) or 0)
                    fill_ts = int(getattr(tr, "entry_fill_ts", 0) or 0)
                    if sig_ts > 0 and send_ts >= sig_ts:
                        lat_parts.append(f"sig→send={send_ts - sig_ts}s")
                    if send_ts > 0 and fill_ts >= send_ts:
                        lat_parts.append(f"send→fill={fill_ts - send_ts}s")
                    lat_txt = ("\nLatency: " + " | ".join(lat_parts)) if lat_parts else ""
                    tg_trade(
                        f"✅ ENTRY FILLED {sym} {tr.side} qty={tr.qty} avg={float(getattr(tr,'avg',0) or 0):.6f}"
                        f"{lat_txt}"
                    )
                    _db_log_event("ENTRY", tr, sym)
                    _db_log_ml_entry(tr, sym)
                    if TRADE_CHARTS_SEND_ON_ENTRY:
                        p = _make_trade_chart(sym, tr, stage="entry")
                        if p:
                            tg_send_photo(p, caption=f"entry chart {sym} {tr.side} [{getattr(tr, 'strategy', '')}]")
                continue

            # позиции нет — ждём grace период
            if age < ENTRY_CONFIRM_GRACE_SEC:
                continue

            # grace вышел — считаем вход не состоялся
            tr.status = "FAILED"
            tr.close_reason = "ENTRY_NOT_CONFIRMED"
            tg_trade(f"🟡 ENTRY FAILED {sym}: no position after {ENTRY_CONFIRM_GRACE_SEC}s")
            try:
                del TRADES[(exch, sym)]
            except Exception:
                pass
            continue

        # --- 2) Если сделка OPEN и позиции нет — закрыто (TP/SL/manual) ---
        if getattr(tr, "status", "OPEN") == "OPEN":
            if size <= 0:
                tr.close_reason = tr.close_reason or "POSITION_GONE(TP/SL/MANUAL)"
                _finalize_and_report_closed(tr, sym)

                # ВАЖНО: удаляем только если уже "CLOSED".
                # Если "PENDING_PNL" — оставляем в TRADES, чтобы добрать PnL в следующих sync.
                if getattr(tr, "status", "") == "CLOSED":
                    try:
                        del TRADES[(exch, sym)]
                    except Exception:
                        pass
                continue

            # обновим qty/side, если частично закрыли руками
            tr.qty = float(size)
            if side in ("Buy", "Sell"):
                tr.side = side

            # manual TP/SL lock — оставляем как у тебя
            if RESPECT_MANUAL_TPSL:
                age2 = now - int(getattr(tr, "tpsl_last_set_ts", 0) or 0)
                if (tp_ex is not None or sl_ex is not None) and age2 >= MANUAL_TPSL_MIN_AGE_SEC:
                    changed = tpsl_diff(sym, tr.tp_price, tp_ex) or tpsl_diff(sym, tr.sl_price, sl_ex)
                    if changed:
                        tr.tp_price = tp_ex
                        tr.sl_price = sl_ex
                        tr.tpsl_manual_lock = True
                        tr.tpsl_on_exchange = True
                        tg_trade(f"🧷 MANUAL TPSL LOCK {sym}: TP={tp_ex} SL={sl_ex}")

# =========================== КЛИЕНТЫ ===========================
BYBIT_CLIENTS: List[BybitClient] = []
for acc in ACCOUNTS:
    if acc.get("key") and acc.get("secret"):
        BYBIT_CLIENTS.append(BybitClient(acc.get("name","noname"), acc["key"], acc["secret"], acc.get("base", BYBIT_BASE_DEFAULT)))

TRADE_CLIENT: Optional[BybitClient] = next((c for c in BYBIT_CLIENTS if c.name == TRADE_ACCOUNT_NAME), None)

# =========================== APPLY PER-ACCOUNT TRADE SETTINGS ===========================
def _find_account_cfg(name: str) -> Optional[dict]:
    for a in (ACCOUNTS or []):
        if (a.get("name") or "").strip() == name:
            return a
    return None

_acc_cfg = _find_account_cfg(TRADE_ACCOUNT_NAME)
_trade_cfg = (_acc_cfg or {}).get("trade") or (_acc_cfg or {})

# defaults (если в JSON нет поля)
try:
    BYBIT_LEVERAGE = int(_trade_cfg.get("leverage", BYBIT_LEVERAGE))
except Exception:
    pass

try:
    MAX_POSITIONS = int(_trade_cfg.get("max_positions", _trade_cfg.get("max_trades", MAX_POSITIONS)))
except Exception:
    pass

try:
    RISK_PER_TRADE_PCT = float(_trade_cfg.get("risk_pct", RISK_PER_TRADE_PCT))
    # normalize: allow config to be either fraction (0.01) or percent (1.0)
    # if user passed a fraction (<=1), convert to percent for internal logic
    if RISK_PER_TRADE_PCT > 0 and RISK_PER_TRADE_PCT <= 1.0:
        RISK_PER_TRADE_PCT *= 100.0
except Exception:
    pass

try:
    CAP_NOTIONAL_TO_EQUITY = bool(_trade_cfg.get("cap_notional_to_equity", CAP_NOTIONAL_TO_EQUITY))
except Exception:
    pass

# position mode может быть индивидуальным
try:
    BYBIT_POS_MODE = str(_trade_cfg.get("position_mode", BYBIT_POS_MODE)).strip().lower()
except Exception:
    pass
# --- extra per-account fields (from BYBIT_ACCOUNTS_JSON.trade) ---
try:
    # allow "enabled" to override TRADE_ON per account
    if "enabled" in _trade_cfg:
        TRADE_ON = bool(_trade_cfg.get("enabled"))
except Exception:
    pass

try:
    # support both names: max_positions OR max_trades
    if "max_positions" in _trade_cfg:
        MAX_POSITIONS = int(_trade_cfg.get("max_positions", MAX_POSITIONS))
    elif "max_trades" in _trade_cfg:
        MAX_POSITIONS = int(_trade_cfg.get("max_trades", MAX_POSITIONS))
except Exception:
    pass

try:
    if "reserve_equity_frac" in _trade_cfg:
        RESERVE_EQUITY_FRAC = float(_trade_cfg.get("reserve_equity_frac", RESERVE_EQUITY_FRAC))
except Exception:
    pass

try:
    if "min_notional_usd" in _trade_cfg:
        MIN_NOTIONAL_USD = float(_trade_cfg.get("min_notional_usd", MIN_NOTIONAL_USD))
except Exception:
    pass

try:
    if "bounce_execute_trades" in _trade_cfg:
        BOUNCE_EXECUTE_TRADES = bool(_trade_cfg.get("bounce_execute_trades", BOUNCE_EXECUTE_TRADES))
except Exception:
    pass

try:
    if "bounce_top_n" in _trade_cfg:
        BOUNCE_TOP_N = int(_trade_cfg.get("bounce_top_n", BOUNCE_TOP_N))
except Exception:
    pass


try:
    # ✅ ГЛАВНЫЙ РЕГУЛЯТОР: лимит капитала бота
    if "bot_capital_usd" in _trade_cfg:
        BOT_CAPITAL_USD = float(_trade_cfg.get("bot_capital_usd"))
except Exception:
    pass

POS_IS_ONEWAY = (BYBIT_POS_MODE != "hedge")
# =======================================================================================


# =========================== МЕТА ПО СИМВОЛАМ ===========================
_BYBIT_LAST = {}  # symbol -> lastPrice (float), кеш из /market/tickers
_BYBIT_CACHE = {"syms": [], "ts": 0}
_BYBIT_META = {}


def bybit_symbols(top_n:int)->List[str]:
    base_url = (TRADE_CLIENT.base if (TRADE_CLIENT is not None) else BYBIT_BASE_DEFAULT)
    now = int(time.time())
    if _BYBIT_CACHE["syms"] and now - _BYBIT_CACHE["ts"] < 600:
        syms = _BYBIT_CACHE["syms"]
        return syms if top_n is None else syms[:top_n]

    r1 = requests.get(f"{base_url}/v5/market/instruments-info",
                      params={"category":"linear"}, timeout=15)
    r1.raise_for_status()
    inst = [x for x in r1.json()["result"]["list"]
            if x["status"]=="Trading" and x["quoteCoin"]=="USDT"]

    for x in inst:
        sym = x["symbol"]
        flt = x.get("lotSizeFilter", {}) or {}
        pf  = x.get("priceFilter", {}) or {}

        _BYBIT_META[sym] = {
            "qtyStep": _to_float_safe(flt.get("qtyStep", "0.001"), 0.001),
            "minOrderQty": _to_float_safe(flt.get("minOrderQty", "0.001"), 0.001),

            "amtStep": _to_float_safe(flt.get("amtStep", "1"), 1.0),           # шаг по USDT для quoteCoin
            "minOrderAmt": _to_float_safe(flt.get("minOrderAmt", "5"), 5.0),   # минималка по USDT

            "tickSize": _to_float_safe(pf.get("tickSize", "0.000001"), 0.000001),  # шаг цены (важно для TP/SL)
        }

    t = requests.get(
        f"{base_url}/v5/market/tickers",
        params={"category":"linear"},
        timeout=15
    ).json()["result"]["list"]

    t24 = {x["symbol"]: float(x.get("turnover24h", 0) or 0) for x in t}

    # lastPrice cache (для фильтра min-notional под депозит)
    global _BYBIT_LAST
    _BYBIT_LAST = {}
    for x in t:
        sym = x.get("symbol")
        lp = x.get("lastPrice")
        if sym and lp not in (None, "", "0"):
            try:
                _BYBIT_LAST[sym] = float(lp)
            except Exception:
                pass


    inst = [x for x in inst if t24.get(x["symbol"],0) >= MIN_24H_TURNOVER]
    inst.sort(key=lambda x: t24.get(x["symbol"],0), reverse=True)
    syms = [x["symbol"] for x in inst]

    _BYBIT_CACHE["syms"] = syms
    _BYBIT_CACHE["ts"] = now
    return syms if top_n is None else syms[:top_n]

def _decimals_from_step(step: float) -> int:
    s = f"{step:.10f}".rstrip('0').rstrip('.')
    if '.' in s:
        return len(s.split('.')[1])
    return 0

def round_qty(symbol: str, qty: float) -> float:
    meta = _BYBIT_META.get(symbol, {"qtyStep": 0.001, "minOrderQty": 0.001})
    step = float(meta["qtyStep"] or 0.001)
    minq = float(meta["minOrderQty"] or 0.001)

    d_step = Decimal(str(step))
    d_qty  = Decimal(str(qty))

    # округляем вниз к кратности шага
    q = (d_qty / d_step).to_integral_value(rounding=ROUND_DOWN) * d_step
    if q < Decimal(str(minq)):
        q = Decimal(str(minq))

    # форматируем с ровно нужным числом знаков (иначе Bybit может ругаться на формат)
    decs = _decimals_from_step(step)
    return float(f"{q:.{decs}f}")

def tpsl_diff(sym: str, a: Optional[float], b: Optional[float]) -> bool:
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    tick = float(_get_meta(sym).get("tickSize") or 0.000001)
    eps = tick * float(MANUAL_TPSL_DETECT_TICKS)
    return abs(float(a) - float(b)) > eps


def _get_meta(symbol: str) -> dict:
    # берем из кеша, а если вдруг нет — дотащим через instruments-info
    m = _BYBIT_META.get(symbol)
    if m:
        return m
    try:
        base_url = (TRADE_CLIENT.base if TRADE_CLIENT else BYBIT_BASE_DEFAULT)
        r = requests.get(f"{base_url}/v5/market/instruments-info",
                         params={"category":"linear","symbol":symbol}, timeout=7)
        j = r.json()
        lst = ((j.get("result") or {}).get("list") or [])
        if lst:
            flt = lst[0].get("lotSizeFilter", {}) or {}
            pf  = lst[0].get("priceFilter", {}) or {}

            m = {
                "qtyStep": _to_float_safe(flt.get("qtyStep", "1")),
                "minOrderQty": _to_float_safe(flt.get("minOrderQty", "1")),
                "amtStep": _to_float_safe(flt.get("amtStep", "1")),
                "minOrderAmt": _to_float_safe(flt.get("minOrderAmt", "5")),
                "tickSize": _to_float_safe(pf.get("tickSize", "0.000001")),
            }

            _BYBIT_META[symbol] = m
            return m
    except Exception as e:
        log_error(f"meta fetch fail {symbol}: {e}")
    return {"qtyStep": 1.0, "minOrderQty": 1.0}
def _fmt_by_step(val: float, step: float) -> str:
    step = float(step or 1.0)
    s = f"{step:.10f}".rstrip("0").rstrip(".")
    decs = len(s.split(".")[1]) if "." in s else 0
    return f"{float(val):.{decs}f}"

def fmt_qty(symbol: str, qty: float) -> str:
    m = _get_meta(symbol)
    return _fmt_by_step(qty, float(m.get("qtyStep") or 1.0))

def fmt_amt(symbol: str, amt: float) -> str:
    m = _get_meta(symbol)
    return _fmt_by_step(amt, float(m.get("amtStep") or 1.0))

def fmt_price(symbol: str, px: float) -> str:
    m = _get_meta(symbol)
    return _fmt_by_step(px, float(m.get("tickSize") or 0.000001))

def strict_round_qty(symbol: str, qty: float) -> float:
    meta = _get_meta(symbol)
    step = float(meta.get("qtyStep") or 1.0)
    minq = float(meta.get("minOrderQty") or 1.0)

    # округляем ВНИЗ к кратности шага
    d_step = Decimal(str(step))
    d_qty  = Decimal(str(qty))
    q = (d_qty / d_step).to_integral_value(rounding=ROUND_DOWN) * d_step
    if q < Decimal(str(minq)):
        q = Decimal(str(minq))

    # строгое форматирование по числу знаков шага (иначе Bybit ругается)

    s = f"{step:.10f}".rstrip('0').rstrip('.')
    decs = len(s.split('.')[1]) if '.' in s else 0
    return float(f"{q:.{decs}f}")

def floor_qty_no_min(symbol: str, qty: float) -> float:
    """
    Для reduceOnly close: только округление ВНИЗ по qtyStep.
    НЕ поднимаем до minOrderQty (иначе можно попытаться закрыть больше чем есть).
    """
    meta = _get_meta(symbol)
    step = float(meta.get("qtyStep") or 1.0)
    if qty <= 0:
        return 0.0

    d_step = Decimal(str(step))
    d_qty  = Decimal(str(qty))
    q = (d_qty / d_step).to_integral_value(rounding=ROUND_DOWN) * d_step

    # формат по количеству знаков шага
    s = f"{step:.10f}".rstrip('0').rstrip('.')
    decs = len(s.split('.')[1]) if '.' in s else 0
    out = float(f"{q:.{decs}f}")
    return out if out > 0 else 0.0


def strict_round_quote_amt(symbol: str, usdt_amt: float) -> float:
    meta = _get_meta(symbol)
    step = float(meta.get("amtStep") or 1.0)
    min_amt = float(meta.get("minOrderAmt") or 5.0)
    d_step = Decimal(str(step))
    d_amt  = Decimal(str(usdt_amt))
    q = (d_amt / d_step).to_integral_value(rounding=ROUND_DOWN) * d_step
    if q < Decimal(str(min_amt)):
        q = Decimal(str(min_amt))
    # шаг по USDT обычно целый → формат без лишних знаков
    s = f"{step:.10f}".rstrip('0').rstrip('.')
    decs = len(s.split('.')[1]) if '.' in s else 0
    return float(f"{q:.{decs}f}")
def strict_round_price_dir(symbol: str, price: float, rounding_mode) -> float:
    """
    Округляет цену по tickSize В НУЖНУЮ СТОРОНУ:
    rounding_mode = ROUND_DOWN или ROUND_UP
    """
    meta = _get_meta(symbol)
    step = float(meta.get("tickSize") or 0.000001)

    d_step = Decimal(str(step))
    d_px   = Decimal(str(price))

    px = (d_px / d_step).to_integral_value(rounding=rounding_mode) * d_step

    s = f"{step:.10f}".rstrip('0').rstrip('.')
    decs = len(s.split('.')[1]) if '.' in s else 0
    return float(f"{px:.{decs}f}")


def round_tp_sl_prices(symbol: str, side: str, entry: float,
                       tp_raw: float | None, sl_raw: float | None) -> tuple[float | None, float | None]:
    """
    Консервативно и безопасно:
      Buy : TP вверх (away), SL вниз (away)
      Sell: TP вниз (away), SL вверх (away)
    + гарантирует, что TP/SL валидны относительно entry (минимум 1 тик дистанции).
    """
    meta = _get_meta(symbol)
    tick = float(meta.get("tickSize") or 0.000001)
    if tick <= 0:
        tick = 0.000001

    tp = None
    sl = None

    # rounding to tick
    if tp_raw is not None:
        tp_mode = ROUND_UP if side == "Buy" else ROUND_DOWN
        tp = strict_round_price_dir(symbol, float(tp_raw), tp_mode)

    if sl_raw is not None:
        sl_mode = ROUND_DOWN if side == "Buy" else ROUND_UP
        sl = strict_round_price_dir(symbol, float(sl_raw), sl_mode)


    # fix logical placement vs entry (do not drop to None — fix by 1 tick)
      
    if entry and entry > 0:
        if side == "Buy":
            if tp is not None and tp <= entry:
                tp = strict_round_price_dir(symbol, entry + tick, ROUND_UP)   
            if sl is not None and sl >= entry:
                sl = strict_round_price_dir(symbol, entry - tick, ROUND_DOWN) 
        else:  
            if tp is not None and tp >= entry:
                tp = strict_round_price_dir(symbol, entry - tick, ROUND_DOWN) 
  
            if sl is not None and sl <= entry:
                sl = strict_round_price_dir(symbol, entry + tick, ROUND_UP)   

    return tp, sl


def _prepare_exchange_tpsl(
    symbol: str,
    side: str,
    tp: Optional[float],
    sl: Optional[float],
    entry_ref: Optional[float] = None,
) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Финальная sanity-подготовка TP/SL перед отправкой на биржу.

    Что делаем:
      - выбрасываем нечисловые / <= 0 значения;
      - если есть entry_ref, ещё раз прогоняем через round_tp_sl_prices();
      - не даём отправить на биржу логически перевёрнутые уровни.
    """
    def _norm(px: Optional[float]) -> Optional[float]:
        if px in (None, "", "0"):
            return None
        try:
            out = float(px)
        except Exception:
            return None
        if not math.isfinite(out) or out <= 0:
            return None
        return out

    tp_v = _norm(tp)
    sl_v = _norm(sl)
    entry_v = _norm(entry_ref)

    if entry_v is not None:
        tp_v, sl_v = round_tp_sl_prices(symbol, side, entry_v, tp_v, sl_v)

    if tp_v is not None and sl_v is not None:
        if side == "Buy" and tp_v <= sl_v:
            return None, None, f"invalid Buy TP/SL after sanitize: tp={tp_v} sl={sl_v} entry={entry_v}"
        if side == "Sell" and tp_v >= sl_v:
            return None, None, f"invalid Sell TP/SL after sanitize: tp={tp_v} sl={sl_v} entry={entry_v}"

    return tp_v, sl_v, None


# =========================== TP/SL RETRY + RISK SIZING ===========================
_LAST_TPSL_ENSURE_TS = 0

def _finalize_and_report_closed(tr, sym: str):
    now = now_s()

    # если entry_ts не выставлен — поставим, чтобы окно не улетело
    entry_ts = int(getattr(tr, "entry_ts", 0) or 0)
    if entry_ts <= 0:
        entry_ts = now - 3600

    # небольшой буфер назад/вперёд, чтобы запись точно попала в окно
    start_ms = int((entry_ts - 120) * 1000)
    end_ms   = int((now + 120) * 1000)

    rows = []
    try:
        rows = TRADE_CLIENT.get_closed_pnl(sym, start_ms, end_ms, limit=50)
    except Exception as e:
        log_error(f"closed-pnl fetch fail {sym}: {e}")

    # выберем самую свежую запись
    row = None
    if rows:
        def _t(r):
            return int(r.get("updatedTime") or r.get("createdTime") or 0)
        row = max(rows, key=_t)

    pnl_closed = None
    fee_sum = None
    exit_px = None

    if row:
        # closedPnl: отличаем "нет поля" от "0"
        pnl_raw = row.get("closedPnl", None)
        if pnl_raw not in (None, ""):
            try:
                pnl_closed = float(pnl_raw)
            except Exception:
                pnl_closed = None

        # exit price (на разных аккаунтах/версиях Bybit ключи могут отличаться)
        for k in ("avgExitPrice", "exitPrice", "avgClosePrice", "closeAvgPrice"):
            v = row.get(k)
            if v not in (None, "", "0"):
                try:
                    exit_px = float(v)
                    break
                except Exception:
                    pass

        # fees: пробуем несколько вариантов
        def _f(key: str) -> float:
            v = row.get(key)
            try:
                return float(v) if v not in (None, "") else 0.0
            except Exception:
                return 0.0

        fee_sum = (
            _f("cumEntryFee") + _f("cumExitFee")
            + _f("totalFee") + _f("fee")
        )

    # если записи closed-pnl ещё нет ИЛИ Bybit ещё не дал closedPnl — ставим pending и попробуем позже
    if pnl_closed is None:
        first = not getattr(tr, "pending_pnl_since", None)
        if first:
            tr.pending_pnl_since = now
            tg_trade(
                f"ℹ️ CLOSED {sym} {getattr(tr, 'side','')}\n"
                f"Realized PnL: (pending)\n"
                f"Reason: {getattr(tr, 'close_reason', '')}".strip()
            )
        tr.status = "PENDING_PNL"
        tr.exit_ts = now
        return

    # --- уточняем reason: TP/SL (если до этого был общий POSITION_GONE...)
    try:
        tick = float(_get_meta(sym).get("tickSize") or 0.000001)
        eps = tick * 2

        cur_reason = (getattr(tr, "close_reason", "") or "").strip()
        can_override = (cur_reason == "") or ("POSITION_GONE" in cur_reason)

        if can_override and exit_px is not None:
            tp = getattr(tr, "tp_price", None)
            sl = getattr(tr, "sl_price", None)
            side = getattr(tr, "side", None)

            if side == "Buy":
                if tp is not None and exit_px >= float(tp) - eps:
                    tr.close_reason = "TP"
                elif sl is not None and exit_px <= float(sl) + eps:
                    tr.close_reason = "SL"
            elif side == "Sell":
                if tp is not None and exit_px <= float(tp) + eps:
                    tr.close_reason = "TP"
                elif sl is not None and exit_px >= float(sl) - eps:
                    tr.close_reason = "SL"
    except Exception as e:
        log_error(f"reason classify fail {sym}: {e}")

    try:
        tr.exit_source = str(getattr(tr, "close_reason", "") or "UNKNOWN")
    except Exception:
        pass

    # --- fees fallback: если Bybit не отдал нормальные fee-поля (часто бывает)
    if fee_sum is None:
        fee_sum = 0.0

    if abs(float(fee_sum)) < 1e-12:
        try:
            fees = 0.0
            entry_oid = getattr(tr, "entry_order_id", None)
            if entry_oid:
                for e in TRADE_CLIENT.get_executions(sym, entry_oid, limit=50):
                    v = e.get("execFee")
                    if v not in (None, "", "0"):
                        try:
                            fees += float(v)
                        except Exception:
                            pass
            if fees > 0:
                fee_sum = fees
        except Exception as e:
            log_error(f"fees fallback fail {sym}: {e}")

    # есть pnl — финальный статус
    tr.status = "CLOSED"
    tr.exit_ts = now

    msg = f"✅ CLOSED {sym} {getattr(tr, 'side', '')}".strip()
    msg += f"\nRealized PnL: {pnl_closed:+.4f} USDT"
    if fee_sum is not None:
        msg += f"\nFees: {float(fee_sum):.4f} USDT"
    if exit_px is not None:
        msg += f"\nExit px: {exit_px:.6f}"
    if getattr(tr, "close_reason", None):
        msg += f"\nReason: {tr.close_reason}"
    hold_txt = []
    fill_ts = int(getattr(tr, "entry_fill_ts", 0) or 0)
    exit_ts = int(now)
    if fill_ts > 0 and exit_ts >= fill_ts:
        hold_txt.append(f"hold={exit_ts - fill_ts}s")
    send_ts = int(getattr(tr, "order_send_ts", 0) or 0)
    if send_ts > 0 and fill_ts > 0 and fill_ts >= send_ts:
        hold_txt.append(f"send→fill={fill_ts - send_ts}s")
    if fill_ts > 0 and exit_ts >= fill_ts:
        hold_txt.append(f"fill→close={exit_ts - fill_ts}s")
    if hold_txt:
        msg += "\nTiming: " + " | ".join(hold_txt)
    tg_trade(msg)
    _db_log_event("CLOSE", tr, sym, pnl=pnl_closed, fees=fee_sum, exit_px=exit_px)
    _db_log_ml_close(tr, sym, pnl=pnl_closed, fees=fee_sum)
    # Cooldown after breakout SL to reduce repeated entries in noisy chop.
    try:
        if str(getattr(tr, "strategy", "")) == "inplay_breakout":
            reason = str(getattr(tr, "close_reason", "") or "").upper()
            if ("SL" in reason) and int(BREAKOUT_SL_COOLDOWN_SEC) > 0:
                _BREAKOUT_COOLDOWN_UNTIL[str(sym).upper()] = int(now) + int(BREAKOUT_SL_COOLDOWN_SEC)
    except Exception as e:
        log_error(f"breakout cooldown set fail {sym}: {e}")
    if TRADE_CHARTS_SEND_ON_CLOSE:
        p = _make_trade_chart(sym, tr, stage="close", pnl=pnl_closed, exit_px=exit_px)
        if p:
            tg_send_photo(p, caption=f"close chart {sym} [{getattr(tr, 'strategy', '')}] pnl={pnl_closed:+.4f}")

def set_tp_sl_retry(symbol: str, side: str, tp: Optional[float], sl: Optional[float]) -> bool:
    if DRY_RUN or TRADE_CLIENT is None:
        return False
    if not ALWAYS_SET_TPSL_ON_EXCHANGE:
        return False

    tr = get_trade("Bybit", symbol)
    entry_ref = None
    if tr is not None:
        try:
            entry_ref = float(getattr(tr, "avg", 0.0) or getattr(tr, "entry_price", 0.0) or 0.0) or None
        except Exception:
            entry_ref = None

    tp_send, sl_send, invalid_reason = _prepare_exchange_tpsl(symbol, side, tp, sl, entry_ref=entry_ref)
    if invalid_reason:
        log_error(f"TP/SL invariant reject {symbol}: {invalid_reason}")
        return False
    if tp_send is None and sl_send is None:
        log_error(f"TP/SL invariant reject {symbol}: nothing valid to send (tp={tp}, sl={sl})")
        return False

    for i in range(1, TPSL_RETRY_ATTEMPTS + 1):
        try:
            TRADE_CLIENT.set_tp_sl(symbol, side, tp_send, sl_send)
            return True

        except Exception as e:
            txt = str(e).lower()

            # ✅ 34040 not modified = УСПЕХ
            if ("34040" in txt) or ("not modified" in txt):
                return True

            # 🟦 10001 zero position = позиции уже нет (не ретраим, не пугаем)
            if ("10001" in txt) or ("zero position" in txt):
                log_error(f"TP/SL skip (zero position) {symbol}: {e}")
                return False

            log_error(f"set_tp_sl_retry fail {symbol} try={i}: {e}")
            if i == TPSL_RETRY_ATTEMPTS:
                tg_trade(f"⚠️ TP/SL set FAIL {symbol}: {e}")
                return False

            time.sleep(TPSL_RETRY_DELAY_SEC * i)

    return False


def max_notional_allowed(equity: float) -> float:
    """
    Максимальный notional (в USDT), который разрешаем брать *на одну позицию*.

    Логика:
      - CAP_NOTIONAL_TO_EQUITY=True  => базовый лимит = equity
      - CAP_NOTIONAL_TO_EQUITY=False => базовый лимит = equity * leverage
      - затем вычитаем резерв (RESERVE_EQUITY_FRAC)
      - затем делим на MAX_POSITIONS (чтобы суммарно не раздать весь лимит на 1 сделку)
    """
    if equity <= 0:
        return 0.0
    cap_total = equity if CAP_NOTIONAL_TO_EQUITY else (equity * BYBIT_LEVERAGE)
    cap_total *= (1.0 - RESERVE_EQUITY_FRAC)
    per_trade = cap_total
    try:
        if int(MAX_POSITIONS) > 1:
            per_trade = cap_total / float(int(MAX_POSITIONS))
    except Exception:
        pass
    return max(0.0, float(per_trade))


def _manage_inplay_runner(symbol: str, tr: TradeState, price: float):
    if TRADE_CLIENT is None:
        return
    now = now_s()
    if now - int(getattr(tr, "last_runner_action_ts", 0) or 0) < 2:
        return

    side = tr.side
    if side not in ("Buy", "Sell"):
        return

    if side == "Buy":
        tr.hh = price if tr.hh is None else max(tr.hh, price)
    else:
        tr.ll = price if tr.ll is None else min(tr.ll, price)

    if tr.time_stop_sec and tr.entry_ts:
        if now - int(tr.entry_ts) >= int(tr.time_stop_sec):
            qty = float(tr.remaining_qty or tr.qty or 0.0)
            if qty > 0:
                TRADE_CLIENT.close_market(symbol, side, qty)
                tr.close_reason = "TIME_STOP"
                tr.last_runner_action_ts = now
                tg_trade(f"🟧 INPLAY TIME STOP {symbol}: closed qty≈{qty}")
            return

    risk = 0.0
    if tr.entry_price and tr.initial_sl_price:
        risk = abs(float(tr.entry_price) - float(tr.initial_sl_price))

    if tr.be_trigger_rr and tr.be_trigger_rr > 0 and (not tr.be_armed) and risk > 0:
        if side == "Buy":
            be_hit = price >= (float(tr.entry_price) + float(tr.be_trigger_rr) * risk)
            be_sl = float(tr.entry_price) + float(tr.be_lock_rr or 0.0) * risk
            better = tr.sl_price is None or be_sl > float(tr.sl_price)
        else:
            be_hit = price <= (float(tr.entry_price) - float(tr.be_trigger_rr) * risk)
            be_sl = float(tr.entry_price) - float(tr.be_lock_rr or 0.0) * risk
            better = tr.sl_price is None or be_sl < float(tr.sl_price)
        if be_hit and better:
            tr.sl_price = float(be_sl)
            ok = set_tp_sl_retry(symbol, side, None, tr.sl_price)
            if ok:
                tr.tpsl_last_set_ts = now_s()
                tr.last_runner_action_ts = now
            tr.be_armed = True

    if tr.tps and tr.tp_fracs and tr.tp_hit:
        for i, tp in enumerate(tr.tps):
            if i >= len(tr.tp_hit) or tr.tp_hit[i]:
                continue
            hit = (price >= tp) if side == "Buy" else (price <= tp)
            if not hit:
                continue
            qty_target = float(tr.initial_qty) * float(tr.tp_fracs[i])
            qty_left = float(tr.remaining_qty or tr.qty or 0.0)
            qty_to_close = min(qty_target, qty_left)
            if qty_to_close <= 0:
                tr.tp_hit[i] = True
                continue
            TRADE_CLIENT.close_market(symbol, side, qty_to_close)
            tr.remaining_qty = max(0.0, qty_left - qty_to_close)
            tr.tp_hit[i] = True
            tr.last_runner_action_ts = now
            tg_trade(f"🟩 INPLAY TP{i+1} {symbol}: closed≈{qty_to_close}")

    trail_ready = bool((tr.trail_activate_rr or 0.0) <= 0.0 or tr.trail_armed)
    if (not trail_ready) and tr.trail_mult and tr.trail_mult > 0 and risk > 0:
        if side == "Buy":
            trail_hit = price >= (float(tr.entry_price) + float(tr.trail_activate_rr) * risk)
        else:
            trail_hit = price <= (float(tr.entry_price) - float(tr.trail_activate_rr) * risk)
        if trail_hit:
            tr.trail_armed = True

    if tr.trail_mult and tr.trail_mult > 0 and (((tr.trail_activate_rr or 0.0) <= 0.0) or tr.trail_armed):
        rows = fetch_klines(symbol, "5", max(5, tr.trail_period + 3))
        atr = _atr_abs_from_klines(rows, int(tr.trail_period))
        if atr > 0:
            if side == "Buy" and tr.hh is not None:
                new_sl = tr.hh - float(tr.trail_mult) * atr
                if tr.sl_price is None or new_sl > float(tr.sl_price):
                    tr.sl_price = float(new_sl)
                    ok = set_tp_sl_retry(symbol, side, None, tr.sl_price)
                    if ok:
                        tr.tpsl_last_set_ts = now_s()
                        tr.last_runner_action_ts = now
            elif side == "Sell" and tr.ll is not None:
                new_sl = tr.ll + float(tr.trail_mult) * atr
                if tr.sl_price is None or new_sl < float(tr.sl_price):
                    tr.sl_price = float(new_sl)
                    ok = set_tp_sl_retry(symbol, side, None, tr.sl_price)
                    if ok:
                        tr.tpsl_last_set_ts = now_s()
                        tr.last_runner_action_ts = now

def calc_notional_usd_from_stop_pct(stop_pct: float, risk_mult: float = 1.0) -> float:
    """
    Риск-модель:
      risk_usd = equity * RISK_PER_TRADE_PCT
      notional = risk_usd / (stop_pct/100)
    Затем cap по max_notional_allowed().
    Если notional < MIN_NOTIONAL_USD -> 0 (пропуск).
    """
    if stop_pct is None or stop_pct <= 0:
        return 0.0

    equity = float(_get_effective_equity() or 0.0)
    if equity <= 0:
        return 0.0

    mult = max(0.1, float(risk_mult or 1.0))
    risk_usd = equity * (RISK_PER_TRADE_PCT / 100.0) * mult

    notional_raw = risk_usd / (stop_pct / 100.0)
    notional = min(notional_raw, max_notional_allowed(equity))

    fill = notional / notional_raw if notional_raw > 0 else 0.0
    if fill < MIN_NOTIONAL_FILL_FRAC:
        return 0.0


    if notional < MIN_NOTIONAL_USD:
        return 0.0

    return float(notional)


def breakout_quality_score(
    *,
    chase_pct: float,
    late_pct: float,
    spread_pct: float,
    pullback_pct: float,
) -> float:
    chase_cap = max(0.01, float(BREAKOUT_MAX_CHASE_PCT or 0.01))
    late_cap = max(0.01, float(BREAKOUT_MAX_LATE_VS_REF_PCT or 0.01))
    spread_cap = max(0.01, float(BREAKOUT_MAX_SPREAD_PCT or 0.01))
    pull_thr = max(0.01, float(BREAKOUT_MIN_PULLBACK_FROM_EXTREME_PCT or 0.01))

    chase_score = max(0.0, min(1.0, 1.0 - (max(0.0, chase_pct) / chase_cap)))
    late_score = max(0.0, min(1.0, 1.0 - (max(0.0, late_pct) / late_cap)))
    spread_score = max(0.0, min(1.0, 1.0 - (max(0.0, spread_pct) / spread_cap)))
    pull_score = max(0.0, min(1.0, max(0.0, pullback_pct) / (pull_thr * 1.8)))

    return (
        0.30 * spread_score
        + 0.25 * chase_score
        + 0.25 * late_score
        + 0.20 * pull_score
    )


def breakout_sizeup_multiplier_from_score(score: float) -> float:
    if not BREAKOUT_SIZEUP_ENABLE or BREAKOUT_SIZEUP_MAX_MULT <= 1.0:
        return 1.0
    if score < BREAKOUT_SIZEUP_MIN_SCORE:
        return 1.0

    stretch = (score - BREAKOUT_SIZEUP_MIN_SCORE) / max(1e-9, (1.0 - BREAKOUT_SIZEUP_MIN_SCORE))
    stretch = max(0.0, min(1.0, stretch))
    return 1.0 + (BREAKOUT_SIZEUP_MAX_MULT - 1.0) * stretch


def breakout_quality_boost_multiplier(score: float) -> float:
    """Extra risk/notional boost only for top-quality setups."""
    if not BREAKOUT_QUALITY_BOOST_ENABLE:
        return 1.0
    s1 = min(float(BREAKOUT_QUALITY_BOOST_SCORE_1), float(BREAKOUT_QUALITY_BOOST_SCORE_2))
    s2 = max(float(BREAKOUT_QUALITY_BOOST_SCORE_1), float(BREAKOUT_QUALITY_BOOST_SCORE_2))
    if score >= s2:
        return max(float(BREAKOUT_QUALITY_BOOST_MULT_1), float(BREAKOUT_QUALITY_BOOST_MULT_2))
    if score >= s1:
        return min(float(BREAKOUT_QUALITY_BOOST_MULT_1), float(BREAKOUT_QUALITY_BOOST_MULT_2))
    return 1.0

    

def ensure_open_positions_have_tpsl():
    """
    Страховка: раз в TPSL_ENSURE_EVERY_SEC секунд пробегаем TRADES
    и ставим TP/SL на бирже, если вдруг не поставились/бот перезапускался.
    """
    global _LAST_TPSL_ENSURE_TS
    if DRY_RUN or TRADE_CLIENT is None:
        return

    now = now_s()
    if now - _LAST_TPSL_ENSURE_TS < TPSL_ENSURE_EVERY_SEC:
        return
    _LAST_TPSL_ENSURE_TS = now

    for (exch, sym), tr in list(TRADES.items()):
        if exch != "Bybit":
            continue
        if getattr(tr, "status", "OPEN") != "OPEN":
            continue
        if getattr(tr, "close_requested", False):
            continue

        if tr.qty <= 0 or not tr.avg:
            continue
        # если TP/SL вручную изменены на бирже — не перезатираем
        if RESPECT_MANUAL_TPSL and getattr(tr, "tpsl_manual_lock", False):
            continue

        # если tp/sl ещё не рассчитаны — посчитаем по % от средней
        if tr.tp_price is None or tr.sl_price is None:
            avg = float(tr.avg)

            if tr.side == "Sell":
                tp_raw = avg * (1.0 - TP_PCT / 100.0)
                sl_raw = avg * (1.0 + SL_PCT / 100.0)
            else:
                tp_raw = avg * (1.0 + TP_PCT / 100.0)
                sl_raw = avg * (1.0 - SL_PCT / 100.0)

            tp_r, sl_r = round_tp_sl_prices(sym, tr.side, avg, tp_raw, sl_raw)
            tr.tp_price = tp_r
            tr.sl_price = sl_r

        was_on = bool(getattr(tr, "tpsl_on_exchange", False))

        ok = set_tp_sl_retry(sym, tr.side, tr.tp_price, tr.sl_price)
        if ok:
            tr.tpsl_on_exchange = True
            tr.tpsl_last_set_ts = now_s()
            tr.tpsl_manual_lock = False

            # уведомляем только если раньше считали, что TP/SL на бирже НЕ было
            if not was_on:
                tg_trade(f"🧷 TP/SL ensured {sym}: TP={tr.tp_price:.6f} SL={tr.sl_price:.6f}")


def bootstrap_open_trades_from_exchange():
    """
    На старте восстанавливает открытые Bybit-позиции в локальный TRADES.
    Это нужно, чтобы pulse/sync/TP-SL управление не теряли позицию после рестарта.
    """
    if DRY_RUN or TRADE_CLIENT is None:
        return

    try:
        rows = TRADE_CLIENT.list_open_positions()
    except Exception as e:
        log_error(f"bootstrap positions fail: {e}")
        return

    restored = 0
    for row in rows:
        sym = str(row.get("symbol") or "").upper().strip()
        if not sym:
            continue
        key = ("Bybit", sym)
        if key in TRADES:
            continue

        try:
            qty = abs(float(row.get("size") or 0.0))
        except Exception:
            qty = 0.0
        if qty <= 0:
            continue

        side = str(row.get("side") or "Buy").strip() or "Buy"
        avg_raw = row.get("avgPrice")
        tp_raw = row.get("takeProfit")
        sl_raw = row.get("stopLoss")
        avg_ex = float(avg_raw) if avg_raw not in (None, "", "0") else 0.0
        tp_ex = float(tp_raw) if tp_raw not in (None, "", "0") else None
        sl_ex = float(sl_raw) if sl_raw not in (None, "", "0") else None

        ev = _get_last_open_entry_event(sym, side=side)
        strategy = str((ev or {}).get("strategy") or "bootstrap")
        entry_ts = int((ev or {}).get("entry_ts") or int(time.time()))
        entry_px = float((ev or {}).get("entry_price") or avg_ex or 0.0)
        tp_px = tp_ex if tp_ex is not None else (ev or {}).get("tp_price")
        sl_px = sl_ex if sl_ex is not None else (ev or {}).get("sl_price")

        tr = TradeState(symbol=sym, side=side, strategy=strategy)
        tr.qty = float(qty)
        tr.status = "OPEN"
        tr.entry_ts = entry_ts
        tr.entry_fill_ts = entry_ts
        tr.entry_confirm_sent = True
        tr.avg = float(avg_ex or entry_px or 0.0)
        tr.entry_price = float(avg_ex or entry_px or 0.0)
        tr.entry_price_req = float(entry_px or avg_ex or 0.0)
        tr.tp_price = float(tp_px) if tp_px not in (None, "") else None
        tr.sl_price = float(sl_px) if sl_px not in (None, "") else None
        tr.tpsl_on_exchange = bool(tp_ex is not None or sl_ex is not None)
        tr.tpsl_manual_lock = bool(tp_ex is not None or sl_ex is not None)
        tr.tpsl_last_set_ts = now_s()
        TRADES[key] = tr
        restored += 1

        tg_trade(
            f"🔁 RESTORED [{TRADE_CLIENT.name}] {sym} {side} qty={qty:.6f} "
            f"avg={float(tr.avg or 0.0):.6f} strategy={strategy}"
        )

    if restored > 0:
        tg_trade(f"🔁 Startup restore complete: restored_open_positions={restored}")

    reconcile_stale_db_entries_with_exchange(rows)


def ensure_leverage(symbol: str, lev: int = BYBIT_LEVERAGE):
    if TRADE_CLIENT is None:
        return
    TRADE_CLIENT.ensure_leverage(symbol, lev)

# =========================== ORDER BOOK ANALYZER ===========================
class OrderBookAnalyzer:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def get_sell_pressure(self, symbol: str) -> float:
        try:
            j = requests.get(
                f"{self.base_url}/v5/market/orderbook",
                params={"category":"linear","symbol":symbol,"limit":50},
                timeout=3
            ).json()
            if str(j.get("retCode")) != "0":
                return 0.5
            asks = j["result"].get("a", [])
            bids = j["result"].get("b", [])
            total_asks = 0.0
            total_bids = 0.0
            for a in asks:
                total_asks += float(a[1])
            for b in bids:
                total_bids += float(b[1])
            if total_asks + total_bids == 0:
                return 0.5
            return total_asks / (total_asks + total_bids)
        except Exception:
            return 0.5

    def get_spread_pct(self, symbol: str) -> float:
        try:
            j = requests.get(
                f"{self.base_url}/v5/market/orderbook",
                params={"category":"linear","symbol":symbol,"limit":1},
                timeout=3
            ).json()
            if str(j.get("retCode")) != "0":
                return 0.0
            asks = j["result"].get("a", [])
            bids = j["result"].get("b", [])
            if not asks or not bids:
                return 0.0
            best_ask = float(asks[0][0])
            best_bid = float(bids[0][0])
            if best_ask <= 0 or best_bid <= 0:
                return 0.0
            mid = (best_ask + best_bid) / 2.0
            if mid <= 0:
                return 0.0
            return abs(best_ask - best_bid) / mid * 100.0
        except Exception:
            return 0.0

ORDERBOOK = OrderBookAnalyzer((TRADE_CLIENT.base if TRADE_CLIENT else BYBIT_BASE_DEFAULT))
_OB_CACHE = {}   # symbol -> (ts, value)
OB_TTL_SEC = 2   # не дергать стакан чаще чем раз в 2 секунды на символ

def get_sell_pressure_cached(symbol: str) -> float:
    now = now_s()
    v = _OB_CACHE.get(symbol)
    if v and (now - v[0] <= OB_TTL_SEC):
        return v[1]
    val = ORDERBOOK.get_sell_pressure(symbol)
    _OB_CACHE[symbol] = (now, val)
    return val

def get_spread_pct_cached(symbol: str) -> float:
    now = now_s()
    v = _OB_CACHE.get(("spread", symbol))
    if v and (now - v[0] <= OB_TTL_SEC):
        return v[1]
    val = ORDERBOOK.get_spread_pct(symbol)
    _OB_CACHE[("spread", symbol)] = (now, val)
    return val

BASE_URL_PUBLIC = (TRADE_CLIENT.base if TRADE_CLIENT else BYBIT_BASE_DEFAULT)

LEVELS_SVC = LevelsService(base_url=BASE_URL_PUBLIC, ttl_sec=900)
BOUNCE_STRAT = BounceStrategy(base_url=BASE_URL_PUBLIC, levels=LEVELS_SVC)
BOUNCE_STRAT.breakout_risk_max = BOUNCE_MAX_BREAKOUT_RISK


# =========================== RANGE (1h range + 5m confirmation) ===========================
RANGE_REGISTRY = RangeRegistry()

RANGE_SCANNER = RangeScanner(
    fetch_klines=fetch_klines_for_range,

    registry=RANGE_REGISTRY,
    interval_1h=RANGE_SCAN_TF,
    lookback_h=RANGE_LOOKBACK_H,
    rescan_ttl_sec=RANGE_RESCAN_SEC,
    min_range_pct=MIN_RANGE_PCT,
    max_range_pct=MAX_RANGE_PCT,
    min_touches=RANGE_MIN_TOUCHES,
)

RANGE_STRATEGY = RangeStrategy(
    fetch_klines=fetch_klines_for_range,
    registry=RANGE_REGISTRY,
    confirm_tf=RANGE_CONFIRM_TF,
    confirm_limit=RANGE_CONFIRM_LIMIT,
    atr_period=RANGE_ATR_PERIOD,
    entry_zone_frac=RANGE_ENTRY_ZONE_FRAC,
    sweep_frac=RANGE_SWEEP_FRAC,
    reclaim_frac=RANGE_RECLAIM_FRAC,
    wick_frac_min=RANGE_WICK_FRAC_MIN,
    require_prev_sweep=RANGE_REQUIRE_PREV_SWEEP,
    impulse_body_atr_max=RANGE_IMPULSE_BODY_ATR_MAX,
    adaptive_regime=RANGE_ADAPTIVE_REGIME,
    regime_low_atr_pct=RANGE_REGIME_LOW_ATR_PCT,
    regime_high_atr_pct=RANGE_REGIME_HIGH_ATR_PCT,
    impulse_body_atr_max_low=RANGE_IMPULSE_BODY_ATR_MAX_LOW,
    impulse_body_atr_max_high=RANGE_IMPULSE_BODY_ATR_MAX_HIGH,
    min_rr_low=RANGE_MIN_RR_LOW,
    min_rr_high=RANGE_MIN_RR_HIGH,
    adaptive_tp=RANGE_ADAPTIVE_TP,
    tp_frac_low=RANGE_TP_FRAC_LOW,
    tp_frac_high=RANGE_TP_FRAC_HIGH,
    tp_mode=RANGE_TP_MODE,
    min_rr=RANGE_MIN_RR,
    sl_width_frac=RANGE_SL_WIDTH_FRAC,
    sl_buffer_frac=RANGE_SL_BUFFER_FRAC,
    sl_atr_mult=RANGE_SL_ATR_MULT,
    allow_long=RANGE_ALLOW_LONG,
    allow_short=RANGE_ALLOW_SHORT,
)

# ===== SLOPED CHANNEL ENGINE =====
if ENABLE_SLOPED_TRADING:
    try:
        from strategies.sloped_channel_live import SlopedChannelLiveEngine
        SLOPED_ENGINE = SlopedChannelLiveEngine(fetch_klines)
        print("[SLOPED] engine initialised")
    except Exception as _e:
        log_error(f"[SLOPED] engine init fail: {_e}")
        SLOPED_ENGINE = None

# ===== FLAT RESISTANCE FADE ENGINE =====
if ENABLE_FLAT_TRADING:
    try:
        from strategies.flat_resistance_fade_live import FlatResistanceFadeLiveEngine
        FLAT_ENGINE = FlatResistanceFadeLiveEngine(fetch_klines)
        print("[FLAT] engine initialised")
    except Exception as _e:
        log_error(f"[FLAT] engine init fail: {_e}")
        FLAT_ENGINE = None

# ===== BREAKDOWN SHORTS ENGINE =====
if ENABLE_BREAKDOWN_TRADING:
    try:
        BREAKDOWN_ENGINE = BreakdownLiveEngine(fetch_klines)
        print("[BREAKDOWN] engine initialised")
    except Exception as _e:
        log_error(f"[BREAKDOWN] engine init fail: {_e}")
        BREAKDOWN_ENGINE = None


_ENGINE_LAZY_INIT_FAIL_TS: Dict[str, int] = {}


def _log_engine_lazy_init_fail(tag: str, err: Exception) -> None:
    now = now_s()
    last = int(_ENGINE_LAZY_INIT_FAIL_TS.get(tag, 0) or 0)
    if now - last < 300:
        return
    _ENGINE_LAZY_INIT_FAIL_TS[tag] = now
    log_error(f"[{tag}] engine lazy-init fail: {err}\n{traceback.format_exc()}")


def _ensure_sloped_engine() -> bool:
    global SLOPED_ENGINE
    if SLOPED_ENGINE is not None:
        return True
    if not ENABLE_SLOPED_TRADING:
        return False
    try:
        from strategies.sloped_channel_live import SlopedChannelLiveEngine
        SLOPED_ENGINE = SlopedChannelLiveEngine(fetch_klines)
        print("[SLOPED] engine lazy-init ok")
        return True
    except Exception as e:
        SLOPED_ENGINE = None
        _log_engine_lazy_init_fail("SLOPED", e)
        return False


def _ensure_flat_engine() -> bool:
    global FLAT_ENGINE
    if FLAT_ENGINE is not None:
        return True
    if not ENABLE_FLAT_TRADING:
        return False
    try:
        from strategies.flat_resistance_fade_live import FlatResistanceFadeLiveEngine
        FLAT_ENGINE = FlatResistanceFadeLiveEngine(fetch_klines)
        print("[FLAT] engine lazy-init ok")
        return True
    except Exception as e:
        FLAT_ENGINE = None
        _log_engine_lazy_init_fail("FLAT", e)
        return False


def _ensure_breakdown_engine() -> bool:
    global BREAKDOWN_ENGINE
    if BREAKDOWN_ENGINE is not None:
        return True
    if not ENABLE_BREAKDOWN_TRADING:
        return False
    try:
        BREAKDOWN_ENGINE = BreakdownLiveEngine(fetch_klines)
        print("[BREAKDOWN] engine lazy-init ok")
        return True
    except Exception as e:
        BREAKDOWN_ENGINE = None
        _log_engine_lazy_init_fail("BREAKDOWN", e)
        return False

# ===== MICRO SCALPER ENGINE =====
if ENABLE_MICRO_SCALPER_TRADING:
    try:
        MICRO_SCALPER_ENGINE = MicroScalperLiveEngine(fetch_klines)
        print("[MICRO_SCALPER] engine initialised")
    except Exception as _e:
        log_error(f"[MICRO_SCALPER] engine init fail: {_e}")
        MICRO_SCALPER_ENGINE = None

# ===== SUPPORT RECLAIM LONGS ENGINE =====
if ENABLE_SUPPORT_RECLAIM_TRADING:
    try:
        SUPPORT_RECLAIM_ENGINE = SupportReclaimLiveEngine(fetch_klines)
        print("[SUPPORT_RECLAIM] engine initialised")
    except Exception as _e:
        log_error(f"[SUPPORT_RECLAIM] engine init fail: {_e}")
        SUPPORT_RECLAIM_ENGINE = None

# ===== TRIPLE SCREEN v132 ENGINE =====
if ENABLE_TS132_TRADING:
    try:
        from archive.strategies_retired.triple_screen_v132 import TripleScreenV132Strategy
        TS132_ENGINE = {}  # symbol -> TripleScreenV132Strategy
        print("[TS132] engine initialised (per-symbol lazy)")
    except Exception as _e:
        log_error(f"[TS132] engine init fail: {_e}")
        TS132_ENGINE = None


# пример "короткого" bounce под маленький депозит
BOUNCE_STRAT.sl_pct = 0.35     # стоп ~0.35%
BOUNCE_STRAT.rr     = 1.3      # TP ~0.455%
BOUNCE_STRAT.min_potential_pct = 0.30

BOUNCE_STRAT.min_body_pct = 10.0
BOUNCE_STRAT.max_level_dist_pct = BOUNCE_MAX_DIST_PCT
BOUNCE_STRAT.breakout_risk_max = BOUNCE_MAX_BREAKOUT_RISK
BOUNCE_STRAT.min_potential_pct = BOUNCE_MIN_POTENTIAL_PCT

BOUNCE_MAX_ENTRIES_PER_HOUR = 2
BOUNCE_ENTRY_TS = collections.deque(maxlen=50)  # timestamps последних входов bounce
ENABLE_BOUNCE = True
BOUNCE_TRY_EVERY_SEC = 30  # как часто пытаться искать отскок на символ
BOUNCE_STRAT.check_cooldown_sec = BOUNCE_TRY_EVERY_SEC


EQUITY_CACHE = {"val": None, "ts": 0}
EQUITY_TTL_SEC = 25

# =========================== ПОРТФЕЛЬНЫЙ МЕНЕДЖЕР ===========================
def _fetch_equity_live() -> Optional[float]:
    if TRADE_CLIENT is None:
        return None

    # ── AUTH FLOOD FIX ──────────────────────────────────────────────────────
    # If auth is disabled (cooldown after failure), return None *silently*.
    # The caller (_get_equity_now) will use the cached value instead.
    # This prevents errors.log from being flooded with hundreds of
    # "equity fetch fail: AUTH_DISABLED" lines after a single auth expiry.
    acct_name = getattr(TRADE_CLIENT, "name", TRADE_ACCOUNT_NAME)
    if auth_disabled(acct_name):
        return None
    # ────────────────────────────────────────────────────────────────────────

    try:
        wb = TRADE_CLIENT.wallet_balance()
        lst = (wb.get("result") or {}).get("list") or []
        if not lst:
            return None

        row0 = lst[0] or {}
        # Bybit unified отдаёт totalEquity прямо тут
        v = row0.get("totalEquity")
        if v not in (None, "", "0"):
            return float(v)

        return None

    except Exception as e:
        # Логируем только если auth ещё не задизаблен — иначе flood
        if not auth_disabled(acct_name):
            log_error(f"equity fetch fail: {e}")
        return None


def _get_equity_now() -> float:
    # DRY_RUN / no client
    if DRY_RUN or TRADE_CLIENT is None:
        if PORTFOLIO_STATE["start_equity"] is None:
            dry_eq = os.getenv("DRY_RUN_EQUITY", "1000").strip()
            try:
                PORTFOLIO_STATE["start_equity"] = float(dry_eq)
            except Exception:
                PORTFOLIO_STATE["start_equity"] = 1000.0
        return float(PORTFOLIO_STATE["start_equity"] or 0.0)

    now = now_s()

    # кэш
    if EQUITY_CACHE["val"] is not None and (now - int(EQUITY_CACHE["ts"] or 0) <= EQUITY_TTL_SEC):
        return float(EQUITY_CACHE["val"])

    eq = _fetch_equity_live()

    # если не смогли получить equity — вернём последнее известное
    if eq is None:
        if EQUITY_CACHE["val"] is not None:
            return float(EQUITY_CACHE["val"])
        return 0.0

    EQUITY_CACHE["val"] = float(eq)
    EQUITY_CACHE["ts"] = now
    return float(eq)

def _get_effective_equity() -> float:
    eq = float(_get_equity_now() or 0.0)
    cap = BOT_CAPITAL_USD
    try:
        if cap is not None:
            cap = float(cap)
            if cap > 0:
                return min(eq, cap)
    except Exception:
        pass
    return eq


BASE_RISK_PCT = 0.004  # 0.4% от депо, можно 0.003

def calc_leg_usd_half_equity() -> float:
    equity = float(_get_effective_equity() or 0.0)
    if equity <= 0:
        return 0.0
    planned = (equity * 0.5) * BYBIT_LEVERAGE
    planned *= (1.0 - RESERVE_EQUITY_FRAC)
    leg = max(MIN_LEG_USD, min(planned, MAX_LEG_USD))
    return max(0.0, leg)

def calc_position_usd(signal_score: int, atr_value: Optional[float]) -> float:
    equity = float(_get_effective_equity() or 0.0)
    if equity <= 0:
        return 0.0
    strength = min(max(signal_score / 5.0, 0.2), 1.0)
    vol_k = 1.0
    if atr_value is not None and atr_value > 0:
        vol_k = 1.0 / max(0.6, atr_value / 0.12)
    usd = equity * BASE_RISK_PCT * strength * vol_k
    return max(MIN_NOTIONAL_USD, min(usd, equity * 0.02))
     

def portfolio_init_if_needed():
    today = _today_ymd()
    if PORTFOLIO_STATE["start_equity"] is None:
        eq = _get_effective_equity()
        PORTFOLIO_STATE["start_equity"] = eq
        PORTFOLIO_STATE["day_equity_start"] = eq
        PORTFOLIO_STATE["day"] = today
        PORTFOLIO_STATE["daily_pnl_usd"] = 0.0
        PORTFOLIO_STATE["disabled"] = False
        
    elif PORTFOLIO_STATE["day"] != today:
        eq = _get_effective_equity()
        PORTFOLIO_STATE["day"] = today
        PORTFOLIO_STATE["day_equity_start"] = eq
        PORTFOLIO_STATE["daily_pnl_usd"] = 0.0
        PORTFOLIO_STATE["disabled"] = False

def portfolio_can_open() -> bool:
    portfolio_init_if_needed()
    if PORTFOLIO_STATE["disabled"]:
        return False
    open_pos = len(TRADES)
    if open_pos >= MAX_POSITIONS:
        return False
    eq_start = PORTFOLIO_STATE["start_equity"]
    eq_day = PORTFOLIO_STATE["day_equity_start"]
    cur_eq = _get_effective_equity()
    if eq_start and cur_eq < eq_start * (1 - MAX_DRAWDOWN_PCT/100.0):
        PORTFOLIO_STATE["disabled"] = True
        return False
    if eq_day and cur_eq < eq_day * (1 - DAILY_LOSS_LIMIT_PCT/100.0):
        PORTFOLIO_STATE["disabled"] = True
        return False
    return True


def _trade_open_risk_usd(tr: TradeState) -> float:
    try:
        status = str(getattr(tr, "status", "") or "").upper()
        if status in {"CLOSED", "FAILED", "CANCELLED", "ERROR"}:
            return 0.0
        qty = float(getattr(tr, "remaining_qty", 0.0) or getattr(tr, "qty", 0.0) or 0.0)
        entry = float(
            getattr(tr, "entry_price", 0.0)
            or getattr(tr, "avg", 0.0)
            or getattr(tr, "entry_price_req", 0.0)
            or 0.0
        )
        sl = float(getattr(tr, "sl_price", 0.0) or 0.0)
        if qty <= 0 or entry <= 0 or sl <= 0:
            return 0.0
        return max(0.0, qty * abs(entry - sl))
    except Exception:
        return 0.0


def current_open_portfolio_risk_usd() -> float:
    total = 0.0
    for tr in TRADES.values():
        total += _trade_open_risk_usd(tr)
    return max(0.0, float(total))


def portfolio_can_add_open_risk(additional_risk_usd: float = 0.0) -> tuple[bool, float, float]:
    cap_pct = float(MAX_OPEN_PORTFOLIO_RISK_PCT or 0.0)
    if cap_pct <= 0:
        return True, 0.0, 0.0
    eq = float(_get_effective_equity() or 0.0)
    if eq <= 0:
        return False, 0.0, cap_pct
    total_usd = current_open_portfolio_risk_usd() + max(0.0, float(additional_risk_usd or 0.0))
    total_pct = (total_usd / max(1e-12, eq)) * 100.0
    return total_pct <= cap_pct + 1e-9, total_pct, cap_pct

def portfolio_reg_pnl(notional_usd: float, pnl_pct: float):
    portfolio_init_if_needed()
    pnl_usd = notional_usd * (pnl_pct / 100.0)
    PORTFOLIO_STATE["daily_pnl_usd"] += pnl_usd
    eq = _get_effective_equity()
    if PORTFOLIO_STATE["day_equity_start"] and eq < PORTFOLIO_STATE["day_equity_start"] * (1 - DAILY_LOSS_LIMIT_PCT/100.0):
        PORTFOLIO_STATE["disabled"] = True

TRADES: Dict[Tuple[str,str], TradeState] = {}
_SYMBOL_ENTRY_LOCKS: Dict[Tuple[str, str], asyncio.Lock] = {}


def _entry_lock_key(exch: str, sym: str) -> Tuple[str, str]:
    return (str(exch or "").strip(), str(sym or "").upper().strip())


def _get_symbol_entry_lock(exch: str, sym: str) -> asyncio.Lock:
    key = _entry_lock_key(exch, sym)
    lock = _SYMBOL_ENTRY_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _SYMBOL_ENTRY_LOCKS[key] = lock
    return lock

def _update_avg(avg: float, q_old: float, px_new: float, q_new: float) -> float:
    if q_old <= 0:
        return px_new
    return (avg*q_old + px_new*q_new) / (q_old + q_new)

def get_trade(exch:str, sym:str) -> Optional[TradeState]:
    return TRADES.get((exch, sym))

def place_market(symbol: str, side: str, usd_amount: float) -> Tuple[str, float]:
    st = S("Bybit", symbol)
    price = st.prices[-1][1] if len(st.prices) else None
    base_url = (TRADE_CLIENT.base if TRADE_CLIENT else BYBIT_BASE_DEFAULT)

    if not price:
        j = requests.get(
            f"{base_url}/v5/market/tickers",
            params={"category":"linear","symbol":symbol},
            timeout=10
        ).json()
        price = float(j["result"]["list"][0]["lastPrice"])
    # гарантируем минимальный номинал ордера
    usd_amount = max(usd_amount, MIN_NOTIONAL_USD)

    # гарантируем минимальный номинал ордера ТОЛЬКО для pump-стратегии.
    # Для bounce мы шлём qty напрямую (TRADE_CLIENT.place_market), поэтому сюда не попадаем.
    usd_amount = float(usd_amount)
    if usd_amount < MIN_NOTIONAL_USD:
        tg_trade(f"🟡 SKIP {symbol}: usd_amount {usd_amount:.2f} < MIN_NOTIONAL_USD {MIN_NOTIONAL_USD:.2f}")
        return f"SKIP-{symbol}-{int(time.time())}", 0.0

    # ← ВСЕГДА считаем qty после того как price получена
    qty_raw = usd_amount / price
    qty = strict_round_qty(symbol, qty_raw)

    ensure_leverage(symbol, BYBIT_LEVERAGE)

    if TRADE_CLIENT is None:
        fake_id = f"NOKEY-{symbol}-{int(time.time())}"
        tg_trade(f"🟡 нет TRADE_CLIENT, сделка не открыта: {side} {symbol} {usd_amount}$")
        return fake_id, qty

    if symbol in ("4USDT", "1000BONKUSDT", "JELLYJELLYUSDT"):
        meta = _get_meta(symbol)
        tg_trade(f"🔎 {symbol} try: qty={qty} step={meta.get('qtyStep')} min={meta.get('minOrderQty')}")

    return TRADE_CLIENT.place_market(symbol, side, qty)

def close_market(symbol: str, side: str, qty: float):
    if TRADE_CLIENT is None:
        return
    q = floor_qty_no_min(symbol, float(qty))
    if q <= 0:
        log_error(f"close_market skip {symbol}: qty too small after floor ({qty})")
        return
    TRADE_CLIENT.close_market(symbol, side, q)


# =========================== МОДУЛИ РАЗВОРОТА ===========================
class ExhaustionAnalyzer:
    def analyze(self, st, peak_price: float, cur_price: float,
                buys2: float, sells2: float, q_total: float, base_med: float) -> dict:
        vol_exhaust = q_total < base_med * 1.3
        below_mid = False
        if st.last_pump:
            mid = (peak_price + st.last_pump["base"]) / 2.0
            below_mid = (cur_price <= mid)
        sell_pressure = 0.0
        if (buys2 + sells2) > 0:
            sell_pressure = sells2 / (buys2 + sells2)
        drop_pct = (peak_price - cur_price) / max(1e-9, peak_price) * 100.0
        score = 0
        if vol_exhaust: score += 1
        if below_mid: score += 1
        if sell_pressure >= 0.60: score += 1
        if drop_pct >= 0.4: score += 1
        return {
            "vol_exhaust": vol_exhaust,
            "below_mid": below_mid,
            "sell_pressure": sell_pressure,
            "drop_pct": drop_pct,
            "score": score
        }

class EntryTrigger:
    def __init__(self, need_score=5):
        self.need_score = need_score

    def should_short(self, exhaust_data, ema_flip_ok, ob_pressure,
                     need_score=None, ob_threshold=None, sell_dom_ok=False) -> bool:
        need = self.need_score if need_score is None else need_score
        thr  = 0.45 if ob_threshold is None else ob_threshold
        if not ema_flip_ok:
            return False
        score_ok = (exhaust_data["score"] >= need)
        # стакан считаем валидным только вместе с доминацией продаж в самой второй половине окна
        ob_ok    = (ob_pressure >= thr) and sell_dom_ok
        return score_ok or ob_ok


class PositionManager:
    def __init__(self, tp_pct, sl_pct, stall_bounce_pct, stall_min_sell_imb):
        self.tp_pct = tp_pct
        self.sl_pct = sl_pct
        self.stall_bounce_pct = stall_bounce_pct
        self.stall_min_sell_imb = stall_min_sell_imb
        self.acc_name = TRADE_CLIENT.name if TRADE_CLIENT else "NO_CLIENT"

    def manage(self, exch, sym, st, tr, p1, buys2, sells2):
        if not TRADE_ON or exch != "Bybit":
            return
        if TRADE_CLIENT is None:
            return
        if p1 is None or tr.qty <= 0:
            return
        if getattr(tr, "status", None) != "OPEN":
            return

        now = now_s()

        # --- Bounce strategy: TP/SL + time exit ---
        # --- Bounce strategy: TP/SL + time exit ---
        if getattr(tr, "strategy", "pump") in ("bounce", "range"):
            now = now_s()

            # если уже запросили закрытие — не спамим повторными close
            if getattr(tr, "close_requested", False):
                return

            hit_tp = False
            hit_sl = False

            if tr.tp_price is not None:
                if tr.side == "Buy" and p1 >= tr.tp_price:
                    hit_tp = True
                if tr.side == "Sell" and p1 <= tr.tp_price:
                    hit_tp = True

            if tr.sl_price is not None:
                if tr.side == "Buy" and p1 <= tr.sl_price:
                    hit_sl = True
                if tr.side == "Sell" and p1 >= tr.sl_price:
                    hit_sl = True

            max_hold = int(getattr(BOUNCE_STRAT, "max_hold_sec", 3600))
            hit_time = (now - int(tr.entry_ts or now)) >= max_hold

            if not (hit_tp or hit_sl or hit_time):
                return

            reason = "TP" if hit_tp else ("SL" if hit_sl else "TIME")

            # проверим фактический размер позиции на бирже
            try:
                size_now, side_now, _, _, _, _ = TRADE_CLIENT.get_position_summary(sym)
            except Exception as e:
                log_error(f"get_position_summary before close fail {sym}: {e}")
                return

            # если позиции уже нет — финализируем через closed-pnl (pending)
            if size_now <= 0:
                tr.close_reason = tr.close_reason or f"BOUNCE_{reason}_POSITION_GONE"
                _finalize_and_report_closed(tr, sym)
                # удаление из TRADES делает sync_trades_with_exchange(), когда status станет CLOSED
                return

            # ставим флаг закрытия и отправляем reduceOnly close по реальному size
            tr.close_requested = True
            tr.exit_req_ts = now
            tr.close_reason = tr.close_reason or f"BOUNCE_{reason}"

            try:
                close_market(sym, tr.side, float(size_now))
            except Exception as e:
                tr.close_requested = False  # дадим повторить позже
                log_error(f"close bounce fail {sym}: {e}")
                tg_trade(f"🛑 CLOSE FAIL {sym} bounce {reason}: {e}")
                return

            acc_name = TRADE_CLIENT.name if TRADE_CLIENT else "NO_CLIENT"
            tg_trade(f"🟣 CLOSE SENT [{acc_name}] {sym} bounce {reason} px={p1:.6f} size={size_now}")
            return

        # --- Pump-fade strategy: минимум (если у тебя есть своя логика — вставишь потом) ---
        # TP/SL по % от средней
        if tr.avg and tr.avg > 0:
            if tr.side == "Sell":
                tp_raw = tr.avg * (1.0 - TP_PCT / 100.0)
                sl_raw = tr.avg * (1.0 + SL_PCT / 100.0)
                tp_px, sl_px = round_tp_sl_prices(sym, tr.side, tr.avg, tp_raw, sl_raw)

EXHAUST_ANALYZER = ExhaustionAnalyzer()
ENTRY_TRIGGER = EntryTrigger(need_score=2)
POS_MANAGER = PositionManager(
    tp_pct=TP_PCT,
    sl_pct=SL_PCT,
    stall_bounce_pct=STALL_BOUNCE_PCT,
    stall_min_sell_imb=STALL_MIN_SELL_IMB
)

# =========================== ДЕТЕКТОР ===========================
def ctx_5m_move_pct(st: SymState, ts: int) -> Optional[float]:
    if not st.ctx5m: return None
    t0 = ts - CTX_5M_SEC
    p0 = None; p1 = st.ctx5m[-1][1]
    for t,p in st.ctx5m:
        if t >= t0:
            p0 = p; break
    if p0 is None or p0<=0: return None
    return (p1 - p0) / p0 * 100.0

def last_two_5m_bars(st: SymState, now: int):
    """
    Строим две последние 5-минутные "свечи" из ctx5m:
    prev (от -10 до -5 минут) и cur (от -5 минут до сейчас).
    bar = dict(open, high, low, close, range, body, up).
    """
    cur_start = now - 300        # последние 5 минут
    prev_start = now - 600       # 5 минут до них

    prev_prices = [p for (t, p) in st.ctx5m if prev_start <= t < cur_start]
    cur_prices  = [p for (t, p) in st.ctx5m if t >= cur_start]

    def make_bar(prices: List[float]):
        if len(prices) < 3:
            return None
        o = prices[0]
        c = prices[-1]
        h = max(prices)
        l = min(prices)
        rng = max(1e-9, h - l)
        body = abs(c - o)
        up = c > o
        return {
            "open": o,
            "close": c,
            "high": h,
            "low": l,
            "range": rng,
            "body": body,
            "up": up,
        }

    prev_bar = make_bar(prev_prices)
    cur_bar  = make_bar(cur_prices)
    return prev_bar, cur_bar

def breakout_ref_price(st: SymState, side: str, lookback_bars: int = 20) -> Optional[float]:
    bars = list(getattr(st, "bars5m", []) or [])
    lb = max(5, int(lookback_bars))
    if len(bars) < 3:
        return None
    seg = bars[-lb:]
    try:
        if str(side).lower() == "buy":
            return max(float(b.get("h", 0.0) or 0.0) for b in seg)
        return min(float(b.get("l", 0.0) or 0.0) for b in seg)
    except Exception:
        return None

def qty_floor_from_notional(symbol: str, notional_usd: float, price: float) -> tuple[float, float, str]:
    """
    notional_usd -> qty, округление ВНИЗ по qtyStep.
    НЕ поднимаем до minQty. Если minQty не достигается — возвращаем reason.
    """
    meta = _get_meta(symbol)
    min_qty = float(meta.get("minOrderQty") or 0.0)
    qty_step = float(meta.get("qtyStep") or 0.0) or 1.0

    qty_raw = float(notional_usd) / max(1e-12, float(price))

    d_step = Decimal(str(qty_step))
    q_floor_dec = (Decimal(str(qty_raw)) / d_step).to_integral_value(rounding=ROUND_DOWN) * d_step
    qty_floor = float(q_floor_dec)

    if qty_floor <= 0 or (min_qty and qty_floor < min_qty):
        return 0.0, 0.0, "BELOW_MIN_QTY"

    notional_real = qty_floor * float(price)

    cap = max_notional_allowed(_get_effective_equity())
    if CAP_NOTIONAL_TO_EQUITY and notional_real > cap + 1e-6:
        return 0.0, notional_real, "CAP_NOTIONAL_EXCEEDED"

    return qty_floor, notional_real, ""


def min_notional_for_min_qty(symbol: str, price: float) -> float:
    """Estimate minimum notional needed to satisfy exchange min qty after floor rounding."""
    meta = _get_meta(symbol)
    min_qty = float(meta.get("minOrderQty") or 0.0)
    qty_step = float(meta.get("qtyStep") or 0.0) or 1.0
    if min_qty <= 0:
        return 0.0
    # Ensure we ask at least one step above min_qty to survive floor operations.
    qty_target = max(min_qty, min_qty + qty_step)
    return float(qty_target) * max(1e-12, float(price))


def _ema_list(vals: list[float], period: int) -> float:
    if not vals or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = float(vals[0])
    for x in vals[1:]:
        e = float(x) * k + e * (1.0 - k)
    return e


def _live_regime_from_state(st: SymState) -> str:
    """Classify market regime from live 5m state as 'flat' or 'trend'."""
    closes = list(getattr(st, "closes", []) or [])
    highs = list(getattr(st, "highs", []) or [])
    lows = list(getattr(st, "lows", []) or [])
    if len(closes) < 120 or len(highs) < 120 or len(lows) < 120:
        return "trend"
    cur = float(closes[-1] or 0.0)
    if cur <= 0:
        return "trend"
    ef = _ema_list(closes[-90:], 20)
    es = _ema_list(closes[-140:], 50)
    es_prev = _ema_list(closes[-190:-40], 50) if len(closes) >= 190 else float("nan")
    atr_pct = calc_atr_pct(highs, lows, closes)
    if not (math.isfinite(ef) and math.isfinite(es) and math.isfinite(es_prev) and math.isfinite(atr_pct)):
        return "trend"
    gap_pct = abs(ef - es) / cur * 100.0
    slope_pct = abs((es - es_prev) / max(1e-12, abs(es_prev))) * 100.0
    is_flat = (gap_pct <= 0.55) and (slope_pct <= 0.55) and (0.20 <= atr_pct <= 2.40)
    return "flat" if is_flat else "trend"


def live_allocator_multiplier(strategy_key: str, regime: str) -> float:
    if not LIVE_ALLOCATOR_ENABLE:
        return 1.0
    st = str(strategy_key or "").strip().lower()
    rg = str(regime or "trend").strip().lower()
    if st == "breakout":
        m = LIVE_ALLOCATOR_BREAKOUT_FLAT_MULT if rg == "flat" else LIVE_ALLOCATOR_BREAKOUT_TREND_MULT
    elif st == "midterm":
        m = LIVE_ALLOCATOR_MIDTERM_FLAT_MULT if rg == "flat" else LIVE_ALLOCATOR_MIDTERM_TREND_MULT
    else:
        m = 1.0
    return max(float(LIVE_ALLOCATOR_MULT_MIN), min(float(LIVE_ALLOCATOR_MULT_MAX), float(m)))


_RANGE_LAST_TRY = {}            # symbol -> ts
RANGE_TRY_EVERY_SEC = 20

_INPLAY_LAST_TRY = {}           # symbol -> ts
_BREAKOUT_LAST_TRY = {}         # symbol -> ts
_RETEST_LAST_TRY = {}           # symbol -> ts
_MIDTERM_LAST_TRY = {}          # symbol -> ts
_SLOPED_LAST_TRY = {}           # symbol -> ts
_FLAT_LAST_TRY = {}             # symbol -> ts
_BREAKDOWN_LAST_TRY = {}        # symbol -> ts
_TS132_LAST_TRY = {}            # symbol -> ts
_BREAKOUT_COOLDOWN_UNTIL = {}   # symbol -> ts
_BREAKOUT_COOLDOWN_LOG_TS = {}  # symbol -> ts
_KILLER_GUARD_LOG_TS = {}       # symbol -> ts


def _get_news_events_and_policy():
    """Return (events, policy) — reloads from disk every _NEWS_CACHE_TTL seconds."""
    global _NEWS_EVENTS, _NEWS_POLICY, _NEWS_CACHE_TS
    now = now_s()
    if now - _NEWS_CACHE_TS > _NEWS_CACHE_TTL:
        try:
            _NEWS_EVENTS = load_news_events(_NEWS_EVENTS_PATH)
        except Exception:
            pass
        try:
            _NEWS_POLICY = load_news_policy(_NEWS_POLICY_PATH)
        except Exception:
            pass
        _NEWS_CACHE_TS = now
    return _NEWS_EVENTS, _NEWS_POLICY
_BREAKOUT_SESSION_LOG_TS = {}   # symbol -> ts

async def try_range_entry_async(symbol: str, price: float):
    if not ENABLE_RANGE_TRADING:
        return
    if not TRADE_ON or DRY_RUN:
        return
    if TRADE_CLIENT is None:
        return
    if get_trade("Bybit", symbol) is not None:
        return
    if not portfolio_can_open():
        return

    now = now_s()
    last = int(_RANGE_LAST_TRY.get(symbol, 0) or 0)
    if now - last < RANGE_TRY_EVERY_SEC:
        return
    _RANGE_LAST_TRY[symbol] = now

    sig = await RANGE_STRATEGY.maybe_signal(symbol, price)
    if not sig:
        return

    # округлим TP/SL под tickSize и логически проверим
    tp_r, sl_r = round_tp_sl_prices(symbol, sig.side, float(price), sig.tp, sig.sl)
    if tp_r is None or sl_r is None:
        return

    stop_pct = abs((float(sl_r) - float(price)) / max(1e-12, float(price))) * 100.0
    dyn_usd = calc_notional_usd_from_stop_pct(stop_pct)
    if dyn_usd <= 0:
        tg_trade(f"🟡 RANGE SKIP {symbol}: stop={stop_pct:.2f}% -> notional too small")
        return

    qty_floor, notional_real, reason = qty_floor_from_notional(symbol, dyn_usd, price)
    if qty_floor <= 0:
        tg_trade(f"🟡 RANGE SKIP {symbol}: {reason} (need≈{dyn_usd:.2f}$)")
        return
    proposed_risk_usd = qty_floor * abs(float(price) - float(sl_r))
    can_add, total_risk_pct, cap_risk_pct = portfolio_can_add_open_risk(proposed_risk_usd)
    if not can_add:
        tg_trade_throttled(
            f"portfolio_risk:range:{symbol}",
            f"🟡 RANGE SKIP {symbol}: open-risk {total_risk_pct:.2f}% > cap {cap_risk_pct:.2f}%",
            3600,
        )
        return

    ensure_leverage(symbol, BYBIT_LEVERAGE)

    # для range так же запрещаем quoteCoin fallback
    oid, q = TRADE_CLIENT.place_market(symbol, sig.side, qty_floor, allow_quote_fallback=False)

    tr = TradeState(
        symbol=symbol,
        side=sig.side,
        qty=q,
        entry_price_req=float(price),
        entry_ts=now,
    )
    tr.entry_order_id = oid
    tr.status = "PENDING_ENTRY"
    tr.strategy = "range"
    tr.avg = float(price)
    tr.entry_price = float(price)
    tr.tp_price = float(tp_r)
    tr.sl_price = float(sl_r)
    TRADES[("Bybit", symbol)] = tr

    ok = set_tp_sl_retry(symbol, tr.side, tr.tp_price, tr.sl_price)
    tr.tpsl_on_exchange = bool(ok)
    tr.tpsl_last_set_ts = now_s()
    if ok:
        tr.tpsl_manual_lock = False

    tg_trade(
        f"🟦 RANGE ENTRY [{TRADE_CLIENT.name}] {symbol} {sig.side}\n"
        f"entry≈{price:.6f} TP={tr.tp_price:.6f} SL={tr.sl_price:.6f}\n"
        f"notional≈{notional_real:.2f}$ qty≈{q}\n"
        f"reason={sig.reason}"
    )


async def try_inplay_entry_async(symbol: str, price: float):
    if not ENABLE_INPLAY_TRADING:
        return
    if not TRADE_ON or DRY_RUN:
        return
    if TRADE_CLIENT is None:
        return
    if get_trade("Bybit", symbol) is not None:
        return
    if INPLAY_SYMBOLS and (symbol not in INPLAY_SYMBOLS):
        return
    if not portfolio_can_open():
        return

    now = now_s()
    last = int(_INPLAY_LAST_TRY.get(symbol, 0) or 0)
    if now - last < INPLAY_TRY_EVERY_SEC:
        return
    _INPLAY_LAST_TRY[symbol] = now

    try:
        sig = await INPLAY_ENGINE.signal_async(symbol, price, int(now * 1000))
    except Exception as e:
        log_error(f"inplay signal error {symbol}: {e}")
        return
    if not sig:
        return

    side = "Buy" if sig.side == "long" else "Sell"
    entry = float(sig.entry)
    tp = float(sig.tp)
    sl = float(sig.sl)

    # If runner plan exists, we only place SL on exchange (TPs handled by runner)
    use_runner = bool(getattr(sig, "tps", None)) and bool(getattr(sig, "tp_fracs", None))
    tp_r, sl_r = round_tp_sl_prices(symbol, side, entry, None if use_runner else tp, sl)
    if tp_r is None or sl_r is None:
        return

    stop_pct = abs((float(sl_r) - float(entry)) / max(1e-12, float(entry))) * 100.0
    dyn_usd = calc_notional_usd_from_stop_pct(stop_pct)
    if dyn_usd <= 0:
        tg_trade(f"🟡 INPLAY SKIP {symbol}: stop={stop_pct:.2f}% -> notional too small")
        return

    qty_floor, notional_real, reason = qty_floor_from_notional(symbol, dyn_usd, entry)
    if qty_floor <= 0:
        tg_trade(f"🟡 INPLAY SKIP {symbol}: {reason} (need≈{dyn_usd:.2f}$)")
        return
    proposed_risk_usd = qty_floor * abs(float(entry) - float(sl_r))
    can_add, total_risk_pct, cap_risk_pct = portfolio_can_add_open_risk(proposed_risk_usd)
    if not can_add:
        tg_trade_throttled(
            f"portfolio_risk:inplay:{symbol}",
            f"🟡 INPLAY SKIP {symbol}: open-risk {total_risk_pct:.2f}% > cap {cap_risk_pct:.2f}%",
            3600,
        )
        return

    ensure_leverage(symbol, BYBIT_LEVERAGE)

    oid, q = TRADE_CLIENT.place_market(symbol, side, qty_floor, allow_quote_fallback=False)

    tr = TradeState(
        symbol=symbol,
        side=side,
        qty=q,
        entry_price_req=float(entry),
        entry_ts=now,
    )
    tr.entry_order_id = oid
    tr.status = "PENDING_ENTRY"
    tr.strategy = "inplay"
    tr.avg = float(entry)
    tr.entry_price = float(entry)
    tr.tp_price = float(tp_r) if tp_r is not None else None
    tr.sl_price = float(sl_r)
    tr.runner_enabled = bool(use_runner)
    if tr.runner_enabled:
        tr.tps = [float(x) for x in (sig.tps or [])]
        tr.tp_fracs = [float(x) for x in (sig.tp_fracs or [])]
        tr.tp_hit = [False for _ in tr.tps]
        tr.initial_qty = float(q)
        tr.remaining_qty = float(q)
        tr.trail_mult = float(getattr(sig, "trailing_atr_mult", 0.0) or 0.0)
        tr.trail_period = int(getattr(sig, "trailing_atr_period", 14) or 14)
        ts_bars = int(getattr(sig, "time_stop_bars", 0) or 0)
        tr.time_stop_sec = int(ts_bars * 300)
    TRADES[("Bybit", symbol)] = tr

    ok = set_tp_sl_retry(symbol, tr.side, tr.tp_price, tr.sl_price)
    tr.tpsl_on_exchange = bool(ok)
    tr.tpsl_last_set_ts = now_s()
    if ok:
        tr.tpsl_manual_lock = False

    if tr.tp_price is not None:
        tp_txt = f"{tr.tp_price:.6f}"
    else:
        tp_txt = "runner"
    tg_trade(
        f"🟩 INPLAY ENTRY [{TRADE_CLIENT.name}] {symbol} {side}\n"
        f"entry≈{entry:.6f} TP={tp_txt} SL={tr.sl_price:.6f}\n"
        f"notional≈{notional_real:.2f}$ qty≈{q}\n"
        f"reason={sig.reason}"
    )


async def try_breakout_entry_async(symbol: str, price: float):
    if not ENABLE_BREAKOUT_TRADING:
        return
    if not TRADE_ON or DRY_RUN:
        return
    if TRADE_CLIENT is None:
        return
    if get_trade("Bybit", symbol) is not None:
        return
    if BREAKOUT_SYMBOLS and (symbol not in BREAKOUT_SYMBOLS):
        return
    if not portfolio_can_open():
        return

    now = now_s()
    signal_ts = int(now)
    cool_until = int(_BREAKOUT_COOLDOWN_UNTIL.get(symbol, 0) or 0)
    if cool_until > now:
        last_log = int(_BREAKOUT_COOLDOWN_LOG_TS.get(symbol, 0) or 0)
        if now - last_log >= 300:
            mins = max(1, (cool_until - now) // 60)
            tg_trade(f"🟡 BREAKOUT COOLDOWN {symbol}: {mins}m left")
            _BREAKOUT_COOLDOWN_LOG_TS[symbol] = now
        return

    if KILLER_GUARD_ENABLE:
        banned = _refresh_killer_guard_cache()
        if symbol in banned:
            last_log = int(_KILLER_GUARD_LOG_TS.get(symbol, 0) or 0)
            if now - last_log >= max(30, int(KILLER_GUARD_LOG_EVERY_SEC)):
                tg_trade(f"🟡 BREAKOUT SKIP {symbol}: killer-guard (recent net<= {KILLER_GUARD_MAX_NET_PNL})")
                _KILLER_GUARD_LOG_TS[symbol] = now
            return

    last = int(_BREAKOUT_LAST_TRY.get(symbol, 0) or 0)
    if now - last < BREAKOUT_TRY_EVERY_SEC:
        return
    _BREAKOUT_LAST_TRY[symbol] = now
    _diag_inc("breakout_try")

    # ── News filter ──────────────────────────────────────────────────────────
    if _NEWS_FILTER_ENABLE:
        try:
            _ev, _pol = _get_news_events_and_policy()
            blocked, reason = _news_is_blocked(
                symbol=symbol,
                ts_utc=int(now),
                strategy_name="inplay_breakout",
                events=_ev,
                policy=_pol,
            )
            if blocked:
                _diag_inc("breakout_skip_news")
                tg_trade(f"📰 BREAKOUT SKIP {symbol}: news blackout — {reason}")
                return
        except Exception as _nf_err:
            log_error(f"news_filter error: {_nf_err}")

    if BREAKOUT_SESSION_FILTER_ENABLE:
        sess = _session_name_utc(now)
        allowed = BREAKOUT_SESSION_ALLOWED or {"asia", "europe", "us"}
        if sess not in allowed:
            last_log = int(_BREAKOUT_SESSION_LOG_TS.get(symbol, 0) or 0)
            if now - last_log >= 600:
                tg_trade(f"🟡 BREAKOUT SKIP {symbol}: session={sess} not in {sorted(allowed)}")
                _BREAKOUT_SESSION_LOG_TS[symbol] = now
            return

    try:
        sig = await BREAKOUT_ENGINE.signal_async(symbol, price, int(now * 1000))
    except Exception as e:
        log_error(f"breakout signal error {symbol}: {e}")
        return
    if not sig:
        _diag_inc("breakout_no_signal")
        try:
            ns_reason = BREAKOUT_ENGINE.last_no_signal_reason(symbol)
        except Exception:
            ns_reason = ""
        _diag_inc(_breakout_no_signal_diag_key(ns_reason))
        # ── Impulse deficit histogram ────────────────────────────────────────
        # When the impulse filter is the blocker, record HOW FAR below threshold
        # to distinguish "deep flat" (ratio < 0.25) from "almost there" (ratio ≥ 0.75).
        if ns_reason in ("impulse_weak", "impulse_body_weak", "impulse_vol_weak"):
            try:
                ratio = BREAKOUT_ENGINE.last_impulse_ratio(symbol)
            except Exception:
                ratio = 0.0
            if ratio < 0.25:
                _diag_inc("breakout_ns_impulse_q1")    # < 25% of threshold
            elif ratio < 0.50:
                _diag_inc("breakout_ns_impulse_q2")    # 25-50% of threshold
            elif ratio < 0.75:
                _diag_inc("breakout_ns_impulse_q3")    # 50-75% of threshold
            else:
                _diag_inc("breakout_ns_impulse_q4")    # 75-100% of threshold
        return

    side = "Buy" if sig.side == "long" else "Sell"
    entry = float(sig.entry)
    tp = float(sig.tp)
    sl = float(sig.sl)
    chase_pct = 0.0
    late_pct = 0.0
    pullback = 0.0
    sp = 0.0

    def _breakout_skip_alert(reason_key: str, msg: str):
        _record_breakout_skip(symbol, reason_key)
        if BREAKOUT_SKIP_TG_IMMEDIATE:
            tg_trade_throttled(
                f"breakout_skip:{symbol}:{reason_key}",
                msg,
                BREAKOUT_SKIP_ALERT_COOLDOWN_SEC,
            )

    # Don't chase far from planned entry; prefer retest-like fills.
    if BREAKOUT_MAX_CHASE_PCT > 0:
        chase_pct = abs((float(price) - float(entry)) / max(1e-12, float(entry))) * 100.0
        if chase_pct > BREAKOUT_MAX_CHASE_PCT:
            _breakout_skip_alert(
                "chase",
                f"🟡 BREAKOUT SKIP {symbol}: chase {chase_pct:.2f}% > {BREAKOUT_MAX_CHASE_PCT:.2f}%",
            )
            return

    st = S("Bybit", symbol)
    _prev5, cur5 = last_two_5m_bars(st, now)
    if BREAKOUT_MIN_QUOTE_5M_USD > 0:
        t0_liq = int(now - 300)
        q5m = 0.0
        for x in st.trades:
            if x[0] >= t0_liq:
                q5m += float(x[2] or 0.0)
        if q5m < BREAKOUT_MIN_QUOTE_5M_USD:
            _diag_inc("breakout_skip_liq")
            _breakout_skip_alert(
                "liq5m",
                f"🟡 BREAKOUT SKIP {symbol}: liq5m {q5m:.0f}$ < {BREAKOUT_MIN_QUOTE_5M_USD:.0f}$",
            )
            return

    # Retest confirmation: require touch near entry and directional close in current 5m bar.
    if BREAKOUT_REQUIRE_RETEST_CONFIRM:
        if not cur5:
            return
        tol = max(0.01, float(BREAKOUT_RETEST_TOUCH_PCT))
        if side == "Buy":
            touched = cur5["low"] <= float(entry) * (1.0 + tol / 100.0)
            confirmed = bool(cur5["up"]) and float(cur5["close"]) >= float(entry)
        else:
            touched = cur5["high"] >= float(entry) * (1.0 - tol / 100.0)
            confirmed = (not bool(cur5["up"])) and float(cur5["close"]) <= float(entry)
        if not (touched and confirmed):
            return

    # Anti-late-entry: skip if current/entry price is too far beyond breakout reference.
    ref_px = breakout_ref_price(st, side, BREAKOUT_REF_LOOKBACK_BARS)
    if ref_px and BREAKOUT_MAX_LATE_VS_REF_PCT > 0:
        base_px = max(float(entry), float(price)) if side == "Buy" else min(float(entry), float(price))
        if side == "Buy":
            late_pct = (base_px - ref_px) / max(ref_px, 1e-12) * 100.0
        else:
            late_pct = (ref_px - base_px) / max(ref_px, 1e-12) * 100.0
        if late_pct > BREAKOUT_MAX_LATE_VS_REF_PCT:
            _breakout_skip_alert(
                "late",
                f"🟡 BREAKOUT SKIP {symbol}: late {late_pct:.2f}% > {BREAKOUT_MAX_LATE_VS_REF_PCT:.2f}%",
            )
            return

    # Anti-FOMO: require at least minimal pullback from the current 5m extreme.
    if cur5 and BREAKOUT_MIN_PULLBACK_FROM_EXTREME_PCT > 0:
        pullback_min = float(BREAKOUT_MIN_PULLBACK_FROM_EXTREME_PCT)
        if side == "Buy":
            pullback = (float(cur5["high"]) - float(price)) / max(float(cur5["high"]), 1e-12) * 100.0
        else:
            pullback = (float(price) - float(cur5["low"])) / max(float(cur5["low"]), 1e-12) * 100.0
        # Use a tiny epsilon to avoid noisy edge-case alerts like "0.03% < 0.03%" caused by formatting.
        if pullback + 1e-9 < pullback_min:
            _diag_inc("breakout_skip_pullback")
            delta = max(0.0, pullback_min - pullback)
            _breakout_skip_alert(
                "pullback",
                f"🟡 BREAKOUT SKIP {symbol}: pullback {pullback:.4f}% < {pullback_min:.4f}% (delta {delta:.4f}%)"
            )
            return

    use_runner = bool(getattr(sig, "tps", None)) and bool(getattr(sig, "tp_fracs", None))
    tp_r, sl_r = round_tp_sl_prices(symbol, side, entry, None if use_runner else tp, sl)
    if tp_r is None or sl_r is None:
        return

    if BREAKOUT_MAX_SPREAD_PCT > 0:
        sp = float(get_spread_pct_cached(symbol))
        if sp >= BREAKOUT_MAX_SPREAD_PCT:
            _breakout_skip_alert(
                "spread",
                f"🟡 BREAKOUT SKIP {symbol}: spread {sp:.2f}% >= {BREAKOUT_MAX_SPREAD_PCT:.2f}%",
            )
            return

    stop_pct = abs((float(sl_r) - float(entry)) / max(1e-12, float(entry))) * 100.0

    # Widen too-tight stops using ATR floor (helps noisy post-breakout pullbacks).
    atr_pct = calc_atr_pct(list(st.highs), list(st.lows), list(st.closes))
    min_stop_pct = float(BREAKOUT_MIN_STOP_ATR_MULT) * float(atr_pct)
    if min_stop_pct > 0 and stop_pct < min_stop_pct:
        rr = 1.0
        try:
            if side == "Buy":
                rr = max(0.5, (float(tp_r) - float(entry)) / max(1e-12, float(entry) - float(sl_r)))
                sl = float(entry) * (1.0 - min_stop_pct / 100.0)
                tp = float(entry) + rr * (float(entry) - float(sl))
            else:
                rr = max(0.5, (float(entry) - float(tp_r)) / max(1e-12, float(sl_r) - float(entry)))
                sl = float(entry) * (1.0 + min_stop_pct / 100.0)
                tp = float(entry) - rr * (float(sl) - float(entry))
            tp_r, sl_r = round_tp_sl_prices(symbol, side, entry, None if use_runner else tp, sl)
            if tp_r is None or sl_r is None:
                return
            stop_pct = abs((float(sl_r) - float(entry)) / max(1e-12, float(entry))) * 100.0
        except Exception as e:
            log_error(f"breakout atr-sl adjust fail {symbol}: {e}")
    quality_score = breakout_quality_score(
        chase_pct=chase_pct,
        late_pct=late_pct,
        spread_pct=sp,
        pullback_pct=pullback,
    )
    if BREAKOUT_QUALITY_MIN_SCORE > 0 and quality_score < BREAKOUT_QUALITY_MIN_SCORE:
        _diag_inc("breakout_skip_quality")
        _breakout_skip_alert(
            "quality",
            f"🟡 BREAKOUT SKIP {symbol}: quality {quality_score:.2f} < {BREAKOUT_QUALITY_MIN_SCORE:.2f}"
        )
        return
    size_mult = breakout_sizeup_multiplier_from_score(quality_score)
    quality_boost_mult = breakout_quality_boost_multiplier(quality_score)
    st_alloc = live_allocator_multiplier("breakout", _live_regime_from_state(st))
    risk_mult = float(size_mult) * float(quality_boost_mult) * float(st_alloc)
    dyn_usd = calc_notional_usd_from_stop_pct(stop_pct, risk_mult=risk_mult)
    if dyn_usd <= 0:
        _breakout_skip_alert(
            "notional_small",
            f"🟡 BREAKOUT SKIP {symbol}: stop={stop_pct:.2f}% -> notional too small",
        )
        return

    qty_floor, notional_real, reason = qty_floor_from_notional(symbol, dyn_usd, entry)
    if qty_floor <= 0:
        _diag_inc("breakout_skip_minqty")
        _breakout_skip_alert(
            f"minqty:{reason}",
            f"🟡 BREAKOUT SKIP {symbol}: {reason} (need≈{dyn_usd:.2f}$)",
        )
        return
    proposed_risk_usd = qty_floor * abs(float(entry) - float(sl_r))
    can_add, total_risk_pct, cap_risk_pct = portfolio_can_add_open_risk(proposed_risk_usd)
    if not can_add:
        _breakout_skip_alert(
            "portfolio_risk",
            f"🟡 BREAKOUT SKIP {symbol}: open-risk {total_risk_pct:.2f}% > cap {cap_risk_pct:.2f}%",
        )
        return

    entry_lock = _get_symbol_entry_lock("Bybit", symbol)
    if entry_lock.locked():
        _diag_inc("breakout_skip_symbol_lock")
        return
    async with entry_lock:
        if get_trade("Bybit", symbol) is not None:
            return
        if not portfolio_can_open():
            return

        ensure_leverage(symbol, BYBIT_LEVERAGE)
        _diag_inc("breakout_entry")
        order_send_ts = int(now_s())
        oid, q = TRADE_CLIENT.place_market(symbol, side, qty_floor, allow_quote_fallback=False)
        order_ack_ts = int(now_s())

        tr = TradeState(
            symbol=symbol,
            side=side,
            qty=q,
            entry_price_req=float(entry),
            entry_ts=now,
        )
        tr.entry_order_id = oid
        tr.status = "PENDING_ENTRY"
        tr.strategy = "inplay_breakout"
        tr.avg = float(entry)
        tr.entry_price = float(entry)
        tr.entry_notional_usd = float(notional_real)
        tr.ml_features = {
            "signal": "inplay_breakout",
            "chase_pct": float(chase_pct),
            "late_pct": float(late_pct),
            "pullback_pct": float(pullback),
            "spread_pct": float(sp),
            "quality_score": float(quality_score),
            "size_mult": float(size_mult),
            "quality_boost_mult": float(quality_boost_mult),
            "alloc_mult": float(st_alloc),
            "risk_mult": float(risk_mult),
            "stop_pct": float(stop_pct),
            "session": str(_session_name_utc(now)),
            "symbol_family": "alt",
        }
        tr.tp_price = float(tp_r) if tp_r is not None else None
        tr.sl_price = float(sl_r)
        tr.signal_ts = int(signal_ts)
        tr.order_send_ts = int(order_send_ts)
        tr.order_ack_ts = int(order_ack_ts)
        tr.runner_enabled = bool(use_runner)
        if tr.runner_enabled:
            tr.tps = [float(x) for x in (sig.tps or [])]
            tr.tp_fracs = [float(x) for x in (sig.tp_fracs or [])]
            tr.tp_hit = [False for _ in tr.tps]
            tr.initial_qty = float(q)
            tr.remaining_qty = float(q)
            tr.trail_mult = float(getattr(sig, "trailing_atr_mult", 0.0) or 0.0)
            tr.trail_period = int(getattr(sig, "trailing_atr_period", 14) or 14)
            ts_bars = int(getattr(sig, "time_stop_bars", 0) or 0)
            tr.time_stop_sec = int(ts_bars * 300)
        TRADES[("Bybit", symbol)] = tr

        ok = set_tp_sl_retry(symbol, tr.side, tr.tp_price, tr.sl_price)
        tr.tpsl_on_exchange = bool(ok)
        tr.tpsl_last_set_ts = now_s()
        if ok:
            tr.tpsl_manual_lock = False

        tp_txt = f"{tr.tp_price:.6f}" if tr.tp_price is not None else "runner"
        tg_trade(
            f"🟩 BREAKOUT ENTRY [{TRADE_CLIENT.name}] {symbol} {side}\n"
            f"entry≈{entry:.6f} TP={tp_txt} SL={tr.sl_price:.6f}\n"
            f"notional≈{notional_real:.2f}$ qty≈{q} quality={quality_score:.2f} "
            f"size_mult={size_mult:.2f} boost={quality_boost_mult:.2f} alloc={st_alloc:.2f}\n"
            f"reason={sig.reason}"
        )


async def try_retest_entry_async(symbol: str, price: float):
    if not ENABLE_RETEST_TRADING:
        return
    if not TRADE_ON or DRY_RUN:
        return
    if TRADE_CLIENT is None:
        return
    if get_trade("Bybit", symbol) is not None:
        return
    if RETEST_SYMBOLS and (symbol not in RETEST_SYMBOLS):
        return
    if not portfolio_can_open():
        return

    now = now_s()
    last = int(_RETEST_LAST_TRY.get(symbol, 0) or 0)
    if now - last < RETEST_TRY_EVERY_SEC:
        return
    _RETEST_LAST_TRY[symbol] = now

    try:
        sig = RETEST_ENGINE.signal(symbol, price)
    except Exception as e:
        log_error(f"retest signal error {symbol}: {e}")
        return
    if not sig:
        return

    side = "Buy" if sig.side == "long" else "Sell"
    entry = float(sig.entry)
    tp = float(sig.tp)
    sl = float(sig.sl)

    tp_r, sl_r = round_tp_sl_prices(symbol, side, entry, tp, sl)
    if tp_r is None or sl_r is None:
        return

    stop_pct = abs((float(sl_r) - float(entry)) / max(1e-12, float(entry))) * 100.0
    dyn_usd = calc_notional_usd_from_stop_pct(stop_pct)
    if dyn_usd <= 0:
        tg_trade(f"🟡 RETEST SKIP {symbol}: stop={stop_pct:.2f}% -> notional too small")
        return

    qty_floor, notional_real, reason = qty_floor_from_notional(symbol, dyn_usd, entry)
    if qty_floor <= 0:
        tg_trade(f"🟡 RETEST SKIP {symbol}: {reason} (need≈{dyn_usd:.2f}$)")
        return
    proposed_risk_usd = qty_floor * abs(float(entry) - float(sl_r))
    can_add, total_risk_pct, cap_risk_pct = portfolio_can_add_open_risk(proposed_risk_usd)
    if not can_add:
        tg_trade_throttled(
            f"portfolio_risk:retest:{symbol}",
            f"🟡 RETEST SKIP {symbol}: open-risk {total_risk_pct:.2f}% > cap {cap_risk_pct:.2f}%",
            3600,
        )
        return

    ensure_leverage(symbol, BYBIT_LEVERAGE)
    oid, q = TRADE_CLIENT.place_market(symbol, side, qty_floor, allow_quote_fallback=False)

    tr = TradeState(
        symbol=symbol,
        side=side,
        qty=q,
        entry_price_req=float(entry),
        entry_ts=now,
    )
    tr.entry_order_id = oid
    tr.status = "PENDING_ENTRY"
    tr.strategy = "retest_levels"
    tr.avg = float(entry)
    tr.entry_price = float(entry)
    tr.tp_price = float(tp_r)
    tr.sl_price = float(sl_r)
    TRADES[("Bybit", symbol)] = tr

    ok = set_tp_sl_retry(symbol, tr.side, tr.tp_price, tr.sl_price)
    tr.tpsl_on_exchange = bool(ok)
    tr.tpsl_last_set_ts = now_s()
    if ok:
        tr.tpsl_manual_lock = False

    tg_trade(
        f"🟦 RETEST ENTRY [{TRADE_CLIENT.name}] {symbol} {side}\n"
        f"entry≈{entry:.6f} TP={tr.tp_price:.6f} SL={tr.sl_price:.6f}\n"
        f"notional≈{notional_real:.2f}$ qty≈{q}\n"
        f"reason={sig.reason}"
    )


async def try_midterm_entry_async(symbol: str, price: float):
    if not ENABLE_MIDTERM_TRADING:
        return
    if not TRADE_ON or DRY_RUN:
        return
    if TRADE_CLIENT is None:
        return
    if get_trade("Bybit", symbol) is not None:
        return
    if MIDTERM_ACTIVE_SYMBOLS and (symbol not in MIDTERM_ACTIVE_SYMBOLS):
        return
    if not portfolio_can_open():
        return

    now = now_s()
    last = int(_MIDTERM_LAST_TRY.get(symbol, 0) or 0)
    if now - last < MIDTERM_TRY_EVERY_SEC:
        return
    _MIDTERM_LAST_TRY[symbol] = now
    _diag_inc("midterm_try")

    try:
        sig = await MIDTERM_ENGINE.signal_async(symbol, price, int(now * 1000))
    except Exception as e:
        log_error(f"midterm signal error {symbol}: {e}")
        return
    if not sig:
        _diag_inc("midterm_no_signal")
        return

    side = "Buy" if sig.side == "long" else "Sell"
    entry = float(sig.entry)
    tp = float(sig.tp)
    sl = float(sig.sl)

    use_runner = bool(getattr(sig, "tps", None)) and bool(getattr(sig, "tp_fracs", None))
    tp_r, sl_r = round_tp_sl_prices(symbol, side, entry, None if use_runner else tp, sl)
    if tp_r is None or sl_r is None:
        return

    stop_pct = abs((float(sl_r) - float(entry)) / max(1e-12, float(entry))) * 100.0
    dyn_usd = calc_notional_usd_from_stop_pct(stop_pct)
    st = S("Bybit", symbol)
    alloc_mult = live_allocator_multiplier("midterm", _live_regime_from_state(st))
    dyn_usd *= float(MIDTERM_NOTIONAL_MULT) * float(alloc_mult)
    if dyn_usd <= 0:
        tg_trade(f"🟡 MIDTERM SKIP {symbol}: stop={stop_pct:.2f}% -> notional too small")
        return

    qty_floor, notional_real, reason = qty_floor_from_notional(symbol, dyn_usd, entry)
    if qty_floor <= 0 and reason == "BELOW_MIN_QTY" and MIDTERM_ALLOW_MINQTY_FALLBACK:
        need_min = min_notional_for_min_qty(symbol, entry)
        if need_min > 0:
            dyn_max = dyn_usd * float(MIDTERM_MINQTY_FALLBACK_MAX_MULT)
            dyn_fallback = min(need_min, dyn_max)
            if dyn_fallback > dyn_usd + 1e-9:
                qty_floor, notional_real, reason2 = qty_floor_from_notional(symbol, dyn_fallback, entry)
                if qty_floor > 0:
                    reason = ""
                    dyn_usd = dyn_fallback
                else:
                    reason = reason2
    if qty_floor <= 0:
        _diag_inc("midterm_skip_minqty")
        tg_trade(f"🟡 MIDTERM SKIP {symbol}: {reason} (need≈{dyn_usd:.2f}$)")
        return
    proposed_risk_usd = qty_floor * abs(float(entry) - float(sl_r))
    can_add, total_risk_pct, cap_risk_pct = portfolio_can_add_open_risk(proposed_risk_usd)
    if not can_add:
        tg_trade_throttled(
            f"portfolio_risk:midterm:{symbol}",
            f"🟡 MIDTERM SKIP {symbol}: open-risk {total_risk_pct:.2f}% > cap {cap_risk_pct:.2f}%",
            3600,
        )
        return

    entry_lock = _get_symbol_entry_lock("Bybit", symbol)
    if entry_lock.locked():
        _diag_inc("midterm_skip_symbol_lock")
        return
    async with entry_lock:
        if get_trade("Bybit", symbol) is not None:
            return
        if not portfolio_can_open():
            return

        ensure_leverage(symbol, BYBIT_LEVERAGE)
        _diag_inc("midterm_entry")
        oid, q = TRADE_CLIENT.place_market(symbol, side, qty_floor, allow_quote_fallback=False)

        tr = TradeState(
            symbol=symbol,
            side=side,
            qty=q,
            entry_price_req=float(entry),
            entry_ts=now,
        )
        tr.entry_order_id = oid
        tr.status = "PENDING_ENTRY"
        tr.strategy = "btc_eth_midterm_pullback"
        tr.avg = float(entry)
        tr.entry_price = float(entry)
        tr.entry_notional_usd = float(notional_real)
        tr.ml_features = {
            "signal": "btc_eth_midterm_pullback",
            "stop_pct": float(stop_pct),
            "alloc_mult": float(MIDTERM_NOTIONAL_MULT),
            "regime_alloc_mult": float(alloc_mult),
            "session": str(_session_name_utc(now)),
            "symbol_family": "btc_eth",
        }
        tr.tp_price = float(tp_r) if tp_r is not None else None
        tr.sl_price = float(sl_r)
        tr.runner_enabled = bool(use_runner)
        if tr.runner_enabled:
            tr.tps = [float(x) for x in (sig.tps or [])]
            tr.tp_fracs = [float(x) for x in (sig.tp_fracs or [])]
            tr.tp_hit = [False for _ in tr.tps]
            tr.initial_qty = float(q)
            tr.remaining_qty = float(q)
            tr.trail_mult = float(getattr(sig, "trailing_atr_mult", 0.0) or 0.0)
            tr.trail_period = int(getattr(sig, "trailing_atr_period", 14) or 14)
            ts_bars = int(getattr(sig, "time_stop_bars", 0) or 0)
            tr.time_stop_sec = int(ts_bars * 300)
        TRADES[("Bybit", symbol)] = tr

        ok = set_tp_sl_retry(symbol, tr.side, tr.tp_price, tr.sl_price)
        tr.tpsl_on_exchange = bool(ok)
        tr.tpsl_last_set_ts = now_s()
        if ok:
            tr.tpsl_manual_lock = False

        tp_txt = f"{tr.tp_price:.6f}" if tr.tp_price is not None else "runner"
        tg_trade(
            f"🟧 MIDTERM ENTRY [{TRADE_CLIENT.name}] {symbol} {side}\n"
            f"entry≈{entry:.6f} TP={tp_txt} SL={tr.sl_price:.6f}\n"
            f"notional≈{notional_real:.2f}$ qty≈{q} alloc_mult={MIDTERM_NOTIONAL_MULT:.2f} regime={alloc_mult:.2f}\n"
            f"reason={sig.reason}"
        )




async def try_sloped_entry_async(symbol: str, price: float):
    """Try sloped channel entry for a symbol."""
    if not ENABLE_SLOPED_TRADING:
        return
    if not _ensure_sloped_engine():
        _diag_inc("sloped_skip_no_engine")
        return
    if not TRADE_ON or DRY_RUN:
        _diag_inc("sloped_skip_trade_off")
        return
    if TRADE_CLIENT is None:
        _diag_inc("sloped_skip_no_client")
        return
    if get_trade("Bybit", symbol) is not None:
        _diag_inc("sloped_skip_open_trade")
        return
    if SLOPED_MAX_OPEN_TRADES > 0:
        open_sloped = 0
        for tr in TRADES.values():
            if getattr(tr, "strategy", "") != "sloped_channel":
                continue
            if str(getattr(tr, "status", "") or "").upper() in {"CLOSED", "ERROR"}:
                continue
            open_sloped += 1
        if open_sloped >= SLOPED_MAX_OPEN_TRADES:
            _diag_inc("sloped_skip_max_open")
            return
    if not portfolio_can_open():
        _diag_inc("sloped_skip_portfolio")
        return

    now = now_s()
    last = int(_SLOPED_LAST_TRY.get(symbol, 0) or 0)
    if now - last < SLOPED_TRY_EVERY_SEC:
        _diag_inc("sloped_skip_cooldown")
        return
    _SLOPED_LAST_TRY[symbol] = now
    _diag_inc("sloped_try")

    try:
        sig = SLOPED_ENGINE.signal(symbol, int(now * 1000), 0, 0, 0, price, 0)
    except Exception as e:
        log_error(f"sloped signal error {symbol}: {e}")
        return
    if not sig:
        return

    side = "Buy" if sig.side == "long" else "Sell"
    entry = float(sig.entry)
    sl = float(sig.sl)
    tp = float(sig.tp)

    use_runner = bool(getattr(sig, "tps", None)) and bool(getattr(sig, "tp_fracs", None))
    tp_r, sl_r = round_tp_sl_prices(symbol, side, entry, None if use_runner else tp, sl)
    if tp_r is None or sl_r is None:
        return

    stop_pct = abs((float(sl_r) - float(entry)) / max(1e-12, float(entry))) * 100.0
    dyn_usd = calc_notional_usd_from_stop_pct(stop_pct, risk_mult=SLOPED_RISK_MULT)
    if dyn_usd <= 0:
        tg_trade(f"🟡 SLOPED SKIP {symbol}: stop={stop_pct:.2f}% -> notional too small")
        return

    qty_floor, notional_real, reason = qty_floor_from_notional(symbol, dyn_usd, price)
    if qty_floor <= 0:
        tg_trade(f"🟡 SLOPED SKIP {symbol}: {reason} (need≈{dyn_usd:.2f}$)")
        return
    proposed_risk_usd = qty_floor * abs(float(entry) - float(sl_r))
    can_add, total_risk_pct, cap_risk_pct = portfolio_can_add_open_risk(proposed_risk_usd)
    if not can_add:
        tg_trade_throttled(
            f"portfolio_risk:sloped:{symbol}",
            f"🟡 SLOPED SKIP {symbol}: open-risk {total_risk_pct:.2f}% > cap {cap_risk_pct:.2f}%",
            3600,
        )
        return

    entry_lock = _get_symbol_entry_lock("Bybit", symbol)
    if entry_lock.locked():
        _diag_inc("sloped_skip_symbol_lock")
        return
    async with entry_lock:
        if get_trade("Bybit", symbol) is not None:
            _diag_inc("sloped_skip_open_trade")
            return
        if not portfolio_can_open():
            _diag_inc("sloped_skip_portfolio")
            return

        ensure_leverage(symbol, BYBIT_LEVERAGE)
        _diag_inc("sloped_entry")
        oid, q = TRADE_CLIENT.place_market(symbol, side, qty_floor, allow_quote_fallback=False)

        tr = TradeState(
            symbol=symbol,
            side=side,
            qty=q,
            entry_price_req=float(entry),
            entry_ts=now,
        )
        tr.entry_order_id = oid
        tr.status = "PENDING_ENTRY"
        tr.strategy = "sloped_channel"
        tr.avg = float(entry)
        tr.entry_price = float(entry)
        tr.entry_notional_usd = float(notional_real)
        tr.tp_price = float(tp_r) if tp_r is not None else None
        tr.sl_price = float(sl_r)
        tr.runner_enabled = bool(use_runner)
        if tr.runner_enabled:
            tr.tps = [float(x) for x in (sig.tps or [])]
            tr.tp_fracs = [float(x) for x in (sig.tp_fracs or [])]
            tr.tp_hit = [False for _ in tr.tps]
            tr.initial_qty = float(q)
            tr.remaining_qty = float(q)
            tr.trail_mult = float(getattr(sig, "trailing_atr_mult", 0.0) or 0.0)
            tr.trail_period = int(getattr(sig, "trailing_atr_period", 14) or 14)
            ts_bars = int(getattr(sig, "time_stop_bars", 0) or 0)
            tr.time_stop_sec = int(ts_bars * 300)
        TRADES[("Bybit", symbol)] = tr

        ok = set_tp_sl_retry(symbol, tr.side, tr.tp_price, tr.sl_price)
        tr.tpsl_on_exchange = bool(ok)
        tr.tpsl_last_set_ts = now_s()
        if ok:
            tr.tpsl_manual_lock = False

        tp_txt = f"{tr.tp_price:.6f}" if tr.tp_price is not None else "runner"
        tg_trade(
            f"🟪 SLOPED ENTRY [{TRADE_CLIENT.name}] {symbol} {sig.side}\n"
            f"entry≈{entry:.6f} TP={tp_txt} SL={tr.sl_price:.6f}\n"
            f"notional≈{notional_real:.2f}$ qty≈{q}\n"
            f"reason={sig.reason}"
        )


async def try_flat_entry_async(symbol: str, price: float):
    """Try flat resistance fade entry for a symbol."""
    if not ENABLE_FLAT_TRADING:
        return
    if not _ensure_flat_engine():
        _diag_inc("flat_skip_no_engine")
        return
    if not TRADE_ON or DRY_RUN:
        _diag_inc("flat_skip_trade_off")
        return
    if TRADE_CLIENT is None:
        _diag_inc("flat_skip_no_client")
        return
    if get_trade("Bybit", symbol) is not None:
        _diag_inc("flat_skip_open_trade")
        return
    if FLAT_MAX_OPEN_TRADES > 0:
        open_flat = 0
        for tr in TRADES.values():
            if getattr(tr, "strategy", "") != "flat_resistance_fade":
                continue
            if str(getattr(tr, "status", "") or "").upper() in {"CLOSED", "ERROR"}:
                continue
            open_flat += 1
        if open_flat >= FLAT_MAX_OPEN_TRADES:
            _diag_inc("flat_skip_max_open")
            return
    if not portfolio_can_open():
        _diag_inc("flat_skip_portfolio")
        return

    now = now_s()
    last = int(_FLAT_LAST_TRY.get(symbol, 0) or 0)
    if now - last < FLAT_TRY_EVERY_SEC:
        _diag_inc("flat_skip_cooldown")
        return
    _FLAT_LAST_TRY[symbol] = now
    _diag_inc("flat_try")

    try:
        sig = FLAT_ENGINE.signal(symbol, int(now * 1000), 0, 0, 0, price, 0)
    except Exception as e:
        log_error(f"flat signal error {symbol}: {e}")
        return
    if not sig:
        return

    side = "Buy" if sig.side == "long" else "Sell"
    entry = float(sig.entry)
    sl = float(sig.sl)
    tp = float(sig.tp)

    use_runner = bool(getattr(sig, "tps", None)) and bool(getattr(sig, "tp_fracs", None))
    tp_r, sl_r = round_tp_sl_prices(symbol, side, entry, None if use_runner else tp, sl)
    if tp_r is None or sl_r is None:
        return

    stop_pct = abs((float(sl_r) - float(entry)) / max(1e-12, float(entry))) * 100.0
    dyn_usd = calc_notional_usd_from_stop_pct(stop_pct, risk_mult=FLAT_RISK_MULT)
    if dyn_usd <= 0:
        tg_trade(f"🟡 FLAT SKIP {symbol}: stop={stop_pct:.2f}% -> notional too small")
        return

    qty_floor, notional_real, reason = qty_floor_from_notional(symbol, dyn_usd, price)
    if qty_floor <= 0:
        tg_trade(f"🟡 FLAT SKIP {symbol}: {reason} (need≈{dyn_usd:.2f}$)")
        return
    proposed_risk_usd = qty_floor * abs(float(entry) - float(sl_r))
    can_add, total_risk_pct, cap_risk_pct = portfolio_can_add_open_risk(proposed_risk_usd)
    if not can_add:
        tg_trade_throttled(
            f"portfolio_risk:flat:{symbol}",
            f"🟡 FLAT SKIP {symbol}: open-risk {total_risk_pct:.2f}% > cap {cap_risk_pct:.2f}%",
            3600,
        )
        return

    entry_lock = _get_symbol_entry_lock("Bybit", symbol)
    if entry_lock.locked():
        _diag_inc("flat_skip_symbol_lock")
        return
    async with entry_lock:
        if get_trade("Bybit", symbol) is not None:
            _diag_inc("flat_skip_open_trade")
            return
        if not portfolio_can_open():
            _diag_inc("flat_skip_portfolio")
            return

        ensure_leverage(symbol, BYBIT_LEVERAGE)
        _diag_inc("flat_entry")
        oid, q = TRADE_CLIENT.place_market(symbol, side, qty_floor, allow_quote_fallback=False)

        tr = TradeState(
            symbol=symbol,
            side=side,
            qty=q,
            entry_price_req=float(entry),
            entry_ts=now,
        )
        tr.entry_order_id = oid
        tr.status = "PENDING_ENTRY"
        tr.strategy = "flat_resistance_fade"
        tr.avg = float(entry)
        tr.entry_price = float(entry)
        tr.entry_notional_usd = float(notional_real)
        tr.tp_price = float(tp_r) if tp_r is not None else None
        tr.sl_price = float(sl_r)
        tr.runner_enabled = bool(use_runner)
        if tr.runner_enabled:
            tr.tps = [float(x) for x in (sig.tps or [])]
            tr.tp_fracs = [float(x) for x in (sig.tp_fracs or [])]
            tr.tp_hit = [False for _ in tr.tps]
            tr.initial_qty = float(q)
            tr.remaining_qty = float(q)
            tr.trail_mult = float(getattr(sig, "trailing_atr_mult", 0.0) or 0.0)
            tr.trail_period = int(getattr(sig, "trailing_atr_period", 14) or 14)
            ts_bars = int(getattr(sig, "time_stop_bars", 0) or 0)
            tr.time_stop_sec = int(ts_bars * 300)
        TRADES[("Bybit", symbol)] = tr

        ok = set_tp_sl_retry(symbol, tr.side, tr.tp_price, tr.sl_price)
        tr.tpsl_on_exchange = bool(ok)
        tr.tpsl_last_set_ts = now_s()
        if ok:
            tr.tpsl_manual_lock = False

        tp_txt = f"{tr.tp_price:.6f}" if tr.tp_price is not None else "runner"
        tg_trade(
            f"🟦 FLAT ENTRY [{TRADE_CLIENT.name}] {symbol} {sig.side}\n"
            f"entry≈{entry:.6f} TP={tp_txt} SL={tr.sl_price:.6f}\n"
            f"notional≈{notional_real:.2f}$ qty≈{q}\n"
            f"reason={sig.reason}"
        )


async def try_breakdown_entry_async(symbol: str, price: float):
    """Try breakdown short entry for a symbol (alt_inplay_breakdown_v1)."""
    if not ENABLE_BREAKDOWN_TRADING:
        return
    if not _ensure_breakdown_engine():
        _diag_inc("breakdown_skip_no_engine")
        return
    if not TRADE_ON or DRY_RUN:
        _diag_inc("breakdown_skip_trade_off")
        return
    if TRADE_CLIENT is None:
        _diag_inc("breakdown_skip_no_client")
        return
    if get_trade("Bybit", symbol) is not None:
        _diag_inc("breakdown_skip_open_trade")
        return
    if BREAKDOWN_MAX_OPEN_TRADES > 0:
        open_bd = 0
        for tr in TRADES.values():
            if getattr(tr, "strategy", "") != "alt_inplay_breakdown_v1":
                continue
            if str(getattr(tr, "status", "") or "").upper() in {"CLOSED", "ERROR"}:
                continue
            open_bd += 1
        if open_bd >= BREAKDOWN_MAX_OPEN_TRADES:
            _diag_inc("breakdown_skip_max_open")
            return
    if not portfolio_can_open():
        _diag_inc("breakdown_skip_portfolio")
        return

    now = now_s()
    last = int(_BREAKDOWN_LAST_TRY.get(symbol, 0) or 0)
    if now - last < BREAKDOWN_TRY_EVERY_SEC:
        _diag_inc("breakdown_skip_cooldown")
        return
    _BREAKDOWN_LAST_TRY[symbol] = now
    _diag_inc("breakdown_try")

    try:
        sig = await BREAKDOWN_ENGINE.signal_async(symbol, int(now * 1000), price)
    except Exception as e:
        log_error(f"breakdown signal error {symbol}: {e}")
        return
    if not sig:
        return

    side = "Buy" if sig.side == "long" else "Sell"
    entry = float(sig.entry)
    sl = float(sig.sl)
    tp = float(sig.tp)

    use_runner = bool(getattr(sig, "tps", None)) and bool(getattr(sig, "tp_fracs", None))
    tp_r, sl_r = round_tp_sl_prices(symbol, side, entry, None if use_runner else tp, sl)
    if tp_r is None or sl_r is None:
        return

    stop_pct = abs((float(sl_r) - float(entry)) / max(1e-12, float(entry))) * 100.0
    dyn_usd = calc_notional_usd_from_stop_pct(stop_pct, risk_mult=BREAKDOWN_RISK_MULT)
    if dyn_usd <= 0:
        tg_trade(f"🟡 BREAKDOWN SKIP {symbol}: stop={stop_pct:.2f}% -> notional too small")
        return

    qty_floor, notional_real, reason = qty_floor_from_notional(symbol, dyn_usd, price)
    if qty_floor <= 0:
        tg_trade(f"🟡 BREAKDOWN SKIP {symbol}: {reason} (need≈{dyn_usd:.2f}$)")
        return
    proposed_risk_usd = qty_floor * abs(float(entry) - float(sl_r))
    can_add, total_risk_pct, cap_risk_pct = portfolio_can_add_open_risk(proposed_risk_usd)
    if not can_add:
        tg_trade_throttled(
            f"portfolio_risk:breakdown:{symbol}",
            f"🟡 BREAKDOWN SKIP {symbol}: open-risk {total_risk_pct:.2f}% > cap {cap_risk_pct:.2f}%",
            3600,
        )
        return

    entry_lock = _get_symbol_entry_lock("Bybit", symbol)
    if entry_lock.locked():
        _diag_inc("breakdown_skip_symbol_lock")
        return
    async with entry_lock:
        if get_trade("Bybit", symbol) is not None:
            _diag_inc("breakdown_skip_open_trade")
            return
        if not portfolio_can_open():
            _diag_inc("breakdown_skip_portfolio")
            return

        ensure_leverage(symbol, BYBIT_LEVERAGE)
        _diag_inc("breakdown_entry")
        oid, q = TRADE_CLIENT.place_market(symbol, side, qty_floor, allow_quote_fallback=False)

        tr = TradeState(
            symbol=symbol,
            side=side,
            qty=q,
            entry_price_req=float(entry),
            entry_ts=now,
        )
        tr.entry_order_id = oid
        tr.status = "PENDING_ENTRY"
        tr.strategy = "alt_inplay_breakdown_v1"
        tr.avg = float(entry)
        tr.entry_price = float(entry)
        tr.entry_notional_usd = float(notional_real)
        tr.tp_price = float(tp_r) if tp_r is not None else None
        tr.sl_price = float(sl_r)
        tr.runner_enabled = bool(use_runner)
        if tr.runner_enabled:
            tr.tps = [float(x) for x in (sig.tps or [])]
            tr.tp_fracs = [float(x) for x in (sig.tp_fracs or [])]
            tr.tp_hit = [False for _ in tr.tps]
            tr.initial_qty = float(q)
            tr.remaining_qty = float(q)
            tr.trail_mult = float(getattr(sig, "trailing_atr_mult", 0.0) or 0.0)
            tr.trail_period = int(getattr(sig, "trailing_atr_period", 14) or 14)
            ts_bars = int(getattr(sig, "time_stop_bars", 0) or 0)
            tr.time_stop_sec = int(ts_bars * 300)
        TRADES[("Bybit", symbol)] = tr

        ok = set_tp_sl_retry(symbol, tr.side, tr.tp_price, tr.sl_price)
        tr.tpsl_on_exchange = bool(ok)
        tr.tpsl_last_set_ts = now_s()
        if ok:
            tr.tpsl_manual_lock = False

        tp_txt = f"{tr.tp_price:.6f}" if tr.tp_price is not None else "runner"
        tg_trade(
            f"🔻 BREAKDOWN ENTRY [{TRADE_CLIENT.name}] {symbol} {sig.side}\n"
            f"entry≈{entry:.6f} TP={tp_txt} SL={tr.sl_price:.6f}\n"
            f"notional≈{notional_real:.2f}$ qty≈{q}\n"
            f"reason={sig.reason}"
        )


async def try_micro_scalper_entry_async(symbol: str, price: float):
    """Try micro scalper entry for a symbol (micro_scalper_v1)."""
    if not ENABLE_MICRO_SCALPER_TRADING:
        return
    if MICRO_SCALPER_ENGINE is None:
        return
    if not TRADE_ON or DRY_RUN:
        return
    if TRADE_CLIENT is None:
        return
    if symbol not in MICRO_SCALPER_SYMBOL_ALLOWLIST:
        return
    if get_trade("Bybit", symbol) is not None:
        return
    if MICRO_SCALPER_MAX_OPEN_TRADES > 0:
        open_ms = sum(
            1 for tr in TRADES.values()
            if getattr(tr, "strategy", "") == "micro_scalper_v1"
            and str(getattr(tr, "status", "")).upper() not in {"CLOSED", "ERROR"}
        )
        if open_ms >= MICRO_SCALPER_MAX_OPEN_TRADES:
            _diag_inc("micro_scalper_skip_max_open")
            return
    if not portfolio_can_open():
        _diag_inc("micro_scalper_skip_portfolio")
        return

    now = now_s()
    last = float(_MICRO_SCALPER_LAST_TRY.get(symbol, 0) or 0)
    if now - last < MICRO_SCALPER_TRY_EVERY_SEC:
        return
    _MICRO_SCALPER_LAST_TRY[symbol] = now
    _diag_inc("micro_scalper_try")

    try:
        sig = MICRO_SCALPER_ENGINE.signal(symbol, int(now * 1000), price)
    except Exception as e:
        log_error(f"micro_scalper signal error {symbol}: {e}")
        return
    if not sig:
        return

    side = "Buy" if sig.side == "long" else "Sell"
    entry = float(sig.entry)
    sl = float(sig.sl)
    tp = float(sig.tp)
    tp_r, sl_r = round_tp_sl_prices(symbol, side, entry, tp, sl)
    if tp_r is None or sl_r is None:
        return

    stop_pct = abs((float(sl_r) - float(entry)) / max(1e-12, float(entry))) * 100.0
    dyn_usd = calc_notional_usd_from_stop_pct(stop_pct, risk_mult=MICRO_SCALPER_RISK_MULT)
    if dyn_usd <= 0:
        return

    qty_floor, notional_real, reason = qty_floor_from_notional(symbol, dyn_usd, price)
    if qty_floor <= 0:
        return
    proposed_risk_usd = qty_floor * abs(float(entry) - float(sl_r))
    can_add, total_risk_pct, cap_risk_pct = portfolio_can_add_open_risk(proposed_risk_usd)
    if not can_add:
        tg_trade_throttled(
            f"portfolio_risk:micro_scalper:{symbol}",
            f"🟡 MICRO_SCALPER SKIP {symbol}: open-risk {total_risk_pct:.2f}% > cap {cap_risk_pct:.2f}%",
            3600,
        )
        return

    entry_lock = _get_symbol_entry_lock("Bybit", symbol)
    if entry_lock.locked():
        return
    async with entry_lock:
        if get_trade("Bybit", symbol) is not None:
            return
        if not portfolio_can_open():
            return
        ensure_leverage(symbol, BYBIT_LEVERAGE)
        _diag_inc("micro_scalper_entry")
        oid, q = TRADE_CLIENT.place_market(symbol, side, qty_floor, allow_quote_fallback=False)
        tr = TradeState(symbol=symbol, side=side, qty=q, entry_price_req=float(entry), entry_ts=now)
        tr.entry_order_id = oid
        tr.status = "PENDING_ENTRY"
        tr.strategy = "micro_scalper_v1"
        tr.avg = float(entry)
        tr.entry_price = float(entry)
        tr.entry_notional_usd = float(notional_real)
        tr.tp_price = float(tp_r)
        tr.sl_price = float(sl_r)
        tr.trail_mult = float(getattr(sig, "trailing_atr_mult", 0.0) or 0.0)
        tr.trail_period = int(getattr(sig, "trailing_atr_period", 14) or 14)
        ts_bars = int(getattr(sig, "time_stop_bars", 0) or 0)
        tr.time_stop_sec = int(ts_bars * 300)
        TRADES[("Bybit", symbol)] = tr
        ok = set_tp_sl_retry(symbol, tr.side, tr.tp_price, tr.sl_price)
        tr.tpsl_on_exchange = bool(ok)
        tr.tpsl_last_set_ts = now_s()
        tg_trade(
            f"⚡ MICRO ENTRY [{TRADE_CLIENT.name}] {symbol} {sig.side}\n"
            f"entry≈{entry:.6f} TP={tp_r:.6f} SL={sl_r:.6f}\n"
            f"notional≈{notional_real:.2f}$ qty≈{q}\n"
            f"reason={sig.reason}"
        )


async def try_support_reclaim_entry_async(symbol: str, price: float):
    """Try support reclaim long entry for a symbol (alt_support_reclaim_v1)."""
    if not ENABLE_SUPPORT_RECLAIM_TRADING:
        return
    if SUPPORT_RECLAIM_ENGINE is None:
        return
    if not TRADE_ON or DRY_RUN:
        return
    if TRADE_CLIENT is None:
        return
    if symbol not in SUPPORT_RECLAIM_SYMBOL_ALLOWLIST:
        return
    if get_trade("Bybit", symbol) is not None:
        return
    if SUPPORT_RECLAIM_MAX_OPEN_TRADES > 0:
        open_sr = sum(
            1 for tr in TRADES.values()
            if getattr(tr, "strategy", "") == "alt_support_reclaim_v1"
            and str(getattr(tr, "status", "")).upper() not in {"CLOSED", "ERROR"}
        )
        if open_sr >= SUPPORT_RECLAIM_MAX_OPEN_TRADES:
            _diag_inc("support_reclaim_skip_max_open")
            return
    if not portfolio_can_open():
        _diag_inc("support_reclaim_skip_portfolio")
        return

    now = now_s()
    last = float(_SUPPORT_RECLAIM_LAST_TRY.get(symbol, 0) or 0)
    if now - last < SUPPORT_RECLAIM_TRY_EVERY_SEC:
        return
    _SUPPORT_RECLAIM_LAST_TRY[symbol] = now
    _diag_inc("support_reclaim_try")

    try:
        sig = SUPPORT_RECLAIM_ENGINE.signal(symbol, int(now * 1000), price)
    except Exception as e:
        log_error(f"support_reclaim signal error {symbol}: {e}")
        return
    if not sig:
        return

    side = "Buy" if sig.side == "long" else "Sell"
    entry = float(sig.entry)
    sl = float(sig.sl)
    tp = float(sig.tp)
    tp_r, sl_r = round_tp_sl_prices(symbol, side, entry, tp, sl)
    if tp_r is None or sl_r is None:
        return

    stop_pct = abs((float(sl_r) - float(entry)) / max(1e-12, float(entry))) * 100.0
    dyn_usd = calc_notional_usd_from_stop_pct(stop_pct, risk_mult=SUPPORT_RECLAIM_RISK_MULT)
    if dyn_usd <= 0:
        return

    qty_floor, notional_real, reason = qty_floor_from_notional(symbol, dyn_usd, price)
    if qty_floor <= 0:
        return
    proposed_risk_usd = qty_floor * abs(float(entry) - float(sl_r))
    can_add, total_risk_pct, cap_risk_pct = portfolio_can_add_open_risk(proposed_risk_usd)
    if not can_add:
        tg_trade_throttled(
            f"portfolio_risk:support_reclaim:{symbol}",
            f"🟡 SUPPORT_RECLAIM SKIP {symbol}: open-risk {total_risk_pct:.2f}% > cap {cap_risk_pct:.2f}%",
            3600,
        )
        return

    entry_lock = _get_symbol_entry_lock("Bybit", symbol)
    if entry_lock.locked():
        return
    async with entry_lock:
        if get_trade("Bybit", symbol) is not None:
            return
        if not portfolio_can_open():
            return
        ensure_leverage(symbol, BYBIT_LEVERAGE)
        _diag_inc("support_reclaim_entry")
        oid, q = TRADE_CLIENT.place_market(symbol, side, qty_floor, allow_quote_fallback=False)
        tr = TradeState(symbol=symbol, side=side, qty=q, entry_price_req=float(entry), entry_ts=now)
        tr.entry_order_id = oid
        tr.status = "PENDING_ENTRY"
        tr.strategy = "alt_support_reclaim_v1"
        tr.avg = float(entry)
        tr.entry_price = float(entry)
        tr.entry_notional_usd = float(notional_real)
        tr.tp_price = float(tp_r)
        tr.sl_price = float(sl_r)
        tr.trail_mult = float(getattr(sig, "trailing_atr_mult", 0.0) or 0.0)
        tr.trail_period = int(getattr(sig, "trailing_atr_period", 14) or 14)
        TRADES[("Bybit", symbol)] = tr
        ok = set_tp_sl_retry(symbol, tr.side, tr.tp_price, tr.sl_price)
        tr.tpsl_on_exchange = bool(ok)
        tr.tpsl_last_set_ts = now_s()
        tg_trade(
            f"🟢 SUPPORT RECLAIM [{TRADE_CLIENT.name}] {symbol} LONG\n"
            f"entry≈{entry:.6f} TP={tp_r:.6f} SL={sl_r:.6f}\n"
            f"notional≈{notional_real:.2f}$ qty≈{q}\n"
            f"reason={sig.reason}"
        )


class _TS132Store:
    """Minimal store that TripleScreenV132Strategy expects for fetch_klines."""
    def __init__(self, symbol: str):
        self.symbol = symbol
    def fetch_klines(self, symbol: str, interval: str, limit: int):
        return fetch_klines(symbol, interval, limit)


async def try_ts132_entry_async(symbol: str, price: float):
    """Try Triple Screen v132 entry for a symbol."""
    if not ENABLE_TS132_TRADING:
        return
    if TS132_ENGINE is None:
        return
    if not TRADE_ON or DRY_RUN:
        return
    if TRADE_CLIENT is None:
        return
    if get_trade("Bybit", symbol) is not None:
        return
    if TS132_SYMBOLS and (symbol not in TS132_SYMBOLS):
        return
    if not portfolio_can_open():
        return

    now = now_s()
    last = int(_TS132_LAST_TRY.get(symbol, 0) or 0)
    if now - last < TS132_TRY_EVERY_SEC:
        return
    _TS132_LAST_TRY[symbol] = now
    _diag_inc("ts132_try")

    # Lazy create per-symbol strategy instance
    if symbol not in TS132_ENGINE:
        from archive.strategies_retired.triple_screen_v132 import TripleScreenV132Strategy
        TS132_ENGINE[symbol] = TripleScreenV132Strategy()
    strat = TS132_ENGINE[symbol]
    store = _TS132Store(symbol)

    try:
        sig = strat.maybe_signal(store, int(now * 1000), price, price, price, price, 0.0)
    except Exception as e:
        log_error(f"ts132 signal error {symbol}: {e}")
        return
    if not sig:
        return

    side = "Buy" if sig.side == "long" else "Sell"
    entry = float(sig.entry)
    sl = float(sig.sl)
    tp = float(sig.tp)

    tp_r, sl_r = round_tp_sl_prices(symbol, side, entry, tp, sl)
    if tp_r is None or sl_r is None:
        return

    stop_pct = abs((float(sl_r) - float(entry)) / max(1e-12, float(entry))) * 100.0
    dyn_usd = calc_notional_usd_from_stop_pct(stop_pct)
    if dyn_usd <= 0:
        tg_trade(f"🟡 TS132 SKIP {symbol}: stop={stop_pct:.2f}% -> notional too small")
        return

    qty_floor, notional_real, reason = qty_floor_from_notional(symbol, dyn_usd, price)
    if qty_floor <= 0:
        tg_trade(f"🟡 TS132 SKIP {symbol}: {reason} (need≈{dyn_usd:.2f}$)")
        return
    proposed_risk_usd = qty_floor * abs(float(entry) - float(sl_r))
    can_add, total_risk_pct, cap_risk_pct = portfolio_can_add_open_risk(proposed_risk_usd)
    if not can_add:
        tg_trade_throttled(
            f"portfolio_risk:ts132:{symbol}",
            f"🟡 TS132 SKIP {symbol}: open-risk {total_risk_pct:.2f}% > cap {cap_risk_pct:.2f}%",
            3600,
        )
        return

    ensure_leverage(symbol, BYBIT_LEVERAGE)
    _diag_inc("ts132_entry")
    oid, q = TRADE_CLIENT.place_market(symbol, side, qty_floor, allow_quote_fallback=False)

    tr = TradeState(
        symbol=symbol,
        side=side,
        qty=q,
        entry_price_req=float(entry),
        entry_ts=now,
    )
    tr.entry_order_id = oid
    tr.status = "PENDING_ENTRY"
    tr.strategy = "triple_screen_v132"
    tr.avg = float(entry)
    tr.entry_price = float(entry)
    tr.entry_notional_usd = float(notional_real)
    tr.tp_price = float(tp_r)
    tr.sl_price = float(sl_r)
    tr.initial_sl_price = float(sl_r)
    tr.be_trigger_rr = float(getattr(sig, "be_trigger_rr", 0.0) or 0.0)
    tr.be_lock_rr = float(getattr(sig, "be_lock_rr", 0.0) or 0.0)
    tr.trail_activate_rr = float(getattr(sig, "trail_activate_rr", 0.0) or 0.0)
    tr.trail_armed = tr.trail_activate_rr <= 0.0
    trail_mult = float(getattr(sig, "trailing_atr_mult", 0.0) or 0.0)
    if trail_mult > 0:
        tr.runner_enabled = True
        tr.tps = [float(tp)]
        tr.tp_fracs = [1.0]
        tr.tp_hit = [False]
        tr.initial_qty = float(q)
        tr.remaining_qty = float(q)
        tr.trail_mult = trail_mult
        tr.trail_period = int(getattr(sig, "trailing_atr_period", 14) or 14)
        ts_bars = int(getattr(sig, "time_stop_bars", 0) or 0)
        tr.time_stop_sec = int(ts_bars * 300)
    TRADES[("Bybit", symbol)] = tr

    ok = set_tp_sl_retry(symbol, tr.side, tr.tp_price, tr.sl_price)
    tr.tpsl_on_exchange = bool(ok)
    tr.tpsl_last_set_ts = now_s()
    if ok:
        tr.tpsl_manual_lock = False

    tg_trade(
        f"🟫 TS132 ENTRY [{TRADE_CLIENT.name}] {symbol} {sig.side}\n"
        f"entry≈{entry:.6f} TP={tr.tp_price:.6f} SL={tr.sl_price:.6f}\n"
        f"notional≈{notional_real:.2f}$ qty≈{q}\n"
        f"reason={sig.reason}"
    )


def try_bounce_entry(exch: str, sym: str, st: SymState, now: int, price: float):
    if not ENABLE_BOUNCE:
        return
    if exch != "Bybit":
        return
    if not TRADE_ON:
        return
    if get_trade(exch, sym) is not None:
        return
    if BOUNCE_SYMBOLS and (sym not in BOUNCE_SYMBOLS):
        return
    if not portfolio_can_open():
        return

    if now - getattr(st, "last_bounce_try", 0) < BOUNCE_TRY_EVERY_SEC:
        return
    
    st.last_bounce_try = now

    try:
        ob = get_sell_pressure_cached(sym)
        sig = BOUNCE_STRAT.try_signal(sym, price, orderbook_pressure=ob)
        if not sig:
            return
        # --- extra hard gates (не зависим от внутренностей BounceStrategy) ---
        try:
            br = float(getattr(sig, "breakout_risk", 0.0) or 0.0)
            pot = float(getattr(sig, "potential_pct", 0.0) or 0.0)
        except Exception:
            br, pot = 0.0, 0.0

        if br > float(BOUNCE_MAX_BREAKOUT_RISK):
            if BOUNCE_DEBUG:
                tg_trade(f"🟡 BOUNCE SKIP {sym}: breakout_risk {br:.2f} > {BOUNCE_MAX_BREAKOUT_RISK:.2f}")
            return

        if pot < float(BOUNCE_MIN_POTENTIAL_PCT):
            if BOUNCE_DEBUG:
                tg_trade(f"🟡 BOUNCE SKIP {sym}: potential {pot:.2f}% < {BOUNCE_MIN_POTENTIAL_PCT:.2f}%")
            return

        # если BounceSignal отдаёт эти флаги — тоже можно резать (опционально)
        if getattr(sig, "micro_trend_ok", True) is False:
            return
        if getattr(sig, "mtf_ok", True) is False:
            return

        # --- ужесточение: не лезем против EMA-тренда ---
        if BOUNCE_REQUIRE_TREND_MATCH and (st.ema_fast is not None) and (st.ema_slow is not None):
            if sig.side == "Buy" and not (st.ema_fast > st.ema_slow):
                return
            if sig.side == "Sell" and not (st.ema_fast < st.ema_slow):
                return

        lvl = float(sig.level.price)
        d = dist_pct(price, lvl)

        def _bdebug(decision: str, reason: str = "", **extra):
            row = {
                "ts": now,
                "symbol": sym,
                "price": f"{price:.10f}",
                "level": f"{lvl:.10f}",
                "kind": getattr(sig.level, "kind", ""),
                "tf": getattr(sig.level, "tf", ""),
                "side": sig.side,
                "dist_pct": f"{d:.4f}",
                "risk": f"{float(getattr(sig, 'breakout_risk', 0.0)):.3f}",
                "potential_pct": f"{float(getattr(sig, 'potential_pct', 0.0)):.3f}",
                "tp": f"{float(getattr(sig, 'tp_price', 0.0)):.10f}",
                "sl": f"{float(getattr(sig, 'sl_price', 0.0)):.10f}",
                "ob_pressure": f"{float(getattr(sig,'ob_pressure', 0.0)):.3f}",
                "atr_5m": f"{float(getattr(sig,'atr_5m', 0.0)):.3f}",
                "volume_factor": f"{float(getattr(sig,'volume_factor', 0.0)):.3f}",
                "false_breakout": str(bool(getattr(sig,'false_breakout', False))),
                "micro_trend_ok": str(bool(getattr(sig,'micro_trend_ok', True))),
                "mtf_ok": str(bool(getattr(sig,'mtf_ok', True))),
                "decision": decision,
                "reason": reason,
                "note": (getattr(sig, "note", "") or "").replace("\n", " "),
            }
            # доп. поля (stop_pct, dyn_usd, qty_*, cap_notional...) — если передали
            row.update(extra)
            log_bounce_debug(row)


        # Санити: уровень должен быть "рядом"
        # Для resistance: цена обычно рядом/ниже уровня; для support: рядом/выше уровня
        # Но главное — абсолютная дистанция, иначе это действительно похоже на рандом.
        too_far = abs(d) > float(BOUNCE_MAX_DIST_PCT)

        decision = "ENTER"
        reason = ""

        if too_far:
            decision = "SKIP"
            reason = "TOO_FAR"


        # Лог в CSV всегда (если BOUNCE_DEBUG=True)
        log_bounce_debug({
            "ts": now,
            "symbol": sym,
            "price": f"{price:.10f}",
            "level": f"{lvl:.10f}",
            "kind": getattr(sig.level, "kind", ""),
            "tf": getattr(sig.level, "tf", ""),
            "side": sig.side,
            "dist_pct": f"{d:.4f}",
            "risk": f"{float(getattr(sig, 'breakout_risk', 0.0)):.3f}",
            "potential_pct": f"{float(getattr(sig, 'potential_pct', 0.0)):.3f}",
            "tp": f"{float(getattr(sig, 'tp_price', 0.0)):.10f}",
            "sl": f"{float(getattr(sig, 'sl_price', 0.0)):.10f}",
            "decision": decision,
            "note": (getattr(sig, "note", "") or "").replace("\n", " "),
             "ob_pressure": f"{float(getattr(sig,'ob_pressure', 0.0)):.3f}",
            "atr_5m": f"{float(getattr(sig,'atr_5m', 0.0)):.3f}",
            "volume_factor": f"{float(getattr(sig,'volume_factor', 0.0)):.3f}",
            "false_breakout": str(bool(getattr(sig,'false_breakout', False))),
            "micro_trend_ok": str(bool(getattr(sig,'micro_trend_ok', True))),
            "mtf_ok": str(bool(getattr(sig,'mtf_ok', True))),
                    })

        # Плюс короткий DEBUG в телегу, чтобы руками сверять с TV
        if BOUNCE_DEBUG and BOUNCE_TG_LOGS and (BOUNCE_EXECUTE_TRADES or BOUNCE_TG_DEBUG_WHEN_LOG_ONLY):
            tg_trade(
                f"🧪 BOUNCE DEBUG {sym} {sig.side}  price={price:.6f}  lvl={lvl:.6f} "
                f"dist={d:+.3f}%  kind={sig.level.kind},{sig.level.tf}  risk={sig.breakout_risk:.2f}  decision={decision}"
            )

        if decision != "ENTER":
            return

        # Проверочный режим: только логируем, но не торгуем
        if not BOUNCE_EXECUTE_TRADES:
            if BOUNCE_LOG_ONLY and BOUNCE_TG_LOGS and BOUNCE_TG_DEBUG_WHEN_LOG_ONLY:
                tg_trade(f"🟡 BOUNCE LOG-ONLY (no trade): {sym} {sig.side} dist={d:+.3f}%")
            return

        tp_r, sl_r = round_tp_sl_prices(sym, sig.side, float(price), sig.tp_price, sig.sl_price)
        if tp_r is None or sl_r is None:
            return

        if str(sig.side).lower() == "buy":
            gross_move_pct = ((float(tp_r) - float(price)) / max(1e-12, float(price))) * 100.0
            risk_pct = ((float(price) - float(sl_r)) / max(1e-12, float(price))) * 100.0
        else:
            gross_move_pct = ((float(price) - float(tp_r)) / max(1e-12, float(price))) * 100.0
            risk_pct = ((float(sl_r) - float(price)) / max(1e-12, float(price))) * 100.0
        net_move_pct = gross_move_pct - float(BOUNCE_EST_ROUNDTRIP_COST_PCT)
        net_rr = net_move_pct / max(1e-12, risk_pct)
        if (
            gross_move_pct < float(BOUNCE_MIN_GROSS_MOVE_PCT)
            or net_move_pct < float(BOUNCE_MIN_NET_MOVE_PCT)
            or net_rr < float(BOUNCE_MIN_NET_RR)
        ):
            if BOUNCE_DEBUG and BOUNCE_TG_LOGS and (BOUNCE_EXECUTE_TRADES or BOUNCE_TG_DEBUG_WHEN_LOG_ONLY):
                tg_trade(
                    f"🟡 BOUNCE SKIP {sym}: weak economics gross={gross_move_pct:.2f}% "
                    f"net={net_move_pct:.2f}% rr={net_rr:.2f}"
                )
            return

        # размер позиции: риск % по дистанции до SL (УЖЕ округлённого)
        if USE_RISK_SIZING and (sl_r is not None):
            stop_pct = abs((float(sl_r) - float(price)) / max(1e-12, float(price))) * 100.0
            dyn_usd = calc_notional_usd_from_stop_pct(stop_pct)
            if dyn_usd <= 0:
                tg_trade(
                    f"🟡 BOUNCE SKIP {sym}: stop={stop_pct:.2f}% -> notional<min({MIN_NOTIONAL_USD}) "
                    f"при риске {RISK_PER_TRADE_PCT:.2f}%"
                )
                return
        else:
            tg_trade(f"🟡 BOUNCE SKIP {sym}: нет SL для risk sizing")
            return


        # --- FIX: minQty/step могут сломать риск. Считаем qty и НЕ даём коду его поднять ---
        meta = _get_meta(sym)
        min_qty = float(meta.get("minOrderQty") or 0.0)
        qty_step = float(meta.get("qtyStep") or 0.0)

        # хотим купить/продать на dyn_usd (USDT) → qty в базовой монете
        qty_raw = float(dyn_usd) / max(1e-12, float(price))

        # округляем ВНИЗ к шагу qtyStep (НЕ повышаем до minQty)
        step = qty_step if qty_step > 0 else 1.0
        d_step = Decimal(str(step))
        q_floor_dec = (Decimal(str(qty_raw)) / d_step).to_integral_value(rounding=ROUND_DOWN) * d_step
        qty_floor = float(q_floor_dec)

        # если после округления ниже minQty — пропускаем (депо/риск слишком маленькие)
        if qty_floor <= 0 or (min_qty and qty_floor < min_qty):
            decision = "SKIP"
            reason = "BELOW_MIN_QTY_AFTER_FLOOR"
            tg_trade(f"🟡 BOUNCE SKIP {sym}: qty<{min_qty} после округления (депо мал / risk-notional мал)")

            log_bounce_debug({
                "ts": now, "symbol": sym,
                "price": f"{price:.10f}", "level": f"{lvl:.10f}",
                "kind": getattr(sig.level, "kind", ""), "tf": getattr(sig.level, "tf", ""),
                "side": sig.side, "dist_pct": f"{d:.4f}",
                "risk": f"{float(getattr(sig,'breakout_risk', 0.0)):.3f}",
                "potential_pct": f"{float(getattr(sig,'potential_pct', 0.0)):.3f}",
                "tp": f"{float(getattr(sig,'tp_price', 0.0)):.10f}",
                "sl": f"{float(getattr(sig,'sl_price', 0.0)):.10f}",
                "ob_pressure": f"{float(getattr(sig,'ob_pressure', 0.0)):.3f}",
                "atr_5m": f"{float(getattr(sig,'atr_5m', 0.0)):.3f}",
                "volume_factor": f"{float(getattr(sig,'volume_factor', 0.0)):.3f}",
                "false_breakout": str(bool(getattr(sig,'false_breakout', False))),
                "micro_trend_ok": str(bool(getattr(sig,'micro_trend_ok', True))),
                "mtf_ok": str(bool(getattr(sig,'mtf_ok', True))),
                "stop_pct": f"{stop_pct:.4f}",
                "dyn_usd": f"{float(dyn_usd):.4f}",
                "qty_raw": f"{qty_raw:.10f}",
                "qty_floor": f"{qty_floor:.10f}",
                "min_qty": f"{min_qty:.10f}",
                "qty_step": f"{qty_step:.10f}",
                "notional_real": f"{(qty_floor*price):.6f}",
                "cap_notional": f"{max_notional_allowed(_get_effective_equity()):.4f}",
                "decision": decision,
                "reason": reason,
                "note": (getattr(sig, "note", "") or "").replace("\n"," "),
            })
            return


        notional_real = qty_floor * float(price)

        # cap notional (почти без плеча)
        cap = max_notional_allowed(_get_effective_equity())
        if CAP_NOTIONAL_TO_EQUITY and notional_real > cap + 1e-6:
            decision = "SKIP"
            reason = "CAP_NOTIONAL_EXCEEDED"
            tg_trade(f"🟡 BOUNCE SKIP {sym}: notional {notional_real:.2f} > cap {cap:.2f} (minQty/step)")

            log_bounce_debug({
                "ts": now, "symbol": sym,
                "price": f"{price:.10f}", "level": f"{lvl:.10f}",
                "kind": getattr(sig.level, "kind", ""), "tf": getattr(sig.level, "tf", ""),
                "side": sig.side, "dist_pct": f"{d:.4f}",
                "risk": f"{float(getattr(sig,'breakout_risk', 0.0)):.3f}",
                "potential_pct": f"{float(getattr(sig,'potential_pct', 0.0)):.3f}",
                "tp": f"{float(getattr(sig,'tp_price', 0.0)):.10f}",
                "sl": f"{float(getattr(sig,'sl_price', 0.0)):.10f}",
                "ob_pressure": f"{float(getattr(sig,'ob_pressure', 0.0)):.3f}",
                "atr_5m": f"{float(getattr(sig,'atr_5m', 0.0)):.3f}",
                "volume_factor": f"{float(getattr(sig,'volume_factor', 0.0)):.3f}",
                "false_breakout": str(bool(getattr(sig,'false_breakout', False))),
                "micro_trend_ok": str(bool(getattr(sig,'micro_trend_ok', True))),
                "mtf_ok": str(bool(getattr(sig,'mtf_ok', True))),
                "stop_pct": f"{stop_pct:.4f}",
                "dyn_usd": f"{float(dyn_usd):.4f}",
                "qty_raw": f"{qty_raw:.10f}",
                "qty_floor": f"{qty_floor:.10f}",
                "min_qty": f"{min_qty:.10f}",
                "qty_step": f"{qty_step:.10f}",
                "notional_real": f"{notional_real:.6f}",
                "cap_notional": f"{cap:.6f}",
                "decision": decision,
                "reason": reason,
                "note": (getattr(sig, "note", "") or "").replace("\n"," "),
            })
            return


        # ВАЖНО: для bounce НЕ вызываем place_market(), чтобы он не поднял размер через MIN_NOTIONAL_USD/minQty
        ensure_leverage(sym, BYBIT_LEVERAGE)

        if TRADE_CLIENT is None:
            oid = f"NOKEY-{sym}-{int(time.time())}"
            q = qty_floor
            tg_trade(f"🟡 нет TRADE_CLIENT, сделка не открыта: {sig.side} {sym} notional≈{notional_real:.2f}$ qty≈{q}")
        else:
            oid, q = TRADE_CLIENT.place_market(sym, sig.side, qty_floor, allow_quote_fallback=False)
        
        tr = TradeState(
            symbol=sym,
            side=sig.side,
            qty=q,
            entry_price_req=float(price),
            entry_ts=now,
        )
        tr.entry_order_id = oid
        tr.status = "PENDING_ENTRY"
        tr.strategy = "bounce"
        tr.avg = float(price)
        tr.entry_price = float(price)
        tr.leg1_done = True
        tr.tp_price, tr.sl_price = tp_r, sl_r
        TRADES[(exch, sym)] = tr


        # для логов/сообщения используем реальный notional
        dyn_usd = float(notional_real)


        # --- ставим TP/SL НА БИРЖЕ (с ретраями) ---
        ok = set_tp_sl_retry(sym, tr.side, tr.tp_price, tr.sl_price)
        tr.tpsl_on_exchange = bool(ok)
        tr.tpsl_last_set_ts = now_s()
        if ok:
            tr.tpsl_manual_lock = False   # если бот только что поставил — это точно AUTO



        acc_name = TRADE_CLIENT.name if TRADE_CLIENT else "NO_CLIENT"
        tg_trade(
            f"🟣 BOUNCE ENTRY [{acc_name}] {sym} {sig.side}\n"
            f"lvl={sig.level.price:.6f} ({sig.level.kind},{sig.level.tf}) dist={d:+.3f}% risk={sig.breakout_risk:.2f}\n"
            f"pot≈{sig.potential_pct:.2f}%  TP={tr.tp_price:.6f}  SL={tr.sl_price:.6f}\n"
            f"usd={dyn_usd:.2f} qty≈{q} px={price:.6f}\n"
            f"{sig.note}"
        )


    except Exception as e:
        log_error(f"bounce_entry fail {sym}: {e}")


def detect(exch: str, sym: str, st: SymState, now: int):
    
    if st.last_eval_ts == now:
        return
    st.last_eval_ts = now

    t0 = now - WINDOW_SEC
    tmid = now - WINDOW_SEC//2
    q_total = q_first = q_second = 0.0
    buys2 = sells2 = 0.0
    p0 = p1 = None
    n_trades = 0
    w_high = None
    w_low = None

    for (ts, p, qq, is_buy) in st.trades:
        if ts >= t0:
            n_trades += 1
            q_total += qq
            if ts < tmid:
                q_first += qq
            else:
                q_second += qq
                if is_buy:
                    buys2 += qq
                else:
                    sells2 += qq

    for (ts, p) in st.prices:
        if ts >= t0:
            if p0 is None:
                p0 = p
            p1 = p
            w_high = p if (w_high is None or p > w_high) else w_high
            w_low  = p if (w_low  is None or p < w_low) else w_low

    if p0 is None or p1 is None or p0 <= 0:
        return
    # ===== BOUNCE ENTRY (отскоки от уровней 1h/4h) — запускать всегда, даже если дальше будут return =====
    try:
        try_bounce_entry(exch, sym, st, now, p1)
    except Exception as _e:
        log_error(f"try_bounce_entry crash {sym}: {_e}")

    # Schedule live strategies before the legacy pump-detector gates below.
    # Otherwise weak/flat market structure can return early and starve breakout,
    # midterm, sloped, and other independent sleeves.
    if exch == "Bybit" and TRADE_ON and (not DRY_RUN):
        # ===== RANGE ENTRY (flat/range) =====
        if ENABLE_RANGE_TRADING:
            last = int(_RANGE_LAST_TRY.get(sym, 0) or 0)
            if now - last >= RANGE_TRY_EVERY_SEC:
                try:
                    asyncio.create_task(try_range_entry_async(sym, p1))
                except Exception as _e:
                    log_error(f"try_range_entry schedule fail {sym}: {_e}")

        # ===== INPLAY ENTRY (retest/runner) =====
        if ENABLE_INPLAY_TRADING:
            last = int(_INPLAY_LAST_TRY.get(sym, 0) or 0)
            if now - last >= INPLAY_TRY_EVERY_SEC:
                try:
                    asyncio.create_task(try_inplay_entry_async(sym, p1))
                except Exception as _e:
                    log_error(f"try_inplay_entry schedule fail {sym}: {_e}")

        # ===== BREAKOUT ENTRY (retest -> continue) =====
        if ENABLE_BREAKOUT_TRADING:
            last = int(_BREAKOUT_LAST_TRY.get(sym, 0) or 0)
            if now - last >= BREAKOUT_TRY_EVERY_SEC:
                try:
                    asyncio.create_task(try_breakout_entry_async(sym, p1))
                except Exception as _e:
                    log_error(f"try_breakout_entry schedule fail {sym}: {_e}")

        if ENABLE_MIDTERM_TRADING:
            last = int(_MIDTERM_LAST_TRY.get(sym, 0) or 0)
            if now - last >= MIDTERM_TRY_EVERY_SEC:
                try:
                    asyncio.create_task(try_midterm_entry_async(sym, p1))
                except Exception as _e:
                    log_error(f"try_midterm_entry schedule fail {sym}: {_e}")

        # ===== RETEST LEVELS ENTRY =====
        if ENABLE_RETEST_TRADING:
            last = int(_RETEST_LAST_TRY.get(sym, 0) or 0)
            if now - last >= RETEST_TRY_EVERY_SEC:
                try:
                    asyncio.create_task(try_retest_entry_async(sym, p1))
                except Exception as _e:
                    log_error(f"try_retest_entry schedule fail {sym}: {_e}")

        # ===== SLOPED CHANNEL ENTRY =====
        if ENABLE_SLOPED_TRADING:
            last = int(_SLOPED_LAST_TRY.get(sym, 0) or 0)
            if now - last >= SLOPED_TRY_EVERY_SEC:
                try:
                    _diag_inc("sloped_sched")
                    asyncio.create_task(try_sloped_entry_async(sym, p1))
                except Exception as _e:
                    log_error(f"try_sloped_entry schedule fail {sym}: {_e}")

        # ===== FLAT RESISTANCE FADE ENTRY =====
        if ENABLE_FLAT_TRADING:
            last = int(_FLAT_LAST_TRY.get(sym, 0) or 0)
            if now - last >= FLAT_TRY_EVERY_SEC:
                try:
                    _diag_inc("flat_sched")
                    asyncio.create_task(try_flat_entry_async(sym, p1))
                except Exception as _e:
                    log_error(f"try_flat_entry schedule fail {sym}: {_e}")

        # ===== BREAKDOWN SHORTS ENTRY =====
        if ENABLE_BREAKDOWN_TRADING:
            last = int(_BREAKDOWN_LAST_TRY.get(sym, 0) or 0)
            if now - last >= BREAKDOWN_TRY_EVERY_SEC:
                try:
                    _diag_inc("breakdown_sched")
                    asyncio.create_task(try_breakdown_entry_async(sym, p1))
                except Exception as _e:
                    log_error(f"try_breakdown_entry schedule fail {sym}: {_e}")

        # ===== MICRO SCALPER ENTRY =====
        if ENABLE_MICRO_SCALPER_TRADING and sym in MICRO_SCALPER_SYMBOL_ALLOWLIST:
            last = float(_MICRO_SCALPER_LAST_TRY.get(sym, 0) or 0)
            if now - last >= MICRO_SCALPER_TRY_EVERY_SEC:
                try:
                    _diag_inc("micro_scalper_sched")
                    asyncio.create_task(try_micro_scalper_entry_async(sym, p1))
                except Exception as _e:
                    log_error(f"try_micro_scalper_entry schedule fail {sym}: {_e}")

        # ===== SUPPORT RECLAIM LONGS ENTRY =====
        if ENABLE_SUPPORT_RECLAIM_TRADING and sym in SUPPORT_RECLAIM_SYMBOL_ALLOWLIST:
            last = float(_SUPPORT_RECLAIM_LAST_TRY.get(sym, 0) or 0)
            if now - last >= SUPPORT_RECLAIM_TRY_EVERY_SEC:
                try:
                    _diag_inc("support_reclaim_sched")
                    asyncio.create_task(try_support_reclaim_entry_async(sym, p1))
                except Exception as _e:
                    log_error(f"try_support_reclaim_entry schedule fail {sym}: {_e}")

        # ===== TRIPLE SCREEN v132 ENTRY =====
        if ENABLE_TS132_TRADING:
            last = int(_TS132_LAST_TRY.get(sym, 0) or 0)
            if now - last >= TS132_TRY_EVERY_SEC:
                try:
                    asyncio.create_task(try_ts132_entry_async(sym, p1))
                except Exception as _e:
                    log_error(f"try_ts132_entry schedule fail {sym}: {_e}")


    # ✅ ВАЖНО: сопровождение открытых bounce-сделок должно работать даже когда фильтры пампа "молчат"
    if TRADE_ON and exch == "Bybit":
        tr = get_trade(exch, sym)
        if (tr
            and getattr(tr, "strategy", "pump") in ("bounce", "range", "sloped_channel", "triple_screen_v132", "flat_resistance_fade")
            and getattr(tr, "status", None) == "OPEN"
            and p1 is not None
        ):
            POS_MANAGER.manage(exch, sym, st, tr, p1, buys2, sells2)

        # ===== INPLAY runner management (partials + trailing + time stop) =====
        if (tr
            and getattr(tr, "strategy", "") in ("inplay", "inplay_breakout", "btc_eth_midterm_pullback", "alt_inplay_breakdown_v1")
            and getattr(tr, "status", None) == "OPEN"
            and getattr(tr, "runner_enabled", False)
            and p1 is not None
        ):
            _manage_inplay_runner(sym, tr, p1)

    rng = max(1e-9, (w_high - w_low) if (w_high is not None and w_low is not None) else abs(p1 - p0))
    body_ratio = abs(p1 - p0) / rng
    ret = (p1 - p0) / p0 * 100.0
    up = ret >= 0
    abs_ret = abs(ret)

    imb = None
    if (buys2 + sells2) > 0:
        imb = buys2 / (buys2 + sells2)
    # --- фильтр качества ленты: пропускаем «дробные» сквизы без крупных принтов
    tq = trade_quality([x for x in st.trades if x[0] >= t0], q_total)

    base_list = list(st.win_hist)
    base_med  = statistics.median(base_list) if len(base_list) >= 7 else 0.0
    mad       = statistics.median([abs(x - base_med) for x in base_list]) if base_list else 0.0
    z_mad     = (q_total - base_med) / max(1e-9, 1.4826 * mad) if mad > 0 else (float("inf") if q_total > base_med * VBOOST else 0.0)

    st.win_hist.append(q_total)
    st.q_hist.append(q_total)
    if tq < 0.02:
        return
    # защита от мусорных/слишком больших
    if q_total > 5_000_000:
        return
    if ret > 9.0:
        return

    if q_total < MIN_WINDOW_QUOTE_USD or base_med <= 0 or n_trades < MIN_TRADES:
        if q_total > 80_000:
            print(f"[dbg] {exch} {sym} q={int(q_total)} Δ={ret:.2f}% trades={n_trades}")
        return

    accel_ok  = (q_second >= ACCEL_K * max(1.0, q_first))
    vboost_ok = (q_total  >= VBOOST  * base_med)
    z_ok      = (z_mad    >= Z_MAD_THR)
    ret_ok    = (abs_ret  >= DELTA_PCT_THR)
    body_ok   = (body_ratio >= BODY_RATIO_MIN)


    if REQUIRE_TWO_HITS:
        two_ok = (len(st.q_hist) >= 2) and (st.q_hist[-1] >= 1.2 * st.q_hist[-2])
    else:
        two_ok = True

    imb_ok = True
    if imb is not None:
        imb_ok = (imb >= IMBALANCE_THR) if up else (imb <= 1.0 - IMBALANCE_THR)

    atr = calc_atr_pct(list(st.highs), list(st.lows), list(st.closes))
    rsi = calc_rsi(list(st.closes))

    # 🔧 ATR больше не режет сигнал, используем его только в логах/для step_ok
    atr_ok = True
    step_ok = True
    if atr is not None:
        step_ok = (abs_ret >= max(DELTA_PCT_THR, MIN_ATR_MULT * atr))

    rsi_ok = (rsi is None) or ((rsi <= 70) if up else (rsi >= 30))


    ema_trend_flag = None
    if st.ema_fast is not None and st.ema_slow is not None:
        ema_trend_flag = (st.ema_fast > st.ema_slow)

    ctx5 = ctx_5m_move_pct(st, now)
    ctx_ok = True
    
    if ctx5 is not None:
        ctx_ok = (ctx5 >= CTX_MIN_MOVE) if up else (ctx5 <= -CTX_MIN_MOVE)
    # ---- 5m-фильтр: текущая 5-минутная свеча должна быть "палкой"
    prev5, cur5 = last_two_5m_bars(st, now)
    spike_ok = True
    if prev5 and cur5:
        # диапазон текущей 5m как минимум в 2 раза больше предыдущей
        if cur5["range"] <= 2.0 * prev5["range"]:
            spike_ok = False
        # свеча должна быть зелёной и с телом не меньше 50% диапазона
        if (not cur5["up"]) or (cur5["body"] < 0.5 * cur5["range"]):
            spike_ok = False
    # если данных по 5m мало (новый инструмент) — spike_ok оставляем True

    # near-miss лог: теперь печатаем ПОСЛЕ того, как все метрики уже посчитаны
    if NEAR_MISS_LOG and up:
        vboost = (q_total / max(1.0, base_med)) if base_med > 0 else 0.0
        accel  = q_second / max(1.0, q_first)
        if (_near(abs_ret, DELTA_PCT_THR, 0.03) or
            _near(vboost, VBOOST, 0.15) or
            _near(z_mad, Z_MAD_THR, 0.25) or
            _near(accel, ACCEL_K, 0.10) or
            (imb is not None and _near(imb, IMBALANCE_THR, 0.03))):
            print(
                f"[NEAR] {exch} {sym} ret={abs_ret:.3f}% vboost={vboost:.2f} "
                f"z={z_mad:.2f} accel={accel:.2f} tq={tq:.2f} "
                f"imb={(imb if imb is not None else float('nan')):.2f} "
                f"atr={atr} step_ok={step_ok} ema_trend_ok={ema_trend_flag} ctx={ctx5}"
            )


    # === отладка: показываем, что именно зарезало сигнал
    if DEBUG_WINDOWS and abs_ret >= 0.12:
        print(f"[FILTERS] {sym}: "
              f"ret_ok={ret_ok} vboost_ok={vboost_ok} z_ok={z_ok} "
              f"accel_ok={accel_ok} trades={n_trades} tq={tq:.2f} "
              f"atr_ok={atr_ok} step_ok={step_ok} rsi_ok={rsi_ok} "
              f"ema_trend_ok={ema_trend_flag} ctx_ok={ctx_ok} imb_ok={imb_ok}")



    open_win  = p0
    close_win = p1
    high_win  = w_high or max(p0, p1)
    low_win   = w_low  or min(p0, p1)
    patt = candle_pattern(open_win, close_win, high_win, low_win)

    # ---- не считаем «V-отскок» после свежего дампа как памп
    ANTI_V_LOOKBACK = 180  # сек — смотрим ~3 минуты контекста
    lo_t = now - ANTI_V_LOOKBACK
    rng_lo = None; rng_hi = None
    for tt, pp in st.ctx5m:
        if tt >= lo_t:
            rng_lo = pp if rng_lo is None else min(rng_lo, pp)
            rng_hi = pp if rng_hi is None else max(rng_hi, pp)

    anti_v_ok = True
    if rng_lo is not None and rng_hi is not None and rng_hi > rng_lo:
        # позиция старта окна внутри недавнего диапазона (0=низ, 1=верх)
        start_pos = (open_win - rng_lo) / (rng_hi - rng_lo)
        # пред-окно (20c до t0): не должно быть сильного слива
        pre_t = t0 - WINDOW_SEC
        pre_p0 = pre_p1 = None
        for (tt, pp) in st.prices:
            if pre_t <= tt < t0:
                if pre_p0 is None: pre_p0 = pp
                pre_p1 = pp
        pre_ret = ((pre_p1 - pre_p0) / pre_p0 * 100.0) if (pre_p0 and pre_p1 and pre_p0>0) else 0.0

        # правило: если стартуем из нижних 35% диапазона И до окна был слив ≤ -1.6%,
        # то это «отскок после дампа», НЕ считаем пампом (пока не пробьём 5м-хай).
        anti_v_ok = not (start_pos <= 0.35 and pre_ret <= -1.6)

    # ---- требуем расширение относительно предыдущего 5м-контекста (до начала окна)
    prev5_t0 = now - CTX_5M_SEC
    prev_high = None
    for tt, pp in st.ctx5m:
        if prev5_t0 <= tt < t0:         # только до начала текущего окна!
            prev_high = pp if prev_high is None else max(prev_high, pp)
    expansion_ok = True
    if prev_high is not None and prev_high > 0:
        expansion_ok = (high_win >= prev_high * (1 + EXPANSION_MIN_PCT/100.0))

    # ---- требуем закрытие ближе к хаям окна (а не просто "перекрыли красную")
    topclose_ok = True
    if high_win is not None and low_win is not None and high_win > low_win:
        topclose_ok = ((high_win - close_win) <= CLOSE_IN_TOP_FRAC * (high_win - low_win))


    # ---- определяем "сильный памп"
    strong_pump = (
        up
        and abs_ret >= STRONG_RET_THR
        and q_total >= max(STRONG_MIN_QUOTE, STRONG_VBOOST * base_med)
        and (q_second >= STRONG_ACCEL * max(1.0, q_first))
        and z_mad >= STRONG_ZMAD
        and (ctx5 is not None and ctx5 >= STRONG_CTX_MIN)
        and expansion_ok and topclose_ok
        and spike_ok
    )

    # ===== ПАМП =====

    if (up and accel_ok and vboost_ok and z_ok and ret_ok and step_ok and body_ok
        and imb_ok and rsi_ok and two_ok and ctx_ok and anti_v_ok):



        if now - st.last_alert >= COOLDOWN_SEC:
            st.last_alert = now
            st.last_pump = {
                "t0": now,
                "peak": p1,
                "base": p0,
                "active_until": now + REV_WINDOW_SEC,
                "strong": bool(strong_pump),   # запоминаем, был ли памп сильным
            }

            pair = f"{base_from_usdt(sym)}/USDT"
            label = "⚡️ ПАМП (STRONG)" if strong_pump else "⚡️ ПАМП"
            msg = (
                f"{label} {WINDOW_SEC}s [UP]\n"
                f"Биржа: {exch}\nПара: {sym} ({pair})\n"
                f"Δ% окна: {ret:.2f}% | trades={n_trades} | body={body_ratio:.2f}\n"
                f"Quote: {int(q_total)} USDT (×{q_total/base_med:.1f}, zMAD={z_mad:.1f})\n"
                f"Accel: {q_second/max(1.0,q_first):.2f}  Imb2: {imb:.2f}\n"
                f"ATR%:{atr:.3f}  RSI:{rsi:.1f}  Trend(EMA20>60):{ema_trend_flag}  5mΔ:{(ctx5 if ctx5 is not None else float('nan')):.2f}%\n"
                f"Pattern: {patt or '—'}"
            )
            tg_send(msg)
            log_signal({
                "ts": now, "exchange": exch, "symbol": sym, "pair": pair, "type": "PUMP",
                "delta_pct": f"{ret:.4f}", "quote_usd": int(q_total),
                "x_to_med": f"{q_total/base_med:.2f}", "zmad": f"{z_mad:.2f}",
                "trades": n_trades, "body": f"{body_ratio:.2f}", "imb2": f"{(imb if imb is not None else float('nan')):.2f}",
                "atr_pct": f"{(atr if atr is not None else float('nan')):.4f}",
                "rsi": f"{(rsi if rsi is not None else float('nan')):.2f}",
                "ema_fast_gt_slow": ema_trend_flag,
                "ctx5m_pct": f"{(ctx5 if ctx5 is not None else float('nan')):.2f}",
                "pattern": (("STRONG " if strong_pump else "") + (patt or ""))
            })
        else:
            if st.last_pump and now <= st.last_pump["active_until"]:
                st.last_pump["peak"] = max(st.last_pump["peak"], p1)


    # ===== РАЗВОРОТ =====
    if st.last_pump and now <= st.last_pump["active_until"]:
        peak = st.last_pump["peak"]
        drop = (peak - p1) / max(1e-9, peak) * 100.0
        strong_flag = bool(st.last_pump.get("strong", False))

        exhaust_data = EXHAUST_ANALYZER.analyze(
            st=st, peak_price=peak, cur_price=p1,
            buys2=buys2, sells2=sells2, q_total=q_total, base_med=base_med
        )

        ob_pressure = get_sell_pressure_cached(sym) if exch == "Bybit" else 0.5
        sell_dom_ok = (sells2 + buys2) > 0 and (sells2 / (sells2 + buys2)) >= 0.54

        ob_gate     = 0.48
        need_score  = max(2, ENTRY_TRIGGER.need_score)
        drop_needed = REV_DROP_PCT_NORMAL

        if strong_flag:
            ob_gate     = 0.40
            need_score  = 2
            drop_needed = REV_DROP_PCT_STRONG

        ema_gate_ok = (
            (st.ema_fast is not None and st.ema_slow is not None and st.ema_fast < st.ema_slow)
        )


        should_short = ENTRY_TRIGGER.should_short(
            exhaust_data, ema_gate_ok, ob_pressure,
            need_score=need_score, ob_threshold=ob_gate, sell_dom_ok=sell_dom_ok
        )

        if strong_flag and drop >= drop_needed and (should_short or sell_dom_ok):
            pair = f"{base_from_usdt(sym)}/USDT"

            # алертим ОДИН раз
            if not st.last_pump.get("rev_sent"):
                st.last_pump["rev_sent"] = True
                tg_send(
                    f"↘️ Разворот после пампа\n"
                    f"Биржа: {exch}\nПара: {sym} ({pair})\n"
                    f"Откат: {drop:.2f}%  sell_imb={(sells2/(buys2+sells2) if (buys2+sells2)>0 else float('nan')):.2f}\n"
                    f"score={exhaust_data['score']} ema_ok={ema_gate_ok} ob={ob_pressure:.2f}"
                )
                log_signal({
                    "ts": now, "exchange": exch, "symbol": sym, "pair": pair, "type": "REVERSAL",
                    "delta_pct": f"-{drop:.4f}", "quote_usd": int(q_total),
                    "x_to_med": f"{q_total/max(1e-9,base_med):.2f}", "zmad": f"{z_mad:.2f}",
                    "trades": n_trades, "body": f"{body_ratio:.2f}",
                })

            can_enter = (
                ENABLE_PUMP_FADE_TRADING
                and
                TRADE_ON and exch == "Bybit"
                and portfolio_can_open()
                and (get_trade(exch, sym) is None)
            )

            if can_enter:
                # риск 1%: используем SL_PCT как стоп в процентах от entry/avg
                if USE_RISK_SIZING:
                    dyn_usd = calc_notional_usd_from_stop_pct(float(SL_PCT))
                    if dyn_usd <= 0:
                        tg_trade(f"🟡 REV SKIP {sym}: SL={SL_PCT:.2f}% -> notional<min({MIN_NOTIONAL_USD}) при риске {RISK_PER_TRADE_PCT:.2f}%")
                        return
                else:
                    dyn_usd = max(MIN_NOTIONAL_USD, 10.0)

                oid, q = place_market(sym, "Sell", dyn_usd)

                tr = TradeState(
                    symbol=sym,
                    side="Sell",
                    qty=q,
                    entry_price_req=float(p1),
                    entry_ts=now,
                )
                tr.entry_order_id = oid
                tr.status = "PENDING_ENTRY"
                tr.strategy = "pump_fade"
                tr.avg = float(p1)
                tr.entry_price = float(p1)
                tr.leg1_done = True
                # рассчитать TP/SL (для Sell и Buy)
                avg = float(tr.avg)

                if tr.side == "Sell":
                    tp_raw = avg * (1.0 - TP_PCT / 100.0)
                    sl_raw = avg * (1.0 + SL_PCT / 100.0)
                else:
                    tp_raw = avg * (1.0 + TP_PCT / 100.0)
                    sl_raw = avg * (1.0 - SL_PCT / 100.0)

                tr.tp_price, tr.sl_price = round_tp_sl_prices(sym, tr.side, avg, tp_raw, sl_raw)

                TRADES[(exch, sym)] = tr

                # ставим TP/SL на бирже с ретраями
                ok = set_tp_sl_retry(sym, tr.side, tr.tp_price, tr.sl_price)
                tr.tpsl_on_exchange = bool(ok)
                tr.tpsl_last_set_ts = now_s()
                if ok:
                    tr.tpsl_manual_lock = False


                acc_name = TRADE_CLIENT.name if TRADE_CLIENT else "NO_CLIENT"
                tg_trade(
                    f"🟣 PUMP_FADE ENTRY [{acc_name}] {sym}\n"
                    f"usd={dyn_usd:.2f} qty≈{q} lev={BYBIT_LEVERAGE}x\n"
                    f"px={p1:.6f} TP={tr.tp_price:.6f} SL={tr.sl_price:.6f}"
                )

                st.last_pump = None

    # ===== СОПРОВОЖДЕНИЕ =====
    if TRADE_ON and exch == "Bybit":
        tr = get_trade(exch, sym)
        if tr and tr.qty > 0 and p1 is not None:

            # ✅ Bounce: без DCA, просто менеджим TP/SL
            if getattr(tr, "strategy", "pump") in ("bounce", "range"):
                return


            # Pump-fade (у тебя это шорт): DCA только для Sell
            if tr.side == "Sell":
                up_from_entry_pct = (p1 / tr.avg - 1.0) * 100.0
                need_dca = (not tr.leg2_done) and (
                    (up_from_entry_pct >= DCA_ENTRY_UP_PCT) or
                    (st.last_pump and "peak" in st.last_pump and p1 >= st.last_pump["peak"] * (1 + DCA_BREAK_PEAK_PCT/100.0))
                )

                if need_dca:
                    dyn_usd2 = calc_leg_usd_half_equity() if USE_HALF_EQUITY_PER_TRADE else min(calc_position_usd(3, atr), 15.0)

                    try:
                        if TRADE_CLIENT and not DRY_RUN:
                            wb = TRADE_CLIENT.wallet_balance()
                            row = ((wb.get("result") or {}).get("list") or [{}])[0]
                            avail = float(row.get("availableBalance") or row.get("totalAvailableBalance") or 0.0)
                            need_margin2 = dyn_usd2 / max(1.0, float(BYBIT_LEVERAGE))
                            if avail + 1e-6 < need_margin2 * 0.98:
                                tg_trade(f"🟡 Пропустил DCA: мало маржи {avail:.2f} < {need_margin2:.2f} (leg2 {dyn_usd2:.2f} @ {BYBIT_LEVERAGE}x)")
                                need_dca = False
                    except Exception as _e:
                        log_error(f"avail check fail (leg2): {_e}")

                    if need_dca:
                        oid2, q2 = place_market(sym, "Sell", dyn_usd2)
                        tr.avg = _update_avg(tr.avg, tr.qty, p1, q2)
                        tr.qty += q2
                        tr.leg2_done = True
                        # после изменения avg/qty пересчитываем TP/SL и обновляем на бирже
                        tp_raw = tr.avg * (1.0 - TP_PCT / 100.0)
                        sl_raw = tr.avg * (1.0 + SL_PCT / 100.0)
                        tr.tp_price, tr.sl_price = round_tp_sl_prices(sym, tr.side, tr.avg, tp_raw, sl_raw)
                        ok = set_tp_sl_retry(sym, tr.side, tr.tp_price, tr.sl_price)
                        tr.tpsl_on_exchange = bool(ok)
                        tr.tpsl_last_set_ts = now_s()
                        if ok:
                            tr.tpsl_manual_lock = False



                        tg_send(f"{'[DRYRUN] ' if DRY_RUN else ''}🟣 SHORT {sym}: leg2 {dyn_usd2:.2f} USDT, qty+={q2}, new_avg≈{tr.avg:.6f}")

            # финальный менеджмент (TP/SL и т.д.)
            POS_MANAGER.manage(exch, sym, st, tr, p1, buys2, sells2)


# =========================== WS BYBIT ===========================
def _recompute_universe_from_symbols(syms: list[str], *, notify: bool = True) -> None:
    global BOUNCE_SYMBOLS
    global INPLAY_SYMBOLS
    global BREAKOUT_SYMBOLS
    global RETEST_SYMBOLS
    global MIDTERM_ACTIVE_SYMBOLS
    global LAST_UNIVERSE_REFRESH_TS

    eq_eff = 0.0
    try:
        eq_eff = float(_get_effective_equity() or 0.0)
    except Exception:
        eq_eff = 0.0
    if eq_eff <= 0 and BOT_CAPITAL_USD:
        try:
            eq_eff = float(BOT_CAPITAL_USD)
        except Exception:
            pass

    cap = max_notional_allowed(eq_eff)
    eligible: list[str] = []
    for s in syms:
        try:
            m = _get_meta(s)
            min_qty = float(m.get("minOrderQty") or 0.0)
            last_px = float(_BYBIT_LAST.get(s) or 0.0)
            if min_qty <= 0 or last_px <= 0:
                continue
            min_notional = min_qty * last_px
            if min_notional <= cap + 1e-9:
                eligible.append(s)
        except Exception:
            continue

    base_filtered = _apply_symbol_filters(eligible)
    bounce_filtered = _apply_symbol_filters(base_filtered, strategy="bounce")
    inplay_filtered = _apply_symbol_filters(base_filtered, strategy="inplay")
    breakout_filtered = _apply_symbol_filters(base_filtered, strategy="breakout")
    if BREAKOUT_SYMBOL_ALLOWLIST:
        breakout_filtered = [s for s in breakout_filtered if s in BREAKOUT_SYMBOL_ALLOWLIST]
    if BREAKOUT_SYMBOL_DENYLIST:
        breakout_filtered = [s for s in breakout_filtered if s not in BREAKOUT_SYMBOL_DENYLIST]
    retest_filtered = _apply_symbol_filters(base_filtered, strategy="retest")

    BOUNCE_SYMBOLS = set(bounce_filtered[:BOUNCE_TOP_N])
    INPLAY_SYMBOLS = set(inplay_filtered[:max(1, int(INPLAY_TOP_N))])
    BREAKOUT_SYMBOLS = set(breakout_filtered[:max(1, int(BREAKOUT_TOP_N))])
    RETEST_SYMBOLS = set(retest_filtered[:max(1, int(RETEST_TOP_N))])
    MIDTERM_ACTIVE_SYMBOLS = {s for s in base_filtered if s in MIDTERM_SYMBOLS}
    LAST_UNIVERSE_REFRESH_TS = int(time.time())

    print(f"[filters] cap≈{cap:.2f} | eligible={len(eligible)}/{len(syms)} | base={len(base_filtered)} | breakout={len(BREAKOUT_SYMBOLS)}")
    if notify:
        if ENABLE_BREAKOUT_TRADING:
            tg_trade(f"🧩 breakout-universe: using={len(BREAKOUT_SYMBOLS)} (top {BREAKOUT_TOP_N})")
        if ENABLE_INPLAY_TRADING:
            tg_trade(f"🧩 inplay-universe: using={len(INPLAY_SYMBOLS)} (top {INPLAY_TOP_N})")
        if ENABLE_RETEST_TRADING:
            tg_trade(f"🧩 retest-universe: using={len(RETEST_SYMBOLS)} (top {RETEST_TOP_N})")
        if ENABLE_MIDTERM_TRADING:
            tg_trade(f"🧩 midterm-universe: using={len(MIDTERM_ACTIVE_SYMBOLS)} ({','.join(sorted(MIDTERM_ACTIVE_SYMBOLS))})")
        if ENABLE_SLOPED_TRADING:
            sloped_symbols = sorted(_parse_symbol_csv(os.getenv("ASC1_SYMBOL_ALLOWLIST", "")))
            if sloped_symbols:
                tg_trade(f"🧩 sloped-universe: using={len(sloped_symbols)} ({','.join(sloped_symbols)})")
            else:
                tg_trade("🧩 sloped-universe: using=dynamic (allowlist unset)")
        if ENABLE_FLAT_TRADING:
            flat_symbols = sorted(_parse_symbol_csv(os.getenv("ARF1_SYMBOL_ALLOWLIST", "")))
            if flat_symbols:
                tg_trade(f"🧩 flat-universe: using={len(flat_symbols)} ({','.join(flat_symbols)})")
            else:
                tg_trade("🧩 flat-universe: using=dynamic (allowlist unset)")
        if ENABLE_BREAKDOWN_TRADING:
            breakdown_symbols = sorted(_parse_symbol_csv(os.getenv("BREAKDOWN_SYMBOL_ALLOWLIST", "")))
            if breakdown_symbols:
                tg_trade(f"🧩 breakdown-universe: using={len(breakdown_symbols)} ({','.join(breakdown_symbols)})")
            else:
                tg_trade("🧩 breakdown-universe: using=dynamic (allowlist unset)")
        if ENABLE_RANGE_TRADING and BOUNCE_TG_LOGS:
            tg_trade(f"🧩 bounce-universe: using={len(BOUNCE_SYMBOLS)} (top {BOUNCE_TOP_N})")


async def symbol_filters_loop():
    """Optional periodic rebuild + in-memory universe refresh without bot restart."""
    if FILTERS_AUTO_REFRESH_SEC <= 0:
        return
    while True:
        try:
            if FILTERS_AUTO_BUILD and FILTERS_AUTO_BUILD_SEC > 0:
                now = int(time.time())
                if now - int(LAST_FILTER_BUILD_TS or 0) >= int(FILTERS_AUTO_BUILD_SEC):
                    ok, msg = _build_symbol_filters()
                    if ok:
                        print("[filters] auto build ok")
                    else:
                        log_error(f"filters auto build failed: {msg}")
            syms = bybit_symbols(TOP_N_BYBIT)
            _recompute_universe_from_symbols(syms, notify=False)
        except Exception as e:
            log_error(f"symbol_filters_loop crash: {e}")
        await asyncio.sleep(max(60, int(FILTERS_AUTO_REFRESH_SEC)))


async def bybit_ws():
    url = "wss://stream.bybit.com/v5/public/linear"
    syms = bybit_symbols(TOP_N_BYBIT)
    _recompute_universe_from_symbols(syms, notify=True)


    print(f"[bybit] got {len(syms)} symbols from REST")
    topics = [f"publicTrade.{s}" for s in syms]

    SHARD_SIZE  = int(os.getenv("BYBIT_WS_SHARD_SIZE", "40"))
    BATCH_SIZE  = int(os.getenv("BYBIT_WS_BATCH_SIZE", "6"))
    BATCH_DELAY = float(os.getenv("BYBIT_WS_BATCH_DELAY", "1.8"))
    START_STAGGER = float(os.getenv("BYBIT_WS_START_STAGGER", "2.0"))
    WS_PING_INTERVAL = float(os.getenv("BYBIT_WS_PING_INTERVAL", "20"))
    WS_PING_TIMEOUT = float(os.getenv("BYBIT_WS_PING_TIMEOUT", "60"))
    WS_OPEN_TIMEOUT = float(os.getenv("BYBIT_WS_OPEN_TIMEOUT", "60"))
    WS_CLOSE_TIMEOUT = float(os.getenv("BYBIT_WS_CLOSE_TIMEOUT", "10"))
    WS_RECONNECT_MIN = max(1.0, float(os.getenv("BYBIT_WS_RECONNECT_MIN_SEC", "5")))
    WS_RECONNECT_MAX = max(WS_RECONNECT_MIN, float(os.getenv("BYBIT_WS_RECONNECT_MAX_SEC", "90")))
    WS_RECONNECT_JITTER = max(0.0, float(os.getenv("BYBIT_WS_RECONNECT_JITTER_SEC", "2.5")))

    shards = [topics[i:i+SHARD_SIZE] for i in range(0, len(topics), SHARD_SIZE)]

    async def run_one(shard_args: List[str], shard_id: int):
        backoff = float(WS_RECONNECT_MIN)
        first_connect = True
        while True:
            try:
                if first_connect:
                    await asyncio.sleep(START_STAGGER * shard_id + random.uniform(0, 1.0))
                    first_connect = False
                else:
                    await asyncio.sleep(random.uniform(0.2, 1.2))
                print(f"[bybit] shard {shard_id} connecting... ({len(shard_args)} topics)")

                async with websockets.connect(
                    url,
                    ping_interval=WS_PING_INTERVAL,
                    ping_timeout=WS_PING_TIMEOUT,
                    open_timeout=WS_OPEN_TIMEOUT,
                    close_timeout=WS_CLOSE_TIMEOUT,
                    max_queue=None,
                    max_size=None,   # <-- ВАЖНО: добавить
                ) as ws:
                    print(f"[bybit] shard {shard_id} CONNECTED ✅")
                    _diag_inc("ws_connect")
                    backoff = float(WS_RECONNECT_MIN)

                    for i in range(0, len(shard_args), BATCH_SIZE):
                        batch = shard_args[i:i+BATCH_SIZE]
                        await ws.send(json.dumps({"op": "subscribe", "args": batch}))
                        print(f"[bybit] shard {shard_id} subscribed: {batch}")
                        await asyncio.sleep(BATCH_DELAY + random.uniform(0, 0.6))

                    while True:
                        raw = await ws.recv()
                        MSG_COUNTER["Bybit"] = MSG_COUNTER.get("Bybit", 0) + 1

                        msg = json.loads(raw)
                        topic = msg.get("topic", "")
                        data = msg.get("data")
                        if not topic or not data:
                            continue

                        m = _bybit_sym_re.search(topic)
                        if not m:
                            continue

                        sym = m.group(1)
                        st = S("Bybit", sym)
                        ts = now_s()

                        for tr in data:
                            t = int(tr["T"] // 1000)
                            p = float(tr["p"])
                            v = float(tr["v"])
                            is_buy = (tr.get("S") == "Buy")
                            qq = p * v

                            st.trades.append((t, p, qq, is_buy))
                            st.prices.append((t, p))

                            o = st.closes[-1] if len(st.closes) else p
                            st.highs.append(max(p, o))
                            st.lows.append(min(p, o))
                            st.closes.append(p)
                            st.ema_fast = ema_val(st.ema_fast, p, EMA_FAST)
                            st.ema_slow = ema_val(st.ema_slow, p, EMA_SLOW)
                            st.ctx5m.append((t, p))

                        trim(st, ts)
                        detect("Bybit", sym, st, ts)

            except (TimeoutError, asyncio.TimeoutError) as e:
                # это как раз "timed out during opening handshake"
                _diag_inc("ws_handshake_timeout")
                _diag_inc("ws_disconnect")
                _diag_inc("ws_disconnect_timeout")
                print(f"[bybit] shard {shard_id} handshake timeout; retry in ~{backoff}s")
                log_error(f"BYBIT shard {shard_id} handshake timeout: {repr(e)}")
                await asyncio.sleep(backoff + random.uniform(0, WS_RECONNECT_JITTER))
                backoff = min(backoff * 1.7, WS_RECONNECT_MAX)

            except InvalidStatus as e:
                _diag_inc("ws_disconnect")
                _diag_inc("ws_disconnect_invalid_status")
                print(f"[bybit] shard {shard_id} InvalidStatus: {repr(e)}")
                log_error(f"BYBIT InvalidStatus shard {shard_id}: {repr(e)}")
                await asyncio.sleep(min(300.0, WS_RECONNECT_MAX * 2.0))

            except (ConnectionClosedError, ConnectionClosedOK) as e:
                # Typical transient WS disconnects; keep logs concise and reconnect fast.
                _diag_inc("ws_disconnect")
                _diag_inc("ws_disconnect_closed")
                print(f"[bybit] shard {shard_id} disconnected(closed): {repr(e)}; retry in ~{backoff}s")
                log_error(f"BYBIT shard {shard_id} disconnected(closed): {repr(e)}")
                await asyncio.sleep(backoff + random.uniform(0, WS_RECONNECT_JITTER))
                backoff = min(backoff * 1.7, WS_RECONNECT_MAX)

            except (ConnectionResetError, OSError) as e:
                _diag_inc("ws_disconnect")
                _diag_inc("ws_disconnect_oserror")
                print(f"[bybit] shard {shard_id} disconnected(oserror): {repr(e)}; retry in ~{backoff}s")
                log_error(f"BYBIT shard {shard_id} disconnected(oserror): {repr(e)}")
                await asyncio.sleep(backoff + random.uniform(0, WS_RECONNECT_JITTER))
                backoff = min(backoff * 1.7, WS_RECONNECT_MAX)

            except Exception as e:
                _diag_inc("ws_disconnect")
                _diag_inc("ws_disconnect_other")
                print(f"[bybit] shard {shard_id} ERROR: {repr(e)}")
                print(traceback.format_exc())
                log_error(f"BYBIT shard {shard_id} crash: {repr(e)}")
                await asyncio.sleep(backoff + random.uniform(0, WS_RECONNECT_JITTER))
                backoff = min(backoff * 1.7, WS_RECONNECT_MAX)


    tasks = [asyncio.create_task(run_one(chunk, i)) for i, chunk in enumerate(shards)]
    await asyncio.gather(*tasks)

# =========================== BINANCE WS ===========================
def binance_symbols(top_n: int) -> List[str]:
    ei = requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo", timeout=15)
    ei.raise_for_status()
    lst = [s for s in ei.json()["symbols"]
           if s.get("quoteAsset")=="USDT" and s.get("contractType")=="PERPETUAL" and s.get("status")=="TRADING"]
    t = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=15).json()
    t24 = {x["symbol"]: float(x.get("quoteVolume",0) or 0) for x in t}
    lst = [s for s in lst if t24.get(s["symbol"],0) >= MIN_24H_TURNOVER]
    lst.sort(key=lambda s: t24.get(s["symbol"],0), reverse=True)
    syms = [s["symbol"] for s in lst]
    return syms if top_n is None else syms[:top_n]

def binance_stream_urls(syms, shard_size=160):
    urls = []
    for i in range(0, len(syms), shard_size):
        chunk = syms[i:i+shard_size]
        streams = "/".join([f"{s.lower()}@aggTrade" for s in chunk])
        urls.append(f"wss://fstream.binance.com/stream?streams={streams}")
    return urls

async def binance_ws():
    syms = binance_symbols(TOP_N_BINANCE)
    urls = binance_stream_urls(syms, shard_size=160)
    async def run_one(url, name):
        backoff = 3
        while True:
            try:
                async with websockets.connect(
                    url,
                    ping_interval=PING_INTERVAL,
                    ping_timeout=45,
                    close_timeout=5,
                    max_queue=None
                ) as ws:
                    backoff = 3
                    while True:
                        wrap = json.loads(await ws.recv())
                        if "stream" not in wrap or "data" not in wrap:
                            continue
                        stream = wrap["stream"]
                        sym = stream.split("@", 1)[0].upper()
                        d = wrap["data"]
                        ts = now_s()
                        st = S("Binance", sym)
                        p = float(d["p"]); q = float(d["q"]); is_buy = (not d.get("m", False))
                        t = int(d.get("T", d.get("E", ts)) // 1000); qq = p * q
                        st.trades.append((t, p, qq, is_buy)); st.prices.append((t, p))
                        o = st.closes[-1] if len(st.closes) else p
                        st.highs.append(max(p, o)); st.lows.append(min(p, o)); st.closes.append(p)
                        st.ema_fast = ema_val(st.ema_fast, p, EMA_FAST)
                        st.ema_slow = ema_val(st.ema_slow, p, EMA_SLOW)
                        st.ctx5m.append((t, p))
                        trim(st, ts)
                        detect("Binance", sym, st, ts)
            except Exception as e:
                print(f"BINANCE shard {name} reconnect in {backoff}s:", repr(e))
                log_error(f"BINANCE shard {name} crash: {repr(e)}")
                await asyncio.sleep(backoff)
                backoff = min(backoff*2, 60)
    tasks = [asyncio.create_task(run_one(u, i)) for i, u in enumerate(urls)]
    await asyncio.gather(*tasks)

# =========================== AUTH ===========================
def auth_check_all_accounts():
    if not BYBIT_CLIENTS:
        msg = "⚠️ Bybit аккаунты не заданы: приватные вызовы отключены."
        print(msg); tg_send(msg)
        return

    lines = []
    for c in BYBIT_CLIENTS:
        try:
            wb = c.wallet_balance()
            equity = None
            lst = (wb.get("result", {}) or {}).get("list", []) or []
            if lst and "totalEquity" in lst[0]:
                equity = float(lst[0]["totalEquity"])
            ok = f"✅ {c.name}: auth OK" + (f", equity≈{equity:.2f} USDT" if equity is not None else "")
            lines.append(ok)
        except Exception as e:
            err = f"🛑 {c.name}: auth FAIL — {e}"
            lines.append(err)
            log_error(f"auth_check {c.name} failed: {e}")

    lines.append(f"🔧 DRY_RUN: {'ON' if DRY_RUN else 'OFF'}")
    if TRADE_CLIENT:
        lines.append(f"🤖 Торговый аккаунт: {TRADE_CLIENT.name}")
    else:
        lines.append("🤖 Торговый аккаунт: не выбран/нет ключей")
    lines.append(
        "🧠 strategies: "
        f"breakout={ENABLE_BREAKOUT_TRADING}, "
        f"pump_fade={ENABLE_PUMP_FADE_TRADING}, "
        f"midterm={ENABLE_MIDTERM_TRADING}, "
        f"inplay={ENABLE_INPLAY_TRADING}, "
        f"retest={ENABLE_RETEST_TRADING}, "
        f"range={ENABLE_RANGE_TRADING}, "
        f"sloped={ENABLE_SLOPED_TRADING}, "
        f"flat={ENABLE_FLAT_TRADING}, "
        f"breakdown={ENABLE_BREAKDOWN_TRADING}, "
        f"ts132={ENABLE_TS132_TRADING}"
    )

    text = "\n".join(lines)
    print(text)
    tg_send(text)


async def range_rescan_loop():
    """
    Раз в RANGE_RESCAN_SEC секунд ищем диапазоны на топ-символах и кладём в RANGE_REGISTRY.
    ВАЖНО: чтобы не убить лимиты Bybit, сканируем не все 220, а, например, первые 120.
    """
    if not ENABLE_RANGE_TRADING:
        return

    while True:
        try:
            syms = bybit_symbols(TOP_N_BYBIT)
            syms = syms[:120]  # ограничение по rate limit

            found = await RANGE_SCANNER.rescan(syms, top_n=50)

            if found:
                top5 = ", ".join([f"{x.symbol}({x.range_pct:.1f}%)" for x in found[:5]])
                tg_trade(f"📏 RANGE scan: found={len(found)} | top: {top5}")
            else:
                tg_trade("📏 RANGE scan: found=0")

        except Exception as e:
            log_error(f"range_rescan_loop crash: {e}")

        await asyncio.sleep(RANGE_RESCAN_SEC)



# =========================== PULSE ===========================
async def pulse():
    last_stats_sent = 0
    last_ws_health_check_ts = 0
    last_ws_alert_ts = 0
    last_ws_alert_status = ""
    ws_no_connect_streak = 0
    last_ws_counters = (
        _diag_get_int("ws_connect"),
        _diag_get_int("ws_disconnect"),
        _diag_get_int("ws_handshake_timeout"),
    )
    last_bybit_msg_count = int(MSG_COUNTER.get("Bybit", 0))
    while True:
        try:
            sync_trades_with_exchange()
        except Exception as e:
            log_error(f"sync_trades crash: {e}")

        try:
            ensure_open_positions_have_tpsl()
        except Exception as e:
            log_error(f"ensure_tpsl crash: {e}")

        print(
            f"[pulse] Bybit msgs={MSG_COUNTER.get('Bybit', 0)}  open_trades={len(TRADES)}  "
            f"disabled={PORTFOLIO_STATE.get('disabled')} | {_runtime_diag_snapshot()}"
        )
        try:
            now = int(time.time())
            if STRATEGY_STATS_TG_EVERY_SEC > 0 and (now - last_stats_sent) >= int(STRATEGY_STATS_TG_EVERY_SEC):
                tg_trade(_strategy_runtime_stats_text(STRATEGY_STATS_LOOKBACK_H))
                last_stats_sent = now
            if BREAKOUT_SKIP_DIGEST_ENABLE:
                _flush_breakout_skip_digest()
            if WS_HEALTH_ALERT_ENABLE and (now - last_ws_health_check_ts) >= int(WS_HEALTH_CHECK_SEC):
                cur_ws = (
                    _diag_get_int("ws_connect"),
                    _diag_get_int("ws_disconnect"),
                    _diag_get_int("ws_handshake_timeout"),
                )
                d_connect = cur_ws[0] - last_ws_counters[0]
                d_disconnect = cur_ws[1] - last_ws_counters[1]
                d_handshake = cur_ws[2] - last_ws_counters[2]
                cur_bybit_msg_count = int(MSG_COUNTER.get("Bybit", 0))
                d_bybit_msgs = max(0, cur_bybit_msg_count - last_bybit_msg_count)
                status, disc_conn_pct, hs_conn_pct = _ws_health_from_delta(d_connect, d_disconnect, d_handshake)
                # If market data is still flowing, avoid paging on "no connect" windows that
                # are noisy but not functionally dead.
                if status == "CRITICAL_NO_CONNECT" and d_bybit_msgs >= int(WS_HEALTH_NO_CONNECT_MIN_MSG_DELTA):
                    status = "NO_DATA"
                if status == "CRITICAL_NO_CONNECT":
                    ws_no_connect_streak += 1
                else:
                    ws_no_connect_streak = 0
                if d_connect >= WS_HEALTH_MIN_CONNECT_DELTA and status in {"WARN", "CRITICAL"}:
                    if (now - last_ws_alert_ts) >= int(WS_HEALTH_ALERT_COOLDOWN_SEC) or status != last_ws_alert_status:
                        tg_trade(
                            "⚠️ WS health "
                            f"{status}: connect={d_connect} disconnect={d_disconnect} handshake_timeout={d_handshake} "
                            f"| disconnect/connect={_fmt_ratio_or_inf(disc_conn_pct)} "
                            f"| handshake/connect={_fmt_ratio_or_inf(hs_conn_pct)} "
                            f"(window={int(WS_HEALTH_CHECK_SEC)}s)"
                        )
                        last_ws_alert_ts = now
                        last_ws_alert_status = status
                elif status == "CRITICAL_NO_CONNECT":
                    if (
                        ws_no_connect_streak >= int(WS_HEALTH_NO_CONNECT_STREAK_ALERT)
                        and (
                            (now - last_ws_alert_ts) >= int(WS_HEALTH_NO_CONNECT_ALERT_COOLDOWN_SEC)
                            or status != last_ws_alert_status
                        )
                    ):
                        tg_trade(
                            "⚠️ WS health CRITICAL_NO_CONNECT: "
                            f"connect={d_connect} disconnect={d_disconnect} handshake_timeout={d_handshake} "
                            f"(window={int(WS_HEALTH_CHECK_SEC)}s, streak={ws_no_connect_streak})"
                        )
                        last_ws_alert_ts = now
                        last_ws_alert_status = status
                last_ws_counters = cur_ws
                last_bybit_msg_count = cur_bybit_msg_count
                last_ws_health_check_ts = now
        except Exception as e:
            log_error(f"strategy-stats pulse fail: {e}")
        await asyncio.sleep(10)

# =========================== RUNNER ===========================
async def runner(coro, title):
    while True:
        try:
            await coro()
        except Exception as e:
            msg = f"{title} crash: {repr(e)}\n{traceback.format_exc()}"
            print(msg)
            log_error(msg)
            try:
                tg_trade(f"🧯 {title} crashed. See errors.log")
            except Exception:
                pass
            await asyncio.sleep(3)

async def main_async():
    tasks = []
    if ENABLE_BYBIT:
        tasks.append(asyncio.create_task(runner(bybit_ws, "BYBIT")))
        tasks.append(asyncio.create_task(runner(symbol_filters_loop, "FILTERS_REFRESH")))
    if ENABLE_BINANCE:
        tasks.append(asyncio.create_task(runner(binance_ws, "BINANCE")))

    if ENABLE_RANGE_TRADING:
        tasks.append(asyncio.create_task(runner(range_rescan_loop, "RANGE_RESCAN")))

    if TG_COMMANDS_ENABLE:
        tasks.append(asyncio.create_task(runner(tg_cmd_loop, "TG_CMD")))
    if REPORTS_ENABLE:
        tasks.append(asyncio.create_task(runner(reports_loop, "REPORTS")))

    tasks.append(asyncio.create_task(pulse()))
    await asyncio.gather(*tasks)


def main():
    _db_init()
    print("Starting real-time pump detector…")
    print(f"Sources: Bybit={ENABLE_BYBIT}, Binance={ENABLE_BINANCE}, MEXC={ENABLE_MEXC}")
    print(f"Trading: {'ON' if TRADE_ON else 'OFF'} (Bybit short fade); DRY_RUN={'ON' if DRY_RUN else 'OFF'}")
    print(f"Bybit position mode: {'ONE-WAY' if POS_IS_ONEWAY else 'HEDGE'}")
    # Effective per-account trade settings (after BYBIT_ACCOUNTS_JSON overrides)
    print(
        f"Account: {TRADE_ACCOUNT_NAME} | leverage={BYBIT_LEVERAGE} | max_positions={MAX_POSITIONS} | "
        f"risk={RISK_PER_TRADE_PCT:.2f}% | cap_notional_to_equity={CAP_NOTIONAL_TO_EQUITY} | "
        f"reserve={RESERVE_EQUITY_FRAC:.2f} | min_notional={MIN_NOTIONAL_USD}"
    )
    print(
        f"Strategies: breakout={ENABLE_BREAKOUT_TRADING} inplay={ENABLE_INPLAY_TRADING} "
        f"retest={ENABLE_RETEST_TRADING} range={ENABLE_RANGE_TRADING} pump_fade={ENABLE_PUMP_FADE_TRADING} "
        f"midterm={ENABLE_MIDTERM_TRADING} sloped={ENABLE_SLOPED_TRADING} flat={ENABLE_FLAT_TRADING} breakdown={ENABLE_BREAKDOWN_TRADING} ts132={ENABLE_TS132_TRADING}"
    )
    if BOT_CAPITAL_USD is not None:
        print(f"Bot capital cap: {BOT_CAPITAL_USD} USDT")
    print(f"Bounce execute: {BOUNCE_EXECUTE_TRADES} (top_n={BOUNCE_TOP_N})")

    if DRY_RUN:
        msg = "🟡 DRY_RUN: пропускаю проверку Bybit auth (приватные вызовы выключены)."
        print(msg); tg_send(msg)
        portfolio_init_if_needed()
    else:
        auth_check_all_accounts()
        portfolio_init_if_needed()
        bootstrap_open_trades_from_exchange()
    try:
        asyncio.run(main_async())
    except Exception as e:
        log_error(f"fatal: {repr(e)}\n{traceback.format_exc()}")
        try:
            tg_trade("🛑 BOT STOPPED: fatal error. Check errors.log")
        except Exception:
            pass
        raise

if __name__ == "__main__":
    main()
