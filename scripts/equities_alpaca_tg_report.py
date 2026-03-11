#!/usr/bin/env python3
"""
equities_alpaca_tg_report.py — Daily Telegram P&L report for Alpaca paper/live.

Usage:
    python3 scripts/equities_alpaca_tg_report.py          # daily P&L report
    python3 scripts/equities_alpaca_tg_report.py --monthly  # monthly summary

ENV vars required:
    ALPACA_API_KEY_ID      — Alpaca API key
    ALPACA_API_SECRET_KEY  — Alpaca secret
    ALPACA_BASE_URL        — paper: https://paper-api.alpaca.markets
    TG_TOKEN               — Telegram bot token (same as main bot)
    TG_CHAT_ID             — Telegram chat ID (same as main bot)

Schedule: run daily at 22:00 UTC (after US market close) via cron or scheduler.
Monthly: run on the 1st of each month.
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── Config ────────────────────────────────────────────────────────────────────
def _env(name: str, default: str = "") -> str:
    val = os.getenv(name)
    return str(val).strip() if val is not None else default


TG_TOKEN   = _env("TG_TOKEN")
TG_CHAT_ID = _env("TG_CHAT_ID")
ALPACA_KEY    = _env("ALPACA_API_KEY_ID")
ALPACA_SECRET = _env("ALPACA_API_SECRET_KEY")
ALPACA_URL    = _env("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
IS_PAPER = "paper" in ALPACA_URL.lower()
MODE_LABEL = "📄 PAPER" if IS_PAPER else "💰 LIVE"

_SSL = ssl.create_default_context()


# ── Alpaca helpers ────────────────────────────────────────────────────────────
def _alpaca(method: str, path: str, payload: dict | None = None) -> Any:
    url = f"{ALPACA_URL.rstrip('/')}{path}"
    body = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        url, data=body, method=method,
        headers={
            "APCA-API-KEY-ID": ALPACA_KEY,
            "APCA-API-SECRET-KEY": ALPACA_SECRET,
            "Content-Type": "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, context=_SSL, timeout=15) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.request.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Alpaca {method} {path}: {exc.code} {detail}") from exc


def get_account() -> dict:
    return _alpaca("GET", "/v2/account")


def get_positions() -> list[dict]:
    return list(_alpaca("GET", "/v2/positions"))


def get_closed_orders(after: str = "") -> list[dict]:
    """Get filled orders. after = ISO timestamp string."""
    qs = "status=filled&limit=100"
    if after:
        qs += f"&after={urllib.parse.quote(after)}"
    return list(_alpaca("GET", f"/v2/orders?{qs}"))


def get_portfolio_history(period: str = "1D", timeframe: str = "1D") -> dict:
    """period: '1D','1W','1M','3M','6M','1A'. timeframe: '1D','15Min','1H'"""
    qs = f"period={period}&timeframe={timeframe}&extended_hours=false"
    return _alpaca("GET", f"/v2/account/portfolio/history?{qs}")


# ── Telegram helpers ──────────────────────────────────────────────────────────
def _tg_send(msg: str) -> None:
    if not TG_TOKEN or not TG_CHAT_ID:
        print(f"[TG disabled] {msg[:100]}", file=sys.stderr)
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TG_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, context=_SSL, timeout=10):
            pass
    except Exception as exc:
        print(f"TG send failed: {exc}", file=sys.stderr)


# ── Reports ───────────────────────────────────────────────────────────────────
def _pnl_emoji(pnl: float) -> str:
    if pnl >= 1.0:  return "🟢"
    if pnl >= 0.0:  return "🟡"
    return "🔴"


def daily_report() -> str:
    acct = get_account()
    equity     = float(acct.get("equity") or 0)
    cash       = float(acct.get("cash") or 0)
    pnl_day    = float(acct.get("unrealized_pl") or 0)     # today's open pnl
    pnl_day_pct = pnl_day / max(1.0, equity - pnl_day) * 100

    positions = get_positions()

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"📊 <b>Equities {MODE_LABEL} — Daily</b>",
        f"<code>{now_str}</code>",
        "",
        f"💼 Equity:  <b>${equity:,.2f}</b>",
        f"💵 Cash:    ${cash:,.2f}",
        f"{_pnl_emoji(pnl_day)} P&amp;L today: <b>{pnl_day:+.2f} ({pnl_day_pct:+.2f}%)</b>",
        "",
        f"📋 Open positions ({len(positions)}):",
    ]

    if not positions:
        lines.append("   — none —")
    else:
        for pos in sorted(positions, key=lambda p: float(p.get("market_value") or 0), reverse=True):
            sym   = pos.get("symbol", "?")
            qty   = float(pos.get("qty") or 0)
            mv    = float(pos.get("market_value") or 0)
            upnl  = float(pos.get("unrealized_pl") or 0)
            upct  = float(pos.get("unrealized_plpc") or 0) * 100
            ep    = float(pos.get("avg_entry_price") or 0)
            cp    = float(pos.get("current_price") or 0)
            lines.append(
                f"  {_pnl_emoji(upnl)} <b>{sym}</b> {qty:.0f}sh "
                f"@{ep:.2f}→{cp:.2f}  "
                f"P&amp;L: <b>{upnl:+.2f} ({upct:+.1f}%)</b>  ${mv:.0f}"
            )

    return "\n".join(lines)


def monthly_report() -> str:
    acct    = get_account()
    equity  = float(acct.get("equity") or 0)
    cash    = float(acct.get("cash") or 0)

    # Portfolio history last month
    history = get_portfolio_history(period="1M", timeframe="1D")
    equity_arr  = history.get("equity") or []
    timestamps  = history.get("timestamp") or []
    pnl_arr     = history.get("profit_loss") or []
    pnl_pct_arr = history.get("profit_loss_pct") or []

    start_equity = float(equity_arr[0]) if equity_arr else equity
    end_equity   = float(equity_arr[-1]) if equity_arr else equity
    month_pnl    = end_equity - start_equity
    month_pct    = month_pnl / max(1.0, start_equity) * 100

    # Closed orders last month
    from datetime import timedelta
    from_date = (datetime.now(timezone.utc) - timedelta(days=32)).strftime("%Y-%m-%dT00:00:00Z")
    orders = get_closed_orders(after=from_date)
    buy_orders  = [o for o in orders if o.get("side") == "buy"]
    sell_orders = [o for o in orders if o.get("side") == "sell"]
    closed_symbols = {o.get("symbol") for o in orders}

    positions = get_positions()

    now_str = datetime.now(timezone.utc).strftime("%Y-%m")
    lines = [
        f"📅 <b>Equities {MODE_LABEL} — Monthly Report {now_str}</b>",
        "",
        f"💼 Start equity: ${start_equity:,.2f}",
        f"💼 End equity:   <b>${end_equity:,.2f}</b>",
        f"{_pnl_emoji(month_pnl)} Month P&amp;L: <b>{month_pnl:+.2f} ({month_pct:+.2f}%)</b>",
        f"💵 Cash: ${cash:,.2f}",
        "",
        f"📋 Trades this month: {len(orders)} orders  ({len(buy_orders)} buys / {len(sell_orders)} sells)",
        f"📋 Symbols traded: {', '.join(sorted(closed_symbols)) or '—'}",
        "",
        f"🔵 Current positions ({len(positions)}):",
    ]

    if not positions:
        lines.append("   — none —")
    else:
        total_upnl = 0.0
        for pos in sorted(positions, key=lambda p: float(p.get("market_value") or 0), reverse=True):
            sym  = pos.get("symbol", "?")
            qty  = float(pos.get("qty") or 0)
            mv   = float(pos.get("market_value") or 0)
            upnl = float(pos.get("unrealized_pl") or 0)
            upct = float(pos.get("unrealized_plpc") or 0) * 100
            ep   = float(pos.get("avg_entry_price") or 0)
            total_upnl += upnl
            lines.append(f"  {_pnl_emoji(upnl)} <b>{sym}</b> {qty:.0f}sh @{ep:.2f}  Unrealized: <b>{upnl:+.2f} ({upct:+.1f}%)</b>  ${mv:.0f}")
        lines.append(f"\n  Total unrealized: <b>{total_upnl:+.2f}</b>")

    lines += [
        "",
        "💡 <i>Next action: refresh equities research picks for next month</i>",
        f"   Run: python3 scripts/equities_monthly_research_sim.py",
    ]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--monthly", action="store_true", help="Send monthly report instead of daily")
    ap.add_argument("--dry-run", action="store_true", help="Print report without sending to TG")
    args = ap.parse_args()

    if not ALPACA_KEY or not ALPACA_SECRET:
        print("error: ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY required", file=sys.stderr)
        return 1

    try:
        msg = monthly_report() if args.monthly else daily_report()
    except Exception as exc:
        msg = f"❌ Equities {MODE_LABEL} report error: {exc}"
        print(msg, file=sys.stderr)

    if args.dry_run:
        print(msg)
        return 0

    _tg_send(msg)
    print(f"Sent {'monthly' if args.monthly else 'daily'} report to Telegram ({len(msg)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
