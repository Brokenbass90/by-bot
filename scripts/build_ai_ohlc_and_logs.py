#!/usr/bin/env python3
"""Lite OHLC + raw log tail для DeepSeek prompt.

Пишет третий файл в runtime/ai_context/: `ohlc_and_logs.json`.
DeepSeek читает его как дополнение к `full_context.json` и `extras.json`.

Что внутри:
1. OHLC snapshot для **top-3 символов** из текущих setup scanner cards
   (выбор автоматический — берём 3 уникальных символа из top карт).
2. Last 50 raw log lines из `runtime/live.out` (хвост без агрегации —
   для случаев когда нужен сырой контекст что происходит в логе).
3. Per-symbol mini-stats: last close, 20-bar high/low, simple RSI(14),
   ATR(14) — посчитано локально из OHLC. ИИ не нужно знать формулы,
   видит готовые числа.

Запуск (cron, можно чаще чем full_context):
    cd /root/by-bot && python3 scripts/build_ai_ohlc_and_logs.py --quiet

Идемпотентно, read-only. Никаких сетевых вызовов — только локальные
кэши klines и live.out.

Стоимость: ~5-10 KB в JSON = ~1500 токенов в prompt. На порядок дешевле,
чем «нарисуй real-time график».
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "runtime" / "ai_context"
DEFAULT_OUT = OUT_DIR / "ohlc_and_logs.json"

LIVE_LOG_CANDIDATES = [
    REPO_ROOT / "runtime" / "live.out",
    REPO_ROOT / "runtime" / "live_mirror" / "live.out",
    REPO_ROOT / "logs" / "live.out",
]

SETUPS_PATH_CANDIDATES = [
    "runtime/setup_scanner/state.json",
    "runtime/setup_scanner_state.json",
    "runtime/live_mirror/setup_scanner_state.json",
    "runtime/setups/latest.json",
    "runtime/operator/setups_latest.json",
]

# В тот же контекст, что и build_ai_full_context — используем тот же
# build path. Без этого мы не знаем, какие символы в top.
FULL_CONTEXT = OUT_DIR / "full_context.json"

KLINES_DIRS = [
    REPO_ROOT / ".cache" / "klines",
    REPO_ROOT / "data_cache",
]

SIGNAL_LOG_RE = re.compile(
    r"(ERROR|WARN|WARNING|entry|closed|exit|order|SL|TP|pulse|regime|allocator|router|watchdog|heartbeat|no_signal|skip)",
    re.IGNORECASE,
)


def load_json(path: Path, fallback: Any = None) -> Any:
    if not path or not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        return {"_error": f"{type(exc).__name__}: {exc}"}


def first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


# --- 1. Pick top-3 symbols from current setup cards ---------------------

def pick_top_symbols(max_n: int = 3) -> tuple[list[str], dict[str, str], str]:
    """Возвращает (symbols, sym_to_tf, source_used)."""
    sym_tf: dict[str, str] = {}
    symbols_ordered: list[str] = []

    # Сначала пробуем full_context.json (там cards_top уже отрендерены)
    fc = load_json(FULL_CONTEXT, fallback={}) or {}
    scanner_block = fc.get("setups_scanner") if isinstance(fc, dict) else None
    cards = None
    source_used = ""
    if isinstance(scanner_block, dict):
        cards = scanner_block.get("cards_top") or scanner_block.get("cards")
        source_used = "full_context.setups_scanner"

    # Если full_context пуст — прямой источник
    if not cards:
        for cand in SETUPS_PATH_CANDIDATES:
            p = REPO_ROOT / cand
            if p.exists():
                data = load_json(p, fallback=None)
                if isinstance(data, dict):
                    cards = data.get("cards") or data.get("setups")
                elif isinstance(data, list):
                    cards = data
                if cards:
                    source_used = cand
                    break

    if not cards:
        return [], {}, "no setup cards found"

    for card in cards:
        if not isinstance(card, dict):
            continue
        sym = (card.get("symbol") or card.get("sym") or "").upper().strip()
        if not sym:
            continue
        tf = str(card.get("tf") or card.get("timeframe") or card.get("interval") or "60")
        if sym not in sym_tf:
            sym_tf[sym] = tf
            symbols_ordered.append(sym)
        if len(symbols_ordered) >= max_n:
            break

    return symbols_ordered, sym_tf, source_used


# --- 2. Load klines for one symbol --------------------------------------

def find_kline_file(symbol: str, tf: str) -> Path | None:
    for kd in KLINES_DIRS:
        if not kd.exists():
            continue
        candidates = (
            list(kd.glob(f"{symbol}_{tf}_*.csv"))
            + list(kd.glob(f"{symbol}_{tf}.csv"))
            + list(kd.glob(f"{symbol}_{tf}_*.json"))
            + list(kd.glob(f"{symbol}_{tf}.json"))
            + list(kd.glob(f"{symbol}*_{tf}_*.csv"))
        )
        if candidates:
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return candidates[0]
    return None


def parse_csv_klines(path: Path, tail: int = 100) -> list[dict[str, float]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    rows = text.strip().splitlines()
    if len(rows) < 2:
        return []
    header = [h.strip().lower() for h in rows[0].split(",")]
    out: list[dict[str, float]] = []
    for line in rows[-tail:]:
        parts = line.split(",")
        if len(parts) < len(header):
            continue
        rec: dict[str, Any] = {}
        for i, h in enumerate(header):
            try:
                rec[h] = float(parts[i])
            except Exception:
                rec[h] = parts[i].strip()
        out.append(rec)
    return out


def rows_to_bars(rows: list[list[Any]], tail: int = 100) -> list[dict[str, float]]:
    out: list[dict[str, float]] = []
    for row in rows[-tail:]:
        if len(row) < 6:
            continue
        try:
            out.append({
                "ts": float(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            })
        except Exception:
            continue
    return out


def parse_json_klines(path: Path, tail: int = 100) -> list[dict[str, float]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, float]] = []
    for item in raw[-tail:]:
        if not isinstance(item, dict):
            continue
        try:
            out.append({
                "ts": float(item.get("ts") or item.get("timestamp") or item.get("open_time") or 0),
                "open": float(item.get("o") or item.get("open")),
                "high": float(item.get("h") or item.get("high")),
                "low": float(item.get("l") or item.get("low")),
                "close": float(item.get("c") or item.get("close")),
                "volume": float(item.get("v") or item.get("volume") or 0.0),
            })
        except Exception:
            continue
    return out


def interval_seconds(tf: str) -> int:
    try:
        return max(60, int(float(tf)) * 60)
    except Exception:
        return 3600


def latest_bar_age_sec(bars: list[dict[str, Any]]) -> int | None:
    if not bars:
        return None
    ts = bars[-1].get("ts") or bars[-1].get("timestamp") or bars[-1].get("open_time")
    try:
        ts_f = float(ts)
        if ts_f > 10_000_000_000:
            ts_f = ts_f / 1000.0
        return max(0, int(time.time() - ts_f))
    except Exception:
        return None


def cache_is_usable(bars: list[dict[str, Any]], tf: str) -> bool:
    age = latest_bar_age_sec(bars)
    if age is None:
        return False
    # For 60/240m bars, the open timestamp of the current candle naturally
    # ages during the candle. Two intervals plus a small grace avoids false
    # stale flags while still rejecting old research caches.
    return age <= interval_seconds(tf) * 2 + 300


def load_cached_bars(symbol: str, tf: str, tail: int = 100) -> tuple[list[dict[str, float]], str | None]:
    # Prefer the shared geometry cache loader because it knows how to merge
    # JSON shards and aggregate 5m/60m caches into higher timeframes.
    try:
        from bot.geometry_cache import load_rows

        rows = load_rows(symbol, tf)
        if rows:
            return rows_to_bars(rows, tail), "bot.geometry_cache"
    except Exception:
        pass

    kp = find_kline_file(symbol, tf)
    if not kp:
        return [], None
    if kp.suffix.lower() == ".json":
        return parse_json_klines(kp, tail), str(kp.relative_to(REPO_ROOT)) if kp.is_relative_to(REPO_ROOT) else str(kp)
    return parse_csv_klines(kp, tail), str(kp.relative_to(REPO_ROOT)) if kp.is_relative_to(REPO_ROOT) else str(kp)


def fetch_bybit_klines(symbol: str, tf: str, tail: int = 100) -> list[dict[str, float]]:
    interval = str(int(float(tf))) if str(tf).replace(".", "", 1).isdigit() else str(tf)
    query = urllib.parse.urlencode({
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": max(20, min(200, int(tail))),
    })
    url = f"https://api.bybit.com/v5/market/kline?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "bybot-ai-context/1.0"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
    if int(payload.get("retCode", -1)) != 0:
        raise RuntimeError(str(payload)[:240])
    raw_rows = ((payload.get("result") or {}).get("list") or [])
    bars: list[dict[str, float]] = []
    for row in raw_rows:
        if len(row) < 6:
            continue
        bars.append({
            "ts": float(row[0]),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        })
    bars.sort(key=lambda b: float(b.get("ts") or 0))
    return bars[-tail:]


def compute_mini_stats(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Локально считает простые stats для AI: last close, hi/lo, RSI(14), ATR(14)."""
    if not bars or len(bars) < 15:
        return {"_warn": f"insufficient bars: {len(bars)}"}

    # нормализуем ключи (open/high/low/close/volume)
    def get(b: dict, *keys, default=None):
        for k in keys:
            if k in b:
                return b[k]
        return default

    closes = [float(get(b, "close", "c", "Close") or 0) for b in bars]
    highs = [float(get(b, "high", "h", "High") or 0) for b in bars]
    lows = [float(get(b, "low", "l", "Low") or 0) for b in bars]

    last_close = closes[-1] if closes else None
    hi_20 = max(highs[-20:]) if len(highs) >= 20 else None
    lo_20 = min(lows[-20:]) if len(lows) >= 20 else None

    # RSI(14)
    rsi = None
    if len(closes) >= 15:
        diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in diffs[-14:]]
        losses = [-d if d < 0 else 0 for d in diffs[-14:]]
        avg_gain = sum(gains) / 14
        avg_loss = sum(losses) / 14
        if avg_loss > 0:
            rs = avg_gain / avg_loss
            rsi = round(100 - (100 / (1 + rs)), 2)
        elif avg_gain > 0:
            rsi = 100.0
        else:
            rsi = 50.0

    # ATR(14)
    atr_pct = None
    if len(bars) >= 15:
        trs = []
        prev_close = closes[-15]
        for i in range(-14, 0):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - prev_close),
                abs(lows[i] - prev_close),
            )
            trs.append(tr)
            prev_close = closes[i]
        if trs:
            atr = sum(trs) / 14
            if last_close and last_close > 0:
                atr_pct = round(atr / last_close * 100, 3)

    # distance to 20-bar hi/lo in %
    dist_to_hi = None
    dist_to_lo = None
    if last_close and hi_20 and lo_20:
        dist_to_hi = round((hi_20 - last_close) / last_close * 100, 3)
        dist_to_lo = round((last_close - lo_20) / last_close * 100, 3)

    return {
        "last_close": last_close,
        "hi_20": hi_20,
        "lo_20": lo_20,
        "dist_to_hi_20_pct": dist_to_hi,
        "dist_to_lo_20_pct": dist_to_lo,
        "rsi_14": rsi,
        "atr_14_pct": atr_pct,
        "bars_count": len(bars),
    }


