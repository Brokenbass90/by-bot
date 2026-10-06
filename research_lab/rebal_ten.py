#!/usr/bin/env python3
"""rebal_ten.py — бумажная тень REBALANCING_PRESSURE (вперёд). Без ордеров; MT5 только чтение (демо FxPro), Alpaca только данные.
Правило заморожено в PREREG_REBALANCING_PRESSURE_2026_10_06.md и здесь не меняется:
  S = (US30[T−5]/US30[d0] − 1) − (TLT[T−5]/TLT[d0] − 1), d0 — последний торговый день прошлого месяца, T−5 — 5-й с конца
  торговый день месяца; позиция = −знак(S) в US30, вход закрытие T−5, выход закрытие последнего торгового дня; 2 bps.
Живые цены: US30 — MT5 D1 (тот же источник, что в исследовании), TLT — Alpaca IEX (SIP свежий запрещён тарифом);
через 2 дня — сверка признака по SIP. Календарь: будни минус праздники NYSE; в конце месяца сверяется с фактическими барами US30.
Состояние: data/rebal_ten/<YYYY-MM>/{signal,vyhod,sverka,KVITANCIYA}.json. Цикл раз в час в screen (без автозапуска):
    cd signal_copy && ../.venv/bin/python3 ../research_lab/rebal_ten.py --proverka | --shag | --cikl
"""
import datetime as dt, hashlib, json, sys, time, urllib.parse
from pathlib import Path
L = Path(__file__).resolve().parent; ROOT = L.parent
sys.path.insert(0, str(L)); sys.path.insert(0, str(ROOT / "scripts"))
import fx_broker_vygruzka as F
import materialize_alpaca_pit_daily as M

D = L / "data" / "rebal_ten"
PRAZDNIKI = {"2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18",
             "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"}
KOM = 0.0002; POSLE_ZAKRYTIYA = dt.time(22, 30)


def utc(): return dt.datetime.now(dt.timezone.utc)


def torg_dni(god, mes):
    d = dt.date(god, mes, 1); out = []
    while d.month == mes:
        if d.weekday() < 5 and d.isoformat() not in PRAZDNIKI:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def proshlyy_torg(d):
    d -= dt.timedelta(days=1)
    while d.weekday() >= 5 or d.isoformat() in PRAZDNIKI:
        d -= dt.timedelta(days=1)
    return d


def us30(m, ot, do):
    r = m.call("get_chart_history", timeout=90.0, symbol="#US30", period="D1",
               datetime_from=f"{ot}T00:00:00", datetime_to=f"{do + dt.timedelta(days=1)}T00:00:00", limit=100)
    bary = F._spisok(r, ("history", "candles", "rates", "bars", "data", "items"))
    return {dt.datetime.utcfromtimestamp(F._vremya(x["time"]) / 1000).date().isoformat(): float(x["close"]) for x in bary}


def tlt(ot, do, feed):
    e = M._load_env(ROOT / "configs/alpaca_paper_local.env"); h = M._alpaca_headers(e["ALPACA_API_KEY_ID"], e["ALPACA_API_SECRET_KEY"])
    p = {"symbols": "TLT", "timeframe": "1Day", "start": str(ot), "end": str(do), "limit": 100, "adjustment": "all", "feed": feed}
    x = M._json_get(f"{M.ALPACA_DATA_ROOT}/v2/stocks/bars?{urllib.parse.urlencode(p)}", h)
    return {b["t"][:10]: float(b["c"]) for b in (x.get("bars") or {}).get("TLT") or []}


def zakryto(d): return utc() >= dt.datetime.combine(d, POSLE_ZAKRYTIYA, tzinfo=dt.timezone.utc)
def sha(o): return hashlib.sha256(json.dumps(o, sort_keys=True).encode()).hexdigest()


