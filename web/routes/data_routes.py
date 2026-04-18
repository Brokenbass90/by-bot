"""Read-only data API — trades, account, regime, allocator, Alpaca, equity curve."""

from __future__ import annotations

import csv
import json
import math
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from ..deps import require_auth

router = APIRouter(prefix="/api", tags=["data"])

# ── project root & path helpers ───────────────────────────────────────────────

_ROOT = Path(__file__).parent.parent.parent


def _rt(*p: str) -> Path:
    return _ROOT / "runtime" / Path(*p)


def _cfg(*p: str) -> Path:
    return _ROOT / "configs" / Path(*p)


def _json(p: Path) -> Optional[dict]:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _read_csv(p: Path) -> List[Dict[str, str]]:
    if not p.exists():
        return []
    try:
        with open(p, newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


# ── find trades.csv files ─────────────────────────────────────────────────────

def _find_trades_csvs() -> List[Path]:
    found = sorted(
        list(_ROOT.glob("runtime/**/trades.csv")) + list(_ROOT.glob("backtest_runs/**/trades.csv")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    root_csv = _ROOT / "trades.csv"
    if root_csv.exists():
        found.insert(0, root_csv)
    return found[:5]  # up to 5 most recent


def _normalise_trade(row: Dict[str, str]) -> Dict[str, Any]:
    """Normalise CSV row to a consistent field set regardless of CSV schema version.

    New format (live bot): entry_ts, exit_ts, entry_price, exit_price, qty, pnl_pct_equity, outcome, reason, fees
    Old format:            open_time, close_time, entry, exit, size, pnl_pct, sl, tp
    We map new → canonical and keep both so nothing breaks.
    """
    t: Dict[str, Any] = dict(row)

    # ── time fields ──────────────────────────────────────────────────────────
    if "entry_ts" in t and "open_time" not in t:
        # entry_ts may be ms epoch (int) or ISO string
        raw = t["entry_ts"]
        if raw and raw.isdigit():
            from datetime import datetime, timezone
            try:
                t["open_time"] = datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            except Exception:
                t["open_time"] = raw
        else:
            t["open_time"] = raw

    if "exit_ts" in t and "close_time" not in t:
        raw = t["exit_ts"]
        if raw and raw.isdigit():
            from datetime import datetime, timezone
            try:
                t["close_time"] = datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            except Exception:
                t["close_time"] = raw
        else:
            t["close_time"] = raw

    # ── price fields ─────────────────────────────────────────────────────────
    if "entry_price" in t and "entry" not in t:
        t["entry"] = t["entry_price"]
    if "exit_price" in t and "exit" not in t:
        t["exit"] = t["exit_price"]

    # ── size ─────────────────────────────────────────────────────────────────
    if "qty" in t and "size" not in t:
        t["size"] = t["qty"]

    # ── pnl% ─────────────────────────────────────────────────────────────────
    if "pnl_pct_equity" in t and "pnl_pct" not in t:
        t["pnl_pct"] = t["pnl_pct_equity"]

    # ── parse numerics ───────────────────────────────────────────────────────
    for f in ("entry", "exit", "pnl", "pnl_pct", "size", "risk", "sl", "tp", "fees"):
        if f in t and t[f]:
            try:
                t[f] = float(t[f])
            except (ValueError, TypeError):
                pass

    return t


def _load_all_trades() -> List[Dict[str, Any]]:
    seen: set = set()
    trades: List[Dict[str, Any]] = []
    for csv_path in _find_trades_csvs():
        for row in _read_csv(csv_path):
            # dedup on either key format
            key = (
                row.get("strategy"),
                row.get("symbol"),
                row.get("open_time") or row.get("entry_ts"),
                row.get("entry") or row.get("entry_price"),
            )
            if key in seen:
                continue
            seen.add(key)
            trades.append(_normalise_trade(row))

    trades.sort(
        key=lambda t: str(t.get("close_time") or t.get("exit_ts") or t.get("open_time") or ""),
        reverse=True,
    )
    return trades


# ── bot status (fast heartbeat check) ────────────────────────────────────────

@router.get("/status")
async def get_status(_: str = Depends(require_auth)):
    """Quick bot liveness check — heartbeat, regime, open trades."""
    hb_path = _rt("bot_heartbeat.json")
    hb = _json(hb_path)

    regime_data = _json(_rt("regime", "orchestrator_state.json")) or _json(_rt("regime.json"))
    cp = _json(_rt("control_plane", "control_plane_watchdog_state.json"))

    now_ts = datetime.now(timezone.utc).timestamp()
    hb_age = None
    bot_alive = False
    if hb_path.exists():
        hb_age = int(now_ts - hb_path.stat().st_mtime)
        bot_alive = hb_age < 120  # alive if heartbeat < 2 min old

    return {
        "bot_alive": bot_alive,
        "heartbeat_age_sec": hb_age,
        "open_trades": hb.get("open_trades", 0) if hb else 0,
        "regime": (regime_data or {}).get("regime", "unknown"),
        "regime_confidence": (regime_data or {}).get("confidence"),
        "global_risk_mult": (regime_data or {}).get("global_risk_mult"),
        "control_plane_status": (cp or {}).get("status", "unknown"),
        "ws_guard_active": (hb or {}).get("ws_guard_active", False),
        "ts_utc": datetime.now(timezone.utc).isoformat(),
    }


# ── trades ────────────────────────────────────────────────────────────────────

@router.get("/trades")
async def get_trades(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    strategy: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    side: Optional[str] = Query(None),
    _: str = Depends(require_auth),
):
    trades = _load_all_trades()
    if strategy:
        trades = [t for t in trades if t.get("strategy", "").lower() == strategy.lower()]
    if symbol:
        trades = [t for t in trades if t.get("symbol", "").upper() == symbol.upper()]
    if side:
        trades = [t for t in trades if t.get("side", "").lower() == side.lower()]

    total = len(trades)
    s = (page - 1) * page_size
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, math.ceil(total / page_size)),
        "trades": trades[s: s + page_size],
    }


@router.get("/trades/summary")
async def get_summary(_: str = Depends(require_auth)):
    """Per-strategy stats + overall portfolio metrics."""
    trades = _load_all_trades()

    by_strat: Dict[str, dict] = defaultdict(lambda: {
        "wins": 0, "losses": 0, "gross_win": 0.0, "gross_loss": 0.0,
        "net": 0.0, "pnl_series": [],
    })
    total_gross_win = total_gross_loss = 0.0

    for t in trades:
        pnl = t.get("pnl")
        if not isinstance(pnl, float):
            continue
        s = by_strat[t.get("strategy", "unknown")]
        if pnl > 0:
            s["wins"] += 1
            s["gross_win"] += pnl
            total_gross_win += pnl
        elif pnl < 0:
            s["losses"] += 1
            s["gross_loss"] += abs(pnl)
            total_gross_loss += abs(pnl)
        s["net"] += pnl
        s["pnl_series"].append(round(pnl, 4))

    result = []
    for strat, rec in sorted(by_strat.items(), key=lambda x: -x[1]["net"]):
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
            "pnl_series": rec["pnl_series"][-20:],  # last 20 for sparkline
        })

    portfolio_pf = (total_gross_win / total_gross_loss) if total_gross_loss > 0 else None
    return {
        "strategies": result,
        "total_trades": len(trades),
        "portfolio_pf": round(portfolio_pf, 3) if portfolio_pf else None,
        "portfolio_net": round(sum(
            t.get("pnl", 0) for t in trades if isinstance(t.get("pnl"), float)
        ), 4),
    }


