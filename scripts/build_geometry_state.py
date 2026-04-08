#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.chart_geometry import analyze_geometry  # noqa: E402
from bot.geometry_cache import load_rows  # noqa: E402


ROUTER_STATE_PATH = ROOT / "runtime" / "router" / "symbol_router_state.json"
ALLOWLIST_ENV_PATH = ROOT / "configs" / "dynamic_allowlist_latest.env"
OUT_STATE_PATH = ROOT / "runtime" / "geometry" / "geometry_state.json"
OUT_HISTORY_PATH = ROOT / "runtime" / "geometry" / "geometry_history.jsonl"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    tmp.replace(path)


def _append_history(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _csv_symbols(raw: str) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in str(raw or "").replace(";", ",").split(","):
        sym = item.strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def _symbols_from_router_state(path: Path) -> List[str]:
    state = _load_json(path, {})
    profiles = state.get("profiles") or {}
    out: List[str] = []
    seen: set[str] = set()
    for entry in profiles.values():
        for sym in entry.get("symbols") or []:
            symbol = str(sym or "").strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            out.append(symbol)
    return out


def _symbols_from_allowlist_env(path: Path) -> List[str]:
    if not path.exists():
        return []
    out: List[str] = []
    seen: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if "ALLOWLIST" not in key and not key.endswith("_SYMBOLS"):
            continue
        for sym in _csv_symbols(value):
            if sym in seen:
                continue
            seen.add(sym)
            out.append(sym)
    return out


def _resolve_symbols(*, explicit_symbols: List[str], router_state_path: Path, allowlist_env_path: Path, max_symbols: int) -> List[str]:
    if explicit_symbols:
        return explicit_symbols[: max(1, int(max_symbols))]
    from_router = _symbols_from_router_state(router_state_path)
    if from_router:
        return from_router[: max(1, int(max_symbols))]
    return _symbols_from_allowlist_env(allowlist_env_path)[: max(1, int(max_symbols))]


def _trend_label(snapshot: Dict[str, Any]) -> str:
    channel = dict(snapshot.get("channel") or {})
    slope_pct = _safe_float(channel.get("slope_pct_per_bar"), 0.0)
    r2 = _safe_float(channel.get("r2"), 0.0)
    if r2 >= 0.35 and slope_pct >= 0.02:
        return "trend_up"
    if r2 >= 0.35 and slope_pct <= -0.02:
        return "trend_down"
    return "range_or_transition"


def _level_context(snapshot: Dict[str, Any]) -> str:
    price = _safe_float(snapshot.get("current_price"), 0.0)
    atr = max(_safe_float(snapshot.get("atr"), 0.0), max(price * 0.0015, 1e-12))
    nearest = dict(snapshot.get("nearest_levels") or {})
    above = list(nearest.get("above") or [])
    below = list(nearest.get("below") or [])
    if above:
        dist_above_atr = (_safe_float(above[0].get("price"), price) - price) / atr
        if dist_above_atr <= 0.6:
            return "near_resistance"
    if below:
        dist_below_atr = (price - _safe_float(below[0].get("price"), price)) / atr
        if dist_below_atr <= 0.6:
            return "near_support"
    return "mid_range"


def _quality_flags(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    channel = dict(snapshot.get("channel") or {})
    compression = dict(snapshot.get("compression") or {})
    return {
        "trend_label": _trend_label(snapshot),
        "level_context": _level_context(snapshot),
        "is_compressed": bool(compression.get("is_compressed")),
        "compression_ratio": _safe_float(compression.get("compression_ratio"), 0.0),
        "channel_r2": _safe_float(channel.get("r2"), 0.0),
        "channel_width_pct": _safe_float(channel.get("width_pct"), 0.0),
        "channel_position": _safe_float(channel.get("position"), 0.0),
        "slope_pct_per_bar": _safe_float(channel.get("slope_pct_per_bar"), 0.0),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Build deterministic geometry state for router/advisory usage.")
    ap.add_argument("--symbols", default="", help="Comma-separated explicit symbols. Default: resolve from router state or allowlist env.")
    ap.add_argument("--intervals", default="60,240", help="Comma-separated intervals, e.g. 60,240")
    ap.add_argument("--bars", type=int, default=240, help="Bars per interval for geometry analysis.")
    ap.add_argument("--max-symbols", type=int, default=24)
    ap.add_argument("--router-state", default=str(ROUTER_STATE_PATH))
    ap.add_argument("--allowlist-env", default=str(ALLOWLIST_ENV_PATH))
    ap.add_argument("--out-json", default=str(OUT_STATE_PATH))
    ap.add_argument("--history-jsonl", default=str(OUT_HISTORY_PATH))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    intervals = [str(x).strip() for x in str(args.intervals or "").split(",") if str(x).strip()]
    if not intervals:
        raise SystemExit("No intervals requested")

    explicit_symbols = _csv_symbols(args.symbols)
    router_state_path = Path(args.router_state).expanduser()
    allowlist_env_path = Path(args.allowlist_env).expanduser()
    out_json = Path(args.out_json).expanduser()
    history_jsonl = Path(args.history_jsonl).expanduser()
    if not router_state_path.is_absolute():
        router_state_path = ROOT / router_state_path
    if not allowlist_env_path.is_absolute():
        allowlist_env_path = ROOT / allowlist_env_path
    if not out_json.is_absolute():
        out_json = ROOT / out_json
    if not history_jsonl.is_absolute():
        history_jsonl = ROOT / history_jsonl

    symbols = _resolve_symbols(
        explicit_symbols=explicit_symbols,
        router_state_path=router_state_path,
        allowlist_env_path=allowlist_env_path,
        max_symbols=args.max_symbols,
    )
    if not symbols:
        raise SystemExit("No symbols available from router state or allowlist env")

    symbol_state: Dict[str, Dict[str, Any]] = {}
    missing: List[Dict[str, str]] = []
    analyzed_count = 0
    for symbol in symbols:
        per_interval: Dict[str, Any] = {}
        for interval in intervals:
            rows = load_rows(symbol, interval)
            if not rows:
                missing.append({"symbol": symbol, "interval": interval})
                continue
            snapshot = analyze_geometry(rows[-max(20, int(args.bars)) :])
            if str(snapshot.get("status")) != "ok":
                missing.append({"symbol": symbol, "interval": interval})
                continue
            snapshot["flags"] = _quality_flags(snapshot)
            per_interval[interval] = snapshot
            analyzed_count += 1
        if per_interval:
            symbol_state[symbol] = per_interval

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "state_version": "1",
        "symbol_source": "explicit" if explicit_symbols else ("router" if router_state_path.exists() else "allowlist_env"),
        "intervals": intervals,
        "bars": int(args.bars),
        "requested_symbols": symbols,
        "symbols_analyzed": len(symbol_state),
        "snapshots_built": analyzed_count,
        "missing": missing,
        "symbols": symbol_state,
    }
    if not args.dry_run:
        _write_json_atomic(out_json, payload)
        _append_history(
            history_jsonl,
            {
                "generated_at_utc": payload["generated_at_utc"],
                "symbols_analyzed": payload["symbols_analyzed"],
                "snapshots_built": payload["snapshots_built"],
                "missing_count": len(missing),
                "intervals": intervals,
            },
        )
    if not args.quiet:
        print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