def ohlc_block(symbols: list[str], sym_tf: dict[str, str], tail: int = 100) -> dict[str, Any]:
    per_symbol: dict[str, Any] = {}
    for sym in symbols:
        tf = sym_tf.get(sym, "60")
        bars_raw, source = load_cached_bars(sym, tf, tail)
        source_kind = "cache"
        fetch_error = ""
        if not cache_is_usable(bars_raw, tf):
            try:
                bars_raw = fetch_bybit_klines(sym, tf, tail)
                source = "bybit_public_market_kline"
                source_kind = "live_fetch"
            except Exception as exc:
                fetch_error = f"{type(exc).__name__}: {exc}"
        stats = compute_mini_stats(bars_raw)
        # Bars тэйл — компактный (только OHLC + ts, не всё подряд)
        compact_bars = []
        for b in bars_raw[-min(30, tail):]:
            compact_bars.append({
                "ts": b.get("ts") or b.get("timestamp") or b.get("open_time") or b.get("time"),
                "o": b.get("open") or b.get("o"),
                "h": b.get("high") or b.get("h"),
                "l": b.get("low") or b.get("l"),
                "c": b.get("close") or b.get("c"),
                "v": b.get("volume") or b.get("v"),
            })

        age_sec = latest_bar_age_sec(bars_raw)
        usable = bool(cache_is_usable(bars_raw, tf) and "insufficient" not in str(stats.get("_warn", "")))

        per_symbol[sym] = {
            "timeframe": tf,
            "source": source or "none",
            "source_kind": source_kind,
            "latest_bar_age_sec": age_sec,
            "usable_for_decisions": usable,
            "fetch_error": fetch_error,
            "stats": stats,
            "bars_tail_30": compact_bars,
        }
    return per_symbol


