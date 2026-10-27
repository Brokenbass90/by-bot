#!/usr/bin/env python3
"""avtopodacha.py — Factory, исправление №3: автоподача заранее зарегистрированных заявок в конвейер без агента.
Заявка = файл data/factory_v3/gotovye_zayavki/<id>.json {spec, karta, prereg}; prereg-файл обязан существовать и быть
закоммичен (проверка: файл есть в git HEAD). Подаётся один раз (повтор id в очереди — пропуск). Live-контракты не трогает."""
import json, subprocess, sys
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB / "factory_v3"))
PAPKA = LAB / "data/factory_v3/gotovye_zayavki"


def v_gite(put):
    try:
        # 19.10: исследовательская ветка — research/fabrika-v1; рабочее дерево может стоять на ветке Codex (HEAD ≠ наша ветка)
        return any(subprocess.run(["git", "cat-file", "-e", f"{ref}:research_lab/{put}"], cwd=LAB.parent, capture_output=True, timeout=60).returncode == 0
                   for ref in ("research/fabrika-v1", "HEAD"))
    except Exception:
        return False


def prohod():
    import konveyer_v1 as K
    if not PAPKA.exists(): return dict(podano=0, zhdut=0)
    uzhe = {z["spec"]["id"] for z in K.chitat(K.OCHERED) if z["tip"] == "zayavka"}
    podano, zhdut, otkaz = [], [], []
    for p in sorted(PAPKA.glob("*.json")):
        z = json.loads(p.read_text()); i = z["spec"]["id"]
        if i in uzhe: continue
        if not v_gite(z.get("prereg", "")): zhdut.append(i); continue        # prereg не закоммичен — не подаём
        try:
            K.podat(z["spec"], z["karta"]); podano.append(i)
        except Exception as e:
            otkaz.append(f"{i}: {str(e)[:80]}")
    return dict(podano=podano, zhdut_prereg=zhdut, otkaz=otkaz)


if __name__ == "__main__":
    print(prohod())
