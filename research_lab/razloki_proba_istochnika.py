#!/usr/bin/env python3
"""razloki_proba_istochnika.py — проверка источника истории разлоков (29.10.2026, Claude; PM: сначала качество и даты, без движка).
Mobula metadata → release_schedule (без ключа, режим разработки). По 15 известным токенам с разлоками печатает: сколько событий, сколько в прошлом
(2024–2025), есть ли дата и объём. Вывод: годится ли для исторической проверки. Только чтение.  .venv/bin/python3 research_lab/razloki_proba_istochnika.py"""
import json, time, urllib.parse, urllib.request
T = ["arbitrum", "aptos", "sui", "optimism", "celestia", "starknet", "worldcoin", "pyth-network", "jupiter", "sei", "dydx", "immutable-x", "axie-infinity", "ondo", "zksync"]
for a in T:
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.mobula.io/api/1/metadata?" + urllib.parse.urlencode(dict(asset=a)), headers={"User-Agent": "research-readonly/1.0"}), timeout=20) as r:
            d = json.loads(r.read()).get("data") or {}
    except Exception as e:
        print(a, "ошибка", str(e)[:80]); continue
    rs = d.get("release_schedule") or []
    ts = []
    for x in rs:
        t = x.get("unlock_date") or x.get("date") or x.get("timestamp")
        try: t = int(t) / (1000 if int(t) > 1e11 else 1)
        except Exception: t = None
        if t: ts.append(t)
    proshl = [t for t in ts if 1704067200 <= t <= 1759276800]
    print(f"{a:16s} событий {len(rs):4d} | с датой {len(ts):4d} | в 2024–09.2025 {len(proshl):4d} | пример {json.dumps(rs[:1], ensure_ascii=False)[:160]}")
    time.sleep(0.5)
