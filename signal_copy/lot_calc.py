# -*- coding: utf-8 -*-
"""Расчёт лота по тем же двум сигналам. Терминал даёт loss_per_lot, мы делим."""

SPECS = {  # в бою эти числа приходят из терминала, не из кода
    "XAUUSD": dict(contract=100,     vol_min=0.01, vol_step=0.01),
    "EURUSD": dict(contract=100_000, vol_min=0.01, vol_step=0.01),
}
SIGNALS = [
    ("XAUUSD", "BUY", 4353.7,  4361.63, 4347.11),
    ("EURUSD", "BUY", 1.15950, 1.16034, 1.15900),
]
RISK_PCT = 0.5

print(f"{'сигнал':<9} {'депозит':>8} {'риск':>7} {'$/лот':>9} {'сырой лот':>10} {'лот':>6} {'реальный риск':>16}")
print("-" * 72)
for sym, side, e_min, e_max, sl in SIGNALS:
    sp = SPECS[sym]
    entry = e_max if side == "BUY" else e_min      # худший край зоны — консервативно
    loss_per_lot = abs(entry - sl) * sp["contract"]
    for bal in (1000, 3000, 10000):
        risk_cash = bal * RISK_PCT / 100
        raw = risk_cash / loss_per_lot
        lot = round(raw / sp["vol_step"]) * sp["vol_step"]
        if lot < sp["vol_min"]:
            real = sp["vol_min"] * loss_per_lot
            verdict = f"ОТКАЗ · мин.лот = ${real:,.0f} ({real/bal*100:.2f}%)"
            lot_s = "—"
        else:
            real = lot * loss_per_lot
            verdict = f"${real:,.2f} ({real/bal*100:.2f}%)"
            lot_s = f"{lot:.2f}"
        print(f"{sym:<9} {bal:>8,} {risk_cash:>6.1f}$ {loss_per_lot:>9,.0f} {raw:>10.4f} {lot_s:>6} {verdict:>16}")
    print()
