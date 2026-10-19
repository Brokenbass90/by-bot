#!/usr/bin/env python3
"""ai_generaciya.py — хук сторожа: не чаще раза в сутки (UTC) просит локальную Ollama ОДНО предложение-формулу
(factory_v3/ai_raund.py --formula --n 1 --zapisat --model qwen3:4b, режим меню v1). Дальше файл подхватывает
ai_formula_cikl (prereg-коммит до прогона → прогон → вердикт). Только исследование: DATA_ONLY / ORDERS_OFF.

Работа владельца на Маке важнее фабрики (PM 19.10):
- ресурсы проверяет ai_raund: свободная память ≥ модель + max(1.5 ГБ, ½ модели), давление памяти macOS = норма,
  loadavg/ядра ≤ 75 %, /api/ps пуст, 2 потока, таймаут 300 с, дедлайн 600 с, выгрузка модели сразу;
- отказ по ресурсам или недоступная Ollama → SKIP с отсрочкой 1 → 2 → 4 → 8 ч; не больше 4 попыток в сутки;
- квота: не больше 5 предложений за ISO-неделю; суточный и оконный бюджет ИИ — из реестра;
- каждый проход (и пропуск) пишется в `data/factory_v3/ai_generaciya_zhurnal.jsonl` (только дописывается)."""
import datetime as dt, json, subprocess, sys
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; ROOT = LAB.parent
SOST = LAB / "data" / "factory_v3" / "ai_generaciya_sost.json"
ZH = LAB / "data" / "factory_v3" / "ai_generaciya_zhurnal.jsonl"
MODEL = "qwen3:4b"
MAKS_POPYTOK_DEN, MAKS_V_NEDELYU, OTSROCHKA_CH = 4, 5, (1, 2, 4, 8)


def _sostoyanie_reestra():
    sys.path.insert(0, str(LAB / "factory_v3"))
    import ai_formula_v1 as F
    from reestr_v1 import Reestr
    S = Reestr().sostoyanie(); o = S["okna"][F.OKNO_II]
    ostalos = int(o.get("byudzhet") or 0) - sum(1 for p in S["popytki"].values() if p["okno"] == F.OKNO_II)
    return dict(segodnya=F.popytok_segodnya(), sutochnyy=F.MAKS_POPYTOK_V_SUTKI, ostalos=ostalos, rezerv=F.REZERV_OKNA,
                menyu=len(F.menyu(S)))


def _zapusk():
    r = subprocess.run([sys.executable, str(LAB / "factory_v3" / "ai_raund.py"), "--formula", "--n", "1", "--zapisat",
                        "--model", MODEL], cwd=str(ROOT), capture_output=True, text=True, timeout=660)
    return (r.stdout + r.stderr).strip()[-800:]


def _zhurnal(z):
    ZH.parent.mkdir(parents=True, exist_ok=True)
    with ZH.open("a") as f:
        f.write(json.dumps(z, ensure_ascii=False) + "\n")


def prohod(seychas=None, sostoyanie_fn=_sostoyanie_reestra, zapusk_fn=_zapusk):
    t = seychas or dt.datetime.now(dt.timezone.utc); den = t.date().isoformat()
    ned = "%d-W%02d" % t.isocalendar()[:2]
    s = json.loads(SOST.read_text()) if SOST.exists() else {}
    if s.get("den") != den:
        s.update(den=den, popytok_den=0, sleduyushchaya=None)
    if s.get("nedelya") != ned:
        s.update(nedelya=ned, v_nedelyu=0)

    def itog(status, **kw):
        z = dict(kogda=t.isoformat(timespec="seconds"), status=status, **kw); _zhurnal(z)
        SOST.parent.mkdir(parents=True, exist_ok=True); SOST.write_text(json.dumps(s, ensure_ascii=False, indent=1))
        return z

    if s.get("uspeh_den") == den:
        return {"status": "uzhe_segodnya"}                       # не пишем в журнал каждый час
    if s.get("sleduyushchaya") and t.isoformat() < s["sleduyushchaya"]:
        return {"status": "otsrochka", "do": s["sleduyushchaya"]}
    if s["popytok_den"] >= MAKS_POPYTOK_DEN:
        return {"status": "dnevnoy_limit_popytok"}
    if s["v_nedelyu"] >= MAKS_V_NEDELYU:
        return itog("nedelnaya_kvota", v_nedelyu=s["v_nedelyu"])
    r = sostoyanie_fn()
    if r["segodnya"] >= r["sutochnyy"]:
        return itog("sutochnyy_byudzhet_reestra")
    if r["ostalos"] <= r["rezerv"]:
        return itog("okonnyy_byudzhet_II_ischerpan", ostalos=r["ostalos"])
    if not r["menyu"]:
        return itog("menyu_pusto")
    s["popytok_den"] += 1
    vyvod = zapusk_fn()
    if "V_OCHEREDI_HUKA" in vyvod:
        s.update(uspeh_den=den, sleduyushchaya=None); s["v_nedelyu"] += 1
        return itog("v_ocheredi", vyvod=vyvod[-300:])
    k = s["popytok_den"] - 1
    s["sleduyushchaya"] = (t + dt.timedelta(hours=OTSROCHKA_CH[min(k, len(OTSROCHKA_CH) - 1)])).isoformat()
    vid = "skip_ollama" if "недоступна" in vyvod else ("skip_resursy" if "ОТКАЗ" in vyvod else "otkloneno_proverkoy")
    return itog(vid, vyvod=vyvod[-300:], sleduyushchaya=s["sleduyushchaya"])


if __name__ == "__main__":
    print(json.dumps(prohod(), ensure_ascii=False))
