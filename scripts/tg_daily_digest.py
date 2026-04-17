#!/usr/bin/env python3
"""
tg_daily_digest.py — Morning health digest for both Bybit bot + Alpaca branches.

Sends a single Telegram message at 08:00 UTC with:
  • Bybit bot: CB state, regime, allocator status, open trades, recent closes
  • Alpaca intraday: today's P&L, open positions, protection state
  • Alpaca monthly: current picks, hold duration, unrealized P&L

Usage:
  python3 scripts/tg_daily_digest.py               # full digest
  python3 scripts/tg_daily_digest.py --bybit-only   # only Bybit section
  python3 scripts/tg_daily_digest.py --alpaca-only  # only Alpaca section
  python3 scripts/tg_daily_digest.py --dry-run      # print, don't send

Cron (08:00 UTC every day):
  0 8 * * * /bin/bash -lc 'cd /root/by-bot && source .venv/bin/activate && python3 scripts/tg_daily_digest.py >> logs/tg_daily_digest.log 2>&1'

ENV:
  TG_TOKEN, TG_CHAT_ID — Telegram credentials (from alpaca_paper_local.env or live env)
  ALPACA_API_KEY_ID, ALPACA_API_SECRET_KEY, ALPACA_BASE_URL — for Alpaca positions
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib import request, error

ROOT = Path(__file__).resolve().parent.parent


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _env(name: str, default: str = "") -> str:
    val = os.getenv(name)
    return str(val).strip() if val is not None else default


def _env_bool(name: str, default: bool = False) -> bool:
    return _env(name, "1" if default else "0").lower() in {"1", "true", "yes"}


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def _read_json(path: Path) -> dict:
    try:
        with path.open() as f:
            return json.load(f)
    except Exception:
        return {}


def _age_str(age_sec: Optional[float]) -> str:
    if age_sec is None:
        return "?"
    if age_sec < 120:
        return f"{int(age_sec)}s ago"
    if age_sec < 7200:
        return f"{int(age_sec/60)}m ago"
    if age_sec < 172800:
        return f"{age_sec/3600:.1f}h ago"
    return f"{age_sec/86400:.1f}d ago"


def _file_age(path: Path) -> Optional[float]:
    try:
        return time.time() - path.stat().st_mtime
    except Exception:
        return None


def _tg_send(token: str, chat_id: str, msg: str, dry_run: bool = False) -> bool:
    if dry_run:
        print("─── TG MESSAGE ───")
        print(msg)
        print("──────────────────")
        return True
    if not token or not chat_id:
        print("[tg_digest] TG_TOKEN or TG_CHAT_ID not set — skipping send")
        return False
    payload = json.dumps({
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()
    req = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    ctx = ssl.create_default_context()
    try:
        with request.urlopen(req, context=ctx, timeout=15):
            return True
    except Exception as exc:
        print(f"[tg_digest] TG send failed: {exc}")
        return False


# ─── Alpaca API ───────────────────────────────────────────────────────────────

def _alpaca_get(path: str) -> Any:
    key_id = _env("ALPACA_API_KEY_ID")
    secret = _env("ALPACA_API_SECRET_KEY")
    base_url = _env("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    if not key_id or not secret:
        return None
    url = f"{base_url}{path}"
    req = request.Request(url, headers={
        "APCA-API-KEY-ID": key_id,
        "APCA-API-SECRET-KEY": secret,
    })
    ctx = ssl.create_default_context()
    try:
        with request.urlopen(req, context=ctx, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return None


# ─── Bybit Bot Section ────────────────────────────────────────────────────────

def _bybit_section() -> str:
    lines = []

    # ── Heartbeat ────────────────────────────────────────────────────────────
    hb_path = ROOT / "runtime" / "bot_heartbeat.json"
    hb = _read_json(hb_path)
    hb_age = _file_age(hb_path)

    if hb and hb_age is not None and hb_age < 120:
        uptime_h = hb.get("uptime_s", 0) / 3600
        open_trades = hb.get("open_trades", 0)
        bot_status = f"🟢 online ({uptime_h:.1f}h up, {open_trades} open)"
    elif hb_age is not None:
        bot_status = f"🔴 offline (last seen {_age_str(hb_age)})"
    else:
        bot_status = "🔴 offline (no heartbeat file)"

    lines.append(f"<b>🤖 Bybit Bot:</b> {bot_status}")

    # ── Circuit Breaker ───────────────────────────────────────────────────────
    cb_path = ROOT / "runtime" / "circuit_breaker.json"
    cb = _read_json(cb_path)
    if cb:
        cb_state = cb.get("state", "NORMAL")
        equity = cb.get("equity", 0)
        daily_dd = cb.get("daily_dd_pct", 0)
        peak_dd = cb.get("peak_dd_pct", 0)
        if cb_state == "HALT":
            halt_until = cb.get("halt_until_epoch", 0)
            remaining = max(0, halt_until - time.time())
            cb_line = (f"🚨 CB: HALT (daily={daily_dd:.1f}% / peak={peak_dd:.1f}%, "
                       f"clears in {remaining/3600:.1f}h)")
        elif cb_state == "CAUTION":
            cb_line = f"⚠️ CB: CAUTION (daily={daily_dd:.1f}% / peak={peak_dd:.1f}%)"
        else:
            cb_line = "✅ CB: NORMAL"
    else:
        cb_line = "✅ CB: NORMAL (no HALT event recorded)"
    lines.append(cb_line)

    # ── Regime ────────────────────────────────────────────────────────────────
    regime_path = ROOT / "runtime" / "regime" / "orchestrator_state.json"
    regime = _read_json(regime_path)
    regime_age = _file_age(regime_path)
    if regime:
        r = regime.get("regime", "?")
        conf = float(regime.get("confidence", 0))
        risk = float(regime.get("global_risk_mult", 1.0))
        regime_emoji = {"bear_trend": "🐻", "bear_chop": "🌫", "bull_chop": "🌤", "bull_trend": "🐂"}.get(r, "❓")
        stale = " ⚠️stale" if (regime_age or 0) > 7200 else ""
        lines.append(f"📊 Regime: {regime_emoji} <b>{r}</b> (conf={conf:.2f}, risk={risk:.2f}×){stale}")
    else:
        lines.append("📊 Regime: ❓ unknown")

    # ── Allocator ─────────────────────────────────────────────────────────────
    alloc_state_path = ROOT / "runtime" / "control_plane" / "portfolio_allocator_state.json"
    alloc = _read_json(alloc_state_path)
    if alloc:
        status = alloc.get("status", "?")
        degraded = alloc.get("degraded", False)
        safe_mode = alloc.get("safe_mode", False)
        risk_mult = alloc.get("allocator_global_risk_mult", 1.0)
        if safe_mode:
            reasons = alloc.get("safe_mode_reasons", [])
            alloc_line = f"🔴 Allocator: SAFE_MODE ({risk_mult:.2f}×) — {', '.join(reasons[:2])}"
        elif degraded:
            reasons = alloc.get("degraded_reasons", [])
            alloc_line = f"⚠️ Allocator: DEGRADED ({risk_mult:.2f}×) — {', '.join(reasons[:2])}"
        else:
            alloc_line = f"✅ Allocator: OK ({risk_mult:.2f}×)"
        lines.append(alloc_line)
    else:
        lines.append("⚠️ Allocator: state file not found")

    # ── Strategy health quick summary ─────────────────────────────────────────
    health_path = ROOT / "configs" / "strategy_health.json"
    health = _read_json(health_path)
    health_age = _file_age(health_path)
    if health:
        overall = health.get("overall_health", "?")
        strats = health.get("strategies", {})
        paused = [k for k, v in strats.items() if isinstance(v, dict) and v.get("status") in ("PAUSE", "KILL")]
        watch = [k for k, v in strats.items() if isinstance(v, dict) and v.get("status") == "WATCH"]
        health_emoji = "✅" if overall == "OK" else ("⚠️" if overall == "WATCH" else "🔴")
        age_warn = f" [{_age_str(health_age)} old]" if (health_age or 0) > 604800 else ""
        summary = f"active:{len(strats)-len(paused)-len(watch)}"
        if watch:
            summary += f" watch:{len(watch)}"
        if paused:
            summary += f" paused:{len(paused)}"
        lines.append(f"{health_emoji} Strategy health: {overall} ({summary}){age_warn}")
    else:
        lines.append("❓ Strategy health: file not found")

    # ── Recent closed trades (from logs) ──────────────────────────────────────
    log_dir = ROOT / "logs"
    trade_log = None
    for candidate in ["trades.jsonl", "closed_trades.jsonl", "bot_trades.jsonl"]:
        p = log_dir / candidate
        if p.exists():
            trade_log = p
            break

    if trade_log:
        trades_today = []
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            with trade_log.open() as f:
                for line in f:
                    try:
                        t = json.loads(line)
                        ts = t.get("close_ts") or t.get("closed_at") or t.get("ts", "")
                        if today_str in str(ts):
                            trades_today.append(t)
                    except Exception:
                        pass
        except Exception:
            pass

        if trades_today:
            pnl_sum = sum(float(t.get("pnl", 0)) for t in trades_today)
            wins = sum(1 for t in trades_today if float(t.get("pnl", 0)) > 0)
            losses = sum(1 for t in trades_today if float(t.get("pnl", 0)) < 0)
            pnl_emoji = "📈" if pnl_sum > 0 else "📉"
            lines.append(f"{pnl_emoji} Today's trades: {len(trades_today)} ({wins}W/{losses}L) = <b>{pnl_sum:+.2f} USDT</b>")
        else:
            lines.append("💤 Today's trades: 0 (no closes yet)")

    return "\n".join(lines)


# ─── Alpaca Intraday Section ─────────────────────────────────────────────────

def _alpaca_intraday_section() -> str:
    lines = []
    advisory_path = ROOT / "runtime" / "equities_intraday_dynamic_v1" / "latest_advisory.json"
    adv = _read_json(advisory_path)
    age = _file_age(advisory_path)

    if adv and age is not None and age < 86400:
        mode = adv.get("mode", "?")
        today_pnl = adv.get("today_pnl_usd", None)
        open_pos = adv.get("open_positions", [])
        entries_blocked = adv.get("entries_blocked", False)
        prot = adv.get("protection", {})

        status = "🟢 running" if mode == "LIVE_PAPER" else "⚪ dry-run"
        if entries_blocked:
            block_reason = adv.get("entries_blocked_reason", "unknown")
            status = f"⛔ blocked ({block_reason})"

        lines.append(f"<b>📈 Alpaca Intraday ({mode}):</b> {status}")

        if today_pnl is not None:
            pnl_e = "📈" if today_pnl >= 0 else "📉"
            lines.append(f"  {pnl_e} Today P&L: <b>${today_pnl:+.2f}</b>")

        if open_pos:
            lines.append(f"  📌 Open: {', '.join(str(p) for p in open_pos[:6])}")
        else:
            lines.append("  💤 Open: none")

        # Protection layers
        spy_ok = prot.get("spy_gate_pass", "?")
        eq_ok = prot.get("equity_curve_pass", "?")
        dd_ok = prot.get("daily_loss_ok", "?")
        lines.append(f"  🛡 SPY={spy_ok} | EqCurve={eq_ok} | DailyDD={dd_ok}")
    else:
        stale = f" (stale {_age_str(age)})" if age is not None else ""
        lines.append(f"<b>📈 Alpaca Intraday:</b> ❓ no advisory{stale}")

    return "\n".join(lines)


# ─── Alpaca Monthly Section ──────────────────────────────────────────────────

def _alpaca_monthly_section() -> str:
    lines = []

    # Try to get live positions from Alpaca API
    positions = _alpaca_get("/v2/positions")
    account = _alpaca_get("/v2/account")

    # Load current cycle picks
    cycle_path = ROOT / "runtime" / "equities_monthly_v36" / "current_cycle_picks.csv"
    refresh_path = ROOT / "runtime" / "equities_monthly_v36" / "latest_refresh.env"
    refresh_age = _file_age(refresh_path)

    # Parse current picks
    current_tickers: list[str] = []
    cycle_month = "?"
    if cycle_path.exists():
        try:
            with cycle_path.open() as f:
                lines_ = f.readlines()
            if len(lines_) > 1:
                for row in lines_[1:]:
                    parts = row.strip().split(",")
                    if len(parts) >= 2:
                        if not cycle_month or cycle_month == "?":
                            cycle_month = parts[0]
                        current_tickers.append(parts[1])
        except Exception:
            pass

    if account:
        equity = float(account.get("equity", 0))
        cash = float(account.get("cash", 0))
        buying_power = float(account.get("buying_power", 0))
        lines.append(f"<b>📅 Alpaca Monthly ({cycle_month}):</b>")
        lines.append(f"  💰 Equity: <b>${equity:,.0f}</b> | Cash: ${cash:,.0f}")
    else:
        lines.append(f"<b>📅 Alpaca Monthly ({cycle_month}):</b>")
        lines.append("  💰 Equity: API unavailable")

    if current_tickers:
        lines.append(f"  📋 Picks: {', '.join(current_tickers)}")
    else:
        lines.append("  📋 Picks: none found")

    # Show open positions with P&L
    if positions and isinstance(positions, list):
        # Filter to monthly tickers only (exclude intraday leftovers)
        monthly_pos = [p for p in positions if p.get("symbol") in current_tickers] if current_tickers else positions
        if monthly_pos:
            for pos in monthly_pos[:4]:
                sym = pos.get("symbol", "?")
                qty = pos.get("qty", "?")
                unrealized = float(pos.get("unrealized_pl", 0))
                unrealized_pct = float(pos.get("unrealized_plpc", 0)) * 100
                e = "📈" if unrealized >= 0 else "📉"
                lines.append(f"  {e} {sym}: {unrealized_pct:+.1f}% ({unrealized:+.2f} USD)")
        else:
            lines.append("  💤 No open positions yet")
    else:
        lines.append("  💤 No positions / API unavailable")

    stale_warn = ""
    if refresh_age is not None and refresh_age > 1209600:  # 14 days
        stale_warn = f" ⚠️ picks {_age_str(refresh_age)} old — refresh on 1st!"
    elif refresh_age is not None:
        stale_warn = f" (refreshed {_age_str(refresh_age)})"
    lines.append(f"  🔄 Picks{stale_warn}")

    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Morning Telegram health digest")
    ap.add_argument("--bybit-only", action="store_true")
    ap.add_argument("--alpaca-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="Print, don't send to TG")
    args = ap.parse_args()

    # Load credentials
    _load_env_file(ROOT / "configs" / "alpaca_paper_local.env")
    # Also try live bot env for TG creds if not already set
    live_env_candidates = [
        ROOT / "configs" / "core3_live_canary_20260411_sloped_momentum.env",
        ROOT / "configs" / "live_bot.env",
    ]
    for cand in live_env_candidates:
        if cand.exists():
            _load_env_file(cand)
            break

    token = _env("TG_TOKEN")
    chat_id = _env("TG_CHAT_ID")
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    sections: list[str] = []
    sections.append(f"☀️ <b>Daily Digest — {now_utc}</b>")
    sections.append("")

    if not args.alpaca_only:
        sections.append(_bybit_section())

    if not args.bybit_only:
        sections.append("")
        sections.append(_alpaca_intraday_section())
        sections.append("")
        sections.append(_alpaca_monthly_section())

    msg = "\n".join(sections)
    success = _tg_send(token, chat_id, msg, dry_run=args.dry_run)
    if not args.dry_run:
        print(f"[tg_digest] {'sent' if success else 'failed'} — {now_utc}")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
