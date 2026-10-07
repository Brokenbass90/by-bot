#!/usr/bin/env python3
"""os2/signaly.py — потоки сделок ног для B3 (Trading OS v2). Переиспользует research_lab/orchestrator.py
(симуляция, издержки 6 bps/сторона, SEALED_FROM 2025-10-01 — запечатанное не читается).
Исправлено в обвязке (стратегии не тронуты): пауза в вызовах = штатная (5m-бары) × 5 / база; удержание задаётся в ЧАСАХ
и переводится в бары базы; ноги с входом на 15m (ETS2, SF3) считаются на 15m-данных (os2/dannye_15m из m5), а не на H1.
Режим к сделке НЕ привязывается (B2/B3 отдельно).
Запуск:  .venv/bin/python research_lab/os2/signaly.py ETS2 SF3      (база и данные берутся из NOGI)"""
import glob, hashlib, json, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB)); sys.path.insert(0, str(LAB.parent))
import orchestrator as O

H1 = str(LAB / "data/h1"); M15 = str(LAB / "os2/dannye_15m")
# нога: модуль, класс, префикс env, сторона, множитель стопа (как в orchestrator 08.2026; BOUNCE1 — 1.0 = стоп стратегии),
#       удержание ЧАСОВ, пауза штатная в 5m-барах, данные, база мин, символы (None = все файлы)
NOGI = {
    "ATT1":    ("alt_trendline_touch_v1", "AltTrendlineTouchV1Strategy", "ATT1", "short", 6.0, 336, 96, H1, 60, None),
    "SBR1":    ("sloped_break_retest_v1", "SlopedBreakRetestV1Strategy", "SBR1", "long", 4.0, 168, 0, H1, 60, None),
    "ASR1":    ("alt_support_reclaim_v1", "AltSupportReclaimV1Strategy", "ASR1", "long", 4.0, 168, 72, H1, 60, None),
    "ETS2":    ("elder_triple_screen_v2", "ElderTripleScreenV2Strategy", "ETS2", "short", 4.0, 168, 36, M15, 15, None),
    "SF3":     ("spike_fade_v3", "SpikeFadeV3Strategy", "SF3", "short", 4.0, 336, 0, M15, 15, None),
    "BOUNCE1": ("alt_support_bounce_v1", "AltSupportBounceV1Strategy", "BOUNCE1", "long", 1.0, 48, 72, H1, 60, ["BTCUSDT", "ETHUSDT"]),
}

def main(imena):
    out = LAB / "os2" / "potoki"; out.mkdir(parents=True, exist_ok=True)
    d = np.load(f"{H1}/BTCUSDT.npz"); c = d["ohlcv"][:, 3].astype(float); e = O.ema(c, 200)
    man_p = out / "MANIFEST.json"; man = json.loads(man_p.read_text()) if man_p.exists() else {}
    for n in imena:
        mod, cls, pfx, side, mult, hold_h, cd5, data, baza, syms = NOGI[n]
        k = 60 // baza
        files = sorted(glob.glob(f"{data}/*.npz"))
        if syms: files = [f for f in files if Path(f).stem in syms]
        O.LEGS = [(mod, cls, pfx, side, mult, hold_h * k, (), int(round(cd5 * 5 / baza)))]
        print(f"=== {n}: генерация, база {baza}m, монет {len(files)}", flush=True)
        tr = O.build_trades(files, d["ts"], (c - e) / e)
        for t in tr:
            t.pop("reg", None); t["hours"] = int(np.ceil(t["hours"] / k))
        b = json.dumps(tr).encode(); (out / f"{n}.json").write_bytes(b)
        man[n] = {"sdelok": len(tr), "sha256": hashlib.sha256(b).hexdigest(), "noga": [str(x) for x in NOGI[n]], "monet": len(files)}
        man_p.write_text(json.dumps(man, ensure_ascii=False, indent=1))
        print(f"=== {n}: сделок {len(tr)}", flush=True)

if __name__ == "__main__":
    main(sys.argv[1:] or ["ETS2", "SF3"])
