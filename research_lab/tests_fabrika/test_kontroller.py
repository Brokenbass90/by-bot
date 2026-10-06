#!/usr/bin/env python3
"""Тесты FACTORY AUTONOMY V1 (контроллер) на синтетике.   python3 research_lab/tests_fabrika/test_kontroller.py"""
import json, sys, tempfile
from pathlib import Path
LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "fabrika")); sys.path.insert(0, str(LAB / "tests_fabrika"))
import kontroller as KO  # noqa: E402
import reestr_strategiy as RS  # noqa: E402
import test_sudya_xs as T  # noqa: E402
ok = 0
def proverka(i, u):
    global ok
    assert u, i; ok += 1; print("PASS", i)

def main():
    lab = Path(tempfile.mkdtemp()) / "lab"; T.sintetika(lab / "data" / "sint")
    (lab / "generator").mkdir(parents=True); (lab / "generator" / "kladbische.json").write_text(json.dumps([{"semya": "MERTVAYA"}]))
    (lab / "fabrika").mkdir(); (lab / "fabrika" / "digest_nablyudenie.json").write_text(json.dumps({"teni": {}, "arhivy": ["sint"]}))
    (lab / "diag.json").write_text("{}")
    sp = json.loads((LAB / "prereg" / "KITY_M3_POTOK.json").read_text()); sp.pop("legacy_kvitanciya")
    sp.update(dannye="sint", okno_dannyh="sint_okno", diagnostika={"fayl": "diag.json", "izmerenie_vybrano": "M2"})
    och = lab / "data" / "fabrika_xs" / "ochered"; och.mkdir(parents=True)
    def q(name, **kw): (och / f"{name}.json").write_text(json.dumps(dict(sp, **kw)))
    q("A", id="NEODOBREN")
    q("B", id="MERTV", semya="mertvaya", odobreno={"kem": "Claude"})
    q("C", id="BEZ_DIAG", semya="X1", odobreno={"kem": "Claude"}, diagnostika={})
    q("D", id="ZHIV", semya="ZHIVAYA", odobreno={"kem": "Claude"})
    k = KO.Kontroller(lab)
    proverka("шаг 1: замок на живом", k.shag() == "ZAMOK ZHIV")
    proverka("неодобренный не взят", (och / "A.json").exists())
    proverka("кладбище отклонено", (och / "B.otkaz").exists())
    proverka("без диагностики признаков отклонено", (och / "C.otkaz").exists())
    proverka("WIP=1: второй не берётся, пока слот занят", k.slot() == {"aktivnye": ["ZHIV"]})
    r2 = k.shag(); proverka("шаг 2: один прогон до терминала", r2.startswith("TERMINAL ZHIV"))
    st = r2.split()[-1]
    rr = RS.zagruzit(k.reestr)["zapisi"]["ZHIV"]
    proverka("реестр записан с вердиктом и окном", rr["verdikt"] == st and rr["okno_dannyh"] == "sint_okno")
    proverka("сообщение владельцу на терминал", "ZHIV → " in k.vladelec.read_text())
    if st == "READY_FOR_BUILD":
        proverka("пакет Codex создан", (k.fx / "ZHIV" / "PAKET_CODEX.md").exists())
    else:
        proverka("KILL → кладбище", any(x["semya"] == "ZHIVAYA" for x in json.loads(k.kl_f.read_text())))
    try:
        RS.zapisat(dict(id="ZHIV", verdikt="OTHER"), k.reestr); proverka("вердикт в реестре неизменяем", False)
    except ValueError:
        proverka("вердикт в реестре неизменяем", True)
    q("E", id="ZHIV", semya="DRUGAYA", odobreno={"kem": "Claude"})
    proverka("повтор id отклонён", k.shag() == "PUSTO" and (och / "E.otkaz").exists())
    for n in range(KO.LIMIT_PROVEROK):                       # забиваем окно до лимита
        RS.zapisat(dict(id=f"F{n}", okno_dannyh="perepolnennoe", verdikt="KILL"), k.reestr)
    q("G", id="NA_PEREPOLNENNOM", semya="G1", odobreno={"kem": "Claude"}, okno_dannyh="perepolnennoe")
    proverka("множественность: окно исчерпано → BLOCKED", k.shag() == "PUSTO" and (och / "G.otkaz").exists()
             and "нужны новые данные" in k.vladelec.read_text())
    # скрипт-судья
    (lab / "sudya_test.py").write_text("import json\nfrom pathlib import Path\nPath('rez_t.json').write_text(json.dumps({'status':'KILL','PRIMARY':{'t':0.1}}))\n")
    q("H", id="SKRIPT", semya="S1", odobreno={"kem": "Claude"}, tip_sudi="skript", skript="sudya_test.py", rezultat="rez_t.json", vhodnye_fayly=["diag.json"])
    proverka("скрипт: замок", k.shag() == "ZAMOK SKRIPT")
    (lab / "sudya_test.py").write_text("print('изменён')\n")
    proverka("скрипт изменён после замка → отказ", k.shag().startswith("OTKAZ"))
    zz = k.cep.read_text().splitlines(); proverka("цепочка замков ведётся", len(zz) >= 2)
    k.cep.write_text("\n".join(zz[:-1] + [zz[-1].replace('"SKRIPT"', '"PODMENA"')]) + "\n")
    try:
        k.cepochka(); proverka("подмена в цепочке обнаружена", False)
    except Exception:
        proverka("подмена в цепочке обнаружена", True)
    print(f"ВСЕ ТЕСТЫ: {ok} PASS")

if __name__ == "__main__":
    main()
