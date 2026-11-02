#!/usr/bin/env python3
"""poly_sports_ws_sbor.py — запись публичного спортивного WebSocket Polymarket (02.11.2026, Claude; задание PM P0.5). Только чтение, без ключей.
wss://sports-api.polymarket.com/ws — поток обновлений матчей (счёт, период, статус, ended, finishedAt), подписка не нужна; сервер шлёт
«ping» каждые 5 с, отвечаем «pong». Документация: docs.polymarket.com/market-data/websocket/sports.
Зачем: ESPN опаздывает — рынок доходит до 0.99 раньше ESPN FINAL (медиана 16 мин, книги схлопываются за 1–3 мин до FINAL у NFL).
Это источник самой площадки: меряем его задержку против стакана — есть ли вообще окно для вероятностной модели по ходу матча.
Пишется только изменение (status, score, period, ended) по gameId + поле t_ms = наше время получения. Выход data/poly_sports_ws/igry.jsonl.
Запуск вручную или через podnyat_vse.sh:  .venv/bin/python research_lab/poly_sports_ws_sbor.py"""
import json, time
from pathlib import Path
from websockets.sync.client import connect
URL = "wss://sports-api.polymarket.com/ws"
OUT = Path(__file__).resolve().parent / "data" / "poly_sports_ws"; OUT.mkdir(parents=True, exist_ok=True); ZH = OUT / "igry.jsonl"

def main():
    prosh = {}
    while True:
        try:
            with connect(URL, open_timeout=20, ping_interval=None, max_size=2 ** 22) as ws:
                print(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "подключено", flush=True)
                while True:
                    m = ws.recv(timeout=60)
                    if m == "ping": ws.send("pong"); continue
                    t = int(time.time() * 1000)
                    try: d = json.loads(m)
                    except Exception: continue
                    for g in (d if isinstance(d, list) else [d]):
                        if not isinstance(g, dict) or "gameId" not in g: continue
                        k = (g.get("status"), g.get("score"), g.get("period"), g.get("ended"))
                        if prosh.get(g["gameId"]) == k: continue
                        prosh[g["gameId"]] = k
                        with ZH.open("a") as f: f.write(json.dumps(dict(t_ms=t, **g), ensure_ascii=False) + "\n")
        except Exception as e:
            with ZH.open("a") as f: f.write(json.dumps(dict(t_ms=int(time.time() * 1000), oshibka=str(e)[:120]), ensure_ascii=False) + "\n")
            time.sleep(10)

if __name__ == "__main__":
    main()
