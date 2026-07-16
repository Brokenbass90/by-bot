"""Truth adapter for historical strategy health and current live sleeve evidence.

The project has two intentionally different artifacts:
* configs/strategy_health.json: an equity-curve/research snapshot;
* runtime/portfolio_health.json: recent live closes graded by the running bot.

Operator surfaces must never present the first artifact as fresh live evidence.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict


def _load_dict(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _age_sec(path: Path, *, now: float) -> int | None:
    try:
        return max(0, int(now - path.stat().st_mtime))
    except OSError:
        return None


def load_health_truth(
    root: Path,
    *,
    now: float | None = None,
    historical_max_age_sec: int = 8 * 86400,
    live_max_age_sec: int = 2 * 3600,
) -> Dict[str, Any]:
    now_value = time.time() if now is None else float(now)
    historical_path = root / "configs" / "strategy_health.json"
    live_path = root / "runtime" / "portfolio_health.json"

    historical_payload = _load_dict(historical_path)
    historical_age = _age_sec(historical_path, now=now_value)
    live_payload = _load_dict(live_path)
    live_age = _age_sec(live_path, now=now_value)

    return {
        "historical": {
            "path": str(historical_path),
            "exists": historical_path.exists(),
            "age_sec": historical_age,
            "stale": historical_age is None or historical_age > int(historical_max_age_sec),
            "authority": "historical_research",
            "timestamp": str(historical_payload.get("timestamp") or ""),
            "overall_health": str(historical_payload.get("overall_health") or "unknown"),
            "strategies": dict(historical_payload.get("strategies") or {}),
        },
        "live": {
            "path": str(live_path),
            "exists": live_path.exists(),
            "age_sec": live_age,
            "stale": live_age is None or live_age > int(live_max_age_sec),
            "authority": "live_closes_alert_only",
            "ts": live_payload.get("ts"),
            "sleeves": dict(live_payload.get("sleeves") or {}),
            "degraded_sleeves": list(live_payload.get("degraded_sleeves") or []),
            "halted_sleeves": list(live_payload.get("halted_sleeves") or []),
        },
    }


def compact_age(age_sec: int | None) -> str:
    if age_sec is None:
        return "missing"
    if age_sec < 120:
        return f"{age_sec}s"
    if age_sec < 7200:
        return f"{age_sec / 60.0:.0f}m"
    if age_sec < 172800:
        return f"{age_sec / 3600.0:.1f}h"
    return f"{age_sec / 86400.0:.1f}d"
