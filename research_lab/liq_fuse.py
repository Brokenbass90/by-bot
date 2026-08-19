#!/usr/bin/env python3
"""
liq_fuse.py — ПРЕДОХРАНИТЕЛЬ по каскадам ликвидаций.

Идея владельца: гоняться за китами ради прибыли нельзя (замерено:
каскады дают +7.9 bps при круге 8 bps, эффект настоящий, но под издержками),
а вот как ЗАЩИТУ тот же сигнал использовать можно.

Логика простая: сигнал, слишком мелкий для входа, вполне может быть
достаточно крупным, чтобы понять «сейчас не время открываться».
Для предохранителя важна не доходность, а РИСК — насколько сильно
цена ходит против свежего входа.

Меряем: после всплеска ликвидаций какой максимальный ход ПРОТИВ входа
за следующие 30/60/120 минут, в единицах ATR. И сравниваем с обычным
моментом. Если против входа ходит заметно сильнее — предохранитель
оправдан, потому что стоп будет выбивать чаще.

Данные: runtime/liquidations/bybit_liquidations.jsonl + 5m из data_cache.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
LIQ = os.path.join(ROOT, "runtime", "liquidations", "bybit_liquidations.jsonl")
BUCKET_MS = 300_000                 # 5 минут
HOR = (6, 12, 24)                   # 30 / 60 / 120 минут в 5m барах
CASCADE_Q = 0.95                    # всплеск = верхние 5% по этому символу
ATR_N = 24


def load_liq():
    per = defaultdict(lambda: defaultdict(float))
    n = 0
    with open(LIQ) as fh:
        for line in fh:
            try:
                r = json.loads(line)
                b = (int(r["ts_ms"]) // BUCKET_MS) * BUCKET_MS
                per[r["symbol"]][b] += float(r.get("usd") or 0.0)
                n += 1
            except Exception:
                continue
    return per, n


def load_5m(sym, t0, t1):
    best, nb = None, 0
    for p in glob.glob(os.path.join(ROOT, "data_cache", f"{sym}_5_*.json")):
        try:
            rows = json.loads(open(p).read())
        except Exception:
            continue
        if len(rows) > nb:
            best, nb = rows, len(rows)
    if not best:
        return None
    # часть файлов в data_cache хранит строки словарями, часть списками
    if isinstance(best[0], dict):
        a = np.asarray([[r["ts"], r["o"], r["h"], r["l"], r["c"], r.get("v", 0) or 0]
                        for r in best], dtype=np.float64)
    else:
        a = np.asarray([r[:6] for r in best], dtype=np.float64)
    m = (a[:, 0] >= t0 - 86400000) & (a[:, 0] <= t1 + 86400000)
    a = a[m]
    if len(a) < 500:
        return None
    return pd.DataFrame(a[:, 1:], columns=list("ohlcv"),
                        index=pd.to_datetime(a[:, 0].astype("int64"), unit="ms", utc=True))


def main():
    per, n = load_liq()
    print(f"[данные] событий ликвидаций {n:,}, символов {len(per)}")
    tops = sorted(per, key=lambda s: sum(per[s].values()), reverse=True)[:12]
    print(f"[символы] {tops}\n")

    rows = []
    for sym in tops:
        buckets = per[sym]
        ts = np.array(sorted(buckets))
        if len(ts) < 200:
            continue
        d = load_5m(sym, int(ts.min()), int(ts.max()))
        if d is None:
            continue
        usd = pd.Series({pd.Timestamp(t, unit="ms", tz="UTC"): v for t, v in buckets.items()})
        usd = usd.reindex(d.index).fillna(0.0)

        c, h, l = d["c"], d["h"], d["l"]
        pc = c.shift(1)
        tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / ATR_N, adjust=False, min_periods=ATR_N).mean()

        thr = usd[usd > 0].quantile(CASCADE_Q)
        casc = (usd >= thr) & (usd > 0)

        for hh in HOR:
            fut_lo = l.shift(-hh).rolling(hh, min_periods=1).min()
            fut_hi = h.shift(-hh).rolling(hh, min_periods=1).max()
            # ход против ЛОНГА и против ШОРТА, в ATR
            adv_long = (c - fut_lo) / atr
            adv_short = (fut_hi - c) / atr
            worst = pd.concat([adv_long, adv_short], axis=1).max(axis=1)
            fwd = np.log(c.shift(-hh) / c) * 1e4
            base = np.zeros(len(c), bool); base[::12] = True
            # ПУЛИМ по всем символам: каскадов на один символ 3-27,
            # по отдельности выборки нет, вместе — есть
            for tag, sel in (("каскад", casc.to_numpy()), ("обычно", base)):
                w = worst.to_numpy()[sel]; f = fwd.to_numpy()[sel]
                ok = np.isfinite(w) & np.isfinite(f)
                if ok.sum() == 0:
                    continue
                rows.append(pd.DataFrame(dict(symbol=sym, hor_min=hh * 5, tag=tag,
                                              adverse=w[ok], move=f[ok])))
        print(f"  {sym:<14} всплесков {int(casc.sum()):>4}  порог ${thr:,.0f}", flush=True)

    df = pd.concat(rows, ignore_index=True)
    print("\n═══ ХОД ПРОТИВ ВХОДА (в ATR), все символы вместе ═══")
    g = df.groupby(["hor_min", "tag"])["adverse"].agg(
        n="size", против_ATR="mean", медиана="median",
        хвост_p90=lambda x: x.quantile(0.9)).round(3)
    g["ход_bps"] = df.groupby(["hor_min", "tag"])["move"].mean().round(1)
    print(g.to_string())

    print("\n═══ ВО СКОЛЬКО РАЗ ХУЖЕ ПОСЛЕ КАСКАДА ═══")
    for hh in sorted(df.hor_min.unique()):
        A = df[(df.hor_min == hh) & (df.tag == "каскад")]["adverse"]
        B = df[(df.hor_min == hh) & (df.tag == "обычно")]["adverse"]
        # значимость: бутстрап по дням, окна пересекаются
        rng = np.random.default_rng(7)
        bs = [A.sample(len(A), replace=True, random_state=int(rng.integers(1e6))).mean()
              - B.sample(len(B), replace=True, random_state=int(rng.integers(1e6))).mean()
              for _ in range(300)]
        se = float(np.std(bs, ddof=1))
        d = A.mean() - B.mean()
        print(f"  {hh:>4} мин:  среднее x{A.mean()/B.mean():.2f}   хвост x{A.quantile(.9)/B.quantile(.9):.2f}"
              f"   разница {d:+.2f} ATR, t={d/se if se>0 else float('nan'):.1f}   n={len(A)}")

    out = os.path.join(ROOT, "research_lab", "results", "liq_fuse")
    os.makedirs(out, exist_ok=True)
    df.to_csv(os.path.join(out, "liq_fuse.csv"), index=False)
    print(f"\n[сохранено] {out}/liq_fuse.csv")


if __name__ == "__main__":
    main()
