#!/usr/bin/env python3
"""
Alpaca Intraday Bridge — WF-Validated Strategies + 3-Layer Protection
======================================================================
Runs three walkforward-validated intraday strategies on US equity M5 bars
and submits bracket paper orders to Alpaca when a signal fires.

Strategies (WF results — 67% positive walkforward segments each):
  TSLA  → breakout_continuation_session_v1 + quality_guard   (+6200 cents, 98 trades)
  GOOGL → grid_reversion_session_v1 + safe_winrate           (+2270 cents, 87 trades)
  JPM   → grid_reversion_session_v1 (default)                (+1542 cents, 75 trades)

3-Layer Protection System:
  Layer 1 — SPY Regime Gate:
    If SPY close < SMA50 (daily) → NO new long positions. Market is bearish.
    Configurable: INTRADAY_SPY_SMA_PERIOD=50, INTRADAY_SPY_GATE=1

  Layer 2 — Daily Loss Limit:
    If today's realized P&L < -INTRADAY_MAX_DAILY_LOSS_PCT% of equity → halt for the day.
    Default: 2% of account equity. Resets at midnight UTC.
    Configurable: INTRADAY_MAX_DAILY_LOSS_PCT=2.0

  Layer 3 — Equity Curve Filter (20-day rolling):
    Tracks daily P&L log. If 20-day rolling return is negative → observation mode only.
    No new entries until equity curve recovers above its 10-day MA.
    Configurable: INTRADAY_EQUITY_CURVE_DAYS=20, INTRADAY_EQUITY_CURVE_GATE=1

Usage:
  # Dry-run (default) — checks signals + filters, no orders sent
  python3 scripts/equities_alpaca_intraday_bridge.py --dry-run

  # Live paper trading
  python3 scripts/equities_alpaca_intraday_bridge.py --live --once

  # Daemon mode — loops every 5 minutes
  python3 scripts/equities_alpaca_intraday_bridge.py --live --daemon

Crontab (market hours Mon-Fri):
  */5 14-21 * * 1-5 cd /root/by-bot && python3 scripts/equities_alpaca_intraday_bridge.py \
    --live --once >> logs/intraday_bridge.log 2>&1

Config env vars (or configs/alpaca_paper_local.env):
  ALPACA_API_KEY_ID, ALPACA_API_SECRET_KEY, ALPACA_BASE_URL
  INTRADAY_NOTIONAL_USD=200          # $ notional per position
  INTRADAY_MAX_POSITIONS=3           # max simultaneous positions
  INTRADAY_SPY_GATE=1                # 1=enabled, 0=disabled
  INTRADAY_SPY_SMA_PERIOD=50         # SPY SMA period (daily bars)
  INTRADAY_MAX_DAILY_LOSS_PCT=2.0    # halt if down X% today
  INTRADAY_EQUITY_CURVE_GATE=1       # 1=enabled, 0=disabled
  INTRADAY_EQUITY_CURVE_DAYS=20      # rolling window for equity filter
  INTRADAY_CLOSE_UNKNOWN_REMOTE_POSITIONS=0  # close paper leftovers not tracked in intraday_state
  TG_TOKEN, TG_CHAT_ID               # Telegram alerts
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import ssl
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error, request

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex.data import load_m5_csv
from forex.strategies.breakout_continuation_session_v1 import (
    BreakoutContinuationSessionV1,
    Config as BreakoutConfig,
)
from forex.strategies.grid_reversion_session_v1 import (
    GridReversionSessionV1,
    Config as GridReversionConfig,
)
from forex.strategies.trend_pullback_rebound_v1 import (
    TrendPullbackReboundV1,
    Config as TrendPullbackConfig,
)
from forex.strategies.trend_retest_session_v1 import (
    TrendRetestSessionV1,
    Config as TrendRetestConfig,
)
from forex.types import Candle, Signal

# ── File paths ──────────────────────────────────────────────────────────────────
ALPACA_DATA_URL    = "https://data.alpaca.markets"
STATE_FILE         = ROOT / "configs" / "intraday_state.json"
EQUITY_LOG_FILE    = ROOT / "configs" / "intraday_equity_log.json"
ENV_FILE           = ROOT / "configs" / "alpaca_paper_local.env"
INTRADAY_CFG_FILE  = ROOT / "configs" / "intraday_config.json"   # hot-reloadable symbol + strategy config
ADVISORY_DIR       = ROOT / "runtime" / "equities_intraday_dynamic_v1"
ADVISORY_FILE      = ADVISORY_DIR / "latest_advisory.json"
MONTHLY_RUNTIME_DIR = ROOT / "runtime" / "equities_monthly_v36"

# US market session in UTC (EDT: +4h, EST: +5h). Wide window handles DST.
US_SESSION_UTC_START = 14   # 10:00 AM ET (EDT safety buffer)
US_SESSION_UTC_END   = 21   # 5:00 PM ET

# ── WF-validated strategy configs ──────────────────────────────────────────────
LEGACY_STRATEGIES = {
    "TSLA": {
        "class": "breakout_continuation",
        "config": BreakoutConfig(
            ema_fast=34, ema_slow=144, breakout_lookback=24, breakout_atr=0.10,
            min_body_atr=0.14, max_chase_atr=0.55, sl_atr_mult=1.2, rr=1.9,
            cooldown_bars=18, session_utc_start=US_SESSION_UTC_START,
            session_utc_end=US_SESSION_UTC_END, trend_slope_bars=8,
            min_ema_gap_atr=0.35, min_slow_slope_atr=0.10,
            min_range_width_atr=1.2, max_atr_pct=0.45,
        ),
    },
    "GOOGL": {
        "class": "grid_reversion",
        "config": GridReversionConfig(
            ema_mid=100, ema_slow=220, grid_step_atr=0.9, trend_guard_atr=0.8,
            rsi_long_max=40.0, rsi_short_min=60.0, tp_to_ema_buffer_atr=0.03,
            sl_atr_mult=1.15, rr_cap=1.5, cooldown_bars=14,
            session_utc_start=US_SESSION_UTC_START, session_utc_end=US_SESSION_UTC_END,
        ),
    },
    "JPM": {
        "class": "grid_reversion",
        "config": GridReversionConfig(
            ema_mid=100, ema_slow=220, grid_step_atr=1.0, trend_guard_atr=0.9,
            rsi_long_max=42.0, rsi_short_min=58.0, tp_to_ema_buffer_atr=0.08,
            sl_atr_mult=1.2, rr_cap=2.2, cooldown_bars=16,
            session_utc_start=US_SESSION_UTC_START, session_utc_end=US_SESSION_UTC_END,
        ),
    },
}

DEFAULT_CLASS_CONFIGS = {
    "breakout_continuation": BreakoutConfig(
        ema_fast=34, ema_slow=144, breakout_lookback=24, breakout_atr=0.10,
        min_body_atr=0.14, max_chase_atr=0.55, sl_atr_mult=1.2, rr=1.9,
        cooldown_bars=18, session_utc_start=US_SESSION_UTC_START,
        session_utc_end=US_SESSION_UTC_END, trend_slope_bars=8,
        min_ema_gap_atr=0.35, min_slow_slope_atr=0.10,
        min_range_width_atr=1.2, max_atr_pct=0.45,
    ),
    "breakout_continuation:quality_guard": BreakoutConfig(
        ema_fast=34, ema_slow=144, breakout_lookback=24, breakout_atr=0.10,
        min_body_atr=0.14, max_chase_atr=0.55, sl_atr_mult=1.2, rr=1.9,
        cooldown_bars=18, session_utc_start=US_SESSION_UTC_START,
        session_utc_end=US_SESSION_UTC_END, trend_slope_bars=8,
        min_ema_gap_atr=0.35, min_slow_slope_atr=0.10,
        min_range_width_atr=1.2, max_atr_pct=0.45,
    ),
    "grid_reversion": GridReversionConfig(
        ema_mid=100, ema_slow=220, grid_step_atr=0.9, trend_guard_atr=0.8,
        rsi_long_max=40.0, rsi_short_min=60.0, tp_to_ema_buffer_atr=0.03,
        sl_atr_mult=1.15, rr_cap=1.5, cooldown_bars=14,
        session_utc_start=US_SESSION_UTC_START, session_utc_end=US_SESSION_UTC_END,
    ),
    "grid_reversion:safe_winrate": GridReversionConfig(
        ema_mid=100, ema_slow=220, grid_step_atr=0.9, trend_guard_atr=0.8,
        rsi_long_max=40.0, rsi_short_min=60.0, tp_to_ema_buffer_atr=0.03,
        sl_atr_mult=1.15, rr_cap=1.5, cooldown_bars=14,
        session_utc_start=US_SESSION_UTC_START, session_utc_end=US_SESSION_UTC_END,
    ),
    "trend_retest": TrendRetestConfig(
        ema_fast=55, ema_slow=220, breakout_lookback=42, retest_window_bars=8,
        sl_atr_mult=1.4, rr=2.5, cooldown_bars=32,
        session_utc_start=US_SESSION_UTC_START, session_utc_end=US_SESSION_UTC_END,
    ),
    "trend_retest:quality_guard": TrendRetestConfig(
        ema_fast=48, ema_slow=220, breakout_lookback=36, retest_window_bars=8,
        sl_atr_mult=1.2, rr=1.8, cooldown_bars=28,
        session_utc_start=US_SESSION_UTC_START, session_utc_end=US_SESSION_UTC_END,
        trend_slope_bars=8, min_ema_gap_atr=0.35, min_slow_slope_atr=0.10,
        max_atr_pct=0.35, min_breakout_body_atr=0.10, max_entry_extension_atr=0.35,
    ),
    "trend_pullback_rebound": TrendPullbackConfig(
        pullback_zone_atr=0.30, reclaim_atr=0.05,
        rsi_long_max=52.0, rsi_short_min=48.0,
        sl_atr_mult=1.35, rr=2.0, cooldown_bars=16,
        session_utc_start=US_SESSION_UTC_START, session_utc_end=US_SESSION_UTC_END,
    ),
    "trend_pullback_rebound:quality_guard": TrendPullbackConfig(
        pullback_zone_atr=0.24, reclaim_atr=0.07,
        rsi_long_max=50.0, rsi_short_min=50.0,
        sl_atr_mult=1.25, rr=2.0, cooldown_bars=20,
        session_utc_start=US_SESSION_UTC_START, session_utc_end=US_SESSION_UTC_END,
        trend_slope_bars=8, min_ema_gap_atr=0.30, min_slow_slope_atr=0.08,
        max_atr_pct=0.45, min_rebound_body_atr=0.06, max_pullthrough_slow_atr=0.15,
    ),
}

# ── Env helpers ────────────────────────────────────────────────────────────────
def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.split("#")[0].strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val

def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default)).strip()

def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except Exception:
        return default

def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except Exception:
        return default

def _env_bool(name: str, default: bool) -> bool:
    return _env(name, "1" if default else "0").lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: str = "") -> List[str]:
    raw = _env(name, default)
    if not raw:
        return []
    return [p.strip().upper() for p in raw.replace(";", ",").split(",") if p.strip()]


def _load_strategy_map_from_env() -> Dict[str, str]:
    out: Dict[str, str] = {}

    raw_json = _env("INTRADAY_STRATEGY_MAP_JSON")
    if raw_json:
        try:
            payload = json.loads(raw_json)
            if isinstance(payload, dict):
                for k, v in payload.items():
                    out[str(k).strip().upper()] = str(v).strip()
        except Exception:
            pass

    map_file = _env("INTRADAY_STRATEGY_MAP_FILE")
    if map_file:
        try:
            payload = json.loads(Path(map_file).expanduser().read_text())
            if isinstance(payload, dict):
                for k, v in payload.items():
                    out[str(k).strip().upper()] = str(v).strip()
        except Exception:
            pass

    for sym in _env_csv("INTRADAY_BREAKOUT_SYMBOLS"):
        out[sym] = "breakout_continuation"
    for sym in _env_csv("INTRADAY_REVERSION_SYMBOLS"):
        out[sym] = "grid_reversion"
    return out


def _load_intraday_config() -> dict:
    """Load optional intraday_config.json. Returns empty dict if missing or malformed.

    Expected format:
    {
      "symbols": ["TSLA", "GOOGL", "NVDA", ...],        # override symbol list
      "strategy_map": {"TSLA": "breakout_continuation", "NVDA": "breakout_continuation"},
      "max_symbols": 10
    }
    """
    cfg_file = Path(_env("INTRADAY_CONFIG_FILE", str(INTRADAY_CFG_FILE))).expanduser()
    if not cfg_file.exists():
        return {}
    try:
        raw = json.loads(cfg_file.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception as exc:
        print(f"[intraday_bridge] warning: failed to load {cfg_file}: {exc}")
        return {}


def _maybe_refresh_intraday_config() -> None:
    if not _env_bool("INTRADAY_DYNAMIC_BUILD", False):
        return
    builder = Path(_env("INTRADAY_DYNAMIC_BUILDER", str(ROOT / "scripts" / "build_equities_intraday_watchlist.py"))).expanduser()
    if not builder.exists():
        print(f"[intraday_bridge] warning: dynamic builder not found: {builder}")
        return

    out_json = Path(_env("INTRADAY_CONFIG_FILE", str(INTRADAY_CFG_FILE))).expanduser()
    cmd = [
        sys.executable,
        str(builder),
        "--data-dir",
        _env("INTRADAY_DATA_DIR", str(ROOT / "data_cache" / "equities_1h")),
        "--max-symbols",
        str(max(1, _env_int("INTRADAY_DYNAMIC_MAX_SYMBOLS", _env_int("INTRADAY_MAX_SYMBOLS", 12)))),
        "--breakout-target",
        str(max(0, _env_int("INTRADAY_DYNAMIC_BREAKOUT_TARGET", 6))),
        "--reversion-target",
        str(max(0, _env_int("INTRADAY_DYNAMIC_REVERSION_TARGET", 6))),
        "--min-avg-dollar-vol",
        str(max(0.0, _env_float("INTRADAY_DYNAMIC_MIN_AVG_DOLLAR_VOL", 25_000_000.0))),
        "--out-json",
        str(out_json),
    ]
    symbol_pool = _env("INTRADAY_DYNAMIC_SYMBOL_POOL", "")
    if symbol_pool:
        cmd.extend(["--symbols", symbol_pool])

    try:
        res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True)
        first_line = (res.stdout or "").strip().splitlines()
        if first_line:
            print(f"[intraday_bridge] dynamic watchlist refreshed: {first_line[0]}")
    except Exception as exc:
        print(f"[intraday_bridge] warning: dynamic watchlist refresh failed: {exc}")


def _discover_intraday_symbols(data_dir: Path, limit: int) -> List[str]:
    symbols: List[str] = []
    if not data_dir.exists():
        return symbols
    for csv_path in sorted(data_dir.glob("*_M5.csv")):
        stem = csv_path.stem
        if not stem.endswith("_M5"):
            continue
        sym = stem[:-3].upper()
        if not sym:
            continue
        symbols.append(sym)
        if limit > 0 and len(symbols) >= limit:
            break
    return symbols


def _build_runtime_catalog() -> tuple[Dict[str, dict], Dict[str, Path]]:
    _maybe_refresh_intraday_config()
    data_dir = Path(_env("INTRADAY_DATA_DIR", str(ROOT / "data_cache" / "equities_1h"))).expanduser()
    max_symbols = max(1, _env_int("INTRADAY_MAX_SYMBOLS", 30))
    explicit_symbols = _env_csv("INTRADAY_SYMBOLS")
    autodiscover = _env_bool("INTRADAY_AUTODISCOVER_FROM_CACHE", True)   # changed default: True enables dynamic discovery

    # Load optional hot-reloadable config file
    file_cfg = _load_intraday_config()
    if file_cfg.get("max_symbols"):
        max_symbols = max(1, int(file_cfg["max_symbols"]))

    # Symbol resolution priority: env > config file > autodiscover > legacy defaults
    if explicit_symbols:
        symbols = explicit_symbols[:max_symbols]
    elif file_cfg.get("symbols"):
        symbols = [s.strip().upper() for s in file_cfg["symbols"] if s.strip()][:max_symbols]
    elif autodiscover:
        discovered = _discover_intraday_symbols(data_dir, max_symbols)
        symbols = discovered if discovered else list(LEGACY_STRATEGIES.keys())
    else:
        symbols = list(LEGACY_STRATEGIES.keys())

    strategy_map = _load_strategy_map_from_env()
    # Merge strategy_map from config file (lower priority than env)
    for sym, cls in file_cfg.get("strategy_map", {}).items():
        if sym.strip().upper() not in strategy_map:
            strategy_map[sym.strip().upper()] = str(cls).strip()
    default_class = _env("INTRADAY_DEFAULT_CLASS", "grid_reversion").strip() or "grid_reversion"
    if default_class not in DEFAULT_CLASS_CONFIGS:
        default_class = "grid_reversion"

    runtime_specs: Dict[str, dict] = {}
    csv_paths: Dict[str, Path] = {}
    for symbol in symbols:
        legacy = LEGACY_STRATEGIES.get(symbol)
        class_name = strategy_map.get(symbol)
        if not class_name and legacy:
            class_name = str(legacy["class"])
        if class_name not in DEFAULT_CLASS_CONFIGS:
            class_name = default_class

        if legacy and class_name == legacy["class"]:
            cfg = copy.deepcopy(legacy["config"])
        else:
            cfg = copy.deepcopy(DEFAULT_CLASS_CONFIGS[class_name])

        runtime_specs[symbol] = {"class": class_name, "config": cfg}
        csv_paths[symbol] = data_dir / f"{symbol}_M5.csv"
    return runtime_specs, csv_paths

# ── Telegram ────────────────────────────────────────────────────────────────────
def _tg(token: str, chat_id: str, msg: str) -> None:
    if not token or not chat_id:
        return
    payload = json.dumps({"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}).encode()
    req = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, context=ssl.create_default_context(), timeout=10):
            pass
    except Exception:
        pass


def _load_monthly_managed_symbols() -> set[str]:
    symbols: set[str] = set()
    csv_path = MONTHLY_RUNTIME_DIR / "current_cycle_picks.csv"
    if not csv_path.exists():
        return symbols
    try:
        with csv_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                sym = str(row.get("ticker") or "").strip().upper()
                if sym:
                    symbols.add(sym)
    except Exception:
        return set()
    return symbols


def _fmt_usd_compact(value: float) -> str:
    amount = float(value or 0.0)
    if abs(amount) >= 1.0:
        return f"${amount:.2f}"
    if abs(amount) >= 0.01:
        return f"${amount:.3f}"
    return f"${amount:.4f}"


def _humanize_reason(reason: str) -> str:
    raw = str(reason or "").strip()
    if not raw:
        return "strategy signal"
    mapping = {
        "fx_grid_reversion_long": "grid reversion long",
        "fx_grid_reversion_short": "grid reversion short",
        "fx_breakout_continuation_long": "breakout continuation long",
        "fx_breakout_continuation_short": "breakout continuation short",
        "fx_trend_retest_long": "trend retest long",
        "fx_trend_retest_short": "trend retest short",
        "fx_trend_pullback_rebound_long": "trend pullback rebound long",
        "fx_trend_pullback_rebound_short": "trend pullback rebound short",
    }
    if raw in mapping:
        return mapping[raw]
    cleaned = raw.replace("fx_", "").replace("_", " ").strip()
    return cleaned or raw

# ── Alpaca client ───────────────────────────────────────────────────────────────
class AlpacaClient:
    def __init__(self, base_url: str, key_id: str, secret_key: str):
        self.base_url = base_url.rstrip("/")
        self.key_id = key_id
        self.secret_key = secret_key
        self._ssl = ssl.create_default_context()

    def _headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.key_id,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json",
        }

    def _req(self, method: str, url: str, payload: Optional[dict] = None) -> Any:
        body = json.dumps(payload).encode() if payload is not None else None
        req = request.Request(url, data=body, headers=self._headers(), method=method)
        try:
            with request.urlopen(req, context=self._ssl, timeout=20) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {url} → {exc.code}: {detail}") from exc

    def get_account(self) -> dict:
        return self._req("GET", f"{self.base_url}/v2/account")

    def list_positions(self) -> List[dict]:
        return list(self._req("GET", f"{self.base_url}/v2/positions") or [])

    def list_orders(self, status: str = "open") -> List[dict]:
        return list(self._req("GET", f"{self.base_url}/v2/orders?status={status}") or [])

    def submit_bracket_order(self, symbol: str, side: str, qty: int,
                             stop_loss_price: float, take_profit_price: float) -> dict:
        payload: dict = {
            "symbol": symbol, "qty": str(qty), "side": side,
            "type": "market", "time_in_force": "day", "order_class": "bracket",
            "stop_loss":   {"stop_price":  f"{stop_loss_price:.2f}"},
            "take_profit": {"limit_price": f"{take_profit_price:.2f}"},
        }
        return self._req("POST", f"{self.base_url}/v2/orders", payload)

    def close_position(self, symbol: str) -> dict:
        return self._req("DELETE", f"{self.base_url}/v2/positions/{symbol}")

    def get_bars_raw(self, symbol: str, timeframe: str = "5Min",
                     limit: int = 500) -> List[dict]:
        """Returns raw bar dicts from Alpaca data API."""
        url = (f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/bars"
               f"?timeframe={timeframe}&limit={limit}&adjustment=raw&feed=iex")
        data = self._req("GET", url)
        return list(data.get("bars") or [])

    def get_bars(self, symbol: str, timeframe: str = "5Min",
                 limit: int = 500) -> List[Candle]:
        candles: List[Candle] = []
        for b in self.get_bars_raw(symbol, timeframe, limit):
            t_str = b.get("t", "")
            try:
                dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                ts = int(dt.timestamp())
            except Exception:
                continue
            candles.append(Candle(
                ts=ts, o=float(b.get("o", 0)), h=float(b.get("h", 0)),
                l=float(b.get("l", 0)), c=float(b.get("c", 0)), v=float(b.get("v", 0)),
            ))
        return candles

    def get_daily_closes(self, symbol: str, limit: int = 60) -> List[float]:
        """Fetch daily close prices for SMA computation."""
        bars = self.get_bars_raw(symbol, timeframe="1Day", limit=limit)
        return [float(b.get("c", 0)) for b in bars if b.get("c")]

# ── State: open positions ───────────────────────────────────────────────────────
@dataclass
class PositionState:
    symbol: str
    side: str
    entry_price: float
    sl_price: float
    tp_price: float
    qty: int
    entry_ts: int
    alpaca_order_id: str = ""
    realized_pnl: float = 0.0   # filled on close

def _load_state() -> Dict[str, PositionState]:
    if not STATE_FILE.exists():
        return {}
    try:
        raw = json.loads(STATE_FILE.read_text())
        return {k: PositionState(**v) for k, v in raw.items()}
    except Exception:
        return {}

def _save_state(state: Dict[str, PositionState]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({k: asdict(v) for k, v in state.items()}, indent=2))

# ── Equity curve log ────────────────────────────────────────────────────────────
@dataclass
class DailyPnL:
    date: str        # YYYY-MM-DD
    pnl_usd: float   # realized P&L that day

def _load_equity_log() -> List[DailyPnL]:
    if not EQUITY_LOG_FILE.exists():
        return []
    try:
        raw = json.loads(EQUITY_LOG_FILE.read_text())
        return [DailyPnL(**e) for e in raw]
    except Exception:
        return []

def _save_equity_log(log: List[DailyPnL]) -> None:
    EQUITY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    EQUITY_LOG_FILE.write_text(json.dumps([asdict(e) for e in log], indent=2))


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)

def _record_daily_pnl(pnl_usd: float) -> None:
    """Add today's P&L to the equity log (accumulates intraday)."""
    today = date.today().isoformat()
    log = _load_equity_log()
    if log and log[-1].date == today:
        log[-1].pnl_usd += pnl_usd
    else:
        log.append(DailyPnL(date=today, pnl_usd=pnl_usd))
    # Keep last 90 days
    log = log[-90:]
    _save_equity_log(log)

