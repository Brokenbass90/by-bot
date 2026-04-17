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


def _latest_summary_path(picks_csv: Path) -> Path | None:
    current_cycle_summary = _env("ALPACA_CURRENT_CYCLE_SUMMARY_CSV", "")
    if current_cycle_summary:
        path = Path(current_cycle_summary)
        if path.exists() and picks_csv.name == "current_cycle_picks.csv":
            return path
    env_path = _env("EQ_LATEST_SUMMARY_CSV", "")
    if env_path:
        path = Path(env_path)
        if path.exists():
            return path
    if picks_csv.name == "current_cycle_picks.csv":
        runtime_candidate = picks_csv.parent / "current_cycle_summary.csv"
        if runtime_candidate.exists():
            return runtime_candidate
    candidate = picks_csv.parent / "summary.csv"
    return candidate if candidate.exists() else None


def _load_summary_row(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    try:
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        return rows[0] if rows else {}
    except Exception:
        return {}


def _deepseek_chat(system: str, user: str) -> str:
    api_key = _env("DEEPSEEK_API_KEY")
    if not api_key:
        return ""
    url = _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/") + "/chat/completions"
    payload = {
        "model": _env("DEEPSEEK_MODEL", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "max_tokens": 220,
    }
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, context=ssl.create_default_context(), timeout=float(_env("DEEPSEEK_TIMEOUT_SEC", "12") or 12)) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw) if raw else {}
        choices = data.get("choices") or []
        if not choices:
            return ""
        return str(choices[0].get("message", {}).get("content", "")).strip()
    except Exception:
        return ""


