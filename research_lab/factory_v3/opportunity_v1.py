#!/usr/bin/env python3
"""opportunity_v1.py — единый формат записи возможности (OpportunityRecord V1), 14.10.2026.

Любая семья (поглощение, ликвидации, KITY, Elder, FX/золото) отдаёт одинаковые строки → общая таблица для будущего мозга
(LightGBM на всех ногах) и для DuckDB/pandas. Формат хранения: CSV.gz + схема (pyarrow/duckdb в .venv нет; конвертация в Parquet —
одной командой позже, без смены схемы). Озеро данных НЕ является воротами для экспериментов.

Поля (порядок фиксирован):
  ts_resheniya_ms  — момент решения (когда решение могло быть принято)
  ts_priznakov_ms  — самый поздний момент данных, вошедших в признаки (обязан быть ≤ ts_resheniya_ms)
  ts_vhoda_ms      — момент входа (обязан быть ≥ ts_resheniya_ms)
  simvol, mehanizm, versiya, storona (+1/−1)
  cena_vhoda (может быть пусто, если нога считает исход в R), izderzhki_dolya (круг), priznaki_json (словарь признаков, известных к ts_priznakov_ms)
  ts_vyhoda_ms, cena_vyhoda, fanding_dolya, dohod_net_dolya   — ИСХОД (заполняется отдельно, после закрытия; может быть пусто)
Проверка причинности встроена: запись с нарушенным порядком времени отклоняется.
"""
import csv, gzip, json
from pathlib import Path

POLYA = ["ts_resheniya_ms", "ts_priznakov_ms", "ts_vhoda_ms", "simvol", "mehanizm", "versiya", "storona", "cena_vhoda",
         "izderzhki_dolya", "priznaki_json", "ts_vyhoda_ms", "cena_vyhoda", "fanding_dolya", "dohod_net_dolya"]


class NarushenieVremeni(Exception):
    pass


def zapis(ts_resheniya_ms, ts_priznakov_ms, ts_vhoda_ms, simvol, mehanizm, versiya, storona, cena_vhoda, izderzhki_dolya,
          priznaki, ts_vyhoda_ms=None, cena_vyhoda=None, fanding_dolya=None, dohod_net_dolya=None):
    if not ts_priznakov_ms <= ts_resheniya_ms <= ts_vhoda_ms:
        raise NarushenieVremeni(f"{simvol} {mehanizm}: признаки {ts_priznakov_ms} / решение {ts_resheniya_ms} / вход {ts_vhoda_ms}")
    if ts_vyhoda_ms is not None and ts_vyhoda_ms <= ts_vhoda_ms:
        raise NarushenieVremeni(f"{simvol}: выход не позже входа")
    if storona not in (1, -1): raise ValueError("storona ∈ {+1, −1}")
    return dict(ts_resheniya_ms=int(ts_resheniya_ms), ts_priznakov_ms=int(ts_priznakov_ms), ts_vhoda_ms=int(ts_vhoda_ms),
                simvol=simvol, mehanizm=mehanizm, versiya=versiya, storona=int(storona), cena_vhoda=None if cena_vhoda is None else float(cena_vhoda),
                izderzhki_dolya=float(izderzhki_dolya), priznaki_json=json.dumps(priznaki, sort_keys=True),
                ts_vyhoda_ms=ts_vyhoda_ms, cena_vyhoda=cena_vyhoda, fanding_dolya=fanding_dolya, dohod_net_dolya=dohod_net_dolya)


def zapisat(put, zapisi):
    put = Path(put); put.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(put, "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=POLYA); w.writeheader()
        for z in zapisi: w.writerow(z)
    (put.parent / (put.name.replace(".csv.gz", "") + ".schema.json")).write_text(json.dumps(dict(format="OpportunityRecord V1", polya=POLYA)))


def prochitat(put):
    with gzip.open(put, "rt", newline="") as f:
        return list(csv.DictReader(f))