def _get_today_pnl() -> float:
    today = date.today().isoformat()
    log = _load_equity_log()
    if log and log[-1].date == today:
        return log[-1].pnl_usd
    return 0.0

# ── Layer 1: SPY Regime Gate ────────────────────────────────────────────────────
def _spy_regime_ok(client: AlpacaClient, dry_run: bool,
                   sma_period: int = 50) -> tuple[bool, str]:
    """
    Returns (ok, reason).
    ok=True  → SPY above SMA{sma_period}, longs allowed.
    ok=False → SPY below SMA{sma_period}, bearish regime, no new longs.
    In dry-run mode: tries to use cached SPY CSV, falls back to ok=True.
    """
    def _cached_spy_closes() -> List[float]:
        spy_csv = ROOT / "data_cache" / "equities_1h" / "SPY_M5.csv"
        if not spy_csv.exists():
            return []
        m5 = load_m5_csv(str(spy_csv))
        daily: Dict[str, float] = {}
        for c in m5:
            d = datetime.fromtimestamp(c.ts, tz=timezone.utc).strftime("%Y-%m-%d")
            daily[d] = c.c
        return [v for v in list(daily.values())[-(sma_period + 5):]]

    closes: List[float] = []

    if not dry_run:
        try:
            closes = client.get_daily_closes("SPY", limit=sma_period + 5)
        except Exception as exc:
            closes = _cached_spy_closes()
            if not closes:
                return True, f"SPY fetch failed ({exc}) and no cache — allowing by default"
        if len(closes) < sma_period:
            cached = _cached_spy_closes()
            if cached:
                closes = cached
    else:
        closes = _cached_spy_closes()
        if not closes:
            return True, "SPY CSV not found — allowing by default (dry-run)"

    if len(closes) < sma_period:
        return True, f"Not enough SPY bars ({len(closes)}) — allowing by default"

    sma = sum(closes[-sma_period:]) / sma_period
    spy_last = closes[-1]
    pct_vs_sma = (spy_last / sma - 1.0) * 100

    if spy_last >= sma:
        return True, f"SPY ${spy_last:.2f} ≥ SMA{sma_period} ${sma:.2f} (+{pct_vs_sma:.1f}%) ✓"
    else:
        return False, f"SPY ${spy_last:.2f} < SMA{sma_period} ${sma:.2f} ({pct_vs_sma:.1f}%) ✗ BEARISH"

