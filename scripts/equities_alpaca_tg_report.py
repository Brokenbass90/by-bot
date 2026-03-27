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
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
LOCAL_ENV = Path(os.getenv("ALPACA_REPORT_LOCAL_ENV", str(ROOT / "configs" / "alpaca_paper_local.env")))
if load_dotenv is not None and LOCAL_ENV.exists():
    load_dotenv(LOCAL_ENV, override=False)


# ── Config ────────────────────────────────────────────────────────────────────
def _env(name: str, default: str = "") -> str:
    val = os.getenv(name)
    return str(val).strip() if val is not None else default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except Exception:
        return default


TG_TOKEN   = _env("TG_TOKEN")
TG_CHAT_ID = _env("TG_CHAT_ID")
ALPACA_KEY    = _env("ALPACA_API_KEY_ID")
ALPACA_SECRET = _env("ALPACA_API_SECRET_KEY")
ALPACA_URL    = _env("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
DEEPSEEK_KEY  = _env("DEEPSEEK_API_KEY")
DEEPSEEK_URL  = _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = _env("DEEPSEEK_MODEL", "deepseek-chat")
ALPACA_DEEPSEEK_NOTE_ENABLE = _env_bool("ALPACA_DEEPSEEK_NOTE_ENABLE", True)
ALPACA_DEEPSEEK_NOTE_MAX_CHARS = max(180, _env_int("ALPACA_DEEPSEEK_NOTE_MAX_CHARS", 420))
IS_PAPER = "paper" in ALPACA_URL.lower()
MODE_LABEL = "📄 PAPER" if IS_PAPER else "💰 LIVE"
RUNTIME_REPORT_DIR = Path(os.getenv("ALPACA_REPORT_RUNTIME_DIR", str(ROOT / "runtime" / "alpaca_reports")))

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


def _tg_send_photo(path: Path, caption: str = "") -> bool:
    if not TG_TOKEN or not TG_CHAT_ID or not path.exists():
        return False
    try:
        import requests  # local dependency already used by the main bot
    except Exception as exc:
        print(f"TG photo disabled: requests import failed: {exc}", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    try:
        with path.open("rb") as fh:
            resp = requests.post(
                url,
                data={"chat_id": TG_CHAT_ID, "caption": caption},
                files={"photo": fh},
                timeout=20,
            )
        resp.raise_for_status()
        return True
    except Exception as exc:
        print(f"TG photo send failed: {exc}", file=sys.stderr)
        return False


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _read_csv_first(path: Path) -> dict[str, str] | None:
    if not path.exists():
        return None
    try:
        import csv
        with path.open(newline="", encoding="utf-8") as f:
            return next(csv.DictReader(f), None)
    except Exception:
        return None


def _equities_summary_score(row: dict[str, str]) -> float:
    ret = _safe_float(row.get("compounded_return_pct"), float("-inf"))
    trades = _safe_int(row.get("trades"))
    dd = abs(_safe_float(row.get("max_monthly_dd_pct")))
    months = _safe_int(row.get("months"), -1)
    pos_months = _safe_int(row.get("positive_months"), -1)
    neg_months = max(0, months - pos_months) if months > 0 and pos_months >= 0 else 0
    dd_penalty = max(0.0, dd - 8.0) * 1.5
    neg_penalty = float(neg_months) * 4.0
    return ret - neg_penalty - dd_penalty + trades * 0.02


def _find_best_equities_summary_patterns(glob_patterns: list[str]) -> tuple[Path | None, dict[str, str] | None]:
    best_path: Path | None = None
    best_row: dict[str, str] | None = None
    best_score = float("-inf")
    for pattern in glob_patterns:
        for path in ROOT.glob(pattern):
            row = _read_csv_first(path)
            if not row:
                continue
            score = _equities_summary_score(row)
            if score > best_score:
                best_score = score
                best_path = path
                best_row = row
    return best_path, best_row


def _latest_equities_picks_preview(glob_patterns: list[str], limit: int = 5) -> dict[str, Any] | None:
    latest_csv: Path | None = None
    for pattern in glob_patterns:
        for path in ROOT.glob(pattern):
            if latest_csv is None or path.stat().st_mtime > latest_csv.stat().st_mtime:
                latest_csv = path
    if latest_csv is None:
        return None
    try:
        import csv
        with latest_csv.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        return None
    if not rows:
        return None
    latest_month = max(str(r.get("month") or "").strip() for r in rows)
    picks = [r for r in rows if str(r.get("month") or "").strip() == latest_month]
    picks.sort(key=lambda r: _safe_float(r.get("score")), reverse=True)
    return {
        "path": str(latest_csv),
        "month": latest_month,
        "tickers": [str(r.get("ticker") or "").strip().upper() for r in picks[:limit] if str(r.get("ticker") or "").strip()],
    }


def _deepseek_chat(system: str, user: str) -> str:
    if not DEEPSEEK_KEY:
        return ""
    url = DEEPSEEK_URL.rstrip("/") + "/chat/completions"
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.15,
        "max_tokens": 220,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {DEEPSEEK_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, context=_SSL, timeout=12) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw) if raw else {}
        choices = data.get("choices") or []
        if not choices:
            return ""
        return str(choices[0].get("message", {}).get("content", "")).strip()
    except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError):
        return ""
    except Exception:
        return ""


