#!/usr/bin/env python3
"""
btc_state_table.py — БИТОК КАК ПОВОДЫРЬ: таблица шансов, а не выключатель.

ЗАЧЕМ ИМЕННО ТАБЛИЦА. Простой переключатель по SMA50 уже пробовали:
книга ушла с +164 на +157, красных месяцев стало больше. Правило
«биток растёт — торгуем» не работает, потому что оно выбрасывает половину
данных ради одного бита информации.

Здесь другое: для КАЖДОГО состояния битка меряется, что реально
происходило с альтами после пробоя уровня и после отскока от поддержки.
На выходе стратегия получает не «можно/нельзя», а свой шанс — и может
требовать больше подтверждений там, где шанс хуже.

Состояние битка складывается из четырёх независимых вещей, все считаются
ТОЛЬКО по прошлым данным:
    ТРЕНД        цена выше/ниже SMA за неделю
    СИЛА         доходность за 30 суток: сильно вниз / вбок / сильно вверх
    ВОЛА         ATR суточный к ATR двухнедельному: сжатие / норма / расширение
    ПОЛОЖЕНИЕ    близко ли к максимуму/минимуму месяца

События на альтах (не на битке):
    ПРОБОЙ ВВЕРХ    закрытие выше максимума прошлой недели
    ОТСКОК ОТ НИЗА  минимум коснулся минимума недели, но закрытие выше

Меряется: доля случаев, когда через 24ч и 72ч цена оказалась выше входа
(для пробоя) и средний ход в bps. Рядом всегда стоит БАЗА — та же доля
без всякого условия, иначе цифра нечитаема.
"""
from __future__ import annotations

import argparse
import glob
import json
import os

import numpy as np
import pandas as pd

WEEK, MONTH, FORT = 168, 720, 336
HOR = (24, 72)
MIN_N = 150
DEFAULT_SEARCH_END = "2025-09-30"


