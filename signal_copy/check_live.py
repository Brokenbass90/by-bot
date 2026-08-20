# -*- coding: utf-8 -*-
"""Живая проверка связи с MetaTrader 5. Ничего не открывает и не меняет.

Запуск:  python3 check_live.py
"""
import sys
import config
from mt5_mcp import MT5MCP, MT5Error
from sizing import calculate_lot, quotes_from_symbols

WANT = ["XAUUSD", "EURUSD", "AUDUSD", "GBPUSD", "USDCHF"]
# GOLD намеренно нет: на этом сервере это ДРУГОЙ инструмент
# (contract_size=1, мин.лот=1), а не золото. Алиасы не добавляем.


def main() -> int:
    m = MT5MCP(config.MT5_URL, config.MT5_TOKEN)
    try:
        info = m.connect()
    except MT5Error as e:
        print("НЕ ПОДКЛЮЧИЛСЯ:", e)
        print("Проверь: MT5 запущен, Настройки → MCP → 'Включить внутренний сервер', ключ совпадает.")
        return 1
    print("Связь есть:", info.get("serverInfo", {}).get("name"))

    acc = m.account()
    term = m.terminal()
    print(f"\nСчёт   {acc['login']} · {acc['server']} · {acc['type']} · {acc['margin_mode']}")
    print(f"Деньги {acc['equity']:.2f} {acc['currency']} (свободно {acc['margin_free']:.2f})")
    print(f"Терминал build {term['build']} · связь {term['server_connected']} · "
          f"торговля через MCP {term['mcp_trade_allowed']}")

    # предохранители
    if acc["server"] not in config.ALLOWED_SERVERS and not config.ALLOW_LIVE:
        print(f"\nСТОП: сервер {acc['server']} не в списке разрешённых. Ордера запрещены.")
    if not term["server_connected"]:
        print("\nСТОП: терминал не подключён к серверу брокера.")
        return 1

    # добираем нужные символы в Обзор рынка
    have = {s["symbol"] for s in m.symbols()}
    for name in WANT:
        if name not in have:
            try:
                m.add_symbol(name)
                print(f"  добавил в Обзор рынка: {name}")
            except MT5Error:
                pass

    syms = m.symbols()
    quotes = quotes_from_symbols(syms)
    specs = {s["symbol"]: s for s in syms}
    print(f"\nСимволов в Обзоре рынка: {len(syms)}")
    print(f"{'символ':<10}{'bid':>12}{'ask':>12}{'спред п.':>10}{'контракт':>11}{'мин.лот':>9}")
    for s in syms:
        if s["symbol"] not in WANT:
            continue
        pt = float(s.get("point") or 0) or 1
        spread = (float(s.get("ask") or 0) - float(s.get("bid") or 0)) / pt
        print(f"{s['symbol']:<10}{s.get('bid',0):>12}{s.get('ask',0):>12}"
              f"{spread:>10.1f}{s.get('contract_size',0):>11}{s.get('volume_min',0):>9}")

    pos = m.positions()
    print(f"\nОткрытых позиций: {len(pos)}")

    # превью лота по живому сигналу канала
    print("\n--- превью: BUY XAU/USD 4395-4398, SL 4377 (худший край входа) ---")
    spec = specs.get("XAUUSD") or specs.get("GOLD")
    if not spec:
        print("XAUUSD в Обзоре рынка нет — добавь вручную и перезапусти.")
        return 0
    d = calculate_lot(spec=spec, entry=4398.0, stop=4377.0,
                      equity=float(acc["equity"]), risk_pct=config.RISK_PCT,
                      account_ccy=acc["currency"], quotes=quotes,
                      max_lot=config.MAX_LOT, max_risk_pct=config.MAX_RISK_PCT)
    if d.accepted:
        print(f"  ЛОТ {d.lot}  ·  риск {d.actual_risk:.2f} {acc['currency']} "
              f"({d.actual_risk_pct:.2f}%)  ·  {d.loss_per_lot:.2f} на лот")
    else:
        print(f"  ОТКАЗ: {d.reason}. {d.note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
