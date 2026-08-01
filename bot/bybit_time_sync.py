from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable


TIMESTAMP_ERROR_CODE = "10002"
AUTH_ERROR_CODES = frozenset({"33004", "10003", "10004", "10005"})


def _ret_code(payload: dict[str, Any] | None) -> str:
    return str((payload or {}).get("retCode"))


def is_timestamp_error(payload: dict[str, Any] | None) -> bool:
    """Bybit 10002 is clock/recv-window drift, not an invalid API key."""
    if _ret_code(payload) == TIMESTAMP_ERROR_CODE:
        return True
    message = str((payload or {}).get("retMsg") or "").lower()
    return "req_timestamp" in message and "recv_window" in message


def is_auth_error(payload: dict[str, Any] | None) -> bool:
    """Return only credential/signature failures that justify an auth cooldown."""
    if is_timestamp_error(payload):
        return False
    if _ret_code(payload) in AUTH_ERROR_CODES:
        return True
    message = str((payload or {}).get("retMsg") or "").lower()
    credential_markers = (
        "api key",
        "api-key",
        "api_key",
        "signature",
        "permission denied",
        "key has expired",
    )
    return any(marker in message for marker in credential_markers)


@dataclass
class BybitClock:
    """Small in-process correction learned from a signed Bybit error response."""

    offset_ms: int = 0
    recv_window_ms: int = 10_000
    max_correction_ms: int = 120_000
    now_ms: Callable[[], int] = lambda: int(time.time() * 1000)

    def timestamp(self) -> str:
        return str(int(self.now_ms()) + int(self.offset_ms))

    def learn(self, payload: dict[str, Any] | None) -> bool:
        raw_server_time = (payload or {}).get("time")
        try:
            server_time = int(float(raw_server_time))
        except (TypeError, ValueError, OverflowError):
            return False
        if not math.isfinite(float(server_time)) or server_time <= 0:
            return False
        correction = server_time - int(self.now_ms())
        if abs(correction) > int(self.max_correction_ms):
            return False
        self.offset_ms = int(correction)
        return True

