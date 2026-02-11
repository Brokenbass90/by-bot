#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# smart_pump_reversal_bot.py

import os
import time, json, statistics, asyncio, requests, collections, re, csv, traceback, random, math
import sqlite3
from typing import Dict, Tuple, List, Optional, Any
import websockets
from websockets.exceptions import InvalidStatus
from dotenv import load_dotenv
import hmac, hashlib
from urllib.parse import urlencode
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from sr_levels import LevelsService
from sr_bounce import BounceStrategy
from trade_state import TradeState
from inplay_live import InPlayLiveEngine
from breakout_live import BreakoutLiveEngine
from retest_live import RetestEngine

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

# Минимальная доля "желательного" notional (по риск-сайзингу), которую нужно уметь разместить.
# Если меньше — пропускаем сделку (иначе комиссии/проскальзывание убивают ожидание).
MIN_NOTIONAL_FILL_FRAC = float(os.getenv("MIN_NOTIONAL_FILL_FRAC", "0.40"))


# =========================== ГЛОБАЛ ===========================
DEBUG_WINDOWS = True
MSG_COUNTER = {"Bybit": 0, "Binance": 0}
AUTH_DISABLED_UNTIL = {}  # name -> ts
AUTH_LAST_ERROR = {}      # name -> str
BOT_START_TS = int(time.time())

def auth_disabled(name: str) -> bool:
    if DRY_RUN:
        return False
    until = int((AUTH_DISABLED_UNTIL.get(name) or 0))
    return int(time.time()) < until

def mark_auth_fail(name: str, err: Exception, cooldown_sec: int = 600):
    AUTH_DISABLED_UNTIL[name] = int(time.time()) + int(cooldown_sec)
    AUTH_LAST_ERROR[name] = str(err)[:300]

    try:
        tg_trade(f"🛑 AUTH FAIL [{name}]: {AUTH_LAST_ERROR[name]}\nОтключаю приватные вызовы на {cooldown_sec // 60} мин.")
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
TOP_N_BYBIT = 220
TOP_N_BINANCE = 200

# ===== INPLAY (live) =====
ENABLE_INPLAY_TRADING = os.getenv("ENABLE_INPLAY_TRADING", "0").strip() == "1"
INPLAY_TRY_EVERY_SEC = int(os.getenv("INPLAY_TRY_EVERY_SEC", "30"))
INPLAY_TOP_N = int(os.getenv("INPLAY_TOP_N", "60"))
INPLAY_SYMBOLS = set()
INPLAY_ENGINE = None

# ===== BREAKOUT (live) =====
ENABLE_BREAKOUT_TRADING = os.getenv("ENABLE_BREAKOUT_TRADING", "0").strip() == "1"
BREAKOUT_TRY_EVERY_SEC = int(os.getenv("BREAKOUT_TRY_EVERY_SEC", "30"))
BREAKOUT_TOP_N = int(os.getenv("BREAKOUT_TOP_N", "60"))
BREAKOUT_SYMBOLS = set()
BREAKOUT_ENGINE = None

# ===== RETEST LEVELS (live) =====
ENABLE_RETEST_TRADING = os.getenv("ENABLE_RETEST_TRADING", "0").strip() == "1"
RETEST_TRY_EVERY_SEC = int(os.getenv("RETEST_TRY_EVERY_SEC", "60"))
RETEST_TOP_N = int(os.getenv("RETEST_TOP_N", "60"))
RETEST_SYMBOLS = set()
RETEST_ENGINE = None

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
BOUNCE_DEBUG = True
BOUNCE_DEBUG_CSV = "bounce_debug.csv"

BOUNCE_MAX_DIST_PCT = 0.60
BOUNCE_EXECUTE_TRADES = True  # False = только логировать

# --- Bounce extra filters (то, что ты спросил "куда это") ---
BOUNCE_REQUIRE_TREND_MATCH = True       # не торговать bounce против EMA20/EMA60
BOUNCE_MAX_BREAKOUT_RISK   = 0.55       # максимум допустимого breakout_risk
BOUNCE_MIN_POTENTIAL_PCT   = 0.30       # минимум потенциала (в %)

