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
import csv
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


def _configured_env_bool(name: str, fallback_path: Path, default: bool = False) -> bool:
    """Read effective report env, then the manager's tracked base profile."""
    if name in os.environ:
        return _env_bool(name, default)
    if fallback_path.exists():
        try:
            for raw in fallback_path.read_text(encoding="utf-8").splitlines():
                row = raw.strip()
                if not row or row.startswith("#") or "=" not in row:
                    continue
                key, value = row.split("=", 1)
                if key.strip() == name:
                    return value.strip().strip('"').strip("'").lower() in {
                        "1", "true", "yes", "on"
                    }
        except Exception:
            pass
    return default


def _read_json(path: Path) -> dict:
    try:
        with path.open() as f:
            return json.load(f)
    except Exception:
        return {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt_qty(value: Any) -> str:
    """Preserve fractional Alpaca quantities without noisy trailing zeroes."""
    qty = _safe_float(value)
    rendered = f"{qty:.8f}".rstrip("0").rstrip(".")
    return rendered or "0"


def _flatten_orders(orders: Any) -> list[dict[str, Any]]:
    """Return unique parent/leg orders from Alpaca's nested order response."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(raw: Any) -> None:
        if not isinstance(raw, dict):
            return
        key = str(raw.get("id") or raw.get("client_order_id") or id(raw))
        if key not in seen:
            seen.add(key)
            out.append(raw)
        for leg in raw.get("legs") or []:
            visit(leg)

    for raw in orders if isinstance(orders, list) else []:
        visit(raw)
    return out


def _stop_coverage(positions: Any, orders: Any) -> dict[str, Any]:
    """Compare actual broker positions with still-open protective stop quantities."""
    active = {"new", "accepted", "pending_new", "partially_filled", "held", "replaced"}
    stop_types = {"stop", "stop_limit", "trailing_stop"}
    stops = []
    for order in _flatten_orders(orders):
        if str(order.get("status") or "").lower() not in active:
            continue
        if str(order.get("type") or "").lower() not in stop_types:
            continue
        stops.append(order)

    covered: list[str] = []
    missing: list[str] = []
    rows = positions if isinstance(positions, list) else []
    for pos in rows:
        if not isinstance(pos, dict):
            continue
        symbol = str(pos.get("symbol") or "?").upper()
        qty = abs(_safe_float(pos.get("qty")))
        pos_side = str(pos.get("side") or "long").lower()
        protective_side = "buy" if pos_side == "short" else "sell"
        protected_qty = 0.0
        for order in stops:
            if str(order.get("symbol") or "").upper() != symbol:
                continue
            if str(order.get("side") or "").lower() != protective_side:
                continue
            protected_qty += max(
                0.0,
                _safe_float(order.get("qty")) - _safe_float(order.get("filled_qty")),
            )
        # Alpaca fractional rounding can differ by a few millionths.
        if qty > 0 and protected_qty + max(1e-6, qty * 1e-5) >= qty:
            covered.append(symbol)
        else:
            missing.append(symbol)
    return {
        "covered": covered,
        "missing": missing,
        "covered_count": len(covered),
        "position_count": len(rows),
    }


def _intraday_v1_ledger_status() -> str:
    """Fail closed until the damaged v1 history is rebuilt from broker fills."""
    proof = _read_json(
        ROOT / "runtime" / "equities_intraday_dynamic_v1" / "ledger_reconciliation.json"
    )
    status = str(proof.get("status") or "").upper()
    source = str(proof.get("source") or "").lower()
    if status in {"VERIFIED", "RECONCILED"} and source == "broker_fills":
        return "VERIFIED"
    return "DATA_INVALID"


def _read_monthly_picks(path: Path) -> tuple[str, list[str]]:
    if not path.exists():
        return "?", []
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    except Exception:
        return "?", []
    if not rows:
        return "?", []
    month = str(rows[0].get("month") or "?").strip() or "?"
    tickers = []
    for row in rows:
        symbol = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
        if symbol and symbol not in tickers:
            tickers.append(symbol)
    return month, tickers


def _account_metrics(account: Any, positions: Any, history: Any) -> dict[str, Any]:
    account = account if isinstance(account, dict) else {}
    rows = positions if isinstance(positions, list) else []
    equity = _safe_float(account.get("equity") or account.get("portfolio_value"))
    last_equity = _safe_float(account.get("last_equity"), equity)
    base = _safe_float(
        _env("ALPACA_REPORT_BASE_CAPITAL_USD")
        or _env("ALPACA_LIVE_MAX_CAPITAL_USD")
        or _env("ALPACA_CAPITAL_OVERRIDE_USD")
    )
    open_unrealized = sum(_safe_float(pos.get("unrealized_pl")) for pos in rows if isinstance(pos, dict))
    day_pnl = equity - last_equity if last_equity else None
    intraday_values = [
        _safe_float(pos.get("unrealized_intraday_pl"))
        for pos in rows
        if isinstance(pos, dict) and pos.get("unrealized_intraday_pl") is not None
    ]
    intraday_unrealized = sum(intraday_values) if len(intraday_values) == len(rows) else None
    realized_day_est = (
        day_pnl - intraday_unrealized
        if day_pnl is not None and intraday_unrealized is not None
        else None
    )
    history_equity = history.get("equity") if isinstance(history, dict) else []
    peaks = [equity]
    if base > 0:
        peaks.append(base)
    if isinstance(history_equity, list):
        peaks.extend(_safe_float(value) for value in history_equity)
    peak = max(peaks) if peaks else equity
    dd_pct = ((equity / peak) - 1.0) * 100.0 if peak > 0 else None
    vs_base_pct = ((equity / base) - 1.0) * 100.0 if base > 0 else None
    return {
        "equity": equity,
        "last_equity": last_equity,
        "base": base,
        "day_pnl": day_pnl,
        "open_unrealized": open_unrealized,
        "intraday_unrealized": intraday_unrealized,
        "realized_day_est": realized_day_est,
        "peak": peak,
        "dd_pct": dd_pct,
        "vs_base_pct": vs_base_pct,
    }


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


def _write_delivery_status(key: str, *, success: bool, dry_run: bool) -> None:
    if not key:
        return
    safe_key = "".join(ch for ch in key if ch.isalnum() or ch in {"-", "_"})
    if not safe_key:
        return
    status_key = f"{safe_key}_dry_run" if dry_run else safe_key
    out = ROOT / "runtime" / "alpaca_reports" / f"{status_key}_status.json"
    payload = {
        "report_key": safe_key,
        "attempted_at_utc": datetime.now(timezone.utc).isoformat(),
        "success": bool(success),
        "dry_run": bool(dry_run),
        "broker_mode": "PAPER" if "paper-api" in _env("ALPACA_BASE_URL").lower() else "LIVE",
    }
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(out.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(out)
    except Exception:
        pass


def _write_alpaca_account_state(*, account: Any, positions: Any, orders: Any, base_url: str) -> None:
    # A transient API failure must not replace the last known broker snapshot
    # with an empty payload that looks current.
    if not isinstance(account, dict) or not isinstance(positions, list):
        return

    def _pos_row(pos: dict) -> dict:
        return {
            "symbol": pos.get("symbol"),
            "side": pos.get("side"),
            "qty": pos.get("qty"),
            "market_value": pos.get("market_value"),
            "avg_entry_price": pos.get("avg_entry_price"),
            "unrealized_pl": pos.get("unrealized_pl"),
            "unrealized_plpc": pos.get("unrealized_plpc"),
        }

    def _order_row(order: dict) -> dict:
        return {
            "id": order.get("id"),
            "client_order_id": order.get("client_order_id"),
            "symbol": order.get("symbol"),
            "side": order.get("side"),
            "type": order.get("type"),
            "order_class": order.get("order_class"),
            "qty": order.get("qty"),
            "filled_qty": order.get("filled_qty"),
            "status": order.get("status"),
            "limit_price": order.get("limit_price"),
            "stop_price": order.get("stop_price"),
            "submitted_at": order.get("submitted_at"),
        }

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "account": {
            "status": account.get("status") if isinstance(account, dict) else None,
            "equity": account.get("equity") if isinstance(account, dict) else None,
            "last_equity": account.get("last_equity") if isinstance(account, dict) else None,
            "cash": account.get("cash") if isinstance(account, dict) else None,
            "buying_power": account.get("buying_power") if isinstance(account, dict) else None,
            "portfolio_value": account.get("portfolio_value") if isinstance(account, dict) else None,
            "trading_blocked": account.get("trading_blocked") if isinstance(account, dict) else None,
            "account_blocked": account.get("account_blocked") if isinstance(account, dict) else None,
        },
        "positions": [_pos_row(p) for p in positions if isinstance(p, dict)] if isinstance(positions, list) else [],
        "open_orders": [_order_row(o) for o in orders if isinstance(o, dict)] if isinstance(orders, list) else [],
    }
    out = ROOT / "runtime" / "alpaca_live_v38" / "account_state.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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

        ledger_status = _intraday_v1_ledger_status()
        status = "🟢 PAPER execution" if mode == "LIVE_PAPER" else "⚪ PAPER dry-run/shadow"
        if entries_blocked:
            block_reason = adv.get("entries_blocked_reason", "unknown")
            status = f"⛔ входы заблокированы ({block_reason})"

        lines.append(f"<b>📈 Alpaca Intraday ({mode}):</b> {status}")

        if ledger_status == "DATA_INVALID":
            lines.append(
                "  🚫 P&amp;L v1: <b>DATA_INVALID</b> — старый ledger повреждён повторным booking; "
                "цифры не используются до rebuild из broker fills"
            )
        elif today_pnl is not None:
            pnl_e = "📈" if today_pnl >= 0 else "📉"
            lines.append(f"  {pnl_e} Verified fill-ledger P&amp;L: <b>${today_pnl:+.2f}</b>")

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
    account_label = "LIVE BROKER" if is_live_account else "PAPER BROKER"
    send_orders = _env_bool("ALPACA_SEND_ORDERS", False)
    allow_new_entries = _env_bool("ALPACA_ALLOW_NEW_ENTRIES", True)
    close_stale = _env_bool("ALPACA_CLOSE_STALE_POSITIONS", False)
    safe_hold = (not send_orders) or (not allow_new_entries)

    # Try to get live positions from Alpaca API
    positions = _alpaca_get("/v2/positions")
    account = _alpaca_get("/v2/account")
    orders = _alpaca_get("/v2/orders?status=open&limit=100&nested=true")
    history = _alpaca_get("/v2/account/portfolio/history?period=3M&timeframe=1D&extended_hours=false")
    _write_alpaca_account_state(account=account, positions=positions, orders=orders, base_url=base_url)

    # Load current cycle picks
    cycle_path = ROOT / "runtime" / "equities_monthly_v36" / "current_cycle_picks.csv"
    refresh_path = ROOT / "runtime" / "equities_monthly_v36" / "latest_refresh.env"
    refresh_age = _file_age(refresh_path)

    cycle_month, current_tickers = _read_monthly_picks(cycle_path)
    metrics = _account_metrics(account, positions, history)
    stop_cov = _stop_coverage(positions, orders)
    broker_symbols = sorted(
        str(pos.get("symbol") or "?").upper()
        for pos in positions if isinstance(pos, dict)
    ) if isinstance(positions, list) else []

    if account:
        equity = metrics["equity"]
        cash = _safe_float(account.get("cash"))
        buying_power = _safe_float(account.get("buying_power"))
        lines.append(f"<b>📅 Alpaca Monthly {account_label} ({cycle_month}):</b>")
        report_submit = "ON" if send_orders else "OFF"
        entries = "ON" if allow_new_entries else "OFF"
        hold_label = " | <b>SAFE-HOLD</b>" if safe_hold else ""
        lines.append(
            f"  🔐 Report order-submit={report_submit} | new entries={entries} | "
            f"stale/rotation closes={'ON' if close_stale else 'OFF'}{hold_label}"
        )
        if safe_hold:
            trail_configured = _configured_env_bool(
                "MONTHLY_TRAIL_ENABLE",
                ROOT / "configs" / "alpaca_v38_hybrid_top4_candidate.env",
                False,
            )
            software_trail = "ON" if trail_configured else "OFF"
            lines.append(
                "  🛠 Protection truth: broker-stop coverage is audited below; "
                f"software trail config={software_trail} (requires the scheduled manager poll)"
            )
        lines.append(f"  💰 Equity: <b>${equity:,.2f}</b> | cash: ${cash:,.2f} | BP: ${buying_power:,.2f}")
        if metrics["base"] > 0:
            lines.append(
                f"  📐 Base ${metrics['base']:,.2f}: {metrics['vs_base_pct']:+.2f}% | "
                f"DD от max(base/HWM ${metrics['peak']:,.2f}): <b>{metrics['dd_pct']:+.2f}%</b>"
            )
        if metrics["day_pnl"] is not None:
            pnl_line = f"  🧾 Account day P&amp;L: <b>${metrics['day_pnl']:+.2f}</b>"
            if metrics["intraday_unrealized"] is not None:
                pnl_line += (
                    f" | intraday uPnL ${metrics['intraday_unrealized']:+.2f}"
                    f" | realized est. ${metrics['realized_day_est']:+.2f}"
                )
            lines.append(pnl_line)
        lines.append(f"  📊 Open unrealized: <b>${metrics['open_unrealized']:+.2f}</b>")
    else:
        lines.append(f"<b>📅 Alpaca Monthly {account_label} ({cycle_month}):</b>")
        lines.append("  💰 Equity: API недоступен")

    if current_tickers:
        lines.append(f"  🧪 Current research picks (не holdings): {', '.join(current_tickers)}")
    else:
        lines.append("  🧪 Current research picks: не найдены")
    if isinstance(positions, list):
        lines.append(f"  🏦 Actual broker holdings: {', '.join(broker_symbols) if broker_symbols else 'нет'}")
        picks_not_held = [s for s in current_tickers if s not in broker_symbols]
        holdings_not_picks = [s for s in broker_symbols if s not in current_tickers]
        if picks_not_held:
            lines.append(f"  ℹ️ Picks, которых нет у брокера: {', '.join(picks_not_held)}")
        if holdings_not_picks:
            lines.append(f"  ⚠️ Holdings вне current picks: {', '.join(holdings_not_picks)}")
    else:
        lines.append("  🏦 Actual broker holdings: API недоступен")

    # Show open positions with P&L
    if isinstance(positions, list):
        if positions:
            for pos in positions:
                sym = pos.get("symbol", "?")
                qty = _fmt_qty(pos.get("qty"))
                unrealized = _safe_float(pos.get("unrealized_pl"))
                unrealized_pct = _safe_float(pos.get("unrealized_plpc")) * 100
                e = "📈" if unrealized >= 0 else "📉"
                lines.append(
                    f"  {e} {sym}: qty={qty} | {unrealized_pct:+.2f}% ({unrealized:+.2f} USD)"
                )
        else:
            lines.append("  💤 Открытых broker-позиций пока нет")
    else:
        lines.append("  💤 Позиций нет или API недоступен")

    if isinstance(positions, list) and isinstance(orders, list):
        lines.append(
            f"  🛡 Broker stop coverage: <b>{stop_cov['covered_count']}/{stop_cov['position_count']}</b>"
        )
        if stop_cov["missing"]:
            lines.append(f"  🚨 Без полного stop coverage: {', '.join(stop_cov['missing'])}")
    else:
        lines.append("  ⚠️ Broker stop coverage: API недоступен")

    lines.append(
        "  🚫 Intraday v1 realized history: <b>DATA_INVALID</b> до broker-fill reconciliation"
        if _intraday_v1_ledger_status() == "DATA_INVALID"
        else "  ✅ Intraday v1 realized history: broker-fill reconciled"
    )

    stale_warn = ""
    if refresh_age is not None and refresh_age > 1209600:  # 14 days
        stale_warn = f" ⚠️ picks старые: {_age_str(refresh_age)} — обновить 1-го числа"
    elif refresh_age is not None:
        stale_warn = f" (обновлены {_age_str(refresh_age)})"
    lines.append(f"  🔄 Пики{stale_warn}")
    if is_live_account:
        lines.append("  ℹ️ Это LIVE broker account; отчёт не называет safe-hold активной торговлей.")
    else:
        lines.append("  ℹ️ Это paper-счёт; перед реальными деньгами ждём сверку fills, broker-side protection и итог текущего цикла.")

    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Morning Telegram health digest")
    ap.add_argument("--bybit-only", action="store_true")
    ap.add_argument("--alpaca-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="Print, don't send to TG")
    ap.add_argument(
        "--status-key",
        default="",
        help="Write delivery status under runtime/alpaca_reports (used by report watchdog)",
    )
    args = ap.parse_args()

    # Load credentials. Live env has priority; paper env only fills gaps.
    _load_env_file(ROOT / "configs" / "alpaca_live_v38.env")
    _load_env_file(ROOT / "configs" / "alpaca_live_v38_safe_hold.env")
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
    _write_delivery_status(args.status_key, success=success, dry_run=args.dry_run)
    if not args.dry_run:
        print(f"[tg_digest] {'sent' if success else 'failed'} — {now_utc}")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
