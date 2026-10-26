"""Загрузчик для PREREG_FANDING_POSLE_VYPLATY_EKSTREM_2026_10_26 (только публичные данные Bybit, без ключей).
Запуск из корня: .venv/bin/python3 research_lab/zagruzka_fanding_2025_2026.py   (≈ 99 монет; можно прерывать — готовые не качаются)
Пишет research_lab/data/bybit_fanding_h1_2025_2026/{SYM}.json = {"funding": [[t_ms, rate]...], "h1": [[t, o, h, l, c, v]...]}"""
import json, sys, time, urllib.request
from pathlib import Path
HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "bybit_fanding_h1_2025_2026"; OUT.mkdir(parents=True, exist_ok=True)
A, B = 1759276800000, 1790812800000          # 2025-10-01 … 2026-10-01 UTC
H = 3600_000


def get(u):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "research/1.0"}), timeout=25) as r:
                return json.loads(r.read())["result"]["list"]
        except Exception as e:
            if i == 3: raise
            time.sleep(2 * (i + 1))


def main():
    syms = sorted({z[0] for z in json.load(open(HERE / "results/fanding_doza_20261026/zapisi.json"))["zapisi"]})
    for n, s in enumerate(syms, 1):
        f = OUT / f"{s}.json"
        if f.exists(): continue
        fu, end = {}, B
        while end > A:
            L = get(f"https://api.bybit.com/v5/market/funding/history?category=linear&symbol={s}&startTime={A}&endTime={end}&limit=200")
            if not L: break
            for x in L: fu[int(x["fundingRateTimestamp"])] = float(x["fundingRate"])
            end = min(int(x["fundingRateTimestamp"]) for x in L) - 1; time.sleep(0.12)
        h1, st = {}, A
        while st < B:
            L = get(f"https://api.bybit.com/v5/market/kline?category=linear&symbol={s}&interval=60&start={st}&end={min(B, st + 999 * H)}&limit=1000")
            if not L: st += 999 * H; continue
            for x in L: h1[int(x[0])] = [int(x[0])] + [float(v) for v in x[1:6]]
            st = max(int(x[0]) for x in L) + H; time.sleep(0.12)
        f.write_text(json.dumps({"funding": sorted([t, r] for t, r in fu.items() if A <= t < B), "h1": [h1[k] for k in sorted(h1)]}))
        print(f"{n}/{len(syms)} {s}: фандинг {len(fu)}, часов {len(h1)}", flush=True)
    print("готово:", OUT)


if __name__ == "__main__":
    sys.exit(main())
