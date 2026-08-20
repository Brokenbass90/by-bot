# -*- coding: utf-8 -*-
"""Одноразовые подтверждения close/BE/SL должны быть fail-closed."""
from __future__ import annotations

import pathlib
import tempfile

import store


store.DB_PATH = pathlib.Path(tempfile.mkdtemp()) / "action.db"
conn = store.connect()

token = store.issue_action_approval(
    conn, "close", {"ticket": 123, "symbol": "XAUUSD"}, ttl_sec=30
)
action, payload, error = store.redeem_action_approval(conn, token)
assert not error
assert action == "close"
assert payload == {"ticket": 123, "symbol": "XAUUSD"}

action2, payload2, error2 = store.redeem_action_approval(conn, token)
assert action2 is None and payload2 is None
assert "использовано" in error2

expired = store.issue_action_approval(conn, "breakeven", {"ticket": 7}, ttl_sec=1)
conn.execute("UPDATE action_approval SET expires_ts=0 WHERE token_hash IS NOT NULL AND used_ts=0")
conn.commit()
action3, payload3, error3 = store.redeem_action_approval(conn, expired)
assert action3 is None and payload3 is None
assert "просрочено" in error3

print("OK: action approvals are scoped, atomic, one-time, and expiring")
