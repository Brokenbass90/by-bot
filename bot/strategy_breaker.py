"""Per-strategy live risk breaker + canary expiry (dependency-free, testable).

This module generalizes the inline BREAKDOWN_BREAKER pattern already present in
``smart_pump_reversal_bot.py`` into a small, unit-testable unit so canary sleeves
(e.g. ATT1 short-only) get an automatic risk rollback without editing the
monolith's risk math.

It reads realized closes from the live trades DB (``trade_events`` table, the
same schema the monolith writes) and returns a risk decision:

- ``blocked=True`` (risk_mult 0.0)  -> sleeve must not open new trades;
- ``risk_mult<1.0``                 -> soft cut, scale the sleeve's risk;
- otherwise full risk.

Hard-block triggers (any one):
  * realized net PnL over the lookback <= ``hard_net_pnl``;
  * consecutive losing closes >= ``max_consec_losses`` (if set);
  * canary expiry reached (``expiry_utc`` in the past) -> forces human review
    before risk can continue.

Soft-cut trigger:
  * realized net PnL over the lookback <= ``soft_net_pnl`` -> ``soft_mult``.

All thresholds are explicit so the caller (monolith or a cron supervisor) owns
the policy. Pure stdlib; safe to import anywhere.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Optional


def _parse_expiry(expiry_utc: Optional[str]) -> Optional[float]:
    """Parse an ISO-ish UTC expiry string into an epoch float, or None."""
    if not expiry_utc:
        return None
    s = str(expiry_utc).strip()
    if not s:
        return None
    # Accept 'YYYY-MM-DD', 'YYYY-MM-DDTHH:MM:SS', optional trailing 'Z'.
    s = s.replace("Z", "").replace(" UTC", "").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    return None


def recent_close_stats(
    db_path: str,
    strategy: str,
    lookback_days: float,
    *,
    now_ts: Optional[float] = None,
) -> dict[str, float]:
    """Aggregate realized closes for ``strategy`` over the lookback window."""
    stats = {
        "trades": 0.0,
        "wins": 0.0,
        "net_pnl": 0.0,
        "winrate": 0.0,
        "max_consec_losses": 0.0,
    }
    if not strategy or not db_path:
        return stats
    now = float(now_ts if now_ts is not None else time.time())
    since_ts = int(now - float(max(1.0, lookback_days)) * 86400.0)
    try:
        with sqlite3.connect(db_path) as con:
            rows = con.execute(
                """
                SELECT pnl, ts
                  FROM trade_events
                 WHERE event='CLOSE'
                   AND strategy=?
                   AND pnl IS NOT NULL
                   AND ts>=?
                 ORDER BY ts ASC
                """,
                (str(strategy), since_ts),
            ).fetchall()
    except sqlite3.Error:
        return stats

    trades = 0
    wins = 0
    net = 0.0
    consec = 0
    max_consec = 0
    for pnl_raw, _ts in rows:
        try:
            pnl = float(pnl_raw)
        except (TypeError, ValueError):
            continue
        trades += 1
        net += pnl
        if pnl > 0:
            wins += 1
            consec = 0
        else:
            consec += 1
            max_consec = max(max_consec, consec)
    stats["trades"] = float(trades)
    stats["wins"] = float(wins)
    stats["net_pnl"] = float(net)
    stats["winrate"] = (100.0 * wins / trades) if trades > 0 else 0.0
    stats["max_consec_losses"] = float(max_consec)
    return stats


def breaker_state(
    db_path: str,
    strategy: str,
    *,
    enable: bool = True,
    lookback_days: float = 30.0,
    min_trades: int = 6,
    soft_net_pnl: float = -2.0,
    soft_mult: float = 0.5,
    hard_net_pnl: float = -4.5,
    max_consec_losses: Optional[int] = None,
    expiry_utc: Optional[str] = None,
    now_ts: Optional[float] = None,
) -> dict[str, Any]:
    """Return a risk decision dict for ``strategy``.

    Keys: enabled, lookback_days, min_trades, trades, net_pnl, winrate,
    max_consec_losses, blocked (bool), risk_mult (float), reason (str), expired.
    """
    stats = recent_close_stats(db_path, strategy, lookback_days, now_ts=now_ts)
    trades = int(stats["trades"])
    net_pnl = float(stats["net_pnl"])
    consec = int(stats["max_consec_losses"])

    state: dict[str, Any] = {
        "enabled": bool(enable),
        "lookback_days": float(lookback_days),
        "min_trades": int(min_trades),
        "trades": trades,
        "net_pnl": round(net_pnl, 4),
        "winrate": round(float(stats["winrate"]), 2),
        "max_consec_losses": consec,
        "blocked": False,
        "risk_mult": 1.0,
        "reason": "",
        "expired": False,
    }

    # Expiry is independent of trade count: a canary window that elapsed must
    # stop opening new risk until a human renews it.
    expiry_ts = _parse_expiry(expiry_utc)
    now = float(now_ts if now_ts is not None else time.time())
    if expiry_ts is not None and now >= expiry_ts:
        state["expired"] = True
        state["blocked"] = True
        state["risk_mult"] = 0.0
        state["reason"] = f"canary expired at {expiry_utc} (UTC); needs manual renewal"
        return state

    if not enable:
        return state

    # Consecutive-loss kill works even on small samples (string of stop-outs).
    if max_consec_losses is not None and consec >= int(max_consec_losses):
        state["blocked"] = True
        state["risk_mult"] = 0.0
        state["reason"] = f"{consec} consecutive losing closes >= {int(max_consec_losses)}"
        return state

    # PnL gates require a minimum sample to avoid noise.
    if trades < int(min_trades):
        return state

    if net_pnl <= float(hard_net_pnl):
        state["blocked"] = True
        state["risk_mult"] = 0.0
        state["reason"] = (
            f"{lookback_days:g}d net {net_pnl:+.2f} <= hard {float(hard_net_pnl):+.2f} "
            f"over {trades} closes"
        )
        return state

    if net_pnl <= float(soft_net_pnl):
        state["risk_mult"] = float(max(0.05, min(1.0, soft_mult)))
        state["reason"] = (
            f"{lookback_days:g}d net {net_pnl:+.2f} <= soft {float(soft_net_pnl):+.2f} "
            f"over {trades} closes"
        )
    return state
