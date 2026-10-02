#!/usr/bin/env python3
"""atlas_izderzhek.py — атлас реальных издержек площадки (02.10). Только чтение, ни одного ордера.

Урок NOCHNOY FX: сигнал на +2.3 bps съели издержки. Прежде чем искать новые механизмы на CFD/FX, нужно знать,
сколько стоит вход на каждом инструменте в каждый час суток. Атлас — данные, не гипотеза: ничего не тестирует.
По каждому инструменту из списка: спред (медиана и p75) в bps цены по часам UTC за ~400 дней (часовые бары MT5),
свопы long/short, размер контракта. Время сервера определяется по открытию недель (как в fx_broker_vygruzka).

    cd signal_copy && ../.venv/bin/python3 ../research_lab/fabrika/atlas_izderzhek.py --komissiya 3.5
Кладёт research_lab/data/atlas_izderzhek_<сервер>.json и печатает топ самых дешёвых инструментов.
"""
import argparse, datetime as dt, json, sys
from pathlib import Path
import numpy as np

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
import fx_broker_vygruzka as F            # noqa: E402  (мост, поиск символа, история, время сервера)

SPISOK = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD", "EURGBP", "EURJPY", "EURCHF",
          "EURAUD", "EURCAD", "GBPJPY", "GBPCHF", "AUDJPY", "CADJPY", "CHFJPY", "AUDNZD", "AUDCAD", "NZDJPY",
          "XAUUSD", "XAGUSD", "US500", "NAS100", "US30", "GER40", "UK100", "JPN225", "EUSTX50", "FRA40",
          "BRENT", "WTI", "NGAS", "BTCUSD", "ETHUSD"]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--komissiya", type=float, required=True,
                                                    help="USD за лот за сторону (для FX; у CFD индексов обычно 0)")
    a = ap.parse_args()
    m = F.MT5MCP(F.config.MT5_URL, F.config.MT5_TOKEN); m.connect()
    server = str(m.account().get("server", ""))
    print("сервер:", server)
    if "MetaQuotes" in server:
        sys.exit("MetaQuotes-Demo — нужен счёт реального брокера")
    do = dt.date.today(); ot = do - dt.timedelta(days=400)
    syroe, rez = {}, {}
    for s in SPISOK:
        try:
            imya, sp = F.naiti_simvol(m, s)
        except F.MT5Error:
            print(f"{s}: нет у брокера"); continue
        ts, spr, bt = F.istoriya_spreda(m, s, imya, ot, do)
        if not ts:
            print(f"{s} ({imya}): истории нет"); continue
        syroe[s] = (imya, sp, ts, spr, bt)
        print(f"{s} ({imya}): часов {len(ts)}", flush=True)
    if "EURUSD" not in syroe:
        sys.exit("нет EURUSD — время сервера не определить")
    vr, diag = F.opredelit_vremya(syroe["EURUSD"][4])
    print("время сервера:", vr, diag)
    if vr == "neopredeleno":
        sys.exit("правило времени сервера не определено — атлас по часам UTC не строю")
    sdvig = {"utc": lambda d: 0, "ny_close": lambda d: 3 if F.leto_us(d) else 2,
             "mt5_eet": lambda d: 3 if F.leto_eu(d) else 2}[vr]
    for s, (imya, sp, ts, spr, bt) in syroe.items():
        point = float(sp.get("point") or 0)
        cena = float(sp.get("bid") or sp.get("ask") or 0)
        if point <= 0 or cena <= 0:
            continue
        chasy = {}
        for t, v in zip(ts, spr):
            srv = dt.datetime.utcfromtimestamp(t / 1000)
            utc = srv - dt.timedelta(hours=sdvig(srv.date()))
            chasy.setdefault(utc.hour, []).append(v * point / cena * 1e4)
        po_chasam = {h: [round(float(np.median(x)), 2), round(float(np.percentile(x, 75)), 2)]
                     for h, x in sorted(chasy.items()) if len(x) >= 20}
        vse = [y for x in chasy.values() for y in x]
        kontrakt = float(sp.get("contract_size") or sp.get("trade_contract_size") or 0)
        fx = len(s) == 6 and s.isalpha() and not s.startswith(("XAU", "XAG", "BTC", "ETH"))
        nominal_usd = (kontrakt * cena if s.endswith("USD") else kontrakt if s.startswith("USD") else 0) if fx else 0
        kom_bps = 2 * a.komissiya / nominal_usd * 1e4 if nominal_usd else 0.0      # кроссы без USD — комиссию не считаем
        rez[s] = {"imya": imya, "spred_med_bps": round(float(np.median(vse)), 2),
                  "spred_p75_bps": round(float(np.percentile(vse, 75)), 2),
                  "komissiya_krug_bps_primerno": round(kom_bps, 2), "po_chasam_utc_med_p75_bps": po_chasam,
                  "swap_long": sp.get("swap_long"), "swap_short": sp.get("swap_short"),
                  "swap_mode": sp.get("swap_mode"), "kontrakt": kontrakt, "cena_snimka": cena}
    out = LAB / f"data/atlas_izderzhek_{server.replace(' ', '_')}.json"
    out.write_text(json.dumps({"server": server, "vremya": vr, "kogda": dt.date.today().isoformat(),
                               "komissiya_usd_lot_side": a.komissiya, "instrumenty": rez}, ensure_ascii=False, indent=1))
    print("\nкруг (спред p75 + комиссия), bps — от дешёвых к дорогим:")
    for s, r in sorted(rez.items(), key=lambda kv: kv[1]["spred_p75_bps"] + kv[1]["komissiya_krug_bps_primerno"]):
        print(f"  {s:8s} {r['spred_p75_bps'] + r['komissiya_krug_bps_primerno']:7.2f}   (спред мед {r['spred_med_bps']})")
    print("готово:", out)


if __name__ == "__main__":
    main()
