"""reestr_sink.py — запись вердиктов фабрики в канонический реестр.

    research_lab/data/reestr.json        ЕДИНСТВЕННАЯ машинная база (канон)
    research_lab/fabrika/verdikty.jsonl  журнал доказательств, только дописывание
    research_lab/STRATEGY_MASTER.md      вид на реестр, генерируется (fabrika.py --master)

Запись в реестр:
  * эксклюзивный замок fcntl.flock на data/reestr.zapis.lock на всё время
    «прочитать → изменить → записать» (замок держит и reestr.py --perevesti);
  * запись атомарная: временный файл в той же папке + os.replace;
  * пишем, только если содержимое изменилось (повторная синхронизация — no-op);
  * правило реестра соблюдается: вниз можно только в NEGATIVE; то, что владелец
    или производство подняли выше (SHADOW и т.п.), фабрика не опускает — пишет
    свой вердикт в поле fabrika, не трогая sostoyanie;
  * каждый переход дописывается в reestr_istoriya.jsonl.
"""
from __future__ import annotations
import contextlib, fcntl, json, os, tempfile, time
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
BAZA = LAB / "data/reestr.json"
ISTORIYA = LAB / "data/reestr_istoriya.jsonl"
ZAMOK_ZAPISI = LAB / "data/reestr.zapis.lock"
SOSTOYANIYA = ["NEGATIVE", "HYPOTHESIS", "POSITIVE_LEAD", "CANDIDATE", "SHADOW", "READY_FOR_BUILD",
               "READY_FOR_CANARY", "TINY_LIVE", "SCALE_CANDIDATE"]

# вердикт фабрики → состояние реестра
KARTA = {"NEGATIVE": "NEGATIVE", "FAILED_CONFIRMATION": "NEGATIVE",
         "POSITIVE_LEAD": "POSITIVE_LEAD", "LEAD_BLOCKED_DATA": "POSITIVE_LEAD",
         "CONFIRMED": "CANDIDATE",
         "PLUS_NO_CONFIDENCE": "HYPOTHESIS", "INCONCLUSIVE_LOW_N": "HYPOTHESIS",
         "CONFIRMATION_INCONCLUSIVE": "POSITIVE_LEAD", "CONFIRMATION_WAITING_DATA": "POSITIVE_LEAD",
         "BLOCKED_DATA": "HYPOTHESIS"}


