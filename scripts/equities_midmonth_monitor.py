#!/usr/bin/env python3
"""Mid-month position health check for Alpaca equities.

Runs weekly (or on-demand) to check:
  1. Are current positions still healthy? (stop levels, regime)
  2. Should we exit early? (stop breach, thesis break)
  3. Regime health update

Sends Telegram alerts on issues.

Auto-exit mode (ALPACA_AUTO_EXIT_ENABLED=1):
  - Automatically submits market sell orders for positions flagged
    as STOP_BREACHED, CRITICAL_STOP, or DEEP_LOSS (>-8%).
  - ALPACA_AUTO_EXIT_MIN_LOSS_PCT (default -8.0): deep-loss threshold for auto-exit.
  - ALPACA_AUTO_EXIT_DRY_RUN=1: log what would be closed, but do not submit orders.
  - Default: disabled (ALPACA_AUTO_EXIT_ENABLED=0) — safe for manual operation.

Usage:
  # Load .env first
  source configs/alpaca_paper_local.env
  python3 scripts/equities_midmonth_monitor.py

Cron (weekly, Wed 15:00 UTC):
  0 15 * * 3 cd /root/by-bot && source configs/alpaca_paper_local.env && python3 scripts/equities_midmonth_monitor.py >> logs/alpaca_midmonth.log 2>&1
"""
from __future__ import annotations

import json
import math
import os
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import pstdev
from typing import Any
from urllib import error, request

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _env(name: str, default: str = "") -> str:
    val = os.getenv(name)
    return str(val).strip() if val is not None else default


def _tg_send(token: str, chat_id: str, msg: str) -> None:
    if not token or not chat_id:
        print(msg)
        return
    payload = json.dumps({
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "HTML",
    }).encode()
    req = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    ctx = ssl.create_default_context()
    try:
        with request.urlopen(req, context=ctx, timeout=10):
            pass
    except Exception:
        print(msg)


