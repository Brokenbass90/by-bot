#!/usr/bin/env python3
"""ПОЧЕМУ НЕ ВХОДИТ: какой именно порог держит стратегию.

    python3 research_lab/strategy_gate_ablation.py sloped_resistance_choch_v1
    python3 research_lab/strategy_gate_ablation.py alt_support_bounce_v1 SOLUSDT 20000

Механически перебирает КАЖДЫЙ числовой и булев параметр конфига, ослабляет
его по очереди и считает, сколько сигналов это разблокирует. Сортирует по
эффекту. Никаких моделей и догадок — только «отпустил ручку, стало N».

КАК ЧИТАТЬ
  ручка даёт большой прирост   -> она и есть связывающее ограничение;
  все ручки дают ноль          -> дело не в порогах, а в структуре
                                  (баг, недостижимая ветка, единицы измерения);
  прирост только у одной ручки -> остальные фильтры декоративны.

ВАЖНО, ЧТОБЫ НЕ ОБМАНУТЬСЯ
  Больше сигналов НЕ значит лучше. Проверено на squeeze-ноге: «починка»
  утроила число сигналов и увела результат с +0.13R/сд в −0.04R/сд.
  Этот инструмент отвечает на вопрос «что держит», а не «что улучшит».
  Любое найденное ослабление обязано проверяться прогоном на R.
"""
from __future__ import annotations

import copy
import glob
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

# два множителя вместо четырёх: каждый — полный проход по барам,
# при 40 ручках четвёрка превращается в 160 проходов и часы
MULTS = (0.0, 20.0)


def load_candles(symbol: str, limit: int):
    from backtest.engine import Candle
    best, n = None, 0
    for p in glob.glob(f"data_cache/{symbol}_5_*.json"):
        try:
            rows = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:
            continue
        if len(rows) > n:
            best, n = rows, len(rows)
    out = []
    for x in (best or [])[:limit]:
        if isinstance(x, dict):
            out.append(Candle(ts=int(float(x["ts"])), o=float(x["o"]), h=float(x["h"]),
                              l=float(x["l"]), c=float(x["c"]), v=float(x.get("v", 0) or 0)))
        else:
            out.append(Candle(ts=int(float(x[0])), o=float(x[1]), h=float(x[2]),
                              l=float(x[3]), c=float(x[4]),
                              v=float(x[5]) if len(x) > 5 else 0.0))
    return out


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "sloped_resistance_choch_v1"
    symbol = sys.argv[2] if len(sys.argv) > 2 else "SOLUSDT"
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 8000

    from backtest.engine import KlineStore
    mod = importlib.import_module(f"strategies.{name}")
    classes = [getattr(mod, n) for n in dir(mod) if isinstance(getattr(mod, n), type)
               and any(hasattr(getattr(mod, n), m) for m in ("maybe_signal", "evaluate"))]
    if not classes:
        print("класс стратегии не найден")
        return 1
    cls = classes[0]
    entry = "maybe_signal" if hasattr(cls, "maybe_signal") else "evaluate"

    cs = load_candles(symbol, limit)
    if len(cs) < 2000:
        print(f"мало данных по {symbol}")
        return 1

    probe = cls()
    cfg = getattr(probe, "cfg", None)
    if cfg is None:
        print("у стратегии нет .cfg — ablation неприменим "
              "(параметры в self.params: используй env-свип)")
        return 1

    fields = [(k, v) for k, v in vars(cfg).items()
              if isinstance(v, (int, float, bool)) and not k.startswith("_")]

    def count(overrides: dict) -> int:
        store = KlineStore(symbol, cs, base_interval_min=5)
        s = cls()
        for k, v in overrides.items():
            setattr(s.cfg, k, v)
        n = 0
        for i in range(len(cs)):
            store.i5 = i; store.i = i; store.i_base = i
            try:
                if entry == "maybe_signal":
                    r = s.maybe_signal(store, cs[i].ts, cs[i].o, cs[i].h, cs[i].l, cs[i].c, cs[i].v)
                else:
                    r = s.evaluate(store, i)
                if r is not None:
                    n += 1
            except Exception:
                pass
        return n

    base = count({})
    days = len(cs) * 5 / 1440
    print(f"{name}   {symbol}   {len(cs)} баров ({days:.0f} дней)")
    print(f"базовое число сигналов: {base}\n")

    print(f"ручек к проверке: {len(fields)}   (печатаю по ходу, порядок — как в конфиге)\n")
    print(f"{'ручка':<32}{'было':>12}{'стало':>12}{'сигналов':>10}{'прирост':>9}", flush=True)
    results = []
    for k, v in fields:
        best_n, best_v = base, None
        if isinstance(v, bool):
            n = count({k: not v})
            if n > best_n:
                best_n, best_v = n, not v
        else:
            for m in MULTS:
                nv = type(v)(v * m) if v else type(v)(m)
                if nv == v:
                    continue
                n = count({k: nv})
                if n > best_n:
                    best_n, best_v = n, nv
        if best_v is not None:
            results.append((best_n - base, k, v, best_v, best_n))
            print(f"{k:<32}{str(v):>12}{str(best_v):>12}{best_n:>10}{best_n - base:>+9}", flush=True)

    if not results:
        print("НИ ОДНА ручка не добавляет сигналов.")
        print("Значит дело не в порогах, а в структуре: недостижимая ветка,")
        print("баг единиц измерения или условие, противоречащее самому себе.")
        print("Дальше: research_lab/strategy_liveness_probe.py — он покажет,")
        print("какие строки не выполняются ни разу.")
        return 0

    results.sort(reverse=True)
    print("\n── ИТОГ, по силе эффекта:")
    for d, k, old, new, n in results[:15]:
        print(f"{k:<32}{str(old):>12}{str(new):>12}{n:>10}{d:>+9}")

    print(f"\nСВЯЗЫВАЮЩЕЕ ОГРАНИЧЕНИЕ: {results[0][1]}")
    print("Больше сигналов НЕ значит лучше — проверять прогоном на R.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
