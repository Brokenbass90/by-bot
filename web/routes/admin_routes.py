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
from ..deps import require_auth

router = APIRouter(prefix="/api/admin", tags=["admin"])

_ROOT = Path(__file__).parent.parent.parent


def _rt(*p: str) -> Path:
    return _ROOT / "runtime" / Path(*p)


# ── User management ───────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(email: str = Depends(require_auth)):
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
async def add_user(body: AddUserRequest, email: str = Depends(require_auth)):
    """Pre-create user slot (TOTP setup still required via CLI)."""
    target = body.email.strip().lower()
    if not target or "@" not in target:
        raise HTTPException(status_code=400, detail="Invalid email")

    cfg = _load_config()
    cfg.setdefault("users", {})[target] = {
        "enabled": False,
        "note": body.note or "pending_totp_setup",
    }
    _save_config(cfg)
    return {"created": target, "message": f"Slot created. Run: python3 web/setup_totp.py --email {target}"}


@router.delete("/users/{target_email}")
async def remove_user(target_email: str, email: str = Depends(require_auth)):
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
async def toggle_user(target_email: str, email: str = Depends(require_auth)):
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

def _load_all_trades() -> List[Dict[str, Any]]:
    seen: set = set()
    trades: List[Dict[str, Any]] = []
    paths = sorted(
        list(_ROOT.glob("runtime/**/trades.csv")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    root_csv = _ROOT / "trades.csv"
    if root_csv.exists():
        paths.insert(0, root_csv)

    for csv_path in paths[:5]:
        try:
            with open(csv_path, newline="") as f:
                for row in csv.DictReader(f):
                    key = (row.get("strategy"), row.get("symbol"), row.get("open_time"), row.get("entry"))
                    if key in seen:
                        continue
                    seen.add(key)
                    for field in ("pnl", "entry", "exit", "size"):
                        if row.get(field):
                            try:
                                row[field] = float(row[field])
                            except ValueError:
                                pass
                    trades.append(dict(row))
        except Exception:
            pass

    return trades


@router.get("/stats/daily")
async def daily_stats(_: str = Depends(require_auth)):
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
async def monthly_stats(_: str = Depends(require_auth)):
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
async def get_audit(_: str = Depends(require_auth)):
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
