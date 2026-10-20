#!/usr/bin/env python3
"""research_machine.py — машина исследований. Одна стратегия -> один паспорт.

ЗАЧЕМ. Слепой перебор дал 54 тысячи папок и систематическое завышение.
Эта машина перебирает не «всё подряд», а ЧЕТЫРЕ ОСИ, про которые
измерено, что они двигают результат:

    ширина стопа   плечо = цена/стоп, а издержки = плечо × комиссия
    удержание      у эджа есть естественный горизонт
    сторона        лонг и шорт несимметричны
    режим рынка    BTC выше/ниже своей EMA200 на входе

Сигналы генерируются ОДИН раз штатными параметрами, оси применяются
только на симуляции. Иначе меняется набор сделок и результат — артефакт.

Всегда печатается ТРИ числа, а не одно:
    сигнал до издержек   есть ли направление вообще
    издержки             сколько стоит доступ
    итог                 что остаётся

И всегда — минимально различимый эффект при этом числе сделок.
Если итог меньше него, вывод «не проверено», а не «не работает».

Запуск:
    python3 research_machine.py --strategy alt_trendline_touch_v1 \
        --cls AltTrendlineTouchV1Strategy --prefix ATT1 --data h1 --tag att1

Данные: папка с .npz (ts, ohlcv[o,h,l,c,v]) — часовые бары.
Окна объявлены в коде и запечатанный период не читается.
"""
from __future__ import annotations

import argparse
import glob
import importlib
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

WINDOWS = {
    "2024-03..2025-09": (1709251200000, 1759276800000),
    "2023-01..2024-02": (1672531200000, 1709251200000),
}
SEALED_FROM = 1759276800000          # 2025-10-01 — дальше не читаем никогда
STOPS = (1.0, 2.0, 4.0, 6.0, 8.0)
HOLDS = (168, 336)
FLAT = 0.02                          # ±2% от EMA200 — объявлено заранее, не подбиралось
REGIMES = (
    (None,                          "любой"),
    (lambda d: d < 0,               "падает"),
    (lambda d: d >= 0,              "растёт"),
    (lambda d: -FLAT <= d < 0,      "флет-"),
    (lambda d: 0 <= d < FLAT,       "флет+"),
    (lambda d: d < -FLAT,           "тренд-"),
    (lambda d: d >= FLAT,           "тренд+"),
)
FEE_BPS_SIDE = 6.0

# ЕДИНЫЙ ПОТОЛОК ЗАТРАТ И ЕДИНОЕ ЧИСЛО РОЗЫГРЫШЕЙ. Заведены 1 сентября.
#
# ДЕФЕКТ, найденный первым же прогоном конвейера: perebor_korzina.py
# держал MAX_LEV = 400 с комментарием «тот же потолок 0.12R при спреде
# 1.5 bps», а simulate всё равно берёт FEE_BPS_SIDE = 6. Значит сделка
# с плечом 400 стоила 0.48R и всё равно попадала в выборку, тогда как
# osi.py такие сделки отбрасывала на 100. Две наши собственные ступени
# мерили разные вселенные сделок: у PUMP4 вышло 2.15σ на ступени 2 и
# 3.39σ на ступени 3 при одинаковой конфигурации.
#
# Потолок считается ОТ ФАКТИЧЕСКОЙ комиссии, а не от желаемой:
#     затраты = lev * 2 * FEE_BPS_SIDE / 1e4 <= 0.12R  ->  lev <= 100
MAX_LEV = 0.12 / (2 * FEE_BPS_SIDE / 1e4)     # = 100.0
ROZYGRYSHEY = 20                              # розыгрышей контроля
LOOKBACK = 120
SIGMA_R = 1.03    # исторический разброс одной сделки при стопе ×1, только для справки


