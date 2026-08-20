# -*- coding: utf-8 -*-
"""База signal_copy. Своя SQLite, ничего общего с trades.db основного бота.

Пишем ВСЁ: исходный текст, результат разбора, расчёт риска, запрос к терминалу,
ответ терминала. Без записи решения нет решения.
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

DB_PATH = Path(os.getenv("SIGCOPY_DB", Path(__file__).parent / "data" / "signal_copy.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS message (
    id            INTEGER PRIMARY KEY,
    ts            INTEGER NOT NULL,
    source        TEXT NOT NULL DEFAULT 'paste',
    raw_text      TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    kind          TEXT,
    parsed_json   TEXT,
    used_llm      INTEGER NOT NULL DEFAULT 0,
    UNIQUE(content_hash)
);

CREATE TABLE IF NOT EXISTS signal_group (
    id            INTEGER PRIMARY KEY,
    ts            INTEGER NOT NULL,
    message_id    INTEGER REFERENCES message(id),
    symbol        TEXT NOT NULL,
    side          TEXT NOT NULL,
    entry_min     REAL,
    entry_max     REAL,
    stop_loss     REAL,
    take_profits  TEXT,
    chosen_tp     REAL,
    status        TEXT NOT NULL DEFAULT 'NEW',
    price_at_capture REAL,
    account_login INTEGER,
    trade_mode    TEXT,
    broker_server TEXT,
    note          TEXT
);

CREATE TABLE IF NOT EXISTS approval (
    token_hash    TEXT PRIMARY KEY,
    group_id      INTEGER NOT NULL REFERENCES signal_group(id),
    created_ts    INTEGER NOT NULL,
    expires_ts    INTEGER NOT NULL,
    used_ts       INTEGER NOT NULL DEFAULT 0,
    payload_json  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS action_approval (
    token_hash    TEXT PRIMARY KEY,
    action        TEXT NOT NULL,
    created_ts    INTEGER NOT NULL,
    expires_ts    INTEGER NOT NULL,
    used_ts       INTEGER NOT NULL DEFAULT 0,
    payload_json  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS execution (
    id            INTEGER PRIMARY KEY,
    ts            INTEGER NOT NULL,
    group_id      INTEGER REFERENCES signal_group(id),
    action        TEXT NOT NULL,
    client_id     TEXT NOT NULL,
    request_json  TEXT,
    response_json TEXT,
    ok            INTEGER NOT NULL DEFAULT 0,
    ticket        INTEGER,
    error         TEXT,
    UNIQUE(client_id, action)
);

CREATE TABLE IF NOT EXISTS decision_log (
    id       INTEGER PRIMARY KEY,
    ts       INTEGER NOT NULL,
    group_id INTEGER,
    stage    TEXT NOT NULL,
    detail   TEXT
);
CREATE TABLE IF NOT EXISTS telegram_update (
    update_id INTEGER PRIMARY KEY,
    claimed_ts INTEGER NOT NULL,
    finished_ts INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'CLAIMED'
);
CREATE INDEX IF NOT EXISTS idx_group_status ON signal_group(status);
"""


def now() -> int:
    return int(time.time())


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    # Forward-only migration for databases created by the first local draft.
    columns = {row["name"] for row in c.execute("PRAGMA table_info(signal_group)")}
    if "broker_server" not in columns:
        c.execute("ALTER TABLE signal_group ADD COLUMN broker_server TEXT")
        c.commit()
    return c


def log(conn, group_id: int | None, stage: str, detail: Any) -> None:
    conn.execute("INSERT INTO decision_log(ts,group_id,stage,detail) VALUES(?,?,?,?)",
                 (now(), group_id, stage,
                  detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)))
    conn.commit()


