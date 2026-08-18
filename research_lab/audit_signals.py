#!/usr/bin/env python3
"""audit_signals.py — проверка входов и выходов стратегий на баги и логику.

Не про прибыль. Про то, что сигнал вообще корректный.

Семь проверок на каждой стратегии:

  1. ЗАВИСИМОСТЬ ОТ ГЛУБИНЫ ИСТОРИИ. Сигнал считается дважды: с полной
     историей до текущего бара и с обрезанной до 400 баров. Если решения
     разошлись — уровни стратегии зависят от того, сколько истории ей
     дали. В тесте истории тысячи баров, в бою — фиксированное окно
     запроса. Это прямое расхождение теста и боя.
  2. СТОП НЕ С ТОЙ СТОРОНЫ. У лонга стоп обязан быть ниже входа,
     у шорта — выше.
  3. ЦЕЛИ НЕ С ТОЙ СТОРОНЫ ИЛИ НЕ ПО ПОРЯДКУ.
  4. ДОЛИ ЦЕЛЕЙ. Сумма tp_fracs не должна превышать 1.
  5. ВХОД НЕ ПО ТОЙ СВЕЧЕ. Стратегия объявляет entry. Сравниваем его
     с закрытием сигнальной свечи и с открытием следующей. Разрыв
     меряем в долях риска: это цена того, что в бою мы входим позже.
  6. ПОВТОРЫ. Сколько баров подряд горит один и тот же сигнал. Если
     много — одна идея превращается в двадцать «сделок», и любая
     статистика по ним завышена.
  7. ПЛЕЧО. entry / |entry - sl|. Больше 50 — издержки съедят всё.

Запуск:
    python3 research_lab/audit_signals.py --symbols 6
"""
from __future__ import annotations
import argparse, glob, importlib, json, os, sys
from pathlib import Path
import numpy as np

ROOT = str(Path(__file__).resolve().parents[1])
DATA = f"{ROOT}/research_lab/data/h1"
LOOKBACK = 120

STRATS = [
    ("alt_trendline_touch_v1",     "AltTrendlineTouchV1Strategy",     "ATT1"),
    ("alt_support_reclaim_v1",     "AltSupportReclaimV1Strategy",     "ASR1"),
    ("alt_sloped_channel_v1",      "AltSlopedChannelV1Strategy",      "ASC1"),
    ("alt_horizontal_break_v1",    "AltHorizontalBreakV1Strategy",    "HZBO1"),
    ("alt_channel_bounce_v1",      "AltChannelBounceV1Strategy",      "ACB1"),
    ("alt_range_reclaim_v1",       "AltRangeReclaimV1Strategy",       "ARR1"),
    ("alt_range_scalp_v1",         "AltRangeScalpV1Strategy",         "ARS1"),
    ("alt_resistance_fade_v1",     "AltResistanceFadeV1Strategy",     "ARF1"),
    ("alt_resistance_fade_v2",     "AltResistanceFadeV2Strategy",     "ARF2"),
    ("spike_fade_v3",              "SpikeFadeV3Strategy",             "SF3"),
    ("pump_fade_smart_v1",         "PumpFadeSmartV1Strategy",         "PFS1"),
    ("impulse_volume_breakout_v1", "ImpulseVolumeBreakoutV1Strategy", "IVB1"),
    ("elder_triple_screen_v2",     "ElderTripleScreenV2Strategy",     "ETS2"),
]


class Store:
    """стакан баров; rows задаётся снаружи"""
    def __init__(self, sym):
        self.symbol = sym
        self.rows = []

    def fetch_klines(self, sym, tf, n):
        return self.rows[-n:]


def sig_key(s):
    if s is None:
        return None
    return (s.side, round(float(s.entry), 10), round(float(s.sl), 10),
            tuple(round(float(x), 10) for x in (s.tps or [])))


