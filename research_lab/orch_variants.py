#!/usr/bin/env python3
"""orch_variants.py — читает кэш сигналов и сравнивает варианты диспетчера.

РАЗВЕДКА, НЕ ДОКАЗАТЕЛЬСТВО. Здесь перебираются варианты, а значит
работает поправка на множественность. Ни одно число отсюда нельзя
брать как результат — только как повод объявить предрегистрацию.

Варианты:
  все ноги, без режима      как сейчас в живом боте
  все ноги, по режиму       базовый диспетчер
  по режиму + приоритет     сильной ноге слот отдаётся первой
  только ATT1 по режиму     одна нога без конкурентов
  без ASR1                  проверка, кто мешает
"""
import json, math, sys
from pathlib import Path
import numpy as np

ROOT = str(Path(__file__).resolve().parents[1])
WINDOWS = {"2024-03..2025-09": (1709251200000, 1759276800000),
           "2023-01..2024-02": (1672531200000, 1709251200000)}
REG = {"ATT1": {"флет-"}, "ASR1": {"флет+"}, "ETS2": {"флет-"}, "SF3": {"флет-"}}
PRIO = {"ATT1": 0, "ETS2": 1, "SF3": 2, "ASR1": 3}     # меньше = важнее
SLOTS = 3
SIGMA_R = 1.03


def run(trades, w0, w1, legs, use_reg, priority, hold_hours=6):
    """hold_hours — сколько часов ждать сильную ногу, прежде чем отдать слот слабой"""
    pool = [t for t in trades if w0 <= t["ts"] < w1 and t["leg"] in legs]
    if use_reg:
        pool = [t for t in pool if t["reg"] in REG[t["leg"]]]
    pool.sort(key=lambda x: (x["ts"], PRIO[x["leg"]] if priority else 0))
    if priority:
        # внутри часового окна сначала отдаём слоты сильным ногам
        buckets = {}
        for t in pool:
            buckets.setdefault(t["ts"] // (hold_hours * 3600000), []).append(t)
        pool = []
        for k in sorted(buckets):
            pool.extend(sorted(buckets[k], key=lambda x: (PRIO[x["leg"]], x["ts"])))
    openp, taken = [], []
    for t in pool:
        openp = [x for x in openp if x[0] > t["ts"]]
        if any(x[1] == t["sym"] for x in openp) or len(openp) >= SLOTS:
            continue
        openp.append((t["ts"] + t["hours"] * 3600000, t["sym"]))
        taken.append(t)
    if len(taken) < 20:
        return None
    R = np.array([x["R"] for x in taken]); eq = np.cumsum(R)
    se = R.std(ddof=1) / math.sqrt(len(R))
    months = (w1 - w0) / (30.44 * 86400000)
    return dict(n=len(R), total=float(eq[-1]), mean=float(R.mean()),
                sigma=float(R.mean() / se) if se else 0,
                mde=1.96 * SIGMA_R / math.sqrt(len(R)),
                dd=float(np.max(np.maximum.accumulate(eq) - eq)),
                pm=float(eq[-1] / months), wr=float((R > 0).mean()), taken=taken)


def main():
    cache = sys.argv[1] if len(sys.argv) > 1 else f"{ROOT}/research_lab/orch_signals.json"
    trades = json.loads(Path(cache).read_text(encoding="utf-8"))
    ALL = {"ATT1", "ASR1", "ETS2", "SF3"}
    variants = [
        ("все ноги, без режима",   ALL, False, False),
        ("все ноги, по режиму",    ALL, True,  False),
        ("по режиму + приоритет",  ALL, True,  True),
        ("без ASR1, приоритет",    ALL - {"ASR1"}, True, True),
        ("только ATT1",            {"ATT1"}, True, False),
        ("ATT1 + ETS2",            {"ATT1", "ETS2"}, True, True),
    ]
    print(f"кэш: {Path(cache).name}, сделок в нём {len(trades)}\n")
    for wname, (a, b) in WINDOWS.items():
        print(f"╔══ окно {wname}")
        print(f"{'вариант':<24}{'сделок':>7}{'ИТОГО':>10}{'на сделку':>11}{'σ':>7}"
              f"{'порог':>9}{'просадка':>10}{'в месяц':>9}{'винрейт':>9}")
        for name, legs, ur, pr in variants:
            r = run(trades, a, b, legs, ur, pr)
            if not r:
                print(f"{name:<24} сделок мало"); continue
            mark = " ВИДНО" if abs(r["mean"]) > r["mde"] else ""
            print(f"{name:<24}{r['n']:>7}{r['total']:>+9.1f}R{r['mean']:>+10.4f}R"
                  f"{r['sigma']:>+7.2f}{r['mde']:>8.3f}R{r['dd']:>9.1f}R"
                  f"{r['pm']:>+8.2f}R{r['wr']:>9.0%}{mark}")
        print()


if __name__ == "__main__":
    main()
