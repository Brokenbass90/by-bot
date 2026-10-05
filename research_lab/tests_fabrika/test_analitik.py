#!/usr/bin/env python3
"""Тест среза 3 без модели.   python3 research_lab/tests_fabrika/test_analitik.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "generator"))
import analitik as A  # noqa: E402
ok = 0
def proverka(i, u):
    global ok
    assert u, i; ok += 1; print("PASS", i)
kl = [{"semya": "TOLPA_XS"}, {"semya": "REZHIMNYY_CARRY"}]
dobr = dict(imya="X", semya="LISTING_DRIFT", mehanizm="m", kto_ostavlyaet_dengi="k", storona="LONG", izmereniya=["a", "b"],
            dannye="d", pochemu_ne_dubl="p", deshevyy_test="t")
p, o = A.proverit({"kandidaty": [dobr, dict(dobr, semya="tolpa_xs"), dict(dobr, izmereniya=["a"]), dobr]}, kl)
p2, o2 = A.proverit({"kandidaty": [dict(dobr, semya="TAKER_FLOW2")]}, kl)
proverka("принят корректный", len(p) == 1 and p[0]["status"] == "DRAFT")
proverka("кладбище отклонено (регистр/знаки)", any(x["prichina_otkaza"] == "семья на кладбище или занята" and x["semya"] == "tolpa_xs" for x in o))
proverka("занятая семья отклонена", not p2 and o2[0]["semya"] == "TAKER_FLOW2")
proverka("одно измерение отклонено", any(x["prichina_otkaza"] == "сторона/измерения вне схемы" for x in o))
proverka("не больше 3 рассмотрено", len(p) + len(o) == 3)
A.MODEL = "llava:latest"
try:
    A.ollama("x"); proverka("визуальная модель запрещена", False)
except SystemExit:
    proverka("визуальная модель запрещена", True)
print(f"ВСЕ ТЕСТЫ: {ok} PASS")
