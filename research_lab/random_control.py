#!/usr/bin/env python3
"""random_control.py — сколько дал бы СЛУЧАЙНЫЙ вход с той же геометрией.

ЭТОГО КОНТРОЛЯ У НАС НЕ БЫЛО НИКОГДА, И ЭТО ГЛАВНЫЙ ПРОБЕЛ.

Окно 2024-03…2025-09 — это падение альтов. Шорт чего угодно в нём
зарабатывал сам по себе. Значит вопрос не «сколько даёт стратегия»,
а «сколько она даёт СВЕРХ случайного входа в те же часы, по тем же
монетам, с той же геометрией стопа и целей».

Как устроен контроль. Для каждой реальной сделки берём:
    ту же монету,
    случайный час внутри того же календарного месяца,
    ту же сторону,
    то же расстояние до стопа в процентах цены,
    те же цели в единицах риска,
    то же удержание.
Всё, кроме момента входа, совпадает. Разница — и есть эдж стратегии.

Повторяем 20 раз, чтобы у контроля был свой доверительный интервал.
"""
from __future__ import annotations
import glob, importlib, math, os, sys
from pathlib import Path
import numpy as np
from research_machine import Store, pervyy_dlya, zapisat_sboy  # единый склад и контракт

ROOT = str(Path(__file__).resolve().parents[1])
DATA = f"{ROOT}/research_lab/data/h1"
WINDOWS = {"2024-03..2025-09": (1709251200000, 1759276800000),
           "2023-01..2024-02": (1672531200000, 1709251200000)}
FEE_BPS_SIDE, LOOKBACK, FLAT = 6.0, 120, 0.02
DRAWS = 20


def ema(x, n):
    k = 2 / (n + 1); e = x[0]; out = np.empty(len(x))
    for i, v in enumerate(x):
        e = v * k + e * (1 - k); out[i] = e
    return out


def sim_geo(bars, i, short, stop_pct, rr1, rr2, f1, hold):
    """вход по открытию следующего бара, геометрия задана в долях цены и R"""
    e = i + 1
    if e >= len(bars):
        return None
    entry = float(bars[e][1])
    risk = entry * stop_pct
    if risk <= 0:
        return None
    sl = entry + risk if short else entry - risk
    tp1 = entry - rr1 * risk if short else entry + rr1 * risk
    tp2 = entry - rr2 * risk if short else entry + rr2 * risk
    lev = entry / risk
    cost = lev * 2 * FEE_BPS_SIDE / 1e4
    stop, rem, gross, done = sl, 1.0, 0.0, False
    for j in range(e, min(e + hold, len(bars))):
        h, l = float(bars[j][2]), float(bars[j][3])
        if (h >= stop) if short else (l <= stop):
            gross += rem * ((entry - stop) if short else (stop - entry)) / risk
            return gross - cost
        if not done and ((l <= tp1) if short else (h >= tp1)):
            gross += f1 * rr1; rem -= f1; done = True
        if rem > 1e-9 and ((l <= tp2) if short else (h >= tp2)):
            gross += rem * rr2
            return gross - cost
    j = min(e + hold, len(bars)) - 1
    px = float(bars[j][4])
    gross += rem * ((entry - px) if short else (px - entry)) / risk
    return gross - cost


def sim_zatuh(bars, i, short, stop_pct, rr1, rr2, f1, hold, zatuh=0, fiks=0):
    """То же, что sim_geo, плюс ДВА способа выйти раньше срока.

    zatuh = K: выходим, если за последние K баров цена НЕ обновила
              максимум в нашу сторону. Это и есть «движение затухает».
    fiks  = N: выходим ровно через N баров, что бы ни происходило.

    Зачем fiks. Если ранний выход улучшает результат при ЛЮБОМ правиле,
    значит помогает не распознавание затухания, а просто «меньше времени
    в рынке». fiks — контроль именно на это: он выходит так же рано, но
    ничего не распознаёт. Затухание обязано бить его, а не только базу.

    Порядок в баре, объявлен заранее: сначала стоп, потом цели, и только
    потом ранние выходы. Стоп имеет приоритет всегда.

    Одна и та же функция считает и реальную сделку, и контроль случайным
    входом — тогда между ними физически не может разъехаться геометрия.
    """
    e = i + 1
    if e >= len(bars):
        return None
    entry = float(bars[e][1])
    risk = entry * stop_pct
    if risk <= 0:
        return None
    sl = entry + risk if short else entry - risk
    tp1 = entry - rr1 * risk if short else entry + rr1 * risk
    tp2 = entry - rr2 * risk if short else entry + rr2 * risk
    lev = entry / risk
    cost = lev * 2 * FEE_BPS_SIDE / 1e4
    stop, rem, gross, done = sl, 1.0, 0.0, False
    ekstremum = entry
    bez_novogo = 0

    for j in range(e, min(e + hold, len(bars))):
        h, l = float(bars[j][2]), float(bars[j][3])
        if (h >= stop) if short else (l <= stop):
            gross += rem * ((entry - stop) if short else (stop - entry)) / risk
            return gross - cost, j - e
        if not done and ((l <= tp1) if short else (h >= tp1)):
            gross += f1 * rr1; rem -= f1; done = True
        if rem > 1e-9 and ((l <= tp2) if short else (h >= tp2)):
            gross += rem * rr2
            return gross - cost, j - e

        novyy = l if short else h
        luchshe = (novyy < ekstremum) if short else (novyy > ekstremum)
        if luchshe:
            ekstremum = novyy
            bez_novogo = 0
        else:
            bez_novogo += 1

        rano = (zatuh and bez_novogo >= zatuh) or (fiks and (j - e + 1) >= fiks)
        if rano:
            px = float(bars[j][4])
            gross += rem * ((entry - px) if short else (px - entry)) / risk
            return gross - cost, j - e

    j = min(e + hold, len(bars)) - 1
    px = float(bars[j][4])
    gross += rem * ((entry - px) if short else (px - entry)) / risk
    return gross - cost, j - e


