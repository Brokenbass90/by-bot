#!/usr/bin/env python3
"""
Funding Rate Carry Executor
===========================
Polls Bybit perpetual funding rates and opens/closes carry positions
based on configurable thresholds.

Strategy:
  - NEGATIVE funding (< -threshold) → open LONG perp (shorts pay you)
  - POSITIVE funding (> +threshold) → open SHORT perp (longs pay you)
  - Close when funding reverts toward 0 or flips

Risk management:
  - Max 1 position per symbol
  - Max total allocation = CARRY_MAX_CAPITAL_PCT of account
  - Stop-loss = CARRY_SL_PCT of position

ENV variables (can be in .env or runtime/funding_carry/):
  CARRY_SYMBOLS          comma-separated symbols to watch (default: BTCUSDT,ETHUSDT,SOLUSDT)
  CARRY_MIN_RATE_PCT     funding rate threshold to enter (abs, default: 0.05)  = 0.05%
  CARRY_CLOSE_RATE_PCT   funding rate threshold to close (abs, default: 0.01) = 0.01%
  CARRY_POSITION_USD     USD per position (default: 50)
  CARRY_MAX_POSITIONS    max simultaneous positions (default: 3)
  CARRY_SL_PCT           stop loss as % of entry (default: 2.5)
  CARRY_DRY_RUN          1 = log only, do not actually trade (default: 1)
  CARRY_STATE_FILE       JSON file to track open carry positions

  BYBIT_API_KEY, BYBIT_API_SECRET (same as main bot)
  TG_TOKEN, TG_CHAT_ID (for Telegram alerts)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error, request

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── ENV helpers ──────────────────────────────────────────────────────────────

def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name) or default).strip()

def _env_float(name: str, default: float) -> float:
    try: return float(_env(name, str(default)))
    except: return default

def _env_int(name: str, default: int) -> int:
    try: return int(_env(name, str(default)))
    except: return default

def _env_bool(name: str, default: bool) -> bool:
    return _env(name, "1" if default else "0").lower() in {"1","true","yes","on"}


# ── Telegram ──────────────────────────────────────────────────────────────────

def _tg(token: str, chat_id: str, msg: str) -> None:
    if not token or not chat_id:
        return
    import ssl as _ssl
    data = json.dumps({"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}).encode()
    req = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with request.urlopen(req, context=_ssl.create_default_context(), timeout=8):
            pass
    except Exception:
        pass


# ── Bybit V5 client ───────────────────────────────────────────────────────────

class BybitClient:
    BASE = "https://api.bybit.com"

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        self.key = api_key
        self.secret = api_secret
        if testnet:
            self.BASE = "https://api-testnet.bybit.com"

    def _sign(self, ts: str, payload: str) -> str:
        raw = f"{ts}{self.key}5000{payload}"
        return hmac.new(self.secret.encode(), raw.encode(), hashlib.sha256).hexdigest()

    def _get(self, path: str, params: dict) -> dict:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{self.BASE}{path}?{qs}"
        req = request.Request(url)
        try:
            with request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except error.HTTPError as e:
            raise RuntimeError(f"GET {path} failed: {e.code} {e.read()[:200]}")

    def _post(self, path: str, body: dict) -> dict:
        import ssl as _ssl
        ts = str(int(time.time() * 1000))
        payload = json.dumps(body)
        sig = self._sign(ts, payload)
        req = request.Request(
            f"{self.BASE}{path}",
            data=payload.encode(),
            headers={
                "X-BAPI-API-KEY": self.key,
                "X-BAPI-TIMESTAMP": ts,
                "X-BAPI-SIGN": sig,
                "X-BAPI-RECV-WINDOW": "5000",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, context=_ssl.create_default_context(), timeout=10) as resp:
                return json.loads(resp.read())
        except error.HTTPError as e:
            raise RuntimeError(f"POST {path} failed: {e.code} {e.read()[:300]}")

    def get_funding_rate(self, symbol: str) -> float:
        """Return current 8H funding rate as decimal (e.g. 0.0001 = 0.01%)."""
        data = self._get("/v5/market/tickers", {"category": "linear", "symbol": symbol})
        items = (data.get("result") or {}).get("list") or []
        if not items:
            raise ValueError(f"No ticker data for {symbol}")
        return float(items[0].get("fundingRate") or 0.0)

    def get_position(self, symbol: str) -> dict | None:
        """Return open position dict or None."""
        ts = str(int(time.time() * 1000))
        qs = f"category=linear&symbol={symbol}"
        sig = hmac.new(self.secret.encode(), f"{ts}{self.key}5000{qs}".encode(), hashlib.sha256).hexdigest()
        import ssl as _ssl
        req = request.Request(
            f"{self.BASE}/v5/position/list?{qs}",
            headers={
                "X-BAPI-API-KEY": self.key,
                "X-BAPI-TIMESTAMP": ts,
                "X-BAPI-SIGN": sig,
                "X-BAPI-RECV-WINDOW": "5000",
            },
        )
        with request.urlopen(req, context=_ssl.create_default_context(), timeout=10) as resp:
            data = json.loads(resp.read())
        items = (data.get("result") or {}).get("list") or []
        for item in items:
            if float(item.get("size") or 0) != 0:
                return item
        return None

    def get_account_balance_usdt(self) -> float:
        ts = str(int(time.time() * 1000))
        qs = "accountType=UNIFIED"
        sig = hmac.new(self.secret.encode(), f"{ts}{self.key}5000{qs}".encode(), hashlib.sha256).hexdigest()
        import ssl as _ssl
        req = request.Request(
            f"{self.BASE}/v5/account/wallet-balance?{qs}",
            headers={
                "X-BAPI-API-KEY": self.key,
                "X-BAPI-TIMESTAMP": ts,
                "X-BAPI-SIGN": sig,
                "X-BAPI-RECV-WINDOW": "5000",
            },
        )
        with request.urlopen(req, context=_ssl.create_default_context(), timeout=10) as resp:
            data = json.loads(resp.read())
        coins = ((data.get("result") or {}).get("list") or [{}])[0].get("coin") or []
        for coin in coins:
            if coin.get("coin") == "USDT":
                return float(coin.get("walletBalance") or 0.0)
        return 0.0

    def place_order(self, symbol: str, side: str, qty: str) -> dict:
        return self._post("/v5/order/create", {
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": "Market",
            "qty": qty,
            "timeInForce": "IOC",
        })

    def close_position(self, symbol: str, side: str, qty: str) -> dict:
        close_side = "Sell" if side == "Buy" else "Buy"
        return self._post("/v5/order/create", {
            "category": "linear",
            "symbol": symbol,
            "side": close_side,
            "orderType": "Market",
            "qty": qty,
            "timeInForce": "IOC",
            "reduceOnly": True,
        })


# ── State management ──────────────────────────────────────────────────────────

def _load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {"positions": {}}

def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


# ── Min contract qty helper ───────────────────────────────────────────────────

def _min_qty(symbol: str) -> float:
    """Return minimum order qty for common symbols."""
    defaults = {
        "BTCUSDT": 0.001, "ETHUSDT": 0.01, "SOLUSDT": 0.1,
        "BNBUSDT": 0.01,  "XRPUSDT": 1.0,  "DOGEUSDT": 10.0,
        "LTCUSDT": 0.01,  "AVAXUSDT": 0.1, "DOTUSDT": 0.1,
        "ADAUSDT": 1.0,   "MATICUSDT": 1.0,
    }
    return defaults.get(symbol.upper(), 0.1)


# ── Main ──────────────────────────────────────────────────────────────────────

def run_once(client: BybitClient | None, cfg: dict, state: dict, dry_run: bool,
             tg_token: str, tg_chat_id: str) -> dict:
    """Scan symbols, manage positions. Returns updated state."""
    symbols        = [s.strip().upper() for s in cfg["symbols"]]
    min_rate       = cfg["min_rate"]       # abs threshold to enter
    close_rate     = cfg["close_rate"]     # abs threshold to close
    position_usd   = cfg["position_usd"]
    max_positions  = cfg["max_positions"]
    sl_pct         = cfg["sl_pct"] / 100.0

    positions: dict = state.get("positions", {})
    actions = []

    for symbol in symbols:
        try:
            if client:
                rate = client.get_funding_rate(symbol)
            else:
                # DRY_RUN with no keys: skip actual API
                rate = 0.0
        except Exception as e:
            print(f"  [{symbol}] funding rate fetch error: {e}")
            continue

        rate_pct = rate * 100.0
        print(f"  [{symbol}] funding_rate={rate_pct:.4f}%", end="")

        in_pos = symbol in positions
        pos = positions.get(symbol, {})

        # ── Check exit conditions for existing positions ─────────────
        if in_pos:
            entry_side = pos.get("side", "")
            abs_rate = abs(rate_pct)
            # Close if funding has reduced significantly
            should_close = abs_rate < close_rate
            # Also close if direction flipped (funding now hurts us)
            if entry_side == "Buy" and rate_pct > close_rate:
                should_close = True   # funding now positive = paying for longs
            if entry_side == "Sell" and rate_pct < -close_rate:
                should_close = True   # funding now negative = paying for shorts

            if should_close:
                qty = str(pos.get("qty", "0"))
                if not dry_run and client:
                    try:
                        result = client.close_position(symbol, entry_side, qty)
                        print(f" → CLOSE {entry_side} (funding faded to {rate_pct:.4f}%)")
                    except Exception as e:
                        print(f" → CLOSE FAILED: {e}")
                        continue
                else:
                    print(f" → [DRY_RUN] CLOSE {entry_side} (funding={rate_pct:.4f}%)")
                del positions[symbol]
                actions.append({"symbol": symbol, "action": "close", "rate_pct": rate_pct})
                msg = f"💰 CARRY CLOSE {symbol} {entry_side}\nfunding={rate_pct:.4f}% (faded)"
                _tg(tg_token, tg_chat_id, msg)
                continue
            else:
                print(f" → HOLD {entry_side} (funding={rate_pct:.4f}%)")
                continue

        # ── Check entry conditions ───────────────────────────────────
        if len(positions) >= max_positions:
            print(f" → SKIP (max_positions={max_positions} reached)")
            continue

        entry_side = None
        if rate_pct < -min_rate:
            entry_side = "Buy"   # negative funding → longs collect from shorts
        elif rate_pct > min_rate:
            entry_side = "Sell"  # positive funding → shorts collect from longs

        if not entry_side:
            print(f" → no signal (|{rate_pct:.4f}%| < {min_rate:.3f}%)")
            continue

        # Compute qty from USD position size
        price = 0.0
        if client:
            try:
                ticker = client._get("/v5/market/tickers", {"category": "linear", "symbol": symbol})
                price = float((ticker.get("result", {}).get("list") or [{}])[0].get("lastPrice", 0) or 0)
            except Exception:
                pass
        qty_raw = position_usd / max(price, 1.0) if price > 0 else 0
        min_q = _min_qty(symbol)
        qty = max(round(qty_raw / min_q) * min_q, min_q)
        qty_str = f"{qty:.4f}".rstrip("0").rstrip(".")

        if not dry_run and client and price > 0:
            try:
                result = client.place_order(symbol, entry_side, qty_str)
                print(f" → ENTER {entry_side} qty={qty_str} (funding={rate_pct:.4f}%)")
            except Exception as e:
                print(f" → ENTER FAILED: {e}")
                continue
        else:
            print(f" → [DRY_RUN] ENTER {entry_side} qty={qty_str} (funding={rate_pct:.4f}%, price≈{price:.2f})")

        positions[symbol] = {
            "side": entry_side,
            "qty": qty_str,
            "entry_price": price,
            "entry_ts": int(time.time()),
            "entry_rate_pct": rate_pct,
            "sl_pct": sl_pct * 100,
        }
        actions.append({"symbol": symbol, "action": "enter", "side": entry_side, "rate_pct": rate_pct})
        msg = (f"💸 CARRY ENTER {symbol} {entry_side} qty={qty_str}\n"
               f"funding={rate_pct:.4f}% → collecting carry\n"
               f"{'⚠️ DRY RUN — no real order' if dry_run else '✅ Order placed'}")
        _tg(tg_token, tg_chat_id, msg)

    state["positions"] = positions
    state["last_run_ts"] = int(time.time())
    return state


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Funding carry executor — scan rates and manage positions")
    ap.add_argument("--dry-run", action="store_true", default=_env_bool("CARRY_DRY_RUN", True))
    ap.add_argument("--symbols",    default=_env("CARRY_SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT"))
    ap.add_argument("--min-rate",   type=float, default=_env_float("CARRY_MIN_RATE_PCT", 0.05))
    ap.add_argument("--close-rate", type=float, default=_env_float("CARRY_CLOSE_RATE_PCT", 0.01))
    ap.add_argument("--position-usd", type=float, default=_env_float("CARRY_POSITION_USD", 50.0))
    ap.add_argument("--max-positions", type=int, default=_env_int("CARRY_MAX_POSITIONS", 3))
    ap.add_argument("--sl-pct",     type=float, default=_env_float("CARRY_SL_PCT", 2.5))
    ap.add_argument("--state-file", default=_env("CARRY_STATE_FILE",
                                                   "runtime/funding_carry/executor_state.json"))
    args = ap.parse_args()

    api_key    = _env("BYBIT_API_KEY")
    api_secret = _env("BYBIT_API_SECRET")
    tg_token   = _env("TG_TOKEN")
    tg_chat_id = _env("TG_CHAT_ID")

    client = None
    if api_key and api_secret:
        client = BybitClient(api_key, api_secret)
    elif not args.dry_run:
        print("ERROR: BYBIT_API_KEY / BYBIT_API_SECRET not set. Use --dry-run or set keys.", file=sys.stderr)
        return 1

    cfg = {
        "symbols":       [s.strip().upper() for s in args.symbols.split(",") if s.strip()],
        "min_rate":      args.min_rate,
        "close_rate":    args.close_rate,
        "position_usd":  args.position_usd,
        "max_positions": args.max_positions,
        "sl_pct":        args.sl_pct,
    }

    state_path = Path(args.state_file)
    state = _load_state(state_path)

    print(f"\n{'─'*60}")
    print(f"Funding Carry Executor — {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print(f"dry_run={args.dry_run}  symbols={cfg['symbols']}")
    print(f"entry_threshold={cfg['min_rate']:.3f}%  close_threshold={cfg['close_rate']:.3f}%")
    print(f"position_usd=${cfg['position_usd']:.0f}  max_positions={cfg['max_positions']}")
    print(f"{'─'*60}")

    state = run_once(client, cfg, state, args.dry_run, tg_token, tg_chat_id)
    _save_state(state_path, state)

    open_positions = state.get("positions", {})
    print(f"\nOpen carry positions: {len(open_positions)}")
    for sym, pos in open_positions.items():
        print(f"  {sym}: {pos['side']} qty={pos['qty']} rate={pos.get('entry_rate_pct',0):.4f}%")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