# === Bounce universe control ===
BOUNCE_TOP_N = 50                 # bounce только на топ-50 ликвидных инструментов
BOUNCE_SYMBOLS = set()            # заполнится в bybit_ws() после получения syms

ENTRY_CONFIRM_GRACE_SEC = 25   # сколько ждём “позиция появится” прежде чем признать FAIL
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
    if hit and (now - hit[0] < 15):
        return hit[1]

    r = requests.get(
        f"{base}/v5/market/kline",
        params={"category": "linear", "symbol": symbol, "interval": str(interval), "limit": limit},
        timeout=10,
    )
    r.raise_for_status()
    j = r.json()
    if str(j.get("retCode")) != "0":
        raise RuntimeError(f"Bybit kline error: {j}")

    rows = ((j.get("result") or {}).get("list") or [])
    rows = list(reversed(rows))  # делаем: старые -> новые

    _KLINE_RAW_CACHE[key] = (now, rows)
    return rows

# init inplay live engine after fetch_klines is available
if INPLAY_ENGINE is None:
    INPLAY_ENGINE = InPlayLiveEngine(fetch_klines)
if BREAKOUT_ENGINE is None:
    BREAKOUT_ENGINE = BreakoutLiveEngine(fetch_klines)
if RETEST_ENGINE is None:
    RETEST_ENGINE = RetestEngine(fetch_klines)


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

def dist_pct(price: float, level: float) -> float:
    return (price - level) / max(1e-12, level) * 100.0


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

# =========================== .env ===========================
load_dotenv()
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
MIN_RANGE_PCT = float(os.getenv("MIN_RANGE_PCT", "3.0"))
MAX_RANGE_PCT = float(os.getenv("MAX_RANGE_PCT", "8.0"))
RANGE_MIN_TOUCHES = int(os.getenv("RANGE_MIN_TOUCHES", "3"))

RANGE_ENTRY_ZONE_FRAC = float(os.getenv("RANGE_ENTRY_ZONE_FRAC", "0.08"))
RANGE_SWEEP_FRAC = float(os.getenv("RANGE_SWEEP_FRAC", "0.02"))
RANGE_TP_MODE = os.getenv("RANGE_TP_MODE", "mid").strip()
RANGE_TP_FRAC = float(os.getenv("RANGE_TP_FRAC", "0.45"))
RANGE_SL_BUFFER_FRAC = float(os.getenv("RANGE_SL_BUFFER_FRAC", "0.03"))
RANGE_SL_ATR_MULT = float(os.getenv("RANGE_SL_ATR_MULT", "0.8"))

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

# =========================== TELEGRAM COMMANDS ===========================
TG_COMMANDS_ENABLE = os.getenv("TG_COMMANDS_ENABLE", "1").strip() == "1"

def _tg_reply(msg: str):
    tg_send(msg)

def _parse_float(s: str) -> float | None:
    try:
        return float(s)
    except Exception:
        return None

def _handle_tg_command(text: str):
    global TRADE_ON, RISK_PER_TRADE_PCT, BOT_CAPITAL_USD, MAX_POSITIONS

    cmd = text.strip().split()
    if not cmd:
        return
    name = cmd[0].lower()

    if name in ("/help", "/start"):
        _tg_reply(
            "🤖 Управление ботом\n"
            "• /status — статус и риск\n"
            "• /ping — жив ли бот\n"
            "• /pause — пауза торговли\n"
            "• /resume — продолжить\n"
            "• /risk 0.5 — риск в %\n"
            "• /capital 200 — кап бота\n"
            "• /positions 3 — макс. позиций (1–10)"
        )
        return

    if name == "/status":
        eq = _get_effective_equity()
        _tg_reply(
            f"Status: {'ON' if TRADE_ON else 'OFF'} | disabled={PORTFOLIO_STATE.get('disabled')}\n"
            f"Equity≈{eq:.2f} USDT | open={len(TRADES)}\n"
            f"risk={RISK_PER_TRADE_PCT:.2f}% | max_positions={MAX_POSITIONS} | capital={BOT_CAPITAL_USD}"
        )
        return

    if name == "/ping":
        up = max(0, int(time.time()) - int(BOT_START_TS))
        h = up // 3600
        m = (up % 3600) // 60
        s = up % 60
        _tg_reply(f"✅ alive | uptime {h:02d}:{m:02d}:{s:02d}")
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
                text = (msg.get("text") or "").strip()
                if text.startswith("/"):
                    _handle_tg_command(text)
        except Exception as e:
            log_error(f"tg cmd loop error: {e}")
        await asyncio.sleep(1)

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