def sim_limit(bars, i, short, stop_pct, rr1, rr2, f1, hold,
              otstup, zhdat, fee_vhod=1.5, fee_vyhod=5.5):
    """ЧЕСТНЫЙ ЛИМИТНЫЙ ВХОД. Возвращает (R, баров, исполнился) или None.

    Прогон при комиссии 1.5 bps 2 сентября считал, что КАЖДЫЙ лимит
    исполнился. Это верхняя граница, а не оценка: лимит на откате
    исполняется только если цена вернулась. Здесь это моделируется.

    Правило, объявленное до прогонов:
      * ордер ставится на `otstup` (доля цены) ПРОТИВ движения от
        закрытия сигнального бара: лонг ниже, шорт выше;
      * ордер живёт `zhdat` баров;
      * коснулись — вход ПО ЦЕНЕ ЛИМИТА (не хуже, это и есть смысл лимита);
      * не коснулись — СДЕЛКИ НЕТ, возвращаем None. Не «вошли по рынку»,
        а именно нет сделки. Так же обязан считаться и контроль.

    Комиссия РАЗНАЯ на вход и выход, и это принципиально:
      вход  лимитом  -> мейкер (дёшево)
      выход по стопу -> тейкер (дорого)
    Считать обе стороны мейкерскими — то же самое вранье, что считать
    витрину прибылью.
    """
    ref = float(bars[i][4])
    if ref <= 0 or otstup < 0:
        return None
    limit = ref * (1.0 + otstup) if short else ref * (1.0 - otstup)

    e = None
    for j in range(i + 1, min(i + 1 + max(1, zhdat), len(bars))):
        h, l = float(bars[j][2]), float(bars[j][3])
        if (h >= limit) if short else (l <= limit):
            e = j
            break
    if e is None:
        return None                      # цена не вернулась — сделки нет

    entry = limit
    risk = entry * stop_pct
    if risk <= 0:
        return None
    sl = entry + risk if short else entry - risk
    tp1 = entry - rr1 * risk if short else entry + rr1 * risk
    tp2 = entry - rr2 * risk if short else entry + rr2 * risk
    lev = entry / risk
    cost = lev * (fee_vhod + fee_vyhod) / 1e4
    stop, rem, gross, done = sl, 1.0, 0.0, False

    for j in range(e, min(e + hold, len(bars))):
        h, l = float(bars[j][2]), float(bars[j][3])
        if (h >= stop) if short else (l <= stop):
            gross += rem * ((entry - stop) if short else (stop - entry)) / risk
            return gross - cost, j - e, True
        if not done and ((l <= tp1) if short else (h >= tp1)):
            gross += f1 * rr1; rem -= f1; done = True
        if rem > 1e-9 and ((l <= tp2) if short else (h >= tp2)):
            gross += rem * rr2
            return gross - cost, j - e, True
    j = min(e + hold, len(bars)) - 1
    px = float(bars[j][4])
    gross += rem * ((entry - px) if short else (px - entry)) / risk
    return gross - cost, j - e, True


