#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
portfolio_status.py — простой отчёт по портфелю для оператора.

Что показывает:
  - Баланс по каждому Bybit аккаунту (main + sub-account'ы)
  - Открытые позиции
  - PnL: сегодня / неделя / месяц / год
  - Прогноз EOY на текущем темпе
  - Аллокацию: какой % от плана $500/$1000/$500 заполнен

Запуск:
  python3 scripts/portfolio_status.py           # вывод в консоль
  python3 scripts/portfolio_status.py --tg      # отправить в Telegram
  python3 scripts/portfolio_status.py --json    # машинный формат

Что требуется:
  - BYBIT_ACCOUNTS_JSON в .env (main + sub-arb-overlay)
  - runtime/live_trade_events.jsonl или runtime/trades.csv (для PnL)
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
TRADES_CSV = ROOT / "runtime" / "trades.csv"
LIVE_EVENTS = ROOT / "runtime" / "live_trade_events.jsonl"

# План распределения капитала (от пользователя)
PLAN = {
    "main":         {"target_usd": 500.0,  "purpose": "directional crypto trading"},
    "arb_overlay":  {"target_usd": 1000.0, "purpose": "funding harvest + basis arb"},
    "alpaca":       {"target_usd": 500.0,  "purpose": "equities (paper -> real)"},
    "reserve":      {"target_usd": 200.0,  "purpose": "Bybit Earn flexible USDT"},
}


def _sign_bybit_v5(secret: str, query_string: str, timestamp: str, recv_window: str, api_key: str) -> str:
    """Signature for Bybit V5 API."""
    raw = timestamp + api_key + recv_window + query_string
    return hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()


def _bybit_get(base: str, path: str, key: str, secret: str, params: Optional[Dict] = None) -> Dict:
    params = params or {}
    qs = urllib.parse.urlencode(sorted(params.items()))
    ts = str(int(time.time() * 1000))
    recv = "10000"
    sign = _sign_bybit_v5(secret, qs, ts, recv, key)
    url = f"{base.rstrip('/')}{path}" + (f"?{qs}" if qs else "")
    req = urllib.request.Request(
        url,
        headers={
            "X-BAPI-API-KEY": key,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": recv,
            "X-BAPI-SIGN": sign,
            "User-Agent": "by-bot/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        return {"error": str(exc), "retCode": -1}


def _get_account_balance(account: Dict) -> Dict[str, Any]:
    """Get equity + breakdown for one Bybit account."""
    name = account.get("name", "?")
    key = account.get("key", "")
    secret = account.get("secret", "")
    base = account.get("base", "https://api.bybit.com")
    if not key or not secret:
        return {"name": name, "error": "missing credentials"}

    # Unified Trading Account wallet balance
    data = _bybit_get(base, "/v5/account/wallet-balance", key, secret, {"accountType": "UNIFIED"})
    if data.get("retCode") != 0:
        return {"name": name, "error": f"API err: {data.get('retMsg', data.get('error', 'unknown'))}"}

    try:
        wallet = data["result"]["list"][0]
        total_equity = float(wallet.get("totalEquity") or 0)
        total_available = float(wallet.get("totalAvailableBalance") or 0)
        unrealized = float(wallet.get("totalPerpUPL") or 0)
        coins = []
        for c in wallet.get("coin", []):
            wallet_balance = float(c.get("walletBalance") or 0)
            if wallet_balance > 0.01:
                coins.append({
                    "coin": c.get("coin"),
                    "balance": round(wallet_balance, 4),
                    "usd_value": round(float(c.get("usdValue") or 0), 2),
                })
        return {
            "name": name,
            "total_equity_usd": round(total_equity, 2),
            "available_usd": round(total_available, 2),
            "unrealized_pnl_usd": round(unrealized, 2),
            "coins": coins,
        }
    except (IndexError, KeyError, ValueError) as exc:
        return {"name": name, "error": f"parse: {exc}"}


def _get_positions(account: Dict) -> List[Dict[str, Any]]:
    """Get open positions for one account."""
    key = account.get("key", "")
    secret = account.get("secret", "")
    base = account.get("base", "https://api.bybit.com")
    if not key or not secret:
        return []
    data = _bybit_get(base, "/v5/position/list", key, secret, {"category": "linear", "settleCoin": "USDT"})
    if data.get("retCode") != 0:
        return []
    out = []
    for p in (data.get("result") or {}).get("list", []):
        try:
            size = float(p.get("size") or 0)
            if size <= 0:
                continue
            out.append({
                "symbol":      p.get("symbol"),
                "side":        p.get("side"),
                "size":        size,
                "entry_price": float(p.get("avgPrice") or 0),
                "mark_price":  float(p.get("markPrice") or 0),
                "unrealized_pnl": round(float(p.get("unrealisedPnl") or 0), 4),
                "leverage":    p.get("leverage"),
            })
        except (TypeError, ValueError):
            continue
    return out


def _load_trades_for_window(days: int) -> List[Dict[str, Any]]:
    """Load closed trades from runtime files."""
    cutoff = time.time() - days * 86400
    trades = []

    # Try CSV first
    if TRADES_CSV.exists():
        import csv
        with TRADES_CSV.open(newline="", encoding="utf-8", errors="ignore") as f:
            for row in csv.DictReader(f):
                ts_raw = row.get("exit_ts") or row.get("close_time") or row.get("open_time")
                try:
                    ts_val = float(ts_raw)
                    if ts_val > 1e12:
                        ts_val /= 1000.0
                except (TypeError, ValueError):
                    continue
                if ts_val < cutoff:
                    continue
                try:
                    pnl = float(row.get("pnl") or 0)
                except (TypeError, ValueError):
                    pnl = 0.0
                trades.append({
                    "strategy": row.get("strategy", ""),
                    "symbol": row.get("symbol", ""),
                    "exit_ts": ts_val,
                    "pnl": pnl,
                })

    # Then live events
    if not trades and LIVE_EVENTS.exists():
        buckets = {}
        for raw in LIVE_EVENTS.read_text(errors="ignore").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                evt = json.loads(raw)
            except json.JSONDecodeError:
                continue
            oid = str(evt.get("entry_order_id") or evt.get("symbol", "") + str(evt.get("ts", "")))
            rec = buckets.setdefault(oid, {})
            rec.update(evt)
        for rec in buckets.values():
            if rec.get("event") != "close":
                continue
            try:
                ts_val = int(rec.get("ts") or 0)
                if ts_val < cutoff:
                    continue
                trades.append({
                    "strategy": rec.get("strategy", ""),
                    "symbol": rec.get("symbol", ""),
                    "exit_ts": ts_val,
                    "pnl": float(rec.get("pnl") or 0),
                })
            except (TypeError, ValueError):
                continue

    return trades


def _summarize_pnl(trades: List[Dict[str, Any]]) -> Dict[str, float]:
    """Sum PnL across multiple windows."""
    now = time.time()
    windows = {"today": 86400, "week": 7 * 86400, "month": 30 * 86400, "year": 365 * 86400}
    summary = {k: 0.0 for k in windows}
    counts = {k: 0 for k in windows}
    for t in trades:
        age = now - float(t.get("exit_ts", 0))
        for win, sec in windows.items():
            if age <= sec:
                summary[win] += t.get("pnl", 0.0)
                counts[win] += 1
    return {
        "today_pnl": round(summary["today"], 2),
        "today_n": counts["today"],
        "week_pnl": round(summary["week"], 2),
        "week_n": counts["week"],
        "month_pnl": round(summary["month"], 2),
        "month_n": counts["month"],
        "year_pnl": round(summary["year"], 2),
        "year_n": counts["year"],
    }


def _load_accounts() -> List[Dict]:
    """Read BYBIT_ACCOUNTS_JSON from environment or .env file."""
    raw = os.getenv("BYBIT_ACCOUNTS_JSON", "")
    if not raw:
        env_path = ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("BYBIT_ACCOUNTS_JSON="):
                    raw = line.split("=", 1)[1].strip()
                    break
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def _tg_send(text: str) -> None:
    token = os.getenv("TG_TOKEN", "").strip()
    chat = (os.getenv("TG_CHAT_ID") or os.getenv("TG_CHAT") or "").strip()
    if not token or not chat:
        return
    try:
        payload = json.dumps({"chat_id": chat, "text": text[:3500], "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload, headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        print(f"[portfolio] TG send failed: {exc}", file=sys.stderr)


def _format_report(report: Dict[str, Any], html: bool = False) -> str:
    bold = lambda s: f"<b>{s}</b>" if html else s
    code = lambda s: f"<code>{s}</code>" if html else s

    lines = [bold(f"📊 Portfolio Status — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"), ""]

    # Per-account
    total_equity = 0.0
    for acc in report["accounts"]:
        if acc.get("error"):
            lines.append(f"  ❌ {acc['name']}: {acc['error']}")
            continue
        eq = acc.get("total_equity_usd", 0)
        total_equity += eq
        target = PLAN.get(acc["name"], {}).get("target_usd", 0)
        pct = (eq / target * 100) if target else 0
        bar = "█" * int(pct // 10) + "░" * (10 - int(pct // 10))
        lines.append(f"  💰 {bold(acc['name'])}: ${eq:.2f} / ${target:.0f}  {bar} {pct:.0f}%")
        upnl = acc.get("unrealized_pnl_usd", 0)
        if abs(upnl) > 0.01:
            sign = "+" if upnl > 0 else ""
            lines.append(f"     unrealized: {sign}${upnl:.2f}")

    lines.append("")
    lines.append(bold(f"Total equity: ${total_equity:.2f}"))

    # Open positions
    if report["positions"]:
        lines.append("")
        lines.append(bold(f"📈 Open positions ({len(report['positions'])}):"))
        for p in report["positions"][:8]:
            sign = "+" if p["unrealized_pnl"] >= 0 else ""
            lines.append(
                f"  {p['symbol']} {p['side']} sz={p['size']} @ {p['entry_price']:.4f}  "
                f"→ {p['mark_price']:.4f}  PnL: {sign}${p['unrealized_pnl']:.2f}"
            )

    # PnL summary
    pnl = report["pnl"]
    lines.append("")
    lines.append(bold("💹 Realized PnL:"))
    lines.append(f"  Today:  ${pnl['today_pnl']:+.2f}   ({pnl['today_n']} trades)")
    lines.append(f"  Week:   ${pnl['week_pnl']:+.2f}   ({pnl['week_n']} trades)")
    lines.append(f"  Month:  ${pnl['month_pnl']:+.2f}   ({pnl['month_n']} trades)")
    lines.append(f"  Year:   ${pnl['year_pnl']:+.2f}   ({pnl['year_n']} trades)")

    # EOY projection
    days_into_year = (datetime.now(timezone.utc) - datetime(datetime.now().year, 1, 1, tzinfo=timezone.utc)).days
    if days_into_year > 0 and pnl["year_pnl"] != 0:
        daily_avg = pnl["year_pnl"] / days_into_year
        eoy_projection = daily_avg * 365
        monthly_avg = daily_avg * 30
        lines.append(f"  EOY proj: ${eoy_projection:+.0f} ({monthly_avg:+.2f}/мес avg)")

    # Plan progress
    lines.append("")
    lines.append(bold("📋 План $2200 (твой стартовый):"))
    main_eq = next((a.get("total_equity_usd", 0) for a in report["accounts"] if a.get("name") == "main"), 0)
    arb_eq = next((a.get("total_equity_usd", 0) for a in report["accounts"] if a.get("name") == "arb_overlay"), 0)
    funded_pct = ((main_eq + arb_eq) / 1500 * 100) if (main_eq + arb_eq) > 0 else 0
    lines.append(f"  Bybit (main+arb): ${main_eq + arb_eq:.0f} / $1500 — {funded_pct:.0f}% от плана")
    lines.append(f"  + Alpaca $500 (отдельно), резерв $200 в Bybit Earn (отдельно)")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Portfolio status across Bybit accounts.")
    ap.add_argument("--tg", action="store_true", help="Send to Telegram.")
    ap.add_argument("--json", action="store_true", help="Machine-readable JSON.")
    ap.add_argument("--days-pnl", type=int, default=365, help="Window for PnL summary.")
    args = ap.parse_args()

    accounts = _load_accounts()
    if not accounts:
        print("[portfolio] ERROR: BYBIT_ACCOUNTS_JSON not set. Check .env.", file=sys.stderr)
        return 1

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "accounts": [],
        "positions": [],
        "pnl": {},
    }

    for acc in accounts:
        balance = _get_account_balance(acc)
        report["accounts"].append(balance)
        if not balance.get("error"):
            positions = _get_positions(acc)
            for p in positions:
                p["account"] = acc.get("name")
            report["positions"].extend(positions)

    trades = _load_trades_for_window(args.days_pnl)
    report["pnl"] = _summarize_pnl(trades)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(_format_report(report, html=False))

    if args.tg:
        _tg_send(_format_report(report, html=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
