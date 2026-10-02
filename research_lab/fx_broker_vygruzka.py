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
import argparse, calendar, datetime as dt, json, sys
from pathlib import Path

KOREN = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(KOREN / "signal_copy"))
import config                              # noqa: E402
from mt5_mcp import MT5MCP, MT5Error, SUFFIXES   # noqa: E402


def naiti_simvol(m, s):
    """02.10: у брокера пары могут быть с суффиксом (Bullwaves: EURUSD!). Пробуем тот же инструмент с суффиксами
    площадки; если в Обзоре рынка нет — добавляем в Обзор (витрина котировок, не торговая операция)."""
    for c in [s, s + "!"] + [s + x for x in SUFFIXES]:
        for dobavit in (False, True):
            try:
                if dobavit:
                    m.add_symbol(c)
                sp = m.symbol(c)
                nastoyashchee = str(sp.get("name") or sp.get("symbol") or c)
                if nastoyashchee.upper().startswith(s):
                    return nastoyashchee, sp
            except MT5Error:
                continue
    raise MT5Error(f"{s}: не найден ни под одним суффиксом")

PARY = ["AUDUSD", "EURUSD", "GBPUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY"]
OUT = KOREN / "research_lab/data/fx_broker"


def _vs(y, m, n):
    """n-е воскресенье месяца (n=-1 — последнее)"""
    d = [w[6] for w in calendar.monthcalendar(y, m) if w[6]]
    return d[n] if n < 0 else d[n - 1]


def leto_us(d):
    a = dt.date(d.year, 3, _vs(d.year, 3, 2)); b = dt.date(d.year, 11, _vs(d.year, 11, 1)); return a <= d < b


def leto_eu(d):
    a = dt.date(d.year, 3, _vs(d.year, 3, -1)); b = dt.date(d.year, 10, _vs(d.year, 10, -1)); return a <= d < b


def opredelit_vremya(ts_ms):
    """02.10: время сервера НЕ предполагается. Рынок FX открывается в вс 17:00 Нью-Йорка = 21:00 UTC (лето США) /
    22:00 UTC (зима США). По часу сервера первого бара каждой недели считаем сдвиг сервер−UTC и проверяем правила:
      utc       — сдвиг 0;
      ny_close  — +3 летом США, +2 зимой США (открытие недели всегда 00:00 сервера);
      mt5_eet   — +3 летом ЕС, +2 зимой ЕС (как MetaQuotes-Demo).
    Правило принимается, если совпало ≥ 95% недель и оно единственное лучшее; иначе 'neopredeleno' — ворота откажут."""
    ts = sorted(ts_ms); otkr = [ts[i] for i in range(1, len(ts)) if ts[i] - ts[i - 1] > 24 * 3600_000]
    pravila = {"utc": lambda d: 0, "ny_close": lambda d: 3 if leto_us(d) else 2, "mt5_eet": lambda d: 3 if leto_eu(d) else 2}
    sovp = {k: 0 for k in pravila}; sdvigi = {}
    for t in otkr:
        srv = dt.datetime.utcfromtimestamp(t / 1000)
        d = srv.date() if srv.hour >= 12 else srv.date() - dt.timedelta(days=1)    # воскресенье открытия
        utc_chas = 21 if leto_us(d) else 22
        sd = (srv.hour - utc_chas) % 24; sdvigi[sd] = sdvigi.get(sd, 0) + 1
        for k, f in pravila.items():
            sovp[k] += sd == f(d)
    n = max(len(otkr), 1); dol = {k: v / n for k, v in sovp.items()}
    luchshie = [k for k, v in dol.items() if v == max(dol.values())]
    rez = luchshie[0] if len(luchshie) == 1 and dol[luchshie[0]] >= 0.95 else "neopredeleno"
    return rez, {"nedel": len(otkr), "doli": {k: round(v, 3) for k, v in dol.items()}, "sdvigi_chasov": sdvigi}


BARY = {}
CHASY_TIKOV = {20, 21, 22, 6, 7, 8}          # вокруг входа 21 UTC и выхода +10 ч
_pokazano = set()


