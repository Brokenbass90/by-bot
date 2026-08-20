# -*- coding: utf-8 -*-
"""Проверка предохранителей на том самом случае, что выстрелил вживую."""
from sizing import calculate_lot

Q = {"EURUSD": 1.16619}
BASE = dict(symbol="XAUUSD", contract_size=100.0, currency_profit="USD",
            volume_min=0.01, volume_max=50, volume_step=0.01, digits=2)

CASES = [
    ("без котировок (то, что случилось)",  dict(BASE, bid=0, ask=0, tick_size=0.01, tick_value=0.1)),
    ("котировки есть, tick_value мусорный", dict(BASE, bid=4390, ask=4390.3, tick_size=0.01, tick_value=0.1)),
    ("tick_value в долларах, счёт в евро",  dict(BASE, bid=4390, ask=4390.3, tick_size=0.01, tick_value=1.0)),
    ("tick_value верный (уже в евро)",      dict(BASE, bid=4390, ask=4390.3, tick_size=0.01, tick_value=0.8575)),
    ("tick_value пуст, считаем по контракту",dict(BASE, bid=4390, ask=4390.3, tick_size=0, tick_value=0)),
]
for name, spec in CASES:
    d = calculate_lot(spec=spec, entry=4398.0, stop=4377.0, equity=2000.0,
                      risk_pct=0.5, account_ccy="EUR", quotes=Q, max_risk_pct=2.0)
    if d.accepted:
        print(f"✅ {name:<40} лот {d.lot:<6} риск €{d.actual_risk:>7.2f} ({d.actual_risk_pct:.2f}%)  [{d.reason}]")
    else:
        print(f"⛔ {name:<40} ОТКАЗ — {d.reason} {d.note}")

# Крупный шаг лота не должен округлить риск вверх.
d = calculate_lot(
    spec=dict(BASE, bid=100, ask=101, tick_size=0, tick_value=0,
              contract_size=1.0, currency_profit="EUR", volume_step=0.1,
              volume_min=0.1),
    entry=101, stop=91, equity=1000, risk_pct=0.55, account_ccy="EUR",
    quotes={}, max_risk_pct=2.0,
)
assert d.accepted and d.lot == 0.5, d
assert d.actual_risk_pct <= 0.55, d
print("OK: volume_step is floored; actual risk never exceeds requested risk")
