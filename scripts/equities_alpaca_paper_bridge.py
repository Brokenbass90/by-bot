#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
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


def _tg_dedupe_state_path() -> Path:
    raw = _env("ALPACA_TG_DEDUPE_STATE", "")
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parent.parent / "runtime" / "alpaca_tg_dedupe.json"


def _is_actionable_equities_report(report: dict[str, Any]) -> bool:
    passive_actions = {"hold_existing", "hold_pending_buy"}
    results = report.get("results") or []
    if not results:
        return False
    return any(str(r.get("action") or "") not in passive_actions for r in results if isinstance(r, dict))


def _tg_send_equities_report(token: str, chat_id: str, msg: str, report: dict[str, Any]) -> None:
    """Suppress repeated HOLD-only reports while preserving BUY/CLOSE/STOP alerts."""
    if _is_actionable_equities_report(report) or not _env_bool("ALPACA_TG_DEDUPE_HOLD_ONLY", True):
        _tg_send(token, chat_id, msg)
        return

    window_sec = max(0, _env_int("ALPACA_TG_DEDUPE_HOLD_SEC", 21600))
    if window_sec <= 0:
        _tg_send(token, chat_id, msg)
        return

    digest = hashlib.sha256(msg.encode("utf-8", errors="replace")).hexdigest()
    path = _tg_dedupe_state_path()
    now = time.time()
    try:
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        state = {}
    previous = state.get("equities_hold_only") if isinstance(state, dict) else {}
    if (
        isinstance(previous, dict)
        and previous.get("digest") == digest
        and now - float(previous.get("ts") or 0.0) < window_sec
    ):
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    state["equities_hold_only"] = {"digest": digest, "ts": now}
    path.write_text(json.dumps(state, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    _tg_send(token, chat_id, msg)


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
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    weight: float | None = None


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


def _live_order_guard_errors(
    *,
    base_url: str,
    send_orders: bool,
    capital_override_usd: float,
) -> list[str]:
    """Fail closed before the paper bridge is allowed to touch a live account."""
    if not send_orders or "paper" in str(base_url).lower():
        return []

    errors: list[str] = []
    if _env("ALPACA_LIVE_ACCOUNT_ROLE").lower() != "monthly_v38":
        errors.append("ALPACA_LIVE_ACCOUNT_ROLE must be monthly_v38")
    if _env("ALPACA_LIVE_CONFIRM") != "MONTHLY_V38_LIVE":
        errors.append("ALPACA_LIVE_CONFIRM must be MONTHLY_V38_LIVE")

    max_capital = max(1.0, _env_float("ALPACA_LIVE_MAX_CAPITAL_USD", 500.0))
    if capital_override_usd <= 0:
        errors.append("ALPACA_CAPITAL_OVERRIDE_USD must be set for live orders")
    elif capital_override_usd > max_capital:
        errors.append(
            f"ALPACA_CAPITAL_OVERRIDE_USD={capital_override_usd:.2f} exceeds "
            f"ALPACA_LIVE_MAX_CAPITAL_USD={max_capital:.2f}"
        )
    return errors


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


def _optional_float(value: Any) -> float | None:
    try:
        text = str(value if value is not None else "").strip()
        if not text:
            return None
        parsed = float(text)
        return parsed if math.isfinite(parsed) else None
    except Exception:
        return None


def _format_price(price: float) -> str:
    if price < 1.0:
        return f"{price:.4f}"
    return f"{price:.2f}"


def _format_qty(qty: float) -> str:
    return f"{qty:.9f}".rstrip("0").rstrip(".")


def _is_fractional_qty(qty: float) -> bool:
    return abs(qty - round(qty)) > 1e-8


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

    def get_clock(self) -> dict[str, Any]:
        """Return Alpaca market clock: {is_open, next_open, next_close, timestamp}."""
        return self._request("GET", "/v2/clock")

    def list_positions(self) -> list[dict[str, Any]]:
        return list(self._request("GET", "/v2/positions"))

    def list_orders(self, *, status: str = "open", limit: int = 100) -> list[dict[str, Any]]:
        return list(self._request("GET", f"/v2/orders?status={status}&direction=desc&limit={int(limit)}"))

    def get_order(self, order_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v2/orders/{order_id}")

    def submit_market_buy(self, symbol: str, notional: float) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "notional": f"{notional:.2f}",
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
        }
        return self._request("POST", "/v2/orders", payload)

    def submit_market_buy_qty(self, symbol: str, qty: float) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "qty": _format_qty(qty),
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
        }
        return self._request("POST", "/v2/orders", payload)

    def submit_bracket_buy(
        self,
        symbol: str,
        *,
        notional: float | None,
        qty: float | None,
        stop_loss_price: float,
        take_profit_price: float,
        time_in_force: str = "day",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "symbol": symbol,
            "side": "buy",
            "type": "market",
            "time_in_force": time_in_force,
            "order_class": "bracket",
            "take_profit": {"limit_price": _format_price(take_profit_price)},
            "stop_loss": {"stop_price": _format_price(stop_loss_price)},
        }
        if qty is not None and qty > 0:
            payload["qty"] = _format_qty(qty)
        elif notional is not None and notional > 0:
            payload["notional"] = f"{notional:.2f}"
        else:
            raise RuntimeError("bracket buy requires qty or notional")
        return self._request("POST", "/v2/orders", payload)

    def submit_stop_sell(self, symbol: str, *, qty: float, stop_price: float, time_in_force: str = "day") -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "qty": _format_qty(qty),
            "side": "sell",
            "type": "stop",
            "time_in_force": time_in_force,
            "stop_price": _format_price(stop_price),
        }
        return self._request("POST", "/v2/orders", payload)

    def submit_trailing_stop_sell(
        self,
        symbol: str,
        *,
        qty: float,
        trail_percent: float,
        time_in_force: str = "day",
    ) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "qty": _format_qty(qty),
            "side": "sell",
            "type": "trailing_stop",
            "time_in_force": time_in_force,
            "trail_percent": f"{trail_percent:.4f}".rstrip("0").rstrip("."),
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
                entry_price=_optional_float(row.get("entry_price")),
                stop_price=_optional_float(row.get("stop_price")),
                target_price=_optional_float(row.get("target_price")),
                weight=_optional_float(row.get("weight")),
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
    symbols: set[str] = set()
    raw = _env("ALPACA_INTRADAY_STATE_PATH", "")
    state_path = Path(raw) if raw else (Path(__file__).resolve().parent.parent / "configs" / "intraday_state.json")
    if state_path.exists():
        try:
            data = json.loads(state_path.read_text())
        except Exception:
            data = {}
        if isinstance(data, dict):
            for sym in data.keys():
                token = str(sym or "").strip().upper()
                if token:
                    symbols.add(token)

    # Intraday removes owned state after submitting a close order, while the
    # remote paper position can remain open until Alpaca fills it. Treat those
    # in-flight closes as intraday-owned so monthly cleanup cannot close them.
    advisory_raw = _env("ALPACA_INTRADAY_ADVISORY_PATH", "")
    advisory_path = (
        Path(advisory_raw)
        if advisory_raw
        else Path(__file__).resolve().parent.parent
        / "runtime"
        / "equities_intraday_dynamic_v1"
        / "latest_advisory.json"
    )
    if advisory_path.exists():
        try:
            advisory = json.loads(advisory_path.read_text())
        except Exception:
            advisory = {}
        if isinstance(advisory, dict):
            for sym in advisory.get("pending_close_positions") or []:
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


