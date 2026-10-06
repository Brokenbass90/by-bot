#!/usr/bin/env python3
"""reestr_strategiy.py — Strategy Registry + журнал множественных проверок (FACTORY AUTONOMY V1).

data/fabrika_xs/REESTR_STRATEGIY.json — машиночитаемый реестр: одна запись на механизм-измерение:
  id, semya, mehanizm, dannye (источник), okno_dannyh (ключ окна для учёта множественных проверок), prereg, prereg_sha256,
  verdikt (KILL/READY_FOR_BUILD/PNL_FAIL/BLOCKED_DATA/…), metriki, nezavisimost (теги), korrelyacii (теги),
  vpered (статус вперёд-тени), ispolnenie (статус у Codex), dengi (решение владельца), kvitanciya, kogda.
Журнал проверок = число ИЗРАСХОДОВАННЫХ исходов на каждом окне данных (okno_dannyh): растёт с каждым терминалом.
Пишет только детерминированный код (контроллер/Claude); ИИ сюда не пишет.
    python3 research_lab/fabrika/reestr_strategiy.py            сводка
"""
from __future__ import annotations
import datetime as dt, json, sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
F = LAB / "data" / "fabrika_xs" / "REESTR_STRATEGIY.json"
POLYA = ("id", "semya", "mehanizm", "dannye", "okno_dannyh", "prereg", "prereg_sha256", "verdikt", "metriki",
         "nezavisimost", "korrelyacii", "vpered", "ispolnenie", "dengi", "kvitanciya", "kogda")


def zagruzit(f: Path = F) -> dict:
    return json.loads(f.read_text()) if f.exists() else {"zapisi": {}}


def sohranit(r: dict, f: Path = F):
    f.parent.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(r, ensure_ascii=False, indent=1))


def zapisat(zapis: dict, f: Path = F) -> dict:
    """Добавить/обновить запись. Терминальный вердикт неизменяем: попытка сменить его — ошибка."""
    r = zagruzit(f); z = r["zapisi"].get(zapis["id"], {})
    if z.get("verdikt") and zapis.get("verdikt") and z["verdikt"] != zapis["verdikt"]:
        raise ValueError(f"{zapis['id']}: терминальный вердикт {z['verdikt']} неизменяем")
    z.update({k: v for k, v in zapis.items() if k in POLYA and v is not None})
    z.setdefault("kogda", dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    r["zapisi"][zapis["id"]] = z; sohranit(r, f); return z


def zhurnal_proverok(f: Path = F) -> dict:
    """сколько исходов израсходовано на каждом окне данных"""
    out = {}
    for z in zagruzit(f)["zapisi"].values():
        if z.get("verdikt"):
            out[z.get("okno_dannyh", "?")] = out.get(z.get("okno_dannyh", "?"), 0) + 1
    return out


def svodka(f: Path = F) -> str:
    r = zagruzit(f)["zapisi"]; s = [f"стратегий в реестре: {len(r)}"]
    for z in sorted(r.values(), key=lambda z: z.get("kogda", "")):
        s.append(f"  {z['id']:<28} {z.get('verdikt','—'):<22} вперёд: {z.get('vpered','—'):<18} исполнение: {z.get('ispolnenie','—')}")
    s.append("журнал проверок (израсходовано исходов на окне данных):")
    for k, v in sorted(zhurnal_proverok(f).items(), key=lambda x: -x[1]):
        s.append(f"  {k:<40} {v}")
    return "\n".join(s)


if __name__ == "__main__":
    print(svodka())
