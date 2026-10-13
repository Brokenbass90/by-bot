#!/usr/bin/env python3
"""Ремонт M5 тени Breakout после двойного процесса (13.10.2026). Логику стратегии и prereg НЕ трогает.
Два процесса breakout_ten.py --cikl писали в одни файлы → блоки дублей (значения идентичны) → MTFContractError на всех монетах
с 12.10 10:04 UTC. Скрипт: оставляет первое вхождение каждого ts, проверяет (1) дубли идентичны, (2) непрерывность +5 мин,
(3) префикс state[:source_count] не изменился (sha). По умолчанию сухой прогон; --primenit — резервная копия в m5_bak_dubli/
и перезапись. Запускать ТОЛЬКО при остановленных процессах тени.
"""
import hashlib, json, shutil, sys
from pathlib import Path
D = Path(__file__).resolve().parents[1] / "data" / "breakout_ten"; M5 = 300_000
PRIM = "--primenit" in sys.argv; BAK = D / "m5_bak_dubli"
itog = {}
for f in sorted((D / "m5").glob("*.jsonl")):
    s = f.stem; rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    seen, out, konflikt = {}, [], 0
    for r in rows:
        if r[0] in seen:
            konflikt += seen[r[0]] != r
            continue
        seen[r[0]] = r; out.append(r)
    dyry = sum(1 for a, b in zip(out, out[1:]) if b[0] - a[0] != M5)
    st = json.loads((D / "state" / f"{s}.json").read_text())["payload"]; sc = st["source_count"]
    prefiks_ok = rows[:sc] == out[:sc]
    itog[s] = dict(bylo=len(rows), stalo=len(out), dubley=len(rows) - len(out), konflikt=konflikt, dyry=dyry, prefiks_ok=prefiks_ok)
    if konflikt or dyry or not prefiks_ok:
        print("СТОП", s, itog[s]); sys.exit(1)
    if PRIM and len(out) != len(rows):
        BAK.mkdir(exist_ok=True); shutil.copy2(f, BAK / f.name)
        f.write_text("".join(json.dumps(r) + "\n" for r in out))
print(json.dumps(dict(primeneno=PRIM, monet=len(itog), dubley=sum(v["dubley"] for v in itog.values()),
                      vse_ok=True), ensure_ascii=False))