def _alpaca_ai_note(*, monthly: bool, equity: float, cash: float, positions: list[dict[str, Any]]) -> str:
    if not ALPACA_DEEPSEEK_NOTE_ENABLE or not DEEPSEEK_KEY:
        return ""
    confirmed_path, confirmed = _find_best_equities_summary_patterns([
        "backtest_runs/*equities_monthly_v21_red_month_push*/summary.csv",
    ])
    repair_path, repair = _find_best_equities_summary_patterns([
        "backtest_runs/*equities_monthly_v23_breadth_exit_cluster*/summary.csv",
    ])
    picks = _latest_equities_picks_preview([
        "backtest_runs/*equities_monthly_v23_breadth_exit_cluster*/picks.csv",
        "backtest_runs/*equities_monthly_v21_red_month_push*/picks.csv",
    ])
    pos_lines = []
    for pos in sorted(positions, key=lambda p: float(p.get("market_value") or 0), reverse=True)[:5]:
        sym = str(pos.get("symbol") or "?")
        mv = _safe_float(pos.get("market_value"))
        upnl = _safe_float(pos.get("unrealized_pl"))
        upct = _safe_float(pos.get("unrealized_plpc")) * 100.0
        pos_lines.append(f"{sym}: ${mv:.0f}, pnl={upnl:+.2f} ({upct:+.1f}%)")
    pos_text = "; ".join(pos_lines) if pos_lines else "no open positions"
    confirmed_text = "n/a"
    if confirmed:
        months = _safe_int(confirmed.get("months"))
        pos_months = _safe_int(confirmed.get("positive_months"))
        neg_months = max(0, months - pos_months) if months > 0 else 0
        confirmed_text = (
            f"{confirmed_path.parent.name if confirmed_path else 'confirmed'}: "
            f"ret={_safe_float(confirmed.get('compounded_return_pct')):.2f}% "
            f"trades={_safe_int(confirmed.get('trades'))} "
            f"wr={_safe_float(confirmed.get('winrate_pct')):.1f}% "
            f"red_months={neg_months}"
        )
    repair_text = "n/a"
    if repair:
        repair_text = (
            f"{repair_path.parent.name if repair_path else 'repair'}: "
            f"ret={_safe_float(repair.get('compounded_return_pct')):.2f}% "
            f"trades={_safe_int(repair.get('trades'))} "
            f"wr={_safe_float(repair.get('winrate_pct')):.1f}% "
            f"max_month_dd={_safe_float(repair.get('max_monthly_dd_pct')):.2f}%"
        )
    picks_text = "n/a"
    if picks and picks["tickers"]:
        picks_text = f"{picks['month']}: {', '.join(picks['tickers'])}"

    system = (
        "Ты аккуратный equities risk/advisory analyst для monthly momentum sleeve. "
        "Дай краткую практичную записку на русском максимум в 3 коротких строках. "
        "Не пиши дисклеймеры, не повторяй входные данные целиком."
    )
    user = (
        f"mode={'monthly' if monthly else 'daily'} {MODE_LABEL}\n"
        f"equity={equity:.2f} cash={cash:.2f}\n"
        f"positions={pos_text}\n"
        f"confirmed_frontier={confirmed_text}\n"
        f"latest_repair={repair_text}\n"
        f"latest_picks={picks_text}\n\n"
        "Скажи:\n"
        "1) что по режиму/качеству equities sleeve,\n"
        "2) есть ли warning по концентрации/застаиванию,\n"
        "3) next action: hold / refresh / trim-watch."
    )
    note = _deepseek_chat(system, user)
    if not note:
        return ""
    note = note.strip()
    if len(note) > ALPACA_DEEPSEEK_NOTE_MAX_CHARS:
        note = note[: ALPACA_DEEPSEEK_NOTE_MAX_CHARS - 1].rstrip() + "…"
    return note