# --- 3. Raw log tail (без агрегации) ------------------------------------

def raw_log_tail(n: int = 50) -> dict[str, Any]:
    log_path = first_existing(LIVE_LOG_CANDIDATES)
    if not log_path:
        return {"_warn": "no live.out found",
                "candidates": [str(p.relative_to(REPO_ROOT)) for p in LIVE_LOG_CANDIDATES
                               if p.is_relative_to(REPO_ROOT)]}
    try:
        with log_path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            # читаем максимум последние 200 KB чтобы найти 50 строк
            chunk = min(size, 200 * 1024)
            f.seek(-chunk, 2)
            buf = f.read().decode("utf-8", errors="ignore")
        all_lines = buf.splitlines()
        filtered = [
            ln for ln in all_lines
            if not ln.startswith("[dbg]") and SIGNAL_LOG_RE.search(ln)
        ]
        tail_lines = filtered[-n:]
        if not tail_lines:
            tail_lines = [ln for ln in all_lines if not ln.startswith("[dbg]")][-min(n, 12):]
    except Exception as exc:
        return {"_error": f"{type(exc).__name__}: {exc}"}

    try:
        mtime = log_path.stat().st_mtime
        age_sec = int(datetime.now(tz=timezone.utc).timestamp() - mtime)
    except Exception:
        age_sec = None

    return {
        "source": str(log_path.relative_to(REPO_ROOT)) if log_path.is_relative_to(REPO_ROOT) else str(log_path),
        "log_file_age_sec": age_sec,
        "n_lines": len(tail_lines),
        "filter": "non-debug signal/warn/error/order/pulse lines",
        # Обрезаем длинные строки до 300 символов чтобы не палить токены
        "lines": [(ln if len(ln) <= 300 else ln[:297] + "...") for ln in tail_lines],
    }


