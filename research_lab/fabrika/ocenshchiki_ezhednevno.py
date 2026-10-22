#!/usr/bin/env python3
"""Хук сторожа (22.10.2026): раз в сутки UTC (первый проход после 06:00) запускает forward-оценщики отдельными процессами —
pump4_pereschet.py (PUMP4 V1 + парные V2) и slope_hedge_vpered.py (наклонная + хедж BTC). Отдельный процесс — чтобы chdir и
сетевые ошибки оценщика не задевали сторожа. Таймаут 25 мин на оценщик. Итог (код, последние строки вывода) — в
data/ocenshchiki_ezhednevno.jsonl; ошибка видна в журнале сторожа через возвращаемый статус. Ордеров, ключей, LIVE — нет."""
import datetime as dt, json, subprocess, sys
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; ROOT = LAB.parent
ZH = LAB / "data" / "ocenshchiki_ezhednevno.jsonl"
SOST = LAB / "data" / "ocenshchiki_ezhednevno_sost.json"
OCENSHCHIKI = ("pump4_pereschet.py", "slope_hedge_vpered.py")
CHAS_UTC = 6


def prohod(seychas=None, zapusk=None):
    t = seychas or dt.datetime.now(dt.timezone.utc)
    sost = json.loads(SOST.read_text()) if SOST.exists() else {}
    den = t.date().isoformat()
    if t.hour < CHAS_UTC or sost.get("den") == den:
        return {"status": "NE_SEGODNYA_ILI_UZHE", "posledniy_den": sost.get("den")}
    run = zapusk or (lambda f: subprocess.run([sys.executable, str(LAB / f)], cwd=str(ROOT), capture_output=True, text=True, timeout=1500))
    itog = {}
    for f in OCENSHCHIKI:
        try:
            r = run(f); hvost = (r.stdout or "")[-600:]; itog[f] = dict(kod=r.returncode, hvost=hvost, oshibka=(r.stderr or "")[-300:] if r.returncode else "")
        except Exception as e:
            itog[f] = dict(kod=None, oshibka=f"{type(e).__name__}: {str(e)[:200]}")
    with ZH.open("a") as fh:
        fh.write(json.dumps(dict(kogda=t.isoformat(timespec="seconds"), itog=itog), ensure_ascii=False) + "\n")
    SOST.write_text(json.dumps({"den": den}))
    plohie = [f for f, v in itog.items() if v.get("kod") != 0]
    return {"status": "OSHIBKA" if plohie else "OK", "plohie": plohie}


if __name__ == "__main__":
    print(json.dumps(prohod(), ensure_ascii=False))
