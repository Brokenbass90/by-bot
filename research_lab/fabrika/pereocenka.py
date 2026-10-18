#!/usr/bin/env python3
"""pereocenka.py — Factory, исправление №1 (FACTORY_SOSTOYANIE_AVTONOMNOSTI_2026_10_18): регулярная переоценка живых/теневых
стратегий против их эталона. Хук сторожа; пересчёт раз в сутки; только отчёт data/storozh/PEREOCENKA.json, ничего не выключает.
Паспорта (эталоны) заморожены здесь; изменение эталона = новая версия файла. Статусы: OK / DEGRADACIYA / MALO_DANNYH.
DEGRADACIYA: среднее последних n наблюдений ниже эталона больше чем на 2 стандартные ошибки (n ≥ min_n)."""
import datetime as dt, json, time
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; D = LAB / "data"; OUT = D / "storozh/PEREOCENKA.json"


def _jsonl(p): return [json.loads(s) for s in p.read_text().splitlines() if s.strip()] if p.exists() else []


def att1(): return [x["R"] for x in _jsonl(D / "ten_ATT1.jsonl") if "R" in x]
def asm1(): return [x["R"] for x in _jsonl(D / "asm1_fiks/ishody.jsonl")]
def etf(): return [x["R_bps"] for x in _jsonl(D / "etf_premiya/ishody_ETF_PREMIYA.jsonl") if x.get("vhod") == "isp"]
def kity():
    out = []
    for p in sorted((D / "kity_bybit_ten").glob("20*/vyhod.json")):
        v = json.loads(p.read_text())
        if v.get("nedelya_bps") is not None: out.append(v["nedelya_bps"])
    return out


PASPORTA = {   # эталон = DEV/исторический результат из квитанций; единицы — как у ряда
    "ATT1_TEN": dict(ryad=att1, etalon=0.0, edinica="R после издержек", min_n=200, okno=500,
                     istochnik="ATT1_VOSSTANOVLENIE_ISTORII_2026_10_18.md (эталон 0 = безубыточность; DEV не положителен)"),
    "KITY_M3_TEN": dict(ryad=kity, etalon=57.6, edinica="bps/нед, среднее по ногам", min_n=8, okno=26,
                        istochnik="data/KITY_BYBIT_KVITANCIYA.json"),
    "ASM1_FIKS": dict(ryad=asm1, etalon=0.0, edinica="R", min_n=30, okno=100, istochnik="PREREG_ASM1_FIKS_VPERED_2026_10_17.md"),
    "ETF_PREMIYA_BTC": dict(ryad=etf, etalon=78.1, edinica="bps после 11 bps, исполнимый вход", min_n=10, okno=50,
                            istochnik="реестр ETF_PREMIYA_BTC_V1_1: сырой после издержек +78.1 bps, n 48"),
}


def ocenit(imya, p):
    x = np.array(p["ryad"](), float)[-p["okno"]:]
    if p["etalon"] is None or len(x) < p["min_n"]:
        return dict(status="MALO_DANNYH" if p["etalon"] is not None else "NET_ETALONA", n=int(len(x)), edinica=p["edinica"])
    m = float(x.mean()); se = float(x.std(ddof=1) / np.sqrt(len(x)))
    st = "DEGRADACIYA" if m < p["etalon"] - 2 * se else "OK"
    return dict(status=st, n=int(len(x)), sredn=round(m, 4), se=round(se, 4), etalon=p["etalon"], edinica=p["edinica"], istochnik=p["istochnik"])


def prohod():
    if OUT.exists() and time.time() - OUT.stat().st_mtime < 20 * 3600: return dict(status="uzhe_segodnya")
    rez = {k: ocenit(k, p) for k, p in PASPORTA.items()}
    OUT.write_text(json.dumps(dict(kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), strategii=rez), ensure_ascii=False, indent=1))
    return {k: v["status"] for k, v in rez.items()}


if __name__ == "__main__":
    print(json.dumps(prohod(), ensure_ascii=False))
