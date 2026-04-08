from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from scripts.equity_curve_autopilot import (
    _analyze_strategy,
    _find_latest_run,
    _load_trades,
    _overall_status,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TIMELINE_PATH = ROOT / "runtime" / "control_plane" / "strategy_health_timeline.json"
CURRENT_HEALTH_PATH = ROOT / "configs" / "strategy_health.json"


def _fallback_latest_portfolio_run() -> Path | None:
    candidates: List[Path] = []
    search_roots = [ROOT / "backtest_runs", ROOT / "backtest_archive"]
    for base in search_roots:
        if not base.exists():
            continue
        for csv_path in base.glob("portfolio_*/trades.csv"):
            run_dir = csv_path.parent
            name = run_dir.name.lower()
            if any(marker in name for marker in ("sweep", "probe", "smoke", "debug", "candidate", "autoresearch")):
                continue
            candidates.append(run_dir)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _fallback_run_from_health() -> Path | None:
    try:
        if not CURRENT_HEALTH_PATH.exists():
            return None
        payload = json.loads(CURRENT_HEALTH_PATH.read_text(encoding="utf-8"))
        run_dir = str(payload.get("run_dir") or "").strip()
        if not run_dir:
            return None
        p = Path(run_dir)
        if not p.is_absolute():
            p = ROOT / "backtest_runs" / run_dir
        return p if p.exists() else None
    except Exception:
        return None


def _checkpoint_datetimes(trades_end_ts: List[int], step_days: int) -> List[datetime]:
    if not trades_end_ts:
        return []
    step_days = max(1, int(step_days or 15))
    first_dt = datetime.fromtimestamp(min(trades_end_ts), tz=timezone.utc)
    last_dt = datetime.fromtimestamp(max(trades_end_ts), tz=timezone.utc)
    cur = first_dt.replace(hour=23, minute=59, second=59, microsecond=0)
    end = last_dt.replace(hour=23, minute=59, second=59, microsecond=0)
    points: List[datetime] = []
    while cur <= end:
        points.append(cur)
        cur += timedelta(days=step_days)
    if not points or points[-1] != end:
        points.append(end)
    return points


def _serialize_health(now_ts: int, run_dir: Path, healths: List[Any]) -> Dict[str, Any]:
    now_utc = datetime.fromtimestamp(int(now_ts), tz=timezone.utc)
    overall = _overall_status(healths)
    return {
        "timestamp": now_utc.isoformat(),
        "run_dir": run_dir.name,
        "strategies": {
            h.name: {
                "status": h.status,
                "total_pnl": round(h.total_pnl, 4),
                "rolling_30d_pnl": round(h.rolling_30d_pnl, 4),
                "rolling_60d_pnl": round(h.rolling_60d_pnl, 4),
                "curve_vs_ma20": round(h.curve_vs_ma20, 4),
                "trades_total": int(h.trades_total),
                "trades_30d": int(h.trades_30d),
                "winrate_total": round(h.winrate_total, 3),
                "winrate_30d": round(h.winrate_30d, 3),
                "pf_30d": round(h.pf_30d, 3),
                "notes": h.notes,
            }
            for h in healths
        },
        "paused_strategies": [h.name for h in healths if h.status in ("PAUSE", "KILL")],
        "overall_health": overall,
    }


def build_strategy_health_timeline(run_dir: Path | None = None, *, step_days: int = 15) -> Dict[str, Any]:
    chosen_run = run_dir or _find_latest_run() or _fallback_run_from_health() or _fallback_latest_portfolio_run()
    if chosen_run is None or not chosen_run.exists():
        raise FileNotFoundError("No trusted run directory available for health timeline.")

    trades = _load_trades(chosen_run)
    if not trades:
        raise RuntimeError(f"No trades found in {chosen_run}")

    checkpoints = _checkpoint_datetimes([int(t.exit_ts) for t in trades], int(step_days))
    by_strategy: Dict[str, List[Any]] = {}
    for trade in trades:
        by_strategy.setdefault(str(trade.strategy), []).append(trade)

    snapshots: List[Dict[str, Any]] = []
    for idx, checkpoint_dt in enumerate(checkpoints, start=1):
        checkpoint_ts = int(checkpoint_dt.timestamp())
        healths = []
        for name, per_strategy in sorted(by_strategy.items()):
            eligible = [t for t in per_strategy if int(t.exit_ts) <= checkpoint_ts]
            if not eligible:
                continue
            healths.append(_analyze_strategy(name, eligible, checkpoint_ts))

        payload = _serialize_health(checkpoint_ts, chosen_run, healths)
        payload["checkpoint_index"] = idx
        payload["checkpoint_date_utc"] = checkpoint_dt.date().isoformat()
        payload["checkpoint_ts"] = checkpoint_ts
        payload["health_source"] = "timeline"
        snapshots.append(payload)

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(chosen_run),
        "step_days": int(step_days),
        "snapshots": snapshots,
    }


def select_health_snapshot(
    timeline: Dict[str, Any],
    checkpoint_ts: int,
    *,
    fallback_health: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    fallback = dict(fallback_health or {})
    fallback_strategies = dict(fallback.get("strategies") or {})
    snapshots = list(timeline.get("snapshots") or [])
    chosen: Dict[str, Any] | None = None
    for item in snapshots:
        item_ts = int(item.get("checkpoint_ts") or 0)
        if item_ts <= int(checkpoint_ts):
            chosen = dict(item)
        else:
            break

    if chosen is None:
        chosen = {
            "timestamp": datetime.fromtimestamp(int(checkpoint_ts), tz=timezone.utc).isoformat(),
            "checkpoint_ts": int(checkpoint_ts),
            "health_source": "pre_timeline_fallback",
            "strategies": {},
            "paused_strategies": [],
            "overall_health": "OK",
        }

    timeline_strategies = dict(chosen.get("strategies") or {})
    merged_strategies = dict(timeline_strategies)
    for strategy_name, info in fallback_strategies.items():
        if strategy_name not in merged_strategies:
            merged_strategies[str(strategy_name)] = info

    chosen["strategies"] = merged_strategies
    chosen["fallback_strategy_count"] = max(0, len(merged_strategies) - len(timeline_strategies))
    return chosen


def load_strategy_health_timeline(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}
