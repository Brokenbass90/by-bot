"""
bot/auth.py — Auth state and helpers.

Extracted from smart_pump_reversal_bot.py (lines ~212-225).
Shared mutable state: AUTH_DISABLED_UNTIL, AUTH_LAST_ERROR.
These dicts are module-level singletons — all importers share the same objects.

FIX vs original: mark_auth_fail now accepts an optional notify_fn callback
so that callers can pass tg_trade without creating a circular import.
The original signature is preserved for compatibility (notify_fn defaults to None).
"""
from __future__ import annotations

import time
import os
from typing import Optional, Callable

# ─── Shared auth state ──────────────────────────────────────────────────────
AUTH_DISABLED_UNTIL: dict = {}   # account_name → expiry_ts
AUTH_LAST_ERROR: dict = {}       # account_name → error_str

BOT_START_TS: int = int(time.time())


# ─── Helpers ────────────────────────────────────────────────────────────────

def auth_disabled(name: str) -> bool:
    """Return True if private API calls are disabled for this account.

    DRY_RUN is read lazily from the environment to avoid load order issues.
    In DRY_RUN mode auth is always considered enabled (no real calls anyway).
    """
    dry_run = os.getenv("DRY_RUN", "True").strip().lower() in ("1", "true", "yes", "y")
    if dry_run:
        return False
    until = int(AUTH_DISABLED_UNTIL.get(name) or 0)
    return int(time.time()) < until


def mark_auth_fail(
    name: str,
    err: Exception,
    cooldown_sec: int = 600,
    notify_fn: Optional[Callable[[str], None]] = None,
) -> None:
    """Record an auth failure and disable private calls for cooldown_sec.

    FIX: auth flood prevention — once this is called, auth_disabled() returns
    True for the next `cooldown_sec` seconds. All callers should check
    auth_disabled() BEFORE making a request to prevent flood-logging.

    Args:
        notify_fn: Optional callback (e.g. tg_trade) to send a Telegram alert.
                   Pass None to suppress notifications (e.g. during startup).
    """
    AUTH_DISABLED_UNTIL[name] = int(time.time()) + int(cooldown_sec)
    AUTH_LAST_ERROR[name] = str(err)[:300]

    if notify_fn is not None:
        try:
            notify_fn(
                f"🛑 AUTH FAIL [{name}]: {AUTH_LAST_ERROR[name]}\n"
                f"Отключаю приватные вызовы на {cooldown_sec // 60} мин."
            )
        except Exception:
            pass


def auth_cooldown_remaining(name: str) -> int:
    """Return seconds remaining in auth cooldown, or 0 if not disabled."""
    until = int(AUTH_DISABLED_UNTIL.get(name) or 0)
    remaining = until - int(time.time())
    return max(0, remaining)
