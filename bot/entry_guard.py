"""
bot/entry_guard.py — lightweight circuit breaker for new entry submissions.
"""
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class EntryCircuitSnapshot:
    open: bool
    failures: int
    remaining_sec: int
    reason: str


class EntryCircuitBreaker:
    """Trip after repeated entry-submit failures and cool down before retrying."""

    def __init__(self, *, failure_threshold: int = 3, cooldown_sec: int = 90) -> None:
        self.failure_threshold = max(1, int(failure_threshold))
        self.cooldown_sec = max(1, int(cooldown_sec))
        self._failures = 0
        self._open_until = 0.0
        self._reason = ""

    def is_open(self, now: float | None = None) -> bool:
        ts = float(time.time() if now is None else now)
        return ts < float(self._open_until)

    def remaining_sec(self, now: float | None = None) -> int:
        ts = float(time.time() if now is None else now)
        return max(0, int(self._open_until - ts))

    def note_success(self) -> None:
        self._failures = 0
        self._open_until = 0.0
        self._reason = ""

    def note_failure(self, reason: str, now: float | None = None) -> EntryCircuitSnapshot:
        ts = float(time.time() if now is None else now)
        self._failures += 1
        self._reason = str(reason or "")[:240]
        if self._failures >= self.failure_threshold:
            self._open_until = max(float(self._open_until), ts + float(self.cooldown_sec))
        return self.snapshot(now=ts)

    def snapshot(self, now: float | None = None) -> EntryCircuitSnapshot:
        ts = float(time.time() if now is None else now)
        return EntryCircuitSnapshot(
            open=self.is_open(ts),
            failures=int(self._failures),
            remaining_sec=self.remaining_sec(ts),
            reason=str(self._reason or ""),
        )
