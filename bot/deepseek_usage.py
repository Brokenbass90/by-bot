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
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence


CURRENT_DEEPSEEK_MODEL = "deepseek-v4-flash"
RETIRED_DEEPSEEK_MODELS = frozenset({"deepseek-chat", "deepseek-reasoner"})
# Source checked 2026-10-03: https://api-docs.deepseek.com/quick_start/pricing/
# Flash uncached peak: $0.30 input / $1.20 output per million tokens. Always
# charge this ceiling, including off-peak/cache hits; this is not a provider bill.
DEEPSEEK_PRICE_VALID_UNTIL_TS = 1793491200  # 2026-11-01 00:00 UTC
_FLASH_MODELS = ("deepseek-v4-flash", "deepseek-flash", "deepseek-v4-flash-vision-exp")
_MAX_MONTHLY_USD_MICROS = 1_000_000
_PRICE_POLICY = "flash-20261003-peak-utf8-envelope-v1"
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
            if isinstance(value, float):
                continue  # Fractional/non-finite provider counters are not billing evidence.
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
    # Migrate under a write lock, including concurrent first starts. The triggers
    # also protect an already-loaded legacy Telegram INSERT without a core restart.
    connection.execute("BEGIN IMMEDIATE")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(provider_attempts)")}
    for name, kind in (("reserved_usd_micros", "INTEGER"), ("charge_usd_micros", "INTEGER"),
                       ("pricing_policy", "TEXT")):
        if name not in columns:
            connection.execute(f"ALTER TABLE provider_attempts ADD COLUMN {name} {kind}")
    connection.execute("""CREATE TABLE IF NOT EXISTS ai_budget_months (
        month_utc TEXT PRIMARY KEY, cap_usd_micros INTEGER NOT NULL)""")
    # Unknown historical billing occupies the entire envelope; no retroactive
    # 'zero cost' inference. Existing token counters may only lower a known bound.
    connection.execute("""UPDATE provider_attempts SET
        reserved_usd_micros = CASE WHEN source='legacy_audit_migration' THEN 1000000
            ELSE ((max(0,prompt_chars)*4+8192)*3+max(0,max_tokens)*12+9)/10 END,
        charge_usd_micros = CASE WHEN source='legacy_audit_migration' THEN 1000000
            WHEN status='ok' AND prompt_tokens>=0 AND completion_tokens>=0
                 AND total_tokens=prompt_tokens+completion_tokens
            THEN (prompt_tokens*3+completion_tokens*12+9)/10
            ELSE ((max(0,prompt_chars)*4+8192)*3+max(0,max_tokens)*12+9)/10 END,
        pricing_policy='flash-20261003-peak-utf8-envelope-v1'
        WHERE charge_usd_micros IS NULL""")
    ceiling = "((NEW.prompt_chars*4+8192)*3+NEW.max_tokens*12+9)/10"
    model_sql = ",".join("'" + value + "'" for value in _FLASH_MODELS)
    connection.execute(f"""CREATE TRIGGER IF NOT EXISTS ai_cash_before_attempt_v1
        BEFORE INSERT ON provider_attempts WHEN NEW.source != 'legacy_audit_migration'
        BEGIN
          SELECT CASE WHEN NEW.model NOT IN ({model_sql}) OR NEW.ts >= {DEEPSEEK_PRICE_VALID_UNTIL_TS}
            OR NEW.prompt_chars<0 OR NEW.prompt_chars>100000 OR NEW.max_tokens<=0 OR NEW.max_tokens>1200
            THEN RAISE(ABORT,'DeepSeek cash policy denies model/time/size') END;
          SELECT CASE WHEN EXISTS(SELECT 1 FROM provider_attempts WHERE status='billing_contract_breach')
            THEN RAISE(ABORT,'DeepSeek billing contract breach') END;
          SELECT CASE WHEN (SELECT COALESCE(SUM(charge_usd_micros),0) FROM provider_attempts
              WHERE substr(day_utc,1,7)=strftime('%Y-%m',NEW.ts,'unixepoch')) + {ceiling}
              > COALESCE((SELECT cap_usd_micros FROM ai_budget_months
                  WHERE month_utc=strftime('%Y-%m',NEW.ts,'unixepoch')),1000000)
            THEN RAISE(ABORT,'DeepSeek monthly cash budget exhausted') END;
        END""")
    connection.execute(f"""CREATE TRIGGER IF NOT EXISTS ai_cash_after_attempt_v1
        AFTER INSERT ON provider_attempts
        BEGIN
          UPDATE provider_attempts SET
            reserved_usd_micros=CASE WHEN NEW.source='legacy_audit_migration' THEN 1000000 ELSE {ceiling} END,
            charge_usd_micros=CASE WHEN NEW.source='legacy_audit_migration' THEN 1000000 ELSE {ceiling} END,
            pricing_policy='{_PRICE_POLICY}' WHERE id=NEW.id;
        END""")
    connection.execute("""CREATE TRIGGER IF NOT EXISTS ai_cash_after_finalize_v1
        AFTER UPDATE OF status,prompt_tokens,completion_tokens,total_tokens ON provider_attempts
        WHEN NEW.status='ok' AND typeof(NEW.prompt_tokens)='integer'
          AND typeof(NEW.completion_tokens)='integer' AND NEW.prompt_tokens>=0 AND NEW.completion_tokens>=0
          AND NEW.total_tokens=NEW.prompt_tokens+NEW.completion_tokens
        BEGIN
          UPDATE provider_attempts SET
            status=CASE WHEN NEW.prompt_tokens>NEW.prompt_chars*4+8192
                  OR NEW.completion_tokens>NEW.max_tokens
                  OR (NEW.prompt_tokens*3+NEW.completion_tokens*12+9)/10>NEW.reserved_usd_micros
                THEN 'billing_contract_breach' ELSE 'ok' END,
            charge_usd_micros=CASE WHEN NEW.prompt_tokens>NEW.prompt_chars*4+8192
                  OR NEW.completion_tokens>NEW.max_tokens
                  OR (NEW.prompt_tokens*3+NEW.completion_tokens*12+9)/10>NEW.reserved_usd_micros
                THEN max(NEW.reserved_usd_micros,(NEW.prompt_tokens*3+NEW.completion_tokens*12+9)/10)
                ELSE (NEW.prompt_tokens*3+NEW.completion_tokens*12+9)/10 END
            WHERE id=NEW.id;
        END""")
    connection.commit()
    return connection


