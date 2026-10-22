#!/usr/bin/env python3
"""Судья тени POLY_YES_PEREPLATA (prereg PREREG_POLY_YES_PEREPLATA_VPERED + дополнения 1–3). Запуск ежедневно хуком ocenshchiki_ezhednevno.
До 30 событий с исходом — ТОЛЬКО счётчики (доход не читается). С 30 — вердикт по prereg; окончательный — 60.
Пишет results/poly_yes_verdikt_latest.json и .txt (текст для Telegram/веба). Ордеров, кошельков, ключей нет."""
import collections, datetime as dt, json, math, statistics as st, sys
from pathlib import Path
LAB = Path(__file__).resolve().parent
ZH = LAB / "data" / "poly_yes_ten.jsonl"
VOROTA, FINAL = 30, 60


def t_stat(x):
    return st.mean(x) / (st.stdev(x) / math.sqrt(len(x))) if len(x) > 2 and st.stdev(x) > 0 else None


def sudit(rows, seychas=None):
    vh = {r["conditionId"]: r for r in rows if r.get("tip") == "reshenie" and r.get("status") == "VHOD"}
    ish = {r["conditionId"]: r for r in rows if r.get("tip") == "ishod" and r.get("status") == "OK" and r["conditionId"] in vh}
    sob_vse = {r["sobytie"] for r in vh.values()}
    sob_ish = collections.defaultdict(list)
    for cid, r in ish.items(): sob_ish[vh[cid]["sobytie"]].append(cid)
    # событие считается с исходом, только если исходы есть у всех его входов
    polnye = {s: c for s, c in sob_ish.items() if len(c) == sum(1 for r in vh.values() if r["sobytie"] == s)}
    out = dict(kogda=(seychas or dt.datetime.now(dt.timezone.utc)).isoformat(timespec="seconds"), resheniy=sum(1 for r in rows if r.get("tip") == "reshenie"),
               vhodov=len(vh), sobytiy_s_vhodom=len(sob_vse), sobytiy_s_ishodom=len(polnye),
               dat_s_ishodom=len({s.split("|")[1] for s in polnye}), vorota=VOROTA, final=FINAL)
    if len(polnye) < VOROTA:
        out.update(status="NAKOPLENIE", dohod="СКРЫТ ДО 30 СОБЫТИЙ (prereg)")
        return out
    evs = sorted(polnye.items(), key=lambda kv: vh[kv[1][0]]["raschet_ms"])
    a = [st.mean(ish[c]["dohod"] for c in cs) for _, cs in evs]
    b = [st.mean(ish[c]["dohod_stress"] for c in cs) for _, cs in evs]
    po_datam = collections.defaultdict(list)
    for (s, _), x in zip(evs, a): po_datam[s.split("|")[1]].append(x)
    ad = [st.mean(v) for _, v in sorted(po_datam.items())]
    h = len(a) // 2
    m, t, td = st.mean(a), t_stat(a), t_stat(ad)
    ok = m > 0 and t is not None and t >= 2.0 and st.mean(a[:h]) > 0 and st.mean(a[h:]) > 0 and st.mean(b) > 0
    if ok and (td is None or td < 2.0): v = "INCONCLUSIVE"            # дополнение 3
    elif ok: v = "PASS"
    elif m <= 0: v = "FAIL"
    else: v = "INCONCLUSIVE"
    if v == "INCONCLUSIVE" and len(polnye) >= FINAL: v = "FAIL"         # INCONCLUSIVE до 60, потом FAIL
    out.update(status=v, srednee=round(m, 4), t_sobytiya=round(t, 2) if t else None, t_daty=round(td, 2) if td else None,
               polovina1=round(st.mean(a[:h]), 4), polovina2=round(st.mean(a[h:]), 4), stress=round(st.mean(b), 4),
               okonchatelnyy=len(polnye) >= FINAL)
    return out


def tekst(o):
    if o["status"] == "NAKOPLENIE":
        return (f"Polymarket тень [SHADOW] · событий с исходом {o['sobytiy_s_ishodom']}/{o['vorota']} (дат {o['dat_s_ishodom']}) · "
                f"входов {o['vhodov']}, решений {o['resheniy']} · доход скрыт до {o['vorota']} событий")
    return (f"Polymarket тень — {'ОКОНЧАТЕЛЬНЫЙ ' if o['okonchatelnyy'] else ''}ВЕРДИКТ: {o['status']}\n"
            f"событий {o['sobytiy_s_ishodom']}, дат {o['dat_s_ishodom']} · средний доход {o['srednee']*100:+.1f}% · стресс {o['stress']*100:+.1f}%\n"
            f"t по событиям {o['t_sobytiya']} · t по датам {o['t_daty']} · половины {o['polovina1']*100:+.1f}% / {o['polovina2']*100:+.1f}%")


def main():
    rows = [json.loads(l) for l in ZH.read_text().splitlines() if l.strip()] if ZH.exists() else []
    o = sudit(rows)
    (LAB / "results").mkdir(exist_ok=True)
    (LAB / "results" / "poly_yes_verdikt_latest.json").write_text(json.dumps(o, ensure_ascii=False, indent=1))
    (LAB / "results" / "poly_yes_verdikt_latest.txt").write_text(tekst(o) + "\n")
    print(tekst(o))


if __name__ == "__main__":
    main()
