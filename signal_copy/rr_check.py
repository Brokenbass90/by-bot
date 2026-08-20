# -*- coding: utf-8 -*-
"""Геометрия сигналов: сколько риска на сколько прибыли. Только арифметика."""
S = [  # symbol, side, entry_min, entry_max, sl, [tp1..tp4]
 ("AUDUSD","BUY",0.70810,0.70820,0.70669,[0.70892,0.71033,0.71190,0.71295]),
 ("XAUUSD","BUY",4395,4398,4377,[4402.1,4408.4,4419.1,4436.2]),
 ("XAUUSD","SELL",4399,4402,4416.7,[4396.1,4390.4,4384.5,4366.8]),
 ("AUDUSD","SELL",0.70580,0.70580,0.70689,[0.70542,0.70509,0.70470,0.70392]),
]
print(f"{'сигнал':<16}{'риск':>10} │ {'R до TP1':>9}{'TP2':>8}{'TP3':>8}{'TP4':>8}")
print("─"*68)
for sym, side, lo, hi, sl, tps in S:
    entry = hi if side=="BUY" else lo          # худший край зоны
    risk  = abs(entry - sl)
    rs = [ (tp-entry)/risk if side=="BUY" else (entry-tp)/risk for tp in tps ]
    name = f"{sym} {side}"
    print(f"{name:<16}{risk:>10.5f} │ " + "".join(f"{r:>8.2f}" for r in ([rs[0]]+rs[1:])))
print("""
Худший край зоны входа = консервативно: для BUY верхняя граница, для SELL нижняя.
Риск считается до стопа, R = прибыль / риск.""")

print("\nСколько нужно правильных сделок, чтобы не терять, если брать только TP1:")
for sym, side, lo, hi, sl, tps in S:
    entry = hi if side=="BUY" else lo
    r1 = abs(tps[0]-entry)/abs(entry-sl)
    need = 1/(1+r1)
    print(f"  {sym} {side:<5} R={r1:.2f} → нужен винрейт {need*100:.0f}%")