def save_message(conn, raw_text: str, content_hash: str, kind: str,
                 parsed: Any, source: str = "paste", used_llm: bool = False) -> tuple[int, bool]:
    """Возвращает (id, is_new). Повтор того же текста не создаёт вторую запись."""
    cur = conn.execute("SELECT id FROM message WHERE content_hash=?", (content_hash,))
    row = cur.fetchone()
    if row:
        return row["id"], False
    cur = conn.execute(
        "INSERT INTO message(ts,source,raw_text,content_hash,kind,parsed_json,used_llm)"
        " VALUES(?,?,?,?,?,?,?)",
        (now(), source, raw_text, content_hash, kind,
         json.dumps(parsed, ensure_ascii=False, default=str), int(used_llm)))
    conn.commit()
    return cur.lastrowid, True


def create_group(conn, message_id: int, sig: dict, account: dict,
                 price_at_capture: float | None) -> int:
    cur = conn.execute(
        "INSERT INTO signal_group(ts,message_id,symbol,side,entry_min,entry_max,stop_loss,"
        "take_profits,chosen_tp,status,price_at_capture,account_login,trade_mode,broker_server)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (now(), message_id, sig["symbol"], sig["side"], sig.get("entry_min"),
         sig.get("entry_max"), sig.get("stop_loss"),
         json.dumps(sig.get("take_profits") or []), sig.get("chosen_tp"),
         "NEW", price_at_capture, account.get("login"), account.get("type"),
         account.get("server")))
    conn.commit()
    return cur.lastrowid


def open_groups(conn, symbol: str | None = None) -> list[sqlite3.Row]:
    q = "SELECT * FROM signal_group WHERE status IN ('OPEN','PARTIAL')"
    args: tuple = ()
    if symbol:
        q += " AND symbol=?"
        args = (symbol,)
    return list(conn.execute(q + " ORDER BY id DESC", args))


def recent_groups(conn, limit: int = 30) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM signal_group ORDER BY id DESC LIMIT ?", (limit,)))


def set_status(conn, group_id: int, status: str, note: str | None = None) -> None:
    conn.execute("UPDATE signal_group SET status=?, note=COALESCE(?,note) WHERE id=?",
                 (status, note, group_id))
    conn.commit()


# ── одноразовый токен подтверждения ──────────────────────────────────────
import hashlib


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def issue_approval(conn, group_id: int, payload: dict, ttl_sec: int = 300) -> str:
    token = secrets.token_urlsafe(18)
    conn.execute("INSERT INTO approval(token_hash,group_id,created_ts,expires_ts,payload_json)"
                 " VALUES(?,?,?,?,?)",
                 (_sha(token), group_id, now(), now() + ttl_sec,
                  json.dumps(payload, ensure_ascii=False)))
    conn.commit()
    return token


def redeem_approval(conn, token: str) -> tuple[dict | None, str]:
    """Гасит токен. Второй раз тот же токен не сработает — защита от двойного клика."""
    row = conn.execute("SELECT * FROM approval WHERE token_hash=?", (_sha(token),)).fetchone()
    if not row:
        return None, "подтверждение не найдено"
    if row["used_ts"]:
        return None, "это подтверждение уже использовано"
    if now() > row["expires_ts"]:
        return None, "подтверждение просрочено, пересчитай заново"
    cur = conn.execute("UPDATE approval SET used_ts=? WHERE token_hash=? AND used_ts=0",
                       (now(), _sha(token)))
    conn.commit()
    if cur.rowcount != 1:
        return None, "подтверждение уже погашено параллельно"
    return json.loads(row["payload_json"]), ""


