#!/usr/bin/env python3
"""ai_formula_cikl.py — хук сторожа (HUKI.json): автоматическая обработка предложений ИИ (19.10.2026).

Кто угодно (Ollama-раунд, Claude, Codex) кладёт JSON-предложение в data/factory_v3/ai_predlozheniya/. Каждый проход сторожа
берёт не больше одного предложения: проверка (ai_formula_v1.proverit: словарь атомов, без чисел, дубли, бюджет суток,
резерв окна) → предрегистрация пишется и коммитится в ветку research/fabrika-v1 ДО прогона → реестр NEW → SCREEN →
ферма на DEV-окне → вердикт реестра (FAIL → гипотеза KILL). Отклонённые — в otkloneno/ с причиной, выполненные — в obrabotano/.
Деньги, риск, LIVE, CONFIRM-окна этот хук не трогает.
"""
import datetime as dt, json, os, subprocess, sys, tempfile
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; ROOT = LAB.parent
sys.path.insert(0, str(LAB / "factory_v3")); sys.path.insert(0, str(LAB))
PAPKA = LAB / "data" / "factory_v3" / "ai_predlozheniya"
VETKA = "research/fabrika-v1"


def git_commit(put, soobshchenie):
    rel = str(Path(put).resolve().relative_to(ROOT))
    env = dict(os.environ, GIT_INDEX_FILE=tempfile.mktemp(prefix="idx_ai_"))
    g = lambda *a: subprocess.run(["git", *a], cwd=ROOT, env=env, capture_output=True, text=True, check=True).stdout.strip()
    g("read-tree", VETKA); g("update-index", "--add", rel); t = g("write-tree")
    c = g("commit-tree", t, "-p", VETKA, "-m", soobshchenie); g("update-ref", f"refs/heads/{VETKA}", c)
    return c


def prohod(maks=1):
    import importlib, ai_formula_v1 as F
    importlib.reload(F)
    from reestr_v1 import Reestr
    if not PAPKA.exists():
        return dict(predlozheniy=0)
    for x in ("obrabotano", "otkloneno"): (PAPKA / x).mkdir(exist_ok=True)
    rez = []
    for f in sorted(PAPKA.glob("*.json"))[:maks]:
        try:
            pr = json.loads(f.read_text())
        except Exception as e:
            f.replace(PAPKA / "otkloneno" / f.name); rez.append(dict(fayl=f.name, otkaz=f"не JSON: {e}")); continue
        S = Reestr().sostoyanie(); err = F.proverit(pr, S, F.popytok_segodnya())
        if err:
            f.replace(PAPKA / "otkloneno" / f.name)
            (PAPKA / "otkloneno" / (f.stem + ".prichina.txt")).write_text("\n".join(err)); rez.append(dict(id=pr.get("id"), otkaz=err)); continue
        p = F.prereg_put(pr)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True); p.write_text(F.prereg_tekst(pr, S))
        if not F.prereg_v_gite(p):
            c = git_commit(p, f"AI prereg {pr['id']} (auto, ai_formula_cikl, before run)")
            rez.append(dict(id=pr["id"], prereg_commit=c[:7]))
        itog = F.zapustit(pr)
        f.replace(PAPKA / "obrabotano" / f.name); rez.append(dict(id=pr["id"], itog=itog))
    return dict(predlozheniy=len(rez), rez=rez)


if __name__ == "__main__":
    print(json.dumps(prohod(), ensure_ascii=False, indent=1))
