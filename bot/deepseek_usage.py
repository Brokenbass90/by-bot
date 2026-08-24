"""Small, secret-free DeepSeek request accounting and budget helpers.

The legacy ``data/deepseek_audit.jsonl`` records questions and answers but did
not persist provider usage.  This module is intentionally separate: it stores
only request metadata and token counters returned by DeepSeek.  The SQLite
attempt ledger durably reserves each paid HTTP attempt before transport; the
JSONL helper remains API-compatible for non-overlay callers.  Prompts,
responses, API keys and HTTP bodies must never be written here.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


CURRENT_DEEPSEEK_MODEL = "deepseek-v4-flash"
RETIRED_DEEPSEEK_MODELS = frozenset({"deepseek-chat", "deepseek-reasoner"})
_TOKEN_FIELDS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "prompt_cache_hit_tokens",
    "prompt_cache_miss_tokens",
)


@dataclass(frozen=True)
class DeepSeekAttemptReservation:
    """Opaque handle for one durably reserved provider HTTP attempt."""

    attempt_id: int
    path: Path


_ATTEMPT_SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    ts_utc TEXT NOT NULL,
    day_utc TEXT NOT NULL,
    source TEXT NOT NULL,
    model TEXT NOT NULL,
    max_tokens INTEGER NOT NULL,
    prompt_chars INTEGER NOT NULL,
    status TEXT NOT NULL,
    finalized_ts INTEGER,
    latency_ms INTEGER,
    error_type TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    prompt_cache_hit_tokens INTEGER,
    prompt_cache_miss_tokens INTEGER
)
"""
_MIGRATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS budget_migrations (
    day_utc TEXT PRIMARY KEY,
    seeded_ts INTEGER NOT NULL,
    legacy_audit_count INTEGER NOT NULL
)
"""


def normalize_deepseek_model(raw: str | None) -> str:
    """Map retired aliases to the current low-cost chat model."""
    model = str(raw or "").strip()
    if not model or model.lower() in RETIRED_DEEPSEEK_MODELS:
        return CURRENT_DEEPSEEK_MODEL
    return model


def prompt_char_count(messages: Sequence[Mapping[str, Any]]) -> int:
    """Return an input-size proxy without retaining any input text."""
    total = 0
    for item in messages:
        if not isinstance(item, Mapping):
            continue
        total += len(str(item.get("role") or ""))
        total += len(str(item.get("content") or ""))
    return total


def extract_usage(response_payload: Mapping[str, Any] | None) -> dict[str, int]:
    """Extract actual provider counters from an OpenAI-compatible response."""
    if not isinstance(response_payload, Mapping):
        return {}
    raw = response_payload.get("usage")
    if not isinstance(raw, Mapping):
        return {}
    result: dict[str, int] = {}
    for key in _TOKEN_FIELDS:
        value = raw.get(key)
        if isinstance(value, bool):
            continue
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number >= 0:
            result[key] = number
    return result


def usage_log_path() -> Path:
    deployed_root = Path("/root/by-bot")
    default_root = deployed_root if deployed_root.exists() else Path(__file__).resolve().parents[1]
    default_path = default_root / "runtime" / "ai" / "deepseek_usage.jsonl"
    raw = str(
        os.getenv(
            "DEEPSEEK_USAGE_LOG_PATH",
            str(default_path),
        )
        or ""
    ).strip()
    return Path(raw or default_path)


def attempt_ledger_path() -> Path:
    """Return the SQLite ledger used for atomic paid-request reservations."""
    raw = str(os.getenv("DEEPSEEK_ATTEMPT_LEDGER_PATH", "") or "").strip()
    if raw:
        return Path(raw)
    return usage_log_path().with_name("deepseek_attempts.sqlite3")


def _attempt_connection(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=30.0)
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(_ATTEMPT_SCHEMA)
    connection.execute(_MIGRATION_SCHEMA)
    connection.commit()
    return connection


def seed_attempt_ledger_from_legacy_audit(
    audit_path: Path,
    *,
    path: Path | None = None,
    now_ts: int | None = None,
) -> int | None:
    """One-time, fail-closed migration of today's legacy answer audit count.

    Only row timestamps/statuses are inspected.  Questions, answers, prompts,
    response bodies and credentials are never copied into the attempt ledger.
    The migration marker and seed rows commit in one ``BEGIN IMMEDIATE``
    transaction, so concurrent process starts cannot double-seed the day.
    """
    ts = int(time.time() if now_ts is None else now_ts)
    stamp = datetime.fromtimestamp(ts, tz=timezone.utc)
    day = stamp.strftime("%Y-%m-%d")
    legacy_count = 0
    try:
        if audit_path.exists():
            with audit_path.open("r", encoding="utf-8") as handle:
                for raw in handle:
                    try:
                        row = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if not isinstance(row, dict):
                        continue
                    status = str(row.get("status") or "").strip().lower()
                    if status not in {"ok", "error", "empty"}:
                        continue
                    try:
                        row_ts = int(row.get("ts") or 0)
                    except (TypeError, ValueError):
                        continue
                    if row_ts <= 0:
                        continue
                    try:
                        row_day = datetime.fromtimestamp(row_ts, tz=timezone.utc).strftime("%Y-%m-%d")
                    except (OverflowError, OSError, ValueError):
                        continue
                    if row_day == day:
                        legacy_count += 1
    except OSError:
        return None

    destination = path or attempt_ledger_path()
    connection: sqlite3.Connection | None = None
    try:
        connection = _attempt_connection(destination)
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT legacy_audit_count FROM budget_migrations WHERE day_utc = ?",
            (day,),
        ).fetchone()
        if existing is not None:
            connection.rollback()
            return int(existing[0])
        for _ in range(legacy_count):
            connection.execute(
                """
                INSERT INTO provider_attempts (
                    ts, ts_utc, day_utc, source, model, max_tokens,
                    prompt_chars, status, finalized_ts, latency_ms
                ) VALUES (?, ?, ?, 'legacy_audit_migration', ?, 0, 0,
                          'legacy_audit_seed', ?, 0)
                """,
                (ts, stamp.isoformat(), day, CURRENT_DEEPSEEK_MODEL, ts),
            )
        connection.execute(
            """
            INSERT INTO budget_migrations (day_utc, seeded_ts, legacy_audit_count)
            VALUES (?, ?, ?)
            """,
            (day, ts, legacy_count),
        )
        connection.commit()
        return legacy_count
    except (OSError, sqlite3.Error, TypeError, ValueError):
        if connection is not None:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
        return None
    finally:
        if connection is not None:
            connection.close()


def reserve_deepseek_attempt(
    *,
    source: str,
    model: str,
    max_tokens: int,
    prompt_chars: int,
    daily_cap: int,
    path: Path | None = None,
    now_ts: int | None = None,
) -> DeepSeekAttemptReservation | None:
    """Atomically reserve one daily provider-attempt slot before HTTP.

    The committed SQLite row is the authoritative, concurrency-safe budget
    record.  It contains sizes/counters only, never prompts, responses, keys or
    request bodies.  Any storage/locking failure is fail-closed and returns
    ``None`` so callers cannot spend without durable accounting.
    """
    cap = max(0, int(daily_cap or 0))
    if cap <= 0:
        return None
    ts = int(time.time() if now_ts is None else now_ts)
    stamp = datetime.fromtimestamp(ts, tz=timezone.utc)
    day = stamp.strftime("%Y-%m-%d")
    destination = path or attempt_ledger_path()
    connection: sqlite3.Connection | None = None
    try:
        connection = _attempt_connection(destination)
        connection.execute("BEGIN IMMEDIATE")
        used = int(
            connection.execute(
                "SELECT COUNT(*) FROM provider_attempts WHERE day_utc = ?",
                (day,),
            ).fetchone()[0]
        )
        if used >= cap:
            connection.rollback()
            return None
        cursor = connection.execute(
            """
            INSERT INTO provider_attempts (
                ts, ts_utc, day_utc, source, model, max_tokens,
                prompt_chars, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'reserved')
            """,
            (
                ts,
                stamp.isoformat(),
                day,
                str(source or "unknown")[:120],
                normalize_deepseek_model(model),
                max(0, int(max_tokens or 0)),
                max(0, int(prompt_chars or 0)),
            ),
        )
        attempt_id = int(cursor.lastrowid)
        connection.commit()
        return DeepSeekAttemptReservation(attempt_id=attempt_id, path=destination)
    except (OSError, sqlite3.Error, TypeError, ValueError):
        if connection is not None:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
        return None
    finally:
        if connection is not None:
            connection.close()


def finalize_deepseek_attempt(
    reservation: DeepSeekAttemptReservation,
    *,
    latency_ms: int,
    status: str,
    response_payload: Mapping[str, Any] | None = None,
    error_type: str | None = None,
    now_ts: int | None = None,
) -> bool:
    """Finalize the single row for a reserved HTTP attempt."""
    usage = extract_usage(response_payload)
    connection: sqlite3.Connection | None = None
    try:
        connection = _attempt_connection(reservation.path)
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """
            UPDATE provider_attempts SET
                status = ?, finalized_ts = ?, latency_ms = ?, error_type = ?,
                prompt_tokens = ?, completion_tokens = ?, total_tokens = ?,
                prompt_cache_hit_tokens = ?, prompt_cache_miss_tokens = ?
            WHERE id = ? AND status = 'reserved'
            """,
            (
                str(status or "unknown")[:40],
                int(time.time() if now_ts is None else now_ts),
                max(0, int(latency_ms or 0)),
                str(error_type)[:120] if error_type else None,
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
                usage.get("total_tokens"),
                usage.get("prompt_cache_hit_tokens"),
                usage.get("prompt_cache_miss_tokens"),
                int(reservation.attempt_id),
            ),
        )
        if int(cursor.rowcount or 0) != 1:
            connection.rollback()
            return False
        connection.commit()
        return True
    except (OSError, sqlite3.Error, TypeError, ValueError):
        if connection is not None:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
        return False
    finally:
        if connection is not None:
            connection.close()


def count_deepseek_attempts(
    *,
    path: Path | None = None,
    day_utc: str | None = None,
    now_ts: int | None = None,
) -> int:
    """Count durable provider-attempt reservations for one UTC day."""
    ts = int(time.time() if now_ts is None else now_ts)
    day = day_utc or datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    destination = path or attempt_ledger_path()
    connection: sqlite3.Connection | None = None
    try:
        connection = _attempt_connection(destination)
        row = connection.execute(
            "SELECT COUNT(*) FROM provider_attempts WHERE day_utc = ?",
            (str(day),),
        ).fetchone()
        return int(row[0] if row else 0)
    except (OSError, sqlite3.Error, TypeError, ValueError):
        # Counting failure must never report spare budget.
        return 2**31 - 1
    finally:
        if connection is not None:
            connection.close()


def read_deepseek_attempts(*, path: Path | None = None) -> list[dict[str, Any]]:
    """Read sanitized attempt rows for diagnostics/tests."""
    destination = path or attempt_ledger_path()
    connection: sqlite3.Connection | None = None
    try:
        connection = _attempt_connection(destination)
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT * FROM provider_attempts ORDER BY id").fetchall()
        return [dict(row) for row in rows]
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return []
    finally:
        if connection is not None:
            connection.close()


def append_deepseek_usage(
    *,
    source: str,
    model: str,
    max_tokens: int,
    prompt_chars: int,
    latency_ms: int,
    status: str,
    response_payload: Mapping[str, Any] | None = None,
    error_type: str | None = None,
    path: Path | None = None,
) -> bool:
    """Append one sanitized accounting row.

    Failure to write accounting must never turn an advisory AI failure into a
    trading/runtime failure, hence the boolean result instead of an exception.
    ``error_type`` is restricted to a class/status label; callers must not pass
    provider messages because they can echo request data.
    """
    row: dict[str, Any] = {
        "ts": int(time.time()),
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(source or "unknown")[:120],
        "model": normalize_deepseek_model(model),
        "max_tokens": max(0, int(max_tokens or 0)),
        "prompt_chars": max(0, int(prompt_chars or 0)),
        "latency_ms": max(0, int(latency_ms or 0)),
        "status": str(status or "unknown")[:40],
    }
    row.update(extract_usage(response_payload))
    if error_type:
        row["error_type"] = str(error_type)[:120]
    try:
        destination = path or usage_log_path()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return True
    except (OSError, TypeError, ValueError):
        return False