@router.get("/equity")
async def get_equity(_: str = Depends(require_auth)):
    """Cumulative equity curve from all closed trades (sorted by close_time)."""
    trades = _load_all_trades()

    def _t(trade: dict) -> str:
        return str(trade.get("close_time") or trade.get("exit_ts") or trade.get("time") or "")

    timed = [t for t in trades if isinstance(t.get("pnl"), float) and _t(t)]
    timed.sort(key=_t)

    equity = 0.0
    points = [{"t": "start", "equity": 0.0, "pnl": 0.0}]
    for t in timed:
        equity += t["pnl"]
        points.append({
            "t": _t(t),
            "equity": round(equity, 4),
            "pnl": t["pnl"],
            "strategy": t.get("strategy", "?"),
            "symbol": t.get("symbol", "?"),
        })
    return {"points": points, "final_equity": round(equity, 4)}


# ── account ───────────────────────────────────────────────────────────────────

@router.get("/account")
async def get_account(_: str = Depends(require_auth)):
    snap = _json(_rt("operator", "operator_snapshot.json"))
    if not snap:
        return {"error": "operator_snapshot.json not found"}

    # Simplify for frontend
    hb = snap.get("heartbeat", {})
    cp = snap.get("control_plane", {})
    alloc = snap.get("allocator", {})

    return {
        "generated_at_utc": snap.get("generated_at_utc"),
        "bot_alive": hb.get("exists", False),
        "open_trades": hb.get("open_trades", 0),
        "uptime_s": hb.get("uptime_s", 0),
        "regime": hb.get("regime", "unknown"),
        "ws_guard_active": hb.get("ws_guard_active", False),
        "control_plane_status": cp.get("watchdog", {}).get("status", "unknown"),
        "allocator_status": alloc.get("status"),
        "raw": snap,
    }


# ── regime ────────────────────────────────────────────────────────────────────

@router.get("/regime")
async def get_regime(_: str = Depends(require_auth)):
    data = (
        _json(_rt("regime", "orchestrator_state.json"))
        or _json(_rt("regime.json"))
        or {"regime": "UNKNOWN"}
    )
    return data


