"""ATT1 live wiring — decision_bus attribution + edge_monitor supervision.

Implements reports/ATT1_DECISION_BUS_EDGE_MONITOR_WIRING_SPEC_2026_07_03.md as a
self-contained, unit-testable module; smart_pump_reversal_bot.py only calls thin
entry points. RAILS:
  * v1 observes and alerts; it never blocks trading (the ATT1 breaker stays the
    only automatic stop).
  * every public function is exception-proof: a wiring failure must NEVER kill
    or delay an order path.
  * everything is behind env flags, default OFF; rollback = unset the flags.

Env:
  ATT1_DECISION_BUS_ENABLE   bool, default 0 — write enter/skip/outcome records.
  DECISION_BUS_PATH          default runtime/decision_bus.jsonl (size-rotated).
  ATT1_EDGE_MONITOR_ENABLE   bool, default 0 — hourly health check vs baseline.
  ATT1_EDGE_BASELINE_EXPECTANCY_R  default 0.054 (fee-stress 10/5bps: 16.53R/307).
  ATT1_EDGE_INTERVAL_SEC     default 3600.
  ATT1_EDGE_HEALTH_PATH      default runtime/att1_edge_health.json.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from bot.decision_bus import DecisionBus, build_decision, attach_outcome
from bot.edge_monitor import assess_sleeve

ATT1_STRATEGY_ID = "att1_trendline_touch"
_BUS_MAX_BYTES = 16 * 1024 * 1024
_last_edge_check_ts: float = 0.0


def _env_flag(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in ("1", "true", "yes", "on")


def _bus_path() -> Path:
    p = Path(str(os.getenv("DECISION_BUS_PATH", "runtime/decision_bus.jsonl")))
    if not p.is_absolute():
        p = Path(__file__).resolve().parents[1] / p
    return p


def _rotate_if_big(path: Path) -> None:
    try:
        if path.exists() and path.stat().st_size >= _BUS_MAX_BYTES:
            path.replace(path.with_name(path.name + ".1"))
    except Exception:
        pass


def _append(rec) -> None:
    path = _bus_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_if_big(path)
    DecisionBus(str(path)).append(rec)


def bus_enabled() -> bool:
    return _env_flag("ATT1_DECISION_BUS_ENABLE")


# ── decision records (never raise) ──────────────────────────────────────────

def record_skip(symbol: str, side: str, reason: str, **extra: Any) -> None:
    """Post-signal skip (breaker/shadow/minqty/...). No-op unless enabled."""
    if not bus_enabled():
        return
    try:
        clean = {k: v for k, v in extra.items()
                 if isinstance(v, (str, int, float, bool)) or v is None}
        rec = build_decision(
            ts=int(time.time()), symbol=symbol, strategy=ATT1_STRATEGY_ID,
            side=str(side or "?"), decision="skip", reason=str(reason)[:120],
            extra=clean or None,
        )
        _append(rec)
    except Exception:
        pass


def record_entry(
    *,
    symbol: str,
    side: str,
    entry: float,
    sl: float,
    tp: Optional[float],
    breaker_mult: float,
    effective_risk_mult: float,
    stop_pct: float,
    minqty_fallback: bool,
    notional_usd: float,
    qty: float,
    regime: str = "",
) -> str:
    """Write an enter record; returns bus_id ('' when disabled/failed)."""
    if not bus_enabled():
        return ""
    try:
        bus_id = f"{int(time.time() * 1000)}_{str(symbol).upper()}"
        rec = build_decision(
            ts=int(time.time()), symbol=symbol, strategy=ATT1_STRATEGY_ID,
            side=str(side), decision="enter", reason="signal",
            extra={
                "bus_id": bus_id,
                "regime": str(regime or os.getenv("ORCH_REGIME", "unknown")),
                "breaker_mult": float(breaker_mult),
                "effective_risk_mult": float(effective_risk_mult),
                "stop_pct": float(stop_pct),
                "minqty_fallback": bool(minqty_fallback),
                "notional_usd": float(notional_usd),
                "qty": float(qty),
            },
        )
        rec.plan = {"entry": float(entry), "stop": float(sl),
                    "tp1": (float(tp) if tp is not None else None), "tp2": None, "rr2": None}
        _append(rec)
        return bus_id
    except Exception:
        return ""


def record_outcome(tr: Any, symbol: str, *, pnl: float, exit_reason: str = "") -> None:
    """Close the loop for an ATT1 trade. R is computed from ACTUAL risk
    (qty * |entry - sl|), so minqty-fallback trades do not distort R stats."""
    if not bus_enabled():
        return
    try:
        if str(getattr(tr, "strategy", "") or "") != ATT1_STRATEGY_ID:
            return
        bus_id = str(getattr(tr, "att1_bus_id", "") or "")
        qty = float(getattr(tr, "qty", 0.0) or 0.0)
        entry_px = float(getattr(tr, "avg", 0.0) or getattr(tr, "entry_price", 0.0) or 0.0)
        sl_px = float(getattr(tr, "sl_price", 0.0) or 0.0)
        risk_usd = qty * abs(entry_px - sl_px)
        r_mult = (float(pnl) / risk_usd) if risk_usd > 0 else float("nan")
        rec = build_decision(
            ts=int(time.time()), symbol=symbol, strategy=ATT1_STRATEGY_ID,
            side=("long" if str(getattr(tr, "side", "")) == "Buy" else "short"),
            decision="outcome", reason=str(exit_reason or "")[:120],
            extra={"bus_id": bus_id, "risk_usd": round(risk_usd, 6)},
        )
        attach_outcome(rec, filled=True, r_multiple=round(r_mult, 4) if r_mult == r_mult else float("nan"),
                       pnl=float(pnl), exit_reason=str(exit_reason or ""))
        _append(rec)
    except Exception:
        pass


# ── edge monitor (periodic, alert-only) ─────────────────────────────────────

def att1_r_multiples_from_db(db_path: str, *, lookback_days: int = 90) -> List[float]:
    """R-multiples of closed ATT1 trades from trade_events, actual-risk based."""
    out: List[float] = []
    cutoff = int(time.time()) - int(lookback_days) * 86400
    with sqlite3.connect(db_path) as con:
        rows = con.execute(
            "SELECT qty, entry_price, sl_price, pnl FROM trade_events "
            "WHERE event='CLOSE' AND strategy=? AND ts>=? ORDER BY ts",
            (ATT1_STRATEGY_ID, cutoff),
        ).fetchall()
    for qty, entry_px, sl_px, pnl in rows:
        try:
            risk = float(qty or 0.0) * abs(float(entry_px or 0.0) - float(sl_px or 0.0))
            if risk > 0 and pnl is not None:
                out.append(float(pnl) / risk)
        except Exception:
            continue
    return out


def _health_path() -> Path:
    p = Path(str(os.getenv("ATT1_EDGE_HEALTH_PATH", "runtime/att1_edge_health.json")))
    if not p.is_absolute():
        p = Path(__file__).resolve().parents[1] / p
    return p


def edge_check(db_path: str, *, notify: Optional[Callable[[str], Any]] = None,
               now_ts: Optional[float] = None) -> Dict[str, Any]:
    """Assess ATT1 live health vs baseline; persist report; alert on status change.
    ALERT-ONLY: never touches risk (breaker is the sole automatic stop)."""
    baseline = float(os.getenv("ATT1_EDGE_BASELINE_EXPECTANCY_R", "0.054") or 0.054)
    rs = att1_r_multiples_from_db(db_path)
    rep = assess_sleeve(rs, sleeve="att1_short_r001", baseline_expectancy_R=baseline)
    d = {
        "ts": int(now_ts if now_ts is not None else time.time()),
        "sleeve": rep.sleeve, "status": rep.status, "n": rep.n,
        "live_expectancy_R": rep.live_expectancy_R if rep.live_expectancy_R == rep.live_expectancy_R else None,
        "baseline_expectancy_R": rep.baseline_expectancy_R,
        "win_rate": rep.win_rate if rep.win_rate == rep.win_rate else None,
        "drawdown_R": rep.drawdown_R, "worst_losing_streak": rep.worst_losing_streak,
        "reason": rep.reason,
    }
    path = _health_path()
    prev_status = ""
    try:
        if path.exists():
            prev_status = str(json.loads(path.read_text()).get("status", "") or "")
    except Exception:
        prev_status = ""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d, ensure_ascii=True))
    except Exception:
        pass
    if notify is not None and prev_status and prev_status != rep.status:
        try:
            icon = "🛑" if rep.status == "halt" else ("🟠" if rep.status == "degraded" else "ℹ️")
            notify(f"{icon} ATT1 edge_monitor: {prev_status} -> {rep.status} "
                   f"(n={rep.n}, liveExp={d['live_expectancy_R']}, reason={rep.reason})")
        except Exception:
            pass
    return d


def maybe_edge_check(db_path: str, *, notify: Optional[Callable[[str], Any]] = None) -> Optional[Dict[str, Any]]:
    """Rate-limited edge_check for the heartbeat loop. No-op unless enabled."""
    global _last_edge_check_ts
    if not _env_flag("ATT1_EDGE_MONITOR_ENABLE"):
        return None
    try:
        interval = max(300, int(os.getenv("ATT1_EDGE_INTERVAL_SEC", "3600") or 3600))
        now = time.time()
        if now - _last_edge_check_ts < interval:
            return None
        _last_edge_check_ts = now
        return edge_check(db_path, notify=notify, now_ts=now)
    except Exception:
        return None
