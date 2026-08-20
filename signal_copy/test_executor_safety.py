# -*- coding: utf-8 -*-
"""Regression tests for MT5 retcode, fresh risk and numeric position type."""
from __future__ import annotations

import pathlib
import tempfile

import config
import store
from executor import breakeven, execute_approved, list_positions


config.EXECUTION_ENABLE = True
config.ALLOW_LIVE = False
config.ALLOWED_SERVERS = ("MetaQuotes-Demo",)
config.ALLOWED_ACCOUNT_LOGINS = (1,)
config.ALLOWED_ACCOUNT_TYPES = ("demo",)
store.DB_PATH = pathlib.Path(tempfile.mkdtemp()) / "executor.db"
conn = store.connect()


def arm(client_id: str) -> tuple[int, str]:
    msg_id, _ = store.save_message(conn, client_id, client_id, "SIGNAL", {})
    gid = store.create_group(
        conn, msg_id,
        {"symbol": "XAUUSD", "side": "BUY", "entry_min": 100.0,
         "entry_max": 100.0, "stop_loss": 90.0, "take_profits": [120.0],
         "chosen_tp": 120.0},
        {"login": 1, "type": "demo"}, 100.0,
    )
    token = store.issue_approval(conn, gid, {
        "symbol": "XAUUSD", "side": "BUY", "lot": 0.5, "sl": 90.0,
        "tp": 120.0, "group_id": gid, "risk_cash": 5.0,
        "equity_ccy": "USD", "client_id": client_id,
    })
    return gid, token


class FakeMCP:
    def __init__(self, response, after=None):
        self.response = response
        self.after = after or []
        self.position_calls = 0
        self.trade_calls = 0

    def account(self):
        return {"server": "MetaQuotes-Demo", "login": 1, "type": "demo",
                "equity": 1000.0, "currency": "USD"}

    def terminal(self):
        return {"server_connected": True, "mcp_trade_allowed": True}

    def symbols(self):
        return [{"symbol": "XAUUSD", "bid": 99.9, "ask": 100.0, "point": 0.1,
                 "contract_size": 1.0, "currency_profit": "USD",
                 "volume_min": 0.1, "volume_max": 50.0, "volume_step": 0.1,
                 "tick_size": 0.0, "tick_value": 0.0}]

    def positions(self):
        self.position_calls += 1
        return [] if self.position_calls == 1 else list(self.after)

    def call(self, name, **request):
        self.trade_calls += 1
        return self.response


# A positive-looking order id beside a rejected retcode must never become OPEN.
gid, token = arm("reject-retcode")
bad = FakeMCP({"retcode": 10016, "success": False, "order": 987654})
result = execute_approved(token, bad, conn)
assert result["ok"] is False, result
assert conn.execute("SELECT status FROM signal_group WHERE id=?", (gid,)).fetchone()[0] == "FAILED"

# Explicit MT5 success still needs a newly reconciled broker position.
gid2, token2 = arm("good-retcode")
position = {"ticket": 42, "symbol": "XAUUSD", "type": 0, "volume": 0.5,
            "price_open": 100.0, "price_current": 101.0, "sl": 90.0,
            "tp": 120.0, "profit": 0.5, "swap": 0.0}
good = FakeMCP({"retcode": 10009, "order": 42}, after=[position])
result2 = execute_approved(token2, good, conn)
assert result2["ok"] is True and result2["ticket"] == 42, result2

# Numeric MT5 type 0 is BUY, so BE on a losing BUY must fail without a trade call.
class PositionMCP:
    calls = 0

    def positions(self):
        return [{"ticket": 77, "symbol": "XAUUSD", "type": 0, "volume": 0.1,
                 "price_open": 100.0, "price_current": 99.0, "sl": 90.0,
                 "tp": 120.0, "profit": -1.0, "swap": 0.0}]

    def call(self, *args, **kwargs):
        self.calls += 1
        return {"retcode": 10009}


pm = PositionMCP()
assert list_positions(pm, conn)[0]["type"] == "buy"
be = breakeven(77, "XAUUSD", pm, conn, client_id="be-losing-buy")
assert be["ok"] is False and pm.calls == 0, be

print("OK: retcodes, broker reconciliation, fresh risk, and numeric BUY are fail-closed")
