#!/usr/bin/env python3
"""poly_clob_ws_sbor.py — запись стакана Polymarket по WebSocket для начавшихся/скорых матчей (02.11.2026, Claude; задание PM P0.1). Только чтение.
wss://ws-subscriptions-clob.polymarket.com/ws/market (docs.polymarket.com/market-data/websocket/overview): подписка по asset_id, PING раз в 10 с.
Зачем: судья «спортивный WebSocket против стакана» должен сравнивать время событий с точностью до секунд, а не по минутным снимкам монитора.
Какие рынки: из data/poly_monitor/rynki.jsonl — вопрос с « vs», konec (= начало матча) в окне [сейчас − 6 ч, сейчас + 2 ч]; пересчёт раз в 5 мин.
Пишем: best_bid_ask (лучшие цены), last_trade_price (сделки), market_resolved, а из book — лучшие цены и глубину в 2 ¢ (без полного стакана).
У каждой записи ts_srv (время биржи, мс) и t_ms (наше время получения). Выход data/poly_clob_ws/YYYY-MM-DD.jsonl.
Запуск через podnyat_vse.sh или вручную: .venv/bin/python research_lab/poly_clob_ws_sbor.py"""
import datetime as dt, json, time
from pathlib import Path
from websockets.sync.client import connect
URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
LAB = Path(__file__).resolve().parent; RY = LAB / "data" / "poly_monitor" / "rynki.jsonl"; OUT = LAB / "data" / "poly_clob_ws"; OUT.mkdir(parents=True, exist_ok=True)

def pis(z):
    with (OUT / (time.strftime("%Y-%m-%d", time.gmtime()) + ".jsonl")).open("a") as f: f.write(json.dumps(z, ensure_ascii=False) + "\n")

def tekushchie():
    """token → id рынка для матчей, идущих сейчас или скоро."""
    akt = {}; now = dt.datetime.now(dt.timezone.utc)
    for l in RY.open():
        try: z = json.loads(l)
        except Exception: continue
        if z.get("sob") == "dobavlen" and " vs" in z.get("vopros", "") and z.get("token"):
            try: k = dt.datetime.fromisoformat(z["konec"])
            except Exception: continue
            if now - dt.timedelta(hours=6) <= k <= now + dt.timedelta(hours=2): akt[z["token"]] = z["id"]
        elif z.get("sob") == "vybyl":
            for t in [t for t, i in akt.items() if i == z.get("id")]: akt.pop(t, None)
    return akt

def glub(urovni, best, vverh):
    s = 0.0
    for u in urovni or []:
        p, q = float(u["price"]), float(u["size"])
        if (vverh and p <= best + 0.02) or (not vverh and p >= best - 0.02): s += p * q
    return round(s, 2)

def main():
    while True:
        try:
            with connect(URL, open_timeout=20, ping_interval=None, max_size=2 ** 24) as ws:
                akt = tekushchie(); ws.send(json.dumps(dict(assets_ids=list(akt), type="market", custom_feature_enabled=True)))
                pis(dict(t_ms=int(time.time() * 1000), sob="podpiska", aktivov=len(akt)))
                t_ping = t_spisok = time.time()
                while True:
                    if time.time() - t_ping > 10: ws.send("PING"); t_ping = time.time()
                    if time.time() - t_spisok > 300:
                        nov = tekushchie(); dob = [t for t in nov if t not in akt]; ub = [t for t in akt if t not in nov]
                        if dob: ws.send(json.dumps(dict(assets_ids=dob, operation="subscribe", custom_feature_enabled=True)))
                        if ub: ws.send(json.dumps(dict(assets_ids=ub, operation="unsubscribe")))
                        akt = nov; t_spisok = time.time(); pis(dict(t_ms=int(time.time() * 1000), sob="podpiska", aktivov=len(akt), dob=len(dob), ub=len(ub)))
                    try: m = ws.recv(timeout=5)
                    except TimeoutError: continue
                    if m == "PONG": continue
                    t = int(time.time() * 1000)
                    try: d = json.loads(m)
                    except Exception: continue
                    for e in (d if isinstance(d, list) else [d]):
                        et = e.get("event_type"); ts = int(e["timestamp"]) if str(e.get("timestamp", "")).isdigit() else None
                        if et == "best_bid_ask":
                            pis(dict(t_ms=t, ts_srv=ts, sob="bba", aid=e.get("asset_id"), id=akt.get(e.get("asset_id")), bid=e.get("best_bid"), ask=e.get("best_ask")))
                        elif et == "last_trade_price":
                            pis(dict(t_ms=t, ts_srv=ts, sob="sdelka", aid=e.get("asset_id"), id=akt.get(e.get("asset_id")), cena=e.get("price"), razmer=e.get("size"), storona=e.get("side"), fee_bps=e.get("fee_rate_bps")))
                        elif et == "market_resolved":
                            pis(dict(t_ms=t, ts_srv=ts, sob="razreshen", market=e.get("market"), pobeditel=e.get("winning_asset_id"), ishod=e.get("winning_outcome")))
                        elif et == "book":
                            b = sorted(e.get("bids") or [], key=lambda u: -float(u["price"])); a = sorted(e.get("asks") or [], key=lambda u: float(u["price"]))
                            bb = float(b[0]["price"]) if b else None; ba = float(a[0]["price"]) if a else None
                            pis(dict(t_ms=t, ts_srv=ts, sob="kniga", aid=e.get("asset_id"), id=akt.get(e.get("asset_id")), bid=bb, ask=ba,
                                     gl_bid=glub(b, bb, False) if bb is not None else 0, gl_ask=glub(a, ba, True) if ba is not None else 0))
        except Exception as ex:
            pis(dict(t_ms=int(time.time() * 1000), sob="oshibka", tekst=str(ex)[:150])); time.sleep(10)

if __name__ == "__main__":
    main()
