#!/usr/bin/env python3
"""Extras context for AI on the bot (DeepSeek) — расширенные данные.

Дополняет `scripts/build_ai_full_context.py`. Кладёт второй файл:
`runtime/ai_context/extras.json`, который DeepSeek читает плюсом к
`full_context.json`. Это даёт ИИ ассистенту умения, которых не было:

1. Trade history глубже 5 — последние 200 closed trades с PnL + per-sleeve roll-up.
2. Bot errors — top error/warn lines из runtime/live.out (агрегированные по типу).
3. Indicators snapshot — RSI / ATR / EMA per symbol (если есть в geometry_state).
4. Bybit open orders — снимок из runtime/operator/operator_snapshot.json
   (Codex туда уже пишет, не нужен отдельный API call).
5. OHLC snapshot — последние 100 баров для top-5 символов (если найдём cache).
6. Memory lines — rolling buffer ключевых выводов prior сессий (append-only).

Запуск (cron, рядом с build_ai_full_context.py):
    cd /root/by-bot && python3 scripts/build_ai_extras.py --quiet

Идемпотентно, read-only, ничего не торгует, не правит .env.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "runtime" / "ai_context"
EXTRAS_OUT = OUT_DIR / "extras.json"
MEMORY_OUT = OUT_DIR / "memory_lines.jsonl"
FULL_CONTEXT = OUT_DIR / "full_context.json"

# Источники
LIVE_TRADES = [
    REPO_ROOT / "runtime" / "live_trade_events.jsonl",
    REPO_ROOT / "runtime" / "live_mirror" / "live_trade_events.jsonl",
]
LIVE_LOG = REPO_ROOT / "runtime" / "live.out"
GEOMETRY = REPO_ROOT / "runtime" / "geometry" / "geometry_state.json"
OPERATOR_SNAP = REPO_ROOT / "runtime" / "operator" / "operator_snapshot.json"
KLINES_DIRS = [
    REPO_ROOT / ".cache" / "klines",
    REPO_ROOT / "data_cache",
]


def first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


def load_json(path: Path, fallback: Any = None) -> Any:
    if not path or not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        return {"_error": f"{type(exc).__name__}: {exc}"}


def tail_jsonl(path: Path, n: int) -> list[Any]:
    if not path or not path.exists() or n <= 0:
        return []
    out: list[Any] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-n:]
    except Exception:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            out.append({"_raw": line})
    return out


# --- 1. Trade history с per-sleeve roll-up -------------------------------

def trade_history_summary(tail_n: int = 200) -> dict[str, Any]:
    trades_path = first_existing(LIVE_TRADES)
    if not trades_path:
        return {"_warn": "no live_trade_events.jsonl found"}

    events = tail_jsonl(trades_path, tail_n)
    closed = [e for e in events if isinstance(e, dict) and e.get("event") == "close"]

    per_sleeve: dict[str, dict[str, float]] = defaultdict(lambda: {
        "n_closed": 0, "n_win": 0, "n_loss": 0,
        "gross_win": 0.0, "gross_loss": 0.0, "total_pnl": 0.0,
        "max_win": 0.0, "max_loss": 0.0,
    })
    last_close_ts = 0
    for ev in closed:
        sleeve = str(ev.get("strategy") or "unknown")
        pnl = float(ev.get("pnl") or 0.0)
        ts = int(ev.get("ts") or 0)
        last_close_ts = max(last_close_ts, ts)
        bucket = per_sleeve[sleeve]
        bucket["n_closed"] += 1
        bucket["total_pnl"] += pnl
        if pnl > 0:
            bucket["n_win"] += 1
            bucket["gross_win"] += pnl
            bucket["max_win"] = max(bucket["max_win"], pnl)
        elif pnl < 0:
            bucket["n_loss"] += 1
            bucket["gross_loss"] += pnl
            bucket["max_loss"] = min(bucket["max_loss"], pnl)

    # PF + WR
    for s, b in per_sleeve.items():
        n = b["n_closed"]
        b["winrate_pct"] = round(b["n_win"] / n * 100, 2) if n else 0
        gw = b["gross_win"]
        gl = abs(b["gross_loss"]) or 1e-9
        b["profit_factor"] = round(gw / gl, 3)
        b["avg_pnl"] = round(b["total_pnl"] / n, 4) if n else 0.0

    age_sec = None
    if last_close_ts:
        age_sec = int(datetime.now(tz=timezone.utc).timestamp()) - last_close_ts

    return {
        "source": str(trades_path.relative_to(REPO_ROOT)),
        "events_in_tail": len(events),
        "closed_in_tail": len(closed),
        "per_sleeve": dict(per_sleeve),
        "last_close_age_sec": age_sec,
        "last_5_closes": [
            {
                "ts_utc": e.get("ts_utc"),
                "strategy": e.get("strategy"),
                "symbol": e.get("symbol"),
                "side": e.get("side"),
                "pnl": e.get("pnl"),
                "close_reason": e.get("close_reason"),
            }
            for e in closed[-5:]
        ],
    }


# --- 2. Bot errors summary ----------------------------------------------

ERROR_PATTERNS = [
    re.compile(r"\b(ERROR|CRITICAL|FATAL)\b", re.IGNORECASE),
    re.compile(r"\bretCode\s*[:=]\s*(\d+)", re.IGNORECASE),
    re.compile(r"\bauth.*(failed|expired|invalid)", re.IGNORECASE),
    re.compile(r"\b(Traceback|Exception|RuntimeError|ValueError|KeyError)\b"),
]


def log_errors_summary(max_lines_scan: int = 5000, top_n: int = 20) -> dict[str, Any]:
    if not LIVE_LOG.exists():
        return {"_warn": f"no {LIVE_LOG.relative_to(REPO_ROOT)}"}
    try:
        # Читаем последние N строк (большой файл — читаем хвост)
        with LIVE_LOG.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            chunk = min(size, 1024 * 1024)  # 1 MB max
            f.seek(-chunk, 2)
            buf = f.read().decode("utf-8", errors="ignore")
        lines = buf.splitlines()[-max_lines_scan:]
    except Exception as exc:
        return {"_error": f"log read: {type(exc).__name__}: {exc}"}

    counter: Counter[str] = Counter()
    last_examples: dict[str, str] = {}
    err_lines = 0
    for ln in lines:
        for pat in ERROR_PATTERNS:
            m = pat.search(ln)
            if m:
                err_lines += 1
                # ключ — pattern-имя + первая капча (если есть)
                key = pat.pattern.replace("\\b", "").split("|")[0][:40]
                if m.groups():
                    key = f"{key}:{m.group(1)}"
                counter[key] += 1
                if key not in last_examples:
                    last_examples[key] = ln.strip()[:300]
                break

    top = counter.most_common(top_n)
    return {
        "source": str(LIVE_LOG.relative_to(REPO_ROOT)),
        "lines_scanned": len(lines),
        "error_lines_total": err_lines,
        "top_patterns": [
            {"pattern": k, "count": v, "example": last_examples.get(k, "")}
            for k, v in top
        ],
    }


# --- 3. Indicators snapshot per symbol ----------------------------------

def indicators_snapshot(top_n_symbols: int = 12) -> dict[str, Any]:
    geo = load_json(GEOMETRY, fallback={}) or {}
    if not geo:
        return {"_warn": f"no {GEOMETRY.relative_to(REPO_ROOT)}"}
    symbols_block = geo.get("symbols") or {}
    if not isinstance(symbols_block, dict):
        return {"_warn": "geometry.symbols not a dict"}

    out: dict[str, Any] = {
        "source": str(GEOMETRY.relative_to(REPO_ROOT)),
        "generated_at_utc": geo.get("generated_at_utc"),
        "symbols": {},
    }
    # Берём top_n по abs(rsi - 50) или объёму, если есть; иначе первые
    items = list(symbols_block.items())
    items_sorted = items[: top_n_symbols]

    for sym, payload in items_sorted:
        if not isinstance(payload, dict):
            continue
        # Извлекаем известные индикаторы — структура может варьироваться
        ind = {}
        for tf_key, tf_val in payload.items():
            if not isinstance(tf_val, dict):
                continue
            tf_ind = {}
            for k in ("rsi", "rsi14", "atr", "atr_pct", "ema_fast", "ema_slow",
                      "ema_50", "ema_200", "close", "close_last",
                      "volume_avg", "vol_mult", "trend"):
                if k in tf_val:
                    tf_ind[k] = tf_val[k]
            if tf_ind:
                ind[tf_key] = tf_ind
        if ind:
            out["symbols"][sym] = ind

    out["n_symbols"] = len(out["symbols"])
    return out


# --- 4. Bybit open positions / orders -----------------------------------

def bybit_positions_snapshot() -> dict[str, Any]:
    op = load_json(OPERATOR_SNAP, fallback={}) or {}
    if not op:
        return {"_warn": f"no {OPERATOR_SNAP.relative_to(REPO_ROOT)}"}
    # Codex кладёт в operator_snapshot.json раздел про bybit positions
    keys = ("bybit_positions", "open_positions", "bybit", "positions")
    result = {"source": str(OPERATOR_SNAP.relative_to(REPO_ROOT))}
    for k in keys:
        if k in op:
            result[k] = op[k]
    if len(result) == 1:
        result["_warn"] = "no bybit-positions section found in operator_snapshot"
    return result


# --- 5. OHLC snapshot для top symbols (best-effort) ---------------------

def ohlc_snapshot(symbols: list[str], tail_bars: int = 100, tf: str = "60") -> dict[str, Any]:
    """Best-effort: ищет cached klines по символам, возвращает последние tail_bars."""
    out: dict[str, Any] = {"timeframe_minutes": tf, "per_symbol": {}}
    found = 0
    for sym in symbols:
        for kd in KLINES_DIRS:
            if not kd.exists():
                continue
            # часто файл имеет вид {SYMBOL}_{TF}_*.csv или .json
            candidates = (
                list(kd.glob(f"{sym}_{tf}_*.csv"))
                + list(kd.glob(f"{sym}_{tf}_*.json"))
                + list(kd.glob(f"{sym}_{tf}.csv"))
                + list(kd.glob(f"{sym}*{tf}*.csv"))
            )
            if not candidates:
                continue
            # самый свежий
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            picked = candidates[0]
            try:
                if picked.suffix == ".csv":
                    text = picked.read_text(encoding="utf-8", errors="ignore")
                    rows = text.strip().splitlines()
                    header = rows[0]
                    bars = rows[-tail_bars:]
                    out["per_symbol"][sym] = {
                        "source": str(picked.relative_to(REPO_ROOT)),
                        "header": header,
                        "bars_count": len(bars),
                        "bars_tail": bars[-min(20, tail_bars):],  # последние 20 для AI
                    }
                else:
                    payload = load_json(picked, fallback=[])
                    if isinstance(payload, list):
                        out["per_symbol"][sym] = {
                            "source": str(picked.relative_to(REPO_ROOT)),
                            "bars_count": len(payload),
                            "bars_tail": payload[-min(20, tail_bars):],
                        }
                found += 1
                break
            except Exception:
                continue
    out["n_symbols_found"] = found
    if found == 0:
        out["_warn"] = "no klines cache files found in .cache/klines or data_cache"
    return out


def infer_top_setup_symbols(limit: int = 5) -> list[str]:
    """Берёт top setup symbols из full_context, чтобы cron мог давать AI
    свечной хвост без ручного списка символов."""
    full_ctx = load_json(FULL_CONTEXT, fallback={}) or {}
    setup = full_ctx.get("setups_scanner") if isinstance(full_ctx, dict) else {}
    cards = setup.get("cards_top") if isinstance(setup, dict) else []
    symbols: list[str] = []
    for card in cards if isinstance(cards, list) else []:
        if not isinstance(card, dict):
            continue
        sym = str(card.get("symbol") or "").strip().upper()
        if sym and sym not in symbols:
            symbols.append(sym)
        if len(symbols) >= limit:
            break
    return symbols


# --- 6. Memory lines (rolling buffer) -----------------------------------

def memory_lines_tail(n: int = 50) -> list[dict[str, Any]]:
    """Читает последние N строк memory_lines.jsonl — append-only журнал
    «ключевых выводов» Claude/DeepSeek от прошлых сессий. Записывают
    туда внешние процессы (см. memory_append() ниже)."""
    return tail_jsonl(MEMORY_OUT, n)


def memory_append(entry: dict[str, Any]) -> None:
    """Утилита: дописать в memory_lines.jsonl. Используется из других
    скриптов или вручную:
        from scripts.build_ai_extras import memory_append
        memory_append({"ts_utc": "...", "author": "claude", "topic": "...",
                       "text": "..."})
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if "ts_utc" not in entry:
        entry["ts_utc"] = datetime.now(tz=timezone.utc).isoformat()
    with MEMORY_OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# --- Main ---------------------------------------------------------------

