#!/usr/bin/env python3
"""pm2_monotonnost.py — PM2 POLY_MICROSTRUCTURE: арбитраж монотонности лестниц «<монета> above K on <дата>?».
Правила заморожены 2026-10-01 ДО первых снимков v5.

Логика: при K1 < K2 событие «выше K2» влечёт «выше K1», значит честно P(K1) ≥ P(K2).
Если лучший ask YES(K1) < лучший bid YES(K2), то: купить YES(K1) по ask, продать YES(K2) по bid
(на Polymarket — купить NO(K2) по 1 − bid). Выплата пары в конце ≥ 0 при любом исходе, прибыль ≥ bid − ask.
Издержки на круг: 1¢ на ногу (комиссии крипто-рынков и проскальзывание) = 2¢ на пару.
Исполнимый размер — минимум объёмов на лучшем уровне двух ног (в долях, $ = доли × цена).

Данные: data/poly/snimki/*.jsonl, kat == "strike" (сборщик v5), дубли (t, conditionId) убираются.
Вердикт (минимум 3 календарных дня снимков):
  EXECUTABLE — нарушений с прибылью ≥ 2¢ после издержек и размером ≥ $20: ≥ 10 кругов на ≥ 3 разных днях;
  NOT_EXECUTABLE — иначе; ЖДЁМ — меньше 3 дней данных.
    python3 research_lab/pm2_monotonnost.py
"""
import collections, glob, json, re
from pathlib import Path

D = Path(__file__).resolve().parent / "data/poly/snimki"
IZD = 0.02; MIN_PRIB = 0.02; MIN_USD = 20.0
RE_K = re.compile(r"above\s*\$?([\d,\.]+)\s*(k)?", re.I)


def strike(z):
    for txt in (z.get("vopros") or "",):
        m = RE_K.search(txt)
        if m:
            return float(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1)
    return None


def main():
    kruge = collections.defaultdict(dict)        # (t, sobytie) -> conditionId -> (K, bid, bsz, ask, asz)
    dni = set()
    for f in sorted(D.glob("*.jsonl")):
        for l in open(f):
            if '"strike"' not in l:
                continue
            z = json.loads(l)
            if z.get("kat") != "strike":
                continue
            K = strike(z)
            if K is None or not z["bids"] or not z["asks"]:
                continue
            dni.add(f.stem)
            kruge[(z["t"], z["sobytie"])][z["conditionId"]] = (K, z["bids"][0][0], z["bids"][0][1], z["asks"][0][0], z["asks"][0][1])
    narush, primery = [], []
    for (t, ev), ms in kruge.items():
        L = sorted(ms.values())
        for i in range(len(L)):
            for j in range(i + 1, len(L)):
                K1, _, _, a1, as1 = L[i]; K2, b2, bs2, _, _ = L[j]
                if K2 <= K1:
                    continue
                prib = b2 - a1 - IZD
                razm = min(as1 * a1, bs2 * (1 - b2))           # $ вложений на ногу
                if prib >= MIN_PRIB and razm >= MIN_USD:
                    narush.append((t, ev, K1, K2, round(prib, 3), round(razm, 1)))
    po_dnyam = collections.Counter(__import__("time").strftime("%Y-%m-%d", __import__("time").gmtime(t / 1000)) for t, *_ in narush)
    krugov = len({(t, ev) for t, ev, *_ in narush})
    v = ("ЖДЁМ" if len(dni) < 3 else
         "EXECUTABLE" if krugov >= 10 and len(po_dnyam) >= 3 else "NOT_EXECUTABLE")
    print(f"PM2: дней {len(dni)}, кругов лестниц {len(kruge)}, нарушений {len(narush)} в {krugov} кругах, по дням {dict(po_dnyam)} → {v}")
    for x in sorted(narush, key=lambda x: -x[4])[:5]:
        print("  пример:", x)


if __name__ == "__main__":
    main()