def _vremya(t):
    if isinstance(t, (int, float)):
        return int(t) * 1000 if t < 10**11 else int(t)
    t = str(t).replace("Z", "").replace(".", "-", 2).replace(" ", "T")
    return int(dt.datetime.fromisoformat(t).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def _spisok(r, klyuchi):
    return r if isinstance(r, list) else next((r[k] for k in klyuchi if isinstance(r, dict) and isinstance(r.get(k), list)), [])


def _oshibka(m, tool, e):
    if tool in _pokazano:
        return
    _pokazano.add(tool)
    print(f"  !! {tool}: {str(e)[:600]}")
    try:
        resp, _ = m._post({"jsonrpc": "2.0", "id": 98, "method": "tools/list", "params": {}})
        for t in ((resp or {}).get("result") or {}).get("tools") or []:
            if t.get("name") == tool:
                print(f"  схема {tool}: {json.dumps(t.get('inputSchema'), ensure_ascii=False)[:600]}")
    except Exception:
        pass


def istoriya_spreda(m, s, imya, ot, do):
    ts, spr, bt = [], [], []
    try:                                     # история отдаётся только по символам, выбранным в Обзоре рынка (selected)
        m.add_symbol(imya)
    except MT5Error as e:
        print(f"  {imya}: не добавился в Обзор рынка ({str(e)[:120]})")
    tek = ot
    while tek < do:
        kraj = min(tek + dt.timedelta(days=30), do + dt.timedelta(days=1))
        bary = []
        for popytka in range(4):             # терминал подкачивает историю с сервера при первом запросе — пусто ≠ нет данных
            try:
                r = m.call("get_chart_history", timeout=90.0, symbol=imya, period="H1",
                           datetime_from=tek.strftime("%Y-%m-%dT00:00:00"), datetime_to=kraj.strftime("%Y-%m-%dT00:00:00"),
                           limit=1000)
            except MT5Error as e:
                _oshibka(m, "get_chart_history", e); break
            bary = _spisok(r, ("history", "candles", "rates", "bars", "data", "items"))
            if bary:
                break
            __import__("time").sleep(3)
        if bary and "bary" not in _pokazano:
            _pokazano.add("bary"); print(f"  ключи бара: {sorted(bary[0].keys())}")
        for x in bary:
            t = x.get("time") or x.get("datetime")
            if t is None:
                continue
            t = _vremya(t); bt.append(t)
            if x.get("spread") is not None:
                ts.append(t); spr.append(float(x["spread"]))
        tek = kraj
    return ts, spr, sorted(set(bt))


def _den_trojnogo(sp):
    """день тройного свопа: MT5 0=вс … 6=сб → Python 0=пн … 6=вс; мост отдаёт swap_rollover3day(s), бывает float"""
    v = sp.get("swap_rollover3days", sp.get("swap_rollover3day"))
    try:
        return (int(float(v)) - 1) % 7
    except (TypeError, ValueError):
        return 2


def _sdvig(pravilo, d):
    return {"utc": 0, "ny_close": 3 if leto_us(d) else 2, "mt5_eet": 3 if leto_eu(d) else 2}[pravilo]


def spred_iz_tikov(m, imya, point, pravilo, ot, do):
    ts, spr = [], []
    d = ot
    while d < do:
        if d.weekday() < 5:
            for h in sorted(CHASY_TIKOV):
                utc = dt.datetime(d.year, d.month, d.day, h)
                srv = utc + dt.timedelta(hours=_sdvig(pravilo, d))
                try:
                    r = m.call("get_chart_ticks_history", timeout=90.0, symbol=imya,
                               datetime_from=srv.strftime("%Y-%m-%dT%H:%M:%S"),
                               datetime_to=(srv + dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S"), limit=20000)
                except MT5Error as e:
                    _oshibka(m, "get_chart_ticks_history", e); continue
                tiki = _spisok(r, ("ticks", "history", "data", "items"))
                if tiki and "tiki" not in _pokazano:
                    _pokazano.add("tiki"); print(f"  ключи тика: {sorted(tiki[0].keys())}")
                v = [float(x["ask"]) - float(x["bid"]) for x in tiki
                     if x.get("ask") and x.get("bid") and float(x["ask"]) > 0 and float(x["bid"]) > 0]
                if len(v) >= 5:
                    ts.append(int(srv.replace(tzinfo=dt.timezone.utc).timestamp() * 1000))
                    spr.append(float(sorted(v)[len(v) // 2]) / point)
        d += dt.timedelta(days=4)
    return ts, spr


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--komissiya", type=float, default=None,
                                                    help="USD за 1 лот за одну сторону (0 для счёта без комиссии); "
                                                         "без аргумента — только разведка счёта и комиссии из истории, без выгрузки")
    ap.add_argument("--dney", type=int, default=400)
    a = ap.parse_args(); OUT.mkdir(parents=True, exist_ok=True)
    m = MT5MCP(config.MT5_URL, config.MT5_TOKEN); m.connect()
    acc = m.account()
    server = str(acc.get("server", "")); company = str(acc.get("company", ""))
    print(f"брокер: {company} | сервер: {server} | режим: {acc.get('trade_mode')}")
    if not any(k in server.lower() for k in ("fxpro", "bullwaves")):
        print("  !! ВНИМАНИЕ: площадка повтора зафиксирована — FxPro (сырой спред). Этот сервер в вердикт не идёт.")
    if "MetaQuotes" in server or "MetaQuotes" in company:
        sys.exit("это MetaQuotes-Demo — нужен счёт реального брокера (можно его демо того же типа)")
    print(f"валюта счёта: {acc.get('currency')} | плечо: {acc.get('leverage')} | группа: {acc.get('group') or '-'}")
    if a.komissiya is None:                 # 02.10: разведка комиссии по истории закрытых позиций (только чтение)
        try:
            r = m.call("get_trading_history_positions", timeout=60.0,
                       date_from=(dt.date.today() - dt.timedelta(days=400)).isoformat(), date_to=dt.date.today().isoformat())
        except MT5Error as e:
            sys.exit(f"мост не отдал историю позиций ({str(e)[:120]}) — посмотри комиссию в MT5 руками")
        poz = r if isinstance(r, list) else next((r[k] for k in ("positions", "history", "items", "data")
                                                  if isinstance(r, dict) and isinstance(r.get(k), list)), [])
        if not poz:
            sys.exit("закрытых позиций в истории нет (новый/демо-счёт) — комиссию из истории не узнать")
        print("поля позиции:", sorted(poz[0].keys()))
        kom = sum(float(p.get("commission") or 0) for p in poz); ob = sum(float(p.get("volume") or 0) for p in poz)
        po_simv = {}
        for p in poz:
            q = po_simv.setdefault(p.get("symbol"), [0, 0.0, 0.0]); q[0] += 1
            q[1] += float(p.get("volume") or 0); q[2] += float(p.get("commission") or 0)
        print(f"позиций {len(poz)}, лотов {ob:.2f}, комиссия всего {kom:.2f} {acc.get('currency')}")
        for k, (n, v, c) in sorted(po_simv.items(), key=lambda kv: -kv[1][0])[:10]:
            print(f"  {k}: позиций {n}, лотов {v:.2f}, комиссия {c:.2f} → {abs(c) / v if v else 0:.2f} за лот за круг")
        sys.exit("разведка окончена; выгрузка не делалась")
    spec = {"broker": company, "server": server, "vremya": None, "trade_mode": acc.get("trade_mode"),
            "kogda": dt.datetime.utcnow().isoformat(timespec="seconds")}
    do = dt.date.today(); ot = do - dt.timedelta(days=a.dney)
    for s in PARY:
        try:
            imya, sp = naiti_simvol(m, s)
            if imya != s:
                print(f"{s}: у брокера называется {imya}")
        except MT5Error as e:
            print(f"{s}: нет в Обзоре рынка ({e}) — добавь символ (с суффиксом брокера, если он есть)"); continue
        spec[s] = {"point": sp.get("point"), "contract_size": sp.get("trade_contract_size") or sp.get("contract_size"),
                   "swap_long": sp.get("swap_long"), "swap_mode": {1: "points", 2: "money_per_lot"}.get(sp.get("swap_mode"), sp.get("swap_mode")),
                   "swap_3day": _den_trojnogo(sp),
                   "commission_usd_per_lot_side": a.komissiya, "imya_u_brokera": imya, "_syroe": sp}
        ts, spr, bt = istoriya_spreda(m, s, imya, ot, do)
        BARY[s] = bt
        (OUT / f"{s}.json").write_text(json.dumps({"ts": ts, "spread_points": spr}))
        print(f"{s}: баров H1 {len(bt)}, часов со спредом {len(ts)}; своп long {spec[s]['swap_long']} ({spec[s]['swap_mode']})")
    vr, diag = opredelit_vremya(BARY.get("EURUSD") or []) if BARY.get("EURUSD") else ("neopredeleno", {"prichina": "нет часовых баров"})
    if vr != "neopredeleno" and any(BARY[q] and not json.load(open(OUT / f"{q}.json"))["ts"] for q in BARY):
        print(f"в барах нет поля spread — беру спред из тиков (выборка: каждый 4-й день, часы UTC {sorted(CHASY_TIKOV)}), правило времени {vr}")
        for q in BARY:
            ts, spr = spred_iz_tikov(m, spec[q]["imya_u_brokera"], spec[q]["point"], vr, ot, do)
            (OUT / f"{q}.json").write_text(json.dumps({"ts": ts, "spread_points": spr, "istochnik": "tiki"}))
            print(f"  {q}: часов со спредом из тиков {len(ts)}")
    try:                                   # независимая проверка: время последнего тика (сервер) против UTC сейчас
        tik = naiti_simvol(m, "EURUSD")[1].get("time")
        if isinstance(tik, (int, float)) and tik > 0:
            diag["sdvig_po_tiku_chasov"] = round((tik - dt.datetime.now(dt.timezone.utc).timestamp()) / 3600, 2)
    except Exception:
        pass
    spec["vremya"] = vr; spec["vremya_diagnostika"] = diag
    print(f"время сервера: {vr} | {diag}")
    if vr == "neopredeleno":
        print("  !! правило времени сервера не определено — ворота издержек откажут (INSUFFICIENT_DATA); пришли этот вывод")
    (OUT / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1, default=str))
    print("готово:", OUT)


if __name__ == "__main__":
    main()
