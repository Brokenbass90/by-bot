# -*- coding: utf-8 -*-
"""Цепочка: текст → разбор → привязка → риск → карточка превью.

Здесь НЕТ отправки ордера. Эта функция физически не может открыть позицию —
она только готовит предложение и одноразовый токен подтверждения.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Any

import config
import store
from parser_v2 import parse, split_signals, classify
from sizing import calculate_lot, quotes_from_symbols


def content_hash(text: str) -> str:
    norm = " ".join(text.split()).lower()
    return hashlib.sha256(norm.encode()).hexdigest()


@dataclass
class Card:
    """То, что видит человек перед тем, как нажать кнопку."""
    kind: str
    title: str = ""
    symbol: str | None = None
    side: str | None = None
    entry_min: float | None = None
    entry_max: float | None = None
    entry_used: float | None = None
    entry_zone_edge: float | None = None
    drift_r: float | None = None
    rr: float | None = None
    stop_loss: float | None = None
    take_profits: list = field(default_factory=list)
    chosen_tp: float | None = None
    lot: float | None = None
    risk_cash: float | None = None
    risk_pct: float | None = None
    loss_per_lot: float | None = None
    currency: str = ""
    market_bid: float | None = None
    market_ask: float | None = None
    spread_points: float | None = None
    can_execute: bool = False
    blockers: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    group_id: int | None = None
    token: str | None = None
    raw: str = ""
    engine: str = "rules"

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def _worst_entry(side: str, lo: float | None, hi: float | None, spec: dict) -> float | None:
    """Консервативный край зоны: для BUY верхний, для SELL нижний.
    Если зоны нет — текущая рыночная цена."""
    if lo is not None and hi is not None:
        return hi if side == "BUY" else lo
    return float(spec.get("ask") or 0) if side == "BUY" else float(spec.get("bid") or 0)


def _pick_tp(tps: list, n: int) -> float | None:
    if not tps:
        return None
    idx = max(1, min(int(n), len(tps))) - 1
    return float(tps[idx])


def build_cards(text: str, mcp, conn, use_llm: bool = True) -> list[Card]:
    """Разбирает вставленное сообщение и возвращает карточки для показа."""
    account = mcp.account()
    terminal = mcp.terminal()
    syms = mcp.symbols()
    specs = {s["symbol"]: s for s in syms}
    quotes = quotes_from_symbols(syms)
    open_pos = mcp.positions()

    # общие для всех карточек запреты
    global_blockers: list[str] = []
    if not terminal.get("server_connected"):
        global_blockers.append("терминал не подключён к серверу брокера")
    if not terminal.get("mcp_trade_allowed"):
        global_blockers.append("в настройках MT5 запрещена торговля через MCP")
    if account.get("server") not in config.ALLOWED_SERVERS and not config.ALLOW_LIVE:
        global_blockers.append(f"сервер {account.get('server')} не разрешён (ALLOW_LIVE=False)")
    if account.get("read_only"):
        global_blockers.append("счёт только для чтения")
    if len(open_pos) >= config.MAX_POSITIONS:
        global_blockers.append(f"уже открыто {len(open_pos)} позиций из {config.MAX_POSITIONS}")

    cards: list[Card] = []
    for block in split_signals(text):
        if not block.strip():
            continue
        p = parse(block)
        engine = "rules"

        # правила не справились — зовём модель, но только тогда
        if use_llm and (p.kind == "UNKNOWN" or (p.kind == "SIGNAL" and p.errors)):
            try:
                from llm import parse_with_llm
                got, note = parse_with_llm(block)
                if got:
                    engine = f"llm:{note}"
                    for k in ("symbol", "side", "entry_min", "entry_max", "stop_loss"):
                        if getattr(p, k, None) is None and got.get(k) is not None:
                            setattr(p, k, got[k])
                    if not p.take_profits and got.get("take_profits"):
                        p.take_profits = got["take_profits"]
                    if got.get("action") in ("MOVE_SL", "CLOSE_PARTIAL", "CLOSE_ALL"):
                        p.kind = got["action"]
            except Exception as e:
                engine = f"llm недоступен: {e}"

        card = Card(kind=p.kind, raw=block.strip(), engine=engine,
                    currency=account.get("currency", ""))

        # ── не сигнал ────────────────────────────────────────────────────
        if p.kind == "PLAIN_TEXT":
            card.kind = "PLAIN_TEXT"
            card.title = "Это обычный текст, а не сигнал"
            card.warnings.append("Поболтать с ботом тут пока нельзя — окно принимает "
                                 "только сообщения канала. Чат будет отдельно.")
            cards.append(card)
            continue

        if p.kind != "SIGNAL":
            card.symbol = p.symbol
            titles = {"NOISE": "Шум — не сигнал", "MOVE_SL_BE": "Просят перенести стоп в безубыток",
                      "MOVE_SL": "Просят перенести стоп",
                      "RESULT_TP": "Отчёт канала: взята цель", "RESULT_SL": "Отчёт канала: стоп",
                      "CLOSE_PARTIAL": "Просят закрыть часть", "CLOSE_ALL": "Просят закрыть всё",
                      "UNKNOWN": "Не распознано — проверь текст",
                      "PLAIN_TEXT": "Это обычный текст, а не сигнал"}
            card.title = titles.get(p.kind, p.kind)
            if p.kind in ("MOVE_SL_BE", "MOVE_SL", "CLOSE_PARTIAL", "CLOSE_ALL"):
                groups = store.open_groups(conn, p.symbol)
                if not groups and p.symbol is None:
                    groups = store.open_groups(conn)
                if len(groups) == 1:
                    card.group_id = groups[0]["id"]
                    card.warnings.append(f"привязал к сделке #{groups[0]['id']} "
                                         f"({groups[0]['symbol']} {groups[0]['side']})")
                elif len(groups) > 1:
                    card.blockers.append("подходит несколько открытых сделок — выбери вручную")
                else:
                    card.blockers.append("нет открытых сделок, к которым это отнести")
            cards.append(card)
            continue

        # ── сигнал ───────────────────────────────────────────────────────
        card.title = f"{p.symbol} {p.side}"
        card.symbol, card.side = p.symbol, p.side
        card.entry_min, card.entry_max = p.entry_min, p.entry_max
        card.stop_loss, card.take_profits = p.stop_loss, p.take_profits
        card.blockers.extend(p.errors)
        card.blockers.extend(global_blockers)

        if p.stop_loss is None:
            card.blockers.append("сигнал без стопа — торговля запрещена")

        spec = specs.get(p.symbol or "")
        if spec is None:
            card.blockers.append(f"символа {p.symbol} нет в Обзоре рынка терминала")
            cards.append(card)
            continue

        card.market_bid = float(spec.get("bid") or 0)
        card.market_ask = float(spec.get("ask") or 0)
        pt = float(spec.get("point") or 0) or 1
        card.spread_points = round((card.market_ask - card.market_bid) / pt, 1)

        card.chosen_tp = _pick_tp(p.take_profits, config.DEFAULT_TP)

        # Ордер уходит по рынку, значит считать надо по цене исполнения,
        # а не по цене из сигнала. Зона входа остаётся справочной.
        entry = card.market_ask if p.side == "BUY" else card.market_bid
        card.entry_used = entry
        card.entry_zone_edge = _worst_entry(p.side, p.entry_min, p.entry_max, spec)

        if entry and p.stop_loss:
            # 1. Цена уже за стопом — сигнал мёртв.
            dead = (entry <= p.stop_loss) if p.side == "BUY" else (entry >= p.stop_loss)
            if dead:
                card.blockers.append(
                    f"цена {entry} уже за стопом {p.stop_loss} — сигнал протух, "
                    f"стоп оказался бы с другой стороны от входа")

            # 2. Цель уже пройдена.
            if card.chosen_tp and not dead:
                passed = (entry >= card.chosen_tp) if p.side == "BUY" else (entry <= card.chosen_tp)
                if passed:
                    card.blockers.append(
                        f"цена {entry} уже прошла цель {card.chosen_tp} — заходить некуда")

            risk_dist = abs(entry - p.stop_loss)

            # 2b. Стоп не должен схлопнуться. Если рынок подошёл вплотную к стопу,
            # расстояние до него становится мизерным, объём взлетает, а позицию
            # сносит шумом. Меряем от риска, который заложил канал.
            signal_risk = (abs(card.entry_zone_edge - p.stop_loss)
                           if card.entry_zone_edge else 0.0)
            pt_ = float(spec.get("point") or 0) or 1
            stop_pts = risk_dist / pt_
            spread_pts = max(card.spread_points or 0, 0.0)
            broker_min = float(spec.get("trade_stops_level") or 0)
            need_pts = max(broker_min, config.MIN_STOP_SPREADS * spread_pts)
            if stop_pts < need_pts:
                card.blockers.append(
                    f"стоп всего в {stop_pts:.0f} п. от цены при спреде {spread_pts:.0f} п. — "
                    f"его снесёт шумом. Нужно минимум {need_pts:.0f} п.")
            if signal_risk > 0 and risk_dist < signal_risk * config.MIN_RISK_KEEP:
                card.blockers.append(
                    f"рынок подошёл к стопу: в сигнале до стопа было "
                    f"{signal_risk/pt_:.0f} п., сейчас осталось {stop_pts:.0f} п. "
                    f"({risk_dist/signal_risk*100:.0f}% от заложенного) — сделка уже не та")

            # 3. Насколько рынок убежал от зоны входа. Считаем в долях РИСКА
            # СИГНАЛА: текущий риск может быть почти нулевым, и деление на него
            # даёт бессмысленные десятки R.
            base = signal_risk if signal_risk > 0 else risk_dist
            if card.entry_zone_edge and base > 0:
                worse = ((entry - card.entry_zone_edge) if p.side == "BUY"
                         else (card.entry_zone_edge - entry))
                card.drift_r = round(worse / base, 2)
                if card.drift_r < -config.MAX_ENTRY_DRIFT_R * 2:
                    card.blockers.append(
                        f"рынок ушёл от зоны на {abs(card.drift_r)}R в нашу сторону — "
                        f"движение уже случилось без нас, входить не в ту сделку")
                if card.drift_r > config.MAX_ENTRY_DRIFT_R:
                    card.blockers.append(
                        f"рынок ушёл от зоны входа на {card.drift_r}R "
                        f"(допустимо {config.MAX_ENTRY_DRIFT_R}R) — входить поздно")
                elif card.drift_r > config.MAX_ENTRY_DRIFT_R / 2:
                    card.warnings.append(f"рынок уже на {card.drift_r}R хуже зоны входа")

            # 4. Что реально остаётся взять по текущей цене.
            rr_base = signal_risk if signal_risk > 0 else risk_dist
            if card.chosen_tp and rr_base > 0:
                card.rr = round(abs(card.chosen_tp - entry) / rr_base, 2)
                if card.rr < config.MIN_RR and not card.blockers:
                    card.warnings.append(
                        f"по текущей цене остаётся всего {card.rr}R — "
                        f"нужен винрейт {100/(1+card.rr):.0f}%, чтобы не терять")

        if entry and p.stop_loss:
            d = calculate_lot(spec=spec, entry=entry, stop=p.stop_loss,
                              equity=float(account.get("equity") or 0),
                              risk_pct=config.RISK_PCT,
                              account_ccy=account.get("currency", "USD"),
                              quotes=quotes, max_lot=config.MAX_LOT,
                              max_risk_pct=config.MAX_RISK_PCT)
            card.lot, card.risk_cash = d.lot, d.actual_risk
            card.risk_pct, card.loss_per_lot = d.actual_risk_pct, d.loss_per_lot
            if not d.accepted:
                card.blockers.append(f"{d.reason}. {d.note}".strip())
            elif d.note:
                card.warnings.append(d.note)

        # встречная позиция по тому же символу — предупреждаем, не перекрываем
        opposite = [x for x in open_pos if x.get("symbol") == p.symbol
                    and str(x.get("type", "")).lower() != str(p.side or "").lower()]
        if opposite:
            card.warnings.append(f"по {p.symbol} уже открыта встречная позиция — "
                                 f"проверь, не было ли команды на отмену")

        card.can_execute = not card.blockers
        cards.append(card)

    return cards


def persist_and_arm(cards: list[Card], text: str, mcp, conn, source: str = "paste") -> list[Card]:
    """Сохраняет сообщение и выдаёт одноразовые токены исполнимым карточкам."""
    account = mcp.account()
    h = content_hash(text)
    kinds = ",".join(sorted({c.kind for c in cards}))
    msg_id, is_new = store.save_message(
        conn, text, h, kinds, [c.as_dict() for c in cards], source=source,
        used_llm=any(c.engine.startswith("llm") for c in cards))
    if not is_new:
        for c in cards:
            c.can_execute = False
            c.blockers.append("это сообщение уже обрабатывалось (защита от дубля)")
        return cards

    for c in cards:
        if c.kind != "SIGNAL" or not c.can_execute:
            continue
        gid = store.create_group(conn, msg_id, {
            "symbol": c.symbol, "side": c.side, "entry_min": c.entry_min,
            "entry_max": c.entry_max, "stop_loss": c.stop_loss,
            "take_profits": c.take_profits, "chosen_tp": c.chosen_tp,
        }, account, c.market_bid)
        c.group_id = gid
        try:
            import journal
            journal.remember_planned_risk(conn, gid, c.risk_cash or 0.0)
        except Exception:
            pass
        # Ключ идемпотентности рождается ВМЕСТЕ с подтверждением, до отправки.
        # Так повторный клик или ретрай сети не смогут открыть вторую позицию.
        client_id = f"sc-{gid}-{secrets.token_hex(4)}"
        c.token = store.issue_approval(conn, gid, {
            "client_id": client_id,
            "symbol": c.symbol, "side": c.side, "lot": c.lot,
            "sl": c.stop_loss, "tp": c.chosen_tp, "group_id": gid,
            "risk_cash": c.risk_cash, "equity_ccy": c.currency,
        })
        store.log(conn, gid, "preview", c.as_dict())
    return cards
