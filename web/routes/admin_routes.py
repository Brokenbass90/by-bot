"""Admin routes: user management + daily P&L stats."""

from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth import _load_config, _save_config, hash_password
from ..deps import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

_ROOT = Path(__file__).parent.parent.parent
_RUNTIME_ROOT = Path(os.getenv("WEB_RUNTIME_ROOT", str(_ROOT / "runtime")))


def _rt(*p: str) -> Path:
    return _RUNTIME_ROOT / Path(*p)


# ── User management ───────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(email: str = Depends(require_admin)):
    """List all users in web_config.json."""
    cfg = _load_config()
    users = []
    for em, data in cfg.get("users", {}).items():
        users.append({
            "email": em,
            "enabled": data.get("enabled", True),
            "has_totp": bool(data.get("totp_secret")),
            "has_password": bool(data.get("hashed_password")),
            "note": data.get("note", ""),
        })
    return {"users": users}


class AddUserRequest(BaseModel):
    email: str
    note: Optional[str] = ""


@router.post("/users")
async def add_user(body: AddUserRequest, email: str = Depends(require_admin)):
    """Pre-create user slot (TOTP setup still required via CLI)."""
    target = body.email.strip().lower()
    if not target or "@" not in target:
        raise HTTPException(status_code=400, detail="Invalid email")

    cfg = _load_config()
    cfg.setdefault("users", {})[target] = {
        "enabled": False,
        "is_admin": False,
        "note": body.note or "pending_totp_setup",
    }
    _save_config(cfg)
    return {"created": target, "message": f"Slot created. Run: python3 web/setup_totp.py --email {target}"}


@router.delete("/users/{target_email}")
async def remove_user(target_email: str, email: str = Depends(require_admin)):
    target = target_email.strip().lower()
    if target == email:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    cfg = _load_config()
    users = cfg.get("users", {})
    if target not in users:
        raise HTTPException(status_code=404, detail="User not found")

    del users[target]
    cfg["users"] = users
    _save_config(cfg)
    return {"removed": target}


@router.post("/users/{target_email}/toggle")
async def toggle_user(target_email: str, email: str = Depends(require_admin)):
    target = target_email.strip().lower()
    if target == email:
        raise HTTPException(status_code=400, detail="Cannot disable yourself")

    cfg = _load_config()
    users = cfg.get("users", {})
    if target not in users:
        raise HTTPException(status_code=404, detail="User not found")

    current = users[target].get("enabled", True)
    users[target]["enabled"] = not current
    cfg["users"] = users
    _save_config(cfg)
    return {"email": target, "enabled": not current}


# ── Daily P&L stats ───────────────────────────────────────────────────────────

def _normalise_ts(raw: str) -> str:
    """Convert ms-epoch or ISO timestamp to YYYY-MM-DD HH:MM string."""
    if raw and str(raw).isdigit():
        try:
            return datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
    return str(raw)


