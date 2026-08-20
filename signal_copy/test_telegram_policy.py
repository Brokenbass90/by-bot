# -*- coding: utf-8 -*-
"""Telegram transport stays allowlisted and never creates action-less buttons."""
from __future__ import annotations

import os

os.environ["SIGCOPY_TG_CHAT_IDS"] = "123,-456"
os.environ["SIGCOPY_TG_USER_IDS"] = "123,-456"

import telegram_bot


assert telegram_bot.is_allowed(123, 123, "private")
assert telegram_bot.is_allowed("-456", "-456", "private")
assert not telegram_bot.is_allowed(123, 999, "private")
assert not telegram_bot.is_allowed(123, 123, "group")
assert not telegram_bot.is_allowed(None, None, "private")


class Card:
    kind = "SIGNAL"
    symbol = "XAUUSD"
    side = "BUY"
    entry_used = 4400.0
    stop_loss = 4380.0
    chosen_tp = 4440.0
    lot = 0.01
    risk_cash = 10.0
    currency = "USD"
    rr = 2.0
    can_execute = True
    blockers = []
    warnings = []


text = telegram_bot.card_text(Card())
assert "РУЧНОМУ ПОДТВЕРЖДЕНИЮ" in text
assert "XAUUSD BUY" in text
print("OK: Telegram intake is allowlisted and describes manual confirmation")
