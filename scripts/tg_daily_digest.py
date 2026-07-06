#!/usr/bin/env python3
"""
tg_daily_digest.py — Russian morning health digest for Bybit + Alpaca branches.

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
  TG_TOKEN, TG_CHAT_ID/TG_CHAT — Telegram credentials (from live bot env)
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
try:
    from proof_of_life import _event_ts_iso, _latest_trade_event, _runtime_sets, _sleeve_label
except Exception:  # pragma: no cover - digest must still run if proof helper changes
    _event_ts_iso = None
    _latest_trade_event = None
    _runtime_sets = None
    _sleeve_label = None


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


def _tail_jsonl(path: Path, limit: int = 80) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
        return out
    except Exception:
        return []


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


def _write_latest_digest(msg: str) -> None:
    out = ROOT / "runtime" / "operator" / "daily_digest_latest.html"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(msg, encoding="utf-8")
    except Exception:
        pass


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
        bot_status = f"🟢 работает {uptime_h:.1f}ч, открытых сделок: {open_trades}"
    elif hb_age is not None:
        bot_status = f"🔴 нет свежего heartbeat, последний был {_age_str(hb_age)}"
    else:
        bot_status = "🔴 нет файла heartbeat"

    lines.append(f"<b>🤖 Крипта Bybit:</b> {bot_status}")
    if hb and int(hb.get("open_trades") or 0) > 0:
        lines.append("  ℹ️ Есть открытая позиция: бот не молчит, сейчас управляет сделкой.")
    else:
        lines.append("  ℹ️ Открытых 0 = бот жив, но сейчас вне позиции.")

    pos = _read_json(ROOT / "runtime" / "live_positions.json")
    positions = pos.get("positions") if isinstance(pos, dict) else None
    if positions:
        for p in list(positions)[:3]:
            try:
                symbol = p.get("symbol", "?")
                side = p.get("side", "?")
                strategy = p.get("strategy", "?")
                entry = float(p.get("entry", 0.0) or 0.0)
                current = float(p.get("current", 0.0) or 0.0)
                sl = float(p.get("sl", p.get("exchange_sl", 0.0)) or 0.0)
                tp = float(p.get("tp", p.get("exchange_tp", 0.0)) or 0.0)
                upnl = float(p.get("upnl_usd", 0.0) or 0.0)
                upnl_pct = float(p.get("upnl_pct", 0.0) or 0.0)
                lines.append(
                    f"  📌 {symbol} {side} {strategy}: entry={entry:g} now={current:g} "
                    f"SL={sl:g} TP={tp:g} uPnL={upnl:+.3f} ({upnl_pct:+.2f}%)"
                )
            except Exception:
                continue

    # ── What is truly live now ───────────────────────────────────────────────
    if hb and _runtime_sets and _sleeve_label:
        _enabled, rmult, live, shadow, _off = _runtime_sets(hb)
        live_line = ", ".join(_sleeve_label(s, rmult.get(s)) for s in live) if live else "нет, всё shadow"
        shadow_line = ", ".join(shadow[:6]) + ("..." if len(shadow) > 6 else "")
        lines.append(f"🎯 Live-риск: {live_line}")
        lines.append(f"👁 Shadow/телеметрия: {shadow_line or '-'}")

    if _latest_trade_event and _event_ts_iso:
        last = _latest_trade_event(_tail_jsonl(ROOT / "runtime" / "live_trade_events.jsonl"))
        if last:
            iso = _event_ts_iso(last)
            age = _age_str((time.time() - datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()) if iso else None)
            lines.append(
                f"🧾 Последняя сделка: {age} — {last.get('event')} "
                f"{last.get('strategy')} {last.get('symbol')}"
            )

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
            cb_line = (f"🚨 Защита счёта: HALT (день={daily_dd:.1f}% / пик={peak_dd:.1f}%, "
                       f"снимется через {remaining/3600:.1f}ч)")
        elif cb_state == "CAUTION":
            cb_line = f"⚠️ Защита счёта: CAUTION (день={daily_dd:.1f}% / пик={peak_dd:.1f}%)"
        else:
            cb_line = "✅ Защита счёта: NORMAL"
    else:
        cb_line = "✅ Защита счёта: NORMAL (HALT не было)"
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
        regime_label = {
            "bear_trend": "медвежий тренд",
            "bear_chop": "медвежий боковик",
            "bull_chop": "бычий боковик",
            "bull_trend": "бычий тренд",
        }.get(r, str(r))
        stale = " ⚠️ устарело" if (regime_age or 0) > 7200 else ""
        lines.append(f"📊 Режим рынка: {regime_emoji} <b>{regime_label}</b> (уверенность={conf:.2f}, риск={risk:.2f}×){stale}")
    else:
        lines.append("📊 Режим рынка: ❓ неизвестен")

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
            alloc_line = f"🔴 Аллокатор: SAFE_MODE ({risk_mult:.2f}×) — {', '.join(reasons[:2])}"
        elif degraded:
            reasons = alloc.get("degraded_reasons", [])
            alloc_line = f"⚠️ Аллокатор: DEGRADED ({risk_mult:.2f}×) — {', '.join(reasons[:2])}"
        else:
            alloc_line = f"✅ Аллокатор: OK ({risk_mult:.2f}×)"
        lines.append(alloc_line)
    else:
        lines.append("⚠️ Аллокатор: файл состояния не найден")

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
        age_warn = f" ⚠️ файл старый: {_age_str(health_age)}" if (health_age or 0) > 604800 else ""
        summary = f"активных по health-файлу:{len(strats)-len(paused)-len(watch)}"
        if watch:
            summary += f" watch:{len(watch)}"
        if paused:
            summary += f" pause/kill:{len(paused)}"
        lines.append(f"{health_emoji} Health стратегий: {overall} ({summary}){age_warn}")
        if (health_age or 0) > 604800:
            lines.append("  ℹ️ Это не список live-рукавов, а старый health-снимок; live-рукава берём из .env/allocator.")
    else:
        lines.append("❓ Health стратегий: файл не найден")

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
            lines.append(f"{pnl_emoji} Сделки сегодня: {len(trades_today)} ({wins}W/{losses}L) = <b>{pnl_sum:+.2f} USDT</b>")
        else:
            lines.append("💤 Сделки сегодня: 0 закрытых")

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
        pending_close = list(adv.get("pending_close_positions") or [])
        monthly_positions = list(adv.get("monthly_managed_positions") or [])
        remote_only = list(adv.get("remote_only_positions") or [])
        state = _read_json(ROOT / "configs" / "intraday_state.json")
        tracked_positions = sorted(str(symbol) for symbol in state.keys()) if isinstance(state, dict) else []
        entries_blocked = adv.get("entries_blocked", False)
        prot = adv.get("protection", {})

        status = "🟢 paper работает" if mode == "LIVE_PAPER" else "⚪ dry-run"
        if entries_blocked:
            block_reason = adv.get("entries_blocked_reason", "unknown")
            status = f"⛔ входы заблокированы ({block_reason})"

        lines.append(f"<b>📈 Alpaca Intraday ({mode}):</b> {status}")

        if today_pnl is not None:
            pnl_e = "📈" if today_pnl >= 0 else "📉"
            lines.append(f"  {pnl_e} Paper journal P&L: <b>${today_pnl:+.2f}</b> (сверяем по fills)")

        if tracked_positions:
            lines.append(f"  📌 Intraday tracked: {', '.join(tracked_positions[:6])}")
        else:
            lines.append("  💤 Intraday tracked позиций нет")
        if pending_close:
            lines.append(f"  ⏳ Awaiting close fill: {', '.join(str(p) for p in pending_close[:6])}")
        if monthly_positions:
            lines.append(f"  📅 Monthly-owned (не intraday): {', '.join(str(p) for p in monthly_positions[:6])}")
        if remote_only:
            lines.append(f"  ⚠️ Неатрибутированные broker positions: {', '.join(str(p) for p in remote_only[:6])}")

        # Protection layers
        spy_ok = prot.get("spy_gate_pass", "?")
        eq_ok = prot.get("equity_curve_pass", "?")
        dd_ok = prot.get("daily_loss_ok", "?")
        lines.append(f"  🛡 Защиты: SPY={spy_ok} | EquityCurve={eq_ok} | DailyDD={dd_ok}")
    else:
        stale = f" (stale {_age_str(age)})" if age is not None else ""
        lines.append(f"<b>📈 Alpaca Intraday:</b> ❓ нет свежего advisory{stale}")

    return "\n".join(lines)


# ─── Alpaca Monthly Section ──────────────────────────────────────────────────

def _alpaca_monthly_section() -> str:
    lines = []
    base_url = _env("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    is_live_account = "paper-api" not in base_url
    account_label = "LIVE" if is_live_account else "paper"

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
        lines.append(f"<b>📅 Alpaca Monthly {account_label} ({cycle_month}):</b>")
        lines.append(f"  💰 Equity: <b>${equity:,.0f}</b> | cash: ${cash:,.0f} | BP: ${buying_power:,.0f}")
    else:
        lines.append(f"<b>📅 Alpaca Monthly {account_label} ({cycle_month}):</b>")
        lines.append("  💰 Equity: API недоступен")

    if current_tickers:
        lines.append(f"  📋 Выбранные акции: {', '.join(current_tickers)}")
    else:
        lines.append("  📋 Выбранных акций не найдено")

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
            lines.append("  💤 Открытых monthly-позиций пока нет")
    else:
        lines.append("  💤 Позиций нет или API недоступен")

    stale_warn = ""
    if refresh_age is not None and refresh_age > 1209600:  # 14 days
        stale_warn = f" ⚠️ picks старые: {_age_str(refresh_age)} — обновить 1-го числа"
    elif refresh_age is not None:
        stale_warn = f" (обновлены {_age_str(refresh_age)})"
    lines.append(f"  🔄 Пики{stale_warn}")
    if is_live_account:
        lines.append("  ℹ️ Это LIVE-счёт; все заявки должны идти только через capped v38 и broker-side stop protection.")
    else:
        lines.append("  ℹ️ Это paper-счёт; перед реальными деньгами ждём сверку fills, broker-side protection и итог текущего цикла.")

    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Morning Telegram health digest")
    ap.add_argument("--bybit-only", action="store_true")
    ap.add_argument("--alpaca-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="Print, don't send to TG")
    args = ap.parse_args()

    # Load credentials. Live env has priority; paper env only fills gaps.
    _load_env_file(ROOT / "configs" / "alpaca_live_v38.env")
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
    chat_id = _env("TG_CHAT_ID") or _env("TG_CHAT")
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    sections: list[str] = []
    sections.append(f"☀️ <b>Ежедневный отчёт — {now_utc}</b>")
    sections.append("")

    if not args.alpaca_only:
        sections.append(_bybit_section())

    if not args.bybit_only:
        sections.append("")
        sections.append(_alpaca_intraday_section())
        sections.append("")
        sections.append(_alpaca_monthly_section())

    msg = "\n".join(sections)
    _write_latest_digest(msg)
    success = _tg_send(token, chat_id, msg, dry_run=args.dry_run)
    if not args.dry_run:
        print(f"[tg_digest] {'sent' if success else 'failed'} — {now_utc}")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
