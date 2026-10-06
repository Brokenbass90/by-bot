#!/usr/bin/env python3
"""os2/signaly.py — потоки сделок ног для B3 (Trading OS v2). Переиспользует research_lab/orchestrator.py
(симуляция, издержки 6 bps/сторона, SEALED_FROM 2025-10-01 — запечатанное не читается), паузы исправлены (÷12).
Режим к сделке НЕ привязывается здесь: B2 выбирает определение режима отдельно, до просмотра исходов.
Запуск (в screen, ~10–25 мин на ногу):  python3 research_lab/os2/signaly.py ETS2 ASR1 SF3
Выход: research_lab/os2/potoki/<НОГА>.json (+ sha256 в potoki/MANIFEST.json)."""
import glob, hashlib, json, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB)); sys.path.insert(0, str(LAB.parent))
import orchestrator as O

NOGI = {  # (модуль, класс, префикс, сторона, множитель стопа, удержание ч, режимы — не используются, пауза в вызовах)
    "ATT1": ("alt_trendline_touch_v1", "AltTrendlineTouchV1Strategy", "ATT1", "short", 6.0, 336, (), 8),
    "SBR1": ("sloped_break_retest_v1", "SlopedBreakRetestV1Strategy", "SBR1", "long", 4.0, 168, (), 0),
    "ASR1": ("alt_support_reclaim_v1", "AltSupportReclaimV1Strategy", "ASR1", "long", 4.0, 168, (), 6),
    "ETS2": ("elder_triple_screen_v2", "ElderTripleScreenV2Strategy", "ETS2", "short", 4.0, 168, (), 3),
    "SF3":  ("spike_fade_v3", "SpikeFadeV3Strategy", "SF3", "short", 4.0, 336, (), 0),
}

def main(imena):
    out = LAB / "os2" / "potoki"; out.mkdir(parents=True, exist_ok=True)
    files = sorted(glob.glob(f"{O.DATA}/*.npz"))
    d = np.load(f"{O.DATA}/BTCUSDT.npz"); c = d["ohlcv"][:, 3].astype(float); e = O.ema(c, 200)
    man_p = out / "MANIFEST.json"; man = json.loads(man_p.read_text()) if man_p.exists() else {}
    for n in imena:
        O.LEGS = [NOGI[n]]
        print(f"=== {n}: генерация", flush=True)
        tr = O.build_trades(files, d["ts"], (c - e) / e)
        for t in tr: t.pop("reg", None)          # режим назначит B2
        b = json.dumps(tr).encode(); (out / f"{n}.json").write_bytes(b)
        man[n] = {"sdelok": len(tr), "sha256": hashlib.sha256(b).hexdigest(), "noga": list(NOGI[n])}
        man_p.write_text(json.dumps(man, ensure_ascii=False, indent=1))
        print(f"=== {n}: сделок {len(tr)}", flush=True)

if __name__ == "__main__":
    main(sys.argv[1:] or ["ETS2", "ASR1", "SF3"])