def issue_action_approval(conn, action: str, payload: dict, ttl_sec: int = 90) -> str:
    """Выдаёт короткоживущий одноразовый токен для денежного действия.

    Открытие сделки использует ``approval`` выше. Эта отдельная таблица не даёт
    случайно подменить токен открытия токеном закрытия/переноса стопа.
    """
    token = secrets.token_urlsafe(18)
    conn.execute(
        "INSERT INTO action_approval(token_hash,action,created_ts,expires_ts,payload_json)"
        " VALUES(?,?,?,?,?)",
        (_sha(token), action, now(), now() + max(1, int(ttl_sec)),
         json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()
    return token


def redeem_action_approval(conn, token: str) -> tuple[str | None, dict | None, str]:
    """Атомарно гасит токен действия; повтор и просрочка всегда fail-closed."""
    token_hash = _sha(token)
    row = conn.execute(
        "SELECT * FROM action_approval WHERE token_hash=?", (token_hash,)
    ).fetchone()
    if not row:
        return None, None, "подтверждение действия не найдено"
    if row["used_ts"]:
        return None, None, "это подтверждение уже использовано"
    if now() > row["expires_ts"]:
        return None, None, "подтверждение просрочено, обнови позиции и повтори"
    cur = conn.execute(
        "UPDATE action_approval SET used_ts=? WHERE token_hash=? AND used_ts=0",
        (now(), token_hash),
    )
    conn.commit()
    if cur.rowcount != 1:
        return None, None, "подтверждение уже погашено параллельно"
    return str(row["action"]), json.loads(row["payload_json"]), ""


def record_execution(conn, group_id: int, action: str, client_id: str,
                     request: dict, response: Any, ok: bool,
                     ticket: int | None, error: str = "") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO execution(ts,group_id,action,client_id,request_json,"
        "response_json,ok,ticket,error) VALUES(?,?,?,?,?,?,?,?,?)",
        (now(), group_id, action, client_id,
         json.dumps(request, ensure_ascii=False),
         json.dumps(response, ensure_ascii=False, default=str),
         int(ok), ticket, error))
    conn.commit()


def begin_execution(conn, group_id: int | None, action: str, client_id: str,
                    request: dict) -> tuple[bool, str]:
    """До вызова брокера резервирует idempotency key.

    Если процесс упал после отправки, запись остаётся pending и повторная
    отправка блокируется до ручной сверки с терминалом.
    """
    try:
        conn.execute(
            "INSERT INTO execution(ts,group_id,action,client_id,request_json,response_json,ok,error)"
            " VALUES(?,?,?,?,?,?,0,?)",
            (now(), group_id, action, client_id, json.dumps(request, ensure_ascii=False),
             "{}", "pending_broker_reconciliation"),
        )
        conn.commit()
        return True, ""
    except sqlite3.IntegrityError:
        row = conn.execute(
            "SELECT ok,error FROM execution WHERE client_id=? AND action=?",
            (client_id, action),
        ).fetchone()
        if row and row["ok"]:
            return False, "действие уже исполнено"
        return False, "предыдущее исполнение имеет неизвестный результат; сначала сверь терминал"


def finish_execution(conn, client_id: str, action: str, response: Any, ok: bool,
                     ticket: int | None, error: str = "") -> None:
    conn.execute(
        "UPDATE execution SET response_json=?,ok=?,ticket=?,error=?"
        " WHERE client_id=? AND action=?",
        (json.dumps(response, ensure_ascii=False, default=str), int(ok), ticket,
         error, client_id, action),
    )
    conn.commit()


def already_executed(conn, client_id: str, action: str) -> bool:
    return conn.execute("SELECT 1 FROM execution WHERE client_id=? AND action=? AND ok=1",
                        (client_id, action)).fetchone() is not None


# ── Telegram replay ledger ──────────────────────────────────────────────
def claim_telegram_update(conn, update_id: int) -> bool:
    """Atomically claim an update before any parsing or money action.

    A crash after this point remains fail-closed: Telegram may redeliver the
    update, but it cannot produce a second approval or execution.
    """
    try:
        conn.execute(
            "INSERT INTO telegram_update(update_id,claimed_ts) VALUES(?,?)",
            (int(update_id), now()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def finish_telegram_update(conn, update_id: int, status: str) -> None:
    conn.execute(
        "UPDATE telegram_update SET finished_ts=?,status=? WHERE update_id=?",
        (now(), str(status)[:32], int(update_id)),
    )
    conn.commit()


def last_telegram_update_id(conn) -> int:
    row = conn.execute("SELECT MAX(update_id) AS update_id FROM telegram_update").fetchone()
    return int(row["update_id"] or 0)
