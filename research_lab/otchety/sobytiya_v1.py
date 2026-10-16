#!/usr/bin/env python3
"""sobytiya_v1.py — ReportEvent v1: ОДНА нормализованная схема событий для Telegram и веба всех рукавов (16.10.2026).

Источник истины — неизменяемый журнал исполнения (Codex). Отчёт ничего не пересчитывает сам: деньги (gross/fees/funding/net),
количества и цены берутся из журнала; TAX-A читает те же строки. Падение отчёта никогда не блокирует торговлю.

Типы: ENTRY_FILLED, PROTECTION_BOUND, STOP_MOVED, PARTIAL_FILL, EXIT_FILLED, FAILED_SAFE_FLAT, NO_SEND, ACCOUNTING_FINAL.
Общие поля: schema, type, ts_ms, sleeve, venue, strategy, evidence_id (ID квитанции/журнала), mode (LIVE|PAPER|SHADOW|DEMO).
Позиционные (по типу): symbol, side (long|short), qty, px, notional, stop_px, targets, reason, fees, funding, slippage_bps,
gross_pnl, net_pnl, ccy, legs (для корзин: [{symbol, side, status, qty, fees, protected}]), owner_flat (bool).
"""
TIPY = ("ENTRY_FILLED", "PROTECTION_BOUND", "STOP_MOVED", "PARTIAL_FILL", "EXIT_FILLED", "FAILED_SAFE_FLAT", "NO_SEND", "ACCOUNTING_FINAL")
OBSHCHIE = ("type", "ts_ms", "sleeve", "venue", "strategy", "evidence_id", "mode")
PO_TIPU = {
    "ENTRY_FILLED": ("symbol", "side", "qty", "px", "ccy"),
    "PROTECTION_BOUND": ("symbol", "stop_px"),
    "STOP_MOVED": ("symbol", "stop_px", "stop_px_prev"),
    "PARTIAL_FILL": ("symbol", "side", "qty", "px", "qty_planned"),
    "EXIT_FILLED": ("symbol", "side", "qty", "px", "reason", "ccy"),
    "FAILED_SAFE_FLAT": ("reason", "owner_flat", "legs", "net_pnl", "ccy"),
    "NO_SEND": ("reason",),
    "ACCOUNTING_FINAL": ("gross_pnl", "fees", "funding", "net_pnl", "ccy"),
}
# соответствие событиям, которые уже читает веб-лента (web/activity_feed.read_trade_events)
V_LENTU = {"ENTRY_FILLED": "entry_filled", "EXIT_FILLED": "close", "STOP_MOVED": "order_submitted", "PARTIAL_FILL": "entry_filled"}


class OshibkaSobytiya(ValueError):
    pass


def proverit(e):
    if e.get("type") not in TIPY: raise OshibkaSobytiya(f"type ∉ {TIPY}")
    net = [k for k in OBSHCHIE + PO_TIPU[e["type"]] if e.get(k) is None]
    if net: raise OshibkaSobytiya(f"{e['type']}: нет полей {net}")
    if e["mode"] not in ("LIVE", "PAPER", "SHADOW", "DEMO"): raise OshibkaSobytiya("mode")
    if e.get("side") is not None and e["side"] not in ("long", "short"): raise OshibkaSobytiya("side ∈ long|short")
    if e["type"] == "ACCOUNTING_FINAL" and abs(e["gross_pnl"] - e["fees"] + e["funding"] - e["net_pnl"]) > 1e-6:
        raise OshibkaSobytiya("net ≠ gross − fees + funding (знак funding: + получено, − уплачено)")
    return e


def dlya_lenty(e):
    """Строка в формате web/activity_feed (существующая лента) — новые типы проходят как есть."""
    proverit(e)
    out = dict(event=V_LENTU.get(e["type"], e["type"].lower()), ts=e["ts_ms"], symbol=e.get("symbol") or e["sleeve"],
               side="Buy" if e.get("side") == "long" else "Sell" if e.get("side") == "short" else "",
               strategy=e["strategy"], venue=e["venue"], evidence_id=e["evidence_id"], mode=e["mode"])
    for k_src, k_dst in (("px", "fill_price"), ("stop_px", "sl_price"), ("net_pnl", "pnl")):
        if e.get(k_src) is not None: out[k_dst] = e[k_src]
    if e["type"] == "EXIT_FILLED": out["exit_price"] = e["px"]
    return out


def iz_kity_terminal(d, evidence_id=None, ts_go=None):
    """Адаптер: терминальная квитанция KITY micro (KITY_POST_GO_OWNER_MICRO_TERMINAL_V1) → события. Числа — дословно из квитанции."""
    ev = evidence_id or f"kity_micro:{d['command_id']}"; base = dict(sleeve="KITY", venue="Bybit", strategy="KITY_MICRO_EXEC",
                                                                    evidence_id=ev, mode="LIVE")
    off = {x["symbol"]: x["after_go_ms"] for x in d.get("entry_intent_offsets_ms", [])}
    legs, out = [], []
    for sym, x in d["per_symbol"].items():
        side = "long" if x["side"] == "Buy" else "short"
        q = float(x["entry_quantity"]); prot = float(x["native_stop_full_quantity"]) == q
        legs.append(dict(symbol=sym, side=side, status="FILLED→CLOSED", qty=q, fees=float(x["fees_usdt"]), protected=prot,
                         after_go_ms=off.get(sym)))
    for sym in d.get("not_attempted_legs", []):
        legs.append(dict(symbol=sym, side=None, status="НЕ ОТПРАВЛЕНА", qty=0.0, fees=0.0, protected=None, after_go_ms=None))
    gross, fees, fund, net = (float(d[k]) for k in ("gross_pnl_usdt", "fees_usdt", "funding_usdt", "terminal_net_usdt"))
    tip = "FAILED_SAFE_FLAT" if int(d["filled_legs"]) < int(d["required_legs"]) else "ACCOUNTING_FINAL"
    if tip == "FAILED_SAFE_FLAT":
        out.append(proverit(dict(base, type=tip, ts_ms=int(d["finality_ms"]), reason=d.get("unwind_reason", ""),
                                 defect=d.get("planning_defect"), owner_flat=bool(d.get("broker_flat_proven")), legs=legs,
                                 filled=int(d["filled_legs"]), required=int(d["required_legs"]), gross_pnl=gross, fees=fees,
                                 funding=fund, net_pnl=net, ccy="USDT", go_ms=int(d["go_ms"]),
                                 entry_deadline_ms=int(d["entry_dispatch_deadline_ms"]),
                                 planned_gross=float(d["planned_ten_leg_gross_usdt"]), actual_gross=float(d["actual_entry_gross_usdt"]),
                                 exchange_rejections=int(d.get("exchange_create_rejections", 0)))))
    out.append(proverit(dict(base, type="ACCOUNTING_FINAL", ts_ms=int(d["observation_completed_ms"]), gross_pnl=gross, fees=fees,
                             funding=fund, net_pnl=net, ccy="USDT", legs=legs)))
    return out
