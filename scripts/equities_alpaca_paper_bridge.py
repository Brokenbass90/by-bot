#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import ssl
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

# Optional earnings filter (graceful fallback if import fails)
try:
    _scripts_dir = Path(__file__).resolve().parent
    if str(_scripts_dir) not in sys.path:
        sys.path.insert(0, str(_scripts_dir))
    from equities_earnings_filter import filter_safe_picks as _filter_earnings
    _EARNINGS_FILTER_OK = True
except ImportError:
    _EARNINGS_FILTER_OK = False
    def _filter_earnings(symbols, **kw):  # type: ignore[misc]
        return {s: (True, "filter_unavailable") for s in symbols}


def _tg_send(token: str, chat_id: str, msg: str) -> None:
    """Send a message to Telegram. Silent on failure."""
    if not token or not chat_id:
        return
    import ssl as _ssl
    payload = json.dumps({
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "HTML",
    }).encode()
    req_tg = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    ctx = _ssl.create_default_context()
    try:
        with request.urlopen(req_tg, context=ctx, timeout=10):
            pass
    except Exception:
        pass


@dataclass
class Pick:
    month: str
    ticker: str
    entry_day: str
    score: float
    atr20_pct: float
    momentum20_pct: float
    momentum60_pct: float
    pullback60_pct: float
    universe_score: float | None


def _env(name: str, default: str = "") -> str:
    val = os.getenv(name)
    return str(val).strip() if val is not None else default


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
    raw = _env(name, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on"}


class AlpacaClient:
    def __init__(self, base_url: str, key_id: str, secret_key: str):
        self.base_url = base_url.rstrip("/")
        self.key_id = key_id
        self.secret_key = secret_key
        self._ssl_ctx = ssl.create_default_context()

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.key_id,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=body, headers=self._headers(), method=method)
        try:
            with request.urlopen(req, context=self._ssl_ctx, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc

    def get_account(self) -> dict[str, Any]:
        return self._request("GET", "/v2/account")

    def list_positions(self) -> list[dict[str, Any]]:
        return list(self._request("GET", "/v2/positions"))

    def submit_market_buy(self, symbol: str, notional: float) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "notional": f"{notional:.2f}",
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
        }
        return self._request("POST", "/v2/orders", payload)

    def close_position(self, symbol: str) -> dict[str, Any]:
        return self._request("DELETE", f"/v2/positions/{symbol}")


def _load_picks(csv_path: Path, month: str | None) -> list[Pick]:
    out: list[Pick] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        rows = list(rd)
    if not rows:
        return out
    if not month:
        month = max((r.get("month") or "").strip() for r in rows)
    for row in rows:
        if (row.get("month") or "").strip() != month:
            continue
        universe_score = (row.get("universe_score") or "").strip()
        out.append(
            Pick(
                month=month,
                ticker=(row.get("ticker") or "").strip().upper(),
                entry_day=(row.get("entry_day") or "").strip(),
                score=float(row.get("score") or 0.0),
                atr20_pct=float(row.get("atr20_pct") or 0.0),
                momentum20_pct=float(row.get("momentum20_pct") or 0.0),
                momentum60_pct=float(row.get("momentum60_pct") or 0.0),
                pullback60_pct=float(row.get("pullback60_pct") or 0.0),
                universe_score=float(universe_score) if universe_score else None,
            )
        )
    out.sort(key=lambda x: x.score, reverse=True)
    return out


def _default_picks_csv() -> Path | None:
    root = Path(__file__).resolve().parent.parent
    runs = sorted(root.glob("backtest_runs/equities_monthly_research_*/picks.csv"))
    return runs[-1] if runs else None


