"""OANDA REST API client — ready for live deployment when OANDA_API_TOKEN is set.

Скелет под docs.oanda.com/v3/. Не делает реальных запросов до тех пор пока
OANDA_API_TOKEN не выставлен в env.

Поддерживаемые endpoints:
  - /v3/accounts/{id}/instruments    — список инструментов
  - /v3/accounts/{id}/pricing        — текущие цены (streaming через separate stream URL)
  - /v3/accounts/{id}/orders         — POST для размещения ордера
  - /v3/accounts/{id}/positions      — текущие позиции
  - /v3/accounts/{id}/trades         — история сделок
  - /v3/accounts/{id}/summary        — баланс + equity

Usage:
    from forex.oanda.client import OandaClient
    cli = OandaClient()
    if not cli.ready:
        raise SystemExit("Add OANDA_API_TOKEN to .env first")
    print(cli.account_summary())
    cli.place_market_order(
        instrument="EUR_USD", units=1000, side="buy",
        stop_loss=1.0820, take_profit=1.0900,
        client_extensions={"id": "claude_test_001", "tag": "smoke"},
    )
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib import error, request


@dataclass
class OandaConfig:
    api_token: str = ""
    account_id: str = ""
    env: str = "practice"  # practice|live
    base_url: str = ""

    def resolve_base_url(self) -> str:
        if self.base_url:
            return self.base_url
        if self.env.lower() == "live":
            return "https://api-fxtrade.oanda.com"
        return "https://api-fxpractice.oanda.com"


def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return str(v).strip() if v is not None else default


class OandaClient:
    """Lightweight REST wrapper. Не использует requests чтобы не тащить deps в forex/."""

    def __init__(self, cfg: Optional[OandaConfig] = None):
        if cfg is None:
            cfg = OandaConfig(
                api_token=_env("OANDA_API_TOKEN"),
                account_id=_env("OANDA_ACCOUNT_ID"),
                env=_env("OANDA_ENV", "practice"),
                base_url=_env("OANDA_BASE_URL", ""),
            )
        self.cfg = cfg
        self.cfg.base_url = self.cfg.resolve_base_url()

    @property
    def ready(self) -> bool:
        return bool(self.cfg.api_token) and bool(self.cfg.account_id)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.cfg.api_token}",
            "Content-Type": "application/json",
            "Accept-Datetime-Format": "RFC3339",
        }

    def _url(self, path: str) -> str:
        return f"{self.cfg.base_url.rstrip('/')}{path}"

    def _request(self, method: str, path: str, body: Optional[dict] = None, timeout: float = 10.0) -> dict:
        if not self.ready:
            raise RuntimeError("OandaClient not ready: set OANDA_API_TOKEN and OANDA_ACCOUNT_ID in .env")
        url = self._url(path)
        data = json.dumps(body).encode() if body is not None else None
        req = request.Request(url=url, data=data, method=method, headers=self._headers())
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                if not raw:
                    return {}
                return json.loads(raw)
        except error.HTTPError as e:
            body_txt = e.read().decode("utf-8", errors="replace") if e.fp else ""
            raise RuntimeError(f"OANDA HTTP {e.code} {method} {path}: {body_txt[:300]}") from e
        except error.URLError as e:
            raise RuntimeError(f"OANDA network error {method} {path}: {e.reason}") from e

    # ── Account ───────────────────────────────────────────────────────────────
    def account_summary(self) -> dict:
        return self._request("GET", f"/v3/accounts/{self.cfg.account_id}/summary")

    def instruments(self) -> dict:
        return self._request("GET", f"/v3/accounts/{self.cfg.account_id}/instruments")

    # ── Pricing ───────────────────────────────────────────────────────────────
    def pricing(self, instruments: list[str]) -> dict:
        ins_csv = ",".join(s.replace("/", "_").upper() for s in instruments)
        return self._request("GET", f"/v3/accounts/{self.cfg.account_id}/pricing?instruments={ins_csv}")

    # ── Orders ────────────────────────────────────────────────────────────────
    def place_market_order(
        self,
        instrument: str,
        units: int,
        side: str = "buy",
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        time_in_force: str = "FOK",
        client_extensions: Optional[dict] = None,
    ) -> dict:
        """Размещает Market order с опциональными SL/TP.

        instrument: "EUR_USD", "USD_JPY" (NB: в OANDA underscore разделитель).
        units: положительное число; для side="sell" автоматически становится отрицательным.
        side: buy | sell.
        stop_loss / take_profit: ABSOLUTE prices (not pip-distance).
        client_extensions.id: используется как orderLinkId аналогично Bybit (idempotency).
        """
        units_signed = abs(int(units)) * (1 if side.lower() == "buy" else -1)
        order = {
            "type": "MARKET",
            "instrument": instrument.replace("/", "_").upper(),
            "units": str(units_signed),
            "timeInForce": time_in_force,
            "positionFill": "DEFAULT",
        }
        if stop_loss is not None:
            order["stopLossOnFill"] = {"price": f"{stop_loss:.5f}", "timeInForce": "GTC"}
        if take_profit is not None:
            order["takeProfitOnFill"] = {"price": f"{take_profit:.5f}", "timeInForce": "GTC"}
        if client_extensions:
            order["clientExtensions"] = {
                "id": str(client_extensions.get("id", ""))[:128],
                "tag": str(client_extensions.get("tag", ""))[:128],
                "comment": str(client_extensions.get("comment", ""))[:128],
            }
        body = {"order": order}
        return self._request("POST", f"/v3/accounts/{self.cfg.account_id}/orders", body=body)

    def close_position(self, instrument: str, side: str = "all") -> dict:
        """Закрывает позицию по instrument. side ∈ {long, short, all}."""
        ins = instrument.replace("/", "_").upper()
        body: dict[str, Any] = {}
        if side in ("long", "all"):
            body["longUnits"] = "ALL"
        if side in ("short", "all"):
            body["shortUnits"] = "ALL"
        return self._request("PUT", f"/v3/accounts/{self.cfg.account_id}/positions/{ins}/close", body=body)

    # ── Positions / trades ────────────────────────────────────────────────────
    def open_positions(self) -> dict:
        return self._request("GET", f"/v3/accounts/{self.cfg.account_id}/openPositions")

    def open_trades(self) -> dict:
        return self._request("GET", f"/v3/accounts/{self.cfg.account_id}/openTrades")

    def trade_history(self, count: int = 50) -> dict:
        return self._request("GET", f"/v3/accounts/{self.cfg.account_id}/trades?count={count}&state=ALL")


# Smoke test (требует OANDA_API_TOKEN)
if __name__ == "__main__":
    cli = OandaClient()
    if not cli.ready:
        print("Set OANDA_API_TOKEN and OANDA_ACCOUNT_ID in .env first.")
        raise SystemExit(0)
    print("Account summary:")
    print(json.dumps(cli.account_summary(), indent=2)[:500])
    print()
    print("Pricing EUR_USD, GBP_USD:")
    print(json.dumps(cli.pricing(["EUR_USD", "GBP_USD"]), indent=2)[:500])