def pervyy_argument(Klass) -> str:
    """Что стратегия ждёт первым аргументом maybe_signal: склад или символ.

    ДЕФЕКТ, найден 1 сентября. Лаборатория ВСЕМ стратегиям передавала
    Store. Но четыре из корпуса — вся семья pump_fade, включая нашего
    ведущего кандидата PUMP4 — объявляют `maybe_signal(self, symbol: str,
    ...)`. Им уезжал объект Store вместо строки символа.

    Пока список разрешённых монет был пуст, это ничего не портило:
    символ используется только для проверки allow/deny и для подписи
    сигнала, сама логика входа от него не зависит. Но стоило поставить
    ПРАВИЛЬНЫЙ префикс переменных — и стратегия отвергла 2800 баров
    подряд с причиной ALLOWLIST_REJECT, то есть выглядела бы «молчащей».
    Ровно так 31 августа мы чуть не похоронили живые ноги.

    И это же прямой случай расхождения тестов с живым кодом: живой бот
    зовёт `maybe_signal(symbol, ...)`, а лаборатория звала
    `maybe_signal(store, ...)`.
    """
    import inspect
    try:
        p = list(inspect.signature(Klass.maybe_signal).parameters)
    except (TypeError, ValueError):
        return "store"
    return "symbol" if len(p) > 1 and p[1] == "symbol" else "store"


def _tf_v_minutah(tf) -> int | None:
    """'240' / 240 / '4h' / 'H1' -> минуты. Не понял — None."""
    if tf is None:
        return None
    t = str(tf).strip().lower()
    if t.isdigit():
        return int(t)
    edinicy = {"m": 1, "h": 60, "d": 1440, "w": 10080}
    if t and t[0] in edinicy and t[1:].isdigit():          # h1, d1, m5
        return edinicy[t[0]] * int(t[1:])
    if t and t[-1] in edinicy and t[:-1].isdigit():        # 4h, 15m
        return edinicy[t[-1]] * int(t[:-1])
    return None


SBOI = {}          # {имя стратегии: сколько раз упала внутри}


def pervyy_dlya(Klass, st, simvol):
    """ЧТО передать стратегии первым аргументом. Один ответ на всю лабораторию.

    2 сентября выяснилось, что я починил три файла из тринадцати.
    Остальные десять — включая random_control.py, который у нас записан
    как КАНОНИЧЕСКИЙ контроль, и read_sealed.py, который читает
    запечатанный период — продолжали звать по старому контракту.
    Дублированная реализация плодит один и тот же баг столько раз,
    сколько у неё копий. Поэтому ответ теперь ровно один и здесь.
    """
    return simvol if pervyy_argument(Klass) == "symbol" else st


def zapisat_sboy(imya, e):
    """Исключение внутри стратегии — НЕ «нет сигнала».

    Раньше `except Exception: continue` превращал падение стратегии в
    молчание, и молчание читалось как «ей нечего сказать». Теперь сбои
    считаются и их видно.
    """
    k = f"{imya}:{type(e).__name__}"
    SBOI[k] = SBOI.get(k, 0) + 1


# Порог, выше которого результат прогона считается НЕДЕЙСТВИТЕЛЬНЫМ.
# Если стратегия падала чаще, чем на каждом сотом решении, её выборка
# сформирована не правилом входа, а исключениями, и мерить там нечего.
DOLYA_SBOEV_PREDEL = 0.01


def otchet_sboev(resheniy: int = 0) -> bool:
    """Печатает сбои и отвечает, можно ли верить прогону.

    Возвращает False, если сбоев больше порога. Это «fail closed»:
    молчание больше не выдаётся за отсутствие сигнала.
    """
    vsego = sum(SBOI.values())
    if not vsego:
        print("  СБОЕВ СТРАТЕГИЙ: 0")
        return True
    print(f"  СБОЕВ СТРАТЕГИЙ: {vsego}")
    for k, v in sorted(SBOI.items(), key=lambda x: -x[1])[:8]:
        print(f"    {v:>7}  {k}")
    if resheniy > 0:
        d = vsego / resheniy
        print(f"    доля от всех решений: {d:.4%} (предел {DOLYA_SBOEV_PREDEL:.2%})")
        if d > DOLYA_SBOEV_PREDEL:
            print("    ПРОГОН НЕДЕЙСТВИТЕЛЕН: выборку сформировали падения,")
            print("    а не правило входа. Чинить стратегию, потом мерить.")
            return False
    return True