def audit(mod, cls, prefix, files, verbose=False):
    syms = ",".join(sorted(Path(f).stem for f in files))
    os.environ[f"{prefix}_SYMBOL_ALLOWLIST"] = syms
    os.environ.setdefault(f"{prefix}_ALLOW_LONGS", "1")
    os.environ.setdefault(f"{prefix}_ALLOW_SHORTS", "1")
    try:
        Strategy = getattr(importlib.import_module(f"strategies.{mod}"), cls)
    except Exception as e:
        return dict(error=f"{type(e).__name__}: {e}")

    r = dict(n=0, future=0, sl_side=0, tp_side=0, tp_order=0, frac=0,
             entry_is_close=0, entry_other=0, gaps=[], levs=[], runs=[], err=0)
    for fp in files:
        d = np.load(fp); ts, o = d["ts"], d["ohlcv"].astype(float)
        bars = [[int(ts[x]), o[x, 0], o[x, 1], o[x, 2], o[x, 3], o[x, 4]]
                for x in range(len(ts))]
        if len(bars) < LOOKBACK + 200:
            continue
        sym = Path(fp).stem
        st_now, st_cut = Store(sym), Store(sym)
        strat_now, strat_cut = Strategy(), Strategy()
        prev, run = None, 0
        for i in range(LOOKBACK, len(bars) - 1):
            b = bars[i]
            st_now.rows = bars[: i + 1]
            try:
                s = strat_now.maybe_signal(st_now, b[0], b[1], b[2], b[3], b[4], b[5])
            except Exception:
                r["err"] += 1
                continue
            k = sig_key(s)
            # повторы
            if k is not None and k == prev:
                run += 1
            else:
                if run:
                    r["runs"].append(run + 1)
                run = 0
            prev = k
            if s is None:
                continue
            r["n"] += 1

            # 1. зависимость от глубины истории.
            # Свежий объект прогревается предыдущим баром: почти все
            # стратегии пропускают самый первый вызов (_last_tf_ts is None).
            try:
                s2 = Strategy(); c2 = Store(sym)
                sc = None
                # ПРОГРЕВ 10 БАРОВ. Часть стратегий — двухступенчатые
                # автоматы (сначала «заготовка», через N баров
                # подтверждение). Одного вызова им мало, и без прогрева
                # тест ловит собственную недоработку, а не баг стратегии.
                for j in range(i - 10, i + 1):
                    c2.rows = bars[max(0, j - 399): j + 1]
                    pb = bars[j]
                    sc = s2.maybe_signal(c2, pb[0], pb[1], pb[2], pb[3], pb[4], pb[5])
                if sig_key(sc) != k:
                    r["future"] += 1
            except Exception:
                pass

            entry, sl = float(s.entry), float(s.sl)
            long = s.side == "long"
            # 2. сторона стопа
            if (sl >= entry) if long else (sl <= entry):
                r["sl_side"] += 1
                continue
            risk = abs(entry - sl)
            r["levs"].append(entry / risk if risk else 1e9)
            # 3. цели
            tps = [float(x) for x in (s.tps or []) if x]
            if tps:
                if any((t <= entry) if long else (t >= entry) for t in tps):
                    r["tp_side"] += 1
                srt = sorted(tps, reverse=not long)
                if srt != tps:
                    r["tp_order"] += 1
            # 4. доли
            fr = [float(x) for x in (s.tp_fracs or [])]
            if fr and sum(fr) > 1.0 + 1e-9:
                r["frac"] += 1
            # 5. по какой свече вход
            close_i, open_next = float(b[4]), float(bars[i + 1][1])
            if abs(entry - close_i) < 1e-12:
                r["entry_is_close"] += 1
            else:
                r["entry_other"] += 1
                lo, hi = float(b[3]), float(b[2])
                if lo <= entry <= hi:
                    r["entry_inbar"] = r.get("entry_inbar", 0) + 1
            r["gaps"].append(((open_next - entry) if long else (entry - open_next)) / risk)
        if run:
            r["runs"].append(run + 1)
    return r


def line(name, r):
    if "error" in r:
        return f"{name:<8} НЕ ЗАГРУЗИЛАСЬ: {r['error'][:60]}"
    if r["n"] == 0:
        return f"{name:<8} сигналов 0 — проверять нечего (ошибок внутри: {r['err']})"
    g = np.array(r["gaps"]) if r["gaps"] else np.array([0.0])
    lv = np.array(r["levs"]) if r["levs"] else np.array([0.0])
    runs = np.array(r["runs"]) if r["runs"] else np.array([1])
    flags = []
    if r["future"]:
        flags.append(f"ЗАВИСИТ ОТ ГЛУБИНЫ {r['future']*100//max(1,r['n'])}%")
    if r["sl_side"]:
        flags.append(f"стоп-сторона {r['sl_side']}")
    if r["tp_side"]:
        flags.append(f"цель-сторона {r['tp_side']}")
    if r["tp_order"]:
        flags.append(f"цели-порядок {r['tp_order']}")
    if r["frac"]:
        flags.append(f"доли>1 {r['frac']}")
    if np.median(lv) > 50:
        flags.append(f"плечо {np.median(lv):.0f}")
    if np.median(runs) > 3:
        flags.append(f"повтор x{np.median(runs):.0f}")
    if abs(np.median(g)) > 0.05:
        flags.append(f"разрыв входа {np.median(g):+.3f}R")
    if r.get("entry_inbar"):
        flags.append(f"ВХОД ВНУТРИ СВЕЧИ {r['entry_inbar']*100//max(1,r['n'])}%")
    return (f"{name:<8}n={r['n']:<6} вход=закрытие {r['entry_is_close']*100//max(1,r['n'])}%  "
            f"плечо {np.median(lv):>5.0f}  разрыв {np.median(g):>+7.4f}R  "
            f"повтор x{np.median(runs):.0f}  " + ("| " + ", ".join(flags) if flags else "| чисто"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", type=int, default=6)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    sys.path.insert(0, ROOT)
    files = sorted(glob.glob(f"{DATA}/*.npz"))[: a.symbols]
    print(f"аудит на {len(files)} символах, часовые бары\n")
    print("порядок колонок: сколько сигналов | вход равен закрытию свечи | "
          "плечо | разрыв между объявленным входом и открытием следующей свечи | "
          "сколько баров подряд горит один сигнал\n")
    out = {}
    for mod, cls, pfx in STRATS:
        if a.only and pfx.lower() != a.only.lower():
            continue
        r = audit(mod, cls, pfx, files)
        out[pfx] = {k: v for k, v in r.items() if k not in ("gaps", "levs", "runs")}
        print(line(pfx, r), flush=True)
    Path(f"{ROOT}/research_lab/audit_signals.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nсводка: research_lab/audit_signals.json")


if __name__ == "__main__":
    main()
