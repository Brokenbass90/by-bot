#!/usr/bin/env python3
"""orchestrator.py — собрать ноги в один портфель и проверить, помогает ли
переключение по режиму.

ЗАЧЕМ. У нас есть ноги, каждая из которых что-то даёт в своей ячейке.
Вопрос не в том, хороша ли нога. Вопрос: если поставить над ними
диспетчера, который смотрит на состояние BTC и решает, кому сейчас
можно торговать, — станет лучше, чем без него?

Проверяем ровно одно сравнение, объявленное заранее:

    БЕЗ ДИСПЕТЧЕРА   все ноги торгуют всегда
    С ДИСПЕТЧЕРОМ    нога торгует только в своём режиме

Всё остальное — слоты, риск, запрет двух позиций по одному символу —
одинаково у обоих. Никакой подгонки: слотов 3, как в живом боте.

Режимы BTC по отклонению от EMA200 на часах:
    флет-   от -2% до 0      флет+   от 0 до +2%
    тренд-  ниже -2%         тренд+  выше +2%

Ноги и их режимы взяты из прогонов 18 августа и здесь НЕ подбираются.

Запуск:
    python3 research_lab/orchestrator.py              # полный
    python3 research_lab/orchestrator.py --cache-only # только собрать сигналы
"""
from __future__ import annotations
import argparse, glob, importlib, json, math, os, sys
from pathlib import Path
import numpy as np

ROOT = str(Path(__file__).resolve().parents[1])
DATA = f"{ROOT}/research_lab/data/h1"
CACHE = f"{ROOT}/research_lab/orch_signals.json"
WINDOWS = {
    "2024-03..2025-09": (1709251200000, 1759276800000),
    "2023-01..2024-02": (1672531200000, 1709251200000),
}
SEALED_FROM = 1759276800000
FEE_BPS_SIDE = 6.0
LOOKBACK = 120
FLAT = 0.02
SLOTS = 12                     # измерено: 12 против 2 даёт 4.5x при той же просадке

# ПРИОРИТЕТ НОГ. Слот уходит не первому пришедшему, а сильнейшей ноге
# внутри часового окна. Порядок задан ОДИН раз по измеренному эджу
# над случайным входом и дальше не подбирается:
#   SBR1 +0.0826R / +0.0820R  — знак держится на обоих окнах
#   ATT1 +0.0628R / +0.0128R  — второе окно слабее
PRIORITY = {"SBR1": 0, "ATT1": 1}
PRIORITY_WINDOW_H = 6          # в пределах скольких часов сравниваем ноги

# нога: модуль, класс, префикс, сторона, множитель стопа, удержание, режимы, пауза
#
# Пауза — в барах вызова. Штатное значение стратегии задано в
# пятиминутках, а счётчик тикает раз в вызов. На часовых данных
# его надо делить на 12, иначе пауза длиннее живой в двенадцать раз.
LEGS = [
    # Две ноги, каждая прошла контроль случайным входом НА ОБОИХ окнах.
    # Больше в портфеле никого: остальные либо только на одном окне,
    # либо значимо хуже случайного входа.
    ("alt_trendline_touch_v1", "AltTrendlineTouchV1Strategy", "ATT1",
     "short", 6.0, 336, ("флет-",), 8),
    ("sloped_break_retest_v1", "SlopedBreakRetestV1Strategy", "SBR1",
     "long", 4.0, 168, ("флет+",), 0),
]


class Store:
    def __init__(self, sym):
        self.symbol = sym
        self.rows = []

    def fetch_klines(self, sym, tf, n):
        return self.rows[-n:]


def ema(x, n):
    k = 2 / (n + 1); e = x[0]; out = np.empty(len(x))
    for i, v in enumerate(x):
        e = v * k + e * (1 - k); out[i] = e
    return out


def regime_name(d):
    if d is None:
        return "нет"
    if d < -FLAT:
        return "тренд-"
    if d < 0:
        return "флет-"
    if d < FLAT:
        return "флет+"
    return "тренд+"


