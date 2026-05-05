"""OANDA signal-to-order bridge.

Принимает TradeSignal от forex-стратегий, превращает в OANDA market order
с bracket SL/TP. Идемпотентность через client_extensions.id (per-bar SHA1
аналогично Bybit `bot/order_link.py`).

Usage (из bot loop):
    from forex.oanda.bridge import OandaBridge
    bridge = OandaBridge()  # читает .env
    if not bridge.ready:
        return  # OANDA credentials не выставлены → silent skip
    bridge.execute_signal(signal, equity=500.0)

Risk per trade controlled by env:
    FOREX_RISK_PCT          (0.005)  — % equity per trade
    FOREX_MAX_POSITIONS     (3)
    FOREX_LEVERAGE          (10)     — applied as units multiplier
    FOREX_DRY_RUN           (1)      — 1 = log only, 0 = real orders
    FOREX_PIP_MULT_LOOKUP   — для каждой пары размер pip (по умолчанию EUR_USD=0.0001, JPY pairs=0.01)
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from forex.oanda.client import OandaClient


# Pip size lookup
_PIP_SIZE = {
    "EUR_USD": 0.0001, "GBP_USD": 0.0001, "AUD_USD": 0.0001, "NZD_USD": 0.0001,
    "USD_CAD": 0.0001, "USD_CHF": 0.0001,
    "USD_JPY": 0.01, "EUR_JPY": 0.01, "GBP_JPY": 0.01, "AUD_JPY": 0.01,
    "EUR_GBP": 0.0001, "EUR_CHF": 0.0001, "GBP_CHF": 0.0001,
    # CFD на indices (приближённо)
    "SPX500_USD": 0.1, "NAS100_USD": 0.1, "DE30_EUR": 0.1,
    # Metals
    "XAU_USD": 0.01, "XAG_USD": 0.001,
}


def _pip_size(instrument: str) -> float:
    ins = instrument.replace("/", "_").upper()
    return _PIP_SIZE.get(ins, 0.0001)


def _env_float(name: str, default: float) -> float:
    try: return float(os.getenv(name, "") or default)
    except Exception: return default


def _env_int(name: str, default: int) -> int:
    try: return int(os.getenv(name, "") or default)
    except Exception: return default


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or ("1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _make_link_id(strategy: str, instrument: str, side: str) -> str:
    """Per-5m-bar SHA1 для idempotency (аналог Bybit `bot.order_link`)."""
    bar_ts = int(time.time() // 300) * 300
    raw = f"oanda|{strategy}|{instrument}|{side}|{bar_ts}"
    return hashlib.sha1(raw.encode()).hexdigest()[:28]


@dataclass
class OandaBridgeConfig:
    risk_pct: float = 0.005
    max_positions: int = 3
    leverage: int = 10
    dry_run: bool = True
    log_path: Path = Path("runtime/oanda/bridge_log.jsonl")


class OandaBridge:
    def __init__(self, cfg: Optional[OandaBridgeConfig] = None, client: Optional[OandaClient] = None):
        self.cfg = cfg or OandaBridgeConfig(
            risk_pct=_env_float("FOREX_RISK_PCT", 0.005),
            max_positions=_env_int("FOREX_MAX_POSITIONS", 3),
            leverage=_env_int("FOREX_LEVERAGE", 10),
            dry_run=_env_bool("FOREX_DRY_RUN", True),
        )
        self.client = client or OandaClient()
        self.cfg.log_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def ready(self) -> bool:
        return self.client.ready

    def _log(self, event: dict) -> None:
        try:
            event.setdefault("ts", int(time.time()))
            with open(self.cfg.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def calc_units(self, equity: float, entry: float, sl: float, instrument: str) -> int:
        """Position sizing: risk_pct of equity / |entry - sl| in pips × leverage."""
        pip = _pip_size(instrument)
        risk_usd = equity * self.cfg.risk_pct
        sl_pips = abs(entry - sl) / pip
        if sl_pips <= 0:
            return 0
        # Approximation: 1 pip on 1000 units of EUR_USD ≈ $0.10
        units_per_pip_value = 0.10 if "JPY" not in instrument.upper() else 1.0  # rough
        units = (risk_usd / sl_pips) * (1.0 / units_per_pip_value) * 1000
        units *= self.cfg.leverage
        return max(0, int(units))

    def execute_signal(self, signal: dict, equity: float) -> dict:
        """Принимает signal: {strategy, instrument, side, entry, sl, tp, ...}.

        Возвращает {status, link_id, order_id, units, message}.
        """
        if not self.ready:
            self._log({"event": "skip", "reason": "not_ready"})
            return {"status": "skip", "reason": "not_ready"}

        instrument = signal.get("instrument") or signal.get("symbol", "EUR_USD")
        side = (signal.get("side") or "buy").lower()
        entry = float(signal.get("entry", 0) or 0)
        sl = float(signal.get("sl", 0) or 0)
        tp = signal.get("tp")
        if tp is not None:
            try: tp = float(tp)
            except: tp = None
        strategy = signal.get("strategy", "unknown")

        units = self.calc_units(equity=equity, entry=entry, sl=sl, instrument=instrument)
        if units <= 0:
            self._log({"event": "skip", "reason": "zero_units", "signal": signal})
            return {"status": "skip", "reason": "zero_units"}

        link_id = _make_link_id(strategy, instrument, side)

        if self.cfg.dry_run:
            self._log({
                "event": "dry_run", "link_id": link_id, "strategy": strategy,
                "instrument": instrument, "side": side, "units": units,
                "entry": entry, "sl": sl, "tp": tp,
            })
            return {"status": "dry_run", "link_id": link_id, "units": units}

        try:
            resp = self.client.place_market_order(
                instrument=instrument,
                units=units,
                side=side,
                stop_loss=sl if sl > 0 else None,
                take_profit=tp if tp and tp > 0 else None,
                client_extensions={"id": link_id, "tag": strategy[:64]},
            )
            order_id = ((resp or {}).get("orderFillTransaction") or {}).get("id", "")
            self._log({
                "event": "placed", "link_id": link_id, "order_id": order_id,
                "strategy": strategy, "instrument": instrument, "side": side, "units": units,
                "entry": entry, "sl": sl, "tp": tp,
            })
            return {"status": "placed", "link_id": link_id, "order_id": order_id, "units": units}
        except Exception as e:
            self._log({"event": "error", "link_id": link_id, "error": str(e)[:200]})
            return {"status": "error", "link_id": link_id, "error": str(e)[:200]}


if __name__ == "__main__":
    bridge = OandaBridge()
    print(f"Ready: {bridge.ready}")
    print(f"Config: dry_run={bridge.cfg.dry_run}, risk_pct={bridge.cfg.risk_pct}, leverage={bridge.cfg.leverage}")