def base_from_usdt(s: str) -> str:
    return s[:-4] if s.endswith("USDT") else s

def now_s() -> int:
    return int(time.time())

def _to_float_safe(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def _today_ymd():
    return time.strftime("%Y-%m-%d", time.gmtime())

# =========================== СОСТОЯНИЕ СИМВОЛОВ ===========================
class SymState:
    __slots__ = (
        "trades","prices","win_hist","last_eval_ts","last_alert",
        "highs","lows","closes","last_pump","q_hist",
        "ema_fast","ema_slow","ctx5m","last_bounce_try",
        # добавь это:
        "bars5m","cur5_id","cur5_o","cur5_h","cur5_l","cur5_c","cur5_quote",
    )
    def __init__(self):
        self.trades = collections.deque()
        self.prices = collections.deque()
        self.win_hist = collections.deque(maxlen=BASE_WINDOWS)
        self.last_eval_ts = 0
        self.last_alert = 0
        self.highs  = collections.deque(maxlen=240)
        self.lows   = collections.deque(maxlen=240)
        self.closes = collections.deque(maxlen=240)
        self.last_pump = None
        self.q_hist = collections.deque(maxlen=2)
        self.ema_fast = None
        self.ema_slow = None
        self.ctx5m = collections.deque()
        self.last_bounce_try = 0

        self.cur5_id = None
        self.bars5m = collections.deque(maxlen=300)
        self.cur5_o = self.cur5_h = self.cur5_l = self.cur5_c = None
        self.cur5_quote = 0.0

STATE: Dict[Tuple[str, str], SymState] = {}

def update_5m_bar(st: SymState, t: int, p: float, qq: float):
    bar_id = t // 300
    if st.cur5_id != bar_id:
        # закрываем прошлую
        if st.cur5_id is not None and st.cur5_o is not None:
            st.bars5m.append({
                "id": st.cur5_id,
                "o": st.cur5_o, "h": st.cur5_h, "l": st.cur5_l, "c": st.cur5_c,
                "quote": st.cur5_quote,
            })
        # старт новой
        st.cur5_id = bar_id
        st.cur5_o = st.cur5_h = st.cur5_l = st.cur5_c = p
        st.cur5_quote = 0.0
    else:
        st.cur5_h = max(st.cur5_h, p)
        st.cur5_l = min(st.cur5_l, p)
        st.cur5_c = p

    st.cur5_quote += qq

def S(exch: str, sym: str) -> SymState:
    k = (exch, sym)
    st = STATE.get(k)
    if st is None:
        st = SymState()
        STATE[k] = st
    return st

def trim(st: SymState, ts: int):
    cut = ts - WINDOW_SEC*2
    while st.trades and st.trades[0][0] < cut: st.trades.popleft()
    while st.prices and st.prices[0][0] < cut: st.prices.popleft()
    cut5 = ts - (CTX_5M_SEC + 10)
    while st.ctx5m and st.ctx5m[0][0] < cut5:
        st.ctx5m.popleft()

def calc_atr_pct(h, l, c, period=14):
    """
    Обёртка над indicators.atr_pct_from_ohlc для совместимости со старым API.
    """
    return atr_pct_from_ohlc(list(h), list(l), list(c), period=period, fallback=0.8)


def calc_rsi(closes, period=14):
    return rsi_calc(list(closes), period=period)


def ema_val(prev: Optional[float], price: float, length: int) -> float:
    return ema_incremental(prev, float(price), length)


def candle_pattern(open_p, close_p, high_p, low_p) -> Optional[str]:
    return candle_pattern_detect(float(open_p), float(close_p), float(high_p), float(low_p))


def engulfing(prev_o, prev_c, o, c) -> bool:
    return engulfing_bear(prev_o, prev_c, float(o), float(c))


def trade_quality(trades: list, q_total: float) -> float:
    return calc_trade_quality(trades, float(q_total))

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
                # для bounce/риск-сайзинга нельзя “поднимать” notional через quoteCoin
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

                tr.qty = float(size)
                if side in ("Buy", "Sell"):
                    tr.side = side

                # ✅ реальный avgPrice с биржи
                if avg_ex is not None and float(avg_ex) > 0:
                    tr.avg = float(avg_ex)
                    tr.entry_price = float(avg_ex)

                    # если TP/SL уже были рассчитаны по "примерному" price — пересчитаем от реального avg
                    if getattr(tr, "strategy", "pump") in ("bounce", "range", "inplay"):
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
                    tg_trade(f"✅ ENTRY FILLED {sym} {tr.side} qty={tr.qty} avg={float(getattr(tr,'avg',0) or 0):.6f}")
                    _db_log_event("ENTRY", tr, sym)
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
    tg_trade(msg)
    _db_log_event("CLOSE", tr, sym, pnl=pnl_closed, fees=fee_sum, exit_px=exit_px)

def set_tp_sl_retry(symbol: str, side: str, tp: Optional[float], sl: Optional[float]) -> bool:
    if DRY_RUN or TRADE_CLIENT is None:
        return False
    if not ALWAYS_SET_TPSL_ON_EXCHANGE:
        return False

    for i in range(1, TPSL_RETRY_ATTEMPTS + 1):
        try:
            TRADE_CLIENT.set_tp_sl(symbol, side, tp, sl)
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

    if tr.trail_mult and tr.trail_mult > 0:
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

def calc_notional_usd_from_stop_pct(stop_pct: float) -> float:
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

    risk_usd = equity * (RISK_PER_TRADE_PCT / 100.0)

    notional_raw = risk_usd / (stop_pct / 100.0)
    notional = min(notional_raw, max_notional_allowed(equity))

    fill = notional / notional_raw if notional_raw > 0 else 0.0
    if fill < MIN_NOTIONAL_FILL_FRAC:
        return 0.0


    if notional < MIN_NOTIONAL_USD:
        return 0.0

    return float(notional)

    

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

BASE_URL_PUBLIC = (TRADE_CLIENT.base if TRADE_CLIENT else BYBIT_BASE_DEFAULT)

LEVELS_SVC = LevelsService(base_url=BASE_URL_PUBLIC, ttl_sec=900)
BOUNCE_STRAT = BounceStrategy(base_url=BASE_URL_PUBLIC, levels=LEVELS_SVC)
BOUNCE_STRAT.breakout_risk_max = BOUNCE_MAX_BREAKOUT_RISK


# =========================== RANGE (1h range + 5m confirmation) ===========================
RANGE_REGISTRY = RangeRegistry()

RANGE_SCANNER = RangeScanner(
    fetch_klines=fetch_klines_for_range,

    registry=RANGE_REGISTRY,
    interval_1h="60",
    lookback_h=RANGE_LOOKBACK_H,
    rescan_ttl_sec=RANGE_RESCAN_SEC,
    min_range_pct=MIN_RANGE_PCT,
    max_range_pct=MAX_RANGE_PCT,
    min_touches=RANGE_MIN_TOUCHES,
)

RANGE_STRATEGY = RangeStrategy(
    fetch_klines=fetch_klines_for_range,
    registry=RANGE_REGISTRY,
    confirm_tf="5",
    confirm_limit=5,
    entry_zone_frac=RANGE_ENTRY_ZONE_FRAC,
    sweep_frac=RANGE_SWEEP_FRAC,
    tp_mode=RANGE_TP_MODE,
    sl_buffer_frac=RANGE_SL_BUFFER_FRAC,
    sl_atr_mult=RANGE_SL_ATR_MULT,
    allow_long=RANGE_ALLOW_LONG,
    allow_short=RANGE_ALLOW_SHORT,
)



# пример “короткого” bounce под маленький депозит
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
    try:
        wb = TRADE_CLIENT.wallet_balance()
        lst = (wb.get("result") or {}).get("list") or []
        if not lst:
            return None

        row0 = lst[0] or {}
        # Bybit unified обычно отдаёт totalEquity прямо тут
        v = row0.get("totalEquity")
        if v not in (None, "", "0"):
            return float(v)

        # fallback (на всякий)
        v2 = row0.get("accountIMRate")  # не equity, но иногда поля разные; лучше просто None
        return None

    except Exception as e:
        # не валим бота из-за equity, просто логируем
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

def portfolio_reg_pnl(notional_usd: float, pnl_pct: float):
    portfolio_init_if_needed()
    pnl_usd = notional_usd * (pnl_pct / 100.0)
    PORTFOLIO_STATE["daily_pnl_usd"] += pnl_usd
    eq = _get_effective_equity()
    if PORTFOLIO_STATE["day_equity_start"] and eq < PORTFOLIO_STATE["day_equity_start"] * (1 - DAILY_LOSS_LIMIT_PCT/100.0):
        PORTFOLIO_STATE["disabled"] = True

TRADES: Dict[Tuple[str,str], TradeState] = {}

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


_RANGE_LAST_TRY = {}            # symbol -> ts
RANGE_TRY_EVERY_SEC = 20

_INPLAY_LAST_TRY = {}           # symbol -> ts
_BREAKOUT_LAST_TRY = {}         # symbol -> ts
_RETEST_LAST_TRY = {}           # symbol -> ts

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
        sig = INPLAY_ENGINE.signal(symbol, price, int(now * 1000))
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
    last = int(_BREAKOUT_LAST_TRY.get(symbol, 0) or 0)
    if now - last < BREAKOUT_TRY_EVERY_SEC:
        return
    _BREAKOUT_LAST_TRY[symbol] = now

    try:
        sig = BREAKOUT_ENGINE.signal(symbol, price, int(now * 1000))
    except Exception as e:
        log_error(f"breakout signal error {symbol}: {e}")
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
        tg_trade(f"🟡 BREAKOUT SKIP {symbol}: stop={stop_pct:.2f}% -> notional too small")
        return

    qty_floor, notional_real, reason = qty_floor_from_notional(symbol, dyn_usd, entry)
    if qty_floor <= 0:
        tg_trade(f"🟡 BREAKOUT SKIP {symbol}: {reason} (need≈{dyn_usd:.2f}$)")
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
    tr.strategy = "inplay_breakout"
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
        f"🟩 BREAKOUT ENTRY [{TRADE_CLIENT.name}] {symbol} {side}\n"
        f"entry≈{entry:.6f} TP={tr.tp_price:.6f} SL={tr.sl_price:.6f}\n"
        f"notional≈{notional_real:.2f}$ qty≈{q}\n"
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
        if BOUNCE_DEBUG:
            tg_trade(
                f"🧪 BOUNCE DEBUG {sym} {sig.side}  price={price:.6f}  lvl={lvl:.6f} "
                f"dist={d:+.3f}%  kind={sig.level.kind},{sig.level.tf}  risk={sig.breakout_risk:.2f}  decision={decision}"
            )

        if decision != "ENTER":
            return

        # Проверочный режим: только логируем, но не торгуем
        if not BOUNCE_EXECUTE_TRADES:
            tg_trade(f"🟡 BOUNCE LOG-ONLY (no trade): {sym} {sig.side} dist={d:+.3f}%")
            return

        tp_r, sl_r = round_tp_sl_prices(sym, sig.side, float(price), sig.tp_price, sig.sl_price)

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

    # ===== RANGE ENTRY (flat/range) =====
    if exch == "Bybit" and ENABLE_RANGE_TRADING and TRADE_ON and (not DRY_RUN):
        last = int(_RANGE_LAST_TRY.get(sym, 0) or 0)
        if now - last >= RANGE_TRY_EVERY_SEC:
            try:
                asyncio.create_task(try_range_entry_async(sym, p1))
            except Exception as _e:
                log_error(f"try_range_entry schedule fail {sym}: {_e}")

    # ===== INPLAY ENTRY (retest/runner) =====
    if exch == "Bybit" and ENABLE_INPLAY_TRADING and TRADE_ON and (not DRY_RUN):
        last = int(_INPLAY_LAST_TRY.get(sym, 0) or 0)
        if now - last >= INPLAY_TRY_EVERY_SEC:
            try:
                asyncio.create_task(try_inplay_entry_async(sym, p1))
            except Exception as _e:
                log_error(f"try_inplay_entry schedule fail {sym}: {_e}")

    # ===== BREAKOUT ENTRY (retest -> continue) =====
    if exch == "Bybit" and ENABLE_BREAKOUT_TRADING and TRADE_ON and (not DRY_RUN):
        last = int(_BREAKOUT_LAST_TRY.get(sym, 0) or 0)
        if now - last >= BREAKOUT_TRY_EVERY_SEC:
            try:
                asyncio.create_task(try_breakout_entry_async(sym, p1))
            except Exception as _e:
                log_error(f"try_breakout_entry schedule fail {sym}: {_e}")

    # ===== RETEST LEVELS ENTRY =====
    if exch == "Bybit" and ENABLE_RETEST_TRADING and TRADE_ON and (not DRY_RUN):
        last = int(_RETEST_LAST_TRY.get(sym, 0) or 0)
        if now - last >= RETEST_TRY_EVERY_SEC:
            try:
                asyncio.create_task(try_retest_entry_async(sym, p1))
            except Exception as _e:
                log_error(f"try_retest_entry schedule fail {sym}: {_e}")




    # ✅ ВАЖНО: сопровождение открытых bounce-сделок должно работать даже когда фильтры пампа "молчат"
    if TRADE_ON and exch == "Bybit":
        tr = get_trade(exch, sym)
        if (tr
            and getattr(tr, "strategy", "pump") in ("bounce", "range")
            and getattr(tr, "status", None) == "OPEN"   
            and p1 is not None
        ):
            POS_MANAGER.manage(exch, sym, st, tr, p1, buys2, sells2)

        # ===== INPLAY runner management (partials + trailing + time stop) =====
        if (tr
            and getattr(tr, "strategy", "") == "inplay"
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

    # ---- требуем закрытие ближе к хаям окна (а не просто “перекрыли красную”)
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
                tr.strategy = "pump"
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
                    f"🟣 ENTRY [{acc_name}] {sym}\n"
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
async def bybit_ws():
    url = "wss://stream.bybit.com/v5/public/linear"
    syms = bybit_symbols(TOP_N_BYBIT)


    # bounce universe = подмножество, которое реально можно открыть на текущий cap
    global BOUNCE_SYMBOLS
    global INPLAY_SYMBOLS
    global BREAKOUT_SYMBOLS
    global RETEST_SYMBOLS

    eq_eff = 0.0
    try:
        eq_eff = float(_get_effective_equity() or 0.0)
    except Exception:
        eq_eff = 0.0

    # если equity не получили, но задан BOT_CAPITAL_USD — используем его как “плановый” cap
    if eq_eff <= 0 and BOT_CAPITAL_USD:
        try:
            eq_eff = float(BOT_CAPITAL_USD)
        except Exception:
            pass

    cap = max_notional_allowed(eq_eff)

    eligible = []

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

    BOUNCE_SYMBOLS = set(eligible[:BOUNCE_TOP_N])
    INPLAY_SYMBOLS = set(eligible[:max(1, int(INPLAY_TOP_N))])
    BREAKOUT_SYMBOLS = set(eligible[:max(1, int(BREAKOUT_TOP_N))])
    RETEST_SYMBOLS = set(eligible[:max(1, int(RETEST_TOP_N))])

    # global RANGE_RESCAN_TASK
    # if ENABLE_RANGE_TRADING and RANGE_RESCAN_TASK is None:
    #     RANGE_RESCAN_TASK = asyncio.create_task(range_rescan_loop())


    print(f"[bounce] cap≈{cap:.2f} USDT | eligible={len(eligible)}/{len(syms)} | universe size={len(BOUNCE_SYMBOLS)} (top {BOUNCE_TOP_N})")
    if ENABLE_INPLAY_TRADING:
        print(f"[inplay] universe size={len(INPLAY_SYMBOLS)} (top {INPLAY_TOP_N})")
    if ENABLE_BREAKOUT_TRADING:
        print(f"[breakout] universe size={len(BREAKOUT_SYMBOLS)} (top {BREAKOUT_TOP_N})")
    if ENABLE_RETEST_TRADING:
        print(f"[retest] universe size={len(RETEST_SYMBOLS)} (top {RETEST_TOP_N})")

    # опционально: в телегу
    tg_trade(f"🧩 bounce-universe: cap≈{cap:.2f} | eligible={len(eligible)}/{len(syms)} | using={len(BOUNCE_SYMBOLS)}")
    if ENABLE_INPLAY_TRADING:
        tg_trade(f"🧩 inplay-universe: using={len(INPLAY_SYMBOLS)} (top {INPLAY_TOP_N})")
    if ENABLE_BREAKOUT_TRADING:
        tg_trade(f"🧩 breakout-universe: using={len(BREAKOUT_SYMBOLS)} (top {BREAKOUT_TOP_N})")
    if ENABLE_RETEST_TRADING:
        tg_trade(f"🧩 retest-universe: using={len(RETEST_SYMBOLS)} (top {RETEST_TOP_N})")


    print(f"[bybit] got {len(syms)} symbols from REST")
    topics = [f"publicTrade.{s}" for s in syms]

    SHARD_SIZE  = 80
    BATCH_SIZE  = 8
    BATCH_DELAY = 1.5
    START_STAGGER = 2.0

    shards = [topics[i:i+SHARD_SIZE] for i in range(0, len(topics), SHARD_SIZE)]

    async def run_one(shard_args: List[str], shard_id: int):
        backoff = 10  # стартовый backoff
        while True:
            try:
                await asyncio.sleep(START_STAGGER * shard_id + random.uniform(0, 1.0))
                print(f"[bybit] shard {shard_id} connecting... ({len(shard_args)} topics)")

                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=45,
                    open_timeout=60,
                    close_timeout=10,
                    max_queue=None,
                    max_size=None,   # <-- ВАЖНО: добавить
                ) as ws:
                    print(f"[bybit] shard {shard_id} CONNECTED ✅")
                    backoff = 10  # сбрасываем после успешного коннекта

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
                print(f"[bybit] shard {shard_id} handshake timeout; retry in ~{backoff}s")
                log_error(f"BYBIT shard {shard_id} handshake timeout: {repr(e)}")
                await asyncio.sleep(backoff + random.uniform(0, 5.0))
                backoff = min(backoff * 2, 120)

            except InvalidStatus as e:
                print(f"[bybit] shard {shard_id} InvalidStatus: {repr(e)}")
                log_error(f"BYBIT InvalidStatus shard {shard_id}: {repr(e)}")
                await asyncio.sleep(300)

            except Exception as e:
                print(f"[bybit] shard {shard_id} ERROR: {repr(e)}")
                print(traceback.format_exc())
                log_error(f"BYBIT shard {shard_id} crash: {repr(e)}")
                await asyncio.sleep(backoff + random.uniform(0, 5.0))
                backoff = min(backoff * 2, 120)

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
    while True:
        try:
            sync_trades_with_exchange()
        except Exception as e:
            log_error(f"sync_trades crash: {e}")

        try:
            ensure_open_positions_have_tpsl()
        except Exception as e:
            log_error(f"ensure_tpsl crash: {e}")

        print(f"[pulse] Bybit msgs={MSG_COUNTER.get('Bybit', 0)}  open_trades={len(TRADES)}  disabled={PORTFOLIO_STATE.get('disabled')}")
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
    if ENABLE_BINANCE:
        tasks.append(asyncio.create_task(runner(binance_ws, "BINANCE")))

    if ENABLE_RANGE_TRADING:
        tasks.append(asyncio.create_task(runner(range_rescan_loop, "RANGE_RESCAN")))

    if TG_COMMANDS_ENABLE:
        tasks.append(asyncio.create_task(runner(tg_cmd_loop, "TG_CMD")))

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
