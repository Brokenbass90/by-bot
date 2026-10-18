#!/usr/bin/env python3
"""kesh_att1.py — хук сторожа: один снимок часовых свечей Bybit для монет тени ATT1 (PREREG_ATT1_ODNOVREMENNYY_KONTROL).
Не больше 120 монет за проход, возобновляемо; после полного снимка ничего не делает. Публичный API, без ключей и ордеров."""
import json, time, urllib.request
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; D = LAB / "data/h1_kesh_att1"; GOTOVO = D / "GOTOVO.json"


def prohod(maks=120):
    if GOTOVO.exists(): return dict(status="GOTOVO")
    D.mkdir(parents=True, exist_ok=True)
    syms = sorted({json.loads(s)["sym"] for s in (LAB / "data/ten_ATT1.jsonl").read_text().splitlines() if s.strip()})
    n = osh = 0
    for s in syms:
        p = D / f"{s}.json"
        if p.exists(): continue
        if n >= maks: break
        u = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={s}&interval=60&limit=1000"
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "kesh_att1/1.0"}), timeout=20) as f:
                d = json.loads(f.read().decode())
            lst = (d.get("result") or {}).get("list") or []
            p.write_text(json.dumps([[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in reversed(lst)]))
        except Exception:
            osh += 1
        n += 1; time.sleep(0.1)
    ost = sum(1 for s in syms if not (D / f"{s}.json").exists())
    if ost == 0 or (ost <= 10 and n == 0):
        GOTOVO.write_text(json.dumps(dict(monet=len(syms), propusk=ost, kogda=int(time.time() * 1000))))
    return dict(skachano=n, oshibok=osh, ostalos=ost)


if __name__ == "__main__":
    print(prohod())
