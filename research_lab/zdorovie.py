#!/usr/bin/env python3
"""zdorovie.py — снимок здоровья исследовательских линий (02.10). ТОЛЬКО ЧТЕНИЕ: счётчики, свежесть, пропуски.
Ни одного вердикта и ни одной метрики доходности: будущие окна не подсматриваются вне замороженных точек.

    python3 research_lab/zdorovie.py
"""
import collections, datetime as dt, glob, json, os, time
from pathlib import Path

LAB = Path(__file__).resolve().parent; ROOT = LAB.parent; D = LAB / "data"
SEJCHAS = time.time()


def vozrast(p):
    p = Path(p)
    return f"{(SEJCHAS - p.stat().st_mtime) / 3600:.1f} ч назад" if p.exists() else "НЕТ ФАЙЛА"


def utc(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


def pm2():
    gran = 1790870959643; krugi = collections.Counter(); dubli = 0; vidano = set(); dni = set()
    for f in sorted((D / "poly/snimki").glob("*.jsonl")):
        for l in open(f):
            if '"strike"' not in l:
                continue
            z = json.loads(l)
            if z.get("kat") != "strike" or z.get("otbor") != "v5" or z["t"] < gran:
                continue
            k = (z["t"], z["conditionId"])
            dubli += k in vidano; vidano.add(k); krugi[z["t"]] += 1; dni.add(utc(z["t"])[:10])
    t = sorted(krugi); pauzy = [(b - a) / 60000 for a, b in zip(t, t[1:])]
    return {"krugov_v5": len(t), "zapisey": sum(krugi.values()), "dubley": dubli, "kalendarnyh_dney": sorted(dni),
            "max_pauza_min": round(max(pauzy), 1) if pauzy else None, "posledniy": utc(t[-1]) if t else None,
            "gotov_k_verdiktu": len(dni) >= 3, "sborshchik_log": vozrast(D / "poly/snimki.log")}


def tolpa():
    p = D / "poz_chas/BTCUSDT.json"; z = json.load(open(p)) if p.exists() else {"lsr": []}
    pit = json.load(open(D / "pit_daily/BTCUSDT.json"))["daily"]
    poz = len([f for f in (D / "poz_chas").glob("*USDT*.json")])
    return {"chasovyh_monet": poz, "lsr_chas_posledniy_BTC": utc(z["lsr"][-1][0]) if z["lsr"] else None,
            "pit_daily_posledniy_BTC": utc(pit[-1][0]),
            "lsr_sut_posledniy_BTC": utc(json.load(open(D / "lsr_sutochnyy/BTCUSDT.json"))["lsr"][-1][0]),
            "vselennaya_do": max(json.load(open(D / "basis/vselennaya_pit_usd50.json"))["sostav"]),
            "primechanie": "вперёд с 2026-10-02 (TOLPA_1D) и 2026-10-01 (TOLPA_XS): данные после этих дат нужно дописать"}


def peregrev():
    led = [ROOT / "runtime/funding_positioning_dynamic_shadow_ledger.jsonl", ROOT / "runtime/funding_positioning_post_n42_frozen_ledger.jsonl"]
    import importlib.util, sys
    sys.path.insert(0, str(LAB)); import fanding_hvost as F
    n = len(F.iskhody(F.ZAMOROZKA_MS, 10**14))
    return {"short_hvost_buduschih_sobytiy": f"{n} из 30", "ledzhery": {p.name[:40]: vozrast(p) for p in led},
            "C8V": "нужна ежемесячная докачка pit_daily --vse --obnovit (с начала ноября)"}


def ets():
    v = sum(1 for _ in open(D / "yadro/ETS2M/vhody.jsonl")) if (D / "yadro/ETS2M/vhody.jsonl").exists() else None
    i = sum(1 for _ in open(D / "yadro/ETS2M/ishody.jsonl")) if (D / "yadro/ETS2M/ishody.jsonl").exists() else None
    return {"ETS2M_vhodov_lokalno": v, "ETS2M_ishodov_lokalno": i, "ETS2M_lokalnaya_kopiya": vozrast(D / "yadro/ETS2M/ishody.jsonl"),
            "ETS2S_ten_log": vozrast(D / "ten_ETS2S.log"), "ATT1_ten_log": vozrast(D / "ten_ATT1.log"),
            "SILA_log": vozrast(D / "ten_SILA.log"), "verdikt_ETS2M": "не раньше 2026-10-10 19:00 UTC (на VPS)"}


def attention():
    dni = sorted(p.stem for p in (D / "akcii_grouped").glob("20*.json"))
    etb = sorted(p.stem for p in (D / "etb_snimki").glob("*.json"))
    vpered = [d for d in dni if d >= "2026-10-02"]
    return {"posledniy_den_akciy": dni[-1], "dney_vpered_s_2026_10_02": len(vpered), "etb_snimki": etb,
            "primechanie": "события с 02.10; 10-дневное окно — первые сделки учитываются не раньше ~16.10; нужна докачка раз в 1–3 дня"}


if __name__ == "__main__":
    rez = {"kogda_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")}
    for k, f in (("PM2", pm2), ("TOLPA", tolpa), ("PEREGREV", peregrev), ("ETS", ets), ("ATTENTION_ETB", attention)):
        try:
            rez[k] = f()
        except Exception as e:
            rez[k] = {"oshibka": f"{type(e).__name__}: {e}"[:200]}
    print(json.dumps(rez, ensure_ascii=False, indent=1))
