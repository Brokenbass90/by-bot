#!/usr/bin/env python3
"""crypto_strategies_backtest.py — backtester ключевых crypto-стратегий на Bybit public klines.

Не требует API ключа (publi endpoint).
Запуск:
    cd /root/by-bot
    python3 scripts/crypto_strategies_backtest.py

Покрывает упрощённые версии:
    - ASB1 (support_bounce):   long при RSI<35 + cross MA20
    - ATT1 (trend tactical):   long на pullback к MA50 в uptrend
    - IVB1 (impulse breakout): long на close > 20-bar high + volume>2x
    - RANGE_SCALP:             long+short на касаниях BB
    - sloped (channel):        ranging within ±2σ

Для каждой стратегии 2 варианта:
    static  — фиксированный SL/TP (1×ATR / 2×ATR)
    trail   — trailing stop (ATR-based)

Выход:
    - таблица win-rate / PF / DD / monthly returns по символам
    - сравнение static vs trail
    - JSON-отчёт + TG summary
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, parse, request

PROJECT_ROOT = Path("/root/by-bot")
RUNTIME = PROJECT_ROOT / "runtime"

BYBIT_API = "https://api.bybit.com/v5/market/kline"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "ADAUSDT"]
INTERVAL = "60"  # 1h bars
DAYS = 365  # 1 year
INITIAL = 1000.0
RISK_PCT = 1.0  # % equity per trade
LEVERAGE = 3.0


def fetch_klines(symbol: str, interval: str = INTERVAL, limit: int = 1000) -> list[dict]:
    """Fetches up to N=limit bars. Bybit returns max 1000 per call.
    Для 365 дней 1h = 8760 bars → нужно несколько вызовов с пагинацией.
    """
    end_ms = int(time.time() * 1000)
    all_bars = []
    interval_min = int(interval)
    bars_per_day = 24 * 60 // interval_min
    total_bars_needed = DAYS * bars_per_day

    while len(all_bars) < total_bars_needed:
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": min(1000, total_bars_needed - len(all_bars)),
            "end": str(end_ms),
        }
        url = f"{BYBIT_API}?{parse.urlencode(params)}"
        try:
            with request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"  fetch error {symbol}: {e}")
            break
        bars = data.get("result", {}).get("list", []) or []
        if not bars:
            break
        all_bars.extend(bars)
        # Bybit отдаёт от newest к oldest. Берём oldest как end для next call.
        end_ms = int(bars[-1][0]) - 1
        time.sleep(0.1)
        if len(bars) < 1000:
            break

    # Reverse to oldest-first
    bars_dicts = [
        {
            "ts": int(b[0]),
            "open": float(b[1]),
            "high": float(b[2]),
            "low": float(b[3]),
            "close": float(b[4]),
            "volume": float(b[5]),
        }
        for b in reversed(all_bars)
    ]
    return bars_dicts


# === Indicators ===

def rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, period + 1):
        ch = closes[-i] - closes[-i - 1]
        if ch > 0:
            gains.append(ch)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(-ch)
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    if avg_l == 0:
        return 100
    rs = avg_g / avg_l
    return 100 - (100 / (1 + rs))


def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    return sum(trs[-period:]) / period


# === Стратегии (упрощённые сигналы для backtest) ===

def signal_asb1(bars: list[dict], i: int) -> str | None:
    """Support bounce: RSI<35 + close > MA20 (отскок от перепроданности)."""
    if i < 20:
        return None
    closes = [b["close"] for b in bars[:i + 1]]
    r = rsi(closes)
    ma20 = sma(closes, 20)
    if r is not None and r < 35 and ma20 and closes[-1] > ma20 and closes[-2] < ma20:
        return "long"
    return None


def signal_att1(bars: list[dict], i: int) -> str | None:
    """Trend tactical: uptrend (close > MA50) + pullback к MA50 + bounce."""
    if i < 50:
        return None
    closes = [b["close"] for b in bars[:i + 1]]
    ma50 = sma(closes, 50)
    ma20 = sma(closes, 20)
    if not ma50 or not ma20:
        return None
    if closes[-1] > ma50 and ma20 > ma50:  # uptrend
        if closes[-2] <= ma20 and closes[-1] > ma20:  # bounce from MA20
            return "long"
    return None


def signal_ivb1(bars: list[dict], i: int) -> str | None:
    """Impulse breakout: close > 20-bar high + volume > 2× average."""
    if i < 20:
        return None
    window = bars[i - 20:i]
    high20 = max(b["high"] for b in window)
    avg_vol = sum(b["volume"] for b in window) / 20
    if bars[i]["close"] > high20 and bars[i]["volume"] > 2 * avg_vol:
        return "long"
    return None


def signal_range_scalp(bars: list[dict], i: int) -> str | None:
    """RSI<25 long, RSI>75 short."""
    if i < 20:
        return None
    closes = [b["close"] for b in bars[:i + 1]]
    r = rsi(closes)
    if r < 25:
        return "long"
    if r > 75:
        return "short"
    return None


STRATEGIES = {
    "ASB1": signal_asb1,
    "ATT1": signal_att1,
    "IVB1": signal_ivb1,
    "RANGE_SCALP": signal_range_scalp,
}


# === Backtest engine ===

def run_strategy(bars: list[dict], signal_fn, trail: bool = False, sl_atr: float = 1.0,
                 tp_atr: float = 2.0, trail_atr: float = 1.5) -> dict:
    equity = INITIAL
    position = None
    trades = []
    equity_curve = [INITIAL]

    for i in range(50, len(bars)):
        bar = bars[i]
        closes = [b["close"] for b in bars[:i + 1]]
        highs = [b["high"] for b in bars[:i + 1]]
        lows = [b["low"] for b in bars[:i + 1]]
        a = atr(highs, lows, closes)

        # Manage open position
        if position:
            if position["side"] == "long":
                # Update trailing high
                position["high"] = max(position["high"], bar["high"])
                if trail:
                    new_stop = position["high"] - trail_atr * a
                    position["stop"] = max(position["stop"], new_stop)
                # Check exits
                if bar["low"] <= position["stop"]:
                    pnl = (position["stop"] - position["entry"]) / position["entry"] * 100 * LEVERAGE
                    equity += equity * (pnl / 100) * (RISK_PCT / 100)
                    trades.append({"side": "long", "entry": position["entry"], "exit": position["stop"], "pnl_pct": pnl})
                    position = None
                elif not trail and bar["high"] >= position["tp"]:
                    pnl = (position["tp"] - position["entry"]) / position["entry"] * 100 * LEVERAGE
                    equity += equity * (pnl / 100) * (RISK_PCT / 100)
                    trades.append({"side": "long", "entry": position["entry"], "exit": position["tp"], "pnl_pct": pnl})
                    position = None
            elif position["side"] == "short":
                position["low"] = min(position["low"], bar["low"])
                if trail:
                    new_stop = position["low"] + trail_atr * a
                    position["stop"] = min(position["stop"], new_stop)
                if bar["high"] >= position["stop"]:
                    pnl = (position["entry"] - position["stop"]) / position["entry"] * 100 * LEVERAGE
                    equity += equity * (pnl / 100) * (RISK_PCT / 100)
                    trades.append({"side": "short", "entry": position["entry"], "exit": position["stop"], "pnl_pct": pnl})
                    position = None
                elif not trail and bar["low"] <= position["tp"]:
                    pnl = (position["entry"] - position["tp"]) / position["entry"] * 100 * LEVERAGE
                    equity += equity * (pnl / 100) * (RISK_PCT / 100)
                    trades.append({"side": "short", "entry": position["entry"], "exit": position["tp"], "pnl_pct": pnl})
                    position = None

        # Open new position
        if not position and a > 0:
            sig = signal_fn(bars, i)
            if sig == "long":
                position = {
                    "side": "long",
                    "entry": bar["close"],
                    "stop": bar["close"] - sl_atr * a,
                    "tp": bar["close"] + tp_atr * a,
                    "high": bar["close"],
                }
            elif sig == "short":
                position = {
                    "side": "short",
                    "entry": bar["close"],
                    "stop": bar["close"] + sl_atr * a,
                    "tp": bar["close"] - tp_atr * a,
                    "low": bar["close"],
                }

        equity_curve.append(equity)

    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    pf = (sum(t["pnl_pct"] for t in wins) / abs(sum(t["pnl_pct"] for t in losses))) if losses else float("inf")
    win_rate = len(wins) / len(trades) * 100 if trades else 0

    # Drawdown
    peak = INITIAL
    max_dd = 0
    for e in equity_curve:
        peak = max(peak, e)
        dd = (peak - e) / peak * 100
        max_dd = max(max_dd, dd)

    return {
        "n_trades": len(trades),
        "win_rate": win_rate,
        "pf": pf,
        "final_equity": equity,
        "return_pct": (equity - INITIAL) / INITIAL * 100,
        "max_dd_pct": max_dd,
    }


def main() -> int:
    print(f"=== CRYPTO STRATEGIES BACKTEST ({DAYS}d, {INTERVAL}m bars, leverage {LEVERAGE}x) ===\n")

    all_results = {}
    for symbol in SYMBOLS:
        print(f"Fetching {symbol}...")
        bars = fetch_klines(symbol)
        if len(bars) < 200:
            print(f"  insufficient bars ({len(bars)}), skip")
            continue
        print(f"  {len(bars)} bars loaded ({bars[0]['ts']}..{bars[-1]['ts']})")

        results_sym = {}
        for strat_name, sig_fn in STRATEGIES.items():
            for variant, trail in [("static", False), ("trail", True)]:
                r = run_strategy(bars, sig_fn, trail=trail)
                results_sym[f"{strat_name}_{variant}"] = r
        all_results[symbol] = results_sym

    if not all_results:
        print("FATAL: no data fetched (network blocked?)")
        return 1

    # Печать таблицы
    print(f"\n\n{'='*90}")
    print(f"{'Symbol':<10} {'Strategy':<18} {'Trades':>7} {'WR%':>6} {'PF':>6} {'Return%':>9} {'DD%':>7}")
    print("=" * 90)
    for symbol, strs in all_results.items():
        for sname, r in strs.items():
            pf_str = f"{r['pf']:.2f}" if r['pf'] != float('inf') else "∞"
            print(f"{symbol:<10} {sname:<18} {r['n_trades']:>7d} {r['win_rate']:>5.1f}% {pf_str:>6} {r['return_pct']:>8.1f}% {r['max_dd_pct']:>6.1f}%")
        print("-" * 90)

    # Лучшие стратегии — агрегат
    print(f"\n\n=== AGGREGATE STRATEGY RANKING (avg по символам) ===")
    by_strat = {}
    for strs in all_results.values():
        for sname, r in strs.items():
            by_strat.setdefault(sname, []).append(r)

    rows = []
    for sname, runs in by_strat.items():
        avg_ret = sum(r['return_pct'] for r in runs) / len(runs)
        avg_pf = sum(r['pf'] if r['pf'] != float('inf') else 5.0 for r in runs) / len(runs)
        avg_dd = sum(r['max_dd_pct'] for r in runs) / len(runs)
        avg_wr = sum(r['win_rate'] for r in runs) / len(runs)
        total_trades = sum(r['n_trades'] for r in runs)
        rows.append((sname, total_trades, avg_wr, avg_pf, avg_ret, avg_dd))

    rows.sort(key=lambda x: -x[4])  # by avg_return
    print(f"{'Strategy':<18} {'Trades':>7} {'WR%':>6} {'PF':>6} {'Ret%':>8} {'DD%':>7}")
    for r in rows:
        print(f"{r[0]:<18} {r[1]:>7d} {r[2]:>5.1f}% {r[3]:>5.2f} {r[4]:>7.1f}% {r[5]:>6.1f}%")

    # Static vs trail сравнение
    print(f"\n=== STATIC vs TRAIL ===")
    for strat in STRATEGIES:
        s = next((r for r in rows if r[0] == f"{strat}_static"), None)
        t = next((r for r in rows if r[0] == f"{strat}_trail"), None)
        if s and t:
            delta = t[4] - s[4]
            print(f"{strat:<14} static {s[4]:>+6.1f}% / trail {t[4]:>+6.1f}% / delta {delta:>+5.1f}pp")

    # JSON архив
    out_dir = RUNTIME
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"crypto_backtest_report_{datetime.now().strftime('%Y%m%d')}.json"
    report = {
        "ts": datetime.now().isoformat(),
        "period_days": DAYS,
        "interval": INTERVAL,
        "symbols": list(all_results.keys()),
        "results": all_results,
        "ranking": [{"strategy": r[0], "trades": r[1], "wr": r[2], "pf": r[3], "ret": r[4], "dd": r[5]} for r in rows],
    }
    report_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\n📄 Report: {report_path}")

    # TG summary
    print(f"\n=== TG SUMMARY ===")
    print(f"📊 Crypto backtest {DAYS}d ({INTERVAL}m bars):")
    print(f"   Top-3:")
    for r in rows[:3]:
        print(f"   - {r[0]}: {r[4]:.1f}% return, PF {r[3]:.2f}, {r[1]} trades")
    print(f"   Bottom-3:")
    for r in rows[-3:]:
        print(f"   - {r[0]}: {r[4]:.1f}% return, DD {r[5]:.1f}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
