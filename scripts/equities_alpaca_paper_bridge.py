#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import math
import os
import ssl
import stat
import sys
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import urlencode

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


def _atomic_write_json(path: Path, payload: Any) -> None:
    """Durably replace one JSON state file without exposing a partial value."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd: int | None = None
    try:
        fd = os.open(tmp, flags, 0o600)
        data = (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short JSON state write")
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.replace(tmp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if fd is not None:
            os.close(fd)
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


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

    state["equities_hold_only"] = {"digest": digest, "ts": now}
    _atomic_write_json(path, state)
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


def _hard_capped_normalized_weights(
    raw_weights: dict[str, float], *, maximum_weight: float = 0.60
) -> dict[str, float]:
    """Normalize weights without ever re-breaching the per-name hard cap.

    If too few eligible names exist to fill the sleeve under the cap, the
    unallocated remainder stays cash.  The former cap-then-renormalize path
    could turn one capped 60% name back into 100% of the allocated sleeve.
    """
    if not 0.0 < maximum_weight <= 1.0:
        raise ValueError("maximum_weight must be in (0, 1]")
    clean = {
        str(symbol): float(value)
        for symbol, value in raw_weights.items()
        if str(symbol) and math.isfinite(float(value)) and float(value) > 0.0
    }
    if not clean:
        return {}
    result = {symbol: 0.0 for symbol in clean}
    remaining = set(clean)
    remaining_mass = min(1.0, len(clean) * maximum_weight)
    while remaining and remaining_mass > 1e-12:
        total_raw = sum(clean[symbol] for symbol in remaining)
        capped = [
            symbol
            for symbol in sorted(remaining)
            if remaining_mass * clean[symbol] / total_raw >= maximum_weight - 1e-12
        ]
        if not capped:
            for symbol in remaining:
                result[symbol] = remaining_mass * clean[symbol] / total_raw
            break
        for symbol in capped:
            result[symbol] = maximum_weight
            remaining.remove(symbol)
            remaining_mass -= maximum_weight
    return result


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
    try:
        value = Decimal(str(qty))
    except (InvalidOperation, ValueError):
        return True
    if not value.is_finite() or value <= 0:
        return True
    return value != value.to_integral_value()


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


class AlpacaAPIError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


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
            raise AlpacaAPIError(exc.code, f"{method} {path} failed: {exc.code} {detail}") from exc

    def get_account(self) -> dict[str, Any]:
        return self._request("GET", "/v2/account")

    def get_clock(self) -> dict[str, Any]:
        """Return Alpaca market clock: {is_open, next_open, next_close, timestamp}."""
        return self._request("GET", "/v2/clock")

    def list_positions(self) -> list[dict[str, Any]]:
        return list(self._request("GET", "/v2/positions"))

    def list_orders(self, *, status: str = "open", limit: int = 100, symbols: list[str] | None = None) -> list[dict[str, Any]]:
        params = {"status": status, "direction": "desc", "limit": str(int(limit))}
        if symbols is not None:
            params["symbols"] = ",".join(symbols)
        return list(self._request("GET", "/v2/orders?" + urlencode(params)))

    def get_order(self, order_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v2/orders/{order_id}")

    def get_order_by_client_id(self, client_id: str) -> dict[str, Any] | None:
        try:
            return self._request("GET", "/v2/orders:by_client_order_id?" + urlencode({"client_order_id": client_id}))
        except AlpacaAPIError as exc:
            if exc.status_code == 404:
                return None
            raise

    def submit_market_sell_qty(self, symbol: str, qty: float, *, client_order_id: str) -> dict[str, Any]:
        return self._request("POST", "/v2/orders", {
            "symbol": symbol, "qty": _format_qty(qty), "side": "sell",
            "type": "market", "time_in_force": "day", "client_order_id": client_order_id,
        })

    def submit_market_buy(self, symbol: str, notional: float, *, client_order_id: str | None = None) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "notional": f"{notional:.2f}",
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
        }
        if client_order_id:
            payload["client_order_id"] = client_order_id
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

    def submit_stop_sell(self, symbol: str, *, qty: float, stop_price: float, time_in_force: str = "day", client_order_id: str | None = None) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "qty": _format_qty(qty),
            "side": "sell",
            "type": "stop",
            "time_in_force": time_in_force,
            "stop_price": _format_price(stop_price),
        }
        if client_order_id:
            payload["client_order_id"] = client_order_id
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

    def replace_order(self, order_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Atomically replace an open Alpaca order.

        Protective-exit tooling uses this instead of cancel-then-submit so a
        live position is never deliberately left without broker protection.
        """
        return self._request("PATCH", f"/v2/orders/{order_id}", payload)


_PAPER_API_URL = "https://paper-api.alpaca.markets"
_PAPER_KILL_REASONS = {
    "owner_kill", "restart_state_mismatch", "unprotected_after_reconcile", "missed_full_session",
}
_ACTIVE_ORDER_STATUSES = {"accepted", "new", "pending_new", "partially_filled", "accepted_for_bidding", "pending_replace"}
_TERMINAL_ORDER_STATUSES = {"canceled", "expired", "filled", "rejected", "replaced", "stopped"}


class PaperKillValidationError(RuntimeError):
    pass


