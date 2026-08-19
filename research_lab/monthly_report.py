#!/usr/bin/env python3
"""monthly_report.py — портфель по месяцам: сколько, винрейт, красные месяцы.

Читает кэш сигналов оркестратора и прогоняет портфельную логику
(режимный диспетчер, приоритет ног, 12 слотов, один символ за раз),
после чего печатает помесячную разбивку.

Именно этот отчёт нужен, чтобы понять не «сколько всего», а
«как часто бывает плохо и насколько глубоко».
"""
import json, datetime as dt, sys
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = {"ATT1": "флет-", "SBR1": "флет+"}
PRIO = {"SBR1": 0, "ATT1": 1}
SLOTS = int(sys.argv[1]) if len(sys.argv) > 1 else 12
WINDOW_H = 6

tr = json.loads((ROOT / "research_lab/orch_signals.json").read_text(encoding="utf-8"))
pool = [t for t in tr if t["reg"] == REG.get(t["leg"])]
buck = {}
for t in pool:
    buck.setdefault(t["ts"] // (WINDOW_H * 3600000), []).append(t)
pool = []
for k in sorted(buck):
    pool.extend(sorted(buck[k], key=lambda x: (PRIO.get(x["leg"], 9), x["ts"])))
op, tk = [], []
for t in pool:
    op = [x for x in op if x[0] > t["ts"]]
    if any(x[1] == t["sym"] for x in op) or len(op) >= SLOTS:
        continue
    op.append((t["ts"] + t["hours"] * 3600000, t["sym"]))
    tk.append(t)
tk.sort(key=lambda x: x["ts"])

mon = {}
for t in tk:
    mon.setdefault(dt.datetime.utcfromtimestamp(t["ts"] / 1000).strftime("%Y-%m"), []).append(t["R"])
print(f"слотов {SLOTS}\n")
print(f"{'месяц':<9}{'сделок':>7}{'итог R':>9}{'винрейт':>9}")
tot = red = 0
worst = 0.0
for k in sorted(mon):
    R = np.array(mon[k]); tot += R.sum()
    if R.sum() < 0:
        red += 1; worst = min(worst, R.sum())
    bar = ("█" if R.sum() > 0 else "░") * min(20, int(abs(R.sum())))
    print(f"{k:<9}{len(R):>7}{R.sum():>+9.1f}{(R>0).mean():>9.0%}  {bar}")
m = len(mon)
eq = np.cumsum([t["R"] for t in tk])
print(f"\nмесяцев {m}, итог {tot:+.1f}R, в среднем {tot/m:+.2f}R в месяц")
print(f"красных месяцев {red} из {m} ({red*100//m}%), худший {worst:+.1f}R")
print(f"максимальная просадка по кривой {np.max(np.maximum.accumulate(eq)-eq):.1f}R")
print(f"\nпри риске 1% на сделку: ~{tot/m:.2f}% в месяц, просадка ~{np.max(np.maximum.accumulate(eq)-eq):.0f}%")
