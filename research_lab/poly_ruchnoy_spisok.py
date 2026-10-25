#!/usr/bin/env python3
"""poly_ruchnoy_spisok.py — «ручной режим» Polymarket (25.10.2026): список сегодняшних входов тени POLY_YES_PEREPLATA
в виде инструкции для человека. Только чтение журнала решений (исходы и доход не читаются). Пока нет PASS и GO владельца —
это ПРОВЕРКА исполнимости вручную, не сигнал к сделке.
    .venv/bin/python3 research_lab/poly_ruchnoy_spisok.py           # решения последних 26 часов
    .venv/bin/python3 research_lab/poly_ruchnoy_spisok.py --chasov 72"""
import datetime as dt, json, sys, time
from pathlib import Path
ZH = Path(__file__).resolve().parent / "data" / "poly_yes_ten.jsonl"
MES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def spisok(rows, seychas_ms, chasov=26):
    out = []
    for r in rows:
        if r.get("tip") != "reshenie" or r.get("status") != "VHOD" or seychas_ms - r["reshenie_ms"] > chasov * 3600_000: continue
        d = dt.datetime.fromtimestamp(r["raschet_ms"] / 1000, dt.timezone.utc)
        x = f"{r['X']:,.0f}" if r["X"] >= 100 else f"{r['X']:g}"
        out.append(dict(vopros=f"Will the price of {r['aktiv']} be above ${x} on {MES[d.month - 1]} {d.day}?",
                        kupit="NO", na_usd=10, limit_cena=round(min(0.999, r["best_ask_no"] + 0.01), 3),
                        cena_teni=r["cena_no"], raschet_utc=d.strftime("%d.%m %H:%M UTC"),
                        reshenie_utc=dt.datetime.fromtimestamp(r["reshenie_ms"] / 1000, dt.timezone.utc).strftime("%d.%m %H:%M UTC")))
    return out


if __name__ == "__main__":
    ch = int(sys.argv[sys.argv.index("--chasov") + 1]) if "--chasov" in sys.argv else 26
    rows = [json.loads(l) for l in ZH.read_text().splitlines() if l.strip()]
    sp = spisok(rows, int(time.time() * 1000), ch)
    print(f"Polymarket — входы тени за {ch} ч (ПРОВЕРКА исполнимости; деньги только после PASS и GO): {len(sp)}")
    for s in sp:
        print(f"• {s['vopros']}\n  купить {s['kupit']} на ${s['na_usd']}, лимит цены ≤ {s['limit_cena']} (цена тени {s['cena_teni']:.3f} с комиссией), "
              f"решение {s['reshenie_utc']}, расчёт {s['raschet_utc']}")
