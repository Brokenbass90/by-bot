# -*- coding: utf-8 -*-
"""Калибровка стоимости пункта опытным путём.

Зачем: у XAUUSD на этом сервере tick_value и contract_size противоречат друг
другу в 10 раз. Вместо угадывания открываем минимальный лот на демо, смотрим,
какой убыток показал САМ терминал сразу после открытия (это ровно спред),
и вычисляем настоящую стоимость пункта. Потом закрываем.

Результат пишется в symbol_calibration.json и дальше используется расчётом лота.

Запуск:  python3 calibrate.py XAUUSD
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import config
from mt5_mcp import MT5MCP, MT5Error

CALIB_PATH = Path(__file__).parent / "symbol_calibration.json"


def main(symbol: str = "XAUUSD") -> int:
    m = MT5MCP(config.MT5_URL, config.MT5_TOKEN)
    m.connect()
    acc, term = m.account(), m.terminal()

    # ── жёсткие предохранители: только демо, только разрешённый сервер ──
    if acc.get("type") != "demo" or acc.get("server") not in config.ALLOWED_SERVERS:
        print(f"ОТКАЗ: калибровка только на демо. Сейчас {acc.get('server')} / {acc.get('type')}")
        return 1
    if not term.get("server_connected"):
        print("ОТКАЗ: нет связи с брокером")
        return 1

    spec = m.symbol(symbol)
    bid, ask = float(spec["bid"]), float(spec["ask"])
    point = float(spec.get("point") or 0.01)
    vol = float(spec.get("volume_min") or 0.01)
    if bid <= 0 or ask <= 0:
        print(f"ОТКАЗ: нет котировок по {symbol}")
        return 1

    spread_pts = (ask - bid) / point
    print(f"Счёт {acc['login']} · {acc['server']} · {acc['type']} · {acc['currency']}")
    print(f"{symbol}: bid {bid} ask {ask} · спред {spread_pts:.1f} п. · point {point}")
    print(f"contract_size {spec.get('contract_size')} · tick_size {spec.get('tick_size')} "
          f"· tick_value {spec.get('tick_value')}")
    print(f"\nОткрою {vol} лота, замерю и сразу закрою. Убыток будет около размера спреда.")
    if input("Продолжить? (да/нет): ").strip().lower() not in ("да", "y", "yes", "д"):
        print("отменено")
        return 0

    # широкий стоп, чтобы не нарушать правило «без стопа не торгуем»
    wide_sl = round(bid * 0.95, spec.get("digits", 2))
    req = {"symbol": symbol, "type": "buy", "volume": vol, "sl": wide_sl,
           "comment": "sigcopy-calibration"}
    print(f"\nОтправляю: {req}")
    try:
        resp = m.call("trade_send_market_order", **req)
    except MT5Error as e:
        print("терминал отказал:", e)
        return 1
    print("ответ терминала:", json.dumps(resp, ensure_ascii=False)[:400])

    time.sleep(1.5)
    positions = [p for p in m.positions() if p.get("symbol") == symbol]
    if not positions:
        print("позиция не найдена — возможно, не открылась")
        return 1
    pos = positions[0]
    print("\n=== ПОЛЯ ПОЗИЦИИ (нужны для дальнейшей работы) ===")
    for k, v in pos.items():
        print(f"  {k:<22} = {v}")

    profit = float(pos.get("profit") or 0)
    price_open = float(pos.get("price_open") or pos.get("open_price") or 0)
    price_cur = float(pos.get("price_current") or pos.get("current_price") or bid)
    moved_pts = (price_cur - price_open) / point

    result = {"symbol": symbol, "volume": vol, "profit_reported": profit,
              "price_open": price_open, "price_current": price_cur,
              "moved_points": round(moved_pts, 2), "account_currency": acc["currency"]}

    if abs(moved_pts) > 0.01 and vol > 0:
        per_point_per_lot = abs(profit) / abs(moved_pts) / vol
        result["value_per_point_per_lot"] = round(per_point_per_lot, 6)
        by_contract = point * float(spec.get("contract_size") or 0)
        print(f"\n=== ИТОГ ===")
        print(f"  терминал показал убыток {profit} {acc['currency']} при движении "
              f"{moved_pts:.1f} п. на {vol} лота")
        print(f"  → стоимость пункта на 1 лот = {per_point_per_lot:.4f} {acc['currency']}")
        print(f"  для сравнения, по contract_size = {by_contract:.4f} (в валюте прибыли)")
    else:
        print("\nЦена не сдвинулась — замер не получился, попробуй ещё раз.")

    # закрываем
    ticket = pos.get("ticket") or pos.get("position_ticket") or pos.get("position")
    if ticket:
        print(f"\nЗакрываю позицию {ticket}...")
        try:
            close = m.call("trade_close_single_position", symbol=symbol,
                           position_ticket=int(ticket))
            print("закрыто:", json.dumps(close, ensure_ascii=False)[:300])
            result["closed"] = True
        except MT5Error as e:
            print("НЕ ЗАКРЫЛОСЬ, закрой руками в терминале:", e)
            result["closed"] = False

    prev = {}
    if CALIB_PATH.exists():
        prev = json.loads(CALIB_PATH.read_text(encoding="utf-8"))
    prev[symbol] = result
    CALIB_PATH.write_text(json.dumps(prev, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nЗаписал в {CALIB_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"))