def _paper_kill_number(value: Any, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PaperKillValidationError(f"invalid_{field}") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise PaperKillValidationError(f"invalid_{field}")
    return parsed


def _paper_kill_state_path(state_dir: Path) -> Path:
    return state_dir / ".paper-entry-halt.json"


def _paper_kill_state_dir(base_url: str, key_id: str) -> Path:
    """Keep a kill halt account-scoped, rather than sharing the locks directory."""
    return _alpaca_account_lock_path(base_url, key_id).with_suffix(".paper-kill")


def paper_entry_halted(*, base_url: str, state_dir: Path) -> bool:
    """Suppress intended PAPER or explicitly enabled intended LIVE entries after a durable halt."""
    intended_live = base_url == "https://api.alpaca.markets" and _env_bool("ALPACA_INTENDED_LIVE", False)
    if base_url != _PAPER_API_URL and not intended_live:
        return False
    try:
        state = json.loads(_paper_kill_state_path(state_dir).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False
    except Exception:
        return True
    if not isinstance(state, dict) or not isinstance(state.get("halted"), bool):
        return True
    return state["halted"]


def _validated_paper_kill_scope(
    *, proof: Any, client: Any, base_url: str, intended_live: bool = False
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if intended_live:
        if base_url != "https://api.alpaca.markets":
            raise PaperKillValidationError("intended_live_kill_requires_exact_live_endpoint")
    elif base_url != _PAPER_API_URL:
        raise PaperKillValidationError("paper_kill_requires_exact_paper_endpoint")
    if not isinstance(proof, dict) or str(proof.get("reason") or "") not in _PAPER_KILL_REASONS:
        raise PaperKillValidationError("invalid_paper_kill_proof_reason")
    account = client.get_account()
    account_id = str(account.get("id") or "").strip()
    if intended_live:
        try:
            _load_intended_live_binding(
                base_url=base_url, account_id=account_id, require_enabled=True
            )
        except IntendedPaperProtectionError as exc:
            raise PaperKillValidationError(f"intended_live_kill_binding_invalid:{exc}") from exc
    if not account_id or account_id != str(proof.get("account_id") or "").strip():
        raise PaperKillValidationError("paper_kill_account_mismatch")
    proof_rows = proof.get("positions")
    if not isinstance(proof_rows, list) or not proof_rows:
        raise PaperKillValidationError("invalid_paper_kill_positions")
    scope: dict[str, dict[str, Any]] = {}
    for row in proof_rows:
        if not isinstance(row, dict):
            raise PaperKillValidationError("invalid_paper_kill_position")
        symbol = str(row.get("symbol") or "").strip().upper()
        entry_id = str(row.get("entry_order_id") or "").strip()
        if not symbol or not entry_id or symbol in scope:
            raise PaperKillValidationError("invalid_or_duplicate_paper_kill_position")
        scope[symbol] = {
            "entry_order_id": entry_id,
            "qty": _paper_kill_number(row.get("qty"), "proof_qty"),
            "avg_entry_price": _paper_kill_number(row.get("avg_entry_price"), "proof_avg_entry_price"),
        }
    positions = client.list_positions()
    orders = client.list_orders(status="all", limit=500, symbols=sorted(scope))
    if len(orders) >= 500:
        raise PaperKillValidationError("paper_kill_orders_incomplete")
    current = {str(p.get("symbol") or "").strip().upper(): p for p in positions if isinstance(p, dict)}
    for symbol, expected in scope.items():
        buys = [o for o in orders if isinstance(o, dict) and str(o.get("symbol") or "").strip().upper() == symbol and str(o.get("side") or "").lower() == "buy" and str(o.get("status") or "").lower() in {"filled", "canceled", "expired"} and _safe_float(o.get("filled_qty"), 0.0) > 0]
        if not buys or str(buys[0].get("id") or "").strip() != expected["entry_order_id"]:
            raise PaperKillValidationError(f"paper_kill_latest_buy_mismatch:{symbol}")
        entry = buys[0]
        if _paper_kill_number(entry.get("filled_qty"), "entry_filled_qty") != expected["qty"] or _paper_kill_number(entry.get("filled_avg_price"), "entry_filled_avg_price") != expected["avg_entry_price"]:
            raise PaperKillValidationError(f"paper_kill_entry_fill_mismatch:{symbol}")
        pos = current.get(symbol)
        if pos is None:
            continue
        qty = _paper_kill_number(pos.get("qty"), "current_qty")
        avg = _paper_kill_number(pos.get("avg_entry_price"), "current_avg_entry_price")
        if str(pos.get("side") or "long").strip().lower() == "short" or qty > expected["qty"] or avg != expected["avg_entry_price"]:
            raise PaperKillValidationError(f"paper_kill_position_mismatch:{symbol}")
    return scope, positions, orders


def run_paper_owned_kill(
    *, proof: Any, client: Any, base_url: str, apply: bool, state_dir: Path,
    intended_live: bool = False,
) -> dict[str, Any]:
    """Validate an explicit paper-owned proof before any scoped exit action."""
    scope, positions, orders = _validated_paper_kill_scope(
        proof=proof, client=client, base_url=base_url, intended_live=intended_live
    )
    current_symbols = {str(p.get("symbol") or "").strip().upper() for p in positions if isinstance(p, dict)}
    present = sorted(set(scope) & current_symbols)
    receipt: dict[str, Any] = {"status": "dry_run_not_confirmed", "generated_at_utc": datetime.now(timezone.utc).isoformat(), "reason": str(proof["reason"]), "scope_symbols": sorted(scope), "present_symbols": present, "plan": [{"symbol": s, "action": "close_owned_position"} for s in present], "order_results": []}
    if not apply:
        return receipt
    if _env("ALPACA_SEND_ORDERS") != "1" or _env("ALPACA_ALLOW_NEW_ENTRIES", "1") != "0":
        raise PaperKillValidationError("paper_kill_apply_guard_not_satisfied")
    if intended_live:
        if _env("ALPACA_INTENDED_LIVE_KILL_ACK") != "INTENDED_OWNED_EXITS_ONLY":
            raise PaperKillValidationError("intended_live_kill_ack_not_satisfied")
    elif _env("ALPACA_PAPER_KILL_ACK") != "PAPER_OWNED_EXITS_ONLY":
        raise PaperKillValidationError("paper_kill_apply_guard_not_satisfied")
    _atomic_write_json(_paper_kill_state_path(state_dir), {"halted": True, "account_id": str(proof["account_id"]), "reason": str(proof["reason"]), "updated_at_utc": datetime.now(timezone.utc).isoformat()})
    clock = client.get_clock()
    if not bool(clock.get("is_open")):
        receipt["status"] = "awaiting_regular_session"
        receipt["next_open"] = clock.get("next_open")
        return receipt
    pending_market_close = {
        str(o.get("symbol") or "").strip().upper()
        for o in orders
        if isinstance(o, dict)
        and str(o.get("symbol") or "").strip().upper() in scope
        and str(o.get("side") or "").lower() == "sell"
        and str(o.get("type") or "").lower() == "market"
        and str(o.get("status") or "").lower() in _ACTIVE_ORDER_STATUSES
    }
    if pending_market_close:
        receipt["status"] = "not_confirmed_pending_close"
        receipt["pending_symbols"] = sorted(pending_market_close)
        return receipt
    active_buys = [o for o in orders if isinstance(o, dict) and str(o.get("symbol") or "").strip().upper() in scope and str(o.get("status") or "").lower() in _ACTIVE_ORDER_STATUSES and str(o.get("side") or "").lower() == "buy"]
    if active_buys:
        raise PaperKillValidationError("paper_kill_unproven_active_buy")
    absent_with_active_order = {
        str(o.get("symbol") or "").strip().upper()
        for o in orders if isinstance(o, dict) and str(o.get("symbol") or "").strip().upper() in scope
        and str(o.get("symbol") or "").strip().upper() not in current_symbols
        and str(o.get("status") or "").lower() in _ACTIVE_ORDER_STATUSES
    }
    if absent_with_active_order:
        raise PaperKillValidationError("paper_kill_active_order_without_position")
    active = [o for o in orders if isinstance(o, dict) and str(o.get("symbol") or "").strip().upper() in scope and str(o.get("status") or "").lower() in _ACTIVE_ORDER_STATUSES]
    for order in active:
        order_id = str(order.get("id") or "").strip()
        if not order_id:
            raise PaperKillValidationError("paper_kill_active_order_missing_id")
        cancelled = client.cancel_order(order_id)
        confirmed = client.get_order(order_id)
        receipt["order_results"].append({"order_id": order_id, "cancel_status": cancelled.get("status"), "confirmed_status": confirmed.get("status")})
        if str(confirmed.get("status") or "").lower() not in _TERMINAL_ORDER_STATUSES:
            raise PaperKillValidationError(f"paper_kill_cancel_not_terminal:{order_id}")
    _, refreshed_positions, refreshed_orders = _validated_paper_kill_scope(
        proof=proof, client=client, base_url=base_url, intended_live=intended_live
    )
    refreshed_symbols = {str(p.get("symbol") or "").strip().upper() for p in refreshed_positions if isinstance(p, dict)}
    pending = {str(o.get("symbol") or "").strip().upper() for o in refreshed_orders if isinstance(o, dict) and str(o.get("symbol") or "").strip().upper() in scope and str(o.get("status") or "").lower() in _ACTIVE_ORDER_STATUSES and str(o.get("side") or "").lower() in {"buy", "sell"}}
    if pending:
        receipt["status"] = "not_confirmed_pending_close"
        receipt["pending_symbols"] = sorted(pending)
        return receipt
    for symbol in sorted(set(scope) & refreshed_symbols):
        close = client.close_position(symbol)
        receipt["order_results"].append({"symbol": symbol, "close_order_id": close.get("id"), "close_status": close.get("status")})
    _, final_positions, final_orders = _validated_paper_kill_scope(
        proof=proof, client=client, base_url=base_url, intended_live=intended_live
    )
    final_symbols = {str(p.get("symbol") or "").strip().upper() for p in final_positions if isinstance(p, dict)}
    final_active = {str(o.get("symbol") or "").strip().upper() for o in final_orders if isinstance(o, dict) and str(o.get("symbol") or "").strip().upper() in scope and str(o.get("status") or "").lower() in _ACTIVE_ORDER_STATUSES}
    receipt["status"] = "confirmed_flat" if not (set(scope) & final_symbols) and not final_active else "not_confirmed"
    receipt["remaining_symbols"] = sorted(set(scope) & final_symbols)
    return receipt


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


def _load_intraday_managed_symbols(*, strict: bool = False) -> set[str]:
    symbols: set[str] = set()
    raw = _env("ALPACA_INTRADAY_STATE_PATH", "")
    state_path = Path(raw) if raw else (Path(__file__).resolve().parent.parent / "configs" / "intraday_state.json")
    if state_path.exists():
        try:
            data = json.loads(state_path.read_text())
        except Exception as exc:
            if strict:
                raise RuntimeError(
                    f"intraday ownership state is unreadable; refusing monthly cleanup: {state_path}"
                ) from exc
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
    payload = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(payload, dict):
        raise ValueError("reentry_state_corrupt")
    payload["symbols"] = dict(sorted(state.items()))
    _atomic_write_json(path, payload)


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


def _reconcile_intended_stop_exits(
    *, client: Any, state: dict[str, Any], state_path: Path, reentry_path: Path,
    positions: dict[str, Any], open_orders: list[dict[str, Any]],
    account_id: str, state_dir: Path, now: datetime | None = None,
) -> set[str]:
    """Persist a confirmed stop's calendar lock before retiring its lifecycle."""
    now = now or datetime.now(timezone.utc)
    try:
        raw = json.loads(reentry_path.read_text(encoding="utf-8")) if reentry_path.exists() else {"symbols": {}}
        if not isinstance(raw, dict) or not isinstance(raw.get("symbols"), dict):
            raise IntendedPaperProtectionError("reentry_state_corrupt")
        blocks = raw["symbols"]
        for symbol, row in blocks.items():
            if (not isinstance(row, dict) or symbol != symbol.upper()
                or _parse_iso_utc(str(row.get("blocked_until") or "")) is None):
                raise IntendedPaperProtectionError("reentry_state_corrupt")
        if len(open_orders) >= 100:
            raise IntendedPaperProtectionError("intended_orders_snapshot_incomplete")
        removed: set[str] = set()
        for symbol, record in list(state.items()):
            _validated_existing_intended_lifecycle(record, account_id)
            if record.get("rotation_intent"):
                continue  # Reconciled by the same-cycle market-exit path.
            if symbol in positions:
                continue
            order_id = str(record.get("accepted_order_id") or "").strip()
            order = client.get_order(order_id) if order_id else None
            if (not isinstance(order, dict)
                or str(order.get("id") or "") != order_id
                or str(order.get("symbol") or "").upper() != symbol
                or str(order.get("side") or "").lower() != "sell"
                or str(order.get("type") or "").lower() != "stop"
                or str(order.get("status") or "").lower() != "filled"):
                raise IntendedPaperProtectionError(f"intended_stop_exit_not_confirmed:{symbol}")
            qty = _intended_finite_positive(order.get("filled_qty"))
            avg = _intended_finite_positive(order.get("filled_avg_price"))
            exit_at = str(order.get("filled_at") or "").strip()
            entry_at = _parse_iso_utc(str(record.get("lifecycle_first_seen_at_utc") or ""))
            exit_dt = _parse_iso_utc(exit_at)
            if (qty is None or avg is None or exit_dt is None or entry_at is None
                or exit_dt < entry_at or exit_dt > now + timedelta(seconds=5)
                or qty + max(1e-9, float(record["qty"]) * 1e-6) < float(record["qty"])):
                raise IntendedPaperProtectionError(f"intended_stop_exit_invalid:{symbol}")
            if any(str(o.get("symbol") or "").upper() == symbol
                   and str(o.get("status") or "").lower() in _ACTIVE_ORDER_STATUSES
                   for o in open_orders):
                raise IntendedPaperProtectionError(f"intended_stop_exit_active_conflict:{symbol}")
            # Refresh after the order readback so an old flat snapshot cannot retire a new position.
            if any(str(pos.get("symbol") or "").upper() == symbol for pos in client.list_positions()):
                raise IntendedPaperProtectionError(f"intended_stop_exit_not_flat:{symbol}")
            expected = {
                "reason": "confirmed_intended_stop_exit", "created_at": exit_at,
                "blocked_until": (exit_dt + timedelta(days=21)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "entry_order_id": record["entry_order_id"], "account_id": account_id,
                "exit_order_id": order_id, "exit_qty": qty,
                "exit_avg_price": avg, "exit_filled_at": exit_at,
            }
            previous = blocks.get(symbol, {})
            if previous.get("exit_order_id") == order_id and previous != expected:
                raise IntendedPaperProtectionError(f"intended_stop_exit_receipt_mismatch:{symbol}")
            blocks[symbol] = expected
            _save_reentry_block_state(reentry_path, blocks)
            next_state = {key: row for key, row in state.items() if key != symbol}
            _atomic_write_json(state_path, next_state)
            state.pop(symbol)
            removed.add(symbol)
        return removed
    except Exception as exc:
        _halt_intended_paper_entries(state_dir, account_id, str(exc))
        raise


def _rotate_intended_monthly(
    *, client: Any, base_url: str, account_id: str, capital: float,
    state_path: Path, reentry_path: Path, selected_symbols: set[str],
    entry_session: str, now: datetime | None = None,
) -> dict[str, Any]:
    """Under the account writer lock, settle owned month-turn exits before buys."""
    from zoneinfo import ZoneInfo
    now = now or datetime.now(timezone.utc)
    if not _intended_lifecycle_enabled(base_url, account_id=account_id, capital=capital, require_enabled=True):
        raise IntendedPaperProtectionError("rotation_requires_intended_mode")
    if str(client.get_account().get("id") or "") != account_id:
        raise IntendedPaperProtectionError("rotation_account_mismatch")
    clock = client.get_clock()
    session = datetime.fromisoformat(str(clock["timestamp"]).replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York")).date()
    cycle = date.fromisoformat(entry_session)
    if not clock.get("is_open") or session < cycle:
        return {"status": "PENDING", "reason": "awaiting_entry_session"}
    state, state_error = _load_protective_floor_state(state_path)
    if state_error not in {"", "state_missing"}:
        raise IntendedPaperProtectionError("rotation_state_corrupt")
    raw = json.loads(reentry_path.read_text()) if reentry_path.exists() else {"symbols": {}}
    if not isinstance(raw, dict) or not isinstance(raw.get("symbols"), dict) or not isinstance(raw.get("rotation_exits", {}), dict):
        raise IntendedPaperProtectionError("rotation_receipts_corrupt")
    completed = []
    for symbol, record in list(state.items()):
        _validated_existing_intended_lifecycle(record, account_id)
        intent = record.get("rotation_intent")
        if symbol in selected_symbols and not intent:
            continue
        entry = client.get_order(str(record["entry_order_id"]))
        if (str(entry.get("id")) != record["entry_order_id"] or entry.get("symbol") != symbol
            or entry.get("side") != "buy" or entry.get("status") not in {"filled", "canceled", "expired"}
            or not math.isclose(_safe_float(entry.get("filled_avg_price")), float(record["entry_price"]), rel_tol=1e-9)
            or not math.isclose(_safe_float(entry.get("filled_qty")), float(record.get("entry_fill_qty", record["qty"])), rel_tol=1e-9)):
            raise IntendedPaperProtectionError(f"rotation_entry_identity_mismatch:{symbol}")
        identity = hashlib.sha256(f"{account_id}|{_INTENDED_PAPER_STRATEGY_ID}|{record['entry_order_id']}|{entry_session}|{symbol}".encode()).hexdigest()[:32]
        expected = {"entry_session": entry_session, "client_order_id": "alp-rotate-" + identity, "qty": record["qty"]}
        if intent is not None and intent != expected:
            raise IntendedPaperProtectionError(f"rotation_intent_mismatch:{symbol}")
        existing = client.get_order_by_client_id(expected["client_order_id"])
        positions = {p["symbol"]: p for p in client.list_positions()}
        orders = client.list_orders(status="open", limit=100)
        if len(orders) >= 100:
            raise IntendedPaperProtectionError("rotation_orders_incomplete")
        owned_orders = [o for o in orders if o.get("symbol") == symbol]
        allowed_ids = {record.get("accepted_order_id"), (existing or {}).get("id")}
        if any(not o.get("id") or o["id"] not in allowed_ids for o in owned_orders):
            raise IntendedPaperProtectionError(f"rotation_unknown_order:{symbol}")
        if existing is None:
            pos = positions.get(symbol)
            if pos is None:
                # A stop can fill before/during cancellation. Let its exact receipt
                # create the 21-day lock; never replace it with a market exit.
                record.pop("rotation_intent", None)
                _atomic_write_json(state_path, state)
                _reconcile_intended_stop_exits(client=client, state=state, state_path=state_path,
                    reentry_path=reentry_path, positions=positions, open_orders=orders,
                    account_id=account_id, state_dir=_paper_kill_state_dir(base_url, _env("ALPACA_API_KEY_ID")), now=now)
                continue
            if (pos.get("side", "long") != "long"
                or not math.isclose(_safe_float(pos.get("qty")), float(record["qty"]), rel_tol=1e-9)
                or not math.isclose(_safe_float(pos.get("avg_entry_price")), float(record["entry_price"]), rel_tol=1e-9)):
                raise IntendedPaperProtectionError(f"rotation_position_mismatch:{symbol}")
            if session != cycle:
                raise IntendedPaperProtectionError(f"rotation_missed_entry_session:{symbol}")
            if not intent:
                record["rotation_intent"] = expected
                _atomic_write_json(state_path, state)  # fsync before cancel/submit
            stop_id = str(record.get("accepted_order_id") or "")
            stop = client.get_order(stop_id)
            if (stop.get("symbol") != symbol or stop.get("side") != "sell" or stop.get("type") != "stop"):
                raise IntendedPaperProtectionError(f"rotation_stop_identity_mismatch:{symbol}")
            if stop.get("status") not in _TERMINAL_ORDER_STATUSES:
                client.cancel_order(stop_id)
                stop = client.get_order(stop_id)
            if stop.get("status") not in _TERMINAL_ORDER_STATUSES:
                return {"status": "PENDING", "reason": "stop_cancel_pending", "symbol": symbol}
            if _safe_float(stop.get("filled_qty")) > 0:
                record.pop("rotation_intent", None)
                _atomic_write_json(state_path, state)
                return {"status": "PENDING", "reason": "stop_fill_requires_reconciliation", "symbol": symbol}
            fresh = next((p for p in client.list_positions() if p.get("symbol") == symbol), None)
            if fresh is None or not math.isclose(_safe_float(fresh.get("qty")), float(record["qty"]), rel_tol=1e-9):
                raise IntendedPaperProtectionError(f"rotation_position_changed_after_cancel:{symbol}")
            # Recheck exact LIVE approval immediately before the broker write.
            _intended_lifecycle_enabled(base_url, account_id=account_id, capital=capital, require_enabled=True)
            existing = client.submit_market_sell_qty(symbol, float(record["qty"]), client_order_id=expected["client_order_id"])
        if (existing.get("client_order_id") != expected["client_order_id"] or existing.get("symbol") != symbol
            or existing.get("side") != "sell" or existing.get("type") != "market" or not existing.get("id")
            or not math.isclose(_safe_float(existing.get("qty")), float(record["qty"]), rel_tol=1e-9)):
            raise IntendedPaperProtectionError(f"rotation_exit_identity_mismatch:{symbol}")
        if existing.get("status") in _ACTIVE_ORDER_STATUSES:
            return {"status": "PENDING", "reason": "market_exit_pending", "symbol": symbol}
        filled_at = _parse_iso_utc(str(existing.get("filled_at") or ""))
        if (existing.get("status") != "filled" or filled_at is None or filled_at > now + timedelta(seconds=5)
            or filled_at < _parse_iso_utc(record["lifecycle_first_seen_at_utc"])
            or not math.isclose(_safe_float(existing.get("filled_qty")), float(record["qty"]), rel_tol=1e-9)
            or _intended_finite_positive(existing.get("filled_avg_price")) is None):
            raise IntendedPaperProtectionError(f"rotation_exit_not_confirmed:{symbol}")
        if any(p.get("symbol") == symbol for p in client.list_positions()):
            return {"status": "PENDING", "reason": "awaiting_flat_truth", "symbol": symbol}
        fresh_orders = client.list_orders(status="open", limit=100)
        if len(fresh_orders) >= 100 or any(o.get("symbol") == symbol for o in fresh_orders):
            raise IntendedPaperProtectionError(f"rotation_flat_orders_not_confirmed:{symbol}")
        # Existing re-entry artifact retains exit receipts without adding a block.
        raw = json.loads(reentry_path.read_text()) if reentry_path.exists() else {"symbols": {}}
        exits = raw.setdefault("rotation_exits", {})
        receipt = {"entry_order_id": record["entry_order_id"], "account_id": account_id,
                   "symbol": symbol, "entry_session": entry_session, "exit_order": existing,
                   "retired_lifecycle": record}
        if identity in exits and exits[identity] != receipt:
            raise IntendedPaperProtectionError(f"rotation_receipt_mismatch:{symbol}")
        exits[identity] = receipt
        _atomic_write_json(reentry_path, raw)
        state.pop(symbol)
        _atomic_write_json(state_path, state)
        completed.append(symbol)
    return {"status": "COMPLETE", "closed_symbols": completed}


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


def _new_entry_allowed(symbol: str, *, enabled: bool, blocked_symbols: set[str]) -> bool:
    """Fail closed for preservation mode and same-cycle exit cooldowns."""
    return bool(enabled) and symbol.strip().upper() not in blocked_symbols


def _default_broker_protection_tif(order_class: str) -> str:
    """Return the broad default before exact broker quantity is known.

    ``_persistent_exit_tif_for_qty`` is the authoritative final policy:
    fractional equity exits must remain DAY while whole-share exits may use
    GTC.  A default alone must never decide the submitted TIF.
    """
    return "gtc" if order_class.strip().lower() == "simple_stop" else "day"


def _persistent_exit_tif_for_qty(configured_tif: str, qty: float) -> str:
    """Choose the strongest Alpaca TIF legal for the exact equity quantity.

    Alpaca accepts fractional equity stop orders only with DAY. Whole-share
    stop and trailing-stop orders can use GTC. The broker quantity therefore
    has authority over a stale or over-broad configuration value.
    """
    del configured_tif
    return "day" if _is_fractional_qty(qty) else "gtc"


def _alpaca_account_lock_path(base_url: str, key_id: str) -> Path:
    configured = _env("ALPACA_BRIDGE_LOCK_PATH", "")
    if configured:
        return Path(configured)
    identity = f"{base_url}|{key_id}"
    digest = hashlib.sha256(identity.encode("utf-8", errors="replace")).hexdigest()[:16]
    return (
        Path(__file__).resolve().parent.parent
        / "runtime"
        / "locks"
        / f"alpaca_bridge_{digest}.lock"
    )


def _acquire_account_writer_lock(fd: int, wait_seconds: float) -> bool:
    """Acquire the shared broker-writer lock with a bounded retry window."""
    deadline = time.monotonic() + max(0.0, float(wait_seconds))
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.25, remaining))


def _protective_exit_hwm_state_path() -> Path:
    raw = _env("ALPACA_PROTECTIVE_EXIT_HWM_PATH", "")
    if raw:
        return Path(raw)
    runtime_raw = _env("ALPACA_PROTECTIVE_EXIT_RUNTIME_DIR", "")
    runtime_dir = (
        Path(runtime_raw)
        if runtime_raw
        else Path(__file__).resolve().parent.parent / "runtime" / "alpaca_live_v38"
    )
    return runtime_dir / "protective_exit_hwm.json"


def _load_protective_floor_state(path: Path) -> tuple[dict[str, Any], str]:
    """Load the broker-accepted floor ledger without hiding corruption."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, "state_missing"
    except Exception as exc:
        return {}, f"state_read_error:{type(exc).__name__}"
    try:
        payload = json.loads(raw)
    except Exception as exc:
        return {}, f"state_json_error:{type(exc).__name__}"
    if not isinstance(payload, dict):
        return {}, "state_root_not_object"
    return payload, ""


def _matching_protective_floor_record(
    symbol: str,
    position: dict[str, Any],
    hwm_state: dict[str, Any],
) -> dict[str, Any]:
    """Return a broker-accepted floor bound to the current SAFE_HOLD lifecycle."""
    record = hwm_state.get(str(symbol).strip().upper())
    if not isinstance(record, dict):
        return {}
    position_entry = _safe_float(position.get("avg_entry_price"), 0.0)
    record_entry = _safe_float(record.get("entry_price"), 0.0)
    first_seen = str(record.get("lifecycle_first_seen_at_utc") or "").strip()
    accepted_floor = _safe_float(record.get("accepted_stop_floor"), 0.0)
    if position_entry <= 0 or record_entry <= 0 or not first_seen or accepted_floor <= 0:
        return {}
    entry_tolerance = max(0.01, position_entry * 1e-4)
    if abs(record_entry - position_entry) > entry_tolerance:
        return {}
    return record


def _accepted_floor_preflight_violations(
    *,
    positions: Iterable[dict[str, Any]],
    intraday_managed_symbols: Iterable[str],
    protective_floor_state: dict[str, Any],
    state_error: str,
) -> list[dict[str, Any]]:
    """Block all mutations when an existing lifecycle has no trusted floor."""
    intraday = {
        str(symbol).strip().upper()
        for symbol in intraday_managed_symbols
        if str(symbol).strip()
    }
    managed_positions = [
        dict(raw or {})
        for raw in positions
        if str((raw or {}).get("symbol") or "").strip().upper() not in intraday
        and str((raw or {}).get("symbol") or "").strip()
    ]
    if not managed_positions:
        return []
    if state_error:
        return [
            {
                "symbol": "*",
                "reason": "protective_floor_state_not_authoritative",
                "state_error": state_error,
            }
        ]
    violations: list[dict[str, Any]] = []
    for position in managed_positions:
        symbol = str(position.get("symbol") or "").strip().upper()
        if not _matching_protective_floor_record(
            symbol,
            position,
            protective_floor_state,
        ):
            violations.append(
                {
                    "symbol": symbol,
                    "reason": "existing_lifecycle_floor_not_reconciled",
                }
            )
    return violations


def _protected_rearm_stop_price(
    symbol: str,
    plan_stop_price: float,
    position: dict[str, Any],
    existing_stops: Iterable[dict[str, Any]],
    hwm_state: dict[str, Any],
) -> float:
    """Never re-arm below a broker-observed/confirmed lifecycle floor."""
    candidates = [max(0.0, _safe_float(plan_stop_price, 0.0))]
    candidates.extend(
        max(0.0, _safe_float(order.get("stop_price"), 0.0))
        for order in existing_stops
        if isinstance(order, dict)
        and str(order.get("type") or order.get("order_type") or "stop").lower()
        in {"stop", "stop_limit"}
    )
    record = _matching_protective_floor_record(symbol, position, hwm_state)
    candidates.append(max(0.0, _safe_float(record.get("accepted_stop_floor"), 0.0)))
    return max(candidates)


def _rearm_intended_position(
    *, client: Any, symbol: str, position: dict[str, Any],
    existing_stops: list[dict[str, Any]], state: dict[str, Any],
    state_path: Path, account_id: str,
) -> dict[str, Any]:
    record = _validated_existing_intended_lifecycle(state.get(symbol), account_id)
    qty = _intended_finite_positive(position.get("qty"))
    entry = _intended_finite_positive(position.get("avg_entry_price"))
    current = _intended_finite_positive(position.get("current_price"))
    if (qty is None or entry is None or current is None
        or abs(entry - float(record["entry_price"])) > max(1e-8, entry * 1e-6)
        or qty > float(record["qty"]) + max(1e-9, float(record["qty"]) * 1e-6)
        or str(position.get("side") or "long").lower() != "long"):
        raise IntendedPaperProtectionError(f"intended_rearm_position_mismatch:{symbol}")
    floor = float(record["accepted_stop_floor"])
    if len(existing_stops) > 1:
        raise IntendedPaperProtectionError(f"intended_rearm_multiple_stops:{symbol}")
    if existing_stops:
        order = existing_stops[0]
    else:
        if current <= floor:
            raise IntendedPaperProtectionError(f"intended_rearm_price_below_floor:{symbol}")
        order = client.submit_stop_sell(symbol, qty=qty, stop_price=floor,
                                       time_in_force=_persistent_exit_tif_for_qty("", qty))
    confirmed = _confirmed_intended_stop(client, order, symbol=symbol, qty=qty, requested_stop=floor)
    updated = {**record, "qty": qty, "hwm": max(float(record["hwm"]), current),
               "accepted_order_id": confirmed["id"],
               "accepted_order_tif": confirmed["time_in_force"],
               "accepted_stop_floor": max(floor, float(confirmed["stop_price"]))}
    next_state = {**state, symbol: updated}
    _atomic_write_json(state_path, next_state)
    state[symbol] = updated
    return confirmed


def _single_covering_stop_needing_update(
    existing_stops: list[dict[str, Any]],
    position_qty: float,
    required_tif: str,
    target_stop_price: float,
) -> dict[str, Any] | None:
    """Find one covering stop whose TIF or locked price needs an atomic raise."""
    if len(existing_stops) != 1 or position_qty <= 0:
        return None
    tolerance = max(1e-9, position_qty * 1e-6)
    if abs(_protected_stop_qty(existing_stops) - position_qty) > tolerance:
        return None
    order = existing_stops[0]
    order_type = str(order.get("type") or order.get("order_type") or "").strip().lower()
    if order_type not in {"stop", "stop_limit"}:
        return None
    current_tif = str(order.get("time_in_force") or "").strip().lower()
    current_stop = _safe_float(order.get("stop_price"), 0.0)
    formatted_target = _safe_float(_format_price(target_stop_price), 0.0)
    needs_tif = current_tif != str(required_tif).strip().lower()
    needs_raise = formatted_target > current_stop + 1e-12
    return order if needs_tif or needs_raise else None


def _save_hwm_state(path: Path, state: dict[str, dict[str, Any]]) -> None:
    _atomic_write_json(path, state)


class IntendedPaperProtectionError(RuntimeError):
    """An intended-paper entry cannot be proven terminal and protected."""


_INTENDED_PAPER_STRATEGY_ID = "ALPACA-BASELINE-26f7ff663dc98e87"


def _load_intended_live_binding(
    *,
    base_url: str,
    account_id: str | None = None,
    capital: float | None = None,
    require_enabled: bool = False,
) -> dict[str, Any]:
    """Load the explicit binding required for an intended LIVE sleeve."""
    if str(base_url).rstrip("/") != "https://api.alpaca.markets":
        raise IntendedPaperProtectionError("intended_live_binding_requires_exact_live_endpoint")
    raw_path = _env("ALPACA_INTENDED_LIVE_BINDING_PATH")
    if not raw_path:
        raise IntendedPaperProtectionError("intended_live_binding_path_missing")
    try:
        binding = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntendedPaperProtectionError("intended_live_binding_unreadable") from exc
    if not isinstance(binding, dict):
        raise IntendedPaperProtectionError("intended_live_binding_not_object")
    if type(binding.get("schema_version")) is not int or binding["schema_version"] != 1:
        raise IntendedPaperProtectionError("intended_live_binding_schema_version_invalid")
    if binding.get("endpoint") != "https://api.alpaca.markets":
        raise IntendedPaperProtectionError("intended_live_binding_endpoint_invalid")
    if str(binding.get("strategy_id") or "") != _INTENDED_PAPER_STRATEGY_ID:
        raise IntendedPaperProtectionError("intended_live_binding_strategy_id_invalid")
    configured_account = binding.get("account_id")
    if not isinstance(configured_account, str) or not configured_account.strip():
        raise IntendedPaperProtectionError("intended_live_binding_account_id_missing")
    configured_account_id = configured_account.strip()
    enabled = binding.get("enabled")
    if not isinstance(enabled, bool):
        raise IntendedPaperProtectionError("intended_live_binding_enabled_invalid")

    for field, expected in (("max_positions", 4), ("gross_exposure", 0.70), ("maximum_weight", 0.60)):
        value = binding.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) != expected:
            raise IntendedPaperProtectionError(f"intended_live_binding_{field}_invalid")

    if "capital_usd" not in binding:
        raise IntendedPaperProtectionError("intended_live_binding_capital_missing")
    configured_capital = binding["capital_usd"]
    if configured_capital is None:
        if enabled:
            raise IntendedPaperProtectionError("intended_live_binding_enabled_capital_missing")
    elif isinstance(configured_capital, bool) or not isinstance(configured_capital, (int, float)) or not math.isfinite(float(configured_capital)) or float(configured_capital) <= 0:
        raise IntendedPaperProtectionError("intended_live_binding_capital_invalid")

    if account_id is not None and str(account_id).strip() != configured_account_id:
        raise IntendedPaperProtectionError("intended_live_binding_account_id_mismatch")
    if capital is not None:
        if isinstance(capital, bool):
            raise IntendedPaperProtectionError("intended_live_binding_capital_mismatch")
        try:
            requested_capital = float(capital)
        except (TypeError, ValueError) as exc:
            raise IntendedPaperProtectionError("intended_live_binding_capital_mismatch") from exc
        if not math.isfinite(requested_capital):
            raise IntendedPaperProtectionError("intended_live_binding_capital_mismatch")
        if configured_capital is None:
            if enabled or requested_capital != 0:
                raise IntendedPaperProtectionError("intended_live_binding_capital_mismatch")
        elif requested_capital != float(configured_capital):
            raise IntendedPaperProtectionError("intended_live_binding_capital_mismatch")

    if require_enabled:
        if not enabled:
            raise IntendedPaperProtectionError("intended_live_binding_disabled")
        if configured_capital is None:
            raise IntendedPaperProtectionError("intended_live_binding_enabled_capital_missing")
        if _env("ALPACA_INTENDED_LIVE_ACK") != "INTENDED_LIVE_CANARY":
            raise IntendedPaperProtectionError("intended_live_binding_ack_missing")
        errors = _live_order_guard_errors(
            base_url=base_url,
            send_orders=True,
            capital_override_usd=float(configured_capital),
        )
        if errors:
            raise IntendedPaperProtectionError("intended_live_binding_live_guard_failed:" + "; ".join(errors))
    return binding


def _intended_lifecycle_enabled(
    base_url: str,
    *,
    require_enabled: bool = False,
    account_id: str | None = None,
    capital: float | None = None,
) -> bool:
    """Select the explicit intended PAPER or LIVE lifecycle mode, if any."""
    intended_paper = _env_bool("ALPACA_INTENDED_PAPER", False)
    intended_live = _env_bool("ALPACA_INTENDED_LIVE", False)
    if intended_paper and intended_live:
        raise IntendedPaperProtectionError("intended_lifecycle_modes_mutually_exclusive")
    if intended_paper:
        if base_url != _PAPER_API_URL:
            raise IntendedPaperProtectionError("intended_paper_requires_exact_paper_endpoint")
        return True
    if intended_live:
        _load_intended_live_binding(
            base_url=base_url,
            account_id=account_id,
            capital=capital,
            require_enabled=require_enabled,
        )
        return True
    return False


def _intended_finite_positive(value: Any) -> float | None:
    parsed = _safe_float(value, 0.0)
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _validated_existing_intended_lifecycle(record: Any, account_id: str, *, allow_pending: bool = False) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise IntendedPaperProtectionError("existing_lifecycle_corrupt")
    required = {
        "entry_order_id", "entry_price", "qty", "hwm", "accepted_stop_floor",
        "lifecycle_first_seen_at_utc", "account_id", "strategy_id",
    }
    if not required.issubset(record):
        raise IntendedPaperProtectionError("existing_lifecycle_corrupt")
    if not str(record.get("entry_order_id") or "").strip():
        raise IntendedPaperProtectionError("existing_lifecycle_corrupt")
    if str(record.get("account_id") or "").strip() != account_id:
        raise IntendedPaperProtectionError("existing_lifecycle_account_mismatch")
    if str(record.get("strategy_id") or "").strip() != _INTENDED_PAPER_STRATEGY_ID:
        raise IntendedPaperProtectionError("existing_lifecycle_strategy_mismatch")
    fields = ["entry_price", "qty", "hwm"]
    if not (allow_pending and record.get("protection_pending") is True and record.get("accepted_stop_floor") == 0):
        fields.append("accepted_stop_floor")
    if any(_intended_finite_positive(record.get(field)) is None for field in fields):
        raise IntendedPaperProtectionError("existing_lifecycle_nonfinite_or_nonpositive")
    if _parse_iso_utc(str(record.get("lifecycle_first_seen_at_utc") or "")) is None:
        raise IntendedPaperProtectionError("existing_lifecycle_invalid_timestamp")
    return record


def _persist_intended_pending_fill(path: Path, *, account_id: str, symbol: str, entry: dict[str, Any]) -> None:
    state, error = _load_protective_floor_state(path)
    if error not in {"", "state_missing"} or symbol in state:
        raise IntendedPaperProtectionError("pending_fill_state_conflict")
    qty = _intended_finite_positive(entry.get("filled_qty"))
    price = _intended_finite_positive(entry.get("filled_avg_price"))
    stamp = entry.get("filled_at") or entry.get("submitted_at") or entry.get("created_at")
    if not account_id or qty is None or price is None or not entry.get("id") or _parse_iso_utc(str(stamp or "")) is None:
        raise IntendedPaperProtectionError("pending_fill_invalid")
    state[symbol] = {"account_id": account_id, "strategy_id": _INTENDED_PAPER_STRATEGY_ID,
        "entry_order_id": entry["id"], "entry_price": price, "qty": qty, "entry_fill_qty": qty, "hwm": price,
        "accepted_stop_floor": 0, "lifecycle_first_seen_at_utc": stamp, "protection_pending": True}
    _atomic_write_json(path, state)


def _finish_intended_entry_intent(*, client: Any, base_url: str, account_id: str,
    capital: float, payload: dict[str, Any], client_id: str, entry: dict[str, Any],
    reentry_path: Path, state_path: Path, state_dir: Path, timeout_sec: float = 0) -> dict[str, Any]:
    """Recover only a reserved broker order; never infer ownership from a ticker."""
    intent = payload["entry_intents"][client_id]
    symbol = intent["symbol"]
    if (entry.get("client_order_id") != client_id or entry.get("symbol") != symbol
        or entry.get("side") != "buy" or entry.get("type") != "market"
        or entry.get("time_in_force") != "day"
        or not math.isclose(_safe_float(entry.get("notional")), intent["notional"], abs_tol=.000001)):
        raise IntendedPaperProtectionError("reserved_entry_order_mismatch")
    final = _terminal_intended_entry(client, entry, expected_symbol=symbol, timeout_sec=timeout_sec)
    qty, price = float(final["filled_qty"]), float(final["filled_avg_price"])
    positions = [p for p in client.list_positions() if p.get("symbol") == symbol]
    if (len(positions) != 1 or positions[0].get("side", "long") != "long"
        or not math.isclose(_safe_float(positions[0].get("qty")), qty, rel_tol=1e-9, abs_tol=1e-9)
        or not math.isclose(_safe_float(positions[0].get("avg_entry_price")), price, rel_tol=1e-9, abs_tol=1e-8)):
        raise IntendedPaperProtectionError("reserved_entry_position_mismatch")
    floor = price - float(intent["risk_distance"])
    if not math.isfinite(floor) or not 0 < floor < price:
        raise IntendedPaperProtectionError("reserved_entry_floor_invalid")
    state, error = _load_protective_floor_state(state_path)
    if error not in {"", "state_missing"}:
        raise IntendedPaperProtectionError("reserved_entry_state_corrupt")
    if symbol not in state:
        _persist_intended_pending_fill(state_path, account_id=account_id, symbol=symbol, entry=final)
    else:
        record = _validated_existing_intended_lifecycle(state[symbol], account_id, allow_pending=True)
        if record["entry_order_id"] != final["id"] or not math.isclose(float(record["qty"]), qty, rel_tol=1e-9):
            raise IntendedPaperProtectionError("reserved_entry_lifecycle_conflict")
        floor = max(floor, float(record["accepted_stop_floor"]))
    stop_id = client_id.replace("alp-entry-", "alp-floor-", 1)
    stop = client.get_order_by_client_id(stop_id)
    open_orders = client.list_orders(status="open", limit=100)
    if len(open_orders) >= 100 or any(o.get("symbol") == symbol and o.get("id") != (stop or {}).get("id") for o in open_orders):
        raise IntendedPaperProtectionError("reserved_entry_unknown_open_order")
    if stop is None:
        _intended_lifecycle_enabled(base_url, account_id=account_id, capital=capital, require_enabled=True)
        stop = client.submit_stop_sell(symbol, qty=qty, stop_price=floor,
            time_in_force=_persistent_exit_tif_for_qty("", qty), client_order_id=stop_id)
    if stop.get("client_order_id") != stop_id:
        raise IntendedPaperProtectionError("reserved_stop_identity_mismatch")
    record = _complete_intended_paper_simple_stop(client=client, base_url=base_url, state_dir=state_dir,
        ledger_path=state_path, account_id=account_id, entry_order=final, stop_order=stop,
        symbol=symbol, requested_stop=floor, intended_live=_env_bool("ALPACA_INTENDED_LIVE", False), capital=capital)
    intent.update(status="complete", entry_order_id=final["id"], stop_order_id=stop["id"])
    _atomic_write_json(reentry_path, payload)
    return record


def _submit_intended_reserved_entry(*, client: Any, base_url: str, account_id: str,
    capital: float, reentry_path: Path, state_path: Path, state_dir: Path,
    pick: Pick, notional: float, timeout_sec: float) -> dict[str, Any]:
    _intended_lifecycle_enabled(base_url, account_id=account_id, capital=capital, require_enabled=True)
    if client.get_account().get("id") != account_id:
        raise IntendedPaperProtectionError("reserved_entry_account_mismatch")
    distance = float(pick.entry_price) - float(pick.stop_price)
    if not math.isfinite(distance) or distance <= 0 or not math.isfinite(notional) or notional <= 0:
        raise IntendedPaperProtectionError("reserved_entry_parameters_invalid")
    client_id = "alp-entry-" + hashlib.sha256(f"{account_id}|{_INTENDED_PAPER_STRATEGY_ID}|{pick.entry_day}|{pick.ticker}".encode()).hexdigest()[:32]
    payload = json.loads(reentry_path.read_text()) if reentry_path.exists() else {"symbols": {}}
    intent = {"account_id": account_id, "strategy_id": _INTENDED_PAPER_STRATEGY_ID,
        "symbol": pick.ticker, "entry_session": pick.entry_day, "notional": notional,
        "risk_distance": distance, "status": "reserved"}
    entries = payload.setdefault("entry_intents", {})
    if client_id in entries:
        if entries[client_id].get("status") != "reserved":
            raise IntendedPaperProtectionError("entry_cycle_already_consumed")
        if entries[client_id] != intent:
            raise IntendedPaperProtectionError("reserved_entry_changed")
    else:
        if any(p.get("symbol") == pick.ticker for p in client.list_positions()):
            raise IntendedPaperProtectionError("reserved_entry_existing_position")
        entries[client_id] = intent
        _atomic_write_json(reentry_path, payload)
    entry = client.get_order_by_client_id(client_id)
    if entry is None:
        entry = client.submit_market_buy(pick.ticker, notional, client_order_id=client_id)
    return _finish_intended_entry_intent(client=client, base_url=base_url, account_id=account_id, capital=capital,
        payload=payload, client_id=client_id, entry=entry, reentry_path=reentry_path,
        state_path=state_path, state_dir=state_dir, timeout_sec=timeout_sec)


def _recover_intended_entry_intents(*, client: Any, base_url: str, account_id: str,
    capital: float, reentry_path: Path, state_path: Path, state_dir: Path) -> None:
    if not reentry_path.exists():
        return
    payload = json.loads(reentry_path.read_text())
    for client_id, intent in payload.get("entry_intents", {}).items():
        if intent.get("status") != "reserved":
            continue
        _intended_lifecycle_enabled(base_url, account_id=account_id, capital=capital, require_enabled=True)
        if intent.get("account_id") != account_id or intent.get("strategy_id") != _INTENDED_PAPER_STRATEGY_ID or client.get_account().get("id") != account_id:
            raise IntendedPaperProtectionError("reserved_entry_account_mismatch")
        entry = client.get_order_by_client_id(client_id)
        if entry is None:
            if any(p.get("symbol") == intent["symbol"] for p in client.list_positions()):
                raise IntendedPaperProtectionError("reserved_entry_unknown_position")
            # Crash before dispatch: consume the reservation, never create new
            # exposure in a recovery pass or retry a different session's entry.
            intent["status"] = "not_submitted"
            _atomic_write_json(reentry_path, payload)
            continue
        _finish_intended_entry_intent(client=client, base_url=base_url, account_id=account_id, capital=capital,
            payload=payload, client_id=client_id, entry=entry, reentry_path=reentry_path,
            state_path=state_path, state_dir=state_dir)


def _intended_frozen_weights(picks: Iterable[Pick]) -> dict[str, float]:
    """Validate frozen intended-paper sleeve weights without redistributing them."""
    weights: dict[str, float] = {}
    for pick in picks:
        symbol = str(pick.ticker or "").strip().upper()
        if not symbol:
            raise IntendedPaperProtectionError("intended_weight_missing_symbol")
        if symbol in weights:
            raise IntendedPaperProtectionError("intended_weight_duplicate_symbol")
        weight = pick.weight
        if weight is None or not math.isfinite(float(weight)) or not 0.0 < float(weight) <= 0.60:
            raise IntendedPaperProtectionError(f"intended_weight_invalid:{symbol}")
        weights[symbol] = float(weight)
    if sum(weights.values()) > 1.0 + 1e-9:
        raise IntendedPaperProtectionError("intended_weight_total_invalid")
    return weights


def _halt_intended_paper_entries(state_dir: Path, account_id: str, reason: str) -> None:
    _atomic_write_json(
        _paper_kill_state_path(state_dir),
        {
            "halted": True,
            "account_id": str(account_id),
            "reason": str(reason),
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )


def _validate_intended_entry_readback(
    confirmed: Any, *, order_id: str, expected_symbol: str
) -> dict[str, Any]:
    if not isinstance(confirmed, dict):
        raise IntendedPaperProtectionError("entry_readback_invalid")
    if str(confirmed.get("id") or "").strip() != order_id:
        raise IntendedPaperProtectionError("entry_id_mismatch")
    if str(confirmed.get("symbol") or "").strip().upper() != expected_symbol.strip().upper():
        raise IntendedPaperProtectionError("entry_symbol_mismatch")
    if str(confirmed.get("side") or "").strip().lower() != "buy":
        raise IntendedPaperProtectionError("entry_side_mismatch")
    return confirmed


def _terminal_intended_entry(
    client: Any,
    entry_order: dict[str, Any],
    *,
    expected_symbol: str,
    timeout_sec: float = 0.0,
) -> dict[str, Any]:
    """Cancel an active entry, then accept only a terminal broker readback."""
    order_id = str(entry_order.get("id") or "").strip()
    if not order_id:
        raise IntendedPaperProtectionError("entry_missing_order_id")
    try:
        confirmed = client.get_order(order_id)
    except Exception as exc:
        raise IntendedPaperProtectionError("entry_readback_failed") from exc
    confirmed = _validate_intended_entry_readback(
        confirmed, order_id=order_id, expected_symbol=expected_symbol
    )
    status = str(confirmed.get("status") or "").strip().lower()
    deadline = time.monotonic() + max(0.0, timeout_sec)
    while status in _ACTIVE_ORDER_STATUSES and time.monotonic() < deadline:
        time.sleep(max(0.0, min(0.25, deadline - time.monotonic())))
        try:
            confirmed = client.get_order(order_id)
        except Exception as exc:
            raise IntendedPaperProtectionError("entry_wait_readback_failed") from exc
        confirmed = _validate_intended_entry_readback(
            confirmed, order_id=order_id, expected_symbol=expected_symbol
        )
        status = str(confirmed.get("status") or "").strip().lower()
    if status in _ACTIVE_ORDER_STATUSES:
        try:
            client.cancel_order(order_id)
            confirmed = client.get_order(order_id)
        except Exception as exc:
            raise IntendedPaperProtectionError("entry_cancel_readback_failed") from exc
        confirmed = _validate_intended_entry_readback(
            confirmed, order_id=order_id, expected_symbol=expected_symbol
        )
        status = str(confirmed.get("status") or "").strip().lower()
    if status not in {"filled", "canceled", "expired"}:
        raise IntendedPaperProtectionError(f"entry_not_terminal:{status or 'unknown'}")
    qty = _intended_finite_positive(confirmed.get("filled_qty"))
    avg = _intended_finite_positive(confirmed.get("filled_avg_price"))
    if qty is None or avg is None:
        raise IntendedPaperProtectionError("entry_terminal_without_positive_fill")
    return confirmed


def _confirmed_intended_stop(
    client: Any,
    stop_order: dict[str, Any],
    *,
    symbol: str,
    qty: float,
    requested_stop: float,
) -> dict[str, Any]:
    """Require an exact fixed-stop broker readback before a success is recorded."""
    order_id = str(stop_order.get("id") or "").strip()
    if not order_id:
        raise IntendedPaperProtectionError("stop_missing_order_id")
    try:
        confirmed = client.get_order(order_id)
    except Exception as exc:
        raise IntendedPaperProtectionError("stop_readback_failed") from exc
    if not isinstance(confirmed, dict):
        raise IntendedPaperProtectionError("stop_readback_invalid")
    if str(confirmed.get("id") or "").strip() != order_id:
        raise IntendedPaperProtectionError("stop_id_mismatch")
    if str(confirmed.get("symbol") or "").strip().upper() != symbol.strip().upper():
        raise IntendedPaperProtectionError("stop_symbol_mismatch")
    if str(confirmed.get("side") or "").strip().lower() != "sell":
        raise IntendedPaperProtectionError("stop_side_mismatch")
    if str(confirmed.get("type") or confirmed.get("order_type") or "").strip().lower() != "stop":
        raise IntendedPaperProtectionError("stop_type_mismatch")
    if str(confirmed.get("status") or "").strip().lower() not in {"accepted", "new"}:
        raise IntendedPaperProtectionError("stop_not_accepted")
    order_qty = _intended_finite_positive(confirmed.get("qty"))
    filled_qty = _safe_float(confirmed.get("filled_qty"), 0.0)
    if order_qty is None or not math.isfinite(filled_qty) or filled_qty < 0:
        raise IntendedPaperProtectionError("stop_invalid_qty")
    if confirmed.get("leaves_qty") not in {None, ""}:
        leaves = _safe_float(confirmed.get("leaves_qty"), 0.0)
        if not math.isfinite(leaves) or leaves < 0:
            raise IntendedPaperProtectionError("stop_invalid_remaining_qty")
    remaining = _intended_finite_positive(_remaining_sell_order_qty(confirmed))
    if remaining is None:
        raise IntendedPaperProtectionError("stop_invalid_remaining_qty")
    tolerance = max(1e-9, qty * 1e-6)
    if abs(remaining - qty) > tolerance:
        raise IntendedPaperProtectionError("stop_remaining_qty_mismatch")
    expected_tif = _persistent_exit_tif_for_qty("", qty)
    if str(confirmed.get("time_in_force") or "").strip().lower() != expected_tif:
        raise IntendedPaperProtectionError("stop_tif_mismatch")
    requested_normalized = _intended_finite_positive(_format_price(requested_stop))
    confirmed_stop = _intended_finite_positive(confirmed.get("stop_price"))
    if requested_normalized is None or confirmed_stop is None:
        raise IntendedPaperProtectionError("stop_invalid_price")
    if confirmed_stop + 1e-12 < requested_normalized:
        raise IntendedPaperProtectionError("stop_below_requested_floor")
    return confirmed


def _complete_intended_paper_simple_stop(
    *,
    client: Any,
    base_url: str,
    state_dir: Path,
    ledger_path: Path,
    account_id: str,
    entry_order: dict[str, Any],
    stop_order: dict[str, Any],
    symbol: str,
    requested_stop: float,
    intended_live: bool = False,
    capital: float | None = None,
) -> dict[str, Any]:
    """Bind a terminal intended-paper fill to its broker-confirmed fixed floor."""
    if intended_live:
        _load_intended_live_binding(
            base_url=base_url,
            account_id=account_id,
            capital=capital,
            require_enabled=True,
        )
    elif base_url != _PAPER_API_URL:
        raise IntendedPaperProtectionError("intended_paper_requires_exact_paper_endpoint")
    account_id = str(account_id or "").strip()
    if not account_id:
        raise IntendedPaperProtectionError("intended_paper_missing_account_id")
    sym = str(symbol or "").strip().upper()
    if not sym:
        raise IntendedPaperProtectionError("intended_paper_missing_symbol")
    try:
        entry = _terminal_intended_entry(client, entry_order, expected_symbol=sym)
        qty = _intended_finite_positive(entry.get("filled_qty"))
        entry_price = _intended_finite_positive(entry.get("filled_avg_price"))
        if qty is None or entry_price is None:
            raise IntendedPaperProtectionError("entry_terminal_without_positive_fill")
        stop = _confirmed_intended_stop(
            client, stop_order, symbol=sym, qty=qty, requested_stop=requested_stop
        )
        first_seen = next(
            (str(entry.get(field) or "").strip()
             for field in ("filled_at", "submitted_at", "created_at")
             if str(entry.get(field) or "").strip()),
            "",
        )
        if not first_seen:
            raise IntendedPaperProtectionError("entry_missing_broker_lifecycle_timestamp")
        if _parse_iso_utc(first_seen) is None:
            raise IntendedPaperProtectionError("entry_invalid_broker_lifecycle_timestamp")
        state, state_error = _load_protective_floor_state(ledger_path)
        if state_error and state_error != "state_missing":
            raise IntendedPaperProtectionError(f"protective_floor_state_corrupt:{state_error}")
        existing = state.get(sym)
        entry_id = str(entry.get("id") or "").strip()
        stop_price = _intended_finite_positive(stop.get("stop_price"))
        if stop_price is None:
            raise IntendedPaperProtectionError("stop_invalid_price")
        if isinstance(existing, dict):
            existing = _validated_existing_intended_lifecycle(existing, account_id, allow_pending=True)
            same_lifecycle = (
                str(existing.get("entry_order_id") or "").strip() == entry_id
                and str(existing.get("account_id") or "").strip() == account_id
                and str(existing.get("strategy_id") or "").strip() == _INTENDED_PAPER_STRATEGY_ID
                and abs(_safe_float(existing.get("entry_price"), 0.0) - entry_price) <= max(0.01, entry_price * 1e-4)
                and abs(_safe_float(existing.get("qty"), 0.0) - qty) <= max(1e-9, qty * 1e-6)
            )
            if not same_lifecycle:
                raise IntendedPaperProtectionError("conflicting_existing_lifecycle")
            if stop_price + 1e-12 < float(existing["accepted_stop_floor"]):
                raise IntendedPaperProtectionError("stop_below_durable_floor")
            hwm = max(entry_price, _safe_float(existing.get("hwm"), 0.0))
            floor = max(stop_price, _safe_float(existing.get("accepted_stop_floor"), 0.0))
            first_seen = str(existing["lifecycle_first_seen_at_utc"])
            record = dict(existing)
        elif existing is None:
            hwm, floor, record = entry_price, stop_price, {}
        else:
            raise IntendedPaperProtectionError("existing_lifecycle_corrupt")
        record.pop("protection_pending", None)
        record.update({
            "entry_price": entry_price,
            "qty": qty, "entry_fill_qty": qty,
            "hwm": hwm,
            "accepted_stop_floor": floor,
            "entry_order_id": entry_id,
            "accepted_order_id": str(stop.get("id") or "").strip(),
            "accepted_order_tif": str(stop.get("time_in_force") or "").strip().lower(),
            "lifecycle_first_seen_at_utc": first_seen,
            "account_id": account_id,
            "strategy_id": _INTENDED_PAPER_STRATEGY_ID,
        })
        state[sym] = record
        _atomic_write_json(ledger_path, state)
        return record
    except Exception as exc:
        try:
            _halt_intended_paper_entries(state_dir, account_id, str(exc))
        except Exception as halt_exc:
            raise IntendedPaperProtectionError("intended_paper_halt_persist_failed") from halt_exc
        if isinstance(exc, IntendedPaperProtectionError):
            raise
        raise IntendedPaperProtectionError("intended_paper_protection_failed") from exc


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


def _quantity_for_notional(
    notional: float,
    entry: float,
    *,
    whole_share_only: bool,
) -> tuple[float | None, str]:
    """Translate a cash budget into a quantity without exceeding that budget."""
    if not math.isfinite(notional) or notional <= 0:
        return None, "non_positive_notional"
    if not math.isfinite(entry) or entry <= 0:
        return None, "missing_entry_price_for_qty"
    raw_qty = notional / entry
    if whole_share_only:
        qty = float(math.floor(raw_qty + 1e-12))
        if qty < 1.0:
            return None, "whole_share_budget_below_one_share"
        return qty, ""
    if raw_qty <= 0:
        return None, "non_positive_qty"
    return raw_qty, ""


def _build_bracket_buy_spec(
    pick: Pick,
    *,
    notional: float,
    stop_loss_pct: float,
    target_pct: float,
    size_mode: str,
    whole_share_only: bool = False,
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
        qty, qty_reason = _quantity_for_notional(
            notional,
            _safe_float(entry, 0.0),
            whole_share_only=whole_share_only,
        )
        if qty is None:
            return None, qty_reason
        spec["qty"] = qty
        spec["notional"] = None
        spec["estimated_notional"] = qty * float(entry)
    elif size_mode != "notional":
        return None, f"unsupported_size_mode:{size_mode}"
    elif whole_share_only:
        return None, "whole_share_policy_requires_qty_size_mode"
    return spec, ""


def _broker_stop_rearm_symbols(
    *,
    hold_symbols: Iterable[str],
    current_position_symbols: Iterable[str],
    intraday_managed_symbols: Iterable[str],
    close_stale_positions: bool,
) -> list[str]:
    """Return every existing monthly position that must retain broker protection."""
    protected = {str(sym).strip().upper() for sym in hold_symbols if str(sym).strip()}
    intraday = {str(sym).strip().upper() for sym in intraday_managed_symbols if str(sym).strip()}
    if not close_stale_positions:
        # SAFE-HOLD deliberately keeps stale positions, so they still require
        # the same broker-side stop coverage as currently selected holdings.
        protected.update(
            str(sym).strip().upper()
            for sym in current_position_symbols
            if str(sym).strip()
        )
    return sorted(protected - intraday)


def _remaining_sell_order_qty(row: dict[str, Any]) -> float:
    """Return the still-open quantity of one Alpaca sell order."""
    leaves_raw = row.get("leaves_qty")
    if leaves_raw not in {None, ""}:
        return abs(_safe_float(leaves_raw, 0.0))
    order_qty = abs(_safe_float(row.get("qty"), 0.0))
    filled_qty = abs(_safe_float(row.get("filled_qty"), 0.0))
    return max(0.0, order_qty - filled_qty)


def _protected_stop_qty(open_stop_orders: Iterable[dict[str, Any]]) -> float:
    return sum(_remaining_sell_order_qty(dict(row or {})) for row in open_stop_orders)


def _broker_truth_snapshot(
    *,
    account: dict[str, Any],
    positions: Iterable[dict[str, Any]],
    open_orders: Iterable[dict[str, Any]],
    intraday_managed_symbols: Iterable[str],
) -> dict[str, Any]:
    """Build a sanitized post-action broker receipt for web/AI truth views."""
    intraday = {str(sym).strip().upper() for sym in intraday_managed_symbols if str(sym).strip()}
    position_rows: list[dict[str, Any]] = []
    position_symbols: set[str] = set()
    position_qty_by_symbol: dict[str, float] = {}
    for raw in positions:
        row = dict(raw or {})
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or symbol in intraday:
            continue
        position_symbols.add(symbol)
        position_qty_by_symbol[symbol] = abs(_safe_float(row.get("qty"), 0.0))
        position_rows.append(
            {
                "symbol": symbol,
                "side": str(row.get("side") or ""),
                "qty": str(row.get("qty") or ""),
                "market_value": str(row.get("market_value") or ""),
                "avg_entry_price": str(row.get("avg_entry_price") or ""),
                "unrealized_pl": str(row.get("unrealized_pl") or ""),
                "unrealized_plpc": str(row.get("unrealized_plpc") or ""),
            }
        )

    active_statuses = {"accepted", "new", "pending_new", "partially_filled", "accepted_for_bidding"}
    stop_rows: list[dict[str, Any]] = []
    stop_symbols: set[str] = set()
    protected_qty_by_symbol: dict[str, float] = {}
    for raw in open_orders:
        row = dict(raw or {})
        symbol = str(row.get("symbol") or "").strip().upper()
        side = str(row.get("side") or "").strip().lower()
        order_type = str(row.get("type") or "").strip().lower()
        status = str(row.get("status") or "").strip().lower()
        if (
            symbol not in position_symbols
            or side != "sell"
            or order_type not in {"stop", "stop_limit", "trailing_stop"}
            or status not in active_statuses
        ):
            continue
        stop_symbols.add(symbol)
        protected_qty = _remaining_sell_order_qty(row)
        protected_qty_by_symbol[symbol] = protected_qty_by_symbol.get(symbol, 0.0) + protected_qty
        stop_rows.append(
            {
                "symbol": symbol,
                "type": order_type,
                "status": status,
                "qty": str(row.get("qty") or ""),
                "filled_qty": str(row.get("filled_qty") or ""),
                "protected_remaining_qty": protected_qty,
                "order_id": str(row.get("id") or ""),
                "stop_price": str(row.get("stop_price") or ""),
                "time_in_force": str(row.get("time_in_force") or "").lower(),
                "trail_percent": str(row.get("trail_percent") or ""),
            }
        )

    missing = sorted(position_symbols - stop_symbols)
    underprotected: list[str] = []
    overprotected: list[str] = []
    fully_protected: list[str] = []
    for symbol in sorted(position_symbols):
        position_qty = position_qty_by_symbol.get(symbol, 0.0)
        protected_qty = protected_qty_by_symbol.get(symbol, 0.0)
        tolerance = max(1e-9, position_qty * 1e-6)
        if position_qty <= 0:
            if symbol in stop_symbols:
                underprotected.append(symbol)
        elif protected_qty + tolerance < position_qty:
            if symbol in stop_symbols:
                underprotected.append(symbol)
        elif protected_qty <= position_qty + tolerance:
            fully_protected.append(symbol)
        if protected_qty > position_qty + tolerance:
            overprotected.append(symbol)
    protection_gaps = sorted(set(missing) | set(underprotected) | set(overprotected))
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "account": {
            "status": account.get("status"),
            "equity": str(account.get("equity") or ""),
            "last_equity": str(account.get("last_equity") or ""),
            "cash": str(account.get("cash") or ""),
            "buying_power": str(account.get("buying_power") or ""),
            "portfolio_value": str(account.get("portfolio_value") or ""),
            "trading_blocked": bool(account.get("trading_blocked")),
            "account_blocked": bool(account.get("account_blocked")),
        },
        "positions": sorted(position_rows, key=lambda row: row["symbol"]),
        "open_stops": sorted(stop_rows, key=lambda row: row["symbol"]),
        "position_symbols": sorted(position_symbols),
        "stop_symbols": sorted(stop_symbols),
        "missing_stop_symbols": missing,
        "underprotected_stop_symbols": underprotected,
        "overprotected_stop_symbols": overprotected,
        "protection_gap_symbols": protection_gaps,
        "position_qty_by_symbol": position_qty_by_symbol,
        "protected_qty_by_symbol": protected_qty_by_symbol,
        "stop_coverage_count": len(fully_protected),
        "position_count": len(position_symbols),
        "stop_coverage_complete": not protection_gaps,
    }


def _broker_protection_policy_violations(
    *,
    positions: Iterable[dict[str, Any]],
    open_orders: Iterable[dict[str, Any]],
    intraday_managed_symbols: Iterable[str],
    protective_floor_state: dict[str, Any],
    requested_tif: str,
) -> list[dict[str, Any]]:
    """Reconcile the exact fixed-stop invariant against fresh broker truth.

    Quantity coverage alone is insufficient: a full-size stop can still be
    illegal for the quantity, expire under the wrong TIF, or sit below a
    previously broker-confirmed lifecycle floor.
    """
    intraday = {
        str(symbol).strip().upper()
        for symbol in intraday_managed_symbols
        if str(symbol).strip()
    }
    positions_by_symbol = {
        str(row.get("symbol") or "").strip().upper(): dict(row or {})
        for row in positions
        if str(row.get("symbol") or "").strip().upper() not in intraday
        and str(row.get("symbol") or "").strip()
    }
    active_statuses = {
        "accepted",
        "new",
        "pending_new",
        "partially_filled",
        "accepted_for_bidding",
        "held",
    }
    fixed_by_symbol: dict[str, list[dict[str, Any]]] = {}
    protective_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for raw in open_orders:
        order = dict(raw or {})
        symbol = str(order.get("symbol") or "").strip().upper()
        order_type = str(order.get("type") or order.get("order_type") or "").strip().lower()
        if (
            symbol not in positions_by_symbol
            or str(order.get("side") or "").strip().lower() != "sell"
            or str(order.get("status") or "").strip().lower() not in active_statuses
            or order_type not in {"stop", "stop_limit", "trailing_stop"}
        ):
            continue
        protective_by_symbol.setdefault(symbol, []).append(order)
        if order_type in {"stop", "stop_limit"}:
            fixed_by_symbol.setdefault(symbol, []).append(order)

    violations: list[dict[str, Any]] = []
    for symbol, position in sorted(positions_by_symbol.items()):
        qty = abs(_safe_float(position.get("qty"), 0.0))
        fixed = fixed_by_symbol.get(symbol, [])
        protective = protective_by_symbol.get(symbol, [])
        if qty <= 0:
            violations.append({"symbol": symbol, "reason": "invalid_position_qty"})
            continue
        if len(fixed) != 1 or len(protective) != 1:
            violations.append(
                {
                    "symbol": symbol,
                    "reason": "expected_exactly_one_fixed_stop",
                    "fixed_stop_count": len(fixed),
                    "protective_order_count": len(protective),
                }
            )
            continue
        order = fixed[0]
        remaining = _remaining_sell_order_qty(order)
        tolerance = max(1e-9, qty * 1e-6)
        if abs(remaining - qty) > tolerance:
            violations.append(
                {
                    "symbol": symbol,
                    "reason": "fixed_stop_qty_mismatch",
                    "position_qty": qty,
                    "protected_qty": remaining,
                }
            )
        expected_tif = _persistent_exit_tif_for_qty(requested_tif, qty)
        actual_tif = str(order.get("time_in_force") or "").strip().lower()
        if actual_tif != expected_tif:
            violations.append(
                {
                    "symbol": symbol,
                    "reason": "fixed_stop_tif_mismatch",
                    "expected_tif": expected_tif,
                    "actual_tif": actual_tif,
                }
            )
        record = _matching_protective_floor_record(
            symbol,
            position,
            protective_floor_state,
        )
        if not record:
            violations.append(
                {"symbol": symbol, "reason": "accepted_stop_floor_not_reconciled"}
            )
            continue
        accepted_floor = _safe_float(record.get("accepted_stop_floor"), 0.0)
        actual_stop = _safe_float(order.get("stop_price"), 0.0)
        if actual_stop + 1e-12 < accepted_floor:
            violations.append(
                {
                    "symbol": symbol,
                    "reason": "fixed_stop_below_accepted_floor",
                    "actual_stop": actual_stop,
                    "accepted_stop_floor": accepted_floor,
                }
            )
    return violations


def _write_manager_receipt(path: Path, report: dict[str, Any]) -> None:
    """Atomically publish the latest deterministic manager/broker truth receipt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "report": report,
    }
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd: int | None = None
    try:
        fd = os.open(tmp, flags, 0o600)
        data = (json.dumps(payload, ensure_ascii=True, indent=2) + "\n").encode("utf-8")
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short manager-receipt write")
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.replace(tmp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if fd is not None:
            os.close(fd)
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _wait_for_fill_details(
    client: AlpacaClient,
    order: dict[str, Any],
    *,
    timeout_sec: float,
) -> tuple[float, str, float]:
    order_id = str(order.get("id") or "").strip()
    status = str(order.get("status") or "").strip().lower()
    filled_qty = _safe_float(order.get("filled_qty"), 0.0)
    filled_avg_price = _safe_float(order.get("filled_avg_price"), 0.0)
    deadline = time.time() + max(0.0, timeout_sec)
    while (
        order_id
        and (filled_qty <= 0 or filled_avg_price <= 0)
        and status not in {"canceled", "expired", "rejected"}
        and time.time() < deadline
    ):
        time.sleep(1.0)
        try:
            order = client.get_order(order_id)
        except RuntimeError:
            break
        status = str(order.get("status") or "").strip().lower()
        filled_qty = _safe_float(order.get("filled_qty"), 0.0)
        filled_avg_price = _safe_float(order.get("filled_avg_price"), 0.0)
    return filled_qty, status, filled_avg_price


def _wait_for_filled_qty(client: AlpacaClient, order: dict[str, Any], *, timeout_sec: float) -> tuple[float, str]:
    """Backward-compatible quantity-only wrapper used by older callers/tests."""

    filled_qty, status, _ = _wait_for_fill_details(client, order, timeout_sec=timeout_sec)
    return filled_qty, status


def _entry_relative_stop_price(
    pick: Pick,
    *,
    filled_avg_price: float,
    fallback_stop_loss_pct: float,
) -> float:
    """Move the frozen signal-time risk distance to the actual entry fill.

    The challenger changes only the stop anchor.  If a pick carries a valid
    signal entry and stop, their absolute distance is retained.  Otherwise the
    already configured percentage stop is anchored to the fill.  No future bar
    or same-session high/low is consulted.
    """

    if not math.isfinite(filled_avg_price) or filled_avg_price <= 0:
        raise RuntimeError("entry_relative_stop requires positive filled_avg_price")
    reference = _safe_float(pick.entry_price, 0.0)
    frozen_stop = _safe_float(pick.stop_price, 0.0)
    if reference > 0 and frozen_stop > 0 and reference > frozen_stop:
        risk_distance = reference - frozen_stop
    else:
        risk_distance = filled_avg_price * max(0.01, float(fallback_stop_loss_pct))
    stop = filled_avg_price - risk_distance
    if not math.isfinite(stop) or stop <= 0 or stop >= filled_avg_price:
        raise RuntimeError("entry_relative_stop produced invalid stop")
    return stop


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
    if "T" in s or " " in s:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (TypeError, ValueError):
            pass
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _main_unlocked() -> int:
    ap = argparse.ArgumentParser(description="Dry-run-first Alpaca paper bridge for monthly equities picks")
    ap.add_argument("--picks-csv", default=_env("ALPACA_PICKS_CSV", ""))
    ap.add_argument("--month", default=_env("ALPACA_PICKS_MONTH", ""))
    kill_group = ap.add_mutually_exclusive_group()
    kill_group.add_argument("--paper-kill-owned", metavar="PROOF_JSON")
    kill_group.add_argument("--intended-live-kill-owned", metavar="PROOF_JSON")
    ap.add_argument("--apply-kill", action="store_true")
    args = ap.parse_args()

    # This deliberately runs before reading picks: an explicit owner proof is
    # the only authority for its bounded paper-only exit scope.
    if args.paper_kill_owned or args.intended_live_kill_owned:
        intended_live_kill = bool(args.intended_live_kill_owned)
        proof_path = Path(args.intended_live_kill_owned or args.paper_kill_owned)
        receipt_path = proof_path.parent / "paper_kill_receipt.json"
        base_url = _env("ALPACA_BASE_URL", _PAPER_API_URL)
        state_dir = _paper_kill_state_dir(base_url, _env("ALPACA_API_KEY_ID"))
        try:
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            if not _env("ALPACA_API_KEY_ID") or not _env("ALPACA_API_SECRET_KEY"):
                raise PaperKillValidationError("missing_alpaca_keys")
            receipt = run_paper_owned_kill(
                proof=proof,
                client=AlpacaClient(base_url, _env("ALPACA_API_KEY_ID"), _env("ALPACA_API_SECRET_KEY")),
                base_url=base_url,
                apply=bool(args.apply_kill),
                state_dir=state_dir,
                intended_live=intended_live_kill,
            )
        except (OSError, json.JSONDecodeError, PaperKillValidationError, RuntimeError) as exc:
            receipt = {"status": "rejected", "error": str(exc), "not_confirmed": True}
            _atomic_write_json(receipt_path, receipt)
            print(json.dumps(receipt, ensure_ascii=True, sort_keys=True), file=sys.stderr)
            return 2
        receipt["not_confirmed"] = receipt.get("status") != "confirmed_flat"
        _atomic_write_json(receipt_path, receipt)
        print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
        return 0 if not args.apply_kill or receipt["status"] == "awaiting_regular_session" or receipt["status"] == "confirmed_flat" else 5

    picks_csv = Path(args.picks_csv) if args.picks_csv else _default_picks_csv()
    if picks_csv is None or not picks_csv.exists():
        print("error=no_picks_csv", file=sys.stderr)
        return 2

    picks = _load_picks(picks_csv, args.month or None)
    allow_empty_picks_for_cash = _env_bool("ALPACA_ALLOW_EMPTY_PICKS_FOR_CASH", False)
    if not picks and not allow_empty_picks_for_cash:
        print("error=no_picks_for_month", file=sys.stderr)
        return 3

    max_positions = max(1, _env_int("ALPACA_MAX_POSITIONS", 3))
    target_alloc_pct = max(0.01, min(1.0, _env_float("ALPACA_TARGET_ALLOC_PCT", 0.45)))
    min_dollar_order = max(1.0, _env_float("ALPACA_MIN_DOLLAR_ORDER", 50.0))
    send_orders = _env_bool("ALPACA_SEND_ORDERS", False)
    allow_new_entries = _env_bool("ALPACA_ALLOW_NEW_ENTRIES", True)
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
    whole_share_only = _env_bool("ALPACA_WHOLE_SHARE_ONLY", False)
    broker_protection_tif_requested = _env(
        "ALPACA_BROKER_PROTECTION_TIF",
        _default_broker_protection_tif(broker_protection_order_class),
    ).lower()
    broker_protection_tif = broker_protection_tif_requested
    broker_target_pct = max(0.0, _env_float("ALPACA_BROKER_TARGET_PCT", 0.08))
    broker_wait_fill_sec = max(1.0, _env_float("ALPACA_BROKER_PROTECTION_WAIT_FILL_SEC", 20.0))
    entry_relative_stop_enable = _env_bool("ALPACA_ENTRY_RELATIVE_STOP_ENABLE", False)
    native_trailing_enable = _env_bool("ALPACA_NATIVE_TRAIL_ENABLE", False)
    native_trailing_required = _env_bool("ALPACA_NATIVE_TRAIL_REQUIRED", False)
    native_trailing_tif_requested = _env("ALPACA_NATIVE_TRAIL_TIF", broker_protection_tif).lower()
    native_trailing_tif = native_trailing_tif_requested
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
    try:
        intended_paper = _intended_lifecycle_enabled(
            base_url,
            require_enabled=send_orders,
            capital=capital_override_usd,
        )
        intended_frozen_weights = _intended_frozen_weights(picks) if intended_paper else {}
    except IntendedPaperProtectionError as exc:
        print(f"error={exc}", file=sys.stderr)
        return 8
    paper_halt_active = paper_entry_halted(
        base_url=base_url,
        state_dir=_paper_kill_state_dir(base_url, key_id),
    )
    if paper_halt_active:
        allow_new_entries = False
    if whole_share_only and (
        not broker_protection_enable
        or not broker_protection_required
        or broker_protection_order_class != "simple_stop"
        or broker_protection_size_mode != "qty"
    ):
        print("error=whole_share_policy_requires_required_simple_stop_qty_protection", file=sys.stderr)
        return 8
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
        if intended_paper:
            try:
                _intended_lifecycle_enabled(
                    base_url,
                    require_enabled=send_orders,
                    account_id=str(account.get("id") or ""),
                    capital=capital_override_usd,
                )
            except IntendedPaperProtectionError as exc:
                print(f"error={exc}", file=sys.stderr)
                return 8
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
            _clock = {"is_open": not intended_paper, "_clock_error": str(_exc)}
        _market_is_open = bool(_clock.get("is_open"))
        if not _market_is_open:
            _next_open = _clock.get("next_open")
            print(
                f"[paper_bridge] market closed (next_open={_next_open}); skipping new BUY submissions this run",
                flush=True,
            )
    if intended_paper and send_orders and _market_is_open:
        try:
            _recover_intended_entry_intents(client=client, base_url=base_url,
                account_id=str(account.get("id") or ""), capital=capital_override_usd,
                reentry_path=reentry_block_path, state_path=_protective_exit_hwm_state_path(),
                state_dir=_paper_kill_state_dir(base_url, key_id))
            positions = client.list_positions()
            open_orders = client.list_orders(status="open", limit=100)
        except Exception as exc:
            _halt_intended_paper_entries(_paper_kill_state_dir(base_url, key_id), str(account.get("id") or ""), str(exc))
            print(json.dumps({"error": "entry_recovery_not_confirmed", "detail": str(exc)}))
            return 9
    if intended_paper and send_orders and _env_bool("ALPACA_INTENDED_MONTHLY", False):
        try:
            monthly_entry = _env("ALPACA_INTENDED_ENTRY_SESSION")
            if not monthly_entry or any(p.entry_day != monthly_entry for p in picks):
                raise IntendedPaperProtectionError("rotation_picks_session_mismatch")
            monthly_state_path = _protective_exit_hwm_state_path()
            monthly_state, monthly_error = _load_protective_floor_state(monthly_state_path)
            if monthly_error not in {"", "state_missing"}:
                raise IntendedPaperProtectionError("rotation_state_corrupt")
            _reconcile_intended_stop_exits(client=client, state=monthly_state,
                state_path=monthly_state_path, reentry_path=reentry_block_path,
                positions={p["symbol"]: p for p in positions}, open_orders=open_orders,
                account_id=str(account.get("id") or ""), state_dir=_paper_kill_state_dir(base_url, key_id))
            # DAY orders on retained names may have expired overnight. Restore
            # their durable floors before waiting on any stale-name market exit.
            selected_monthly = {p.ticker for p in picks}
            for position in positions:
                symbol = position.get("symbol")
                if symbol not in monthly_state or symbol not in selected_monthly or monthly_state[symbol].get("rotation_intent"):
                    continue
                _rearm_intended_position(client=client, symbol=symbol, position=position,
                    existing_stops=[o for o in open_orders if o.get("symbol") == symbol and o.get("type") == "stop" and o.get("side") == "sell"],
                    state=monthly_state, state_path=monthly_state_path, account_id=str(account.get("id") or ""))
            rotation = _rotate_intended_monthly(client=client, base_url=base_url,
                account_id=str(account.get("id") or ""), capital=capital_override_usd,
                state_path=monthly_state_path, reentry_path=reentry_block_path,
                selected_symbols={p.ticker for p in picks}, entry_session=monthly_entry)
            if rotation["status"] != "COMPLETE":
                print(json.dumps({"monthly_rotation": rotation}))
                return 77  # Known pending exit: no buys, no duplicate dispatch.
            account = client.get_account()
            positions = client.list_positions()
            open_orders = client.list_orders(status="open", limit=100)
        except Exception as exc:
            _halt_intended_paper_entries(_paper_kill_state_dir(base_url, key_id), str(account.get("id") or ""), str(exc))
            print(json.dumps({"error": "monthly_rotation_not_confirmed", "detail": str(exc)}))
            return 9
    buying_power = float(account.get("buying_power") or account.get("cash") or 0.0)
    cash = float(account.get("cash") or 0.0)
    effective_capital = min(buying_power, capital_override_usd) if capital_override_usd > 0 else buying_power
    if intended_paper and not offline_dry_run:
        equity = _intended_finite_positive(account.get("equity"))
        if equity is None:
            print(json.dumps({"error": "intended_equity_not_confirmed"}))
            return 8
        effective_capital = min(equity, capital_override_usd) if capital_override_usd > 0 else equity
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

    if intended_paper:
        try:
            intended_frozen_weights = _intended_frozen_weights(picks)
        except IntendedPaperProtectionError as exc:
            print(f"error={exc}", file=sys.stderr)
            return 8

    stale_guard_triggered = (
        pick_age_days is not None
        and pick_age_days > max_pick_age_days
        and not allow_stale_picks
        and not (intended_paper and not allow_new_entries)
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
    intraday_managed_symbols = _load_intraday_managed_symbols(strict=close_stale_positions)
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
    candidate_new_buy_symbols = [p.ticker for p in selected if p.ticker not in occupied_symbols]
    new_buy_symbols = list(candidate_new_buy_symbols) if allow_new_entries else []

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
    candidate_replacement_buys = replacement_picks[:replacement_slots] if replacement_slots > 0 else []
    replacement_buys = list(candidate_replacement_buys) if allow_new_entries else []

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

    if intended_paper:
        score_weights = {
            p.ticker: intended_frozen_weights[p.ticker]
            for p in all_active
        }
        per_ticker_notional = {
            ticker: effective_capital * target_alloc_pct * weight
            for ticker, weight in score_weights.items()
        }
        per_position_notional = 0.0
    elif (weighted_sizing or atr_adjusted_sizing) and all_active:
        raw = {p.ticker: _raw_weight(p) for p in all_active}
        # Hard clamp: no position may exceed 60% of the sleeve.  Do not
        # renormalize capped weights upward; the unused sleeve remains cash.
        score_weights = _hard_capped_normalized_weights(raw, maximum_weight=0.60)
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
    protective_floor_state_path = _protective_exit_hwm_state_path()
    protective_floor_state: dict[str, Any] = {}
    protective_floor_state_error = ""
    if broker_protection_enable and broker_protection_order_class == "simple_stop":
        protective_floor_state, protective_floor_state_error = (
            _load_protective_floor_state(protective_floor_state_path)
        )
    if intended_paper and send_orders:
        try:
            if protective_floor_state_error not in {"", "state_missing"}:
                raise IntendedPaperProtectionError("intended_floor_state_corrupt")
            _reconcile_intended_stop_exits(
                client=client, state=protective_floor_state, state_path=protective_floor_state_path,
                reentry_path=reentry_block_path, positions=current_positions, open_orders=open_orders,
                account_id=str(account.get("id") or ""), state_dir=_paper_kill_state_dir(base_url, key_id),
            )
            reentry_block_state = _active_reentry_blocks(_load_reentry_block_state(reentry_block_path), now_utc)
            blocked_reentry_symbols.update(set(reentry_block_state) - occupied_symbols)
            active_reentry_blocks = {sym: row for sym, row in reentry_block_state.items()
                                    if sym in blocked_reentry_symbols}
        except Exception as exc:
            _halt_intended_paper_entries(_paper_kill_state_dir(base_url, key_id),
                                        str(account.get("id") or ""), str(exc))
            print(json.dumps({"error": "intended_exit_reconciliation_not_confirmed", "detail": str(exc)}))
            return 9
    protection_preflight_violations: list[dict[str, Any]] = []
    if (
        send_orders
        and broker_protection_required
        and broker_protection_order_class == "simple_stop"
    ):
        protection_preflight_violations = _accepted_floor_preflight_violations(
            positions=current_positions.values(),
            intraday_managed_symbols=intraday_managed_symbols,
            protective_floor_state=protective_floor_state,
            state_error=protective_floor_state_error,
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
        "allow_new_entries": bool(allow_new_entries),
        "paper_entry_halt_active": bool(paper_halt_active),
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
        "native_trailing_tif_requested": native_trailing_tif_requested,
        "native_trailing_tif": native_trailing_tif,
        "native_trailing_tif_policy": "fractional_day_whole_gtc",
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
        "whole_share_only": whole_share_only,
        "broker_protection_tif_requested": broker_protection_tif_requested,
        "broker_protection_tif": broker_protection_tif,
        "broker_protection_tif_policy": "fractional_day_whole_gtc",
        "protective_floor_state_path": str(protective_floor_state_path),
        "protective_floor_state_error": protective_floor_state_error,
        "protection_preflight_violations": protection_preflight_violations,
        "protection_mutations_allowed": not protection_preflight_violations,
        "broker_target_pct": round(broker_target_pct * 100, 2),
        "broker_wait_fill_sec": broker_wait_fill_sec,
        "entry_relative_stop_enabled": entry_relative_stop_enable,
        "midmonth_rotation_enabled": midmonth_rotation,
        "midmonth_day_threshold": midmonth_day_threshold,
        "midmonth_dd_pct": round(midmonth_dd_pct * 100, 2),
        "rotation_triggered": rotation_symbols,
        "rotation_loss_pct": rotation_details,
        "candidate_replacement_buys": candidate_replacement_buys,
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
        "candidate_new_buy_symbols": candidate_new_buy_symbols,
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
            whole_share_only=whole_share_only,
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
                "stop_anchor": "actual_fill" if entry_relative_stop_enable else "signal_reference",
            }
        )

    intended_paper_entry_halted = False

    def _submit_buy_action(pick: Pick, *, action: str, notional: float) -> None:
        nonlocal intended_paper_entry_halted
        score_weight = round(score_weights.get(pick.ticker, 0.0), 4)
        if intended_paper_entry_halted or paper_entry_halted(
            base_url=base_url,
            state_dir=_paper_kill_state_dir(base_url, key_id),
        ):
            report["results"].append(
                {
                    "ticker": pick.ticker,
                    "action": action,
                    "status": "skipped_paper_entry_halted",
                    "notional": round(notional, 2),
                    "score_weight": score_weight,
                }
            )
            return
        if intended_paper and notional < min_dollar_order:
            report["results"].append(
                {
                    "ticker": pick.ticker,
                    "action": action,
                    "status": "skipped_below_minimum_order",
                    "notional": round(notional, 2),
                    "score_weight": score_weight,
                }
            )
            return
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
            if entry_relative_stop_enable and broker_protection_order_class != "simple_stop":
                reason = "entry_relative_stop_requires_simple_stop_fill_then_protect"
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
                whole_share_only=whole_share_only,
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
                    if intended_paper and protective_floor_state_error not in {"", "state_missing"}:
                        raise IntendedPaperProtectionError(
                            f"protective_floor_state_corrupt:{protective_floor_state_error}"
                        )
                    if intended_paper and pick.ticker in protective_floor_state:
                        _validated_existing_intended_lifecycle(
                            protective_floor_state[pick.ticker],
                            str(account.get("id") or "").strip(),
                        )
                        raise IntendedPaperProtectionError("existing_lifecycle_unreconciled")
                    qty = float(spec.get("qty") or 0.0)
                    if qty <= 0:
                        raise RuntimeError("simple_stop requires qty sizing")
                    if intended_paper:
                        fresh_cash = _safe_float(client.get_account().get("cash"), -1)
                        if not math.isfinite(fresh_cash) or fresh_cash < 0:
                            raise IntendedPaperProtectionError("intended_cash_not_confirmed")
                        bounded_notional = float(Decimal(str(min(notional, fresh_cash))).quantize(Decimal("0.01"), rounding=ROUND_DOWN))
                        if bounded_notional < min_dollar_order:
                            report["results"].append({"ticker": pick.ticker, "status": "skipped_cash_below_minimum"})
                            return
                        record = _submit_intended_reserved_entry(client=client, base_url=base_url,
                            account_id=str(account.get("id") or ""), capital=capital_override_usd,
                            reentry_path=reentry_block_path, state_path=protective_floor_state_path,
                            state_dir=_paper_kill_state_dir(base_url, key_id), pick=pick,
                            notional=bounded_notional, timeout_sec=broker_wait_fill_sec)
                        report["results"].append({"ticker": pick.ticker, "action": "protected_market_buy",
                            "entry_order_id": record["entry_order_id"], "entry_status": "terminal",
                            "stop_order_id": record["accepted_order_id"], "notional": bounded_notional,
                            "qty": _format_qty(record["qty"]), "filled_avg_price": record["entry_price"],
                            "stop_price": record["accepted_stop_floor"], "stop_anchor": "actual_fill",
                            "score_weight": score_weight})
                        return
                    else:
                        entry_order = client.submit_market_buy_qty(pick.ticker, qty)  # type: ignore[union-attr]
                    if intended_paper:
                        final_entry = _terminal_intended_entry(
                            client,
                            entry_order,
                            expected_symbol=pick.ticker,
                            timeout_sec=broker_wait_fill_sec,
                        )  # type: ignore[arg-type]
                        filled_qty = _safe_float(final_entry.get("filled_qty"), 0.0)
                        filled_avg_price = _safe_float(final_entry.get("filled_avg_price"), 0.0)
                        entry_status = str(final_entry.get("status") or "").strip().lower()
                        _persist_intended_pending_fill(protective_floor_state_path,
                            account_id=str(account.get("id") or ""), symbol=pick.ticker, entry=final_entry)
                    else:
                        filled_qty, entry_status, filled_avg_price = _wait_for_fill_details(
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
                    stop_price = float(spec["stop_loss_price"])
                    if entry_relative_stop_enable:
                        stop_price = _entry_relative_stop_price(
                            pick,
                            filled_avg_price=filled_avg_price,
                            fallback_stop_loss_pct=stop_loss_pct,
                        )
                    stop_order = client.submit_stop_sell(  # type: ignore[union-attr]
                        pick.ticker,
                        qty=filled_qty,
                        stop_price=stop_price,
                        time_in_force=_persistent_exit_tif_for_qty(
                            broker_protection_tif_requested,
                            filled_qty,
                        ),
                    )
                    if intended_paper:
                        _complete_intended_paper_simple_stop(
                            client=client,  # type: ignore[arg-type]
                            base_url=base_url,
                            state_dir=_paper_kill_state_dir(base_url, key_id),
                            ledger_path=protective_floor_state_path,
                            account_id=str(account.get("id") or ""),
                            entry_order=entry_order,
                            stop_order=stop_order,
                            symbol=pick.ticker,
                            requested_stop=stop_price,
                            intended_live=_env_bool("ALPACA_INTENDED_LIVE", False),
                            capital=capital_override_usd,
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
                            "filled_avg_price": round(filled_avg_price, 4) if filled_avg_price > 0 else None,
                            "stop_price": round(stop_price, 4),
                            "stop_anchor": "actual_fill" if entry_relative_stop_enable else "signal_reference",
                            "target_price": round(float(spec["take_profit_price"]), 4),
                            "score_weight": score_weight,
                        }
                    )
                    return
                except RuntimeError as exc:
                    if broker_protection_required:
                        if intended_paper:
                            intended_paper_entry_halted = True
                            try:
                                _halt_intended_paper_entries(
                                    _paper_kill_state_dir(base_url, key_id),
                                    str(account.get("id") or ""),
                                    str(exc),
                                )
                            except Exception:
                                pass
                        else:
                            try:
                                client.close_position(pick.ticker)  # type: ignore[union-attr]
                            except RuntimeError:
                                pass
                        report["results"].append(
                            {
                                "ticker": pick.ticker,
                                "action": "protected_market_buy" if action == "market_buy" else "replacement_protected_market_buy",
                                "status": "not_confirmed_halted" if intended_paper else "error_closed_if_needed",
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

    if send_orders and not protection_preflight_violations:
        # ── 1. Stop-loss closes (highest priority) ────────────────────────────
        if enable_stop_loss:
            for symbol in sl_triggered_symbols:
                if symbol not in current_positions:
                    continue
                if not _cancel_open_sell_orders(symbol, action="stop_loss_cancel_sell_order"):
                    continue
                try:
                    result = client.close_position(symbol)
                    if reentry_block_enable:
                        _add_reentry_block(
                            reentry_block_state,
                            symbol,
                            now=now_utc,
                            days=trail_reentry_block_days,
                            reason="stop_loss_close",
                        )
                        blocked_reentry_symbols.add(symbol)
                        _save_reentry_block_state(reentry_block_path, reentry_block_state)
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
                        blocked_reentry_symbols.add(symbol)
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
                            time_in_force=_persistent_exit_tif_for_qty(
                                broker_protection_tif_requested,
                                qty,
                            ),
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
                        time_in_force=_persistent_exit_tif_for_qty(
                            native_trailing_tif_requested,
                            qty,
                        ),
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
                            time_in_force=_persistent_exit_tif_for_qty(
                                broker_protection_tif_requested,
                                qty,
                            ),
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
            rearm_symbols = _broker_stop_rearm_symbols(
                hold_symbols=hold_symbols,
                current_position_symbols=current_positions.keys(),
                intraday_managed_symbols=intraday_managed_symbols,
                close_stale_positions=close_stale_positions,
            )
            for symbol in rearm_symbols:
                if symbol in closed_out:
                    continue
                pos = current_positions.get(symbol)
                pick = picks_by_ticker.get(symbol)
                if not pos:
                    continue
                if intended_paper:
                    try:
                        if not _market_is_open:
                            continue
                        confirmed = _rearm_intended_position(
                            client=client, symbol=symbol, position=pos,
                            existing_stops=list(open_stop_sell_orders.get(symbol) or []),
                            state=protective_floor_state, state_path=protective_floor_state_path,
                            account_id=str(account.get("id") or ""),
                        )
                        report["results"].append({"ticker": symbol, "action": "intended_rearm",
                                                  "status": "confirmed", "order_id": confirmed["id"],
                                                  "time_in_force": confirmed["time_in_force"]})
                    except Exception as exc:
                        intended_paper_entry_halted = True
                        _halt_intended_paper_entries(_paper_kill_state_dir(base_url, key_id),
                                                    str(account.get("id") or ""), str(exc))
                        report["results"].append({"ticker": symbol, "action": "intended_rearm",
                                                  "status": "not_confirmed_halted", "error": str(exc)})
                    continue
                notional = per_ticker_notional.get(symbol, per_position_notional)
                if pick is not None:
                    spec, reason = _build_bracket_buy_spec(
                        pick,
                        notional=notional,
                        stop_loss_pct=stop_loss_pct,
                        target_pct=broker_target_pct,
                        size_mode="qty",
                    )
                else:
                    avg_entry = _safe_float(pos.get("avg_entry_price"), 0.0)
                    spec = (
                        {"stop_loss_price": avg_entry * (1.0 - stop_loss_pct)}
                        if avg_entry > 0
                        else None
                    )
                    reason = "" if spec is not None else "missing_pick_and_avg_entry_price"
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
                existing_stops = list(open_stop_sell_orders.get(symbol) or [])
                protected_qty = _protected_stop_qty(existing_stops)
                tolerance = max(1e-9, qty * 1e-6)
                required_stop_tif = _persistent_exit_tif_for_qty(
                    broker_protection_tif_requested,
                    qty,
                )
                protected_stop_price = _protected_rearm_stop_price(
                    symbol,
                    float(spec["stop_loss_price"]),
                    pos,
                    existing_stops,
                    protective_floor_state,
                )
                protection_update_order = _single_covering_stop_needing_update(
                    existing_stops,
                    qty,
                    required_stop_tif,
                    protected_stop_price,
                )
                if existing_stops and abs(protected_qty - qty) <= tolerance:
                    if protection_update_order is not None:
                        order_id = str(protection_update_order.get("id") or "").strip()
                        if not order_id:
                            report["results"].append(
                                {
                                    "ticker": symbol,
                                    "action": "rearm_replace_protection",
                                    "status": "error",
                                    "error": "missing_order_id",
                                }
                            )
                            continue
                        stop_price = protected_stop_price
                        cur = _safe_float(pos.get("current_price"), 0.0)
                        if cur > 0 and cur <= stop_price:
                            cancel_failed = False
                            for order in existing_stops:
                                existing_order_id = str(order.get("id") or "").strip()
                                if not existing_order_id:
                                    cancel_failed = True
                                    continue
                                try:
                                    client.cancel_order(existing_order_id)
                                except RuntimeError as exc:
                                    cancel_failed = True
                                    report["results"].append(
                                        {
                                            "ticker": symbol,
                                            "action": "floor_breach_cancel_stop",
                                            "order_id": existing_order_id,
                                            "status": "error",
                                            "error": str(exc),
                                        }
                                    )
                            if cancel_failed:
                                report["results"].append(
                                    {
                                        "ticker": symbol,
                                        "action": "floor_breach_exit",
                                        "status": "blocked",
                                        "error": "could_not_cancel_existing_stop",
                                        "current_price": round(cur, 4),
                                        "accepted_floor": round(stop_price, 4),
                                    }
                                )
                                continue
                            try:
                                result = client.close_position(symbol)
                                report["results"].append(
                                    {
                                        "ticker": symbol,
                                        "action": "floor_breach_exit",
                                        "order_id": result.get("id"),
                                        "status": result.get("status"),
                                        "current_price": round(cur, 4),
                                        "accepted_floor": round(stop_price, 4),
                                    }
                                )
                            except RuntimeError as exc:
                                report["results"].append(
                                    {
                                        "ticker": symbol,
                                        "action": "floor_breach_exit",
                                        "status": "error",
                                        "error": str(exc),
                                        "mutation_outcome": "NOT_CONFIRMED_until_broker_refresh",
                                    }
                                )
                                # The close may have failed after the fixed stop
                                # was canceled. Restore emergency DAY/GTC coverage
                                # below the current mark; the final accepted-floor
                                # gate remains failed and alerts until reconciled.
                                emergency_stop = min(
                                    float(spec["stop_loss_price"]),
                                    cur * (1.0 - 0.001),
                                )
                                if emergency_stop > 0:
                                    try:
                                        emergency = client.submit_stop_sell(
                                            symbol,
                                            qty=qty,
                                            stop_price=emergency_stop,
                                            time_in_force=required_stop_tif,
                                        )
                                        report["results"].append(
                                            {
                                                "ticker": symbol,
                                                "action": "floor_breach_emergency_stop",
                                                "order_id": emergency.get("id"),
                                                "status": emergency.get("status"),
                                                "stop_price": round(emergency_stop, 4),
                                            }
                                        )
                                    except RuntimeError as emergency_exc:
                                        report["results"].append(
                                            {
                                                "ticker": symbol,
                                                "action": "floor_breach_emergency_stop",
                                                "status": "error",
                                                "error": str(emergency_exc),
                                            }
                                        )
                            continue
                        try:
                            result = client.replace_order(
                                order_id,
                                {
                                    "stop_price": _format_price(stop_price),
                                    "time_in_force": required_stop_tif,
                                },
                            )
                            report["results"].append(
                                {
                                    "ticker": symbol,
                                    "action": "rearm_replace_protection",
                                    "old_order_id": order_id,
                                    "order_id": result.get("id"),
                                    "status": result.get("status"),
                                    "qty": _format_qty(qty),
                                    "old_tif": str(protection_update_order.get("time_in_force") or "").lower(),
                                    "time_in_force": required_stop_tif,
                                    "old_stop_price": _safe_float(protection_update_order.get("stop_price"), 0.0),
                                    "stop_price": round(stop_price, 4),
                                }
                            )
                        except RuntimeError as exc:
                            report["results"].append(
                                {
                                    "ticker": symbol,
                                    "action": "rearm_replace_protection",
                                    "status": "error",
                                    "error": str(exc),
                                    "mutation_outcome": "NOT_CONFIRMED_until_broker_refresh",
                                }
                            )
                        continue
                    continue
                if existing_stops:
                    cancel_failed = False
                    for order in existing_stops:
                        order_id = str(order.get("id") or "").strip()
                        if not order_id:
                            cancel_failed = True
                            report["results"].append(
                                {
                                    "ticker": symbol,
                                    "action": "rearm_cancel_mismatched_stop",
                                    "status": "error",
                                    "error": "missing_order_id",
                                }
                            )
                            continue
                        try:
                            result = client.cancel_order(order_id)
                            report["results"].append(
                                {
                                    "ticker": symbol,
                                    "action": "rearm_cancel_mismatched_stop",
                                    "order_id": order_id,
                                    "status": result.get("status", "canceled"),
                                    "position_qty": qty,
                                    "protected_qty_before": protected_qty,
                                }
                            )
                        except RuntimeError as exc:
                            cancel_failed = True
                            report["results"].append(
                                {
                                    "ticker": symbol,
                                    "action": "rearm_cancel_mismatched_stop",
                                    "order_id": order_id,
                                    "status": "error",
                                    "error": str(exc),
                                }
                            )
                    if cancel_failed:
                        continue
                    # A partially filled stop changes the broker position.  Do
                    # not reuse the pre-action quantity after cancellation.
                    try:
                        refreshed_rows = client.list_positions()
                    except RuntimeError as exc:
                        report["results"].append(
                            {
                                "ticker": symbol,
                                "action": "rearm_refresh_position_after_cancel",
                                "status": "error",
                                "error": str(exc),
                            }
                        )
                        continue
                    refreshed = {
                        str(row.get("symbol") or "").strip().upper(): row
                        for row in refreshed_rows
                        if str(row.get("symbol") or "").strip()
                    }
                    pos = refreshed.get(symbol)
                    if not pos:
                        continue
                    current_positions[symbol] = pos
                    qty = abs(_safe_float(pos.get("qty"), 0.0))
                    if qty <= 0:
                        continue
                    # A partially filled stop can change whole/fractional
                    # status. Recompute both the legal TIF and lifecycle-bound
                    # floor from the refreshed broker position.
                    required_stop_tif = _persistent_exit_tif_for_qty(
                        broker_protection_tif_requested,
                        qty,
                    )
                    protected_stop_price = _protected_rearm_stop_price(
                        symbol,
                        float(spec["stop_loss_price"]),
                        pos,
                        existing_stops,
                        protective_floor_state,
                    )
                stop_price = protected_stop_price
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
                        result = client.submit_stop_sell(
                            symbol,
                            qty=qty,
                            stop_price=stop_price,
                            time_in_force=required_stop_tif,
                        )
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
            if not _new_entry_allowed(
                pick.ticker,
                enabled=allow_new_entries,
                blocked_symbols=blocked_reentry_symbols,
            ):
                report["results"].append(
                    {
                        "ticker": pick.ticker,
                        "action": "market_buy",
                        "status": (
                            "skipped_new_entries_disabled"
                            if not allow_new_entries
                            else "skipped_reentry_block"
                        ),
                    }
                )
                continue
            notional = per_ticker_notional.get(pick.ticker, per_position_notional)
            _submit_buy_action(pick, action="market_buy", notional=notional)

        # ── 5. Buy replacement picks (after SL/rotation freed slots) ──────────
        for ticker in replacement_buys:
            if not _new_entry_allowed(
                ticker,
                enabled=allow_new_entries,
                blocked_symbols=blocked_reentry_symbols,
            ):
                continue
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

    truth_account = account
    truth_positions = positions
    truth_orders = open_orders
    if client is not None and send_orders:
        try:
            # Post-action refresh makes stop coverage immediately visible to
            # web/AI instead of waiting for the next Telegram reporting cron.
            truth_account = client.get_account()
            truth_positions = client.list_positions()
            truth_orders = client.list_orders(status="open", limit=100)
        except Exception as exc:
            report["broker_truth_refresh_error"] = f"{type(exc).__name__}: {exc}"
    report["broker_truth_authoritative"] = bool(
        client is not None and not report.get("broker_truth_refresh_error")
    )
    report["broker_truth_after"] = _broker_truth_snapshot(
        account=truth_account,
        positions=truth_positions,
        open_orders=truth_orders,
        intraday_managed_symbols=intraday_managed_symbols,
    )
    protection_fatal = False
    protection_policy_violations: list[dict[str, Any]] = []
    if send_orders and broker_protection_required:
        truth = report["broker_truth_after"]
        if protection_preflight_violations:
            protection_fatal = True
            report["fatal_protection_error"] = "pre_action_protective_floor_not_confirmed"
        if not report["broker_truth_authoritative"]:
            protection_fatal = True
            report["fatal_protection_error"] = "post_action_broker_truth_not_confirmed"
        elif not bool(truth.get("stop_coverage_complete")):
            protection_fatal = True
            report["fatal_protection_error"] = "post_action_broker_stop_coverage_incomplete"
        if (
            report["broker_truth_authoritative"]
            and broker_protection_order_class == "simple_stop"
        ):
            final_floor_state, final_floor_error = _load_protective_floor_state(
                protective_floor_state_path
            )
            if final_floor_error and int(truth.get("position_count") or 0) > 0:
                protection_policy_violations.append(
                    {
                        "symbol": "*",
                        "reason": "protective_floor_state_not_authoritative",
                        "state_error": final_floor_error,
                    }
                )
            protection_policy_violations.extend(
                _broker_protection_policy_violations(
                    positions=truth_positions,
                    open_orders=truth_orders,
                    intraday_managed_symbols=intraday_managed_symbols,
                    protective_floor_state=final_floor_state,
                    requested_tif=broker_protection_tif_requested,
                )
            )
            if protection_policy_violations:
                protection_fatal = True
                report["fatal_protection_error"] = (
                    "post_action_broker_stop_policy_not_confirmed"
                )
    report["protection_policy_violations"] = protection_policy_violations
    report["protection_gate_passed"] = not protection_fatal
    report["protection_gate_status"] = "PASS" if not protection_fatal else "NOT_CONFIRMED"

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

    manager_receipt_path = picks_csv.parent / "latest_manager_receipt.json"
    report["manager_receipt_path"] = str(manager_receipt_path)
    _write_manager_receipt(manager_receipt_path, report)

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

    return 4 if protection_fatal else 0


def main() -> int:
    """Run one broker cycle under a bounded-wait per-account writer lock."""
    lock_path = _alpaca_account_lock_path(
        _env("ALPACA_BASE_URL"),
        _env("ALPACA_API_KEY_ID"),
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(lock_path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            print("error=alpaca_bridge_lock_not_regular", file=sys.stderr)
            return 75
        os.fchmod(fd, 0o600)
        if not _acquire_account_writer_lock(
            fd,
            _env_float("ALPACA_WRITER_LOCK_WAIT_SEC", 60.0),
        ):
            print("status=failed_single_writer_lock_timeout", file=sys.stderr)
            return 75
        return _main_unlocked()
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


if __name__ == "__main__":
    raise SystemExit(main())
