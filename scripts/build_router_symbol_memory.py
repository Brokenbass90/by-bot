#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_regime_state import _classify_regime, _fetch_4h  # noqa: E402
from scripts.dynamic_allowlist import _DEFAULT_PROFILES  # noqa: E402


BACKTEST_RUNS = ROOT / "backtest_runs"
REGISTRY_PATH = ROOT / "configs" / "strategy_profile_registry.json"
OUT_PATH = ROOT / "runtime" / "control_plane" / "router_symbol_memory.json"
OUT_HISTORY = ROOT / "runtime" / "control_plane" / "router_symbol_memory_history.jsonl"
FOUR_H_MS = 4 * 60 * 60 * 1000


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _iter_trade_files(root: Path, *, pattern: str, max_files: int) -> List[Path]:
    files = sorted(root.rglob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[: max(1, int(max_files))]


def _load_cached_rows(path: Path) -> List[Dict[str, float]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    out: List[Dict[str, float]] = []
    for item in raw:
        try:
            out.append(
                {
                    "ts": int(item["ts"]),
                    "o": float(item["o"]),
                    "h": float(item["h"]),
                    "l": float(item["l"]),
                    "c": float(item["c"]),
                    "v": float(item["v"]),
                }
            )
        except Exception:
            continue
    out.sort(key=lambda row: int(row["ts"]))
    return out


def _aggregate_rows(rows: List[Dict[str, float]], *, target_ms: int) -> List[Dict[str, float]]:
    buckets: Dict[int, Dict[str, float]] = {}
    order: List[int] = []
    for row in rows:
        bucket_ts = int(row["ts"] // target_ms) * target_ms
        slot = buckets.get(bucket_ts)
        if slot is None:
            slot = {
                "ts": bucket_ts,
                "o": row["o"],
                "h": row["h"],
                "l": row["l"],
                "c": row["c"],
                "v": row["v"],
            }
            buckets[bucket_ts] = slot
            order.append(bucket_ts)
        else:
            slot["h"] = max(slot["h"], row["h"])
            slot["l"] = min(slot["l"], row["l"])
            slot["c"] = row["c"]
            slot["v"] += row["v"]
    return [buckets[ts] for ts in sorted(order)]


def _load_full_btc_cache() -> List[Dict[str, float]]:
    cache_dir = ROOT / "data_cache"
    if not cache_dir.exists():
        return []
    seen: set[int] = set()
    merged: List[Dict[str, float]] = []
    paths_240 = sorted(cache_dir.glob("BTCUSDT_240_*.json"))
    if paths_240:
        for path in paths_240:
            for row in _load_cached_rows(path):
                ts = int(row["ts"])
                if ts in seen:
                    continue
                seen.add(ts)
                merged.append(row)
        merged.sort(key=lambda row: int(row["ts"]))
        return merged

    paths_60 = sorted(cache_dir.glob("BTCUSDT_60_*.json"))
    if paths_60:
        lower: List[Dict[str, float]] = []
        for path in paths_60:
            lower.extend(_load_cached_rows(path))
        if lower:
            return _aggregate_rows(lower, target_ms=FOUR_H_MS)
    return []


def _env_key_matchers(registry: Dict[str, Any]) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for item in registry.get("profiles") or []:
        env_key = str(item.get("env_key") or "").strip().upper()
        for tag in item.get("strategy_tags") or []:
            tag_norm = str(tag or "").strip().lower()
            if not env_key or not tag_norm:
                continue
            pair = (tag_norm, env_key)
            if pair not in seen:
                seen.add(pair)
                pairs.append(pair)
    for profile in _DEFAULT_PROFILES:
        env_key = str(profile.env_key or "").strip().upper()
        for tag in profile.strategy_tags:
            tag_norm = str(tag or "").strip().lower()
            if not env_key or not tag_norm:
                continue
            pair = (tag_norm, env_key)
            if pair not in seen:
                seen.add(pair)
                pairs.append(pair)
    pairs.sort(key=lambda item: len(item[0]), reverse=True)
    return pairs


def _match_env_key(strategy: str, matchers: Iterable[Tuple[str, str]]) -> str | None:
    strategy_norm = str(strategy or "").strip().lower()
    for tag, env_key in matchers:
        if tag and tag in strategy_norm:
            return env_key
    return None


def _btc_regime_for_ts(entry_ts_ms: int, cache: Dict[int, str], *, btc_rows: List[Dict[str, float]]) -> str:
    bucket_end_ms = (int(entry_ts_ms) // FOUR_H_MS + 1) * FOUR_H_MS
    cached = cache.get(bucket_end_ms)
    if cached:
        return cached
    candles = [row for row in btc_rows if int(row["ts"]) < bucket_end_ms]
    candles = candles[-120:]
    if len(candles) < 60:
        candles = _fetch_4h("BTCUSDT", 120, end_ms=bucket_end_ms, cache_only=True)
    if len(candles) < 60:
        regime = "unknown"
    else:
        regime, _ = _classify_regime(candles)
    cache[bucket_end_ms] = regime
    return regime


def _pf(gross_profit: float, gross_loss_abs: float) -> float:
    if gross_loss_abs > 1e-12:
        return gross_profit / gross_loss_abs
    return 9999.0 if gross_profit > 0 else 0.0


def _penalty(stats: Dict[str, Any]) -> Tuple[float, str]:
    trades = int(stats.get("trades") or 0)
    if trades <= 0:
        return 0.0, "no_trades"
    net = float(stats.get("net") or 0.0)
    gross_profit = float(stats.get("gross_profit") or 0.0)
    gross_loss_abs = float(stats.get("gross_loss_abs") or 0.0)
    sl_count = int(stats.get("sl_count") or 0)
    pf = _pf(gross_profit, gross_loss_abs)
    avg_pnl = net / max(1, trades)
    confidence = min(1.0, trades / 12.0)
    pf_pen = 0.0 if pf >= 1.05 else min(1.0, (1.05 - pf) / 0.55)
    avg_pen = 0.0 if avg_pnl >= 0.0 else min(1.0, abs(avg_pnl) / 0.35)
    sl_pen = min(1.0, sl_count / max(1, trades))
    penalty = confidence * (pf_pen * 0.50 + avg_pen * 0.30 + sl_pen * 0.20)
    reasons: List[str] = []
    if pf_pen > 0.0:
        reasons.append(f"pf={pf:.2f}")
    if avg_pen > 0.0:
        reasons.append(f"avg_pnl={avg_pnl:+.3f}")
    if sl_pen > 0.40:
        reasons.append(f"sl_ratio={sl_pen:.2f}")
    if not reasons:
        reasons.append("healthy_or_low_sample")
    return round(min(1.0, penalty), 4), ",".join(reasons)


def _new_bucket() -> Dict[str, Any]:
    return {
        "trades": 0,
        "net": 0.0,
        "wins": 0,
        "gross_profit": 0.0,
        "gross_loss_abs": 0.0,
        "sl_count": 0,
        "tp_count": 0,
        "time_count": 0,
        "source_files": set(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Build per-symbol router memory from historical trades.")
    ap.add_argument("--registry", default=str(REGISTRY_PATH))
    ap.add_argument("--backtest-root", default=str(BACKTEST_RUNS))
    ap.add_argument("--pattern", default="trades.csv", help="File name to search for under backtest root.")
    ap.add_argument("--max-files", type=int, default=200)
    ap.add_argument("--min-trades", type=int, default=3)
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--out-history", default=str(OUT_HISTORY))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    registry_path = Path(args.registry).expanduser()
    if not registry_path.is_absolute():
        registry_path = ROOT / registry_path
    backtest_root = Path(args.backtest_root).expanduser()
    if not backtest_root.is_absolute():
        backtest_root = ROOT / backtest_root
    out_path = Path(args.out).expanduser()
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_history = Path(args.out_history).expanduser()
    if not out_history.is_absolute():
        out_history = ROOT / out_history

    registry = _load_json(registry_path, {"profiles": []})
    matchers = _env_key_matchers(registry)
    trade_files = _iter_trade_files(backtest_root, pattern=str(args.pattern), max_files=int(args.max_files))
    if not trade_files:
        raise FileNotFoundError(f"no trades files under {backtest_root}")

    regime_cache: Dict[int, str] = {}
    btc_rows = _load_full_btc_cache()
    agg: Dict[Tuple[str, str, str], Dict[str, Any]] = defaultdict(_new_bucket)
    used_files = 0
    used_rows = 0

    for path in trade_files:
        try:
            with path.open(newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    strategy = str(row.get("strategy") or "").strip()
                    symbol = str(row.get("symbol") or "").strip().upper()
                    if not strategy or not symbol:
                        continue
                    env_key = _match_env_key(strategy, matchers)
                    if not env_key:
                        continue
                    try:
                        entry_ts = int(float(row.get("entry_ts") or 0))
                    except Exception:
                        entry_ts = 0
                    regime = _btc_regime_for_ts(entry_ts, regime_cache, btc_rows=btc_rows) if entry_ts > 0 else "unknown"
                    pnl = float(row.get("pnl") or 0.0)
                    outcome = str(row.get("outcome") or "").strip().lower()

                    for regime_key in (regime, "all"):
                        bucket = agg[(env_key, regime_key, symbol)]
                        bucket["trades"] += 1
                        bucket["net"] += pnl
                        if pnl > 0:
                            bucket["wins"] += 1
                            bucket["gross_profit"] += pnl
                        elif pnl < 0:
                            bucket["gross_loss_abs"] += abs(pnl)
                        if outcome == "sl":
                            bucket["sl_count"] += 1
                        elif outcome == "tp":
                            bucket["tp_count"] += 1
                        elif outcome == "time":
                            bucket["time_count"] += 1
                        bucket["source_files"].add(path.parent.name)
                    used_rows += 1
            used_files += 1
        except Exception:
            continue

    profiles: Dict[str, Dict[str, Any]] = {}
    summary: Dict[str, Dict[str, Any]] = {}
    for (env_key, regime, symbol), stats in sorted(agg.items()):
        trades = int(stats["trades"])
        if trades < int(args.min_trades):
            continue
        env_block = profiles.setdefault(env_key, {})
        regime_block = env_block.setdefault(regime, {"symbols": {}})
        penalty, reason = _penalty(stats)
        pf = _pf(float(stats["gross_profit"]), float(stats["gross_loss_abs"]))
        symbol_info = {
            "trades": trades,
            "net": round(float(stats["net"]), 6),
            "winrate": round(float(stats["wins"]) / max(1, trades), 4),
            "profit_factor": round(float(pf), 4),
            "sl_ratio": round(float(stats["sl_count"]) / max(1, trades), 4),
            "avg_pnl": round(float(stats["net"]) / max(1, trades), 6),
            "source_files": sorted(stats["source_files"]),
            "source_files_count": len(stats["source_files"]),
            "penalty": penalty,
            "reason": reason,
        }
        regime_block["symbols"][symbol] = symbol_info
        if penalty > 0:
            env_summary = summary.setdefault(env_key, {}).setdefault(regime, {"top_penalties": []})
            env_summary["top_penalties"].append({"symbol": symbol, "penalty": penalty, "reason": reason})

    for env_key, regimes in summary.items():
        for regime, data in regimes.items():
            data["top_penalties"] = sorted(
                data["top_penalties"],
                key=lambda item: (-float(item["penalty"]), item["symbol"]),
            )[:10]

    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "version": 1,
        "generated_at_utc": generated_at,
        "registry_path": str(registry_path),
        "backtest_root": str(backtest_root),
        "pattern": str(args.pattern),
        "max_files": int(args.max_files),
        "used_files": used_files,
        "used_rows": used_rows,
        "min_trades": int(args.min_trades),
        "regime_source": "btc_4h_cache_only",
        "btc_cache_bars": len(btc_rows),
        "profiles": profiles,
        "summary": summary,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_history.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    with out_history.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "generated_at_utc": generated_at,
                    "used_files": used_files,
                    "used_rows": used_rows,
                    "profile_count": len(profiles),
                    "path": str(out_path),
                },
                ensure_ascii=True,
            )
            + "\n"
        )

    if not args.quiet:
        print(f"saved={out_path}")
        print(f"used_files={used_files}")
        print(f"used_rows={used_rows}")
        for env_key, regimes in sorted(summary.items()):
            for regime, data in sorted(regimes.items()):
                top = data.get("top_penalties") or []
                if not top:
                    continue
                preview = ", ".join(f"{item['symbol']}:{item['penalty']:.2f}" for item in top[:5])
                print(f"{env_key} {regime}: {preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
