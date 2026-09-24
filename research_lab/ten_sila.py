#!/usr/bin/env python3
"""ten_sila.py — проспективная тень нейтральной корзины «относительная сила к BTC».

ЗАЧЕМ. На истории механизм дал t 1.61 при 190 наблюдениях (P_KR_SILA_K_BTC_LS,
предрегистрация PREREG_PAKET_V5_2026_09_23.md). Это не находка: порог 2.5.
Окно подтверждения на истории тратить нельзя — его мало и оно одно. Поэтому
доказательство добываем временем: каждый день вперёд — это наблюдение,
которого никто не видел.

ПРАВИЛА ЗАМОРОЖЕНЫ в PREREG_TEN_SILA_2026_09_23.md. Здесь они только исполняются.
Ни денег, ни ключей, ни ордеров: только публичные данные Bybit.

ГЛАВНОЕ ПРАВИЛО. Засчитывается только день, наступивший ПОСЛЕ первого запуска.
Момент старта пишется на диск один раз и не меняется при перезапусках.

ЗАПУСК (долгим процессом, автозапуска на этой машине нет):

    caffeinate -i .venv-research/bin/python research_lab/ten_sila.py --minut 100000 --pauza 21600
    python3 research_lab/ten_sila.py --otchet
"""
from __future__ import annotations
import argparse, json, os, sys, time
import datetime as dt
from pathlib import Path

KOREN = Path(__file__).resolve().parents[1]
os.chdir(KOREN)
sys.path.insert(0, str(KOREN / "research_lab/fabrika"))
import numpy as np                                    # noqa: E402
import dannye_pit_kripto as bybit                     # noqa: E402

DATA = Path("research_lab/data")
ZHURNAL = DATA / "ten_SILA.jsonl"
SOST = DATA / "ten_SILA_sostoyanie.json"
PIDF = DATA / "ten_SILA.pid"
VSELENNAYA = DATA / "basis/vselennaya_pit_usd50.json"
DEN = 86400000

# ── замороженные параметры (см. предрегистрацию) ──────────────────────
OKNO = 20          # дней, за которые считаем обгон BTC
DERZHAT = 5        # дней в позиции
DOLYA = 0.2        # верхние и нижние 20% вселенной
KOMISSIYA = 7.0    # б.п. за сторону; две ноги, вход и выход
ROZYGRYSHEY = 50   # случайных пар корзин для контроля
MIN_CHLENOV = 14   # меньше — день пропускаем
VOROTA = 100       # закрытых решений до вердикта


def seychas_ms():
    return int(time.time() * 1000)


def den_ms(ms):
    return ms // DEN * DEN


def zamok():
    if PIDF.exists():
        try:
            os.kill(int(PIDF.read_text()), 0)
            print(f"Тень СИЛА уже работает, процесс {PIDF.read_text().strip()}."); sys.exit(0)
        except (OSError, ValueError):
            pass
    PIDF.write_text(str(os.getpid()))


