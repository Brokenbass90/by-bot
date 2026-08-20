# -*- coding: utf-8 -*-
"""Журнал сделок: следит за позициями, ловит момент закрытия, считает итог.

Зачем отдельный модуль: терминал показывает только ОТКРЫТЫЕ позиции. Как только
стоп или цель срабатывают, позиция исчезает, и вместе с ней исчез бы результат.
Поэтому мы на каждом опросе снимаем слепок, а когда позиция пропала — сверяем
с историей терминала и записываем исход навсегда.

Отсюда же берутся цифры, ради которых всё затевалось: винрейт, средний R,
ожидание, profit factor и разница между обещанием канала и фактом.
"""
from __future__ import annotations

import json
import time
from typing import Any

import store

SCHEMA = """
CREATE TABLE IF NOT EXISTS position_snapshot (
    ticket        INTEGER PRIMARY KEY,
    group_id      INTEGER,
    symbol        TEXT,
    side          TEXT,
    volume        REAL,
    price_open    REAL,
    price_current REAL,
    sl            REAL,
    tp            REAL,
    profit        REAL,
    swap          REAL,
    first_seen    INTEGER,
    last_seen     INTEGER,
    closed        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS trade_result (
    ticket        INTEGER PRIMARY KEY,
    group_id      INTEGER,
    symbol        TEXT,
    side          TEXT,
    volume        REAL,
    price_open    REAL,
    price_exit    REAL,
    sl            REAL,
    tp            REAL,
    profit        REAL,
    swap          REAL,
    r_multiple    REAL,
    planned_risk  REAL,
    opened_ts     INTEGER,
    closed_ts     INTEGER,
    duration_sec  INTEGER,
    outcome       TEXT,
    source        TEXT
);
CREATE INDEX IF NOT EXISTS idx_result_closed ON trade_result(closed_ts);
"""


def ensure_schema(conn) -> None:
    conn.executescript(SCHEMA)
    # planned_risk появился позже — добавляем мягко, чтобы старая база не сломалась
    cols = {r[1] for r in conn.execute("PRAGMA table_info(signal_group)")}
    if "planned_risk" not in cols:
        conn.execute("ALTER TABLE signal_group ADD COLUMN planned_risk REAL")
    conn.commit()


def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def remember_planned_risk(conn, group_id: int, risk_cash: float) -> None:
    """Запоминаем, сколько денег мы СОБИРАЛИСЬ рискнуть. Без этого R не посчитать."""
    ensure_schema(conn)
    conn.execute("UPDATE signal_group SET planned_risk=? WHERE id=?",
                 (_f(risk_cash), group_id))
    conn.commit()


def _planned_risk(conn, group_id: int | None, snap: dict) -> float:
    """Риск в деньгах: сначала из плана, иначе прикидываем от стопа."""
    if group_id:
        row = conn.execute("SELECT planned_risk FROM signal_group WHERE id=?",
                           (group_id,)).fetchone()
        if row and row["planned_risk"]:
            return _f(row["planned_risk"])
    # запасной путь: убыток на пункт выводим из текущей прибыли позиции
    entry, cur, sl = _f(snap.get("price_open")), _f(snap.get("price_current")), _f(snap.get("sl"))
    moved = abs(cur - entry)
    if moved > 0 and sl > 0:
        per_price = abs(_f(snap.get("profit"))) / moved
        return per_price * abs(entry - sl)
    return 0.0


def snapshot_positions(conn, positions: list[dict]) -> None:
    """Слепок живых позиций. Вызывается на каждом опросе."""
    ensure_schema(conn)
    ts = store.now()
    for p in positions:
        t = p.get("ticket")
        if not t:
            continue
        conn.execute("""
            INSERT INTO position_snapshot
              (ticket,group_id,symbol,side,volume,price_open,price_current,sl,tp,
               profit,swap,first_seen,last_seen,closed)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0)
            ON CONFLICT(ticket) DO UPDATE SET
              price_current=excluded.price_current, sl=excluded.sl, tp=excluded.tp,
              profit=excluded.profit, swap=excluded.swap, last_seen=excluded.last_seen,
              group_id=COALESCE(position_snapshot.group_id, excluded.group_id),
              closed=0
        """, (int(t), p.get("group_id"), p.get("symbol"), p.get("type"),
              _f(p.get("volume")), _f(p.get("price_open")), _f(p.get("price_current")),
              _f(p.get("sl")), _f(p.get("tp")), _f(p.get("profit")), _f(p.get("swap")),
              ts, ts))
    conn.commit()


