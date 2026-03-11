"""
bot/env_helpers.py — Pure env/config helpers.
No external project dependencies. Safe to import anywhere.
Extracted from smart_pump_reversal_bot.py (lines ~43-68).
"""
from __future__ import annotations
import os


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _csv_lower_set(name: str) -> set:
    raw = os.getenv(name, "") or ""
    return {x.strip().lower() for x in str(raw).split(",") if x.strip()}


def _csv_upper_set(name: str) -> set:
    raw = os.getenv(name, "") or ""
    return {x.strip().upper() for x in str(raw).split(",") if x.strip()}


def _session_name_utc(ts_sec: int) -> str:
    """Return session name: 'asia' / 'europe' / 'us' / 'off'."""
    hour = (int(ts_sec) // 3600) % 24
    if 0 <= hour < 9:
        return "asia"
    if 8 <= hour < 17:
        return "europe"
    if 13 <= hour < 22:
        return "us"
    return "off"
