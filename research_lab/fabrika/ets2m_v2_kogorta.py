#!/usr/bin/env python3
"""ETS2M_V2 — когорта по времени ОБНАРУЖЕНИЯ сигнала в источнике (поправка A1 к PREREG_ETS2M_V2_VPERED_2026_10_11).

Почему: yadro.py переносит вход только после закрытия сделки источника (ему нужен R), поэтому vhody.zapisano = время закрытия.
Правило V2 «zapisano − ts ≤ 6 ч» по ядру отбирало сделки, закрывшиеся за 6 ч (отбор по исходу). Исправление: время обнаружения =
zapisano ПЕРВОЙ записи (sym, ts) в источнике data/ten_ETS2S.jsonl (ожидающая запись пишется при обнаружении, до исхода).
Член когорты ⇔ ts ≥ T0 и (обнаружение − ts) ≤ 6 ч. Порядок (ts, sym). Окно 1 = первые 900, окно 2 = следующие 900.
Пин списка id пишется один раз, когда набрано 900 своевременных и прошло 6 ч после ts последнего члена (позже своевременным стать
никто не может) — до чтения любых R. Оценка — НЕИЗМЕНЁННЫЙ yadro.otsenit на входах, отфильтрованных по пину.
    python3 research_lab/fabrika/ets2m_v2_kogorta.py                 # только счётчики, пин при готовности
    python3 research_lab/fabrika/ets2m_v2_kogorta.py --otsenit 1     # судья окна 1 (после пина и закрытия всех)
"""
import argparse, datetime as dt, hashlib, json, sys, time
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB))
T0 = int(dt.datetime(2026, 10, 11, 21, 1, 43, tzinfo=dt.timezone.utc).timestamp() * 1000)
H = 3_600_000; OKNO = 900; LAG_MAX = 6 * H; EPOHA = "ETS2M"
ISTOCHNIK = LAB / "data" / "ten_ETS2S.jsonl"; PAPKA = LAB / "data" / "yadro" / EPOHA


def jl(p):
    return [json.loads(x) for x in open(p) if x.strip()] if Path(p).exists() else []


def chleny():
    perv = {}
    for r in jl(ISTOCHNIK):
        perv.setdefault((r["sym"], int(r["ts"])), r)          # первая запись = момент обнаружения
    vse = [k for k in perv if k[1] >= T0]
    vovr = sorted((k for k in vse if perv[k]["zapisano"] - k[1] <= LAG_MAX), key=lambda k: (k[1], k[0]))
    return vse, vovr


def hs_yadra():
    hs = {x["hesh_strategii"] for x in jl(PAPKA / "vhody.jsonl")}
    if len(hs) != 1: raise SystemExit(f"ядро: ожидался один hesh_strategii, есть {hs}")
    return hs.pop()


def pin_put(okno): return LAB / "fabrika" / f"KOGORTA_ETS2M_V2_OKNO{okno}.json"


def schet():
    import yadro
    vse, vovr = chleny(); now = int(time.time() * 1000); hs = hs_yadra()
    v_yadre = {x["id"] for x in jl(PAPKA / "vhody.jsonl")}
    print(f"с T0: решений {len(vse)}, своевременных (≤6 ч) {len(vovr)}, поздних {len(vse) - len(vovr)}")
    for okno in (1, 2):
        chast = vovr[(okno - 1) * OKNO: okno * OKNO]
        ids = [yadro.id_vhoda(hs, s, ts) for s, ts in chast]
        print(f"окно {okno}: набрано {len(chast)}/{OKNO}, уже в ядре (закрыты) {sum(i in v_yadre for i in ids)}")
        p = pin_put(okno)
        if len(chast) == OKNO and now >= chast[-1][1] + LAG_MAX and not p.exists():
            obj = {"epoha": EPOHA, "okno": okno, "T0_ms": T0, "pravilo": "ts>=T0, первая запись источника − ts ≤ 6 ч, порядок (ts,sym)",
                   "istochnik": str(ISTOCHNIK.name), "hesh_strategii": hs, "ids": ids,
                   "ts_pervyy": chast[0][1], "ts_posledniy": chast[-1][1], "zapisano": dt.datetime.now(dt.timezone.utc).isoformat()}
            obj["sha256_ids"] = hashlib.sha256(json.dumps(ids).encode()).hexdigest()
            p.write_text(json.dumps(obj, ensure_ascii=False, indent=1)); print(f"  ПИН окна {okno}: {obj['sha256_ids']}")
        elif p.exists():
            pin = json.loads(p.read_text())
            ok = pin["ids"] == ids
            print(f"  пин есть: {pin['sha256_ids'][:16]}… сверка со списком сейчас: {'OK' if ok else 'РАСХОЖДЕНИЕ'}")
            if not ok: return 3
    return 0


def otsenit(okno):
    import yadro
    pin = json.loads(pin_put(okno).read_text())
    if hashlib.sha256(json.dumps(pin["ids"]).encode()).hexdigest() != pin["sha256_ids"]: raise SystemExit("пин повреждён")
    nuzhno = set(pin["ids"]); orig = yadro.chitat_jsonl
    def filtr(p):
        rows = orig(p)
        return [x for x in rows if x["id"] in nuzhno] if Path(p).name == "vhody.jsonl" else rows
    yadro.chitat_jsonl = filtr                                   # судья тот же, меняется только набор входов
    return yadro.otsenit(EPOHA, OKNO)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--otsenit", type=int, choices=(1, 2)); a = ap.parse_args()
    sys.exit(otsenit(a.otsenit) if a.otsenit else schet())
