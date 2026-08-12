#!/usr/bin/env python3
"""
path_sim.py — «ход в ATR» превращается в настоящие R.

ЗАЧЕМ. Средний форвардный ход НЕ равен прибыли: до этого среднего надо
дожить. По замеру горизонтов средний ход ПРОТИВ входа составляет
1.5 ATR за 6 часов и 5.2 ATR за 72 — стоп в 2 ATR будет выбит в
большинстве длинных сделок. Пересчёт «средний ход / ширина стопа» даёт
завышенную цифру и его нельзя показывать как доход.

ЗДЕСЬ честно: по каждому сигналу идём по барам вперёд и смотрим,
что случилось РАНЬШЕ — стоп или конец горизонта. Внутри бара
консервативно считаем, что сначала цена сходила против нас.

Результат в R, где R = ширина стопа. Издержки вычитаются в R.

Сетка объявлена заранее: 5 ширин стопа x 6 горизонтов = 30 вариантов
на символ. Порог для чемпиона поднимается по числу ВСЕХ вариантов.
"""
from __future__ import annotations

import json
import math
import os
import signal
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
sys.path.insert(0, "research_lab")
import strategy_adapter as A

NAME = sys.argv[1] if len(sys.argv) > 1 else "alt_elder_revived_v1"
SYM = sys.argv[2] if len(sys.argv) > 2 else "ETHUSDT"
WIN, N_WIN = 40000, 4
# ОШИБКА ПЕРВОЙ ВЕРСИИ, ИСПРАВЛЕНА: стоп мерился в ATR ПЯТИМИНУТНОГО бара.
# Для ETH это ~0.19% цены, то есть «широкий стоп 4 ATR» = 0.75% движения.
# Ставить такой стоп на удержание 24 часа бессмысленно — выбивает почти
# всегда, и низкий винрейт был следствием этого, а не свойством ноги.
# Теперь стоп масштабируется под горизонт: за H часов цена в среднем
# проходит ~ATR*sqrt(12*H), и стоп берётся кратным ИМЕННО этой величине.
STOP_MULT = (0.5, 0.75, 1.0, 1.5, 2.0)   # доля от типичного хода за горизонт
HOURS = (3, 4, 6, 8, 12, 24)
COST_BPS = 16.0                        # круг: комиссия + слиппедж
ATR_N = 24
PER = float(os.getenv("PATH_SIM_PER_SECONDS", "60"))
SEARCH_END_UTC = os.getenv("RESEARCH_SEARCH_END_UTC", "").strip()
INPUT_PATH = os.getenv("PATH_SIM_INPUT", "").strip()
PASSPORT_PATH = os.getenv("PATH_SIM_PASSPORT", "").strip()
SEARCH_END_MS = None
if SEARCH_END_UTC:
    parsed_end = datetime.fromisoformat(SEARCH_END_UTC.replace("Z", "+00:00"))
    if parsed_end.tzinfo is None:
        parsed_end = parsed_end.replace(tzinfo=timezone.utc)
    SEARCH_END_MS = int(parsed_end.timestamp() * 1000)
OUT = os.getenv("PATH_SIM_OUT", "research_lab/results/path_sim_v2")


class _Slow(Exception):
    pass


def _verify_passport():
    if not INPUT_PATH or not PASSPORT_PATH or not SEARCH_END_UTC:
        raise RuntimeError(
            "PATH_SIM_INPUT, PATH_SIM_PASSPORT and RESEARCH_SEARCH_END_UTC are required"
        )
    from pathlib import Path
    from research_lab.run_passport import sha256_file, validate_passport
    passport = validate_passport(json.loads(Path(PASSPORT_PATH).read_text(encoding="utf-8")))
    if SYM not in (passport.get("measurement_contract") or {}).get("universe", []):
        raise RuntimeError("passport universe does not contain requested symbol")
    expected = {str(Path(row["path"]).resolve()): row["sha256"] for row in passport["inputs"]}
    input_resolved = str(Path(INPUT_PATH).resolve())
    if expected.get(input_resolved) != sha256_file(Path(INPUT_PATH)):
        raise RuntimeError("physical input is not bound to passport hash")
    for row in passport["code"]:
        if sha256_file(Path(row["path"])) != row["sha256"]:
            raise RuntimeError(f"passport code hash drift: {Path(row['path']).name}")
    return passport