def _history_lookup(mcp, symbol: str, ticket: int, since_ts: int) -> dict | None:
    """Спрашиваем терминал о закрытой позиции. Схема истории может отличаться,
    поэтому ищем аккуратно и молча сдаёмся, если не нашли."""
    try:
        from datetime import datetime, timedelta, timezone
        frm = datetime.fromtimestamp(max(0, since_ts - 3600), tz=timezone.utc)
        to = datetime.now(timezone.utc) + timedelta(hours=1)
        got = mcp.call("get_trading_history_positions",
                       datetime_from=frm.strftime("%Y-%m-%dT%H:%M:%S"),
                       datetime_to=to.strftime("%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return None
    rows: list = []
    if isinstance(got, dict):
        for key in ("positions", "deals", "history", "rows", "items"):
            if isinstance(got.get(key), list):
                rows = got[key]
                break
    elif isinstance(got, list):
        rows = got
    for r in rows:
        if not isinstance(r, dict):
            continue
        for k in ("ticket", "position_ticket", "position", "position_id"):
            if str(r.get(k, "")) == str(ticket):
                return r
    return None


def reconcile(conn, mcp, positions: list[dict]) -> list[dict]:
    """Сравнить живые позиции со слепками. Пропавшие — закрыть и записать итог."""
    ensure_schema(conn)
    snapshot_positions(conn, positions)
    live = {int(p["ticket"]) for p in positions if p.get("ticket")}
    closed_now = []

    for row in conn.execute("SELECT * FROM position_snapshot WHERE closed=0"):
        ticket = int(row["ticket"])
        if ticket in live:
            continue
        snap = dict(row)
        hist = _history_lookup(mcp, snap.get("symbol") or "", ticket,
                               int(snap.get("first_seen") or store.now()))

        # Пустой список позиций может быть кратковременным сбоем транспорта.
        # Без подтверждения из broker history не имеем права объявлять сделку
        # закрытой и превращать последний unrealized PnL в итоговый результат.
        if hist is None:
            continue

        profit = _f(hist.get("profit"))
        swap = _f(hist.get("swap"))
        exit_price = _f(hist.get("price_close") or hist.get("price_current"))
        if exit_price <= 0:
            continue
        source = "история терминала"

        risk = _planned_risk(conn, snap.get("group_id"), snap)
        net_profit = profit + swap
        r_mult = round(net_profit / risk, 3) if risk > 0 else None

        sl, tp = _f(snap.get("sl")), _f(snap.get("tp"))
        outcome = "прибыль" if net_profit > 0 else ("убыток" if net_profit < 0 else "в ноль")
        if sl and abs(exit_price - sl) <= abs(exit_price) * 1e-4:
            outcome = "стоп"
        elif tp and abs(exit_price - tp) <= abs(exit_price) * 1e-4:
            outcome = "цель"

        opened = int(snap.get("first_seen") or store.now())
        closed_ts = store.now()
        conn.execute("""INSERT OR REPLACE INTO trade_result
            (ticket,group_id,symbol,side,volume,price_open,price_exit,sl,tp,profit,swap,
             r_multiple,planned_risk,opened_ts,closed_ts,duration_sec,outcome,source)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ticket, snap.get("group_id"), snap.get("symbol"), snap.get("side"),
             _f(snap.get("volume")), _f(snap.get("price_open")), exit_price, sl, tp,
             profit, swap, r_mult, risk, opened, closed_ts, closed_ts - opened,
             outcome, source))
        conn.execute("UPDATE position_snapshot SET closed=1 WHERE ticket=?", (ticket,))
        if snap.get("group_id"):
            store.set_status(conn, int(snap["group_id"]), "CLOSED",
                             f"{outcome}, {profit:+.2f}")
        store.log(conn, snap.get("group_id"), "trade_closed",
                  {"ticket": ticket, "profit": profit, "r": r_mult,
                   "outcome": outcome, "source": source})
        closed_now.append({"ticket": ticket, "symbol": snap.get("symbol"),
                           "profit": profit, "r": r_mult, "outcome": outcome})
    conn.commit()
    return closed_now


def results(conn, limit: int = 100) -> list[dict]:
    ensure_schema(conn)
    return [dict(r) for r in conn.execute(
        "SELECT * FROM trade_result ORDER BY closed_ts DESC LIMIT ?", (limit,))]


def metrics(conn) -> dict:
    """Честные числа по закрытым сделкам. Пустая статистика — это тоже ответ."""
    ensure_schema(conn)
    rows = [dict(r) for r in conn.execute("SELECT * FROM trade_result ORDER BY closed_ts")]
    n = len(rows)
    if not n:
        return {"trades": 0, "note": "закрытых сделок пока нет"}

    profits = [_f(r["profit"]) + _f(r["swap"]) for r in rows]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    rs = [_f(r["r_multiple"]) for r in rows if r["r_multiple"] is not None]

    gross_win, gross_loss = sum(wins), -sum(losses)
    equity, peak, max_dd = 0.0, 0.0, 0.0
    for p in profits:
        equity += p
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    avg_win = gross_win / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0
    win_rate = len(wins) / n

    return {
        "trades": n,
        "wins": len(wins), "losses": len(losses),
        "win_rate": round(win_rate * 100, 1),
        "total_profit": round(sum(profits), 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "expectancy": round(win_rate * avg_win - (1 - win_rate) * avg_loss, 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        "max_drawdown": round(max_dd, 2),
        "avg_r": round(sum(rs) / len(rs), 3) if rs else None,
        "total_r": round(sum(rs), 2) if rs else None,
        # различимость: при разбросе ~1R среднее различимо на уровне 1.96/sqrt(n)
        "r_error_band": round(1.96 / (len(rs) ** 0.5), 3) if rs else None,
        "by_symbol": _group(rows, "symbol"),
        "by_side": _group(rows, "side"),
    }


def _group(rows: list[dict], field: str) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        buckets.setdefault(str(r.get(field) or "?"), []).append(r)
    out = []
    for key, items in sorted(buckets.items()):
        p = [_f(x["profit"]) + _f(x["swap"]) for x in items]
        w = len([x for x in p if x > 0])
        out.append({"key": key, "trades": len(items), "wins": w,
                    "win_rate": round(w / len(items) * 100, 1),
                    "profit": round(sum(p), 2)})
    return out