def _alpaca_request(base_url: str, key_id: str, secret: str, method: str, path: str, body: Any = None) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    headers = {
        "APCA-API-KEY-ID": key_id,
        "APCA-API-SECRET-KEY": secret,
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(url, data=data, headers=headers, method=method)
    ctx = ssl.create_default_context()
    try:
        with request.urlopen(req, context=ctx, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as e:
        return {"error": e.code, "detail": e.read().decode("utf-8", errors="replace")}


def _close_position(base_url: str, key_id: str, secret: str, symbol: str, qty: float, dry_run: bool = False) -> dict:
    """Submit a market sell order to close a long position."""
    if dry_run:
        print(f"[DRY_RUN] Would close {symbol} qty={qty}")
        return {"dry_run": True, "symbol": symbol}
    body = {
        "symbol": symbol,
        "qty": str(abs(qty)),
        "side": "sell",
        "type": "market",
        "time_in_force": "day",
    }
    return _alpaca_request(base_url, key_id, secret, "POST", "/v2/orders", body=body)


def _fetch_quote(ticker: str) -> dict | None:
    """Fetch latest quote from Yahoo Finance (no API key needed)."""
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        hist = tk.history(period="5d", interval="1h")
        if hist is None or hist.empty:
            return None
        last = hist.iloc[-1]
        return {
            "price": float(last["Close"]),
            "high_5d": float(hist["High"].max()),
            "low_5d": float(hist["Low"].min()),
        }
    except Exception:
        return None


def _compute_atr(ticker: str, period: int = 20) -> float | None:
    """Compute current ATR from recent daily data."""
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        hist = tk.history(period="60d", interval="1d")
        if hist is None or len(hist) < period + 1:
            return None
        trs = []
        for i in range(1, len(hist)):
            h = float(hist.iloc[i]["High"])
            l = float(hist.iloc[i]["Low"])
            pc = float(hist.iloc[i-1]["Close"])
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        if len(trs) < period:
            return None
        return sum(trs[-period:]) / period
    except Exception:
        return None


def _regime_check(benchmarks=("SPY", "QQQ")) -> dict:
    """Quick regime health check using benchmark momentum and SMA."""
    result = {}
    try:
        import yfinance as yf
        for ticker in benchmarks:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="6mo", interval="1d")
            if hist is None or len(hist) < 60:
                result[ticker] = {"status": "no_data"}
                continue
            closes = [float(x) for x in hist["Close"]]
            current = closes[-1]
            sma50 = sum(closes[-50:]) / 50
            sma20 = sum(closes[-20:]) / 20
            mom60 = (current / closes[-60] - 1.0) * 100 if len(closes) >= 60 else 0.0
            mom20 = (current / closes[-20] - 1.0) * 100 if len(closes) >= 20 else 0.0

            # Dynamic thresholds based on recent volatility
            rets = [(closes[i] / closes[i-1] - 1.0) for i in range(max(1, len(closes)-20), len(closes))]
            vol20 = pstdev(rets) if len(rets) >= 5 else 0.02
            vol_regime = "low" if vol20 < 0.012 else ("high" if vol20 > 0.025 else "normal")

            above_sma50 = current > sma50
            above_sma20 = current > sma20
            momentum_ok = mom20 > -2.0 and mom60 > 0.0

            if above_sma50 and above_sma20 and momentum_ok:
                status = "BULLISH"
            elif above_sma50 and (not above_sma20 or not momentum_ok):
                status = "CAUTIOUS"
            else:
                status = "BEARISH"

            result[ticker] = {
                "status": status,
                "price": round(current, 2),
                "sma50": round(sma50, 2),
                "sma20": round(sma20, 2),
                "mom20_pct": round(mom20, 2),
                "mom60_pct": round(mom60, 2),
                "vol20": round(vol20 * 100, 3),
                "vol_regime": vol_regime,
            }
    except Exception as e:
        result["error"] = str(e)
    return result


def main() -> int:
    key_id = _env("ALPACA_API_KEY_ID")
    secret = _env("ALPACA_API_SECRET_KEY")
    base_url = _env("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    tg_token = _env("TG_TOKEN")
    tg_chat_id = _env("TG_CHAT_ID")
    auto_exit_enabled = _env("ALPACA_AUTO_EXIT_ENABLED", "0").lower() in {"1", "true", "yes"}
    auto_exit_dry_run = _env("ALPACA_AUTO_EXIT_DRY_RUN", "0").lower() in {"1", "true", "yes"}
    auto_exit_min_loss = float(_env("ALPACA_AUTO_EXIT_MIN_LOSS_PCT", "-8.0"))

    if not key_id or not secret:
        print("error=missing_alpaca_keys")
        return 1

    # Get account + positions
    account = _alpaca_request(base_url, key_id, secret, "GET", "/v2/account")
    positions_raw = _alpaca_request(base_url, key_id, secret, "GET", "/v2/positions")
    if isinstance(positions_raw, dict) and "error" in positions_raw:
        print(f"error=positions_fetch_failed: {positions_raw}")
        return 2

    positions = positions_raw if isinstance(positions_raw, list) else []

    # Regime check
    regime = _regime_check()

    # Position health
    alerts = []
    auto_closed = []
    position_reports = []

    for pos in positions:
        sym = str(pos.get("symbol", "")).upper()
        qty = float(pos.get("qty", 0))
        avg_entry = float(pos.get("avg_entry_price", 0))
        current_price = float(pos.get("current_price", 0))
        unrealized_pl = float(pos.get("unrealized_pl", 0))
        unrealized_plpc = float(pos.get("unrealized_plpc", 0)) * 100

        # Compute ATR-based stop
        atr = _compute_atr(sym)
        stop_1_5atr = avg_entry - 1.5 * atr if atr else None
        stop_2atr = avg_entry - 2.0 * atr if atr else None

        # Health assessment
        health = "OK"
        auto_exit_reason = None
        if stop_2atr and current_price < stop_2atr:
            health = "CRITICAL_STOP"
            alerts.append(f"CRITICAL: {sym} at ${current_price:.2f} below 2xATR stop ${stop_2atr:.2f}")
            auto_exit_reason = "critical_stop_2atr"
        elif stop_1_5atr and current_price < stop_1_5atr:
            health = "STOP_BREACHED"
            alerts.append(f"STOP BREACHED: {sym} at ${current_price:.2f} below 1.5xATR stop ${stop_1_5atr:.2f}")
            auto_exit_reason = "stop_breached_1.5atr"
        elif unrealized_plpc < auto_exit_min_loss:
            health = "DEEP_LOSS"
            alerts.append(f"DEEP LOSS: {sym} at {unrealized_plpc:.1f}%")
            auto_exit_reason = f"deep_loss_{unrealized_plpc:.1f}pct"
        elif unrealized_plpc > 15.0:
            health = "CONSIDER_PARTIAL_TP"

        # Auto-exit if enabled and position is critical
        exit_result = None
        if auto_exit_enabled and auto_exit_reason and qty > 0:
            exit_result = _close_position(base_url, key_id, secret, sym, qty, dry_run=auto_exit_dry_run)
            prefix = "[DRY_RUN] " if auto_exit_dry_run else ""
            if "error" in (exit_result or {}):
                auto_closed.append(f"{prefix}CLOSE FAILED {sym}: {exit_result.get('detail', 'unknown')}")
            else:
                auto_closed.append(f"{prefix}CLOSED {sym} qty={qty} reason={auto_exit_reason}")
            health = health + "_AUTO_CLOSED"

        position_reports.append({
            "ticker": sym,
            "qty": qty,
            "entry": round(avg_entry, 2),
            "current": round(current_price, 2),
            "pnl_pct": round(unrealized_plpc, 2),
            "pnl_usd": round(unrealized_pl, 2),
            "atr": round(atr, 4) if atr else None,
            "stop_1_5atr": round(stop_1_5atr, 2) if stop_1_5atr else None,
            "health": health,
            "auto_exit_reason": auto_exit_reason,
            "exit_result": exit_result,
        })

    # Build Telegram message
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"<b>Mid-Month Check — {now_str}</b>"]
    lines.append("")

    # Regime
    for bm, data in regime.items():
        if isinstance(data, dict) and "status" in data:
            emoji = {"BULLISH": "🟢", "CAUTIOUS": "🟡", "BEARISH": "🔴"}.get(data["status"], "⚪")
            lines.append(f"{emoji} {bm}: {data['status']} | mom20={data.get('mom20_pct',0):.1f}% vol={data.get('vol20',0):.1f}%")

    lines.append("")

    # Positions
    if not position_reports:
        lines.append("📦 No open positions")
    else:
        total_pnl = sum(p["pnl_usd"] for p in position_reports)
        lines.append(f"📊 Positions ({len(position_reports)}) | Total PnL: ${total_pnl:.2f}")
        for p in position_reports:
            emoji = "🟢" if p["pnl_pct"] > 0 else "🔴"
            health_emoji = {"OK": "✅", "STOP_BREACHED": "🚨", "CRITICAL_STOP": "💀", "DEEP_LOSS": "⚠️", "CONSIDER_PARTIAL_TP": "💰"}.get(p["health"], "❓")
            lines.append(f"  {emoji} {p['ticker']}: ${p['current']} ({p['pnl_pct']:+.1f}%) {health_emoji}")
            if p["stop_1_5atr"]:
                lines.append(f"     stop=${p['stop_1_5atr']} ATR=${p['atr']:.2f}")

    # Alerts
    if alerts:
        lines.append("")
        lines.append("<b>⚠️ ALERTS:</b>")
        for a in alerts:
            lines.append(f"  • {a}")

    # Auto-exit actions
    if auto_exit_enabled and auto_closed:
        lines.append("")
        tag = "[DRY RUN] " if auto_exit_dry_run else ""
        lines.append(f"<b>🤖 {tag}Auto-Exit Actions:</b>")
        for ac in auto_closed:
            lines.append(f"  • {ac}")
    elif auto_exit_enabled:
        lines.append("")
        lines.append("🤖 Auto-exit: enabled — no positions triggered")

    msg = "\n".join(lines)
    _tg_send(tg_token, tg_chat_id, msg)

    # Save report
    report_path = ROOT / "docs" / "equities_midmonth_latest.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump({
            "timestamp": now_str,
            "regime": regime,
            "positions": position_reports,
            "alerts": alerts,
        }, f, indent=2)
    print(f"Report saved to {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
