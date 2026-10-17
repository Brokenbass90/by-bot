#!/usr/bin/env python3
"""MAKRO события (заморожено 17.10.2026 до доходностей). Календарь: data/makro/kalendar_v1.json (federalreserve.gov, bls.gov).
CPI_PEREREAKCIYA: час-бар, содержащий 08:30 ET релиза; знак = −sign(доходность этого бара); вход — следующий бар.
PRE_FOMC: вход за 24 ч до заявления (14:00 ET), знак +1, удержание 24 бара (выход на баре заявления, до объявления).
"""
import json, hashlib, datetime as dt
import numpy as np
from pathlib import Path
from zoneinfo import ZoneInfo
LAB = Path(__file__).resolve().parents[1]; NY = ZoneInfo("America/New_York"); H = 3_600_000

def ms(d, hh, mm):
    return int(dt.datetime.combine(dt.date.fromisoformat(d), dt.time(hh, mm), NY).astimezone(dt.timezone.utc).timestamp() * 1000)

def main():
    k = json.loads((LAB / "data/makro/kalendar_v1.json").read_text())
    z = np.load(LAB / "data/h1/BTCUSDT.npz"); ts = z["ts"].astype(np.int64); x = z["ohlcv"].astype(float)
    idx = {int(t): i for i, t in enumerate(ts)}
    cpi = []
    for d in k["cpi"]:
        b = ms(d, 8, 30) // H * H; i = idx.get(b)
        if i is None or i + 1 >= len(ts): continue
        r = x[i, 3] / x[i, 0] - 1
        if r == 0: continue
        cpi.append(dict(t_ms=int(ts[i + 1]), simvol="BTCUSDT", znak=-1 if r > 0 else 1))
    fomc = [dict(t_ms=ms(d, 14, 0) - 24 * H, simvol="BTCUSDT", znak=1) for d in k["fomc"]]
    out = LAB / "data/makro"; man = dict(gotovo=True, kalendar_sha256=hashlib.sha256((out / "kalendar_v1.json").read_bytes()).hexdigest())
    for imya, ev in (("cpi_pereakciya", cpi), ("pre_fomc", fomc)):
        f = out / f"sobytiya_{imya}_v1.json"; f.write_text(json.dumps(ev))
        man[imya] = dict(sobytiy=len(ev), sha256=hashlib.sha256(f.read_bytes()).hexdigest())
    man["kod_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (out / "MANIFEST.json").write_text(json.dumps(man, ensure_ascii=False, indent=1)); print(man)

if __name__ == "__main__":
    main()
