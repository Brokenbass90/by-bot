#!/usr/bin/env python3
"""Тесты среза 1 (sudya_xs). Реальные исходы TOLPA/KITY НЕ пересчитываются: эквивалентность — на синтетике,
отказ на наследии — до загрузки данных.   python3 research_lab/tests_fabrika/test_sudya_xs.py"""
import datetime as dt, json, shutil, sys, tempfile
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB)); sys.path.insert(0, str(LAB / "fabrika"))
import sudya_xs as X  # noqa: E402
import kity_sudya as K, kity_m3_sudya as S  # noqa: E402

ok = 0


def proverka(imya, uslovie):
    global ok
    assert uslovie, imya
    ok += 1; print("PASS", imya)


def sintetika(papka: Path):
    for p in ("klines", "funding", "metrics", "taker"):
        (papka / p).mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7); d0 = dt.date(2021, 4, 1); n = (dt.date(2026, 9, 30) - d0).days + 1
    for k in range(60):
        s = f"S{k}USDT"; L = n if k != 9 else 700
        ts = [X.ms(d0 + dt.timedelta(days=i)) for i in range(L)]
        sila = rng.normal(0, .02, L)                       # скрытый сигнал: доля тейкеров предсказывает доход
        c = 100 * np.exp(np.cumsum(rng.normal(0, .03, L) + np.roll(sila, 2) * .3))
        json.dump([[t, 1, 1, 1, float(x), 1] for t, x in zip(ts, c)], open(papka / "klines" / f"{s}.json", "w"))
        json.dump([[t + 1, 0.0001] for t in ts], open(papka / "funding" / f"{s}.json", "w"))
        json.dump({(d0 + dt.timedelta(days=i)).isoformat(): [float(v) for v in rng.uniform(.5, 3, 4)] + [float(rng.uniform(1, 9) * 1e8)]
                   for i in range(L)}, open(papka / "metrics" / f"{s}.json", "w"))
        json.dump([[t, 1e6, 5e5 + 1e7 * float(sila[i])] for i, t in enumerate(ts)], open(papka / "taker" / f"{s}.json", "w"))


def main():
    tmp = Path(tempfile.mkdtemp()); baza = tmp / "lab"; dn = baza / "data" / "sint"
    sintetika(dn); (baza / "prereg").mkdir(parents=True)
    sp = json.loads((LAB / "prereg" / "KITY_M3_POTOK.json").read_text())
    sp.update(id="SINT_M3", dannye="sint"); sp.pop("legacy_kvitanciya")
    pr = baza / "prereg" / "SINT_M3.json"; pr.write_text(json.dumps(sp))

    try:
        X.progon(pr, baza); proverka("отказ без замка", False)
    except X.Otkaz:
        proverka("отказ без замка", True)
    X.zamorozit(pr, baza)
    pr.write_text(json.dumps(dict(sp, hold=3)))
    try:
        X.progon(pr, baza); proverka("отказ при правке после заморозки", False)
    except X.Otkaz:
        proverka("отказ при правке после заморозки", True)
    pr.write_text(json.dumps(sp))
    rez = X.progon(pr, baza)
    proverka("квитанция записана", (baza / "data" / "fabrika_xs" / "SINT_M3" / "KVITANCIYA.json").exists())
    try:
        X.progon(pr, baza); proverka("отказ при повторном прогоне", False)
    except X.Otkaz:
        proverka("отказ при повторном прогоне", True)

    # эквивалентность со старым судьёй KITY M3 на той же синтетике
    K.B = dn; S.B = dn; S.REZ = dn / "m3_rezultat.json"
    (dn / "taker_gotovo.json").write_text("{}"); (dn / "manifest.json").write_text("{}")
    S.main(); star = json.loads(S.REZ.read_text())
    for okno in ("PRIMARY", "REPLICATION"):
        a, b = rez[okno], star[okno]
        proverka(f"эквивалентность {okno}", all(json.loads(json.dumps(a.get(k))) == b.get(k) for k in ("n", "edge_bps", "t", "polovinki_bps", "verdikt")) or print(a, b))
    proverka("эквивалентность корр. TOLPA", rez["nezavisimost"]["TOLPA"]["korr"] == star["nezavisimost"]["korr_s_TOLPA"])
    proverka("эквивалентность корр. импульс", rez["nezavisimost"]["IMPULS_1D"]["korr"] == star["nezavisimost"]["korr_s_impulsom_1d"])

    bad = baza / "prereg" / "BAD.json"; bad.write_text(json.dumps(dict(sp, id="BAD", priznak=dict(tip="exec", kod="import os"))))
    try:
        X.zamorozit(bad, baza); proverka("отказ на признаке вне белого списка", False)
    except X.Otkaz:
        proverka("отказ на признаке вне белого списка", True)

    # наследие: реальные KITY M3 / M2 — отказ ДО загрузки данных (исходы не трогаются)
    for imya in ("KITY_M3_POTOK", "KITY_POZICII"):
        p = LAB / "prereg" / f"{imya}.json"; kopiya = baza / "prereg" / f"{imya}.json"; shutil.copy(p, kopiya)
        (baza / Path(json.loads(p.read_text())["legacy_kvitanciya"])).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(LAB / json.loads(p.read_text())["legacy_kvitanciya"], baza / json.loads(p.read_text())["legacy_kvitanciya"])
        X.zamorozit(kopiya, baza)
        try:
            X.progon(kopiya, baza); proverka(f"отказ наследия {imya}", False)
        except X.Otkaz as e:
            proverka(f"отказ наследия {imya}", "израсходован" in str(e))
    print(f"ВСЕ ТЕСТЫ: {ok} PASS")


if __name__ == "__main__":
    main()
