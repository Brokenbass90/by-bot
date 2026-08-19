#!/usr/bin/env python3
"""verify_live_config.py — совпадёт ли живая конфигурация с симуляцией.

ЗАЧЕМ. Симуляция генерирует сигналы штатными параметрами и расширяет
стоп только на этапе расчёта. Живой бот так не умеет: он получит
ATT1_SL_ATR_MULT=6.60 и начнёт СРАЗУ строить широкие стопы — а его
собственный валидатор отбрасывает всё, что шире max_stop_pct.

Этот скрипт ставит переменные ровно так, как написано в спецификации,
прогоняет стратегию и считает сигналы. Если их станет меньше, чем
в симуляции, — спецификация неверна и нога в бою замолчит.

Ровно так двенадцать дней молчал коллектор Inplay.

Запуск:
    python3 research_lab/verify_live_config.py
"""
from __future__ import annotations
import glob, importlib, os, sys
from pathlib import Path
import numpy as np

ROOT = str(Path(__file__).resolve().parents[1])
DATA = f"{ROOT}/research_lab/data/h1"
sys.path.insert(0, ROOT)
sys.path.insert(0, f"{ROOT}/research_lab")
from research_machine import Store, ema

SEAL = 1759276800000
LOOKBACK = 120

CASES = [
    ("ATT1 штатный (как сейчас в боте)", "alt_trendline_touch_v1",
     "AltTrendlineTouchV1Strategy", "ATT1", "short",
     {"ATT1_COOLDOWN_BARS_5M": "8"}),
    ("ATT1 по спецификации БЕЗ правки потолка", "alt_trendline_touch_v1",
     "AltTrendlineTouchV1Strategy", "ATT1", "short",
     {"ATT1_COOLDOWN_BARS_5M": "8", "ATT1_SL_ATR_MULT": "6.60",
      "ATT1_BE_TRIGGER_RR": "0", "ATT1_TRAIL_ATR_MULT": "0"}),
    ("ATT1 по спецификации С правкой потолка", "alt_trendline_touch_v1",
     "AltTrendlineTouchV1Strategy", "ATT1", "short",
     {"ATT1_COOLDOWN_BARS_5M": "8", "ATT1_SL_ATR_MULT": "6.60",
      "ATT1_BE_TRIGGER_RR": "0", "ATT1_TRAIL_ATR_MULT": "0",
      "ATT1_MAX_STOP_PCT": "0.25"}),
    ("SBR1 штатный", "sloped_break_retest_v1",
     "SlopedBreakRetestV1Strategy", "SBR1", "long", {}),
    ("SBR1 по спецификации", "sloped_break_retest_v1",
     "SlopedBreakRetestV1Strategy", "SBR1", "long",
     {"SBR1_SL_ATR_MULT": "4.60", "SBR1_BE_TRIGGER_RR": "0",
      "SBR1_TRAIL_ATR_MULT": "0", "SBR1_ALLOW_SHORTS": "0"}),
]


def run(mod, cls, pfx, side, env, files):
    for k in list(os.environ):
        if k.startswith(pfx + "_"):
            del os.environ[k]
    os.environ[f"{pfx}_SYMBOL_ALLOWLIST"] = ",".join(Path(f).stem for f in files)
    os.environ[f"{pfx}_ALLOW_LONGS"] = "1"
    os.environ[f"{pfx}_ALLOW_SHORTS"] = "1"
    os.environ.update(env)
    for m in list(sys.modules):
        if m.startswith("strategies."):
            del sys.modules[m]
    S = getattr(importlib.import_module(f"strategies.{mod}"), cls)
    n, stops = 0, []
    for fp in files:
        d = np.load(fp); ts, o = d["ts"], d["ohlcv"].astype(float)
        m = ts < SEAL
        ts, o = ts[m], o[m]
        if len(ts) < LOOKBACK + 300:
            continue
        bars = [[int(ts[x]), o[x, 0], o[x, 1], o[x, 2], o[x, 3], o[x, 4]]
                for x in range(len(ts))]
        st = Store(Path(fp).stem); strat = S()
        for i in range(LOOKBACK, len(bars)):
            st.rows = bars[: i + 1]; b = bars[i]
            try:
                s = strat.maybe_signal(st, b[0], b[1], b[2], b[3], b[4], b[5])
            except Exception:
                continue
            if s is None or s.side != side:
                continue
            n += 1
            stops.append(abs(s.entry - s.sl) / s.entry * 100)
    return n, (float(np.median(stops)) if stops else 0.0)


def main():
    files = sorted(glob.glob(f"{DATA}/*.npz"))[:25]
    print(f"проверка на {len(files)} символах, до запечатанного периода\n")
    print(f"{'конфигурация':<44}{'сигналов':>10}{'стоп, % цены':>14}")
    base = {}
    for name, mod, cls, pfx, side, env in CASES:
        n, sp = run(mod, cls, pfx, side, env, files)
        if "штатный" in name:
            base[pfx] = n
        rel = ""
        if pfx in base and base[pfx]:
            rel = f"  ({n * 100 // base[pfx]}% от штатного)"
        print(f"{name:<44}{n:>10}{sp:>13.2f}%{rel}")
    print("\nЕсли по спецификации сигналов заметно меньше штатного —")
    print("нога в бою замолчит, и спецификацию надо править ДО запуска.")


if __name__ == "__main__":
    main()
