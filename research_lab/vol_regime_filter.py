"""РЕЖИМ ВОЛАТИЛЬНОСТИ КАК ФИЛЬТР ДЛЯ УЖЕ РАБОТАЮЩИХ НОГ.

Почему это ценнее новой ноги. Фильтр применяется ко ВСЕМ четырём ногам сразу,
не требует новой стратегии и опирается на уже доказанный эдж. Новая нога —
это месяцы до вердикта; фильтр — это правка гейта, который уже подключён
(`bot/strategy_regime_gate` работает и дал +5 к книге).

Сейчас гейт различает НАПРАВЛЕНИЕ рынка (бык/медведь/флэт). Он не различает
ВОЛАТИЛЬНОСТЬ. Вопрос: теряем ли мы на этом?

Гипотеза, которую проверяем: геометрия «отбой от базы» работает в спокойном
рынке и ломается в турбулентном — потому что при высокой волатильности
уровень перестаёт держать, а стоп выносится шумом.

Обратная гипотеза не менее правдоподобна: при высокой волатильности движения
крупнее, и отбой приносит больше R. Поэтому меряем, а не рассуждаем.

Режим волатильности определяется по BTC (общий для всех символов, как и
направленный режим): реализованная волатильность за 24 часа, ранг среди
предыдущих 30 дней. Ранг, а не абсолютный порог — иначе за 3 года
«высокая волатильность» уедет вместе с ценой BTC.

Важно: режим считается ТОЛЬКО по прошлым данным на момент входа.
Заглядывания вперёд нет.
"""
from __future__ import annotations

import glob
import json
import math
import os
import statistics
import sys

CACHE = "data_cache"


def load_h1(symbol: str):
    files = sorted(glob.glob(f"{CACHE}/{symbol}_5_*.json"),
                   key=os.path.getsize, reverse=True)
    if not files:
        return []
    agg = {}
    for b in json.load(open(files[0])):
        try:
            h = int(b["ts"]) // 3600000 * 3600000
            o, hi, lo, c = float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])
        except Exception:
            continue
        if h not in agg:
            agg[h] = [o, hi, lo, c]
        else:
            r = agg[h]
            r[1] = max(r[1], hi); r[2] = min(r[2], lo); r[3] = c
    return [(k, *v) for k, v in sorted(agg.items())]


def btc_vol_rank(btc):
    """{час -> ранг волатильности 0..1 среди предыдущих 30 дней}.

    ОПТИМИЗАЦИЯ. Первая версия считала pstdev заново для каждой из 120 точек
    истории на каждом баре — это O(n × 120 × 24) и падало по таймауту.
    Здесь скользящее стандартное отклонение считается один раз за проход
    через накопленные суммы, а ранг берётся по уже готовому массиву.
    """
    n = len(btc)
    rets = [0.0] * n
    for i in range(1, n):
        p0, p1 = btc[i - 1][4], btc[i][4]
        rets[i] = math.log(p1 / p0) if p0 > 0 and p1 > 0 else 0.0

    W = 24
    sd = [None] * n            # скользящее std за W баров
    s = s2 = 0.0
    for i in range(n):
        s += rets[i]
        s2 += rets[i] * rets[i]
        if i >= W:
            s -= rets[i - W]
            s2 -= rets[i - W] * rets[i - W]
        if i >= W - 1:
            var = s2 / W - (s / W) ** 2
            sd[i] = math.sqrt(var) if var > 0 else 0.0

    out = {}
    LB = 24 * 30
    for i in range(LB + W, n):
        cur = sd[i]
        if cur is None:
            continue
        hist = [sd[k] for k in range(i - LB, i, 6) if sd[k] is not None]
        if not hist:
            continue
        out[btc[i][0]] = sum(1 for h in hist if h < cur) / len(hist)
    return out


def run(hold, buffer, near, upleg, low_lb, side_mode):
    btc = load_h1("BTCUSDT")
    vol = btc_vol_rank(btc)
    syms = sorted({os.path.basename(f).split("_5_")[0]
                   for f in glob.glob(f"{CACHE}/*_5_*.json")})
    buckets = {"тихо (нижняя треть)": [], "средне": [], "БУРНО (верхняя треть)": []}
    for s in syms:
        bars = load_h1(s)
        if len(bars) < upleg + 300:
            continue
        for i in range(max(upleg, low_lb) + 1, len(bars) - hold - 2):
            c = bars[i][4]
            if side_mode == "long":
                if c <= bars[i - upleg][4]:
                    continue
                ref = min(b[3] for b in bars[i - low_lb + 1:i + 1])
                if ref <= 0 or (c / ref - 1.0) > near:
                    continue
                e = bars[i + 1][1]
                stop = ref * (1.0 - buffer)
                if e <= stop:
                    continue
                risk = e - stop
                seg = bars[i + 1:i + 1 + hold + 1]
                px = next((stop for b in seg if b[3] <= stop), seg[-1][4])
                r = (px - e) / risk
            else:
                if c >= bars[i - upleg][4]:
                    continue
                ref = max(b[2] for b in bars[i - low_lb + 1:i + 1])
                if ref <= 0 or (ref / c - 1.0) > near:
                    continue
                e = bars[i + 1][1]
                stop = ref * (1.0 + buffer)
                if e >= stop:
                    continue
                risk = stop - e
                seg = bars[i + 1:i + 1 + hold + 1]
                px = next((stop for b in seg if b[2] >= stop), seg[-1][4])
                r = (e - px) / risk
            v = vol.get(bars[i][0])
            if v is None:
                continue
            key = ("тихо (нижняя треть)" if v < 0.33
                   else "средне" if v < 0.67 else "БУРНО (верхняя треть)")
            buckets[key].append(r)

    name = "ОТБОЙ ОТ БАЗЫ (лонг)" if side_mode == "long" else "ОТБОЙ ОТ ПОТОЛКА (шорт)"
    print(f"{name} по режиму волатильности BTC, удержание {hold}ч")
    print(f"{'режим':<26}{'событий':>9}{'средн R':>10}{'винрейт':>10}{'t':>8}")
    for k in ("тихо (нижняя треть)", "средне", "БУРНО (верхняя треть)"):
        a = buckets[k]
        if len(a) < 40:
            print(f"{k:<26}{len(a):>9}   мало")
            continue
        m = statistics.fmean(a); sd = statistics.pstdev(a)
        wr = sum(1 for x in a if x > 0) / len(a) * 100
        print(f"{k:<26}{len(a):>9}{m:>+10.3f}{wr:>9.1f}%"
              f"{m/(sd/len(a)**0.5):>+8.2f}")


