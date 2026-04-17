"""Read-only data endpoints: trades, account, regime, allocator, health, journal."""

from __future__ import annotations

import csv
import json
import math
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import require_auth

router = APIRouter(prefix="/api", tags=["data"])

# ── path helpers ──────────────────────────────────────────────────────────────

_ROOT = Path(__file__).parent.parent.parent  # project root


def _runtime(*parts: str) -> Path:
    return _ROOT / "runtime" / Path(*parts)


def _configs(*parts: str) -> Path:
    return _ROOT / "configs" / Path(*parts)


def _json_or_none(p: Path) -> Optional[dict]:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _find_trades_csv() -> Optional[Path]:
    """Find the most recently modified trades.csv anywhere under runtime/."""
    candidates = sorted(
        _ROOT.glob("runtime/**/trades.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0]
    # Fallback: project root
    p = _ROOT / "trades.csv"
    return p if p.exists() else None


# ── trades ────────────────────────────────────────────────────────────────────

def _load_trades(path: Path) -> List[Dict[str, Any]]:
    """Parse trades.csv into list of dicts. Handles missing/empty gracefully."""
    if not path or not path.exists():
        return []
    trades = []
    try:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Normalise numeric fields
                for field in ("entry", "exit", "pnl", "pnl_pct", "size", "risk"):
                    if field in row and row[field]:
                        try:
                            row[field] = float(row[field])
                        except ValueError:
                            pass
                trades.append(dict(row))
    except Exception:
        pass
    return trades


@router.get("/trades")
async def get_trades(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    strategy: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    side: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    _email: str = Depends(require_auth),
):
    """Paginated trade log with optional filters."""
    csv_path = _find_trades_csv()
    trades = _load_trades(csv_path)

    # Apply filters
    if strategy:
        trades = [t for t in trades if t.get("strategy", "").lower() == strategy.lower()]
    if symbol:
        trades = [t for t in trades if t.get("symbol", "").upper() == symbol.upper()]
    if side:
        trades = [t for t in trades if t.get("side", "").lower() == side.lower()]
    if date_from:
        trades = [t for t in trades if str(t.get("open_time", t.get("time", ""))) >= date_from]
    if date_to:
        trades = [t for t in trades if str(t.get("open_time", t.get("time", ""))) <= date_to]

    # Sort newest first
    trades = sorted(
        trades,
        key=lambda t: str(t.get("close_time", t.get("time", ""))),
        reverse=True,
    )

    total = len(trades)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total else 1,
        "trades": trades[start:end],
    }


@router.get("/trades/summary")
async def get_trades_summary(_email: str = Depends(require_auth)):
    """Per-strategy PF, win-rate, net PnL, trade count."""
    csv_path = _find_trades_csv()
    trades = _load_trades(csv_path)

    by_strategy: Dict[str, Dict] = defaultdict(lambda: {
        "wins": 0, "losses": 0, "gross_win": 0.0, "gross_loss": 0.0, "net": 0.0,
    })

    for t in trades:
        strat = t.get("strategy", "unknown")
        pnl = t.get("pnl", 0.0)
        if not isinstance(pnl, float):
            continue
        rec = by_strategy[strat]
        if pnl > 0:
            rec["wins"] += 1
            rec["gross_win"] += pnl
        elif pnl < 0:
            rec["losses"] += 1
            rec["gross_loss"] += abs(pnl)
        rec["net"] += pnl

    result = []
    for strat, rec in sorted(by_strategy.items()):
        total_t = rec["wins"] + rec["losses"]
        pf = (rec["gross_win"] / rec["gross_loss"]) if rec["gross_loss"] > 0 else None
        result.append({
            "strategy": strat,
            "trades": total_t,
            "wins": rec["wins"],
            "losses": rec["losses"],
            "win_rate": round(rec["wins"] / total_t * 100, 1) if total_t else 0,
            "profit_factor": round(pf, 3) if pf is not None else None,
            "net_pnl": round(rec["net"], 4),
        })

    return {"strategies": result, "total_trades": len(trades)}


# ── account ───────────────────────────────────────────────────────────────────

@router.get("/account")
async def get_account(_email: str = Depends(require_auth)):
    """Current account snapshot from operator_snapshot.json."""
    snap = _json_or_none(_runtime("operator", "operator_snapshot.json"))
    if snap is None:
        # Try alternate path
        snap = _json_or_none(_runtime("operator_snapshot.json"))
    if snap is None:
        return {"error": "operator_snapshot.json not found — run the operator script first"}
    return snap


# ── regime ────────────────────────────────────────────────────────────────────

@router.get("/regime")
async def get_regime(_email: str = Depends(require_auth)):
    """Current market regime from runtime/regime.json."""
    data = _json_or_none(_runtime("regime.json"))
    if data is None:
        return {"regime": "UNKNOWN", "error": "regime.json not found"}
    return data


# ── allocator ─────────────────────────────────────────────────────────────────

@router.get("/allocator")
async def get_allocator(_email: str = Depends(require_auth)):
    """Portfolio allocator policy and latest computed values."""
    policy = _json_or_none(_configs("portfolio_allocator_policy.json"))
    latest_env_path = _configs("portfolio_allocator_latest.env")

    env_vals: Dict[str, str] = {}
    if latest_env_path.exists():
        for line in latest_env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env_vals[k.strip()] = v.strip()

    return {
        "policy": policy,
        "latest_env": env_vals,
    }


# ── health ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def get_health(_email: str = Depends(require_auth)):
    """Strategy health data."""
    health = _json_or_none(_runtime("strategy_health.json"))
    timeline = _json_or_none(_runtime("strategy_health_timeline.json"))
    return {
        "current": health,
        "timeline": timeline,
    }


# ── journal ───────────────────────────────────────────────────────────────────

_DATE_HEADER_RE = re.compile(r"^#+\s*(\d{4}-\d{2}-\d{2})")
_SESSION_HEADER_RE = re.compile(r"^#+\s*(Session|Сессия|##)")


def _parse_journal(path: Path) -> List[Dict[str, Any]]:
    """Parse JOURNAL.md into date-indexed list of entries."""
    if not path.exists():
        return []

    entries: List[Dict[str, Any]] = []
    current_date: Optional[str] = None
    current_lines: List[str] = []

    def _flush():
        if current_date and current_lines:
            entries.append({
                "date": current_date,
                "content": "\n".join(current_lines).strip(),
            })

    for line in path.read_text(errors="replace").splitlines():
        m = _DATE_HEADER_RE.match(line)
        if m:
            _flush()
            current_date = m.group(1)
            current_lines = [line]
        else:
            if current_date is not None:
                current_lines.append(line)

    _flush()
    return list(reversed(entries))  # newest first


@router.get("/journal")
async def get_journal(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _email: str = Depends(require_auth),
):
    """JOURNAL.md parsed as a timeline, newest first."""
    journal_path = _ROOT / "docs" / "JOURNAL.md"
    entries = _parse_journal(journal_path)

    total = len(entries)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total else 1,
        "entries": entries[start:end],
    }
