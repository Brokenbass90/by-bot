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

import ssl
import urllib.request

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import require_auth

router = APIRouter(prefix="/api", tags=["data"])

# ── project root & path helpers ───────────────────────────────────────────────

_ROOT = Path(__file__).parent.parent.parent
_RUNTIME_ROOT = Path(os.getenv("WEB_RUNTIME_ROOT", str(_ROOT / "runtime")))
_INCLUDE_BACKTEST_TRADES = os.getenv("WEB_INCLUDE_BACKTEST_TRADES", "0").strip().lower() in {"1", "true", "yes"}


def _rt(*p: str) -> Path:
    return _RUNTIME_ROOT / Path(*p)


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


def _read_env(p: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not p.exists():
        return out
    try:
        for raw in p.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    except Exception:
        return {}
    return out


def _resolve_rooted_path(raw: str) -> Optional[Path]:
    raw = str(raw or "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p
    candidate = (_ROOT / p).resolve()
    return candidate


def _file_age_sec(p: Path) -> Optional[int]:
    if not p.exists():
        return None
    try:
        return int(datetime.now(timezone.utc).timestamp() - p.stat().st_mtime)
    except Exception:
        return None


def _allocator_human_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    status = str(state.get("status") or "unknown").strip().lower()
    degraded_kind = str(state.get("degraded_kind") or "").strip().lower()
    risk = float(state.get("allocator_global_risk_mult", state.get("global_risk_mult") or 0.0) or 0.0)
    reasons = list(state.get("degraded_reasons") or [])

    label = status.upper()
    tone = "neutral"
    detail = ""
    if status == "ok":
        label = "Allocator OK"
        tone = "ok"
        detail = "Risk is fully open for the current sleeve mix."
    elif status == "safe_mode":
        label = "Safe Mode"
        tone = "danger"
        detail = "New entries are heavily restricted until control-plane health improves."
    elif status == "degraded" and degraded_kind == "protective_overlap":
        label = "Risk Reduced For Overlap"
        tone = "warn"
        detail = "Allocator is protecting the portfolio because active sleeves overlap too much. This is a haircut, not a broken allocator."
    elif status == "degraded":
        label = "Allocator Degraded"
        tone = "danger"
        detail = "Allocator is not fully healthy and is trimming risk."

    if reasons:
        detail = (detail + " Reasons: " + ", ".join(reasons)).strip()
    if risk > 0:
        detail = (detail + f" Current global risk ×{risk:.2f}.").strip()

    return {
        "status": status,
        "degraded_kind": degraded_kind or "none",
        "label": label,
        "tone": tone,
        "detail": detail,
        "risk_mult": risk,
    }


def _load_monthly_picks(runtime_dir: Path) -> List[Dict[str, str]]:
    def _latest_month_only(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
        months = sorted({str(r.get("month") or "").strip() for r in rows if str(r.get("month") or "").strip()})
        if not months:
            return rows
        latest = months[-1]
        return [r for r in rows if str(r.get("month") or "").strip() == latest]

    direct = _read_csv(runtime_dir / "current_cycle_picks.csv")
    if direct:
        return _latest_month_only(direct)

    latest_refresh = _read_env(runtime_dir / "latest_refresh.env")
    for key in ("EQ_CURRENT_CYCLE_PICKS_CSV", "ALPACA_CURRENT_CYCLE_PICKS_CSV", "EQ_LATEST_PICKS_CSV"):
        p = _resolve_rooted_path(latest_refresh.get(key, ""))
        if p:
            rows = _read_csv(p)
            if rows:
                return _latest_month_only(rows)

    mirror_latest = _read_csv(runtime_dir / "latest_picks.csv")
    if mirror_latest:
        return _latest_month_only(mirror_latest)
    return []


def _extract_intraday_positions(state: Any) -> List[Dict[str, Any]]:
    if isinstance(state, dict):
        if isinstance(state.get("positions"), dict):
            return list(state.get("positions", {}).values())
        return [v for v in state.values() if isinstance(v, dict) and v.get("symbol")]
    return []


def _load_alpaca_intraday_variant(runtime_name: str, *, label: str, state_cfg_name: Optional[str] = None) -> Dict[str, Any]:
    runtime_dir = _rt(runtime_name)
    advisory = _json(runtime_dir / "latest_advisory.json") or {}
    report = (advisory or {}).get("report", advisory) or {}
    state = _json(_cfg(state_cfg_name)) if state_cfg_name else None
    positions = _extract_intraday_positions(state)
    generated_at = str(advisory.get("generated_at_utc") or "")
    account = dict(advisory.get("account") or {})
    return {
        "id": runtime_name,
        "label": label,
        "exists": runtime_dir.exists(),
        "age_sec": _file_age_sec(runtime_dir / "latest_advisory.json"),
        "generated_at_utc": generated_at,
        "equity": account.get("equity"),
        "cash": account.get("cash"),
        "mode": advisory.get("mode") or report.get("mode") or "",
        "entries_blocked": advisory.get("entries_blocked"),
        "open_positions": list(advisory.get("open_positions") or []),
        "watchlist": list(advisory.get("watchlist") or []),
        "positions": positions,
    }


# ── find trades.csv files ─────────────────────────────────────────────────────

def _find_trades_csvs() -> List[Path]:
    found = list(_RUNTIME_ROOT.glob("**/trades.csv"))
    if _INCLUDE_BACKTEST_TRADES:
        found += list(_ROOT.glob("backtest_runs/**/trades.csv"))
    found = sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)
    root_csv = _RUNTIME_ROOT / "trades.csv"
    if not root_csv.exists():
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
                    # Fallback: if no entry_ts yet (e.g. only a close event exists,
                    # order_submitted was missed), estimate from exit - 1 min so
                    # the chart modal gets a valid timestamp instead of "Missing symbol"
                    if not rec.get("entry_ts"):
                        exit_sec = int(evt.get("ts") or 0)
                        rec["entry_ts"] = max(0, exit_sec - 60)
            for rec in buckets.values():
                if not rec.get("exit_ts"):
                    continue
                side_raw = str(rec.get("side") or "").strip().lower()
                side = "short" if side_raw in {"sell", "short"} else "long"
                entry_ts = int(rec.get("entry_ts") or 0)
                exit_ts = int(rec.get("exit_ts") or 0)
                # Some older close-only live events do not carry a stable entry_order_id,
                # so we may never see the matching submitted/filled event in the same bucket.
                # Fall back to exit_ts so the UI can still open the chart modal around the close.
                if not entry_ts and exit_ts:
                    entry_ts = exit_ts
                entry_notional = float(rec.get("entry_notional_usd") or 0.0)
                pnl = float(rec.get("pnl") or 0.0)
                trade = {
                    "strategy": str(rec.get("strategy") or ""),
                    "symbol": str(rec.get("symbol") or "").upper(),
                    "side": side,
                    "outcome": str(rec.get("close_reason") or "close"),
                    "entry": float(rec.get("entry_price") or 0.0),
                    "exit": float(rec.get("exit_price") or 0.0),
                    "pnl": pnl,
                    "fees": float(rec.get("fees") or 0.0),
                    "sl": float(rec.get("sl_price") or 0.0) if rec.get("sl_price") is not None else None,
                    "tp": float(rec.get("tp_price") or 0.0) if rec.get("tp_price") is not None else None,
                    "entry_ts": entry_ts * 1000 if entry_ts else None,
                    "exit_ts": exit_ts * 1000 if exit_ts else None,
                    "open_time": datetime.fromtimestamp(entry_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if entry_ts else "",
                    "close_time": datetime.fromtimestamp(exit_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if exit_ts else "",
                    "pnl_pct": (pnl / entry_notional * 100.0) if entry_notional > 0 else None,
                }
                trades.append(trade)
        except Exception:
            pass
        trades.sort(
            key=lambda t: str(t.get("close_time") or t.get("exit_ts") or t.get("open_time") or ""),
            reverse=True,
        )
    return trades


def _trade_sources() -> List[str]:
    paths = _find_trades_csvs()
    if paths:
        return [str(p.relative_to(_ROOT)) for p in paths]
    live_jsonl = _rt("live_trade_events.jsonl")
    if live_jsonl.exists():
        return [str(live_jsonl.relative_to(_ROOT))]
    return []


# ── bot status (fast heartbeat check) ────────────────────────────────────────

@router.get("/status")
async def get_status(_: str = Depends(require_auth)):
    """Quick bot liveness check — heartbeat, regime, open trades."""
    hb_path = _rt("bot_heartbeat.json")
    hb = _json(hb_path)

    regime_data = _json(_rt("regime", "orchestrator_state.json")) or _json(_rt("regime.json"))
    cp = _json(_rt("control_plane", "control_plane_watchdog_state.json"))
    allocator_state = _json(_rt("control_plane", "portfolio_allocator_state.json")) or {}
    allocator = _allocator_human_summary(allocator_state)

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
        "allocator_status": allocator["status"],
        "allocator_label": allocator["label"],
        "allocator_tone": allocator["tone"],
        "allocator_detail": allocator["detail"],
        "runtime_root": str(_RUNTIME_ROOT),
        "data_mode": "live_mirror" if _RUNTIME_ROOT != (_ROOT / "runtime") else "local",
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
        "sources": _trade_sources(),
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
        "sources": _trade_sources(),
    }


@router.get("/trades/chart")
async def trade_chart(
    symbol: str,
    entry_ts: int,
    exit_ts: int,
    interval: str = Query("5", regex=r"^(1|3|5|15|30|60|120|240|D)$"),
    entry_price: Optional[float] = None,
    exit_price: Optional[float] = None,
    sl_price: Optional[float] = None,
    tp_price: Optional[float] = None,
    _: str = Depends(require_auth),
):
    """Fetch OHLCV candles from Bybit for a ±8h window around a trade.

    Returns list of {time_ms, open, high, low, close, volume} dicts plus
    entry/exit timestamps so the frontend can draw markers.
    """
    WINDOW_BEFORE_MS = 8 * 3_600_000   # 8 hours before entry
    WINDOW_AFTER_MS  = 4 * 3_600_000   # 4 hours after exit

    start_ms = entry_ts - WINDOW_BEFORE_MS
    end_ms   = max(exit_ts, entry_ts) + WINDOW_AFTER_MS

    # ── Try local kline cache first (fast, no network) ──────────────────────
    candles: list = []
    _cache_dirs = [
        _ROOT / ".cache" / "klines",
        _ROOT / "data_cache" / "klines",
    ]
    for _cache_dir in _cache_dirs:
        if not _cache_dir.exists():
            continue
        sym_u = symbol.upper()
        for _f in sorted(_cache_dir.glob(f"{sym_u}_{interval}_*.json")):
            try:
                parts = _f.stem.split("_")
                file_start = int(parts[2])
                file_end   = int(parts[3])
                # Use this file if it covers at least some of our window
                if file_end < start_ms or file_start > end_ms:
                    continue
                raw_data = json.loads(_f.read_text())
                rows = raw_data if isinstance(raw_data, list) else \
                       raw_data.get("result", {}).get("list", raw_data.get("list", []))
                for row in rows:
                    try:
                        ts_ms = int(row[0])
                        if start_ms <= ts_ms <= end_ms:
                            candles.append({
                                "time_ms": ts_ms,
                                "open":  float(row[1]),
                                "high":  float(row[2]),
                                "low":   float(row[3]),
                                "close": float(row[4]),
                                "volume": float(row[5]) if len(row) > 5 else 0.0,
                            })
                    except (IndexError, ValueError, TypeError):
                        continue
            except Exception:
                continue
        if candles:
            break  # found data in this cache dir

    # Remove duplicates and sort chronologically
    if candles:
        seen: set = set()
        deduped = []
        for c in sorted(candles, key=lambda x: x["time_ms"]):
            if c["time_ms"] not in seen:
                seen.add(c["time_ms"])
                deduped.append(c)
        candles = deduped

    # ── Fall back to live Bybit API if cache miss ────────────────────────────
    source = "cache" if candles else ""
    warning = ""

    if not candles:
        BYBIT_URL = "https://api.bybit.com/v5/market/kline"
        params = (
            f"category=linear&symbol={symbol.upper()}"
            f"&interval={interval}&start={start_ms}&end={end_ms}&limit=1000"
        )
        url = f"{BYBIT_URL}?{params}"
        try:
            ctx = ssl.create_default_context()
            req = urllib.request.Request(url, headers={"User-Agent": "TradingJournal/1.0"})
            with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
                body = json.loads(resp.read().decode())
            if body.get("retCode") == 0:
                for row in reversed(body.get("result", {}).get("list", [])):
                    try:
                        candles.append({
                            "time_ms": int(row[0]),
                            "open":    float(row[1]),
                            "high":    float(row[2]),
                            "low":     float(row[3]),
                            "close":   float(row[4]),
                            "volume":  float(row[5]),
                        })
                    except (IndexError, ValueError):
                        continue
                if candles:
                    source = "bybit"
        except Exception:
            pass  # Network unavailable — return empty candles with no error

    if not candles and entry_price and exit_price:
        # Honest UI fallback: show the trade path and levels when market candles
        # are unavailable for old/live-event-only records.
        lo_candidates = [entry_price, exit_price]
        hi_candidates = [entry_price, exit_price]
        if sl_price:
            lo_candidates.append(sl_price)
            hi_candidates.append(sl_price)
        if tp_price:
            lo_candidates.append(tp_price)
            hi_candidates.append(tp_price)
        low = min(lo_candidates)
        high = max(hi_candidates)
        pad = max((high - low) * 0.08, abs(entry_price) * 0.0005, 1e-6)
        mid_ts = max(entry_ts, min(exit_ts, (entry_ts + exit_ts) // 2))
        candles = [
            {
                "time_ms": max(start_ms, entry_ts - 5 * 60_000),
                "open": entry_price,
                "high": max(entry_price, high) + pad,
                "low": min(entry_price, low) - pad,
                "close": entry_price,
                "volume": 0.0,
            },
            {
                "time_ms": mid_ts,
                "open": entry_price,
                "high": max(entry_price, exit_price, high) + pad,
                "low": min(entry_price, exit_price, low) - pad,
                "close": (entry_price + exit_price) / 2.0,
                "volume": 0.0,
            },
            {
                "time_ms": max(exit_ts, entry_ts + 60_000),
                "open": (entry_price + exit_price) / 2.0,
                "high": max(exit_price, high) + pad,
                "low": min(exit_price, low) - pad,
                "close": exit_price,
                "volume": 0.0,
            },
        ]
        source = "synthetic_trade_path"
        warning = "Market candles were unavailable for this old trade window; showing entry/exit/SL/TP trade path instead."

    return {
        "symbol":   symbol.upper(),
        "interval": interval,
        "entry_ts": entry_ts,
        "exit_ts":  exit_ts,
        "candles":  candles,
        "source": source,
        "warning": warning,
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
    return {"points": points, "final_equity": round(equity, 4), "sources": _trade_sources()}


# ── account ───────────────────────────────────────────────────────────────────

@router.get("/account")
async def get_account(_: str = Depends(require_auth)):
    snap = _json(_rt("operator", "operator_snapshot.json"))
    if not snap:
        return {"error": "operator_snapshot.json not found"}

    # Simplify for frontend
    hb = snap.get("heartbeat", {})
    cp = snap.get("control_plane", {})
    alloc = cp.get("allocator", {}) or snap.get("allocator", {})
    alloc_summary = _allocator_human_summary(alloc)

    return {
        "generated_at_utc": snap.get("generated_at_utc"),
        "bot_alive": hb.get("exists", False),
        "open_trades": hb.get("open_trades", 0),
        "uptime_s": hb.get("uptime_s", 0),
        "regime": hb.get("regime", "unknown"),
        "ws_guard_active": hb.get("ws_guard_active", False),
        "control_plane_status": cp.get("watchdog", {}).get("status", "unknown"),
        "allocator_status": alloc_summary["status"],
        "allocator_label": alloc_summary["label"],
        "allocator_detail": alloc_summary["detail"],
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
    alloc_summary = _allocator_human_summary(state)

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
        "allocator_status": alloc_summary["status"],
        "allocator_label": alloc_summary["label"],
        "allocator_tone": alloc_summary["tone"],
        "allocator_detail": alloc_summary["detail"],
        "degraded_kind": alloc_summary["degraded_kind"],
        "allocator_global_risk_mult": float(
            state.get("allocator_global_risk_mult", state.get("global_risk_mult") or 0.0) or 0.0
        ),
        "degraded_reasons": list(state.get("degraded_reasons") or []),
        "runtime_root": str(_RUNTIME_ROOT),
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
    picks = _load_monthly_picks(monthly_dir)
    summary_rows = _read_csv(monthly_dir / "latest_summary.csv")
    advisory = _json(monthly_dir / "latest_advisory.json")
    intraday_state = _json(_rt("intraday_state.json")) or _json(_cfg("intraday_state.json"))
    intraday_v1 = _load_alpaca_intraday_variant("equities_intraday_dynamic_v1", label="Intraday Dynamic v1", state_cfg_name="intraday_state.json")
    intraday_v3_shadow = _load_alpaca_intraday_variant("equities_intraday_dynamic_v3_shadow", label="Intraday Dynamic v3 Shadow", state_cfg_name="intraday_state_v3_shadow.json")

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

    intraday_positions = _extract_intraday_positions(intraday_state)
    monthly_refresh = _read_env(monthly_dir / "latest_refresh.env")
    monthly_cycle_summary = {
        "exists": monthly_dir.exists(),
        "age_sec": _file_age_sec(monthly_dir / "latest_summary.csv"),
        "current_picks_missing": not (monthly_dir / "current_cycle_picks.csv").exists(),
        "latest_refresh_utc": monthly_refresh.get("EQ_LATEST_REFRESH_UTC") or monthly_refresh.get("ALPACA_REFRESH_UTC") or "",
    }
    variants = [
        {
            "id": "monthly_v36",
            "label": "Monthly Momentum v36",
            "exists": monthly_dir.exists(),
            "age_sec": _file_age_sec(monthly_dir / "latest_summary.csv"),
            "current_picks_count": len(clean_picks),
            "latest_refresh_utc": monthly_cycle_summary["latest_refresh_utc"],
        },
        intraday_v1,
        intraday_v3_shadow,
    ]

    return {
        "current_picks": clean_picks,
        "summary": summary,
        "advisory": (advisory or {}).get("report", advisory),
        "intraday_positions": intraday_positions,
        "intraday_updated_utc": (intraday_state or {}).get("updated_utc"),
        "variants": variants,
        "monthly_cycle": monthly_cycle_summary,
        "intraday_v1": intraday_v1,
        "intraday_v3_shadow": intraday_v3_shadow,
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


# ── strategy analytics ────────────────────────────────────────────────────────

def _compute_strategy_stats(
    trades: List[Dict[str, Any]],
    days: int = 30,
) -> List[Dict[str, Any]]:
    """Compute per-strategy stats for the last `days` days."""
    from datetime import datetime, timezone, timedelta
    cutoff_ms = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000

    by_strategy: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in trades:
        strat = str(t.get("strategy") or "").strip()
        if not strat:
            continue
        # determine timestamp
        ts = t.get("exit_ts") or t.get("entry_ts")
        if ts and float(ts) < cutoff_ms:
            continue
        by_strategy[strat].append(t)

    stats = []
    for strat, strat_trades in sorted(by_strategy.items()):
        n = len(strat_trades)
        pnls = []
        for t in strat_trades:
            pnl_raw = t.get("pnl") or t.get("pnl_pct") or 0
            try:
                pnls.append(float(pnl_raw))
            except (TypeError, ValueError):
                pnls.append(0.0)

        wins   = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        gross_profit = sum(wins)
        gross_loss   = abs(sum(losses))
        pf           = round(gross_profit / gross_loss, 3) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
        wr           = round(len(wins) / n, 3) if n > 0 else 0.0
        avg_win      = round(gross_profit / len(wins), 4) if wins else 0.0
        avg_loss     = round(gross_loss / len(losses), 4) if losses else 0.0
        total_pnl    = round(sum(pnls), 4)

        # Symbol breakdown
        symbol_counts: Dict[str, int] = defaultdict(int)
        for t in strat_trades:
            sym = str(t.get("symbol") or "")
            if sym:
                symbol_counts[sym] += 1
        top_symbols = sorted(symbol_counts.items(), key=lambda x: -x[1])[:5]

        stats.append({
            "strategy":     strat,
            "trades":       n,
            "win_rate":     wr,
            "profit_factor": pf,
            "total_pnl":    total_pnl,
            "avg_win":      avg_win,
            "avg_loss":     avg_loss,
            "gross_profit": round(gross_profit, 4),
            "gross_loss":   round(gross_loss, 4),
            "top_symbols":  [{"symbol": s, "trades": c} for s, c in top_symbols],
        })

    # Sort: by profit_factor desc
    stats.sort(key=lambda x: x["profit_factor"], reverse=True)
    return stats


@router.get("/strategy-stats")
async def get_strategy_stats(
    days: int = Query(30, ge=1, le=365),
    _: str = Depends(require_auth),
):
    """Per-strategy performance summary for the last `days` days."""
    trades = _load_all_trades()
    stats  = _compute_strategy_stats(trades, days=days)

    # Attach live health status if available
    health = _json(_rt("strategy_health.json")) or {}
    health_by_strat: Dict[str, str] = {}
    for k, v in (health.get("strategies") or {}).items():
        health_by_strat[k] = str(v.get("status") or "ok")

    for s in stats:
        s["health_status"] = health_by_strat.get(s["strategy"], "ok")

    # BTC dominance state
    btc_dom = _json(_ROOT / "runtime" / "btc_dominance_state.json")

    # Regime state
    regime_state = _json(_rt("regime", "orchestrator_state.json"))

    return {
        "days": days,
        "total_strategies": len(stats),
        "strategies": stats,
        "btc_dominance": btc_dom,
        "regime": {
            "regime":          (regime_state or {}).get("regime"),
            "confidence":      (regime_state or {}).get("confidence"),
            "global_risk_mult":(regime_state or {}).get("global_risk_mult"),
            "macro_state":     (regime_state or {}).get("macro", {}).get("state") if regime_state else None,
            "alt_bias":        (regime_state or {}).get("btc_dominance", {}).get("alt_bias") if regime_state else None,
        } if regime_state else None,
    }