def sostoyanie():
    if SOST.exists():
        return json.loads(SOST.read_text(encoding="utf-8"))
    s = {"nachalo_ms": seychas_ms(), "nachalo": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    SOST.write_text(json.dumps(s, ensure_ascii=False, indent=1))
    print(f"Момент старта записан: {s['nachalo']}. Всё, что раньше, — история и не считается.")
    return s


def chleny():
    """состав вселенной на последнюю известную дату: топ-50 по OI в долларах"""
    v = json.loads(VSELENNAYA.read_text(encoding="utf-8"))
    d = sorted(v["sostav"])[-1]
    return d, sorted(set(v["sostav"][d]) | {"BTCUSDT"})


KESH = DATA / "ten_SILA_ceny.json"


def _zapros(sym, dney):
    """одна попытка с коротким терпением: молчащая биржа не должна вешать проход"""
    import urllib.request, urllib.parse
    q = urllib.parse.urlencode(dict(category="linear", symbol=sym, interval="D",
                                    start=seychas_ms() - dney * DEN, end=seychas_ms(), limit=1000))
    for _ in range(2):
        try:
            with urllib.request.urlopen(bybit.BASE + "kline?" + q, timeout=10) as r:
                d = json.loads(r.read())
            if d.get("retCode") == 0:
                return d["result"].get("list") or []
        except Exception:
            time.sleep(1)
    return None


def svechi_svezhie(syms, dney=140):
    """последние дневные закрытия: свой кэш + кэш pit_daily + догрузка публичным API.
    Печатает ход работы: молчащий на десять минут лог неотличим от зависшего."""
    C = {}
    if KESH.exists():
        try:
            C = {k: {int(t): float(c) for t, c in v.items()} for k, v in json.loads(KESH.read_text()).items()}
        except Exception:
            C = {}
    t0 = time.time(); nemye = []
    print(f"  обновляю дневные свечи: {len(syms)} символов", flush=True)
    for i, s in enumerate(syms, 1):
        ryad = C.get(s, {})
        if not ryad:
            p = DATA / f"pit_daily/{s}.json"
            if p.exists():
                for r in json.loads(p.read_text()).get("daily", []):
                    ryad[int(r[0]) // DEN * DEN] = float(r[4])
        rows = _zapros(s, dney)
        if rows is None:
            nemye.append(s)
        else:
            for x in rows:
                ryad[int(x[0]) // DEN * DEN] = float(x[4])
        if ryad:
            C[s] = ryad
        if i % 10 == 0 or i == len(syms):
            print(f"    {i}/{len(syms)}, {round(time.time() - t0)} с", flush=True)
        time.sleep(0.08)
    if nemye:
        print(f"  биржа не ответила по {len(nemye)}: {', '.join(nemye[:8])}{'…' if len(nemye) > 8 else ''}", flush=True)
    tmp = KESH.with_suffix(".tmp")
    tmp.write_text(json.dumps({k: {str(t): c for t, c in v.items()} for k, v in C.items()}, ensure_ascii=False))
    tmp.replace(KESH)
    return C


def fanding_za(sym, ot_ms, do_ms):
    """сумма ставок фандинга за период; знак как у биржи: лонг платит при плюсе"""
    r = bybit.get("funding/history", category="linear", symbol=sym,
                  startTime=int(ot_ms), endTime=int(do_ms), limit=200)
    return sum(float(x["fundingRate"]) for x in (r or {}).get("list", []))


def otkryt(s, den, syms, C):
    """решение на закрытии дня den: лонг верхних 20% по обгону BTC, шорт нижних"""
    if den <= den_ms(s["nachalo_ms"]):
        return None                                   # день начался до старта тени
    if any(z["den"] == den for z in zhurnal()):
        return None                                   # уже есть решение на этот день
    ran = den - OKNO * DEN
    btc = C.get("BTCUSDT", {})
    if den not in btc or ran not in btc:
        return None
    r_btc = btc[den] / btc[ran] - 1
    ocenki = []
    for x in syms:
        if x == "BTCUSDT":
            continue
        r = C.get(x, {})
        if den in r and ran in r and r[ran] > 0:
            ocenki.append((r[den] / r[ran] - 1 - r_btc, x, r[den]))
    if len(ocenki) < MIN_CHLENOV:
        return None
    ocenki.sort()
    k = max(1, int(DOLYA * len(ocenki)))
    zapis = {"den": den, "data": dt.datetime.utcfromtimestamp(den / 1000).strftime("%Y-%m-%d"),
             "chlenov": len(ocenki), "k": k, "r_btc": r_btc,
             "long": [{"sym": x, "cena": c, "ocenka": o} for o, x, c in ocenki[-k:]],
             "short": [{"sym": x, "cena": c, "ocenka": o} for o, x, c in ocenki[:k]],
             "vse": [{"sym": x, "cena": c} for _, x, c in ocenki],
             "zakryto": False, "zapisano": seychas_ms()}
    dopisat(zapis)
    print(f"  решение {zapis['data']}: лонг {k}, шорт {k}, членов {len(ocenki)}")
    return zapis


def zakryt(z, C):
    """через DERZHAT дней считаем итог обеих ног и контроль случайными корзинами"""
    kon = z["den"] + DERZHAT * DEN
    if seychas_ms() < kon + DEN:
        return False
    ceny = {}
    for x in z["vse"]:
        r = C.get(x["sym"], {})
        if kon in r:
            ceny[x["sym"]] = r[kon]
    dohod = {x["sym"]: ceny[x["sym"]] / x["cena"] - 1 for x in z["vse"] if x["sym"] in ceny}
    if len(dohod) < MIN_CHLENOV:
        return False
    fnd = {}
    for x in z["long"] + z["short"]:
        if x["sym"] in dohod:
            fnd[x["sym"]] = fanding_za(x["sym"], z["den"], kon)
            time.sleep(0.08)

    def noga(spisok, znak):
        v = [znak * dohod[x["sym"]] - znak * fnd.get(x["sym"], 0.0) for x in spisok if x["sym"] in dohod]
        return float(np.mean(v)) if v else None

    dl, ds = noga(z["long"], 1), noga(z["short"], -1)
    if dl is None or ds is None:
        return False
    izderzhki = 4 * KOMISSIYA / 1e4
    itog = dl + ds - izderzhki
    rng = np.random.default_rng(z["den"] % 2**31)
    simy = [x["sym"] for x in z["vse"] if x["sym"] in dohod]
    sluch = []
    for _ in range(ROZYGRYSHEY):
        p = rng.permutation(len(simy)); k = z["k"]
        a = [dohod[simy[i]] - fnd.get(simy[i], 0.0) for i in p[:k]]
        b = [-dohod[simy[i]] + fnd.get(simy[i], 0.0) for i in p[k:2 * k]]
        if a and b:
            sluch.append(float(np.mean(a) + np.mean(b) - izderzhki))
    z.update(zakryto=True, konec=kon, dohod_long=dl, dohod_short=ds, izderzhki=izderzhki,
             itog=itog, sluchayno=float(np.mean(sluch)) if sluch else None,
             izbytok=itog - float(np.mean(sluch)) if sluch else None,
             chlenov_na_vyhode=len(dohod), zakryto_kogda=seychas_ms())
    return True


def zhurnal():
    if not ZHURNAL.exists():
        return []
    return [json.loads(x) for x in ZHURNAL.read_text(encoding="utf-8").splitlines() if x.strip()]


def dopisat(z):
    with ZHURNAL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(z, ensure_ascii=False) + "\n")


def perezapisat(zs):
    tmp = ZHURNAL.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(z, ensure_ascii=False) + "\n" for z in zs), encoding="utf-8")
    tmp.replace(ZHURNAL)