# ── Layer 2: Daily Loss Limit ────────────────────────────────────────────────────
def _daily_loss_ok(equity: float, max_loss_pct: float) -> tuple[bool, str]:
    """
    Returns (ok, reason).
    ok=False → today's P&L already hit the daily loss limit, no new entries.
    """
    today_pnl = _get_today_pnl()
    if equity <= 0:
        return True, "No equity data — skip daily loss check"
    loss_limit = -(equity * max_loss_pct / 100.0)
    pct_today = (today_pnl / equity) * 100
    if today_pnl < loss_limit:
        return False, (f"Daily loss limit hit: today P&L=${today_pnl:.2f} "
                       f"({pct_today:.2f}%), limit={max_loss_pct:.1f}% ✗")
    return True, f"Daily P&L: ${today_pnl:.2f} ({pct_today:.2f}%), limit OK ✓"

# ── Layer 3: Equity Curve Filter ────────────────────────────────────────────────
def _equity_curve_ok(window_days: int = 20) -> tuple[bool, str]:
    """
    Returns (ok, reason).
    ok=False → 20-day rolling P&L is negative, strategy in drawdown, pause entries.
    Uses 10-day MA of equity log as secondary smoothing.
    """
    log = _load_equity_log()
    if len(log) < 5:
        return True, f"Equity log too short ({len(log)} days) — allowing by default ✓"

    # Rolling sum over last window_days
    recent = log[-window_days:]
    rolling_pnl = sum(e.pnl_usd for e in recent)
    ma10_pnl = sum(e.pnl_usd for e in log[-10:]) if len(log) >= 10 else rolling_pnl

    if rolling_pnl >= 0 or ma10_pnl >= 0:
        return True, (f"Equity curve OK: {window_days}d P&L=${rolling_pnl:.2f}, "
                      f"10d MA=${ma10_pnl:.2f} ✓")
    return False, (f"Equity curve NEGATIVE: {window_days}d P&L=${rolling_pnl:.2f}, "
                   f"10d MA=${ma10_pnl:.2f} — observation mode ✗")

