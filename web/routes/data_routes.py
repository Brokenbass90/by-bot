"""Read-only data API — trades, account, regime, allocator, Alpaca, equity curve."""

from __future__ import annotations

import csv
import json
import math
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import ssl
import urllib.parse
import urllib.request

from fastapi import APIRouter, Depends, HTTPException, Query

from bot.alpaca_truth import build_alpaca_live_truth
from ..deps import require_admin, require_auth

router = APIRouter(prefix="/api", tags=["data"])

# ── project root & path helpers ───────────────────────────────────────────────

_ROOT = Path(__file__).parent.parent.parent
_RUNTIME_ROOT = Path(os.getenv("WEB_RUNTIME_ROOT", str(_ROOT / "runtime")))
_INCLUDE_BACKTEST_TRADES = os.getenv("WEB_INCLUDE_BACKTEST_TRADES", "0").strip().lower() in {"1", "true", "yes"}

SETUP_SCANNER_GEOMETRY_MAX_AGE_SEC = 21_600
SETUP_SCANNER_ROUTER_MAX_AGE_SEC = 28_800
SETUP_SCANNER_ALLOCATOR_MAX_AGE_SEC = 10_800
SETUP_SCANNER_SCORE_SEMANTICS = "heuristic_rank_not_probability"
_EPOCH_SECONDS_MAX_ABS = 10_000_000_000


def _rt(*p: str) -> Path:
    return _RUNTIME_ROOT / Path(*p)


def _epoch_ms(value: int) -> int:
    """Normalize a Unix timestamp expressed in seconds or milliseconds."""
    timestamp = int(value)
    if timestamp and abs(timestamp) < _EPOCH_SECONDS_MAX_ABS:
        return timestamp * 1000
    return timestamp


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


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(out):
        return default
    return out