def build(args: argparse.Namespace) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "schema_version": "1.0",
        "complements": "scripts/build_ai_full_context.py → runtime/ai_context/full_context.json",
    }

    ctx["trade_history"] = trade_history_summary(args.tail_trades)
    ctx["bot_errors"] = log_errors_summary(args.scan_log_lines, args.top_errors)
    ctx["indicators"] = indicators_snapshot(args.top_symbols)
    ctx["bybit_positions"] = bybit_positions_snapshot()

    # OHLC: если список не задан, берём top symbols из scanner cards.
    if args.ohlc_symbols:
        symbols = [s.strip().upper() for s in args.ohlc_symbols.split(",") if s.strip()]
        ctx["ohlc"] = ohlc_snapshot(symbols, args.ohlc_tail, args.ohlc_tf)
    else:
        symbols = infer_top_setup_symbols(5)
        if symbols:
            ctx["ohlc"] = ohlc_snapshot(symbols, args.ohlc_tail, args.ohlc_tf)
            ctx["ohlc"]["symbols_inferred_from"] = "runtime/ai_context/full_context.json: setups_scanner.cards_top"
        else:
            ctx["ohlc"] = {"_skipped": "no --ohlc-symbols and no scanner cards in full_context"}

    ctx["memory_lines"] = memory_lines_tail(args.memory_tail)

    return ctx


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(EXTRAS_OUT))
    ap.add_argument("--tail-trades", type=int, default=200)
    ap.add_argument("--scan-log-lines", type=int, default=5000)
    ap.add_argument("--top-errors", type=int, default=20)
    ap.add_argument("--top-symbols", type=int, default=12)
    ap.add_argument("--ohlc-symbols", default="",
                    help="comma-separated, e.g. BTCUSDT,ETHUSDT")
    ap.add_argument("--ohlc-tail", type=int, default=100)
    ap.add_argument("--ohlc-tf", default="60")
    ap.add_argument("--memory-tail", type=int, default=50)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    out_path = Path(args.out).resolve()
    try:
        out_path.relative_to(OUT_DIR.resolve())
    except ValueError:
        print(f"ERROR: --out must be under {OUT_DIR}, got {out_path}",
              file=sys.stderr)
        return 2

    ctx = build(args)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(ctx, indent=2, ensure_ascii=False, default=str),
                        encoding="utf-8")

    if not args.quiet:
        size_kb = out_path.stat().st_size / 1024
        print(f"# build_ai_extras")
        print(f"output:        {out_path.relative_to(REPO_ROOT) if out_path.is_relative_to(REPO_ROOT) else out_path}")
        print(f"size:          {size_kb:.1f} KB")
        th = ctx.get("trade_history", {})
        print(f"trades tail:   {th.get('events_in_tail')} events, {th.get('closed_in_tail')} closes")
        per = th.get("per_sleeve") or {}
        if per:
            for s, b in sorted(per.items(), key=lambda kv: -(kv[1].get('n_closed') or 0))[:5]:
                print(f"  {s}: n={b['n_closed']} PF={b.get('profit_factor')} WR={b.get('winrate_pct')}% pnl={b.get('total_pnl'):.3f}")
        be = ctx.get("bot_errors", {})
        print(f"log errors:    {be.get('error_lines_total')} in {be.get('lines_scanned')} lines")
        ind = ctx.get("indicators", {})
        print(f"indicators:    {ind.get('n_symbols')} symbols")
        bp = ctx.get("bybit_positions", {})
        keys = [k for k in bp if not k.startswith("_") and k != "source"]
        print(f"bybit pos:     {keys or '(none)'}")
        mem = ctx.get("memory_lines") or []
        print(f"memory lines:  {len(mem)} entries")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