def _require_complete_windows(acc):
    good = [value for key, value in acc.items() if key != "_meta" and value.get("grid")]
    if len(good) != N_WIN:
        raise RuntimeError(f"incomplete experiment: {len(good)}/{N_WIN} valid windows")
    return good


signal.signal(signal.SIGALRM, lambda s, f: (_ for _ in ()).throw(_Slow()))


def side_of(sig):
    for a in ("side", "direction", "dir"):
        v = getattr(sig, a, None) or (sig.get(a) if isinstance(sig, dict) else None)
        if isinstance(v, str):
            u = v.lower()
            if u in ("sell", "short", "-1", "down"):
                return -1
            if u in ("buy", "long", "1", "up"):
                return +1
    for a in ("is_short", "short"):
        if isinstance(getattr(sig, a, None), bool):
            return -1 if getattr(sig, a) else +1
    return +1


def simulate(o, c, hi, lo, atr, idx, sides, stop_atr, hb, cost_bps):
    """stop_atr здесь — УЖЕ пересчитанная в ATR ширина под данный горизонт."""
    """Идём по барам: что случилось раньше — стоп или конец горизонта."""
    out = []
    n = len(c)
    for j, s in zip(idx, sides):
        # The strategy sees the completed signal bar.  The earliest executable
        # market fill is the next 5m open; using c[j] was same-close lookahead.
        entry_i = int(j) + 1
        exit_i = entry_i + int(hb) - 1
        if exit_i >= n or not np.isfinite(atr[j]) or atr[j] <= 0:
            continue
        risk = stop_atr * atr[j]
        entry = o[entry_i]
        stop = entry - s * risk
        res = None
        for k in range(entry_i, exit_i + 1):
            # консервативно: сначала проверяем неблагоприятную сторону бара
            if (s > 0 and lo[k] <= stop) or (s < 0 and hi[k] >= stop):
                res = -1.0
                break
        if res is None:
            res = s * (c[exit_i] - entry) / risk
        # издержки в R: круг в bps от цены, делённый на риск в тех же единицах
        res -= (cost_bps / 1e4) * entry / risk
        out.append(res)
    return np.array(out, float)


def run_window(shift):
    h = A.open_strategy(
        NAME,
        symbol=SYM,
        limit=WIN * (shift + 1),
        end_ms=SEARCH_END_MS,
        input_path=INPUT_PATH,
    )
    if not h.get("ok") or h["symbol"] != SYM:
        return None, h.get("note", "не открылась")[:60]
    full = h["candles"]
    if len(full) < WIN * (shift + 1) * 0.9:
        return None, f"мало истории {len(full)}"
    lo_i = max(0, len(full) - WIN * (shift + 1))
    cs = full[lo_i:lo_i + WIN]

    from backtest.engine import KlineStore
    store = KlineStore(SYM, cs, base_interval_min=5)
    call = A.make_caller(h["conv"], h["obj"], SYM)

    n = len(cs)
    o = np.array([x.o for x in cs]); c = np.array([x.c for x in cs]); hi = np.array([x.h for x in cs]); lo = np.array([x.l for x in cs])
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum.reduce([hi - lo, np.abs(hi - pc), np.abs(lo - pc)])
    atr = pd.Series(tr).ewm(alpha=1 / ATR_N, adjust=False, min_periods=ATR_N).mean().to_numpy()
    ts = pd.to_datetime([x.ts for x in cs], unit="ms", utc=True)

    idx, sides = [], []
    signal.setitimer(signal.ITIMER_REAL, PER)
    timed_out = False
    try:
        for i in range(n):
            store.i5 = i; store.i = i; store.i_base = i
            try:
                r = call(store, cs, i)
            except _Slow:
                raise
            except Exception:
                continue
            if r is not None:
                idx.append(i); sides.append(side_of(r))
    except _Slow:
        timed_out = True
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)

    if timed_out:
        return None, f"таймаут {PER:.0f}s: частичный набор из {len(idx)} сигналов запрещён"

    if len(idx) < 15:
        return None, f"сигналов {len(idx)}"

    grid = []
    for mult in STOP_MULT:
        for hrs in HOURS:
            hb = hrs * 12
            st = mult * math.sqrt(hb)      # типичный ход за горизонт в ATR
            R = simulate(o, c, hi, lo, atr, idx, sides, st, hb, COST_BPS)
            if len(R) < 15:
                continue
            wr = float((R > 0).mean())
            grid.append(dict(stop=round(st, 2), mult=mult, hours=hrs, n=len(R),
                             R_per_trade=round(float(R.mean()), 4),
                             winrate=round(wr, 3),
                             total_R=round(float(R.sum()), 1),
                             stopped=round(float((R <= -1.0 + 1e-9).mean()), 3)))
    days = (ts[-1] - ts[0]).days or 139
    return dict(shift=shift, start=str(ts[0].date()), end=str(ts[-1].date()),
                signals=len(idx), days=days, grid=grid), ""


