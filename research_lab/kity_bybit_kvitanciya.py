#!/usr/bin/env python3
"""kity_bybit_kvitanciya.py — операционная квитанция недели тени KITY_BYBIT (условие C1, KITY_BYBIT_CANARY_USLOVIYA_2026_10_11).
Только проверки исполнения, без PnL-решений: доход недели в квитанцию не входит и ни на что не влияет.
Читает файлы тени data/kity_bybit_ten/<d>/ (snimok_2355.json, potok.json, signal.json, vhod.json, vyhod.json); тень не трогает.
    .venv/bin/python research_lab/kity_bybit_kvitanciya.py 2026-10-15            # вход (C1) — после пт 00:05 UTC
    .venv/bin/python research_lab/kity_bybit_kvitanciya.py 2026-10-15 --fanding  # + полнота фандинга ног (сеть, после выхода)
Пишет data/kity_bybit_ten/<d>/kvitanciya_C1.json. Статус: OPERATIONAL_PASS / OPERATIONAL_FAIL (+ список причин) / NOT_YET.
"""
import argparse, datetime as dt, hashlib, json, sys, urllib.parse, urllib.request
from pathlib import Path
D = Path(__file__).resolve().parent / "data" / "kity_bybit_ten"
MIN_MONET, H, DEN = 30, 3_600_000, 86_400_000


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def t(s): return dt.datetime.fromisoformat(s).astimezone(dt.timezone.utc)


def fanding_kalendar(sym, t0, t1):
    """A6 (Brain V2) §2: покрытие (t0, t1] расчётами из самого источника, без подстановки нуля."""
    q = urllib.parse.urlencode(dict(category="linear", symbol=sym, startTime=t0 - 6 * DEN, endTime=t1 + DEN, limit=200))
    with urllib.request.urlopen(urllib.request.Request("https://api.bybit.com/v5/market/funding/history?" + q,
                                                       headers={"User-Agent": "research-paper"}), timeout=30) as r:
        ts = sorted(int(x["fundingRateTimestamp"]) for x in json.loads(r.read())["result"]["list"])
    do = [x for x in ts if x <= t0]; posle = [x for x in ts if x >= t1]
    if len(do) < 11 or not posle: return "kalendar_ne_zakryt"
    inter = sorted(b - a for a, b in zip(do[-11:-1], do[-10:])); g0 = (inter[4] + inter[5]) / 2
    okno = [x for x in ts if do[-1] <= x <= posle[0]]
    return "ok" if all(b - a <= g0 for a, b in zip(okno, okno[1:])) else "dyra_kalendarya"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("d"); ap.add_argument("--fanding", action="store_true"); a = ap.parse_args()
    d = dt.date.fromisoformat(a.d); p = D / d.isoformat()
    d_1 = d - dt.timedelta(days=1)
    pr = []                                   # (проверка, PASS/FAIL/NOT_YET, деталь)
    def chk(imya, ok, det=""): pr.append(dict(proverka=imya, status=ok, detal=det))

    sn = p / "snimok_2355.json"
    if not sn.exists(): chk("C1.1 снимок 23:50–23:59 d−1", "FAIL", "нет файла")
    else:
        s = json.loads(sn.read_text()); v = t(s["vremya"])
        okno = (dt.datetime(d_1.year, d_1.month, d_1.day, 23, 50, tzinfo=dt.timezone.utc),
                dt.datetime(d.year, d.month, d.day, 0, 0, tzinfo=dt.timezone.utc))
        chk("C1.1 снимок 23:50–23:59 d−1", "PASS" if okno[0] <= v < okno[1] else "FAIL", s["vremya"])
    sg = p / "signal.json"
    if not sg.exists(): chk("C1.2 сигнал до 23:00 UTC дня d", "NOT_YET" if dt.datetime.now(dt.timezone.utc).date() <= d else "FAIL", "нет signal.json")
    else:
        g = json.loads(sg.read_text()); v = t(g["vychisleno"])
        chk("C1.2 сигнал до 23:00 UTC дня d", "PASS" if v < dt.datetime(d.year, d.month, d.day, 23, 0, tzinfo=dt.timezone.utc) else "FAIL", g["vychisleno"])
        chk("C1.3 ≥ 30 монет с признаком", "PASS" if g["monet_s_priznakom"] >= MIN_MONET and g["dostatochno"] else "FAIL", str(g["monet_s_priznakom"]))
        chk("C1.3a хэши входов сигнала", "PASS" if g["sha256"]["snimok"] == sha(sn) and g["sha256"]["potok"] == sha(p / "potok.json") else "FAIL",
            "snimok/potok sha совпадают с файлами")
        nogi = [x["s"] for x in g["long"]] + [x["s"] for x in g["short"]]
        chk("C1.4 все ноги Trading (в снимке)", "PASS" if nogi and all(x in g["instrumenty"] for x in nogi) else "FAIL", ",".join(nogi))
    vh = p / "vhod.json"
    if not vh.exists(): chk("C1.5 цены входа и лот $100", "NOT_YET", "нет vhod.json (пт 00:05 UTC)")
    else:
        h = json.loads(vh.read_text()); poz = h["pozicii"]
        bez_ceny = [x["s"] for x in poz if not x["cena_vhoda"]]; bez_lota = [x["s"] for x in poz if not x["lot_ok"]]
        chk("C1.5a цены входа получены", "PASS" if poz and not bez_ceny else "FAIL", ",".join(bez_ceny))
        chk("C1.5b лот проходит при $100", "PASS" if poz and not bez_lota else "FAIL", ",".join(bez_lota))
    vy = p / "vyhod.json"
    if vy.exists():
        y = json.loads(vy.read_text())
        chk("C1.6 выход: все ноги оценены", "PASS" if y["status"] == "PAPER_WEEK_OPERATIONAL_PASS" else "FAIL", y["status"])
        if a.fanding:
            t0 = int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000) + DEN; t1 = t0 + 7 * DEN
            plohie = {n["s"]: r for n in y["nogi"] if (r := fanding_kalendar(n["s"], t0, t1)) != "ok"}
            chk("C1.7 полнота фандинга (A6)", "PASS" if not plohie else "FAIL", json.dumps(plohie, ensure_ascii=False))
    st = [x["status"] for x in pr]
    itog = "OPERATIONAL_FAIL" if "FAIL" in st else ("NOT_YET" if "NOT_YET" in st else "OPERATIONAL_PASS")
    rez = dict(d=d.isoformat(), sostavleno=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), status=itog, proverki=pr,
               pnl_v_kvitancii=False)
    (p / "kvitanciya_C1.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1)) if p.exists() else None
    for x in pr: print(f"{x['status']:8} {x['proverka']}  {x['detal'][:80]}")
    print("ИТОГ:", itog); return 0 if itog != "OPERATIONAL_FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