def shag(m):
    seg = utc().date(); print(f"{utc().isoformat(timespec='seconds')} пульс: жив", flush=True)
    for god, mes in sorted({(seg.year, seg.month), ((seg - dt.timedelta(days=10)).year, (seg - dt.timedelta(days=10)).month)}):
        if (god, mes) < (2026, 10):
            continue
        dn = torg_dni(god, mes); t5, tk = dn[-5], dn[-1]; d0 = proshlyy_torg(dn[0]); P = D / f"{god}-{mes:02d}"
        sf, vf = P / "signal.json", P / "vyhod.json"
        if not sf.exists() and zakryto(t5):
            u = us30(m, d0, t5); t = tlt(d0, t5, "iex")
            if not all(x in u for x in (str(d0), str(t5))) or not all(x in t for x in (str(d0), str(t5))):
                print("  сигнал: цен ещё нет", {"us30": sorted(u)[-3:], "tlt": sorted(t)[-3:]}); continue
            S = (u[str(t5)] / u[str(d0)] - 1) - (t[str(t5)] / t[str(d0)] - 1)
            sig = dict(mesyac=f"{god}-{mes:02d}", d0=str(d0), t5=str(t5), posledniy=str(tk), S=S, poziciya=-1 if S > 0 else 1,
                       us30={str(d0): u[str(d0)], str(t5): u[str(t5)]}, tlt_iex={str(d0): t[str(d0)], str(t5): t[str(t5)]},
                       vychisleno=utc().isoformat(timespec="seconds"))
            sig["sha256"] = sha(sig); P.mkdir(parents=True, exist_ok=True); sf.write_text(json.dumps(sig, ensure_ascii=False, indent=1))
            print("  СИГНАЛ:", sig["mesyac"], "S", round(S * 100, 3), "%", "→", "ШОРТ US30" if S > 0 else "ЛОНГ US30")
        if sf.exists() and not vf.exists() and zakryto(tk):
            sig = json.loads(sf.read_text()); u = us30(m, t5, tk)
            if str(tk) not in u:
                print("  выход: цены ещё нет"); continue
            r = sig["poziciya"] * (u[str(tk)] / sig["us30"][str(t5)] - 1) - KOM
            fakt = sorted(d for d in us30(m, dn[0], tk) if d[:7] == f"{god}-{mes:02d}")
            vy = dict(vyhod_cena=u[str(tk)], dohod_bps=round(r * 1e4, 2), kalendar_sovpal=(len(fakt) >= 5 and fakt[-5] == str(t5) and fakt[-1] == str(tk)),
                      fakt_dni_hvost=fakt[-6:], zapisano=utc().isoformat(timespec="seconds"))
            vf.write_text(json.dumps(vy, ensure_ascii=False, indent=1)); print("  ВЫХОД:", vy)
        kf = P / "KVITANCIYA.json"
        if vf.exists() and not kf.exists() and seg >= tk + dt.timedelta(days=3):
            sig, vy = json.loads(sf.read_text()), json.loads(vf.read_text())
            t = tlt(d0, t5, "sip"); Ssip = None
            if str(d0) in t and str(t5) in t:
                Ssip = (sig["us30"][str(t5)] / sig["us30"][str(d0)] - 1) - (t[str(t5)] / t[str(d0)] - 1)
            prich = [] if (Ssip is not None and (Ssip > 0) == (sig["S"] > 0)) else ["знак S по SIP не совпал или SIP недоступен"]
            if not vy["kalendar_sovpal"]:
                prich.append("календарь T−5/последний день не совпал с барами US30")
            kv = dict(mesyac=sig["mesyac"], status="PAPER_EVENT_OPERATIONAL_PASS" if not prich else "PAPER_EVENT_OPERATIONAL_FAIL",
                      prichiny=prich, S_iex=sig["S"], S_sip=Ssip, dohod_bps_spravochno=vy["dohod_bps"],
                      primechanie="одно событие — шум; вердикт операционный", sha256_signal=sig["sha256"])
            kf.write_text(json.dumps(kv, ensure_ascii=False, indent=1)); print("  КВИТАНЦИЯ:", kv["status"], prich)


def main():
    m = F.MT5MCP(F.config.MT5_URL, F.config.MT5_TOKEN); m.connect()
    if "MetaQuotes" in str(m.account().get("server", "")):
        sys.exit("нужен демо-счёт FxPro")
    if "--proverka" in sys.argv:
        seg = utc().date(); u = us30(m, seg - dt.timedelta(days=10), seg); t = tlt(seg - dt.timedelta(days=10), seg, "iex")
        dn = torg_dni(2026, 10)
        print("US30 последние:", sorted(u.items())[-2:], "| TLT iex последние:", sorted(t.items())[-2:])
        print("октябрь: d0", proshlyy_torg(dn[0]), "T−5", dn[-5], "последний", dn[-1])
        print("ПРОВЕРКА: OK" if u and t else "ПРОВЕРКА: FAIL"); return
    if "--cikl" in sys.argv:
        while True:
            try:
                shag(m)
            except Exception as e:
                print(utc().isoformat(timespec="seconds"), "ошибка шага:", type(e).__name__, str(e)[:200], flush=True)
                try:
                    m = F.MT5MCP(F.config.MT5_URL, F.config.MT5_TOKEN); m.connect()
                except Exception:
                    pass
            time.sleep(3600)
    shag(m)


if __name__ == "__main__":
    main()