def _hwm_state_path(picks_csv: Path) -> Path:
    raw = _env("MONTHLY_HWM_STATE_PATH", "")
    if raw:
        return Path(raw)
    root = picks_csv.resolve().parent
    for _ in range(5):
        if (root / "runtime").is_dir():
            return root / "runtime" / "alpaca_monthly_hwm.json"
        root = root.parent
    return picks_csv.parent / "alpaca_monthly_hwm.json"


def _reentry_block_state_path(picks_csv: Path) -> Path:
    raw = _env("MONTHLY_REENTRY_BLOCK_STATE_PATH", "")
    if raw:
        return Path(raw)
    root = Path(__file__).resolve().parent.parent
    return root / "runtime" / "alpaca_monthly_reentry_block.json"


def _load_hwm_state(path: Path) -> dict[str, dict[str, Any]]:
    """Load {symbol: {hwm, entry_price, entry_date}} from disk."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_reentry_block_state(path: Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(data, dict) and isinstance(data.get("symbols"), dict):
        return {str(k).upper(): v for k, v in data["symbols"].items() if isinstance(v, dict)}
    return {}


def _save_reentry_block_state(path: Path, state: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"symbols": dict(sorted(state.items()))}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _active_reentry_blocks(
    state: dict[str, dict[str, Any]],
    now: datetime,
) -> dict[str, dict[str, Any]]:
    active: dict[str, dict[str, Any]] = {}
    for sym, rec in state.items():
        blocked_until = _parse_iso_utc(str(rec.get("blocked_until") or ""))
        if blocked_until is None or blocked_until <= now:
            continue
        active[sym.upper()] = rec
    return active


def _add_reentry_block(
    state: dict[str, dict[str, Any]],
    symbol: str,
    *,
    now: datetime,
    days: int,
    reason: str,
) -> None:
    if days <= 0:
        return
    sym = symbol.strip().upper()
    if not sym:
        return
    state[sym] = {
        "reason": reason,
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "blocked_until": (now + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _select_monthly_cycle_picks(
    picks: list[Pick],
    *,
    earnings_blocked: dict[str, str],
    blocked_reentry_symbols: set[str],
    max_positions: int,
    no_current_cycle: bool,
) -> list[Pick]:
    """Pick current monthly candidates after safety filters.

    The refresh step can intentionally write a wider candidate pool than the
    live max position count. This lets the bridge use next-best replacements
    when the top symbols are temporarily blocked by re-entry protection.
    """
    if no_current_cycle:
        return []
    limit = max(0, int(max_positions))
    if limit <= 0:
        return []
    return [
        p for p in picks
        if p.ticker not in earnings_blocked
        and p.ticker not in blocked_reentry_symbols
    ][:limit]


def _save_hwm_state(path: Path, state: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _update_hwm(
    state: dict[str, dict[str, Any]],
    positions: dict[str, dict[str, Any]],
    now_str: str,
) -> dict[str, dict[str, Any]]:
    """Update high-water mark for every live position."""
    for sym, pos in positions.items():
        cur = _safe_float(pos.get("current_price"), 0.0)
        entry = _safe_float(pos.get("avg_entry_price"), 0.0)
        if cur <= 0:
            continue
        rec = state.get(sym, {})
        old_hwm = _safe_float(rec.get("hwm"), cur)
        state[sym] = {
            "hwm": max(old_hwm, cur),
            "entry_price": entry if entry > 0 else _safe_float(rec.get("entry_price"), cur),
            "entry_date": rec.get("entry_date") or now_str,
            "updated": now_str,
        }
    # Drop symbols no longer in positions
    for sym in list(state.keys()):
        if sym not in positions:
            del state[sym]
    return state


def _trail_stop_triggered(
    state: dict[str, dict[str, Any]],
    sym: str,
    pos: dict[str, Any],
    trail_pct: float,
    min_gain_pct: float,
) -> tuple[bool, float, float, float]:
    """Return (triggered, current_gain_pct, drop_from_hwm_pct, peak_gain_pct).

    The trail is armed by the recorded high-water mark, not the current mark.
    Otherwise a position can cross the trailing threshold between polling runs
    and become ineligible for the close once its remaining gain falls below
    ``min_gain_pct``.
    """
    rec = state.get(sym)
    if not rec:
        return False, 0.0, 0.0, 0.0
    cur = _safe_float(pos.get("current_price"), 0.0)
    entry = _safe_float(rec.get("entry_price"), 0.0)
    hwm = _safe_float(rec.get("hwm"), cur)
    if cur <= 0 or entry <= 0 or hwm <= 0:
        return False, 0.0, 0.0, 0.0
    gain_pct = (cur - entry) / entry * 100.0
    peak_gain_pct = (hwm - entry) / entry * 100.0
    drop_pct = (hwm - cur) / hwm * 100.0
    triggered = peak_gain_pct >= min_gain_pct and drop_pct >= trail_pct * 100.0
    return triggered, round(gain_pct, 2), round(drop_pct, 2), round(peak_gain_pct, 2)


def _position_loss_pct(pos: dict[str, Any]) -> float:
    """Return how far below entry a position is (positive = loss).

    Returns 0.0 when the position is flat or profitable.
    Uses ``unrealized_plpc`` from the Alpaca API when available,
    otherwise falls back to avg_entry_price vs current_price.
    """
    raw = pos.get("unrealized_plpc")
    if raw is not None:
        try:
            plpc = float(raw)
            return -plpc if plpc < 0 else 0.0
        except Exception:
            pass
    avg_entry = _safe_float(pos.get("avg_entry_price"), 0.0)
    cur = _safe_float(pos.get("current_price"), 0.0)
    if avg_entry > 0 and cur > 0:
        loss = (avg_entry - cur) / avg_entry
        return loss if loss > 0 else 0.0
    return 0.0


def _position_gain_pct(pos: dict[str, Any], hwm_state: dict[str, dict[str, Any]], sym: str) -> float:
    rec = hwm_state.get(sym, {})
    cur = _safe_float(pos.get("current_price"), 0.0)
    entry = _safe_float(rec.get("entry_price"), 0.0) or _safe_float(pos.get("avg_entry_price"), 0.0)
    if cur <= 0 or entry <= 0:
        return 0.0
    return max(0.0, (cur - entry) / entry * 100.0)


def _build_bracket_buy_spec(
    pick: Pick,
    *,
    notional: float,
    stop_loss_pct: float,
    target_pct: float,
    size_mode: str,
) -> tuple[dict[str, Any] | None, str]:
    entry = pick.entry_price
    stop = pick.stop_price
    target = pick.target_price
    if (stop is None or stop <= 0) and entry is not None and entry > 0:
        stop = entry * (1.0 - stop_loss_pct)
    if (target is None or target <= 0) and entry is not None and entry > 0 and target_pct > 0:
        target = entry * (1.0 + target_pct)

    if stop is None or stop <= 0:
        return None, "missing_stop_price"
    if target is None or target <= 0:
        return None, "missing_target_price"
    if target <= stop:
        return None, "target_must_be_above_stop"

    spec: dict[str, Any] = {
        "stop_loss_price": stop,
        "take_profit_price": target,
        "notional": notional,
        "qty": None,
        "size_mode": size_mode,
    }
    if size_mode == "qty":
        if entry is None or entry <= 0:
            return None, "missing_entry_price_for_qty"
        qty = notional / entry
        if qty <= 0:
            return None, "non_positive_qty"
        spec["qty"] = qty
        spec["notional"] = None
    elif size_mode != "notional":
        return None, f"unsupported_size_mode:{size_mode}"
    return spec, ""


def _wait_for_filled_qty(client: AlpacaClient, order: dict[str, Any], *, timeout_sec: float) -> tuple[float, str]:
    order_id = str(order.get("id") or "").strip()
    status = str(order.get("status") or "").strip().lower()
    filled_qty = _safe_float(order.get("filled_qty"), 0.0)
    deadline = time.time() + max(0.0, timeout_sec)
    while order_id and filled_qty <= 0 and status not in {"canceled", "expired", "rejected"} and time.time() < deadline:
        time.sleep(1.0)
        try:
            order = client.get_order(order_id)
        except RuntimeError:
            break
        status = str(order.get("status") or "").strip().lower()
        filled_qty = _safe_float(order.get("filled_qty"), 0.0)
    return filled_qty, status


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

    max_positions = max(1, _env_int("ALPACA_MAX_POSITIONS", 3))
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

    # ── Enhancement: trailing stop (high-water mark) ─────────────────────────
    # Once a position gains >= MONTHLY_TRAIL_MIN_GAIN_PCT, start trailing.
    # If it then drops MONTHLY_TRAIL_PCT% from its peak → close to lock profit.
    enable_trail_stop = _env_bool("MONTHLY_TRAIL_ENABLE", True)
    trail_pct = max(0.01, _env_float("MONTHLY_TRAIL_PCT", 0.06))       # 6% drop from peak
    trail_min_gain_pct = max(0.0, _env_float("MONTHLY_TRAIL_MIN_GAIN_PCT", 8.0))  # only trail after +8%
    hwm_path = _hwm_state_path(picks_csv)

    # ── Enhancement: ATR-adjusted position sizing ─────────────────────────────
    # Low-volatility picks get more capital; high-volatility picks get less.
    # Combined weight = score / sqrt(atr20_pct) so it balances momentum vs risk.
    atr_adjusted_sizing = _env_bool("MONTHLY_ATR_SIZING", True)

    # ── Enhancement: individual stop-loss per position ────────────────────────
    # Close any position down more than MONTHLY_SL_PCT from entry.
    # Works for both held picks and stale positions.
    enable_stop_loss = _env_bool("MONTHLY_SL_ENABLE", True)
    stop_loss_pct = max(0.01, _env_float("MONTHLY_SL_PCT", 0.08))   # default 8%

    # Broker-side entry protection. When enabled, new monthly buys use an
    # Alpaca bracket order so a broker-hosted stop and target are queued as
    # soon as the entry fills. The existing HWM trail remains software-managed.
    broker_protection_enable = _env_bool("ALPACA_BROKER_PROTECTION_ENABLE", False)
    broker_protection_required = _env_bool("ALPACA_BROKER_PROTECTION_REQUIRED", broker_protection_enable)
    broker_protection_order_class = _env("ALPACA_BROKER_PROTECTION_ORDER_CLASS", "bracket").lower()
    broker_protection_size_mode = _env("ALPACA_BROKER_PROTECTION_SIZE_MODE", "qty").lower()
    broker_protection_tif = _env("ALPACA_BROKER_PROTECTION_TIF", "day").lower()
    broker_target_pct = max(0.0, _env_float("ALPACA_BROKER_TARGET_PCT", 0.08))
    broker_wait_fill_sec = max(1.0, _env_float("ALPACA_BROKER_PROTECTION_WAIT_FILL_SEC", 20.0))
    native_trailing_enable = _env_bool("ALPACA_NATIVE_TRAIL_ENABLE", False)
    native_trailing_required = _env_bool("ALPACA_NATIVE_TRAIL_REQUIRED", False)
    native_trailing_tif = _env("ALPACA_NATIVE_TRAIL_TIF", broker_protection_tif).lower()
    native_trailing_min_gain_pct = max(
        0.0,
        _env_float("ALPACA_NATIVE_TRAIL_MIN_GAIN_PCT", trail_min_gain_pct),
    )
    native_trailing_percent = max(
        0.1,
        _env_float("ALPACA_NATIVE_TRAIL_PERCENT", trail_pct * 100.0),
    )
    native_trailing_cancel_existing = _env_bool("ALPACA_NATIVE_TRAIL_CANCEL_EXISTING_STOPS", True)
    reentry_block_enable = _env_bool("MONTHLY_REENTRY_BLOCK_ENABLE", True)
    trail_reentry_block_days = max(0, _env_int("MONTHLY_TRAIL_REENTRY_BLOCK_DAYS", 14))
    reentry_block_path = _reentry_block_state_path(picks_csv)

    # ── Enhancement: score-weighted position sizing ───────────────────────────
    # Higher-momentum picks get a larger slice of the allocation.
    weighted_sizing = _env_bool("MONTHLY_WEIGHTED_SIZING", True)

    # ── Enhancement: mid-month rotation ──────────────────────────────────────
    # After day N of the month, replace held picks that have lost momentum
    # (lost > MONTHLY_MIDMONTH_DD_PCT) with next best candidates.
    midmonth_rotation = _env_bool("MONTHLY_MIDMONTH_ROTATION", True)
    midmonth_day_threshold = max(1, _env_int("MONTHLY_MIDMONTH_DAY", 14))
    midmonth_dd_pct = max(0.01, _env_float("MONTHLY_MIDMONTH_DD_PCT", 0.05))  # 5%

    key_id = _env("ALPACA_API_KEY_ID")
    secret_key = _env("ALPACA_API_SECRET_KEY")
    base_url = _env("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    live_guard_errors = _live_order_guard_errors(
        base_url=base_url,
        send_orders=send_orders,
        capital_override_usd=capital_override_usd,
    )
    if live_guard_errors:
        print(
            json.dumps(
                {
                    "error": "alpaca_live_order_guard",
                    "issues": live_guard_errors,
                    "hint": "use a monthly-v38-only live credential profile with a bounded capital override",
                },
                ensure_ascii=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 6
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
        # 2026-06-02: pre-flight market clock check.
        # New BUY orders submitted while market is closed end with
        # status=accepted and never fill within broker_wait_fill_sec,
        # causing every pick to be canceled. Skip submission if closed,
        # let next run during market hours actually fill.
        try:
            _clock = client.get_clock()
        except Exception as _exc:
            _clock = {"is_open": True, "_clock_error": str(_exc)}
        _market_is_open = bool(_clock.get("is_open"))
        if not _market_is_open:
            _next_open = _clock.get("next_open")
            print(
                f"[paper_bridge] market closed (next_open={_next_open}); skipping new BUY submissions this run",
                flush=True,
            )
    buying_power = float(account.get("buying_power") or account.get("cash") or 0.0)
    cash = float(account.get("cash") or 0.0)
    effective_capital = min(buying_power, capital_override_usd) if capital_override_usd > 0 else buying_power
    current_positions = {str(p.get("symbol") or "").strip().upper(): p for p in positions if str(p.get("symbol") or "").strip()}
    pending_buy_orders: dict[str, list[dict[str, Any]]] = {}
    open_sell_orders: dict[str, list[dict[str, Any]]] = {}
    open_stop_sell_orders: dict[str, list[dict[str, Any]]] = {}
    open_trailing_sell_orders: dict[str, list[dict[str, Any]]] = {}
    for order in open_orders:
        symbol = str(order.get("symbol") or "").strip().upper()
        side = str(order.get("side") or "").strip().lower()
        status = str(order.get("status") or "").strip().lower()
        order_type = str(order.get("type") or "").strip().lower()
        if not symbol:
            continue
        if status in {"accepted", "new", "pending_new", "partially_filled", "accepted_for_bidding"}:
            if side == "buy":
                pending_buy_orders.setdefault(symbol, []).append(order)
            elif side == "sell":
                open_sell_orders.setdefault(symbol, []).append(order)
                if order_type in {"stop", "stop_limit", "trailing_stop"}:
                    open_stop_sell_orders.setdefault(symbol, []).append(order)
                if order_type == "trailing_stop":
                    open_trailing_sell_orders.setdefault(symbol, []).append(order)
    occupied_symbols = set(current_positions.keys()) | set(pending_buy_orders.keys())
    now_utc = datetime.now(timezone.utc)
    reentry_block_state: dict[str, dict[str, Any]] = {}
    active_reentry_blocks: dict[str, dict[str, Any]] = {}
    blocked_reentry_symbols: set[str] = set()
    if reentry_block_enable:
        reentry_block_state = _active_reentry_blocks(_load_reentry_block_state(reentry_block_path), now_utc)
        blocked_reentry_symbols = set(reentry_block_state) - occupied_symbols
        active_reentry_blocks = {
            sym: rec for sym, rec in reentry_block_state.items()
            if sym in blocked_reentry_symbols
        }
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

    selected = _select_monthly_cycle_picks(
        picks,
        earnings_blocked=earnings_blocked,
        blocked_reentry_symbols=blocked_reentry_symbols,
        max_positions=max_positions,
        no_current_cycle=no_current_cycle,
    )
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

    # ── Stop-loss detection ───────────────────────────────────────────────────
    # Any position (held or stale) that is down >= stop_loss_pct → force close.
    sl_triggered_symbols: list[str] = []
    sl_details: dict[str, float] = {}
    if enable_stop_loss and not offline_dry_run:
        for sym, pos in current_positions.items():
            if sym in intraday_managed_symbols:
                continue  # Never touch intraday-managed positions
            loss = _position_loss_pct(pos)
            if loss >= stop_loss_pct:
                sl_triggered_symbols.append(sym)
                sl_details[sym] = round(loss * 100, 2)

    # ── Trailing stop detection ───────────────────────────────────────────────
    # Load/update HWM state BEFORE checking trailing stops
    hwm_state: dict[str, dict[str, Any]] = {}
    trail_triggered_symbols: list[str] = []
    trail_details: dict[str, dict[str, float]] = {}
    native_trailing_candidates: list[str] = []
    native_trailing_details: dict[str, dict[str, float]] = {}
    native_trailing_fractional_skips: list[str] = []
    now_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if (enable_trail_stop or native_trailing_enable) and not offline_dry_run:
        hwm_state = _load_hwm_state(hwm_path)
        hwm_state = _update_hwm(hwm_state, current_positions, now_utc_str)
        for sym in list(current_positions.keys()):
            if sym in intraday_managed_symbols:
                continue
            if sym in sl_triggered_symbols:
                continue  # SL already handles this one
            if native_trailing_enable and open_trailing_sell_orders.get(sym):
                continue  # Broker-hosted trailing stop already owns this exit.
            pos = current_positions[sym]
            if native_trailing_enable:
                qty = abs(_safe_float(pos.get("qty"), 0.0))
                if qty > 0 and _is_fractional_qty(qty):
                    native_trailing_fractional_skips.append(sym)
                else:
                    gain = _position_gain_pct(pos, hwm_state, sym)
                    if gain >= native_trailing_min_gain_pct:
                        native_trailing_candidates.append(sym)
                        native_trailing_details[sym] = {
                            "gain_pct": round(gain, 2),
                            "trail_percent": round(native_trailing_percent, 4),
                        }
                        continue
            if enable_trail_stop:
                fired, gain, drop, peak_gain = _trail_stop_triggered(
                    hwm_state, sym, pos, trail_pct, trail_min_gain_pct
                )
                if fired:
                    trail_triggered_symbols.append(sym)
                    trail_details[sym] = {
                        "gain_pct": gain,
                        "peak_gain_pct": peak_gain,
                        "drop_from_hwm_pct": drop,
                    }
                    continue

    # Symbols freed by stop-loss may become new buy candidates
    # (we'll try to fill with next-best picks after closing)
    sl_freed_slots = len(sl_triggered_symbols)

    # ── Mid-month rotation detection ─────────────────────────────────────────
    today_day = datetime.now(timezone.utc).day
    rotation_symbols: list[str] = []
    rotation_details: dict[str, float] = {}
    if midmonth_rotation and today_day > midmonth_day_threshold and not offline_dry_run:
        for sym in list(hold_symbols):
            if sym in sl_triggered_symbols:
                continue  # Already being closed by SL
            if sym in intraday_managed_symbols:
                continue
            pos = current_positions.get(sym, {})
            loss = _position_loss_pct(pos)
            if loss >= midmonth_dd_pct:
                rotation_symbols.append(sym)
                rotation_details[sym] = round(loss * 100, 2)

    # Symbols being rotated out are treated as stale for buy purposes
    rotated_out = set(rotation_symbols)
    trail_out = set(trail_triggered_symbols)
    closed_out = set(sl_triggered_symbols) | rotated_out | trail_out

    # Extend new_buy_symbols: after SL + rotation + trail closes, fill with next picks
    extended_candidates = [
        p.ticker for p in picks
        if p.ticker not in earnings_blocked and p.ticker not in blocked_reentry_symbols
    ]
    already_handled = (
        (set(hold_symbols) - closed_out)
        | set(new_buy_symbols)
        | closed_out
    )
    replacement_picks = [t for t in extended_candidates if t not in already_handled]
    replacement_slots = len(closed_out) - len([s for s in closed_out if s not in current_positions])
    replacement_buys = replacement_picks[:replacement_slots] if replacement_slots > 0 else []

    # ── Score-weighted + ATR-adjusted position sizing ─────────────────────────
    # Combined weight = score × (1 / sqrt(atr20_pct)) so high-volatility picks
    # get less capital automatically.  Fallback: equal weight.
    all_buy_tickers = new_buy_symbols + replacement_buys
    all_buy_set = set(all_buy_tickers)
    all_active = [p for p in picks if p.ticker in (selected_symbols | all_buy_set)]

    def _raw_weight(p: Pick) -> float:
        base = max(0.001, p.score)
        if atr_adjusted_sizing and p.atr20_pct > 0:
            base = base / max(0.5, math.sqrt(p.atr20_pct))
        return base

    if (weighted_sizing or atr_adjusted_sizing) and all_active:
        raw = {p.ticker: _raw_weight(p) for p in all_active}
        total_raw = sum(raw.values()) or 1.0
        score_weights = {t: w / total_raw for t, w in raw.items()}
        # Clamp: no single position > 60% of allocation
        max_w = min(0.60, max(score_weights.values()) if score_weights else 0.60)
        score_weights = {t: min(w, max_w) for t, w in score_weights.items()}
        sw_total = sum(score_weights.values()) or 1.0
        score_weights = {t: w / sw_total for t, w in score_weights.items()}
        per_ticker_notional: dict[str, float] = {
            t: max(min_dollar_order, effective_capital * target_alloc_pct * w)
            for t, w in score_weights.items()
        }
        per_position_notional = max(
            min_dollar_order,
            effective_capital * target_alloc_pct / max(1, len(all_active)),
        )
    else:
        per_position_notional = (
            max(min_dollar_order, effective_capital * target_alloc_pct / max(1, len(selected)))
            if selected
            else 0.0
        )
        per_ticker_notional = {p.ticker: per_position_notional for p in all_active}
        score_weights = {}
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
        "stop_loss_pct": round(stop_loss_pct * 100, 2),
        "stop_loss_enabled": enable_stop_loss,
        "sl_triggered": sl_triggered_symbols,
        "sl_loss_pct": sl_details,
        "trail_stop_enabled": enable_trail_stop,
        "trail_pct": round(trail_pct * 100, 2),
        "trail_min_gain_pct": trail_min_gain_pct,
        "trail_triggered": trail_triggered_symbols,
        "trail_details": trail_details,
        "native_trailing_enabled": native_trailing_enable,
        "native_trailing_required": native_trailing_required,
        "native_trailing_tif": native_trailing_tif,
        "native_trailing_min_gain_pct": native_trailing_min_gain_pct,
        "native_trailing_percent": round(native_trailing_percent, 4),
        "native_trailing_candidates": native_trailing_candidates,
        "native_trailing_details": native_trailing_details,
        "native_trailing_fractional_skips": native_trailing_fractional_skips,
        "reentry_block_enabled": reentry_block_enable,
        "trail_reentry_block_days": trail_reentry_block_days,
        "reentry_blocked_symbols": sorted(active_reentry_blocks),
        "reentry_block_details": active_reentry_blocks,
        "broker_protection_enabled": broker_protection_enable,
        "broker_protection_required": broker_protection_required,
        "broker_protection_order_class": broker_protection_order_class,
        "broker_protection_size_mode": broker_protection_size_mode,
        "broker_protection_tif": broker_protection_tif,
        "broker_target_pct": round(broker_target_pct * 100, 2),
        "broker_wait_fill_sec": broker_wait_fill_sec,
        "midmonth_rotation_enabled": midmonth_rotation,
        "midmonth_day_threshold": midmonth_day_threshold,
        "midmonth_dd_pct": round(midmonth_dd_pct * 100, 2),
        "rotation_triggered": rotation_symbols,
        "rotation_loss_pct": rotation_details,
        "replacement_buys": replacement_buys,
        "weighted_sizing": weighted_sizing,
        "atr_adjusted_sizing": atr_adjusted_sizing,
        "score_weights": {t: round(w, 4) for t, w in score_weights.items()},
        "pending_buy_orders": [
            {
                "ticker": sym,
                "count": len(orders),
                "order_ids": [str(o.get("id") or "") for o in orders if str(o.get("id") or "").strip()],
                "notionals": [str(o.get("notional") or "") for o in orders],
            }
            for sym, orders in sorted(pending_buy_orders.items())
        ],
        "open_stop_sell_orders": [
            {
                "ticker": sym,
                "count": len(orders),
                "order_ids": [str(o.get("id") or "") for o in orders if str(o.get("id") or "").strip()],
                "stop_prices": [str(o.get("stop_price") or "") for o in orders],
            }
            for sym, orders in sorted(open_stop_sell_orders.items())
        ],
        "open_trailing_sell_orders": [
            {
                "ticker": sym,
                "count": len(orders),
                "order_ids": [str(o.get("id") or "") for o in orders if str(o.get("id") or "").strip()],
                "trail_percents": [str(o.get("trail_percent") or "") for o in orders],
            }
            for sym, orders in sorted(open_trailing_sell_orders.items())
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
                "entry_price": None if p.entry_price is None else round(p.entry_price, 4),
                "stop_price": None if p.stop_price is None else round(p.stop_price, 4),
                "target_price": None if p.target_price is None else round(p.target_price, 4),
            }
            for p in selected
        ],
        "planned_broker_orders": [],
        "results": [],
    }
    picks_by_ticker = {p.ticker: p for p in picks}
    for ticker in all_buy_tickers:
        pick = picks_by_ticker.get(ticker)
        if pick is None:
            continue
        notional = per_ticker_notional.get(ticker, per_position_notional)
        spec, reason = _build_bracket_buy_spec(
            pick,
            notional=notional,
            stop_loss_pct=stop_loss_pct,
            target_pct=broker_target_pct,
            size_mode=broker_protection_size_mode,
        )
        report["planned_broker_orders"].append(
            {
                "ticker": ticker,
                "order_class": broker_protection_order_class if broker_protection_enable else "market",
                "status": "ok" if (not broker_protection_enable or spec is not None) else "invalid",
                "reason": reason,
                "notional": round(notional, 2),
                "qty": None if spec is None or spec.get("qty") is None else _format_qty(float(spec["qty"])),
                "stop_price": None if spec is None else round(float(spec["stop_loss_price"]), 4),
                "target_price": None if spec is None else round(float(spec["take_profit_price"]), 4),
            }
        )

    def _submit_buy_action(pick: Pick, *, action: str, notional: float) -> None:
        score_weight = round(score_weights.get(pick.ticker, 0.0), 4)
        # 2026-06-02: skip BUY submissions while market is closed.
        if not offline_dry_run and not _market_is_open:
            report["results"].append(
                {
                    "ticker": pick.ticker,
                    "action": action,
                    "status": "skipped_market_closed",
                    "error": "alpaca_clock_is_open_false",
                    "notional": round(notional, 2),
                    "score_weight": score_weight,
                }
            )
            return
        if broker_protection_enable:
            if broker_protection_order_class not in {"bracket", "simple_stop"}:
                reason = f"unsupported_broker_protection_order_class:{broker_protection_order_class}"
                if broker_protection_required:
                    report["results"].append(
                        {
                            "ticker": pick.ticker,
                            "action": action,
                            "status": "skipped_unprotected",
                            "error": reason,
                            "notional": round(notional, 2),
                            "score_weight": score_weight,
                        }
                    )
                    return

            spec, reason = _build_bracket_buy_spec(
                pick,
                notional=notional,
                stop_loss_pct=stop_loss_pct,
                target_pct=broker_target_pct,
                size_mode=broker_protection_size_mode,
            )
            if spec is None:
                if broker_protection_required:
                    report["results"].append(
                        {
                            "ticker": pick.ticker,
                            "action": action,
                            "status": "skipped_unprotected",
                            "error": reason,
                            "notional": round(notional, 2),
                            "score_weight": score_weight,
                        }
                    )
                    return
            elif broker_protection_order_class == "simple_stop":
                try:
                    qty = float(spec.get("qty") or 0.0)
                    if qty <= 0:
                        raise RuntimeError("simple_stop requires qty sizing")
                    entry_order = client.submit_market_buy_qty(pick.ticker, qty)  # type: ignore[union-attr]
                    filled_qty, entry_status = _wait_for_filled_qty(
                        client,  # type: ignore[arg-type]
                        entry_order,
                        timeout_sec=broker_wait_fill_sec,
                    )
                    if filled_qty <= 0:
                        order_id = str(entry_order.get("id") or "").strip()
                        if order_id:
                            try:
                                client.cancel_order(order_id)  # type: ignore[union-attr]
                            except RuntimeError:
                                pass
                        raise RuntimeError(f"entry_not_filled_before_stop status={entry_status}")
                    stop_order = client.submit_stop_sell(  # type: ignore[union-attr]
                        pick.ticker,
                        qty=filled_qty,
                        stop_price=float(spec["stop_loss_price"]),
                        time_in_force=broker_protection_tif,
                    )
                    report["results"].append(
                        {
                            "ticker": pick.ticker,
                            "action": "protected_market_buy" if action == "market_buy" else "replacement_protected_market_buy",
                            "entry_order_id": entry_order.get("id"),
                            "entry_status": entry_status,
                            "stop_order_id": stop_order.get("id"),
                            "stop_status": stop_order.get("status"),
                            "notional": round(notional, 2),
                            "qty": _format_qty(filled_qty),
                            "stop_price": round(float(spec["stop_loss_price"]), 4),
                            "target_price": round(float(spec["take_profit_price"]), 4),
                            "score_weight": score_weight,
                        }
                    )
                    return
                except RuntimeError as exc:
                    if broker_protection_required:
                        try:
                            client.close_position(pick.ticker)  # type: ignore[union-attr]
                        except RuntimeError:
                            pass
                        report["results"].append(
                            {
                                "ticker": pick.ticker,
                                "action": "protected_market_buy" if action == "market_buy" else "replacement_protected_market_buy",
                                "status": "error_closed_if_needed",
                                "error": str(exc),
                                "notional": round(notional, 2),
                                "score_weight": score_weight,
                            }
                        )
                        return
            else:
                try:
                    result = client.submit_bracket_buy(  # type: ignore[union-attr]
                        pick.ticker,
                        notional=spec.get("notional"),
                        qty=spec.get("qty"),
                        stop_loss_price=float(spec["stop_loss_price"]),
                        take_profit_price=float(spec["take_profit_price"]),
                        time_in_force=broker_protection_tif,
                    )
                    report["results"].append(
                        {
                            "ticker": pick.ticker,
                            "action": "bracket_buy" if action == "market_buy" else "replacement_bracket_buy",
                            "order_id": result.get("id"),
                            "status": result.get("status"),
                            "notional": round(notional, 2),
                            "qty": None if spec.get("qty") is None else _format_qty(float(spec["qty"])),
                            "stop_price": round(float(spec["stop_loss_price"]), 4),
                            "target_price": round(float(spec["take_profit_price"]), 4),
                            "score_weight": score_weight,
                        }
                    )
                    return
                except RuntimeError as exc:
                    if broker_protection_required:
                        report["results"].append(
                            {
                                "ticker": pick.ticker,
                                "action": "bracket_buy" if action == "market_buy" else "replacement_bracket_buy",
                                "status": "error",
                                "error": str(exc),
                                "notional": round(notional, 2),
                                "score_weight": score_weight,
                            }
                        )
                        return

        result = client.submit_market_buy(pick.ticker, notional)  # type: ignore[union-attr]
        report["results"].append(
            {
                "ticker": pick.ticker,
                "action": action,
                "order_id": result.get("id"),
                "status": result.get("status"),
                "notional": round(notional, 2),
                "score_weight": score_weight,
                "broker_protection": False,
            }
        )

    def _cancel_open_sell_orders(symbol: str, *, action: str) -> bool:
        """Cancel existing protective sell orders so Alpaca releases held qty."""
        cancel_failed = False
        for order in open_sell_orders.get(symbol, []):
            order_id = str(order.get("id") or "").strip()
            if not order_id:
                continue
            try:
                result = client.cancel_order(order_id)
                report["results"].append(
                    {
                        "ticker": symbol,
                        "action": action,
                        "order_id": order_id,
                        "status": result.get("status", "canceled"),
                    }
                )
            except RuntimeError as exc:
                cancel_failed = True
                report["results"].append(
                    {
                        "ticker": symbol,
                        "action": action,
                        "order_id": order_id,
                        "status": "error",
                        "error": str(exc),
                    }
                )
        return not cancel_failed

    if send_orders:
        # ── 1. Stop-loss closes (highest priority) ────────────────────────────
        if enable_stop_loss:
            for symbol in sl_triggered_symbols:
                if symbol not in current_positions:
                    continue
                if not _cancel_open_sell_orders(symbol, action="stop_loss_cancel_sell_order"):
                    continue
                try:
                    result = client.close_position(symbol)
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "stop_loss_close",
                            "loss_pct": sl_details.get(symbol, 0.0),
                            "order_id": result.get("id"),
                            "status": result.get("status"),
                        }
                    )
                except RuntimeError as exc:
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "stop_loss_close",
                            "status": "error",
                            "error": str(exc),
                        }
                    )

        # ── 1b. Trailing stop closes (lock-in profits) ────────────────────────
        if enable_trail_stop:
            for symbol in trail_triggered_symbols:
                if symbol not in current_positions:
                    continue
                det = trail_details.get(symbol, {})
                if not _cancel_open_sell_orders(symbol, action="trail_stop_cancel_sell_order"):
                    continue
                try:
                    result = client.close_position(symbol)
                    if reentry_block_enable:
                        _add_reentry_block(
                            reentry_block_state,
                            symbol,
                            now=now_utc,
                            days=trail_reentry_block_days,
                            reason="trail_stop_close",
                        )
                    report["results"].append({
                        "ticker": symbol,
                        "action": "trail_stop_close",
                        "gain_pct": det.get("gain_pct", 0.0),
                        "drop_from_hwm_pct": det.get("drop_from_hwm_pct", 0.0),
                        "order_id": result.get("id"),
                        "status": result.get("status"),
                    })
                except RuntimeError as exc:
                    report["results"].append({
                        "ticker": symbol,
                        "action": "trail_stop_close",
                        "status": "error",
                        "error": str(exc),
                    })
                    pick = picks_by_ticker.get(symbol)
                    if not pick:
                        continue
                    notional = per_ticker_notional.get(symbol, per_position_notional)
                    spec, reason = _build_bracket_buy_spec(
                        pick,
                        notional=notional,
                        stop_loss_pct=stop_loss_pct,
                        target_pct=broker_target_pct,
                        size_mode="qty",
                    )
                    if spec is None:
                        report["results"].append({
                            "ticker": symbol,
                            "action": "trail_stop_fallback_stop",
                            "status": "skipped",
                            "error": reason,
                        })
                        continue
                    qty = abs(_safe_float(current_positions.get(symbol, {}).get("qty"), 0.0))
                    if qty <= 0:
                        continue
                    try:
                        fallback = client.submit_stop_sell(
                            symbol,
                            qty=qty,
                            stop_price=float(spec["stop_loss_price"]),
                            time_in_force=broker_protection_tif,
                        )
                        report["results"].append({
                            "ticker": symbol,
                            "action": "trail_stop_fallback_stop",
                            "order_id": fallback.get("id"),
                            "status": fallback.get("status"),
                            "qty": _format_qty(qty),
                            "stop_price": round(float(spec["stop_loss_price"]), 4),
                        })
                    except RuntimeError as fallback_exc:
                        report["results"].append({
                            "ticker": symbol,
                            "action": "trail_stop_fallback_stop",
                            "status": "error",
                            "error": str(fallback_exc),
                        })
            # Persist updated HWM state
            _save_hwm_state(hwm_path, hwm_state)
            if reentry_block_enable:
                _save_reentry_block_state(reentry_block_path, reentry_block_state)

        # ── 2. Mid-month rotation closes ──────────────────────────────────────
        if midmonth_rotation and rotation_symbols:
            for symbol in rotation_symbols:
                if symbol not in current_positions:
                    continue
                try:
                    result = client.close_position(symbol)
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "rotation_close",
                            "loss_pct": rotation_details.get(symbol, 0.0),
                            "order_id": result.get("id"),
                            "status": result.get("status"),
                        }
                    )
                except RuntimeError as exc:
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "rotation_close",
                            "status": "error",
                            "error": str(exc),
                        }
                    )

        # ── 2b. Promote profitable monthly positions to broker-native trail ──
        if native_trailing_enable:
            for symbol in native_trailing_candidates:
                if symbol not in current_positions:
                    continue
                if symbol in closed_out:
                    continue
                if symbol in intraday_managed_symbols:
                    continue
                if open_trailing_sell_orders.get(symbol):
                    continue
                pos = current_positions.get(symbol, {})
                qty = abs(_safe_float(pos.get("qty"), 0.0))
                if qty <= 0:
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "native_trailing_stop_sell",
                            "status": "skipped",
                            "error": "missing_qty",
                        }
                    )
                    continue

                cancel_failed = False
                if native_trailing_cancel_existing:
                    for order in open_sell_orders.get(symbol, []):
                        order_id = str(order.get("id") or "").strip()
                        if not order_id:
                            continue
                        try:
                            result = client.cancel_order(order_id)
                            report["results"].append(
                                {
                                    "ticker": symbol,
                                    "action": "native_trailing_cancel_sell_order",
                                    "order_id": order_id,
                                    "status": result.get("status", "canceled"),
                                }
                            )
                        except RuntimeError as exc:
                            cancel_failed = True
                            report["results"].append(
                                {
                                    "ticker": symbol,
                                    "action": "native_trailing_cancel_sell_order",
                                    "order_id": order_id,
                                    "status": "error",
                                    "error": str(exc),
                                }
                            )
                    if cancel_failed and native_trailing_required:
                        continue

                try:
                    result = client.submit_trailing_stop_sell(
                        symbol,
                        qty=qty,
                        trail_percent=native_trailing_percent,
                        time_in_force=native_trailing_tif,
                    )
                    det = native_trailing_details.get(symbol, {})
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "native_trailing_stop_sell",
                            "order_id": result.get("id"),
                            "status": result.get("status"),
                            "qty": _format_qty(qty),
                            "gain_pct": det.get("gain_pct", 0.0),
                            "trail_percent": native_trailing_percent,
                        }
                    )
                except RuntimeError as exc:
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "native_trailing_stop_sell",
                            "status": "error",
                            "error": str(exc),
                            "qty": _format_qty(qty),
                            "trail_percent": native_trailing_percent,
                        }
                    )
                    pick = picks_by_ticker.get(symbol)
                    if not pick:
                        continue
                    notional = per_ticker_notional.get(symbol, per_position_notional)
                    spec, reason = _build_bracket_buy_spec(
                        pick,
                        notional=notional,
                        stop_loss_pct=stop_loss_pct,
                        target_pct=broker_target_pct,
                        size_mode="qty",
                    )
                    if spec is None:
                        report["results"].append(
                            {
                                "ticker": symbol,
                                "action": "native_trailing_fallback_stop",
                                "status": "skipped",
                                "error": reason,
                            }
                        )
                        continue
                    try:
                        fallback = client.submit_stop_sell(
                            symbol,
                            qty=qty,
                            stop_price=float(spec["stop_loss_price"]),
                            time_in_force=broker_protection_tif,
                        )
                        report["results"].append(
                            {
                                "ticker": symbol,
                                "action": "native_trailing_fallback_stop",
                                "order_id": fallback.get("id"),
                                "status": fallback.get("status"),
                                "qty": _format_qty(qty),
                                "stop_price": round(float(spec["stop_loss_price"]), 4),
                            }
                        )
                    except RuntimeError as fallback_exc:
                        report["results"].append(
                            {
                                "ticker": symbol,
                                "action": "native_trailing_fallback_stop",
                                "status": "error",
                                "error": str(fallback_exc),
                            }
                        )

        # ── 3. Close stale positions (classic month-end rotation) ─────────────
        if close_stale_positions:
            for symbol in stale_symbols:
                if symbol in sl_triggered_symbols or symbol in rotation_symbols:
                    continue  # Already handled above
                if not _cancel_open_sell_orders(symbol, action="close_position_cancel_sell_order"):
                    continue
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

        # ── 3b. Re-arm broker stop for existing monthly fractional positions ─
        if broker_protection_enable and broker_protection_order_class == "simple_stop":
            for symbol in hold_symbols:
                if symbol in intraday_managed_symbols:
                    continue
                if symbol in closed_out:
                    continue
                if open_stop_sell_orders.get(symbol):
                    continue
                pos = current_positions.get(symbol)
                pick = picks_by_ticker.get(symbol)
                if not pos or not pick:
                    continue
                notional = per_ticker_notional.get(symbol, per_position_notional)
                spec, reason = _build_bracket_buy_spec(
                    pick,
                    notional=notional,
                    stop_loss_pct=stop_loss_pct,
                    target_pct=broker_target_pct,
                    size_mode="qty",
                )
                qty = abs(_safe_float(pos.get("qty"), 0.0))
                if spec is None or qty <= 0:
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "rearm_stop_sell",
                            "status": "skipped",
                            "error": reason or "missing_qty",
                        }
                    )
                    continue
                stop_price = float(spec["stop_loss_price"])
                cur = _safe_float(pos.get("current_price"), 0.0)
                try:
                    if cur > 0 and cur <= stop_price:
                        result = client.close_position(symbol)
                        report["results"].append(
                            {
                                "ticker": symbol,
                                "action": "rearm_close_below_stop",
                                "order_id": result.get("id"),
                                "status": result.get("status"),
                                "current_price": round(cur, 4),
                                "stop_price": round(stop_price, 4),
                            }
                        )
                    else:
                        result = client.submit_stop_sell(symbol, qty=qty, stop_price=stop_price, time_in_force=broker_protection_tif)
                        report["results"].append(
                            {
                                "ticker": symbol,
                                "action": "rearm_stop_sell",
                                "order_id": result.get("id"),
                                "status": result.get("status"),
                                "qty": _format_qty(qty),
                                "stop_price": round(stop_price, 4),
                            }
                        )
                except RuntimeError as exc:
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "rearm_stop_sell",
                            "status": "error",
                            "error": str(exc),
                        }
                    )

        # ── 4. Buy new picks (main cycle) ─────────────────────────────────────
        for pick in selected:
            if pick.ticker in current_positions and pick.ticker not in sl_triggered_symbols and pick.ticker not in rotation_symbols:
                report["results"].append(
                    {
                        "ticker": pick.ticker,
                        "action": "hold_existing",
                        "status": "skipped_existing_position",
                        "score_weight": round(score_weights.get(pick.ticker, 0.0), 4),
                    }
                )
                continue
            if pick.ticker in pending_buy_orders and pick.ticker not in sl_triggered_symbols:
                report["results"].append(
                    {
                        "ticker": pick.ticker,
                        "action": "hold_pending_buy",
                        "status": "skipped_existing_open_order",
                    }
                )
                continue
            notional = per_ticker_notional.get(pick.ticker, per_position_notional)
            _submit_buy_action(pick, action="market_buy", notional=notional)

        # ── 5. Buy replacement picks (after SL/rotation freed slots) ──────────
        for ticker in replacement_buys:
            if ticker in current_positions or ticker in pending_buy_orders:
                continue
            if ticker in earnings_blocked:
                continue
            notional = per_ticker_notional.get(ticker, per_position_notional)
            try:
                pick = picks_by_ticker.get(ticker)
                if pick is None:
                    report["results"].append(
                        {
                            "ticker": ticker,
                            "action": "replacement_buy",
                            "status": "error",
                            "error": "missing_pick_details",
                            "notional": round(notional, 2),
                        }
                    )
                    continue
                _submit_buy_action(pick, action="replacement_buy", notional=notional)
            except RuntimeError as exc:
                report["results"].append(
                    {
                        "ticker": ticker,
                        "action": "replacement_buy",
                        "status": "error",
                        "error": str(exc),
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
                notional = r.get("notional", per_position_notional)
                sw = r.get("score_weight", 0.0)
                sw_str = f" w={sw:.2f}" if weighted_sizing and sw > 0 else ""
                lines.append(f"  🟢 BUY {ticker} ${round(notional,0):.0f}{sw_str} — {r.get('status','?')}")
            elif action == "bracket_buy":
                notional = r.get("notional", per_position_notional)
                sw = r.get("score_weight", 0.0)
                sw_str = f" w={sw:.2f}" if weighted_sizing and sw > 0 else ""
                lines.append(
                    f"  🟢 BRACKET {ticker} ${round(notional,0):.0f}{sw_str} "
                    f"SL {r.get('stop_price','?')} TP {r.get('target_price','?')} — {r.get('status','?')}"
                )
            elif action == "replacement_buy":
                notional = r.get("notional", per_position_notional)
                lines.append(f"  🔄 REPLACE-BUY {ticker} ${round(notional,0):.0f} — {r.get('status','?')}")
            elif action == "replacement_bracket_buy":
                notional = r.get("notional", per_position_notional)
                lines.append(
                    f"  🔄 REPLACE-BRACKET {ticker} ${round(notional,0):.0f} "
                    f"SL {r.get('stop_price','?')} TP {r.get('target_price','?')} — {r.get('status','?')}"
                )
            elif action == "protected_market_buy":
                notional = r.get("notional", per_position_notional)
                sw = r.get("score_weight", 0.0)
                sw_str = f" w={sw:.2f}" if weighted_sizing and sw > 0 else ""
                lines.append(
                    f"  🟢 BUY+STOP {ticker} ${round(notional,0):.0f}{sw_str} "
                    f"SL {r.get('stop_price','?')} — {r.get('stop_status', r.get('status','?'))}"
                )
            elif action == "replacement_protected_market_buy":
                notional = r.get("notional", per_position_notional)
                lines.append(
                    f"  🔄 REPLACE BUY+STOP {ticker} ${round(notional,0):.0f} "
                    f"SL {r.get('stop_price','?')} — {r.get('stop_status', r.get('status','?'))}"
                )
            elif action == "trail_stop_close":
                gain = r.get("gain_pct", 0.0)
                drop = r.get("drop_from_hwm_pct", 0.0)
                lines.append(f"  🔒 TRAIL-CLOSE {ticker} +{gain:.1f}% from entry, -{drop:.1f}% from peak")
            elif action == "stop_loss_close":
                loss = r.get("loss_pct", 0.0)
                lines.append(f"  🛑 STOP-LOSS {ticker} -{loss:.1f}% — {r.get('status','?')}")
            elif action == "rotation_close":
                loss = r.get("loss_pct", 0.0)
                lines.append(f"  🔁 ROTATE-OUT {ticker} -{loss:.1f}% (mid-month)")
            elif action == "close_position":
                lines.append(f"  🔴 CLOSE {ticker}")
            elif action == "cancel_pending_buy":
                lines.append(f"  🟠 CANCEL pending {ticker}")
            elif action == "rearm_stop_sell":
                lines.append(f"  🛡️ REARM STOP {ticker} SL {r.get('stop_price','?')} — {r.get('status','?')}")
            elif action == "rearm_close_below_stop":
                lines.append(f"  🛑 CLOSE {ticker}: current <= broker stop — {r.get('status','?')}")
            elif action == "native_trailing_cancel_sell_order":
                lines.append(f"  🟠 CANCEL fixed sell {ticker} before native trail — {r.get('status','?')}")
            elif action == "native_trailing_stop_sell":
                lines.append(
                    f"  🧷 NATIVE TRAIL {ticker} trail {r.get('trail_percent','?')}% "
                    f"after +{r.get('gain_pct', 0.0):.1f}% — {r.get('status','?')}"
                )
            elif action == "native_trailing_fallback_stop":
                lines.append(f"  🛡️ FALLBACK STOP {ticker} SL {r.get('stop_price','?')} — {r.get('status','?')}")
            elif action == "hold_existing":
                sw = r.get("score_weight", 0.0)
                sw_str = f" w={sw:.2f}" if weighted_sizing and sw > 0 else ""
                lines.append(f"  🟡 HOLD {ticker}{sw_str}")
            elif action == "hold_pending_buy":
                lines.append(f"  🟡 HOLD pending {ticker}")
        if not report["results"]:
            lines.append("  — No actions taken —")
        if advisory:
            lines += ["", "🧠 <b>AI advisory</b>", str(advisory.get("note") or "").strip()]
        _tg_send_equities_report(tg_token, tg_chat_id, "\n".join(lines), report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
