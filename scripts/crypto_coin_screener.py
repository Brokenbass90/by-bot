#!/usr/bin/env python3
"""crypto_coin_screener.py — Fast Bybit perpetuals momentum screener.

Scans the top-N USDT perpetuals by 24h turnover, ranks them by momentum,
ATR, and trend direction. Writes results to runtime/coin_screener_latest.json
(readable by the web dashboard and /brief TG command).

Optionally sends a Telegram digest.

Usage:
    python3 scripts/crypto_coin_screener.py              # scan + save JSON
    python3 scripts/crypto_coin_screener.py --tg         # scan + TG digest
    python3 scripts/crypto_coin_screener.py --dry-run    # print only, no write
    python3 scripts/crypto_coin_screener.py --top 60     # scan top-60 by volume

Cron (every 6h):
    0 */6 * * * cd /root/by-bot && .venv/bin/python3 scripts/crypto_coin_screener.py --tg >> logs/screener.log 2>&1
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BYBIT_BASE = os.getenv("BYBIT_BASE", "https://api.bybit.com").rstrip("/")
OUTPUT_PATH = ROOT / "runtime" / "coin_screener_latest.json"
HTTP_TIMEOUT = 10
KLINE_INTERVAL = "60"   # 1h candles
KLINE_LIMIT    = 55      # 55 bars → 54 returns = ~2.25 days

# ── Telegram helpers ────────────────────────────────────────────────────────

def _tg_send(token: str, chat: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for attempt in range(3):
        try:
            r = requests.post(
                url,
                json={"chat_id": chat, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(2 ** attempt)


# ── Bybit data helpers ──────────────────────────────────────────────────────

def _fetch_tickers() -> list[dict[str, Any]]:
    """Return list of linear perpetual tickers sorted by turnover24h desc."""
    r = requests.get(
        f"{BYBIT_BASE}/v5/market/tickers",
        params={"category": "linear"},
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    result = r.json().get("result", {})
    tickers = result.get("list", [])
    usdt_perps = [t for t in tickers if str(t.get("symbol", "")).endswith("USDT")]
    usdt_perps.sort(key=lambda t: float(t.get("turnover24h") or 0), reverse=True)
    return usdt_perps


def _fetch_klines(symbol: str, interval: str, limit: int) -> list[list]:
    """Return klines oldest→newest: [timestamp, open, high, low, close, volume]."""
    r = requests.get(
        f"{BYBIT_BASE}/v5/market/kline",
        params={"category": "linear", "symbol": symbol, "interval": interval, "limit": limit},
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    if str(data.get("retCode")) != "0":
        raise RuntimeError(f"Bybit error: {data.get('retMsg')}")
    rows = (data.get("result") or {}).get("list") or []
    return list(reversed(rows))   # oldest first


# ── Technical indicators ────────────────────────────────────────────────────

def _safe_float(v: Any, default: float = float("nan")) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _ema(closes: list[float], period: int) -> float:
    if not closes:
        return 0.0
    k = 2.0 / (period + 1)
    ema = sum(closes[:period]) / period if len(closes) >= period else closes[0]
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(0.0, d))
        losses.append(max(0.0, -d))
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + ag / al)


def _atr_pct(bars: list, period: int = 14) -> float:
    trs = []
    for i in range(1, len(bars)):
        h  = _safe_float(bars[i][2])
        lo = _safe_float(bars[i][3])
        pc = _safe_float(bars[i - 1][4])
        if math.isfinite(h) and math.isfinite(lo) and math.isfinite(pc):
            trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    if not trs:
        return 0.0
    atr = sum(trs[-period:]) / min(period, len(trs))
    last_c = _safe_float(bars[-1][4])
    return (atr / last_c * 100.0) if last_c > 0 else 0.0


def _score_symbol(symbol: str, ticker: dict, verbose: bool = False) -> dict[str, Any] | None:
    """Fetch klines and compute all indicators. Returns None on failure."""
    try:
        bars = _fetch_klines(symbol, KLINE_INTERVAL, KLINE_LIMIT)
        if len(bars) < 26:
            return None

        closes = [_safe_float(b[4]) for b in bars]
        volumes = [_safe_float(b[5]) for b in bars]

        # Filter bad data
        if not all(math.isfinite(c) and c > 0 for c in closes[-5:]):
            return None

        cur_close = closes[-1]

        # Momentum: 24h and 4h
        mom_24h = (cur_close / closes[-25] - 1.0) * 100.0 if len(closes) >= 25 and closes[-25] > 0 else 0.0
        mom_4h  = (cur_close / closes[-5]  - 1.0) * 100.0 if len(closes) >= 5  and closes[-5]  > 0 else 0.0

        # RSI
        rsi_val = _rsi(closes[-28:] if len(closes) >= 28 else closes)

        # ATR%
        atr_pct = _atr_pct(bars[-20:] if len(bars) >= 20 else bars)

        # EMA trend
        ema20 = _ema(closes, 20)
        ema50 = _ema(closes, 50) if len(closes) >= 50 else ema20
        if ema20 > ema50 * 1.002:
            trend = "up"
        elif ema20 < ema50 * 0.998:
            trend = "dn"
        else:
            trend = "flat"

        # Volume trend (recent vs average)
        avg_vol = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else sum(volumes) / len(volumes)
        recent_vol = sum(volumes[-4:]) / 4 if len(volumes) >= 4 else volumes[-1]
        vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

        # Turnover + price from ticker
        turnover_24h = _safe_float(ticker.get("turnover24h"), 0.0)
        last_price   = _safe_float(ticker.get("lastPrice"), cur_close)
        funding_rate = _safe_float(ticker.get("fundingRate"), float("nan"))

        # Category score (higher = better for longs in bull, or better shorts in bear)
        trend_score = mom_24h + 0.4 * mom_4h - 0.3 * atr_pct

        return {
            "symbol":       symbol,
            "base":         symbol.replace("USDT", ""),
            "price":        round(last_price, 6),
            "mom_24h":      round(mom_24h, 2),
            "mom_4h":       round(mom_4h, 2),
            "rsi":          round(rsi_val, 1),
            "atr_pct":      round(atr_pct, 3),
            "ema_trend":    trend,
            "vol_ratio":    round(vol_ratio, 2),
            "turnover_24h": round(turnover_24h / 1_000_000, 1),   # in $M
            "funding_rate": round(funding_rate * 100, 4) if math.isfinite(funding_rate) else None,
            "trend_score":  round(trend_score, 3),
        }
    except Exception as exc:
        if verbose:
            print(f"  ⚠️  {symbol}: {exc}", file=sys.stderr)
        return None


def _categorise(rows: list[dict]) -> dict[str, list[dict]]:
    trending_up = sorted(
        [r for r in rows if r["ema_trend"] == "up" and r["mom_24h"] > 0.5],
        key=lambda r: r["trend_score"], reverse=True,
    )
    trending_dn = sorted(
        [r for r in rows if r["ema_trend"] == "dn" and r["mom_24h"] < -0.5],
        key=lambda r: r["trend_score"],
    )
    ranging = sorted(
        [r for r in rows if abs(r["mom_24h"]) <= 2.0 and r["atr_pct"] < 0.8],
        key=lambda r: r["atr_pct"],
    )
    high_vol = sorted(
        [r for r in rows if r["vol_ratio"] > 1.8],
        key=lambda r: r["vol_ratio"], reverse=True,
    )
    return {
        "trending_up": trending_up,
        "trending_dn": trending_dn,
        "ranging":     ranging,
        "high_volume": high_vol,
        "all_ranked":  sorted(rows, key=lambda r: r["trend_score"], reverse=True),
    }


def _build_tg_message(cats: dict, scanned: int, elapsed: float) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"🪙 *Crypto Screener* — {ts}", f"_Scanned {scanned} symbols in {elapsed:.0f}s_\n"]

    def _row(r: dict) -> str:
        base = r["base"]
        fr_str = ""
        if r["funding_rate"] is not None:
            fr_icon = "🟢" if abs(r["funding_rate"]) < 0.01 else ("🟡" if abs(r["funding_rate"]) < 0.05 else "🔴")
            fr_str = f" FR{fr_icon}{r['funding_rate']:+.3f}%"
        return (
            f"  `{base:<7}` {r['mom_24h']:+.1f}% | ATR {r['atr_pct']:.2f}% | RSI {r['rsi']:.0f}{fr_str}"
        )

    up = cats["trending_up"]
    dn = cats["trending_dn"]
    rng = cats["ranging"]
    hvol = cats["high_volume"]

    if up:
        lines.append("📈 *Трендовые вверх* (лонги):")
        lines.extend(_row(r) for r in up[:5])
    else:
        lines.append("📈 _Нет явных up-трендов_")

    lines.append("")
    if dn:
        lines.append("📉 *Трендовые вниз* (шорты):")
        lines.extend(_row(r) for r in dn[:5])
    else:
        lines.append("📉 _Нет явных down-трендов_")

    lines.append("")
    if rng:
        lines.append("🔁 *Боковик* (ARF1/flat):")
        lines.extend(_row(r) for r in rng[:4])

    if hvol:
        lines.append("")
        lines.append("⚡ *Аномальный объём* (×базовый):")
        for r in hvol[:3]:
            lines.append(f"  `{r['base']:<7}` vol×{r['vol_ratio']:.1f} | {r['mom_24h']:+.1f}%")

    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Bybit perpetuals screener")
    ap.add_argument("--top",     type=int, default=40, help="Number of top symbols by volume to scan")
    ap.add_argument("--tg",      action="store_true",  help="Send Telegram digest")
    ap.add_argument("--dry-run", action="store_true",  help="Print results, skip file write")
    ap.add_argument("--verbose", action="store_true",  help="Show per-symbol errors")
    args = ap.parse_args()

    t0 = time.time()
    print(f"[screener] Fetching top-{args.top} tickers …")
    tickers = _fetch_tickers()[:args.top]
    symbols = [t["symbol"] for t in tickers]
    ticker_map = {t["symbol"]: t for t in tickers}

    print(f"[screener] Scanning {len(symbols)} symbols …")
    rows: list[dict] = []
    for i, sym in enumerate(symbols, 1):
        result = _score_symbol(sym, ticker_map[sym], verbose=args.verbose)
        if result:
            rows.append(result)
        if i % 10 == 0:
            print(f"  … {i}/{len(symbols)} done, {len(rows)} valid")
        time.sleep(0.05)   # polite rate-limit

    elapsed = time.time() - t0
    cats = _categorise(rows)

    # Build output payload
    now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "updated_utc":   now_utc,
        "scanned":       len(rows),
        "elapsed_sec":   round(elapsed, 1),
        "categories":    {k: v[:10] for k, v in cats.items()},
        "all_ranked":    cats["all_ranked"],
    }

    # Print summary
    print(f"\n[screener] Done in {elapsed:.1f}s — {len(rows)} symbols scored")
    print(f"  📈 Up: {len(cats['trending_up'])}  📉 Down: {len(cats['trending_dn'])}  "
          f"🔁 Ranging: {len(cats['ranging'])}  ⚡ HighVol: {len(cats['high_volume'])}")

    if cats["trending_up"]:
        print("  Top longs:  " + ", ".join(r["base"] for r in cats["trending_up"][:5]))
    if cats["trending_dn"]:
        print("  Top shorts: " + ", ".join(r["base"] for r in cats["trending_dn"][:5]))
    if cats["ranging"]:
        print("  Top range:  " + ", ".join(r["base"] for r in cats["ranging"][:4]))

    # Write JSON
    if not args.dry_run:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUTPUT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(OUTPUT_PATH)
        print(f"[screener] Saved → {OUTPUT_PATH}")

    # Telegram
    if args.tg:
        tg_token = os.getenv("TG_TOKEN", "")
        tg_chat  = os.getenv("TG_CHAT_ID", "")
        if tg_token and tg_chat:
            msg = _build_tg_message(cats, len(rows), elapsed)
            _tg_send(tg_token, tg_chat, msg)
            print("[screener] Telegram digest sent")
        else:
            print("[screener] ⚠️  TG_TOKEN / TG_CHAT_ID not set — skip Telegram")


if __name__ == "__main__":
    main()
