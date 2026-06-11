"""Extra endpoints — live positions, monthly P&L, AI code reader, AI position actions.

Wire-up in web/main.py:

    from .routes.extra_routes import router as extra_router
    app.include_router(extra_router)

These endpoints answer four user requests:

  1. /api/positions/live      — current open positions snapshot from Bybit
  2. /api/pnl/monthly         — per-month income/expense breakdown
  3. /api/ai/code-search      — AI reads project files (read-only, sandboxed)
  4. /api/ai/propose-position-action — AI proposes close/move-SL/TP, user confirms

All endpoints respect `require_auth`. AI position actions require explicit user
confirmation via PUT (with action_id); they NEVER auto-execute.

Author: Claude Opus, 2026-06-03. Backend for journal upgrades.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import ssl
import time
import urllib.parse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib import error, request

from fastapi import APIRouter, Depends, HTTPException, Body, Path as PathParam
from pydantic import BaseModel

from ..deps import require_auth, require_admin


router = APIRouter(prefix="/api", tags=["extra"])

_ROOT = Path(__file__).parent.parent.parent
_RUNTIME = _ROOT / "runtime"
_LIVE_EVENTS = _RUNTIME / "live_mirror" / "live_trade_events.jsonl"
_PENDING_ACTIONS = _RUNTIME / "ai_position_actions.jsonl"
_SSL = ssl.create_default_context()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(p: Path, default: Any = None) -> Any:
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _tail_events(n: int = 20000) -> list[dict[str, Any]]:
    if not _LIVE_EVENTS.exists():
        return []
    try:
        with _LIVE_EVENTS.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()[-n:]
    except Exception:
        return []
    out = []
    for raw in lines:
        try:
            out.append(json.loads(raw))
        except Exception:
            continue
    return out


# ---------------------------------------------------------------------------
# 1) Live positions snapshot — pulls from Bybit /v5/position/list
# ---------------------------------------------------------------------------

def _bybit_signed_get(path: str, params: dict[str, str]) -> Any:
    key = (os.getenv("BYBIT_API_KEY") or "").strip()
    secret = (os.getenv("BYBIT_API_SECRET") or "").strip()
    if not (key and secret):
        return {"_error": "missing_bybit_credentials"}
    ts = str(int(time.time() * 1000))
    recv = "5000"
    query = urllib.parse.urlencode(sorted(params.items())) if params else ""
    payload = f"{ts}{key}{recv}{query}"
    sign = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    url = f"https://api.bybit.com{path}" + (f"?{query}" if query else "")
    req = request.Request(
        url,
        headers={
            "X-BAPI-API-KEY": key,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": recv,
            "X-BAPI-SIGN": sign,
        },
    )
    try:
        with request.urlopen(req, context=_SSL, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"_error": f"{type(exc).__name__}:{str(exc)[:120]}"}


@router.get("/positions/live")
async def positions_live(_: str = Depends(require_auth)):
    """Returns current open positions on Bybit linear futures."""
    data = _bybit_signed_get("/v5/position/list", {"category": "linear", "settleCoin": "USDT"})
    if isinstance(data, dict) and "_error" in data:
        raise HTTPException(status_code=502, detail=data["_error"])
    rows = (data.get("result") or {}).get("list") if isinstance(data, dict) else []
    positions = []
    for r in rows or []:
        try:
            size = abs(float(r.get("size") or 0.0))
        except Exception:
            size = 0.0
        if size <= 0:
            continue
        positions.append({
            "symbol": r.get("symbol"),
            "side": r.get("side"),
            "size": size,
            "avg_price": float(r.get("avgPrice") or 0.0),
            "mark_price": float(r.get("markPrice") or 0.0),
            "unrealized_pnl": float(r.get("unrealisedPnl") or 0.0),
            "stop_loss": str(r.get("stopLoss") or "").strip(),
            "take_profit": str(r.get("takeProfit") or "").strip(),
            "position_idx": r.get("positionIdx"),
            "leverage": float(r.get("leverage") or 0.0),
            "created_time": r.get("createdTime"),
            "updated_time": r.get("updatedTime"),
        })
    return {
        "generated_at_utc": _utc_now(),
        "positions": positions,
        "count": len(positions),
    }


# ---------------------------------------------------------------------------
# 2) Monthly P&L breakdown
# ---------------------------------------------------------------------------

@router.get("/pnl/monthly")
async def pnl_monthly(_: str = Depends(require_auth)):
    """Returns per-month income/expense breakdown from live_trade_events.jsonl."""
    events = _tail_events(20000)
    by_month: dict[str, dict[str, float]] = defaultdict(
        lambda: {"trades": 0, "wins": 0, "losses": 0,
                 "gross_profit": 0.0, "gross_loss": 0.0,
                 "fees": 0.0, "net_pnl": 0.0}
    )
    for ev in events:
        if str(ev.get("event") or "") != "close":
            continue
        try:
            ts = int(ev.get("ts") or 0)
            if ts <= 0:
                continue
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            month = dt.strftime("%Y-%m")
            pnl = float(ev.get("pnl") or 0.0)
            fee = float(ev.get("fees") or 0.0)
            b = by_month[month]
            b["trades"] += 1
            b["net_pnl"] += pnl
            b["fees"] += fee
            if pnl > 0:
                b["wins"] += 1
                b["gross_profit"] += pnl
            else:
                b["losses"] += 1
                b["gross_loss"] += abs(pnl)
        except Exception:
            continue

    months = []
    for m, b in sorted(by_month.items()):
        wr = (b["wins"] / b["trades"] * 100.0) if b["trades"] > 0 else 0.0
        pf = (b["gross_profit"] / b["gross_loss"]) if b["gross_loss"] > 0 else (99.0 if b["gross_profit"] > 0 else 0.0)
        months.append({
            "month": m,
            "trades": int(b["trades"]),
            "winrate_pct": round(wr, 2),
            "profit_factor": round(pf, 3),
            "gross_profit": round(b["gross_profit"], 4),
            "gross_loss": round(b["gross_loss"], 4),
            "fees": round(b["fees"], 4),
            "net_pnl": round(b["net_pnl"], 4),
        })

    total_net = sum(m["net_pnl"] for m in months)
    total_trades = sum(m["trades"] for m in months)
    return {
        "generated_at_utc": _utc_now(),
        "months": months,
        "totals": {
            "trades": total_trades,
            "net_pnl": round(total_net, 4),
            "total_fees": round(sum(m["fees"] for m in months), 4),
        },
    }


# ---------------------------------------------------------------------------
# 3) AI Code Reader — grep + read with sandboxing
# ---------------------------------------------------------------------------

# Allowed roots (no traversal outside)
_ALLOWED_ROOTS = ["strategies", "bot", "scripts", "configs", "web", "docs", "backtest", "runtime/ai_context", "runtime/strategy_pipeline.json", "runtime/strategy_registry.json"]
_MAX_GREP_RESULTS = 100
_MAX_READ_LINES = 400


def _safe_path(rel: str) -> Optional[Path]:
    """Resolve a path safely, return None if outside allowed roots."""
    if not rel or ".." in rel.split("/"):
        return None
    p = (_ROOT / rel).resolve()
    try:
        p.relative_to(_ROOT.resolve())
    except ValueError:
        return None
    # Must be under allowed root
    rel_norm = str(p.relative_to(_ROOT.resolve()))
    if not any(rel_norm == r or rel_norm.startswith(r + "/") for r in _ALLOWED_ROOTS):
        return None
    return p


class CodeSearchRequest(BaseModel):
    mode: str  # "read" | "grep" | "list"
    path: Optional[str] = None
    pattern: Optional[str] = None
    glob: Optional[str] = None  # e.g. "strategies/**/*.py"
    line_start: Optional[int] = None
    line_end: Optional[int] = None


@router.post("/ai/code-search")
async def ai_code_search(body: CodeSearchRequest, _: str = Depends(require_auth)):
    """Read-only code search/inspection for AI agent."""
    mode = (body.mode or "").strip().lower()

    if mode == "list":
        # List files matching glob within allowed roots
        glob_pat = body.glob or "**/*.py"
        # Constrain glob to a single allowed root
        root_match = next((r for r in _ALLOWED_ROOTS if glob_pat.startswith(r + "/") or glob_pat == r), None)
        if not root_match:
            raise HTTPException(status_code=400, detail="glob must start with an allowed root: " + ",".join(_ALLOWED_ROOTS))
        files = []
        for p in (_ROOT / root_match).rglob(Path(glob_pat).name):
            try:
                rel = str(p.relative_to(_ROOT))
                files.append(rel)
            except Exception:
                continue
            if len(files) >= 500:
                break
        return {"mode": "list", "files": files[:500], "count": len(files[:500])}

    if mode == "read":
        if not body.path:
            raise HTTPException(status_code=400, detail="path required")
        p = _safe_path(body.path)
        if p is None or not p.exists() or not p.is_file():
            raise HTTPException(status_code=404, detail="path not found or outside allowed roots")
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"read failed: {exc}")
        start = max(1, body.line_start or 1)
        end = min(len(lines), body.line_end or (start + _MAX_READ_LINES - 1))
        if end - start + 1 > _MAX_READ_LINES:
            end = start + _MAX_READ_LINES - 1
        snippet = "\n".join(f"{i+1:6d}\t{ln}" for i, ln in enumerate(lines[start-1:end], start=start-1))
        return {
            "mode": "read",
            "path": body.path,
            "line_start": start,
            "line_end": end,
            "total_lines": len(lines),
            "content": snippet,
        }

    if mode == "grep":
        if not body.pattern:
            raise HTTPException(status_code=400, detail="pattern required")
        try:
            pat = re.compile(body.pattern)
        except re.error as exc:
            raise HTTPException(status_code=400, detail=f"invalid regex: {exc}")
        glob_pat = body.glob or "**/*.py"
        root_match = next((r for r in _ALLOWED_ROOTS if glob_pat.startswith(r + "/") or glob_pat == r), None)
        if not root_match:
            raise HTTPException(status_code=400, detail="glob must start with an allowed root")
        results = []
        for p in (_ROOT / root_match).rglob(Path(glob_pat).name):
            try:
                for i, ln in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                    if pat.search(ln):
                        results.append({"path": str(p.relative_to(_ROOT)), "line": i, "text": ln[:200]})
                        if len(results) >= _MAX_GREP_RESULTS:
                            break
            except Exception:
                continue
            if len(results) >= _MAX_GREP_RESULTS:
                break
        return {"mode": "grep", "pattern": body.pattern, "matches": results, "count": len(results)}

    raise HTTPException(status_code=400, detail="mode must be 'list', 'read', or 'grep'")


# ---------------------------------------------------------------------------
# 4) AI proposes position action; user confirms via separate call.
# ---------------------------------------------------------------------------

class ProposePositionActionRequest(BaseModel):
    symbol: str
    action: str  # "close" | "move_sl" | "move_tp"
    new_sl: Optional[float] = None
    new_tp: Optional[float] = None
    reason: str  # AI explanation


class ConfirmPositionActionRequest(BaseModel):
    action_id: str
    confirm: bool


def _append_pending_action(entry: dict[str, Any]) -> None:
    _PENDING_ACTIONS.parent.mkdir(parents=True, exist_ok=True)
    with _PENDING_ACTIONS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


@router.post("/ai/propose-position-action")
async def ai_propose_position_action(
    body: ProposePositionActionRequest,
    _: str = Depends(require_admin),
):
    """AI proposes an action on a current open position. User must confirm via /confirm-position-action."""
    if body.action not in {"close", "move_sl", "move_tp"}:
        raise HTTPException(status_code=400, detail="action must be one of: close, move_sl, move_tp")
    action_id = hashlib.sha256(
        f"{body.symbol}{body.action}{body.new_sl}{body.new_tp}{time.time()}".encode()
    ).hexdigest()[:16]
    entry = {
        "action_id": action_id,
        "proposed_at_utc": _utc_now(),
        "symbol": body.symbol.upper(),
        "action": body.action,
        "new_sl": body.new_sl,
        "new_tp": body.new_tp,
        "reason": body.reason,
        "status": "pending",
    }
    _append_pending_action(entry)
    return entry


@router.post("/ai/confirm-position-action")
async def ai_confirm_position_action(
    body: ConfirmPositionActionRequest,
    _: str = Depends(require_admin),
):
    """User confirms (or denies) the action. Only on confirm=True we hit Bybit."""
    # Find the action in pending log
    if not _PENDING_ACTIONS.exists():
        raise HTTPException(status_code=404, detail="no pending actions file")
    matching: Optional[dict[str, Any]] = None
    try:
        with _PENDING_ACTIONS.open("r", encoding="utf-8") as fh:
            for raw in fh:
                try:
                    ev = json.loads(raw)
                except Exception:
                    continue
                if ev.get("action_id") == body.action_id and ev.get("status") == "pending":
                    matching = ev
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"action log read failed: {exc}")
    if matching is None:
        raise HTTPException(status_code=404, detail="action_id not found or already resolved")

    if not body.confirm:
        # Mark denied
        matching["status"] = "denied"
        matching["resolved_at_utc"] = _utc_now()
        _append_pending_action({"_resolution": True, **matching})
        return {"action_id": body.action_id, "result": "denied"}

    # Execute (POST to Bybit)
    sym = str(matching["symbol"]).upper()
    act = matching["action"]
    # Build the trading-stop or close body
    if act == "close":
        # /v5/order/create reduce-only opposite side
        positions = _bybit_signed_get("/v5/position/list", {"category": "linear", "symbol": sym})
        rows = (positions.get("result") or {}).get("list") or []
        active = next((p for p in rows if abs(float(p.get("size") or 0.0)) > 0), None)
        if not active:
            matching["status"] = "no_active_position"
            _append_pending_action({"_resolution": True, **matching})
            return {"action_id": body.action_id, "result": "no_active_position"}
        side_close = "Sell" if str(active.get("side")) == "Buy" else "Buy"
        # NOTE: implementation hands off to a separate executor — see CODEX note below.
        matching["status"] = "queued_for_executor"
        matching["queued_payload"] = {"action": "close", "symbol": sym, "side": side_close,
                                       "qty": str(active.get("size"))}
        _append_pending_action({"_resolution": True, **matching})
        return {"action_id": body.action_id, "result": "queued_for_executor",
                "payload": matching["queued_payload"]}

    if act in {"move_sl", "move_tp"}:
        body_payload: dict[str, str] = {"category": "linear", "symbol": sym, "tpslMode": "Full"}
        if act == "move_sl" and matching.get("new_sl"):
            body_payload["stopLoss"] = f"{float(matching['new_sl']):.8f}"
        if act == "move_tp" and matching.get("new_tp"):
            body_payload["takeProfit"] = f"{float(matching['new_tp']):.8f}"
        matching["status"] = "queued_for_executor"
        matching["queued_payload"] = body_payload
        _append_pending_action({"_resolution": True, **matching})
        return {"action_id": body.action_id, "result": "queued_for_executor",
                "payload": body_payload}

    raise HTTPException(status_code=400, detail="unsupported action")


# ---------------------------------------------------------------------------
# 5) API Keys CRUD — flexible exchange key management
# ---------------------------------------------------------------------------

_EXCHANGE_KEYS_FILE = _ROOT / "configs" / "exchange_keys.env"
_KEYS_BACKUP = _RUNTIME / "secrets_backup"
_SUPPORTED_EXCHANGES = {"binance", "bitget", "mexc", "okx"}
_KEYS_FIELDS = {
    "binance": ("BINANCE_API_KEY", "BINANCE_API_SECRET"),
    "bitget":  ("BITGET_API_KEY", "BITGET_API_SECRET", "BITGET_API_PASSPHRASE"),
    "mexc":    ("MEXC_API_KEY", "MEXC_API_SECRET"),
    "okx":     ("OKX_API_KEY", "OKX_API_SECRET", "OKX_API_PASSPHRASE"),
}


def _read_keys_file() -> dict[str, str]:
    if not _EXCHANGE_KEYS_FILE.exists():
        return {}
    out: dict[str, str] = {}
    for raw in _EXCHANGE_KEYS_FILE.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _write_keys_file(env_map: dict[str, str]) -> None:
    _EXCHANGE_KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Managed by web/routes/extra_routes.py — do not edit by hand if web UI is used.",
             f"# Last update: {_utc_now()}", ""]
    for k in sorted(env_map):
        if env_map[k]:
            lines.append(f"{k}={env_map[k]}")
    _EXCHANGE_KEYS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(_EXCHANGE_KEYS_FILE, 0o600)
    except Exception:
        pass


def _backup_keys_file() -> None:
    if not _EXCHANGE_KEYS_FILE.exists():
        return
    _KEYS_BACKUP.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dst = _KEYS_BACKUP / f"exchange_keys_{ts}.env"
    try:
        dst.write_text(_EXCHANGE_KEYS_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        os.chmod(dst, 0o600)
    except Exception:
        pass


@router.get("/admin/exchange-keys")
async def list_exchange_keys(_: str = Depends(require_admin)):
    """List configured exchanges — returns ONLY presence flags, never values."""
    env_map = _read_keys_file()
    out = {}
    for ex in _SUPPORTED_EXCHANGES:
        fields = _KEYS_FIELDS[ex]
        configured = all(env_map.get(f) for f in fields)
        out[ex] = {
            "configured": configured,
            "fields": list(fields),
            "missing": [f for f in fields if not env_map.get(f)] if not configured else [],
        }
    return {"exchanges": out, "generated_at_utc": _utc_now()}


class KeyUpsertRequest(BaseModel):
    api_key: str
    api_secret: str
    passphrase: Optional[str] = None


@router.put("/admin/exchange-keys/{exchange}")
async def upsert_exchange_keys(
    body: KeyUpsertRequest,
    exchange: str = PathParam(...),
    _: str = Depends(require_admin),
):
    ex = exchange.strip().lower()
    if ex not in _SUPPORTED_EXCHANGES:
        raise HTTPException(status_code=400, detail=f"unsupported exchange '{ex}'")
    fields = _KEYS_FIELDS[ex]
    if len(fields) == 3 and not body.passphrase:
        raise HTTPException(status_code=400, detail=f"{ex} requires passphrase")

    _backup_keys_file()
    env_map = _read_keys_file()
    env_map[fields[0]] = body.api_key.strip()
    env_map[fields[1]] = body.api_secret.strip()
    if len(fields) == 3 and body.passphrase:
        env_map[fields[2]] = body.passphrase.strip()
    _write_keys_file(env_map)
    return {"exchange": ex, "configured": True, "ts_utc": _utc_now()}


@router.delete("/admin/exchange-keys/{exchange}")
async def delete_exchange_keys(
    exchange: str = PathParam(...),
    _: str = Depends(require_admin),
):
    ex = exchange.strip().lower()
    if ex not in _SUPPORTED_EXCHANGES:
        raise HTTPException(status_code=400, detail=f"unsupported exchange '{ex}'")
    _backup_keys_file()
    env_map = _read_keys_file()
    for f in _KEYS_FIELDS[ex]:
        env_map.pop(f, None)
    _write_keys_file(env_map)
    return {"exchange": ex, "configured": False, "ts_utc": _utc_now()}
