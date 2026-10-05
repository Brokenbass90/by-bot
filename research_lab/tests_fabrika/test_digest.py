#!/usr/bin/env python3
"""Тесты среза 2 (digest) на синтетике.   python3 research_lab/tests_fabrika/test_digest.py"""
import datetime as dt, json, os, sys, tempfile, time
from pathlib import Path
LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "fabrika"))
import digest as G  # noqa: E402

ok = 0
def proverka(imya, u):
    global ok
    assert u, imya; ok += 1; print("PASS", imya)

def main():
    lab = Path(tempfile.mkdtemp()); d = lab / "data"; seychas = dt.datetime(2026, 10, 5, 12, tzinfo=dt.timezone.utc)
    for n, posl in (("svezhiy", dt.date(2026, 10, 4)), ("staryy", dt.date(2026, 9, 20))):
        for pap in ("klines", "metrics"):
            (d / n / pap).mkdir(parents=True)
        t = int(dt.datetime(posl.year, posl.month, posl.day, tzinfo=dt.timezone.utc).timestamp() * 1000)
        for s in ("AUSDT", "BUSDT"):
            (d / n / "klines" / f"{s}.json").write_text(json.dumps([[t - 86400000, 1, 1, 1, 1, 1], [t, 1, 1, 1, 1, 1]]))
            (d / n / "metrics" / f"{s}.json").write_text(json.dumps({posl.isoformat(): [1, 2, 3, 4, 5e8]}))
    (d / "x_zagruzka.log").write_text("[1/2] A\n"); os.utime(d / "x_zagruzka.log", (seychas.timestamp() - 7200,) * 2)
    (d / "y_zagruzka.log").write_text("[2/2] B\nГОТОВО\n"); os.utime(d / "y_zagruzka.log", (seychas.timestamp() - 7200,) * 2)
    (d / "ten_Z.log").write_text("Traceback (most recent call last)\n"); os.utime(d / "ten_Z.log", (seychas.timestamp() - 60,) * 2)
    (lab / "fabrika").mkdir(); (lab / "fabrika" / "digest_nablyudenie.json").write_text(json.dumps({"teni": {"ten_Z.log": 180, "ten_T.log": 60}, "arhivy": ["arhivnyy"]}))
    (d / "ten_T.log").write_text("ok\n"); os.utime(d / "ten_T.log", (seychas.timestamp() - 7200,) * 2)
    (d / "staryy_razovyy.log").write_text("x\n"); os.utime(d / "staryy_razovyy.log", (seychas.timestamp() - 30 * 86400,) * 2)
    (d / "arhivnyy" / "klines").mkdir(parents=True); (d / "arhivnyy" / "klines" / "A.json").write_text(json.dumps([[0, 1, 1, 1, 1, 1]]))
    (lab / "prereg").mkdir()
    (lab / "prereg" / "P1.json").write_text(json.dumps({"id": "P1"}))
    (lab / "prereg" / "P1.lock").write_text(json.dumps({"sha256": "x", "kogda": "2026-09-01T00:00:00+00:00"}))
    (d / "fabrika_xs").mkdir(); (d / "fabrika_xs" / "SLOT.json").write_text(json.dumps({"aktivnye": ["A", "B"]}))
    g = G.sobrat(lab, seychas); tr = " | ".join(g["trevogi"])
    proverka("свежий набор без тревоги", "svezhiy" not in tr)
    proverka("старый набор: тревога отставания", "staryy/klines отстаёт на 15" in tr)
    proverka("загрузка молчит без ГОТОВО", "x_zagruzka.log молчит" in tr)
    proverka("законченная загрузка не тревожит", "y_zagruzka.log молчит" not in tr)
    proverka("ошибка в тени", "ten_Z.log: ошибок 1" in tr)
    proverka("prereg без результата > 14 дн.", "prereg P1" in tr)
    proverka("две активные гипотезы", "активных гипотез 2" in tr)
    proverka("тень молчит дольше своего порога", "ten_T.log молчит" in tr)
    proverka("старый разовый лог не шумит", "staryy_razovyy" not in tr)
    proverka("архив не тревожит", "arhivnyy" not in tr)
    proverka("покрытие metrics посчитано", g["nabory"]["svezhiy"]["monet_s_oi_poslednie_8_dat"] == {"2026-10-04": 2})
    try:
        G.ZAPRET_KLYUCHEY.search("edge_bps") and (_ for _ in ()).throw(RuntimeError("x"))
        proverka("запрет полей доходности", False)
    except RuntimeError:
        proverka("запрет полей доходности", True)
    print(f"ВСЕ ТЕСТЫ: {ok} PASS")

if __name__ == "__main__":
    main()