# ── allocator ─────────────────────────────────────────────────────────────────

@router.get("/allocator")
async def get_allocator(_: str = Depends(require_auth)):
    policy = _json(_cfg("portfolio_allocator_policy.json"))
    state = _json(_rt("control_plane", "portfolio_allocator_state.json")) or {}
    sleeve_states: Dict[str, Any] = dict(state.get("sleeves") or {})

    env_vals: Dict[str, str] = {}
    lenv = _cfg("portfolio_allocator_latest.env")
    if lenv.exists():
        for line in lenv.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env_vals[k.strip()] = v.strip()

    # Figure out which sleeves are actually enabled from env
    enabled_envs = {k for k, v in env_vals.items() if v == "1"}

    sleeves_status = []
    for s in (policy or {}).get("sleeves", []):
        runtime = dict(sleeve_states.get(s["name"]) or {})
        mults = s.get("base_risk_mult_by_regime", {})
        policy_active = any(v > 0 for v in mults.values())
        env_enabled = s.get("enable_env", "") in enabled_envs
        sleeves_status.append({
            "name": s["name"],
            "policy_active": policy_active,
            "env_enabled": env_enabled,
            "runtime_enabled": bool(runtime.get("enabled")),
            "runtime_health": str(runtime.get("health_status") or runtime.get("status") or "").upper(),
            "runtime_final_risk_mult": float(runtime.get("final_risk_mult") or 0.0),
            "runtime_symbol_count": int(runtime.get("symbol_count") or 0),
            "runtime_notes": list(runtime.get("notes") or [])[:3],
            "enable_env": s.get("enable_env"),
            "mults": mults,
            "comment": s.get("_comment", ""),
        })

    return {
        "policy_version": (policy or {}).get("policy_version"),
        "allocator_status": str(state.get("status") or ""),
        "allocator_global_risk_mult": float(
            state.get("allocator_global_risk_mult", state.get("global_risk_mult") or 0.0) or 0.0
        ),
        "degraded_reasons": list(state.get("degraded_reasons") or []),
        "sleeves": sleeves_status,
        "env": env_vals,
    }


# ── health ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def get_health(_: str = Depends(require_auth)):
    return {
        "current": _json(_rt("strategy_health.json")),
        "timeline": _json(_rt("strategy_health_timeline.json")),
        "self_audit": _json(_rt("self_audit", "latest.json")),
    }


# ── Alpaca ────────────────────────────────────────────────────────────────────

@router.get("/alpaca")
async def get_alpaca(_: str = Depends(require_auth)):
    """Monthly picks, summary metrics, advisory."""
    monthly_dir = _rt("equities_monthly_v36")
    picks = _read_csv(monthly_dir / "current_cycle_picks.csv")
    summary_rows = _read_csv(monthly_dir / "latest_summary.csv")
    advisory = _json(monthly_dir / "latest_advisory.json")

    summary = summary_rows[0] if summary_rows else {}
    # Convert numeric fields
    for f in ("compounded_return_pct", "profit_factor", "winrate_pct", "trades",
              "months", "calendar_months", "negative_months", "max_monthly_dd_pct"):
        if f in summary and summary[f]:
            try:
                summary[f] = float(summary[f])
            except ValueError:
                pass

    # Parse picks with numeric fields
    clean_picks = []
    for p in picks:
        cp = dict(p)
        for f in ("score", "entry_price", "stop_price", "target_price", "weight",
                  "atr20_pct", "momentum20_pct", "momentum60_pct"):
            if f in cp and cp[f]:
                try:
                    cp[f] = float(cp[f])
                except ValueError:
                    pass
        clean_picks.append(cp)

    return {
        "current_picks": clean_picks,
        "summary": summary,
        "advisory": (advisory or {}).get("report", advisory),
    }


# ── journal ───────────────────────────────────────────────────────────────────

_DATE_RE = re.compile(r"^#+\s*(\d{4}-\d{2}-\d{2})")


def _parse_journal(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    entries, cur_date, cur_lines = [], None, []

    def _flush():
        if cur_date and cur_lines:
            entries.append({"date": cur_date, "content": "\n".join(cur_lines).strip()})

    for line in path.read_text(errors="replace").splitlines():
        m = _DATE_RE.match(line)
        if m:
            _flush()
            cur_date = m.group(1)
            cur_lines = [line]
        elif cur_date is not None:
            cur_lines.append(line)
    _flush()
    return list(reversed(entries))


@router.get("/journal")
async def get_journal(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    _: str = Depends(require_auth),
):
    entries = _parse_journal(_ROOT / "docs" / "JOURNAL.md")
    total = len(entries)
    s = (page - 1) * page_size
    return {
        "total": total,
        "page": page,
        "pages": max(1, math.ceil(total / page_size)),
        "entries": entries[s: s + page_size],
    }
