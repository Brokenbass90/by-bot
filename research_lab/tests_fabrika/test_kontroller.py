#!/usr/bin/env python3
"""Тесты среза 4 на синтетике.   python3 research_lab/tests_fabrika/test_kontroller.py"""
import json, sys, tempfile
from pathlib import Path
LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "fabrika")); sys.path.insert(0, str(LAB / "tests_fabrika"))
import kontroller as KO  # noqa: E402
import test_sudya_xs as T  # noqa: E402
ok = 0
def proverka(i, u):
    global ok
    assert u, i; ok += 1; print("PASS", i)

def main():
    lab = Path(tempfile.mkdtemp()) / "lab"; T.sintetika(lab / "data" / "sint")
    (lab / "generator").mkdir(parents=True); (lab / "generator" / "kladbische.json").write_text(json.dumps([{"semya": "MERTVAYA"}]))
    (lab / "fabrika").mkdir(); (lab / "fabrika" / "digest_nablyudenie.json").write_text(json.dumps({"teni": {}, "arhivy": ["sint"]}))
    sp = json.loads((LAB / "prereg" / "KITY_M3_POTOK.json").read_text()); sp.pop("legacy_kvitanciya")
    och = lab / "data" / "fabrika_xs" / "ochered"; och.mkdir(parents=True)
    (och / "A_NEODOBREN.json").write_text(json.dumps(dict(sp, id="NEODOBREN", dannye="sint")))
    (och / "B_MERTV.json").write_text(json.dumps(dict(sp, id="MERTV", semya="mertvaya", dannye="sint", odobreno={"kem": "Claude"})))
    (och / "C_ZHIV.json").write_text(json.dumps(dict(sp, id="ZHIV", semya="ZHIVAYA", dannye="sint", odobreno={"kem": "Claude"})))
    k = KO.Kontroller(lab)
    r1 = k.shag(); proverka("шаг 1: замок на одобренном живом", r1 == "ZAMOK ZHIV")
    proverka("неодобренный не взят", (och / "A_NEODOBREN.json").exists())
    proverka("семья с кладбища отклонена", (och / "B_MERTV.otkaz").exists())
    proverka("замок записан", (lab / "prereg" / "ZHIV.lock").exists())
    r2 = k.shag(); proverka("шаг 2: один прогон до терминала", r2.startswith("TERMINAL ZHIV"))
    proverka("слот освобождён", k.slot() == {"aktivnye": []})
    proverka("квитанция есть", (lab / "data" / "fabrika_xs" / "ZHIV" / "KVITANCIYA.json").exists())
    zh = [json.loads(l) for l in (lab / "data" / "fabrika_xs" / "zhurnal.jsonl").read_text().splitlines()]
    proverka("журнал: отказ, замок, терминал", [z["sobytie"] for z in zh] == ["OTKAZ_KLADBISCHE", "ZAMOK", "TERMINAL"])
    r3 = k.shag(); proverka("шаг 3: очередь пуста (неодобренный не исполняется)", r3 == "PUSTO")
    (och / "D_ZHIV2.json").write_text(json.dumps(dict(sp, id="ZHIV", semya="DRUGAYA", dannye="sint", odobreno={"kem": "Claude"})))
    proverka("повтор id с квитанцией отклонён", k.shag() == "PUSTO" and (och / "D_ZHIV2.otkaz").exists())
    (och / "E_NET_DANNYH.json").write_text(json.dumps(dict(sp, id="NET", semya="NET", dannye="netu", odobreno={"kem": "Claude"})))
    proverka("нет набора → BLOCKED_DATA", k.shag() == "BLOCKED_DATA")
    print(f"ВСЕ ТЕСТЫ: {ok} PASS")

if __name__ == "__main__":
    main()
