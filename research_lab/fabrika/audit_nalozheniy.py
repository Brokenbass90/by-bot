#!/usr/bin/env python3
"""audit_nalozheniy.py — постоянный аудит теней (27.10.2026, Claude): доля решений, наложенных на ещё открытую позицию той же
монеты. Причина: у ETS2S 78 % решений тени оказались повторными входами (ETS2S_POVTOR_ITOG_2026_10_27.md), у ATT1 21 %.
Хук сторожа (fabrika/HUKI.json). Только чтение журналов; выход `data/storozh/nalozheniya.json`.
Тревога, если наложено > 5 % — экономика такой тени не годится для вердикта без непрерывного повтора."""
import collections, glob, json, statistics, time
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; D = LAB / "data"; OUT = D / "storozh" / "nalozheniya.json"
H = 3_600_000; POROG = 0.05

def bez_nalozheniy(L, zhdat=0):
    """Решения, принимаемые по порядку времени, если монета свободна (одна позиция на монету). Для честной оценки журналов
    с наложениями (ten.py до --blok-zhurnal). Выход позиции ≈ ts + (barov + zhdat + 2) ч."""
    svob, out = {}, []
    for x in sorted(L, key=lambda x: int(x["ts"])):
        if x.get("barov") is None or x.get("R") is None: continue
        if int(x["ts"]) < svob.get(x["sym"], -1): continue
        out.append(x); svob[x["sym"]] = int(x["ts"]) + (int(x["barov"]) + zhdat + 2) * H
    return out

def dolya_nalozheniy(L):
    L = [x for x in L if x.get("barov") is not None and x.get("R") is not None]
    return 1 - len(bez_nalozheniy(L)) / len(L) if L else 0.0

def odin(p):
    L = []
    for s in p.open(encoding="utf-8"):
        try: x = json.loads(s)
        except Exception: continue
        if isinstance(x, dict) and "R" in x and "sym" in x and "ts" in x and x.get("barov") is not None and x.get("R") is not None:
            L.append(x)
    if not L: return None
    by = collections.defaultdict(list)
    for x in L: by[x["sym"]].append((int(x["ts"]), int(x["ts"]) + (int(x["barov"]) + 2) * H))
    o = 0
    for v in by.values():
        v.sort(); e = -1
        for a, b in v:
            if a < e: o += 1
            e = max(e, b)
    return dict(ishodov=len(L), nalozheno=o, dolya=round(o / len(L), 3), sred_R=round(statistics.mean(x["R"] for x in L), 4),
                status="TREVOGA" if o / len(L) > POROG else "OK")

def prohod():
    rez = {}
    for f in sorted(glob.glob(str(D / "ten_*.jsonl"))) + sorted(glob.glob(str(D / "*" / "zhurnal*.jsonl"))):
        r = odin(Path(f))
        if r: rez[Path(f).relative_to(D).as_posix()] = r
    out = dict(kogda=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), porog=POROG, zhurnaly=rez,
               trevogi=[k for k, v in rez.items() if v["status"] == "TREVOGA"])
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return {"trevog": len(out["trevogi"]), "spisok": out["trevogi"]}

if __name__ == "__main__":
    print(json.dumps(prohod(), ensure_ascii=False))