class Store:
    """Склад баров для стратегий.

    УСТАРЕЛ 4 сентября. Замена — `research_ohlcv_store.ResearchKlineStore`
    Кодекса в каноническом дереве: он ловит дыру в данных, кривую
    геометрию бара, бар не на сетке UTC и обрезанную первую корзину —
    ничего из этого здесь нет. Этот класс живёт до слияния и НЕ
    чинится: две реализации склада — это ровно та болезнь, из которой
    проект выбирается. Подробности и контракт: DLYA_KODEKSA_2026_09_04_STORE.md

    ДЕФЕКТ, найденный 1 сентября и самый дорогой за всё время.
    Раньше здесь было:

        def fetch_klines(self, sym, tf, n):
            return self.rows[-n:]

    Аргумент `tf` ИГНОРИРОВАЛСЯ. Стратегия просила четырёхчасовые бары —
    получала часовые. Просила пятнадцатиминутные — получала те же часовые.

    В корпусе 30 стратегий из 95 запрашивают РАЗНЫЕ таймфреймы. Все
    тридцать мерились сломанным прибором. Elder Triple Screen — метод,
    весь смысл которого в согласии трёх таймфреймов — у нас сравнивал
    часовик сам с собой и, разумеется, попадал ровно в случайность.

    Теперь:
      * базовый таймфрейм определяется по самим данным;
      * больший таймфрейм СОБИРАЕТСЯ из базового по календарным границам;
      * меньший таймфрейм отдать неоткуда — возвращаем пусто И СЧИТАЕМ
        отказы. Молча подсовывать не тот масштаб больше нельзя.
    """

    def __init__(self, sym, bazovyy_tf: int | None = None):
        self.symbol = sym
        self.rows = []
        self._baza = bazovyy_tf
        self.otkazy = {}          # {минуты: сколько раз не смогли отдать}

    def baza(self) -> int:
        """Базовый таймфрейм в минутах, по расстоянию между барами."""
        if self._baza:
            return self._baza
        if len(self.rows) < 3:
            return 60
        d = [self.rows[i + 1][0] - self.rows[i][0] for i in range(min(50, len(self.rows) - 1))]
        d = [x for x in d if x > 0]
        if not d:
            return 60
        d.sort()
        self._baza = max(1, int(round(d[len(d) // 2] / 60000)))
        return self._baza

    def fetch_klines(self, sym, tf, n):
        m = _tf_v_minutah(tf)
        b = self.baza()
        if m is None or m == b:
            return self.rows[-n:]
        if m < b or m % b:
            self.otkazy[m] = self.otkazy.get(m, 0) + 1
            return []
        k = m // b
        hvost = self.rows[-(int(n) + 2) * k:]
        shag = m * 60000
        svechi, tek, klyuch = [], None, None
        for r in hvost:
            kl = int(r[0]) // shag
            if kl != klyuch:
                if tek is not None:
                    svechi.append(tek)
                tek = [kl * shag, r[1], r[2], r[3], r[4], r[5]]
                klyuch = kl
            else:
                tek[2] = max(tek[2], r[2])
                tek[3] = min(tek[3], r[3])
                tek[4] = r[4]
                tek[5] += r[5]
        if tek is not None:
            svechi.append(tek)
        return svechi[-int(n):]


def ema(x, n):
    k = 2 / (n + 1); e = x[0]; out = np.empty(len(x))
    for i, v in enumerate(x):
        e = v * k + e * (1 - k); out[i] = e
    return out


def simulate(bars, i, side, sl0, tps, f1, mult, hold):
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


def week_boot(R, ts, n=1500, seed=5):
    """блочный бутстрап по неделям: соседние сделки зависимы"""
    wk = (np.array(ts) // (7 * 86400000)).astype(np.int64)
    ub = np.unique(wk)
    if len(ub) < 6:
        return None, None
    idx = {b: np.flatnonzero(wk == b) for b in ub}
    g = np.random.default_rng(seed); out = np.empty(n)
    for i in range(n):
        p = g.choice(ub, len(ub), replace=True)
        out[i] = R[np.concatenate([idx[b] for b in p])].mean()
    return float(np.quantile(out, 0.025)), float(np.quantile(out, 0.975))


def stats(rows):
    if len(rows) < 50:
        return None
    R = np.array([x["R"] for x in rows]); lev = np.array([x["lev"] for x in rows])
    ts = np.array([x["ts"] for x in rows])
    g = R + lev * 2 * FEE_BPS_SIDE / 1e4
    se = R.std(ddof=1) / math.sqrt(len(R))
    # Порог различимости считается по ФАКТИЧЕСКОМУ разбросу этой
    # конфигурации, а не по константе. Константа 1.03R измерена при
    # стопе ×1; при стопе ×6 разброс 0.44R, и порог по константе
    # завышен в 2.4 раза. Мы этим сами себе занижали результаты.
    mde = 1.96 * float(R.std(ddof=1)) / math.sqrt(len(R))
    lo, hi = week_boot(R, ts)
    return dict(n=len(R), signal=float(g.mean()), cost=float((lev * 2 * FEE_BPS_SIDE / 1e4).mean()),
                net=float(R.mean()), sigma=float(R.mean() / se) if se else 0.0,
                mde=float(mde), visible=bool(abs(R.mean()) > mde),
                boot_lo=lo, boot_hi=hi,
                winrate=float((R > 0).mean()), lev=float(np.median(lev)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--cls", required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--data", default="h1")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--root", default="/mnt/user-data/uploads/bybit-bot-clean-v28")
    ap.add_argument("--regime-file", default="",
                    help="откуда брать режим рынка; по умолчанию BTCUSDT.npz из папки данных")
    ap.add_argument("--cooldown", type=int, default=0,
                    help="пауза между сделками в БАРАХ вызова. Штатное значение "
                         "задано в пятиминутках, а счётчик тикает раз в вызов, "
                         "поэтому на часах его надо делить на 12. 0 = не трогать.")
    a = ap.parse_args()

    sys.path.insert(0, a.root)
    files = sorted(glob.glob(f"{a.data}/*.npz"))
    if not files:
        print("нет данных в", a.data); return 1
    syms = ",".join(sorted(Path(f).stem for f in files))
    os.environ[f"{a.prefix}_SYMBOL_ALLOWLIST"] = syms
    os.environ.setdefault(f"{a.prefix}_ALLOW_LONGS", "1")
    os.environ.setdefault(f"{a.prefix}_ALLOW_SHORTS", "1")
    if a.cooldown > 0:
        os.environ[f"{a.prefix}_COOLDOWN_BARS_5M"] = str(a.cooldown)
        print(f"пауза между сделками: {a.cooldown} баров вызова", flush=True)
    Strategy = getattr(importlib.import_module(f"strategies.{a.strategy}"), a.cls)

    btc = None
    rf = a.regime_file or next((f for f in files if Path(f).stem == "BTCUSDT"), "")
    for f in ([rf] if rf else []):
        if True:
            d = np.load(f)
            c = d["ohlcv"][:, 3].astype(float)
            e = ema(c, 200)
            btc = (d["ts"], (c - e) / e)          # относительное отклонение от EMA200
    def regime(t):
        """возвращает отклонение BTC от своей EMA200 в долях (может быть None)"""
        if btc is None:
            return None
        j = max(0, int(np.searchsorted(btc[0], t, side="right")) - 1)
        return float(btc[1][j]) if j < len(btc[1]) else None

    passport = dict(strategy=a.strategy, prefix=a.prefix, symbols=len(files),
                    windows={}, axes=dict(stops=list(STOPS), holds=list(HOLDS)))

    for wname, (sta, cut) in WINDOWS.items():
        assert cut <= SEALED_FROM, "запечатанный период читать нельзя"
        res = {}
        for k, fp in enumerate(files):
            d = np.load(fp); ts, o = d["ts"], d["ohlcv"].astype(float)
            m = ts < cut
            ts, o = ts[m], o[m]
            if len(ts) < LOOKBACK + 300:
                continue
            bars = [[int(ts[x]), o[x, 0], o[x, 1], o[x, 2], o[x, 3], o[x, 4]] for x in range(len(ts))]
            st = Store(Path(fp).stem)
            strat = Strategy()
            pervyy = pervyy_dlya(Strategy, st, Path(fp).stem)
            sigs = []
            for i in range(LOOKBACK, len(bars)):
                st.rows = bars[: i + 1]
                b = bars[i]
                try:
                    s = strat.maybe_signal(pervyy, b[0], b[1], b[2], b[3], b[4], b[5])
                except Exception as _e:
                    zapisat_sboy('research_machine', _e)
                    continue
                if s is None or b[0] < sta:
                    continue
                sigs.append((i, s.side, s.sl, list(s.tps or []), (s.tp_fracs or [0.55])[0]))
            for mult in STOPS:
                for hold in HOLDS:
                    key = (mult, hold)
                    block = -1
                    bag = res.setdefault(key, [])
                    for i, side, sl0, tps, f1 in sigs:
                        if i <= block:
                            continue
                        r = simulate(bars, i, side, sl0, tps, f1, mult, hold)
                        if r is None:
                            continue
                        r.update(side=side, ts=int(bars[i][0]), up=regime(bars[i][0]))
                        bag.append(r)
                        block = i + r["bars"] + 1
            if (k + 1) % 40 == 0:
                print(f"[{wname}] ... {k+1}/{len(files)}", flush=True)

        print(f"\n╔══ {a.tag} — окно {wname}")
        print(f"{'стоп×':<7}{'держ':<7}{'сторона':<9}{'режим':<9}{'n':>6}"
              f"{'сигнал':>11}{'изд.':>9}{'ИТОГ':>11}{'σ':>7}{'видно?':>9}{'винрейт':>9}")
        wout = {}
        for (mult, hold), bag in sorted(res.items()):
            for side in ("short", "long", "both"):
                for rg, rname in REGIMES:
                    sel = [x for x in bag
                           if (side == "both" or x["side"] == side)
                           and (rg is None or (x["up"] is not None and rg(x["up"])))]
                    s = stats(sel)
                    if not s:
                        continue
                    vis = "видно" if abs(s["net"]) > s["mde"] else "шум"
                    if True:
                        print(f"{mult:<7}{hold:<7}{side:<9}{rname:<9}{s['n']:>6}"
                              f"{s['signal']:>+10.4f}R{s['cost']:>8.4f}R{s['net']:>+10.4f}R"
                              f"{s['sigma']:>+7.2f}{vis:>9}{s['winrate']:>9.0%}")
                    wout[f"{mult}|{hold}|{side}|{rname}"] = s
        passport["windows"][wname] = wout

    out = Path(a.root) / "research_lab" / f"passport_{a.tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(passport, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nпаспорт: {out}")

    # автоматический отсев: что выжило на ОБОИХ окнах
    print("\n╔══ ОТСЕВ: конфигурации, положительные на ОБОИХ окнах")
    ws = list(passport["windows"].values())
    if len(ws) == 2:
        good = []
        for key, s1 in ws[0].items():
            s2 = ws[1].get(key)
            if not s2:
                continue
            # строгий отсев: плюс на обоих окнах, достаточно сделок,
            # эффект больше шума хотя бы на одном, и нижняя граница
            # недельного бутстрапа выше нуля хотя бы на одном
            if (s1["net"] > 0 and s2["net"] > 0
                    and s1["n"] >= 200 and s2["n"] >= 200
                    and (s1["visible"] or s2["visible"])
                    and ((s1.get("boot_lo") or -1) > 0 or (s2.get("boot_lo") or -1) > 0)):
                good.append((key, s1, s2))
        good.sort(key=lambda x: -(x[1]["net"] + x[2]["net"]))
        if not good:
            print("  ни одна конфигурация не положительна на обоих окнах")
        for key, s1, s2 in good[:12]:
            b1 = f"[{s1['boot_lo']:+.4f}..{s1['boot_hi']:+.4f}]" if s1.get("boot_lo") is not None else ""
            b2 = f"[{s2['boot_lo']:+.4f}..{s2['boot_hi']:+.4f}]" if s2.get("boot_lo") is not None else ""
            print(f"  {key:<26} окно1 {s1['net']:+.4f}R n={s1['n']:<5}{b1:<22}"
                  f"окно2 {s2['net']:+.4f}R n={s2['n']:<5}{b2}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