def load(h1dir, search_end):
    ser = {}
    cutoff = pd.Timestamp(search_end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    for fp in sorted(glob.glob(os.path.join(h1dir, "*.npz"))):
        z = np.load(fp)
        idx = pd.to_datetime(z["ts"], unit="ms", utc=True)
        frame = pd.DataFrame(
            z["ohlcv"][:, :4].astype("float64"), index=idx, columns=list("ohlc"))
        frame = frame.loc[:cutoff]
        if len(frame):
            ser[os.path.basename(fp)[:-4]] = frame
    return ser


def btc_state(b):
    """Четыре фактора состояния битка. Только прошлое."""
    c, h, l = b["c"], b["h"], b["l"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr_d = tr.ewm(alpha=1 / 24, adjust=False, min_periods=24).mean()
    atr_f = tr.ewm(alpha=1 / FORT, adjust=False, min_periods=FORT).mean()

    trend = np.where(c > c.rolling(WEEK, min_periods=WEEK).mean(), "выше_недели", "ниже_недели")

    r30 = c / c.shift(MONTH) - 1.0
    power = np.where(r30 > 0.10, "сильно_вверх",
             np.where(r30 < -0.10, "сильно_вниз", "вбок"))

    ratio = atr_d / atr_f
    vola = np.where(ratio < 0.85, "сжатие",
            np.where(ratio > 1.15, "расширение", "норма"))

    hi = h.shift(1).rolling(MONTH, min_periods=MONTH).max()
    lo = l.shift(1).rolling(MONTH, min_periods=MONTH).min()
    pos = (c - lo) / (hi - lo)
    place = np.where(pos > 0.8, "у_вершины_месяца",
             np.where(pos < 0.2, "у_дна_месяца", "в_середине"))

    out = pd.DataFrame(dict(trend=trend, power=power, vola=vola, place=place), index=c.index)
    valid = (
        c.rolling(WEEK, min_periods=WEEK).mean().notna()
        & r30.notna()
        & atr_d.notna()
        & atr_f.notna()
        & hi.notna()
        & lo.notna()
    )
    return out.where(valid, None)


def alt_events(d):
    """Два события на альте. Уровень — экстремум ПРОШЛОЙ недели (shift(1))."""
    c, h, l = d["c"], d["h"], d["l"]
    hi = h.shift(1).rolling(WEEK, min_periods=WEEK).max()
    lo = l.shift(1).rolling(WEEK, min_periods=WEEK).min()
    br = c > hi                                   # пробой вверх
    bo = (l <= lo) & (c > lo)                     # отскок от низа недели
    return br.fillna(False), bo.fillna(False)


def decluster(mask, gap=24):
    idx = np.flatnonzero(mask.to_numpy())
    keep, last = [], -10 ** 9
    for t in idx:
        if t - last >= gap:
            keep.append(t); last = t
    out = np.zeros(len(mask), bool)
    out[keep] = True
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--h1dir", default="research_lab/data/h1")
    parser.add_argument("--out", default="research_lab/results/btc_state_preholdout")
    parser.add_argument("--search-end", default=DEFAULT_SEARCH_END)
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    ser = load(args.h1dir, args.search_end)
    if "BTCUSDT" not in ser:
        raise SystemExit("нет BTCUSDT")
    st = btc_state(ser["BTCUSDT"])
    print(f"[данные] символов {len(ser)}, часов у битка {len(st)}", flush=True)

    rows = []
    for sym, d in ser.items():
        if sym == "BTCUSDT" or len(d) < MONTH + 200:
            continue
        d = d[~d.index.duplicated()]
        s = st.reindex(d.index)
        br, bo = alt_events(d)
        c = d["c"]
        fwd = {hh: (c.shift(-hh) / c - 1.0) for hh in HOR}
        for ev_name, m in (("пробой_вверх", br), ("отскок_от_низа", bo)):
            sel = decluster(m)
            if sel.sum() == 0:
                continue
            for hh in HOR:
                f = fwd[hh].to_numpy()[sel]
                ok = np.isfinite(f)
                if ok.sum() == 0:
                    continue
                sub = s[sel]
                rows.append(pd.DataFrame(dict(
                    event=ev_name, hor=hh, ret=f[ok], symbol=sym,
                    ts=sub.index.to_numpy()[ok],
                    trend=sub["trend"].to_numpy()[ok], power=sub["power"].to_numpy()[ok],
                    vola=sub["vola"].to_numpy()[ok], place=sub["place"].to_numpy()[ok])))
        # база: каждый 24-й час без всякого условия
        base = np.zeros(len(c), bool); base[::24] = True
        for hh in HOR:
            f = fwd[hh].to_numpy()[base]
            ok = np.isfinite(f)
            sub = s[base]
            rows.append(pd.DataFrame(dict(
                event="БАЗА", hor=hh, ret=f[ok], symbol=sym,
                ts=sub.index.to_numpy()[ok],
                trend=sub["trend"].to_numpy()[ok], power=sub["power"].to_numpy()[ok],
                vola=sub["vola"].to_numpy()[ok], place=sub["place"].to_numpy()[ok])))

    df = pd.concat(rows, ignore_index=True)
    df = df[df["trend"].notna()]
    ts_utc = pd.to_datetime(df["ts"], utc=True)
    df["fold"] = np.where(
        ts_utc < pd.Timestamp("2024-01-01", tz="UTC"),
        "2023",
        np.where(ts_utc < pd.Timestamp("2025-01-01", tz="UTC"), "2024", "2025_pre"),
    )
    iso = ts_utc.dt.isocalendar()
    df["week"] = iso.year.astype(int) * 100 + iso.week.astype(int)
    print(f"[событий] всего строк {len(df):,}", flush=True)

    def table(by):
        g = df.groupby(["event", "hor", by])["ret"]
        t = g.agg(n="size", доля_вверх=lambda x: (x > 0).mean(), средний_bps=lambda x: x.mean() * 1e4)
        return t[t["n"] >= MIN_N].round(3)

    res = {
        "_meta": {
            "schema_id": "btc_state_table_descriptive_v2",
            "status": "DESCRIPTIVE_ONLY_NOT_A_TRADING_GATE",
            "search_end_utc": args.search_end,
            "reserved_holdout_used": False,
            "symbol_count": len(ser),
            "pooled_row_count": len(df),
            "limitations": [
                "pooled rows are cross-sectionally dependent",
                "levels are generic weekly extrema, not strategy-native levels",
                "no costed R or prospective shadow evidence",
            ],
        }
    }
    for by in ("trend", "power", "vola", "place"):
        t = table(by)
        res[by] = json.loads(t.reset_index().to_json(orient="records", force_ascii=False))
        print(f"\n═══ БИТОК: {by} ═══")
        for hh in HOR:
            sl = t.xs(hh, level="hor", drop_level=False)
            print(f"  ── через {hh}ч")
            for (ev, _, val), r in sl.iterrows():
                print(f"     {ev:<16} {val:<18} n={int(r['n']):>6}  "
                      f"вверх {r['доля_вверх']:.1%}  {r['средний_bps']:>+8.1f} bps")

    # Chronological stability against the matching unconditional base state.
    # Weekly aggregation prevents thousands of same-hour alt observations from
    # masquerading as thousands of independent market regimes.
    validation = []
    for by in ("trend", "power", "vola", "place"):
        for (event, hor, state_value), event_rows in df[df["event"] != "БАЗА"].groupby(
            ["event", "hor", by]
        ):
            base_rows = df[
                (df["event"] == "БАЗА")
                & (df["hor"] == hor)
                & (df[by] == state_value)
            ]
            fold_rows = []
            for fold in ("2023", "2024", "2025_pre"):
                ev = event_rows[event_rows["fold"] == fold]
                ba = base_rows[base_rows["fold"] == fold]
                if len(ev) < 50 or len(ba) < 150:
                    continue
                fold_rows.append(
                    {
                        "fold": fold,
                        "event_n": len(ev),
                        "base_n": len(ba),
                        "delta_up_pp": round(float(((ev["ret"] > 0).mean() - (ba["ret"] > 0).mean()) * 100), 3),
                        "delta_mean_bps": round(float((ev["ret"].mean() - ba["ret"].mean()) * 10_000), 3),
                    }
                )
            ev_week = event_rows.groupby("week")["ret"].mean()
            ba_week = base_rows.groupby("week")["ret"].mean()
            common = ev_week.index.intersection(ba_week.index)
            weekly_diff = (ev_week.reindex(common) - ba_week.reindex(common)).dropna()
            weekly_t = None
            if len(weekly_diff) >= 12 and weekly_diff.std(ddof=1) > 0:
                weekly_t = float(weekly_diff.mean() / (weekly_diff.std(ddof=1) / np.sqrt(len(weekly_diff))))
            validation.append(
                {
                    "dimension": by,
                    "event": event,
                    "hor": int(hor),
                    "state": state_value,
                    "folds": fold_rows,
                    "fold_delta_up_signs": [int(np.sign(row["delta_up_pp"])) for row in fold_rows],
                    "fold_delta_bps_signs": [int(np.sign(row["delta_mean_bps"])) for row in fold_rows],
                    "weekly_cluster_count": len(weekly_diff),
                    "weekly_mean_delta_bps": round(float(weekly_diff.mean() * 10_000), 3) if len(weekly_diff) else None,
                    "weekly_t_return": round(weekly_t, 3) if weekly_t is not None else None,
                }
            )
    res["_validation"] = validation

    with open(os.path.join(args.out, "btc_state_table.json"), "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2)
    print(f"\n[сохранено] {args.out}/btc_state_table.json")


if __name__ == "__main__":
    main()