# ── Strategy helpers ────────────────────────────────────────────────────────────
def _build_strategy(symbol: str, strategy_specs: Dict[str, dict]):
    spec = strategy_specs[symbol]
    class_name = spec["class"]
    if class_name.startswith("breakout_continuation"):
        return BreakoutContinuationSessionV1(cfg=spec["config"])
    elif class_name.startswith("grid_reversion"):
        return GridReversionSessionV1(cfg=spec["config"])
    elif class_name.startswith("trend_retest"):
        return TrendRetestSessionV1(cfg=spec["config"])
    elif class_name.startswith("trend_pullback_rebound"):
        return TrendPullbackReboundV1(cfg=spec["config"])
    raise ValueError(f"Unknown strategy class: {spec['class']}")

def _load_candles(symbol: str, client: AlpacaClient, dry_run: bool,
                  csv_paths: Dict[str, Path]) -> List[Candle]:
    historical: List[Candle] = []
    csv_path = csv_paths.get(symbol)
    if csv_path and csv_path.exists():
        historical = load_m5_csv(str(csv_path))[-1500:]

    live: List[Candle] = []
    if not dry_run:
        try:
            live = client.get_bars(symbol, timeframe="5Min", limit=200)
        except Exception as exc:
            print(f"    [WARN] Live bars failed for {symbol}: {exc}")

    all_by_ts: Dict[int, Candle] = {c.ts: c for c in historical}
    for c in live:
        all_by_ts[c.ts] = c
    return sorted(all_by_ts.values(), key=lambda c: c.ts)