def main():
    mod, cls, pfx = sys.argv[1], sys.argv[2], sys.argv[3]
    side_want = sys.argv[4] if len(sys.argv) > 4 else "short"
    mult = float(sys.argv[5]) if len(sys.argv) > 5 else 1.0
    hold = int(sys.argv[6]) if len(sys.argv) > 6 else 336
    regime = sys.argv[7] if len(sys.argv) > 7 else "флет-"
    cooldown = sys.argv[8] if len(sys.argv) > 8 else "0"
    data_dir = sys.argv[9] if len(sys.argv) > 9 else DATA
    globals()["DATA"] = data_dir
    reg_src = sys.argv[10] if len(sys.argv) > 10 else f"{data_dir}/BTCUSDT.npz"

    sys.path.insert(0, ROOT)
    files = sorted(glob.glob(f"{data_dir}/*.npz"))
    syms = ",".join(Path(f).stem for f in files)
    os.environ.update({f"{pfx}_SYMBOL_ALLOWLIST": syms, f"{pfx}_ALLOW_LONGS": "1",
                       f"{pfx}_ALLOW_SHORTS": "1"})
    if cooldown != "0":
        os.environ[f"{pfx}_COOLDOWN_BARS_5M"] = cooldown
    S = getattr(importlib.import_module(f"strategies.{mod}"), cls)

    d = np.load(reg_src)
    c = d["ohlcv"][:, 3].astype(float); em = ema(c, 200)
    bts, bdist = d["ts"], (c - em) / em

    def reg_ok(t):
        if regime == "любой":
            return True
        j = max(0, int(np.searchsorted(bts, t, side="right")) - 1)
        v = float(bdist[j]) if j < len(bdist) else 0.0
        return {"флет-": -FLAT <= v < 0, "флет+": 0 <= v < FLAT,
                "тренд-": v < -FLAT, "тренд+": v >= FLAT,
                "падает": v < 0, "растёт": v >= 0}[regime]

    real = {w: [] for w in WINDOWS}
    ctrl = {w: [[] for _ in range(DRAWS)] for w in WINDOWS}
    rng = np.random.default_rng(7)
    short = side_want == "short"

    for k, fp in enumerate(files):
        dd = np.load(fp); ts, o = dd["ts"], dd["ohlcv"].astype(float)
        m = ts < 1759276800000
        ts, o = ts[m], o[m]
        if len(ts) < LOOKBACK + 300:
            continue
        bars = [[int(ts[x]), o[x, 0], o[x, 1], o[x, 2], o[x, 3], o[x, 4]]
                for x in range(len(ts))]
        month = (ts // (30 * 86400000)).astype(np.int64)
        st = Store(Path(fp).stem)
        strat = S()
        pervyy = pervyy_dlya(S, st, Path(fp).stem)
        block = -1
        for i in range(LOOKBACK, len(bars) - 1):
            st.rows = bars[: i + 1]; b = bars[i]
            try:
                s = strat.maybe_signal(pervyy, b[0], b[1], b[2], b[3], b[4], b[5])
            except Exception as _e:
                zapisat_sboy('random_control', _e)
                continue
            if s is None or s.side != side_want or i <= block or not reg_ok(b[0]):
                continue
            entry0 = float(bars[i + 1][1])
            sl = entry0 + (float(s.sl) - entry0) * mult
            risk = abs(sl - entry0)
            if risk <= 0:
                continue
            stop_pct = risk / entry0
            tps = [float(x) for x in (s.tps or [])]
            if len(tps) < 2:
                continue
            rr1 = abs(tps[0] - entry0) / risk
            rr2 = abs(tps[1] - entry0) / risk
            f1 = float((s.tp_fracs or [0.55])[0])
            r = sim_geo(bars, i, short, stop_pct, rr1, rr2, f1, hold)
            if r is None:
                continue
            block = i + hold // 4
            t = b[0]
            for w, (a, b2) in WINDOWS.items():
                if a <= t < b2:
                    real[w].append(r)
                    pool = np.flatnonzero((month == month[i]) &
                                          (np.arange(len(ts)) >= LOOKBACK) &
                                          (np.arange(len(ts)) < len(ts) - 1))
                    if len(pool) < 5:
                        continue
                    for dr in range(DRAWS):
                        j = int(rng.choice(pool))
                        rc = sim_geo(bars, j, short, stop_pct, rr1, rr2, f1, hold)
                        if rc is not None:
                            ctrl[w][dr].append(rc)
        if (k + 1) % 40 == 0:
            print(f"... {k+1}/{len(files)}", flush=True)

    print(f"\n{pfx}: {side_want}, стоп ×{mult}, держ {hold} ч, режим «{regime}»")
    print(f"{'окно':<20}{'n':>6}{'стратегия':>12}{'случайно':>12}"
          f"{'разброс сл.':>13}{'ЭДЖ':>12}{'σ эджа':>9}")
    for w in WINDOWS:
        R = np.array(real[w])
        if len(R) < 50:
            print(f"{w:<20} сделок мало"); continue
        cm = np.array([np.mean(x) for x in ctrl[w] if len(x) > 20])
        if len(cm) < 5:
            print(f"{w:<20} контроль не собрался"); continue
        edge = R.mean() - cm.mean()
        se = math.sqrt(R.std(ddof=1) ** 2 / len(R) + cm.var(ddof=1))
        print(f"{w:<20}{len(R):>6}{R.mean():>+11.4f}R{cm.mean():>+11.4f}R"
              f"{cm.std(ddof=1):>12.4f}R{edge:>+11.4f}R{edge/se:>+9.2f}")


if __name__ == "__main__":
    main()
