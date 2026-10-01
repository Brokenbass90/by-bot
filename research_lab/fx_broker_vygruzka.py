#!/usr/bin/env python3
"""fx_broker_vygruzka.py — данные брокера для ворот издержек NOCHNOY FX (nochnoy_fx_cost_gate.py).

Через тот же мост MT5, что и tyanem_mt5.py. Сохраняет ТОЛЬКО издержки: спред по часам и спецификацию
символов (своп, размер лота, пункт). Цены не сохраняются — окна исследований не затрагиваются.
Перед запуском в терминале MT5 должен быть открыт счёт того брокера и того типа, на котором будет торговля
(можно демо-счёт того же типа у того же брокера — спреды и свопы у них те же). MetaQuotes-Demo не годится.
Комиссию за лот MT5 в спецификации не отдаёт — передаётся аргументом из условий счёта.
Только чтение, ни одного ордера, логин и токен не печатаются.

    cd signal_copy && ../.venv/bin/python3 ../research_lab/fx_broker_vygruzka.py --komissiya 3.5
"""
import argparse, datetime as dt, json, sys
from pathlib import Path

KOREN = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(KOREN / "signal_copy"))
import config                              # noqa: E402
from mt5_mcp import MT5MCP, MT5Error       # noqa: E402

PARY = ["AUDUSD", "EURUSD", "GBPUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY"]
OUT = KOREN / "research_lab/data/fx_broker"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--komissiya", type=float, required=True,
                                                    help="USD за 1 лот за одну сторону (0 для счёта без комиссии)")
    ap.add_argument("--dney", type=int, default=400)
    a = ap.parse_args(); OUT.mkdir(parents=True, exist_ok=True)
    m = MT5MCP(config.MT5_URL, config.MT5_TOKEN); m.connect()
    acc = m.account()
    server = str(acc.get("server", "")); company = str(acc.get("company", ""))
    print(f"брокер: {company} | сервер: {server} | режим: {acc.get('trade_mode')}")
    if "MetaQuotes" in server or "MetaQuotes" in company:
        sys.exit("это MetaQuotes-Demo — нужен счёт реального брокера (можно его демо того же типа)")
    spec = {"broker": company, "server": server, "vremya": "mt5_eet", "trade_mode": acc.get("trade_mode"),
            "kogda": dt.datetime.utcnow().isoformat(timespec="seconds")}
    do = dt.date.today(); ot = do - dt.timedelta(days=a.dney)
    for s in PARY:
        try:
            sp = m.symbol(s)
        except MT5Error as e:
            print(f"{s}: нет в Обзоре рынка ({e}) — добавь символ (с суффиксом брокера, если он есть)"); continue
        spec[s] = {"point": sp.get("point"), "contract_size": sp.get("trade_contract_size") or sp.get("contract_size"),
                   "swap_long": sp.get("swap_long"), "swap_mode": {1: "points", 2: "money_per_lot"}.get(sp.get("swap_mode"), sp.get("swap_mode")),
                   "swap_3day": sp.get("swap_rollover3days", 3) - 1 if isinstance(sp.get("swap_rollover3days"), int) else 2,
                   "commission_usd_per_lot_side": a.komissiya, "_syroe": sp}
        ts, spr = [], []
        tek = ot
        while tek < do:
            kraj = min(tek + dt.timedelta(days=90), do)
            try:
                r = m.call("get_chart_history", timeout=90.0, symbol=s, period="H1",
                           datetime_from=tek.isoformat(), datetime_to=kraj.isoformat(), limit=100000)
            except MT5Error as e:
                print(f"  {s} {tek}: {str(e)[:100]}"); tek = kraj; continue
            bary = r if isinstance(r, list) else next((r[k] for k in ("candles", "rates", "bars", "history", "data", "items")
                                                         if isinstance(r, dict) and isinstance(r.get(k), list)), [])
            for b in bary:
                t = b.get("time") or b.get("datetime"); v = b.get("spread")
                if t is None or v is None:
                    continue
                if isinstance(t, str):
                    t = int(dt.datetime.fromisoformat(t.replace("Z", "")).replace(tzinfo=dt.timezone.utc).timestamp())
                ts.append(int(t) * 1000 if t < 10**11 else int(t)); spr.append(float(v))
            tek = kraj
        (OUT / f"{s}.json").write_text(json.dumps({"ts": ts, "spread_points": spr}))
        print(f"{s}: часов со спредом {len(ts)}; своп long {spec[s]['swap_long']} ({spec[s]['swap_mode']})")
        if not ts:
            print("  !! мост не отдаёт поле spread — пришли вывод, сделаем иначе")
    (OUT / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1, default=str))
    print("готово:", OUT)


if __name__ == "__main__":
    main()
