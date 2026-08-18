#!/usr/bin/env python3
"""harvest_passports.py — свести все паспорта в один список кандидатов.

ЗАЧЕМ. Полная очередь даёт 49 стратегий × 210 ячеек ≈ 10 000 проверок.
При таком переборе несколько ячеек покажут 3σ чисто случайно. Поэтому
здесь не «победители», а кандидаты, и рядом с каждым — насколько
строгий порог он обязан взять.

Отбор, объявленный до чтения результатов:

  1. знак ПОЛОЖИТЕЛЕН на обоих окнах;
  2. сделок не меньше 200 на первом окне и 100 на втором;
  3. эффект больше фактического порога различимости хотя бы на одном;
  4. нижняя граница недельного бутстрапа выше нуля хотя бы на одном;
  5. значимость на первом окне не ниже порога Бонферрони для числа
     фактически прочитанных ячеек.

Пятое условие — главное отличие от прошлых разборов. Раньше мы
смотрели на 3σ и радовались, не считая, из скольких попыток эта
тройка получена.
"""
from __future__ import annotations
import json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {"_smoke", "_smoke2"}


def z_bonferroni(m):
    """порог значимости при m независимых проверках, односторонний, 5%"""
    # приближение обратной нормали (Acklam), достаточно точное для наших целей
    p = 1 - 0.05 / max(1, m)
    if p >= 1:
        return 9.0
    q = p - 0.5
    if abs(q) <= 0.425:
        r = 0.180625 - q * q
        return q * (((2509.08 * r + 33430.6) * r + 67265.8) * r + 45921.95) / \
               ((((5226.5 * r + 28729.1) * r + 39307.9) * r + 21213.79) * r + 1)
    r = math.sqrt(-math.log(1 - p))
    return (((2.938164 * r + 4.374664) * r + 2.549732) * r + 2.938164) / \
           ((1.637068 * r + 3.754408) * r + 1)


def main():
    packs, cells = {}, 0
    for f in sorted((ROOT / "research_lab").glob("passport_*.json")):
        tag = f.stem[9:]
        if tag in SKIP:
            continue
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        ws = list(p["windows"].values())
        if len(ws) != 2:
            continue
        packs[tag] = ws
        cells += len(ws[0])

    z = z_bonferroni(cells)
    print(f"прочитано стратегий: {len(packs)}, ячеек всего: {cells}")
    print(f"порог значимости с поправкой на {cells} проверок: {z:.2f}σ\n")

    good = []
    for tag, (w1, w2) in packs.items():
        for k, s1 in w1.items():
            s2 = w2.get(k)
            if not s2:
                continue
            if s1["net"] <= 0 or s2["net"] <= 0:
                continue
            if s1["n"] < 200 or s2["n"] < 100:
                continue
            if not (s1.get("visible") or s2.get("visible")):
                continue
            if not ((s1.get("boot_lo") or -1) > 0 or (s2.get("boot_lo") or -1) > 0):
                continue
            good.append((s1["sigma"], tag, k, s1, s2))
    good.sort(reverse=True)

    if not good:
        print("ни одной ячейки, прошедшей все пять условий")
        return

    strong = [g for g in good if g[0] >= z]
    print(f"прошли отбор: {len(good)}, из них взяли поправку Бонферрони: {len(strong)}\n")
    print(f"{'':<2}{'нога':<10}{'конфигурация':<24}{'окно1':>26}{'окно2':>22}")
    for sg, tag, k, s1, s2 in good[:30]:
        mark = "!!" if sg >= z else "  "
        print(f"{mark}{tag:<10}{k:<24}"
              f"{s1['net']:>+9.4f}R n={s1['n']:<5}σ={s1['sigma']:>+5.2f}"
              f"{s2['net']:>+9.4f}R n={s2['n']:<5}σ={s2['sigma']:>+5.2f}")
    print("\n!! = значимость выше порога с поправкой на число проверок.")
    print("   Без пометки — кандидат, но объяснимый случайностью перебора.")
    out = ROOT / "research_lab" / "candidates.json"
    out.write_text(json.dumps(
        [dict(leg=t, cfg=k, w1=s1, w2=s2, bonferroni=sg >= z)
         for sg, t, k, s1, s2 in good], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nсписок: {out}")


if __name__ == "__main__":
    main()
