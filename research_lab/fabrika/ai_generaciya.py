#!/usr/bin/env python3
"""ai_generaciya.py — хук сторожа: раз в сутки (UTC) просит локальную Ollama предложить ОДНУ формулу (режим меню,
factory_v3/ai_raund.py --formula --n 1 --zapisat --model qwen3:4b). Дальше файл предложения подхватывает хук
ai_formula_cikl (prereg-коммит до прогона → прогон → вердикт). Только исследование, ордеров нет.

Ничего не делает, если: сегодня уже была успешная генерация; суточный или оконный бюджет ИИ исчерпан; меню пусто.
Ресурсы проверяет сам ai_raund (модель ≤ 8B, /api/ps пуст, свободная память ≥ модель + max(2 ГБ, модель), замок,
таймаут 120 с, дедлайн 300 с) — при нехватке памяти отказ, повтор на следующем часовом проходе."""
import datetime as dt, json, subprocess, sys
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; ROOT = LAB.parent
SOST = LAB / "data" / "factory_v3" / "ai_generaciya_sost.json"
MODEL = "qwen3:4b"


def prohod():
    sys.path.insert(0, str(LAB / "factory_v3"))
    import ai_formula_v1 as F
    from reestr_v1 import Reestr
    segodnya = dt.datetime.now(dt.timezone.utc).date().isoformat()
    s = json.loads(SOST.read_text()) if SOST.exists() else {}
    if s.get("uspeh_den") == segodnya:
        return {"status": "uzhe_segodnya"}
    S = Reestr().sostoyanie()
    if F.popytok_segodnya() >= F.MAKS_POPYTOK_V_SUTKI:
        return {"status": "sutochnyy_byudzhet_ischerpan"}
    o = S["okna"][F.OKNO_II]
    ostalos = int(o.get("byudzhet") or 0) - sum(1 for p in S["popytki"].values() if p["okno"] == F.OKNO_II)
    if ostalos <= F.REZERV_OKNA:
        return {"status": "okonnyy_byudzhet_II_ischerpan", "okno": F.OKNO_II, "ostalos": ostalos}
    if not F.menyu(S):
        return {"status": "menyu_pusto"}
    r = subprocess.run([sys.executable, str(LAB / "factory_v3" / "ai_raund.py"), "--formula", "--n", "1", "--zapisat",
                        "--model", MODEL], cwd=str(ROOT), capture_output=True, text=True, timeout=330)
    vyvod = (r.stdout + r.stderr).strip()[-600:]
    ok = "V_OCHEREDI_HUKA" in vyvod
    s.update(posledniy=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), vyvod=vyvod)
    if ok:
        s["uspeh_den"] = segodnya
    SOST.parent.mkdir(parents=True, exist_ok=True); SOST.write_text(json.dumps(s, ensure_ascii=False, indent=1))
    return {"status": "v_ocheredi" if ok else ("otkaz" if "ОТКАЗ" in vyvod else "net_predlozheniya"), "vyvod": vyvod[-200:]}


if __name__ == "__main__":
    print(json.dumps(prohod(), ensure_ascii=False))
