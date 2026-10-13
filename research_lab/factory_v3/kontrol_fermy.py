#!/usr/bin/env python3
"""kontrol_fermy.py — еженедельная «прозвонка» фабрики (13.10.2026). Только чтение данных; реестры — временные.
  1. Контрольные образцы: ферма + шаблон обязаны воспроизвести числа замороженных судей (KITY M3 / SPOT_A / SPOT_B) до знака.
  2. Калибровка подложенным edge: детерминированные семена → результат обязан совпасть с эталоном KALIBROVKA_FERMY.json;
     дополнительно пороги здравого смысла: ложные срабатывания ≤ 5%, мощность на 150 bps ≥ 50%.
Итог: data/factory_v3/KONTROL_FERMY.json со статусом OK / TREVOGA и списком расхождений. Сторож запускает раз в 7 дней.
    python3 research_lab/factory_v3/kontrol_fermy.py
"""
import datetime as dt, json, sys, tempfile, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import kalibrovka_fermy as K, validaciya_fermy as V

D = HERE.parent / "data" / "factory_v3"; OUT = D / "KONTROL_FERMY.json"


def kontrol():
    t0 = time.time(); problemy = []; tmp = Path(tempfile.mkdtemp())
    obrazcy = {}
    for s in V.SLUCHAI:
        r = V.main(s, put_reestra=tmp / f"v_{s}.jsonl", pisat=False); obrazcy[s] = r["status"]
        if r["status"] != "REPRODUCED": problemy.append(f"образец {s}: {r['ferma_metrika']} ≠ {r['etalon']}")
    kal = K.main(20, put=tmp / "kal.jsonl", pisat=False)
    et = D / "KALIBROVKA_FERMY.json"
    if et.exists():
        e = json.loads(et.read_text())
        if (e["lozhnye_srabatyvaniya"], e["moshchnost"]) != (kal["lozhnye_srabatyvaniya"], kal["moshchnost"]):
            problemy.append(f"калибровка изменилась: эталон {e['moshchnost']} / ЛС {e['lozhnye_srabatyvaniya']}, сейчас {kal['moshchnost']} / ЛС {kal['lozhnye_srabatyvaniya']}")
    else:
        problemy.append("нет эталона KALIBROVKA_FERMY.json")
    if kal["lozhnye_srabatyvaniya"] > 0.05: problemy.append(f"ложные срабатывания {kal['lozhnye_srabatyvaniya']} > 5%")
    if kal["moshchnost"].get("150_bps", 0) < 0.5: problemy.append(f"мощность на 150 bps {kal['moshchnost'].get('150_bps')} < 50%")
    rez = dict(kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), status="OK" if not problemy else "TREVOGA",
               obrazcy=obrazcy, kalibrovka=dict(ls=kal["lozhnye_srabatyvaniya"], moshchnost=kal["moshchnost"]),
               problemy=problemy, sekund=round(time.time() - t0, 1))
    D.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(rez, ensure_ascii=False, indent=1))
    return rez


def pora(dney=7):
    return not OUT.exists() or (time.time() - OUT.stat().st_mtime) > dney * 86400


if __name__ == "__main__":
    print(json.dumps(kontrol(), ensure_ascii=False, indent=1))
