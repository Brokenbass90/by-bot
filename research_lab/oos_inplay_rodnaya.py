#!/usr/bin/env python3
"""OOS 2026-07-01…сейчас для inplay_retest (родная геометрия), PREREG_INPLAY_RODNAYA_GEOMETRIYA_2026_10_20.
Запускать ТОЛЬКО для стратегий с DEV_PASS:  .venv/bin/python3 research_lab/oos_inplay_rodnaya.py inplay_retest_v3
Публичные 15m свечи Bybit (62 монеты из data/m15), без ключей/ордеров. Итог: research_lab/results/oos_inplay_<стратегия>.json"""
import glob, json, math, os, sys, time, urllib.request
from pathlib import Path
import numpy as np
KOREN = Path(__file__).resolve().parents[1]; os.chdir(KOREN)
sys.path.insert(0, str(KOREN)); sys.path.insert(0, str(KOREN / "research_lab"))
import inplay_rodnaya as N                      # тот же симулятор и правила
import skan_m15 as S
from research_machine import Store, pervyy_argument
OKNO_S, RAZOGREV_S, M15 = 1782864000000, 1774972800000, 900_000      # 2026-07-01; разогрев с 2026-04-01
PROG = 2.24


def svechi(sym, s, e):
    out = []
    while s < e:
        u = (f"https://api.bybit.com/v5/market/kline?category=linear&symbol={sym}&interval=15&start={s}"
             f"&end={min(e, s + 999 * M15)}&limit=1000")
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "oos/1.0"}), timeout=25) as f:
            lst = ((json.loads(f.read().decode()).get("result") or {}).get("list") or [])
        part = sorted([int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in lst)
        if not part: break
        out.extend(p for p in part if not out or p[0] > out[-1][0]); s = part[-1][0] + M15; time.sleep(0.1)
    return out


def main():
    mod = sys.argv[1]; kesh = Path("research_lab/data/oos_bybit_m15_20261020"); kesh.mkdir(parents=True, exist_ok=True)
    now = int(time.time() * 1000); B = {}
    for f in sorted(glob.glob("research_lab/data/m15/*.npz")):
        sym = Path(f).stem; p = kesh / f"{sym}.json"
        if not p.exists():
            try: p.write_text(json.dumps([x for x in svechi(sym, RAZOGREV_S, (now // M15) * M15) if x[0] + M15 <= now]))
            except Exception: p.write_text("[]")
        b = json.loads(p.read_text())
        if len(b) > 2000: B[sym] = b
    S.OKNA = {"OOS": (OKNO_S, 10 ** 13)}; N.S.OKNA = S.OKNA
    r = N.progon(S.klass(mod), B); o = r.get("OOS", {})
    r["OOS_PASS"] = bool(o.get("n", 0) >= 50 and o.get("edzh", -1) > 0 and o.get("sigma", 0) >= PROG and o["monet_v_pluse"] * 2 >= o["monet"])
    r.pop("DEV_PASS", None); r["strategiya"] = mod; r["simvolov"] = len(B)
    out = Path(f"research_lab/results/oos_inplay_{mod}.json"); out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(r, ensure_ascii=False, indent=1, default=lambda x: x.item() if hasattr(x, "item") else str(x)))
    print(json.dumps(r, ensure_ascii=False, default=lambda x: x.item() if hasattr(x, "item") else str(x)))


if __name__ == "__main__":
    main()