@contextlib.contextmanager
def zamok(put=ZAMOK_ZAPISI):
    put.parent.mkdir(parents=True, exist_ok=True)
    with open(put, "a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def atomarno(put: Path, tekst: str):
    fd, tmp = tempfile.mkstemp(dir=str(put.parent), prefix=put.name + ".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(tekst); fh.flush(); os.fsync(fh.fileno())
    os.replace(tmp, put)


def _istoriya(zapisi):
    if zapisi:
        with ISTORIYA.open("a", encoding="utf-8") as fh:
            for z in zapisi:
                fh.write(json.dumps(z, ensure_ascii=False) + "\n")


def primenit(obnovleniya, baza=BAZA, istoriya=True):
    """obnovleniya: список словарей {id, sostoyanie?, ...поля}. Возвращает число изменённых."""
    with zamok(baza.parent / ZAMOK_ZAPISI.name):
        z = json.loads(baza.read_text(encoding="utf-8")) if baza.exists() else []
        po_id = {x["id"]: x for x in z}
        do = json.dumps(z, ensure_ascii=False, sort_keys=True)
        perehody = []
        for ob in obnovleniya:
            ob = dict(ob); nov_sost = ob.pop("sostoyanie", None)
            x = po_id.get(ob["id"])
            if x is None:
                x = {"id": ob["id"], "sostoyanie": nov_sost or "HYPOTHESIS"}
                z.append(x); po_id[x["id"]] = x
                perehody.append({"id": x["id"], "iz": None, "v": x["sostoyanie"]})
            x.update({k: v for k, v in ob.items() if k != "id"})
            if nov_sost and nov_sost != x["sostoyanie"]:
                st = x["sostoyanie"]
                vniz = SOSTOYANIYA.index(nov_sost) < SOSTOYANIYA.index(st) if st in SOSTOYANIYA else False
                if nov_sost == "NEGATIVE" or not vniz:
                    perehody.append({"id": x["id"], "iz": st, "v": nov_sost}); x["sostoyanie"] = nov_sost
        posle = json.dumps(z, ensure_ascii=False, sort_keys=True)
        if posle == do:
            return 0
        atomarno(baza, json.dumps(z, ensure_ascii=False, indent=1) + "\n")
        if istoriya:
            _istoriya([{"kogda_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "perehod": p,
                        "istochnik": "fabrika"} for p in perehody])
        return len(perehody) or 1


def slot_dlya(it):
    if it.get("slot"):
        return it["slot"]
    sm, ry = it.get("semya") or "", it.get("rynok") or ""
    if sm == "event_continuation" or sm.startswith("bull"):
        return "rost"
    if ry == "kripto_pit" and sm.startswith("xs"):
        return "neytral"
    return None


def iz_verdiktov(ochered, verdikty_po_id):
    """строит обновления реестра из очереди и последних вердиктов фабрики"""
    obn = []
    for it in ochered:
        v = verdikty_po_id.get(it["id"])
        if not v or it.get("tip") == "paritet" or v["verdikt"] not in KARTA:
            continue
        obn.append({"id": it["id"], "sostoyanie": KARTA[v["verdikt"]],
                    "imya": it.get("imya") or f"{it.get('semya')} · {it.get('rynok')} · {it.get('param', {})}",
                    "istochnik": "fabrika", "semya": it.get("semya"), "rynok": it.get("rynok"),
                    "slot": slot_dlya(it),
                    "fabrika": {"verdikt": v["verdikt"], "pochemu": v["pochemu"], "kogda": v["kogda"],
                                "etap": (it.get("param") or {}).get("etap")},
                    "svidetelstvo": f"research_lab/fabrika/verdikty.jsonl#{it['id']}@{v['kogda']}",
                    "pass_fail": it.get("prereg"),
                    "shans": 0.0, "znanie": 0.0, "cena": 1.0, "deystvie": "fabrika"})
    return obn


def samoproverka():
    """атомарность, замок при параллельной записи, правило «вниз только в NEGATIVE», идемпотентность"""
    import multiprocessing as mp
    d = Path(tempfile.mkdtemp()); baza = d / "reestr.json"; baza.write_text("[]")
    ps = [mp.Process(target=_rabotnik, args=(k, str(baza))) for k in range(4)]
    [p.start() for p in ps]; [p.join() for p in ps]
    z = json.loads(baza.read_text()); res = []
    res.append(("4 процесса × 40 записей параллельно → 160, файл цел", len(z) == 160 and len({x["id"] for x in z}) == 160))
    primenit([{"id": "s", "sostoyanie": "SHADOW"}], baza=baza, istoriya=False)
    primenit([{"id": "s", "sostoyanie": "HYPOTHESIS", "fabrika": {"v": "PLUS"}}], baza=baza, istoriya=False)
    s = next(x for x in json.loads(baza.read_text()) if x["id"] == "s")
    res.append(("SHADOW не опускается, вердикт фабрики рядом", s["sostoyanie"] == "SHADOW" and s["fabrika"] == {"v": "PLUS"}))
    primenit([{"id": "s", "sostoyanie": "NEGATIVE"}], baza=baza, istoriya=False)
    s = next(x for x in json.loads(baza.read_text()) if x["id"] == "s")
    res.append(("вниз в NEGATIVE — можно", s["sostoyanie"] == "NEGATIVE"))
    m = os.stat(baza).st_mtime_ns; n = primenit([{"id": "s", "sostoyanie": "NEGATIVE"}], baza=baza, istoriya=False)
    res.append(("повтор той же записи — файл не трогается", n == 0 and os.stat(baza).st_mtime_ns == m))
    res.append(("временных файлов не осталось", not [f for f in os.listdir(d) if f.endswith(".tmp")]))
    bad = 0
    for name, ok in res:
        bad += not ok; print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    return bad


def _rabotnik(k, baza):
    for i in range(40):
        primenit([{"id": f"p{k}_{i}", "sostoyanie": "HYPOTHESIS"}], baza=Path(baza), istoriya=False)


if __name__ == "__main__":
    import sys
    sys.exit(1 if samoproverka() else 0)