def _check_signal_last(candles: List[Candle], symbol: str,
                       strategy_specs: Dict[str, dict]) -> Optional[Signal]:
    if len(candles) < 250:
        return None
    strat = _build_strategy(symbol, strategy_specs)
    result: Optional[Signal] = None
    n = len(candles)
    for i in range(n):
        sig = strat.maybe_signal(candles, i)
        if i == n - 1:
            result = sig
    return result

# ── Main logic ──────────────────────────────────────────────────────────────────
def run_once(client: AlpacaClient, dry_run: bool,
             strategy_specs: Dict[str, dict], csv_paths: Dict[str, Path],
             verbose: bool = True) -> None:
    notional_usd   = _env_float("INTRADAY_NOTIONAL_USD", 200.0)
    max_positions  = _env_int("INTRADAY_MAX_POSITIONS", 3)
    spy_gate_on    = _env_bool("INTRADAY_SPY_GATE", True)
    spy_sma_period = _env_int("INTRADAY_SPY_SMA_PERIOD", 50)
    max_daily_loss = _env_float("INTRADAY_MAX_DAILY_LOSS_PCT", 2.0)
    eq_curve_on    = _env_bool("INTRADAY_EQUITY_CURVE_GATE", True)
    eq_curve_days  = _env_int("INTRADAY_EQUITY_CURVE_DAYS", 20)
    tg_token       = _env("TG_TOKEN")
    tg_chat        = _env("TG_CHAT_ID")

    now_utc = datetime.now(timezone.utc)
    now_ts  = int(now_utc.timestamp())
    now_str = now_utc.strftime("%Y-%m-%d %H:%M UTC")
    advisory: Dict[str, Any] = {
        "generated_at_utc": now_str,
        "generated_ts": now_ts,
        "mode": "DRY_RUN" if dry_run else "LIVE_PAPER",
        "entries_blocked": False,
        "protection": {},
        "account": {},
        "watchlist": list(strategy_specs.keys()),
        "open_positions": [],
        "remote_only_positions": [],
        "symbols": [],
        "today_pnl_usd": 0.0,
    }

    print(f"\n{'='*62}")
    print(f"  Intraday Bridge — {now_str} {'[DRY-RUN]' if dry_run else '[LIVE PAPER]'}")
    print(f"{'='*62}")

    # ── Account info ───────────────────────────────────────────────
    equity = 0.0
    try:
        acct   = client.get_account()
        equity = float(acct.get("equity") or acct.get("portfolio_value") or 0)
        cash   = float(acct.get("cash") or 0)
        advisory["account"] = {"equity": equity, "cash": cash}
        print(f"  Account: equity=${equity:.2f}  cash=${cash:.2f}")
    except Exception as exc:
        advisory["account_error"] = str(exc)
        print(f"  [WARN] Account fetch failed: {exc}")

    # ── 3-Layer filter check ───────────────────────────────────────
    print(f"\n  ── Protection Filters ──")

    # Layer 1: SPY regime
    entries_blocked = False
    spy_ok, spy_msg = True, "SPY gate disabled"
    if spy_gate_on:
        spy_ok, spy_msg = _spy_regime_ok(client, dry_run, spy_sma_period)
    print(f"  [L1-SPY]    {spy_msg}")
    advisory["protection"]["spy"] = {"enabled": spy_gate_on, "ok": spy_ok, "message": spy_msg}
    if not spy_ok:
        entries_blocked = True

    # Layer 2: Daily loss limit
    daily_ok, daily_msg = _daily_loss_ok(equity, max_daily_loss)
    print(f"  [L2-DAILY]  {daily_msg}")
    advisory["protection"]["daily_loss"] = {"enabled": True, "ok": daily_ok, "message": daily_msg}
    if not daily_ok:
        entries_blocked = True

    # Layer 3: Equity curve
    curve_ok, curve_msg = True, "Equity curve gate disabled"
    if eq_curve_on:
        curve_ok, curve_msg = _equity_curve_ok(eq_curve_days)
    print(f"  [L3-CURVE]  {curve_msg}")
    advisory["protection"]["equity_curve"] = {"enabled": eq_curve_on, "ok": curve_ok, "message": curve_msg}
    if not curve_ok:
        entries_blocked = True

    if entries_blocked:
        advisory["entries_blocked"] = True
        print(f"\n  ⛔ NEW ENTRIES BLOCKED by protection filter(s)")
        _tg(tg_token, tg_chat,
            f"⛔ <b>Intraday Bridge — entries blocked</b>\n"
            f"L1-SPY: {spy_msg}\nL2-Daily: {daily_msg}\nL3-Curve: {curve_msg}\n{now_str}")
    else:
        print(f"\n  ✅ All filters passed — scanning for signals")

    # ── Load open position state ───────────────────────────────────
    state = _load_state()

    # ── Sync with Alpaca: detect SL/TP closes ─────────────────────
    if not dry_run:
        try:
            open_positions = {p["symbol"]: p for p in client.list_positions()}
        except Exception:
            open_positions = {}

        closed = [sym for sym in list(state.keys()) if sym not in open_positions]
        for sym in closed:
            ps = state.pop(sym)
            held_min = (now_ts - ps.entry_ts) // 60

            # Estimate realized P&L from position data
            alp_pos = open_positions.get(sym, {})
            realized = float(alp_pos.get("unrealized_pl", 0))  # fallback estimate
            _record_daily_pnl(realized)

            realized_label = _fmt_usd_compact(realized)
            print(f"\n  [{sym}] ✓ Position closed (SL/TP) after {held_min}m "
                  f"| est. P&L={realized_label}")
            _tg(tg_token, tg_chat,
                f"📊 <b>{sym}</b> closed (SL/TP) after {held_min}m\n"
                f"Entry=${ps.entry_price:.2f} | SL=${ps.sl_price:.2f} | TP=${ps.tp_price:.2f}\n"
                f"Est. P&L: {realized_label}")
        _save_state(state)

        monthly_managed_symbols = _load_monthly_managed_symbols()
        remote_only_symbols = sorted(sym for sym in open_positions.keys() if sym not in state)
        protected_remote_symbols = sorted(sym for sym in remote_only_symbols if sym in monthly_managed_symbols)
        remote_only_symbols = sorted(sym for sym in remote_only_symbols if sym not in monthly_managed_symbols)
        advisory["remote_only_positions"] = list(remote_only_symbols)
        advisory["monthly_managed_symbols"] = sorted(monthly_managed_symbols)
        advisory["monthly_managed_positions"] = list(protected_remote_symbols)
        close_unknown_remote = _env_bool("INTRADAY_CLOSE_UNKNOWN_REMOTE_POSITIONS", False)
        if protected_remote_symbols:
            print(f"\n  [INFO] Monthly-managed remote paper positions preserved: {', '.join(protected_remote_symbols)}")
        if remote_only_symbols:
            print(f"\n  [WARN] Remote paper positions not tracked by intraday state: {', '.join(remote_only_symbols)}")
            if close_unknown_remote:
                for sym in remote_only_symbols:
                    try:
                        result = client.close_position(sym)
                        print(f"    → Close sent for unknown remote position {sym}: {result.get('status') or result.get('id') or 'submitted'}")
                        _tg(
                            tg_token,
                            tg_chat,
                            f"🧹 <b>Intraday cleanup</b>\nClosed stale remote Alpaca paper position: <b>{sym}</b>\n{now_str}",
                        )
                    except Exception as exc:
                        print(f"    ✗ Failed to close unknown remote position {sym}: {exc}")
                        _tg(tg_token, tg_chat, f"⚠️ <b>Intraday cleanup</b> failed for {sym}: {exc}")
            else:
                print("    → Keeping them as occupied slots for this cycle")
    else:
        open_positions = {}
        remote_only_symbols = []
        monthly_managed_symbols = _load_monthly_managed_symbols()
        protected_remote_symbols = []
        advisory["monthly_managed_symbols"] = sorted(monthly_managed_symbols)

    occupied_symbols = sorted(
        set(state.keys())
        | set(remote_only_symbols)
        | set(protected_remote_symbols)
        | set(monthly_managed_symbols)
    )
    open_count = len(occupied_symbols)
    advisory["open_positions"] = list(occupied_symbols)
    print(f"\n  Open positions: {open_count}/{max_positions} — {occupied_symbols or 'none'}")

    # ── Signal scan ────────────────────────────────────────────────
    for symbol in strategy_specs:
        symbol_status: Dict[str, Any] = {
            "symbol": symbol,
            "strategy_class": str(strategy_specs.get(symbol, {}).get("class", "")),
            "status": "unknown",
        }
        print(f"\n  [{symbol}]")

        if symbol in state:
            ps = state[symbol]
            held_min = (now_ts - ps.entry_ts) // 60
            symbol_status.update({"status": "already_open", "held_min": held_min})
            advisory["symbols"].append(symbol_status)
            print(f"    → In position {held_min}m | "
                  f"entry=${ps.entry_price:.2f} SL=${ps.sl_price:.2f} TP=${ps.tp_price:.2f}")
            continue

        if symbol in remote_only_symbols:
            symbol_status["status"] = "remote_only_position"
            advisory["symbols"].append(symbol_status)
            print(f"    → Remote Alpaca position exists outside intraday state — skip")
            continue

        if symbol in protected_remote_symbols:
            symbol_status["status"] = "monthly_managed_position"
            advisory["symbols"].append(symbol_status)
            print(f"    → Monthly-managed Alpaca position exists — preserve and skip")
            continue

        if symbol in monthly_managed_symbols:
            symbol_status["status"] = "monthly_managed_symbol"
            advisory["symbols"].append(symbol_status)
            print(f"    → Reserved by monthly Alpaca cycle — skip")
            continue

        if entries_blocked:
            symbol_status["status"] = "blocked_by_protection"
            advisory["symbols"].append(symbol_status)
            print(f"    → Skipped (protection filter active)")
            continue

        if open_count >= max_positions:
            symbol_status["status"] = "max_positions_reached"
            advisory["symbols"].append(symbol_status)
            print(f"    → Max positions ({max_positions}) reached — skip")
            continue

        # Load candles (historical seed + live)
        candles = _load_candles(symbol, client, dry_run, csv_paths)
        if len(candles) < 250:
            symbol_status.update({"status": "not_enough_candles", "candles": len(candles)})
            advisory["symbols"].append(symbol_status)
            print(f"    → Not enough candles ({len(candles)}) — skip")
            continue
        last_dt = datetime.fromtimestamp(candles[-1].ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        print(f"    Loaded {len(candles)} candles | last bar: {last_dt}")

        # Session check
        last_hour = (candles[-1].ts // 3600) % 24
        if not (US_SESSION_UTC_START <= last_hour < US_SESSION_UTC_END):
            symbol_status.update({"status": "outside_session", "last_hour_utc": last_hour})
            advisory["symbols"].append(symbol_status)
            print(f"    → Outside session (hour={last_hour} UTC) — skip")
            continue

        # Strategy signal
        sig = _check_signal_last(candles, symbol, strategy_specs)
        if sig is None:
            symbol_status["status"] = "no_signal"
            advisory["symbols"].append(symbol_status)
            print(f"    → No signal")
            continue

        # Validate geometry
        entry_price = candles[-1].c
        sl_price, tp_price = sig.sl, sig.tp
        if sig.side == "long":
            if not (sl_price < entry_price < tp_price):
                symbol_status.update({"status": "invalid_geometry", "side": sig.side})
                advisory["symbols"].append(symbol_status)
                print(f"    → Geometry invalid (long): SL={sl_price:.2f} e={entry_price:.2f} TP={tp_price:.2f}")
                continue
        else:
            if not (tp_price < entry_price < sl_price):
                symbol_status.update({"status": "invalid_geometry", "side": sig.side})
                advisory["symbols"].append(symbol_status)
                print(f"    → Geometry invalid (short): TP={tp_price:.2f} e={entry_price:.2f} SL={sl_price:.2f}")
                continue

        qty             = max(1, int(notional_usd / entry_price))
        actual_notional = qty * entry_price
        risk_usd        = abs(entry_price - sl_price) * qty
        rr_label        = f"RR≈{abs(tp_price-entry_price)/max(1e-6,abs(entry_price-sl_price)):.1f}"

        print(f"    ★ SIGNAL {sig.side.upper()} | e≈${entry_price:.2f} | "
              f"SL=${sl_price:.2f} TP=${tp_price:.2f} | {rr_label}")
        print(f"      qty={qty} | notional=${actual_notional:.2f} | risk≈${risk_usd:.2f}")

        if dry_run:
            symbol_status.update({
                "status": "dry_run_signal",
                "side": sig.side,
                "entry_price": round(entry_price, 4),
                "sl_price": round(sl_price, 4),
                "tp_price": round(tp_price, 4),
                "qty": qty,
                "rr_label": rr_label,
                "reason": sig.reason or "",
            })
            advisory["symbols"].append(symbol_status)
            print(f"    → [DRY-RUN] Would submit bracket order")
            _tg(tg_token, tg_chat,
                f"🔍 <b>[DRY-RUN] {symbol}</b> {sig.side.upper()}\n"
                f"e≈${entry_price:.2f} | SL=${sl_price:.2f} | TP=${tp_price:.2f} | {rr_label}\n"
                f"Qty={qty} | Risk≈${risk_usd:.2f} | {now_str}")
        else:
            try:
                alpaca_side = "buy" if sig.side == "long" else "sell"
                order = client.submit_bracket_order(
                    symbol=symbol, side=alpaca_side, qty=qty,
                    stop_loss_price=sl_price, take_profit_price=tp_price,
                )
                order_id = order.get("id", "")
                print(f"    ✅ Order submitted: {order_id}")
                state[symbol] = PositionState(
                    symbol=symbol, side=sig.side, entry_price=entry_price,
                    sl_price=sl_price, tp_price=tp_price, qty=qty,
                    entry_ts=now_ts, alpaca_order_id=order_id,
                )
                open_count += 1
                _save_state(state)
                symbol_status.update({
                    "status": "order_submitted",
                    "side": sig.side,
                    "entry_price": round(entry_price, 4),
                    "sl_price": round(sl_price, 4),
                    "tp_price": round(tp_price, 4),
                    "qty": qty,
                    "rr_label": rr_label,
                    "reason": sig.reason or "",
                    "order_id": order_id,
                })
                advisory["symbols"].append(symbol_status)
                reason_label = _humanize_reason(sig.reason)
                _tg(tg_token, tg_chat,
                    f"📈 <b>{symbol}</b> {sig.side.upper()} entry\n"
                    f"Price≈${entry_price:.2f} | SL=${sl_price:.2f} | TP=${tp_price:.2f} | {rr_label}\n"
                    f"Qty={qty} | Notional≈${actual_notional:.2f} | Risk≈${risk_usd:.2f}\n"
                    f"Reason: {reason_label} | {now_str}")
            except Exception as exc:
                symbol_status.update({"status": "order_failed", "error": str(exc)})
                advisory["symbols"].append(symbol_status)
                print(f"    ✗ Order failed: {exc}")
                _tg(tg_token, tg_chat, f"⚠️ <b>{symbol}</b> order error: {exc}")

    print(f"\n  Done. Open: {list(state.keys()) or 'none'}")
    print(f"  Today P&L: ${_get_today_pnl():.2f}")
    advisory["today_pnl_usd"] = _get_today_pnl()
    advisory["open_positions"] = sorted(set(state.keys()) | set(remote_only_symbols))
    _write_json_atomic(ADVISORY_FILE, advisory)

# ── CLI ─────────────────────────────────────────────────────────────────────────
def main() -> None:
    _load_env_file(ENV_FILE)

    ap = argparse.ArgumentParser(description="Alpaca Intraday Bridge — 3-Layer Protection")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="No orders (default)")
    mode.add_argument("--live",    action="store_true", help="Submit real paper orders")
    run_m = ap.add_mutually_exclusive_group()
    run_m.add_argument("--once",   action="store_true", help="Run once then exit (cron)")
    run_m.add_argument("--daemon", action="store_true", help="Loop every N seconds")
    ap.add_argument("--interval", type=int, default=300, help="Daemon interval (s)")
    args = ap.parse_args()

    dry_run  = not args.live
    key_id   = _env("ALPACA_API_KEY_ID")
    secret   = _env("ALPACA_API_SECRET_KEY")
    base_url = _env("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    if not key_id or not secret:
        print("ERROR: ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY not set.")
        sys.exit(1)

    client = AlpacaClient(base_url, key_id, secret)

    print(f"Alpaca Intraday Bridge v2 (3-Layer Protection)")
    print(f"  Mode: {'DRY-RUN' if dry_run else 'LIVE PAPER'}")
    print(f"  Filters: SPY={_env_bool('INTRADAY_SPY_GATE', True)} | "
          f"DailyLoss={_env_float('INTRADAY_MAX_DAILY_LOSS_PCT', 2.0)}% | "
          f"EqCurve={_env_bool('INTRADAY_EQUITY_CURVE_GATE', True)}")

    if args.daemon:
        print(f"  Daemon mode (interval={args.interval}s) — Ctrl+C to stop")
        while True:
            try:
                strategy_specs, csv_paths = _build_runtime_catalog()
                print(f"  Watchlist ({len(strategy_specs)}): {', '.join(strategy_specs)}")
                run_once(client, dry_run=dry_run, strategy_specs=strategy_specs, csv_paths=csv_paths)
            except KeyboardInterrupt:
                print("\nStopped.")
                break
            except Exception as exc:
                print(f"[ERROR] {exc}")
            time.sleep(args.interval)
    else:
        strategy_specs, csv_paths = _build_runtime_catalog()
        print(f"  Watchlist ({len(strategy_specs)}): {', '.join(strategy_specs)}")
        run_once(client, dry_run=dry_run, strategy_specs=strategy_specs, csv_paths=csv_paths)


if __name__ == "__main__":
    main()
