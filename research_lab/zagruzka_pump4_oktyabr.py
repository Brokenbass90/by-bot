"""Догрузка для экономики PUMP4 с фандингом (26.10.2026): фандинг и H1 Bybit с 2026-09-25 по текущий час — только монеты 84 сделок
эталона `results/pump4_polnyy_povtor_20261026T0857Z.json`. Публичные данные, без ключей.
Запуск из корня: .venv/bin/python3 research_lab/zagruzka_pump4_oktyabr.py   → research_lab/data/bybit_pump4_okt_2026/{SYM}.json"""
import json, time
from pathlib import Path
import zagruzka_fanding_2025_2026 as Z
HERE = Path(__file__).resolve().parent; OUT = HERE / "data" / "bybit_pump4_okt_2026"; OUT.mkdir(parents=True, exist_ok=True)
A = 1790294400000; H = 3600_000
B = int(time.time() * 1000) // H * H
syms = sorted({x["sym"] for x in json.load(open(HERE / "results/pump4_polnyy_povtor_20261026T0857Z.json"))["sdelki"]})
for n, s in enumerate(syms, 1):
    fu, end = {}, B
    while end > A:
        L = Z.get(f"https://api.bybit.com/v5/market/funding/history?category=linear&symbol={s}&startTime={A}&endTime={end}&limit=200")
        if not L: break
        for x in L: fu[int(x["fundingRateTimestamp"])] = float(x["fundingRate"])
        end = min(int(x["fundingRateTimestamp"]) for x in L) - 1; time.sleep(0.12)
    h1, st = {}, A
    while st < B:
        L = Z.get(f"https://api.bybit.com/v5/market/kline?category=linear&symbol={s}&interval=60&start={st}&end={min(B, st + 999 * H)}&limit=1000")
        if not L: st += 999 * H; continue
        for x in L: h1[int(x[0])] = [int(x[0])] + [float(v) for v in x[1:6]]
        st = max(int(x[0]) for x in L) + H; time.sleep(0.12)
    (OUT / f"{s}.json").write_text(json.dumps({"do_ms": B, "funding": sorted([t, r] for t, r in fu.items()), "h1": [h1[k] for k in sorted(h1)]}))
    print(f"{n}/{len(syms)} {s}: фандинг {len(fu)}, часов {len(h1)}", flush=True)
print("готово:", OUT)