def _parse_date_ymd(text: str) -> date | None:
    s = str(text or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _pick_age_days(picks: list[Pick]) -> tuple[str, int | None]:
    latest_entry = ""
    latest_dt: date | None = None
    for p in picks:
        d = _parse_date_ymd(p.entry_day)
        if d is None:
            continue
        if latest_dt is None or d > latest_dt:
            latest_dt = d
            latest_entry = p.entry_day
    if latest_dt is None:
        return "", None
    now_utc = datetime.now(timezone.utc).date()
    return latest_entry, max(0, (now_utc - latest_dt).days)


def _parse_iso_utc(text: str) -> datetime | None:
    s = str(text or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Dry-run-first Alpaca paper bridge for monthly equities picks")
    ap.add_argument("--picks-csv", default=_env("ALPACA_PICKS_CSV", ""))
    ap.add_argument("--month", default=_env("ALPACA_PICKS_MONTH", ""))
    args = ap.parse_args()

    picks_csv = Path(args.picks_csv) if args.picks_csv else _default_picks_csv()
    if picks_csv is None or not picks_csv.exists():
        print("error=no_picks_csv", file=sys.stderr)
        return 2

    picks = _load_picks(picks_csv, args.month or None)
    if not picks:
        print("error=no_picks_for_month", file=sys.stderr)
        return 3

    max_positions = max(1, _env_int("ALPACA_MAX_POSITIONS", 2))
    target_alloc_pct = max(0.01, min(1.0, _env_float("ALPACA_TARGET_ALLOC_PCT", 0.45)))
    min_dollar_order = max(1.0, _env_float("ALPACA_MIN_DOLLAR_ORDER", 50.0))
    send_orders = _env_bool("ALPACA_SEND_ORDERS", False)
    close_stale_positions = _env_bool("ALPACA_CLOSE_STALE_POSITIONS", False)
    capital_override_usd = max(0.0, _env_float("ALPACA_CAPITAL_OVERRIDE_USD", 0.0))
    allow_stale_picks = _env_bool("ALPACA_ALLOW_STALE_PICKS", False)
    max_pick_age_days = max(1, _env_int("ALPACA_MAX_PICK_AGE_DAYS", 45))
    refresh_grace_hours = max(1, _env_int("ALPACA_REFRESH_GRACE_HOURS", 48))
    refresh_utc_raw = _env("ALPACA_REFRESH_UTC")
    refresh_utc = _parse_iso_utc(refresh_utc_raw)
    refresh_age_hours: float | None = None
    refreshed_recently = False
    if refresh_utc is not None:
        refresh_age_hours = max(0.0, (datetime.now(timezone.utc) - refresh_utc).total_seconds() / 3600.0)
        refreshed_recently = refresh_age_hours <= float(refresh_grace_hours)

    tg_token   = _env("TG_TOKEN")
    tg_chat_id = _env("TG_CHAT_ID")
    earnings_days = max(1, _env_int("EARNINGS_DAYS_GUARD", 5))
    use_earnings_filter = _env_bool("ALPACA_EARNINGS_FILTER", _EARNINGS_FILTER_OK)

    key_id = _env("ALPACA_API_KEY_ID")
    secret_key = _env("ALPACA_API_SECRET_KEY")
    base_url = _env("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    if not key_id or not secret_key:
        print("error=missing_alpaca_keys", file=sys.stderr)
        return 4

    client = AlpacaClient(base_url, key_id, secret_key)
    account = client.get_account()
    buying_power = float(account.get("buying_power") or account.get("cash") or 0.0)
    cash = float(account.get("cash") or 0.0)
    effective_capital = min(buying_power, capital_override_usd) if capital_override_usd > 0 else buying_power
    positions = client.list_positions()
    current_positions = {str(p.get("symbol") or "").strip().upper(): p for p in positions if str(p.get("symbol") or "").strip()}
    latest_entry_day, pick_age_days = _pick_age_days(picks)
    stale_guard_triggered = (
        pick_age_days is not None
        and pick_age_days > max_pick_age_days
        and not allow_stale_picks
    )
    if stale_guard_triggered and not refreshed_recently:
        print(
            json.dumps(
                {
                    "error": "stale_picks_guard",
                    "picks_csv": str(picks_csv),
                    "month": picks[0].month,
                    "latest_entry_day": latest_entry_day,
                    "pick_age_days": pick_age_days,
                    "max_pick_age_days": max_pick_age_days,
                    "refresh_utc": refresh_utc_raw,
                    "refresh_age_hours": None if refresh_age_hours is None else round(refresh_age_hours, 2),
                    "hint": "refresh equities research or set ALPACA_ALLOW_STALE_PICKS=1 explicitly",
                },
                ensure_ascii=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 5
    # ── Earnings filter ──────────────────────────────────────────────────────
    earnings_blocked: dict[str, str] = {}
    if use_earnings_filter:
        candidate_tickers = [p.ticker for p in picks[:max_positions * 2]]
        ek = _filter_earnings(candidate_tickers, days_guard=earnings_days)
        for sym, (safe, reason) in ek.items():
            if not safe:
                earnings_blocked[sym] = reason
    # If a fresh refresh still leaves only stale picks, interpret it as
    # "no current cycle candidates" instead of buying old names.
    no_current_cycle = bool(stale_guard_triggered and refreshed_recently)

    # Select only picks not blocked by earnings, up to max_positions
    selected = [] if no_current_cycle else [p for p in picks if p.ticker not in earnings_blocked][:max_positions]
    selected_symbols = {p.ticker for p in selected}
    stale_symbols = sorted(sym for sym in current_positions.keys() if sym not in selected_symbols)
    hold_symbols = sorted(sym for sym in current_positions.keys() if sym in selected_symbols)
    new_buy_symbols = [p.ticker for p in selected if p.ticker not in current_positions]
    per_position_notional = (
        max(min_dollar_order, effective_capital * target_alloc_pct / max(1, len(selected)))
        if selected
        else 0.0
    )

    report = {
        "status": (
            "dry_run_no_current_cycle" if (no_current_cycle and not send_orders)
            else "send_orders_no_current_cycle" if no_current_cycle
            else "dry_run" if not send_orders
            else "send_orders"
        ),
        "month": selected[0].month if selected else (picks[0].month if picks else ""),
        "earnings_blocked": earnings_blocked,
        "picks_csv": str(picks_csv),
        "buying_power": round(buying_power, 2),
        "cash": round(cash, 2),
        "effective_capital": round(effective_capital, 2),
        "per_position_notional": round(per_position_notional, 2),
        "close_stale_positions": bool(close_stale_positions),
        "latest_entry_day": latest_entry_day,
        "pick_age_days": pick_age_days,
        "max_pick_age_days": max_pick_age_days,
        "refresh_utc": refresh_utc_raw,
        "refresh_age_hours": None if refresh_age_hours is None else round(refresh_age_hours, 2),
        "no_current_cycle": no_current_cycle,
        "positions_before": [
            {
                "ticker": sym,
                "qty": str(pos.get("qty") or ""),
                "market_value": str(pos.get("market_value") or ""),
            }
            for sym, pos in sorted(current_positions.items())
        ],
        "stale_positions": stale_symbols,
        "hold_positions": hold_symbols,
        "new_buy_symbols": new_buy_symbols,
        "selected": [
            {
                "ticker": p.ticker,
                "score": round(p.score, 6),
                "atr20_pct": round(p.atr20_pct, 3),
                "momentum60_pct": round(p.momentum60_pct, 3),
                "pullback60_pct": round(p.pullback60_pct, 3),
                "universe_score": None if p.universe_score is None else round(p.universe_score, 6),
            }
            for p in selected
        ],
        "results": [],
    }
    if send_orders:
        if close_stale_positions:
            for symbol in stale_symbols:
                result = client.close_position(symbol)
                report["results"].append(
                    {
                        "ticker": symbol,
                        "action": "close_position",
                        "order_id": result.get("id"),
                        "status": result.get("status"),
                    }
                )
        for pick in selected:
            if pick.ticker in current_positions:
                report["results"].append(
                    {
                        "ticker": pick.ticker,
                        "action": "hold_existing",
                        "status": "skipped_existing_position",
                    }
                )
                continue
            result = client.submit_market_buy(pick.ticker, per_position_notional)
            report["results"].append(
                {
                    "ticker": pick.ticker,
                    "action": "market_buy",
                    "order_id": result.get("id"),
                    "status": result.get("status"),
                    "notional": per_position_notional,
                }
            )
    print(json.dumps(report, ensure_ascii=True, separators=(",", ":")))

    # ── Telegram notification ─────────────────────────────────────────────────
    if tg_token and tg_chat_id:
        mode = "📄 PAPER" if "paper" in base_url.lower() else "💰 LIVE"
        month_label = report.get("month", "?")
        lines = [f"📊 <b>Equities {mode} — {month_label}</b>"]
        if not send_orders:
            lines.append("⚠️ DRY RUN — no real orders placed")
        if no_current_cycle:
            lines.append("🟡 No current monthly picks after fresh refresh; staying flat")
        lines += [
            f"💼 Capital: ${round(effective_capital,2):,}",
            f"📋 Per position: ${round(per_position_notional,2):,}",
        ]
        if earnings_blocked:
            lines.append(f"🚫 Earnings blocked: {', '.join(sorted(earnings_blocked))}")
        for r in report["results"]:
            ticker = r.get("ticker", "?")
            action = r.get("action", "?")
            if action == "market_buy":
                status = r.get("status", "?")
                lines.append(f"  🟢 BUY {ticker} ${round(per_position_notional,0):.0f} — {status}")
            elif action == "close_position":
                lines.append(f"  🔴 CLOSE {ticker}")
            elif action == "hold_existing":
                lines.append(f"  🟡 HOLD {ticker}")
        if not report["results"]:
            lines.append("  — No actions taken —")
        _tg_send(tg_token, tg_chat_id, "\n".join(lines))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