def simulate(bars, i, side, sl0, tps, f1, mult, hold):
    """вход по открытию следующего бара; стоп проверяется раньше целей"""
    e = i + 1
    if e >= len(bars):
        return None
    entry = float(bars[e][1])
    short = side == "short"
    sl = entry + (sl0 - entry) * mult
    risk = (sl - entry) if short else (entry - sl)
    if risk <= 0:
        return None
    lev = entry / risk
    cost = lev * 2 * FEE_BPS_SIDE / 1e4
    tp1, tp2 = (list(tps) + [None, None])[:2]
    stop, rem, gross, tp1_done = sl, 1.0, 0.0, False
    for j in range(e, min(e + hold, len(bars))):
        h, l = float(bars[j][2]), float(bars[j][3])
        if (h >= stop) if short else (l <= stop):
            gross += rem * ((entry - stop) if short else (stop - entry)) / risk
            return dict(R=gross - cost, bars=j - e, lev=lev)
        if tp1 and not tp1_done and ((l <= tp1) if short else (h >= tp1)):
            # БЫЛО: условие rem > f1 - 1e-9. При доле ровно 0.5 после
            # первого срабатывания rem становится равным f1, условие
            # остаётся истинным, и первая цель исполнялась ВТОРОЙ раз.
            # Позиция целиком закрывалась по tp1 вместо того, чтобы
            # оставить половину под вторую цель или под стоп.
            gross += f1 * ((entry - tp1) if short else (tp1 - entry)) / risk
            rem -= f1
            tp1_done = True
        if tp2 and rem > 1e-9 and ((l <= tp2) if short else (h >= tp2)):
            gross += rem * ((entry - tp2) if short else (tp2 - entry)) / risk
            return dict(R=gross - cost, bars=j - e, lev=lev)
    j = min(e + hold, len(bars)) - 1
    px = float(bars[j][4])
    gross += rem * ((entry - px) if short else (px - entry)) / risk
    return dict(R=gross - cost, bars=j - e, lev=lev)


def build_trades(files, btc_ts, btc_dist):
    """один раз генерируем сигналы каждой ноги и сразу считаем их исход"""
    def reg_at(t):
        j = max(0, int(np.searchsorted(btc_ts, t, side="right")) - 1)
        return float(btc_dist[j]) if j < len(btc_dist) else None

    trades = []
    for mod, cls, pfx, side_want, mult, hold, _regs, cd in LEGS:
        syms = ",".join(sorted(Path(f).stem for f in files))
        os.environ[f"{pfx}_SYMBOL_ALLOWLIST"] = syms
        os.environ.setdefault(f"{pfx}_ALLOW_LONGS", "1")
        os.environ.setdefault(f"{pfx}_ALLOW_SHORTS", "1")
        if cd > 0:
            os.environ[f"{pfx}_COOLDOWN_BARS_5M"] = str(cd)
        Strategy = getattr(importlib.import_module(f"strategies.{mod}"), cls)
        cnt = 0
        for k, fp in enumerate(files):
            d = np.load(fp); ts, o = d["ts"], d["ohlcv"].astype(float)
            m = ts < SEALED_FROM
            ts, o = ts[m], o[m]
            if len(ts) < LOOKBACK + 300:
                continue
            sym = Path(fp).stem
            bars = [[int(ts[x]), o[x, 0], o[x, 1], o[x, 2], o[x, 3], o[x, 4]]
                    for x in range(len(ts))]
            st = Store(sym); strat = Strategy()
            for i in range(LOOKBACK, len(bars)):
                st.rows = bars[: i + 1]
                b = bars[i]
                try:
                    s = strat.maybe_signal(st, b[0], b[1], b[2], b[3], b[4], b[5])
                except Exception:
                    continue
                if s is None or s.side != side_want:
                    continue
                r = simulate(bars, i, s.side, s.sl, list(s.tps or []),
                             (s.tp_fracs or [0.55])[0], mult, hold)
                if r is None:
                    continue
                trades.append(dict(leg=pfx, sym=sym, side=s.side,
                                   ts=int(b[0]), R=round(r["R"], 6),
                                   hours=int(r["bars"]) + 1,
                                   lev=round(r["lev"], 2),
                                   reg=regime_name(reg_at(b[0]))))
                cnt += 1
            if (k + 1) % 40 == 0:
                print(f"  {pfx}: {k+1}/{len(files)}, сделок {cnt}", flush=True)
        print(f"{pfx}: всего {cnt} сигналов", flush=True)
    trades.sort(key=lambda x: x["ts"])
    return trades