def _profile_hits_by_symbol(router_state: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    hits: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for env_key, profile in (router_state.get("profiles") or {}).items():
        label = str(env_key or "").replace("_SYMBOL_ALLOWLIST", "")
        score_by_symbol: Dict[str, Dict[str, Any]] = {}
        geometry = profile.get("geometry") if isinstance(profile, dict) else None
        for row in (geometry or {}).get("symbol_scores") or []:
            sym = str(row.get("symbol") or "").strip()
            if sym:
                score_by_symbol[sym] = row
        for sym in profile.get("symbols") or []:
            symbol = str(sym or "").strip()
            if not symbol:
                continue
            score_row = score_by_symbol.get(symbol, {})
            hits[symbol].append({
                "profile": label,
                "score": round(_as_float(score_row.get("score"), 0.0), 3),
                "reasons": list(score_row.get("reasons") or [])[:4],
            })
    for symbol in hits:
        hits[symbol].sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return hits


def _allocator_sleeve_map(allocator_state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    sleeves = allocator_state.get("sleeves") or {}
    if isinstance(sleeves, list):
        return {str(s.get("name") or ""): s for s in sleeves if isinstance(s, dict)}
    if isinstance(sleeves, dict):
        return {str(k): v for k, v in sleeves.items() if isinstance(v, dict)}
    return {}


def _nearest_level(snapshot: Dict[str, Any], side: str) -> Optional[Dict[str, Any]]:
    levels = (snapshot.get("nearest_levels") or {}).get(side) or []
    return levels[0] if levels else None


def _dist_atr(price: float, level_price: float, atr: float) -> Optional[float]:
    if price <= 0 or level_price <= 0 or atr <= 0:
        return None
    return abs(level_price - price) / atr


def _setup_card(
    *,
    symbol: str,
    interval: str,
    setup_type: str,
    side: str,
    strategy: str,
    score: float,
    price: float,
    level: Optional[Dict[str, Any]],
    atr: float,
    invalidation: Optional[float],
    reasons: List[str],
    router_hits: List[Dict[str, Any]],
    sleeve_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    level_price = _as_float((level or {}).get("price"), 0.0)
    level_dist = _dist_atr(price, level_price, atr) if level_price else None
    sleeve = sleeve_map.get(strategy) or {}
    runtime_risk = _as_float(
        sleeve.get("final_risk_mult", sleeve.get("runtime_final_risk_mult", 0.0)),
        0.0,
    )
    return {
        "symbol": symbol,
        "interval": interval,
        "setup_type": setup_type,
        "side": side,
        "strategy": strategy,
        "score": round(score, 2),
        "price": round(price, 8),
        "level_price": round(level_price, 8) if level_price else None,
        "level_touches": int(_as_float((level or {}).get("touches"), 0.0)),
        "level_side": (level or {}).get("side_bias"),
        "distance_atr": round(level_dist, 2) if level_dist is not None else None,
        "invalidation": round(invalidation, 8) if invalidation else None,
        "reasons": [r for r in reasons if r][:6],
        "router_profiles": router_hits[:4],
        "runtime": {
            "enabled": bool(sleeve.get("enabled", sleeve.get("runtime_enabled", False))),
            "risk_mult": round(runtime_risk, 3),
            "health": str(sleeve.get("health_status") or sleeve.get("runtime_health") or "unknown"),
        },
    }


def _build_setup_cards(
    geometry_state: Dict[str, Any],
    router_state: Dict[str, Any],
    allocator_state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    profile_hits = _profile_hits_by_symbol(router_state)
    sleeve_map = _allocator_sleeve_map(allocator_state)
    cards: List[Dict[str, Any]] = []

    for symbol, intervals in (geometry_state.get("symbols") or {}).items():
        if not isinstance(intervals, dict):
            continue
        for interval, snapshot in intervals.items():
            if not isinstance(snapshot, dict) or snapshot.get("status") != "ok":
                continue
            price = _as_float(snapshot.get("current_price"), 0.0)
            atr = _as_float(snapshot.get("atr"), 0.0)
            if price <= 0 or atr <= 0:
                continue
            flags = snapshot.get("flags") or {}
            channel = snapshot.get("channel") or {}
            compression = snapshot.get("compression") or {}
            trend = str(flags.get("trend_label") or "")
            level_context = str(flags.get("level_context") or "")
            channel_pos = _as_float(channel.get("position"), 0.5)
            channel_r2 = _as_float(channel.get("r2"), 0.0)
            is_compressed = bool(compression.get("is_compressed") or flags.get("is_compressed"))
            compression_ratio = _as_float(compression.get("compression_ratio"), 1.0)
            above = _nearest_level(snapshot, "above")
            below = _nearest_level(snapshot, "below")
            above_dist = _dist_atr(price, _as_float((above or {}).get("price"), 0.0), atr) if above else None
            below_dist = _dist_atr(price, _as_float((below or {}).get("price"), 0.0), atr) if below else None
            router_hits = profile_hits.get(str(symbol), [])
            common_reasons = [
                trend.replace("_", " ") if trend else "",
                level_context.replace("_", " ") if level_context else "",
                "compressed" if is_compressed else "",
                f"channel r2 {channel_r2:.2f}" if channel_r2 else "",
            ]

            if above and above_dist is not None and above_dist <= 0.9:
                touches = _as_float(above.get("touches"), 0.0)
                score = 62 + touches * 3 + max(0, 0.9 - above_dist) * 18 + max(0, channel_pos - 0.65) * 18
                cards.append(_setup_card(
                    symbol=str(symbol), interval=str(interval), setup_type="resistance fade",
                    side="SHORT", strategy="flat", score=score, price=price, level=above, atr=atr,
                    invalidation=_as_float(above.get("price"), price) + atr * 0.35,
                    reasons=common_reasons + ["near resistance", "candidate for ARF1/flat"],
                    router_hits=router_hits, sleeve_map=sleeve_map,
                ))
                if is_compressed:
                    breakout_score = 58 + touches * 2 + max(0, 0.9 - above_dist) * 16 + (1 - compression_ratio) * 18
                    cards.append(_setup_card(
                        symbol=str(symbol), interval=str(interval), setup_type="breakout watch",
                        side="LONG", strategy="breakout", score=breakout_score, price=price, level=above, atr=atr,
                        invalidation=_as_float(above.get("price"), price) - atr * 0.45,
                        reasons=common_reasons + ["compressed below resistance", "wait for breakout + retest"],
                        router_hits=router_hits, sleeve_map=sleeve_map,
                    ))

            if below and below_dist is not None and below_dist <= 0.9:
                touches = _as_float(below.get("touches"), 0.0)
                score = 62 + touches * 3 + max(0, 0.9 - below_dist) * 18 + max(0, 0.35 - channel_pos) * 18
                cards.append(_setup_card(
                    symbol=str(symbol), interval=str(interval), setup_type="support bounce",
                    side="LONG", strategy="asb1", score=score, price=price, level=below, atr=atr,
                    invalidation=_as_float(below.get("price"), price) - atr * 0.35,
                    reasons=common_reasons + ["near support", "candidate for bounce/ASB1"],
                    router_hits=router_hits, sleeve_map=sleeve_map,
                ))
                if is_compressed or trend == "trend_down":
                    breakdown_score = 58 + touches * 2 + max(0, 0.9 - below_dist) * 16 + (1 - compression_ratio) * 18
                    cards.append(_setup_card(
                        symbol=str(symbol), interval=str(interval), setup_type="breakdown watch",
                        side="SHORT", strategy="breakdown", score=breakdown_score, price=price, level=below, atr=atr,
                        invalidation=_as_float(below.get("price"), price) + atr * 0.45,
                        reasons=common_reasons + ["support pressure", "wait for breakdown + retest"],
                        router_hits=router_hits, sleeve_map=sleeve_map,
                    ))

            if trend == "trend_down" and channel_pos >= 0.68:
                ref_level = above or {"price": channel.get("upper"), "touches": 0, "side_bias": "channel"}
                score = 60 + channel_r2 * 18 + max(0, channel_pos - 0.68) * 25
                cards.append(_setup_card(
                    symbol=str(symbol), interval=str(interval), setup_type="bear continuation",
                    side="SHORT", strategy="brc1", score=score, price=price, level=ref_level, atr=atr,
                    invalidation=price + atr * 1.2,
                    reasons=common_reasons + ["down-channel upper half", "BRC1 shadow candidate"],
                    router_hits=router_hits, sleeve_map=sleeve_map,
                ))

            if trend == "trend_up" and channel_pos <= 0.32:
                ref_level = below or {"price": channel.get("lower"), "touches": 0, "side_bias": "channel"}
                score = 60 + channel_r2 * 18 + max(0, 0.32 - channel_pos) * 25
                cards.append(_setup_card(
                    symbol=str(symbol), interval=str(interval), setup_type="trend pullback",
                    side="LONG", strategy="att1", score=score, price=price, level=ref_level, atr=atr,
                    invalidation=price - atr * 1.2,
                    reasons=common_reasons + ["up-channel pullback", "ATT1/midterm candidate"],
                    router_hits=router_hits, sleeve_map=sleeve_map,
                ))

            if is_compressed and (above_dist is None or above_dist > 0.9) and (below_dist is None or below_dist > 0.9):
                score = 52 + (1 - compression_ratio) * 22 + channel_r2 * 8
                cards.append(_setup_card(
                    symbol=str(symbol), interval=str(interval), setup_type="volatility squeeze",
                    side="BOTH", strategy="ivb1", score=score, price=price, level=None, atr=atr,
                    invalidation=None,
                    reasons=common_reasons + ["compressed away from nearest level", "needs trigger candle"],
                    router_hits=router_hits, sleeve_map=sleeve_map,
                ))

    cards.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return cards[:80]


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


_MONTHLY_NUMERIC_FIELDS = (
    "compounded_return_pct", "profit_factor", "winrate_pct", "trades",
    "months", "calendar_months", "negative_months", "max_monthly_dd_pct",
    "positive_months", "inactive_months", "avg_trade_return_pct",
    "avg_month_return_pct", "positive_months_pct",
)


def _coerce_monthly_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(summary or {})
    for field in _MONTHLY_NUMERIC_FIELDS:
        if field in out and out[field] not in ("", None):
            try:
                out[field] = float(out[field])
            except (TypeError, ValueError):
                pass
    return out


def _clean_monthly_picks(picks: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    clean_picks: List[Dict[str, Any]] = []
    for pick in picks:
        cp: Dict[str, Any] = dict(pick)
        for field in (
            "score", "base_score", "overlay_score", "selection_score",
            "entry_price", "stop_price", "target_price", "weight",
            "atr20_pct", "momentum20_pct", "momentum60_pct",
            "pullback60_pct", "universe_score", "corr_penalty",
            "max_corr_to_existing",
        ):
            if field in cp and cp[field] not in ("", None):
                try:
                    cp[field] = float(cp[field])
                except (TypeError, ValueError):
                    pass
        clean_picks.append(cp)
    return clean_picks


def _load_alpaca_monthly_variant(runtime_name: str, *, label: str) -> Dict[str, Any]:
    runtime_dir = _rt(runtime_name)
    picks = _clean_monthly_picks(_load_monthly_picks(runtime_dir))
    summary_rows = _read_csv(runtime_dir / "latest_summary.csv")
    if not summary_rows:
        summary_rows = _read_csv(runtime_dir / "summary.csv")
    if not summary_rows:
        summary_rows = _read_csv(runtime_dir / "current_cycle_summary.csv")
    summary = _coerce_monthly_summary(summary_rows[0] if summary_rows else {})
    refresh = _read_env(runtime_dir / "latest_refresh.env")
    return {
        "id": runtime_name,
        "label": label,
        "exists": runtime_dir.exists(),
        "age_sec": _file_age_sec(runtime_dir / "latest_summary.csv"),
        "current_picks_count": len(picks),
        "current_picks": picks,
        "summary": summary,
        "latest_refresh_utc": refresh.get("EQ_LATEST_REFRESH_UTC") or refresh.get("ALPACA_REFRESH_UTC") or "",
        "current_picks_missing": not (runtime_dir / "current_cycle_picks.csv").exists(),
    }


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
    state = (_json(_rt(state_cfg_name)) or _json(_cfg(state_cfg_name))) if state_cfg_name else None
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
        "monthly_managed_positions": list(advisory.get("monthly_managed_positions") or []),
        "pending_close_positions": list(advisory.get("pending_close_positions") or []),
        "remote_only_positions": list(advisory.get("remote_only_positions") or []),
        "today_pnl_usd": advisory.get("today_pnl_usd"),
        "pnl_status": "paper_journal_verify_fills",
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


def _live_events_path() -> Path:
    mirror_path = _RUNTIME_ROOT / "live_mirror" / "live_trade_events.jsonl"
    if mirror_path.exists():
        return mirror_path
    return _RUNTIME_ROOT / "live_trade_events.jsonl"


def _iter_live_close_events() -> List[Dict[str, Any]]:
    path = _live_events_path()
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not raw.strip():
                continue
            try:
                event = json.loads(raw)
            except Exception:
                continue
            if event.get("event") == "close" and event.get("pnl") is not None:
                rows.append(event)
    except Exception:
        return []
    return rows


def _event_epoch(event: Dict[str, Any]) -> Optional[float]:
    raw = event.get("ts")
    try:
        if raw is not None and raw != "":
            value = float(raw)
            return value / 1000.0 if value > 1e12 else value
    except Exception:
        pass
    raw_iso = event.get("ts_utc") or event.get("close_time") or event.get("exit_ts")
    try:
        if raw_iso:
            return datetime.fromisoformat(str(raw_iso).replace(" UTC", "+00:00").replace("Z", "+00:00")).timestamp()
    except Exception:
        return None
    return None


def _period_start(period: str) -> Optional[float]:
    now = datetime.now(timezone.utc)
    period = (period or "month").strip().lower()
    if period == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    if period == "week":
        return (now - timedelta(days=7)).timestamp()
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
    if period == "year":
        return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
    return None


def _operator_pnl_payload(period: str) -> Dict[str, Any]:
    since = _period_start(period)
    rows: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"sleeve": "", "trades": 0, "win": 0, "loss": 0, "pnl": 0.0, "fees": 0.0}
    )
    total = {"pnl": 0.0, "fees": 0.0, "trades": 0}
    for event in _iter_live_close_events():
        ts = _event_epoch(event)
        if since is not None and (ts is None or ts < since):
            continue
        sleeve = str(event.get("strategy") or "unknown")
        row = rows[sleeve]
        row["sleeve"] = sleeve
        try:
            pnl = float(event.get("pnl") or 0.0)
        except Exception:
            pnl = 0.0
        try:
            fees = float(event.get("fees") or 0.0)
        except Exception:
            fees = 0.0
        row["trades"] += 1
        row["pnl"] += pnl
        row["fees"] += fees
        row["win" if pnl > 0 else "loss"] += 1
        total["pnl"] += pnl
        total["fees"] += fees
        total["trades"] += 1
    out_rows = sorted(rows.values(), key=lambda row: float(row["pnl"]))
    for row in out_rows:
        row["pnl"] = round(float(row["pnl"]), 6)
        row["fees"] = round(float(row["fees"]), 6)
    total["pnl"] = round(float(total["pnl"]), 6)
    total["fees"] = round(float(total["fees"]), 6)
    return {"period": period, "rows": out_rows, "total": total, "source": str(_live_events_path())}


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
        default_alive_sec = "300" if _RUNTIME_ROOT != (_ROOT / "runtime") else "120"
        alive_threshold_sec = int(os.getenv("WEB_HEARTBEAT_ALIVE_SEC", default_alive_sec) or default_alive_sec)
        bot_alive = hb_age < alive_threshold_sec

    # ── last trade summary + abnormal-no-trades warning (NEW 2026-05-03) ─────
    # Top-bar 1-glance UX: чтобы пользователь увидел "0 trades 5 days" сразу.
    last_trade_age_sec: Optional[int] = None
    last_trade_strategy: Optional[str] = None
    last_trade_symbol: Optional[str] = None
    last_trade_pnl: Optional[float] = None
    today_pnl_total: float = 0.0
    today_trades_count: int = 0
    abnormal_no_trades: bool = False

    def _ts_to_epoch(raw):
        if raw is None or raw == "":
            return None
        try:
            if isinstance(raw, (int, float)):
                v = float(raw)
                return v / 1000.0 if v > 1e12 else v
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
        except Exception:
            return None

    try:
        trades = _load_all_trades()
        if trades:
            latest = trades[0]  # _load_all_trades returns desc-sorted
            cts = _ts_to_epoch(latest.get("close_time") or latest.get("exit_ts"))
            if cts is not None:
                last_trade_age_sec = int(now_ts - cts)
            last_trade_strategy = latest.get("strategy")
            last_trade_symbol = latest.get("symbol")
            try:
                last_trade_pnl = float(latest.get("pnl") or latest.get("pnl_usd") or 0.0)
            except Exception:
                last_trade_pnl = None

        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        for t in trades:
            cts2 = _ts_to_epoch(t.get("close_time") or t.get("exit_ts"))
            if cts2 is not None and cts2 >= today_start:
                today_trades_count += 1
                try:
                    today_pnl_total += float(t.get("pnl") or t.get("pnl_usd") or 0.0)
                except Exception:
                    pass

        warn_threshold = int(os.getenv("WEB_NO_TRADES_WARN_HOURS", "24") or 24) * 3600
        if bot_alive and (last_trade_age_sec is None or last_trade_age_sec > warn_threshold):
            abnormal_no_trades = True
    except Exception:
        # never fail /status because of trade-loading issues
        pass

    return {
        "bot_alive": bot_alive,
        "heartbeat_age_sec": hb_age,
        "heartbeat_alive_threshold_sec": alive_threshold_sec if hb_path.exists() else None,
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
        # NEW (2026-05-03): top-bar 1-glance summary
        "last_trade_age_sec": last_trade_age_sec,
        "last_trade_strategy": last_trade_strategy,
        "last_trade_symbol": last_trade_symbol,
        "last_trade_pnl": last_trade_pnl,
        "today_pnl_total": round(today_pnl_total, 4),
        "today_trades_count": today_trades_count,
        "abnormal_no_trades": abnormal_no_trades,
        "runtime_root": str(_RUNTIME_ROOT),
        "data_mode": "live_mirror" if _RUNTIME_ROOT != (_ROOT / "runtime") else "local",
        "ts_utc": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/heartbeat")
async def operator_heartbeat(_: str = Depends(require_auth)):
    """Compact heartbeat contract used by the additive operator console."""
    hb = _json(_rt("bot_heartbeat.json")) or {}
    if not hb:
        hb = _json(_RUNTIME_ROOT / "live_mirror" / "bot_heartbeat.json") or {}
    return {
        "trade_on": bool(hb.get("trade_on")),
        "dry_run": hb.get("dry_run"),
        "regime": hb.get("regime", "unknown"),
        "open_trades": hb.get("open_trades", 0),
        "bybit_msgs": hb.get("bybit_msgs", 0),
        "risk_per_trade_pct": hb.get("risk_per_trade_pct"),
        "allocator_global_risk_mult": hb.get("allocator_global_risk_mult"),
        "orch_global_risk_mult": hb.get("orch_global_risk_mult"),
        "ts": hb.get("ts"),
    }


@router.get("/pnl")
async def operator_pnl(period: str = Query("month"), _: str = Depends(require_auth)):
    """P&L contract used by the additive operator console."""
    if period not in {"day", "week", "month", "year", "all"}:
        raise HTTPException(status_code=400, detail="period must be day|week|month|year|all")
    return _operator_pnl_payload(period)


@router.get("/strategy-catalog")
async def operator_strategy_catalog(_: str = Depends(require_auth)):
    """Read-only strategy catalog for web and on-board AI."""
    try:
        from bot.strategy_catalog import build_strategy_catalog
        return build_strategy_catalog()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"strategy catalog unavailable: {exc}")


@router.get("/ai/tools")
async def ai_toolbox_manifest(_: str = Depends(require_auth)):
    from bot.ai_tools import available_tools
    return {"tools": available_tools()}


@router.get("/ai/pulse")
async def ai_pulse(_: str = Depends(require_auth)):
    from bot.ai_tools import get_pulse
    return {"text": get_pulse()}


@router.get("/ai/codemap")
async def ai_codemap(_: str = Depends(require_auth)):
    from bot.ai_tools import get_codemap
    return get_codemap()


@router.get("/ai/code/list")
async def ai_code_list(subdir: str = Query("strategies"), _: str = Depends(require_admin)):
    from bot.ai_tools import list_modules
    return {"files": list_modules(subdir)}


@router.get("/ai/code/read")
async def ai_code_read(path: str = Query(...), _: str = Depends(require_admin)):
    from bot.ai_tools import read_code
    return {"path": path, "content": read_code(path)}


@router.get("/ai/code/search")
async def ai_code_search(
    pattern: str = Query(...),
    subdir: str = Query("strategies"),
    _: str = Depends(require_admin),
):
    from bot.ai_tools import search_code
    return {"matches": search_code(pattern, subdir)}


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
    interval: str = Query("5", pattern=r"^(1|3|5|15|30|60|120|240|D)$"),
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
    # Live-position snapshots use epoch seconds, while journal rows and
    # Date.now() use epoch milliseconds.  Normalize each value independently
    # before building the Bybit/cache window so mixed inputs are safe.
    entry_ts = _epoch_ms(entry_ts)
    exit_ts = _epoch_ms(exit_ts)

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
            "runtime_symbols": list(runtime.get("symbols") or [])[:24],
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
    live_monthly = build_alpaca_live_truth(_ROOT, runtime_root=_RUNTIME_ROOT)
    monthly_dir = _rt("equities_monthly_v36")
    monthly_v38 = _load_alpaca_monthly_variant(
        "equities_monthly_v36",
        label="v38 Hybrid Monthly",
    )
    monthly_v38_active = _load_alpaca_monthly_variant(
        "equities_monthly_v38_more_active_research",
        label="v38-active Monthly Research",
    )
    picks = monthly_v38["current_picks"]
    advisory = _json(monthly_dir / "latest_advisory.json")
    intraday_state = _json(_rt("intraday_state.json")) or _json(_cfg("intraday_state.json"))
    intraday_v1 = _load_alpaca_intraday_variant("equities_intraday_dynamic_v1", label="Intraday Dynamic v1", state_cfg_name="intraday_state.json")
    intraday_v3_shadow = _load_alpaca_intraday_variant("equities_intraday_dynamic_v3_shadow", label="Intraday Dynamic v3 Shadow", state_cfg_name="intraday_state_v3_shadow.json")

    summary = monthly_v38["summary"]
    clean_picks = picks

    intraday_positions = _extract_intraday_positions(intraday_state)
    monthly_refresh = _read_env(monthly_dir / "latest_refresh.env")
    monthly_cycle_summary = {
        "exists": monthly_dir.exists(),
        "age_sec": _file_age_sec(monthly_dir / "latest_summary.csv"),
        "current_picks_missing": not (monthly_dir / "current_cycle_picks.csv").exists(),
        "latest_refresh_utc": monthly_refresh.get("EQ_LATEST_REFRESH_UTC") or monthly_refresh.get("ALPACA_REFRESH_UTC") or "",
    }
    variants = [
        monthly_v38,
        monthly_v38_active,
        intraday_v1,
        intraday_v3_shadow,
    ]

    return {
        "live_monthly": live_monthly,
        "current_picks": clean_picks,
        "summary": summary,
        "advisory": (advisory or {}).get("report", advisory),
        "intraday_positions": intraday_positions,
        "intraday_updated_utc": (intraday_state or {}).get("updated_utc"),
        "variants": variants,
        "monthly_variants": [monthly_v38, monthly_v38_active],
        "monthly_cycle": monthly_cycle_summary,
        "v38_active": monthly_v38_active,
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


@router.get("/setup-scanner")
async def get_setup_scanner(
    _: str = Depends(require_auth),
):
    """Geometry/router driven setup candidates for the operator dashboard."""
    geometry_path = _rt("geometry", "geometry_state.json")
    router_path = _rt("router", "symbol_router_state.json")
    allocator_path = _rt("control_plane", "portfolio_allocator_state.json")

    source_specs = {
        "geometry": (geometry_path, SETUP_SCANNER_GEOMETRY_MAX_AGE_SEC),
        "router": (router_path, SETUP_SCANNER_ROUTER_MAX_AGE_SEC),
        "allocator": (allocator_path, SETUP_SCANNER_ALLOCATOR_MAX_AGE_SEC),
    }
    source_states: Dict[str, Dict[str, Any]] = {}
    source_ages: Dict[str, Optional[int]] = {}
    blockers: List[str] = []
    for name, (path, max_age_sec) in source_specs.items():
        age_sec = _file_age_sec(path)
        state = _json(path)
        source_ages[name] = age_sec
        if (
            age_sec is None
            or age_sec > max_age_sec
            or not isinstance(state, dict)
            or not state
        ):
            blockers.append(f"{name}_missing_or_stale")
            continue
        source_states[name] = state

    authoritative = not blockers
    geometry_state = source_states.get("geometry", {}) if authoritative else {}
    router_state = source_states.get("router", {}) if authoritative else {}
    allocator_state = source_states.get("allocator", {}) if authoritative else {}
    cards = _build_setup_cards(geometry_state, router_state, allocator_state) if authoritative else []

    active_sleeves = []
    for name, sleeve in _allocator_sleeve_map(allocator_state).items():
        if bool(sleeve.get("enabled", sleeve.get("runtime_enabled", False))) or _as_float(sleeve.get("final_risk_mult"), 0.0) > 0:
            active_sleeves.append({
                "name": name,
                "risk_mult": round(_as_float(sleeve.get("final_risk_mult", sleeve.get("runtime_final_risk_mult", 0.0)), 0.0), 3),
                "health": str(sleeve.get("health_status") or sleeve.get("runtime_health") or "unknown"),
                "symbols": list(sleeve.get("symbols") or [])[:12],
            })
    active_sleeves.sort(key=lambda x: x.get("risk_mult", 0.0), reverse=True)

    return {
        "authoritative": authoritative,
        "blockers": blockers,
        "score_semantics": SETUP_SCANNER_SCORE_SEMANTICS,
        "freshness_max_age_sec": {
            name: max_age_sec for name, (_path, max_age_sec) in source_specs.items()
        },
        "generated_at_utc": geometry_state.get("generated_at_utc"),
        "geometry_age_sec": source_ages["geometry"],
        "router_age_sec": source_ages["router"],
        "allocator_age_sec": source_ages["allocator"],
        "symbols_analyzed": geometry_state.get("symbols_analyzed") or len(geometry_state.get("symbols") or {}),
        "snapshots_built": geometry_state.get("snapshots_built"),
        "intervals": geometry_state.get("intervals") or [],
        "regime": router_state.get("regime") or allocator_state.get("regime"),
        "confidence": router_state.get("confidence"),
        "allocator_status": allocator_state.get("status"),
        "safe_mode": bool(allocator_state.get("safe_mode")) if authoritative else None,
        "active_sleeves": active_sleeves,
        "cards": cards,
        "notes": [
            "Scanner cards are candidates, not trade approvals.",
            "Score is a heuristic rank, not a probability.",
            "Promotion still requires annual/OOS/additivity tests.",
            "AI should rank and explain these setups, not bypass risk gates.",
        ],
    }


@router.get("/setup-scanner/chart")
async def get_setup_scanner_chart(
    symbol: str = Query(..., pattern=r"^[A-Z0-9]{3,24}$"),
    interval: str = Query("60", pattern=r"^(1|3|5|15|30|60|120|240|D)$"),
    limit: int = Query(64, ge=20, le=120),
    _: str = Depends(require_auth),
):
    """Return recent public Bybit candles for an operator setup card."""
    params = urllib.parse.urlencode({
        "category": "linear",
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": limit,
    })
    url = f"https://api.bybit.com/v5/market/kline?{params}"
    candles: List[Dict[str, Any]] = []
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
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": float(row[5]),
                    })
                except (IndexError, TypeError, ValueError):
                    continue
    except Exception:
        pass
    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "source": "bybit_public" if candles else "unavailable",
        "candles": candles,
    }


# ── live-pnl ─────────────────────────────────────────────────────────────────

@router.get("/live-pnl")
async def get_live_pnl(_: str = Depends(require_auth)):
    """
    Live open positions with unrealized PnL.
    Bot writes runtime/live_positions.json every 10 s in heartbeat loop.
    Also returns today's closed PnL from trade journal.
    """
    pos_data = _json(_rt("live_positions.json")) or {}
    positions = pos_data.get("positions") or []
    pos_ts    = pos_data.get("ts")
    pos_age   = int(datetime.now(timezone.utc).timestamp() - pos_ts) if pos_ts else None

    # Today's closed PnL from journal
    today_pnl   = 0.0
    today_count = 0
    week_pnl    = 0.0
    week_count  = 0
    try:
        trades = _load_all_trades()
        now_ts     = datetime.now(timezone.utc).timestamp()
        today_start = now_ts - 86400
        week_start  = now_ts - 7 * 86400

        def _ts(t: dict) -> float | None:
            raw = t.get("close_time") or t.get("exit_ts")
            if raw is None:
                return None
            try:
                if isinstance(raw, (int, float)):
                    v = float(raw)
                    return v / 1000.0 if v > 1e12 else v
                return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
            except Exception:
                return None

        for t in trades:
            cts = _ts(t)
            if cts is None:
                continue
            try:
                pnl = float(t.get("pnl") or t.get("pnl_usd") or 0.0)
            except Exception:
                continue
            if cts >= today_start:
                today_pnl += pnl
                today_count += 1
            if cts >= week_start:
                week_pnl += pnl
                week_count += 1
    except Exception:
        pass

    # Health gate sleeve status
    sleeve_health: dict = {}
    try:
        hd = (
            _json(_rt("strategy_health.json"))
            or _json(_ROOT / "configs" / "strategy_health.json")
            or {}
        )
        for sname, sinfo in (hd.get("strategies") or {}).items():
            short = sname.replace("alt_", "").replace("btc_eth_", "").replace("_v1", "")
            sleeve_health[short] = str(sinfo.get("status", "OK")).upper()
    except Exception:
        pass

    total_upnl = sum(p.get("upnl_usd", 0.0) for p in positions)

    return {
        "positions": positions,
        "positions_count": len(positions),
        "positions_age_sec": pos_age,
        "positions_stale": pos_age is not None and pos_age > 60,
        "trade_on": pos_data.get("trade_on", True),
        "dry_run": pos_data.get("dry_run", False),
        "total_upnl_usd": round(total_upnl, 4),
        "today_pnl_usd": round(today_pnl, 4),
        "today_trades": today_count,
        "week_pnl_usd": round(week_pnl, 4),
        "week_trades": week_count,
        "sleeve_health": sleeve_health,
        "ts_utc": datetime.now(timezone.utc).isoformat(),
    }


# ── sweeps watchdog ───────────────────────────────────────────────────────────

@router.get("/sweeps")
async def get_sweeps(limit: int = 20, _: str = Depends(require_auth)):
    """
    Scan backtest_runs/autoresearch_* directories and return progress + top results.
    """
    import csv as _csv
    import re as _re

    backtest_root = _ROOT / "backtest_runs"
    if not backtest_root.exists():
        return {"sweeps": [], "total": 0}

    dirs = sorted(
        [d for d in backtest_root.iterdir() if d.is_dir() and d.name.startswith("autoresearch_")],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )[:limit]

    sweeps = []
    now_ts = datetime.now(timezone.utc).timestamp()

    for d in dirs:
        prog_path = d / "progress.json"
        ranked_path = d / "ranked_results.csv"
        spec_path   = d / "spec.json"

        prog   = _json(prog_path) or {}
        spec   = _json(spec_path) or {}
        age_s  = int(now_ts - d.stat().st_mtime)

        current = int(prog.get("current", 0))
        total   = int(prog.get("total", 0))
        updated = prog.get("updated_utc", "")

        # Status detection
        if total > 0 and current >= total:
            run_status = "done"
        elif age_s < 3600 and current > 0:
            run_status = "running"
        elif age_s < 7200:
            run_status = "recent"
        else:
            run_status = "old"

        # Parse name + stamp from dir name: autoresearch_STAMP_NAME
        m = _re.match(r"autoresearch_(\d{8}_\d{6})_(.*)", d.name)
        stamp = m.group(1) if m else ""
        name  = m.group(2) if m else d.name

        # Top winners from ranked_results.csv
        winners = []
        try:
            if ranked_path.exists():
                with open(ranked_path, newline="", encoding="utf-8") as f:
                    reader = _csv.DictReader(f)
                    for i, row in enumerate(reader):
                        if i >= 5:
                            break
                        passed = str(row.get("passed", "")).lower() == "true"
                        try:
                            overrides = json.loads(row.get("overrides_json") or "{}")
                        except Exception:
                            overrides = {}
                        winners.append({
                            "rank":           i + 1,
                            "tag":            row.get("tag", ""),
                            "passed":         passed,
                            "score":          _safe_float(row.get("score")),
                            "net_pnl":        _safe_float(row.get("net_pnl")),
                            "profit_factor":  _safe_float(row.get("profit_factor")),
                            "winrate":        _safe_float(row.get("winrate")),
                            "max_drawdown":   _safe_float(row.get("max_drawdown")),
                            "trades":         _safe_int(row.get("trades")),
                            "fail_reasons":   row.get("fail_reasons", ""),
                            "overrides":      overrides,
                        })
        except Exception:
            pass

        passed_count = sum(1 for w in winners if w["passed"])

        sweeps.append({
            "dir":          d.name,
            "name":         name,
            "stamp":        stamp,
            "status":       run_status,
            "age_sec":      age_s,
            "current":      current,
            "total":        total,
            "pct":          round(current / total * 100, 1) if total > 0 else 0,
            "updated_utc":  updated,
            "spec_name":    spec.get("name", name),
            "spec_desc":    spec.get("description", "")[:120],
            "last_passed":  prog.get("last_passed", False),
            "last_pf":      prog.get("last_profit_factor"),
            "last_pnl":     prog.get("last_net_pnl"),
            "winners":      winners,
            "passed_count": passed_count,
        })

    return {
        "sweeps":    sweeps,
        "total":     len(dirs),
        "ts_utc":    datetime.now(timezone.utc).isoformat(),
    }


def _safe_float(v) -> Optional[float]:
    try:
        return round(float(v), 4) if v not in (None, "", "None") else None
    except Exception:
        return None


def _safe_int(v) -> Optional[int]:
    try:
        return int(float(v)) if v not in (None, "", "None") else None
    except Exception:
        return None


# ── Funding rates ─────────────────────────────────────────────────────────────

@router.get("/funding-rates")
async def get_funding_rates(_: str = Depends(require_auth)):
    """
    Return latest funding rates from configs/funding_rates_latest.json.
    Annotates each symbol with a tier: low / medium / high / extreme.
    """
    fr_path = _ROOT / "configs" / "funding_rates_latest.json"
    data: dict = {}
    updated_utc = None
    age_sec = None

    if fr_path.exists():
        try:
            raw = json.loads(fr_path.read_text())
            data = raw.get("rates", {})
            updated_utc = raw.get("updated_utc")
            if updated_utc:
                from datetime import datetime, timezone
                ts = datetime.fromisoformat(updated_utc.replace("Z", "+00:00"))
                age_sec = round((datetime.now(timezone.utc) - ts).total_seconds())
        except Exception:
            pass

    def _tier(rate: float) -> str:
        abs_r = abs(rate)
        if abs_r < 0.0001:   return "low"
        if abs_r < 0.0005:   return "medium"
        if abs_r < 0.001:    return "high"
        return "extreme"

    annotated = {}
    for sym, rate in data.items():
        annotated[sym] = {
            "rate":     rate,
            "rate_pct": round(rate * 100, 5),
            "tier":     _tier(rate),
        }

    return {
        "rates":       annotated,
        "updated_utc": updated_utc,
        "age_sec":     age_sec,
        "stale":       age_sec is not None and age_sec > 600,
        "count":       len(annotated),
    }


@router.get("/coin-screener")
async def coin_screener(
    _: None = Depends(require_auth),
):
    """Latest output from scripts/crypto_coin_screener.py."""
    import json
    sc_path = _ROOT / "runtime" / "coin_screener_latest.json"
    if not sc_path.exists():
        return {
            "available": False,
            "message":   "Run: python3 scripts/crypto_coin_screener.py",
            "updated_utc": None,
        }
    try:
        data = json.loads(sc_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"available": False, "error": str(exc)}

    # Compute staleness
    updated_utc = data.get("updated_utc")
    age_sec = None
    if updated_utc:
        from datetime import datetime, timezone
        try:
            ts = datetime.fromisoformat(updated_utc.replace("Z", "+00:00"))
            age_sec = round((datetime.now(timezone.utc) - ts).total_seconds())
        except Exception:
            pass

    return {
        "available":   True,
        "updated_utc": updated_utc,
        "age_sec":     age_sec,
        "stale":       age_sec is not None and age_sec > 25200,  # 7h
        "scanned":     data.get("scanned", 0),
        "elapsed_sec": data.get("elapsed_sec"),
        "categories":  data.get("categories", {}),
    }


# ── P&L breakdown by sleeve / day / month (Opus 2026-06-08) ──────────────────
# Backbone for the clickable "Today P&L" modal. Reads the live trade-event log
# and aggregates realized P&L per strategy (sleeve), per day and per month.
@router.get("/pnl/by-sleeve")
async def pnl_by_sleeve(_: str = Depends(require_auth)):
    events_path = _RUNTIME_ROOT / "live_mirror" / "live_trade_events.jsonl"
    if not events_path.exists():
        events_path = _RUNTIME_ROOT / "live_trade_events.jsonl"
    def _acc() -> Dict[str, float]:
        return {"pnl": 0.0, "fees": 0.0, "wins": 0, "losses": 0, "trades": 0}
    def _add(d: Dict[str, float], pnl: float, fees: float) -> None:
        d["pnl"] += pnl; d["fees"] += fees; d["trades"] += 1
        d["wins" if pnl >= 0 else "losses"] += 1
    by_sleeve: Dict[str, Dict[str, float]] = defaultdict(_acc)
    by_day: Dict[str, Dict[str, float]] = defaultdict(_acc)
    by_month: Dict[str, Dict[str, float]] = defaultdict(_acc)
    total = _acc()
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("event") != "close" or e.get("pnl") is None:
                continue
            pnl = float(e.get("pnl") or 0.0)
            fees = float(e.get("fees") or 0.0)
            sleeve = str(e.get("strategy") or "unknown")
            day = str(e.get("ts_utc") or "")[:10]
            month = day[:7]
            _add(by_sleeve[sleeve], pnl, fees)
            if day:
                _add(by_day[day], pnl, fees)
            if month:
                _add(by_month[month], pnl, fees)
            _add(total, pnl, fees)
    def _rnd(d):
        return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in d.items()}
    return {
        "total": _rnd(total),
        "by_sleeve": {k: _rnd(v) for k, v in sorted(by_sleeve.items(), key=lambda kv: kv[1]["pnl"])},
        "by_day": {k: _rnd(v) for k, v in sorted(by_day.items())},
        "by_month": {k: _rnd(v) for k, v in sorted(by_month.items())},
    }
