"""Загрузчик для PREREG_KAPITULYACIYA_OI_H1_2026_10_26: часовой OI Bybit (публичный, без ключей), 2023-12-15…2026-10-01, 137 монет PUMP4.
Запуск из корня (≈ 1 ч; можно прерывать — готовые монеты не качаются; лучше в screen):
    .venv/bin/python3 research_lab/zagruzka_oi_h1.py   → research_lab/data/bybit_oi_h1_full/{SYM}.json = [[t_ms, oi], ...]"""
import json, time
from pathlib import Path
import zagruzka_fanding_2025_2026 as Z
HERE = Path(__file__).resolve().parent; OUT = HERE / "data" / "bybit_oi_h1_full"; OUT.mkdir(parents=True, exist_ok=True)
A, B, H = 1702598400000, 1790812800000, 3600_000
syms = json.load(open(HERE / "data" / "pump4_v1_universe_20261020.json"))["symbols"]
for n, s in enumerate(syms, 1):
    f = OUT / f"{s}.json"
    if f.exists(): continue
    oi, end = {}, B
    while end > A:
        try:
            L = Z.get(f"https://api.bybit.com/v5/market/open-interest?category=linear&symbol={s}&intervalTime=1h&startTime={A}&endTime={end}&limit=200")
        except Exception as e:
            print("  !", s, e); break
        if not L: break
        for x in L: oi[int(x["timestamp"])] = float(x["openInterest"])
        nxt = min(int(x["timestamp"]) for x in L) - 1
        if nxt >= end: break
        end = nxt; time.sleep(0.1)
    f.write_text(json.dumps(sorted([t, v] for t, v in oi.items())))
    print(f"{n}/{len(syms)} {s}: часов OI {len(oi)}", flush=True)
print("готово:", OUT)