def _build_progress_chart(*, monthly: bool) -> Path | None:
    try:
        os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "runtime" / "mplconfig"))
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
        from matplotlib.ticker import FuncFormatter
    except Exception as exc:
        print(f"chart disabled: matplotlib unavailable: {exc}", file=sys.stderr)
        return None

    period = "3M" if monthly else "1M"
    timeframe = "1D"
    history = get_portfolio_history(period=period, timeframe=timeframe)
    ts = history.get("timestamp") or []
    equity = history.get("equity") or []
    if not ts or not equity or len(ts) != len(equity):
        return None

    try:
        xs = [datetime.fromtimestamp(int(t), tz=timezone.utc) for t in ts]
        ys = [float(v) for v in equity]
    except Exception:
        return None
    if len(xs) < 2:
        return None

    RUNTIME_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = RUNTIME_REPORT_DIR / ("alpaca_monthly_progress.png" if monthly else "alpaca_daily_progress.png")
    color = "#1f8f55" if (ys[-1] - ys[0]) >= 0 else "#b23b3b"

    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=150)
    ax.plot(xs, ys, color=color, linewidth=2.0)
    ax.fill_between(xs, ys, min(ys), color=color, alpha=0.12)
    ax.set_title(f"Equities {MODE_LABEL} progress", fontsize=11)
    ax.set_ylabel("Equity, USD")
    ax.grid(alpha=0.22, linestyle="--", linewidth=0.7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}"))
    if monthly:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


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

    ai_note = _alpaca_ai_note(monthly=False, equity=equity, cash=cash, positions=positions)
    if ai_note:
        lines += ["", "🧠 <b>AI note</b>", ai_note]

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
    ai_note = _alpaca_ai_note(monthly=True, equity=end_equity, cash=cash, positions=positions)
    if ai_note:
        lines += ["", "🧠 <b>AI note</b>", ai_note]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--monthly", action="store_true", help="Send monthly report instead of daily")
    ap.add_argument("--dry-run", action="store_true", help="Print report without sending to TG")
    ap.add_argument("--no-chart", action="store_true", help="Do not attach progress chart")
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
        chart_path = None if args.no_chart else _build_progress_chart(monthly=args.monthly)
        if chart_path:
            print(f"chart={chart_path}")
        return 0

    _tg_send(msg)
    chart_path = None if args.no_chart else _build_progress_chart(monthly=args.monthly)
    if chart_path:
        _tg_send_photo(
            chart_path,
            caption=f"Equities {MODE_LABEL} {'monthly' if args.monthly else 'daily'} progress",
        )
    print(f"Sent {'monthly' if args.monthly else 'daily'} report to Telegram ({len(msg)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
