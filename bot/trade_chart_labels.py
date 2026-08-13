"""Truthful labels shared by Telegram trade-chart renderers."""
from __future__ import annotations

from typing import Any, Mapping


def normalize_bybit_timeframe(value: Any) -> str | None:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if raw.isdigit():
        return f"{int(raw)}m"
    aliases = {"d": "1d", "w": "1w", "m": "1M"}
    return aliases.get(raw, raw)


def signal_timeframe_label(
    strategy: str,
    geometry: Mapping[str, Any] | None,
    *,
    att1_default: str = "60",
) -> tuple[str, str]:
    """Return ``(label, provenance)`` without inventing an exact timeframe.

    New snapshots serialize ``tf=`` in the signal reason.  Old ATT1 snapshots
    predate that field, so their configured family default is shown explicitly
    as a fallback rather than being presented as recorded evidence.
    """
    payload = geometry or {}
    recorded = normalize_bybit_timeframe(payload.get("signal_timeframe"))
    if recorded:
        return recorded, "recorded_signal_reason"
    if "att1" in str(strategy or "").strip().lower():
        fallback = normalize_bybit_timeframe(att1_default)
        if fallback:
            return fallback, "att1_config_fallback"
    return "unknown", "not_recorded"