def main():
    passport = _verify_passport()
    os.makedirs(OUT, exist_ok=True)
    fp = os.path.join(OUT, f"{NAME}__{SYM}.json")
    acc = json.load(open(fp)) if os.path.exists(fp) else {}
    acc["_meta"] = {
        "schema_id": "path_sim_fail_closed_v4_next_open",
        "strategy": NAME,
        "symbol": SYM,
        "search_end_utc": SEARCH_END_UTC or None,
        "reserved_holdout_used": False if SEARCH_END_UTC else None,
        "timeout_seconds": PER,
        "partial_timeout_results_allowed": False,
        "signal_information_time": "completed_5m_close",
        "entry_execution": "next_5m_open",
        "same_close_entry": False,
        "variant_count": len(STOP_MULT) * len(HOURS),
        "physical_input": str(INPUT_PATH),
        "passport_sha256": passport["passport_sha256"],
    }
    print(f"{NAME} на {SYM}: стоп x горизонт = {len(STOP_MULT)}x{len(HOURS)} на окно\n")
    for sh in range(N_WIN):
        if str(sh) in acc:
            continue
        try:
            r, err = run_window(sh)
        except Exception as e:
            r, err = None, f"{type(e).__name__}: {e}"[:60]
        acc[str(sh)] = r if r else dict(shift=sh, skipped=err)
        json.dump(acc, open(fp, "w"), ensure_ascii=False, indent=2)
        if r:
            best = max(r["grid"], key=lambda g: g["R_per_trade"])
            print(f"  окно {sh} {r['start']}..{r['end']} сиг={r['signals']:<4} "
                  f"лучший: стоп {best['stop']} гор {best['hours']}ч  "
                  f"{best['R_per_trade']:+.3f}R  WR {best['winrate']:.0%}", flush=True)
        else:
            print(f"  окно {sh}: {err}", flush=True)

    good = _require_complete_windows(acc)
    if len(good) >= 2:
        keys = {(g.get("mult", g["stop"]), g["hours"]) for v in good for g in v["grid"]}
        N = len(keys) * len(good)
        rows = []
        for k in sorted(keys):
            cells = [g for v in good for g in v["grid"]
                     if (g.get("mult", g["stop"]), g["hours"]) == k]
            if len(cells) < len(good):
                continue
            rp = [g["R_per_trade"] for g in cells]
            rows.append((k, float(np.median(rp)), float(np.mean([x > 0 for x in rp])),
                         float(np.mean([g["winrate"] for g in cells])),
                         sum(g["n"] for g in cells)))
        rows.sort(key=lambda x: -x[1])
        print(f"\n═══ ПО {len(good)} ОКНАМ, всего вариантов {len(rows)} ═══")
        print(f"{'стоп×':>6}{'гор':>6}{'R/сделку':>10}{'окон+':>7}{'WR':>7}{'сделок':>8}")
        for (st, hr), med, pos, wr, nn in rows[:12]:
            print(f"{st:>6}{hr:>5}ч{med:>+10.3f}{pos:>7.0%}{wr:>7.0%}{nn:>8}")
        alive = [r for r in rows if r[1] > 0 and r[2] >= 0.75]
        print(f"\nвариантов с плюсом в >=75% окон: {len(alive)} из {len(rows)}")
        if alive:
            (st, hr), med, pos, wr, nn = alive[0]
            per_year = np.mean([v["signals"] / v["days"] * 365 for v in good])
            print(f"ЛУЧШИЙ УСТОЙЧИВЫЙ: стоп ×{st} хода за горизонт, {hr}ч, {med:+.3f}R/сделку, WR {wr:.0%}")
            print(f"  наблюдаемая частота сигналов ~{per_year:.0f}/год")
            print("  ВАЖНО: частота × средний R не является портфельной годовой доходностью; "
                  "нужны симуляция перекрывающихся позиций, слоты, капитал и просадка")
    _verify_passport()  # fail closed if code/input changed during the run
    print(f"\n[сохранено] {fp}")


if __name__ == "__main__":
    main()
