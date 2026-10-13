#!/usr/bin/env python3
"""sudi_v_reestr.py — перенос результатов НАСТОЯЩИХ замороженных судей в реестр (Factory V3, P0). 13.10.2026.
Код и критерии судей не меняются: мост только читает их итоговые файлы и пишет квитанции в реестр (идемпотентно по sha256).

  KITY_M3_BYBIT_TEN  ← data/kity_bybit_ten/<d>/kvitanciya_C1.json (C1), paritet_C2.json (C2)
                       готовность досье канарейки = ≥ 2 разных четверга с C1=OPERATIONAL_PASS и C2=C2_PASS (KITY_BYBIT_CANARY_USLOVIYA)
  ETS2M_V2           ← data/factory_v3/kvitancii/ETS2M_V2_OKNO<n>.txt — вывод замороженного судьи (ets2m_ocenka.py);
                       статус NOT_MEASURED / MEASURED; вердикт по правилу prereg выносит CRO через sudya_most_v1.verdikt
  BOUNCE1, BOUNCE1_8, BREAKOUT_TOP50 ← только счётчик закрытых решений до порога n=30 (PROGRESS), без PnL
Запускается сторожем раз в час и вручную: python3 research_lab/factory_v3/sudi_v_reestr.py
"""
import glob, hashlib, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from reestr_v1 import Reestr, OshibkaReestra

D = HERE.parent / "data"


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _zapisat(r, g, vid, status, put, detali=None):
    try:
        r.kvitanciya(g, vid, status, str(Path(put).relative_to(HERE.parent)), sha(put), detali); return 1
    except OshibkaReestra:
        return 0                                         # уже записана (тот же sha) или гипотезы нет


def kity(r, baza=None):
    baza = Path(baza or D / "kity_bybit_ten"); n = 0
    for f in sorted(baza.glob("*/kvitanciya_C1.json")):
        n += _zapisat(r, "KITY_M3_BYBIT_TEN", f"C1:{f.parent.name}", json.loads(f.read_text())["status"], f)
    for f in sorted(baza.glob("*/paritet_C2.json")):
        n += _zapisat(r, "KITY_M3_BYBIT_TEN", f"C2:{f.parent.name}", json.loads(f.read_text())["status"], f)
    return n


def gotovnost_kanareyki_kity(r):
    k = r.sostoyanie()["gipotezy"].get("KITY_M3_BYBIT_TEN", {}).get("kvitancii", [])
    posl = {}
    for x in k: posl[x["vid"]] = x["status"]                 # последняя квитанция каждого вида/даты
    dni = {v.split(":")[1] for v in posl}
    ok = sorted(d for d in dni if posl.get(f"C1:{d}") == "OPERATIONAL_PASS" and posl.get(f"C2:{d}") == "C2_PASS")
    return dict(chistyh_nedel=len(ok), nedeli=ok, gotovo_k_dosie=len(ok) >= 2)


def elder(r):
    n = 0
    for f in sorted((D / "factory_v3" / "kvitancii").glob("ETS2M_V2_OKNO*.txt")):
        st = "NOT_MEASURED" if "NOT_MEASURED" in f.read_text() else "MEASURED"
        n += _zapisat(r, "ETS2M_V2", f"OTSENKA:{f.stem}", st, f)
    return n


def progress(r):
    """n закрытых решений теней (только счёт), квитанция пишется при изменении счётчика."""
    istochniki = {"BOUNCE1": (D / "bounce_ten_BOUNCE1" / "zhurnal.jsonl", "ZAKRYTA"),
                  "BOUNCE1_8": (D / "bounce_ten_BOUNCE1_8" / "zhurnal.jsonl", "ZAKRYTA"),
                  "BREAKOUT_TOP50": (D / "breakout_ten" / "sdelki.jsonl", None)}
    out, n = {}, 0
    for g, (p, zakr) in istochniki.items():
        cnt = 0
        if p.exists():
            with open(p) as f:
                for l in f:
                    if l.strip() and (zakr is None or json.loads(l).get("status") == zakr): cnt += 1
        out[g] = cnt
        snap = D / "factory_v3" / "progress" / f"{g}.json"; snap.parent.mkdir(parents=True, exist_ok=True)
        if not snap.exists() or json.loads(snap.read_text()).get("zakryto") != cnt:
            snap.write_text(json.dumps(dict(gipoteza=g, zakryto=cnt, porog=30, istochnik=str(p.relative_to(HERE.parent)))))
            n += _zapisat(r, g, "PROGRESS", f"{cnt}/30", snap, dict(zakryto=cnt))
    return out, n


def vse(r=None):
    r = r or Reestr()
    pr, n_pr = progress(r)
    return dict(kity_novyh=kity(r), elder_novyh=elder(r), progress=pr, progress_novyh=n_pr, kity_kanareyka=gotovnost_kanareyki_kity(r))


if __name__ == "__main__":
    print(json.dumps(vse(), ensure_ascii=False, indent=1))