def krug():
    s = sostoyanie()
    den_v, syms = chleny()
    C = svechi_svezhie(syms)
    segodnya = den_ms(seychas_ms())
    otkryt(s, segodnya - DEN, syms, C)                # вчерашнее закрытие — последнее готовое
    zs = zhurnal(); izmeneno = False
    for z in zs:
        if not z.get("zakryto") and zakryt(z, C):
            izmeneno = True
    if izmeneno:
        perezapisat(zs)
    otkr = sum(1 for z in zs if not z.get("zakryto"))
    zak = sum(1 for z in zs if z.get("zakryto"))
    print(f"  состав вселенной от {den_v}; открытых решений {otkr}, закрытых {zak} из {VOROTA}")


def otchet():
    zs = [z for z in zhurnal() if z.get("zakryto") and z.get("izbytok") is not None]
    print(f"ТЕНЬ СИЛА — нейтральная корзина «обгон BTC»")
    s = sostoyanie()
    print(f"  старт: {s['nachalo']}")
    print(f"  закрытых решений: {len(zs)} из {VOROTA}")
    if not zs:
        print("  ещё нечего считать."); return
    ib = np.array([z["izbytok"] for z in zs]); it = np.array([z["itog"] for z in zs])
    n_eff = len(zs) / DERZHAT
    t = float(ib.mean() / (ib.std(ddof=1) / np.sqrt(n_eff))) if len(zs) > 1 and ib.std(ddof=1) > 0 else 0.0
    print(f"  итог стратегии (с издержками и фандингом): {it.mean():+.4f} за решение")
    print(f"  случайная пара корзин:                     {it.mean() - ib.mean():+.4f}")
    print(f"  избыток над случайностью:                  {ib.mean():+.4f}, t={t:+.2f} при n_eff {n_eff:.1f}")
    if len(zs) >= VOROTA:
        print("  ВОРОТА ДОСТИГНУТЫ: пора выносить вердикт по предрегистрации.")
    else:
        print(f"  до ворот ещё {VOROTA - len(zs)} решений — вердикта нет и быть не может.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minut", type=int, default=0)
    ap.add_argument("--pauza", type=int, default=21600)
    ap.add_argument("--otchet", action="store_true")
    a = ap.parse_args()
    if a.otchet:
        otchet(); return
    zamok()
    kon = time.time() + a.minut * 60
    n = 0
    while True:
        n += 1
        print(f"\n--- проход {n}  {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC ---", flush=True)
        try:
            krug()
        except Exception as e:
            print("  сбой прохода:", repr(e), flush=True)
        if time.time() >= kon:
            break
        time.sleep(a.pauza)


if __name__ == "__main__":
    main()