# --- Main ---------------------------------------------------------------

def build(args: argparse.Namespace) -> dict[str, Any]:
    symbols, sym_tf, src = pick_top_symbols(args.top_symbols)
    ctx = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "schema_version": "1.0",
        "complements": "scripts/build_ai_full_context.py + scripts/build_ai_extras.py",
        "top_symbols": symbols,
        "top_symbols_source": src,
        "ohlc": ohlc_block(symbols, sym_tf, args.ohlc_tail) if symbols else {"_warn": "no top symbols"},
        "log_tail": raw_log_tail(args.log_tail),
    }
    return ctx


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--top-symbols", type=int, default=3)
    ap.add_argument("--ohlc-tail", type=int, default=100)
    ap.add_argument("--log-tail", type=int, default=50)
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
        print(f"# build_ai_ohlc_and_logs")
        print(f"output:        {out_path.relative_to(REPO_ROOT) if out_path.is_relative_to(REPO_ROOT) else out_path}")
        print(f"size:          {size_kb:.1f} KB")
        print(f"top symbols:   {ctx.get('top_symbols')} (source: {ctx.get('top_symbols_source')})")
        ohlc = ctx.get("ohlc") or {}
        for sym, data in ohlc.items():
            if isinstance(data, dict) and "stats" in data:
                s = data["stats"]
                print(f"  {sym} tf={data.get('timeframe')}: "
                      f"close={s.get('last_close')} RSI={s.get('rsi_14')} "
                      f"ATR%={s.get('atr_14_pct')} "
                      f"hi/lo20=[{s.get('lo_20')}..{s.get('hi_20')}] "
                      f"age={data.get('latest_bar_age_sec')}s "
                      f"source={data.get('source_kind')} usable={data.get('usable_for_decisions')}")
            else:
                print(f"  {sym}: {data}")
        lt = ctx.get("log_tail") or {}
        print(f"log tail:      {lt.get('n_lines')} lines "
              f"(file age {lt.get('log_file_age_sec')}s)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