def _extract_json(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _alpaca_advisory_path(picks_csv: Path) -> Path:
    raw = _env("ALPACA_DEEPSEEK_ADVISORY_PATH", "")
    if raw:
        return Path(raw)
    runtime_dir = (
        _env("ALPACA_AUTOPILOT_RUNTIME_DIR", "")
        or _env("EQ_V35_RUNTIME_DIR", "")
        or _env("EQ_BASELINE_RUNTIME_DIR", "")
    )
    if runtime_dir:
        return Path(runtime_dir) / "latest_advisory.json"
    return picks_csv.parent / "latest_advisory.json"


def _load_offline_snapshot(picks_csv: Path) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    snapshot_raw = _env("ALPACA_OFFLINE_SNAPSHOT_JSON", "")
    candidates: list[Path] = []
    if snapshot_raw:
        candidates.append(Path(snapshot_raw))
    candidates.append(_alpaca_advisory_path(picks_csv))

    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        report = payload.get("report") if isinstance(payload, dict) else None
        report = report if isinstance(report, dict) else payload if isinstance(payload, dict) else {}
        buying_power = _safe_float(report.get("buying_power"), _env_float("ALPACA_OFFLINE_BUYING_POWER", 0.0))
        cash = _safe_float(report.get("cash"), _env_float("ALPACA_OFFLINE_CASH", buying_power))
        positions_raw = report.get("positions_before") or []
        positions: list[dict[str, Any]] = []
        if isinstance(positions_raw, list):
            for pos in positions_raw:
                if not isinstance(pos, dict):
                    continue
                positions.append(
                    {
                        "symbol": str(pos.get("ticker") or pos.get("symbol") or "").strip().upper(),
                        "qty": str(pos.get("qty") or ""),
                        "market_value": str(pos.get("market_value") or ""),
                    }
                )
        account = {
            "buying_power": buying_power,
            "cash": cash,
        }
        return account, positions, str(path)

    buying_power = _env_float("ALPACA_OFFLINE_BUYING_POWER", 0.0)
    cash = _env_float("ALPACA_OFFLINE_CASH", buying_power)
    return {"buying_power": buying_power, "cash": cash}, [], ""


def _alpaca_ai_advisory(
    *,
    report: dict[str, Any],
    summary_row: dict[str, str],
    picks_csv: Path,
) -> dict[str, Any]:
    enabled = _env_bool("ALPACA_DEEPSEEK_ADVISORY_ENABLE", _env_bool("ALPACA_DEEPSEEK_NOTE_ENABLE", False))
    if not enabled:
        return {}
    if not _env("DEEPSEEK_API_KEY"):
        return {}

    max_chars = max(240, _env_int("ALPACA_DEEPSEEK_ADVISORY_MAX_CHARS", _env_int("ALPACA_DEEPSEEK_NOTE_MAX_CHARS", 420)))
    positions = report.get("positions_before") or []
    selected = report.get("selected") or []
    pos_lines = []
    for pos in positions[:5]:
        sym = str(pos.get("ticker") or "?")
        mv = _safe_float(pos.get("market_value"))
        pos_lines.append(f"{sym}:${mv:.0f}")
    sel_lines = []
    for row in selected[:5]:
        sym = str(row.get("ticker") or "?")
        score = _safe_float(row.get("score"))
        mom60 = _safe_float(row.get("momentum60_pct"))
        pb60 = _safe_float(row.get("pullback60_pct"))
        sel_lines.append(f"{sym}(score={score:.3f},mom60={mom60:.1f},pb60={pb60:.1f})")

    cycle_reason = str(report.get("cycle_reason") or "")
    summary_bits = (
        f"ret={_safe_float(summary_row.get('compounded_return_pct')):.2f}% "
        f"trades={_safe_int(summary_row.get('trades'))} "
        f"pf={_safe_float(summary_row.get('profit_factor')):.3f} "
        f"winrate={_safe_float(summary_row.get('winrate_pct')):.1f}% "
        f"active_months={_safe_int(summary_row.get('months'))} "
        f"calendar_months={_safe_int(summary_row.get('calendar_months'))} "
        f"inactive_months={_safe_int(summary_row.get('inactive_months'))} "
        f"neg_months={_safe_int(summary_row.get('negative_months'))} "
        f"max_month_dd={_safe_float(summary_row.get('max_monthly_dd_pct')):.2f}%"
    )

    system = (
        "Ты аккуратный equities monthly sleeve advisor. "
        "Верни только JSON-объект с ключами verdict, next_action, note. "
        "verdict: one of hold_flat, close_stale, keep_positions, buy_selected, refresh_watch. "
        "next_action: one short snake_case phrase. "
        "note: short Russian explanation <= 220 chars, practical, no disclaimers."
    )
    user = (
        f"status={report.get('status')}\n"
        f"cycle_reason={cycle_reason}\n"
        f"month={report.get('month')}\n"
        f"picks_csv={picks_csv}\n"
        f"latest_entry_day={report.get('latest_entry_day')}\n"
        f"pick_age_days={report.get('pick_age_days')}\n"
        f"refresh_age_hours={report.get('refresh_age_hours')}\n"
        f"stale_positions={','.join(report.get('stale_positions') or []) or 'none'}\n"
        f"hold_positions={','.join(report.get('hold_positions') or []) or 'none'}\n"
        f"new_buy_symbols={','.join(report.get('new_buy_symbols') or []) or 'none'}\n"
        f"positions={'; '.join(pos_lines) or 'none'}\n"
        f"selected={'; '.join(sel_lines) or 'none'}\n"
        f"summary={summary_bits}\n"
        "Дай advisory verdict для paper monthly sleeve: что делать сейчас и почему."
    )
    raw = _deepseek_chat(system, user)
    if not raw:
        return {}
    parsed = _extract_json(raw)
    note = str(parsed.get("note") or raw).strip()
    if len(note) > max_chars:
        note = note[: max_chars - 1].rstrip() + "…"
    advisory = {
        "source": "deepseek",
        "verdict": str(parsed.get("verdict") or "refresh_watch").strip() or "refresh_watch",
        "next_action": str(parsed.get("next_action") or "manual_review").strip() or "manual_review",
        "note": note,
        "raw": raw[:1000],
    }
    return advisory


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

    def list_orders(self, *, status: str = "open", limit: int = 100) -> list[dict[str, Any]]:
        return list(self._request("GET", f"/v2/orders?status={status}&direction=desc&limit={int(limit)}"))

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

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/v2/orders/{order_id}")


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


def _monthly_runtime_dirs() -> list[Path]:
    root = Path(__file__).resolve().parent.parent
    candidates: list[Path] = []
    for raw in (
        _env("ALPACA_AUTOPILOT_RUNTIME_DIR", ""),
        _env("EQ_V35_RUNTIME_DIR", ""),
        _env("EQ_BASELINE_RUNTIME_DIR", ""),
    ):
        if not raw:
            continue
        path = Path(raw)
        if path.exists():
            candidates.append(path)
    runtime_root = root / "runtime"
    if runtime_root.exists():
        for path in sorted(runtime_root.glob("equities_monthly*")):
            if path.is_dir():
                candidates.append(path)
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def _current_cycle_picks_path(picks_csv: Path) -> Path | None:
    raw = _env("ALPACA_CURRENT_CYCLE_PICKS_CSV", "")
    if raw:
        path = Path(raw)
        if path.exists():
            return path
    for runtime_dir in _monthly_runtime_dirs():
        path = runtime_dir / "current_cycle_picks.csv"
        if path.exists():
            return path
    candidate = picks_csv.parent / "current_cycle_picks.csv"
    return candidate if candidate.exists() else None


def _load_intraday_managed_symbols() -> set[str]:
    raw = _env("ALPACA_INTRADAY_STATE_PATH", "")
    state_path = Path(raw) if raw else (Path(__file__).resolve().parent.parent / "configs" / "intraday_state.json")
    if not state_path.exists():
        return set()
    try:
        data = json.loads(state_path.read_text())
    except Exception:
        return set()
    if not isinstance(data, dict):
        return set()
    symbols: set[str] = set()
    for sym in data.keys():
        token = str(sym or "").strip().upper()
        if token:
            symbols.add(token)
    return symbols


def _is_held_for_orders_conflict(exc: Exception) -> bool:
    text = str(exc).lower()
    return "held_for_orders" in text or "insufficient qty available for order" in text


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
    offline_dry_run = _env_bool("ALPACA_OFFLINE_DRY_RUN", False) and not send_orders
    capital_override_usd = max(0.0, _env_float("ALPACA_CAPITAL_OVERRIDE_USD", 0.0))
    allow_stale_picks = _env_bool("ALPACA_ALLOW_STALE_PICKS", False)
    max_pick_age_days = max(1, _env_int("ALPACA_MAX_PICK_AGE_DAYS", 45))
    refresh_grace_hours = max(1, _env_int("ALPACA_REFRESH_GRACE_HOURS", 48))
    refresh_utc_raw = _env("ALPACA_REFRESH_UTC") or _env("EQ_LATEST_REFRESH_UTC")
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
    if (not key_id or not secret_key) and not offline_dry_run:
        print("error=missing_alpaca_keys", file=sys.stderr)
        return 4

    snapshot_path = ""
    if offline_dry_run:
        account, positions, snapshot_path = _load_offline_snapshot(picks_csv)
        open_orders: list[dict[str, Any]] = []
        client = None
    else:
        client = AlpacaClient(base_url, key_id, secret_key)
        account = client.get_account()
        positions = client.list_positions()
        open_orders = client.list_orders(status="open", limit=100)
    buying_power = float(account.get("buying_power") or account.get("cash") or 0.0)
    cash = float(account.get("cash") or 0.0)
    effective_capital = min(buying_power, capital_override_usd) if capital_override_usd > 0 else buying_power
    current_positions = {str(p.get("symbol") or "").strip().upper(): p for p in positions if str(p.get("symbol") or "").strip()}
    pending_buy_orders: dict[str, list[dict[str, Any]]] = {}
    for order in open_orders:
        symbol = str(order.get("symbol") or "").strip().upper()
        side = str(order.get("side") or "").strip().lower()
        status = str(order.get("status") or "").strip().lower()
        if not symbol or side != "buy":
            continue
        if status in {"accepted", "new", "pending_new", "partially_filled", "accepted_for_bidding"}:
            pending_buy_orders.setdefault(symbol, []).append(order)
    occupied_symbols = set(current_positions.keys()) | set(pending_buy_orders.keys())
    latest_entry_day, pick_age_days = _pick_age_days(picks)
    current_cycle_csv = _current_cycle_picks_path(picks_csv)
    current_cycle_picks: list[Pick] = []
    current_entry_day = ""
    current_pick_age_days: int | None = None
    if current_cycle_csv is not None:
        current_cycle_picks = _load_picks(current_cycle_csv, None)
        current_entry_day, current_pick_age_days = _pick_age_days(current_cycle_picks)
        current_cycle_is_fresh = bool(
            current_cycle_picks
            and current_pick_age_days is not None
            and current_pick_age_days <= max_pick_age_days
        )
        if current_cycle_is_fresh:
            picks_csv = current_cycle_csv
            picks = current_cycle_picks
            latest_entry_day = current_entry_day
            pick_age_days = current_pick_age_days

    stale_guard_triggered = (
        pick_age_days is not None
        and pick_age_days > max_pick_age_days
        and not allow_stale_picks
    )
    if stale_guard_triggered and refreshed_recently:
        if current_cycle_picks and current_pick_age_days is not None and current_pick_age_days <= max_pick_age_days:
            picks_csv = current_cycle_csv if current_cycle_csv is not None else picks_csv
            picks = current_cycle_picks
            latest_entry_day = current_entry_day
            pick_age_days = current_pick_age_days
            stale_guard_triggered = False
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
    intraday_managed_symbols = _load_intraday_managed_symbols()
    protected_intraday_symbols = sorted(sym for sym in current_positions.keys() if sym in intraday_managed_symbols)
    protected_intraday_orders = sorted(sym for sym in pending_buy_orders.keys() if sym in intraday_managed_symbols)
    stale_symbols = sorted(
        sym for sym in current_positions.keys()
        if sym not in selected_symbols and sym not in intraday_managed_symbols
    )
    stale_order_symbols = sorted(
        sym for sym in pending_buy_orders.keys()
        if sym not in selected_symbols and sym not in intraday_managed_symbols
    )
    hold_symbols = sorted(sym for sym in occupied_symbols if sym in selected_symbols)
    new_buy_symbols = [p.ticker for p in selected if p.ticker not in occupied_symbols]
    per_position_notional = (
        max(min_dollar_order, effective_capital * target_alloc_pct / max(1, len(selected)))
        if selected
        else 0.0
    )
    summary_path = _latest_summary_path(picks_csv)
    summary_row = _load_summary_row(summary_path)
    cycle_reason = (
        "no_current_cycle_after_refresh" if no_current_cycle
        else "selected_current_cycle" if selected
        else "filtered_to_zero_candidates"
    )

    report = {
        "status": (
            "offline_dry_run_no_current_cycle" if (no_current_cycle and offline_dry_run)
            else "offline_dry_run" if offline_dry_run
            else "dry_run_no_current_cycle" if (no_current_cycle and not send_orders)
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
        "offline_snapshot_path": snapshot_path,
        "no_current_cycle": no_current_cycle,
        "cycle_reason": cycle_reason,
        "summary_csv": str(summary_path) if summary_path else "",
        "summary_metrics": {
            "compounded_return_pct": round(_safe_float(summary_row.get("compounded_return_pct")), 4),
            "trades": _safe_int(summary_row.get("trades")),
            "profit_factor": round(_safe_float(summary_row.get("profit_factor")), 4),
            "winrate_pct": round(_safe_float(summary_row.get("winrate_pct")), 4),
            "months": _safe_int(summary_row.get("months")),
            "calendar_months": _safe_int(summary_row.get("calendar_months")),
            "inactive_months": _safe_int(summary_row.get("inactive_months")),
            "negative_months": _safe_int(summary_row.get("negative_months")),
            "max_monthly_dd_pct": round(_safe_float(summary_row.get("max_monthly_dd_pct")), 4),
        },
        "positions_before": [
            {
                "ticker": sym,
                "qty": str(pos.get("qty") or ""),
                "market_value": str(pos.get("market_value") or ""),
            }
            for sym, pos in sorted(current_positions.items())
        ],
        "intraday_managed_symbols": sorted(intraday_managed_symbols),
        "protected_intraday_positions": protected_intraday_symbols,
        "protected_intraday_pending_orders": protected_intraday_orders,
        "stale_positions": stale_symbols,
        "stale_pending_orders": stale_order_symbols,
        "hold_positions": hold_symbols,
        "pending_buy_orders": [
            {
                "ticker": sym,
                "count": len(orders),
                "order_ids": [str(o.get("id") or "") for o in orders if str(o.get("id") or "").strip()],
                "notionals": [str(o.get("notional") or "") for o in orders],
            }
            for sym, orders in sorted(pending_buy_orders.items())
        ],
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
                try:
                    result = client.close_position(symbol)
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "close_position",
                            "order_id": result.get("id"),
                            "status": result.get("status"),
                        }
                    )
                except RuntimeError as exc:
                    if _is_held_for_orders_conflict(exc):
                        report["results"].append(
                            {
                                "ticker": symbol,
                                "action": "close_position",
                                "status": "deferred_held_for_orders",
                                "error": str(exc),
                            }
                        )
                        continue
                    raise
            for symbol in stale_order_symbols:
                for order in pending_buy_orders.get(symbol, []):
                    order_id = str(order.get("id") or "").strip()
                    if not order_id:
                        continue
                    result = client.cancel_order(order_id)
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "cancel_pending_buy",
                            "order_id": order_id,
                            "status": result.get("status", "canceled"),
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
            if pick.ticker in pending_buy_orders:
                report["results"].append(
                    {
                        "ticker": pick.ticker,
                        "action": "hold_pending_buy",
                        "status": "skipped_existing_open_order",
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

    advisory = _alpaca_ai_advisory(report=report, summary_row=summary_row, picks_csv=picks_csv)
    if advisory:
        report["advisory"] = advisory
        advisory_path = _alpaca_advisory_path(picks_csv)
        advisory_path.parent.mkdir(parents=True, exist_ok=True)
        advisory_payload = {
            "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "picks_csv": str(picks_csv),
            "summary_csv": str(summary_path) if summary_path else "",
            "report": report,
        }
        advisory_path.write_text(
            json.dumps(advisory_payload, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
        report["advisory_path"] = str(advisory_path)

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
        lines.append(f"🧭 Cycle: {cycle_reason}")
        for r in report["results"]:
            ticker = r.get("ticker", "?")
            action = r.get("action", "?")
            if action == "market_buy":
                status = r.get("status", "?")
                lines.append(f"  🟢 BUY {ticker} ${round(per_position_notional,0):.0f} — {status}")
            elif action == "close_position":
                lines.append(f"  🔴 CLOSE {ticker}")
            elif action == "cancel_pending_buy":
                lines.append(f"  🟠 CANCEL pending {ticker}")
            elif action == "hold_existing":
                lines.append(f"  🟡 HOLD {ticker}")
            elif action == "hold_pending_buy":
                lines.append(f"  🟡 HOLD pending {ticker}")
        if not report["results"]:
            lines.append("  — No actions taken —")
        if advisory:
            lines += ["", "🧠 <b>AI advisory</b>", str(advisory.get("note") or "").strip()]
        _tg_send(tg_token, tg_chat_id, "\n".join(lines))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