def run_beta_removed(hold, near, upleg, low_lb, side_mode):
    """То же самое, но со СНЯТИЕМ РЫНКА.

    Зачем отдельная функция. Первая версия дала красивую перевёрнутую U
    на лонгах (t=+7.39) и ОБРАТНУЮ картину на шортах. Асимметрия — признак
    того, что мерялось направление рынка, а не режим волатильности:
    выборка росла, вспышки волатильности совпадали с падениями.

    Здесь из результата вычитается равновзвешенная доходность ВСЕХ монет
    за тот же период удержания. Остаётся то, что рынком не объясняется.

    Меряется простая доходность за фиксированное окно, БЕЗ стопа: вопрос
    «есть ли направленный эдж сверх рынка», а не «сколько R снимем».
    Стоп делает результат зависимым от пути и мешает чистому снятию беты.
    """
    syms = sorted({os.path.basename(f).split("_5_")[0]
                   for f in glob.glob(f"{CACHE}/*_5_*.json")})
    bars = {s: load_h1(s) for s in syms}
    bars = {s: b for s, b in bars.items() if len(b) > upleg + 300}
    vol = btc_vol_rank(bars.get("BTCUSDT") or [])
    idx = {s: {row[0]: i for i, row in enumerate(b)} for s, b in bars.items()}

    def market_ret(ts, h):
        rs = []
        for s, b in bars.items():
            i = idx[s].get(ts)
            if i is None or i + h >= len(b):
                continue
            o, c = b[i][1], b[i + h][4]
            if o > 0:
                rs.append(c / o - 1.0)
        return statistics.fmean(rs) if len(rs) >= 5 else None

    buckets = {"тихо": [], "средне": [], "БУРНО": []}
    for s, b in bars.items():
        for i in range(max(upleg, low_lb) + 1, len(b) - hold - 2):
            c = b[i][4]
            if side_mode == "long":
                if c <= b[i - upleg][4]:
                    continue
                ref = min(x[3] for x in b[i - low_lb + 1:i + 1])
                if ref <= 0 or (c / ref - 1.0) > near:
                    continue
                sign = 1.0
            else:
                if c >= b[i - upleg][4]:
                    continue
                ref = max(x[2] for x in b[i - low_lb + 1:i + 1])
                if ref <= 0 or (ref / c - 1.0) > near:
                    continue
                sign = -1.0
            if i + 1 + hold >= len(b):
                continue
            o = b[i + 1][1]
            if o <= 0:
                continue
            raw = b[i + 1 + hold][4] / o - 1.0
            m = market_ret(b[i + 1][0], hold)
            v = vol.get(b[i][0])
            if m is None or v is None:
                continue
            key = "тихо" if v < 0.33 else ("средне" if v < 0.67 else "БУРНО")
            buckets[key].append(sign * (raw - m) * 10000)

    name = "ЛОНГ от базы" if side_mode == "long" else "ШОРТ от потолка"
    print(f"{name} — СВЕРХ РЫНКА, удержание {hold}ч, без стопа")
    print(f"{'режим':<12}{'событий':>9}{'избыточно bps':>16}{'плюсовых':>11}{'t':>8}")
    for k in ("тихо", "средне", "БУРНО"):
        a = buckets[k]
        if len(a) < 40:
            print(f"{k:<12}{len(a):>9}   мало")
            continue
        m = statistics.fmean(a)
        sd = statistics.pstdev(a)
        pos = sum(1 for x in a if x > 0) / len(a) * 100
        print(f"{k:<12}{len(a):>9}{m:>+16.1f}{pos:>10.0f}%"
              f"{m/(sd/len(a)**0.5):>+8.2f}")


if __name__ == "__main__":
    hold = int(sys.argv[1]) if len(sys.argv) > 1 else 48
    mode = sys.argv[2] if len(sys.argv) > 2 else "long"
    if len(sys.argv) > 3 and sys.argv[3] == "beta":
        run_beta_removed(hold, near=0.02, upleg=240, low_lb=120, side_mode=mode)
    else:
        run(hold, buffer=0.025, near=0.02, upleg=240, low_lb=120, side_mode=mode)