def _load_all_trades() -> List[Dict[str, Any]]:
    """Load trades, normalising both old and new CSV schemas to canonical field names."""
    seen: set = set()
    trades: List[Dict[str, Any]] = []
    paths = sorted(
        list(_RUNTIME_ROOT.glob("**/trades.csv")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    root_csv = _RUNTIME_ROOT / "trades.csv"
    if not root_csv.exists():
        root_csv = _ROOT / "trades.csv"
    if root_csv.exists():
        paths.insert(0, root_csv)

    for csv_path in paths[:5]:
        try:
            with open(csv_path, newline="") as f:
                for row in csv.DictReader(f):
                    t = dict(row)
                    # new schema → canonical
                    if "exit_ts" in t and "close_time" not in t:
                        t["close_time"] = _normalise_ts(t["exit_ts"])
                    if "entry_ts" in t and "open_time" not in t:
                        t["open_time"] = _normalise_ts(t["entry_ts"])
                    if "entry_price" in t and "entry" not in t:
                        t["entry"] = t["entry_price"]
                    if "exit_price" in t and "exit" not in t:
                        t["exit"] = t["exit_price"]
                    if "qty" in t and "size" not in t:
                        t["size"] = t["qty"]
                    if "pnl_pct_equity" in t and "pnl_pct" not in t:
                        t["pnl_pct"] = t["pnl_pct_equity"]

                    key = (t.get("strategy"), t.get("symbol"), t.get("open_time"), t.get("entry"))
                    if key in seen:
                        continue
                    seen.add(key)

                    for field in ("pnl", "entry", "exit", "size", "fees", "pnl_pct"):
                        if t.get(field):
                            try:
                                t[field] = float(t[field])
                            except (ValueError, TypeError):
                                pass
                    trades.append(t)
        except Exception:
            pass

    if trades:
        return trades

    live_jsonl = _rt("live_trade_events.jsonl")
    if live_jsonl.exists():
        buckets: Dict[str, Dict[str, Any]] = {}
        try:
            for raw in live_jsonl.read_text(errors="ignore").splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    evt = json.loads(raw)
                except Exception:
                    continue
                event_name = str(evt.get("event") or "").strip().lower()
                if event_name not in {"order_submitted", "entry_filled", "close"}:
                    continue
                order_id = str(evt.get("entry_order_id") or "").strip()
                if not order_id:
                    order_id = "|".join(
                        [
                            str(evt.get("symbol") or ""),
                            str(evt.get("strategy") or ""),
                            str(evt.get("side") or ""),
                            str(evt.get("ts") or ""),
                        ]
                    )
                rec = buckets.setdefault(order_id, {})
                rec.update({k: v for k, v in evt.items() if v not in (None, "")})
                if event_name == "order_submitted":
                    rec.setdefault("entry_ts", int(evt.get("ts") or 0))
                elif event_name == "entry_filled":
                    rec["entry_ts"] = int(evt.get("ts") or rec.get("entry_ts") or 0)
                elif event_name == "close":
                    rec["exit_ts"] = int(evt.get("ts") or 0)
            for rec in buckets.values():
                if not rec.get("exit_ts"):
                    continue
                side_raw = str(rec.get("side") or "").strip().lower()
                side = "short" if side_raw in {"sell", "short"} else "long"
                entry_ts = int(rec.get("entry_ts") or 0)
                exit_ts = int(rec.get("exit_ts") or 0)
                entry_notional = float(rec.get("entry_notional_usd") or 0.0)
                pnl = float(rec.get("pnl") or 0.0)
                trades.append({
                    "strategy": str(rec.get("strategy") or ""),
                    "symbol": str(rec.get("symbol") or "").upper(),
                    "side": side,
                    "open_time": datetime.fromtimestamp(entry_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if entry_ts else "",
                    "close_time": datetime.fromtimestamp(exit_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if exit_ts else "",
                    "entry": float(rec.get("entry_price") or 0.0),
                    "exit": float(rec.get("exit_price") or 0.0),
                    "pnl": pnl,
                    "fees": float(rec.get("fees") or 0.0),
                    "pnl_pct": (pnl / entry_notional * 100.0) if entry_notional > 0 else None,
                })
        except Exception:
            pass
    return trades


@router.get("/stats/daily")
async def daily_stats(_: str = Depends(require_admin)):
    """P&L aggregated by day + strategy breakdown per day."""
    trades = _load_all_trades()

    by_day: Dict[str, dict] = defaultdict(lambda: {
        "date": "",
        "net": 0.0,
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "by_strategy": defaultdict(float),
    })

    for t in trades:
        pnl = t.get("pnl")
        if not isinstance(pnl, float):
            continue
        # Get date from close_time or time
        raw_time = t.get("close_time") or t.get("time") or ""
        date = str(raw_time)[:10]
        if not date or date == "":
            continue

        rec = by_day[date]
        rec["date"] = date
        rec["net"] = round(rec["net"] + pnl, 6)
        rec["trades"] += 1
        if pnl > 0:
            rec["wins"] += 1
        elif pnl < 0:
            rec["losses"] += 1
        strat = t.get("strategy", "unknown")
        rec["by_strategy"][strat] = round(rec["by_strategy"][strat] + pnl, 6)

    # Convert to list, sort by date
    result = []
    running = 0.0
    for date in sorted(by_day.keys()):
        rec = by_day[date]
        running = round(running + rec["net"], 6)
        result.append({
            "date": date,
            "net": round(rec["net"], 4),
            "cumulative": round(running, 4),
            "trades": rec["trades"],
            "wins": rec["wins"],
            "losses": rec["losses"],
            "by_strategy": dict(rec["by_strategy"]),
        })

    return {
        "days": list(reversed(result)),  # newest first
        "total_days": len(result),
        "green_days": sum(1 for d in result if d["net"] > 0),
        "red_days": sum(1 for d in result if d["net"] < 0),
        "total_net": round(running, 4),
    }


@router.get("/stats/monthly")
async def monthly_stats(_: str = Depends(require_admin)):
    """P&L aggregated by month."""
    trades = _load_all_trades()

    by_month: Dict[str, dict] = defaultdict(lambda: {
        "month": "", "net": 0.0, "trades": 0, "wins": 0, "losses": 0,
    })

    for t in trades:
        pnl = t.get("pnl")
        if not isinstance(pnl, float):
            continue
        raw_time = t.get("close_time") or t.get("time") or ""
        month = str(raw_time)[:7]
        if not month:
            continue
        rec = by_month[month]
        rec["month"] = month
        rec["net"] = round(rec["net"] + pnl, 6)
        rec["trades"] += 1
        if pnl > 0:
            rec["wins"] += 1
        elif pnl < 0:
            rec["losses"] += 1

    result = [by_month[m] for m in sorted(by_month.keys())]
    running = 0.0
    for rec in result:
        running = round(running + rec["net"], 6)
        rec["cumulative"] = round(running, 4)

    return {"months": list(reversed(result))}


# ── Audit log ─────────────────────────────────────────────────────────────────

@router.get("/audit")
async def get_audit(_: str = Depends(require_admin)):
    """Web command audit log."""
    audit_path = _rt("web_audit_log.jsonl")
    if not audit_path.exists():
        return {"entries": []}
    entries = []
    for line in audit_path.read_text().splitlines()[-100:]:
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return {"entries": list(reversed(entries))}