def portfolio(trades, use_orchestrator, wstart, wend):
    """хронологический проход со слотами; вход отклоняется, если мест нет"""
    legreg = {p: set(r) for _, _, p, _, _, _, r, _ in LEGS}
    open_until = []        # (ts_exit, symbol)
    taken, skipped_full, skipped_reg, skipped_sym = [], 0, 0, 0
    # ПРИОРИТЕТ: внутри окна в PRIORITY_WINDOW_H часов слот уходит
    # сильнейшей ноге, а не первой по времени. Раньше слоты забирала
    # самая частая нога, а не самая полезная.
    _buck = {}
    for _t in trades:
        _buck.setdefault(_t["ts"] // (PRIORITY_WINDOW_H * 3600000), []).append(_t)
    trades = []
    for _k in sorted(_buck):
        trades.extend(sorted(_buck[_k],
                             key=lambda x: (PRIORITY.get(x["leg"], 9), x["ts"])))
    for t in trades:
        if not (wstart <= t["ts"] < wend):
            continue
        if use_orchestrator and t["reg"] not in legreg[t["leg"]]:
            skipped_reg += 1
            continue
        open_until = [x for x in open_until if x[0] > t["ts"]]
        if any(x[1] == t["sym"] for x in open_until):
            skipped_sym += 1
            continue
        if len(open_until) >= SLOTS:
            skipped_full += 1
            continue
        open_until.append((t["ts"] + t["hours"] * 3600000, t["sym"]))
        taken.append(t)
    if not taken:
        return None
    R = np.array([x["R"] for x in taken])
    eq = np.cumsum(R)
    dd = float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else 0.0
    months = max(1.0, (wend - wstart) / (30.44 * 86400000))
    se = R.std(ddof=1) / math.sqrt(len(R)) if len(R) > 1 else 1e9
    return dict(n=len(R), total=float(eq[-1]), mean=float(R.mean()),
                sigma=float(R.mean() / se) if se else 0.0, dd=dd,
                per_month=float(eq[-1] / months), trades_month=len(R) / months,
                winrate=float((R > 0).mean()), taken=taken,
                skip_reg=skipped_reg, skip_full=skipped_full, skip_sym=skipped_sym)


def show(title, a):
    if a is None:
        print(f"{title:<22} сделок нет")
        return
    print(f"{title:<22}{a['n']:>7}{a['total']:>+11.1f}R{a['mean']:>+10.4f}R"
          f"{a['sigma']:>+8.2f}{a['dd']:>9.1f}R{a['per_month']:>+10.2f}R"
          f"{a['trades_month']:>9.1f}{a['winrate']:>9.0%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-only", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, ROOT)
    files = sorted(glob.glob(f"{DATA}/*.npz"))
    if not files:
        print("нет данных"); return 1

    d = np.load(f"{DATA}/BTCUSDT.npz")
    c = d["ohlcv"][:, 3].astype(float); e = ema(c, 200)
    btc_ts, btc_dist = d["ts"], (c - e) / e

    if a.rebuild or not Path(CACHE).exists():
        print("генерирую сигналы всех ног (это долго, один раз)...", flush=True)
        trades = build_trades(files, btc_ts, btc_dist)
        Path(CACHE).write_text(json.dumps(trades), encoding="utf-8")
        print(f"кэш: {CACHE}, сделок {len(trades)}")
    else:
        trades = json.loads(Path(CACHE).read_text(encoding="utf-8"))
        print(f"кэш прочитан: {len(trades)} сделок")
    if a.cache_only:
        return 0

    hdr = (f"{'':<22}{'сделок':>7}{'ИТОГО':>11}{'на сделку':>11}"
           f"{'σ':>8}{'просадка':>10}{'в месяц':>10}{'сделок/мес':>10}{'винрейт':>9}")
    for wname, (sta, cut) in WINDOWS.items():
        print(f"\n╔══ окно {wname}")
        print(hdr)
        off = portfolio(trades, False, sta, cut)
        on = portfolio(trades, True, sta, cut)
        show("БЕЗ диспетчера", off)
        show("С диспетчером", on)
        if off and on:
            print(f"\n  разница на сделку: {on['mean'] - off['mean']:+.4f}R")
            print(f"  диспетчер отклонил по режиму: {on['skip_reg']}, "
                  f"нет слота: {on['skip_full']}, символ занят: {on['skip_sym']}")
        if on:
            print("\n  вклад ног (с диспетчером):")
            for _, _, pfx, _, _, _, _, _ in LEGS:
                g = [x for x in on["taken"] if x["leg"] == pfx]
                if not g:
                    print(f"    {pfx:<6} сделок нет"); continue
                R = np.array([x["R"] for x in g])
                print(f"    {pfx:<6}{len(R):>6} сделок{R.sum():>+9.1f}R"
                      f"{R.mean():>+10.4f}R  винрейт {(R > 0).mean():.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