def _monthly_cap_usd_micros() -> int:
    try:
        value = Decimal(os.getenv("DEEPSEEK_MONTHLY_USD_CAP", "1"))
        if not value.is_finite() or value <= 0:
            return 0
        return min(_MAX_MONTHLY_USD_MICROS, int(value * 1_000_000))
    except (InvalidOperation, ValueError, OverflowError):
        return 0


def _persist_monthly_cap(connection: sqlite3.Connection, month: str, cap: int) -> None:
    connection.execute('BEGIN IMMEDIATE')
    connection.execute('''INSERT INTO ai_budget_months(month_utc,cap_usd_micros) VALUES(?,?)
        ON CONFLICT(month_utc) DO UPDATE SET cap_usd_micros=min(cap_usd_micros,excluded.cap_usd_micros)''',
        (month,cap))
    connection.commit()  # Persist reductions even when the next attempt is denied.


def deepseek_cash_budget_status(*, path: Path | None = None, now_ts: int | None = None) -> dict[str, Any]:
    stamp = datetime.fromtimestamp(time.time() if now_ts is None else now_ts, tz=timezone.utc)
    month = stamp.strftime("%Y-%m")
    result = {"month_utc": month, "cap_usd_micros": 0, "charged_usd_micros": 0,
              "remaining_usd_micros": 0, "pricing_policy": _PRICE_POLICY, "accounting_ok": False}
    connection = None
    try:
        connection = _attempt_connection(path or attempt_ledger_path())
        _persist_monthly_cap(connection,month,_monthly_cap_usd_micros())
        cap_row = connection.execute("SELECT cap_usd_micros FROM ai_budget_months WHERE month_utc=?", (month,)).fetchone()
        cap = min(_monthly_cap_usd_micros(), int(cap_row[0]) if cap_row else _MAX_MONTHLY_USD_MICROS)
        charged = int(connection.execute("SELECT COALESCE(SUM(charge_usd_micros),0) FROM provider_attempts WHERE substr(day_utc,1,7)=?", (month,)).fetchone()[0])
        breach = connection.execute("SELECT 1 FROM provider_attempts WHERE status='billing_contract_breach' LIMIT 1").fetchone()
        valid = stamp.timestamp() < DEEPSEEK_PRICE_VALID_UNTIL_TS and not breach and cap > 0
        result.update(cap_usd_micros=cap, charged_usd_micros=charged,
                      remaining_usd_micros=max(0,cap-charged) if valid else 0, accounting_ok=bool(valid))
    except (OSError, sqlite3.Error, TypeError, ValueError):
        pass
    finally:
        if connection is not None:
            connection.close()
    return result


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
    cash_cap = _monthly_cap_usd_micros()
    ts = int(time.time() if now_ts is None else now_ts)
    stamp = datetime.fromtimestamp(ts, tz=timezone.utc)
    day = stamp.strftime("%Y-%m-%d")
    destination = path or attempt_ledger_path()
    connection: sqlite3.Connection | None = None
    try:
        connection = _attempt_connection(destination)
        _persist_monthly_cap(connection,day[:7],cash_cap)
        if cap<=0 or cash_cap<=0:
            return None
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
        previous = connection.execute("SELECT reserved_usd_micros,prompt_chars,max_tokens FROM provider_attempts WHERE id=? AND status='reserved'", (reservation.attempt_id,)).fetchone()
        if previous is None:
            connection.rollback()
            return False
        charge = int(previous[0])
        actual_cost = None
        if all(key in usage for key in ("prompt_tokens", "completion_tokens", "total_tokens")):
            if usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens']:
                actual_cost = (usage['prompt_tokens']*3 + usage['completion_tokens']*12+9)//10
                if usage['prompt_tokens'] > int(previous[1])*4+8192 or usage['completion_tokens'] > int(previous[2]) or actual_cost > charge:
                    status = 'billing_contract_breach'
                    charge = max(charge, actual_cost)
                elif status == 'ok':
                    charge = actual_cost
        cursor = connection.execute(
            """
            UPDATE provider_attempts SET
                status = ?, finalized_ts = ?, latency_ms = ?, error_type = ?,
                prompt_tokens = ?, completion_tokens = ?, total_tokens = ?,
                prompt_cache_hit_tokens = ?, prompt_cache_miss_tokens = ?, charge_usd_micros = ?
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
                charge,
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
