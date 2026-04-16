"""
bot/env_helpers.py — Pure env/config helpers.
No external project dependencies. Safe to import anywhere.
Extracted from smart_pump_reversal_bot.py (lines ~43-68).
"""
from __future__ import annotations
import os


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        if not name:
            continue
        v = os.getenv(name)
        if v is None:
            continue
        text = str(v).strip()
        if text:
            return text
    return default


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _env_bool_any(*names: str, default: bool) -> bool:
    raw = _env_first(*names, default="1" if default else "0")
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _env_float_any(*names: str, default: float) -> float:
    raw = _env_first(*names, default=str(default))
    try:
        return float(raw)
    except Exception:
        return default


def _mirror_env_aliases(alias_map: dict[str, str]) -> None:
    for canonical, alias in alias_map.items():
        canonical_value = _env_first(canonical, default="")
        if canonical_value:
            continue
        alias_value = _env_first(alias, default="")
        if alias_value:
            os.environ[canonical] = alias_value


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
